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

        # Fetching first (safe: never touches the working tree/HEAD) makes the
        # pinned commit available locally for the ancestor check below, even
        # on a component that was already fetched+patched in a prior run.
        run("git", "fetch", "--no-tags", "origin", component["commit"], cwd=target)

        head = subprocess.run(
            ["git", "-C", str(target), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        if head == component["commit"]:
            print(f"fetch: {component['name']} already at {component['commit']}")
            continue
        is_patched = subprocess.run(
            ["git", "-C", str(target), "merge-base", "--is-ancestor",
             component["commit"], "HEAD"],
        ).returncode == 0
        if is_patched:
            # HEAD already has the pinned commit as an ancestor -- i.e. this
            # is a working tree with the patch series' commits applied on
            # top (apply_series.py's job), not a bare fresh checkout.
            # `git checkout --detach <pinned commit>` below is *destructive*
            # in this case: it silently discards every one of those applied
            # commits (they become dangling, reachable only via reflog until
            # GC) whenever the working tree happens to be clean -- this bit
            # DADAO-0628 for real on 2026-07-15/16 (re-running `make fetch`
            # for an unrelated new component wiped .work/source/qemu's
            # applied DADAO patches back to bare upstream; recovered via
            # `git reset --hard` to the last-known-good commit found in the
            # reflog). Leave an already-patched component alone.
            print(f"fetch: {component['name']} HEAD ({head[:12]}) already has "
                  f"{component['commit']} as an ancestor (patches applied on "
                  "top) -- leaving it alone")
            continue

        run("git", "checkout", "--detach", component["commit"], cwd=target)
        print(f"fetch: {component['name']} -> {component['commit']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
