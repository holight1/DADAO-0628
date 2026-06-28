#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    with (ROOT / "manifests/components.lock.toml").open("rb") as stream:
        manifest = tomllib.load(stream)
    enabled = [c for c in manifest.get("component", []) if c.get("enabled")]
    if not enabled:
        print("apply-series: no components enabled")
        return 0

    source_root = ROOT / manifest.get("work_root", ".work") / "source"
    for component in enabled:
        source = source_root / component["name"]
        if not (source / ".git").exists():
            raise SystemExit(f"apply-series: missing source {source}; run make fetch")
        head = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"],
                                       text=True).strip()
        if head != component["commit"]:
            raise SystemExit(f"apply-series: {component['name']} HEAD is not its base commit")
        series_path = ROOT / component["patch_series"]
        patches = [line.strip() for line in series_path.read_text().splitlines()
                   if line.strip() and not line.lstrip().startswith("#")]
        if not patches:
            print(f"apply-series: {component['name']} has an empty series")
            continue
        for item in patches:
            patch = ROOT / "components" / component["name"] / "patches" / item
            subprocess.run(["git", "-C", str(source), "am", str(patch)], check=True)
        print(f"apply-series: {component['name']} applied {len(patches)} patches")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
