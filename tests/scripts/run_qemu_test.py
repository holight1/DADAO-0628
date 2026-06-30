#!/usr/bin/env python3
"""Run a single YAML test case through QEMU and report pass/fail."""

import sys
import os
import subprocess
import tempfile
import yaml

sys.path.insert(0, os.path.dirname(__file__))
from build_test_binary import build_test_binary

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TRAMPOLINE = os.path.join(HERE, 'trampoline.bin')
DEFAULT_QEMU = os.path.join(
    os.path.dirname(os.path.dirname(HERE)),
    '.work', 'source', 'qemu', 'build', 'qemu-system-dadao',
)
ALT_QEMU = os.path.expanduser(
    '~/toolchain/DADAO/__install/bin/qemu-system-dadao'
)


FAULT_CODES = {'ILLI': 0x82, 'MALIGN': 0x81, 'UNDI': 0x83}


def find_qemu():
    for p in [DEFAULT_QEMU, ALT_QEMU]:
        if os.path.isfile(p):
            return p
    for p in ['qemu-system-dadao']:
        try:
            subprocess.run([p, '--version'], capture_output=True, timeout=5)
            return p
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return None


def _classify(exit_code, case):
    """Classify test result based on exit code and expected properties."""
    expected_fault = case.get('expected_fault')
    if expected_fault is None:
        if exit_code == 0:
            return ('PASS', 'exit=0')
        if exit_code == 1:
            return ('FAIL', 'state mismatch')
        return ('FAIL', f'unexpected exit=0x{exit_code:02X}')
    else:
        expected_code = FAULT_CODES.get(expected_fault)
        if expected_code is None:
            return ('FAIL', f'unknown fault: {expected_fault}')
        if exit_code == expected_code:
            return ('PASS', f'{expected_fault} (expected)')
        if exit_code == 0:
            return ('FAIL', f'expected {expected_fault}, got exit=0 (no fault)')
        return ('FAIL',
                f'expected {expected_fault} exit=0x{expected_code:02X}, '
                f'got 0x{exit_code:02X}')


def run_case(case, trampoline_path=None, qemu_bin=None):
    if isinstance(case, str):
        with open(case) as f:
            cases = yaml.safe_load(f)
        return _run_one(cases[0], trampoline_path, qemu_bin)
    return _run_one(case, trampoline_path, qemu_bin)


def _run_one(case, trampoline_path, qemu_bin):
    if qemu_bin is None:
        qemu_bin = find_qemu()
    if qemu_bin is None:
        return ('SKIP', 'no qemu binary found')
    if trampoline_path is None:
        trampoline_path = DEFAULT_TRAMPOLINE
    binary = build_test_binary(case)
    with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as f:
        f.write(binary)
        test_path = f.name
    try:
        result = subprocess.run(
            [qemu_bin, '-M', 'dadao-m1', '-nographic',
             '-bios', trampoline_path, '-kernel', test_path],
            capture_output=True, timeout=5)
        exit_code = result.returncode
    except subprocess.TimeoutExpired:
        return ('FAIL', 'timeout')
    except FileNotFoundError:
        return ('SKIP', f'qemu not found: {qemu_bin}')
    finally:
        os.unlink(test_path)
    return _classify(exit_code, case)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('case', help='YAML file or YAML string')
    parser.add_argument('--qemu', help='QEMU binary path')
    parser.add_argument('--trampoline', default=DEFAULT_TRAMPOLINE)
    args = parser.parse_args()
    qemu_bin = args.qemu or find_qemu()
    any_fail = False
    total = 0
    skip_count = 0
    if os.path.isfile(args.case):
        with open(args.case) as f:
            cases = yaml.safe_load(f)
        for case in cases:
            if case.get('status') == 'deferred':
                continue
            status, detail = _run_one(case, args.trampoline, qemu_bin)
            total += 1
            desc = case.get('notes', case.get('mnemonic', 'unknown'))
            print(f'{status:8s} {detail:30s} {desc}')
            if status == 'FAIL':
                any_fail = True
            elif status == 'SKIP':
                skip_count += 1
    else:
        case = yaml.safe_load(args.case)
        if isinstance(case, list):
            case = case[0]
        status, detail = _run_one(case, args.trampoline, qemu_bin)
        total += 1
        print(f'{status:8s} {detail}')
        if status == 'FAIL':
            any_fail = True
        elif status == 'SKIP':
            skip_count += 1
    if total == 0:
        print('ERROR: 0 cases executed', file=sys.stderr)
        sys.exit(2)
    if skip_count == total:
        print(f'ERROR: all {total} cases skipped (QEMU missing?)', file=sys.stderr)
        sys.exit(2)
    if any_fail:
        sys.exit(1)


if __name__ == '__main__':
    main()
