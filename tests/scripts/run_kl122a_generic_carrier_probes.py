#!/usr/bin/env python3
"""KL-122a generic CFX frame/vector carrier probe for QEMU and gem5."""

import os
import struct

import run_kl120a_cfx_carrier_probes as k120
from build_test_binary import load_reg, UNIMP_ENCODING
import gen_min_elf

CFX_PTW = 4
PASS = 46
FAIL = 0x97
TARGET_OFFSET = 0x300


def gen(base):
    out = bytearray()
    load_reg(out, "rd", 30, 0)

    # cfx_ptw had no frame/vector storage before KL-122a.
    k120.add_check(out, CFX_PTW, 5, 0, 2)
    k120.add_check(out, CFX_PTW, 5, 1, 0x0123456789ABCDEF)
    k120.add_check(out, CFX_PTW, 5, 3,
                   0xABCD000000000000 | (base + TARGET_OFFSET),
                   base + TARGET_OFFSET)
    k120.add_check(out, CFX_PTW, 5, 5, k120.CFX_POWER)
    k120.add_check(out, CFX_PTW, 2, 10, 0xFFFF000012345678,
                   0x0000000012345678)

    # Hardware-owned cause fields reset zero and ignore software writes.
    for rc in (2, 4):
        load_reg(out, "rd", 2, 0xFFFFFFFFFFFFFFFF)
        k120.write_crrr(out, k120.OP_CFX2RC, CFX_PTW, 5, rc, 2)
        k120.write_crrr(out, k120.OP_CFX2RD, CFX_PTW, 5, rc, 3)
        k120.write_orrr(out, k120.MISC_ORR, 30, 30, 3)

    load_reg(out, "rd", 26, PASS)
    load_reg(out, "rd", 27, FAIL)
    word = (k120.OP_CSZ << 24) | (30 << 18) | (28 << 12) | \
        (26 << 6) | 27
    out.extend(struct.pack(">I", word))

    # Permit power/hypv -> ptw cross-cfx escape, then prove the generic
    # frame's cause_ip is selected by landing at the target halt.
    load_reg(out, "rd", 2, ~(1 << CFX_PTW) & 0xFFFFFFFFFFFFFFFF)
    k120.write_crrr(
        out, k120.OP_CFX2RC, k120.CFX_POWER, 3, 7, 2)
    k120.write_ciii(out, k120.OP_ESCAPE, CFX_PTW, 0)

    if len(out) > TARGET_OFFSET:
        raise AssertionError("KL-122a probe overlaps target")
    poison = struct.pack(">I", UNIMP_ENCODING)
    while len(out) < TARGET_OFFSET:
        out.extend(poison)
    out.extend(struct.pack(">I", (k120.OP_HALT << 24) | (28 << 18)))
    return bytes(out)


def main():
    k120.EVIDENCE = os.path.join(
        k120.REPO, ".work", "evidence", "kl122a-probes")
    os.makedirs(k120.EVIDENCE, exist_ok=True)

    qemu = k120.run_qemu("generic-carrier", gen(k120.o3.ROM_BASE))
    gem5 = k120.run_gem5("generic-carrier", gen(gen_min_elf.LOAD_ADDR))
    assert qemu.returncode == PASS, qemu.stderr
    assert gem5.returncode == PASS, gem5.stderr
    assert k120.gem5_code(gem5.stdout) == PASS, gem5.stdout
    assert "escape cfx=4" in qemu.stderr
    assert "escape cfx=4" in gem5.stderr
    print("PASS: generic cfx_ptw frame/vector/escape=46/46")


if __name__ == "__main__":
    main()
