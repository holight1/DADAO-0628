#!/usr/bin/env python3
"""Validate docs/issues.yaml format and report issue summary."""

import sys
import yaml

PATH = "docs/issues.yaml"

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


def main():
    with open(PATH) as f:
        try:
            data = yaml.load(f, Loader=DuplicateKeyLoader)
        except yaml.YAMLError as e:
            print(f"ERROR: {PATH}: {e}")
            print("ISSUE REGISTRY: FAIL (1 error(s))")
            sys.exit(1)

    if not isinstance(data, list):
        print(f"ERROR: {PATH}: expected a list, got {type(data).__name__}")
        sys.exit(1)

    errors = []
    open_count = 0
    closed_count = 0
    m1_gate_blocking = []

    for i, entry in enumerate(data):
        if not isinstance(entry, dict):
            errors.append(f"Entry {i}: expected a mapping, got {type(entry).__name__}")
            continue

        missing = REQUIRED - set(entry.keys())
        if missing:
            errors.append(f"Entry {i}: missing fields: {sorted(missing)}")
            continue

        eid = entry["id"]
        status = entry["status"]

        if status not in VALID_STATUSES:
            errors.append(f"Entry {i} ({eid}): invalid status '{status}'")

        if status == "open":
            open_count += 1
        elif status == "closed":
            closed_count += 1

        blocks = entry.get("blocks")
        if blocks and "M1-gate" in blocks and status == "open":
            m1_gate_blocking.append(eid)

    if errors:
        for e in errors:
            print(f"  {e}")
        print(f"ISSUE REGISTRY: FAIL ({len(errors)} error(s))")
        sys.exit(1)

    print(f"Open:   {open_count}")
    print(f"Closed: {closed_count}")
    print(f"Total:  {len(data)}")
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
