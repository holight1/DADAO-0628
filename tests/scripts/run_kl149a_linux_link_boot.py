#!/usr/bin/env python3
"""KL-149a fail-closed Linux link, flat Image, and QEMU reset gate."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import socket
import struct
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / ".work" / "source" / "linux"
OUTPUT = ROOT / ".work" / "build" / "linux"
LLVM_BIN = ROOT / ".work" / "build" / "llvm" / "bin"
QEMU_SOURCE = ROOT / ".work" / "source" / "qemu"
QEMU = QEMU_SOURCE / "build" / "qemu-system-dadao"
EVIDENCE = ROOT / ".work" / "evidence" / "kl149a-linux-link-boot"
SERIES = ROOT / "components" / "linux" / "patches" / "series"
MANIFEST = ROOT / "manifests" / "components.lock.toml"

KL149_PATCHES = (
    (
        "0001-dadao-add-K3-configuration-skeleton.patch",
        "6dbd09a49be915128bb6a55360df79cf8c7c419a",
        "14ef129f2b38c5bd058f38316bf00de9e72a13a3",
    ),
    (
        "0002-dadao-add-Linux-compile-substrate.patch",
        "c06b6f93a3c33968145f001859f29702e47f3244",
        "728747dae1a19c159825459a485c624e403f9d6e",
    ),
    (
        "0003-dadao-link-K3-image-and-add-reset-entry.patch",
        "fca53b59dc8048ba9c4cd3965e488d8a11e07dbd",
        "476ab7b802482f307123dc7aa3e165d948323ca0",
    ),
    # Filled after the independent-review follow-up component commit.
    (
        "0004-dadao-harden-KL-149a-mode-and-O0-link-gates.patch",
        "b5f89a803600ecbe445c3aad64fceb51d8a61140",
        "94de1e4bf4c4f25c9771963989f43bfce0125a2b",
    ),
    (
        "0005-dadao-identify-KL-149a-bad-mode-path.patch",
        "f1349f6ee7858f8be8f6e91d18ea9b006f52c281",
        "aa1651702ecaa5c80918c376662f72489e9e015f",
    ),
)

RAM_BASE = 0x80000000
RAM_SIZE = 0x08000000
MARKER_ADDR = 0x87FD0000
STACK_TOP = 0x87FF0000
SCRATCH_END = 0x88000000
MARKER_VALUE = 0x4B4C313439414845
MARKER_BYTES = struct.pack(">Q", MARKER_VALUE)
FAILURE_VALUE = 0x4B4C313439424144
QEMU_EXPECTED_HEAD = "eee0933b064014f3ab305eaa275883f025223d53"
QEMU_EXPECTED_SHA256 = (
    "97bfa45fbb15c1f2c52dd7ddeec555da4b3d8a447c47cba3bdf862db5a76fcd8"
)
ROM_EXPECTED_SHA256 = (
    "46c1e4af50162dd9be1adb82eb9223a6902f0629a0a4c9d3f18822aee5e536c7"
)
NEGATIVE_ROM_EXPECTED_SHA256 = (
    "7cf369ba7b7cac026b693f560d991da91ddc201725848ab621c355488f9aca8c"
)


class GateError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def execute(
    name: str,
    command: list[str],
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    (EVIDENCE / f"{name}.log").write_text(
        "=== command ===\n"
        + shlex.join(command)
        + "\n=== returncode ===\n"
        + str(result.returncode)
        + "\n=== stdout ===\n"
        + result.stdout
        + "\n=== stderr ===\n"
        + result.stderr
    )
    if check and result.returncode:
        raise GateError(f"{name}: rc={result.returncode}")
    return result


def make(name: str, *targets: str) -> subprocess.CompletedProcess[str]:
    return execute(
        name,
        [
            "make",
            "-C",
            str(SOURCE),
            f"O={OUTPUT}",
            "ARCH=dadao",
            f"CC={LLVM_BIN / 'clang'} --target=dadao",
            f"LD={LLVM_BIN / 'ld.lld'}",
            f"AR={LLVM_BIN / 'llvm-ar'}",
            f"NM={LLVM_BIN / 'llvm-nm'}",
            f"OBJCOPY={LLVM_BIN / 'llvm-objcopy'}",
            f"OBJDUMP={LLVM_BIN / 'llvm-objdump'}",
            f"READELF={LLVM_BIN / 'llvm-readelf'}",
            "HOSTCC=cc",
            "HOSTCXX=c++",
            "KCFLAGS=-O0",
            "KBUILD_LDFLAGS=--error-limit=0",
            *targets,
        ],
    )


def component(name: str) -> dict:
    with MANIFEST.open("rb") as stream:
        manifest = tomllib.load(stream)
    for row in manifest["component"]:
        if row["name"] == name:
            return row
    raise GateError(f"manifest component missing: {name}")


def patch_id(payload: str) -> str:
    result = subprocess.run(
        ["git", "patch-id", "--stable"],
        cwd=ROOT,
        text=True,
        input=payload,
        capture_output=True,
    )
    if result.returncode or not result.stdout.strip():
        raise GateError("cannot calculate stable patch-id")
    return result.stdout.split()[0]


def verify_patch_identity() -> list[dict[str, str]]:
    patches = [
        line.strip()
        for line in SERIES.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    expected_names = [name for name, _commit, _patch_id in KL149_PATCHES]
    if patches != expected_names:
        raise GateError(f"KL-149a patch series drifted: {patches}")

    pin = component("linux")["commit"]
    commits = execute(
        "linux-commits",
        ["git", "-C", str(SOURCE), "rev-list", "--reverse", f"{pin}..HEAD"],
    ).stdout.splitlines()
    if len(commits) != len(patches):
        raise GateError(
            f"Linux commit/patch count mismatch: {len(commits)} != {len(patches)}"
        )

    rows: list[dict[str, str]] = []
    for index, (commit_hash, patch_name) in enumerate(
        zip(commits, patches, strict=True)
    ):
        patch_path = SERIES.parent / patch_name
        if not patch_path.is_file():
            raise GateError(f"missing patch payload: {patch_name}")
        commit_mail = execute(
            f"commit-{index + 1:04d}",
            ["git", "-C", str(SOURCE), "show", "--pretty=email", commit_hash],
        ).stdout
        commit_id = patch_id(commit_mail)
        payload_id = patch_id(patch_path.read_text())
        if commit_id != payload_id:
            raise GateError(
                f"patch payload drift: {patch_name}: "
                f"{payload_id} != {commit_id}"
            )
        if index < len(KL149_PATCHES):
            expected_commit = KL149_PATCHES[index][1]
            expected_id = KL149_PATCHES[index][2]
            if commit_hash != expected_commit:
                raise GateError(
                    f"frozen commit drift: {patch_name}: "
                    f"{commit_hash} != {expected_commit}"
                )
            if payload_id != expected_id:
                raise GateError(
                    f"frozen patch-id drift: {patch_name}: "
                    f"{payload_id} != {expected_id}"
                )
        rows.append(
            {
                "patch": patch_name,
                "commit": commit_hash,
                "patch_id": payload_id,
            }
        )
    (EVIDENCE / "patch-identity.json").write_text(
        json.dumps(rows, indent=2, sort_keys=True) + "\n"
    )
    return rows


def verify_elf_and_image() -> dict[str, object]:
    vmlinux = OUTPUT / "vmlinux"
    image = OUTPUT / "arch" / "dadao" / "boot" / "Image"
    for path in (vmlinux, image):
        if not path.is_file() or path.stat().st_size == 0:
            raise GateError(f"missing or empty output: {path}")

    readobj = execute(
        "vmlinux-readobj",
        [str(LLVM_BIN / "llvm-readobj"), "--file-headers", str(vmlinux)],
    ).stdout
    required = (
        "Class: 64-bit (0x2)",
        "DataEncoding: BigEndian (0x2)",
        "Type: Executable (0x2)",
        "Machine: 0xDA0",
        "Entry: 0x80000000",
    )
    missing = [value for value in required if value not in readobj]
    if missing:
        raise GateError(f"vmlinux ELF markers missing: {missing}")

    undefined = execute(
        "vmlinux-undefined",
        [str(LLVM_BIN / "llvm-nm"), "-u", str(vmlinux)],
    ).stdout.strip()
    if undefined:
        raise GateError(f"vmlinux has undefined symbols:\n{undefined}")

    symbols = execute(
        "vmlinux-symbols",
        [str(LLVM_BIN / "llvm-nm"), "-n", str(vmlinux)],
    ).stdout
    start_rows = [
        row for row in symbols.splitlines() if row.rstrip().endswith(" _start")
    ]
    if len(start_rows) != 1 or start_rows[0].split()[0] != "0000000080000000":
        raise GateError(f"unexpected _start symbol: {start_rows}")
    end_rows = [
        row for row in symbols.splitlines() if row.rstrip().endswith(" _end")
    ]
    if len(end_rows) != 1:
        raise GateError(f"unexpected _end symbol: {end_rows}")
    end_address = int(end_rows[0].split()[0], 16)

    head = EVIDENCE / "head-text.bin"
    execute(
        "head-text",
        [
            str(LLVM_BIN / "llvm-objcopy"),
            "-O",
            "binary",
            "--only-section=.head.text",
            str(vmlinux),
            str(head),
        ],
    )
    head_bytes = head.read_bytes()
    image_bytes = image.read_bytes()
    if not head_bytes or not image_bytes.startswith(head_bytes):
        raise GateError("flat Image prefix does not match linked .head.text")
    if len(image_bytes) > RAM_SIZE:
        raise GateError(f"Image exceeds QEMU RAM: {len(image_bytes)} > {RAM_SIZE}")
    if RAM_BASE + len(image_bytes) > MARKER_ADDR:
        raise GateError("flat Image overlaps the reserved marker/scratch window")
    if not (end_address <= MARKER_ADDR < STACK_TOP < SCRATCH_END):
        raise GateError(
            "linked _end, marker, early stack, and scratch end overlap/order drift"
        )

    config = (OUTPUT / ".config").read_text()
    for option in (
        "CONFIG_DADAO_K3_O0_LINK_COMPAT=y",
        "CONFIG_DADAO_K3_EARLY_MARKER=y",
        "# CONFIG_KALLSYMS is not set",
    ):
        if option not in config:
            raise GateError(f"required KL-149a config missing: {option}")

    return {
        "vmlinux": str(vmlinux),
        "vmlinux_size": vmlinux.stat().st_size,
        "vmlinux_sha256": sha256(vmlinux),
        "image": str(image),
        "image_size": image.stat().st_size,
        "image_sha256": sha256(image),
        "head_size": len(head_bytes),
        "head_sha256": sha256(head),
        "entry": f"0x{RAM_BASE:016x}",
        "end": f"0x{end_address:016x}",
    }


def qmp_roundtrip(stream, request: dict) -> object:
    stream.write(json.dumps(request) + "\n")
    stream.flush()
    while True:
        line = stream.readline()
        if not line:
            raise GateError("QMP connection closed")
        reply = json.loads(line)
        if "error" in reply:
            raise GateError(f"QMP error: {reply['error']}")
        if "return" in reply:
            return reply["return"]


def dump_oracle(stream, marker_path: Path) -> tuple[int, int]:
    marker_path.unlink(missing_ok=True)
    result = qmp_roundtrip(
        stream,
        {
            "execute": "human-monitor-command",
            "arguments": {
                "command-line": f'pmemsave {MARKER_ADDR:#x} 16 "{marker_path}"'
            },
        },
    )
    if result:
        raise GateError(f"QEMU pmemsave failed: {result}")
    payload = marker_path.read_bytes()
    if len(payload) != 16:
        raise GateError(f"QEMU oracle read size is {len(payload)}")
    return struct.unpack(">QQ", payload)


def qemu_identity() -> dict[str, str]:
    if not QEMU.is_file() or not os.access(QEMU, os.X_OK):
        raise GateError(f"QEMU binary missing or not executable: {QEMU}")
    qemu_head = execute(
        "qemu-head", ["git", "-C", str(QEMU_SOURCE), "rev-parse", "HEAD"]
    ).stdout.strip()
    if qemu_head != QEMU_EXPECTED_HEAD:
        raise GateError(f"QEMU HEAD drift: {qemu_head} != {QEMU_EXPECTED_HEAD}")
    dirty = execute(
        "qemu-status",
        ["git", "-C", str(QEMU_SOURCE), "status", "--porcelain=v1"],
    ).stdout.strip()
    if dirty:
        raise GateError(f"QEMU source worktree dirty:\n{dirty}")
    binary_hash = sha256(QEMU)
    if binary_hash != QEMU_EXPECTED_SHA256:
        raise GateError(
            f"QEMU binary hash drift: {binary_hash} != {QEMU_EXPECTED_SHA256}"
        )
    version = execute("qemu-version", [str(QEMU), "--version"]).stdout.splitlines()
    version_line = version[0] if version else ""
    if QEMU_EXPECTED_HEAD[:7] not in version_line:
        raise GateError(
            f"QEMU version does not bind expected source HEAD: {version_line}"
        )
    return {
        "qemu": str(QEMU.resolve()),
        "qemu_sha256": binary_hash,
        "qemu_head": qemu_head,
        "qemu_version": version_line,
    }


def verify_qemu(
    image: Path,
    rom: Path,
    *,
    expect_marker: bool,
    timeout: float = 30.0,
) -> dict[str, object]:
    if MARKER_BYTES in rom.read_bytes():
        raise GateError("handoff ROM contains the kernel marker value")

    transport = tempfile.TemporaryDirectory(prefix="kl149a_qmp_")
    qmp_path = Path(transport.name) / "qmp.sock"
    marker_path = Path(transport.name) / "marker.bin"
    qemu_log = EVIDENCE / (
        "qemu-positive-runtime.log"
        if expect_marker
        else "qemu-wrong-mode-runtime.log"
    )
    command = [
        str(QEMU),
        "-M",
        "dadao-m1",
        "-S",
        "-global",
        "dadao-cpu.cfx-smon-real=on",
        "-bios",
        str(rom),
        "-kernel",
        str(image),
        "-display",
        "none",
        "-serial",
        "none",
        "-no-shutdown",
        "-qmp",
        f"unix:{qmp_path},server,nowait",
    ]
    proc = subprocess.Popen(
        command, cwd=ROOT, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    marker = None
    status = None
    greeting = ""
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        deadline = time.time() + min(timeout, 10.0)
        while True:
            try:
                sock.connect(str(qmp_path))
                break
            except OSError:
                if proc.poll() is not None:
                    raise GateError(
                        f"QEMU exited before QMP connect: rc={proc.returncode}"
                    )
                if time.time() >= deadline:
                    raise GateError("QMP connect timeout")
                time.sleep(0.02)
        sock.settimeout(3.0)
        stream = sock.makefile("rw", encoding="utf-8", newline="\n")
        greeting = stream.readline()
        if not greeting:
            raise GateError("QMP greeting missing")
        qmp_roundtrip(stream, {"execute": "qmp_capabilities"})
        initial_marker, initial_failure = dump_oracle(stream, marker_path)
        if initial_marker != 0 or initial_failure != 0:
            raise GateError(
                "oracle scratch is nonzero before CPU start: "
                f"marker={initial_marker:#x} failure={initial_failure:#x}"
            )
        qmp_roundtrip(stream, {"execute": "cont"})

        deadline = time.time() + timeout
        while time.time() < deadline:
            if proc.poll() is not None:
                raise GateError(
                    f"QEMU exited before marker: rc={proc.returncode}"
                )
            marker, failure = dump_oracle(stream, marker_path)
            if marker == MARKER_VALUE:
                break
            status = qmp_roundtrip(stream, {"execute": "query-status"})
            if status.get("status") == "shutdown":
                break
            time.sleep(0.05)
        else:
            raise GateError(
                f"guest marker timeout: last=0x{(marker or 0):016x}"
            )

        status = qmp_roundtrip(stream, {"execute": "query-status"})
        if expect_marker:
            if marker != MARKER_VALUE:
                raise GateError(
                    f"supervisor marker missing: last=0x{(marker or 0):016x}"
                )
            if status.get("status") != "running" or not status.get("running"):
                raise GateError(f"QEMU not running after marker: {status}")
            if failure != 0:
                raise GateError(
                    f"positive ROM authored failure word: {failure:#x}"
                )
        else:
            if marker != 0:
                raise GateError(
                    f"wrong-mode negative ROM changed PASS marker: {marker:#x}"
                )
            if failure != FAILURE_VALUE:
                raise GateError(
                    "wrong-mode shutdown did not reach mode assertion: "
                    f"failure={failure:#x}"
                )
            if status.get("status") != "shutdown" or status.get("running"):
                raise GateError(
                    f"wrong-mode negative ROM did not fail closed: {status}"
                )
        try:
            qmp_roundtrip(stream, {"execute": "quit"})
        except (GateError, OSError, TimeoutError):
            pass
        sock.close()
    finally:
        if proc.poll() is None:
            proc.kill()
        stdout, stderr = proc.communicate()
        qemu_log.write_text(
            "=== command ===\n"
            + shlex.join(command)
            + "\n=== greeting ===\n"
            + greeting
            + "\n=== stdout ===\n"
            + stdout
            + "\n=== stderr ===\n"
            + stderr
        )
        transport.cleanup()

    return {
        "initial_marker": f"0x{initial_marker:016x}",
        "initial_failure": f"0x{initial_failure:016x}",
        "marker_address": f"0x{MARKER_ADDR:016x}",
        "marker_value": f"0x{marker:016x}",
        "failure_value": f"0x{failure:016x}",
        "expected_marker": expect_marker,
        "qmp_status": status,
    }


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    execute(
        "kl148a-prerequisite",
        [sys.executable, str(ROOT / "tests/scripts/run_kl148a_linux_compile.py")],
    )
    patch_rows = verify_patch_identity()
    linux_dirty = execute(
        "linux-status-before",
        ["git", "-C", str(SOURCE), "status", "--porcelain=v1"],
    ).stdout.strip()
    if linux_dirty:
        raise GateError(f"Linux worktree dirty before build:\n{linux_dirty}")

    make("mrproper", "mrproper")
    make("defconfig", "dadao_defconfig")
    make("olddefconfig", "olddefconfig")
    build = make("image", "Image")
    diagnostics = build.stdout + build.stderr
    found = []
    if "shift count is negative" in diagnostics:
        found.append("shift count is negative")
    if any(
        "ELF_CLASS" in line and "is not defined" in line
        for line in diagnostics.splitlines()
    ):
        found.append("ELF_CLASS is not defined")
    if found:
        raise GateError(f"forbidden build diagnostics present: {found}")
    image_result = verify_elf_and_image()

    rom = EVIDENCE / "kl149a-linux-handoff.bin"
    execute(
        "handoff-rom",
        [
            sys.executable,
            str(ROOT / "tests/scripts/gen_kl149a_linux_handoff.py"),
            str(rom),
        ],
    )
    if sha256(rom) != ROM_EXPECTED_SHA256:
        raise GateError("positive handoff ROM identity drift")
    negative_rom = EVIDENCE / "kl149a-linux-handoff-wrong-mode.bin"
    execute(
        "handoff-rom-negative",
        [
            sys.executable,
            str(ROOT / "tests/scripts/gen_kl149a_linux_handoff.py"),
            str(negative_rom),
            "--previous-mode",
            "3",
        ],
    )
    if sha256(negative_rom) != NEGATIVE_ROM_EXPECTED_SHA256:
        raise GateError("negative handoff ROM identity drift")
    identity = qemu_identity()
    qemu_result = verify_qemu(
        Path(image_result["image"]), rom, expect_marker=True
    )
    negative_result = verify_qemu(
        Path(image_result["image"]),
        negative_rom,
        expect_marker=False,
        timeout=10.0,
    )

    dirty = execute(
        "linux-status",
        ["git", "-C", str(SOURCE), "status", "--porcelain=v1"],
    ).stdout.strip()
    if dirty:
        raise GateError(f"Linux worktree dirty after gate:\n{dirty}")

    summary = {
        "task": "KL-149a",
        "result": "PASS",
        "build_flags": {"ARCH": "dadao", "KCFLAGS": "-O0"},
        "patches": patch_rows,
        "rom": {
            "path": str(rom),
            "size": rom.stat().st_size,
            "sha256": sha256(rom),
        },
        "linux": image_result,
        "runtime": qemu_result,
        "negative_runtime": negative_result,
        "qemu_identity": identity,
    }
    (EVIDENCE / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    print("PASS: KL-149a Linux linked Image and QEMU reset handoff")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GateError as exc:
        raise SystemExit(f"KL-149a FAIL: {exc}") from exc
