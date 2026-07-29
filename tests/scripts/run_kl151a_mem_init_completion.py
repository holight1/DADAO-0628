#!/usr/bin/env python3
"""KL-151a fail-closed K3 mem_init completion gate."""

from __future__ import annotations

import hashlib
import json
import os
import re
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
RUNNER = Path(__file__).resolve()
LINUX_SOURCE = ROOT / ".work" / "source" / "linux"
LINUX_OUTPUT = ROOT / ".work" / "build" / "linux"
LLVM_BIN = ROOT / ".work" / "build" / "llvm" / "bin"
QEMU_SOURCE = ROOT / ".work" / "source" / "qemu"
QEMU_BUILD = QEMU_SOURCE / "build"
QEMU = QEMU_BUILD / "qemu-system-dadao"
EVIDENCE = ROOT / ".work" / "evidence" / "kl151a-mem-init-completion"
LINUX_SERIES = ROOT / "components" / "linux" / "patches" / "series"
QEMU_SERIES = ROOT / "components" / "qemu" / "patches" / "series"
MANIFEST = ROOT / "manifests" / "components.lock.toml"
KL150_SUMMARY = (
    ROOT / ".work" / "evidence" / "kl150a-linux-early-console" / "summary.json"
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
    (
        "0008-dadao-complete-K3-mem_init-progress.patch",
        "537c61baef6e8ca04cc3d77f6cc9da7856fd6d5e",
        "dd1a1b39796f9ebf27ed6e6f07ba02c22252fcd4",
    ),
    (
        "0009-dadao-widen-page-expected-state-result-for-K3-O0.patch",
        "3e83c7744f5d093eba3a46284416b8409f3d452c",
        "bc9463edbe258e4e3c417c5c9563f00748d57cb2",
    ),
    (
        "0010-dadao-widen-compaction-capture-result-for-K3-O0.patch",
        "8f0b11da8346dc46402974e7a6a8626cff103ed3",
        "80d0cabb985e3d30b95c8cdc61038ea0f494bc0b",
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

KL150_SUMMARY_SHA256 = (
    "844f5ece4ea5b837e7ada01e4b2c841aecf7118ffb18b814de55eb24fe28d83c"
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
ORACLE_SIZE = 48

MARKER_VALUE = 0x4B4C313439414845
FAILURE_VALUE = 0x4B4C313439424144
PROGRESS_VALUES = (
    0x4B4C313530534145,  # KL150SAE: entered setup_arch
    0x4B4C313530534144,  # KL150SAD: setup_arch memory setup done
    0x4B4C3135304D494E,  # KL150MIN: entered mem_init
    0x4B4C3135314D4944,  # KL151MID: mem_init completed
)
PROGRESS_NAMES = (
    "setup_arch_enter",
    "setup_arch_done",
    "mem_init_enter",
    "mem_init_done",
)
ANCHORS = (
    b"DADAO M1 test-machine early console online\n",
    b"Linux version 5.4.0",
    b"DADAO M1 setup_arch complete\n",
    b"Memory:",
)
NEXT_BLOCKER_EXCEPTION_INDEX = 3
NEXT_BLOCKER_PC = 0x8027985C
NEXT_BLOCKER_SYMBOL = "prepare_alloc_pages"
NEXT_BLOCKER_SYMBOL_ADDRESS = 0x80279694

CARRIER_FIX_STAGES = (
    {
        "label": "pre-0009-page-expected-state",
        "commit": "537c61baef6e8ca04cc3d77f6cc9da7856fd6d5e",
        "exception_index": 3,
        "pc": 0x80280D8C,
        "symbol": "page_expected_state",
        "symbol_address": 0x80280BCC,
        "source": "mm/page_alloc.c::page_expected_state",
        "stack_slot_offset": 43,
    },
    {
        "label": "pre-0010-compaction-capture",
        "commit": "3e83c7744f5d093eba3a46284416b8409f3d452c",
        "exception_index": 3,
        "pc": 0x80282400,
        "symbol": "compaction_capture",
        "symbol_address": 0x80282318,
        "source": "mm/page_alloc.c::compaction_capture",
        "stack_slot_offset": 31,
    },
)


class GateError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_identity(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise GateError(f"evidence artifact missing: {path}")
    return {
        "path": str(path),
        "size": path.stat().st_size,
        "sha256": sha256(path),
    }


def atomic_write_json(path: Path, payload: object) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def prepare_single_run_evidence() -> dict[str, object]:
    if EVIDENCE.exists():
        shutil.rmtree(EVIDENCE)
    EVIDENCE.mkdir(parents=True)
    runner = file_identity(RUNNER)
    atomic_write_json(
        EVIDENCE / "RUNNING.json",
        {
            "task": "KL-151a",
            "state": "RUNNING",
            "runner_identity": runner,
            "started_unix_ns": time.time_ns(),
        },
    )
    return runner


def publish_failure(error: BaseException) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "summary.json").unlink(missing_ok=True)
    (EVIDENCE / "RUNNING.json").unlink(missing_ok=True)
    atomic_write_json(
        EVIDENCE / "FAILED.json",
        {
            "task": "KL-151a",
            "state": "FAILED",
            "error": str(error),
            "runner_identity": (
                file_identity(RUNNER) if RUNNER.is_file() else None
            ),
            "failed_unix_ns": time.time_ns(),
        },
    )


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


def make_tree(
    name: str, source: Path, output: Path, *targets: str
) -> subprocess.CompletedProcess[str]:
    return execute(
        name,
        [
            "make",
            "-C",
            str(source),
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


def make(
    name: str, output: Path, *targets: str
) -> subprocess.CompletedProcess[str]:
    return make_tree(name, LINUX_SOURCE, output, *targets)


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


def verify_kl150_frozen_evidence() -> dict[str, object]:
    if not KL150_SUMMARY.is_file():
        raise GateError(f"KL-150a summary missing: {KL150_SUMMARY}")
    if sha256(KL150_SUMMARY) != KL150_SUMMARY_SHA256:
        raise GateError("KL-150a frozen summary identity drift")
    summary = json.loads(KL150_SUMMARY.read_text())
    required = {
        ("task",): "KL-150a",
        ("result",): "PASS",
        ("counts", "pass"): 4,
        ("counts", "fail"): 0,
        ("counts", "skip"): 0,
        ("build_flags", "KCFLAGS"): "-O0",
        ("qemu_identity", "head"): QEMU_HEAD,
        ("qemu_identity", "sha256"):
            QEMU_SHA256,
        ("positive_runtime", "console_anchor_counts"): [1, 1, 1],
        ("positive_runtime", "console_verdict"): True,
        ("negative_serial_none", "console_verdict"): False,
        ("negative_wrong_mode", "status", "status"): "shutdown",
    }
    for keys, expected in required.items():
        value: object = summary
        for key in keys:
            value = value[key]  # type: ignore[index]
        if value != expected:
            raise GateError(
                f"KL-150a evidence drift at {'.'.join(keys)}: "
                f"{value!r} != {expected!r}"
            )
    expected_final = (
        "4b4c3134394148450000000000000000"
        "4b4c3135305341454b4c3135305341444b4c3135304d494e"
    )
    if summary["positive_runtime"]["final_raw_hex"] != expected_final:
        raise GateError("KL-150a positive five-word oracle drifted")
    if summary["negative_serial_none"]["final_raw_hex"] != expected_final:
        raise GateError("KL-150a serial-none QMP oracle drifted")
    expected_wrong = (
        "00000000000000004b4c313439424144"
        "000000000000000000000000000000000000000000000000"
    )
    if summary["negative_wrong_mode"]["final_raw_hex"] != expected_wrong:
        raise GateError("KL-150a wrong-mode oracle drifted")
    console = Path(summary["positive_runtime"]["console_path"]).read_bytes()
    if not all(console.count(anchor) == 1 for anchor in ANCHORS[:3]):
        raise GateError("KL-150a frozen console anchors drifted")
    linux_rows = summary["component_queues"]["linux"]
    expected_patches = [
        {"patch": name, "commit": commit, "patch_id": payload_id}
        for name, commit, payload_id in LINUX_PATCHES[:7]
    ]
    if linux_rows != expected_patches:
        raise GateError("KL-150a frozen Linux patch identities drifted")
    return {
        "path": str(KL150_SUMMARY),
        "sha256": sha256(KL150_SUMMARY),
        "counts": summary["counts"],
        "qemu_head": summary["qemu_identity"]["head"],
        "linux_patches": linux_rows,
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
        raise GateError("Linux KL-151a series names/order drifted")
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
        (1, 1, 1, 1) if expect_console else (0, 1, 0, 1)
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
            "DADAO_M1_PROGRESS_MEM_INIT_DONE\t0x87fd0028UL",
        ),
        setup: (
            "DADAO_M1_PROGRESS_SETUP_ENTER_VALUE",
            "DADAO_M1_PROGRESS_SETUP_DONE_VALUE",
        ),
        mem_init: (
            "DADAO_M1_PROGRESS_MEM_INIT_VALUE",
            "DADAO_M1_PROGRESS_MEM_INIT_DONE_VALUE",
        ),
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
        mem_body.find("mem_init_print_info(NULL);"),
        mem_body.find("DADAO_M1_PROGRESS_MEM_INIT_DONE_VALUE"),
    )
    if min(mem_order) < 0 or tuple(sorted(mem_order)) != mem_order:
        raise GateError(
            "mem_init progress source order drifted: "
            f"enter/free/print/done={mem_order}"
        )
    done_write = re.compile(
        r"dadao_m1_progress_write\(\s*"
        r"DADAO_M1_PROGRESS_MEM_INIT_DONE\s*,\s*"
        r"DADAO_M1_PROGRESS_MEM_INIT_DONE_VALUE\s*\);"
    )
    done_matches = list(done_write.finditer(mem_body))
    if len(done_matches) != 1:
        raise GateError(
            "mem_init completion write must occur exactly once in mem_init"
        )
    if mem_body[done_matches[0].end():].strip():
        raise GateError(
            "KL151MID write is not the final real statement in mem_init"
        )
    head_text = head.read_text()
    for value in (
        "4b4c313530534145",
        "4b4c313530534144",
        "4b4c3135304d494e",
        "4b4c3135314d4944",
    ):
        if value in head_text.lower():
            raise GateError("head.S pre-fills a KL-150/KL-151 progress value")
    return {
        "setup_arch_enter": str(setup),
        "setup_arch_done": str(setup),
        "mem_init_enter": str(mem_init),
        "mem_init_done": str(mem_init),
        "console": str(early_console),
        "contract": str(header),
    }


def build_linux_image() -> dict[str, object]:
    make("linux-mrproper", LINUX_OUTPUT, "mrproper")
    make("linux-defconfig", LINUX_OUTPUT, "dadao_defconfig")
    make("linux-olddefconfig", LINUX_OUTPUT, "olddefconfig")
    positive_build = make("linux-image", LINUX_OUTPUT, "Image")
    reject_forbidden_diagnostics(positive_build)
    return verify_image(LINUX_OUTPUT, expect_console=True)


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


def decode_oracle(payload: bytes) -> tuple[int, int, int, int, int, int]:
    return struct.unpack(">QQQQQQ", payload)


def progress_is_ordered(words: tuple[int, int, int, int]) -> bool:
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
    passed = counts == [1, 1, 1, 1] and positions == sorted(positions)
    return passed, counts, positions


def identify_post_memory_blocker(
    name: str, trace_path: Path
) -> dict[str, object]:
    trace = trace_path.read_text()
    matches = re.findall(
        r"dadao: exception index=(\d+) pc=(0x[0-9a-f]+)", trace
    )
    maligned = [
        (int(index), int(pc, 16))
        for index, pc in matches
        if int(index) == NEXT_BLOCKER_EXCEPTION_INDEX
    ]
    if not maligned:
        raise GateError(f"{name}: no post-memory MALIGN in QEMU trace")
    if any(item != (NEXT_BLOCKER_EXCEPTION_INDEX, NEXT_BLOCKER_PC)
           for item in maligned):
        raise GateError(f"{name}: post-memory exception drift: {maligned}")

    symbols = execute(
        f"{name}-post-memory-symbols",
        [str(LLVM_BIN / "llvm-nm"), "-n", str(LINUX_OUTPUT / "vmlinux")],
    ).stdout.splitlines()
    resolved: tuple[int, str] | None = None
    for line in symbols:
        fields = line.split()
        if len(fields) != 3:
            continue
        try:
            address = int(fields[0], 16)
        except ValueError:
            continue
        if address <= NEXT_BLOCKER_PC:
            resolved = (address, fields[2])
        else:
            break
    expected = (NEXT_BLOCKER_SYMBOL_ADDRESS, NEXT_BLOCKER_SYMBOL)
    if resolved != expected:
        raise GateError(
            f"{name}: post-memory symbol drift: {resolved} != {expected}"
        )

    disassembly = execute(
        f"{name}-post-memory-disassembly",
        [
            str(LLVM_BIN / "llvm-objdump"),
            "--arch-name=dadao",
            "-d",
            f"--start-address={NEXT_BLOCKER_PC - 0x28:#x}",
            f"--stop-address={NEXT_BLOCKER_PC + 0xc:#x}",
            str(LINUX_OUTPUT / "vmlinux"),
        ],
    ).stdout
    required_disassembly = (
        "addi rb8, rb1, 71",
        "stb rd16, rb8, 0",
        f"{NEXT_BLOCKER_PC:x}:",
        "ldo rd31, rb8, 0",
    )
    missing = [
        marker for marker in required_disassembly if marker not in disassembly
    ]
    if missing:
        raise GateError(
            f"{name}: post-memory stack-slot proof drift: {missing}"
        )
    page_alloc = (LINUX_SOURCE / "mm/page_alloc.c").read_text()
    if page_alloc.count(
        "static inline bool prepare_alloc_pages("
    ) != 1:
        raise GateError(
            f"{name}: next-blocker source signature is no longer frozen"
        )
    return {
        "exception": "EXCP_MALIGN",
        "exception_index": NEXT_BLOCKER_EXCEPTION_INDEX,
        "pc": f"0x{NEXT_BLOCKER_PC:016x}",
        "symbol": NEXT_BLOCKER_SYMBOL,
        "symbol_address": f"0x{NEXT_BLOCKER_SYMBOL_ADDRESS:016x}",
        "symbol_offset": f"0x{NEXT_BLOCKER_PC - NEXT_BLOCKER_SYMBOL_ADDRESS:x}",
        "source": "mm/page_alloc.c::prepare_alloc_pages",
        "stack_slot_evidence": {
            "offset_from_rb1": 71,
            "store": "stb",
            "reload": "ldo",
        },
        "trace_path": str(trace_path),
        "disassembly_path": str(
            EVIDENCE / f"{name}-post-memory-disassembly.log"
        ),
    }


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


def analyze_carrier_failure(
    stage: dict[str, object], vmlinux: Path, trace_path: Path
) -> dict[str, object]:
    label = str(stage["label"])
    expected_index = int(stage["exception_index"])
    expected_pc = int(stage["pc"])
    expected_symbol = str(stage["symbol"])
    expected_symbol_address = int(stage["symbol_address"])
    stack_slot_offset = int(stage["stack_slot_offset"])

    trace = trace_path.read_text()
    exceptions = [
        (int(index), int(pc, 16))
        for index, pc in re.findall(
            r"dadao: exception index=(\d+) pc=(0x[0-9a-f]+)", trace
        )
        if int(index) == expected_index
    ]
    expected_exception = (expected_index, expected_pc)
    if not exceptions or any(item != expected_exception for item in exceptions):
        raise GateError(
            f"{label}: carrier-fix exception drift: {exceptions}"
        )

    symbol_result = execute(
        f"{label}-symbols",
        [str(LLVM_BIN / "llvm-nm"), "-n", str(vmlinux)],
    )
    resolved: tuple[int, str] | None = None
    for line in symbol_result.stdout.splitlines():
        fields = line.split()
        if len(fields) != 3:
            continue
        try:
            address = int(fields[0], 16)
        except ValueError:
            continue
        if address <= expected_pc:
            resolved = (address, fields[2])
        else:
            break
    expected_resolution = (expected_symbol_address, expected_symbol)
    if resolved != expected_resolution:
        raise GateError(
            f"{label}: carrier-fix symbol drift: "
            f"{resolved} != {expected_resolution}"
        )

    disassembly_result = execute(
        f"{label}-disassembly",
        [
            str(LLVM_BIN / "llvm-objdump"),
            "--arch-name=dadao",
            "-d",
            f"--start-address={expected_pc - 0x30:#x}",
            f"--stop-address={expected_pc + 0xc:#x}",
            str(vmlinux),
        ],
    )
    required = (
        f"addi rb8, rb1, {stack_slot_offset}",
        "stb rd16, rb8, 0",
        f"{expected_pc:x}:",
        "ldo rd31, rb8, 0",
    )
    missing = [
        marker for marker in required
        if marker not in disassembly_result.stdout
    ]
    if missing:
        raise GateError(
            f"{label}: carrier-fix stack-slot proof drift: {missing}"
        )
    return {
        "exception": "EXCP_MALIGN",
        "exception_index": expected_index,
        "pc": f"0x{expected_pc:016x}",
        "symbol": expected_symbol,
        "symbol_address": f"0x{expected_symbol_address:016x}",
        "symbol_offset": f"0x{expected_pc - expected_symbol_address:x}",
        "source": stage["source"],
        "stack_slot_evidence": {
            "offset_from_rb1": stack_slot_offset,
            "store": "stb",
            "reload": "ldo",
        },
        "symbol_log": file_identity(EVIDENCE / f"{label}-symbols.log"),
        "disassembly_log": file_identity(
            EVIDENCE / f"{label}-disassembly.log"
        ),
    }


def run_expected_carrier_failure(
    stage: dict[str, object], image: Path, vmlinux: Path, rom: Path
) -> dict[str, object]:
    label = str(stage["label"])
    stage_dir = EVIDENCE / "carrier-fix" / label
    stage_dir.mkdir(parents=True, exist_ok=True)
    transport = tempfile.TemporaryDirectory(prefix="kl151a_carrier_")
    transport_path = Path(transport.name)
    qmp_path = transport_path / "qmp.sock"
    oracle_path = transport_path / "oracle.bin"
    console_path = stage_dir / "console.bin"
    trace_path = stage_dir / "qemu-trace.log"
    runtime_path = stage_dir / "qemu-runtime.log"
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
        f"file:{console_path}",
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
    initial = b""
    final = b""
    status: object = None
    try:
        sock, stream, greeting = connect_qmp(proc, qmp_path, 10.0)
        initial = dump_oracle(stream, oracle_path)
        if initial != bytes(ORACLE_SIZE):
            raise GateError(
                f"{label}: historical scratch is nonzero before cont"
            )
        (stage_dir / "progress-initial.bin").write_bytes(initial)
        qmp_roundtrip(stream, {"execute": "cont"})
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise GateError(
                    f"{label}: QEMU exited before expected MALIGN"
                )
            status = qmp_roundtrip(stream, {"execute": "query-status"})
            if status.get("status") == "shutdown":
                break
            time.sleep(0.02)
        else:
            raise GateError(f"{label}: expected MALIGN timeout")
        final = dump_oracle(stream, oracle_path)
        expected_oracle = (
            MARKER_VALUE,
            0,
            PROGRESS_VALUES[0],
            PROGRESS_VALUES[1],
            PROGRESS_VALUES[2],
            0,
        )
        if decode_oracle(final) != expected_oracle:
            raise GateError(
                f"{label}: historical oracle drift: {decode_oracle(final)}"
            )
        (stage_dir / "progress-final.bin").write_bytes(final)
        try:
            qmp_roundtrip(stream, {"execute": "quit"})
        except (GateError, OSError, TimeoutError):
            pass
        sock.close()
    finally:
        if proc.poll() is None:
            proc.kill()
        stdout, stderr = proc.communicate()
        runtime_path.write_text(
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

    blocker = analyze_carrier_failure(stage, vmlinux, trace_path)
    return {
        "status": status,
        "initial_raw_hex": initial.hex(),
        "final_raw_hex": final.hex(),
        "image": file_identity(stage_dir / "Image"),
        "initial_raw": file_identity(stage_dir / "progress-initial.bin"),
        "final_raw": file_identity(stage_dir / "progress-final.bin"),
        "trace": file_identity(trace_path),
        "console": file_identity(console_path),
        "qemu_runtime": file_identity(runtime_path),
        "observed_failure": blocker,
    }


def build_and_run_carrier_stage(
    stage: dict[str, object], rom: Path
) -> dict[str, object]:
    label = str(stage["label"])
    commit = str(stage["commit"])
    source_parent = ROOT / ".work" / "source"
    build_parent = ROOT / ".work" / "build"
    source_parent.mkdir(parents=True, exist_ok=True)
    build_parent.mkdir(parents=True, exist_ok=True)
    source_path = Path(
        tempfile.mkdtemp(prefix=f"kl151a-{label}-", dir=source_parent)
    )
    shutil.rmtree(source_path)
    output_path = Path(
        tempfile.mkdtemp(prefix=f"kl151a-{label}-", dir=build_parent)
    )
    worktree_added = False
    result: dict[str, object] | None = None
    try:
        execute(
            f"{label}-worktree-add",
            [
                "git",
                "-C",
                str(LINUX_SOURCE),
                "worktree",
                "add",
                "--detach",
                str(source_path),
                commit,
            ],
        )
        worktree_added = True
        identity = execute(
            f"{label}-commit-identity",
            [
                "git",
                "-C",
                str(source_path),
                "show",
                "-s",
                "--format=%H%n%P%n%s",
                "HEAD",
            ],
        ).stdout.splitlines()
        if not identity or identity[0] != commit:
            raise GateError(f"{label}: historical HEAD identity drift")
        dirty = execute(
            f"{label}-status-before",
            ["git", "-C", str(source_path), "status", "--porcelain=v1"],
        ).stdout.strip()
        if dirty:
            raise GateError(f"{label}: historical worktree dirty")

        make_tree(f"{label}-mrproper", source_path, output_path, "mrproper")
        make_tree(
            f"{label}-defconfig",
            source_path,
            output_path,
            "dadao_defconfig",
        )
        make_tree(
            f"{label}-olddefconfig",
            source_path,
            output_path,
            "olddefconfig",
        )
        build = make_tree(
            f"{label}-image", source_path, output_path, "Image"
        )
        reject_forbidden_diagnostics(build)
        image = output_path / "arch/dadao/boot/Image"
        vmlinux = output_path / "vmlinux"
        if not image.is_file() or not vmlinux.is_file():
            raise GateError(f"{label}: historical Image/vmlinux missing")
        stage_dir = EVIDENCE / "carrier-fix" / label
        stage_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(image, stage_dir / "Image")

        runtime = run_expected_carrier_failure(
            stage, stage_dir / "Image", vmlinux, rom
        )
        dirty_after = execute(
            f"{label}-status-after",
            ["git", "-C", str(source_path), "status", "--porcelain=v1"],
        ).stdout.strip()
        if dirty_after:
            raise GateError(
                f"{label}: historical worktree dirty after evidence"
            )
        command_logs = [
            file_identity(EVIDENCE / f"{label}-{suffix}.log")
            for suffix in (
                "worktree-add",
                "commit-identity",
                "status-before",
                "mrproper",
                "defconfig",
                "olddefconfig",
                "image",
                "status-after",
            )
        ]
        result = {
            "label": label,
            "linux_head": commit,
            "linux_parent": identity[1] if len(identity) > 1 else "",
            "linux_subject": identity[2] if len(identity) > 2 else "",
            "build_flags": {"ARCH": "dadao", "KCFLAGS": "-O0"},
            "command_logs": command_logs,
            **runtime,
        }
    finally:
        cleanup_failures: list[str] = []
        if worktree_added:
            remove = execute(
                f"{label}-worktree-remove",
                [
                    "git",
                    "-C",
                    str(LINUX_SOURCE),
                    "worktree",
                    "remove",
                    "--force",
                    str(source_path),
                ],
                check=False,
            )
            if remove.returncode:
                cleanup_failures.append(
                    f"git worktree remove rc={remove.returncode}"
                )
        for path in (output_path, source_path):
            try:
                if path.exists():
                    shutil.rmtree(path)
            except OSError as exc:
                cleanup_failures.append(f"cannot remove {path}: {exc}")
            if path.exists():
                cleanup_failures.append(f"path remains after cleanup: {path}")
        worktrees = execute(
            f"{label}-worktree-list-after",
            [
                "git",
                "-C",
                str(LINUX_SOURCE),
                "worktree",
                "list",
                "--porcelain",
            ],
            check=False,
        )
        if worktrees.returncode:
            cleanup_failures.append(
                f"git worktree list rc={worktrees.returncode}"
            )
        elif str(source_path) in worktrees.stdout:
            cleanup_failures.append(
                f"temporary worktree remains registered: {source_path}"
            )
        if cleanup_failures:
            raise GateError(
                f"{label}: temporary worktree cleanup failed: "
                + "; ".join(cleanup_failures)
            )
    if result is None:
        raise GateError(f"{label}: carrier-fix evidence was not produced")
    result["worktree_remove_log"] = file_identity(
        EVIDENCE / f"{label}-worktree-remove.log"
    )
    result["worktree_list_after_log"] = file_identity(
        EVIDENCE / f"{label}-worktree-list-after.log"
    )
    return result


def collect_carrier_fix_evidence(rom: Path) -> list[dict[str, object]]:
    return [
        build_and_run_carrier_stage(stage, rom)
        for stage in CARRIER_FIX_STAGES
    ]


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
    transport = tempfile.TemporaryDirectory(prefix=f"kl151a_{name}_")
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
    blocker = identify_post_memory_blocker(name, trace_path)
    if (
        not isinstance(final_status, dict)
        or final_status.get("status") != "shutdown"
        or final_status.get("running")
    ):
        raise GateError(
            f"{name}: post-memory MALIGN did not produce shutdown: "
            f"{final_status}"
        )
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
        "first_post_memory_blocker": blocker,
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
        (EVIDENCE / "wrong-mode-progress-initial.bin").write_bytes(initial)
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
        if words != (0, FAILURE_VALUE, 0, 0, 0, 0):
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
    rom = EVIDENCE / "kl151a-linux-handoff.bin"
    wrong_mode = EVIDENCE / "kl151a-linux-handoff-wrong-mode.bin"
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
    for payload in (rom.read_bytes(), wrong_mode.read_bytes()):
        if any(struct.pack(">Q", value) in payload for value in PROGRESS_VALUES):
            raise GateError("handoff ROM contains a progress value")
        if forbidden in payload:
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


def publish_artifact_manifest(
    runner_identity: dict[str, object]
) -> dict[str, object]:
    (EVIDENCE / "RUNNING.json").unlink(missing_ok=True)
    (EVIDENCE / "FAILED.json").unlink(missing_ok=True)
    required = (
        EVIDENCE / "positive-progress-initial.bin",
        EVIDENCE / "positive-progress-final.bin",
        EVIDENCE / "positive-qemu-trace.log",
        EVIDENCE / "positive-console.bin",
        EVIDENCE / "positive-post-memory-symbols.log",
        EVIDENCE / "positive-post-memory-disassembly.log",
        EVIDENCE / "positive-qemu-runtime.log",
        EVIDENCE / "serial-none-progress-initial.bin",
        EVIDENCE / "serial-none-progress-final.bin",
        EVIDENCE / "serial-none-qemu-trace.log",
        EVIDENCE / "serial-none-post-memory-symbols.log",
        EVIDENCE / "serial-none-post-memory-disassembly.log",
        EVIDENCE / "serial-none-qemu-runtime.log",
        EVIDENCE / "wrong-mode-progress-initial.bin",
        EVIDENCE / "wrong-mode-progress-final.bin",
        EVIDENCE / "wrong-mode-qemu-runtime.log",
    )
    carrier_required = tuple(
        EVIDENCE / "carrier-fix" / str(stage["label"]) / name
        for stage in CARRIER_FIX_STAGES
        for name in (
            "Image",
            "progress-initial.bin",
            "progress-final.bin",
            "qemu-trace.log",
            "console.bin",
            "qemu-runtime.log",
        )
    )
    missing = [
        str(path) for path in (*required, *carrier_required)
        if not path.is_file()
    ]
    if missing:
        raise GateError(f"key evidence artifacts missing: {missing}")
    excluded_names = {
        "summary.json",
        "artifact-manifest.json",
        "RUNNING.json",
        "FAILED.json",
    }
    artifacts = [
        file_identity(path)
        for path in sorted(EVIDENCE.rglob("*"))
        if path.is_file()
        and path.name not in excluded_names
        and not path.name.startswith(".summary.json.tmp-")
        and not path.name.startswith(".artifact-manifest.json.tmp-")
    ]
    if not artifacts:
        raise GateError("artifact manifest would be empty")
    manifest = {
        "schema": 1,
        "task": "KL-151a",
        "scope": (
            "All files in the clean single-run evidence directory before "
            "artifact-manifest.json and summary.json are published"
        ),
        "cycle_break": (
            "The manifest excludes itself and summary.json; summary.json "
            "binds this manifest by size and SHA256"
        ),
        "runner_identity": runner_identity,
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
    }
    manifest_path = EVIDENCE / "artifact-manifest.json"
    atomic_write_json(manifest_path, manifest)
    return file_identity(manifest_path)


def main() -> int:
    runner_identity = prepare_single_run_evidence()
    frozen = verify_kl150_frozen_evidence()
    queues = verify_component_identities()
    source_contract = verify_progress_source_contract()
    qemu = rebuild_and_verify_qemu()
    rom, wrong_mode_rom = generate_roms()
    carrier_fix_evidence = collect_carrier_fix_evidence(rom)
    positive_image = build_linux_image()

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
    blocker_identity_keys = (
        "exception",
        "exception_index",
        "pc",
        "symbol",
        "symbol_address",
        "symbol_offset",
        "source",
        "stack_slot_evidence",
    )
    if any(
        serial_none["first_post_memory_blocker"][key]
        != positive["first_post_memory_blocker"][key]
        for key in blocker_identity_keys
    ):
        raise GateError(
            "post-memory blocker differs between console transports"
        )

    wrong_mode = run_wrong_mode_guest(
        Path(positive_image["image"]), wrong_mode_rom
    )
    verify_sources_clean_after()

    counts = {"pass": 3, "fail": 0, "skip": 0}
    summary = {
        "task": "KL-151a",
        "result": "PASS",
        "counts": counts,
        "build_flags": {"ARCH": "dadao", "KCFLAGS": "-O0"},
        "kl150_frozen_evidence": frozen,
        "component_queues": queues,
        "carrier_fix_evidence": carrier_fix_evidence,
        "source_stage_contract": source_contract,
        "qemu_identity": qemu,
        "linux_positive": positive_image,
        "rom": {
            "path": str(rom),
            "sha256": sha256(rom),
            "wrong_mode_path": str(wrong_mode_rom),
            "wrong_mode_sha256": sha256(wrong_mode_rom),
        },
        "positive_runtime": positive,
        "negative_serial_none": serial_none,
        "negative_wrong_mode": wrong_mode,
        "first_next_blocker": positive["first_post_memory_blocker"],
        "runner_identity": runner_identity,
        "evidence_publication": {
            "semantics": "clean single-run directory",
            "old_pass_invalidated_at_start": True,
            "summary_publish": "atomic os.replace after all gates",
            "failure_summary_policy": (
                "summary.json absent; FAILED.json records this run"
            ),
        },
    }
    current_runner_identity = file_identity(RUNNER)
    if current_runner_identity != runner_identity:
        raise GateError("runner changed while KL-151a gate was executing")
    summary["artifact_manifest"] = publish_artifact_manifest(runner_identity)
    atomic_write_json(EVIDENCE / "summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    print("PASS: KL-151a mem_init completion (3/3, FAIL=0, SKIP=0)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        publish_failure(exc)
        if isinstance(exc, GateError):
            raise SystemExit(f"KL-151a FAIL: {exc}") from exc
        raise
