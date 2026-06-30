#!/usr/bin/env python3
"""Check QFC table coverage against tools/opcodes.yaml.

Parses the wiki QFC tables and compares defined (op, ha) pairs against
the opcodes.yaml encoding inventory.  Prints warnings but always exits 0
(informational only, not a CI gate).
"""
import os, re, sys, yaml

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIKI = os.path.join(os.path.dirname(REPO), "DADAO-wiki", "SimRISC-00-指令系统设计.md")


# ── helpers for row/column header parsing ───────────────────────────────

def parse_row_main(s):
    """'0001-0xxx' -> op[7:3] (5-bit integer)."""
    m = re.match(r'^(\d{4})-(\d)xxx\s*$', s)
    if m:
        return (int(m.group(1), 2) << 1) | int(m.group(2))
    return None

def parse_col_main(s):
    """'xxxx-x001' -> op[2:0] (3-bit integer)."""
    m = re.match(r'^xxxx-x(\d{3})\s*$', s)
    if m:
        return int(m.group(1), 2)
    return None

def parse_row_sub(s):
    """'000-xxx' -> ha[5:3] (3-bit integer)."""
    m = re.match(r'^(\d{3})-xxx\s*$', s)
    if m:
        return int(m.group(1), 2)
    return None

def parse_col_sub(s):
    """'xxx-000' -> ha[2:0] (3-bit integer)."""
    m = re.match(r'^xxx-(\d{3})\s*$', s)
    if m:
        return int(m.group(1), 2)
    return None


# ── table parser ────────────────────────────────────────────────────────

def parse_main_table(lines):
    """Parse main QFC table.  Returns set of (op, ha=None) for non-empty cells.

    Cells whose text matches a sub-table reference (MISC-Norm, MISC-RF,
    MISC-AMO) are **skipped** per task spec.
    """
    result = set()

    # Find the column-header line (first non-empty line that contains 'xxxx-x')
    col_line = None
    sep_idx = None
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if 'xxxx-x' in stripped and stripped.startswith('|'):
            col_line = stripped
        if '---' in stripped and stripped.startswith('|'):
            sep_idx = idx
        # stop once we pass the separator
        if sep_idx is not None and idx >= sep_idx:
            break

    if col_line is None or sep_idx is None:
        return result

    # Extract column header values
    col_parts = [c.strip() for c in col_line.split('|')]
    # col_parts[0] is empty (before first |), col_parts[1] is first cell (empty for main table), rest are column headings
    col_headers = []
    for cell in col_parts[1:]:
        if not cell:
            continue
        v = parse_col_main(cell)
        if v is not None:
            col_headers.append(v)
        else:
            col_headers.append(None)

    # Parse data rows (lines after separator)
    for line in lines[sep_idx + 1:]:
        stripped = line.strip()
        if not stripped.startswith('|'):
            continue
        parts = [c.strip() for c in stripped.split('|')]
        # parts[0] is empty
        if len(parts) < 2:
            continue
        row_hdr = parts[1]
        row_val = parse_row_main(row_hdr)
        if row_val is None:
            continue

        data_cells = parts[2:]
        for ci, cell in enumerate(data_cells):
            if ci >= len(col_headers):
                break
            if not cell:
                continue
            col_val = col_headers[ci]
            if col_val is None:
                continue
            # Skip sub-table references
            if cell in ("MISC-Norm", "MISC-RF", "MISC-AMO"):
                continue
            op = (row_val << 3) | col_val
            result.add((op, None))

    return result


def parse_sub_table(lines, parent_op):
    """Parse a sub-table (MISC-Norm / MISC-RF / MISC-AMO).

    Returns set of (parent_op, ha) for non-empty cells.
    """
    result = set()

    col_line = None
    sep_idx = None
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if 'xxx-' in stripped and stripped.startswith('|') and col_line is None:
            col_line = stripped
        if '---' in stripped and stripped.startswith('|'):
            sep_idx = idx
            break

    if col_line is None or sep_idx is None:
        return result

    # Extract column headers
    col_parts = [c.strip() for c in col_line.split('|')]
    col_headers = []
    for cell in col_parts[1:]:
        if not cell:
            continue
        v = parse_col_sub(cell)
        if v is not None:
            col_headers.append(v)
        else:
            col_headers.append(None)

    for line in lines[sep_idx + 1:]:
        stripped = line.strip()
        if not stripped.startswith('|'):
            continue
        parts = [c.strip() for c in stripped.split('|')]
        if len(parts) < 2:
            continue
        row_hdr = parts[1]
        row_val = parse_row_sub(row_hdr)
        if row_val is None:
            continue

        data_cells = parts[2:]
        for ci, cell in enumerate(data_cells):
            if ci >= len(col_headers):
                break
            if not cell:
                continue
            col_val = col_headers[ci]
            if col_val is None:
                continue
            ha = (row_val << 3) | col_val
            result.add((parent_op, ha))

    return result


# ── yaml extraction ─────────────────────────────────────────────────────

def get_yaml_opids(opcodes):
    """Return set of (op, ha) from opcodes.yaml records.

    ha may be None (main-table instruction) or an int (sub-table encoding).
    """
    result = set()
    for rec in opcodes:
        op = rec["op"]
        if isinstance(op, str):
            op = int(op, 16)
        ha = rec.get("ha")
        if ha is not None:
            if isinstance(ha, str):
                ha = int(ha, 16)
        result.add((op, ha))
    return result


# ── main ────────────────────────────────────────────────────────────────

def main():
    if not os.path.isfile(WIKI):
        print(f"check_qfc_coverage: wiki not found at {WIKI}", file=sys.stderr)
        sys.exit(0)

    with open(WIKI, encoding="utf-8") as f:
        wiki_lines = f.readlines()

    # ── locate tables by section markers ────────────────────────────────

    sections = {
        "main":      ("## SimRISC QFC",        "### MISC-Norm"),
        "MISC-Norm": ("### MISC-Norm指令编码",  "### MISC-RF"),
        "MISC-RF":   ("### MISC-RF指令编码",    "### MISC-AMO"),
        "MISC-AMO":  ("### MISC-AMO指令编码",   None),   # rest of file
    }

    table_text = {}
    for key, (start_marker, end_marker) in sections.items():
        start = None
        for i, line in enumerate(wiki_lines):
            if start_marker in line:
                start = i
                break
        if start is None:
            continue
        if end_marker is None:
            table_text[key] = wiki_lines[start + 1:]
        else:
            end = None
            for i in range(start + 1, len(wiki_lines)):
                if end_marker in wiki_lines[i]:
                    end = i
                    break
            table_text[key] = wiki_lines[start + 1:end]

    # ── parse tables ────────────────────────────────────────────────────

    wiki_ops = set()          # (op, ha) from main table
    wiki_sub = set()          # (op, ha) from sub-tables

    if "main" in table_text:
        wiki_ops = parse_main_table(table_text["main"])
    if "MISC-Norm" in table_text:
        wiki_sub |= parse_sub_table(table_text["MISC-Norm"], 0x10)

    # ── load opcodes.yaml ───────────────────────────────────────────────

    yaml_path = os.path.join(REPO, "tools", "opcodes.yaml")
    with open(yaml_path) as f:
        yaml_data = yaml.safe_load(f)
    yaml_set = get_yaml_opids(yaml_data)

    # ── compare ─────────────────────────────────────────────────────────

    # Combine wiki sets: main-table (ha=None) + sub-table (ha=int)
    wiki_all = wiki_ops | wiki_sub

    only_yaml = yaml_set - wiki_all
    only_wiki = wiki_all - yaml_set

    # Group by category for clearer reporting
    only_yaml_main = {(op, ha) for (op, ha) in only_yaml if ha is None}
    only_yaml_sub  = {(op, ha) for (op, ha) in only_yaml if ha is not None}
    only_wiki_main = {(op, ha) for (op, ha) in only_wiki if ha is None}
    only_wiki_sub  = {(op, ha) for (op, ha) in only_wiki if ha is not None}

    warnings = []

    for op, ha in sorted(only_yaml_main):
        warnings.append(f"  opcodes.yaml has main-table op=0x{op:02X} (ha=null) — not in QFC wiki")
    for op, ha in sorted(only_yaml_sub):
        warnings.append(f"  opcodes.yaml has sub-table op=0x{op:02X} ha=0x{ha:02X} — not in QFC wiki")
    for op, ha in sorted(only_wiki_main):
        warnings.append(f"  QFC wiki has main-table op=0x{op:02X} — not in opcodes.yaml")
    for op, ha in sorted(only_wiki_sub):
        warnings.append(f"  QFC wiki has sub-table op=0x{op:02X} ha=0x{ha:02X} — not in opcodes.yaml")

    if warnings:
        for w in warnings:
            print(w, file=sys.stderr)
        print(f"check_qfc_coverage: {len(only_yaml)} only in yaml, {len(only_wiki)} only in wiki", file=sys.stderr)
    else:
        print("check_qfc_coverage: all QFC cells accounted for in opcodes.yaml")

    # Always exit 0 (informational)
    sys.exit(0)


if __name__ == "__main__":
    main()
