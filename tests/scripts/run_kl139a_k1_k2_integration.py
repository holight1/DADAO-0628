#!/usr/bin/env python3
"""KL-139a single-image K1 MMU/interrupt integration probe.

One guest image, one RAM image, and one uninterrupted architectural state are
used on both QEMU and gem5.  The guest itself accumulates every mismatch and
halts with PASS only after it has combined:

* enabled PTW/TLB translation with ROM vectors resident in untranslated set0;
* normal-page and superpage translation;
* a walk-origin cfx_ptw fault repaired by a self-handler and retried;
* TLB miss/fill/hit, the KL-129b low16 range-invalidate case, and a real
  cfx_tlb -> cfx_ptw -> cfx_tlb E1 return;
* timer expiry while masked followed by boundary-precise delivery;
* K1_EXT0 assert/deassert/latch/delivery/ack;
* cfx18-before-cfx62 and UART0-before-UART5 priority.

The runner may reuse existing encoding and backend-launch helpers, but it does
not invoke any pre-existing probe.  All checks above live in this one image.
"""

import argparse
import os
import struct
import subprocess
import sys
import tempfile


HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import run_kl127a_ptw_fault_ad_probes as k127  # noqa: E402
import run_kl129a_tlb_probes as k129  # noqa: E402
import run_kl131a_async_dispatch_probes as k131  # noqa: E402
import run_kl133a_cfx_timer_probes as k133  # noqa: E402
import run_kl137a_synthetic_external_interrupt as k137  # noqa: E402
from build_test_binary import load_reg, write_rrii, UNIMP_ENCODING  # noqa:E402


ROM_BASE = k131.ROM_BASE
RAM_BASE = k129.RAM_BASE
SUPV_ENTRY_OFFSET = k131.SUPV_ENTRY_OFFSET
EVIDENCE = os.path.join(REPO, ".work", "evidence", "kl139a-integration")

QEMU = k131.QEMU
GEM5 = k131.GEM5
GEM5_FS_CFG = k131.GEM5_FS_CFG

PASS = 139
FAIL = 0xA3
MASK_ALL = k131.MASK_ALL
MODE_SUPV = k131.MODE_SUPV

CFX_PTW = k131.CFX_PTW
CFX_TLB = k131.CFX_TLB
CFX_TIMER = k131.CFX_TIMER
CFX_UART = k131.CFX_UART
CFX_POWER = k131.CFX_POWER

CG_FRAME = k131.CG_FRAME
RC_FRAME_CAUSE_ID = k131.RC_FRAME_CAUSE_ID
RC_FRAME_CAUSE_IP = k131.RC_FRAME_CAUSE_IP
RC_FRAME_CAUSE_INFO = k131.RC_FRAME_CAUSE_INFO
RC_FRAME_PREV_CFX_CODE = 5
CG_COMMON = k131.CG_COMMON
RC_PENDING = k131.RC_PENDING
RC_EXCP_ASYNC_NUM = k131.RC_EXCP_ASYNC_NUM
RC_EXCP_CAUSE_MASK = k131.RC_EXCP_CAUSE_MASK

SET = 6
L1_BASE = 0x80010000
L2_BASE = 0x80020000
PTW_ENABLE_RC = k129.PTW_ENABLE_RC
PTW_PTBR_CG = k129.PTW_PTBR_CG
PTW_PTHI_CG = k129.PTW_PTHI_CG
PTW_PAHI_CG = k129.PTW_PAHI_CG
PTW_PERM_CG = k129.PTW_PERM_CG
TLB_REG_CG = k129.TLB_REG_CG
TLB_ENABLE_RC = k129.TLB_ENABLE_RC
TLB_CONTROL_CG = k129.TLB_CONTROL_CG
TLB_CONTROL_RC = k129.TLB_CONTROL_RC
TLB_ADDR_START_RC = k129.TLB_ADDR_START_RC
TLB_ADDR_SIZE_RC = k129.TLB_ADDR_SIZE_RC

PERM_R = k129.PERM_R
PERM_W = k129.PERM_W
CAUSE_PTW_NRPERM = 1 << 14
CAUSE_TLB_NWPERM = 1 << 13
CAUSE_CFXTRAP = k131.CAUSE_CFXTRAP
CAUSE_TIMER = k133.CAUSE_TIMER
CAUSE_UART0 = k137.CAUSE_UART0
CAUSE_UART5 = k131.CAUSE_UART5

CG_TIMER = k133.CG_TIMER
RC_TIMER_PENDING = k133.RC_TIMER_PENDING
RC_TIMER_MASK = k133.RC_TIMER_MASK
RC_TIMER_CTRL = k133.RC_TIMER_CTRL
RC_TIMER_REG0 = k133.RC_TIMER_REG0
TIMER_CTRL_ENABLE = k133.TIMER_CTRL_ENABLE

CG_UART = k137.CG_UART
RC_UART_PENDING = k137.RC_UART_PENDING
RC_UART_EXIST = k137.RC_UART_EXIST

OP_CFX2RD = k131.OP_CFX2RD
OP_CFX2RC = k131.OP_CFX2RC
OP_TRAP = k129.OP_TRAP
OP_ESCAPE = k131.OP_ESCAPE
OP_LDO = k131.OP_LDO
OP_STO = k131.OP_STO

PTW_FAULT_HANDLER = 0x2000
TLB_HANDLER = 0x2400
PTW_NESTED_HANDLER = 0x2800
TIMER_HANDLER = 0x2C00
UART0_HANDLER = 0x3000
UART5_HANDLER = 0x3400
ROM_END = 0x3800

ALLONES_REG = 10
PRESERVE_UART5_REG = 11

NORMAL_13 = (SET << 42) | (9 << 29) | (13 << 16) | (3 << 13) | 0x100
NORMAL_14 = (SET << 42) | (9 << 29) | (14 << 16) | (3 << 13) | 0x100
FAULT_VA = (SET << 42) | (9 << 29) | (15 << 16) | (3 << 13) | 0x100
NESTED_VA = (SET << 42) | (9 << 29) | (16 << 16) | (3 << 13) | 0x100
SUPER_VA = (SET << 42) | (10 << 29) | 0x2000

PA13_OLD, PA13_NEW = 0x80100000, 0x80140000
PA14_OLD, PA14_NEW = 0x80110000, 0x80150000
PA_FAULT = 0x80120000
PA_NESTED = 0x80130000

VAL13_OLD, VAL13_NEW = 0x1390130000000001, 0x1390130000000002
VAL14_OLD, VAL14_NEW = 0x1390140000000001, 0x1390140000000002
VAL_FAULT = 0x1390FA0170000001
VAL_NESTED = 0x1390E10000000001
VAL_NESTED_WRITTEN = 0x1390E10000000002
VAL_SUPER = 0x13905A9E00000001


def pad_to(out, offset):
    if len(out) > offset:
        raise ValueError(f"image section overflow {len(out):#x}>{offset:#x}")
    while len(out) < offset:
        out.extend(struct.pack(">I", UNIMP_ENCODING))


def put_qword(image, pa, value):
    offset = pa - RAM_BASE
    if offset < 0 or offset + 8 > len(image):
        raise ValueError(f"RAM fixture address outside image: {pa:#x}")
    image[offset:offset + 8] = struct.pack(">Q", value)


def normal_pte(pa, perms):
    return k129.normal_pte(pa, [3], perms)


def super_pte(pa, perms):
    return k129.super_pte(pa, [0], perms)


def cfx_write(out, cfxcode, cg, rc, value, scratch=2):
    load_reg(out, "rd", scratch, value)
    k131.write_crrr(out, OP_CFX2RC, cfxcode, cg, rc, scratch)


def read_cfx_check(out, cfxcode, cg, rc, expected):
    k131.read_reg_check(out, cfxcode, cg, rc, expected)


def read_mem(out, va, dst=27):
    load_reg(out, "rb", 3, va)
    write_rrii(out, OP_LDO, dst, 3, 0)


def read_mem_check(out, va, expected):
    read_mem(out, va)
    k131.check_eq(out, 27, expected)


def write_mem(out, va, value):
    load_reg(out, "rd", 2, value)
    load_reg(out, "rb", 3, va)
    write_rrii(out, OP_STO, 2, 3, 0)


def write_pte(out, pte_addr, value):
    write_mem(out, pte_addr, value)


def invalidate_range(out, start, size):
    cfx_write(out, CFX_TLB, TLB_CONTROL_CG, TLB_ADDR_START_RC, start)
    cfx_write(out, CFX_TLB, TLB_CONTROL_CG, TLB_ADDR_SIZE_RC, size)
    cfx_write(out, CFX_TLB, TLB_CONTROL_CG, TLB_CONTROL_RC, 2)


def emit_main_and_metadata():
    ram = bytearray(0x200000)
    out = bytearray()
    k131.emit_boot_stub(out, ROM_BASE + SUPV_ENTRY_OFFSET)
    load_reg(out, "rd", 29, 0)

    # PTW is enabled only for set6.  Every exception vector below is in the
    # set0 ROM page, so exception entry never depends on a pageable vector.
    cfx_write(out, CFX_PTW, 2, k131.RC_EXCP_VECTOR,
              ROM_BASE + PTW_FAULT_HANDLER)
    cfx_write(out, CFX_PTW, PTW_PTBR_CG, SET, L1_BASE >> 16)
    cfx_write(out, CFX_PTW, PTW_PTHI_CG, SET, 0)
    cfx_write(out, CFX_PTW, PTW_PAHI_CG, SET, 0)
    cfx_write(out, CFX_PTW, PTW_PERM_CG, PTW_ENABLE_RC, 1 << SET)
    cfx_write(out, CFX_TLB, TLB_REG_CG, TLB_ENABLE_RC, 1 << SET)
    read_cfx_check(out, CFX_PTW, PTW_PERM_CG, PTW_ENABLE_RC, 1 << SET)
    read_cfx_check(out, CFX_TLB, TLB_REG_CG, TLB_ENABLE_RC, 1 << SET)

    # One normal L1 pointer, four normal leaves, and an independent superleaf.
    put_qword(ram, L1_BASE + 9 * 8, (L2_BASE & 0xFFFFFFFFFFFF0000) | 1)
    put_qword(ram, L1_BASE + 10 * 8, super_pte(0x80000000, PERM_R))
    pte13 = L2_BASE + 13 * 8
    pte14 = L2_BASE + 14 * 8
    pte_fault = L2_BASE + 15 * 8
    pte_nested = L2_BASE + 16 * 8
    put_qword(ram, pte13, normal_pte(PA13_OLD, PERM_R))
    put_qword(ram, pte14, normal_pte(PA14_OLD, PERM_R))
    put_qword(ram, pte_fault, normal_pte(PA_FAULT, PERM_W))
    put_qword(ram, pte_nested, normal_pte(PA_NESTED, PERM_R))
    put_qword(ram, PA13_OLD + (NORMAL_13 & 0xFFFF), VAL13_OLD)
    put_qword(ram, PA13_NEW + (NORMAL_13 & 0xFFFF), VAL13_NEW)
    put_qword(ram, PA14_OLD + (NORMAL_14 & 0xFFFF), VAL14_OLD)
    put_qword(ram, PA14_NEW + (NORMAL_14 & 0xFFFF), VAL14_NEW)
    put_qword(ram, PA_FAULT + (FAULT_VA & 0xFFFF), VAL_FAULT)
    put_qword(ram, PA_NESTED + (NESTED_VA & 0xFFFF), VAL_NESTED)
    put_qword(ram, 0x80000000 + (SUPER_VA & 0x1FFFFFFF), VAL_SUPER)

    # Normal and super translations share the enabled MMU/TLB state.
    read_mem_check(out, NORMAL_13, VAL13_OLD)  # miss/fill
    read_mem_check(out, SUPER_VA, VAL_SUPER)   # superpage miss/fill
    read_mem_check(out, NORMAL_13, VAL13_OLD)  # architectural hit

    # A walk-origin NRPERM is repaired in cfx_ptw and self-retried.
    load_reg(out, "rb", 3, FAULT_VA)
    ptw_fault_ip = ROM_BASE + len(out)
    write_rrii(out, OP_LDO, 27, 3, 0)
    k131.check_eq(out, 27, VAL_FAULT)

    # Populate two adjacent entries, change both PTEs, then exercise the
    # KL-129b low16 rule.  Only page13 may be invalidated.
    read_mem_check(out, NORMAL_14, VAL14_OLD)
    write_pte(out, pte13, normal_pte(PA13_NEW, PERM_R))
    write_pte(out, pte14, normal_pte(PA14_NEW, PERM_R))
    invalidate_range(out, (NORMAL_13 & ~0xFFFF) + 0xF000, 0x2000)
    read_mem_check(out, NORMAL_13, VAL13_NEW)
    read_mem_check(out, NORMAL_14, VAL14_OLD)

    # Fill a read-only TLB entry, then make a write hit generate cfx_tlb.
    # Its handler traps into cfx_ptw and returns via E1 before repairing,
    # invalidating, and retrying the original store.
    cfx_write(out, CFX_TLB, 2, k131.RC_EXCP_VECTOR,
              ROM_BASE + TLB_HANDLER)
    cfx_write(out, CFX_PTW, 2, k131.RC_EXCP_VECTOR,
              ROM_BASE + PTW_NESTED_HANDLER)
    read_mem_check(out, NESTED_VA, VAL_NESTED)
    load_reg(out, "rd", 2, VAL_NESTED_WRITTEN)
    load_reg(out, "rb", 3, NESTED_VA)
    nested_fault_ip = ROM_BASE + len(out)
    write_rrii(out, OP_STO, 2, 3, 0)
    read_mem_check(
        out, PA_NESTED + (NESTED_VA & 0xFFFF), VAL_NESTED_WRITTEN)

    # All synchronous MMU work is complete.  Keep every async route blocked
    # while observing the already-deasserted K1_EXT0 latch and expiring timer.
    k131.set_vector(out, CFX_TIMER, ROM_BASE + TIMER_HANDLER)
    k131.set_vector(out, CFX_UART, ROM_BASE + UART0_HANDLER)
    k131.set_excp_cause_mask(
        out, CFX_TIMER, MODE_SUPV, MASK_ALL & ~CAUSE_TIMER)
    k131.set_excp_cause_mask(
        out, CFX_UART, MODE_SUPV,
        MASK_ALL & ~CAUSE_UART0 & ~CAUSE_UART5)
    k131.set_global_mask(out, MODE_SUPV, MASK_ALL)
    k131.set_escape_mask(
        out, CFX_POWER, MODE_SUPV, MASK_ALL & ~(1 << CFX_PTW))
    k131.craft_inner_cfx_mask(
        out, CFX_PTW,
        MASK_ALL & ~(1 << CFX_TIMER) & ~(1 << CFX_UART))

    load_reg(out, "rd", ALLONES_REG, MASK_ALL)
    load_reg(out, "rd", PRESERVE_UART5_REG, MASK_ALL & ~CAUSE_UART0)
    read_cfx_check(out, CFX_UART, CG_UART, RC_UART_EXIST, 1)
    read_cfx_check(out, CFX_UART, CG_UART, RC_UART_PENDING, 1)
    read_cfx_check(
        out, CFX_UART, CG_COMMON, RC_PENDING, CAUSE_UART0 | CAUSE_UART5)

    # Timer0 expires while its private mask is set.  Pending is visible but
    # cannot dispatch until private and shared routing masks are opened.
    cfx_write(out, CFX_TIMER, CG_TIMER, RC_TIMER_MASK, 1)
    cfx_write(out, CFX_TIMER, CG_TIMER, RC_TIMER_REG0, 1)
    cfx_write(out, CFX_TIMER, CG_TIMER, RC_TIMER_CTRL, TIMER_CTRL_ENABLE)
    k133.filler(out)
    k133.filler(out)
    read_cfx_check(out, CFX_TIMER, CG_TIMER, RC_TIMER_PENDING, 1)
    read_cfx_check(out, CFX_TIMER, CG_COMMON, RC_PENDING, CAUSE_TIMER)
    cfx_write(out, CFX_TIMER, CG_TIMER, RC_TIMER_MASK, 0)

    # One shared unmask makes TIMER, UART0, and UART5 eligible together.
    # The next three saved PCs prove cfx and within-cfx priorities.
    mark_timer = ROM_BASE + len(out) + 5 * 4
    k131.set_global_mask(
        out, MODE_SUPV,
        MASK_ALL & ~(1 << CFX_TIMER) & ~(1 << CFX_UART))
    assert ROM_BASE + len(out) == mark_timer
    out.extend(struct.pack(">I", UNIMP_ENCODING))
    mark_uart0 = ROM_BASE + len(out)
    out.extend(struct.pack(">I", UNIMP_ENCODING))

    read_cfx_check(
        out, CFX_TIMER, CG_FRAME, RC_FRAME_CAUSE_ID, CAUSE_TIMER)
    read_cfx_check(
        out, CFX_TIMER, CG_FRAME, RC_FRAME_CAUSE_IP, mark_timer)
    read_cfx_check(
        out, CFX_TIMER, CG_COMMON, RC_EXCP_ASYNC_NUM, 1)
    read_cfx_check(
        out, CFX_UART, CG_FRAME, RC_FRAME_CAUSE_ID, CAUSE_UART0)
    read_cfx_check(
        out, CFX_UART, CG_FRAME, RC_FRAME_CAUSE_IP, mark_uart0)
    read_cfx_check(out, CFX_UART, CG_UART, RC_UART_PENDING, 0)
    read_cfx_check(out, CFX_UART, CG_COMMON, RC_PENDING, CAUSE_UART5)

    # UART0 handler left UART5 latched but masked.  Opening only bit37 must
    # deliver it at this exact boundary through the second vector.
    mark_uart5 = ROM_BASE + len(out) + 5 * 4
    k131.set_excp_cause_mask(
        out, CFX_UART, MODE_SUPV, MASK_ALL & ~CAUSE_UART5)
    assert ROM_BASE + len(out) == mark_uart5
    out.extend(struct.pack(">I", UNIMP_ENCODING))
    read_cfx_check(
        out, CFX_UART, CG_FRAME, RC_FRAME_CAUSE_ID, CAUSE_UART5)
    read_cfx_check(
        out, CFX_UART, CG_FRAME, RC_FRAME_CAUSE_IP, mark_uart5)
    read_cfx_check(
        out, CFX_UART, CG_COMMON, RC_EXCP_ASYNC_NUM, 2)
    # The generic UART5 test source is a persistent level.  Its handler's
    # W0C is therefore followed by the architecturally required re-latch;
    # self masking prevents another delivery before terminal halt.
    read_cfx_check(
        out, CFX_UART, CG_COMMON, RC_PENDING, CAUSE_UART5)
    k131.emit_final_halt(out, PASS, FAIL)

    metadata = {
        "ptw_fault_ip": ptw_fault_ip,
        "nested_fault_ip": nested_fault_ip,
        "pte_fault": pte_fault,
        "pte_nested": pte_nested,
        "mark_timer": mark_timer,
        "mark_uart0": mark_uart0,
        "mark_uart5": mark_uart5,
    }
    return out, ram, metadata


def append_handlers(out, metadata):
    pad_to(out, PTW_FAULT_HANDLER)
    for rc, expected in (
            (RC_FRAME_CAUSE_ID, CAUSE_PTW_NRPERM),
            (RC_FRAME_CAUSE_IP, metadata["ptw_fault_ip"]),
            (RC_FRAME_CAUSE_INFO, FAULT_VA)):
        read_cfx_check(out, CFX_PTW, CG_FRAME, rc, expected)
    write_pte(
        out, metadata["pte_fault"], normal_pte(PA_FAULT, PERM_R | PERM_W))
    load_reg(out, "rb", 3, FAULT_VA)
    k131.write_ciii(out, OP_ESCAPE, CFX_PTW, 0)

    pad_to(out, TLB_HANDLER)
    for rc, expected in (
            (RC_FRAME_CAUSE_ID, CAUSE_TLB_NWPERM),
            (RC_FRAME_CAUSE_IP, metadata["nested_fault_ip"]),
            (RC_FRAME_CAUSE_INFO, NESTED_VA)):
        read_cfx_check(out, CFX_TLB, CG_FRAME, rc, expected)
    trap_ip = ROM_BASE + len(out)
    raw_trap = (OP_TRAP << 24) | (CFX_PTW << 18) | 1
    k131.write_ciii(out, OP_TRAP, CFX_PTW, 1)
    write_pte(
        out, metadata["pte_nested"],
        normal_pte(PA_NESTED, PERM_R | PERM_W))
    invalidate_range(out, NESTED_VA & ~0xFFFF, 0x10000)
    load_reg(out, "rd", 2, VAL_NESTED_WRITTEN)
    load_reg(out, "rb", 3, NESTED_VA)
    k131.write_ciii(out, OP_ESCAPE, CFX_TLB, 0)

    pad_to(out, PTW_NESTED_HANDLER)
    for rc, expected in (
            (RC_FRAME_CAUSE_ID, CAUSE_CFXTRAP),
            (RC_FRAME_CAUSE_IP, trap_ip),
            (RC_FRAME_CAUSE_INFO, raw_trap),
            (RC_FRAME_PREV_CFX_CODE, CFX_TLB)):
        read_cfx_check(out, CFX_PTW, CG_FRAME, rc, expected)
    k131.write_ciii(out, OP_ESCAPE, CFX_PTW, 1)

    pad_to(out, TIMER_HANDLER)
    k131.write_crrr(
        out, OP_CFX2RC, CFX_TIMER, MODE_SUPV,
        RC_EXCP_CAUSE_MASK, ALLONES_REG)
    k131.write_crrr(
        out, OP_CFX2RC, CFX_TIMER, CG_TIMER, RC_TIMER_PENDING, 0)
    k131.write_crrr(
        out, OP_CFX2RC, CFX_TIMER, CG_COMMON, RC_PENDING, 0)
    k131.write_ciii(out, OP_ESCAPE, CFX_TIMER, 1)

    pad_to(out, UART0_HANDLER)
    # Mask all UART causes before acknowledging the deasserted K1_EXT0.
    k131.write_crrr(
        out, OP_CFX2RC, CFX_UART, MODE_SUPV,
        RC_EXCP_CAUSE_MASK, ALLONES_REG)
    k131.write_crrr(
        out, OP_CFX2RC, CFX_UART, CG_UART, RC_UART_PENDING, 0)
    k131.write_crrr(
        out, OP_CFX2RC, CFX_UART, CG_COMMON, RC_PENDING,
        PRESERVE_UART5_REG)
    cfx_write(
        out, CFX_UART, 2, k131.RC_EXCP_VECTOR,
        ROM_BASE + UART5_HANDLER)
    k131.write_ciii(out, OP_ESCAPE, CFX_UART, 1)

    pad_to(out, UART5_HANDLER)
    k131.write_crrr(
        out, OP_CFX2RC, CFX_UART, MODE_SUPV,
        RC_EXCP_CAUSE_MASK, ALLONES_REG)
    k131.write_crrr(
        out, OP_CFX2RC, CFX_UART, CG_COMMON, RC_PENDING, 0)
    k131.write_ciii(out, OP_ESCAPE, CFX_UART, 1)
    pad_to(out, ROM_END)


def build_image():
    out, ram, metadata = emit_main_and_metadata()
    append_handlers(out, metadata)
    return bytes(out), bytes(ram)


def backend_command(backend, rom_path, ram_path):
    if backend == "qemu":
        return [
            QEMU, "-M", "dadao-m1",
            "-global", "dadao-cpu.k1-ext0-test-enable=on",
            "-global", "dadao-cpu.k1-ext0-assert-retired=0",
            "-global", "dadao-cpu.k1-ext0-deassert-retired=1",
            "-global", f"dadao-cpu.cfx-async-test-level-b-code={CFX_UART}",
            "-global",
            f"dadao-cpu.cfx-async-test-level-b-seed={hex(CAUSE_UART5)}",
            "-bios", rom_path, "-kernel", ram_path,
            "-display", "none", "-serial", "none", "-d", "int,mmu",
        ]
    outdir = tempfile.mkdtemp(prefix="gem5_kl139a_")
    return [
        GEM5, "--outdir=" + outdir, GEM5_FS_CFG, rom_path,
        "--data-image", ram_path,
        "--k1-ext0-schedule", "0", "1",
        "--cfx-async-level-b", str(CFX_UART), hex(CAUSE_UART5),
    ]


def run_backend(backend, round_no, rom_path, ram_path):
    command = backend_command(backend, rom_path, ram_path)
    result = subprocess.run(
        command, capture_output=True, timeout=180, text=True)
    log_path = os.path.join(
        EVIDENCE, f"integration-{backend}-round{round_no:02d}.log")
    with open(log_path, "w") as stream:
        stream.write("=== command ===\n" + " ".join(command))
        stream.write("\n=== stdout ===\n" + result.stdout)
        stream.write("\n=== stderr ===\n" + result.stderr)
    if result.returncode != PASS:
        raise AssertionError(
            f"{backend} round{round_no}: rc={result.returncode}, "
            f"expected={PASS}\n{result.stdout[-3000:]}\n"
            f"{result.stderr[-5000:]}")
    if backend == "gem5" and k131.gem5_code(result.stdout) != PASS:
        raise AssertionError(f"gem5 round{round_no}: invalid SIM_END")
    trace = result.stdout + result.stderr
    for marker in ("cfx_tlb miss-fill", "cfx_tlb hit"):
        if marker not in trace:
            raise AssertionError(
                f"{backend} round{round_no}: missing trace marker {marker!r}")
    return log_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=1)
    args = parser.parse_args()
    if args.rounds < 1:
        parser.error("--rounds must be positive")

    os.makedirs(EVIDENCE, exist_ok=True)
    rom, ram = build_image()
    rom_path = os.path.join(EVIDENCE, "kl139a-integration.bin")
    ram_path = os.path.join(EVIDENCE, "kl139a-integration-ram.bin")
    with open(rom_path, "wb") as stream:
        stream.write(rom)
    with open(ram_path, "wb") as stream:
        stream.write(ram)

    for round_no in range(1, args.rounds + 1):
        for backend in ("qemu", "gem5"):
            run_backend(backend, round_no, rom_path, ram_path)
        print(
            f"round {round_no}/{args.rounds}: "
            f"qemu={PASS} gem5={PASS}")

    passed = args.rounds
    claims = (
        "MMU-enable+resident-vectors, normal+super, walk-fault-self-retry, "
        "TLB-miss/fill/hit/low16-invalidate, TLB->PTW->TLB-E1, "
        "timer-masked-expiry+precise-delivery, K1_EXT0-lifecycle+delivery, "
        "cfx18-before-cfx62, UART0-before-UART5"
    )
    nonclaims = (
        "Linux paging, vector-page recovery, TLB performance/timing, "
        "TLB disable-enable entry lifetime, timer1-7/increment mode, "
        "real UART/PLIC/device protocol, Minor/O3/SE, multi-hart"
    )
    print(
        f"QEMU: pass=[{claims}] rounds={passed}/{passed}; "
        f"skip=[]; fail=[]; "
        f"non-claim=[{nonclaims}]")
    print(
        f"gem5: pass=[{claims}] rounds={passed}/{passed}; "
        f"skip=[]; fail=[]; "
        f"non-claim=[{nonclaims}]")
    print(
        "PASS: one shared bare-metal image; MMU+resident vectors+"
        "normal/super+walk-fault-retry+TLB miss/fill/hit/low16-invalidate+"
        "TLB->PTW->TLB E1+masked timer+K1_EXT0 lifecycle+"
        "cross-cfx/same-cfx priority")


if __name__ == "__main__":
    main()
