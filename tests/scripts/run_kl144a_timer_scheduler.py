#!/usr/bin/env python3
"""KL-144a integrated timer-driven K2 scheduler probe.

Task A primes a same-ASID virtual mapping, is interrupted inside a real
three-call RegRAS chain, and returns transparently through the frozen
198-word trap frame.  The timer handler only sets need_resched.  After the
chain unwinds, the cooperative boundary saves A's frozen 135-word task
frame, switches PTBR, invalidates the complete ASID set, and restores task B.
Task B then observes its distinct mapping at the same VA.

The same image bytes run on QEMU and gem5 FullSystem.  A mutation image omits
the A->B invalidate, exposing a real stale hit and a tlb_gen invariant failure.
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
import run_kl129a_tlb_probes as k129  # noqa: E402
import run_kl131a_async_dispatch_probes as k131  # noqa: E402
import run_kl133a_cfx_timer_probes as k133  # noqa: E402
import run_kl141a_coop_switch as k141  # noqa: E402
import run_kl142a_preemptive_trap as k142  # noqa: E402
import run_kl143a_address_space_switch as k143  # noqa: E402
from build_test_binary import UNIMP_ENCODING  # noqa: E402


Emit = k141.Emit
OP_CSZ = k141.OP_CSZ
OP_LDMO_RD = k141.OP_LDMO_RD
OP_STMO_RD = k141.OP_STMO_RD
OP_LDMO_RB = k141.OP_LDMO_RB
OP_STMO_RB = k141.OP_STMO_RB
OP_LDMO_RA = k141.OP_LDMO_RA
OP_STMO_RA = k141.OP_STMO_RA
MISC_AND = k141.MISC_AND
MISC_ORR = k141.MISC_ORR
MISC_XOR = k141.MISC_XOR

ROM_BASE = k131.ROM_BASE
ROM_SIZE = 0x10000
RAM_BASE = 0x80000000
RAM_SIZE = 0x200000
IDENTITY_SLOT_OFF = 0xFFF8
SCENARIO = k2.scenario_id_for("KL144a")

CFX_POWER = k131.CFX_POWER
CFX_TIMER = k131.CFX_TIMER
MODE_SUPV = k131.MODE_SUPV
MODE_CFX_POWER = MODE_SUPV | (CFX_POWER << 8)
MODE_CFX_TIMER = MODE_SUPV | (CFX_TIMER << 8)
CAUSE_TIMER = k133.CAUSE_TIMER
MASK_ALL = k131.MASK_ALL
OPEN_TIMER_CFX_MASK = MASK_ALL & ~(1 << CFX_TIMER)
OPEN_TIMER_CAUSE_MASK = MASK_ALL & ~CAUSE_TIMER

ASID = k143.ASID
ASID_BASE = k143.ASID_BASE
SHARED_VA = k143.SHARED_VA
ROOT_A, ROOT_B = k143.ROOT_A, k143.ROOT_B
VALUE_A, VALUE_B = k143.VALUE_A, k143.VALUE_B
TASK_A, TASK_B = 1, 2

CTRL = 0x8000F000
ADDR_CURSOR = CTRL + 0x08
ADDR_MISMATCH = CTRL + 0x10
ADDR_UNWIND = CTRL + 0x18
MDW = CTRL + 0x100
MDW_SEQ = 0
MDW_CUR = 10
MDW_TIMER = 11
MDW_NEED = 12
MDW_SWITCH = 13
MDW_TLB_GEN = 14
MDW_OBSERVED = 15
ADDR_SEQ = MDW
ADDR_CUR = MDW + MDW_CUR * 8
ADDR_TIMER = MDW + MDW_TIMER * 8
ADDR_NEED = MDW + MDW_NEED * 8
ADDR_SWITCH = MDW + MDW_SWITCH * 8
ADDR_TLB_GEN = MDW + MDW_TLB_GEN * 8
ADDR_OBSERVED = MDW + MDW_OBSERVED * 8

STACK_A_LO, STACK_A_TOP = 0x80060000, 0x80064000
STACK_B_LO, STACK_B_TOP = 0x80065000, 0x80068000
TRAP_FRAME_SIZE = 0x630
TRAP_WORDS = 198
TRAP_FRAME = STACK_A_TOP - TRAP_FRAME_SIZE
COOP_WORDS = 135
FRAME_A, FRAME_B = 0x80070000, 0x80071000
TRAP_TABLE = 0x80072000
FRAME_A_TABLE = 0x80073000
FRAME_B_TABLE = 0x80074000
ZERO_CONTEXT = 0x80075000

REPORT_PA = k141.REPORT_PA
REPORT_WINDOW = k141.REPORT_WINDOW
DOORBELL_OFF = k141.DOORBELL_OFF
DOORBELL = k141.DOORBELL
IDENTITY_MIRROR = k141.IDENTITY_MIRROR
EVIDENCE = os.path.join(REPO, ".work", "evidence", "kl144a-scheduler")

GUARDS = (
    (STACK_A_LO, 0x6AED144A00000001),
    (STACK_A_TOP, 0x6AED144A00000002),
    (STACK_B_LO, 0x6AED144B00000003),
    (STACK_B_TOP, 0x6AED144B00000004),
    (FRAME_A - 8, 0x6AED144A00000005),
    (FRAME_A + COOP_WORDS * 8, 0x6AED144A00000006),
    (FRAME_B - 8, 0x6AED144B00000007),
    (FRAME_B + COOP_WORDS * 8, 0x6AED144B00000008),
    (TRAP_TABLE - 8, 0x6AED144A00000009),
    (TRAP_TABLE + TRAP_WORDS * 8, 0x6AED144A0000000A),
    (REPORT_PA - 8, 0x6AED14400000000B),
    (REPORT_PA + REPORT_WINDOW, 0x6AED14400000000C),
)

N_CHECKPOINTS = 8
MASK48 = (1 << 48) - 1
MASK64 = (1 << 64) - 1


def trap_rd(reg):
    if reg == 62:
        return MASK_ALL
    if reg == 63:
        return OPEN_TIMER_CAUSE_MASK
    return 0xD144000000000000 | (reg << 24) | (reg << 8) | 0x5A


def trap_rb(reg):
    return 0xB144000000000000 | (reg << 24) | (reg << 8) | 0xA5


def task_rd(task, reg):
    return 0xD044000000000000 | (task << 32) | (reg << 8) | 0x5A


def task_rb(task, reg):
    return 0xB044000000000000 | (task << 32) | (reg << 8) | 0xA5


def task_special(task, reg):
    return 0xF044000000000000 | (task << 32) | (reg << 8) | 0x6B


def put_qword(image, address, value):
    offset = address - RAM_BASE
    if offset < 0 or offset + 8 > len(image):
        raise ValueError(f"RAM address outside image: {address:#x}")
    image[offset:offset + 8] = struct.pack(">Q", value & MASK64)


def packed_ptbr(root):
    return (ASID << 48) | root


def emit_check_eq(e, actual_rd, expected):
    k141.check_eq_rd(e, actual_rd, expected)


def emit_guard_check(e, label):
    e.mark(label)
    for address, value in GUARDS:
        e.load("rb", 8, address)
        e.ldo_rd(10, 8, 0)
        emit_check_eq(e, 10, value)
    e.ret()


def emit_check_words(e, label):
    """Args rb8=actual, rb9=expected, rd12=count."""
    e.mark(label)
    e.load("rb", 10, ADDR_MISMATCH)
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


def emit_checkpoint_writer(e, label):
    """Write one checkpoint.

    Args: rd8/9 event/task, rd10/11 saved/resume PC, rd17/18 mode/cause,
    rb9 frame, rd31 frame word count, rd27 packed PTBR, rd28 tlb_gen.
    """
    e.mark(label)
    e.orrr(MISC_ORR, 21, 8, 0)
    e.orrr(MISC_ORR, 22, 9, 0)
    e.orrr(MISC_ORR, 23, 10, 0)
    e.orrr(MISC_ORR, 24, 11, 0)
    e.orrr(MISC_ORR, 25, 17, 0)
    e.orrr(MISC_ORR, 26, 18, 0)
    e.orrr(MISC_ORR, 29, 27, 0)
    e.orrr(MISC_ORR, 30, 28, 0)
    e.orrr(MISC_ORR, 20, 31, 0)
    e.addi_rb(16, 9, 0)
    e.addi_rb(8, 16, 0)
    e.orrr(MISC_ORR, 12, 20, 0)
    e.call("FNV_WORDS")
    e.orrr(MISC_ORR, 18, 13, 0)
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
            (40, 23), (48, 24), (56, 18), (64, 14), (72, 29), (80, 30)):
        e.sto_rd(rd, 12, offset)
    e.addi_rb(12, 12, k2.CHECKPOINT_SIZE)
    e.sto_rb(12, 8, 0)
    e.ret()


def emit_checkpoint(e, event, task, frame, words, root, tlb_gen,
                    saved=None, resume=None, mode=MODE_CFX_POWER, cause=0):
    e.load("rd", 8, event)
    e.load("rd", 9, task)
    if saved:
        e.load_label("rd", 10, saved)
    else:
        e.load("rd", 10, 0)
    if resume:
        e.load_label("rd", 11, resume)
    else:
        e.load("rd", 11, 0)
    e.load("rd", 17, mode)
    e.load("rd", 18, cause)
    e.load("rb", 9, frame)
    e.load("rd", 31, words)
    e.load("rd", 27, packed_ptbr(root))
    e.load("rd", 28, tlb_gen)
    e.call("EMIT_CKPT")


def emit_trap_save(e):
    k142.emit_frame_save_no_scratch(e)
    k142.emit_frame_metadata(e)


def emit_trap_restore(e):
    k142.emit_frame_restore(e)


def emit_coop_save(e):
    e.load("rb", 13, FRAME_A)
    e.addi_rb(9, 13, 0x38)
    e.rrri(OP_STMO_RD, 32, 9, 0, 32)
    e.addi_rb(9, 13, 0x138)
    e.rrri(OP_STMO_RB, 32, 9, 0, 32)
    e.addi_rb(9, 13, 0x238)
    e.rrri(OP_STMO_RA, 0, 9, 0, 63)
    e.addi_rb(9, 13, 0x430)
    e.rrri(OP_STMO_RA, 63, 9, 0, 1)
    e.sto_rb(1, 13, 0x18)
    e.sto_rb(2, 13, 0x20)
    e.sto_rb(3, 13, 0x28)
    e.sto_rb(4, 13, 0x30)
    e.ldo_rd(9, 13, 0x430)
    e.load("rd", 10, MASK48)
    e.orrr(MISC_AND, 9, 9, 10)
    e.sto_rd(9, 13, 0)
    e.load("rd", 9, ASID)
    e.sto_rd(9, 13, 8)
    e.load("rd", 9, ROOT_A)
    e.sto_rd(9, 13, 16)


def emit_coop_restore_b(e):
    e.load("rb", 13, FRAME_B)
    e.addi_rb(9, 13, 0x238)
    e.rrri(OP_LDMO_RA, 0, 9, 0, 63)
    e.addi_rb(9, 13, 0x430)
    e.rrri(OP_LDMO_RA, 63, 9, 0, 1)
    e.addi_rb(9, 13, 0x38)
    e.rrri(OP_LDMO_RD, 32, 9, 0, 32)
    e.addi_rb(9, 13, 0x138)
    e.rrri(OP_LDMO_RB, 32, 9, 0, 32)
    e.ldo_rb(4, 13, 0x30)
    e.ldo_rb(3, 13, 0x28)
    e.ldo_rb(2, 13, 0x20)
    e.ldo_rb(1, 13, 0x18)
    e.ret()


def trap_frame(labels):
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
    words += [trap_rd(reg) for reg in range(1, 64)]
    words += [STACK_A_TOP] + [trap_rb(reg) for reg in range(2, 64)]
    words += k141.ras_model([
        labels["PUSH_L1"] + 4,
        labels["PUSH_L2"] + 4,
        labels["PUSH_L3"] + 4,
    ])
    assert len(words) == TRAP_WORDS
    return words


def coop_frame(labels, task):
    if task == TASK_A:
        pc, root, stack = labels["A_SWITCH_RETURN"], ROOT_A, STACK_A_TOP
    else:
        pc, root, stack = labels["TASK_B"], ROOT_B, STACK_B_TOP
    words = [
        pc, ASID, root, stack,
        task_special(task, 2), task_special(task, 3), task_special(task, 4),
    ]
    words += [task_rd(task, reg) for reg in range(32, 64)]
    words += [task_rb(task, reg) for reg in range(32, 64)]
    words += k141.ras_model([pc])
    assert len(words) == COOP_WORDS
    return words


def build_image(omit_invalidate=False):
    e = Emit()
    k131.emit_boot_stub(e.out, ROM_BASE + 0x200)

    e.mark("MAIN")
    e.load("rb", 1, STACK_A_TOP)
    e.load("rb", 8, ADDR_CUR)
    e.load("rd", 8, TASK_A)
    e.sto_rd(8, 8, 0)

    # Address-space A is active before INIT and its load fills set 6.
    k143.cfx_write_value(e, k143.CFX_PTW, k143.PTW_PTHI_CG, ASID, 0)
    k143.cfx_write_value(e, k143.CFX_PTW, k143.PTW_PAHI_CG, ASID, 0)
    k143.cfx_write_value(
        e, k143.CFX_PTW, k143.PTW_PERM_CG, k143.PTW_ENABLE_RC, 1 << ASID)
    k143.cfx_write_value(
        e, k143.CFX_TLB, k143.TLB_REG_CG, k143.TLB_ENABLE_RC, 1 << ASID)
    k143.cfx_write_value(
        e, k143.CFX_PTW, k143.PTW_PTBR_CG, ASID, ROOT_A)
    k143.emit_invalidate(e)
    e.load("rb", 8, ADDR_TLB_GEN)
    e.load("rd", 8, 1)
    e.sto_rd(8, 8, 0)
    e.load("rb", 3, SHARED_VA)
    e.ldo_rd(8, 3, 0)
    emit_check_eq(e, 8, VALUE_A)
    e.load("rb", 9, ADDR_OBSERVED)
    e.sto_rd(8, 9, 0)

    emit_checkpoint(
        e, k2.EVENT_INIT, TASK_A, ZERO_CONTEXT, COOP_WORDS, ROOT_A, 1)
    e.call("GUARD_CHECK")

    # Configure one-shot timer delivery while keeping TIMER masked until all
    # interrupted state is live.
    e.load_label("rd", 2, "TIMER_HANDLER")
    k131.write_crrr(
        e.out, k131.OP_CFX2RC, CFX_TIMER, 2, k131.RC_EXCP_VECTOR, 2)
    k131.set_excp_cause_mask(
        e.out, CFX_TIMER, MODE_SUPV, MASK_ALL, scratch=2)
    k131.set_global_mask(
        e.out, MODE_SUPV, OPEN_TIMER_CFX_MASK, scratch=2)
    k131.set_escape_mask(
        e.out, CFX_POWER, MODE_SUPV,
        MASK_ALL & ~(1 << k131.CFX_PTW), scratch=2)
    k131.set_escape_mask(
        e.out, CFX_TIMER, MODE_SUPV,
        MASK_ALL & ~(1 << k131.CFX_PTW), scratch=2)
    # The accepted K1 boot-fixture helper establishes inner_cfx_mask before
    # task execution.  No timer handler or scheduler path writes cg5.
    k131.craft_inner_cfx_mask(
        e.out, k131.CFX_PTW, OPEN_TIMER_CFX_MASK, scratch=2)
    k133.set_timer_mask(e.out, 0, scratch=2)

    e.mark("PUSH_L1")
    e.call("L1")
    e.load("rb", 8, ADDR_UNWIND)
    e.ldo_rd(8, 8, 0)
    emit_check_eq(e, 8, 3)
    e.load("rb", 8, ADDR_NEED)
    e.ldo_rd(8, 8, 0)
    emit_check_eq(e, 8, 1)

    # Re-establish the frozen cooperative task context after checker scratch.
    for reg in range(32, 64):
        e.load("rd", reg, task_rd(TASK_A, reg))
    for reg in range(32, 64):
        k142.load_full_rb(e, reg, task_rb(TASK_A, reg))
    for reg in range(2, 5):
        k142.load_full_rb(e, reg, task_special(TASK_A, reg))
    e.load("rb", 1, STACK_A_TOP)
    e.mark("A_SWITCH_CALL")
    e.call("SWITCH")
    e.mark("A_SWITCH_RETURN")
    e.word(UNIMP_ENCODING)

    e.mark("L1")
    e.mark("PUSH_L2")
    e.call("L2")
    e.load("rb", 8, ADDR_UNWIND)
    e.ldo_rd(9, 8, 0)
    e.addi_rd(9, 9, 1)
    e.sto_rd(9, 8, 0)
    e.ret()

    e.mark("L2")
    e.mark("PUSH_L3")
    e.call("L3")
    e.load("rb", 8, ADDR_UNWIND)
    e.ldo_rd(9, 8, 0)
    e.addi_rd(9, 9, 1)
    e.sto_rd(9, 8, 0)
    e.ret()

    e.mark("L3")
    k133.set_timer_counter0(e.out, 1, scratch=2)
    k133.set_timer_ctrl(e.out, k133.TIMER_CTRL_ENABLE, scratch=2)
    for reg in range(2, 64):
        k142.load_full_rb(e, reg, trap_rb(reg))
    for reg in range(1, 64):
        e.load("rd", reg, trap_rd(reg))
    k131.write_crrr(
        e.out, k131.OP_CFX2RC, CFX_TIMER, MODE_SUPV,
        k131.RC_EXCP_CAUSE_MASK, 63)
    e.mark("POISON")
    e.word(UNIMP_ENCODING)
    e.mark("TRAP_RESUME")
    k142.emit_frame_save_no_scratch(e)
    e.load("rb", 8, TRAP_FRAME)
    e.load("rb", 9, TRAP_TABLE)
    e.load("rd", 12, TRAP_WORDS)
    e.call("CHECK_WORDS")
    emit_checkpoint(
        e, k2.EVENT_TRAP_RETURN, TASK_A, TRAP_FRAME, TRAP_WORDS,
        ROOT_A, 1, saved="POISON", resume="TRAP_RESUME",
        mode=MODE_CFX_TIMER, cause=CAUSE_TIMER)
    e.load("rb", 8, ADDR_UNWIND)
    e.ldo_rd(9, 8, 0)
    e.addi_rd(9, 9, 1)
    e.sto_rd(9, 8, 0)
    e.ret()

    e.mark("TIMER_HANDLER")
    # Re-entry exclusion is the only pre-save instruction and uses the live
    # rd62 value deliberately included in the expected frame.
    k131.write_crrr(
        e.out, k131.OP_CFX2RC, CFX_TIMER, MODE_SUPV,
        k131.RC_EXCP_CAUSE_MASK, 62)
    emit_trap_save(e)
    e.addi_rb(1, 1, -TRAP_FRAME_SIZE)
    e.load("rb", 8, ADDR_TIMER)
    e.ldo_rd(9, 8, 0)
    e.addi_rd(9, 9, 1)
    e.sto_rd(9, 8, 0)
    e.load("rb", 8, ADDR_NEED)
    e.load("rd", 9, 1)
    e.sto_rd(9, 8, 0)
    e.load("rb", 8, TRAP_FRAME)
    e.load("rb", 9, TRAP_TABLE)
    e.load("rd", 12, TRAP_WORDS)
    e.call("CHECK_WORDS")
    emit_checkpoint(
        e, k2.EVENT_TIMER, TASK_A, TRAP_FRAME, TRAP_WORDS,
        ROOT_A, 1, saved="POISON", resume="TRAP_RESUME",
        mode=MODE_CFX_TIMER, cause=CAUSE_TIMER)
    emit_checkpoint(
        e, k2.EVENT_TRAP_ENTER, TASK_A, TRAP_FRAME, TRAP_WORDS,
        ROOT_A, 1, saved="POISON", resume="TRAP_RESUME",
        mode=MODE_CFX_TIMER, cause=CAUSE_TIMER)
    k131.write_crrr(
        e.out, k131.OP_CFX2RC, CFX_TIMER, k133.CG_TIMER,
        k133.RC_TIMER_PENDING, 0)
    k131.write_crrr(
        e.out, k131.OP_CFX2RC, CFX_TIMER, k131.CG_COMMON,
        k131.RC_PENDING, 0)
    e.call("HANDLER_CLOBBER")
    emit_trap_restore(e)
    k131.write_ciii(e.out, k131.OP_ESCAPE, CFX_TIMER, 1)

    e.mark("HANDLER_CLOBBER")
    for reg in range(2, 64):
        k142.load_full_rb(
            e, reg, 0xA144000000000000 | (reg << 8) | 0xAA, scratch=1)
    for reg in range(1, 64):
        e.load("rd", reg, 0xE144000000000000 | (reg << 8) | 0xEE)
    e.ret()

    e.mark("SWITCH")
    emit_coop_save(e)
    e.load("rb", 8, FRAME_A)
    e.load("rb", 9, FRAME_A_TABLE)
    e.load("rd", 12, COOP_WORDS)
    e.call("CHECK_WORDS")
    emit_checkpoint(
        e, k2.EVENT_COOP_SAVE, TASK_A, FRAME_A, COOP_WORDS,
        ROOT_A, 1, saved="A_SWITCH_RETURN")
    e.load("rb", 8, ADDR_SWITCH)
    e.load("rd", 8, 1)
    e.sto_rd(8, 8, 0)
    e.load("rb", 8, ADDR_CUR)
    e.load("rd", 8, TASK_B)
    e.sto_rd(8, 8, 0)

    # The target address-space binding is consumed from B's cooperative
    # descriptor; the scheduler has no hidden second root selection.
    e.load("rb", 13, FRAME_B)
    e.load("rb", 8, FRAME_B)
    e.load("rb", 9, FRAME_B_TABLE)
    e.load("rd", 12, COOP_WORDS)
    e.call("CHECK_WORDS")
    e.load("rb", 13, FRAME_B)
    e.ldo_rd(8, 13, 8)
    emit_check_eq(e, 8, ASID)
    e.ldo_rd(2, 13, 16)
    emit_check_eq(e, 2, ROOT_B)
    k143.cfx_write_reg(
        e, k143.CFX_PTW, k143.PTW_PTBR_CG, ASID, 2)
    generation = 1
    if not omit_invalidate:
        k143.emit_invalidate(e)
        generation = 2
        e.load("rb", 8, ADDR_TLB_GEN)
        e.load("rd", 8, generation)
        e.sto_rd(8, 8, 0)
    e.load("rb", 3, SHARED_VA)
    e.ldo_rd(8, 3, 0)
    emit_check_eq(e, 8, VALUE_B)
    e.load("rb", 9, ADDR_OBSERVED)
    e.sto_rd(8, 9, 0)
    e.load("rb", 8, ADDR_NEED)
    e.load("rd", 8, 0)
    e.sto_rd(8, 8, 0)
    emit_checkpoint(
        e, k2.EVENT_AS_SWITCH, TASK_B, FRAME_B, COOP_WORDS,
        ROOT_B, generation)
    emit_checkpoint(
        e, k2.EVENT_COOP_RESTORE, TASK_B, FRAME_B, COOP_WORDS,
        ROOT_B, generation, resume="TASK_B")
    emit_coop_restore_b(e)

    e.mark("TASK_B")
    e.rb2rd(8, 1)
    emit_check_eq(e, 8, STACK_B_TOP)
    for reg in range(32, 64):
        emit_check_eq(e, reg, task_rd(TASK_B, reg))
    for reg in range(32, 64):
        e.rb2rd(8, reg)
        emit_check_eq(e, 8, task_rb(TASK_B, reg))
    for reg in range(2, 5):
        e.rb2rd(8, reg)
        emit_check_eq(e, 8, task_special(TASK_B, reg))
    for address, expected in (
            (ADDR_CUR, TASK_B), (ADDR_TIMER, 1), (ADDR_NEED, 0),
            (ADDR_SWITCH, 1), (ADDR_TLB_GEN, 2),
            (ADDR_OBSERVED, VALUE_B), (ADDR_UNWIND, 3)):
        e.load("rb", 8, address)
        e.ldo_rd(8, 8, 0)
        emit_check_eq(e, 8, expected)
    e.call("GUARD_CHECK")
    emit_checkpoint(
        e, k2.EVENT_FINAL, TASK_B, FRAME_B, COOP_WORDS,
        ROOT_B, generation)

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

    k141.emit_fnv_words(e, "FNV_WORDS")
    emit_check_words(e, "CHECK_WORDS")
    emit_guard_check(e, "GUARD_CHECK")
    emit_checkpoint_writer(e, "EMIT_CKPT")
    e.pad_unimp(IDENTITY_SLOT_OFF)
    e.out.extend(b"\0" * 8)
    if len(e.out) > ROM_SIZE:
        raise ValueError("ROM image overflow")
    rom = bytearray(e.finish())

    trap = trap_frame(e.labels)
    frame_a = coop_frame(e.labels, TASK_A)
    frame_b = coop_frame(e.labels, TASK_B)
    ram = bytearray(RAM_SIZE)
    put_qword(ram, ADDR_CURSOR, REPORT_PA + k2.HEADER_SIZE)
    for address, value in GUARDS:
        put_qword(ram, address, value)
    for address, words in (
            (TRAP_TABLE, trap), (FRAME_A_TABLE, frame_a),
            (FRAME_B_TABLE, frame_b), (FRAME_B, frame_b)):
        offset = address - RAM_BASE
        ram[offset:offset + len(words) * 8] = struct.pack(
            f">{len(words)}Q", *words)

    put_qword(
        ram, k143.L1_A + k143.L1_INDEX * 8,
        (k143.L2_A & 0xFFFFFFFFFFFF0000) | 1)
    put_qword(
        ram, k143.L2_A + k143.L2_INDEX * 8,
        k129.normal_pte(k143.PA_A, [3], k143.PERM_R))
    put_qword(
        ram, k143.L1_B + k143.L1_INDEX * 8,
        (k143.L2_B & 0xFFFFFFFFFFFF0000) | 1)
    put_qword(
        ram, k143.L2_B + k143.L2_INDEX * 8,
        k129.normal_pte(k143.PA_B, [3], k143.PERM_R))
    put_qword(ram, k143.PA_A + (SHARED_VA & 0xFFFF), VALUE_A)
    put_qword(ram, k143.PA_B + (SHARED_VA & 0xFFFF), VALUE_B)

    identity = k2.image_identity(
        bytes(rom), bytes(ram),
        rom_identity_slot=(IDENTITY_SLOT_OFF, 8),
        ram_report_area=(REPORT_PA - RAM_BASE, k2.MAX_REPORT_SIZE))
    rom = bytearray(
        k2.embed_image_identity(bytes(rom), IDENTITY_SLOT_OFF, identity))
    put_qword(ram, IDENTITY_MIRROR, identity)
    return bytes(rom), bytes(ram), e.labels, (trap, frame_a, frame_b), identity


def mdw_digest(seq, current, timer, need, switches, tlb_gen, observed):
    words = [0] * 16
    words[MDW_SEQ] = seq
    words[MDW_CUR] = current
    words[MDW_TIMER] = timer
    words[MDW_NEED] = need
    words[MDW_SWITCH] = switches
    words[MDW_TLB_GEN] = tlb_gen
    words[MDW_OBSERVED] = observed
    return k2.fnv1a64(words)


def build_oracle(labels, frames, identity):
    trap, frame_a, frame_b = frames
    zero_digest = k2.fnv1a64([0] * COOP_WORDS)
    trap_digest = k2.fnv1a64(trap)
    a_digest = k2.fnv1a64(frame_a)
    b_digest = k2.fnv1a64(frame_b)

    def ck(event, task, context, seq, current, timer, need, switches,
           tlb_gen, observed, root, saved=0, resume=0,
           mode=MODE_CFX_POWER, cause=0):
        return k2.ExpectedCheckpoint(
            event_kind=event, task_id=task,
            run_mode=mode & 0xFF, cfx_code=(mode >> 8) & 0xFF,
            cause=cause, saved_pc=saved, resume_pc=resume,
            context_digest=context,
            memory_digest=mdw_digest(
                seq, current, timer, need, switches, tlb_gen, observed),
            asid=ASID, ptbr=root, tlb_gen=tlb_gen)

    expected = [
        ck(k2.EVENT_INIT, TASK_A, zero_digest, 0, TASK_A, 0, 0, 0, 1,
           VALUE_A, ROOT_A),
        ck(k2.EVENT_TIMER, TASK_A, trap_digest, 1, TASK_A, 1, 1, 0, 1,
           VALUE_A, ROOT_A, labels["POISON"], labels["TRAP_RESUME"],
           MODE_CFX_TIMER, CAUSE_TIMER),
        ck(k2.EVENT_TRAP_ENTER, TASK_A, trap_digest, 2, TASK_A, 1, 1, 0,
           1, VALUE_A, ROOT_A, labels["POISON"], labels["TRAP_RESUME"],
           MODE_CFX_TIMER, CAUSE_TIMER),
        ck(k2.EVENT_TRAP_RETURN, TASK_A, trap_digest, 3, TASK_A, 1, 1, 0,
           1, VALUE_A, ROOT_A, labels["POISON"], labels["TRAP_RESUME"],
           MODE_CFX_TIMER, CAUSE_TIMER),
        ck(k2.EVENT_COOP_SAVE, TASK_A, a_digest, 4, TASK_A, 1, 1, 0, 1,
           VALUE_A, ROOT_A, labels["A_SWITCH_RETURN"], 0),
        ck(k2.EVENT_AS_SWITCH, TASK_B, b_digest, 5, TASK_B, 1, 0, 1,
           2, VALUE_B, ROOT_B),
        ck(k2.EVENT_COOP_RESTORE, TASK_B, b_digest, 6, TASK_B, 1, 0, 1,
           2, VALUE_B, ROOT_B,
           0, labels["TASK_B"]),
        ck(k2.EVENT_FINAL, TASK_B, b_digest, 7, TASK_B, 1, 0, 1,
           2, VALUE_B, ROOT_B),
    ]
    assert len(expected) == N_CHECKPOINTS
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
        raise TransportError("run image identity mismatch")


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
    for backend, data in (("qemu", qemu), ("gem5", gem5)):
        with open(os.path.join(
                EVIDENCE, f"report-{backend}{tag}-{round_no:02d}.bin"), "wb") as fh:
            fh.write(data)
    verdict, reasons = k2.compare_dual_backend(qemu, gem5, oracle)
    return verdict, reasons, qemu, gem5


def write_image(tag, omit_invalidate=False):
    rom, ram, labels, frames, identity = build_image(omit_invalidate)
    # A mutation receives its own image identity and resolved PC labels, but
    # never a relaxed semantic oracle: generation=2 and VALUE_B remain the
    # required protocol outcome even when the guest omits invalidate.
    oracle = build_oracle(labels, frames, identity)
    rom_path = os.path.join(EVIDENCE, f"kl144a-{tag}.bin")
    ram_path = os.path.join(EVIDENCE, f"kl144a-{tag}-ram.bin")
    with open(rom_path, "wb") as fh:
        fh.write(rom)
    with open(ram_path, "wb") as fh:
        fh.write(ram)
    return rom_path, ram_path, oracle, rom, ram


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--skip-negative", action="store_true")
    args = parser.parse_args()
    if args.rounds < 1:
        parser.error("--rounds must be positive")

    os.makedirs(EVIDENCE, exist_ok=True)
    rom_path, ram_path, oracle, rom, ram = write_image("positive")
    print(f"image: sha256-rom={hashlib.sha256(rom).hexdigest()}")
    print(f"image: sha256-ram={hashlib.sha256(ram).hexdigest()}")
    print(f"image: canonical identity={oracle.image_identity:#018x} "
          f"checkpoints={N_CHECKPOINTS}")

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
        mrom, mram, moracle, _, _ = write_image("mutation", True)
        verdict, reasons, qemu, gem5 = run_one(
            1, mrom, mram, moracle, "-mut")
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
            print("negative omit-invalidate: dual=FAIL "
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
        "timer-driven reschedule, transparent 198-word trap context, "
        "escape-before-cooperative boundary, 135-word task switch, "
        "same-ASID PTBR+invalidate+tlb_gen, stale-hit negative, "
        "guest+oracle+cross-backend")
    nonclaims = (
        "user<->supervisor, RF, Atomics/SMP, multi-hart, real UART/PLIC, "
        "Linux scheduler/trap/clockevent/pgtable API, Minor/O3, performance")
    print(f"QEMU: pass=[{claims}] rounds={args.rounds}/{args.rounds}; "
          f"skip=[]; fail=[]; non-claim=[{nonclaims}]")
    print(f"gem5: pass=[{claims}] rounds={args.rounds}/{args.rounds}; "
          f"skip=[]; fail=[]; non-claim=[{nonclaims}]")
    print("PASS: KL-144a integrated timer-driven scheduler")


if __name__ == "__main__":
    main()
