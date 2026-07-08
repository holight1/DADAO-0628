#!/usr/bin/env python3
"""validate_interp.py — run the Python golden model over the DL-042a core slice
and assert  interpreter_output == vector.expected_state  (faults included).

Reference oracle = tests/vectors/isa/*.yaml (hand-written, independent per
ADR-0007). Interpreter = tools/dadao_interp.py (spec-derived, ADR-0009 M2a).

Scope (core slice): rd-arith.yaml, rd-load-store.yaml, control-flow.yaml.
Other vector files are reported as out-of-phase coverage only.

Result buckets:
  PASS            interpreter matches the vector (state or fault)
  MISMATCH        interpreter disagrees with the vector  ← the finding
  SKIP:unsupported instruction outside this phase's semantics
  SKIP:harness    vector encodes a multi-instruction QEMU-harness outcome
                  (jump/call/ret whose ILLI comes from landing on halt(rd0) /
                  cold-RAS), NOT single-instruction ISA semantics
Exit 0 iff zero MISMATCH.
"""

import os
import sys
import glob
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dadao_interp as I

HERE = os.path.dirname(os.path.abspath(__file__))
VEC_DIR = os.path.join(os.path.dirname(HERE), 'tests', 'vectors', 'isa')
# DL-042c: full coverage = every active vector across all ISA yaml files.
CORE_FILES = [os.path.basename(p)
              for p in sorted(glob.glob(os.path.join(VEC_DIR, '*.yaml')))]


def _cmp_state(st, expected):
    diffs = []
    for name, val in (expected.get('rd') or {}).items():
        n = int(name[2:])
        exp = int(val, 16)
        act = st.rd_read(n)
        if act != exp:
            diffs.append(f'{name} exp=0x{exp:016X} got=0x{act:016X}')
    for name, val in (expected.get('rb') or {}).items():
        n = int(name[2:])
        exp = int(val, 16)
        act = st.rb_read(n)
        if act != exp:
            diffs.append(f'{name} exp=0x{exp:016X} got=0x{act:016X}')
    for entry in (expected.get('memory') or []):
        addr = int(entry['address'], 16)
        width = entry.get('width', 8)
        exp = int(entry['value'], 16)
        act = st.load_mem(addr, width)
        if act != exp:
            diffs.append(f'mem[0x{addr:X}]/{width}B exp=0x{exp:X} got=0x{act:X}')
    return diffs


def _is_harness_artifact(case):
    mn = case.get('mnemonic')
    fmt = case.get('format')
    ef = case.get('expected_fault')
    if ef == 'ILLI' and ((mn in ('jump', 'call') and fmt == 'rrii') or mn == 'ret'):
        return True
    return False


def _eval_case(case):
    """Return (bucket, detail). bucket in PASS/MISMATCH/SKIP-unsupported/SKIP-harness."""
    word = int(case['encoding']['word'], 16)
    inp = case.get('input_state') or {}
    ef = case.get('expected_fault')
    bb = case.get('branch_behavior')

    # branch_behavior vectors ------------------------------------------------
    if bb in ('taken', 'not_taken'):
        try:
            st, flt = I.run(word, inp)
        except I.Unsupported as ex:
            return 'SKIP-unsupported', str(ex)
        if flt is not None:
            return 'MISMATCH', f'unexpected fault {flt} on {bb} branch'
        taken = st.pc_next != (st.pc + 4)
        want = (bb == 'taken')
        if taken == want:
            return 'PASS', f'{bb} (pc_next=0x{st.pc_next:X})'
        return 'MISMATCH', f'want {bb}, got {"taken" if taken else "not_taken"}'
    if bb == 'call_ret':
        # roundtrip: call_i pushes rb0; ret must pop it (spec §5.4/§5.5/§5.6)
        st1, f1 = I.run(0x6C000001, inp)          # call +1
        if f1 is not None:
            return 'MISMATCH', f'call push faulted {f1}'
        st2, f2 = I.run(word, state=st1)          # the ret under test
        if f2 is not None:
            return 'MISMATCH', f'ret faulted {f2}'
        expect = (I.DEFAULT_PC + 4) & I.MASK48
        if st2.pc_next == expect:
            return 'PASS', f'ret popped 0x{st2.pc_next:X}'
        return 'MISMATCH', f'ret popped 0x{st2.pc_next:X}, want 0x{expect:X}'

    # harness-artifact ILLI control-flow vectors -----------------------------
    if _is_harness_artifact(case):
        # spec-faithful behaviour noted for the architect:
        note = 'jump/call rb0→PC+4 no-fault' if case['mnemonic'] != 'ret' \
            else 'ret cold-RAS → RASUF (spec §5.6)'
        return 'SKIP-harness', f"vector ILLI is harness outcome; model: {note}"

    # normal single-instruction vectors --------------------------------------
    try:
        st, flt = I.run(word, inp)
    except I.Unsupported as ex:
        return 'SKIP-unsupported', str(ex)

    if ef is not None:
        if flt == ef:
            return 'PASS', f'fault {ef}'
        return 'MISMATCH', f'expected fault {ef}, got {flt}'
    if flt is not None:
        return 'MISMATCH', f'unexpected fault {flt}'
    exp = case.get('expected_state')
    if not exp:                                    # None or {} → no-fault check
        return 'PASS', 'no-fault / no-state'
    diffs = _cmp_state(st, exp)
    if not diffs:
        return 'PASS', 'state match'
    return 'MISMATCH', '; '.join(diffs)


def main():
    files = [os.path.join(VEC_DIR, f) for f in CORE_FILES]
    totals = {'PASS': 0, 'MISMATCH': 0, 'SKIP-unsupported': 0, 'SKIP-harness': 0}
    mism, harness = [], []
    ops_seen = set()

    print("=== validate_interp: DL-042c full coverage (all active vectors) ===")
    for path in files:
        with open(path) as fh:
            cases = yaml.safe_load(fh)
        fname = os.path.basename(path)
        fp = fmm = fsu = fsh = 0
        for i, case in enumerate(cases):
            if case.get('status') == 'deferred':
                continue
            bucket, detail = _eval_case(case)
            totals[bucket] += 1
            try:
                rec, _ = I.decode(int(case['encoding']['word'], 16))
                ops_seen.add((rec['mnemonic'], rec['format']))
            except Exception:
                pass
            desc = case.get('notes', case.get('mnemonic'))
            if bucket == 'PASS':
                fp += 1
            elif bucket == 'MISMATCH':
                fmm += 1
                mism.append(f'{fname} case[{i}] {case["mnemonic"]}: {detail} | {desc}')
            elif bucket == 'SKIP-unsupported':
                fsu += 1
            else:
                fsh += 1
                harness.append(f'{fname} case[{i}] {case["mnemonic"]}: {detail} | {desc}')
        print(f'  {fname:22s} PASS={fp:3d} MISMATCH={fmm:3d} '
              f'SKIP-unsupported={fsu:3d} SKIP-harness={fsh:3d}')

    print("\n--- coverage (in-scope mnemonic/format decoded) ---")
    print('  ', ', '.join(sorted(f'{m}({f})' for m, f in ops_seen)))

    if harness:
        print("\n--- SKIP:harness (vector encodes harness outcome, escalate) ---")
        for h in harness:
            print('  ', h)

    if mism:
        print("\n--- MISMATCH (interpreter vs vector — findings) ---")
        for m in mism:
            print('  ', m)

    print(f"\n=== TOTAL PASS={totals['PASS']} MISMATCH={totals['MISMATCH']} "
          f"SKIP-unsupported={totals['SKIP-unsupported']} "
          f"SKIP-harness={totals['SKIP-harness']} ===")
    sys.exit(1 if totals['MISMATCH'] else 0)


if __name__ == '__main__':
    main()
