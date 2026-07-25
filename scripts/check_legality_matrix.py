#!/usr/bin/env python3
"""ADR-0009 M3 — Generative legality matrix (first slice).

For every SPEC-derived legality rule x every applicable instruction, generate an
encoding that VIOLATES the rule, then run three cross-checks:

  check-1 QEMU     : does QEMU raise the correct fault? (ILLI/UNDI/MALIGN)
  check-2 opcodes  : is the constraint recorded in tools/opcodes.yaml `legality`?
  check-3 vectors  : is there a legality-class vector covering (instr, rule)?

Report a matrix cell per (instruction, rule): QEMU[OK/BUG] opcodes[记/漏/N/A]
vectors[有/缺]. Exit non-zero if any QEMU-BUG or opcodes-漏 (fail-closed).

★ INDEPENDENCE INVARIANT ★
The rule catalog (tools/legality_rules.yaml) is transcribed from
contracts/isa/spec.md, NOT from opcodes.yaml's `legality` field. opcodes.yaml is
read here ONLY for (a) the encoding skeleton — op/ha/format/field-roles, which is
the Appendix-A canonical inventory (itself spec) — and (b) as the check-2
cross-checked object. The `legality` field is NEVER used to decide what to test;
that is the whole point of M3 (catch what opcodes.yaml omits, e.g. DL-042b
stm* rdha!=rd0).
"""

import os
import sys
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'tests', 'scripts'))

from run_qemu_test import run_case, find_qemu  # noqa: E402

OPCODES = os.path.join(ROOT, 'tools', 'opcodes.yaml')
RULES = os.path.join(ROOT, 'tools', 'legality_rules.yaml')
VECDIR = os.path.join(ROOT, 'tests', 'vectors', 'isa')

# Aligned RAM base used by the existing vectors; +1 makes it width-misaligned.
RAM_BASE = 0x87FF0000
RAM_MISALIGNED = RAM_BASE + 1

MULTI_BLOCK = {'rd2rd', 'rd2rb', 'rb2rd', 'rb2rb'}  # orri block-copy (§2.6.3)


# ─────────────────────────── encoding helpers ──────────────────────────────
def slot_of(name):
    """Which 6-bit slot (ha/hb/hc/hd) a single-slot operand field occupies."""
    if name == 'immu6':
        return 'hd'
    for suf in ('ha', 'hb', 'hc', 'hd'):
        if name.endswith(suf):
            return suf
    return None  # multi-slot immediate (imms12/imms18/...) — irrelevant here


def base_slots(rec):
    """Legal default slot values so ONLY the targeted field violates a rule."""
    slots = {'ha': 0, 'hb': 0, 'hc': 0, 'hd': 0}
    if rec.get('ha') is not None:
        slots['ha'] = rec['ha']  # fixed minor opcode
    for f in rec['fields']:
        sl = slot_of(f['name'])
        if sl is None:
            continue
        if f['name'] == 'immu6':
            slots[sl] = 1                       # legal non-zero count
        elif f.get('bank') in ('rd', 'rb'):
            slots[sl] = 1                       # legal non-zero register
        else:
            slots[sl] = 0                       # immediate
    return slots


def encode(rec, slots):
    return ((rec['op'] & 0xFF) << 24) | ((slots['ha'] & 0x3F) << 18) | \
           ((slots['hb'] & 0x3F) << 12) | ((slots['hc'] & 0x3F) << 6) | \
           (slots['hd'] & 0x3F)


def decode_slots(word):
    return {
        'ha': (word >> 18) & 0x3F,
        'hb': (word >> 12) & 0x3F,
        'hc': (word >> 6) & 0x3F,
        'hd': word & 0x3F,
    }


def field_named(rec, name):
    for f in rec['fields']:
        if f['name'] == name:
            return f
    return None


def dst_fields(rec, bank):
    return [f for f in rec['fields']
            if f.get('role') == 'dst' and f.get('bank') == bank]


def has_field(rec, name):
    return field_named(rec, name) is not None


def mnem_width(mnem):
    """Data-access width in bytes from a load/store mnemonic; None if N/A."""
    if mnem.startswith('ld'):
        region = mnem[2:]
    elif mnem.startswith('st'):
        region = mnem[2:]
    else:
        return None
    if region.startswith('m'):
        region = region[1:]
    if not region:
        return None
    return {'b': 1, 'w': 2, 't': 4, 'o': 8}.get(region[0])


# ─────────────────────── per-rule applicability + violation ────────────────
def applicable(rule, rec):
    """Spec-derived selection. Returns (target_field_name) or None if N/A.

    NB: selection uses mnemonic / format / field-ROLE (encoding structure), never
    opcodes.yaml `legality`. The role/bank tags are Appendix-A encoding facts.
    """
    kind = rule['kind']
    mnem = rec['mnemonic']
    fmt = rec['format']

    if kind == 'reg_dest_zero':
        bank = rule['bank']
        if mnem == 'ret':                       # §2.6.1 exception: ret rdha=rd0 legal
            return None
        dsts = dst_fields(rec, bank)
        if len(dsts) == 1:                      # single-dest only (dual handled apart)
            return dsts[0]['name']
        return None

    if kind == 'store_src_zero':
        if mnem.startswith('st') and has_field(rec, 'rdha'):
            f = field_named(rec, 'rdha')
            if f.get('bank') == 'rd':
                return 'rdha'
        return None

    if kind == 'rb_store_base_zero':
        if mnem.startswith('st') and has_field(rec, 'rbha'):
            return 'rbha'
        return None

    if kind in ('dual_dest_both_zero', 'dual_dest_same'):
        if fmt == 'rrrr' and len(dst_fields(rec, 'rd')) == 2:
            return 'rdha,rdhb'
        return None

    if kind in ('immu6_zero', 'range_overflow'):
        is_multi = (fmt == 'rrri') or (mnem in MULTI_BLOCK)
        if is_multi and has_field(rec, 'immu6'):
            return 'immu6'
        return None

    if kind == 'malign':
        w = mnem_width(mnem)
        if w and w > 1 and has_field(rec, 'rbhb'):
            return 'rbhb'
        return None

    return None


def build_violation(rule, rec, target):
    """Return (word, input_state, note) for a rule violation on rec."""
    kind = rule['kind']
    slots = base_slots(rec)
    ins = {}

    if kind in ('reg_dest_zero', 'store_src_zero', 'rb_store_base_zero'):
        sl = slot_of(target)
        slots[sl] = 0
        return encode(rec, slots), ins, f"{target}={rule['bank']}0 → ILLI"

    if kind == 'dual_dest_both_zero':
        slots['ha'] = 0
        slots['hb'] = 0
        return encode(rec, slots), ins, "rdha=rdhb=rd0 (both) → ILLI"

    if kind == 'dual_dest_same':
        slots['ha'] = 5
        slots['hb'] = 5
        return encode(rec, slots), ins, "rdha=rdhb=rd5 (same non-rd0) → ILLI"

    if kind == 'immu6_zero':
        slots['hd'] = 0            # immu6 = 0
        return encode(rec, slots), ins, "immu6=0 → ILLI"

    if kind == 'range_overflow':
        # first_reg + immu6 > 64. first_reg slot = ha (rrri) or hb (orri block).
        first_slot = 'ha' if rec['format'] == 'rrri' else 'hb'
        slots[first_slot] = 63
        slots['hd'] = 2           # 63 + 2 = 65 > 64
        return encode(rec, slots), ins, "first_reg(63)+immu6(2)=65>64 → ILLI"

    if kind == 'malign':
        w = mnem_width(rec['mnemonic'])
        # base register (rbhb) holds a width-misaligned address; offset 0.
        base_f = field_named(rec, 'rbhb')
        base_reg = 2
        slots[slot_of('rbhb')] = base_reg
        ins = {'rb': {f'rb{base_reg}': f'0x{RAM_MISALIGNED:016X}'}}
        # keep any rd source (rrri rdhc) at a legal non-zero reg with value 0
        note = f"EA=0x{RAM_MISALIGNED:X} not {w}-aligned → MALIGN"
        return encode(rec, slots), ins, note

    raise ValueError(kind)


def expected_opcodes_string(rule, rec, target):
    """The static-legality string opcodes.yaml SHOULD contain (check-2)."""
    kind = rule['kind']
    if kind in ('reg_dest_zero', 'store_src_zero', 'rb_store_base_zero'):
        return f"{target} != {rule['bank']}0"
    if kind == 'dual_dest_both_zero':
        return "not (rdha == rd0 and rdhb == rd0)"
    if kind == 'dual_dest_same':
        return "not (rdha == rdhb and rdha != rd0)"
    if kind == 'immu6_zero':
        return "immu6 != 0"
    if kind == 'range_overflow':
        if rec['format'] == 'rrri':
            if has_field(rec, 'rdha'):
                first = 'rdha'
            elif has_field(rec, 'raha'):
                first = 'raha'
            else:
                first = 'rbha'
        else:
            first = dst_fields(rec, 'rd')[0]['name'] if dst_fields(rec, 'rd') \
                else dst_fields(rec, 'rb')[0]['name']
        return f"{first} + immu6 <= 64"
    return None


def _norm(s):
    return ''.join(s.split())


# ───────────────────────────── check-3 coverage ────────────────────────────
def vector_covers(rule, rec, target, vectors):
    """A legality-class vector structurally exercising this (instr, rule)."""
    for v in vectors:
        if v.get('mnemonic') != rec['mnemonic']:
            continue
        if v.get('expected_fault') != rule['fault']:
            continue
        try:
            word = int(v['encoding']['word'], 16)
        except (KeyError, TypeError, ValueError):
            continue
        d = decode_slots(word)
        kind = rule['kind']
        if kind in ('reg_dest_zero', 'store_src_zero', 'rb_store_base_zero'):
            if d[slot_of(target)] == 0:
                return True
        elif kind == 'dual_dest_both_zero':
            if d['ha'] == 0 and d['hb'] == 0:
                return True
        elif kind == 'dual_dest_same':
            if d['ha'] == d['hb'] and d['ha'] != 0:
                return True
        elif kind == 'immu6_zero':
            if d['hd'] == 0:
                return True
        elif kind == 'range_overflow':
            first = d['ha'] if rec['format'] == 'rrri' else d['hb']
            if first + d['hd'] > 64:
                return True
        elif kind == 'malign':
            return True  # any MALIGN vector for this mnemonic counts
    return False


# ───────────────────────────────── main ────────────────────────────────────
def load_reserved_cases():
    """Representative reserved encodings → UNDI (§2.5 / §2.8.1)."""
    return [
        ("MISC-Norm reserved ha=0x01", 0x10 << 24 | 0x01 << 18),
        ("MISC-Norm reserved ha=0x0C", 0x10 << 24 | 0x0C << 18),
        ("MISC-Norm reserved ha=0x26", 0x10 << 24 | 0x26 << 18),
        ("reserved major op=0x11",     0x11 << 24),
        ("reserved major op=0x18",     0x18 << 24),
    ]


def main():
    opcodes = yaml.safe_load(open(OPCODES))
    catalog = yaml.safe_load(open(RULES))['rules']
    vectors = []
    for fn in sorted(os.listdir(VECDIR)):
        if fn.endswith('.yaml'):
            vectors.extend(yaml.safe_load(open(os.path.join(VECDIR, fn))) or [])

    qemu = find_qemu()
    qemu_note = '' if qemu else '  (QEMU binary NOT found → check-1 = SKIP)'

    rows = []            # (mnem, rule_id, qemu_stat, opc_stat, vec_stat)
    qemu_bugs, opc_missing, vec_missing = [], [], []
    skipped = 0
    deferred_report = []

    print("=" * 78)
    print("ADR-0009 M3 — Generative Legality Matrix" + qemu_note)
    print("Rule source: contracts/isa/spec.md (NOT opcodes.yaml legality field)")
    print("=" * 78)

    for rule in catalog:
        if rule.get('status') == 'deferred':
            deferred_report.append((rule['id'], rule['fault'], rule['spec_cite']))
            continue

        # gather the (rule, instruction) cells
        cells = []
        if rule['kind'] == 'reserved_undi':
            for desc, word in load_reserved_cases():
                cells.append((f"reserved[{desc}]", None, None, word, {},
                              f"{desc} → UNDI"))
        else:
            for rec in opcodes:
                tgt = applicable(rule, rec)
                if tgt is None:
                    continue
                word, ins, note = build_violation(rule, rec, tgt)
                cells.append((rec['mnemonic'], rec, tgt, word, ins, note))

        if not cells:
            print(f"\n[{rule['id']}]  {rule['fault']}  {rule['spec_cite']}"
                  f"\n   (no applicable M1 instruction — not covered this phase)")
            continue

        print(f"\n[{rule['id']}]  {rule['fault']}  {rule['spec_cite']}")
        for mnem, rec, tgt, word, ins, note in cells:
            case = {
                'mnemonic': mnem, 'encoding': {'word': f"0x{word:08X}"},
                'input_state': ins, 'expected_state': None,
                'expected_fault': rule['fault'],
            }
            # check-1 QEMU
            status, detail = run_case(case, qemu_bin=qemu) if qemu else ('SKIP', 'no qemu')
            if status == 'PASS':
                qemu_stat = 'OK'
            elif status == 'SKIP':
                qemu_stat = 'SKIP'
                skipped += 1
            else:
                qemu_stat = 'BUG'
                qemu_bugs.append((mnem, rule['id'], detail))

            # check-2 opcodes
            if rule.get('check2') and rec is not None:
                want = expected_opcodes_string(rule, rec, tgt)
                have = [_norm(s) for s in (rec.get('legality') or [])]
                if want and _norm(want) in have:
                    opc_stat = '记'
                else:
                    opc_stat = '漏'
                    opc_missing.append((mnem, rule['id'], want))
            else:
                opc_stat = 'N/A'

            # check-3 vectors
            if rec is not None:
                vec_stat = '有' if vector_covers(rule, rec, tgt, vectors) else '缺'
            else:
                # reserved encodings: any UNDI vector with same word
                vec_stat = '有' if any(
                    v.get('expected_fault') == 'UNDI' and
                    int(v.get('encoding', {}).get('word', '0'), 16) == word
                    for v in vectors) else '缺'
            if vec_stat == '缺':
                vec_missing.append((mnem, rule['id']))

            rows.append((mnem, rule['id'], qemu_stat, opc_stat, vec_stat))
            print(f"   {mnem:14s} 0x{word:08X}  QEMU[{qemu_stat:4s}] "
                  f"opcodes[{opc_stat:3s}] 向量[{vec_stat}]  {note}")

    # ── deferred / not-covered ────────────────────────────────────────────
    print("\n" + "-" * 78)
    print("Deferred / not-covered this phase (state-dependent or no M1 instr):")
    for rid, fault, cite in deferred_report:
        print(f"   {rid:24s} {fault:7s} {cite}")

    # ── summary ───────────────────────────────────────────────────────────
    print("\n" + "=" * 78)
    print("SUMMARY")
    print(f"  matrix cells        : {len(rows)}")
    print(f"  QEMU-BUG  (check-1) : {len(qemu_bugs)}")
    print(f"  opcodes-漏 (check-2): {len(opc_missing)}")
    print(f"  向量-缺   (check-3) : {len(vec_missing)}")
    if skipped:
        print(f"  QEMU SKIPPED cells  : {skipped}")

    if qemu_bugs:
        print("\n  QEMU-BUG detail (report to architect):")
        for m, r, d in qemu_bugs:
            print(f"    - {m:14s} {r:22s} {d}")
    if opc_missing:
        print("\n  opcodes-漏 detail (report to architect):")
        for m, r, w in opc_missing:
            print(f"    - {m:14s} {r:22s} missing legality: {w!r}")
    if vec_missing:
        print(f"\n  向量-缺 detail ({len(vec_missing)} cells, report to architect):")
        for m, r in vec_missing:
            print(f"    - {m:14s} {r}")

    print("=" * 78)

    # fail-closed: QEMU-BUG or opcodes-漏 → non-zero. 向量-缺 is reported, not fatal
    # (first-round expectation per task; vector backlog goes to architect).
    if skipped and not qemu:
        print("NOTE: QEMU unavailable — check-1 inconclusive; not asserting QEMU pass.")
    if qemu_bugs or opc_missing:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
