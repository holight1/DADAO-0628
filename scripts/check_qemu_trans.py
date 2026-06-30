#!/usr/bin/env python3
"""Check that every M1 opcode in tools/opcodes.yaml has a trans_ function
in .work/qemu/target/dadao/translate.c.

The expected trans function name is derived from the naming convention
observed in the existing translate.c.
"""

import sys
import os
import re
import yaml

OPCODES_PATH = "tools/opcodes.yaml"
TRANSLATE_PATH = ".work/qemu/target/dadao/translate.c"

# MISC-Norm (op=0x10) mapping by ha nybble
_MISC_HA = {
    0x00: "swym",
    0x08: "and_log",
    0x09: "orr",
    0x0A: "xor_bit",
    0x0B: "xnor",
    0x11: "shlu_r",
    0x12: "shrs_r",
    0x13: "shru_r",
    0x14: "exts_r",
    0x15: "extz_r",
    0x19: "shlu_i",
    0x1A: "shrs_i",
    0x1B: "shru_i",
    0x1C: "exts_i",
    0x1D: "extz_i",
    0x24: "cmps_r",
    0x25: "cmpu_r",
    0x28: "rd2rd",
    0x29: "rd2rb",
    0x2A: "rb2rd",
    0x2B: "rb2rb",
    0x2D: "cmp_rb",
    0x2E: "add_rb",
    0x2F: "sub_rb",
    0x3F: "unimp",
}

# RB-bank instructions identified by opcode
_RB_BANK = {
    0x43: "ldo_rb",
    0x47: "ldmo_rb",
    0x49: "addi_rb",
    0x4B: "sto_rb",
    0x4C: "orw_rb",
    0x4D: "andnw_rb",
    0x4E: "setzw_rb",
    0x4F: "stmo_rb",
}

# cmps/cmpu MISC-Norm register form (orrr, op=0x10) handled by _MISC_HA above;
# immediate form uses _i suffix and a separate opcode.
_CMP_IMM = {
    0x12: "cmps_i",
    0x13: "cmpu_i",
}

# jump/call disambiguated by format
_CTL_FORMAT = {
    ("jump", "iiii"): "jump_i",
    ("jump", "rrii"): "jump_r",
    ("call", "iiii"): "call_i",
    ("call", "rrii"): "call_r",
}


def make_trans_name(entry):
    mnemonic = entry["mnemonic"]
    opcode = entry["op"]
    fmt = entry["format"]

    # MISC-Norm by ha nybble
    if opcode == 0x10:
        ha = entry.get("ha")
        if ha is not None and ha in _MISC_HA:
            return "trans_" + _MISC_HA[ha]

    # RB bank by opcode
    if opcode in _RB_BANK:
        return "trans_" + _RB_BANK[opcode]

    # cmps/cmpu immediate form by opcode
    if opcode in _CMP_IMM:
        return "trans_" + _CMP_IMM[opcode]

    # jump/call by format
    key = (mnemonic, fmt)
    if key in _CTL_FORMAT:
        return "trans_" + _CTL_FORMAT[key]

    # Default: trans_<mnemonic>
    return "trans_" + mnemonic


def load_opcodes(path):
    with open(path) as f:
        return yaml.safe_load(f)


def load_trans_functions(path):
    funcs = set()
    pat_fn = re.compile(r'^static bool\s+(trans_\w+)\s*\(')
    pat_macro = re.compile(r'GEN_ILLEGAL_INSN\((\w+)\)')
    with open(path) as f:
        for line in f:
            m = pat_fn.match(line)
            if m:
                funcs.add(m.group(1))
                continue
            m = pat_macro.search(line)
            if m:
                funcs.add("trans_" + m.group(1))
    return funcs


def main():
    if not os.path.exists(TRANSLATE_PATH):
        print(f"ERROR: {TRANSLATE_PATH} not found")
        sys.exit(1)

    opcodes = load_opcodes(OPCODES_PATH)
    trans_funcs = load_trans_functions(TRANSLATE_PATH)

    missing = []
    for op in opcodes:
        expected = make_trans_name(op)
        if expected not in trans_funcs:
            mnemonic = op["mnemonic"]
            fmt = op["format"]
            missing.append((mnemonic, fmt, expected))

    print(f"Opcodes checked: {len(opcodes)}")
    print(f"Trans functions in translate.c: {len(trans_funcs)}")

    if missing:
        print(f"\nMissing trans functions ({len(missing)}):")
        for mnem, fmt, name in missing:
            print(f"  {mnem} ({fmt}) → expected {name}")
        print("\nTRANS COVERAGE: FAIL")
        sys.exit(1)

    print("TRANS COVERAGE: PASS")


if __name__ == "__main__":
    main()
