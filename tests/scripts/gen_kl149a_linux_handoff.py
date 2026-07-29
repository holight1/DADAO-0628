#!/usr/bin/env python3
"""Generate the KL-149a HBI hypv-to-supervisor Linux reset trampoline."""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

from build_test_binary import UNIMP_ENCODING, load_reg
from gen_kl110a_o1_probe import (
    CFX_DELEG_TARGETS,
    CFX_POWER,
    OP_CFX2RC,
    OP_ESCAPE,
    write_ciii,
    write_crrr,
)


KERNEL_ENTRY = 0x80000000


def generate(previous_mode: int = 2) -> bytes:
    if previous_mode not in (0, 1, 2, 3):
        raise ValueError("previous_mode must fit the architectural two bits")
    out = bytearray()

    # HBI section 3: clear the hypv delegation registers before entering
    # supervisor mode.  hmon/cg3 is intentionally excluded by the contract.
    load_reg(out, "rd", 2, 0)
    for _name, cfxcode in CFX_DELEG_TARGETS:
        write_crrr(out, OP_CFX2RC, cfxcode, 3, 12, 2)

    # Restore supervisor mode with all CFX accesses masked, at the raw Image
    # entry loaded by the dadao-m1 -kernel contract.
    load_reg(out, "rd", 2, previous_mode)
    write_crrr(out, OP_CFX2RC, CFX_POWER, 5, 0, 2)
    load_reg(out, "rd", 2, 0xFFFFFFFFFFFFFFFF)
    write_crrr(out, OP_CFX2RC, CFX_POWER, 5, 1, 2)
    load_reg(out, "rd", 2, KERNEL_ENTRY)
    write_crrr(out, OP_CFX2RC, CFX_POWER, 5, 3, 2)
    write_ciii(out, OP_ESCAPE, CFX_POWER, 0)

    # Any fall-through means escape did not perform the architectural return.
    out.extend(struct.pack(">I", UNIMP_ENCODING))
    return bytes(out)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        default=Path("kl149a-linux-handoff.bin"),
    )
    parser.add_argument(
        "--previous-mode",
        type=int,
        choices=range(4),
        default=2,
        help="mode restored by escape; 2 is the HBI supervisor contract",
    )
    args = parser.parse_args()
    output = args.output
    payload = generate(args.previous_mode)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    print(
        f"wrote={output} size={len(payload)} "
        f"previous_mode={args.previous_mode} entry=0x{KERNEL_ENTRY:016x}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
