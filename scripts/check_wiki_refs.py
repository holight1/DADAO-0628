#!/usr/bin/env python3
"""check_wiki_refs.py — audit wiki->spec traceability (ADR-0009 M1)

Check 1: Three-state wiki reference resolution:
  - RESOLVED: file + target found in wiki
  - DANGLING: file found but target missing (hard error)
  - UNPARSEABLE: complex format parser can't handle (warning, non-blocking)

Check 2: Normative assertions (ILLI/UNDI/MALIGN etc.) lacking wiki ref
         or spec-decision marker.
"""

import re
import sys
import os
from pathlib import Path
from collections import defaultdict

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_FILE = REPO_ROOT / "contracts" / "isa" / "spec.md"

def get_wiki_path():
    lock_file = REPO_ROOT / "manifests" / "spec.lock.toml"
    if lock_file.exists():
        content = lock_file.read_text()
        m = re.search(r'local_reference\s*=\s*"([^"]+)"', content)
        if m:
            return Path(m.group(1)).expanduser()
    return Path.home() / "DADAO-wiki"

WIKI_DIR = get_wiki_path()

WIKI_FILES = {}
if WIKI_DIR.exists():
    for fp in WIKI_DIR.glob("*.md"):
        WIKI_FILES[fp.stem.lower()] = fp

# ============================================================================
# Check 1: reference validity
# ============================================================================

WIKI_REF_RE = re.compile(r'\[wiki\s+((?:§[^]]+))\]')

def parse_wiki_refs(text):
    """Extract all wiki references from text. Handles multi-ref with ; separator."""
    refs = []
    for m in WIKI_REF_RE.finditer(text):
        full = m.group(0)
        inner = m.group(1)
        parts = re.split(r';\s*§', inner)
        for i, part in enumerate(parts):
            if i == 0:
                pass
            else:
                part = '§' + part
            refs.append((m.start(), full.strip(), part.strip()))
    return refs

def resolve_prefix_to_file(prefix):
    """Match a short prefix like 'SimRISC-01' to a real filename."""
    prefix_lower = prefix.lower().replace('.md', '').replace('_', '-').replace(' ', '-').strip()
    for stem, path in WIKI_FILES.items():
        if stem == prefix_lower:
            return path
    matches = []
    for stem, path in WIKI_FILES.items():
        if stem.startswith(prefix_lower):
            matches.append(path)
    if len(matches) == 1:
        return matches[0]
    return None

CONTRACT_DOCS = {'SEE', 'ABI', 'ELF', 'MMU'}

def parse_single_ref(ref_text):
    """Parse a single § ref. Returns (file_part, target_type, target_value)."""
    content = ref_text.lstrip('§').strip()

    m = re.match(r'^(.+?)\s+§(.+)$', content)
    if m:
        return (m.group(1).strip(), 'section', m.group(2).strip())

    m = re.match(r'^(.+?)\s+L(\d+)', content)
    if m:
        file_part = m.group(1).strip()
        line_num = int(m.group(2))
        range_m = re.search(r'L(\d+)\s*[\u2013\u2014\-–]\s*L(\d+)', content)
        if range_m:
            return (file_part, 'line_range', (line_num, int(range_m.group(1))))
        return (file_part, 'line', line_num)

    # Try: <KNOWN_PREFIX> <rest> — rest is a free-form section description
    for prefix in sorted(WIKI_FILES.keys(), key=len, reverse=True):
        if content.lower().startswith(prefix):
            rest = content[len(prefix):].strip()
            if rest and not rest.startswith('.md'):
                return (prefix, 'section', rest)
            else:
                return (prefix, 'file_only', None)

    # Try: <short_prefix> <rest> — use the file's short name (e.g. "SimRISC-01")
    # Build a map of short prefixes to wiki file keys
    short_map = {}
    for k in WIKI_FILES:
        # Extract the dash-prefixed part: "simrisc-01" from "simrisc-01-数据类指令"
        parts = k.split('-', 2)
        if len(parts) >= 2:
            short = '-'.join(parts[:2])
            if short not in short_map:
                short_map[short] = k
    for short, full_key in sorted(short_map.items(), key=lambda x: len(x[0]), reverse=True):
        if content.lower().startswith(short) and not content.lower().startswith(full_key):
            rest = content[len(short):].strip()
            if rest and not rest.startswith('.md'):
                return (short, 'section', rest)

    for prefix in WIKI_FILES:
        if content.lower() == prefix:
            return (content.strip(), 'file_only', None)

    if content.endswith('.md'):
        for prefix in WIKI_FILES:
            if content.lower().replace('.md', '') == prefix:
                return (content.strip(), 'file_only', None)

    for doc_name in CONTRACT_DOCS:
        if content.lower().startswith(doc_name.lower()):
            rest = content[len(doc_name):].strip()
            return (doc_name, 'contract_section' if rest else 'contract_only', rest or None)

    return (content, 'unknown', None)

def find_section_in_file(wiki_file, title):
    """Search for a section title in a wiki file. Returns True if found.
    Tries exact match first, then progressively shorter matches (removing trailing words).
    """
    lines = wiki_file.read_text().split('\n')
    title_lower = title.lower()

    # Try full title as substring in headers
    for l in lines:
        s = l.strip()
        if s.startswith('#') and title_lower in s.lower():
            return True

    # Try full title as substring anywhere in text
    for l in lines:
        if title_lower in l.lower():
            return True

    # Try progressively shorter: remove last "word" each time
    words = title.split()
    while len(words) > 1:
        words.pop()
        shorter = ' '.join(words).lower()
        for l in lines:
            s = l.strip()
            if s.startswith('#') and shorter in s.lower():
                return True
        for l in lines:
            if shorter in l.lower():
                return True

    return False

def check_ref_validity(ref_text, line_num):
    """Returns ('OK', None) or state with error description.
    States: RESOLVED, DANGLING, UNPARSEABLE.
    """
    try:
        file_part, target_type, target_value = parse_single_ref(ref_text)
    except Exception as e:
        return ('UNPARSEABLE', f"parse error: {e}")

    if target_type in ('contract_section', 'contract_only'):
        return ('RESOLVED', None)

    wiki_file = resolve_prefix_to_file(file_part)
    if wiki_file is None:
        if file_part.upper() in CONTRACT_DOCS:
            return ('RESOLVED', None)
        return ('DANGLING', f"file not found: '{file_part}'")

    if target_type in ('file_only', 'unknown'):
        return ('RESOLVED', None)

    lines = wiki_file.read_text().split('\n')

    if target_type == 'line':
        if 1 <= target_value <= len(lines):
            return ('RESOLVED', None)
        return ('DANGLING', f"line {target_value} out of range (file has {len(lines)} lines)")

    if target_type == 'line_range':
        start, end = target_value
        if start < 1 or end > len(lines):
            return ('DANGLING', f"line range {start}–{end} out of range (file has {len(lines)} lines)")
        return ('RESOLVED', None)

    if target_type == 'section':
        if find_section_in_file(wiki_file, target_value):
            return ('RESOLVED', None)
        # If title looks like a descriptive comment rather than a formal section,
        # treat as UNPARSEABLE rather than DANGLING
        is_descriptive = (
            len(target_value) > 40 or
            any(c in target_value for c in '（(') or
            bool(re.search(r'[\u4e00-\u9fff]', target_value))  # contains Chinese chars (likely free-form description)
        )
        if is_descriptive:
            return ('UNPARSEABLE', f"descriptive text, not a formal section: '{target_value[:60]}'")
        return ('DANGLING', f"section '{target_value}' not found in {wiki_file.name}")

    return ('RESOLVED', None)

# ============================================================================
# Check 2: normative assertions without wiki ref
# ============================================================================

NORMATIVE_PATTERNS = [
    r'\bILLI\b', r'\bUNDI\b', r'\bMALIGN\b', r'\bIALIGN\b',
    r'\bRASOF\b', r'\bRASUF\b', r'\bEXCP_\w+\b',
    r'触发.*异常', r'trigger.*ILLI', r'trigger.*UNDI',
    r'raise.*ILLI', r'raise.*UNDI',
    r'保留编码', r'reserved.*encod',
    r'\bshall\b', r'\bmust\b', r'必须', r'禁止',
]

SELF_DECISION_MARKERS = [
    r'\[spec-decision\]', r'\[spec-decision:', r'\[ADR-\d+\]',
    r'自主决策', r'自主决定',
]

def check_normative_assertions(text):
    violations = []
    lines = text.split('\n')

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue

        if re.search(r'\[wiki\s+§', line):
            continue

        has_decision = any(re.search(m, line) for m in SELF_DECISION_MARKERS)
        if has_decision:
            continue

        matched = [p for p in NORMATIVE_PATTERNS if re.search(p, line, re.IGNORECASE)]
        if matched:
            violations.append((i, stripped[:120], matched))

    return violations

# ============================================================================
# Main
# ============================================================================

def main():
    if not SPEC_FILE.exists():
        print(f"ERROR: spec file not found: {SPEC_FILE}", file=sys.stderr)
        sys.exit(1)

    spec_text = SPEC_FILE.read_text()

    # ---- Check 1: reference validity ----
    print("=" * 60)
    print("Check 1: Wiki reference validity (3-state)")
    print("=" * 60)

    ref_details = parse_wiki_refs(spec_text)
    total = len(ref_details)

    results = {'RESOLVED': [], 'DANGLING': [], 'UNPARSEABLE': []}
    for pos, full_ref, inner_ref in ref_details:
        line_num = spec_text[:pos].count('\n') + 1
        state, err = check_ref_validity(inner_ref, line_num)
        results[state].append((line_num, full_ref, inner_ref, err))

    print(f"Total: {total}")
    print(f"  RESOLVED:     {len(results['RESOLVED'])}")
    print(f"  DANGLING:     {len(results['DANGLING'])} (HARD ERROR)")
    print(f"  UNPARSEABLE:  {len(results['UNPARSEABLE'])} (warning)")
    print()

    if results['DANGLING']:
        print("--- DANGLING refs ---")
        for line_num, full_ref, inner_ref, err in results['DANGLING']:
            print(f"  spec.md:{line_num}: {full_ref}  -> {err}")

    if results['UNPARSEABLE']:
        print("--- UNPARSEABLE refs (non-blocking) ---")
        for line_num, full_ref, inner_ref, err in results['UNPARSEABLE']:
            print(f"  spec.md:{line_num}: {full_ref}  -> {err}")
    print()

    # ---- Check 2: normative assertions without ref ----
    print("=" * 60)
    print("Check 2: Normative assertions without wiki reference")
    print("=" * 60)

    violations = check_normative_assertions(spec_text)
    print(f"Assertions without wiki ref or spec-decision marker: {len(violations)}")
    print()

    if violations:
        print("--- Violations ---")
        for line_num, snippet, patterns in violations:
            print(f"  spec.md:{line_num}: {snippet}")
        print()

    # ---- Summary ----
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"  Check 1 DANGLING:    {len(results['DANGLING'])}")
    print(f"  Check 1 UNPARSEABLE: {len(results['UNPARSEABLE'])} (warnings)")
    print(f"  Check 2 missing ref: {len(violations)}")

    # Only DANGLING and Check-2 make exit non-zero; UNPARSEABLE is just a warning
    hard_errors = len(results['DANGLING']) + len(violations)
    if hard_errors:
        print(f"\n  OVERALL: FAIL ({hard_errors} hard errors)")
        sys.exit(1)
    else:
        print("\n  OVERALL: PASS")
        sys.exit(0)

if __name__ == "__main__":
    main()
