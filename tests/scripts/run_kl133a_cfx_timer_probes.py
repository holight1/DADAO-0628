#!/usr/bin/env python3
"""KL-133a dual-backend probes: cfx_hart_cycle_lo (cg8/rc2, new per-instruction
-retired counter) and cfx_timer counter0 (cg10, decrement/one-shot/periodic
state machine per contracts/isa/spec.md §8.5.2), on top of KL-131a's generic
maskable async dispatch core.

Reuses run_kl131a_async_dispatch_probes.py's helpers (boot stub, vector/mask
setters, craft_inner_cfx_mask, register-compare accumulator, QEMU/gem5
runners) rather than re-implementing them -- see that module's docstring for
the underlying SEE §5 mechanics this task's TIMER cause rides on unchanged.

The cycle counter advances only after successful architectural retirement.
The retire-fault scenario uses a real PTW permission fault plus escape to
prove the faulting load does not count while the successful handler escape
does. Timer expiry is created by the Nth subsequent retirement and delivered
at the following instruction boundary, before an UNIMP poison executes.

Reentrance hazard this module's handler design works around (rediscovered
independently here, same root cause as KL-131a's own scenario-B design
notes): SEE §5 says "taking an interrupt does not implicitly clear the
[pending] bit -- software must clear it". Right after entry, cfx_timer is a
*self*-target (inner_cfx_code == cfx_timer), which bypasses the
inner_cfx_mask/global_cfx_mask routing checks entirely -- only
excp_cause_mask (step5) still gates it. If a handler's first instruction
clears the *private* pending latch before the *common* one (a literal
reading of wiki L650-660's device-source ack order), the private timer
source remains asserted and the common cause bit is re-latched at every
following instruction boundary.
The very next boundary can therefore re-deliver the *same* cause, sending
control right back to the handler's start before it reaches the private
acknowledge. Observed directly as an infinite
`dadao: trap cfx=18 ... cause_ip=0x100804` loop during development. The fix
mirrors KL-131a's established pattern exactly: the handler's FIRST
instruction unconditionally masks its own excp_cause_mask using a value
pre-loaded into ALLONES_REG before anything becomes eligible (no
value-construction window), which blocks redelivery regardless of pending
state; only then does it drain pending (private, then common, matching the
wiki's prescribed order) and escape.

Tick-accounting design: this module tracks successful retirements via
len(out) bookkeeping for straight-line, non-faulting regions, anchored via
an empirically-verified boot-stub instruction count (BOOT_INSN_COUNT, cross-
checked against gem5 -- see this task's completion notes for the diagnostic).
ticks_at()/Anchor below let every scenario place poison markers at *exactly*
the computed expiry tick without any hand-derived instruction counts,
including across a handler-detour (whose own instruction count is folded
into a fresh anchor after each escape).
"""

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_kl131a_async_dispatch_probes as kl131a  # noqa: E402
import run_kl127a_ptw_fault_ad_probes as kl127a  # noqa: E402
from build_test_binary import load_reg, UNIMP_ENCODING  # noqa: E402

ROM_BASE = kl131a.ROM_BASE
EVIDENCE = os.path.join(kl131a.REPO, ".work", "evidence", "kl133a-probes")
SUPV_ENTRY_OFFSET = kl131a.SUPV_ENTRY_OFFSET
MASK_ALL = kl131a.MASK_ALL
MODE_SUPV = kl131a.MODE_SUPV
CFX_POWER = kl131a.CFX_POWER
CFX_PTW = kl131a.CFX_PTW
CFX_TIMER = kl131a.CFX_TIMER
CG_FRAME = kl131a.CG_FRAME
RC_FRAME_CAUSE_ID = kl131a.RC_FRAME_CAUSE_ID
RC_FRAME_CAUSE_IP = kl131a.RC_FRAME_CAUSE_IP
CG_COMMON = kl131a.CG_COMMON
RC_PENDING = kl131a.RC_PENDING
RC_EXCP_ASYNC_NUM = kl131a.RC_EXCP_ASYNC_NUM
RC_EXCP_CAUSE_MASK = kl131a.RC_EXCP_CAUSE_MASK
OP_CFX2RC = kl131a.OP_CFX2RC
OP_CFX2RD = kl131a.OP_CFX2RD
OP_ESCAPE = kl131a.OP_ESCAPE
OP_HALT = kl131a.OP_HALT
OP_MISC = kl131a.OP_MISC
MISC_ORR = kl131a.MISC_ORR

# --- KL-133a new register addressing (cg,rc), matching cpu.h/isa.hh exactly ---
CFX_HART = 15
CG_HART = 8
RC_HART_CYCLE_LO = 2

CG_TIMER = 10
RC_TIMER_PENDING = 0
RC_TIMER_MASK = 1
RC_TIMER_CTRL = 7
RC_TIMER_REG0 = 8

TIMER_CTRL_ENABLE = 1 << 0
TIMER_CTRL_PERIODIC = 1 << 1
CAUSE_TIMER = 1 << 10

TRAMP_OFFSET = 0x800
ALLONES_REG = 10
HANDLER_LEN = 4  # mask-self + clear-private-pending + clear-common-pending + escape

# Empirically verified (diagnostic binary, both backends agreeing that a
# cfx2rd immediately after boot observes BOOT_INSN_COUNT): number of REAL
# (non-padding) instructions emit_boot_stub() executes from reset to
# supv_entry. Derived from its own source rather than hardcoded blindly:
# load_reg(rd,2,0) [4] + one write_crrr per CFX_DELEG_TARGETS entry +
# (load_reg[4]+write_crrr[1]) x3 (prev_run_mode/prev_cfx_mask/cause_ip) +
# escape[1].
BOOT_INSN_COUNT = 4 + len(kl131a.o1.CFX_DELEG_TARGETS) + (4 + 1) * 3 + 1
assert BOOT_INSN_COUNT == 32, BOOT_INSN_COUNT


def filler(out):
    """Single harmless instruction (`orr rd3, rd3, rd3`) -- one tick, no
    side effect on the mismatch accumulator (rd29) or any scratch register
    used elsewhere in this module."""
    kl131a.write_orrr(out, MISC_ORR, 3, 3, 3)


class Anchor:
    """Tracks absolute "ticks executed since reset" via len(out) bookkeeping.
    Valid for straight-line code; call retarget() after any handler-detour
    (poison-preemption + trampoline + escape) with the handler's exact
    instruction count, since those instructions are not part of `out`'s own
    byte offsets."""

    def __init__(self, out, pos, tick):
        self.out = out
        self.pos = pos
        self.tick = tick

    def before_next(self):
        """Ticks executed strictly before the next instruction to be
        emitted at the current len(out)."""
        assert (len(self.out) - self.pos) % 4 == 0
        return self.tick + (len(self.out) - self.pos) // 4

    def retarget(self, extra_ticks=HANDLER_LEN):
        """Call immediately after resuming from a handler-detour (i.e. right
        after appending the poison word, before appending the first resumed
        instruction). `extra_ticks` = the handler's own instruction count.
        The poison/faulting instruction was fetched but did not retire, so
        its physical slot must be removed from len(out)'s linear count.
        Every successful handler instruction, including escape, did retire."""
        self.tick = self.before_next() - 1 + extra_ticks
        self.pos = len(self.out)

    def place_poison_at(self, target_tick):
        """Retire fillers through `target_tick`, then emit an UNIMP poison.

        Timer expiry is produced by retirement of the last filler and is
        delivered at the following boundary, before the poison executes.
        timeout=0 therefore uses target_tick == before_next() and emits no
        filler at all."""
        remaining = target_tick - self.before_next()
        if remaining < 0:
            raise ValueError(
                f"target_tick {target_tick} not ahead of current position "
                f"(before_next={self.before_next()})")
        for _ in range(remaining):
            filler(self.out)
        assert self.before_next() == target_tick
        addr = ROM_BASE + len(self.out)
        self.out.extend(struct.pack(">I", UNIMP_ENCODING))
        return addr


def set_timer_ctrl(out, value, scratch=2):
    load_reg(out, "rd", scratch, value)
    kl131a.write_crrr(out, OP_CFX2RC, CFX_TIMER, CG_TIMER, RC_TIMER_CTRL, scratch)


def set_timer_counter0(out, value, scratch=2):
    load_reg(out, "rd", scratch, value)
    kl131a.write_crrr(out, OP_CFX2RC, CFX_TIMER, CG_TIMER, RC_TIMER_REG0, scratch)


def set_timer_mask(out, value, scratch=2):
    load_reg(out, "rd", scratch, value)
    kl131a.write_crrr(out, OP_CFX2RC, CFX_TIMER, CG_TIMER, RC_TIMER_MASK, scratch)


def read_cycle_lo_check(out, expected):
    kl131a.read_reg_check(out, CFX_HART, CG_HART, RC_HART_CYCLE_LO, expected)


def read_timer_check(out, rc, expected):
    kl131a.read_reg_check(out, CFX_TIMER, CG_TIMER, rc, expected)


def setup_timer_delivery_path(out):
    """Common prelude for every scenario that needs cfx_timer to actually be
    able to deliver: vector, step5 (excp_cause_mask), step3 (global_cfx_mask),
    escape-mask permission for the craft_inner_cfx_mask carrier, private
    cfx_timer_mask, ALLONES_REG pre-load (see module docstring's reentrance
    fix -- must happen before anything becomes eligible), and finally
    inner_cfx_mask itself (step2/routing) last -- matches KL-131a's own
    established ordering rationale (only the last unmask can make anything
    eligible, so every earlier step is safe regardless of what's pending)."""
    tramp_timer = ROM_BASE + TRAMP_OFFSET
    kl131a.set_vector(out, CFX_TIMER, tramp_timer)
    kl131a.set_excp_cause_mask(out, CFX_TIMER, MODE_SUPV, MASK_ALL & ~CAUSE_TIMER)
    kl131a.set_global_mask(out, MODE_SUPV, MASK_ALL & ~(1 << CFX_TIMER))
    kl131a.set_escape_mask(out, CFX_POWER, MODE_SUPV, MASK_ALL & ~(1 << CFX_PTW))
    set_timer_mask(out, 0)
    load_reg(out, "rd", ALLONES_REG, MASK_ALL)
    kl131a.craft_inner_cfx_mask(out, CFX_PTW, MASK_ALL & ~(1 << CFX_TIMER))
    return tramp_timer


def emit_timer_handler(out, tramp_offset=TRAMP_OFFSET):
    """The one safe handler body every scenario below uses. Exactly
    HANDLER_LEN=4 instructions -- this count is load-bearing for every
    Anchor.retarget() call in this module:
      1. mask self (excp_cause_mask[TIMER][SUPV] := ALLONES_REG) -- blocks
         any redelivery immediately, before the pending drain below (see
         module docstring's reentrance-hazard writeup).
      2. clear private pending (rd0 W0C).
      3. clear common pending (rd0 W0C) -- wiki L650-660 order (private
         before common), now safe since step 1 already removed eligibility.
      4. escape,1 (resumes past the poison slot).
    """
    while len(out) < tramp_offset:
        out.extend(struct.pack(">I", UNIMP_ENCODING))
    assert len(out) == tramp_offset
    kl131a.write_crrr(out, OP_CFX2RC, CFX_TIMER, MODE_SUPV, RC_EXCP_CAUSE_MASK,
                       ALLONES_REG)
    kl131a.write_crrr(out, OP_CFX2RC, CFX_TIMER, CG_TIMER, RC_TIMER_PENDING, 0)
    kl131a.write_crrr(out, OP_CFX2RC, CFX_TIMER, CG_COMMON, RC_PENDING, 0)
    kl131a.write_ciii(out, OP_ESCAPE, CFX_TIMER, 1)


# =====================================================================
# Scenario 1: cfx_hart_cycle_lo -- general per-instruction-retired counter
# =====================================================================

PASS_CYCLE, FAIL_CYCLE = 133, 0x9C


def gen_cycle_lo():
    out = bytearray()
    supv_entry = ROM_BASE + SUPV_ENTRY_OFFSET
    kl131a.emit_boot_stub(out, supv_entry)
    pos_after_boot = len(out)
    anchor = Anchor(out, pos_after_boot, BOOT_INSN_COUNT)

    load_reg(out, "rd", 29, 0)  # mismatch accumulator

    # First reading: a nontrivial absolute value (not 0/1), computed via the
    # anchor rather than hand-derived.
    # cfx2rd observes the count before that successful instruction itself
    # retires; the retirement hook runs after execute.
    base_expected = anchor.before_next()
    read_cycle_lo_check(out, base_expected)

    # Exactly 17 filler instructions (an arbitrary, nontrivial count).
    FILLER_N = 17
    for _ in range(FILLER_N):
        filler(out)

    second_expected = anchor.before_next()
    read_cycle_lo_check(out, second_expected)

    # Independent cross-check: the two expected values are not just
    # separately "correct" against the anchor, they must differ by exactly
    # (7 [base's own read_reg_check body] + FILLER_N) -- read_reg_check emits
    # cfx2rd[1] + check_eq[load_reg(4)+xor(1)+orr(1)=6] = 7 words.
    assert second_expected - base_expected == 7 + FILLER_N

    # A third reading after a DIFFERENT filler count, confirming monotonic
    # (not merely "some fixed delta twice by coincidence").
    FILLER_N2 = 5
    for _ in range(FILLER_N2):
        filler(out)
    third_expected = anchor.before_next()
    read_cycle_lo_check(out, third_expected)
    assert third_expected - second_expected == 7 + FILLER_N2
    assert third_expected > second_expected > base_expected > 0

    kl131a.emit_final_halt(out, PASS_CYCLE, FAIL_CYCLE)
    return bytes(out)


# =====================================================================
# Scenario 1b: precise fault is not retired; handler escape is retired
# =====================================================================

PASS_RETIRE_FAULT = kl127a.PASS


def gen_retire_fault():
    fields = kl127a.build_fault_fixture(
        "NRPERM", "permission", "read", 0)
    out = bytearray()
    load_reg(out, "rd", 29, 0)
    kl127a.cfx_write(
        out, kl127a.CFX_PTW, 2, 10, ROM_BASE + kl127a.HANDLER_OFFSET)
    kl127a.cfx_write(
        out, kl127a.CFX_PTW, kl127a.PTW_PTBR_CG, fields["index"],
        fields["l1_base"] >> 16)
    kl127a.cfx_write(
        out, kl127a.CFX_PTW, kl127a.PTW_PTHI_CG, fields["index"], 0)
    kl127a.cfx_write(
        out, kl127a.CFX_PTW, kl127a.PTW_PAHI_CG, fields["index"], 0)
    kl127a.cfx_write(
        out, kl127a.CFX_PTW, kl127a.PTW_PERM_CG,
        kl127a.PTW_ENABLE_RC, 1 << fields["index"])
    kl127a.emit_mode_switch(out, kl127a.MODE_HYPV)

    executed_to_fault_block = len(out) // 4
    kl127a.pad_to(out, kl127a.FAULT_OFFSET)
    anchor = Anchor(out, len(out), executed_to_fault_block)

    before_fault = anchor.before_next()
    read_cycle_lo_check(out, before_fault)

    load_reg(out, "rb", 3, fields["va"])
    fault_addr = ROM_BASE + len(out)
    kl127a.write_rrii(out, kl127a.OP_LDO, 3, 3, 0)
    anchor.retarget(extra_ticks=1)

    after_fault = anchor.before_next()
    read_cycle_lo_check(out, after_fault)
    assert after_fault - before_fault == 7 + 3 + 1
    kl131a.read_reg_check(out, kl127a.CFX_PTW, CG_FRAME,
                          RC_FRAME_CAUSE_ID, fields["cause"])
    kl131a.read_reg_check(out, kl127a.CFX_PTW, CG_FRAME,
                          RC_FRAME_CAUSE_IP, fault_addr)

    kl131a.emit_final_halt(out, PASS_RETIRE_FAULT, kl127a.FAIL)

    while len(out) < kl127a.HANDLER_OFFSET:
        out.extend(struct.pack(">I", UNIMP_ENCODING))
    assert len(out) == kl127a.HANDLER_OFFSET
    kl131a.write_ciii(out, OP_ESCAPE, kl127a.CFX_PTW, 1)
    return bytes(out), fields["image"]


# =====================================================================
# Scenario 2: one-shot, N>0 and N==0 -- exact-tick expiry, auto-disable, W0C
# =====================================================================

PASS_ONE_SHOT, FAIL_ONE_SHOT = 134, 0x9D
PASS_ONE_SHOT_ZERO, FAIL_ONE_SHOT_ZERO = 135, 0x9E


def _gen_one_shot_case(pass_code, fail_code, n_timeout):
    out = bytearray()
    supv_entry = ROM_BASE + SUPV_ENTRY_OFFSET
    kl131a.emit_boot_stub(out, supv_entry)
    anchor = Anchor(out, len(out), BOOT_INSN_COUNT)

    load_reg(out, "rd", 29, 0)
    setup_timer_delivery_path(out)

    set_timer_counter0(out, n_timeout)
    set_timer_ctrl(out, TIMER_CTRL_ENABLE)  # one-shot, decrement, enable
    k_tick = anchor.before_next()  # ticks through the ctrl-write, inclusive

    # Nonzero N expires after N subsequently retired instructions; zero is
    # already expired and is delivered at the boundary immediately after
    # the arming write.
    target_tick = k_tick + n_timeout
    poison_addr = anchor.place_poison_at(target_tick)
    anchor.retarget()

    kl131a.read_reg_check(out, CFX_TIMER, CG_FRAME, RC_FRAME_CAUSE_ID, CAUSE_TIMER)
    kl131a.read_reg_check(out, CFX_TIMER, CG_FRAME, RC_FRAME_CAUSE_IP, poison_addr)
    kl131a.read_reg_check(out, CFX_TIMER, CG_COMMON, RC_EXCP_ASYNC_NUM, 1)
    read_timer_check(out, RC_TIMER_CTRL, 0)  # one-shot auto-disabled
    read_timer_check(out, RC_TIMER_PENDING, 0)  # cleared by handler
    kl131a.read_reg_check(out, CFX_TIMER, CG_COMMON, RC_PENDING, 0)  # cleared

    kl131a.emit_final_halt(out, pass_code, fail_code)

    emit_timer_handler(out)
    return bytes(out)


def gen_one_shot():
    return _gen_one_shot_case(PASS_ONE_SHOT, FAIL_ONE_SHOT, 5)


def gen_one_shot_zero():
    return _gen_one_shot_case(PASS_ONE_SHOT_ZERO, FAIL_ONE_SHOT_ZERO, 0)


# =====================================================================
# Scenario 3: periodic -- reload, enable preserved, two precise expiries
# =====================================================================

PASS_PERIODIC, FAIL_PERIODIC = 136, 0x9F


def gen_periodic():
    out = bytearray()
    supv_entry = ROM_BASE + SUPV_ENTRY_OFFSET
    kl131a.emit_boot_stub(out, supv_entry)
    anchor = Anchor(out, len(out), BOOT_INSN_COUNT)

    load_reg(out, "rd", 29, 0)
    setup_timer_delivery_path(out)

    # Keep a full period comfortably longer than the immediate post-handler
    # checks. This prevents a verification sequence from manufacturing a
    # stale second expiry; the second period below is explicitly re-armed
    # and independently timed.
    N = 64
    set_timer_counter0(out, N)
    set_timer_ctrl(out, TIMER_CTRL_ENABLE | TIMER_CTRL_PERIODIC)
    k1_tick = anchor.before_next()
    target1 = k1_tick + N
    poison1_addr = anchor.place_poison_at(target1)
    anchor.retarget()

    # The expiry reloads N. Four successful handler instructions retire
    # before resume, so the first read sees exactly N-HANDLER_LEN.
    read_timer_check(out, RC_TIMER_REG0, N - HANDLER_LEN)
    # Freeze countdown while validating period 1. This is an actual ctrl
    # transition, not a widened assertion window.
    set_timer_ctrl(out, 0)
    kl131a.read_reg_check(out, CFX_TIMER, CG_FRAME, RC_FRAME_CAUSE_ID, CAUSE_TIMER)
    kl131a.read_reg_check(out, CFX_TIMER, CG_FRAME, RC_FRAME_CAUSE_IP, poison1_addr)
    kl131a.read_reg_check(out, CFX_TIMER, CG_COMMON, RC_EXCP_ASYNC_NUM, 1)
    read_timer_check(out, RC_TIMER_PENDING, 0)
    kl131a.read_reg_check(out, CFX_TIMER, CG_COMMON, RC_PENDING, 0)

    # Re-arm period 2 from disabled state. The ctrl write's own retirement
    # does not consume the new counter; exactly N successful fillers do.
    set_timer_counter0(out, N)
    kl131a.set_excp_cause_mask(out, CFX_TIMER, MODE_SUPV, MASK_ALL & ~CAUSE_TIMER)
    set_timer_ctrl(out, TIMER_CTRL_ENABLE | TIMER_CTRL_PERIODIC)
    k2_tick = anchor.before_next()

    target2 = k2_tick + N
    poison2_addr = anchor.place_poison_at(target2)
    anchor.retarget()

    # --- Resume 2: verify second expiry, exactly N ticks after the second
    #     re-arm point, enable/mode still preserved ---
    kl131a.read_reg_check(out, CFX_TIMER, CG_FRAME, RC_FRAME_CAUSE_ID, CAUSE_TIMER)
    kl131a.read_reg_check(out, CFX_TIMER, CG_FRAME, RC_FRAME_CAUSE_IP, poison2_addr)
    kl131a.read_reg_check(out, CFX_TIMER, CG_COMMON, RC_EXCP_ASYNC_NUM, 2)
    read_timer_check(out, RC_TIMER_CTRL, TIMER_CTRL_ENABLE | TIMER_CTRL_PERIODIC)

    kl131a.emit_final_halt(out, PASS_PERIODIC, FAIL_PERIODIC)

    emit_timer_handler(out)
    return bytes(out)


# =====================================================================
# Scenario 4: cfx_timer_mask -- expiry-while-masked sets pending only;
# unmasking delivers on the very next boundary
# =====================================================================

PASS_MASK, FAIL_MASK = 137, 0xA0


def gen_mask():
    out = bytearray()
    supv_entry = ROM_BASE + SUPV_ENTRY_OFFSET
    kl131a.emit_boot_stub(out, supv_entry)
    anchor = Anchor(out, len(out), BOOT_INSN_COUNT)

    load_reg(out, "rd", 29, 0)

    tramp_timer = ROM_BASE + TRAMP_OFFSET
    kl131a.set_vector(out, CFX_TIMER, tramp_timer)
    kl131a.set_excp_cause_mask(out, CFX_TIMER, MODE_SUPV, MASK_ALL & ~CAUSE_TIMER)
    kl131a.set_global_mask(out, MODE_SUPV, MASK_ALL & ~(1 << CFX_TIMER))
    kl131a.set_escape_mask(out, CFX_POWER, MODE_SUPV, MASK_ALL & ~(1 << CFX_PTW))
    load_reg(out, "rd", ALLONES_REG, MASK_ALL)
    kl131a.craft_inner_cfx_mask(out, CFX_PTW, MASK_ALL & ~(1 << CFX_TIMER))
    # Deliberately do NOT clear cfx_timer_mask -- stays at its reset default
    # (all-1 == masked, wiki L590 "0=可触发,1=屏蔽").

    N = 4
    set_timer_counter0(out, N)
    set_timer_ctrl(out, TIMER_CTRL_ENABLE)
    k_tick = anchor.before_next()
    target = k_tick + N

    # No poison here -- masked, so this instruction genuinely executes
    # (proving "no entry", not merely "we didn't check for one").
    remaining = target - anchor.before_next()
    for _ in range(remaining):
        filler(out)
    assert anchor.before_next() == target

    # Expiry has happened (private+common pending set, ctrl auto-disabled --
    # unconditional of the mask per contracts/isa/spec.md §8.5.2) but was
    # never delivered: inner_cfx_code is still cfx_power (unchanged) and
    # cfx_timer's own frame cause_id was never written (still its reset
    # value, 0).
    kl131a.read_reg_check(out, CFX_TIMER, CG_FRAME, RC_FRAME_CAUSE_ID, 0)
    read_timer_check(out, RC_TIMER_PENDING, 1)
    kl131a.read_reg_check(out, CFX_TIMER, CG_COMMON, RC_PENDING, CAUSE_TIMER)
    read_timer_check(out, RC_TIMER_CTRL, 0)  # auto-disabled despite masking

    # W0C mechanics sanity: writing 1 must PRESERVE a set pending bit
    # (W0C, not W1C) before we actually clear it with 0.
    load_reg(out, "rd", 2, 1)
    kl131a.write_crrr(out, OP_CFX2RC, CFX_TIMER, CG_TIMER, RC_TIMER_PENDING, 2)
    read_timer_check(out, RC_TIMER_PENDING, 1)  # unchanged

    # Now unmask the private gate -- delivery becomes eligible immediately
    # (pending is already latched); expect entry at the very next boundary.
    set_timer_mask(out, 0)
    unmask_tick = anchor.before_next()
    poison_addr = anchor.place_poison_at(unmask_tick)
    anchor.retarget()

    kl131a.read_reg_check(out, CFX_TIMER, CG_FRAME, RC_FRAME_CAUSE_ID, CAUSE_TIMER)
    kl131a.read_reg_check(out, CFX_TIMER, CG_FRAME, RC_FRAME_CAUSE_IP, poison_addr)
    kl131a.read_reg_check(out, CFX_TIMER, CG_COMMON, RC_EXCP_ASYNC_NUM, 1)
    read_timer_check(out, RC_TIMER_PENDING, 0)
    kl131a.read_reg_check(out, CFX_TIMER, CG_COMMON, RC_PENDING, 0)

    kl131a.emit_final_halt(out, PASS_MASK, FAIL_MASK)

    emit_timer_handler(out)
    return bytes(out)


# =====================================================================
# Scenario 5: private timer source re-latches the common TIMER cause
# =====================================================================

PASS_RELATCH, FAIL_RELATCH = 138, 0xA1


def gen_relatch():
    out = bytearray()
    supv_entry = ROM_BASE + SUPV_ENTRY_OFFSET
    kl131a.emit_boot_stub(out, supv_entry)
    anchor = Anchor(out, len(out), BOOT_INSN_COUNT)

    load_reg(out, "rd", 29, 0)
    # Leave cfx_timer_mask at reset all-ones so pending can be inspected
    # without delivery. The source must re-latch common pending regardless
    # of this mask and regardless of one-shot auto-disable.
    set_timer_counter0(out, 1)
    set_timer_ctrl(out, TIMER_CTRL_ENABLE)
    target = anchor.before_next() + 1
    while anchor.before_next() < target:
        filler(out)

    read_timer_check(out, RC_TIMER_CTRL, 0)
    read_timer_check(out, RC_TIMER_PENDING, 1)
    kl131a.read_reg_check(out, CFX_TIMER, CG_COMMON, RC_PENDING, CAUSE_TIMER)

    # W0C-clear only common TIMER while private bit0 remains asserted.
    load_reg(out, "rd", 2, MASK_ALL & ~CAUSE_TIMER)
    kl131a.write_crrr(out, OP_CFX2RC, CFX_TIMER, CG_COMMON, RC_PENDING, 2)
    # Before this read executes, the following boundary scan must reconstruct
    # common TIMER from the still-asserted private source.
    kl131a.read_reg_check(out, CFX_TIMER, CG_COMMON, RC_PENDING, CAUSE_TIMER)

    # Acknowledge private first, then common. With the source deasserted, the
    # next boundary must leave common TIMER clear.
    kl131a.write_crrr(out, OP_CFX2RC, CFX_TIMER, CG_TIMER, RC_TIMER_PENDING, 0)
    kl131a.write_crrr(out, OP_CFX2RC, CFX_TIMER, CG_COMMON, RC_PENDING, 2)
    read_timer_check(out, RC_TIMER_PENDING, 0)
    kl131a.read_reg_check(out, CFX_TIMER, CG_COMMON, RC_PENDING, 0)

    kl131a.emit_final_halt(out, PASS_RELATCH, FAIL_RELATCH)
    return bytes(out)


# =====================================================================

SCENARIOS = [
    ("cycle-lo", gen_cycle_lo, PASS_CYCLE, False),
    ("retire-fault", gen_retire_fault, PASS_RETIRE_FAULT, True),
    ("one-shot", gen_one_shot, PASS_ONE_SHOT, False),
    ("one-shot-zero", gen_one_shot_zero, PASS_ONE_SHOT_ZERO, False),
    ("periodic", gen_periodic, PASS_PERIODIC, False),
    ("mask", gen_mask, PASS_MASK, False),
    ("relatch", gen_relatch, PASS_RELATCH, False),
]


def main():
    kl131a.EVIDENCE = EVIDENCE
    kl127a.EVIDENCE = EVIDENCE
    results = []
    for name, gen_fn, expect, ptw_fault in SCENARIOS:
        generated = gen_fn()
        if ptw_fault:
            raw, ram = generated
            os.makedirs(EVIDENCE, exist_ok=True)
            rom_path = os.path.join(EVIDENCE, name + ".bin")
            ram_path = os.path.join(EVIDENCE, name + "-ram.bin")
            with open(rom_path, "wb") as stream:
                stream.write(raw)
            with open(ram_path, "wb") as stream:
                stream.write(ram)
            kl127a.run_backend(name, "qemu", rom_path, ram_path)
            kl127a.run_backend(name, "gem5", rom_path, ram_path)
            results.append(f"{name}=OK({expect})")
            continue
        else:
            raw = generated
            q = kl131a.run_qemu(name, raw)
            g = kl131a.run_gem5(name, raw)
        assert q.returncode == expect, (
            f"QEMU {name}: {q.returncode}, expected {expect}\n"
            f"{q.stderr[-4000:]}")
        assert g.returncode == expect, (
            f"gem5 {name}: {g.returncode}, expected {expect}\n"
            f"{g.stdout[-2000:]}")
        assert kl131a.gem5_code(g.stdout) == expect, g.stdout[-2000:]
        results.append(f"{name}=OK({expect})")

    print("PASS: " + " ".join(results))


if __name__ == "__main__":
    main()
