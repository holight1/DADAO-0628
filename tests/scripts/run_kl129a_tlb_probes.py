#!/usr/bin/env python3
"""KL-129a dual-backend architectural TLB probes.

Guest-side checks discriminate miss/fill from hit, both invalidation modes,
all seven hit-generated causes, 16-way true LRU, and the real
cfx_tlb -> trap cfx_ptw -> cfx_tlb E1 return chain.  Backend logs are kept
as supporting evidence; success never depends on process exit alone.
"""

import os
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
GEM5 = os.environ.get(
    "GEM5_OPT", os.path.join(GEM5_DIR, "build", "DADAO", "gem5.opt"))
GEM5_CFG = os.environ.get(
    "GEM5_FS", os.path.join(GEM5_DIR, "tests", "dadao", "dadao_fs.py"))
EVIDENCE = os.path.join(REPO, ".work", "evidence", "kl129a-tlb")

sys.path.insert(0, HERE)
from build_test_binary import load_reg, write_rrii, UNIMP_ENCODING  # noqa:E402


ROM_BASE = 0x00100000
RAM_BASE = 0x80000000
PASS = 42
FAIL = 0x9B
SET = 6
L1_INDEX = 9
L1_BASE = 0x80010000
L2_BASE = 0x80020000

CFX_PTW = 4
CFX_TLB = 5
OP_CFX2RD = 0x72
OP_CFX2RC = 0x73
OP_TRAP = 0x76
OP_ESCAPE = 0x77
OP_HALT = 0x00
OP_JUMP_R = 0x65
OP_LDO = 0x33
OP_STO = 0x3B
OP_MISC = 0x10
MISC_ORR = 0x09
MISC_XOR = 0x0A
OP_CSZ = 0x22

PTW_PERM_CG = 8
PTW_ENABLE_RC = 8
PTW_PTBR_CG = 9
PTW_PTHI_CG = 10
PTW_PAHI_CG = 11
TLB_REG_CG = 8
TLB_EXIST_RC = 0
TLB_ENABLE_RC = 8
TLB_CONTROL_CG = 12
TLB_CONTROL_RC = 0
TLB_ADDR_START_RC = 2
TLB_ADDR_SIZE_RC = 3

PERM_R = 1 << 7
PERM_W = 1 << 6
PERM_X = 1 << 5
CAUSES = {
    "NXPERM": 1 << 12,
    "NWPERM": 1 << 13,
    "NRPERM": 1 << 14,
    "IGPFTRAP": 1 << 18,
    "ISPFTRAP": 1 << 19,
    "DGPFTRAP": 1 << 22,
    "DSPFTRAP": 1 << 23,
}


def write_crrr(out, op, cfxcode, cg, rc, rd):
    word = (op << 24) | (cfxcode << 18) | (cg << 12) | (rc << 6) | rd
    out.extend(struct.pack(">I", word))


def write_ciii(out, op, cfxcode, imm18):
    out.extend(struct.pack(
        ">I", (op << 24) | (cfxcode << 18) | (imm18 & 0x3FFFF)))


def write_orrr(out, minor, dst, lhs, rhs):
    out.extend(struct.pack(
        ">I", (OP_MISC << 24) | (minor << 18) | (dst << 12) |
        (lhs << 6) | rhs))


def cfx_write(out, cfxcode, cg, rc, value):
    load_reg(out, "rd", 2, value)
    write_crrr(out, OP_CFX2RC, cfxcode, cg, rc, 2)


def emit_halt(out, rd):
    out.extend(struct.pack(">I", (OP_HALT << 24) | (rd << 18)))


def emit_value_check(out, actual_rd, expected):
    load_reg(out, "rd", 4, expected)
    write_orrr(out, MISC_XOR, 5, actual_rd, 4)
    write_orrr(out, MISC_ORR, 30, 30, 5)


def emit_result(out):
    load_reg(out, "rd", 26, PASS)
    load_reg(out, "rd", 27, FAIL)
    out.extend(struct.pack(
        ">I", (OP_CSZ << 24) | (30 << 18) | (28 << 12) |
        (26 << 6) | 27))
    emit_halt(out, 28)


def pad_to(out, offset):
    if len(out) > offset:
        raise AssertionError(f"probe overflow {len(out):#x}>{offset:#x}")
    while len(out) < offset:
        out.extend(struct.pack(">I", UNIMP_ENCODING))


def put_qword(image, pa, value):
    off = pa - RAM_BASE
    image[off:off + 8] = struct.pack(">Q", value)


def put_blob(image, pa, blob):
    off = pa - RAM_BASE
    image[off:off + len(blob)] = blob


def normal_va(l2_index, fragment=3, offset=0x100):
    return (SET << 42) | (L1_INDEX << 29) | (l2_index << 16) | \
        (fragment << 13) | offset


def super_va(fragment=1, offset=0x2000):
    return (SET << 42) | (L1_INDEX << 29) | (fragment << 26) | offset


def normal_pte(pa, fragments, perms):
    fragment_bits = sum(1 << (56 + f) for f in fragments)
    return fragment_bits | (pa & 0x0000FFFFFFFF0000) | perms | 1


def super_pte(pa, fragments, perms):
    fragment_bits = sum(1 << (56 + f) for f in fragments)
    return fragment_bits | (pa & 0x0000FFFFE0000000) | perms | 3


def base_image():
    image = bytearray(0x400000)
    put_qword(image, L1_BASE + L1_INDEX * 8,
              (L2_BASE & 0x0000FFFFFFFF0000) | 1)
    return image


def setup(out):
    load_reg(out, "rd", 30, 0)
    cfx_write(out, CFX_PTW, PTW_PTBR_CG, SET, L1_BASE >> 16)
    cfx_write(out, CFX_PTW, PTW_PTHI_CG, SET, 0)
    cfx_write(out, CFX_PTW, PTW_PAHI_CG, SET, 0)
    cfx_write(out, CFX_PTW, PTW_PERM_CG, PTW_ENABLE_RC, 1 << SET)


def read_va(out, va, rd=3):
    load_reg(out, "rb", 3, va)
    write_rrii(out, OP_LDO, rd, 3, 0)


def write_va(out, va, value):
    load_reg(out, "rd", 2, value)
    load_reg(out, "rb", 3, va)
    write_rrii(out, OP_STO, 2, 3, 0)


def write_pte(out, pte_addr, pte):
    load_reg(out, "rd", 2, pte)
    load_reg(out, "rb", 3, pte_addr)
    write_rrii(out, OP_STO, 2, 3, 0)


def gen_hit_and_register_probe():
    image = base_image()
    out = bytearray()
    setup(out)
    write_crrr(out, OP_CFX2RD, CFX_TLB, TLB_REG_CG, TLB_EXIST_RC, 3)
    emit_value_check(out, 3, 0xFFFFFFFFFFFFFFFF)
    write_crrr(out, OP_CFX2RD, CFX_TLB, TLB_REG_CG, TLB_ENABLE_RC, 3)
    emit_value_check(out, 3, 0xFFFFFFFFFFFFFFFF)
    write_crrr(out, OP_CFX2RD, CFX_TLB, TLB_CONTROL_CG,
               TLB_ADDR_SIZE_RC, 3)
    emit_value_check(out, 3, 65536)
    cfx_write(out, CFX_TLB, TLB_REG_CG, TLB_ENABLE_RC, 1 << SET)

    va = normal_va(13)
    pte_addr = L2_BASE + 13 * 8
    pa_old, pa_new = 0x80100000, 0x80110000
    old_value, new_value = 0x1290000000000001, 0x1290000000000002
    put_qword(image, pte_addr, normal_pte(pa_old, [3], PERM_R))
    put_qword(image, pa_old + (va & 0xFFFF), old_value)
    put_qword(image, pa_new + (va & 0xFFFF), new_value)
    read_va(out, va)
    emit_value_check(out, 3, old_value)
    write_pte(out, pte_addr, normal_pte(pa_new, [3], PERM_R))
    read_va(out, va)
    emit_value_check(out, 3, old_value)
    emit_result(out)
    return bytes(out), bytes(image)


def gen_invalidate_probe(kind):
    image = base_image()
    out = bytearray()
    setup(out)
    entries = []
    for idx, old_pa, new_pa in (
            (13, 0x80100000, 0x80120000),
            (14, 0x80110000, 0x80130000)):
        va = normal_va(idx)
        pte_addr = L2_BASE + idx * 8
        old_value = 0x1291000000000000 | idx
        new_value = 0x1292000000000000 | idx
        put_qword(image, pte_addr, normal_pte(old_pa, [3], PERM_R))
        put_qword(image, old_pa + (va & 0xFFFF), old_value)
        put_qword(image, new_pa + (va & 0xFFFF), new_value)
        entries.append((va, pte_addr, new_pa, old_value, new_value))
        read_va(out, va)
        emit_value_check(out, 3, old_value)
    for va, pte_addr, new_pa, _, _ in entries:
        write_pte(out, pte_addr, normal_pte(new_pa, [3], PERM_R))
    if kind == "all":
        cfx_write(out, CFX_TLB, TLB_CONTROL_CG, TLB_CONTROL_RC, 1)
        expected = [entries[0][4], entries[1][4]]
    else:
        cfx_write(out, CFX_TLB, TLB_CONTROL_CG,
                  TLB_ADDR_START_RC, entries[0][0] & ~0xFFFF)
        cfx_write(out, CFX_TLB, TLB_CONTROL_CG, TLB_ADDR_SIZE_RC, 65536)
        cfx_write(out, CFX_TLB, TLB_CONTROL_CG, TLB_CONTROL_RC, 2)
        expected = [entries[0][4], entries[1][3]]
    for entry, value in zip(entries, expected):
        read_va(out, entry[0])
        emit_value_check(out, 3, value)
    emit_result(out)
    return bytes(out), bytes(image)


def gen_disabled_bypass_probe():
    image = base_image()
    out = bytearray()
    setup(out)
    va = normal_va(13)
    pte_addr = L2_BASE + 13 * 8
    pa_old, pa_new = 0x80100000, 0x80110000
    old_value, new_value = 0x1296000000000001, 0x1296000000000002
    put_qword(image, pte_addr, normal_pte(pa_old, [3], PERM_R))
    put_qword(image, pa_old + (va & 0xFFFF), old_value)
    put_qword(image, pa_new + (va & 0xFFFF), new_value)
    read_va(out, va)
    emit_value_check(out, 3, old_value)
    write_pte(out, pte_addr, normal_pte(pa_new, [3], PERM_R))
    cfx_write(out, CFX_TLB, TLB_REG_CG, TLB_ENABLE_RC,
              0xFFFFFFFFFFFFFFFF ^ (1 << SET))
    read_va(out, va)
    emit_value_check(out, 3, new_value)
    emit_result(out)
    return bytes(out), bytes(image)


def gen_lru_probe():
    image = base_image()
    out = bytearray()
    setup(out)
    entries = []
    for way in range(17):
        idx = 20 + way
        va = normal_va(idx)
        pa = 0x80100000 + way * 0x10000
        value = 0x1293000000000000 | way
        pte_addr = L2_BASE + idx * 8
        put_qword(image, pte_addr, normal_pte(pa, [3], PERM_R))
        put_qword(image, pa + (va & 0xFFFF), value)
        entries.append((va, pte_addr, pa, value))
    for entry in entries[:16]:
        read_va(out, entry[0])
        emit_value_check(out, 3, entry[3])
    # Touch way 0, then fill way 16: true LRU must evict way 1.
    read_va(out, entries[0][0])
    emit_value_check(out, 3, entries[0][3])
    read_va(out, entries[16][0])
    emit_value_check(out, 3, entries[16][3])

    new0_pa, new1_pa = 0x80220000, 0x80230000
    new0_val, new1_val = 0x1293F00000000000, 0x1293F00000000001
    put_qword(image, new0_pa + (entries[0][0] & 0xFFFF), new0_val)
    put_qword(image, new1_pa + (entries[1][0] & 0xFFFF), new1_val)
    write_pte(out, entries[0][1], normal_pte(new0_pa, [3], PERM_R))
    write_pte(out, entries[1][1], normal_pte(new1_pa, [3], PERM_R))
    read_va(out, entries[1][0])
    emit_value_check(out, 3, new1_val)
    read_va(out, entries[0][0])
    emit_value_check(out, 3, entries[0][3])
    emit_result(out)
    return bytes(out), bytes(image)


def emit_fault_checks(out, cause, cause_ip, cause_info):
    for rc, expected in ((2, cause), (3, cause_ip), (4, cause_info)):
        write_crrr(out, OP_CFX2RD, CFX_TLB, 5, rc, 3)
        emit_value_check(out, 3, expected)


def gen_hit_fault_probe(name):
    image = base_image()
    out = bytearray()
    setup(out)
    handler_offset = 0x900
    result_offset = 0x700
    cfx_write(out, CFX_TLB, 2, 10, ROM_BASE + handler_offset)

    instruction_fault = name in ("NXPERM", "IGPFTRAP", "ISPFTRAP")
    superpage = name in ("ISPFTRAP", "DSPFTRAP")
    if superpage:
        good_va, bad_va = super_va(1), super_va(2)
        pa = 0x80000000
        perms = PERM_X if instruction_fault else PERM_R
        pte = super_pte(pa, [1], perms)
        pte_addr = L1_BASE + L1_INDEX * 8
        put_qword(image, pte_addr, pte)
    else:
        good_va, bad_va = normal_va(13, 3), normal_va(13, 4)
        pa = 0x80100000
        perms = {
            "NXPERM": PERM_R,
            "NWPERM": PERM_R,
            "NRPERM": PERM_W,
            "IGPFTRAP": PERM_X,
            "DGPFTRAP": PERM_R,
        }[name]
        fragments = [3] if name.endswith("PFTRAP") else [3, 4]
        pte = normal_pte(pa, fragments, perms)
        pte_addr = L2_BASE + 13 * 8
        put_qword(image, pte_addr, pte)

    if name == "NRPERM":
        write_va(out, good_va, 0x1294000000000001)
    elif instruction_fault and name != "NXPERM":
        continuation = ROM_BASE + 0x500
        jump_back = (OP_JUMP_R << 24) | (4 << 18)
        leaf_pa = pa + (good_va & (0x1FFFFFFF if superpage else 0xFFFF))
        if superpage:
            # The shared sparse 0x84000000 super fragment is outside the
            # contiguous data image; populate it through its identity path.
            write_va(out, leaf_pa, jump_back << 32)
        load_reg(out, "rb", 4, continuation)
        load_reg(out, "rb", 3, good_va)
        write_rrii(out, OP_JUMP_R, 3, 0, 0)
        leaf = bytearray()
        write_rrii(leaf, OP_JUMP_R, 4, 0, 0)
        if not superpage:
            put_blob(image, leaf_pa, leaf)
        pad_to(out, continuation - ROM_BASE)
    else:
        read_va(out, good_va)

    if name in ("NWPERM",):
        load_reg(out, "rd", 2, 0x1294000000000002)
        load_reg(out, "rb", 3, bad_va)
        cause_ip = ROM_BASE + len(out)
        write_rrii(out, OP_STO, 2, 3, 0)
    elif name in ("NRPERM", "DGPFTRAP", "DSPFTRAP"):
        load_reg(out, "rb", 3, bad_va)
        cause_ip = ROM_BASE + len(out)
        write_rrii(out, OP_LDO, 3, 3, 0)
    else:
        load_reg(out, "rb", 3, bad_va)
        cause_ip = bad_va
        write_rrii(out, OP_JUMP_R, 3, 0, 0)
    if not instruction_fault:
        load_reg(out, "rb", 4, ROM_BASE + result_offset)
        write_rrii(out, OP_JUMP_R, 4, 0, 0)
    pad_to(out, result_offset)
    emit_result(out)

    pad_to(out, handler_offset)
    emit_fault_checks(out, CAUSES[name], cause_ip, bad_va)
    if instruction_fault:
        cfx_write(out, CFX_TLB, 5, 3, ROM_BASE + result_offset)
        write_ciii(out, OP_ESCAPE, CFX_TLB, 0)
    else:
        write_ciii(out, OP_ESCAPE, CFX_TLB, 1)
    return bytes(out), bytes(image)


def gen_nested_probe():
    image = base_image()
    out = bytearray()
    setup(out)
    tlb_handler = 0x800
    ptw_handler = 0xC00
    cfx_write(out, CFX_TLB, 2, 10, ROM_BASE + tlb_handler)
    cfx_write(out, CFX_PTW, 2, 10, ROM_BASE + ptw_handler)
    va = normal_va(13)
    pa = 0x80100000
    pte_addr = L2_BASE + 13 * 8
    denied = normal_pte(pa, [3], PERM_R)
    corrected = normal_pte(pa, [3], PERM_R | PERM_W)
    put_qword(image, pte_addr, denied)
    read_va(out, va)
    write_va(out, va, 0x1295000000000001)
    read_va(out, pa + (va & 0xFFFF))
    emit_value_check(out, 3, 0x1295000000000001)
    emit_result(out)

    pad_to(out, tlb_handler)
    # The seven dedicated hit-fault probes validate exact cause_ip. This
    # nested probe focuses on both E1 frame transitions and successful retry.
    for rc, expected in ((2, CAUSES["NWPERM"]), (4, va)):
        write_crrr(out, OP_CFX2RD, CFX_TLB, 5, rc, 3)
        emit_value_check(out, 3, expected)
    trap_offset = len(out)
    write_ciii(out, OP_TRAP, CFX_PTW, 1)
    write_pte(out, pte_addr, corrected)
    cfx_write(out, CFX_TLB, TLB_CONTROL_CG, TLB_ADDR_START_RC, va & ~0xFFFF)
    cfx_write(out, CFX_TLB, TLB_CONTROL_CG, TLB_ADDR_SIZE_RC, 65536)
    cfx_write(out, CFX_TLB, TLB_CONTROL_CG, TLB_CONTROL_RC, 2)
    # Retry resumes at the faulting STO, so restore its live operands after
    # the handler's CFX/PTE scratch work.
    load_reg(out, "rd", 2, 0x1295000000000001)
    load_reg(out, "rb", 3, va)
    write_ciii(out, OP_ESCAPE, CFX_TLB, 0)

    pad_to(out, ptw_handler)
    raw_trap = (OP_TRAP << 24) | (CFX_PTW << 18) | 1
    for rc, expected in (
            (2, 1), (3, ROM_BASE + trap_offset),
            (4, raw_trap), (5, CFX_TLB)):
        write_crrr(out, OP_CFX2RD, CFX_PTW, 5, rc, 3)
        emit_value_check(out, 3, expected)
    write_ciii(out, OP_ESCAPE, CFX_PTW, 1)
    return bytes(out), bytes(image)


def run_backend(name, backend, rom_path, ram_path):
    if backend == "qemu":
        command = [
            QEMU, "-M", "dadao-m1", "-bios", rom_path,
            "-kernel", ram_path, "-display", "none", "-serial", "none",
            "-d", "int,mmu",
        ]
    else:
        command = [
            GEM5, "--outdir=" + tempfile.mkdtemp(prefix=f"gem5_kl129a_{name}_"),
            GEM5_CFG, rom_path, "--data-image", ram_path,
        ]
    result = subprocess.run(
        command, capture_output=True, timeout=90, text=True)
    with open(os.path.join(EVIDENCE, f"{name}-{backend}.log"), "w") as stream:
        stream.write("=== command ===\n" + " ".join(command))
        stream.write("\n=== stdout ===\n" + result.stdout)
        stream.write("\n=== stderr ===\n" + result.stderr)
    assert result.returncode == PASS, (
        f"{name}/{backend} rc={result.returncode}\n{result.stderr}")
    if backend == "gem5":
        assert f"SIM_END: halt code={PASS}" in result.stdout
    if name == "hit-register":
        assert "cfx_tlb miss-fill" in result.stderr
        assert "cfx_tlb hit" in result.stderr


def run(name, rom, ram):
    os.makedirs(EVIDENCE, exist_ok=True)
    rom_path = os.path.join(EVIDENCE, name + ".bin")
    ram_path = os.path.join(EVIDENCE, name + "-ram.bin")
    with open(rom_path, "wb") as stream:
        stream.write(rom)
    with open(ram_path, "wb") as stream:
        stream.write(ram)
    for backend in ("qemu", "gem5"):
        run_backend(name, backend, rom_path, ram_path)
    print(f"{name}: qemu=42 gem5=42")


def main():
    probes = [
        ("hit-register", gen_hit_and_register_probe()),
        ("invalidate-all", gen_invalidate_probe("all")),
        ("invalidate-range", gen_invalidate_probe("range")),
        ("disabled-bypass", gen_disabled_bypass_probe()),
        ("true-lru-16way", gen_lru_probe()),
    ]
    probes.extend(
        (f"hit-fault-{name.lower()}", gen_hit_fault_probe(name))
        for name in CAUSES)
    probes.append(("nested-tlb-ptw-tlb", gen_nested_probe()))
    for name, (rom, ram) in probes:
        run(name, rom, ram)
    print("PASS: 13 probes; registers + miss/fill/hit + disabled bypass + "
          "invalidate all/range + 16-way true LRU + 7/7 hit causes + "
          "TLB->PTW->TLB E1; "
          "QEMU=gem5")


if __name__ == "__main__":
    main()
