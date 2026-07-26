#!/usr/bin/env python3
"""KL-120a dual-backend probes for cfx2rd, CFX carriers, and E1 return.

Runs the same raw instruction streams on QEMU bare metal and gem5 SE:

* register: cfx2rc -> cfx2rd round trips for every storage-backed family,
  reset-zero/W0C common pending behavior, and unsupported-read-zero.
* nested: real power -> smon trap/escape, followed by a power self-escape.
  The second escape succeeds only if the first restored inner_cfx_code to
  power; the pre-KL-120a stuck-at-smon behavior raises ILLI instead.
"""

import os
import re
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
QEMU = os.environ.get(
    "QEMU_DADAO",
    os.path.join(REPO, ".work", "source", "qemu", "build",
                 "qemu-system-dadao"))
GEM5_DIR = os.path.expanduser("~/DADAO-gem5")
GEM5_TESTS = os.path.join(GEM5_DIR, "tests", "dadao")
GEM5 = os.environ.get(
    "GEM5_OPT", os.path.join(GEM5_DIR, "build", "DADAO", "gem5.opt"))
GEM5_CFG = os.environ.get(
    "GEM5_SE", os.path.join(GEM5_TESTS, "dadao_se.py"))
EVIDENCE = os.path.join(REPO, ".work", "evidence", "kl120a-probes")

sys.path.insert(0, HERE)
sys.path.insert(0, GEM5_TESTS)
from build_test_binary import load_reg, UNIMP_ENCODING  # noqa: E402
import gen_kl116a_o3_probe as o3  # noqa: E402
import gen_min_elf  # noqa: E402

OP_CFX2RD = 0x72
OP_CFX2RC = 0x73
OP_ESCAPE = 0x77
OP_HALT = 0x00
OP_BRNZ = 0x2B
OP_MISC = 0x10
MISC_ORR = 0x09
MISC_XOR = 0x0A
OP_CSZ = 0x22

CFX_SMON = 2
CFX_PTW = 4
CFX_TIMER = 18
CFX_POWER = 63

REGISTER_PASS = 44
PENDING_PASS = 45
REGISTER_FAIL = 0x98
NESTED_TARGET_OFFSET = 0x3E0


def write_crrr(out, op, cfxcode, cg, rc, rd):
    word = ((op & 0xFF) << 24) | ((cfxcode & 0x3F) << 18) | \
        ((cg & 0x3F) << 12) | ((rc & 0x3F) << 6) | (rd & 0x3F)
    out.extend(struct.pack(">I", word))


def write_ciii(out, op, cfxcode, imm18):
    word = ((op & 0xFF) << 24) | ((cfxcode & 0x3F) << 18) | \
        (imm18 & 0x3FFFF)
    out.extend(struct.pack(">I", word))


def write_orrr(out, minor, dst, lhs, rhs):
    word = (OP_MISC << 24) | ((minor & 0x3F) << 18) | \
        ((dst & 0x3F) << 12) | ((lhs & 0x3F) << 6) | (rhs & 0x3F)
    out.extend(struct.pack(">I", word))


def add_check(out, cfxcode, cg, rc, value, expected=None):
    """Write rd2, read rd3, and OR any mismatch into rd30."""
    if expected is None:
        expected = value
    load_reg(out, "rd", 2, value)
    write_crrr(out, OP_CFX2RC, cfxcode, cg, rc, 2)
    write_crrr(out, OP_CFX2RD, cfxcode, cg, rc, 3)
    load_reg(out, "rd", 4, expected)
    write_orrr(out, MISC_XOR, 5, 3, 4)
    write_orrr(out, MISC_ORR, 30, 30, 5)


def gen_register_probe():
    out = bytearray()
    load_reg(out, "rd", 30, 0)

    # Existing cfx2rc-backed families plus KL-120a's two new carriers.
    add_check(out, CFX_PTW, 3, 12, 0x1234, 0x123C)  # bit3 forced one
    add_check(out, CFX_POWER, 5, 0, 2)
    add_check(out, CFX_POWER, 5, 1, 0x0123456789ABCDEF)
    add_check(out, CFX_POWER, 5, 3, 0xFEDCBA9876543210,
              0x0000BA9876543210)
    add_check(out, CFX_POWER, 5, 5, CFX_TIMER)
    add_check(out, CFX_SMON, 2, 10, 0xFFFF000080000400,
              0x0000000080000400)
    add_check(out, CFX_SMON, 5, 0, 3)
    add_check(out, CFX_SMON, 5, 1, 0xA5A55A5AF0F00F0F)
    add_check(out, CFX_SMON, 5, 3, 0xABCDEF0080000234,
              0x0000EF0080000234)
    add_check(out, CFX_SMON, 5, 5, CFX_POWER)
    for cg, value in enumerate((
            0x1111111111111111, 0x2222222222222222,
            0x3333333333333333, 0x4444444444444444)):
        add_check(out, CFX_TIMER, cg, 7, value)

    # Common pending has no source in KL-120a. It resets zero, and both an
    # all-one (preserve) and all-zero (clear) W0C write leave it zero.
    write_crrr(out, OP_CFX2RD, CFX_TIMER, 4, 7, 3)
    write_orrr(out, MISC_ORR, 30, 30, 3)
    add_check(out, CFX_TIMER, 4, 7, 0xFFFFFFFFFFFFFFFF, 0)
    add_check(out, CFX_TIMER, 4, 7, 0, 0)

    # Reserved/unbacked reads are explicitly inert in this task.
    write_crrr(out, OP_CFX2RD, 7, 6, 6, 3)
    write_orrr(out, MISC_ORR, 30, 30, 3)

    load_reg(out, "rd", 26, REGISTER_PASS)
    load_reg(out, "rd", 27, REGISTER_FAIL)
    word = (OP_CSZ << 24) | (30 << 18) | (28 << 12) | (26 << 6) | 27
    out.extend(struct.pack(">I", word))
    out.extend(struct.pack(">I", (OP_HALT << 24) | (28 << 18)))
    return bytes(out)


def gen_illegal_dest_probe():
    out = bytearray()
    write_crrr(out, OP_CFX2RD, CFX_POWER, 5, 0, 0)
    load_reg(out, "rd", 2, 0x77)
    out.extend(struct.pack(">I", (OP_HALT << 24) | (2 << 18)))
    return bytes(out)


def gen_pending_probe(cfxcode, valid_mask):
    """Verify raw seed filtering and W0C preserve/clear for one cfx."""
    out = bytearray()
    load_reg(out, "rd", 29, 1)
    load_reg(out, "rd", 30, 0)

    def read_check(expected):
        write_crrr(out, OP_CFX2RD, cfxcode, 4, 7, 3)
        load_reg(out, "rd", 4, expected)
        write_orrr(out, MISC_XOR, 5, 3, 4)
        write_orrr(out, MISC_ORR, 30, 30, 5)

    # Test seed is all ones. Read must expose only valid cause bits.
    read_check(valid_mask)
    preserve = 0xAAAAAAAAAAAAAAAA if valid_mask.bit_count() > 1 else valid_mask
    load_reg(out, "rd", 2, preserve)
    write_crrr(out, OP_CFX2RC, cfxcode, 4, 7, 2)
    read_check(valid_mask & preserve)
    load_reg(out, "rd", 2, 0)
    write_crrr(out, OP_CFX2RC, cfxcode, 4, 7, 2)
    read_check(0)

    load_reg(out, "rd", 26, PENDING_PASS)
    load_reg(out, "rd", 27, REGISTER_FAIL)
    word = (OP_CSZ << 24) | (30 << 18) | (28 << 12) | (26 << 6) | 27
    out.extend(struct.pack(">I", word))
    # QEMU may re-enter the current TB while consuming its asynchronous
    # shutdown request.  Isolate halt in its own TB so a re-entry repeats only
    # the already-selected exit code, not the destructive W0C sequence.
    write_ciii(out, OP_BRNZ, 29, 0)
    out.extend(struct.pack(">I", (OP_HALT << 24) | (28 << 18)))
    return bytes(out)


def gen_nested_probe(base):
    o3.ROM_BASE = base
    o3.o1.ROM_BASE = base
    raw = bytearray(o3.gen())
    old_halt = struct.pack(">I", (OP_HALT << 24) | (28 << 18))
    halt_offset = raw.index(old_halt, o3.SUPV_ENTRY_OFFSET)
    target = base + NESTED_TARGET_OFFSET

    continuation = bytearray()
    # Read hardware-populated smon frame fields after the first escape.
    # This covers cfx2rd access to rc2/rc4 without making those HW fields
    # software-writable, and confirms rc5 captured the pre-trap power cfx.
    load_reg(continuation, "rd", 30, 0)
    for rc, expected in (
            (2, 1), (4, 0x76080000), (5, CFX_POWER)):
        if rc in (2, 4):
            load_reg(continuation, "rd", 2, 0)
            write_crrr(continuation, OP_CFX2RC, CFX_SMON, 5, rc, 2)
        write_crrr(continuation, OP_CFX2RD, CFX_SMON, 5, rc, 3)
        load_reg(continuation, "rd", 4, expected)
        write_orrr(continuation, MISC_XOR, 5, 3, 4)
        write_orrr(continuation, MISC_ORR, 30, 30, 5)
    load_reg(continuation, "rd", 26, o3.EXIT_SUCCESS)
    load_reg(continuation, "rd", 27, REGISTER_FAIL)
    word = (OP_CSZ << 24) | (30 << 18) | (28 << 12) | (26 << 6) | 27
    continuation.extend(struct.pack(">I", word))

    load_reg(continuation, "rd", 2, target)
    write_crrr(continuation, OP_CFX2RC, CFX_POWER, 5, 3, 2)
    load_reg(continuation, "rd", 2, 2)
    write_crrr(continuation, OP_CFX2RC, CFX_POWER, 5, 0, 2)
    load_reg(continuation, "rd", 2, 0xFFFFFFFFFFFFFFFF)
    write_crrr(continuation, OP_CFX2RC, CFX_POWER, 5, 1, 2)
    load_reg(continuation, "rd", 2, CFX_POWER)
    write_crrr(continuation, OP_CFX2RC, CFX_POWER, 5, 5, 2)
    write_ciii(continuation, OP_ESCAPE, CFX_POWER, 0)

    if halt_offset + len(continuation) > NESTED_TARGET_OFFSET:
        raise AssertionError("nested continuation overlaps target")
    raw[halt_offset:halt_offset + len(continuation)] = continuation
    poison = struct.pack(">I", UNIMP_ENCODING)
    for offset in range(halt_offset + len(continuation),
                        NESTED_TARGET_OFFSET, 4):
        raw[offset:offset + 4] = poison
    raw[NESTED_TARGET_OFFSET:NESTED_TARGET_OFFSET + 4] = old_halt
    return bytes(raw)


def gem5_code(stdout):
    matches = re.findall(r"SIM_END: .* code=(\d+)", stdout)
    if len(matches) != 1:
        raise AssertionError(
            f"gem5 output has {len(matches)} SIM_END records, expected one")
    return int(matches[0])


def run_qemu(name, raw, real=False, pending_code=None):
    path = os.path.join(EVIDENCE, name + "-qemu.bin")
    with open(path, "wb") as stream:
        stream.write(raw)
    command = [QEMU, "-M", "dadao-m1", "-bios", path, "-display", "none",
               "-serial", "none", "-d", "int"]
    if real:
        command[3:3] = ["-global", "dadao-cpu.cfx-smon-real=on"]
    if pending_code is not None:
        command[3:3] = [
            "-global",
            f"dadao-cpu.cfx-common-pending-test-code={pending_code}",
            "-global",
            "dadao-cpu.cfx-common-pending-test-seed=0xffffffffffffffff",
        ]
    result = subprocess.run(command, capture_output=True, timeout=60, text=True)
    with open(os.path.join(EVIDENCE, name + "-qemu.log"), "w") as stream:
        stream.write("=== command ===\n" + " ".join(command))
        stream.write("\n=== stdout ===\n" + result.stdout)
        stream.write("\n=== stderr ===\n" + result.stderr)
    return result


def run_gem5(name, raw, real=False, pending_code=None):
    elf = gen_min_elf.build_elf(
        raw, data_segs=[(0x80001000, bytes(0x1000)),
                        (0x80002000, bytes(0x1000))])
    path = os.path.join(EVIDENCE, name + "-gem5.elf")
    with open(path, "wb") as stream:
        stream.write(elf)
    outdir = tempfile.mkdtemp(prefix="gem5_kl120a_")
    command = [GEM5, "--outdir=" + outdir, GEM5_CFG, path]
    if real:
        command.append("--cfx-smon-real")
    if pending_code is not None:
        command.extend([
            "--cfx-pending-test", str(pending_code),
            "0xffffffffffffffff"])
    result = subprocess.run(command, capture_output=True, timeout=60, text=True)
    with open(os.path.join(EVIDENCE, name + "-gem5.log"), "w") as stream:
        stream.write("=== command ===\n" + " ".join(command))
        stream.write("\n=== stdout ===\n" + result.stdout)
        stream.write("\n=== stderr ===\n" + result.stderr)
    return result


def main():
    os.makedirs(EVIDENCE, exist_ok=True)

    registers = gen_register_probe()
    qreg = run_qemu("register", registers)
    greg = run_gem5("register", registers)
    assert qreg.returncode == REGISTER_PASS, qreg.stderr
    assert greg.returncode == REGISTER_PASS, greg.stderr
    assert gem5_code(greg.stdout) == REGISTER_PASS, greg.stdout

    illegal = gen_illegal_dest_probe()
    qillegal = run_qemu("illegal-dest", illegal)
    gillegal = run_gem5("illegal-dest", illegal)
    assert qillegal.returncode == 0x82, qillegal.stderr
    assert gillegal.returncode == 0x82, gillegal.stderr
    assert gem5_code(gillegal.stdout) == 0x82, gillegal.stdout

    pending_profiles = {
        CFX_SMON: 1 << 32,
        15: 1 << 8,               # hart IPI
        CFX_TIMER: 1 << 10,
        62: 0xFFFFFFFF00000000,   # UART0..31
        CFX_POWER: 1 << 10,
        CFX_PTW: 0,               # no maskable cause
        7: 0,                     # reserved cfxcode
    }
    for code, valid_mask in pending_profiles.items():
        raw = gen_pending_probe(code, valid_mask)
        qpending = run_qemu(
            f"pending-{code}", raw, pending_code=code)
        gpending = run_gem5(
            f"pending-{code}", raw, pending_code=code)
        assert qpending.returncode == PENDING_PASS, qpending.stderr
        assert gpending.returncode == PENDING_PASS, gpending.stderr
        assert gem5_code(gpending.stdout) == PENDING_PASS, gpending.stdout

    qnested = run_qemu(
        "nested", gen_nested_probe(o3.ROM_BASE), real=True)
    gnested = run_gem5(
        "nested", gen_nested_probe(gen_min_elf.LOAD_ADDR), real=True)
    assert qnested.returncode == o3.EXIT_SUCCESS, qnested.stderr
    assert gnested.returncode == o3.EXIT_SUCCESS, gnested.stderr
    assert gem5_code(gnested.stdout) == o3.EXIT_SUCCESS, gnested.stdout
    assert "escape cfx=2" in qnested.stderr
    assert "escape cfx=63" in qnested.stderr
    assert "escape cfx=2" in gnested.stderr
    assert "escape cfx=63" in gnested.stderr

    print("PASS: register=44/44; rd0 ILLI=130/130; "
          "pending profiles=7x45/45; nested=43/43")


if __name__ == "__main__":
    main()
