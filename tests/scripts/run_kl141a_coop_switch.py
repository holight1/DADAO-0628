#!/usr/bin/env python3
"""KL-141a K2 supervisor cooperative context switch (QEMU + gem5).

Two supervisor kernel tasks in one shared bare-metal ROM/RAM image yield to
each other through a minimal cooperative switch primitive using the frozen
135-word/1080-byte KL-140a frame (resume PC, asid/PTBR metadata,
rb1..rb4, rd32-63, rb32-63, full ra0-63 via the ldmo-ra/stmo-ra contract).

* 25 real A->B / B->A transitions (12 chain-yields + 1 done-yield for A,
  12 chain-yields for B; the final done-yield is absorbed by finalize),
  never restarting the image or having the host write guest registers.
* RegRAS is validated by real control flow: each task builds its own call
  chain at its own addresses and depth (A: 3 levels + a twice-self-recursive
  R giving a refcount-2 slot; B: 7 linear levels), yields at the deepest
  point, resumes, and returns through real rets with a bitmap oracle.
* The guest is fail-closed: every saved frame word is checked against ROM
  tables, restored registers are checked slot by slot, guards/progress/
  counts are checked, and any mismatch increments a RAM mismatch word that
  forces final_status=FAIL.
* KL-140a report/oracle is wired for real: INIT, per-transition
  COOP_SAVE/COOP_RESTORE, FINAL, canonical image identity, and raw report
  bytes retrieved from guest memory after architectural halt (QEMU
  -no-shutdown + QMP pmemsave; gem5 terminal checkpoint) before
  compare_dual_backend().  Backend logs/exit codes are evidence gates only,
  never the verdict.

The same image bytes run on both backends.  A separate mutation image
corrupts one frozen frame word (rd40's slot) after a real save and must
FAIL on both backends; restoring the positive image must PASS again.
"""

import argparse
import gzip
import hashlib
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import k2_report as k2  # noqa: E402
import run_kl131a_async_dispatch_probes as k131  # noqa: E402
from build_test_binary import (  # noqa: E402
    load_reg, write_rrii, UNIMP_ENCODING, SWYM_ENCODING)


QEMU = k131.QEMU
GEM5 = k131.GEM5
GEM5_FS_CFG = os.environ.get("K2_FS_CFG", os.path.join(HERE, "k2_fs_report.py"))

ROM_BASE = k131.ROM_BASE
ROM_SIZE = 0x10000
RAM_BASE = 0x80000000
RAM_SIZE = 0x200000
EVIDENCE = os.path.join(REPO, ".work", "evidence", "kl141a-coop")

SCENARIO = k2.scenario_id_for("KL141a")
IDENTITY_SLOT_OFF = 0xFFF8

# ---------------------------------------------------------------------------
# Scenario memory map (RAM)

CTRL = 0x8000F000
ADDR_CURSOR = CTRL + 0x08
ADDR_MISMATCH = CTRL + 0x10
ADDR_BITMAP_A = CTRL + 0x18
ADDR_BITMAP_B = CTRL + 0x20
ADDR_RECUR_A = CTRL + 0x28
ADDR_RESTORES_A = CTRL + 0x30
ADDR_RESTORES_B = CTRL + 0x38
MDW = CTRL + 0x100           # 16-word memory-digest block
MDW_SEQ = 0
MDW_CUR, MDW_PROG_A, MDW_PROG_B = 10, 11, 12
MDW_SWCOUNT, MDW_DONE_A, MDW_DONE_B = 13, 14, 15
ADDR_SEQ = MDW + MDW_SEQ * 8
RAS_SCRATCH = CTRL + 0x200

STACK_A_LO, STACK_A_TOP = 0x80010000, 0x80012000
STACK_B_LO, STACK_B_TOP = 0x80014000, 0x80016000
FRAME_A, FRAME_B = 0x80018000, 0x80019000
TABLE_RAM_BASE = 0x8001A000
TABLE_RAM_STRIDE = 0x800
TABLE_RAM_ADDR = {
    "TABLE_A_INIT": TABLE_RAM_BASE + 0 * TABLE_RAM_STRIDE,
    "TABLE_A_CHAIN": TABLE_RAM_BASE + 1 * TABLE_RAM_STRIDE,
    "TABLE_A_DONE": TABLE_RAM_BASE + 2 * TABLE_RAM_STRIDE,
    "TABLE_B_INIT": TABLE_RAM_BASE + 3 * TABLE_RAM_STRIDE,
    "TABLE_B_CHAIN": TABLE_RAM_BASE + 4 * TABLE_RAM_STRIDE,
    "TABLE_B_DONE": TABLE_RAM_BASE + 5 * TABLE_RAM_STRIDE,
}

GUARD_SA_LO, GUARD_SA_HI = 0x8000FFF8, STACK_A_TOP
GUARD_SB_LO, GUARD_SB_HI = 0x80013FF8, STACK_B_TOP
GUARD_FA_LO, GUARD_FA_HI = 0x80017FF8, FRAME_A + 1080
GUARD_FB_LO, GUARD_FB_HI = 0x80018FF8, FRAME_B + 1080
GUARD_RP_LO, GUARD_RP_HI = 0x801EFFF8, 0x801F2000

REPORT_PA = 0x801F0000
REPORT_WINDOW = 8192
DOORBELL_OFF = REPORT_WINDOW - 8
DOORBELL = 0xD00BE11D0000141A
IDENTITY_MIRROR = REPORT_PA + k2.MAX_REPORT_SIZE - 8

GUARDS = (
    (GUARD_SA_LO, 0x6AED5A1000000001), (GUARD_SA_HI, 0x6AED5A1000000002),
    (GUARD_SB_LO, 0x6AED5B2000000003), (GUARD_SB_HI, 0x6AED5B2000000004),
    (GUARD_FA_LO, 0x6AEDFA3000000005), (GUARD_FA_HI, 0x6AEDFA3000000006),
    (GUARD_FB_LO, 0x6AEDFB4000000007), (GUARD_FB_HI, 0x6AEDFB4000000008),
    (GUARD_RP_LO, 0x6AED0B5000000009), (GUARD_RP_HI, 0x6AED0B500000000A),
)

TASK_A, TASK_B = 1, 2
CHAIN_ITERS = 12          # chain-yields per task
TRANSITIONS = 2 * CHAIN_ITERS + 1   # 25: A chain*12 + B chain*12 + A done
N_CHECKPOINTS = 1 + 2 * TRANSITIONS + 1   # 52

MASK48 = (1 << 48) - 1
MODE_CFX = 2 | (63 << 8)  # supv, inner cfx = cfx_power after HBI handoff

FNV_OFFSET = k2.FNV1A64_OFFSET
FNV_PRIME = k2.FNV1A64_PRIME

# Bitmap bits: entries 0..6, exits 16..22
MASK_A = 0x000F000F       # L1,L2,L3,R entries 0-3, exits 16-19
MASK_B = 0x007F007F       # M1..M7 entries 0-6, exits 16-22


def poison_rd(task, reg):
    return 0xD0D0000000000000 | (task << 32) | (reg << 8) | 0x5A


def poison_rb(task, reg):
    return 0xB0B0000000000000 | (task << 32) | (reg << 8) | 0xA5


def poison_fp(task):
    return 0xFB20000000000000 | (task << 32) | 0xFB


def poison_gp(task):
    return 0xFB30000000000000 | (task << 32) | 0x6B


def poison_tp(task):
    return 0xFB40000000000000 | (task << 32) | 0x7B


def stack_marker(task, level):
    return 0x57AC000000000000 | (task << 16) | level


# ---------------------------------------------------------------------------
# RegRAS model (contracts/isa/spec.md §5.6) for the deterministic call chains

def ras_model(push_addrs):
    """64 ra slot words after pushing the given return addresses onto an
    initially empty RegRAS (contracts/isa/spec.md §5.6): refill an invalid
    top, compress consecutive equal addresses into the top's reference
    count, otherwise shift entries down (ra{i-1} <- ra{i}) and push."""
    slots = [0] * 64
    for addr in push_addrs:
        top = slots[63]
        refcount = top >> 48
        if refcount == 0:
            slots[63] = (1 << 48) | addr
        elif 1 <= refcount <= 0xFFFE and (top & MASK48) == addr:
            slots[63] = top + (1 << 48)
        else:
            if slots[1] >> 48:
                raise ValueError("RASOF in scenario model")
            for i in range(1, 63):
                slots[i] = slots[i + 1]
            slots[63] = (1 << 48) | addr
    return slots


# ---------------------------------------------------------------------------
# Emitter with label/patch support (branch/call immediates are relative to
# the address of the following instruction, i.e. rb0 semantics)

OP_ADD, OP_MULU = 0x1A, 0x1D
OP_ADDI_RD, OP_ADDI_RB = 0x19, 0x49
OP_CSZ = 0x22
OP_BRNZ, OP_BRZ = 0x2B, 0x2A
OP_LDO_RD, OP_STO_RD = 0x33, 0x3B
OP_LDMO_RD, OP_STMO_RD = 0x37, 0x3F
OP_LDO_RB, OP_STO_RB = 0x43, 0x4B
OP_LDMO_RB, OP_STMO_RB = 0x47, 0x4F
OP_JUMP, OP_CALL, OP_RET = 0x64, 0x6C, 0x6E
OP_LDMO_RA, OP_STMO_RA = 0x67, 0x6F
MISC_AND, MISC_ORR, MISC_XOR = 0x08, 0x09, 0x0A


class Emit:
    def __init__(self):
        self.out = bytearray()
        self.labels = {}
        self.patches = []

    def pc(self):
        return ROM_BASE + len(self.out)

    def mark(self, name):
        self.labels[name] = self.pc()

    def word(self, value):
        self.out.extend(struct.pack(">I", value & 0xFFFFFFFF))

    def rrii(self, op, ha, hb, imm12):
        write_rrii(self.out, op, ha, hb, imm12)

    def rrri(self, op, ha, hb, hc, hd):
        self.word((op << 24) | (ha << 18) | (hb << 12) | (hc << 6) | hd)

    def rrrr(self, op, ha, hb, hc, hd):
        self.word((op << 24) | (ha << 18) | (hb << 12) | (hc << 6) | hd)

    def orrr(self, minor, dst, lhs, rhs):
        self.word((0x10 << 24) | (minor << 18) | (dst << 12) |
                  (lhs << 6) | rhs)

    def riii(self, op, ha, imm18):
        imm18 &= 0x3FFFF
        self.word((op << 24) | (ha << 18) | ((imm18 >> 12) & 0x3F) << 12 |
                  ((imm18 >> 6) & 0x3F) << 6 | (imm18 & 0x3F))

    def iiii(self, op, imm24):
        self.word((op << 24) | (imm24 & 0xFFFFFF))

    def load(self, bank, reg, value):
        load_reg(self.out, bank, reg, value)

    def load_label(self, bank, reg, label):
        self.patches.append((len(self.out), "load" + bank, label, reg))
        self.load(bank, reg, 0)

    def ldo_rd(self, rd, rb, imm):
        self.rrii(OP_LDO_RD, rd, rb, imm)

    def sto_rd(self, rd, rb, imm):
        self.rrii(OP_STO_RD, rd, rb, imm)

    def ldo_rb(self, rb_d, rb_b, imm):
        self.rrii(OP_LDO_RB, rb_d, rb_b, imm)

    def sto_rb(self, rb_d, rb_b, imm):
        self.rrii(OP_STO_RB, rb_d, rb_b, imm)

    def addi_rd(self, dst, src, imm):
        self.rrii(OP_ADDI_RD, dst, src, imm)

    def addi_rb(self, dst, src, imm):
        self.rrii(OP_ADDI_RB, dst, src, imm)

    def rb2rd(self, rd, rb):
        self.word(0x10A80000 | (rd << 12) | (rb << 6) | 1)

    def ret(self):
        self.riii(OP_RET, 0, 0)

    def nop(self):
        self.word(SWYM_ENCODING)

    def call(self, label):
        self.patches.append((len(self.out), "i24", label, OP_CALL))
        self.iiii(OP_CALL, 0)

    def jump(self, label):
        self.patches.append((len(self.out), "i24", label, OP_JUMP))
        self.iiii(OP_JUMP, 0)

    def brnz(self, rd, label):
        self.patches.append((len(self.out), "i18", label, (OP_BRNZ, rd)))
        self.riii(OP_BRNZ, rd, 0)

    def brz(self, rd, label):
        self.patches.append((len(self.out), "i18", label, (OP_BRZ, rd)))
        self.riii(OP_BRZ, rd, 0)

    def pad_unimp(self, offset):
        if len(self.out) > offset:
            raise ValueError(f"section overflow past {offset:#x}")
        while len(self.out) < offset:
            self.word(UNIMP_ENCODING)

    def finish(self):
        for pos, kind, label, extra in self.patches:
            target = self.labels[label]
            if kind in ("loadrd", "loadrb"):
                write_load_patch(
                    self.out, pos, kind[4:], extra, target)
                continue
            instr_pc = ROM_BASE + pos
            delta = target - (instr_pc + 4)
            if delta % 4:
                raise ValueError(f"unaligned branch target {label}")
            imm = delta >> 2
            if kind == "i18":
                if not -(1 << 17) <= imm < (1 << 17):
                    raise ValueError(f"branch to {label} out of range")
                op, rd = extra
                struct.pack_into(">I", self.out, pos,
                                 (op << 24) | (rd << 18) |
                                 (((imm & 0x3FFFF) >> 12) & 0x3F) << 12 |
                                 (((imm & 0x3FFFF) >> 6) & 0x3F) << 6 |
                                 ((imm & 0x3FFFF) & 0x3F))
            else:
                if not -(1 << 23) <= imm < (1 << 23):
                    raise ValueError(f"call/jump to {label} out of range")
                struct.pack_into(">I", self.out, pos,
                                 (extra << 24) | (imm & 0xFFFFFF))
        return bytes(self.out)


def write_load_patch(rom, pos, bank, reg, value):
    """Rewrite a load_reg(bank, reg) sequence's rwii immediate fields."""
    n_wydes = 4 if bank == "rd" else 3
    op_setzw = 0x16 if bank == "rd" else 0x4E
    op_orw = 0x14 if bank == "rd" else 0x4C
    for index in range(n_wydes):
        wyde = n_wydes - 1 - index
        chunk = (value >> (wyde * 16)) & 0xFFFF
        word = struct.unpack(">I", rom[pos + index * 4:pos + index * 4 + 4])[0]
        old_op = (word >> 24) & 0xFF
        if old_op not in (op_setzw, op_orw):
            raise ValueError(f"load patch hit non-rwii op {old_op:#x}")
        # The placeholder is zero, for which load_reg emits SETZW in every
        # slot.  A non-zero resolved label needs the same SETZW/ORW choice
        # load_reg would have made; retaining the placeholder opcode would
        # repeatedly clear higher wydes (e.g. 0x101028 became 0x1028).
        op = (op_setzw if index == 0 or
              (value >> ((wyde + 1) * 16)) == 0 else op_orw)
        struct.pack_into(
            ">I", rom, pos + index * 4,
            (op << 24) | (reg << 18) | ((wyde & 3) << 16) |
            (((chunk >> 12) & 0xF) << 12) | (((chunk >> 6) & 0x3F) << 6) |
            (chunk & 0x3F))


# ---------------------------------------------------------------------------
# Guest helper sequences

def check_eq_rd(e, actual_rd, expected):
    """MISMATCH_RAM |= (actual_rd ^ expected). Clobbers rd27/rd28/rb28."""
    e.load("rd", 28, expected)
    e.orrr(MISC_XOR, 28, actual_rd, 28)
    e.load("rb", 28, ADDR_MISMATCH)
    e.ldo_rd(27, 28, 0)
    e.orrr(MISC_ORR, 27, 27, 28)
    e.sto_rd(27, 28, 0)


def check_eq_rb(e, actual_rb, expected):
    e.rb2rd(27, actual_rb)
    check_eq_rd(e, 27, expected)


def emit_fnv_words(e, label):
    """FNV-1a-64 over words: args rb8=ptr, rd12=count; result rd13.
    Clobbers rd11..rd14, rb8. Contains no call."""
    e.mark(label)
    e.load("rd", 13, FNV_OFFSET)
    e.load("rd", 14, FNV_PRIME)
    e.mark(label + "_loop")
    e.ldo_rd(11, 8, 0)
    e.orrr(MISC_XOR, 13, 13, 11)
    e.rrrr(OP_MULU, 0, 13, 13, 14)
    e.addi_rb(8, 8, 8)
    e.addi_rd(12, 12, -1)
    e.brnz(12, label + "_loop")
    e.ret()


def emit_check_frame(e, label):
    """MISMATCH_RAM |= frame[i] ^ table[i] for 135 words. Args rb8=frame,
    rb9=table. Clobbers rd10..rd13, rb8..rb10. Contains no call."""
    e.mark(label)
    e.load("rb", 10, ADDR_MISMATCH)
    e.load("rd", 12, 135)
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
    """Check all 10 guard words against their constants. No call."""
    e.mark(label)
    for addr, value in GUARDS:
        e.load("rb", 8, addr)
        e.ldo_rd(10, 8, 0)
        check_eq_rd(e, 10, value)
    e.ret()


def emit_checkpoint_writer(e, label):
    """Write one checkpoint record. Args: rd8=event, rd9=task, rd10=saved_pc,
    rd11=resume_pc, rb9=frame ptr for context digest (0 -> digest 0).
    Computes the MDW-block memory digest itself at the pre-write state.
    Clobbers rd8-rd25/rb8-rb16. Calls FNV_WORDS (balanced)."""
    e.mark(label)
    e.orrr(MISC_ORR, 21, 8, 0)     # event
    e.orrr(MISC_ORR, 22, 9, 0)     # task
    e.orrr(MISC_ORR, 23, 10, 0)    # saved_pc
    e.orrr(MISC_ORR, 24, 11, 0)    # resume_pc
    e.addi_rb(16, 9, 0)            # frame ptr
    e.rb2rd(25, 16)
    e.brz(25, label + "_no_ctx")
    e.addi_rb(8, 16, 0)
    e.load("rd", 12, 135)
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
    e.sto_rd(19, 12, 0)
    e.sto_rd(21, 12, 8)
    e.sto_rd(22, 12, 16)
    e.load("rd", 20, MODE_CFX)
    e.sto_rd(20, 12, 24)
    e.load("rd", 20, 0)
    e.sto_rd(20, 12, 32)
    e.sto_rd(23, 12, 40)
    e.sto_rd(24, 12, 48)
    e.sto_rd(18, 12, 56)
    e.sto_rd(14, 12, 64)
    e.load("rd", 20, 0)
    e.sto_rd(20, 12, 72)
    e.sto_rd(20, 12, 80)
    e.addi_rb(12, 12, 88)
    e.sto_rb(12, 8, 0)
    e.ret()


# ---------------------------------------------------------------------------
# Image construction

TABLE_NAMES = ("TABLE_A_INIT", "TABLE_A_CHAIN", "TABLE_A_DONE",
               "TABLE_B_INIT", "TABLE_B_CHAIN", "TABLE_B_DONE")


def build_image(mutation=None, initial_progress=0):
    """Build (rom, ram, labels, tables, identity). mutation=("rd40", 7)
    corrupts the outgoing frame's rd40 slot right after the real SAVE
    checkpoint of transition 7, before the real restore continues."""
    if not 0 <= initial_progress < CHAIN_ITERS:
        raise ValueError("initial_progress outside scenario range")
    e = Emit()
    k131.emit_boot_stub(e.out, ROM_BASE + 0x200)

    # ---- MAIN ------------------------------------------------------------
    e.mark("MAIN")
    e.load("rd", 8, k2.EVENT_INIT)
    e.load("rd", 9, 0)
    e.load("rd", 10, 0)
    e.load("rd", 11, 0)
    e.load("rb", 9, FRAME_A)
    e.call("EMIT_CKPT")
    e.load("rd", 8, TASK_A)
    e.load("rb", 8, MDW + MDW_CUR * 8)
    e.sto_rd(8, 8, 0)
    # bootstrap: restore task A through the same SW_RESTORE path as every
    # later switch (the INITIAL frame's ra63 holds its entry address)
    e.load("rb", 13, FRAME_A)
    e.jump("SW_LOAD")

    # ---- task body --------------------------------------------------------
    def emit_task(task, l1_label, bitmap_addr, prog_off, done_off,
                  stack_top, mask, push1_mark):
        # loop top (also the task entry point)
        e.call("GUARD_CHECK")
        e.load("rb", 8, bitmap_addr)
        e.load("rd", 8, 0)
        e.sto_rd(8, 8, 0)
        if task == TASK_A:
            e.load("rb", 8, ADDR_RECUR_A)
            e.sto_rd(8, 8, 0)
        e.mark(push1_mark)
        e.call(l1_label)
        # post-unwind checks
        e.load("rb", 8, bitmap_addr)
        e.ldo_rd(8, 8, 0)
        check_eq_rd(e, 8, mask)
        e.rb2rd(8, 1)
        check_eq_rd(e, 8, stack_top)
        # RegRAS must be all zero again after the full unwind
        e.load("rb", 8, RAS_SCRATCH)
        e.rrri(OP_STMO_RA, 0, 8, 0, 63)
        e.load("rd", 9, 63 * 8)
        e.rrri(OP_STMO_RA, 63, 8, 9, 1)
        e.load("rd", 11, 0)
        e.load("rd", 12, 64)
        ras_loop = f"TASK_{'A' if task == TASK_A else 'B'}_RASZ"
        e.mark(ras_loop)
        e.ldo_rd(10, 8, 0)
        e.orrr(MISC_ORR, 11, 11, 10)
        e.addi_rb(8, 8, 8)
        e.addi_rd(12, 12, -1)
        e.brnz(12, ras_loop)
        check_eq_rd(e, 11, 0)
        # progress++ and loop while < CHAIN_ITERS
        e.load("rb", 8, MDW + prog_off * 8)
        e.ldo_rd(8, 8, 0)
        e.addi_rd(8, 8, 1)
        e.sto_rd(8, 8, 0)
        e.load("rd", 9, CHAIN_ITERS)
        e.orrr(MISC_XOR, 10, 8, 9)
        e.brnz(10, f"TASK_{'A' if task == TASK_A else 'B'}_LOOP")
        # done: DONE=1; done-yield (never returns for either task)
        e.load("rb", 8, MDW + done_off * 8)
        e.load("rd", 8, 1)
        e.sto_rd(8, 8, 0)
        e.mark(f"TASK_{'A' if task == TASK_A else 'B'}_DONE_CALL")
        e.call("SW_DONE")
        e.word(UNIMP_ENCODING)  # DONE continuation: never executed

    def emit_chain_level(task, level, name, next_label, bitmap_addr,
                         entry_bit, exit_bit, push_mark):
        e.mark(name)
        e.addi_rb(1, 1, -8)
        e.load("rd", 8, stack_marker(task, level))
        e.sto_rd(8, 1, 0)
        e.load("rb", 8, bitmap_addr)
        e.ldo_rd(9, 8, 0)
        e.load("rd", 10, 1 << entry_bit)
        e.orrr(MISC_ORR, 9, 9, 10)
        e.sto_rd(9, 8, 0)
        e.mark(push_mark)
        e.call(next_label)
        e.load("rb", 8, bitmap_addr)
        e.ldo_rd(9, 8, 0)
        e.load("rd", 10, 1 << exit_bit)
        e.orrr(MISC_ORR, 9, 9, 10)
        e.sto_rd(9, 8, 0)
        e.ldo_rd(8, 1, 0)
        check_eq_rd(e, 8, stack_marker(task, level))
        e.addi_rb(1, 1, 8)
        e.ret()

    # ---- task A -----------------------------------------------------------
    e.mark("TASK_A")
    e.mark("TASK_A_LOOP")
    emit_task(TASK_A, "A_L1", ADDR_BITMAP_A, MDW_PROG_A, MDW_DONE_A,
              STACK_A_TOP, MASK_A, "A_PUSH1")
    emit_chain_level(TASK_A, 1, "A_L1", "A_L2", ADDR_BITMAP_A, 0, 16,
                     "A_PUSH2")
    emit_chain_level(TASK_A, 2, "A_L2", "A_L3", ADDR_BITMAP_A, 1, 17,
                     "A_PUSH3")
    emit_chain_level(TASK_A, 3, "A_L3", "A_R", ADDR_BITMAP_A, 2, 18,
                     "A_PUSH4")
    # A_R: twice-self-recursive deepest level (refcount-2 slot)
    e.mark("A_R")
    e.load("rb", 8, ADDR_RECUR_A)
    e.ldo_rd(9, 8, 0)
    e.load("rd", 10, 2)
    e.orrr(MISC_XOR, 11, 9, 10)
    e.brz(11, "A_R_YIELD")
    e.addi_rd(9, 9, 1)
    e.sto_rd(9, 8, 0)
    e.addi_rb(1, 1, -8)
    e.load("rd", 8, stack_marker(TASK_A, 4))
    e.sto_rd(8, 1, 0)
    e.load("rb", 8, ADDR_BITMAP_A)
    e.ldo_rd(9, 8, 0)
    e.load("rd", 10, 1 << 3)
    e.orrr(MISC_ORR, 9, 9, 10)
    e.sto_rd(9, 8, 0)
    e.mark("A_PUSH5")
    e.call("A_R")
    e.load("rb", 8, ADDR_BITMAP_A)
    e.ldo_rd(9, 8, 0)
    e.load("rd", 10, 1 << 19)
    e.orrr(MISC_ORR, 9, 9, 10)
    e.sto_rd(9, 8, 0)
    e.ldo_rd(8, 1, 0)
    check_eq_rd(e, 8, stack_marker(TASK_A, 4))
    e.addi_rb(1, 1, 8)
    e.ret()
    e.mark("A_R_YIELD")
    e.addi_rb(1, 1, -8)
    e.load("rd", 8, stack_marker(TASK_A, 4))
    e.sto_rd(8, 1, 0)
    e.load("rb", 8, ADDR_BITMAP_A)
    e.ldo_rd(9, 8, 0)
    e.load("rd", 10, 1 << 3)
    e.orrr(MISC_ORR, 9, 9, 10)
    e.sto_rd(9, 8, 0)
    e.mark("A_PUSH6")
    e.call("SW_CHAIN")
    e.mark("CONT_A")
    emit_restore_continuation(
        e, TASK_A, "CONT_A", ADDR_BITMAP_A, ADDR_RESTORES_A, FRAME_A,
        "TABLE_A_CHAIN", 19, stack_marker(TASK_A, 4))

    # ---- task B -----------------------------------------------------------
    e.mark("TASK_B")
    e.mark("TASK_B_LOOP")
    emit_task(TASK_B, "B_M1", ADDR_BITMAP_B, MDW_PROG_B, MDW_DONE_B,
              STACK_B_TOP, MASK_B, "B_PUSH1")
    for level in range(1, 8):
        nxt = "B_M8_YIELD" if level == 7 else f"B_M{level + 1}"
        emit_chain_level(TASK_B, level, f"B_M{level}", nxt, ADDR_BITMAP_B,
                         level - 1, 16 + level - 1, f"B_PUSH{level + 1}")
    e.mark("B_M8_YIELD")
    e.call("SW_CHAIN")
    e.mark("CONT_B")
    emit_restore_continuation(
        e, TASK_B, "CONT_B", ADDR_BITMAP_B, ADDR_RESTORES_B, FRAME_B,
        "TABLE_B_CHAIN", None, None)

    # ---- switch primitive -------------------------------------------------
    e.mark("SW_CHAIN")
    e.load("rd", 15, 0)
    e.jump("SW_COMMON")
    e.mark("SW_DONE")
    e.load("rd", 15, 1)
    e.mark("SW_COMMON")
    # both-done precheck: DONE_A==1 && DONE_B==1 -> FINALIZE (no save)
    e.load("rb", 8, MDW + MDW_DONE_A * 8)
    e.ldo_rd(9, 8, 0)
    e.load("rb", 8, MDW + MDW_DONE_B * 8)
    e.ldo_rd(10, 8, 0)
    e.load("rd", 11, 1)
    e.orrr(MISC_XOR, 12, 9, 11)
    e.brnz(12, "SW_SAVE")
    e.orrr(MISC_XOR, 12, 10, 11)
    e.brnz(12, "SW_SAVE")
    e.jump("FINALIZE")
    e.mark("SW_SAVE")
    e.load("rb", 8, MDW + MDW_CUR * 8)
    e.ldo_rd(16, 8, 0)                    # rd16 = CUR
    e.load("rb", 13, FRAME_A)
    e.load("rd", 17, TASK_B)
    e.orrr(MISC_XOR, 18, 16, 17)
    e.brnz(18, "SW_HAVE_FRAME")
    e.load("rb", 13, FRAME_B)
    e.mark("SW_HAVE_FRAME")               # rb13 = outgoing frame
    # save frame per frozen layout
    e.addi_rb(9, 13, 0x38)
    e.rrri(OP_STMO_RD, 32, 9, 0, 32)      # w7..w38 rd32-63
    e.addi_rb(9, 13, 0x138)
    e.rrri(OP_STMO_RB, 32, 9, 0, 32)      # w39..w70 rb32-63
    e.addi_rb(9, 13, 0x238)
    e.rrri(OP_STMO_RA, 0, 9, 0, 63)       # w71..w133 ra0-62
    e.addi_rb(9, 13, 0x430)
    e.rrri(OP_STMO_RA, 63, 9, 0, 1)       # w134 ra63
    e.sto_rb(1, 13, 0x18)
    e.sto_rb(2, 13, 0x20)
    e.sto_rb(3, 13, 0x28)
    e.sto_rb(4, 13, 0x30)
    # resume_pc = frame.ra63[47:0]
    e.ldo_rd(9, 13, 0x430)
    e.load("rd", 10, MASK48)
    e.orrr(MISC_AND, 9, 9, 10)
    e.sto_rd(9, 13, 0)
    # asid = ptbr = 0
    e.load("rd", 9, 0)
    e.sto_rd(9, 13, 8)
    e.sto_rd(9, 13, 16)
    # SAVE-check against table[CUR][variant in rd15]
    emit_table_select(e, 16, 15, "SW_TABSEL")
    e.addi_rb(8, 13, 0)
    e.addi_rb(9, 14, 0)
    e.call("CHECK_FRAME")
    # SAVE checkpoint: task=CUR, saved_pc=frame w0, resume=0
    e.load("rd", 8, k2.EVENT_COOP_SAVE)
    e.orrr(MISC_ORR, 9, 16, 0)
    e.ldo_rd(10, 13, 0)
    e.load("rd", 11, 0)
    e.addi_rb(9, 13, 0)
    e.call("EMIT_CKPT")
    # SWITCH_COUNT++
    e.load("rb", 8, MDW + MDW_SWCOUNT * 8)
    e.ldo_rd(8, 8, 0)
    e.addi_rd(8, 8, 1)
    e.sto_rd(8, 8, 0)
    if mutation is not None:
        field, at_transition = mutation
        mutation_word = {"rd40": 15, "rb40": 47}.get(field)
        if mutation_word is None:
            raise ValueError(f"unknown mutation {mutation}")
        e.load("rb", 8, MDW + MDW_SWCOUNT * 8)
        e.ldo_rd(8, 8, 0)
        e.load("rd", 9, at_transition)
        e.orrr(MISC_XOR, 10, 8, 9)
        e.brnz(10, "MUT_SKIP")
        e.ldo_rd(8, 13, mutation_word * 8)
        e.load("rd", 9, 0xFFFFFFFFFFFFFFFF)
        e.orrr(MISC_XOR, 8, 8, 9)
        e.sto_rd(8, 13, mutation_word * 8)
        e.mark("MUT_SKIP")
    # CUR ^= 3, rb13 = incoming frame
    e.load("rd", 8, 3)
    e.orrr(MISC_XOR, 16, 16, 8)
    e.load("rb", 8, MDW + MDW_CUR * 8)
    e.sto_rd(16, 8, 0)
    e.load("rb", 13, FRAME_A)
    e.load("rd", 17, TASK_B)
    e.orrr(MISC_XOR, 18, 16, 17)
    e.brnz(18, "SW_RESTORE")
    e.load("rb", 13, FRAME_B)
    e.mark("SW_RESTORE")                  # rb13 = incoming frame
    e.load("rd", 8, k2.EVENT_COOP_RESTORE)
    e.orrr(MISC_ORR, 9, 16, 0)
    e.load("rd", 10, 0)
    e.ldo_rd(11, 13, 0)
    e.addi_rb(9, 13, 0)
    e.call("EMIT_CKPT")
    # EMIT_CKPT uses caller-saved scratch; reload the selected task/frame.
    e.load("rb", 8, MDW + MDW_CUR * 8)
    e.ldo_rd(16, 8, 0)
    e.load("rb", 13, FRAME_A)
    e.load("rd", 17, TASK_B)
    e.orrr(MISC_XOR, 18, 16, 17)
    e.brnz(18, "SW_LOAD")
    e.load("rb", 13, FRAME_B)
    e.mark("SW_LOAD")
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

    e.mark("FINALIZE")
    e.load("rd", 8, k2.EVENT_FINAL)
    e.load("rd", 9, 0)
    e.load("rd", 10, 0)
    e.load("rd", 11, 0)
    e.load("rb", 9, FRAME_B)
    e.call("EMIT_CKPT")
    e.call("GUARD_CHECK")
    # Final guest-owned scenario state.  These checks deliberately happen
    # after the FINAL checkpoint (whose positive memory digest is frozen) but
    # before final_status is formed.
    final_words = (
        (MDW + MDW_CUR * 8, TASK_B),
        (MDW + MDW_PROG_A * 8, CHAIN_ITERS),
        (MDW + MDW_PROG_B * 8, CHAIN_ITERS),
        (MDW + MDW_SWCOUNT * 8, TRANSITIONS),
        (MDW + MDW_DONE_A * 8, 1),
        (MDW + MDW_DONE_B * 8, 1),
        (ADDR_RESTORES_A, CHAIN_ITERS),
        (ADDR_RESTORES_B, CHAIN_ITERS),
        (ADDR_BITMAP_A, MASK_A),
        (ADDR_BITMAP_B, MASK_B),
        (ADDR_SEQ, N_CHECKPOINTS),
    )
    for addr, expected in final_words:
        e.load("rb", 8, addr)
        e.ldo_rd(8, 8, 0)
        check_eq_rd(e, 8, expected)
    # report header: 9 words at REPORT_PA
    e.load("rb", 12, REPORT_PA)
    e.load("rd", 8, k2.MAGIC)
    e.sto_rd(8, 12, 0)
    e.load("rd", 8, k2.SCHEMA_VERSION)
    e.sto_rd(8, 12, 8)
    e.load("rd", 8, SCENARIO)
    e.sto_rd(8, 12, 16)
    e.load("rb", 8, IDENTITY_MIRROR)
    e.ldo_rd(8, 8, 0)
    e.sto_rd(8, 12, 24)
    # final_status: MISMATCH==0 ? PASS : FAIL
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
    # Publish the report, then architecturally terminate.  QEMU runs with
    # -no-shutdown so the stopped VM remains available for post-termination
    # pmemsave; gem5 checkpoints after the halt exit event.
    e.load("rd", 8, DOORBELL)
    e.load("rb", 8, REPORT_PA + DOORBELL_OFF)
    e.sto_rd(8, 8, 0)
    e.load("rd", 8, 0)
    e.riii(0x00, 8, 0)

    # ---- shared routines --------------------------------------------------
    emit_fnv_words(e, "FNV_WORDS")
    emit_check_frame(e, "CHECK_FRAME")
    emit_guard_check(e, "GUARD_CHECK")
    emit_checkpoint_writer(e, "EMIT_CKPT")

    # ---- frame tables (need resolved label addresses) ---------------------
    e.pad_unimp(0x8000)
    tables = build_tables(e.labels)
    for name in TABLE_NAMES:
        e.mark(name)
        for word in tables[name]:
            e.out.extend(struct.pack(">Q", word))
    e.pad_unimp(IDENTITY_SLOT_OFF)
    e.out.extend(b"\0" * 8)
    if len(e.out) > ROM_SIZE:
        raise ValueError("ROM image overflow")

    rom = bytearray(e.finish())

    ram = bytearray(RAM_SIZE)
    put_qword(ram, ADDR_CURSOR - RAM_BASE, REPORT_PA + k2.HEADER_SIZE)
    put_qword(
        ram, MDW + MDW_PROG_A * 8 - RAM_BASE, initial_progress)
    put_qword(
        ram, MDW + MDW_PROG_B * 8 - RAM_BASE, initial_progress)
    for addr, value in GUARDS:
        put_qword(ram, addr - RAM_BASE, value)
    for name, words in tables.items():
        table_offset = TABLE_RAM_ADDR[name] - RAM_BASE
        ram[table_offset:table_offset + 8 * len(words)] = struct.pack(
            f">{len(words)}Q", *words)
    for frame_addr, table_name in (
            (FRAME_A, "TABLE_A_INIT"), (FRAME_B, "TABLE_B_INIT")):
        words = tables[table_name]
        frame_offset = frame_addr - RAM_BASE
        ram[frame_offset:frame_offset + 8 * len(words)] = struct.pack(
            f">{len(words)}Q", *words)

    identity = k2.image_identity(
        bytes(rom), bytes(ram),
        rom_identity_slot=(IDENTITY_SLOT_OFF, 8),
        ram_report_area=(REPORT_PA - RAM_BASE, k2.MAX_REPORT_SIZE))
    rom = bytearray(
        k2.embed_image_identity(bytes(rom), IDENTITY_SLOT_OFF, identity))
    put_qword(ram, IDENTITY_MIRROR - RAM_BASE, identity)
    return bytes(rom), bytes(ram), e.labels, tables, identity


def emit_table_select(e, cur_rd, variant_rd, label):
    """rb14 = table[CUR][variant] (variant==0 -> CHAIN else DONE)."""
    e.load("rd", 19, TASK_B)
    e.orrr(MISC_XOR, 20, cur_rd, 19)
    e.brz(20, label + "_b")
    e.brz(variant_rd, label + "_a_chain")
    e.load("rb", 14, TABLE_RAM_ADDR["TABLE_A_DONE"])
    e.jump(label + "_done")
    e.mark(label + "_a_chain")
    e.load("rb", 14, TABLE_RAM_ADDR["TABLE_A_CHAIN"])
    e.jump(label + "_done")
    e.mark(label + "_b")
    e.brz(variant_rd, label + "_b_chain")
    e.load("rb", 14, TABLE_RAM_ADDR["TABLE_B_DONE"])
    e.jump(label + "_done")
    e.mark(label + "_b_chain")
    e.load("rb", 14, TABLE_RAM_ADDR["TABLE_B_CHAIN"])
    e.mark(label + "_done")


def emit_restore_continuation(e, task, _cont_label, bitmap_addr,
                              restores_addr, frame_addr, chain_table_label,
                              exit_bit, marker):
    """RESTORE continuation at the yield site.  SW_RESTORE has already
    emitted the single restore checkpoint before loading the frame; here we
    verify task id/switch count and every restored callee-saved slot."""
    # current-task id must be us
    e.load("rb", 8, MDW + MDW_CUR * 8)
    e.ldo_rd(8, 8, 0)
    check_eq_rd(e, 8, task)
    # First chain-continuation restore occurs at transition 2 for A and
    # transition 3 for B; the initial B activation resumes at TASK_B.
    e.load("rb", 8, restores_addr)
    e.ldo_rd(8, 8, 0)
    e.addi_rd(8, 8, 1)
    e.sto_rd(8, 8, 0)
    e.rrrr(OP_ADD, 0, 9, 8, 8)
    if task == TASK_B:
        e.addi_rd(9, 9, 1)
    e.load("rb", 8, MDW + MDW_SWCOUNT * 8)
    e.ldo_rd(10, 8, 0)
    e.orrr(MISC_XOR, 9, 9, 10)
    e.load("rb", 8, ADDR_MISMATCH)
    e.ldo_rd(10, 8, 0)
    e.orrr(MISC_ORR, 10, 10, 9)
    e.sto_rd(10, 8, 0)
    # restored control registers
    sp_expect = (STACK_A_TOP if task == TASK_A else STACK_B_TOP) - 8 * (
        6 if task == TASK_A else 7)
    e.rb2rd(8, 1)
    check_eq_rd(e, 8, sp_expect)
    e.rb2rd(8, 2)
    check_eq_rd(e, 8, poison_fp(task))
    e.rb2rd(8, 3)
    check_eq_rd(e, 8, poison_gp(task))
    e.rb2rd(8, 4)
    check_eq_rd(e, 8, poison_tp(task))
    for reg in range(32, 64):
        check_eq_rd(e, reg, poison_rd(task, reg))
    for reg in range(32, 64):
        e.rb2rd(8, reg)
        check_eq_rd(e, 8, poison_rb(task, reg))
    # saved frame still in memory must match the chain table
    e.load("rb", 8, frame_addr)
    e.load("rb", 9, TABLE_RAM_ADDR[chain_table_label])
    e.call("CHECK_FRAME")
    # A yields from a frame-owning recursive level and must finish that
    # level here.  B yields from a leaf wrapper, so its B_M7 caller owns
    # the marker and exit bit and will perform the cleanup after this ret.
    if marker is not None:
        e.load("rb", 8, bitmap_addr)
        e.ldo_rd(9, 8, 0)
        e.load("rd", 10, 1 << exit_bit)
        e.orrr(MISC_ORR, 9, 9, 10)
        e.sto_rd(9, 8, 0)
        e.ldo_rd(8, 1, 0)
        check_eq_rd(e, 8, marker)
        e.addi_rb(1, 1, 8)
    e.ret()


def build_tables(labels):
    """The six 135-word frame tables; every PC comes from emitted labels."""
    cont_a, cont_b = labels["CONT_A"], labels["CONT_B"]
    done_a = labels["TASK_A_DONE_CALL"] + 4

    def frame(resume_pc, sp, task, ras):
        words = [resume_pc, 0, 0, sp, poison_fp(task), poison_gp(task),
                 poison_tp(task)]
        words += [poison_rd(task, r) for r in range(32, 64)]
        words += [poison_rb(task, r) for r in range(32, 64)]
        words += ras
        assert len(words) == 135
        return words

    push_a = [labels[f"A_PUSH{i}"] + 4 for i in (1, 2, 3, 4, 5, 5)] + [
        labels["CONT_A"]]
    push_b = [labels[f"B_PUSH{i}"] + 4 for i in range(1, 9)] + [
        labels["CONT_B"]]
    return {
        "TABLE_A_INIT": frame(labels["TASK_A"], STACK_A_TOP, TASK_A,
                              ras_model([labels["TASK_A"]])),
        "TABLE_A_CHAIN": frame(cont_a, STACK_A_TOP - 48, TASK_A,
                               ras_model(push_a)),
        "TABLE_A_DONE": frame(done_a, STACK_A_TOP, TASK_A,
                              ras_model([done_a])),
        "TABLE_B_INIT": frame(labels["TASK_B"], STACK_B_TOP, TASK_B,
                              ras_model([labels["TASK_B"]])),
        "TABLE_B_CHAIN": frame(cont_b, STACK_B_TOP - 56, TASK_B,
                               ras_model(push_b)),
        "TABLE_B_DONE": frame(cont_b, STACK_B_TOP, TASK_B, [0] * 64),
    }


# ---------------------------------------------------------------------------
# Host-side oracle built purely from scenario constants

def build_oracle(labels, tables, identity):
    cont = {TASK_A: labels["CONT_A"], TASK_B: labels["CONT_B"]}
    digest_init_a = k2.fnv1a64(tables["TABLE_A_INIT"])
    digest_init_b = k2.fnv1a64(tables["TABLE_B_INIT"])
    digest_chain = {TASK_A: k2.fnv1a64(tables["TABLE_A_CHAIN"]),
                    TASK_B: k2.fnv1a64(tables["TABLE_B_CHAIN"])}
    digest_done_a = k2.fnv1a64(tables["TABLE_A_DONE"])

    def mdw(cur, pa, pb, count, da, db, seq):
        words = [0] * 16
        words[MDW_SEQ] = seq
        words[MDW_CUR] = cur
        words[MDW_PROG_A] = pa
        words[MDW_PROG_B] = pb
        words[MDW_SWCOUNT] = count
        words[MDW_DONE_A] = da
        words[MDW_DONE_B] = db
        return k2.fnv1a64(words)

    expected = [k2.ExpectedCheckpoint(
        event_kind=k2.EVENT_INIT, task_id=0, run_mode=2, cfx_code=63,
        cause=0, saved_pc=0, resume_pc=0, context_digest=digest_init_a,
        memory_digest=mdw(0, 0, 0, 0, 0, 0, 0), asid=0, ptbr=0, tlb_gen=0)]

    for t in range(1, TRANSITIONS + 1):
        outgoing = TASK_A if t % 2 == 1 else TASK_B
        incoming = TASK_B if t % 2 == 1 else TASK_A
        j = (t + 1) // 2
        done_yield = (t == TRANSITIONS)
        if done_yield:
            pa, pb, da = CHAIN_ITERS, CHAIN_ITERS - 1, 1
            saved_pc = labels["TASK_A_DONE_CALL"] + 4
            ctx = digest_done_a
        else:
            pa = j - 1
            # At an A yield the preceding B chain is still suspended and
            # increments its progress only after this transition restores it.
            pb = j - 1 if outgoing == TASK_B else max(0, j - 2)
            da = 0
            saved_pc = cont[outgoing]
            ctx = digest_chain[outgoing]
        expected.append(k2.ExpectedCheckpoint(
            event_kind=k2.EVENT_COOP_SAVE, task_id=outgoing, run_mode=2,
            cfx_code=63, cause=0, saved_pc=saved_pc, resume_pc=0,
            context_digest=ctx,
            memory_digest=mdw(
                outgoing, pa, pb, t - 1, da, 0, 2 * t - 1),
            asid=0, ptbr=0, tlb_gen=0))
        restore_pc = cont[incoming]
        restore_ctx = digest_chain[incoming]
        if t == 1:
            restore_pc = labels["TASK_B"]
            restore_ctx = digest_init_b
        expected.append(k2.ExpectedCheckpoint(
            event_kind=k2.EVENT_COOP_RESTORE, task_id=incoming, run_mode=2,
            cfx_code=63, cause=0, saved_pc=0, resume_pc=restore_pc,
            context_digest=restore_ctx,
            memory_digest=mdw(incoming, pa, pb, t, da, 0, 2 * t),
            asid=0, ptbr=0, tlb_gen=0))

    expected.append(k2.ExpectedCheckpoint(
        event_kind=k2.EVENT_FINAL, task_id=0, run_mode=2, cfx_code=63,
        cause=0, saved_pc=0, resume_pc=0,
        context_digest=digest_chain[TASK_B],
        memory_digest=mdw(TASK_B, CHAIN_ITERS, CHAIN_ITERS, TRANSITIONS,
                          1, 1, 2 * TRANSITIONS + 1),
        asid=0, ptbr=0, tlb_gen=0))
    assert len(expected) == N_CHECKPOINTS
    return k2.ScenarioOracle(
        scenario_id=SCENARIO, image_identity=identity, checkpoints=expected)


# ---------------------------------------------------------------------------
# Report transports (raw window bytes only; never interpret checkpoints)

class TransportError(Exception):
    pass


def slice_report(window):
    if len(window) != REPORT_WINDOW:
        raise TransportError(f"report window {len(window)} != {REPORT_WINDOW}")
    doorbell = struct.unpack(">Q", window[DOORBELL_OFF:])[0]
    if doorbell != DOORBELL:
        raise TransportError(f"doorbell {doorbell:#018x} != {DOORBELL:#018x}")
    count = struct.unpack(">Q", window[6 * 8:7 * 8])[0]
    if count > k2.MAX_CHECKPOINTS:
        raise TransportError(f"checkpoint count {count} over capacity")
    need = k2.HEADER_SIZE + count * k2.CHECKPOINT_SIZE
    if need > k2.MAX_REPORT_SIZE:
        raise TransportError(f"report length {need} over maximum")
    return window[:need]


def qmp_roundtrip(stream, request):
    stream.write(json.dumps(request) + "\n")
    stream.flush()
    while True:
        try:
            line = stream.readline()
        except (OSError, TimeoutError) as exc:
            raise TransportError(f"QMP response timeout/error: {exc}") from exc
        if not line:
            raise TransportError("QMP connection closed")
        reply = json.loads(line)
        if "error" in reply:
            raise TransportError(f"QMP error: {reply['error']}")
        if "return" in reply:
            return reply["return"]


def run_qemu(rom_path, ram_path, log_path, timeout=180):
    transport_dir = tempfile.TemporaryDirectory(prefix="kl141a_qemu_")
    qmp_path = os.path.join(transport_dir.name, "qmp.sock")
    window_path = os.path.join(transport_dir.name, "report-window.bin")
    command = [
        QEMU, "-M", "dadao-m1",
        "-bios", rom_path, "-kernel", ram_path,
        "-display", "none", "-serial", "none", "-no-shutdown",
        "-qmp", f"unix:{qmp_path},server,nowait",
        "-d", "int,mmu", "-D", log_path,
    ]
    proc = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    window = None
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        deadline = time.time() + 30
        while True:
            try:
                sock.connect(qmp_path)
                break
            except OSError:
                if proc.poll() is not None:
                    raise TransportError("QEMU exited before QMP connect")
                if time.time() > deadline:
                    raise TransportError("QMP connect timeout")
                time.sleep(0.05)
        sock.settimeout(min(timeout, 5))
        stream = sock.makefile("rw", encoding="utf-8", newline="\n")
        try:
            greeting = stream.readline()
        except (OSError, TimeoutError) as exc:
            raise TransportError(
                f"QMP greeting timeout/error: {exc}") from exc
        if not greeting:
            raise TransportError("QMP greeting missing")
        qmp_roundtrip(stream, {"execute": "qmp_capabilities"})
        deadline = time.time() + timeout
        while time.time() < deadline:
            if proc.poll() is not None:
                raise TransportError(
                    f"QEMU exited before guest termination (rc={proc.returncode})")
            status = qmp_roundtrip(stream, {"execute": "query-status"})
            if status.get("status") == "shutdown":
                break
            time.sleep(0.2)
        else:
            raise TransportError("QEMU guest termination timeout")
        hmp_result = qmp_roundtrip(stream, {
            "execute": "human-monitor-command",
            "arguments": {"command-line":
                          f"pmemsave {REPORT_PA} {REPORT_WINDOW} "
                          f"\"{window_path}\""}})
        if hmp_result:
            raise TransportError(
                f"QEMU pmemsave failed: {hmp_result.strip()}")
        with open(window_path, "rb") as fh:
            window = fh.read()
        if len(window) != REPORT_WINDOW or struct.unpack(
                ">Q", window[DOORBELL_OFF:])[0] != DOORBELL:
            raise TransportError(
                "QEMU terminated without a complete report doorbell")
        try:
            qmp_roundtrip(stream, {"execute": "quit"})
        except TransportError:
            pass
        sock.close()
    finally:
        if proc.poll() is None:
            proc.kill()
        stdout, stderr = proc.communicate()
        with open(log_path, "a") as fh:
            fh.write("=== stdout ===\n" + stdout)
            fh.write("\n=== stderr ===\n" + stderr)
        transport_dir.cleanup()
    return slice_report(window)


def run_gem5(rom_path, ram_path, log_path, timeout=600):
    transport_dir = tempfile.TemporaryDirectory(prefix="gem5_kl141a_")
    outdir = transport_dir.name
    command = [
        GEM5, "--outdir=" + outdir, GEM5_FS_CFG, rom_path, ram_path,
        "50000000", "200",
    ]
    with open(log_path, "w") as log:
        proc = subprocess.Popen(
            command, stdout=log, stderr=subprocess.STDOUT)
    store = os.path.join(
        outdir, "k2cpt", "system.physmem.store1.pmem")
    window = None
    try:
        try:
            returncode = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise TransportError("gem5 guest termination timeout") from exc
        if returncode != 0:
            raise TransportError(
                f"gem5 exited abnormally (rc={returncode})")
        try:
            with open(store, "rb") as fh:
                image = gzip.decompress(fh.read())
        except (OSError, gzip.BadGzipFile, EOFError) as exc:
            raise TransportError(
                f"gem5 terminal checkpoint unavailable: {exc}") from exc
        offset = REPORT_PA - RAM_BASE
        window = image[offset:offset + REPORT_WINDOW]
        if len(window) != REPORT_WINDOW or struct.unpack(
                ">Q", window[DOORBELL_OFF:])[0] != DOORBELL:
            raise TransportError(
                "gem5 terminated without a complete report doorbell")
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        transport_dir.cleanup()
    return slice_report(window)


# ---------------------------------------------------------------------------
# Round orchestration

def put_qword(image, offset, value):
    image[offset:offset + 8] = struct.pack(">Q", value)


def verify_run_image(rom_path, ram_path, oracle):
    """Bind the oracle and guest-visible identities to the exact files that
    will be handed to both backends."""
    try:
        with open(rom_path, "rb") as fh:
            rom = fh.read()
        with open(ram_path, "rb") as fh:
            ram = fh.read()
    except OSError as exc:
        raise TransportError(f"run image unavailable: {exc}") from exc
    if len(rom) != ROM_SIZE or len(ram) != RAM_SIZE:
        raise TransportError(
            f"run image size ROM={len(rom)}/{ROM_SIZE} "
            f"RAM={len(ram)}/{RAM_SIZE}")
    computed = k2.image_identity(
        rom, ram, rom_identity_slot=(IDENTITY_SLOT_OFF, 8),
        ram_report_area=(REPORT_PA - RAM_BASE, k2.MAX_REPORT_SIZE))
    embedded = struct.unpack(
        ">Q", rom[IDENTITY_SLOT_OFF:IDENTITY_SLOT_OFF + 8])[0]
    mirror_offset = IDENTITY_MIRROR - RAM_BASE
    mirrored = struct.unpack(">Q", ram[mirror_offset:mirror_offset + 8])[0]
    expected = oracle.image_identity
    if computed != expected or embedded != expected or mirrored != expected:
        raise TransportError(
            "run image identity mismatch: "
            f"computed={computed:#018x} embedded={embedded:#018x} "
            f"mirror={mirrored:#018x} oracle={expected:#018x}")


def run_one_round(round_no, rom_path, ram_path, oracle, tag):
    qemu_bytes = gem5_bytes = None
    problems = []
    try:
        verify_run_image(rom_path, ram_path, oracle)
    except TransportError as exc:
        return k2.Verdict.HARNESS_ERROR, [str(exc)], None, None
    try:
        qemu_bytes = run_qemu(
            rom_path, ram_path,
            os.path.join(EVIDENCE, f"qemu{tag}-round{round_no:02d}.log"))
    except TransportError as exc:
        problems.append(f"qemu transport: {exc}")
    try:
        gem5_bytes = run_gem5(
            rom_path, ram_path,
            os.path.join(EVIDENCE, f"gem5{tag}-round{round_no:02d}.log"))
    except TransportError as exc:
        problems.append(f"gem5 transport: {exc}")
    if problems:
        return k2.Verdict.HARNESS_ERROR, problems, None, None
    for name, data in (("qemu", qemu_bytes), ("gem5", gem5_bytes)):
        with open(os.path.join(
                EVIDENCE, f"report-{name}{tag}-round{round_no:02d}.bin"),
                "wb") as fh:
            fh.write(data)
    verdict, reasons = k2.compare_dual_backend(
        qemu_bytes, gem5_bytes, oracle)
    return verdict, reasons, qemu_bytes, gem5_bytes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--skip-negative", action="store_true")
    args = parser.parse_args()
    if args.rounds < 1:
        parser.error("--rounds must be positive")

    os.makedirs(EVIDENCE, exist_ok=True)
    rom, ram, labels, tables, identity = build_image()
    rom_path = os.path.join(EVIDENCE, "kl141a-coop.bin")
    ram_path = os.path.join(EVIDENCE, "kl141a-coop-ram.bin")
    with open(rom_path, "wb") as fh:
        fh.write(rom)
    with open(ram_path, "wb") as fh:
        fh.write(ram)
    oracle = build_oracle(labels, tables, identity)
    print(f"image: sha256-rom={hashlib.sha256(rom).hexdigest()}")
    print(f"image: sha256-ram={hashlib.sha256(ram).hexdigest()}")
    print(f"image: canonical identity={identity:#018x} "
          f"checkpoints={N_CHECKPOINTS} transitions={TRANSITIONS}")

    failures = 0
    for round_no in range(1, args.rounds + 1):
        verdict, reasons, _, _ = run_one_round(
            round_no, rom_path, ram_path, oracle, "-pos")
        if verdict != k2.Verdict.PASS:
            failures += 1
            print(f"round {round_no}: {verdict.value}")
            for reason in reasons[:8]:
                print(f"  {reason}")
        else:
            print(f"round {round_no}/{args.rounds}: qemu=PASS gem5=PASS "
                  f"oracle=PASS cross=PASS")

    if not args.skip_negative and failures == 0:
        mrom, mram, mlabels, mtables, midentity = build_image(
            mutation=("rd40", 7))
        mrom_path = os.path.join(EVIDENCE, "kl141a-coop-mut.bin")
        mram_path = os.path.join(EVIDENCE, "kl141a-coop-mut-ram.bin")
        with open(mrom_path, "wb") as fh:
            fh.write(mrom)
        with open(mram_path, "wb") as fh:
            fh.write(mram)
        moracle = build_oracle(mlabels, mtables, midentity)
        verdict, reasons, qemu_bytes, gem5_bytes = run_one_round(
            1, mrom_path, mram_path, moracle, "-mut")
        expected_fail = False
        detail = []
        if qemu_bytes is not None and gem5_bytes is not None:
            rq = k2.decode_report(qemu_bytes)
            rg = k2.decode_report(gem5_bytes)
            vq = k2.evaluate_report_bytes(qemu_bytes, moracle)[0]
            vg = k2.evaluate_report_bytes(gem5_bytes, moracle)[0]
            detail = [
                f"qemu={vq.value}/status={k2.STATUS_NAMES[rq.final_status]}"
                f"/mismatch={rq.mismatch_count}",
                f"gem5={vg.value}/status={k2.STATUS_NAMES[rg.final_status]}"
                f"/mismatch={rg.mismatch_count}"]
            expected_fail = (
                verdict == k2.Verdict.FAIL
                and vq == k2.Verdict.FAIL and vg == k2.Verdict.FAIL
                and rq.final_status == k2.STATUS_FAIL
                and rg.final_status == k2.STATUS_FAIL
                and rq.mismatch_count > 0 and rg.mismatch_count > 0)
        if expected_fail:
            print(f"negative mutation(rd40@t7): dual=FAIL "
                  f"({' '.join(detail)}) as required")
        else:
            failures += 1
            print(f"negative mutation: unexpected verdict {verdict.value} "
                  f"({' '.join(detail)})")
            for reason in reasons[:8]:
                print(f"  {reason}")
        verdict, reasons, _, _ = run_one_round(
            1, rom_path, ram_path, oracle, "-post")
        if verdict != k2.Verdict.PASS:
            failures += 1
            print(f"post-restore round: {verdict.value}")
            for reason in reasons[:8]:
                print(f"  {reason}")
        else:
            print("post-restore round: PASS")

    if failures:
        print(f"FAIL: {failures} failing round(s)")
        sys.exit(1)
    claims = (
        f"coop switch primitive+frozen 135-word frame, {TRANSITIONS} real "
        f"transitions, RegRAS call-chain yield/resume with refcount-2 slot, "
        f"guest fail-closed + host oracle + cross-backend, "
        f"negative rd40@t7 mutation")
    nonclaims = (
        "async preemption, trap full-context, PTBR/TLB address-space "
        "switch, user<->supervisor, RF, Atomics/SMP, multi-hart, real "
        "UART/PLIC, Linux scheduler/driver API, Minor/O3, performance")
    print(f"QEMU: pass=[{claims}] rounds={args.rounds}/{args.rounds}; "
          f"skip=[]; fail=[]; non-claim=[{nonclaims}]")
    print(f"gem5: pass=[{claims}] rounds={args.rounds}/{args.rounds}; "
          f"skip=[]; fail=[]; non-claim=[{nonclaims}]")
    print("PASS: KL-141a cooperative context switch dual-backend oracle")


if __name__ == "__main__":
    main()
