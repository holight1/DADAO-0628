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
import run_sail_test as S     # SL-002a: 4th leg, independent Sail spec model

VEC_DIR = os.path.join(REPO, 'tests', 'vectors', 'isa')
# DL-042c: differential over every active vector across all ISA yaml files.
CORE_FILES = [os.path.basename(p)
              for p in sorted(glob.glob(os.path.join(VEC_DIR, '*.yaml')))]


def main():
    qemu_bin = Q.find_qemu()
    gem5_bin = G.find_gem5()
    sail_bin = S.find_sim()
    print("=== run_differential: interpreter vs QEMU vs gem5 vs Sail "
          "(SL-002a 4-way) ===")
    print(f"    qemu = {qemu_bin}")
    print(f"    gem5 = {gem5_bin}")
    print(f"    sail = {sail_bin}")

    # agree3   : interp + QEMU + gem5 all concur with the vector (3-way).
    # agree_gs : interp + QEMU concur; gem5 abstains (SKIP-unsupported).
    agree3 = agree_gs = diverge = harness = qskip = 0
    diverges, harnesses = [], []
    # SL-002a 4th column (Sail). Tracked orthogonally so the existing three-way
    # judgement (agree3/agree_gs/diverge) is byte-for-byte unchanged: Sail only
    # *extends* an already-3-way-agreed case to 4-way, abstains (out-of-slice
    # SKIP), or raises a NEW divergence — it can never flip an existing AGREE.
    agree4 = agree4_sskip = sdiverge = 0
    sdiverges = []

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

            # 4th column: independent Sail spec model (SL-002a). Runs on the
            # same vector; PASS = agrees, SKIP-unsupported = out of the ~6-8
            # instruction rehearsal slice (abstains), FAIL = real 4th divergence.
            sstatus, sdetail = S.run_case(case, sim_bin=sail_bin)
            sail_ran = sstatus in ('PASS', 'FAIL')
            sail_ok = (sstatus == 'PASS')

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
                # Sail extends this already-agreed case to 4-way, or abstains.
                if sail_ran:
                    if sail_ok:
                        agree4 += 1
                    else:
                        sdiverge += 1
                        sdiverges.append(
                            f'{fname} case[{i}] {case["mnemonic"]}: '
                            f'interp={ibucket}; qemu={qstatus}; gem5={gstatus}; '
                            f'sail={sstatus}({sdetail}) | {desc}')
                else:
                    agree4_sskip += 1
            else:
                diverge += 1
                diverges.append(
                    f'{fname} case[{i}] {case["mnemonic"]}: '
                    f'interp={ibucket}({idetail}); qemu={qstatus}({qdetail}); '
                    f'gem5={gstatus}({gdetail}); sail={sstatus}({sdetail}) '
                    f'| {desc}')

    if harnesses:
        print("\n--- HARNESS (single-instr model deliberately abstains) ---")
        for h in harnesses:
            print('  ', h)
    if diverges:
        print("\n--- DIVERGE (interp vs QEMU vs gem5 — architect triages) ---")
        for d in diverges:
            print('  ', d)
    if sdiverges:
        print("\n--- SAIL DIVERGE (4th column disagrees where 3 agreed) ---")
        for d in sdiverges:
            print('  ', d)

    print(f"\n=== AGREE(3-way)={agree3}  AGREE(interp+QEMU, gem5-SKIP)={agree_gs}"
          f"  DIVERGE={diverge}  HARNESS={harness}  QEMU-SKIP={qskip} ===")
    print(f"    gem5 covers {agree3} of the {agree3 + agree_gs} interp+QEMU-agreed "
          f"cases (G1 = 4 instrs; grows with DG-004a).")
    print(f"=== SAIL 4th column: AGREE(4-way)={agree4}  "
          f"Sail-SKIP(out-of-slice)={agree4_sskip}  SAIL-DIVERGE={sdiverge} ===")
    print(f"    Sail covers {agree4} of the {agree3 + agree_gs} agreed cases "
          f"(SL-002a rehearsal slice ~6-8 instrs).")
    if qskip and agree3 == 0 and agree_gs == 0 and diverge == 0:
        print("ERROR: all comparable cases QEMU-skipped (QEMU missing?)",
              file=sys.stderr)
        sys.exit(2)
    sys.exit(1 if (diverge or sdiverge) else 0)


if __name__ == '__main__':
    main()
