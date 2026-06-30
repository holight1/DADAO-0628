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
    os.path.dirname(os.path.dirname(os.path.dirname(HERE))),
    '.work', 'source', 'qemu', 'build', 'qemu-system-dadao',
)
ALT_QEMU = os.path.expanduser(
    '~/toolchain/DADAO/__install/bin/qemu-system-dadao'
)


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
    if exit_code == 0:
        return ('PASS', 'exit=0')
    elif exit_code == 130:
        return ('FAIL', f'exit={exit_code} (ILLI/EXCP)')
    return ('FAIL', f'exit={exit_code}')


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('case', help='YAML file or YAML string')
    parser.add_argument('--qemu', help='QEMU binary path')
    parser.add_argument('--trampoline', default=DEFAULT_TRAMPOLINE)
    args = parser.parse_args()
    qemu_bin = args.qemu or find_qemu()
    if os.path.isfile(args.case):
        with open(args.case) as f:
            cases = yaml.safe_load(f)
        for case in cases:
            status, detail = _run_one(case, args.trampoline, qemu_bin)
            desc = case.get('notes', case.get('mnemonic', 'unknown'))
            print(f'{status:8s} {detail:30s} {desc}')
    else:
        case = yaml.safe_load(args.case)
        if isinstance(case, list):
            case = case[0]
        status, detail = _run_one(case, args.trampoline, qemu_bin)
        print(f'{status:8s} {detail}')


if __name__ == '__main__':
    main()
