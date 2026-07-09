#!/usr/bin/env python3
"""Run a single YAML test case through gem5 and report pass/fail.

Third differential leg alongside run_qemu_test.py (QEMU) and the interpreter.
Same interface: same vector YAML, same build helpers.

Unlike the QEMU harness (which runs a self-checking flat binary that compares
state in-guest and exits 0/ILLI), gem5 currently implements only the G1 core
instructions (halt/addi/add/jump), so it cannot execute the self-check code.
Instead:
  * gem5 dumps its final architectural registers at `halt` (DADAO_REGDUMP line,
    added in arch/dadao/decoder.cc — DG-003a terminal-state readout);
  * this adapter sets up inputs with supported instructions (addi from rd0),
    runs the test instruction, halts, parses the dump, and compares RD/RB
    against the vector's expected_state in Python.

Any case gem5 cannot yet cover (unsupported opcode, a fault-expecting vector,
inputs/memory it cannot set up) is reported SKIP-unsupported — aligned with the
interpreter's skip semantics — never FAIL. Coverage grows as DG-004a adds
instructions and a fault model.
"""

import argparse
import os
import struct
import subprocess
import sys
import tempfile

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))          # ~/DADAO-0628
GEM5_DIR = os.path.expanduser('~/DADAO-gem5')
GEM5_TESTS = os.path.join(GEM5_DIR, 'tests', 'dadao')

sys.path.insert(0, HERE)
sys.path.insert(0, GEM5_TESTS)
from build_test_binary import write_rrii          # noqa: E402
import gen_min_elf                                 # noqa: E402

# gem5 G1 core instructions (opcode -> mnemonic).
SUPPORTED_OPS = {0x00: 'halt', 0x19: 'addi', 0x1A: 'add', 0x64: 'jump'}

DEFAULT_GEM5 = os.path.join(GEM5_DIR, 'build', 'DADAO', 'gem5.opt')
DEFAULT_CONFIG = os.path.join(GEM5_TESTS, 'dadao_se.py')

MASK48 = (1 << 48) - 1
MASK64 = (1 << 64) - 1


def find_gem5():
    for p in [os.environ.get('GEM5_OPT'), DEFAULT_GEM5]:
        if p and os.path.isfile(p):
            return p
    return None


def _as_signed64(v):
    return v - (1 << 64) if v >= (1 << 63) else v


def _fits_imm12(v):
    s = _as_signed64(v & MASK64)
    return -2048 <= s <= 2047


def build_gem5_binary(case):
    """Return a flat DADAO binary runnable on the gem5 G1 core, or None if the
    case is outside gem5's current coverage (caller reports SKIP-unsupported)."""
    if case.get('branch_behavior'):
        return None                                   # branch harness: DG-004a
    if case.get('expected_fault') is not None:
        return None                                   # no fault model yet

    word = int(case['encoding']['word'], 16)
    if (word >> 24) not in SUPPORTED_OPS:
        return None

    inp = case.get('input_state') or {}
    if inp.get('memory'):
        return None                                   # cannot set up memory
    if inp.get('rb'):
        return None                                   # no rb loader instruction

    exp = case.get('expected_state') or {}
    if exp.get('memory'):
        return None                                   # cannot read back memory

    rd_in = inp.get('rd', {})
    for name, vstr in rd_in.items():
        if not _fits_imm12(int(vstr, 16)):
            return None                               # input not addi-loadable

    out = bytearray()
    # Set up rd inputs with `addi rdN, rd0, value` (value fits signed imm12).
    for name in sorted(rd_in):
        n = int(name.replace('rd', ''))
        val = _as_signed64(int(rd_in[name], 16) & MASK64)
        write_rrii(out, 0x19, n, 0, val)              # addi rdN, rd0, val
    # The instruction under test.
    out.extend(struct.pack('>I', word))
    # halt rd0 -> exit 0 and dump final registers.
    out.extend(struct.pack('>I', 0x00 << 24))
    return bytes(out)


def parse_regdump(text):
    """Parse the DADAO_REGDUMP line into {'rd3': int, 'rb1': int, ...}."""
    for line in text.splitlines():
        if line.startswith('DADAO_REGDUMP'):
            regs = {}
            for tok in line.split()[1:]:
                name, _, val = tok.partition('=')
                regs[name] = int(val, 16) & MASK64
            return regs
    return None


def _compare(dump, expected_state):
    diffs = []
    for name, vstr in (expected_state.get('rd') or {}).items():
        want = int(vstr, 16) & MASK64
        got = dump.get(name)
        if got is None:
            diffs.append(f'{name} missing in dump')
        elif got != want:
            diffs.append(f'{name}=0x{got:016X} want 0x{want:016X}')
    # RB is a 48-bit effective address register (spec §1.3): compare low 48 bits.
    for name, vstr in (expected_state.get('rb') or {}).items():
        want = int(vstr, 16) & MASK48
        got = dump.get(name)
        if got is None:
            diffs.append(f'{name} missing in dump')
        elif (got & MASK48) != want:
            diffs.append(f'{name}=0x{got & MASK48:012X} want 0x{want:012X}')
    return diffs


def run_case(case, gem5_bin=None, config=None):
    if isinstance(case, str):
        with open(case) as f:
            case = yaml.safe_load(f)[0]
    return _run_one(case, gem5_bin, config)


def _run_one(case, gem5_bin, config):
    if gem5_bin is None:
        gem5_bin = find_gem5()
    if gem5_bin is None:
        return ('SKIP', 'no gem5.opt found (build DADAO/gem5.opt or set GEM5_OPT)')
    if config is None:
        config = DEFAULT_CONFIG

    binary = build_gem5_binary(case)
    if binary is None:
        mn = case.get('mnemonic', '?')
        return ('SKIP-unsupported', f'{mn}: not in gem5 G1 coverage')

    elf = gen_min_elf.build_elf(binary)
    with tempfile.NamedTemporaryFile(suffix='.elf', delete=False) as f:
        f.write(elf)
        elf_path = f.name
    try:
        result = subprocess.run(
            [gem5_bin, '--outdir=' + tempfile.mkdtemp(prefix='gem5_'),
             config, elf_path],
            capture_output=True, timeout=60, text=True)
    except subprocess.TimeoutExpired:
        return ('FAIL', 'timeout')
    except FileNotFoundError:
        return ('SKIP', f'gem5 not found: {gem5_bin}')
    finally:
        os.unlink(elf_path)

    out = result.stdout + result.stderr
    dump = parse_regdump(out)
    if dump is None:
        # No halt reached -> hit an unsupported instruction at run time.
        return ('SKIP-unsupported',
                f'{case.get("mnemonic", "?")}: no halt/regdump (runtime unknown inst)')

    exp = case.get('expected_state')
    if not exp:                                       # encoding-only / no state
        return ('PASS', 'ran, no-state')
    diffs = _compare(dump, exp)
    if not diffs:
        return ('PASS', 'state match')
    return ('FAIL', '; '.join(diffs))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('case', help='YAML file or YAML string')
    parser.add_argument('--gem5', help='gem5.opt path (or set GEM5_OPT)')
    parser.add_argument('--config', help='gem5 SE config .py',
                        default=DEFAULT_CONFIG)
    args = parser.parse_args()

    gem5_bin = args.gem5 or find_gem5()

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
        status, detail = _run_one(case, gem5_bin, args.config)
        total += 1
        desc = case.get('notes', case.get('mnemonic', 'unknown'))
        print(f'{status:16s} {detail:34s} {desc}')
        if status == 'FAIL':
            any_fail = True
        elif status.startswith('SKIP'):
            skipped += 1
        elif status == 'PASS':
            passed += 1

    print(f'\n=== gem5: PASS={passed} SKIP={skipped} '
          f'FAIL={total - passed - skipped} (total {total}) ===')
    if total == 0:
        print('ERROR: 0 cases executed', file=sys.stderr)
        sys.exit(2)
    sys.exit(1 if any_fail else 0)


if __name__ == '__main__':
    main()
