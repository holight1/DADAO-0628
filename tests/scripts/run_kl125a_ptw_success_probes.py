#!/usr/bin/env python3
"""KL-125a QEMU PTW successful-path probes.

Builds flat ROM programs plus a static RAM image.  Covers cfx_ptw register
storage, disabled-PTBR identity access, and X/R/W success for both a 512 MiB
superpage and a two-level 64 KiB page.  The normal-page L2 table is reached
through PTHI=2 while final data uses the distinct PAHI=1.
"""

import os
import re
import struct
import subprocess


HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
QEMU = os.environ.get(
    "QEMU_DADAO",
    os.path.join(REPO, ".work", "source", "qemu", "build",
                 "qemu-system-dadao"))
EVIDENCE = os.path.join(REPO, ".work", "evidence", "kl125a-ptw")

import sys
sys.path.insert(0, HERE)
from build_test_binary import load_reg, write_rrii  # noqa: E402


ROM_BASE = 0x00100000
RAM_BASE = 0x80000000
PASS = 42
FAIL = 0x98

CFX_PTW = 4
OP_CFX2RD = 0x72
OP_CFX2RC = 0x73
OP_HALT = 0x00
OP_JUMP_R = 0x65
OP_LDO = 0x33
OP_STO = 0x3B
OP_STT = 0x3A
OP_MISC = 0x10
MISC_ORR = 0x09
MISC_XOR = 0x0A
OP_CSZ = 0x22

PTW_PERM_CG = 8
PTW_ENABLE_RC = 8
PTW_PTBR_CG = 9
PTW_PTHI_CG = 10
PTW_PAHI_CG = 11

SUPER_INDEX = 1
NORMAL_INDEX = 2
SUPER_L1_INDEX = 3
NORMAL_L1_INDEX = 5
NORMAL_L2_INDEX = 7
SUPER_FRAGMENT = 1
NORMAL_FRAGMENT = 3
SUPER_OFFSET = (SUPER_FRAGMENT << 26) | 0x20000
NORMAL_OFFSET = (NORMAL_L2_INDEX << 16) | \
    (NORMAL_FRAGMENT << 13) | 0x100
SUPER_VA_BASE = (SUPER_INDEX << 42) | (SUPER_L1_INDEX << 29)
NORMAL_VA_BASE = (NORMAL_INDEX << 42) | (NORMAL_L1_INDEX << 29)
SUPER_PA = RAM_BASE + SUPER_OFFSET
NORMAL_PA = 0x0001000080200000 | (NORMAL_OFFSET & 0xffff)
NORMAL_BACKING_PA = 0x80300000 | (NORMAL_OFFSET & 0xffff)

SUPER_L1_PA = 0x80010000
NORMAL_L1_PA = 0x80030000
NORMAL_L2_HIGH_PA = 0x0002000084000000
NORMAL_L2_BACKING_PA = 0x80100000


def write_crrr(out, op, cfxcode, cg, rc, rd):
    word = ((op & 0xff) << 24) | ((cfxcode & 0x3f) << 18) | \
        ((cg & 0x3f) << 12) | ((rc & 0x3f) << 6) | (rd & 0x3f)
    out.extend(struct.pack(">I", word))


def write_orrr(out, minor, dst, lhs, rhs):
    word = (OP_MISC << 24) | ((minor & 0x3f) << 18) | \
        ((dst & 0x3f) << 12) | ((lhs & 0x3f) << 6) | (rhs & 0x3f)
    out.extend(struct.pack(">I", word))


def emit_halt(out, rd):
    out.extend(struct.pack(">I", (OP_HALT << 24) | (rd << 18)))


def emit_result(out, mismatch_rd=30):
    load_reg(out, "rd", 26, PASS)
    load_reg(out, "rd", 27, FAIL)
    word = (OP_CSZ << 24) | (mismatch_rd << 18) | \
        (28 << 12) | (26 << 6) | 27
    out.extend(struct.pack(">I", word))
    emit_halt(out, 28)


def emit_value_check(out, actual_rd, expected):
    load_reg(out, "rd", 4, expected)
    write_orrr(out, MISC_XOR, 5, actual_rd, 4)
    write_orrr(out, MISC_ORR, 30, 30, 5)


def cfx_write(out, cg, rc, value):
    load_reg(out, "rd", 2, value)
    write_crrr(out, OP_CFX2RC, CFX_PTW, cg, rc, 2)


def configure_ptw(out, index, l1_pa, pthi, pahi):
    cfx_write(out, PTW_PTBR_CG, index, l1_pa >> 16)
    cfx_write(out, PTW_PTHI_CG, index, pthi)
    cfx_write(out, PTW_PAHI_CG, index, pahi)
    cfx_write(out, PTW_PERM_CG, PTW_ENABLE_RC, 1 << index)


def initialize_leaf(out, kind, access):
    physical = SUPER_PA if kind == "super" else NORMAL_BACKING_PA
    if access == "exec":
        code = bytearray()
        load_reg(code, "rd", 2, PASS)
        emit_halt(code, 2)
        for offset in range(0, len(code), 4):
            word = int.from_bytes(code[offset:offset + 4], "big")
            load_reg(out, "rd", 2, word)
            load_reg(out, "rb", 3, physical + offset)
            write_rrii(out, OP_STT, 2, 3, 0)
    elif access == "read":
        load_reg(out, "rd", 2, fixture_value(kind))
        load_reg(out, "rb", 3, physical)
        write_rrii(out, OP_STO, 2, 3, 0)


def gen_register_probe():
    out = bytearray()
    load_reg(out, "rd", 30, 0)
    checks = [
        (PTW_PERM_CG, 0, 0x11, 0x11),
        (PTW_PERM_CG, 1, 0x23, 0x23),
        (PTW_PERM_CG, 2, 0x35, 0x35),
        (PTW_PERM_CG, 3, 0x47, 0x47),
        (PTW_PERM_CG, PTW_ENABLE_RC, 1 << 5, 1 << 5),
        (PTW_PTBR_CG, 5, 0x123456789ABC, 0x123456789ABC),
        (PTW_PTHI_CG, 5, 0x12345, 0x2345),
        (PTW_PAHI_CG, 5, 0xABCDE, 0xBCDE),
    ]
    for cg, rc, value, expected in checks:
        cfx_write(out, cg, rc, value)
        write_crrr(out, OP_CFX2RD, CFX_PTW, cg, rc, 3)
        emit_value_check(out, 3, expected)
    emit_result(out)
    return bytes(out)


def gen_disabled_probe():
    out = bytearray()
    marker = 0x80001000
    value = 0xD15AB1ED12345678
    cfx_write(out, PTW_PTBR_CG, 0, 0xDEADBEEF)
    load_reg(out, "rd", 2, value)
    load_reg(out, "rb", 3, marker)
    write_rrii(out, OP_STO, 2, 3, 0)
    write_rrii(out, OP_LDO, 3, 3, 0)
    load_reg(out, "rd", 30, 0)
    emit_value_check(out, 3, value)
    emit_result(out)
    return bytes(out)


def gen_access_probe(kind, access):
    out = bytearray()
    index = SUPER_INDEX if kind == "super" else NORMAL_INDEX
    virtual = (SUPER_VA_BASE + SUPER_OFFSET
               if kind == "super" else NORMAL_VA_BASE + NORMAL_OFFSET)
    backing = SUPER_PA if kind == "super" else NORMAL_BACKING_PA
    l1_pa = SUPER_L1_PA if kind == "super" else NORMAL_L1_PA
    pthi = 0 if kind == "super" else 2
    pahi = 0 if kind == "super" else 1
    initialize_leaf(out, kind, access)
    configure_ptw(out, index, l1_pa, pthi, pahi)

    if access == "exec":
        load_reg(out, "rb", 3, virtual)
        write_rrii(out, OP_JUMP_R, 3, 0, 0)
    elif access == "read":
        load_reg(out, "rb", 3, virtual)
        write_rrii(out, OP_LDO, 3, 3, 0)
        load_reg(out, "rd", 30, 0)
        emit_value_check(out, 3, fixture_value(kind))
        emit_result(out)
    else:
        value = fixture_value(kind)
        load_reg(out, "rd", 2, value)
        load_reg(out, "rb", 3, virtual)
        write_rrii(out, OP_STO, 2, 3, 0)
        # Verify through the still-disabled index-0 physical identity path.
        load_reg(out, "rb", 3, backing)
        write_rrii(out, OP_LDO, 3, 3, 0)
        load_reg(out, "rd", 30, 0)
        emit_value_check(out, 3, value)
        emit_result(out)
    return bytes(out)


def fixture_value(kind):
    return (0x5155504552504147 if kind == "super"
            else 0x4E4F524D414C5047)


def leaf_permissions(access):
    return {"read": 1 << 7, "write": 1 << 6, "exec": 1 << 5}[access]


def put_qword(image, pa, value):
    offset = pa - RAM_BASE
    image[offset:offset + 8] = struct.pack(">Q", value)


def gen_ram_fixture(kind, access):
    image = bytearray(0x110000)
    perms = leaf_permissions(access)
    if kind == "super":
        pte = (1 << (56 + SUPER_FRAGMENT)) | \
            (0x8000 << 16) | perms | 0x3
        put_qword(image, SUPER_L1_PA + SUPER_L1_INDEX * 8, pte)
    else:
        l1_pte = (0x8400 << 16) | 0x1
        l2_pte = (1 << (56 + NORMAL_FRAGMENT)) | \
            (0x8020 << 16) | perms | 0x1
        put_qword(image, NORMAL_L1_PA + NORMAL_L1_INDEX * 8, l1_pte)
        put_qword(
            image, NORMAL_L2_BACKING_PA + NORMAL_L2_INDEX * 8, l2_pte)
    return bytes(image)


def run(name, rom, ram=None, expected_ptw=None):
    os.makedirs(EVIDENCE, exist_ok=True)
    rom_path = os.path.join(EVIDENCE, name + ".bin")
    with open(rom_path, "wb") as stream:
        stream.write(rom)
    command = [
        QEMU, "-M", "dadao-m1", "-bios", rom_path,
        "-display", "none", "-serial", "none", "-d", "int,mmu",
    ]
    if ram is not None:
        ram_path = os.path.join(EVIDENCE, name + "-ram.bin")
        with open(ram_path, "wb") as stream:
            stream.write(ram)
        command[5:5] = ["-kernel", ram_path]
    result = subprocess.run(
        command, capture_output=True, timeout=60, text=True)
    with open(os.path.join(EVIDENCE, name + ".log"), "w") as stream:
        stream.write("=== command ===\n" + " ".join(command))
        stream.write("\n=== stdout ===\n" + result.stdout)
        stream.write("\n=== stderr ===\n" + result.stderr)
    assert result.returncode == PASS, result.stderr
    if expected_ptw is None:
        assert "dadao: ptw va=" not in result.stderr
    else:
        assert re.search(expected_ptw, result.stderr), result.stderr
    print(f"{name}: {result.returncode}")


def main():
    run("registers", gen_register_probe())
    run("ptbr-disabled-identity", gen_disabled_probe())

    for kind in ("super", "normal"):
        for access in ("exec", "read", "write"):
            virtual = (SUPER_VA_BASE + SUPER_OFFSET
                       if kind == "super" else NORMAL_VA_BASE + NORMAL_OFFSET)
            physical = SUPER_PA if kind == "super" else NORMAL_PA
            leaf_addr = (
                SUPER_L1_PA + SUPER_L1_INDEX * 8
                if kind == "super"
                else NORMAL_L2_HIGH_PA + NORMAL_L2_INDEX * 8)
            access_value = {"read": 0, "write": 1, "exec": 2}[access]
            prot_value = {"read": 1, "write": 2, "exec": 4}[access]
            pattern = (
                rf"dadao: ptw va=0x{virtual:016x} "
                rf"leaf_pte_addr=0x{leaf_addr:016x} .*"
                rf"pa=0x{physical:016x} "
                rf"access={access_value} prot=0x{prot_value:x}")
            run(
                f"{kind}-{access}",
                gen_access_probe(kind, access),
                gen_ram_fixture(kind, access),
                pattern)

    print("PASS: registers; PTBR-disabled identity; nonzero L1/L2/SPF/GPF; "
          "superpage X/R/W; normal-page X/R/W; PTHI=2 != PAHI=1")


if __name__ == "__main__":
    main()
