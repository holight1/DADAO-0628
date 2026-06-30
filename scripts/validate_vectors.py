#!/usr/bin/env python3
"""validate_vectors.py — Validate tests/vectors/isa/*.yaml format.

Checks:
  1. Required fields present.
  2. class/status/fault values are valid.
  3. deferred consistency (status=deferred → expected_state=null, reason set).
  4. encoding.word is valid hex ≤ 0xFFFFFFFF.
  5. mnemonic+format exists in tools/opcodes.yaml.
  6. For active semantic/boundary cases: expected_state is non-null.
"""

import sys
import os
import re
import glob
import yaml

ALLOWED_CLASSES = {"encoding", "legality", "semantic", "boundary", "overlap"}
ALLOWED_STATUS = {"active", "deferred"}
ALLOWED_FAULTS = {None, "ILLI", "UNDI", "MALIGN", "IALIGN", "RASOF", "RASUF"}

REQUIRED_FIELDS = {"mnemonic", "format", "class", "encoding", "input_state",
                   "wiki_cite"}


def load_opcodes(path):
    with open(path) as f:
        records = yaml.safe_load(f)
    by_mnem_fmt = {}
    by_opid = {}
    for rec in records:
        key = (rec["mnemonic"], rec["format"])
        op = rec["op"]
        ha = rec.get("ha")
        opid = (op, str(ha))
        by_mnem_fmt.setdefault(key, []).append(rec)
        by_opid[opid] = rec["mnemonic"]
    return by_mnem_fmt, by_opid


def check_hex_word(word_str, path, line):
    m = re.match(r'^0x([0-9a-fA-F]+)$', word_str)
    if not m:
        return f"{path}:{line}: encoding.word not valid hex: {word_str!r}"
    try:
        val = int(word_str, 16)
        if val > 0xFFFFFFFF:
            return f"{path}:{line}: encoding.word > 0xFFFFFFFF: {word_str}"
    except ValueError:
        return f"{path}:{line}: encoding.word parse error: {word_str!r}"
    return None


def validate_file(filepath, opcodes_by_mnem_fmt):
    errors = []
    covered_opids = set()
    try:
        with open(filepath, "r") as f:
            cases = yaml.safe_load(f)
    except yaml.YAMLError as e:
        return ([f"{filepath}: YAML parse error: {e}"], covered_opids)

    if not isinstance(cases, list):
        return ([f"{filepath}: top-level must be a list"], covered_opids)

    for i, case in enumerate(cases):
        tag = f"{filepath} case[{i}]"

        if not isinstance(case, dict):
            errors.append(f"{tag}: case is not a mapping")
            continue

        # Check required fields
        for field in REQUIRED_FIELDS:
            if field not in case:
                errors.append(f"{tag}: missing required field '{field}'")

        mnem = case.get("mnemonic", "?")
        fmt = case.get("format", "?")
        cls = case.get("class", "?")
        status = case.get("status", "active")
        fault = case.get("expected_fault")
        word = case.get("encoding", {}).get("word") if isinstance(
            case.get("encoding"), dict) else None

        # Check class
        if cls not in ALLOWED_CLASSES:
            errors.append(f"{tag}: invalid class '{cls}'")

        # Check status
        if status not in ALLOWED_STATUS:
            errors.append(f"{tag}: invalid status '{status}'")

        # Check fault
        if fault not in ALLOWED_FAULTS:
            errors.append(f"{tag}: invalid expected_fault '{fault}'")

        # Check encoding word
        if word:
            err = check_hex_word(word, filepath, 0)
            if err:
                errors.append(err)

        # Check encoding.word matches mask/value (at least one rec)
        if word and mnem != "?" and fmt != "?":
            recs = opcodes_by_mnem_fmt.get((mnem, fmt), [])
            if recs:
                wval = int(word, 16)
                for rec in recs:
                    mask_val = int(rec["mask"], 16) if isinstance(rec["mask"], str) else rec["mask"]
                    value_val = int(rec["value"], 16) if isinstance(rec["value"], str) else rec["value"]
                    if (wval & mask_val) == value_val:
                        break
                else:
                    rec = recs[0]
                    errors.append(
                        f"{tag}: encoding.word {word} does not match "
                        f"mask={rec['mask']} value={rec['value']}")

        # Check deferred consistency
        if status == "deferred":
            if case.get("expected_state") is not None:
                errors.append(f"{tag}: status=deferred but expected_state "
                              f"is not null")
            if not case.get("deferred_reason"):
                errors.append(f"{tag}: status=deferred but "
                              f"deferred_reason is empty/missing")

        # Check mnemonic+format in opcodes
        if mnem != "?" and fmt != "?":
            key = (mnem, fmt)
            if key not in opcodes_by_mnem_fmt:
                errors.append(f"{tag}: unknown mnemonic+format: "
                              f"{mnem}({fmt})")
            elif status == "active":
                for rec in opcodes_by_mnem_fmt[key]:
                    opid = (rec["op"], str(rec.get("ha")))
                    covered_opids.add(opid)

        # Check active semantic/boundary has expected_state
        if status == "active" and cls in ("semantic", "boundary"):
            if case.get("expected_state") is None:
                errors.append(f"{tag}: {cls} case must have expected_state")

    return (errors, covered_opids)


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_dir = os.path.abspath(os.path.join(script_dir, ".."))

    opcodes_path = os.path.join(repo_dir, "tools", "opcodes.yaml")
    if not os.path.exists(opcodes_path):
        print("ERROR: tools/opcodes.yaml not found; run DL-001c first",
              file=sys.stderr)
        sys.exit(1)

    by_mnem_fmt, by_opid = load_opcodes(opcodes_path)

    vectors_dir = os.path.join(repo_dir, "tests", "vectors", "isa")
    if not os.path.isdir(vectors_dir):
        print("ERROR: tests/vectors/isa/ not found", file=sys.stderr)
        sys.exit(1)

    yaml_files = sorted(glob.glob(os.path.join(vectors_dir, "*.yaml")))
    if not yaml_files:
        print("ERROR: no YAML files in tests/vectors/isa/", file=sys.stderr)
        sys.exit(1)

    covered_opids = set()
    all_errors = []
    for fpath in yaml_files:
        errors, opids = validate_file(fpath, by_mnem_fmt)
        all_errors.extend(errors)
        covered_opids.update(opids)

    # Coverage check: every (op,ha) in opcodes must have ≥1 active case
    for opid, mnem in by_opid.items():
        if opid not in covered_opids:
            if mnem in ("rd2ra", "ra2rd"):
                continue
            all_errors.append(
                f"COVERAGE MISSING: {mnem} op={opid[0]} ha={opid[1]}")

    if all_errors:
        for e in all_errors:
            print(e, file=sys.stderr)
        sys.exit(1)

    total = 0
    for fpath in yaml_files:
        with open(fpath) as f:
            cases = yaml.safe_load(f)
            total += len(cases) if isinstance(cases, list) else 0
    print(f"validate_vectors: {len(yaml_files)} files, {total} cases, "
          f"{len(covered_opids)}/{len(by_opid)} opcodes covered OK")
    sys.exit(0)


if __name__ == "__main__":
    main()
