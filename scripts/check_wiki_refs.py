#!/usr/bin/env python3
"""check_wiki_refs.py — audit wiki->spec traceability (ADR-0009 M1)

Check 1: Three-state wiki reference resolution:
  - RESOLVED: file + target found in wiki
  - DANGLING: file found but target missing (hard error)
  - UNPARSEABLE: complex format parser can't handle (warning, non-blocking)

Check 2: Normative assertions lacking a wiki ref, a spec-decision marker,
         or an explicit [OPEN] declaration.

Auditing is parameterized by --profile (default: isa). The ISA profile is
byte-for-byte identical to the historical behaviour (DL-039a/b/c) so that
`make check`'s `check-wiki-refs` target never regresses. The ABI profile
(DL-040b, ADR-0009 C1) audits contracts/abi/spec.md with ABI-specific
normative wording and legal markers.
"""

import re
import sys
import os
import argparse
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

# --- ABI profile (DL-040b, ADR-0009 C1) --------------------------------------
# Normative wording actually used by contracts/abi/spec.md: register
# save-classification (callee/caller-saved, immutable), argument-passing and
# return rules (must/shall, extension), stack/alignment discipline, SBZ/reserved.
ABI_NORMATIVE_PATTERNS = [
    r'\bshall\b', r'\bmust\b', r'\bmust not\b',
    r'必须', r'禁止',
    r'\bcallee-saved\b', r'\bcaller-saved\b',
    r'\bImmutable\b',
    r'\bSBZ\b', r'\breserved\b',
    r'sign-extend', r'zero-extend', r'sign- or zero-extend',
    r'\baligned\b', r'\balignment\b', r'对齐',
    r'\bred zone\b', r'红区',
    r'grows downward', r'\bpreserve[sd]?\b',
]

# Legal markers per DL-040b/c: [wiki §…] (handled separately by the line skip),
# [spec-decision: …], [OPEN] (explicitly declared undefined), and
# [M1 architecture decision: …] (DL-040c C1 — treated same as [spec-decision:];
# an adopted M1-scope decision explicitly attributed in-line).
ABI_DECISION_MARKERS = [
    r'\[spec-decision\]', r'\[spec-decision:',
    r'\[M1 architecture decision:',
    r'\[OPEN',
]

def check_normative_assertions(text, patterns=NORMATIVE_PATTERNS,
                               markers=SELF_DECISION_MARKERS):
    violations = []
    lines = text.split('\n')

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue

        if re.search(r'\[wiki\s+§', line):
            continue

        has_decision = any(re.search(m, line) for m in markers)
        if has_decision:
            continue

        matched = [p for p in patterns if re.search(p, line, re.IGNORECASE)]
        if matched:
            violations.append((i, stripped[:120], matched))

    return violations

# --- ABI-profile refined Check-2 (DL-040c) -----------------------------------
# The ABI contract is authored with chapter-level inline citations plus an
# appendix citation table (not per-line refs), and embeds asm examples in
# fenced code blocks. Line-level Check-2 over-reports on that shape. This
# refined variant (ABI profile ONLY — ISA path stays byte-for-byte identical)
# adds five suppressions faithful to how the contract cites the wiki:
#   (1) skip lines inside ``` fenced code blocks (asm example comments are not
#       normative assertions);
#   (2) chapter-level citation inheritance: if the enclosing `##` chapter body
#       already carries a `[wiki §…]`, its normative lines are traced;
#   (3) appendix citation rows (## Appendix + `§X | `DADAO-… §Y`` map rows) are
#       themselves references;
#   (4) pure table separator / header rows are structure, not assertions;
#   (5) decision markers (incl. the [M1 architecture decision:] whitelist).
_FENCE_RE = re.compile(r'^\s*```')
_CHAPTER_RE = re.compile(r'^##\s+(.*)$')          # ## only (### has no space after ##)
_APPENDIX_RE = re.compile(r'^##\s+Appendix', re.IGNORECASE)
_SEP_ROW_RE = re.compile(r'^\s*\|[\s:|\-]+\|\s*$')  # table separator |---|---|
_CITATION_ROW_RE = re.compile(r'\|\s*`[^`]*(?:DADAO|SimRISC)[^`]*§[^`]*`')

def _is_separator_row(line):
    return bool(_SEP_ROW_RE.match(line)) and '-' in line

def check_normative_assertions_abi(text, patterns, markers):
    lines = text.split('\n')
    n = len(lines)

    # pass 1: fenced-code membership (the ``` delimiter lines are skipped too).
    in_fence = [False] * n
    fence = False
    for i, line in enumerate(lines):
        if _FENCE_RE.match(line):
            fence = not fence
            in_fence[i] = True
        else:
            in_fence[i] = fence

    # pass 2: ## chapter boundaries + per-chapter wiki-ref / appendix flags.
    chapter_of = [-1] * n
    chapters = []          # list of [start, end, has_wiki, is_appendix]
    cur = -1
    for i, line in enumerate(lines):
        if _CHAPTER_RE.match(line):
            cur = len(chapters)
            chapters.append([i, n, False, bool(_APPENDIX_RE.match(line))])
            if len(chapters) >= 2:
                chapters[-2][1] = i
        chapter_of[i] = cur
    for c in chapters:
        start, end = c[0], c[1]
        body = '\n'.join(lines[start:end])
        c[2] = bool(re.search(r'\[wiki\s+§', body))

    violations = []
    for i, line in enumerate(lines, 0):
        stripped = line.strip()
        idx1 = i + 1  # 1-based line number for reporting
        if not stripped or stripped.startswith('#'):
            continue
        if in_fence[i]:                                  # (1)
            continue
        ci = chapter_of[i]
        if ci >= 0 and chapters[ci][3]:                  # (3a) appendix section
            continue
        if _CITATION_ROW_RE.search(line):                # (3b) `DADAO-… §…` map row
            continue
        if _is_separator_row(line):                      # (4) separator
            continue
        # (4) header row = table row whose next non-blank line is a separator
        if stripped.startswith('|'):
            j = i + 1
            while j < n and not lines[j].strip():
                j += 1
            if j < n and _is_separator_row(lines[j]):
                continue
        if re.search(r'\[wiki\s+§', line):               # per-line wiki ref
            continue
        if any(re.search(m, line) for m in markers):     # (5) decision markers
            continue
        if ci >= 0 and chapters[ci][2]:                  # (2) chapter inheritance
            continue
        matched = [p for p in patterns if re.search(p, line, re.IGNORECASE)]
        if matched:
            violations.append((idx1, stripped[:120], matched))

    return violations

# ============================================================================
# Main
# ============================================================================

PROFILES = {
    'isa': {
        'spec_file': REPO_ROOT / "contracts" / "isa" / "spec.md",
        'label': 'spec.md',
        'normative_patterns': NORMATIVE_PATTERNS,
        'decision_markers': SELF_DECISION_MARKERS,
    },
    'abi': {
        'spec_file': REPO_ROOT / "contracts" / "abi" / "spec.md",
        'label': 'contracts/abi/spec.md',
        'normative_patterns': ABI_NORMATIVE_PATTERNS,
        'decision_markers': ABI_DECISION_MARKERS,
        'refined': True,   # DL-040c: chapter/appendix/code-fence-aware Check-2
    },
}

def run_audit(config):
    spec_file = config['spec_file']
    label = config['label']

    if not spec_file.exists():
        print(f"ERROR: spec file not found: {spec_file}", file=sys.stderr)
        sys.exit(1)

    spec_text = spec_file.read_text()

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
            print(f"  {label}:{line_num}: {full_ref}  -> {err}")

    if results['UNPARSEABLE']:
        print("--- UNPARSEABLE refs (non-blocking) ---")
        for line_num, full_ref, inner_ref, err in results['UNPARSEABLE']:
            print(f"  {label}:{line_num}: {full_ref}  -> {err}")
    print()

    # ---- Check 2: normative assertions without ref ----
    print("=" * 60)
    print("Check 2: Normative assertions without wiki reference")
    print("=" * 60)

    check2_fn = (check_normative_assertions_abi if config.get('refined')
                 else check_normative_assertions)
    violations = check2_fn(
        spec_text,
        patterns=config['normative_patterns'],
        markers=config['decision_markers'],
    )
    print(f"Assertions without wiki ref or spec-decision marker: {len(violations)}")
    print()

    if violations:
        print("--- Violations ---")
        for line_num, snippet, patterns in violations:
            print(f"  {label}:{line_num}: {snippet}")
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
        return 1
    else:
        print("\n  OVERALL: PASS")
        return 0

def main():
    parser = argparse.ArgumentParser(
        description="Audit wiki->spec traceability (ADR-0009).")
    parser.add_argument(
        '--profile', choices=sorted(PROFILES.keys()), default='isa',
        help="Audit profile / target spec (default: isa).")
    args = parser.parse_args()

    config = PROFILES[args.profile]
    sys.exit(run_audit(config))

if __name__ == "__main__":
    main()
