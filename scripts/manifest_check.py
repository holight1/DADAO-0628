#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHA1 = re.compile(r"^[0-9a-f]{40}$")


def load(name: str) -> dict:
    with (ROOT / "manifests" / name).open("rb") as stream:
        return tomllib.load(stream)


def main() -> int:
    errors: list[str] = []
    spec = load("spec.lock.toml")
    components = load("components.lock.toml")
    references = load("references.toml")

    if not SHA1.fullmatch(spec.get("commit", "")):
        errors.append("spec.lock.toml: commit must be a full 40-character SHA-1")
    if spec.get("status") not in {"candidate", "frozen"}:
        errors.append("spec.lock.toml: status must be candidate or frozen")
    if not spec.get("foundation_included"):
        errors.append("spec.lock.toml: foundation_included must not be empty")

    seen: set[str] = set()
    for component in components.get("component", []):
        name = component.get("name", "")
        if not name or name in seen:
            errors.append(f"components.lock.toml: invalid or duplicate component {name!r}")
        seen.add(name)
        if component.get("enabled") and not SHA1.fullmatch(component.get("commit", "")):
            errors.append(f"component {name}: enabled components require a full commit")
        series = ROOT / component.get("patch_series", "")
        if not series.is_file():
            errors.append(f"component {name}: missing patch series {series}")

    for reference in references.get("reference", []):
        ident = reference.get("id", "")
        if not ident:
            errors.append("references.toml: reference id is required")
        if not SHA1.fullmatch(reference.get("head", "")):
            errors.append(f"reference {ident}: head must be a full commit")
        if not Path(reference.get("path", "")).is_absolute():
            errors.append(f"reference {ident}: path must be absolute")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    enabled = [c["name"] for c in components.get("component", []) if c.get("enabled")]
    print(f"spec: {spec['commit']} ({spec['status']})")
    print(f"enabled components: {', '.join(enabled) if enabled else 'none'}")
    print(f"references: {len(references.get('reference', []))}")
    print("manifest validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
