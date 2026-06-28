#!/usr/bin/env python3
from __future__ import annotations

import shutil
import subprocess


def version(command: list[str]) -> str:
    try:
        output = subprocess.check_output(command, text=True, stderr=subprocess.STDOUT)
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"
    return output.splitlines()[0] if output else "available"


def main() -> int:
    required = {"git": ["git", "--version"], "make": ["make", "--version"],
                "cmake": ["cmake", "--version"], "python3": ["python3", "--version"]}
    native = {"ninja": ["ninja", "--version"], "clang": ["clang", "--version"]}
    missing_required = []

    for name, command in required.items():
        present = shutil.which(name) is not None
        print(f"{name:10} {'OK' if present else 'MISSING':8} {version(command) if present else ''}")
        if not present:
            missing_required.append(name)

    missing_native = []
    for name, command in native.items():
        present = shutil.which(name) is not None
        print(f"{name:10} {'OK' if present else 'MISSING':8} {version(command) if present else ''}")
        if not present:
            missing_native.append(name)

    docker = shutil.which("docker") is not None
    print(f"{'docker':10} {'OK' if docker else 'MISSING':8} {version(['docker', '--version']) if docker else ''}")

    if missing_required:
        print(f"doctor: FAIL; missing required tools: {', '.join(missing_required)}")
        return 1
    if missing_native and not docker:
        print("doctor: FAIL; native LLVM tools are incomplete and Docker is unavailable")
        return 1
    mode = "container" if missing_native else "native"
    print(f"doctor: PASS ({mode} build path available)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
