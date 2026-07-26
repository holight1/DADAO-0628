#!/usr/bin/env python3
"""KL-124a DADAO gem5 FullSystem bare-metal regression probes.

Runs the existing KL-113a, KL-117a, and KL-120a raw instruction streams
directly as flat binaries at 0x00100000.  Each result is compared with a
separately generated SE baseline; the FullSystem side never uses an ELF
wrapper or SE Process.
"""

import os
import re
import subprocess
import sys
import tempfile


HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
GEM5_DIR = os.path.expanduser("~/DADAO-gem5")
GEM5 = os.environ.get(
    "GEM5_OPT", os.path.join(GEM5_DIR, "build", "DADAO", "gem5.opt"))
GEM5_CFG = os.environ.get(
    "GEM5_FS", os.path.join(GEM5_DIR, "tests", "dadao", "dadao_fs.py"))
GEM5_SE_CFG = os.environ.get(
    "GEM5_SE", os.path.join(GEM5_DIR, "tests", "dadao", "dadao_se.py"))
EVIDENCE = os.path.join(REPO, ".work", "evidence", "kl124a-gem5-fs")

sys.path.insert(0, HERE)
import gen_kl110a_o1_probe as o1  # noqa: E402
import gen_kl112a_o2_probes as o2  # noqa: E402
import gen_kl116a_o3_probe as o3  # noqa: E402
import run_kl120a_cfx_carrier_probes as k120  # noqa: E402
sys.path.insert(0, os.path.join(GEM5_DIR, "tests", "dadao"))
import gen_min_elf  # noqa: E402


FS_BASE = 0x00100000
SE_BASE = gen_min_elf.LOAD_ADDR
CODE_WINDOW = 0x10000
DATA_SEGS = [
    (0x80001000, bytes(0x1000)),
    (0x80002000, bytes(0x1000)),
    (0x87FEF000, bytes(0x3000)),
]


def sim_end(stdout):
    matches = re.findall(r"SIM_END: (.*?) code=(\d+)", stdout)
    if len(matches) != 1:
        raise AssertionError(
            f"gem5 output has {len(matches)} SIM_END records, expected one")
    return matches[0][0], int(matches[0][1])


def normalize_address(value):
    if SE_BASE <= value < SE_BASE + CODE_WINDOW:
        return value - SE_BASE + FS_BASE
    return value


def register_dump(stdout):
    lines = [line for line in stdout.splitlines()
             if line.startswith("DADAO_REGDUMP")]
    if not lines:
        return None
    if len(lines) != 1:
        raise AssertionError(f"expected at most one REGDUMP, got {len(lines)}")
    registers = {}
    for name, value in re.findall(r"\b(r[db]\d+)=0x([0-9a-f]+)", lines[0]):
        # rb1 is execution-environment state: SE supplies a process stack,
        # while this firmware-free FullSystem carrier resets it to zero.
        if name == "rb1":
            continue
        registers[name] = normalize_address(int(value, 16))
    return registers


def memory_dump(stdout):
    lines = [line for line in stdout.splitlines()
             if line.startswith("DADAO_MEMDUMP")]
    if not lines:
        return None
    if len(lines) != 1:
        raise AssertionError(f"expected at most one MEMDUMP, got {len(lines)}")
    return lines[0]


def cfx_trace(stderr):
    def normalize_hex(match):
        value = int(match.group(1), 16)
        return f"0x{normalize_address(value):x}"

    return [
        re.sub(r"0x([0-9a-f]+)", normalize_hex, line)
        for line in stderr.splitlines()
        if line.startswith("dadao:")
    ]


def command_options(command, real, pending_code):
    if real:
        command.append("--cfx-smon-real")
    if pending_code is not None:
        command.extend([
            "--cfx-pending-test", str(pending_code),
            "0xffffffffffffffff",
        ])


def execute(name, profile, command):
    result = subprocess.run(
        command, capture_output=True, timeout=60, text=True)
    with open(os.path.join(EVIDENCE, f"{name}-{profile}.log"), "w") as stream:
        stream.write("=== command ===\n" + " ".join(command))
        stream.write("\n=== stdout ===\n" + result.stdout)
        stream.write("\n=== stderr ===\n" + result.stderr)
    return result


def run(name, fs_raw, se_raw, expected, expected_cause,
        real=False, pending_code=None):
    os.makedirs(EVIDENCE, exist_ok=True)
    image = os.path.join(EVIDENCE, name + ".bin")
    with open(image, "wb") as stream:
        stream.write(fs_raw)
    fs_command = [
        GEM5, "--outdir=" + tempfile.mkdtemp(prefix=f"gem5_kl124a_fs_{name}_"),
        GEM5_CFG, image,
    ]
    command_options(fs_command, real, pending_code)
    fs_result = execute(name, "fs", fs_command)

    elf_path = os.path.join(EVIDENCE, name + "-se.elf")
    with open(elf_path, "wb") as stream:
        stream.write(gen_min_elf.build_elf(se_raw, data_segs=DATA_SEGS))
    se_command = [
        GEM5, "--outdir=" + tempfile.mkdtemp(prefix=f"gem5_kl124a_se_{name}_"),
        GEM5_SE_CFG, elf_path,
    ]
    command_options(se_command, real, pending_code)
    se_result = execute(name, "se", se_command)

    for profile, result in (("FS", fs_result), ("SE", se_result)):
        cause, code = sim_end(result.stdout)
        assert result.returncode == expected, result.stderr
        assert code == expected, result.stdout
        assert cause == expected_cause, (
            f"{profile} cause={cause!r}, expected {expected_cause!r}")

    assert register_dump(fs_result.stdout) == register_dump(se_result.stdout)
    assert memory_dump(fs_result.stdout) == memory_dump(se_result.stdout)
    assert cfx_trace(fs_result.stderr) == cfx_trace(se_result.stderr)
    print(f"{name}: {expected_cause}/{expected} FS=SE")
    return fs_result


def main():
    # The generator modules must retain their QEMU/bare-metal base.  An SE
    # runner imported in the same process would rebase these globals.
    assert o1.ROM_BASE == 0x00100000
    assert o2.o1.ROM_BASE == 0x00100000
    assert o3.ROM_BASE == 0x00100000

    fs_o1 = o1.gen()
    fs_design1 = o2.gen_design1_negative()
    fs_design3 = o2.gen_design3_negative()
    fs_o1_regression = o2.o1.gen()
    fs_o3 = o3.gen()
    fs_nested = k120.gen_nested_probe(FS_BASE)

    o1.ROM_BASE = SE_BASE
    o2.o1.ROM_BASE = SE_BASE
    o3.ROM_BASE = SE_BASE
    o3.o1.ROM_BASE = SE_BASE
    se_o1 = o1.gen()
    se_design1 = o2.gen_design1_negative()
    se_design3 = o2.gen_design3_negative()
    se_o1_regression = o2.o1.gen()
    se_o3 = o3.gen()
    se_nested = k120.gen_nested_probe(SE_BASE)

    o1_positive = run(
        "kl113-o1", fs_o1, se_o1, o1.EXIT_CODE, "halt")
    assert "pc=0x100200" in o1_positive.stderr
    run("kl113-design1", fs_design1, se_design1, 0x82, "ILLI")
    run("kl113-design3", fs_design3, se_design3, 0x86, "CFXREG")
    run("kl113-o1-regression", fs_o1_regression, se_o1_regression,
        o1.EXIT_CODE, "halt")

    run("kl117-profile-off", fs_o3, se_o3, o3.EXIT_MISMATCH, "halt")
    o3_on = run(
        "kl117-profile-on", fs_o3, se_o3, o3.EXIT_SUCCESS, "halt",
        real=True)
    assert "cause_ip=0x100234" in o3_on.stderr
    assert "vector=0x100400" in o3_on.stderr
    assert "pc=0x100238" in o3_on.stderr

    registers = k120.gen_register_probe()
    run("kl120-register", registers, registers, k120.REGISTER_PASS, "halt")
    illegal = k120.gen_illegal_dest_probe()
    run("kl120-illegal-dest", illegal, illegal, 0x82, "ILLI")
    pending_profiles = {
        k120.CFX_SMON: 1 << 32,
        15: 1 << 8,
        k120.CFX_TIMER: 1 << 10,
        62: 0xFFFFFFFF00000000,
        k120.CFX_POWER: 1 << 10,
        k120.CFX_PTW: 0,
        7: 0,
    }
    for code, valid_mask in pending_profiles.items():
        pending = k120.gen_pending_probe(code, valid_mask)
        run(f"kl120-pending-{code}", pending, pending,
            k120.PENDING_PASS, "halt", pending_code=code)

    nested = run(
        "kl120-nested", fs_nested, se_nested, o3.EXIT_SUCCESS, "halt",
        real=True)
    assert "escape cfx=2" in nested.stderr
    assert "escape cfx=63" in nested.stderr

    print("PASS: KL-113a=42/130/134/42; KL-117a=153/43; "
          "KL-120a=44/130 + 7x45 + 43 (FullSystem raw)")


if __name__ == "__main__":
    main()
