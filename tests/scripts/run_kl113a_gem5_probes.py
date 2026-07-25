#!/usr/bin/env python3
"""KL-113a gem5 probe runner: hypv<->supv handoff O1 positive + O2
design1/design3 negatives, gem5 side.

Reuses the exact raw instruction sequences from the QEMU-side probe
generators (gen_kl110a_o1_probe.py / gen_kl112a_o2_probes.py, KL-110a/
KL-112a) -- these are backend-agnostic raw opcode streams, no QEMU-specific
loading. Wraps each into a minimal DADAO ELF (gen_min_elf.build_elf, the
same helper run_gem5_test.py uses) and runs it under gem5 SE (dadao_se.py,
DADAOAtomicSimpleCPU), matching the lit E2E GEM5_SE backend convention.

gem5 SE has no bare-metal reset vector/ROM concept (unlike QEMU's `-bios`
load at 0x00100000): the whole ELF .text loads at a fixed different address
(gen_min_elf.LOAD_ADDR, 0x80000000), and ISA::clear() (arch/dadao/isa.cc)
establishes the CFX reset state once at ThreadContext construction, before
that entry point's first instruction runs -- the closest gem5 SE analogue to
QEMU's post-reset observation point. The O1 probe's `supv_entry` address is
therefore rebased from QEMU's ROM_BASE to gem5's LOAD_ADDR (see below); the
instruction encodings themselves are untouched.

Usage: python3 run_kl113a_gem5_probes.py [all|o1|design1|design3|o1regress]
Writes probes + gem5 stdout/stderr logs to .work/evidence/kl113a-probes/.
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))                  # ~/DADAO-0628
GEM5_DIR = os.path.expanduser('~/DADAO-gem5')
GEM5_TESTS = os.path.join(GEM5_DIR, 'tests', 'dadao')
GEM5_BIN = os.environ.get('GEM5_OPT', os.path.join(GEM5_DIR, 'build', 'DADAO', 'gem5.opt'))
GEM5_CFG = os.environ.get('GEM5_SE', os.path.join(GEM5_TESTS, 'dadao_se.py'))
EVIDENCE = os.path.join(REPO, '.work', 'evidence', 'kl113a-probes')

sys.path.insert(0, HERE)
sys.path.insert(0, GEM5_TESTS)
import gen_kl110a_o1_probe as o1          # noqa: E402
import gen_kl112a_o2_probes as o2         # noqa: E402
import gen_min_elf                        # noqa: E402

# gen_kl110a_o1_probe.py's ROM_BASE (0x00100000) is QEMU's `-bios` reset
# vector address -- meaningless for gem5 SE. Rebase so supv_entry
# (ROM_BASE + SUPV_ENTRY_OFFSET) lands inside the loaded .text segment;
# gen()/gen_design1_negative()/gen_design3_negative() read this module
# global at call time. This is a local monkeypatch of the imported module
# object in this process only -- tests/scripts/gen_kl110a_o1_probe.py and
# gen_kl112a_o2_probes.py are untouched. This is the "different ELF/memory
# layout, same instruction semantics" adaptation the KL-113a task file
# explicitly allows (it does not require byte-for-byte probe parity with
# QEMU, since the two backends' loading mechanisms already differ).
o1.ROM_BASE = gen_min_elf.LOAD_ADDR
o2.o1.ROM_BASE = gen_min_elf.LOAD_ADDR

# KL-109a finding (independent subagent review, code-agent/tasks/
# KL-109a-implement-ldmo-ra-stmo-ra-gem5.md): gem5's self-modifying-code
# guard needs the page right after the .text load address (0x80001000, one
# page past gen_min_elf.LOAD_ADDR) explicitly backed by a mapped ELF data
# segment, or stores there trigger a page-table fault. O1's MARKER_ADDR
# reuses that exact address verbatim from gen_kl110a_o1_probe.py.
GUARD_PAGE = (0x80001000, bytes(0x1000))


def run(name, raw_bin):
    """Wrap raw_bin in an ELF, run it under gem5 SE, and save
    <name>.bin/.elf/.log under .work/evidence/kl113a-probes/. Returns the
    completed subprocess.CompletedProcess (returncode is the exit code gem5
    was terminated/killed with, not the guest exit code -- parse
    'SIM_END: <cause> code=<n>' from stdout for that)."""
    os.makedirs(EVIDENCE, exist_ok=True)
    elf = gen_min_elf.build_elf(raw_bin, data_segs=[GUARD_PAGE])
    bin_path = os.path.join(EVIDENCE, f'{name}.bin')
    elf_path = os.path.join(EVIDENCE, f'{name}.elf')
    with open(bin_path, 'wb') as f:
        f.write(raw_bin)
    with open(elf_path, 'wb') as f:
        f.write(elf)
    outdir = tempfile.mkdtemp(prefix=f'gem5_kl113a_{name}_')
    result = subprocess.run(
        [GEM5_BIN, '--outdir=' + outdir, GEM5_CFG, elf_path],
        capture_output=True, timeout=60, text=True)
    log_path = os.path.join(EVIDENCE, f'{name}.log')
    with open(log_path, 'w') as f:
        f.write('=== stdout ===\n' + result.stdout)
        f.write('\n=== stderr ===\n' + result.stderr)
    print(f'--- {name} --- (gem5 process rc={result.returncode})')
    print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip())
    return result


if __name__ == '__main__':
    which = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if which in ('all', 'o1'):
        run('kl113a-o1-handoff', o1.gen())
    if which in ('all', 'design1'):
        run('kl113a-design1-negative', o2.gen_design1_negative())
    if which in ('all', 'design3'):
        run('kl113a-design3-negative', o2.gen_design3_negative())
    if which in ('all', 'o1regress'):
        run('kl113a-o1-regression', o2.o1.gen())
