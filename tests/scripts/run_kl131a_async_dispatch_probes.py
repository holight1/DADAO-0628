#!/usr/bin/env python3
"""KL-131a dual-backend probes: SEE §5 steps 2-6 mask/pending/priority
arbitration gating KL-122a's steps 7-10 carrier, plus the new
instruction-boundary asynchronous dispatch mechanism.

Every binary starts with the verbatim HBI §3 hypv->supv handoff stub
(gen_kl110a_o1_probe.py, already independently verified by O1/O2/O3) so
tests begin at a stable `supv_entry` point: inner_run_mode=SUPV(2),
inner_cfx_code=POWER(63), inner_cfx_mask=ALL-1 (the stub's own crafted
`escape cfx_power,0` self-escape restores exactly this state -- see that
module's docstring). All binaries are flat ROM images loaded at
ROM_BASE=0x00100000, run identically under QEMU (`-M dadao-m1 -bios`) and
gem5 FullSystem (`dadao_fs.py`, KL-124a's bare-metal carrier) -- no ELF
wrapper or address translation needed since both use the same flat layout.

Scenario groups:
  A. sync_masks   -- steps 2/3/4/5 exercised via the TEST-ONLY synchronous
                      dispatch trigger (cg4/rc60): nonmaskable bypass (PTW/
                      NUPERM), inner_cfx_mask block -> ILLI (UART0 from
                      default all-1 inner mask), global_cfx_mask block ->
                      ILLI isolated from inner_cfx_mask via the
                      escape-crafted mask technique (see craft_inner_cfx_mask
                      below) with a same-target A/B contrast proving it is
                      specifically the global mask, and excp_cause_mask block
                      -> pending (self-target, SOFT_RESET). Verifies
                      cfx_trap_num/excp_sync_num/excp_async_num counters at
                      each step.
  B. async_flow    -- real instruction-boundary asynchronous delivery using
                      two independent TEST-ONLY synthetic level sources:
                      boundary-precise cause_ip, cross-cfx priority (hart(15)
                      before uart(62)), same-cfx multi-cause priority (UART0
                      before UART5), and electrics re-latch (pending reasserts
                      itself across a boundary while the source is still
                      configured, independent of a software W0C clear).

The escape-crafted-mask technique: cfx2rc has no direct write path for raw
inner_cfx_mask (it is only ever set by cfxPreciseTrapEnter's hardcoded
switch_cfx_mask=ALL-1, or restored by `escape` from a frame's prev_cfx_mask,
which cg5/rc1 IS software-writable). Pre-populating an unrelated cfx's frame
(prev_run_mode/prev_cfx_mask/cause_ip) and then performing a *cross-cfx*
escape into it (permitted via that cfx's escape_cfx_mask bit) restores
inner_cfx_mask to an arbitrary crafted value while leaving inner_cfx_code
unchanged (non-self escapes do not touch inner_cfx_code, SEE §5 exit flow
step 1-2 vs the E1 self-escape carve-out) -- a legitimate composition of two
already-frozen instructions (`cfx2rc` cg5 writes, KL-120a; `escape`,
KL-112a), not a new mechanism.
"""

import os
import re
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
QEMU = os.environ.get(
    "QEMU_DADAO",
    os.path.join(REPO, ".work", "source", "qemu", "build",
                 "qemu-system-dadao"))
GEM5_DIR = os.path.expanduser("~/DADAO-gem5")
GEM5_TESTS = os.path.join(GEM5_DIR, "tests", "dadao")
GEM5 = os.environ.get(
    "GEM5_OPT", os.path.join(GEM5_DIR, "build", "DADAO", "gem5.opt"))
GEM5_FS_CFG = os.environ.get(
    "GEM5_FS", os.path.join(GEM5_TESTS, "dadao_fs.py"))
EVIDENCE = os.path.join(REPO, ".work", "evidence", "kl131a-probes")

sys.path.insert(0, HERE)
from build_test_binary import load_reg, UNIMP_ENCODING  # noqa: E402
import gen_kl110a_o1_probe as o1  # noqa: E402

ROM_BASE = 0x00100000
SUPV_ENTRY_OFFSET = 0x200

OP_CFX2RC = 0x73
OP_CFX2RD = 0x72
OP_ESCAPE = 0x77
OP_HALT = 0x00
OP_MISC = 0x10
MISC_ORR = 0x09
MISC_XOR = 0x0A
OP_CSZ = 0x22
OP_LDO = 0x33
OP_STO = 0x3B

CFX_UMON, CFX_JMON, CFX_SMON, CFX_HMON = 0, 1, 2, 3
CFX_PTW, CFX_TLB = 4, 5
CFX_HART = 15
CFX_TIMER = 18
CFX_UART = 62
CFX_POWER = 63

MODE_SUPV = 2

CAUSE_CFXTRAP = 1 << 0
CAUSE_ILLI = 1 << 8
CAUSE_NUPERM = 1 << 8        # cfx_ptw, nonmaskable
CAUSE_UART0 = 1 << 32
CAUSE_UART5 = 1 << 37
CAUSE_SOFT_RESET = 1 << 10   # cfx_power
CAUSE_IPI = 1 << 8           # cfx_hart

RC_GLOBAL_MASK = 1
RC_EXCP_VECTOR = 10
RC_EXCP_CAUSE_MASK = 11
CG_FRAME = 5
RC_FRAME_PREV_RUN_MODE = 0
RC_FRAME_PREV_CFX_MASK = 1
RC_FRAME_CAUSE_ID = 2
RC_FRAME_CAUSE_IP = 3
RC_FRAME_CAUSE_INFO = 4
RC_ESCAPE_MASK = 7
CG_COMMON = 4
RC_PENDING = 7
RC_TRAP_NUM = 2
RC_EXCP_SYNC_NUM = 3
RC_EXCP_ASYNC_NUM = 4
CG_TEST_SYNC = 4
RC_TEST_SYNC = 60

MASK_ALL = 0xFFFFFFFFFFFFFFFF


def write_crrr(out, op, ha, hb, hc, hd):
    w = (op << 24) | ((ha & 0x3F) << 18) | ((hb & 0x3F) << 12) | \
        ((hc & 0x3F) << 6) | (hd & 0x3F)
    out.extend(struct.pack(">I", w))


def write_ciii(out, op, ha, imm18):
    imm18 &= 0x3FFFF
    hb = (imm18 >> 12) & 0x3F
    hc = (imm18 >> 6) & 0x3F
    hd = imm18 & 0x3F
    w = (op << 24) | ((ha & 0x3F) << 18) | (hb << 12) | (hc << 6) | hd
    out.extend(struct.pack(">I", w))


def write_orrr(out, minor, dst, lhs, rhs):
    w = (OP_MISC << 24) | ((minor & 0x3F) << 18) | ((dst & 0x3F) << 12) | \
        ((lhs & 0x3F) << 6) | (rhs & 0x3F)
    out.extend(struct.pack(">I", w))


def emit_boot_stub(out, supv_entry):
    """Verbatim HBI §3 power->supv handoff (gen_kl110a_o1_probe.py), padded
    to SUPV_ENTRY_OFFSET. Lands at supv_entry with inner_run_mode=SUPV(2),
    inner_cfx_code=POWER(63), inner_cfx_mask=ALL-1."""
    load_reg(out, "rd", 2, 0)
    for _name, cfxcode in o1.CFX_DELEG_TARGETS:
        write_crrr(out, OP_CFX2RC, cfxcode, 3, 12, 2)
    load_reg(out, "rd", 2, 2)
    write_crrr(out, OP_CFX2RC, CFX_POWER, CG_FRAME, RC_FRAME_PREV_RUN_MODE, 2)
    load_reg(out, "rd", 2, MASK_ALL)
    write_crrr(out, OP_CFX2RC, CFX_POWER, CG_FRAME, RC_FRAME_PREV_CFX_MASK, 2)
    load_reg(out, "rd", 2, supv_entry)
    write_crrr(out, OP_CFX2RC, CFX_POWER, CG_FRAME, RC_FRAME_CAUSE_IP, 2)
    write_ciii(out, OP_ESCAPE, CFX_POWER, 0)
    if len(out) > SUPV_ENTRY_OFFSET:
        raise ValueError("boot stub overflowed SUPV_ENTRY_OFFSET")
    while len(out) < SUPV_ENTRY_OFFSET:
        out.extend(struct.pack(">I", UNIMP_ENCODING))
    assert len(out) == SUPV_ENTRY_OFFSET


def set_vector(out, cfxcode, addr, scratch=2):
    """SEE §3 cg2/rc10 per-cfx supv excp vector (KL-116a write support)."""
    load_reg(out, "rd", scratch, addr)
    write_crrr(out, OP_CFX2RC, cfxcode, 2, RC_EXCP_VECTOR, scratch)


def set_excp_cause_mask(out, cfxcode, mode, value, scratch=2):
    load_reg(out, "rd", scratch, value)
    write_crrr(out, OP_CFX2RC, cfxcode, mode, RC_EXCP_CAUSE_MASK, scratch)


def set_global_mask(out, mode, value, scratch=2):
    load_reg(out, "rd", scratch, value)
    # cfxcode field is ignored for the shared global mask -- use cfxcode=0.
    write_crrr(out, OP_CFX2RC, 0, mode, RC_GLOBAL_MASK, scratch)


def set_escape_mask(out, cfxcode, mode, value, scratch=2):
    load_reg(out, "rd", scratch, value)
    write_crrr(out, OP_CFX2RC, cfxcode, mode, RC_ESCAPE_MASK, scratch)


def check_eq(out, actual_reg, expected_value, acc_reg=29, tmp_reg=28):
    """acc_reg |= (actual_reg ^ expected_value)."""
    load_reg(out, "rd", tmp_reg, expected_value)
    write_orrr(out, MISC_XOR, tmp_reg, actual_reg, tmp_reg)
    write_orrr(out, MISC_ORR, acc_reg, acc_reg, tmp_reg)


def read_reg_check(out, cfxcode, cg, rc, expected, val_reg=27, acc_reg=29):
    write_crrr(out, OP_CFX2RD, cfxcode, cg, rc, val_reg)
    check_eq(out, val_reg, expected, acc_reg)


def emit_final_halt(out, pass_code, fail_code, acc_reg=29):
    """halt with pass_code if acc_reg==0, else fail_code."""
    load_reg(out, "rd", 25, pass_code)
    load_reg(out, "rd", 26, fail_code)
    w = (OP_CSZ << 24) | (acc_reg << 18) | (24 << 12) | (25 << 6) | 26
    out.extend(struct.pack(">I", w))
    out.extend(struct.pack(">I", (OP_HALT << 24) | (24 << 18)))


def test_sync_trigger(out, cfxcode, cause, scratch=5):
    """TEST-ONLY: cfx2rc cfxcode, cg4, rc60, cause -> dadao_cfx_dispatch(...,
    is_sync=true). See cpu.h's DADAO_CFX_TEST_SYNC_DISPATCH_RC comment."""
    load_reg(out, "rd", scratch, cause)
    write_crrr(out, OP_CFX2RC, cfxcode, CG_TEST_SYNC, RC_TEST_SYNC, scratch)


def craft_inner_cfx_mask(out, carrier_cfx, mask_value, scratch=2):
    """Restore inner_cfx_mask to `mask_value` via a non-self escape through
    `carrier_cfx`'s frame (see module docstring). Caller must have already
    cleared the current cfx's escape_cfx_mask bit for carrier_cfx. Resumes
    immediately after this call (inner_run_mode=SUPV, inner_cfx_code
    unchanged); load_reg always emits a fixed 4 rd-words regardless of
    value, so the escape target address is exactly computable in advance."""
    load_reg(out, "rd", scratch, MODE_SUPV)
    write_crrr(out, OP_CFX2RC, carrier_cfx, CG_FRAME,
               RC_FRAME_PREV_RUN_MODE, scratch)
    load_reg(out, "rd", scratch, mask_value)
    write_crrr(out, OP_CFX2RC, carrier_cfx, CG_FRAME,
               RC_FRAME_PREV_CFX_MASK, scratch)
    escape_addr = ROM_BASE + len(out) + 4 * 4 + 4
    load_reg(out, "rd", scratch, escape_addr)
    write_crrr(out, OP_CFX2RC, carrier_cfx, CG_FRAME,
               RC_FRAME_CAUSE_IP, scratch)
    assert ROM_BASE + len(out) == escape_addr, "address bookkeeping bug"
    write_ciii(out, OP_ESCAPE, carrier_cfx, 1)


PASS_A, FAIL_A = 131, 0x9A


def gen_scenario_a():
    """Steps 2/3/4/5 via the TEST-ONLY synchronous dispatch trigger."""
    out = bytearray()
    supv_entry = ROM_BASE + SUPV_ENTRY_OFFSET
    emit_boot_stub(out, supv_entry)

    TRAMP_OFFSET = 0x800
    TRAMP_SLOT = 0x20  # each trampoline gets a fixed 32-byte slot
    tramp_ptw = ROM_BASE + TRAMP_OFFSET + 0 * TRAMP_SLOT
    tramp_smon = ROM_BASE + TRAMP_OFFSET + 1 * TRAMP_SLOT
    tramp_power = ROM_BASE + TRAMP_OFFSET + 2 * TRAMP_SLOT
    tramp_uart = ROM_BASE + TRAMP_OFFSET + 3 * TRAMP_SLOT

    load_reg(out, "rd", 29, 0)  # mismatch accumulator

    set_vector(out, CFX_PTW, tramp_ptw)
    set_vector(out, CFX_SMON, tramp_smon)
    set_vector(out, CFX_POWER, tramp_power)
    set_vector(out, CFX_UART, tramp_uart)
    # Permit a power->ptw cross escape for the mask-crafting technique below.
    set_escape_mask(out, CFX_POWER, MODE_SUPV, MASK_ALL & ~(1 << CFX_PTW))

    # --- A1: step 2, nonmaskable bypass (cfx_ptw NUPERM) ---
    test_sync_trigger(out, CFX_PTW, CAUSE_NUPERM)
    read_reg_check(out, CFX_PTW, CG_FRAME, RC_FRAME_CAUSE_ID, CAUSE_NUPERM)
    read_reg_check(out, CFX_PTW, CG_COMMON, RC_TRAP_NUM, 0)
    read_reg_check(out, CFX_PTW, CG_COMMON, RC_EXCP_SYNC_NUM, 1)
    read_reg_check(out, CFX_PTW, CG_COMMON, RC_EXCP_ASYNC_NUM, 0)

    # --- A2: step 3, default inner_cfx_mask (ALL-1) blocks cross-cfx UART0
    #     -> redirected to ILLI @ current-mode monitor (SUPV -> cfx_smon) ---
    test_sync_trigger(out, CFX_UART, CAUSE_UART0)
    read_reg_check(out, CFX_SMON, CG_FRAME, RC_FRAME_CAUSE_ID, CAUSE_ILLI)
    read_reg_check(out, CFX_SMON, CG_COMMON, RC_EXCP_SYNC_NUM, 1)
    read_reg_check(out, CFX_UART, CG_COMMON, RC_TRAP_NUM, 0)
    read_reg_check(out, CFX_UART, CG_COMMON, RC_EXCP_SYNC_NUM, 0)
    read_reg_check(out, CFX_UART, CG_COMMON, RC_PENDING, 0)

    # --- A3: isolate step 4. Craft inner_cfx_mask with bit62(uart) CLEARED
    #     (so step 3 now passes); global_cfx_mask[SUPV] stays at its ALL-1
    #     default (still blocks uart) -> same ILLI outcome, but now provably
    #     via step 4 since step 3 was just eliminated for this bit. ---
    craft_inner_cfx_mask(out, CFX_PTW, MASK_ALL & ~(1 << CFX_UART))
    test_sync_trigger(out, CFX_UART, CAUSE_UART0)
    read_reg_check(out, CFX_SMON, CG_FRAME, RC_FRAME_CAUSE_ID, CAUSE_ILLI)
    read_reg_check(out, CFX_SMON, CG_COMMON, RC_EXCP_SYNC_NUM, 2)
    read_reg_check(out, CFX_UART, CG_COMMON, RC_TRAP_NUM, 0)
    read_reg_check(out, CFX_UART, CG_COMMON, RC_EXCP_SYNC_NUM, 0)

    # --- A3 positive control: ALSO clear global_cfx_mask[SUPV] bit62 AND
    #     excp_cause_mask[uart][SUPV] bit32 (step 5 -- UART0's own cause bit
    #     -- is independent of steps 3/4 and still defaults to all-1/blocked)
    #     -> all three checks now pass -> entry succeeds for real. This
    #     contrast (A3 blocked vs A3-control succeeding, differing only in
    #     global_cfx_mask) is what isolates step 4 as the specific blocker
    #     in A3, since step 3 was already eliminated before both attempts. ---
    craft_inner_cfx_mask(out, CFX_PTW, MASK_ALL & ~(1 << CFX_UART))
    set_global_mask(out, MODE_SUPV, MASK_ALL & ~(1 << CFX_UART))
    set_excp_cause_mask(out, CFX_UART, MODE_SUPV, MASK_ALL & ~CAUSE_UART0)
    test_sync_trigger(out, CFX_UART, CAUSE_UART0)
    read_reg_check(out, CFX_UART, CG_FRAME, RC_FRAME_CAUSE_ID, CAUSE_UART0)
    read_reg_check(out, CFX_UART, CG_COMMON, RC_EXCP_SYNC_NUM, 1)
    read_reg_check(out, CFX_SMON, CG_COMMON, RC_EXCP_SYNC_NUM, 2)  # unchanged

    set_global_mask(out, MODE_SUPV, MASK_ALL)  # restore default

    # --- A4: step 5 (excp_cause_mask) blocks a self-target (POWER/
    #     SOFT_RESET) -> OR into pending, no entry (sync also just latches
    #     pending on a step-5 block per wiki step 5's pseudocode). ---
    test_sync_trigger(out, CFX_POWER, CAUSE_SOFT_RESET)
    read_reg_check(out, CFX_POWER, CG_COMMON, RC_PENDING, CAUSE_SOFT_RESET)
    read_reg_check(out, CFX_POWER, CG_COMMON, RC_TRAP_NUM, 0)
    read_reg_check(out, CFX_POWER, CG_COMMON, RC_EXCP_SYNC_NUM, 0)

    # Clear the pending latch A4 just set BEFORE unmasking+retriggering
    # below. This is not merely tidiness: leaving it set would mean the
    # instant excp_cause_mask is cleared, POWER/SOFT_RESET is *simultaneously*
    # pending, self-targeted (routing-mask-exempt), and unmasked -- eligible
    # for the asynchronous scan too, one instruction-boundary check before
    # the synchronous trigger even runs. Since entering via the synchronous
    # path never touches pending (only a blocked attempt does), clearing it
    # here keeps this positive control a clean single-path (sync-only) entry
    # with nothing left in pending afterward for scenario B to inherit.
    load_reg(out, "rd", 2, 0)
    write_crrr(out, OP_CFX2RC, CFX_POWER, CG_COMMON, RC_PENDING, 2)

    # --- A4 positive control: clear excp_cause_mask[POWER][SUPV] bit10 and
    #     retrigger -> entry now succeeds. ---
    set_excp_cause_mask(out, CFX_POWER, MODE_SUPV, MASK_ALL & ~(1 << 10))
    test_sync_trigger(out, CFX_POWER, CAUSE_SOFT_RESET)
    read_reg_check(out, CFX_POWER, CG_FRAME, RC_FRAME_CAUSE_ID,
                    CAUSE_SOFT_RESET)
    read_reg_check(out, CFX_POWER, CG_COMMON, RC_EXCP_SYNC_NUM, 1)
    read_reg_check(out, CFX_POWER, CG_COMMON, RC_PENDING, 0)

    emit_final_halt(out, PASS_A, FAIL_A)

    while len(out) < TRAMP_OFFSET:
        out.extend(struct.pack(">I", UNIMP_ENCODING))
    assert len(out) == TRAMP_OFFSET

    def emit_trampoline_slot(body_fn):
        start = len(out)
        body_fn()
        if len(out) - start > TRAMP_SLOT:
            raise ValueError("trampoline body overflowed its slot")
        while len(out) - start < TRAMP_SLOT:
            out.extend(struct.pack(">I", UNIMP_ENCODING))

    emit_trampoline_slot(lambda: write_ciii(out, OP_ESCAPE, CFX_PTW, 1))
    emit_trampoline_slot(lambda: write_ciii(out, OP_ESCAPE, CFX_SMON, 1))
    emit_trampoline_slot(lambda: write_ciii(out, OP_ESCAPE, CFX_POWER, 1))
    emit_trampoline_slot(lambda: write_ciii(out, OP_ESCAPE, CFX_UART, 1))
    return bytes(out)


PASS_B, FAIL_B = 132, 0x9B

OP_BRNZ = 0x2B
OP_BREQ = 0x2E


def write_riii(out, op, ha, imm18):
    imm18 &= 0x3FFFF
    hb = (imm18 >> 12) & 0x3F
    hc = (imm18 >> 6) & 0x3F
    hd = imm18 & 0x3F
    w = (op << 24) | ((ha & 0x3F) << 18) | (hb << 12) | (hc << 6) | hd
    out.extend(struct.pack(">I", w))


def gen_scenario_b():
    """Real instruction-boundary asynchronous delivery: boundary-precise
    cause_ip, cross-cfx priority (hart(15) before uart(62)), same-cfx
    multi-cause priority (UART0 before UART5), and electrics re-latch.

    Design note (see the task completion notes for the full debugging
    story -- this went through three iterations before converging):

    1. A handler that reads/verifies *before* re-masking its own cause
       hangs: inner_cfx_mask auto-resets to ALL-1 on any entry (step 8),
       but that only blocks *other* cfxcodes -- a same-cfx redelivery is a
       self-target and bypasses steps 3-4 entirely. With a persistent
       always-reasserting test source, the still-pending, still-unmasked
       cause re-fires after the handler's very first (non-masking)
       instruction, forever.

    2. A handler that re-masks first, but builds the mask value in the
       handler itself (e.g. load a register, then write it) still hangs:
       precise instruction-boundary checking runs *between every single
       instruction*, so the gap between "build the value" and "write the
       register" is itself an exploitable window for the same
       self-redelivery, and it never converges (checked-and-still-eligible
       every single time, forever) with a maximally adversarial always-on
       source.

    3. A handler that escapes immediately (no masking at all) and defers
       all masking to the *resumed* context still hangs for a different
       reason: `escape` restores inner_cfx_mask from the frame's
       prev_cfx_mask, which was captured as the *already-unmasked* value
       that let the handler in in the first place (step 7 saves whatever
       inner_cfx_mask was immediately before entry) -- so resuming does
       NOT give a fresh blocking state, it gives back the same unmasked
       one, and the just-serviced cfx (now a cross-cfx target again) keeps
       being cross-cfx-eligible.

    The convergent fix: pre-load a register (rd10=ALL-1) in the *safe*
    zone before any unmasking happens (nothing is eligible yet, so this is
    unconditionally safe regardless of instruction count). Each handler's
    very FIRST instruction then atomically (a) masks its own
    excp_cause_mask using that pre-loaded value -- no window, since the
    value was already sitting in a register before entry -- and its
    SECOND instruction overwrites its own frame's prev_cfx_mask with the
    same ALL-1 value, so escaping restores a fully-blocking inner_cfx_mask
    instead of the stale unmasked one. Only then does it read/verify, mask
    a *specific* sub-bit if needed, and escape. Each subsequent unmask is a
    deliberate, single, atomic craft_inner_cfx_mask() call from the safe
    resumed context, re-enabling exactly the next cfx that should fire.
    """
    out = bytearray()
    supv_entry = ROM_BASE + SUPV_ENTRY_OFFSET
    emit_boot_stub(out, supv_entry)

    TRAMP_OFFSET = 0x800
    TRAMP_SLOT = 0x10
    tramp_hart = ROM_BASE + TRAMP_OFFSET + 0 * TRAMP_SLOT
    tramp_uart = ROM_BASE + TRAMP_OFFSET + 1 * TRAMP_SLOT
    ALLONES_REG = 10

    load_reg(out, "rd", 29, 0)  # mismatch accumulator

    set_vector(out, CFX_HART, tramp_hart)
    set_vector(out, CFX_UART, tramp_uart)
    # Permit power->ptw cross escape for the mask-crafting technique.
    set_escape_mask(out, CFX_POWER, MODE_SUPV, MASK_ALL & ~(1 << CFX_PTW))
    # Pre-load the ALL-1 mask value BEFORE anything becomes eligible, so
    # every trampoline's first two instructions are pure register-sourced
    # writes with no value-construction window. See the design note above.
    load_reg(out, "rd", ALLONES_REG, MASK_ALL)

    # --- Electrics part 1: both sources are active but everything stays
    #     masked by default (inner_cfx_mask=ALL-1, cross-cfx from POWER) ->
    #     pending latches anyway (relatch happens regardless of masking),
    #     but nothing is delivered (still executing sequentially here). ---
    read_reg_check(out, CFX_HART, CG_COMMON, RC_PENDING, CAUSE_IPI)
    read_reg_check(out, CFX_UART, CG_COMMON, RC_PENDING,
                    CAUSE_UART0 | CAUSE_UART5)

    # --- Electrics part 2: W0C-clear hart's pending, cross one boundary
    #     (any instruction), then observe it reasserted -- proves the
    #     relatch happens independently of a software clear attempt, not
    #     merely "software never got around to clearing it". Safe here:
    #     hart is still fully masked (inner_cfx_mask default), so this
    #     never becomes eligible regardless of pending's value. ---
    load_reg(out, "rd", 2, 0)
    write_crrr(out, OP_CFX2RC, CFX_HART, CG_COMMON, RC_PENDING, 2)
    load_reg(out, "rd", 3, 0)  # crosses a boundary; result unused
    read_reg_check(out, CFX_HART, CG_COMMON, RC_PENDING, CAUSE_IPI)

    # --- Prerequisite unmasking (safe: inner_cfx_mask still ALL-1, blocking
    #     both hart and uart regardless of these per-cause/global writes). ---
    set_excp_cause_mask(out, CFX_HART, MODE_SUPV, MASK_ALL & ~CAUSE_IPI)
    set_excp_cause_mask(out, CFX_UART, MODE_SUPV,
                         MASK_ALL & ~CAUSE_UART0 & ~CAUSE_UART5)
    set_global_mask(
        out, MODE_SUPV, MASK_ALL & ~(1 << CFX_HART) & ~(1 << CFX_UART))

    # --- Unmask hart+uart together (one atomic inner_cfx_mask update) ->
    #     both simultaneously eligible-and-pending. Lower cfxcode (hart=15)
    #     must be delivered first (contracts/isa/spec.md §8.5.1), with
    #     cause_ip==markA (this instruction never executes; delivery
    #     preempts it). ---
    craft_inner_cfx_mask(
        out, CFX_PTW, MASK_ALL & ~(1 << CFX_HART) & ~(1 << CFX_UART))
    markA = ROM_BASE + len(out)
    out.extend(struct.pack(">I", UNIMP_ENCODING))  # never executes

    # Resumed after hart's trampoline (masks itself + fixes prev_cfx_mask +
    # escapes -- see tramp_hart_body below). inner_cfx_mask is now fully
    # blocking again; safe to read/verify regardless of instruction count.
    read_reg_check(out, CFX_HART, CG_FRAME, RC_FRAME_CAUSE_ID, CAUSE_IPI)
    read_reg_check(out, CFX_HART, CG_FRAME, RC_FRAME_CAUSE_IP, markA)
    read_reg_check(out, CFX_HART, CG_COMMON, RC_EXCP_ASYNC_NUM, 1)
    read_reg_check(out, CFX_HART, CG_COMMON, RC_TRAP_NUM, 0)

    # --- Unmask uart alone (hart's bit stays 1=blocked this time) -> only
    #     uart is eligible; same-cfx priority picks the lower set bit
    #     (UART0) first. cause_ip==markB. ---
    craft_inner_cfx_mask(out, CFX_PTW, MASK_ALL & ~(1 << CFX_UART))
    markB = ROM_BASE + len(out)
    out.extend(struct.pack(">I", UNIMP_ENCODING))  # never executes

    read_reg_check(out, CFX_UART, CG_FRAME, RC_FRAME_CAUSE_ID, CAUSE_UART0)
    read_reg_check(out, CFX_UART, CG_FRAME, RC_FRAME_CAUSE_IP, markB)
    read_reg_check(out, CFX_UART, CG_COMMON, RC_EXCP_ASYNC_NUM, 1)
    # Re-unmask JUST UART5 (UART0 stays masked from tramp_uart's own
    # first-instruction full mask) -- safe, uart is currently blocked by
    # inner_cfx_mask (its own trampoline fixed prev_cfx_mask to ALL-1).
    set_excp_cause_mask(out, CFX_UART, MODE_SUPV, MASK_ALL & ~CAUSE_UART5)

    # --- Unmask uart again -> only UART5 is eligible this time -- proves
    #     the priority scan tries each *eligible* set bit in ascending
    #     order, not just the globally lowest set bit regardless of mask.
    #     cause_ip==markC. ---
    craft_inner_cfx_mask(out, CFX_PTW, MASK_ALL & ~(1 << CFX_UART))
    markC = ROM_BASE + len(out)
    out.extend(struct.pack(">I", UNIMP_ENCODING))  # never executes

    read_reg_check(out, CFX_UART, CG_FRAME, RC_FRAME_CAUSE_ID, CAUSE_UART5)
    read_reg_check(out, CFX_UART, CG_FRAME, RC_FRAME_CAUSE_IP, markC)
    read_reg_check(out, CFX_UART, CG_COMMON, RC_EXCP_ASYNC_NUM, 2)

    # Full cleanup (defensive; inner_cfx_mask's ALL-1 default already blocks
    # everything at this point regardless).
    set_global_mask(out, MODE_SUPV, MASK_ALL)

    emit_final_halt(out, PASS_B, FAIL_B)

    while len(out) < TRAMP_OFFSET:
        out.extend(struct.pack(">I", UNIMP_ENCODING))
    assert len(out) == TRAMP_OFFSET

    def emit_slot(body_fn):
        start = len(out)
        body_fn()
        if len(out) - start > TRAMP_SLOT:
            raise ValueError("trampoline body overflowed its slot")
        while len(out) - start < TRAMP_SLOT:
            out.extend(struct.pack(">I", UNIMP_ENCODING))

    def tramp_hart_body():
        # Instruction 1: mask ALL of hart's causes using the pre-loaded
        # ALL-1 register -- no value-construction window (see design note).
        write_crrr(out, OP_CFX2RC, CFX_HART, MODE_SUPV,
                    RC_EXCP_CAUSE_MASK, ALLONES_REG)
        # Instruction 2: fix prev_cfx_mask so escaping restores a fully
        # blocking inner_cfx_mask, not the already-unmasked value that let
        # this entry happen.
        write_crrr(out, OP_CFX2RC, CFX_HART, CG_FRAME,
                    RC_FRAME_PREV_CFX_MASK, ALLONES_REG)
        write_ciii(out, OP_ESCAPE, CFX_HART, 1)
    emit_slot(tramp_hart_body)

    def tramp_uart_body():
        # Same two-instruction discipline, shared by both UART0 and UART5
        # entries (verification happens in the resumed main flow, using
        # cause_id to distinguish which one just fired).
        write_crrr(out, OP_CFX2RC, CFX_UART, MODE_SUPV,
                    RC_EXCP_CAUSE_MASK, ALLONES_REG)
        write_crrr(out, OP_CFX2RC, CFX_UART, CG_FRAME,
                    RC_FRAME_PREV_CFX_MASK, ALLONES_REG)
        write_ciii(out, OP_ESCAPE, CFX_UART, 1)
    emit_slot(tramp_uart_body)

    return bytes(out)


def run_qemu(name, raw, level_a=None, level_b=None):
    os.makedirs(EVIDENCE, exist_ok=True)
    path = os.path.join(EVIDENCE, name + "-qemu.bin")
    with open(path, "wb") as stream:
        stream.write(raw)
    command = [QEMU, "-M", "dadao-m1", "-bios", path, "-display", "none",
               "-serial", "none", "-d", "int"]
    if level_a is not None:
        code, seed = level_a
        command[3:3] = [
            "-global", f"dadao-cpu.cfx-async-test-level-a-code={code}",
            "-global", f"dadao-cpu.cfx-async-test-level-a-seed={hex(seed)}"]
    if level_b is not None:
        code, seed = level_b
        command[3:3] = [
            "-global", f"dadao-cpu.cfx-async-test-level-b-code={code}",
            "-global", f"dadao-cpu.cfx-async-test-level-b-seed={hex(seed)}"]
    result = subprocess.run(command, capture_output=True, timeout=60,
                             text=True)
    with open(os.path.join(EVIDENCE, name + "-qemu.log"), "w") as stream:
        stream.write("=== command ===\n" + " ".join(command))
        stream.write("\n=== stdout ===\n" + result.stdout)
        stream.write("\n=== stderr ===\n" + result.stderr)
    return result


def gem5_code(stdout):
    matches = re.findall(r"SIM_END: .* code=(\d+)", stdout)
    if len(matches) != 1:
        raise AssertionError(
            f"gem5 output has {len(matches)} SIM_END records, expected one:"
            f" {matches}")
    return int(matches[0])


def run_gem5(name, raw, level_a=None, level_b=None):
    os.makedirs(EVIDENCE, exist_ok=True)
    path = os.path.join(EVIDENCE, name + "-gem5.bin")
    with open(path, "wb") as stream:
        stream.write(raw)
    outdir = tempfile.mkdtemp(prefix="gem5_kl131a_")
    command = [GEM5, "--outdir=" + outdir, GEM5_FS_CFG, path]
    if level_a is not None:
        code, seed = level_a
        command += ["--cfx-async-level-a", str(code), hex(seed)]
    if level_b is not None:
        code, seed = level_b
        command += ["--cfx-async-level-b", str(code), hex(seed)]
    result = subprocess.run(command, capture_output=True, timeout=120,
                             text=True)
    with open(os.path.join(EVIDENCE, name + "-gem5.log"), "w") as stream:
        stream.write("=== command ===\n" + " ".join(command))
        stream.write("\n=== stdout ===\n" + result.stdout)
        stream.write("\n=== stderr ===\n" + result.stderr)
    return result


def main():
    a = gen_scenario_a()
    b = gen_scenario_b()
    level_a = (CFX_HART, CAUSE_IPI)
    level_b = (CFX_UART, CAUSE_UART0 | CAUSE_UART5)

    qa = run_qemu("scenario-a", a)
    ga = run_gem5("scenario-a", a)
    assert qa.returncode == PASS_A, \
        f"QEMU scenario A: {qa.returncode}, expected {PASS_A}\n{qa.stderr[-4000:]}"
    assert ga.returncode == PASS_A, \
        f"gem5 scenario A: {ga.returncode}, expected {PASS_A}\n{ga.stdout[-2000:]}"
    assert gem5_code(ga.stdout) == PASS_A, ga.stdout[-2000:]

    qb = run_qemu("scenario-b", b, level_a=level_a, level_b=level_b)
    gb = run_gem5("scenario-b", b, level_a=level_a, level_b=level_b)
    assert qb.returncode == PASS_B, \
        f"QEMU scenario B: {qb.returncode}, expected {PASS_B}\n{qb.stderr[-4000:]}"
    assert gb.returncode == PASS_B, \
        f"gem5 scenario B: {gb.returncode}, expected {PASS_B}\n{gb.stdout[-2000:]}"
    assert gem5_code(gb.stdout) == PASS_B, gb.stdout[-2000:]

    print(f"PASS: scenario-A(sync masks 2/3/4/5+nonmaskable+counters)="
          f"{PASS_A}/{PASS_A}; "
          f"scenario-B(async boundary+priority+electrics)="
          f"{PASS_B}/{PASS_B}")


if __name__ == "__main__":
    main()
