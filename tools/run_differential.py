#!/usr/bin/env python3
"""run_differential.py — differential harness: Python golden model vs QEMU.

For every in-scope core-slice vector, run BOTH:
  * interpreter (tools/dadao_interp.py, spec-derived) — compared to vector
  * QEMU (via tests/scripts/run_qemu_test.py, self-checking harness) — vs vector
and report AGREE / DIVERGE per the ADR-0009 M2a three-way (interp / QEMU / hand
vector). Because the QEMU harness self-checks against the vector's
expected_state (XOR guard + fault assertion), "QEMU PASS" == "QEMU matches the
vector"; likewise "interp PASS" == "interp matches the vector".

  AGREE    interp and QEMU both concur with the vector (three-way consistent)
  DIVERGE  they disagree with the vector differently → interp bug OR QEMU bug
           OR vector/spec issue (architect triages the three)
  HARNESS  vector encodes a harness-only outcome the single-instruction model
           deliberately does not reproduce (listed, not a real divergence)
  QEMU-SKIP QEMU binary unavailable for that case

QEMU granularity is pass/fail (harness self-check), not a register dump; the
interpreter side supplies the concrete computed value on any divergence.
Exit 0 iff zero DIVERGE.
"""

import os
import sys
import glob
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, 'tests', 'scripts'))

import validate_interp as V
import run_qemu_test as Q
import run_gem5_test as G

VEC_DIR = os.path.join(REPO, 'tests', 'vectors', 'isa')
# DL-042c: differential over every active vector across all ISA yaml files.
CORE_FILES = [os.path.basename(p)
              for p in sorted(glob.glob(os.path.join(VEC_DIR, '*.yaml')))]


def main():
    qemu_bin = Q.find_qemu()
    gem5_bin = G.find_gem5()
    print("=== run_differential: interpreter vs QEMU vs gem5 (DG-003a 3-way) ===")
    print(f"    qemu = {qemu_bin}")
    print(f"    gem5 = {gem5_bin}")

    # agree3   : interp + QEMU + gem5 all concur with the vector (3-way).
    # agree_gs : interp + QEMU concur; gem5 abstains (SKIP-unsupported).
    agree3 = agree_gs = diverge = harness = qskip = 0
    diverges, harnesses = [], []

    for fname in CORE_FILES:
        path = os.path.join(VEC_DIR, fname)
        with open(path) as fh:
            cases = yaml.safe_load(fh)
        for i, case in enumerate(cases):
            if case.get('status') == 'deferred':
                continue
            ibucket, idetail = V._eval_case(case)
            desc = case.get('notes', case.get('mnemonic'))

            if ibucket == 'SKIP-harness':
                harness += 1
                qstatus, qdetail = Q.run_case(case, qemu_bin=qemu_bin)
                harnesses.append(f'{fname} case[{i}] {case["mnemonic"]}: '
                                 f'interp={idetail}; qemu={qstatus}/{qdetail} | {desc}')
                continue
            if ibucket == 'SKIP-unsupported':
                continue

            qstatus, qdetail = Q.run_case(case, qemu_bin=qemu_bin)
            if qstatus == 'SKIP':
                qskip += 1
                continue

            gstatus, gdetail = G.run_case(case, gem5_bin=gem5_bin)
            gem5_ran = gstatus in ('PASS', 'FAIL')

            interp_ok = (ibucket == 'PASS')
            qemu_ok = (qstatus == 'PASS')
            gem5_ok = (gstatus == 'PASS')

            if interp_ok and qemu_ok and (not gem5_ran or gem5_ok):
                # interp + QEMU agree with the vector; gem5 either also agrees
                # (3-way) or abstains (SKIP-unsupported, coverage grows w/ G2).
                if gem5_ran:
                    agree3 += 1
                else:
                    agree_gs += 1
            else:
                diverge += 1
                diverges.append(
                    f'{fname} case[{i}] {case["mnemonic"]}: '
                    f'interp={ibucket}({idetail}); qemu={qstatus}({qdetail}); '
                    f'gem5={gstatus}({gdetail}) | {desc}')

    if harnesses:
        print("\n--- HARNESS (single-instr model deliberately abstains) ---")
        for h in harnesses:
            print('  ', h)
    if diverges:
        print("\n--- DIVERGE (interp vs QEMU vs gem5 — architect triages) ---")
        for d in diverges:
            print('  ', d)

    print(f"\n=== AGREE(3-way)={agree3}  AGREE(interp+QEMU, gem5-SKIP)={agree_gs}"
          f"  DIVERGE={diverge}  HARNESS={harness}  QEMU-SKIP={qskip} ===")
    print(f"    gem5 covers {agree3} of the {agree3 + agree_gs} interp+QEMU-agreed "
          f"cases (G1 = 4 instrs; grows with DG-004a).")
    if qskip and agree3 == 0 and agree_gs == 0 and diverge == 0:
        print("ERROR: all comparable cases QEMU-skipped (QEMU missing?)",
              file=sys.stderr)
        sys.exit(2)
    sys.exit(1 if diverge else 0)


if __name__ == '__main__':
    main()
