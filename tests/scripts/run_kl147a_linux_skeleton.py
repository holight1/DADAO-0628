#!/usr/bin/env python3
"""KL-147a fail-closed Linux/DADAO configuration skeleton gate."""

from __future__ import annotations

import hashlib
import subprocess
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "manifests" / "components.lock.toml"
SOURCE = ROOT / ".work" / "source" / "linux"
OUTPUT = ROOT / ".work" / "build" / "linux"
LLVM_BIN = ROOT / ".work" / "build" / "llvm" / "bin"
SERIES = ROOT / "components" / "linux" / "patches" / "series"


def run(command: list[str], *, capture: bool = False) -> str:
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=capture,
    )
    if result.returncode:
        if capture:
            sys.stderr.write(result.stdout)
            sys.stderr.write(result.stderr)
        raise SystemExit(
            f"KL-147a FAIL: rc={result.returncode}: {' '.join(command)}"
        )
    return result.stdout.strip() if capture else ""


def linux_component() -> dict:
    with MANIFEST.open("rb") as stream:
        manifest = tomllib.load(stream)
    for component in manifest["component"]:
        if component["name"] == "linux":
            return component
    raise SystemExit("KL-147a FAIL: linux component missing from manifest")


def active_series() -> list[str]:
    return [
        line.strip()
        for line in SERIES.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def make(*targets: str) -> None:
    command = [
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
        *targets,
    ]
    run(command)


def config_hash() -> str:
    return hashlib.sha256((OUTPUT / ".config").read_bytes()).hexdigest()


def main() -> int:
    component = linux_component()
    if not component.get("enabled"):
        raise SystemExit("KL-147a FAIL: linux component disabled")
    pin = component.get("commit", "")
    if len(pin) != 40:
        raise SystemExit("KL-147a FAIL: linux pin is not a full commit")

    for tool in (
        "clang",
        "ld.lld",
        "llvm-ar",
        "llvm-nm",
        "llvm-objcopy",
        "llvm-objdump",
        "llvm-readelf",
    ):
        if not (LLVM_BIN / tool).is_file():
            raise SystemExit(f"KL-147a FAIL: missing tool {tool}")

    head = run(["git", "-C", str(SOURCE), "rev-parse", "HEAD"], capture=True)
    run(["git", "-C", str(SOURCE), "merge-base", "--is-ancestor", pin, head])
    dirty = run(
        ["git", "-C", str(SOURCE), "status", "--porcelain=v1"], capture=True
    )
    if dirty:
        raise SystemExit(f"KL-147a FAIL: linux worktree dirty:\n{dirty}")

    patches = active_series()
    if not patches:
        raise SystemExit("KL-147a FAIL: Linux patch series is empty")
    for patch in patches:
        if not (SERIES.parent / patch).is_file():
            raise SystemExit(f"KL-147a FAIL: missing patch payload {patch}")
    count = int(
        run(
            ["git", "-C", str(SOURCE), "rev-list", "--count", f"{pin}..{head}"],
            capture=True,
        )
    )
    if count != len(patches):
        raise SystemExit(
            f"KL-147a FAIL: component commits={count}, series={len(patches)}"
        )

    OUTPUT.mkdir(parents=True, exist_ok=True)
    make("dadao_defconfig")
    make("olddefconfig")

    values: dict[str, str] = {}
    for line in (OUTPUT / ".config").read_text().splitlines():
        if line.startswith("CONFIG_") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    expected = {
        "CONFIG_DADAO": "y",
        "CONFIG_64BIT": "y",
        "CONFIG_MMU": "y",
        "CONFIG_NR_CPUS": "1",
        "CONFIG_BLK_DEV_INITRD": "y",
        "CONFIG_BINFMT_ELF": "y",
    }
    mismatch = {
        key: (values.get(key), value)
        for key, value in expected.items()
        if values.get(key) != value
    }
    if mismatch:
        raise SystemExit(f"KL-147a FAIL: config mismatch {mismatch}")

    first = config_hash()
    make("olddefconfig")
    second = config_hash()
    if first != second:
        raise SystemExit(
            f"KL-147a FAIL: olddefconfig drift {first} != {second}"
        )

    print(f"linux-pin: {pin}")
    print(f"linux-head: {head}")
    print(f"patch-count: {count}")
    print(f"config-sha256: {second}")
    print("PASS: KL-147a Linux/DADAO configuration skeleton")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
