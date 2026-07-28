#!/usr/bin/env python3
"""KL-142a K2 supervisor preemptive full-context probe.

A one-shot timer interrupts a supervisor task at the deepest point of a real
three-call chain.  The timer handler saves the frozen 198-word trap frame
directly below the interrupted rb1, uses calls and deliberately clobbers
general registers, then restores RA/RD/RB and escapes.  The resumed task
immediately snapshots the restored state without scratch and checks every
frame word before returning through the original RegRAS chain.

After the outer timer frame is fully owned, the handler triggers a PTW trap
that pushes a second disjoint 198-word frame.  The inner and outer handlers
restore and escape in LIFO order, proving the frozen cross-CFX E1 ownership
and prev_cfx_code rules without claiming same-CFX recursion.

The same ROM/RAM bytes run on QEMU and gem5 FullSystem.  Verdicts come from
guest fail-closed checks, the KL-140a independent report oracle, and raw
guest-memory report comparison.  A separate image mutates rd17 after a real
save and must fail on both backends.
"""

import argparse
import hashlib
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import k2_report as k2  # noqa: E402
import run_kl131a_async_dispatch_probes as k131  # noqa: E402
import run_kl133a_cfx_timer_probes as k133  # noqa: E402
import run_kl141a_coop_switch as k141  # noqa: E402
from build_test_binary import UNIMP_ENCODING  # noqa: E402


Emit = k141.Emit
OP_CSZ = k141.OP_CSZ
OP_LDMO_RA = k141.OP_LDMO_RA
OP_STMO_RA = k141.OP_STMO_RA
MISC_ORR = k141.MISC_ORR
MISC_XOR = k141.MISC_XOR

ROM_BASE = k131.ROM_BASE
ROM_SIZE = 0x10000
RAM_BASE = 0x80000000
RAM_SIZE = 0x200000
IDENTITY_SLOT_OFF = 0xFFF8

SCENARIO = k2.scenario_id_for("KL142a")
TASK = 1
CFX_TIMER = k131.CFX_TIMER
CFX_POWER = k131.CFX_POWER
CFX_PTW = k131.CFX_PTW
MODE_SUPV = k131.MODE_SUPV
CG_FRAME = k131.CG_FRAME
RC_PREV_MODE = k131.RC_FRAME_PREV_RUN_MODE
RC_PREV_MASK = k131.RC_FRAME_PREV_CFX_MASK
RC_CAUSE_ID = k131.RC_FRAME_CAUSE_ID
RC_CAUSE_IP = k131.RC_FRAME_CAUSE_IP
RC_CAUSE_INFO = k131.RC_FRAME_CAUSE_INFO
RC_PREV_CFX = 5
CAUSE_TIMER = k133.CAUSE_TIMER
CAUSE_CFXTRAP = 1
OP_TRAP = 0x76
MASK_ALL = k131.MASK_ALL
OPEN_TIMER_CFX_MASK = MASK_ALL & ~((1 << CFX_TIMER) | (1 << CFX_PTW))
OPEN_TIMER_CAUSE_MASK = MASK_ALL & ~CAUSE_TIMER

CTRL = 0x8000F000
ADDR_CURSOR = CTRL + 0x08
ADDR_MISMATCH = CTRL + 0x10
MDW = CTRL + 0x100
MDW_SEQ = 0
MDW_ENTRY = 10
MDW_RETURN = 11
MDW_BITMAP = 12
MDW_HELPER = 13
MDW_NEST_HELPER = 14
ADDR_SEQ = MDW
ADDR_ENTRY_COUNT = MDW + MDW_ENTRY * 8
ADDR_RETURN_COUNT = MDW + MDW_RETURN * 8
ADDR_BITMAP = MDW + MDW_BITMAP * 8

STACK_LO = 0x80014000
STACK_TOP = 0x80018000
FRAME_SIZE = 0x630
FRAME_WORDS = 198
FRAME_BASE = STACK_TOP - FRAME_SIZE
EXPECTED_TABLE = 0x8001A000
INNER_FRAME_BASE = FRAME_BASE - FRAME_SIZE
INNER_EXPECTED_TABLE = 0x8001A800
ZERO_CONTEXT = 0x8001B000

REPORT_PA = k141.REPORT_PA
REPORT_WINDOW = k141.REPORT_WINDOW
DOORBELL_OFF = k141.DOORBELL_OFF
DOORBELL = k141.DOORBELL
IDENTITY_MIRROR = k141.IDENTITY_MIRROR
EVIDENCE = os.path.join(REPO, ".work", "evidence", "kl142a-preemptive")

GUARDS = (
    (STACK_LO, 0x6AED142A00000001),
    (STACK_TOP, 0x6AED142A00000003),
    (EXPECTED_TABLE - 8, 0x6AED142A00000004),
    (EXPECTED_TABLE + FRAME_WORDS * 8, 0x6AED142A00000005),
    (INNER_EXPECTED_TABLE - 8, 0x6AED142A00000008),
    (INNER_EXPECTED_TABLE + FRAME_WORDS * 8, 0x6AED142A00000009),
    (REPORT_PA - 8, 0x6AED142A00000006),
    (REPORT_PA + REPORT_WINDOW, 0x6AED142A00000007),
)

BITMAP_DEEP = 0x7
BITMAP_FINAL = 0x00070007
N_CHECKPOINTS = 6
MODE_CFX_POWER = MODE_SUPV | (CFX_POWER << 8)
MODE_CFX_TIMER = MODE_SUPV | (CFX_TIMER << 8)
MASK64 = (1 << 64) - 1


def poison_rd(reg):
    return 0xD142000000000000 | (reg << 24) | (reg << 8) | 0x5A


def expected_rd(reg):
    if reg == 62:
        return MASK_ALL
    if reg == 63:
        return OPEN_TIMER_CAUSE_MASK
    return poison_rd(reg)


def poison_rb(reg):
    return 0xB142000000000000 | (reg << 24) | (reg << 8) | 0xA5


def inner_rd(reg):
    return 0xD242000000000000 | (reg << 24) | (reg << 8) | 0x6B


def inner_rb(reg):
    return 0xB242000000000000 | (reg << 24) | (reg << 8) | 0xB6


def put_qword(image, address, value):
    offset = address - RAM_BASE
    image[offset:offset + 8] = struct.pack(">Q", value & MASK64)


def cfx_read(e, rc, rd=8, cfx=CFX_TIMER):
    k131.write_crrr(
        e.out, k131.OP_CFX2RD, cfx, CG_FRAME, rc, rd)


def load_full_rb(e, reg, value, scratch=8):
    """RB immediates are 48-bit; materialize a full u64 in RD then rd2rb."""
    e.load("rd", scratch, value)
    e.word(0x10A40000 | (reg << 12) | (scratch << 6) | 1)


def emit_frame_save_no_scratch(e):
    """Save RD/RB while rb1 is still old_sp, then save full RegRAS."""
    for reg in range(1, 64):
        e.sto_rd(reg, 1, -FRAME_SIZE + (7 + reg) * 8)
    for reg in range(1, 64):
        e.sto_rb(reg, 1, -FRAME_SIZE + (70 + reg) * 8)
    e.load("rd", 8, (-0x200) & MASK64)
    e.rrri(OP_STMO_RA, 0, 1, 8, 63)
    e.load("rd", 8, (-8) & MASK64)
    e.rrri(OP_STMO_RA, 63, 1, 8, 1)


def emit_frame_metadata(e, owner=CFX_TIMER, nest_level=0):
    e.load("rd", 8, owner)
    e.sto_rd(8, 1, -FRAME_SIZE)
    for word, rc in enumerate(
            (RC_CAUSE_ID, RC_CAUSE_IP, RC_CAUSE_INFO, RC_PREV_MODE,
             RC_PREV_MASK, RC_PREV_CFX), start=1):
        cfx_read(e, rc, cfx=owner)
        e.sto_rd(8, 1, -FRAME_SIZE + word * 8)
    e.load("rd", 8, nest_level)
    e.sto_rd(8, 1, -FRAME_SIZE + 7 * 8)


def emit_frame_restore(e):
    """Strict inverse: RA, RD, RB2..63, RB1 last, then caller emits escape."""
    e.load("rd", 8, 0x430)
    e.rrri(OP_LDMO_RA, 0, 1, 8, 63)
    e.load("rd", 8, 0x628)
    e.rrri(OP_LDMO_RA, 63, 1, 8, 1)
    for reg in range(1, 64):
        e.ldo_rd(reg, 1, 0x40 + (reg - 1) * 8)
    for reg in range(2, 64):
        e.ldo_rb(reg, 1, 0x238 + (reg - 1) * 8)
    e.ldo_rb(1, 1, 0x238)


def emit_check_frame(e, label):
    e.mark(label)
    e.load("rb", 10, ADDR_MISMATCH)
    e.load("rd", 12, FRAME_WORDS)
    e.mark(label + "_loop")
    e.ldo_rd(11, 8, 0)
    e.ldo_rd(10, 9, 0)
    e.orrr(MISC_XOR, 11, 11, 10)
    e.ldo_rd(13, 10, 0)
    e.orrr(MISC_ORR, 13, 13, 11)
    e.sto_rd(13, 10, 0)
    e.addi_rb(8, 8, 8)
    e.addi_rb(9, 9, 8)
    e.addi_rd(12, 12, -1)
    e.brnz(12, label + "_loop")
    e.ret()


def emit_guard_check(e, label):
    e.mark(label)
    for address, value in GUARDS:
        e.load("rb", 8, address)
        e.ldo_rd(10, 8, 0)
        k141.check_eq_rd(e, 10, value)
    e.ret()


def emit_checkpoint_writer(e, label):
    """Args rd8/9/10/11=event/task/saved/resume, rd17=mode_cfx,
    rd18=cause, rb9=frame (zero means no context digest)."""
    e.mark(label)
    e.orrr(MISC_ORR, 21, 8, 0)
    e.orrr(MISC_ORR, 22, 9, 0)
    e.orrr(MISC_ORR, 23, 10, 0)
    e.orrr(MISC_ORR, 24, 11, 0)
    e.orrr(MISC_ORR, 25, 17, 0)
    e.orrr(MISC_ORR, 26, 18, 0)
    e.addi_rb(16, 9, 0)
    e.rb2rd(27, 16)
    e.brz(27, label + "_no_ctx")
    e.addi_rb(8, 16, 0)
    e.load("rd", 12, FRAME_WORDS)
    e.call("FNV_WORDS")
    e.orrr(MISC_ORR, 18, 13, 0)
    e.jump(label + "_ctx_done")
    e.mark(label + "_no_ctx")
    e.load("rd", 18, 0)
    e.mark(label + "_ctx_done")
    e.load("rb", 8, MDW)
    e.load("rd", 12, 16)
    e.call("FNV_WORDS")
    e.orrr(MISC_ORR, 14, 13, 0)
    e.load("rb", 8, ADDR_SEQ)
    e.ldo_rd(19, 8, 0)
    e.addi_rd(20, 19, 1)
    e.sto_rd(20, 8, 0)
    e.load("rb", 8, ADDR_CURSOR)
    e.ldo_rb(12, 8, 0)
    for offset, rd in (
            (0, 19), (8, 21), (16, 22), (24, 25), (32, 26),
            (40, 23), (48, 24), (56, 18), (64, 14)):
        e.sto_rd(rd, 12, offset)
    e.load("rd", 20, 0)
    e.sto_rd(20, 12, 72)
    e.sto_rd(20, 12, 80)
    e.addi_rb(12, 12, k2.CHECKPOINT_SIZE)
    e.sto_rb(12, 8, 0)
    e.ret()


def emit_checkpoint_call(e, event, task, saved_pc_label=None,
                         resume_pc_label=None, mode_cfx=MODE_CFX_POWER,
                         cause=0, frame_addr=None):
    e.load("rd", 8, event)
    e.load("rd", 9, task)
    if saved_pc_label:
        e.load_label("rd", 10, saved_pc_label)
    else:
        e.load("rd", 10, 0)
    if resume_pc_label:
        e.load_label("rd", 11, resume_pc_label)
    else:
        e.load("rd", 11, 0)
    e.load("rd", 17, mode_cfx)
    e.load("rd", 18, cause)
    # Always provide a concrete resident context window.  This also avoids
    # making a report semantic depend on a backend's RB-zero branch path.
    e.load("rb", 9, frame_addr if frame_addr is not None else ZERO_CONTEXT)
    e.call("EMIT_CKPT")


def emit_bitmap_or(e, bit):
    e.load("rb", 8, ADDR_BITMAP)
    e.ldo_rd(9, 8, 0)
    e.load("rd", 10, 1 << bit)
    e.orrr(MISC_ORR, 9, 9, 10)
    e.sto_rd(9, 8, 0)


def expected_ras(labels):
    return k141.ras_model([
        labels["PUSH_L1"] + 4,
        labels["PUSH_L2"] + 4,
        labels["PUSH_L3"] + 4,
    ])


def expected_frame(labels):
    words = [
        CFX_TIMER,
        CAUSE_TIMER,
        labels["POISON"],
        0,
        MODE_SUPV,
        OPEN_TIMER_CFX_MASK,
        CFX_POWER,
        0,
    ]
    words += [expected_rd(reg) for reg in range(1, 64)]
    words += [STACK_TOP] + [poison_rb(reg) for reg in range(2, 64)]
    words += expected_ras(labels)
    assert len(words) == FRAME_WORDS
    return words


def expected_inner_frame(labels):
    raw_trap = (OP_TRAP << 24) | (CFX_PTW << 18) | 1
    words = [
        CFX_PTW,
        CAUSE_CFXTRAP,
        labels["INNER_TRAP"],
        raw_trap,
        MODE_SUPV,
        MASK_ALL,
        CFX_TIMER,
        1,
    ]
    words += [inner_rd(reg) for reg in range(1, 64)]
    words += [FRAME_BASE] + [inner_rb(reg) for reg in range(2, 64)]
    words += expected_ras(labels)
    assert len(words) == FRAME_WORDS
    return words


def build_image(mutation=None):
    if mutation not in (None, "rd17", "rb41", "ra0"):
        raise ValueError(f"unsupported mutation {mutation}")
    e = Emit()
    k131.emit_boot_stub(e.out, ROM_BASE + 0x200)

    e.mark("MAIN")
    e.load("rb", 1, STACK_TOP)
    emit_checkpoint_call(e, k2.EVENT_INIT, 0)
    e.call("GUARD_CHECK")

    # Timer routing is opened while its cause remains masked.  The final
    # cfx2rc in L3 opens that one cause after all live state is poisoned.
    e.load_label("rd", 2, "TIMER_HANDLER")
    k131.write_crrr(
        e.out, k131.OP_CFX2RC, CFX_TIMER, 2, k131.RC_EXCP_VECTOR, 2)
    e.load_label("rd", 2, "PTW_HANDLER")
    k131.write_crrr(
        e.out, k131.OP_CFX2RC, CFX_PTW, 2, k131.RC_EXCP_VECTOR, 2)
    k131.set_excp_cause_mask(
        e.out, CFX_TIMER, MODE_SUPV, MASK_ALL, scratch=2)
    k131.set_excp_cause_mask(
        e.out, CFX_PTW, MODE_SUPV, MASK_ALL & ~CAUSE_CFXTRAP, scratch=2)
    k131.set_global_mask(
        e.out, MODE_SUPV, OPEN_TIMER_CFX_MASK, scratch=2)
    k131.set_escape_mask(
        e.out, CFX_POWER, MODE_SUPV, MASK_ALL & ~(1 << CFX_PTW), scratch=2)
    k131.set_escape_mask(
        e.out, CFX_TIMER, MODE_SUPV, MASK_ALL & ~(1 << CFX_PTW), scratch=2)
    k131.craft_inner_cfx_mask(
        e.out, CFX_PTW, OPEN_TIMER_CFX_MASK, scratch=2)
    k133.set_timer_mask(e.out, 0, scratch=2)

    emit_bitmap_or(e, 0)
    e.mark("PUSH_L1")
    e.call("L1")
    emit_bitmap_or(e, 16)
    e.load("rb", 8, ADDR_BITMAP)
    e.ldo_rd(8, 8, 0)
    k141.check_eq_rd(e, 8, BITMAP_FINAL)
    e.load("rb", 8, ADDR_ENTRY_COUNT)
    e.ldo_rd(8, 8, 0)
    k141.check_eq_rd(e, 8, 2)
    e.load("rb", 8, ADDR_RETURN_COUNT)
    e.ldo_rd(8, 8, 0)
    k141.check_eq_rd(e, 8, 2)
    e.call("GUARD_CHECK")
    emit_checkpoint_call(e, k2.EVENT_FINAL, 0)

    # Guest-owned final verdict and architectural termination.
    e.load("rb", 12, REPORT_PA)
    for offset, value in (
            (0, k2.MAGIC), (8, k2.SCHEMA_VERSION), (16, SCENARIO)):
        e.load("rd", 8, value)
        e.sto_rd(8, 12, offset)
    e.load("rb", 8, IDENTITY_MIRROR)
    e.ldo_rd(8, 8, 0)
    e.sto_rd(8, 12, 24)
    e.load("rb", 8, ADDR_MISMATCH)
    e.ldo_rd(9, 8, 0)
    e.load("rd", 10, k2.STATUS_PASS)
    e.load("rd", 11, k2.STATUS_FAIL)
    e.word((OP_CSZ << 24) | (9 << 18) | (8 << 12) | (10 << 6) | 11)
    e.sto_rd(8, 12, 32)
    e.sto_rd(9, 12, 40)
    e.load("rb", 8, ADDR_SEQ)
    e.ldo_rd(8, 8, 0)
    e.sto_rd(8, 12, 48)
    e.load("rd", 8, 0)
    e.sto_rd(8, 12, 56)
    e.load("rd", 8, k2.MAX_CHECKPOINTS)
    e.sto_rd(8, 12, 64)
    e.load("rd", 8, DOORBELL)
    e.load("rb", 8, REPORT_PA + DOORBELL_OFF)
    e.sto_rd(8, 8, 0)
    e.load("rd", 8, 0)
    e.riii(k131.OP_HALT, 8, 0)

    e.mark("L1")
    emit_bitmap_or(e, 1)
    e.mark("PUSH_L2")
    e.call("L2")
    emit_bitmap_or(e, 17)
    e.ret()

    e.mark("L2")
    emit_bitmap_or(e, 2)
    e.mark("PUSH_L3")
    e.call("L3")
    emit_bitmap_or(e, 18)
    e.ret()

    e.mark("L3")
    k133.set_timer_counter0(e.out, 1, scratch=2)
    k133.set_timer_ctrl(e.out, k133.TIMER_CTRL_ENABLE, scratch=2)
    for reg in range(2, 64):
        load_full_rb(e, reg, poison_rb(reg))
    for reg in range(1, 62):
        e.load("rd", reg, expected_rd(reg))
    e.load("rd", 62, expected_rd(62))
    e.load("rd", 63, expected_rd(63))
    k131.write_crrr(
        e.out, k131.OP_CFX2RC, CFX_TIMER, MODE_SUPV,
        k131.RC_EXCP_CAUSE_MASK, 63)
    e.mark("POISON")
    e.word(UNIMP_ENCODING)
    e.mark("RESUME")

    # Capture the restored task state before any checker can clobber it.
    emit_frame_save_no_scratch(e)
    e.load("rb", 8, FRAME_BASE)
    e.load("rb", 9, EXPECTED_TABLE)
    e.call("CHECK_FRAME")
    e.load("rb", 8, ADDR_RETURN_COUNT)
    e.ldo_rd(9, 8, 0)
    e.addi_rd(9, 9, 1)
    e.sto_rd(9, 8, 0)
    emit_checkpoint_call(
        e, k2.EVENT_TRAP_RETURN, TASK, "POISON", "RESUME",
        MODE_CFX_TIMER, CAUSE_TIMER, frame_addr=FRAME_BASE)
    e.ret()

    e.mark("TIMER_HANDLER")
    # Required re-entry exclusion: this first instruction only masks the
    # source using preloaded rd62 and does not alter any live RD/RB/RA.
    k131.write_crrr(
        e.out, k131.OP_CFX2RC, CFX_TIMER, MODE_SUPV,
        k131.RC_EXCP_CAUSE_MASK, 62)
    emit_frame_save_no_scratch(e)
    emit_frame_metadata(e)
    e.addi_rb(1, 1, -FRAME_SIZE)

    e.load("rb", 8, ADDR_ENTRY_COUNT)
    e.ldo_rd(9, 8, 0)
    e.addi_rd(9, 9, 1)
    e.sto_rd(9, 8, 0)
    e.addi_rb(8, 1, 0)
    e.load("rb", 9, EXPECTED_TABLE)
    e.call("CHECK_FRAME")
    emit_checkpoint_call(
        e, k2.EVENT_TRAP_ENTER, TASK, "POISON", "RESUME",
        MODE_CFX_TIMER, CAUSE_TIMER, frame_addr=FRAME_BASE)

    # Cross-CFX E1: only after the outer SP is down, poison the outer
    # handler's live context and trap into PTW.  The inner handler therefore
    # owns the next disjoint [sp-0x630, sp) window.
    for reg in range(2, 64):
        load_full_rb(e, reg, inner_rb(reg))
    for reg in range(1, 64):
        e.load("rd", reg, inner_rd(reg))
    e.mark("INNER_TRAP")
    k131.write_ciii(e.out, OP_TRAP, CFX_PTW, 1)
    e.mark("INNER_RESUME")
    emit_frame_save_no_scratch(e)
    e.load("rb", 8, INNER_FRAME_BASE)
    e.load("rb", 9, INNER_EXPECTED_TABLE)
    e.call("CHECK_FRAME")
    e.load("rb", 8, ADDR_RETURN_COUNT)
    e.ldo_rd(9, 8, 0)
    e.addi_rd(9, 9, 1)
    e.sto_rd(9, 8, 0)
    emit_checkpoint_call(
        e, k2.EVENT_TRAP_RETURN, TASK, "INNER_TRAP", "INNER_RESUME",
        MODE_SUPV | (CFX_PTW << 8), CAUSE_CFXTRAP,
        frame_addr=INNER_FRAME_BASE)

    if mutation is not None:
        mutation_word = {
            "rd17": 7 + 17,
            "rb41": 70 + 41,
            "ra0": 134,
        }[mutation]
        e.ldo_rd(8, 1, mutation_word * 8)
        e.load("rd", 9, MASK_ALL)
        e.orrr(MISC_XOR, 8, 8, 9)
        e.sto_rd(8, 1, mutation_word * 8)

    # Drain private then common pending while self-delivery remains masked.
    k131.write_crrr(
        e.out, k131.OP_CFX2RC, CFX_TIMER, k133.CG_TIMER,
        k133.RC_TIMER_PENDING, 0)
    k131.write_crrr(
        e.out, k131.OP_CFX2RC, CFX_TIMER, k131.CG_COMMON,
        k131.RC_PENDING, 0)
    e.call("HANDLER_HELPER")
    emit_frame_restore(e)
    k131.write_ciii(e.out, k131.OP_ESCAPE, CFX_TIMER, 1)

    e.mark("PTW_HANDLER")
    emit_frame_save_no_scratch(e)
    emit_frame_metadata(e, owner=CFX_PTW, nest_level=1)
    e.addi_rb(1, 1, -FRAME_SIZE)
    e.load("rb", 8, ADDR_ENTRY_COUNT)
    e.ldo_rd(9, 8, 0)
    e.addi_rd(9, 9, 1)
    e.sto_rd(9, 8, 0)
    e.addi_rb(8, 1, 0)
    e.load("rb", 9, INNER_EXPECTED_TABLE)
    e.call("CHECK_FRAME")
    emit_checkpoint_call(
        e, k2.EVENT_TRAP_ENTER, TASK, "INNER_TRAP", "INNER_RESUME",
        MODE_SUPV | (CFX_PTW << 8), CAUSE_CFXTRAP,
        frame_addr=INNER_FRAME_BASE)
    e.call("INNER_HELPER")
    emit_frame_restore(e)
    k131.write_ciii(e.out, k131.OP_ESCAPE, CFX_PTW, 1)

    e.mark("INNER_HELPER")
    e.load("rb", 8, MDW + MDW_NEST_HELPER * 8)
    e.load("rd", 8, 1)
    e.sto_rd(8, 8, 0)
    for reg in range(2, 64):
        load_full_rb(
            e, reg, 0xA242000000000000 | (reg << 8) | 0xBB, scratch=1)
    for reg in range(1, 64):
        e.load("rd", reg, 0xE242000000000000 | (reg << 8) | 0xEF)
    e.ret()

    e.mark("HANDLER_HELPER")
    e.load("rb", 8, MDW + MDW_HELPER * 8)
    e.load("rd", 8, 1)
    e.sto_rd(8, 8, 0)
    for reg in range(2, 64):
        load_full_rb(
            e, reg, 0xA142000000000000 | (reg << 8) | 0xAA, scratch=1)
    for reg in range(1, 64):
        e.load("rd", reg, 0xE142000000000000 | (reg << 8) | 0xEE)
    e.ret()

    k141.emit_fnv_words(e, "FNV_WORDS")
    emit_check_frame(e, "CHECK_FRAME")
    emit_guard_check(e, "GUARD_CHECK")
    emit_checkpoint_writer(e, "EMIT_CKPT")

    e.pad_unimp(IDENTITY_SLOT_OFF)
    e.out.extend(b"\0" * 8)
    if len(e.out) > ROM_SIZE:
        raise ValueError("ROM image overflow")
    rom = bytearray(e.finish())
    table = expected_frame(e.labels)
    inner_table = expected_inner_frame(e.labels)

    ram = bytearray(RAM_SIZE)
    put_qword(ram, ADDR_CURSOR, REPORT_PA + k2.HEADER_SIZE)
    for address, value in GUARDS:
        put_qword(ram, address, value)
    table_bytes = struct.pack(f">{FRAME_WORDS}Q", *table)
    table_offset = EXPECTED_TABLE - RAM_BASE
    ram[table_offset:table_offset + len(table_bytes)] = table_bytes
    inner_table_bytes = struct.pack(f">{FRAME_WORDS}Q", *inner_table)
    inner_table_offset = INNER_EXPECTED_TABLE - RAM_BASE
    ram[inner_table_offset:inner_table_offset + len(inner_table_bytes)] = (
        inner_table_bytes)

    identity = k2.image_identity(
        bytes(rom), bytes(ram),
        rom_identity_slot=(IDENTITY_SLOT_OFF, 8),
        ram_report_area=(REPORT_PA - RAM_BASE, k2.MAX_REPORT_SIZE))
    rom = bytearray(
        k2.embed_image_identity(bytes(rom), IDENTITY_SLOT_OFF, identity))
    put_qword(ram, IDENTITY_MIRROR, identity)
    return bytes(rom), bytes(ram), e.labels, (table, inner_table), identity


def mdw_digest(seq, entry, returned, bitmap, helper, nest_helper):
    words = [0] * 16
    words[MDW_SEQ] = seq
    words[MDW_ENTRY] = entry
    words[MDW_RETURN] = returned
    words[MDW_BITMAP] = bitmap
    words[MDW_HELPER] = helper
    words[MDW_NEST_HELPER] = nest_helper
    return k2.fnv1a64(words)


def build_oracle(labels, tables, identity):
    table, inner_table = tables
    digest = k2.fnv1a64(table)
    inner_digest = k2.fnv1a64(inner_table)
    zero_digest = k2.fnv1a64([0] * FRAME_WORDS)
    expected = [
        k2.ExpectedCheckpoint(
            event_kind=k2.EVENT_INIT, task_id=0, run_mode=MODE_SUPV,
            cfx_code=CFX_POWER, cause=0, saved_pc=0, resume_pc=0,
            context_digest=zero_digest,
            memory_digest=mdw_digest(0, 0, 0, 0, 0, 0),
            asid=0, ptbr=0, tlb_gen=0),
        k2.ExpectedCheckpoint(
            event_kind=k2.EVENT_TRAP_ENTER, task_id=TASK, run_mode=MODE_SUPV,
            cfx_code=CFX_TIMER, cause=CAUSE_TIMER,
            saved_pc=labels["POISON"], resume_pc=labels["RESUME"],
            context_digest=digest,
            memory_digest=mdw_digest(1, 1, 0, BITMAP_DEEP, 0, 0),
            asid=0, ptbr=0, tlb_gen=0),
        k2.ExpectedCheckpoint(
            event_kind=k2.EVENT_TRAP_ENTER, task_id=TASK, run_mode=MODE_SUPV,
            cfx_code=CFX_PTW, cause=CAUSE_CFXTRAP,
            saved_pc=labels["INNER_TRAP"], resume_pc=labels["INNER_RESUME"],
            context_digest=inner_digest,
            memory_digest=mdw_digest(2, 2, 0, BITMAP_DEEP, 0, 0),
            asid=0, ptbr=0, tlb_gen=0),
        k2.ExpectedCheckpoint(
            event_kind=k2.EVENT_TRAP_RETURN, task_id=TASK, run_mode=MODE_SUPV,
            cfx_code=CFX_PTW, cause=CAUSE_CFXTRAP,
            saved_pc=labels["INNER_TRAP"], resume_pc=labels["INNER_RESUME"],
            context_digest=inner_digest,
            memory_digest=mdw_digest(3, 2, 1, BITMAP_DEEP, 0, 1),
            asid=0, ptbr=0, tlb_gen=0),
        k2.ExpectedCheckpoint(
            event_kind=k2.EVENT_TRAP_RETURN, task_id=TASK, run_mode=MODE_SUPV,
            cfx_code=CFX_TIMER, cause=CAUSE_TIMER,
            saved_pc=labels["POISON"], resume_pc=labels["RESUME"],
            context_digest=digest,
            memory_digest=mdw_digest(4, 2, 2, BITMAP_DEEP, 1, 1),
            asid=0, ptbr=0, tlb_gen=0),
        k2.ExpectedCheckpoint(
            event_kind=k2.EVENT_FINAL, task_id=0, run_mode=MODE_SUPV,
            cfx_code=CFX_POWER, cause=0, saved_pc=0, resume_pc=0,
            context_digest=zero_digest,
            memory_digest=mdw_digest(5, 2, 2, BITMAP_FINAL, 1, 1),
            asid=0, ptbr=0, tlb_gen=0),
    ]
    return k2.ScenarioOracle(
        scenario_id=SCENARIO, image_identity=identity, checkpoints=expected)


class TransportError(Exception):
    pass


def verify_run_image(rom_path, ram_path, oracle):
    with open(rom_path, "rb") as fh:
        rom = fh.read()
    with open(ram_path, "rb") as fh:
        ram = fh.read()
    if len(rom) != ROM_SIZE or len(ram) != RAM_SIZE:
        raise TransportError("run image size mismatch")
    computed = k2.image_identity(
        rom, ram, rom_identity_slot=(IDENTITY_SLOT_OFF, 8),
        ram_report_area=(REPORT_PA - RAM_BASE, k2.MAX_REPORT_SIZE))
    embedded = struct.unpack(
        ">Q", rom[IDENTITY_SLOT_OFF:IDENTITY_SLOT_OFF + 8])[0]
    mirror_off = IDENTITY_MIRROR - RAM_BASE
    mirrored = struct.unpack(">Q", ram[mirror_off:mirror_off + 8])[0]
    if computed != oracle.image_identity or embedded != computed or mirrored != computed:
        raise TransportError(
            f"image identity mismatch computed={computed:#x} "
            f"embedded={embedded:#x} mirror={mirrored:#x}")


def run_one(round_no, rom_path, ram_path, oracle, tag):
    try:
        verify_run_image(rom_path, ram_path, oracle)
        qemu = k141.run_qemu(
            rom_path, ram_path,
            os.path.join(EVIDENCE, f"qemu{tag}-{round_no:02d}.log"))
        gem5 = k141.run_gem5(
            rom_path, ram_path,
            os.path.join(EVIDENCE, f"gem5{tag}-{round_no:02d}.log"))
    except (OSError, k141.TransportError, TransportError) as exc:
        return k2.Verdict.HARNESS_ERROR, [str(exc)], None, None
    for name, data in (("qemu", qemu), ("gem5", gem5)):
        with open(os.path.join(
                EVIDENCE, f"report-{name}{tag}-{round_no:02d}.bin"), "wb") as fh:
            fh.write(data)
    verdict, reasons = k2.compare_dual_backend(qemu, gem5, oracle)
    return verdict, reasons, qemu, gem5


def write_image(tag, mutation=None):
    rom, ram, labels, table, identity = build_image(mutation)
    rom_path = os.path.join(EVIDENCE, f"kl142a-{tag}.bin")
    ram_path = os.path.join(EVIDENCE, f"kl142a-{tag}-ram.bin")
    with open(rom_path, "wb") as fh:
        fh.write(rom)
    with open(ram_path, "wb") as fh:
        fh.write(ram)
    return rom_path, ram_path, build_oracle(labels, table, identity), rom, ram


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--skip-negative", action="store_true")
    parser.add_argument(
        "--mutation", choices=("rd17", "rb41", "ra0"), default="rd17")
    args = parser.parse_args()
    if args.rounds < 1:
        parser.error("--rounds must be positive")

    os.makedirs(EVIDENCE, exist_ok=True)
    rom_path, ram_path, oracle, rom, ram = write_image("positive")
    print(f"image: sha256-rom={hashlib.sha256(rom).hexdigest()}")
    print(f"image: sha256-ram={hashlib.sha256(ram).hexdigest()}")
    print(f"image: canonical identity={oracle.image_identity:#018x} "
          f"frame_words={FRAME_WORDS} checkpoints={N_CHECKPOINTS}")

    failures = 0
    for round_no in range(1, args.rounds + 1):
        verdict, reasons, _, _ = run_one(
            round_no, rom_path, ram_path, oracle, "-pos")
        if verdict == k2.Verdict.PASS:
            print(f"round {round_no}/{args.rounds}: qemu=PASS gem5=PASS "
                  "oracle=PASS cross=PASS")
        else:
            failures += 1
            print(f"round {round_no}: {verdict.value}")
            for reason in reasons[:12]:
                print(f"  {reason}")

    if failures == 0 and not args.skip_negative:
        mrom_path, mram_path, moracle, _, _ = write_image(
            "mutation", args.mutation)
        verdict, reasons, qemu, gem5 = run_one(
            1, mrom_path, mram_path, moracle, "-mut")
        expected_fail = False
        detail = []
        if qemu is not None and gem5 is not None:
            rq, rg = k2.decode_report(qemu), k2.decode_report(gem5)
            vq = k2.evaluate_report_bytes(qemu, moracle)[0]
            vg = k2.evaluate_report_bytes(gem5, moracle)[0]
            detail = [
                f"qemu={vq.value}/status={k2.STATUS_NAMES[rq.final_status]}"
                f"/mismatch={rq.mismatch_count}",
                f"gem5={vg.value}/status={k2.STATUS_NAMES[rg.final_status]}"
                f"/mismatch={rg.mismatch_count}",
            ]
            expected_fail = (
                verdict == k2.Verdict.FAIL
                and vq == k2.Verdict.FAIL and vg == k2.Verdict.FAIL
                and rq.final_status == k2.STATUS_FAIL
                and rg.final_status == k2.STATUS_FAIL
                and rq.mismatch_count > 0 and rg.mismatch_count > 0)
        if expected_fail:
            print(f"negative mutation({args.mutation}): dual=FAIL "
                  f"({' '.join(detail)}) as required")
        else:
            failures += 1
            print(f"negative mutation: unexpected {verdict.value} "
                  f"({' '.join(detail)})")
            for reason in reasons[:12]:
                print(f"  {reason}")

        verdict, reasons, _, _ = run_one(
            1, rom_path, ram_path, oracle, "-post")
        if verdict == k2.Verdict.PASS:
            print("post-restore round: PASS")
        else:
            failures += 1
            print(f"post-restore round: {verdict.value}")
            for reason in reasons[:12]:
                print(f"  {reason}")

    if failures:
        print(f"FAIL: {failures} failing round(s)")
        raise SystemExit(1)
    claims = (
        "one-shot timer preemption, frozen 198-word stack trap frame, "
        "rd1-63/rb1-63/ra0-63 transparency, handler call/ret pollution, "
        "real interrupted call-chain return, timer->PTW cross-CFX E1 with "
        "two disjoint LIFO frames, guest+oracle+cross-backend")
    nonclaims = (
        "same-CFX recursion, PTBR/TLB task switch, user<->supervisor, RF, "
        "Atomics/SMP, multi-hart, real UART/PLIC, Linux trap ABI, Minor/O3, "
        "performance")
    print(f"QEMU: pass=[{claims}] rounds={args.rounds}/{args.rounds}; "
          f"skip=[]; fail=[]; non-claim=[{nonclaims}]")
    print(f"gem5: pass=[{claims}] rounds={args.rounds}/{args.rounds}; "
          f"skip=[]; fail=[]; non-claim=[{nonclaims}]")
    print("PASS: KL-142a preemptive trap full-context dual-backend oracle")


if __name__ == "__main__":
    main()
