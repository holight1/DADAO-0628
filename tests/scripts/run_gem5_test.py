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
from build_test_binary import load_reg, build_branch_test_binary  # noqa: E402
import gen_min_elf                                 # noqa: E402

DEFAULT_GEM5 = os.path.join(GEM5_DIR, 'build', 'DADAO', 'gem5.opt')
DEFAULT_CONFIG = os.path.join(GEM5_TESTS, 'dadao_se.py')

MASK48 = (1 << 48) - 1
MASK64 = (1 << 64) - 1

# DG-004b memory window. Must match arch/dadao/decoder.cc (MEM_WINDOW_BASE /
# MEM_WINDOW_SIZE). A fixed RW data segment covering [BASE, BASE+SIZE) is mapped
# into every test ELF so loads/stores have valid pages; at halt gem5 dumps this
# window (DADAO_MEMDUMP) for expected_state.memory comparison. All memory test
# vectors cluster at 0x87FF0000, well inside the window.
MEM_WINDOW_BASE = 0x87FEF000
MEM_WINDOW_SIZE = 0x3000

# DG-004c fault SE exit codes — must match arch/dadao/faults.hh and the QEMU
# harness FAULT_CODES (run_qemu_test.py). ILLI=illegal operand of a known
# instruction, MALIGN=misaligned access, UNDI=reserved encoding.
FAULT_CODES = {'ILLI': 0x82, 'MALIGN': 0x81, 'UNDI': 0x83, 'RASOF': 0x84, 'RASUF': 0x85}
# Private sentinel gem5 exits with for opcodes it has not implemented yet
# (control flow beyond jump-iiii, register-bank block-copy semantics) → SKIP.
UNIMPL_CODE = 0x7F


def find_gem5():
    for p in [os.environ.get('GEM5_OPT'), DEFAULT_GEM5]:
        if p and os.path.isfile(p):
            return p
    return None


def build_gem5_binary(case):
    """Build a flat DADAO binary that sets up the vector's rd/rb inputs, runs the
    instruction under test, and halts (dumping final register + memory state).
    Returns (code_bytes, window_bytes) or None when outside gem5's current
    coverage (caller reports SKIP-unsupported): branch harness or fault-expecting
    vectors (no fault model yet, DG-004c).

    rd/rb inputs are loaded with setzw/orw (build_test_binary.load_reg), which
    gem5 implements for both banks (setzw-rb/orw-rb added in DG-004b). Initial
    memory (input_state.memory) is placed directly in a fixed RW data segment
    (the memory window) initialised big-endian, so it is mapped and readable by
    loads and writable by stores. expected_state.memory is checked by reading the
    window back from gem5's DADAO_MEMDUMP.

    expected_fault vectors (DG-004c) are also built and run: gem5 raises the
    fault, exits with the fault's SE code, and _run_one compares it to
    FAULT_CODES. Whether the instruction under test is actually implemented is
    decided at run time: an unimplemented opcode exits with the UNIMPL sentinel
    (or leaves no regdump) and the caller SKIPs.

    branch_behavior vectors (DG-004d) use the same branch-over-poison layout as
    the QEMU harness (build_branch_test_binary): correct branch/jump/call/ret →
    exit 0; wrong direction → poison → ILLI. _run_one scores these by exit code.
    The 6 HARNESS control-flow abstains (jump/call/ret with rb0=0 / cold-RAS,
    whose vector ILLI is a trampoline artifact the single-instruction model
    cannot reproduce) are SKIPped here."""
    if case.get('branch_behavior'):
        return build_branch_test_binary(case), bytes(MEM_WINDOW_SIZE)

    # Structural abstain: jump/call/ret 'ILLI' vectors are harness artifacts
    # (jump to addr 0 → trampoline halt → ILLI), not single-instruction faults;
    # gem5 relative-jumps / RASUFs instead. Keep the 6 HARNESS cases SKIP.
    if case.get('mnemonic') in ('jump', 'call', 'ret') \
            and case.get('expected_fault') is not None:
        return None

    inp = case.get('input_state') or {}

    # Initial memory window (big-endian), mapped RW into the ELF.
    window = bytearray(MEM_WINDOW_SIZE)
    for entry in inp.get('memory') or []:
        addr = int(entry['address'], 16)
        width = int(entry.get('width', 8))
        val = int(entry['value'], 16) if isinstance(entry['value'], str) \
            else int(entry['value'])
        off = addr - MEM_WINDOW_BASE
        if off < 0 or off + width > MEM_WINDOW_SIZE:
            return None                               # memory outside window
        for i in range(width):
            window[off + i] = (val >> (8 * (width - 1 - i))) & 0xFF

    word = int(case['encoding']['word'], 16)
    out = bytearray()
    for name in sorted(inp.get('rb', {})):
        n = int(name.replace('rb', ''))
        load_reg(out, 'rb', n, int(inp['rb'][name], 16) & MASK64)
    for name in sorted(inp.get('rd', {})):
        n = int(name.replace('rd', ''))
        load_reg(out, 'rd', n, int(inp['rd'][name], 16) & MASK64)
    out.extend(struct.pack('>I', word))               # instruction under test
    out.extend(struct.pack('>I', 0x00 << 24))         # halt rd0 -> exit 0 + dump
    return bytes(out), bytes(window)


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


def parse_memdump(text):
    """Parse the DADAO_MEMDUMP line into (base, bytearray) or None."""
    for line in text.splitlines():
        if line.startswith('DADAO_MEMDUMP'):
            base = size = None
            data_hex = ''
            for tok in line.split()[1:]:
                key, _, val = tok.partition('=')
                if key == 'base':
                    base = int(val, 16)
                elif key == 'size':
                    size = int(val, 16)
                elif key == 'data':
                    data_hex = val
            if base is None:
                return None
            return base, bytes.fromhex(data_hex)
    return None


def parse_exit_code(text):
    """Extract the SE exit code from dadao_se.py's 'SIM_END: <cause> code=<n>'
    line (decimal). Returns int or None."""
    for line in text.splitlines():
        if line.startswith('SIM_END:'):
            for tok in line.split():
                if tok.startswith('code='):
                    try:
                        return int(tok[len('code='):])
                    except ValueError:
                        return None
    return None


def _compare(dump, expected_state, memdump=None):
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
    # Memory: read expected bytes back (big-endian §2.1) from the dumped window.
    for entry in expected_state.get('memory') or []:
        addr = int(entry['address'], 16)
        width = int(entry.get('width', 8))
        want = (int(entry['value'], 16) if isinstance(entry['value'], str)
                else int(entry['value'])) & ((1 << (width * 8)) - 1)
        if memdump is None:
            diffs.append(f'mem@0x{addr:X} missing memdump')
            continue
        base, data = memdump
        off = addr - base
        if off < 0 or off + width > len(data):
            diffs.append(f'mem@0x{addr:X} outside dump window')
            continue
        got = 0
        for i in range(width):
            got = (got << 8) | data[off + i]
        if got != want:
            diffs.append(f'mem@0x{addr:X}=0x{got:0{width*2}X} '
                         f'want 0x{want:0{width*2}X}')
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

    built = build_gem5_binary(case)
    if built is None:
        mn = case.get('mnemonic', '?')
        return ('SKIP-unsupported', f'{mn}: not in gem5 G1 coverage')
    binary, window = built

    elf = gen_min_elf.build_elf(
        binary, data_segs=[(MEM_WINDOW_BASE, window)])
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
    exit_code = parse_exit_code(out)
    mn = case.get('mnemonic', '?')
    expected_fault = case.get('expected_fault')

    # Branch-over-poison vectors: correctness is carried by the exit code
    # (0 = branch reached the PASS path; ILLI = poison hit = wrong direction).
    if case.get('branch_behavior'):
        if exit_code == 0:
            return ('PASS', f'{case["branch_behavior"]} exit=0')
        if exit_code == UNIMPL_CODE:
            return ('SKIP-unsupported', f'{mn}: unimplemented opcode')
        got = 'none' if exit_code is None else f'0x{exit_code:02X}'
        return ('FAIL', f'{case["branch_behavior"]}: poison/wrong path exit={got}')

    if dump is None:
        # No halt/regdump -> the instruction faulted or is unimplemented.
        if exit_code == UNIMPL_CODE:
            return ('SKIP-unsupported', f'{mn}: unimplemented opcode')
        if expected_fault is not None:
            want = FAULT_CODES.get(expected_fault)
            if want is None:
                return ('FAIL', f'unknown fault type {expected_fault}')
            if exit_code == want:
                return ('PASS', f'{expected_fault} (0x{exit_code:02X})')
            got = 'none' if exit_code is None else f'0x{exit_code:02X}'
            return ('FAIL', f'expected {expected_fault}=0x{want:02X}, got {got}')
        # non-fault vector with no state readout -> uncovered (unknown inst)
        return ('SKIP-unsupported',
                f'{mn}: no halt/regdump (runtime unknown inst)')

    # Reached halt (normal exit, regdump present).
    if expected_fault is not None:
        return ('FAIL', f'expected {expected_fault}, got no fault (halted)')
    memdump = parse_memdump(out)

    exp = case.get('expected_state')
    if not exp:                                       # encoding-only / no state
        return ('PASS', 'ran, no-state')
    diffs = _compare(dump, exp, memdump)
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
