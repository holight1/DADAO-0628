#!/usr/bin/env python3
"""check_wiki_drift.py — Verify every contracts/*/spec.md has a known, valid provenance.

Fail-closed rules:
  - Wiki-sourced contracts: **Source** line must contain the locked Wiki SHA.
  - ADR-sourced contracts:  **Source** line must reference an entry in KNOWN_ADR_SOURCES.
  - Missing or malformed Source: ERROR — the contract cannot be silently accepted.
"""

import re
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LOCK_PATH = REPO_ROOT / "manifests" / "spec.lock.toml"

WIKI_SHA_RE = re.compile(r"\*\*Source\*\*: Wiki commit `([0-9a-fA-F]{40})`")
ADR_SOURCE_RE = re.compile(r"\*\*Source\*\*: ADR-(\d{4})")

# Accepted ADR-sourced contracts: key = relative path, value = expected ADR number string.
KNOWN_ADR_SOURCES: dict[str, str] = {
    "contracts/elf/spec.md": "0003",
}


def main() -> int:
    with open(LOCK_PATH, "rb") as fh:
        lock = tomllib.load(fh)

    locked_commit = lock.get("commit", "")
    if not re.fullmatch(r"[0-9a-f]{40}", locked_commit):
        print("ERROR: spec.lock.toml: commit must be a full 40-character SHA-1",
              file=sys.stderr)
        return 1

    spec_dir = REPO_ROOT / "contracts"
    errors: list[str] = []
    checked = 0

    for spec_path in sorted(spec_dir.rglob("spec.md")):
        rel = spec_path.relative_to(REPO_ROOT).as_posix()
        text = spec_path.read_text()

        wiki_m = WIKI_SHA_RE.search(text)
        adr_m = ADR_SOURCE_RE.search(text)

        if rel in KNOWN_ADR_SOURCES:
            # Must be ADR-sourced; Wiki SHA must NOT appear.
            expected_adr = KNOWN_ADR_SOURCES[rel]
            if wiki_m:
                errors.append(
                    f"ERROR: {rel}: expected ADR-{expected_adr} source but found "
                    f"Wiki SHA {wiki_m.group(1)[:12]}…"
                )
            elif not adr_m:
                errors.append(
                    f"ERROR: {rel}: **Source** line missing or malformed "
                    f"(expected ADR-{expected_adr} reference)"
                )
            elif adr_m.group(1) != expected_adr:
                errors.append(
                    f"ERROR: {rel}: Source references ADR-{adr_m.group(1)} "
                    f"but expected ADR-{expected_adr}"
                )
        else:
            # Must be Wiki-sourced.
            if adr_m:
                errors.append(
                    f"ERROR: {rel}: references ADR-{adr_m.group(1)} but is not "
                    f"listed in KNOWN_ADR_SOURCES — add it or change to Wiki source"
                )
            elif not wiki_m:
                errors.append(
                    f"ERROR: {rel}: **Source** line missing or malformed "
                    f"(expected 'Wiki commit `<sha>`')"
                )
            elif wiki_m.group(1) != locked_commit:
                errors.append(
                    f"ERROR: {rel}: Wiki commit {wiki_m.group(1)[:12]}… "
                    f"!= locked {locked_commit[:12]}…"
                )

        checked += 1

    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        return 1

    print(f"wiki drift check: PASS ({checked} contract(s) verified)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
