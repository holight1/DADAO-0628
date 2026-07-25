#!/usr/bin/env python3
"""KL-117a gem5 A/B probe for real cfx_smon trap entry.

Reuses KL-116a's backend-independent instruction stream, rebased to gem5 SE's
ELF load address. The default run must retain the host syscall shortcut and
exit 0x99; the opt-in run must execute the guest handler, escape to causeIp+4,
and exit 43.

Usage: python3 tests/scripts/run_kl117a_gem5_probe.py
"""

import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
GEM5_DIR = os.path.expanduser("~/DADAO-gem5")
GEM5_TESTS = os.path.join(GEM5_DIR, "tests", "dadao")
GEM5_BIN = os.environ.get(
    "GEM5_OPT", os.path.join(GEM5_DIR, "build", "DADAO", "gem5.opt"))
GEM5_CFG = os.environ.get(
    "GEM5_SE", os.path.join(GEM5_TESTS, "dadao_se.py"))
EVIDENCE = os.path.join(REPO, ".work", "evidence", "kl117a-probe")

sys.path.insert(0, HERE)
sys.path.insert(0, GEM5_TESTS)
import gen_kl116a_o3_probe as o3  # noqa: E402
import gen_min_elf  # noqa: E402
from build_test_binary import load_reg  # noqa: E402

o3.ROM_BASE = gen_min_elf.LOAD_ADDR
o3.o1.ROM_BASE = gen_min_elf.LOAD_ADDR

GUARD_PAGE = (0x80001000, bytes(0x1000))
MARKER_PAGE = (0x80002000, bytes(0x1000))
TRAP_ENCODING = bytes.fromhex("76080000")
PRIOR_CFX_MASK = 0x0123456789ABCDEF


def with_discriminating_prior_mask(raw):
    """Replace the O1 handoff's all-ones previous mask with a distinctive
    value, without changing instruction count or any O3 control flow."""
    original = bytearray()
    load_reg(original, "rd", 2, 0xFFFFFFFFFFFFFFFF)
    o3.write_crrr(
        original, o3.OP_CFX2RC, o3.CFX_POWER, 5, 1, 2)
    replacement = bytearray()
    load_reg(replacement, "rd", 2, PRIOR_CFX_MASK)
    o3.write_crrr(
        replacement, o3.OP_CFX2RC, o3.CFX_POWER, 5, 1, 2)
    if len(original) != len(replacement) or raw.count(original) != 1:
        raise AssertionError("cannot identify unique O1 prevCfxMask sequence")
    return raw.replace(original, replacement)


def sim_code(stdout):
    match = re.search(r"SIM_END: .* code=(\d+)", stdout)
    if not match:
        raise AssertionError("gem5 output has no SIM_END code")
    return int(match.group(1))


def run(name, elf_path, real):
    outdir = tempfile.mkdtemp(prefix=f"gem5_kl117a_{name}_")
    command = [GEM5_BIN, "--outdir=" + outdir, GEM5_CFG, elf_path]
    if real:
        command.append("--cfx-smon-real")
    result = subprocess.run(
        command, capture_output=True, timeout=60, text=True)
    log = "=== command ===\n" + " ".join(command)
    log += "\n\n=== stdout ===\n" + result.stdout
    log += "\n=== stderr ===\n" + result.stderr
    with open(os.path.join(EVIDENCE, name + ".log"), "w") as stream:
        stream.write(log)
    print(f"{name}: process_rc={result.returncode} "
          f"guest_code={sim_code(result.stdout)}")
    return result


def main():
    os.makedirs(EVIDENCE, exist_ok=True)
    raw = with_discriminating_prior_mask(o3.gen())
    trap_offset = raw.index(TRAP_ENCODING)
    cause_ip = gen_min_elf.LOAD_ADDR + trap_offset
    vector = gen_min_elf.LOAD_ADDR + o3.SMON_HANDLER_OFFSET
    elf = gen_min_elf.build_elf(
        raw, data_segs=[GUARD_PAGE, MARKER_PAGE])
    bin_path = os.path.join(EVIDENCE, "kl117a-o3.bin")
    elf_path = os.path.join(EVIDENCE, "kl117a-o3.elf")
    with open(bin_path, "wb") as stream:
        stream.write(raw)
    with open(elf_path, "wb") as stream:
        stream.write(elf)

    off = run("profile-off", elf_path, False)
    assert sim_code(off.stdout) == o3.EXIT_MISMATCH
    assert "dadao: trap cfx_smon" not in off.stderr
    assert "rd31=0xffffffffffffffda" in off.stdout

    on = run("profile-on", elf_path, True)
    assert sim_code(on.stdout) == o3.EXIT_SUCCESS
    assert "rd31=0x0000000000000000" in on.stdout
    expected_enter = (
        "dadao: trap cfx_smon mode 2->2 inner_cfx_code=2 "
        f"cause_id=0x1 cause_ip=0x{cause_ip:x} "
        f"cause_info=0x{int.from_bytes(TRAP_ENCODING, 'big'):x} "
        f"vector=0x{vector:x}")
    assert expected_enter in on.stderr
    expected_escape = (
        f"dadao: escape cfx=2 mode 2->2 mask=0x{PRIOR_CFX_MASK:x} "
        f"pc=0x{cause_ip + 4:x}")
    assert expected_escape in on.stderr
    print(f"PASS: off=0x{o3.EXIT_MISMATCH:x}, on={o3.EXIT_SUCCESS}, "
          f"cause_ip=0x{cause_ip:x}, vector=0x{vector:x}")


if __name__ == "__main__":
    main()
