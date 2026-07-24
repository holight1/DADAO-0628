#!/usr/bin/env python3
"""ML-026a: batch scan runner for the gcc-c-torture execute/ corpus.

Pure scan/classify tool -- does NOT fix anything, does NOT touch any
backend/musl/LLVM/QEMU/gem5 source. For every .c file under the corpus
directory it does, using this project's real clang->ld.lld->QEMU pipeline
(the exact same command-line shape as tests/lit/E2E/musl_printf_int.test /
musl_malloc_printf.test, with the CFLAGS llvm-test-suite's own
gcc-c-torture/execute/CMakeLists.txt uses to keep old-style K&R C accepted
as warnings instead of hard errors -- see that CMakeLists' top-of-file
comment "GCC C Torture Suite is conventionally run without warnings"):

  1. compile (clang --target=dadao, hosted mode, musl include paths)
  2. link (ld.lld -T tests/scripts/dadao.ld against crt1.o + libc.a)
  3. objcopy -O binary
  4. run under QEMU (dadao-m1, -nographic -bios trampoline -kernel <bin>)

gcc-c-torture's own success/failure convention (NOT this project's other
E2E tests' "specific exit code" convention) is used to judge PASS/FAIL:
main()/exit(0) => process exit 0 (musl's __libc_start_main does
`exit(main(...))`); a failing internal check calls abort(), which on this
project's musl/QEMU port empirically and deterministically bottoms out at
process exit 127 (musl's abort() tries SYS_rt_sigaction / SYS_tkill /
SYS_rt_sigprocmask, all unimplemented on this QEMU model -ENOSYS, then
a_crash() writes to NULL, then raises SIGKILL (also ENOSYS) and finally
calls _Exit(127) -- verified directly with minimal exit(0)/abort() probes
during ML-026a triage, see the task's completion notes). Any other exit
code (the DADAO fault codes 0x81-0x85 -- MALIGN/ILLI/UNDI/RASOF/RASUF -- or
anything unexpected) is recorded verbatim, not squashed into one bucket.

Usage:
  # full sweep (writes JSON results, prints a live summary line per file)
  python3 tests/scripts/gcc_torture_sweep.py --workers 8 --out results.json

  # re-run only the files that came back TIMEOUT, with a longer timeout,
  # to separate "genuinely hung" from "just slow" (task requirement)
  python3 tests/scripts/gcc_torture_sweep.py --retest-timeouts results.json \\
      --run-timeout 60 --out results-retest.json

  # gem5 cross-check pass over every FAIL_RUN entry in an existing results
  # file (ADR-0012 D2: QEMU is the main driver, gem5 only buys its way in
  # for entries that look like real defects)
  python3 tests/scripts/gcc_torture_sweep.py --gem5-crosscheck results.json \\
      --out results-gem5.json

  # render a results JSON into the markdown report
  python3 tests/scripts/gcc_torture_sweep.py --report results.json \\
      --report-out docs/reviews/ML-026a-gcc-c-torture-sweep-2026-07-23.md
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_CORPUS = (
    REPO_ROOT / '.work/source/llvm-test-suite/SingleSource/Regression/C/'
    'gcc-c-torture/execute'
)
CLANG = REPO_ROOT / '.work/build/llvm/bin/clang'
LLD = REPO_ROOT / '.work/build/llvm/bin/ld.lld'
OBJCOPY = REPO_ROOT / '.work/build/llvm/bin/llvm-objcopy'
QEMU = REPO_ROOT / '.work/source/qemu/build/qemu-system-dadao'
TRAMPOLINE = REPO_ROOT / 'tests/scripts/trampoline.bin'
DADAO_LD = REPO_ROOT / 'tests/scripts/dadao.ld'
MUSL_SRC = REPO_ROOT / '.work/source/musl'
MUSL_BUILD = REPO_ROOT / '.work/build/musl'
MUSL_CRT1 = MUSL_BUILD / 'lib/crt1.o'
MUSL_LIBC = MUSL_BUILD / 'lib/libc.a'

GEM5 = Path(os.environ.get('GEM5_OPT', str(Path.home() / 'DADAO-gem5/build/DADAO/gem5.opt')))
GEM5_SE = Path(os.environ.get(
    'GEM5_SE', str(Path.home() / 'DADAO-gem5/tests/dadao/dadao_se.py')))

WORKDIR = REPO_ROOT / '.work/gcc-torture-sweep'

# CFLAGS matching llvm-test-suite's own gcc-c-torture/execute/CMakeLists.txt
# base CFLAGS ("GCC C Torture Suite is conventionally run without
# warnings"), plus this project's standard hosted/musl-include recipe
# (tests/lit/E2E/musl_printf_int.test etc.). Deliberately uniform across all
# 1708 files -- no per-file special CFLAGS (that would be a workaround, out
# of scope for a pure scan task; upstream's own per-file extras -fwrapv /
# -lm / -Wno-return-type are intentionally NOT reproduced here, see report).
#
# ML-034a: -ffreestanding deliberately removed (hosted mode). The project
# now has a real, statically-linked musl providing _start/__libc_start_main
# (ML-007a..012a), so clang's hosted-mode assumptions (C11 implicit
# `return 0` from a falling-off-the-end main(), recognizing standard
# library builtins) are both correct and desired -- freestanding's
# rejection of the implicit-return-0 special case was silently turning
# ~12-15 logically-correct torture-suite files into false FAIL_RUN
# (ML-026a report, "method notes" section). -nostdinc is independent of
# hosted/freestanding (it only affects header search path defaults) and is
# kept unchanged.
CFLAGS = [
    '--target=dadao', '-nostdinc',
    '-Wno-implicit-int', '-Wno-int-conversion',
    '-Wno-implicit-function-declaration', '-w',
    '-I', str(MUSL_SRC / 'arch/dadao'),
    '-I', str(MUSL_SRC / 'arch/generic'),
    '-I', str(MUSL_SRC / 'include'),
    '-I', str(MUSL_BUILD / 'obj/include'),
]

# DADAO hardware fault exit codes (tests/scripts/run_qemu_test.py FAULT_CODES).
HW_FAULT_CODES = {0x81: 'MALIGN', 0x82: 'ILLI', 0x83: 'UNDI', 0x84: 'RASOF', 0x85: 'RASUF'}

COMPILE_TIMEOUT_DEFAULT = 60
LINK_TIMEOUT_DEFAULT = 30
RUN_TIMEOUT_DEFAULT = 8


def discover_corpus(root):
    return sorted(p for p in Path(root).rglob('*.c') if p.is_file())


def _flatten(relpath):
    return str(relpath).replace('/', '__')


def _run(cmd, timeout, cwd=None, stdin_devnull=False):
    kwargs = dict(capture_output=True, timeout=timeout, cwd=cwd)
    if stdin_devnull:
        kwargs['stdin'] = subprocess.DEVNULL
    try:
        p = subprocess.run(cmd, **kwargs)
        return p.returncode, p.stdout, p.stderr, False
    except subprocess.TimeoutExpired as exc:
        return None, exc.stdout or b'', exc.stderr or b'', True
    except FileNotFoundError as exc:
        return None, b'', str(exc).encode(), False


def process_one(relpath, corpus_root, run_timeout, compile_timeout, link_timeout):
    src = Path(corpus_root) / relpath
    tag = _flatten(relpath)
    tmp = WORKDIR / tag
    tmp.mkdir(parents=True, exist_ok=True)
    obj = tmp / 'a.o'
    elf = tmp / 'a.elf'
    binf = tmp / 'a.bin'
    result = {'file': str(relpath)}

    cmd = [str(CLANG)] + CFLAGS + ['-c', '-o', str(obj), str(src)]
    t0 = time.time()
    rc, out, err, timed_out = _run(cmd, compile_timeout)
    result['compile_elapsed'] = round(time.time() - t0, 3)
    if timed_out:
        result['status'] = 'TIMEOUT_COMPILE'
        result['stage'] = 'compile'
        return result
    if rc != 0:
        result['status'] = 'FAIL_COMPILE'
        result['stage'] = 'compile'
        result['returncode'] = rc
        result['stderr'] = err.decode('utf-8', 'replace')[-6000:]
        return result

    cmd = [str(LLD), '-T', str(DADAO_LD), '--start-group',
           str(MUSL_CRT1), str(obj), str(MUSL_LIBC), '--end-group',
           '-o', str(elf)]
    t0 = time.time()
    rc, out, err, timed_out = _run(cmd, link_timeout)
    result['link_elapsed'] = round(time.time() - t0, 3)
    if timed_out:
        result['status'] = 'TIMEOUT_LINK'
        result['stage'] = 'link'
        return result
    if rc != 0:
        result['status'] = 'FAIL_LINK'
        result['stage'] = 'link'
        result['returncode'] = rc
        result['stderr'] = err.decode('utf-8', 'replace')[-6000:]
        return result

    rc, out, err, timed_out = _run(
        [str(OBJCOPY), '-O', 'binary', str(elf), str(binf)], 30)
    if rc != 0:
        result['status'] = 'FAIL_LINK'
        result['stage'] = 'objcopy'
        result['returncode'] = rc
        result['stderr'] = err.decode('utf-8', 'replace')[-2000:]
        return result

    cmd = [str(QEMU), '-M', 'dadao-m1', '-nographic',
           '-bios', str(TRAMPOLINE), '-kernel', str(binf)]
    t0 = time.time()
    rc, out, err, timed_out = _run(cmd, run_timeout, stdin_devnull=True)
    result['run_elapsed'] = round(time.time() - t0, 3)
    if timed_out:
        result['status'] = 'TIMEOUT'
        result['stage'] = 'run'
        return result
    result['exit_code'] = rc
    result['elf_path'] = str(elf)
    if rc == 0:
        result['status'] = 'PASS'
    elif rc == 127:
        result['status'] = 'FAIL_RUN'
        result['subcat'] = 'abort_127'
    elif rc in HW_FAULT_CODES:
        result['status'] = 'FAIL_RUN'
        result['subcat'] = f'hw_exception_{HW_FAULT_CODES[rc]}_0x{rc:02x}'
    else:
        result['status'] = 'FAIL_RUN'
        result['subcat'] = f'unexpected_exit_{rc}'
    result['stage'] = 'run'
    tail = (out or b'') + (err or b'')
    result['run_output_tail'] = tail.decode('utf-8', 'replace')[-500:]
    return result


def gem5_crosscheck(elf_path, timeout=30):
    cmd = [str(GEM5), str(GEM5_SE), str(elf_path)]
    rc, out, err, timed_out = _run(cmd, timeout)
    if timed_out:
        return {'gem5_status': 'TIMEOUT'}
    tail = (out or b'') + (err or b'')
    return {
        'gem5_exit_code': rc,
        'gem5_status': 'PASS' if rc == 0 else 'FAIL',
        'gem5_output_tail': tail.decode('utf-8', 'replace')[-500:],
    }


def sweep(args):
    corpus_root = Path(args.corpus).resolve()
    files = discover_corpus(corpus_root)
    if args.limit:
        files = files[:args.limit]
    if args.filter:
        pat = re.compile(args.filter)
        files = [f for f in files if pat.search(str(f))]
    rel = [f.relative_to(corpus_root) for f in files]
    print(f'# {len(rel)} files to scan (corpus={corpus_root})', file=sys.stderr)

    for p in (CLANG, LLD, OBJCOPY, QEMU, TRAMPOLINE, DADAO_LD, MUSL_CRT1, MUSL_LIBC):
        if not p.exists():
            print(f'FATAL: required tool/artifact missing: {p}', file=sys.stderr)
            sys.exit(2)

    WORKDIR.mkdir(parents=True, exist_ok=True)
    results = []
    done = 0
    t_start = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {
            ex.submit(process_one, r, corpus_root, args.run_timeout,
                      args.compile_timeout, args.link_timeout): r
            for r in rel
        }
        for fut in as_completed(futs):
            r = fut.result()
            results.append(r)
            done += 1
            if done % 50 == 0 or done == len(rel):
                elapsed = time.time() - t_start
                print(f'  [{done}/{len(rel)}] elapsed={elapsed:.0f}s '
                      f'last={r["file"]} status={r["status"]}', file=sys.stderr)

    results.sort(key=lambda r: r['file'])
    out_path = Path(args.out)
    out_path.write_text(json.dumps(results, indent=1))
    print(f'wrote {out_path} ({len(results)} entries)', file=sys.stderr)
    _print_summary(results)


def _print_summary(results):
    from collections import Counter
    c = Counter(r['status'] for r in results)
    total = len(results)
    print('--- summary ---', file=sys.stderr)
    for k in sorted(c):
        print(f'{k:20s} {c[k]:5d}', file=sys.stderr)
    print(f'{"TOTAL":20s} {total:5d}', file=sys.stderr)


def retest_timeouts(args):
    data = json.loads(Path(args.retest_timeouts).read_text())
    corpus_root = Path(args.corpus).resolve()
    timeouts = [r for r in data if r['status'] in ('TIMEOUT', 'TIMEOUT_COMPILE', 'TIMEOUT_LINK')]
    print(f'# retesting {len(timeouts)} TIMEOUT entries with run_timeout={args.run_timeout}s',
          file=sys.stderr)
    updated = {r['file']: r for r in data}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {
            ex.submit(process_one, Path(r['file']), corpus_root, args.run_timeout,
                      args.compile_timeout, args.link_timeout): r['file']
            for r in timeouts
        }
        for fut in as_completed(futs):
            newr = fut.result()
            newr['retested'] = True
            updated[newr['file']] = newr
            print(f'  retest {newr["file"]}: {newr["status"]}', file=sys.stderr)
    out = sorted(updated.values(), key=lambda r: r['file'])
    Path(args.out).write_text(json.dumps(out, indent=1))
    print(f'wrote {args.out}', file=sys.stderr)
    _print_summary(out)


def run_gem5_crosscheck(args):
    data = json.loads(Path(args.gem5_crosscheck).read_text())
    targets = [r for r in data if r.get('status') == 'FAIL_RUN' and r.get('elf_path')]
    print(f'# gem5 cross-checking {len(targets)} FAIL_RUN entries', file=sys.stderr)
    for r in targets:
        gr = gem5_crosscheck(r['elf_path'], timeout=args.gem5_timeout)
        r.update(gr)
        print(f'  {r["file"]}: qemu_exit={r.get("exit_code")} '
              f'gem5={gr.get("gem5_status")}/{gr.get("gem5_exit_code")}', file=sys.stderr)
    Path(args.out).write_text(json.dumps(data, indent=1))
    print(f'wrote {args.out}', file=sys.stderr)


COMPILE_SIGNATURES = [
    ('nested_function', re.compile(r'function definition is not allowed here')),
    ('vla_in_struct', re.compile(r'variable length array in structure|fields must have a constant size')),
    ('decimal_float', re.compile(r'decimal type extension not supported|invalid suffix .DD.|invalid suffix .DF.|invalid suffix .DL.')),
    ('unknown_builtin', re.compile(r"use of unknown builtin|undeclared identifier '__builtin|implicit declaration of function '__builtin")),
    ('asm_constraint', re.compile(r"invalid operand for inline asm constraint|invalid input constraint|couldn.t allocate (input|output) register")),
    ('compiler_crash', re.compile(r'LLVM ERROR|PLEASE submit a bug report|Assertion .* failed|Segmentation fault|clang: error: unable to execute command|Stack dump:')),
    ('return_type_mismatch', re.compile(r'non-void function .* should return a value')),
    ('redefinition_conflict', re.compile(r'conflicting types for|redefinition of')),
]

LINK_SIGNATURES = [
    ('companion_no_main', re.compile(r'undefined symbol: main\b')),
]


def classify_compile(stderr):
    for name, pat in COMPILE_SIGNATURES:
        if pat.search(stderr):
            return name
    return 'other_frontend_unclassified'


def classify_link(stderr):
    for name, pat in LINK_SIGNATURES:
        if pat.search(stderr):
            return name
    m = re.findall(r'undefined symbol: (\S+)', stderr)
    if m:
        return 'missing_symbol:' + ','.join(sorted(set(m))[:5])
    return 'other_link_unclassified'


def render_report(args):
    data = json.loads(Path(args.report).read_text())
    from collections import Counter, defaultdict
    total = len(data)
    by_status = Counter(r['status'] for r in data)

    lines = []
    lines.append('# ML-026a: gcc-c-torture 全量扫描报告')
    lines.append('')
    lines.append(f'语料：`{DEFAULT_CORPUS.relative_to(REPO_ROOT)}`，共 **{total}** 个 `.c` 文件。')
    lines.append('')
    lines.append('## 总览')
    lines.append('')
    lines.append('| 分类 | 数量 | 占比 |')
    lines.append('|---|---|---|')
    for k in sorted(by_status):
        lines.append(f'| {k} | {by_status[k]} | {by_status[k]/total*100:.1f}% |')
    npass = by_status.get('PASS', 0)
    lines.append(f'| **TOTAL** | {total} | 100% |')
    lines.append('')
    lines.append(f'**通过率 = {npass}/{total} = {npass/total*100:.1f}%**')
    lines.append('')

    # FAIL_COMPILE detail
    fc = [r for r in data if r['status'] == 'FAIL_COMPILE']
    if fc:
        lines.append('## FAIL_COMPILE 详情')
        lines.append('')
        buckets = defaultdict(list)
        for r in fc:
            cat = classify_compile(r.get('stderr', ''))
            buckets[cat].append(r['file'])
        for cat in sorted(buckets, key=lambda c: -len(buckets[c])):
            files = buckets[cat]
            lines.append(f'### {cat} ({len(files)})')
            lines.append('')
            for f in files:
                lines.append(f'- `{f}`')
            lines.append('')

    fl = [r for r in data if r['status'] == 'FAIL_LINK']
    if fl:
        lines.append('## FAIL_LINK 详情')
        lines.append('')
        buckets = defaultdict(list)
        for r in fl:
            cat = classify_link(r.get('stderr', ''))
            buckets[cat].append(r['file'])
        for cat in sorted(buckets, key=lambda c: -len(buckets[c])):
            files = buckets[cat]
            lines.append(f'### {cat} ({len(files)})')
            lines.append('')
            for f in files:
                lines.append(f'- `{f}`')
            lines.append('')

    to = [r for r in data if r['status'] in ('TIMEOUT', 'TIMEOUT_COMPILE', 'TIMEOUT_LINK')]
    if to:
        lines.append('## TIMEOUT 详情')
        lines.append('')
        for r in to:
            lines.append(f'- `{r["file"]}` (stage={r.get("stage")}, retested={r.get("retested", False)})')
        lines.append('')

    fr = [r for r in data if r['status'] == 'FAIL_RUN']
    if fr:
        lines.append('## FAIL_RUN 详情（重点）')
        lines.append('')
        buckets = defaultdict(list)
        for r in fr:
            buckets[r.get('subcat', 'unknown')].append(r)
        for cat in sorted(buckets, key=lambda c: -len(buckets[c])):
            items = buckets[cat]
            lines.append(f'### {cat} ({len(items)})')
            lines.append('')
            for r in items:
                gem5_note = ''
                if 'gem5_status' in r:
                    gem5_note = f' — gem5: {r["gem5_status"]}(exit={r.get("gem5_exit_code")})'
                lines.append(f'- `{r["file"]}` qemu_exit={r.get("exit_code")}{gem5_note}')
            lines.append('')

    Path(args.report_out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report_out).write_text('\n'.join(lines))
    print(f'wrote {args.report_out}', file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--corpus', default=str(DEFAULT_CORPUS))
    ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--out', default='gcc-torture-results.json')
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--filter', default=None, help='regex on relative path')
    ap.add_argument('--compile-timeout', type=float, default=COMPILE_TIMEOUT_DEFAULT)
    ap.add_argument('--link-timeout', type=float, default=LINK_TIMEOUT_DEFAULT)
    ap.add_argument('--run-timeout', type=float, default=RUN_TIMEOUT_DEFAULT)
    ap.add_argument('--gem5-timeout', type=float, default=30)
    ap.add_argument('--retest-timeouts', default=None,
                     help='path to an existing results JSON; re-run only its TIMEOUT* entries')
    ap.add_argument('--gem5-crosscheck', default=None,
                     help='path to an existing results JSON; gem5-crosscheck its FAIL_RUN entries')
    ap.add_argument('--report', default=None,
                     help='path to an existing results JSON; render it to markdown (see --report-out)')
    ap.add_argument('--report-out', default='docs/reviews/gcc-torture-report.md')
    args = ap.parse_args()

    if args.report:
        render_report(args)
    elif args.retest_timeouts:
        retest_timeouts(args)
    elif args.gem5_crosscheck:
        run_gem5_crosscheck(args)
    else:
        sweep(args)


if __name__ == '__main__':
    main()
