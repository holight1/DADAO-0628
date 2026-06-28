#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str, cwd: Path | None = None) -> None:
    subprocess.run(args, cwd=cwd, check=True)


def main() -> int:
    with (ROOT / "manifests/components.lock.toml").open("rb") as stream:
        manifest = tomllib.load(stream)
    source_root = ROOT / manifest.get("work_root", ".work") / "source"
    enabled = [c for c in manifest.get("component", []) if c.get("enabled")]
    if not enabled:
        print("fetch: no components enabled; accept baseline ADRs first")
        return 0

    source_root.mkdir(parents=True, exist_ok=True)
    for component in enabled:
        target = source_root / component["name"]
        if not target.exists():
            run("git", "clone", "--filter=blob:none", "--no-checkout",
                component["repository"], str(target))
        dirty = subprocess.check_output(
            ["git", "-C", str(target), "status", "--porcelain=v1"], text=True
        )
        if dirty:
            raise SystemExit(f"fetch: {target} is dirty; refusing to overwrite")
        run("git", "fetch", "--no-tags", "origin", component["commit"], cwd=target)
        run("git", "checkout", "--detach", component["commit"], cwd=target)
        print(f"fetch: {component['name']} -> {component['commit']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
