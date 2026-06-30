#!/usr/bin/env python3
"""Validate lit OBJ bytes against tools/opcodes.yaml encoding oracle."""
import sys, os, re, glob, yaml

def load_opcodes(path):
    with open(path) as f:
        return yaml.safe_load(f)

def check_one(word_val, records):
    for rec in records:
        msk = int(rec["mask"], 16) if isinstance(rec["mask"], str) else rec["mask"]
        val = int(rec["value"], 16) if isinstance(rec["value"], str) else rec["value"]
        if (word_val & msk) == val:
            return True
    return False

def main():
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    opcodes = load_opcodes(os.path.join(repo, "tools", "opcodes.yaml"))
    lit_dir = os.path.join(repo, "tests", "lit", "MC", "Dadao")

    obj_pattern = re.compile(r'# OBJ:\s*([0-9a-fA-F]{2})\s+([0-9a-fA-F]{2})\s+([0-9a-fA-F]{2})\s+([0-9a-fA-F]{2})')
    warnings = []
    total = 0

    for fpath in sorted(glob.glob(os.path.join(lit_dir, "*.s"))):
        with open(fpath) as f:
            for lineno, line in enumerate(f, 1):
                m = obj_pattern.search(line)
                if m:
                    word = int(m.group(1) + m.group(2) + m.group(3) + m.group(4), 16)
                    total += 1
                    if not check_one(word, opcodes):
                        warnings.append(f"WARN: {os.path.basename(fpath)}:{lineno}: word 0x{word:08X} matches no opcode")

    if warnings:
        for w in warnings:
            print(w, file=sys.stderr)
        print(f"check_lit_bytes: {total} patterns, {len(warnings)} warnings", file=sys.stderr)
        sys.exit(1)
    print(f"check_lit_bytes: {total} patterns OK")
    sys.exit(0)

if __name__ == "__main__":
    main()
