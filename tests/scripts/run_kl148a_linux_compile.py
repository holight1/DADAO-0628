#!/usr/bin/env python3
"""KL-148a fail-closed Linux/DADAO compile-to-object gate."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / ".work" / "source" / "linux"
OUTPUT = ROOT / ".work" / "build" / "linux"
LLVM_BIN = ROOT / ".work" / "build" / "llvm" / "bin"
EVIDENCE = ROOT / ".work" / "evidence" / "kl148a-linux-compile"
SERIES = ROOT / "components" / "linux" / "patches" / "series"


def execute(name: str, command: list[str]) -> subprocess.CompletedProcess[str]:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    (EVIDENCE / f"{name}.log").write_text(
        "=== command ===\n"
        + " ".join(command)
        + "\n=== returncode ===\n"
        + str(result.returncode)
        + "\n=== stdout ===\n"
        + result.stdout
        + "\n=== stderr ===\n"
        + result.stderr
    )
    if result.returncode:
        sys.stderr.write(result.stdout)
        sys.stderr.write(result.stderr)
        raise SystemExit(f"KL-148a FAIL: {name} rc={result.returncode}")
    return result


def make(name: str, *targets: str) -> None:
    execute(
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
            *targets,
        ],
    )


def patch_id(payload: str) -> str:
    result = subprocess.run(
        ["git", "patch-id", "--stable"],
        cwd=ROOT,
        text=True,
        input=payload,
        capture_output=True,
    )
    if result.returncode or not result.stdout.strip():
        raise SystemExit(
            "KL-148a FAIL: cannot calculate patch-id:\n" + result.stderr
        )
    return result.stdout.split()[0]


def verify_patch_identity() -> None:
    patches = [
        line.strip()
        for line in SERIES.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    commits = subprocess.run(
        [
            "git",
            "-C",
            str(SOURCE),
            "rev-list",
            "--reverse",
            f"HEAD~{len(patches)}..HEAD",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.splitlines()
    if len(commits) != len(patches):
        raise SystemExit("KL-148a FAIL: patch/commit count changed after KL-147a")

    rows: list[str] = []
    for commit, patch in zip(commits, patches, strict=True):
        commit_mail = subprocess.run(
            ["git", "-C", str(SOURCE), "show", "--pretty=email", commit],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        ).stdout
        commit_id = patch_id(commit_mail)
        payload_id = patch_id((SERIES.parent / patch).read_text())
        rows.append(f"{patch} {commit} {payload_id}")
        if commit_id != payload_id:
            raise SystemExit(
                f"KL-148a FAIL: patch payload drift {patch}: "
                f"{payload_id} != {commit_id}"
            )
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "patch-identity.log").write_text("\n".join(rows) + "\n")


def main() -> int:
    execute(
        "kl147a-prerequisite",
        [sys.executable, str(ROOT / "tests/scripts/run_kl147a_linux_skeleton.py")],
    )
    verify_patch_identity()

    make("clean", "clean")
    make("prepare", "prepare")
    make("init-main", "init/main.o")
    make("init-version", "init/version.o")

    obj = OUTPUT / "init" / "main.o"
    if not obj.is_file() or obj.stat().st_size == 0:
        raise SystemExit("KL-148a FAIL: init/main.o missing or empty")
    readobj = execute(
        "readobj",
        [str(LLVM_BIN / "llvm-readobj"), "--file-headers", str(obj)],
    ).stdout
    required = (
        "AddressSize: 64bit",
        "DataEncoding: BigEndian",
        "Type: Relocatable (0x1)",
        "Machine: 0xDA0",
    )
    missing = [marker for marker in required if marker not in readobj]
    if missing:
        raise SystemExit(f"KL-148a FAIL: readobj markers missing: {missing}")
    version_obj = OUTPUT / "init" / "version.o"
    if not version_obj.is_file() or version_obj.stat().st_size == 0:
        raise SystemExit("KL-148a FAIL: init/version.o missing or empty")

    dirty = execute(
        "linux-status",
        ["git", "-C", str(SOURCE), "status", "--porcelain=v1"],
    ).stdout.strip()
    if dirty:
        raise SystemExit(f"KL-148a FAIL: Linux worktree dirty:\n{dirty}")

    print(f"init-main-object: {obj}")
    print(f"init-main-size: {obj.stat().st_size}")
    print(f"init-version-size: {version_obj.stat().st_size}")
    print("PASS: KL-148a Linux/DADAO compile-to-object substrate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
