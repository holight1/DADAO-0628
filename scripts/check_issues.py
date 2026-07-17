#!/usr/bin/env python3
"""Validate docs/issues.yaml (open) + docs/issues-archive.yaml (closed) and
report issue summary.

The registry is split across two files (IN-001a): docs/issues.yaml holds
only status: open entries, docs/issues-archive.yaml holds only status:
closed entries. Each file is validated independently for YAML structure
(duplicate-key detection), then cross-checked: the open file must contain
only open entries, the archive file only closed entries, and the union of
ids across both files must have no duplicates.
"""

import sys
import yaml

OPEN_PATH = "docs/issues.yaml"
ARCHIVE_PATH = "docs/issues-archive.yaml"

REQUIRED = {"id", "title", "status", "scope", "blocks", "resolved_by"}
VALID_STATUSES = {"open", "closed"}


class DuplicateKeyLoader(yaml.SafeLoader):
    """A missing '- id:' line lets a mapping's fields silently absorb the
    next entry's fields as duplicate keys (last one wins) instead of
    raising a parse error — plain SafeLoader doesn't flag this. Override
    construct_mapping to make duplicate keys within one node fatal."""

    def construct_mapping(self, node, deep=False):
        mapping = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in mapping:
                raise yaml.constructor.ConstructorError(
                    None, None, f"duplicate key {key!r} in mapping (a preceding "
                    f"'- id:' line may be missing, merging two entries)",
                    key_node.start_mark,
                )
            mapping.add(key)
        return super().construct_mapping(node, deep=deep)


def load_and_validate(path, errors):
    """Load one registry file, validate its own YAML structure/required
    fields. Returns the parsed entry list (or [] on a fatal load error,
    with the error already appended to `errors`)."""
    try:
        with open(path) as f:
            data = yaml.load(f, Loader=DuplicateKeyLoader)
    except yaml.YAMLError as e:
        errors.append(f"{path}: {e}")
        return []

    if not isinstance(data, list):
        errors.append(f"{path}: expected a list, got {type(data).__name__}")
        return []

    for i, entry in enumerate(data):
        if not isinstance(entry, dict):
            errors.append(f"{path} entry {i}: expected a mapping, got {type(entry).__name__}")
            continue

        missing = REQUIRED - set(entry.keys())
        if missing:
            errors.append(f"{path} entry {i}: missing fields: {sorted(missing)}")
            continue

        eid = entry["id"]
        status = entry["status"]
        if status not in VALID_STATUSES:
            errors.append(f"{path} entry {i} ({eid}): invalid status '{status}'")

    return data


def main():
    errors = []

    open_data = load_and_validate(OPEN_PATH, errors)
    archive_data = load_and_validate(ARCHIVE_PATH, errors)

    if errors:
        for e in errors:
            print(f"  {e}")
        print(f"ISSUE REGISTRY: FAIL ({len(errors)} error(s))")
        sys.exit(1)

    # Cross-file checks.
    for entry in open_data:
        if entry["status"] != "open":
            errors.append(
                f"{OPEN_PATH} entry ({entry['id']}): status '{entry['status']}' "
                f"found in open-only file"
            )
    for entry in archive_data:
        if entry["status"] != "closed":
            errors.append(
                f"{ARCHIVE_PATH} entry ({entry['id']}): status '{entry['status']}' "
                f"found in closed-only archive file"
            )

    all_ids = [e["id"] for e in open_data] + [e["id"] for e in archive_data]
    seen = set()
    for eid in all_ids:
        if eid in seen:
            errors.append(f"duplicate id across registry files: {eid!r}")
        seen.add(eid)

    if errors:
        for e in errors:
            print(f"  {e}")
        print(f"ISSUE REGISTRY: FAIL ({len(errors)} error(s))")
        sys.exit(1)

    open_count = len(open_data)
    closed_count = len(archive_data)

    # M1-gate blocking check: only open entries can block M1-gate.
    m1_gate_blocking = []
    for entry in open_data:
        blocks = entry.get("blocks")
        if blocks and "M1-gate" in blocks:
            m1_gate_blocking.append(entry["id"])

    print(f"Open:   {open_count}")
    print(f"Closed: {closed_count}")
    print(f"Total:  {open_count + closed_count}")
    if m1_gate_blocking:
        print(f"\nM1-gate blocking (open):")
        for eid in m1_gate_blocking:
            print(f"  {eid}", file=sys.stderr)
        print(f"ISSUE REGISTRY: FAIL ({len(m1_gate_blocking)} M1-gate blocker(s) open)",
              file=sys.stderr)
        sys.exit(1)
    print("ISSUE REGISTRY: PASS")


if __name__ == "__main__":
    main()
