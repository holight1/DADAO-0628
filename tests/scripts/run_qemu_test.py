#!/usr/bin/env python3
"""Run a single YAML test case through QEMU and report pass/fail."""

import sys
import os
from pathlib import Path
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
FAULT_CODES = {'ILLI': 0x82, 'MALIGN': 0x81, 'UNDI': 0x83, 'RASOF': 0x84, 'RASUF': 0x85}


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
        if not isinstance(cases, list) or not cases:
            raise ValueError(f'{case}: expected a non-empty YAML list')
        return _run_one(cases[0], trampoline_path, qemu_bin)
    return _run_one(case, trampoline_path, qemu_bin)


def _run_one(case, trampoline_path, qemu_bin):
    try:
        binary = build_test_binary(case)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f'invalid vector input: {exc}') from exc
    if qemu_bin is None:
        qemu_bin = find_qemu()
    if qemu_bin is None:
        return ('SKIP', 'no qemu binary found')
    if trampoline_path is None:
        trampoline_path = DEFAULT_TRAMPOLINE
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


def _load_yaml_file(path):
    try:
        with path.open(encoding='utf-8') as f:
            cases = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f'{path}: cannot read YAML: {exc}') from exc
    if not isinstance(cases, list):
        raise ValueError(f'{path}: expected a YAML list of test cases')
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f'{path}[{index}]: expected a mapping')
    return cases


def _collect_cases(argument):
    path = Path(argument)
    if path.is_file():
        return [(path, _load_yaml_file(path))], False
    if path.is_dir():
        paths = sorted(
            p for p in path.rglob('*')
            if p.is_file() and p.suffix.lower() in {'.yaml', '.yml'}
        )
        if not paths:
            raise ValueError(f'{path}: no YAML files found')
        return [(p, _load_yaml_file(p)) for p in paths], True

    try:
        parsed = yaml.safe_load(argument)
    except yaml.YAMLError as exc:
        raise ValueError(f'input is neither a file/directory nor valid YAML: {exc}') from exc
    if isinstance(parsed, list):
        cases = parsed
    elif isinstance(parsed, dict):
        cases = [parsed]
    else:
        raise ValueError('input is neither a file/directory nor a YAML test case')
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f'YAML case[{index}]: expected a mapping')
    return [(None, cases)], False


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('case', help='YAML file or YAML string')
    parser.add_argument('--qemu', help='QEMU binary path')
    parser.add_argument('--trampoline', default=DEFAULT_TRAMPOLINE)
    args = parser.parse_args()
    try:
        sources, is_directory = _collect_cases(args.case)
    except ValueError as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(2)

    qemu_bin = args.qemu or find_qemu()
    active = deferred = passed = failed = skipped = input_errors = 0
    for path, cases in sources:
        label = path.name if path is not None else None
        for index, case in enumerate(cases):
            if case.get('status') == 'deferred':
                deferred += 1
                continue
            active += 1
            try:
                status, detail = _run_one(case, args.trampoline, qemu_bin)
            except (KeyError, TypeError, ValueError) as exc:
                status, detail = 'ERROR', f'input error: {exc}'
            desc = case.get('notes', case.get('mnemonic', f'case[{index}]'))
            if is_directory:
                desc = f'{path.relative_to(Path(args.case))}: {desc}'
            if label is None:
                print(f'{status:8s} {detail}')
            else:
                print(f'{status:8s} {detail:30s} {desc}')
            if status == 'PASS':
                passed += 1
            elif status == 'FAIL':
                failed += 1
            elif status == 'SKIP':
                skipped += 1
            else:
                input_errors += 1

    print(
        f'SUMMARY active={active} deferred={deferred} pass={passed} '
        f'fail={failed} skip={skipped} input_errors={input_errors}'
    )
    if active == 0:
        print('ERROR: 0 active cases executed', file=sys.stderr)
        sys.exit(2)
    if input_errors:
        sys.exit(2)
    if skipped == active:
        print(f'ERROR: all {active} active cases skipped (QEMU missing?)', file=sys.stderr)
        sys.exit(2)
    if failed:
        sys.exit(1)


if __name__ == '__main__':
    main()
