#!/usr/bin/env python3
"""KL-150a fail-closed M1 early-console and Linux boot-progress gate."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LINUX_SOURCE = ROOT / ".work" / "source" / "linux"
LINUX_OUTPUT = ROOT / ".work" / "build" / "linux"
NO_CONSOLE_OUTPUT = ROOT / ".work" / "build" / "linux-kl150a-no-console"
LLVM_BIN = ROOT / ".work" / "build" / "llvm" / "bin"
QEMU_SOURCE = ROOT / ".work" / "source" / "qemu"
QEMU_BUILD = QEMU_SOURCE / "build"
QEMU = QEMU_BUILD / "qemu-system-dadao"
EVIDENCE = ROOT / ".work" / "evidence" / "kl150a-linux-early-console"
LINUX_SERIES = ROOT / "components" / "linux" / "patches" / "series"
QEMU_SERIES = ROOT / "components" / "qemu" / "patches" / "series"
MANIFEST = ROOT / "manifests" / "components.lock.toml"
KL149_SUMMARY = (
    ROOT / ".work" / "evidence" / "kl149a-linux-link-boot" / "summary.json"
)

LINUX_PATCHES = (
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
    (
        "0006-dadao-add-M1-early-console-and-boot-progress.patch",
        "fdfdb9ca682c8839a7d59595a1b9d5fc9c46da5b",
        "44ff19d0599cc24b3715e88f587ca3a4e9b3dc87",
    ),
    (
        "0007-dadao-harden-K3-O0-early-boot-progress.patch",
        "06c3d571a8ae249e451dc4f2151e6bfd8e8a5873",
        "d4a778294298992ca7255c96972b24d72c05aea0",
    ),
)

QEMU_PARENT = "eee0933b064014f3ab305eaa275883f025223d53"
QEMU_PATCHES = (
    (
        "0037-hw-dadao-add-M1-test-machine-debug-console.patch",
        "247344a110fa99e18e66b4e2ce373e9ddb96d8f7",
        "1e8d1730f84776a0e50db4f77afe14d2c3ac9c58",
    ),
    (
        "0038-target-dadao-log-precise-exception-state.patch",
        "dfc7842229c139cc606141b82845ecf20086e657",
        "b9bb21ea84eac178d7957cfa2faa4e793e9f101e",
    ),
)
QEMU_HEAD = QEMU_PATCHES[-1][1]
QEMU_SHA256 = "2326a4b69f3f8dc3e0c1b5c2f335d0df4c71182a481dd7f6071e4a38f6ac8240"

KL149_SUMMARY_SHA256 = (
    "5bd8d9f3fb08d3ffcacc3169602b3c8c02add66f1ded827f24af6734a73117e0"
)
ROM_SHA256 = "46c1e4af50162dd9be1adb82eb9223a6902f0629a0a4c9d3f18822aee5e536c7"
WRONG_MODE_ROM_SHA256 = (
    "7cf369ba7b7cac026b693f560d991da91ddc201725848ab621c355488f9aca8c"
)

RAM_BASE = 0x80000000
RAM_SIZE = 0x08000000
SCRATCH_BASE = 0x87FD0000
STACK_TOP = 0x87FF0000
SCRATCH_END = 0x88000000
ORACLE_SIZE = 40

MARKER_VALUE = 0x4B4C313439414845
FAILURE_VALUE = 0x4B4C313439424144
PROGRESS_VALUES = (
    0x4B4C313530534145,  # KL150SAE: entered setup_arch
    0x4B4C313530534144,  # KL150SAD: setup_arch memory setup done
    0x4B4C3135304D494E,  # KL150MIN: entered mem_init
)
PROGRESS_NAMES = ("setup_arch_enter", "setup_arch_done", "mem_init_enter")
ANCHORS = (
    b"DADAO M1 test-machine early console online\n",
    b"Linux version 5.4.0",
    b"DADAO M1 setup_arch complete\n",
)


class GateError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def execute(
    name: str,
    command: list[str],
    *,
    cwd: Path = ROOT,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    (EVIDENCE / f"{name}.log").write_text(
        "=== command ===\n"
        + shlex.join(command)
        + "\n=== cwd ===\n"
        + str(cwd)
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


def make(
    name: str, output: Path, *targets: str
) -> subprocess.CompletedProcess[str]:
    return execute(
        name,
        [
            "make",
            "-C",
            str(LINUX_SOURCE),
            f"O={output}",
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


def component_pin(name: str) -> str:
    with MANIFEST.open("rb") as stream:
        manifest = tomllib.load(stream)
    for component in manifest["component"]:
        if component["name"] == name:
            return component["commit"]
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


def series_names(series: Path) -> list[str]:
    return [
        line.strip()
        for line in series.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def verify_queue(
    name: str, source: Path, series: Path
) -> list[dict[str, str]]:
    patches = series_names(series)
    commits = execute(
        f"{name}-commits",
        [
            "git",
            "-C",
            str(source),
            "rev-list",
            "--reverse",
            f"{component_pin(name)}..HEAD",
        ],
    ).stdout.splitlines()
    if len(commits) != len(patches):
        raise GateError(
            f"{name} commit/patch count mismatch: "
            f"{len(commits)} != {len(patches)}"
        )

    rows: list[dict[str, str]] = []
    for index, (commit, patch_name) in enumerate(
        zip(commits, patches, strict=True)
    ):
        patch_path = series.parent / patch_name
        if not patch_path.is_file():
            raise GateError(f"{name} patch missing: {patch_name}")
        commit_mail = execute(
            f"{name}-commit-{index + 1:04d}",
            ["git", "-C", str(source), "show", "--pretty=email", commit],
        ).stdout
        commit_id = patch_id(commit_mail)
        payload_id = patch_id(patch_path.read_text())
        if commit_id != payload_id:
            raise GateError(
                f"{name} patch payload drift: {patch_name}: "
                f"{payload_id} != {commit_id}"
            )
        rows.append(
            {"patch": patch_name, "commit": commit, "patch_id": payload_id}
        )
    return rows


def verify_kl149_frozen_evidence() -> dict[str, object]:
    if not KL149_SUMMARY.is_file():
        raise GateError(f"KL-149a summary missing: {KL149_SUMMARY}")
    if sha256(KL149_SUMMARY) != KL149_SUMMARY_SHA256:
        raise GateError("KL-149a frozen summary identity drift")
    summary = json.loads(KL149_SUMMARY.read_text())
    required = {
        ("task",): "KL-149a",
        ("result",): "PASS",
        ("build_flags", "KCFLAGS"): "-O0",
        ("qemu_identity", "qemu_head"): QEMU_PARENT,
        ("qemu_identity", "qemu_sha256"):
            "97bfa45fbb15c1f2c52dd7ddeec555da4b3d8a447c47cba3bdf862db5a76fcd8",
        ("runtime", "marker_value"): f"0x{MARKER_VALUE:016x}",
        ("runtime", "failure_value"): "0x0000000000000000",
        ("runtime", "qmp_status", "status"): "running",
        ("negative_runtime", "marker_value"): "0x0000000000000000",
        ("negative_runtime", "failure_value"): f"0x{FAILURE_VALUE:016x}",
        ("negative_runtime", "qmp_status", "status"): "shutdown",
    }
    for keys, expected in required.items():
        value: object = summary
        for key in keys:
            value = value[key]  # type: ignore[index]
        if value != expected:
            raise GateError(
                f"KL-149a evidence drift at {'.'.join(keys)}: "
                f"{value!r} != {expected!r}"
            )
    frozen_patches = [tuple(row.values()) for row in summary["patches"]]
    expected_patches = [
        (name, commit, payload_id)
        for name, commit, payload_id in LINUX_PATCHES[:5]
    ]
    normalized = [
        (row["patch"], row["commit"], row["patch_id"])
        for row in summary["patches"]
    ]
    if normalized != expected_patches or len(frozen_patches) != 5:
        raise GateError("KL-149a frozen Linux patch identities drifted")
    return {
        "path": str(KL149_SUMMARY),
        "sha256": sha256(KL149_SUMMARY),
        "qemu_head": summary["qemu_identity"]["qemu_head"],
        "linux_patches": normalized,
    }


def verify_component_identities() -> dict[str, object]:
    for source_name, source in (
        ("Linux", LINUX_SOURCE),
        ("QEMU", QEMU_SOURCE),
    ):
        dirty = execute(
            f"{source_name.lower()}-status-before",
            ["git", "-C", str(source), "status", "--porcelain=v1"],
        ).stdout.strip()
        if dirty:
            raise GateError(f"{source_name} source worktree dirty:\n{dirty}")

    linux_rows = verify_queue("linux", LINUX_SOURCE, LINUX_SERIES)
    expected_linux_names = [row[0] for row in LINUX_PATCHES]
    if series_names(LINUX_SERIES) != expected_linux_names:
        raise GateError("Linux KL-150a series names/order drifted")
    for row, expected in zip(linux_rows, LINUX_PATCHES, strict=True):
        if (
            row["patch"],
            row["commit"],
            row["patch_id"],
        ) != expected:
            raise GateError(f"Linux frozen identity drift: {row}")

    qemu_patches = series_names(QEMU_SERIES)
    qemu_commits = execute(
        "qemu-commits",
        [
            "git",
            "-C",
            str(QEMU_SOURCE),
            "rev-list",
            "--reverse",
            f"{component_pin('qemu')}..HEAD",
        ],
    ).stdout.splitlines()
    if len(qemu_patches) != 38 or len(qemu_commits) != 38:
        raise GateError(
            "QEMU patch/commit count drifted: "
            f"{len(qemu_patches)}/{len(qemu_commits)}"
        )
    qemu_kl150a = []
    for offset, (patch_name, commit, expected_id) in enumerate(
        QEMU_PATCHES, start=1
    ):
        patch_path = QEMU_SERIES.parent / patch_name
        commit_mail = execute(
            f"qemu-kl150a-commit-{offset}",
            ["git", "-C", str(QEMU_SOURCE), "show", "--pretty=email", commit],
        ).stdout
        payload_id = patch_id(patch_path.read_text())
        row = {
            "patch": qemu_patches[-len(QEMU_PATCHES) + offset - 1],
            "commit": qemu_commits[-len(QEMU_PATCHES) + offset - 1],
            "patch_id": payload_id,
        }
        expected = {
            "patch": patch_name,
            "commit": commit,
            "patch_id": expected_id,
        }
        if patch_id(commit_mail) != payload_id:
            raise GateError(
                f"QEMU KL-150a commit/patch payload drift: {patch_name}"
            )
        if row != expected:
            raise GateError(f"QEMU KL-150a identity drift: {row}")
        qemu_kl150a.append(row)
    parent = execute(
        "qemu-kl150a-parent",
        [
            "git",
            "-C",
            str(QEMU_SOURCE),
            "rev-parse",
            f"{QEMU_PATCHES[0][1]}^",
        ],
    ).stdout.strip()
    if parent != QEMU_PARENT:
        raise GateError(f"QEMU KL-149a parent drift: {parent}")
    return {
        "linux": linux_rows,
        "qemu": {
            "baseline": component_pin("qemu"),
            "kl149_parent": parent,
            "patch_count": len(qemu_patches),
            "commit_count": len(qemu_commits),
            "kl150a": qemu_kl150a,
        },
    }


def rebuild_and_verify_qemu() -> dict[str, str]:
    execute(
        "qemu-rebuild",
        ["ninja", "-C", str(QEMU_BUILD), "qemu-system-dadao"],
        cwd=QEMU_SOURCE,
    )
    head = execute(
        "qemu-head", ["git", "-C", str(QEMU_SOURCE), "rev-parse", "HEAD"]
    ).stdout.strip()
    if head != QEMU_HEAD:
        raise GateError(f"QEMU HEAD drift: {head} != {QEMU_HEAD}")
    binary_hash = sha256(QEMU)
    if binary_hash != QEMU_SHA256:
        raise GateError(
            f"rebuilt QEMU hash drift: {binary_hash} != {QEMU_SHA256}"
        )
    version_lines = execute("qemu-version", [str(QEMU), "--version"]).stdout
    version = version_lines.splitlines()[0] if version_lines else ""
    if QEMU_HEAD[:7] not in version:
        raise GateError(f"QEMU version does not bind final HEAD: {version}")
    return {
        "path": str(QEMU),
        "head": head,
        "sha256": binary_hash,
        "version": version,
    }


def reject_forbidden_diagnostics(result: subprocess.CompletedProcess[str]) -> None:
    diagnostics = result.stdout + result.stderr
    found = []
    if "shift count is negative" in diagnostics:
        found.append("shift count is negative")
    if any(
        "ELF_CLASS" in line and "is not defined" in line
        for line in diagnostics.splitlines()
    ):
        found.append("ELF_CLASS is not defined")
    if found:
        raise GateError(f"forbidden Linux build diagnostics: {found}")


def verify_image(output: Path, *, expect_console: bool) -> dict[str, object]:
    vmlinux = output / "vmlinux"
    image = output / "arch" / "dadao" / "boot" / "Image"
    for path in (vmlinux, image):
        if not path.is_file() or path.stat().st_size == 0:
            raise GateError(f"missing or empty Linux output: {path}")

    headers = execute(
        f"{output.name}-vmlinux-readobj",
        [str(LLVM_BIN / "llvm-readobj"), "--file-headers", str(vmlinux)],
    ).stdout
    required = (
        "Class: 64-bit (0x2)",
        "DataEncoding: BigEndian (0x2)",
        "Type: Executable (0x2)",
        "Machine: 0xDA0",
        "Entry: 0x80000000",
    )
    missing = [marker for marker in required if marker not in headers]
    if missing:
        raise GateError(f"vmlinux ELF markers missing: {missing}")
    undefined = execute(
        f"{output.name}-vmlinux-undefined",
        [str(LLVM_BIN / "llvm-nm"), "-u", str(vmlinux)],
    ).stdout.strip()
    if undefined:
        raise GateError(f"vmlinux has undefined symbols:\n{undefined}")
    symbols = execute(
        f"{output.name}-vmlinux-symbols",
        [str(LLVM_BIN / "llvm-nm"), "-n", str(vmlinux)],
    ).stdout.splitlines()
    end_rows = [line for line in symbols if line.rstrip().endswith(" _end")]
    if len(end_rows) != 1:
        raise GateError(f"unexpected _end symbols: {end_rows}")
    end = int(end_rows[0].split()[0], 16)
    image_bytes = image.read_bytes()
    if RAM_BASE + len(image_bytes) > SCRATCH_BASE:
        raise GateError("flat Image overlaps KL-149/KL-150 scratch")
    if not (
        end <= SCRATCH_BASE
        < SCRATCH_BASE + ORACLE_SIZE
        < STACK_TOP
        < SCRATCH_END
    ):
        raise GateError("ELF/scratch/progress/stack layout overlaps")
    config = (output / ".config").read_text()
    expected_config = (
        "CONFIG_DADAO_M1_DEBUG_CONSOLE=y"
        if expect_console
        else "# CONFIG_DADAO_M1_DEBUG_CONSOLE is not set"
    )
    for option in (
        "CONFIG_DADAO_K3_O0_LINK_COMPAT=y",
        "CONFIG_DADAO_K3_EARLY_MARKER=y",
        expected_config,
    ):
        if option not in config:
            raise GateError(f"required Linux config missing: {option}")
    expected_anchor_counts = (
        (1, 1, 1) if expect_console else (0, 1, 0)
    )
    for anchor, expected_count in zip(
        ANCHORS, expected_anchor_counts, strict=True
    ):
        count = image_bytes.count(anchor)
        if count != expected_count:
            raise GateError(
                f"Image anchor identity drift for {anchor!r}: "
                f"{count} != {expected_count}"
            )
    return {
        "vmlinux": str(vmlinux),
        "vmlinux_size": vmlinux.stat().st_size,
        "vmlinux_sha256": sha256(vmlinux),
        "image": str(image),
        "image_size": image.stat().st_size,
        "image_sha256": sha256(image),
        "end": f"0x{end:016x}",
        "debug_console": expect_console,
    }


def verify_progress_source_contract() -> dict[str, str]:
    header = LINUX_SOURCE / "arch/dadao/include/asm/dadao-m1.h"
    setup = LINUX_SOURCE / "arch/dadao/kernel/setup.c"
    mem_init = LINUX_SOURCE / "arch/dadao/mm/init.c"
    early_console = LINUX_SOURCE / "arch/dadao/kernel/early-console.c"
    head = LINUX_SOURCE / "arch/dadao/kernel/head.S"
    required = {
        header: (
            "DADAO_M1_DEBUG_CONSOLE_TX\t0x10001000UL",
            "DADAO_M1_PROGRESS_SETUP_ENTER\t0x87fd0010UL",
            "DADAO_M1_PROGRESS_SETUP_DONE\t0x87fd0018UL",
            "DADAO_M1_PROGRESS_MEM_INIT\t0x87fd0020UL",
        ),
        setup: (
            "DADAO_M1_PROGRESS_SETUP_ENTER_VALUE",
            "DADAO_M1_PROGRESS_SETUP_DONE_VALUE",
        ),
        mem_init: ("DADAO_M1_PROGRESS_MEM_INIT_VALUE",),
        early_console: (
            "DADAO M1 test-machine early console online",
            "DADAO M1 setup_arch complete",
            "register_console(&dadao_m1_debug_console)",
            "dadao_m1_debug_console_setup_done",
        ),
    }
    for path, markers in required.items():
        text = path.read_text()
        for marker in markers:
            if text.count(marker) != 1:
                raise GateError(
                    f"source stage marker drift: {path}: {marker!r}"
                )
    setup_text = setup.read_text()
    setup_start = setup_text.find("void __init setup_arch(char **cmdline_p)")
    setup_end = setup_text.find("\n}\n", setup_start)
    if setup_start < 0 or setup_end < 0:
        raise GateError("cannot isolate setup_arch source body")
    setup_body = setup_text[setup_start:setup_end]
    setup_order = (
        setup_body.find("DADAO_M1_PROGRESS_SETUP_ENTER_VALUE"),
        setup_body.find("paging_init();"),
        setup_body.find("DADAO_M1_PROGRESS_SETUP_DONE_VALUE"),
    )
    if min(setup_order) < 0 or tuple(sorted(setup_order)) != setup_order:
        raise GateError(
            "setup_arch progress source order drifted: "
            f"enter/paging/done={setup_order}"
        )

    mem_text = mem_init.read_text()
    mem_start = mem_text.find("void __init mem_init(void)")
    mem_end = mem_text.find("\n}\n", mem_start)
    if mem_start < 0 or mem_end < 0:
        raise GateError("cannot isolate mem_init source body")
    mem_body = mem_text[mem_start:mem_end]
    mem_order = (
        mem_body.find("DADAO_M1_PROGRESS_MEM_INIT_VALUE"),
        mem_body.find("memblock_free_all();"),
    )
    if min(mem_order) < 0 or tuple(sorted(mem_order)) != mem_order:
        raise GateError(
            "mem_init progress source order drifted: "
            f"enter/free={mem_order}"
        )
    head_text = head.read_text()
    for value in ("4b4c313530534145", "4b4c313530534144", "4b4c3135304d494e"):
        if value in head_text.lower():
            raise GateError("head.S pre-fills a KL-150a progress value")
    return {
        "setup_arch_enter": str(setup),
        "setup_arch_done": str(setup),
        "mem_init_enter": str(mem_init),
        "console": str(early_console),
        "contract": str(header),
    }


def build_linux_images() -> tuple[dict[str, object], dict[str, object]]:
    make("linux-mrproper", LINUX_OUTPUT, "mrproper")
    make("linux-defconfig", LINUX_OUTPUT, "dadao_defconfig")
    make("linux-olddefconfig", LINUX_OUTPUT, "olddefconfig")
    positive_build = make("linux-image", LINUX_OUTPUT, "Image")
    reject_forbidden_diagnostics(positive_build)
    positive = verify_image(LINUX_OUTPUT, expect_console=True)

    shutil.rmtree(NO_CONSOLE_OUTPUT, ignore_errors=True)
    make("linux-no-console-defconfig", NO_CONSOLE_OUTPUT, "dadao_defconfig")
    execute(
        "linux-no-console-disable",
        [
            str(LINUX_SOURCE / "scripts/config"),
            "--file",
            str(NO_CONSOLE_OUTPUT / ".config"),
            "--disable",
            "DADAO_M1_DEBUG_CONSOLE",
        ],
    )
    make(
        "linux-no-console-olddefconfig",
        NO_CONSOLE_OUTPUT,
        "olddefconfig",
    )
    negative_build = make(
        "linux-no-console-image", NO_CONSOLE_OUTPUT, "Image"
    )
    reject_forbidden_diagnostics(negative_build)
    no_console = verify_image(NO_CONSOLE_OUTPUT, expect_console=False)
    if positive["image_sha256"] == no_console["image_sha256"]:
        raise GateError("console-disabled Image is not an independent mutation")
    return positive, no_console


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


def dump_oracle(stream, output: Path) -> bytes:
    output.unlink(missing_ok=True)
    result = qmp_roundtrip(
        stream,
        {
            "execute": "human-monitor-command",
            "arguments": {
                "command-line":
                    f'pmemsave {SCRATCH_BASE:#x} {ORACLE_SIZE} "{output}"'
            },
        },
    )
    if result:
        raise GateError(f"QEMU pmemsave failed: {result}")
    payload = output.read_bytes()
    if len(payload) != ORACLE_SIZE:
        raise GateError(f"QEMU oracle size drift: {len(payload)}")
    return payload


def decode_oracle(payload: bytes) -> tuple[int, int, int, int, int]:
    return struct.unpack(">QQQQQ", payload)


def progress_is_ordered(words: tuple[int, int, int]) -> bool:
    seen_zero = False
    for actual, expected in zip(words, PROGRESS_VALUES, strict=True):
        if actual == 0:
            seen_zero = True
        elif actual != expected or seen_zero:
            return False
    return True


def console_verdict(payload: bytes) -> tuple[bool, list[int], list[int]]:
    counts = [payload.count(anchor) for anchor in ANCHORS]
    positions = [payload.find(anchor) for anchor in ANCHORS]
    passed = counts == [1, 1, 1] and positions == sorted(positions)
    return passed, counts, positions


def connect_qmp(proc: subprocess.Popen[bytes], qmp_path: Path, timeout: float):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    deadline = time.monotonic() + timeout
    while True:
        try:
            sock.connect(str(qmp_path))
            break
        except OSError:
            if proc.poll() is not None:
                raise GateError(
                    f"QEMU exited before QMP connect: rc={proc.returncode}"
                )
            if time.monotonic() >= deadline:
                raise GateError("QMP connect timeout")
            time.sleep(0.02)
    sock.settimeout(3.0)
    stream = sock.makefile("rw", encoding="utf-8", newline="\n")
    greeting = stream.readline()
    if not greeting:
        raise GateError("QMP greeting missing")
    qmp_roundtrip(stream, {"execute": "qmp_capabilities"})
    return sock, stream, greeting


def run_progress_guest(
    name: str,
    image: Path,
    rom: Path,
    *,
    serial_mode: str,
    timeout: float = 30.0,
) -> dict[str, object]:
    if serial_mode not in {"file", "none"}:
        raise GateError(f"invalid serial mode: {serial_mode}")
    transport = tempfile.TemporaryDirectory(prefix=f"kl150a_{name}_")
    transport_path = Path(transport.name)
    qmp_path = transport_path / "qmp.sock"
    oracle_path = transport_path / "oracle.bin"
    console_path = EVIDENCE / f"{name}-console.bin"
    console_path.unlink(missing_ok=True)
    trace_path = EVIDENCE / f"{name}-qemu-trace.log"
    trace_path.unlink(missing_ok=True)
    serial_arg = f"file:{console_path}" if serial_mode == "file" else "none"
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
        serial_arg,
        "-no-shutdown",
        "-d",
        "int",
        "-D",
        str(trace_path),
        "-qmp",
        f"unix:{qmp_path},server,nowait",
    ]
    proc = subprocess.Popen(
        command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    greeting = ""
    snapshots: list[dict[str, object]] = []
    marker_running_status: object = None
    final_status: object = None
    initial = b""
    final = b""
    start = time.monotonic()
    try:
        sock, stream, greeting = connect_qmp(proc, qmp_path, 10.0)
        initial = dump_oracle(stream, oracle_path)
        if initial != bytes(ORACLE_SIZE):
            raise GateError(
                f"{name}: scratch nonzero before CPU start: {initial.hex()}"
            )
        (EVIDENCE / f"{name}-progress-initial.bin").write_bytes(initial)
        qmp_roundtrip(stream, {"execute": "cont"})
        last_words: tuple[int, ...] | None = None
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise GateError(
                    f"{name}: QEMU exited before progress: rc={proc.returncode}"
                )
            final = dump_oracle(stream, oracle_path)
            words = decode_oracle(final)
            if words != last_words:
                snapshots.append(
                    {
                        "elapsed_seconds": round(time.monotonic() - start, 6),
                        "words": [f"0x{value:016x}" for value in words],
                    }
                )
                last_words = words
            marker, failure, *progress = words
            if marker == MARKER_VALUE and marker_running_status is None:
                marker_running_status = qmp_roundtrip(
                    stream, {"execute": "query-status"}
                )
                if (
                    marker_running_status.get("status") != "running"
                    or not marker_running_status.get("running")
                ):
                    raise GateError(
                        f"{name}: KL-149 marker not observed running: "
                        f"{marker_running_status}"
                    )
            if marker not in (0, MARKER_VALUE) or failure != 0:
                raise GateError(
                    f"{name}: KL-149 positive oracle regressed: "
                    f"marker={marker:#x} failure={failure:#x}"
                )
            if not progress_is_ordered(tuple(progress)):
                raise GateError(
                    f"{name}: unordered/invalid progress words: {progress}"
                )
            if tuple(progress) == PROGRESS_VALUES:
                break
            status = qmp_roundtrip(stream, {"execute": "query-status"})
            if status.get("status") == "shutdown":
                registers = qmp_roundtrip(
                    stream,
                    {
                        "execute": "human-monitor-command",
                        "arguments": {"command-line": "info registers"},
                    },
                )
                (EVIDENCE / f"{name}-shutdown-registers.log").write_text(
                    str(registers) + "\n"
                )
                raise GateError(
                    f"{name}: shutdown before all progress words: {words}"
                )
            time.sleep(0.02)
        else:
            raise GateError(f"{name}: progress timeout: {snapshots[-1:]}")
        if marker_running_status is None:
            raise GateError(f"{name}: KL-149 marker was never observed")
        time.sleep(0.2)
        final = dump_oracle(stream, oracle_path)
        final_status = qmp_roundtrip(stream, {"execute": "query-status"})
        expected_final = (MARKER_VALUE, 0, *PROGRESS_VALUES)
        final_words = decode_oracle(final)
        if final_words != expected_final:
            raise GateError(
                f"{name}: final oracle regressed after progress: "
                f"{final_words} != {expected_final}"
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
        (EVIDENCE / f"{name}-qemu-runtime.log").write_text(
            "=== command ===\n"
            + shlex.join(command)
            + "\n=== greeting ===\n"
            + greeting
            + "\n=== stdout ===\n"
            + stdout.decode(errors="replace")
            + "\n=== stderr ===\n"
            + stderr.decode(errors="replace")
        )
        transport.cleanup()
    if not final:
        raise GateError(f"{name}: final oracle missing")
    (EVIDENCE / f"{name}-progress-final.bin").write_bytes(final)
    console = console_path.read_bytes() if console_path.exists() else b""
    verdict, counts, positions = console_verdict(console)
    return {
        "command": command,
        "initial_raw_hex": initial.hex(),
        "final_raw_hex": final.hex(),
        "final_words": {
            "kl149_marker": f"0x{decode_oracle(final)[0]:016x}",
            "kl149_failure": f"0x{decode_oracle(final)[1]:016x}",
            **{
                key: f"0x{value:016x}"
                for key, value in zip(
                    PROGRESS_NAMES, decode_oracle(final)[2:], strict=True
                )
            },
        },
        "snapshots": snapshots,
        "kl149_marker_running_status": marker_running_status,
        "post_progress_status": final_status,
        "console_path": str(console_path),
        "console_size": len(console),
        "console_sha256": sha256(console_path) if console_path.exists() else None,
        "console_anchor_counts": counts,
        "console_anchor_positions": positions,
        "console_verdict": verdict,
        "trace_path": str(trace_path),
    }


def run_wrong_mode_guest(image: Path, rom: Path) -> dict[str, object]:
    transport = tempfile.TemporaryDirectory(prefix="kl150a_wrong_mode_")
    transport_path = Path(transport.name)
    qmp_path = transport_path / "qmp.sock"
    oracle_path = transport_path / "oracle.bin"
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
        command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    greeting = ""
    initial = b""
    final = b""
    status: object = None
    try:
        sock, stream, greeting = connect_qmp(proc, qmp_path, 10.0)
        initial = dump_oracle(stream, oracle_path)
        if initial != bytes(ORACLE_SIZE):
            raise GateError("wrong-mode scratch nonzero before CPU start")
        qmp_roundtrip(stream, {"execute": "cont"})
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            final = dump_oracle(stream, oracle_path)
            status = qmp_roundtrip(stream, {"execute": "query-status"})
            if status.get("status") == "shutdown":
                break
            time.sleep(0.02)
        else:
            raise GateError("wrong-mode negative did not shut down")
        words = decode_oracle(final)
        if words != (0, FAILURE_VALUE, 0, 0, 0):
            raise GateError(f"wrong-mode oracle drift: {words}")
        try:
            qmp_roundtrip(stream, {"execute": "quit"})
        except (GateError, OSError, TimeoutError):
            pass
        sock.close()
    finally:
        if proc.poll() is None:
            proc.kill()
        stdout, stderr = proc.communicate()
        (EVIDENCE / "wrong-mode-qemu-runtime.log").write_text(
            "=== command ===\n"
            + shlex.join(command)
            + "\n=== greeting ===\n"
            + greeting
            + "\n=== stdout ===\n"
            + stdout.decode(errors="replace")
            + "\n=== stderr ===\n"
            + stderr.decode(errors="replace")
        )
        transport.cleanup()
    (EVIDENCE / "wrong-mode-progress-final.bin").write_bytes(final)
    return {
        "initial_raw_hex": initial.hex(),
        "final_raw_hex": final.hex(),
        "status": status,
    }


def generate_roms() -> tuple[Path, Path]:
    rom = EVIDENCE / "kl150a-linux-handoff.bin"
    wrong_mode = EVIDENCE / "kl150a-linux-handoff-wrong-mode.bin"
    execute(
        "handoff-rom",
        [
            sys.executable,
            str(ROOT / "tests/scripts/gen_kl149a_linux_handoff.py"),
            str(rom),
        ],
    )
    execute(
        "handoff-rom-wrong-mode",
        [
            sys.executable,
            str(ROOT / "tests/scripts/gen_kl149a_linux_handoff.py"),
            str(wrong_mode),
            "--previous-mode",
            "3",
        ],
    )
    if sha256(rom) != ROM_SHA256:
        raise GateError("positive HBI ROM identity drift")
    if sha256(wrong_mode) != WRONG_MODE_ROM_SHA256:
        raise GateError("wrong-mode HBI ROM identity drift")
    forbidden = b"".join(struct.pack(">Q", value) for value in PROGRESS_VALUES)
    if any(struct.pack(">Q", value) in rom.read_bytes() for value in PROGRESS_VALUES):
        raise GateError("handoff ROM contains a KL-150a progress value")
    if forbidden in rom.read_bytes():
        raise GateError("handoff ROM pre-fills the progress sequence")
    return rom, wrong_mode


def verify_sources_clean_after() -> None:
    for source_name, source in (
        ("Linux", LINUX_SOURCE),
        ("QEMU", QEMU_SOURCE),
    ):
        dirty = execute(
            f"{source_name.lower()}-status-after",
            ["git", "-C", str(source), "status", "--porcelain=v1"],
        ).stdout.strip()
        if dirty:
            raise GateError(
                f"{source_name} source worktree dirty after gate:\n{dirty}"
            )


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    frozen = verify_kl149_frozen_evidence()
    queues = verify_component_identities()
    source_contract = verify_progress_source_contract()
    qemu = rebuild_and_verify_qemu()
    positive_image, no_console_image = build_linux_images()
    rom, wrong_mode_rom = generate_roms()

    positive = run_progress_guest(
        "positive",
        Path(positive_image["image"]),
        rom,
        serial_mode="file",
    )
    if not positive["console_verdict"]:
        raise GateError(
            "positive console anchors are not unique and ordered: "
            f"counts={positive['console_anchor_counts']} "
            f"positions={positive['console_anchor_positions']}"
        )

    no_console = run_progress_guest(
        "no-console-config",
        Path(no_console_image["image"]),
        rom,
        serial_mode="file",
    )
    if no_console["console_verdict"]:
        raise GateError("no-console config mutation passed the console verdict")
    if no_console["console_anchor_counts"] != [0, 0, 0]:
        raise GateError(
            "no-console config emitted a forbidden anchor: "
            f"{no_console['console_anchor_counts']}"
        )

    serial_none = run_progress_guest(
        "serial-none",
        Path(positive_image["image"]),
        rom,
        serial_mode="none",
    )
    if serial_none["console_verdict"]:
        raise GateError("-serial none passed the console verdict")
    if serial_none["console_size"] != 0:
        raise GateError("-serial none unexpectedly produced console bytes")

    wrong_mode = run_wrong_mode_guest(
        Path(positive_image["image"]), wrong_mode_rom
    )
    verify_sources_clean_after()

    counts = {"pass": 4, "fail": 0, "skip": 0}
    summary = {
        "task": "KL-150a",
        "result": "PASS",
        "counts": counts,
        "build_flags": {"ARCH": "dadao", "KCFLAGS": "-O0"},
        "kl149_frozen_evidence": frozen,
        "component_queues": queues,
        "source_stage_contract": source_contract,
        "qemu_identity": qemu,
        "linux_positive": positive_image,
        "linux_no_console": no_console_image,
        "rom": {
            "path": str(rom),
            "sha256": sha256(rom),
            "wrong_mode_path": str(wrong_mode_rom),
            "wrong_mode_sha256": sha256(wrong_mode_rom),
        },
        "positive_runtime": positive,
        "negative_no_console_config": no_console,
        "negative_serial_none": serial_none,
        "negative_wrong_mode": wrong_mode,
    }
    (EVIDENCE / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    print("PASS: KL-150a early console and boot progress (4/4, SKIP=0)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GateError as exc:
        raise SystemExit(f"KL-150a FAIL: {exc}") from exc
