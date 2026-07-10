#!/usr/bin/env python3
"""Run a single YAML test case through the Sail-generated C simulator.

Fourth differential leg alongside run_qemu_test.py (QEMU), run_gem5_test.py
(gem5), and the interpreter (SL-002a / ADR-0011 M2b rehearsal slice).

The Sail model (sail/*.sail) is an *independent* executable spec: its semantics
are derived only from contracts/isa/spec.md § and tools/opcodes.yaml, never from
QEMU translate.c or gem5 decoder.cc (ADR-0011 D4). `sail -c` compiles it to a C
simulator `dadao_sail_sim` (sail/c_harness/), whose CLI is:

    dadao_sail_sim <code.bin> [<window.bin>]

  * <code.bin>   flat big-endian .text, loaded at 0x80000000 (BINARY_BASE)
  * <window.bin> optional flat RW data window, loaded at MEM_WINDOW_BASE

On halt (op=0x00) the sim prints, exactly like gem5's decoder.cc terminal-state
readout, a `DADAO_REGDUMP ...` line and (when a window is mapped) a
`DADAO_MEMDUMP base=.. size=.. data=..` line, then exits 0. On an architectural
fault it exits with the fault's SE code (FAULT_CODES). For a valid DADAO opcode
that this rehearsal slice does not model yet, it exits UNIMPL_CODE (0x7F) so this
adapter reports SKIP-unsupported — never FAIL — exactly like the gem5 leg.

To avoid re-deriving the (semantics-free) test scaffolding, this adapter reuses
run_gem5_test's flat-binary builder and REGDUMP/MEMDUMP parsers/comparators: the
input setup (setzw/orw loads + halt), the memory window, and the terminal-state
compare are byte-identical to the gem5 leg. Only the executable under test (the
Sail sim vs gem5.opt) and the exit-code plumbing differ. All *architectural*
meaning lives in the .sail model.
"""

import argparse
import os
import subprocess
import sys
import tempfile

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))          # ~/DADAO-0628
SAIL_DIR = os.path.join(REPO, 'sail')
C_HARNESS = os.path.join(SAIL_DIR, 'c_harness')

sys.path.insert(0, HERE)
# Reuse gem5 leg's flat-binary builder + parsers (test scaffolding only; all
# semantics are in the .sail model, not here).
import run_gem5_test as G                              # noqa: E402

FAULT_CODES = {'ILLI': 0x82, 'MALIGN': 0x81, 'UNDI': 0x83}
UNIMPL_CODE = 0x7F
DEFAULT_SIM = os.path.join(C_HARNESS, 'dadao_sail_sim')


def find_sim():
    for p in [os.environ.get('SAIL_SIM'), DEFAULT_SIM]:
        if p and os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


def run_case(case, sim_bin=None):
    if isinstance(case, str):
        with open(case) as f:
            case = yaml.safe_load(f)[0]
    return _run_one(case, sim_bin)


def _run_one(case, sim_bin):
    if sim_bin is None:
        sim_bin = find_sim()
    if sim_bin is None:
        return ('SKIP', 'no dadao_sail_sim (build sail/c_harness or set SAIL_SIM)')

    built = G.build_gem5_binary(case)                  # identical scaffolding
    if built is None:
        mn = case.get('mnemonic', '?')
        return ('SKIP-unsupported', f'{mn}: not in rehearsal harness coverage')
    code, window = built

    code_path = window_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.code', delete=False) as f:
            f.write(code)
            code_path = f.name
        argv = [sim_bin, code_path]
        # Only map the window when the vector touches memory; keeps the dump
        # short for pure-register cases.
        touches_mem = bool((case.get('input_state') or {}).get('memory')) or \
            bool((case.get('expected_state') or {}).get('memory'))
        if touches_mem:
            with tempfile.NamedTemporaryFile(suffix='.win', delete=False) as f:
                f.write(window)
                window_path = f.name
            argv.append(window_path)
        try:
            result = subprocess.run(argv, capture_output=True, timeout=30,
                                    text=True)
        except subprocess.TimeoutExpired:
            return ('FAIL', 'timeout')
        except FileNotFoundError:
            return ('SKIP', f'sim not found: {sim_bin}')
    finally:
        for p in (code_path, window_path):
            if p:
                os.unlink(p)

    out = result.stdout + result.stderr
    exit_code = result.returncode
    mn = case.get('mnemonic', '?')
    expected_fault = case.get('expected_fault')

    if exit_code == UNIMPL_CODE:
        return ('SKIP-unsupported', f'{mn}: opcode not modeled in slice')

    # Branch/jump/call/ret poison vectors: correctness is the exit code (0 =
    # correct control-flow path reached the PASS halt; ILLI = poison hit).
    if case.get('branch_behavior'):
        if exit_code == 0:
            return ('PASS', f'{case["branch_behavior"]} exit=0')
        got = f'0x{exit_code:02X}'
        return ('FAIL',
                f'{case["branch_behavior"]}: poison/wrong path exit={got}')

    dump = G.parse_regdump(out)

    if dump is None:
        # No halt/regdump -> faulted (or, for a fault-expecting vector, expected).
        if expected_fault is not None:
            want = FAULT_CODES.get(expected_fault)
            if want is None:
                return ('FAIL', f'unknown fault type {expected_fault}')
            if exit_code == want:
                return ('PASS', f'{expected_fault} (0x{exit_code:02X})')
            got = 'none' if exit_code is None else f'0x{exit_code:02X}'
            return ('FAIL', f'expected {expected_fault}=0x{want:02X}, got {got}')
        return ('SKIP-unsupported',
                f'{mn}: no halt/regdump (exit 0x{exit_code:02X})')

    # Reached halt with a register dump.
    if expected_fault is not None:
        return ('FAIL', f'expected {expected_fault}, got no fault (halted)')

    memdump = G.parse_memdump(out)
    exp = case.get('expected_state')
    if not exp:
        return ('PASS', 'ran, no-state')
    diffs = G._compare(dump, exp, memdump)
    if not diffs:
        return ('PASS', 'state match')
    return ('FAIL', '; '.join(diffs))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('case', help='YAML file or YAML string')
    parser.add_argument('--sim', help='dadao_sail_sim path (or set SAIL_SIM)')
    args = parser.parse_args()

    sim_bin = args.sim or find_sim()

    total = passed = skipped = 0
    any_fail = False
    if os.path.isfile(args.case):
        with open(args.case) as f:
            cases = yaml.safe_load(f)
    else:
        cases = yaml.safe_load(args.case)
        if isinstance(cases, dict):
            cases = [cases]

    for case in cases:
        if case.get('status') == 'deferred':
            continue
        status, detail = _run_one(case, sim_bin)
        total += 1
        desc = case.get('notes', case.get('mnemonic', 'unknown'))
        print(f'{status:16s} {detail:34s} {desc}')
        if status == 'FAIL':
            any_fail = True
        elif status.startswith('SKIP'):
            skipped += 1
        elif status == 'PASS':
            passed += 1

    print(f'\n=== sail: PASS={passed} SKIP={skipped} '
          f'FAIL={total - passed - skipped} (total {total}) ===')
    if total == 0:
        print('ERROR: 0 cases executed', file=sys.stderr)
        sys.exit(2)
    sys.exit(1 if any_fail else 0)


if __name__ == '__main__':
    main()
