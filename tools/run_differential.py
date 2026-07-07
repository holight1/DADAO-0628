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

CORE_FILES = ['rd-arith.yaml', 'rd-load-store.yaml', 'control-flow.yaml']
VEC_DIR = os.path.join(REPO, 'tests', 'vectors', 'isa')


def main():
    qemu_bin = Q.find_qemu()
    print("=== run_differential: interpreter vs QEMU (DL-042a core slice) ===")
    print(f"    qemu = {qemu_bin}")

    agree = diverge = harness = qskip = 0
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

            interp_ok = (ibucket == 'PASS')
            qemu_ok = (qstatus == 'PASS')
            if interp_ok and qemu_ok:
                agree += 1
            else:
                diverge += 1
                diverges.append(
                    f'{fname} case[{i}] {case["mnemonic"]}: '
                    f'interp={ibucket}({idetail}); qemu={qstatus}({qdetail}) | {desc}')

    if harnesses:
        print("\n--- HARNESS (single-instr model deliberately abstains) ---")
        for h in harnesses:
            print('  ', h)
    if diverges:
        print("\n--- DIVERGE (interp vs QEMU — findings, architect triages) ---")
        for d in diverges:
            print('  ', d)

    print(f"\n=== AGREE={agree} DIVERGE={diverge} "
          f"HARNESS={harness} QEMU-SKIP={qskip} ===")
    if qskip and agree == 0 and diverge == 0:
        print("ERROR: all comparable cases QEMU-skipped (QEMU missing?)",
              file=sys.stderr)
        sys.exit(2)
    sys.exit(1 if diverge else 0)


if __name__ == '__main__':
    main()
