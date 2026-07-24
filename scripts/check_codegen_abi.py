#!/usr/bin/env python3
"""check_codegen_abi.py — C3, ADR-0009 CodeGen/ABI verification branch.

Read-only conformance check between the LLVM DADAO backend and the ABI facts
derived in tools/abi.yaml (C2). This script NEVER modifies the backend; it only
parses backend source and reports agreement.

Compared surfaces:
  1. DADAOCallingConv.td   CC_DADAO   -> abi.yaml arguments.integer.registers
                           RetCC_DADAO-> abi.yaml returns.integer.registers
  2. DADAORegisterInfo.cpp getReservedRegs -> abi.yaml reserved set
     DADAORegisterInfo.td  allocatable order (cross-check with reserved)
  3. TargetDataLayout.cpp  case Triple::dadao string -> abi.yaml datalayout

Verdict tokens per finding:
  MATCH        backend agrees with a contract-fixed fact
  MISMATCH     backend contradicts a contract-fixed fact   (=> nonzero exit)
  OPEN-COMMIT  backend made a choice on an [OPEN] fact       (warning only)
  INFO         surface not in scope of the Phase-5 spike (e.g. pointer ABI,
               callee-saved) — reported for visibility, not a failure

Exit code: 1 if any MISMATCH, else 0.
"""

import os
import re
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ABI_YAML = os.path.join(ROOT, "tools", "abi.yaml")

LLVM = os.path.join(ROOT, ".work", "source", "llvm", "llvm")
CC_TD = os.path.join(LLVM, "lib", "Target", "DADAO", "DADAOCallingConv.td")
REG_CPP = os.path.join(LLVM, "lib", "Target", "DADAO", "DADAORegisterInfo.cpp")
REG_TD = os.path.join(LLVM, "lib", "Target", "DADAO", "DADAORegisterInfo.td")
DL_CPP = os.path.join(LLVM, "lib", "TargetParser", "TargetDataLayout.cpp")

# ---------------------------------------------------------------------------
# result accounting
# ---------------------------------------------------------------------------
findings = []  # (level, section, message)


def record(level, section, message):
    findings.append((level, section, message))


def expand_range(spec):
    """'rd32-rd63' -> ['rd32', ..., 'rd63']; a list passes through lowercased."""
    if isinstance(spec, list):
        return [r.lower() for r in spec]
    m = re.fullmatch(r"([a-z]+)(\d+)-[a-z]+(\d+)", spec.strip())
    if not m:
        raise ValueError(f"bad range: {spec!r}")
    pfx, lo, hi = m.group(1), int(m.group(2)), int(m.group(3))
    return [f"{pfx}{i}" for i in range(lo, hi + 1)]


def read(path):
    if not os.path.isfile(path):
        record("MISMATCH", "backend", f"backend file not found: {path}")
        return None
    with open(path) as f:
        return f.read()


# ---------------------------------------------------------------------------
# backend parsers
# ---------------------------------------------------------------------------
def parse_calling_conv(text):
    """Return (int_regs, ptr_regs, ret_int_regs, ret_ptr_regs) as lowercase
    register-name lists (None if the CallingConv def itself is missing).

    DL-069a: CC_DADAO/RetCC_DADAO now carry two independently-counted rule
    families — CCIfPtr<CCAssignToReg<[RB...]>> for pointer args/returns and
    CCIfType<[i64], CCAssignToReg<[RD...]>> for integer args/returns
    (contracts/abi/spec.md §2.1/§3.1). They must be parsed separately: a
    single combined register list (the pre-DL-069a behavior) can no longer
    distinguish "backend agrees with the pointer contract" from "backend
    agrees with the integer contract" now that both rule families coexist
    in the same CallingConv<[...]> body.
    """
    def body_of(defname):
        m = re.search(rf"def\s+{defname}\s*:\s*CallingConv<(.*?)>\s*;",
                      text, re.S)
        return m.group(1) if m else None

    def regs_for(body, pattern):
        if body is None:
            return None
        regs = []
        for block in re.findall(pattern, body, re.S):
            regs += re.findall(r"R[DBF]\d+", block)
        return [r.lower() for r in regs]

    PTR_RULE = r"CCIfPtr<\s*CCAssignToReg<\[(.*?)\]>\s*>"
    INT_RULE = r"CCIfType<\[i64\],\s*CCAssignToReg<\[(.*?)\]>\s*>"

    cc_body = body_of("CC_DADAO")
    retcc_body = body_of("RetCC_DADAO")
    return (regs_for(cc_body, INT_RULE), regs_for(cc_body, PTR_RULE),
            regs_for(retcc_body, INT_RULE), regs_for(retcc_body, PTR_RULE))


def parse_reserved(text):
    """Set of lowercase reg names from Reserved.set(DADAO::RXn) calls."""
    return {r.lower() for r in re.findall(r"Reserved\.set\(DADAO::(R[DBF]\d+)\)", text)}


def parse_allocatable(text, klass):
    """(sequence 'RD%u', lo, hi) inside a RegisterClass def -> lo,hi ints."""
    m = re.search(rf'def\s+{klass}\s*:\s*RegisterClass<.*?sequence\s+"R[DBF]%u",\s*(\d+),\s*(\d+)',
                  text, re.S)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def parse_datalayout(text):
    m = re.search(r"case Triple::dadao:\s*return\s*\"([^\"]+)\"", text)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# checks
# ---------------------------------------------------------------------------
def check_calling_conv(abi):
    text = read(CC_TD)
    if text is None:
        return
    cc, ptr_cc, retcc, ptr_retcc = parse_calling_conv(text)

    # integer parameters
    want = expand_range(abi["arguments"]["integer"]["registers"])
    cite = abi["arguments"]["integer"]["abi_cite"]
    if cc is None:
        record("MISMATCH", "CallingConv", f"CC_DADAO not found (contract {cite})")
    elif cc == want:
        record("MATCH", "CallingConv",
               f"integer params rd16..rd31 [{cite}]")
    else:
        record("MISMATCH", "CallingConv",
               f"integer params: backend={cc} contract={want} [{cite}]")

    # integer return (ML-038a: contract is now a register LIST -- rd31 then
    # rd30 -- to cover the 128-bit-scalar two-register split; expand_range
    # already accepts a plain list here the same way it does for
    # arguments.integer.registers, so no separate wrapping logic is needed)
    rwant = expand_range(abi["returns"]["integer"]["registers"])
    rcite = abi["returns"]["integer"]["abi_cite"]
    if retcc is None:
        record("MISMATCH", "CallingConv", f"RetCC_DADAO not found (contract {rcite})")
    elif retcc == rwant:
        record("MATCH", "CallingConv",
               f"integer return {'/'.join(rwant)} [{rcite}]")
    else:
        record("MISMATCH", "CallingConv",
               f"integer return: backend={retcc} contract={rwant} [{rcite}]")

    # pointer parameters (DL-069a: RB bank, independently counted from RD)
    pwant = expand_range(abi["arguments"]["pointer"]["registers"])
    pcite = abi["arguments"]["pointer"]["abi_cite"]
    if not ptr_cc:
        record("INFO", "CallingConv",
               "pointer params rb16..rb31 not implemented in backend "
               f"(no CCIfPtr rule found); contract defines them [{pcite}]")
    elif ptr_cc == pwant:
        record("MATCH", "CallingConv", f"pointer params rb16..rb31 [{pcite}]")
    else:
        record("MISMATCH", "CallingConv",
               f"pointer params: backend={ptr_cc} contract={pwant} [{pcite}]")

    # pointer return (DL-069a: rb31, independently from the integer rd31 rule)
    prwant = [abi["returns"]["pointer"]["register"].lower()]
    prcite = abi["returns"]["pointer"]["abi_cite"]
    if not ptr_retcc:
        record("INFO", "CallingConv",
               "pointer return rb31 not implemented in backend "
               f"(no CCIfPtr rule found); contract defines it [{prcite}]")
    elif ptr_retcc == prwant:
        record("MATCH", "CallingConv", f"pointer return rb31 [{prcite}]")
    else:
        record("MISMATCH", "CallingConv",
               f"pointer return: backend={ptr_retcc} contract={prwant} [{prcite}]")


def check_reserved(abi):
    text = read(REG_CPP)
    if text is None:
        return
    backend = parse_reserved(text)

    contract_fixed = set()
    contract_open = set()
    for e in abi["reserved"]:
        (contract_fixed if e["status"] == "fixed" else contract_open).add(e["reg"])

    for e in abi["reserved"]:
        reg, status, cite = e["reg"], e["status"], e["abi_cite"]
        in_backend = reg in backend
        if status == "fixed":
            if in_backend:
                record("MATCH", "Reserved", f"{reg} reserved [{cite}]")
            else:
                record("MISMATCH", "Reserved",
                       f"{reg} must be reserved but backend allocates it [{cite}]")
        else:  # open
            if in_backend:
                record("OPEN-COMMIT", "Reserved",
                       f"{reg} is [OPEN] in ABI; backend chose to RESERVE it [{cite}]")
            else:
                record("INFO", "Reserved",
                       f"{reg} is [OPEN] in ABI; backend leaves it allocatable [{cite}]")

    # backend must not reserve anything the contract does not list
    extra = backend - contract_fixed - contract_open
    for reg in sorted(extra):
        record("MISMATCH", "Reserved",
               f"backend reserves {reg} which is not a contract reserved/open register")

    # cross-check: td allocatable order agrees with getReservedRegs
    td = read(REG_TD)
    if td is not None:
        for bank, klass in (("rd", "GPRD_Allocatable"), ("rb", "GPRB_Allocatable")):
            rng = parse_allocatable(td, klass)
            if rng is None:
                record("INFO", "Allocatable", f"{klass} sequence not found")
                continue
            lo, hi = rng
            non_alloc = {f"{bank}{i}" for i in range(0, lo)}
            reserved_in_bank = {r for r in backend if r.startswith(bank)}
            if non_alloc == reserved_in_bank:
                record("MATCH", "Allocatable",
                       f"{klass}=r{lo}..{hi}; non-allocatable {bank}0..{bank}{lo-1} "
                       "agrees with getReservedRegs")
            else:
                record("MISMATCH", "Allocatable",
                       f"{klass}=r{lo}..{hi} implies non-alloc {sorted(non_alloc)} "
                       f"but getReservedRegs has {sorted(reserved_in_bank)}")


def _dl_tokens(s):
    return s.split("-")


def check_datalayout(abi):
    text = read(DL_CPP)
    if text is None:
        return
    backend = parse_datalayout(text)
    dl = abi["datalayout"]
    expected = dl["expected_string"]
    if backend is None:
        record("MISMATCH", "DataLayout",
               f"case Triple::dadao string not found (contract {dl['expected_string_cite']})")
        return

    bt, et = _dl_tokens(backend), _dl_tokens(expected)
    record("INFO", "DataLayout", f"backend string  = {backend}")
    record("INFO", "DataLayout", f"contract string = {expected} [{dl['expected_string_cite']}]")

    # endianness
    be = bt[0] if bt else ""
    if be == dl["endianness"]:
        record("MATCH", "DataLayout", f"endianness {be} (big-endian) [{dl['endianness_cite']}]")
    else:
        record("MISMATCH", "DataLayout",
               f"endianness: backend={be} contract={dl['endianness']} [{dl['endianness_cite']}]")

    # int64 width/alignment
    if dl["int64"] in bt:
        record("MATCH", "DataLayout", f"{dl['int64']} (LP64) [{dl['int64_cite']}]")
    else:
        record("MISMATCH", "DataLayout",
               f"{dl['int64']} missing; backend has {[t for t in bt if t.startswith('i')]} "
               f"[{dl['int64_cite']}]")

    # native width
    if dl["native"] in bt:
        record("MATCH", "DataLayout", f"{dl['native']} native width [{dl['native_cite']}]")
    else:
        record("MISMATCH", "DataLayout",
               f"{dl['native']} missing; backend has {[t for t in bt if t.startswith('n')]} "
               f"[{dl['native_cite']}]")

    # stack alignment — the flagged S128 vs 8-byte check
    backend_S = next((t for t in bt if t.startswith("S")), None)
    want_S = f"S{dl['stack_alignment_bits']}"
    if backend_S == want_S:
        record("MATCH", "DataLayout",
               f"stack alignment {backend_S} = {dl['stack_alignment_bytes']}B "
               f"[{dl['stack_alignment_cite']}]")
    else:
        b_bits = backend_S[1:] if backend_S else "(absent)"
        b_bytes = (int(b_bits) // 8) if backend_S and b_bits.isdigit() else "?"
        record("MISMATCH", "DataLayout",
               f"STACK ALIGNMENT CONFLICT: backend {backend_S or '(absent)'} "
               f"(= {b_bytes}B) vs ABI {want_S} (= {dl['stack_alignment_bytes']}B, "
               f"'{dl['stack_alignment_cite']}'). The backend mandates a STRICTER "
               f"stack alignment than the ABI requires.")


# ---------------------------------------------------------------------------
def main():
    with open(ABI_YAML) as f:
        abi = yaml.safe_load(f)

    check_calling_conv(abi)
    check_reserved(abi)
    check_datalayout(abi)

    order = {"MATCH": 0, "OPEN-COMMIT": 1, "INFO": 2, "MISMATCH": 3}
    counts = {k: 0 for k in order}

    print("=" * 72)
    print("CodeGen/ABI conformance (C3) — backend vs tools/abi.yaml")
    print("=" * 72)
    for level in ("MISMATCH", "OPEN-COMMIT", "MATCH", "INFO"):
        for lv, section, msg in findings:
            if lv == level:
                counts[lv] += 1
                print(f"[{lv:<11}] {section:<12} {msg}")

    print("-" * 72)
    print(f"MATCH={counts['MATCH']}  OPEN-COMMIT={counts['OPEN-COMMIT']}  "
          f"INFO={counts['INFO']}  MISMATCH={counts['MISMATCH']}")

    if counts["MISMATCH"]:
        print("RESULT: FAIL (backend diverges from ABI contract on fixed fact(s))")
        sys.exit(1)
    print("RESULT: PASS (no MISMATCH; OPEN-COMMIT/INFO are advisory)")
    sys.exit(0)


if __name__ == "__main__":
    main()
