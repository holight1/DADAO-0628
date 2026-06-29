#!/usr/bin/env python3
"""validate_encoding.py — Validate tools/opcodes.yaml consistency.

Checks:
  1. (value & mask) == value for every record.
  2. MISC-Norm records have mask=0xFFFC0000; others have mask=0xFF000000.
  3. Fields within a record do not overlap.
  4. Field bits are within [0..31].
  5. No two records have identical (op, ha, mnemonic, format).
  6. No two records have intersecting (mask, value) decode space.
  7. role and bank values are from allowed sets.
"""

import sys
import re

try:
    import yaml as _yaml
except ImportError:
    sys.exit(
        "ERROR: PyYAML not installed. Run: pip install pyyaml\n"
        "       or: python3 -m pip install pyyaml"
    )


def _load(path):
    with open(path) as f:
        return _yaml.safe_load(f)

ALLOWED_ROLES = {"dst", "src", "imm", "fixed", "sbz"}
ALLOWED_BANKS = {"rd", "rb", "ra", "rf", "imm", "null"}

MISC_NORM_MASK = 0xFFFC0000
OTHER_MASK = 0xFF000000


def parse_bitrange(s):
    m = re.match(r'^\[(\d+):(\d+)\]$', s.strip())
    if not m:
        raise ValueError(f"invalid bit range: {s!r}")
    high, low = int(m.group(1)), int(m.group(2))
    if high < low or high > 31 or low < 0:
        raise ValueError(f"bit range out of bounds: {s!r}")
    return high, low


def check_fields_non_overlapping(fields):
    occupied = {}
    for f in fields:
        high, low = parse_bitrange(f["bits"])
        for b in range(low, high + 1):
            if b in occupied:
                return (False, f"bits overlap at bit {b}: field "
                        f"{f['name']} ({f['bits']}) conflicts with "
                        f"{occupied[b]}")
            occupied[b] = f"{f['name']} ({f['bits']})"
    return (True, "")


def check_value_mask(rec):
    mnem = rec["mnemonic"]
    fmt = rec["format"]
    tag = f"{mnem}({fmt})"
    val = rec["value"]
    msk = rec["mask"]

    if (val & msk) != val:
        return (False, f"{tag}: (value & mask) != value: "
                f"0x{val:08X} & 0x{msk:08X} = 0x{val & msk:08X}")

    if rec["ha"] is not None:
        expected_mask = MISC_NORM_MASK
        expected_val = (0x10 << 24) | (rec["ha"] << 18)
    else:
        expected_mask = OTHER_MASK
        expected_val = rec["op"] << 24

    if msk != expected_mask:
        return (False, f"{tag}: mask 0x{msk:08X} != expected "
                f"0x{expected_mask:08X}")
    if val != expected_val:
        return (False, f"{tag}: value 0x{val:08X} != expected "
                f"0x{expected_val:08X}")
    return (True, "")


def check_decode_conflict(records):
    for i, a in enumerate(records):
        for b in records[i + 1:]:
            common = a["mask"] & b["mask"]
            if (a["value"] & common) == (b["value"] & common):
                tag_a = f"{a['mnemonic']}({a['format']})"
                tag_b = f"{b['mnemonic']}({b['format']})"
                return (False, f"decode conflict: {tag_a} and {tag_b}")
    return (True, "")


def main():
    if len(sys.argv) < 2:
        print("Usage: validate_encoding.py <opcodes.yaml>", file=sys.stderr)
        sys.exit(1)

    path = sys.argv[1]
    records = _load(path)

    if not isinstance(records, list):
        print("ERROR: top-level must be a list", file=sys.stderr)
        sys.exit(1)

    errors = []
    seen_keys = {}

    for i, rec in enumerate(records):
        tag = f"record[{i}]"
        mnem = rec.get("mnemonic", "?")
        fmt = rec.get("format", "?")

        # Check uniqueness of (op, ha, mnemonic, format)
        op_ha_key = (rec.get("op"), rec.get("ha"), mnem, fmt)
        if op_ha_key in seen_keys:
            errors.append(f"{tag}: duplicate key: op={rec.get('op')}, "
                          f"ha={rec.get('ha')}, mnem={mnem}, fmt={fmt}")
        seen_keys[op_ha_key] = i

        # Check mask/value arithmetic
        ok, msg = check_value_mask(rec)
        if not ok:
            errors.append(f"ERROR: {msg}")

        # Check fields
        fields = rec.get("fields", [])
        if not fields:
            errors.append(f"ERROR: {tag} {mnem}({fmt}): no fields")

        # Check roles and banks
        for f in fields:
            if f.get("role") not in ALLOWED_ROLES:
                errors.append(f"ERROR: {tag} {mnem}({fmt}): field "
                              f"{f['name']} invalid role {f.get('role')}")
            if f.get("bank") not in ALLOWED_BANKS:
                errors.append(f"ERROR: {tag} {mnem}({fmt}): field "
                              f"{f['name']} invalid bank {f.get('bank')}")

        # Check field overlap
        ok, msg = check_fields_non_overlapping(fields)
        if not ok:
            errors.append(f"ERROR: {tag} {mnem}({fmt}): {msg}")

        # Check field bits within bounds
        for f in fields:
            try:
                parse_bitrange(f["bits"])
            except ValueError as e:
                errors.append(f"ERROR: {tag} {mnem}({fmt}): field "
                              f"{f['name']}: {e}")

    # Check decode conflicts
    ok, msg = check_decode_conflict(records)
    if not ok:
        errors.append(f"ERROR: {msg}")

    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        sys.exit(1)

    print(f"validate_encoding: {len(records)} records OK")
    sys.exit(0)


if __name__ == "__main__":
    main()
