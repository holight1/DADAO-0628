#!/usr/bin/env python3
"""dadao_interp.py — DADAO SimRISC M1 Python golden model (ADR-0009 M2a).

INDEPENDENCE CONTRACT (ADR-0009 §M2a, §独立性保证)
--------------------------------------------------
This interpreter is an INDEPENDENT reimplementation of DADAO SimRISC semantics.
Its ONLY sources are:
  * decode  ← tools/opcodes.yaml (mask/value + field layout)
  * semantics ← contracts/isa/spec.md (every handler cites the §section)
It DELIBERATELY does NOT read QEMU's target/dadao/translate.c or helper.c.
The whole point of `interpreter vs QEMU` differencing is that the two are
independent projections of the spec; copying QEMU would make the diff circular.

SCOPE (DL-042a first phase = core slice):
  * RD arithmetic     : addi, add, sub, muls, mulu, divs, divu   (spec §3.5-§3.7)
  * RD load/store     : ldbs/ldbu/ldws/ldwu/ldts/ldtu/ldo, stb/stw/stt/sto,
                        ldm*/stm* (multi)                          (spec §3.1-§3.4)
  * RB load/store     : ldo(0x43), ldmo(0x47), sto(0x4B), stmo(0x4F) (spec §4.1-§4.2)
  * Control flow      : brn/brnn/brz/brnz/brp/brnp, breq/brne,
                        jump, call, ret + RegRAS                    (spec §5)
  * swym / unimp                                                   (spec §6)
Out of this phase (decoder recognises them but semantics unimplemented →
reported as "unsupported", NOT executed): RD wyde/logic/shift/compare/
cond-assign, RB arithmetic/compare/wyde/block-copy, rela.

FAULTS (precise, no architectural side effect — spec §2.7):
  ILLI  operand legality (spec §2.6, §3.x, §4.x) + int div-by-zero / INT64_MIN÷-1 (§3.7)
  UNDI  reserved encoding / unimp                 (spec §2.5, §6.2)
  MALIGN unaligned load/store                     (spec §3.1)
  IALIGN PC not 4-aligned                         (spec §2.1)
  RASOF/RASUF RegRAS overflow / underflow         (spec §5.6)
"""

import os
import yaml

MASK64 = (1 << 64) - 1
MASK48 = (1 << 48) - 1
MASK128 = (1 << 128) - 1
INT64_MIN = -(1 << 63)
INT64_MAX = (1 << 63) - 1

DEFAULT_PC = 0x80000000   # matches test-machine BINARY_BASE (ADR-0004 harness)

_HERE = os.path.dirname(os.path.abspath(__file__))
_OPCODES_PATH = os.path.join(_HERE, 'opcodes.yaml')


class Fault(Exception):
    """Precise architectural exception (spec §2.7)."""
    def __init__(self, kind, detail=''):
        self.kind = kind
        super().__init__(f'{kind}: {detail}' if detail else kind)


class Unsupported(Exception):
    """Instruction is decodable but its semantics are out of this phase."""
    def __init__(self, mnemonic, fmt):
        self.mnemonic = mnemonic
        self.fmt = fmt
        super().__init__(f'unsupported in DL-042a slice: {mnemonic}({fmt})')


# ─── decode table (driven by opcodes.yaml, NOT hand-coded) ───────────────────

def _load_records(path=_OPCODES_PATH):
    with open(path) as f:
        recs = yaml.safe_load(f)
    out = []
    for r in recs:
        mask = int(r['mask'], 16) if isinstance(r['mask'], str) else r['mask']
        value = int(r['value'], 16) if isinstance(r['value'], str) else r['value']
        out.append((mask, value, r))
    return out


_RECORDS = _load_records()


def _parse_bits(spec):
    hi, lo = spec.strip('[]').split(':')
    return int(hi), int(lo)


def _sext(val, bits):
    if val & (1 << (bits - 1)):
        return val - (1 << bits)
    return val


def decode(word):
    """Return (record, fields) for a 32-bit instruction word.

    Driven entirely by opcodes.yaml mask/value + field bit-ranges.
    Raises Fault(UNDI) for reserved encodings (spec §2.5)."""
    word &= 0xFFFFFFFF
    match = None
    for mask, value, rec in _RECORDS:
        if (word & mask) == value:
            match = rec
            break
    if match is None:
        raise Fault('UNDI', f'reserved encoding 0x{word:08X}')
    fields = {}
    for fld in match['fields']:
        hi, lo = _parse_bits(fld['bits'])
        raw = (word >> lo) & ((1 << (hi - lo + 1)) - 1)
        if fld.get('role') == 'imm' and fld.get('signed'):
            fields[fld['name']] = _sext(raw, hi - lo + 1)
        else:
            fields[fld['name']] = raw
    return match, fields


# ─── architectural state ─────────────────────────────────────────────────────

class State:
    def __init__(self):
        self.rd = [0] * 64
        self.rb = [0] * 64
        self.rf = [0] * 64
        self.ra = [0] * 64
        self.mem = {}          # addr[47:0] -> byte
        self.pc = DEFAULT_PC
        self.pc_next = None

    # RD: rd0 hardwired zero (spec §1.2)
    def rd_read(self, n):
        return 0 if n == 0 else (self.rd[n] & MASK64)

    def rd_write(self, n, v):
        if n == 0:                       # rd0 write = no-op (dual-dest discard)
            return
        self.rd[n] = v & MASK64

    # RB: rb0 = PC+4, hardware-maintained (spec §1.3)
    def rb_read(self, n):
        return self.rb[n] & MASK64

    def rb_write(self, n, v):
        self.rb[n] = v & MASK64

    def load_mem(self, ea, n):
        ea &= MASK48
        v = 0
        for i in range(n):
            v = (v << 8) | self.mem.get((ea + i) & MASK48, 0)   # big-endian §2.1
        return v

    def store_mem(self, ea, n, val):
        ea &= MASK48
        for i in range(n):
            self.mem[(ea + i) & MASK48] = (val >> (8 * (n - 1 - i))) & 0xFF


def build_state(input_state, pc=DEFAULT_PC):
    """Construct a State from a vector `input_state` mapping."""
    st = State()
    st.pc = pc
    st.rb[0] = (pc + 4) & MASK48          # rb0 = current_PC + 4 (spec §1.3)
    input_state = input_state or {}
    for name, val in (input_state.get('rd') or {}).items():
        st.rd[int(name[2:])] = int(val, 16) & MASK64
    for name, val in (input_state.get('rb') or {}).items():
        st.rb[int(name[2:])] = int(val, 16) & MASK64
    for entry in (input_state.get('memory') or []):
        addr = int(entry['address'], 16)
        width = entry.get('width', 8)
        v = entry['value']
        v = int(v, 16) if isinstance(v, str) else v
        st.store_mem(addr, width, v)
    return st


# ─── legality (spec §2.6, §3.x, §4.x — NOT copied from QEMU) ──────────────────

# Which op codes are multi-register (immu6 range + bank-boundary rules, §2.6.3)
_RD_LOADS = {0x30, 0x31, 0x32, 0x40, 0x41, 0x42, 0x33}     # rdha != rd0 (§3.1)
_RD_STORES = {0x38, 0x39, 0x3A, 0x3B}                       # rdha != rd0 (§3.2/§2.6.1)
_RD_MLOADS = {0x34, 0x35, 0x36, 0x37, 0x44, 0x45, 0x46}     # §3.3
_RD_MSTORES = {0x3C, 0x3D, 0x3E, 0x3F}                      # §3.4
_RB_LOADS = {0x43}                                          # rbha != rb0 (§4.1)
_RB_MLOADS = {0x47}                                         # §4.2
_RB_STORES = {0x4B}                                         # sto-rb (§4.1)
_RB_MSTORES = {0x4F}                                        # stmo-rb (§4.2)
_DUAL_DEST = {0x1A, 0x1B, 0x1C, 0x1D, 0x1E, 0x1F}           # add/sub/mul/div (§2.6.1)


def _check_multi_range(first, count, bank):
    # spec §2.6.3: immu6=0 → ILLI; first+count > 64 → ILLI (no wrap)
    if count == 0:
        raise Fault('ILLI', 'immu6 == 0 (spec §2.6.3)')
    if first + count > 64:
        raise Fault('ILLI', f'{bank}{first}+{count} > 64 (spec §2.6.3)')


def check_legality(op, ha, f):
    """Raise Fault(ILLI) on static operand-legality violation (spec §2.6)."""
    if op in _RD_LOADS:
        if f['rdha'] == 0:
            raise Fault('ILLI', 'rdha == rd0 (spec §2.6.1/§3.1)')
    elif op in _RD_STORES:
        # spec §2.6.1: store data source rdha == rd0 → ILLI.
        # NOTE: opcodes.yaml store records carry legality:[] (omission) — the
        # rule is taken from spec §3.2/§2.6.1, not from opcodes.yaml.
        if f['rdha'] == 0:
            raise Fault('ILLI', 'store from rd0 (spec §2.6.1/§3.2)')
    elif op in _RD_MLOADS:
        if f['rdha'] == 0:
            raise Fault('ILLI', 'rdha == rd0 (spec §2.6.1/§3.3)')
        _check_multi_range(f['rdha'], f['immu6'], 'rd')
    elif op in _RD_MSTORES:
        if f['rdha'] == 0:
            raise Fault('ILLI', 'store from rd0 (spec §2.6.1/§3.4)')
        _check_multi_range(f['rdha'], f['immu6'], 'rd')
    elif op in _RB_LOADS or op in _RB_STORES:
        if f['rbha'] == 0:
            raise Fault('ILLI', 'rbha == rb0 (spec §2.6.2/§4.1)')
    elif op in _RB_MLOADS or op in _RB_MSTORES:
        if f['rbha'] == 0:
            raise Fault('ILLI', 'rbha == rb0 (spec §2.6.2/§4.2)')
        _check_multi_range(f['rbha'], f['immu6'], 'rb')
    elif op == 0x19:                                  # addi RD (§3.6)
        if f['rdha'] == 0:
            raise Fault('ILLI', 'rdha == rd0 (spec §3.6)')
    elif op in _DUAL_DEST:                            # add/sub/mul/div (§2.6.1)
        a, b = f['rdha'], f['rdhb']
        if a == 0 and b == 0:
            raise Fault('ILLI', 'both dst == rd0 (spec §2.6.1)')
        if a == b and a != 0:
            raise Fault('ILLI', 'rdha == rdhb non-rd0 (spec §2.6.1)')


# ─── condition flags (spec Appendix B) ───────────────────────────────────────

def _cond(mnemonic, v):
    neg = (v >> 63) & 1
    if mnemonic == 'brn':
        return neg == 1
    if mnemonic == 'brnn':
        return neg == 0
    if mnemonic == 'brz':
        return v == 0
    if mnemonic == 'brnz':
        return v != 0
    if mnemonic == 'brp':
        return neg == 0 and v != 0
    if mnemonic == 'brnp':
        return neg == 1 or v == 0
    raise AssertionError(mnemonic)


# ─── RegRAS (spec §5.6) ──────────────────────────────────────────────────────

def _ras_push(st, new_addr):
    new_addr &= MASK48
    top = st.ra[63]
    cnt = (top >> 48) & 0xFFFF
    addr48 = top & MASK48
    if cnt == 0:
        st.ra[63] = (1 << 48) | new_addr
    elif 1 <= cnt <= 0xFFFE and addr48 == new_addr:
        st.ra[63] = ((cnt + 1) << 48) | addr48       # recursion collapse
    else:
        if ((st.ra[1] >> 48) & 0xFFFF) != 0:
            raise Fault('RASOF', 'RegRAS overflow (spec §5.6)')
        for i in range(2, 64):                        # ra{i-1} <- ra{i}
            st.ra[i - 1] = st.ra[i]
        st.ra[63] = (1 << 48) | new_addr


def _ras_pop(st):
    top = st.ra[63]
    cnt = (top >> 48) & 0xFFFF
    addr48 = top & MASK48
    if cnt > 1:
        st.ra[63] = ((cnt - 1) << 48) | addr48
        return addr48
    if cnt == 1:
        for i in range(62, 0, -1):                    # ra{i+1} <- ra{i}
            st.ra[i + 1] = st.ra[i]
        st.ra[1] = 0
        return addr48
    raise Fault('RASUF', 'RegRAS underflow (spec §5.6)')


# ─── memory access helpers (load/store, spec §3.1-§3.4, §4.1-§4.2) ───────────

# op -> (width_bytes, signed_or_None)
_LD_INFO = {
    0x30: (1, True),  0x31: (2, True),  0x32: (4, True),  0x33: (8, None),
    0x40: (1, False), 0x41: (2, False), 0x42: (4, False), 0x43: (8, None),
    0x34: (1, True),  0x35: (2, True),  0x36: (4, True),  0x37: (8, None),
    0x44: (1, False), 0x45: (2, False), 0x46: (4, False), 0x47: (8, None),
}
_ST_INFO = {
    0x38: 1, 0x39: 2, 0x3A: 4, 0x3B: 8, 0x4B: 8,
    0x3C: 1, 0x3D: 2, 0x3E: 4, 0x3F: 8, 0x4F: 8,
}


def _extend(val, width, signed):
    if signed:                                        # sign-extend to 64 (§3.1)
        return _sext(val, width * 8) & MASK64
    return val & MASK64                               # zero-extend / octa


def _check_align(ea, width):
    # spec §3.1: byte no fault; wyde/tetra/octa must be naturally aligned.
    if width > 1 and (ea % width) != 0:
        raise Fault('MALIGN', f'ea=0x{ea:X} width={width} (spec §3.1)')


# ─── main execute ────────────────────────────────────────────────────────────

def _exec(word, st):
    rec, f = decode(word)
    op = rec['op']
    mn = rec['mnemonic']
    ha = rec.get('ha')

    # unimp / swym (spec §6)
    if op == 0x10 and ha == 0x3F:
        raise Fault('ILLI', 'unimp (spec §6.2)')      # spec §6.2: unimp → ILLI
    if op == 0x10 and ha == 0x00:
        st.pc_next = st.pc + 4                         # swym: NOP (spec §6.1)
        return

    check_legality(op, ha, f)
    st.pc_next = st.pc + 4                             # default sequential

    # ── RD arithmetic ────────────────────────────────────────────────────────
    if op == 0x19:                                    # addi (spec §3.6)
        st.rd_write(f['rdha'], (st.rd_read(f['rdhb']) + f['imms12']) & MASK64)
        return
    if op in (0x1A, 0x1B):                             # add / sub (spec §3.5)
        sa = _sext(st.rd_read(f['rdhc']), 64)
        sb = _sext(st.rd_read(f['rdhd']), 64)
        res = (sa + sb if op == 0x1A else sa - sb) & MASK128
        st.rd_write(f['rdha'], (res >> 64) & MASK64)   # high half
        st.rd_write(f['rdhb'], res & MASK64)           # low half
        return
    if op in (0x1C, 0x1D):                             # muls / mulu (spec §3.7)
        if op == 0x1C:
            prod = (_sext(st.rd_read(f['rdhc']), 64) *
                    _sext(st.rd_read(f['rdhd']), 64)) & MASK128
        else:
            prod = (st.rd_read(f['rdhc']) * st.rd_read(f['rdhd'])) & MASK128
        st.rd_write(f['rdha'], (prod >> 64) & MASK64)
        st.rd_write(f['rdhb'], prod & MASK64)
        return
    if op in (0x1E, 0x1F):                             # divs / divu (spec §3.7)
        c = st.rd_read(f['rdhc'])
        d = st.rd_read(f['rdhd'])
        if op == 0x1E:
            sc, sd = _sext(c, 64), _sext(d, 64)
            if sd == 0:
                raise Fault('ILLI', 'signed div by zero (spec §3.7)')
            if sc == INT64_MIN and sd == -1:
                raise Fault('ILLI', 'INT64_MIN / -1 overflow (spec §3.7)')
            # trunc toward zero (C99); remainder sign = dividend sign (spec §3.7)
            q = abs(sc) // abs(sd)
            if (sc < 0) != (sd < 0):
                q = -q
            r = sc - q * sd
            st.rd_write(f['rdha'], r & MASK64)         # remainder
            st.rd_write(f['rdhb'], q & MASK64)         # quotient
        else:
            if d == 0:
                raise Fault('ILLI', 'unsigned div by zero (spec §3.7)')
            st.rd_write(f['rdha'], (c % d) & MASK64)
            st.rd_write(f['rdhb'], (c // d) & MASK64)
        return

    # ── loads ────────────────────────────────────────────────────────────────
    if op in _LD_INFO and rec['format'] == 'rrii':    # single load (§3.1/§4.1)
        width, signed = _LD_INFO[op]
        ea = (st.rb_read(f['rbhb']) + f['imms12']) & MASK48
        _check_align(ea, width)
        val = _extend(st.load_mem(ea, width), width, signed)
        if op in _RB_LOADS:
            st.rb_write(f['rbha'], val)                # full 64-bit (§4.1)
        else:
            st.rd_write(f['rdha'], val)
        return
    if op in _LD_INFO and rec['format'] == 'rrri':    # multi load (§3.3/§4.2)
        width, signed = _LD_INFO[op]
        base = st.rb_read(f['rbhb']) & MASK48
        idx = st.rd_read(f['rdhc']) & MASK48           # snapshot (§2.7)
        count = f['immu6']
        eas = [(base + idx + i * width) & MASK48 for i in range(count)]
        for ea in eas:                                 # precise: pre-check all
            _check_align(ea, width)
        first = f['rbha'] if op in _RB_MLOADS else f['rdha']
        for i, ea in enumerate(eas):
            val = _extend(st.load_mem(ea, width), width, signed)
            if op in _RB_MLOADS:
                st.rb_write(first + i, val)
            else:
                st.rd_write(first + i, val)
        return

    # ── stores ───────────────────────────────────────────────────────────────
    if op in _ST_INFO and rec['format'] == 'rrii':    # single store (§3.2/§4.1)
        width = _ST_INFO[op]
        ea = (st.rb_read(f['rbhb']) + f['imms12']) & MASK48
        _check_align(ea, width)
        src = st.rb_read(f['rbha']) if op in _RB_STORES else st.rd_read(f['rdha'])
        st.store_mem(ea, width, src & ((1 << (width * 8)) - 1))
        return
    if op in _ST_INFO and rec['format'] == 'rrri':    # multi store (§3.4/§4.2)
        width = _ST_INFO[op]
        base = st.rb_read(f['rbhb']) & MASK48
        idx = st.rd_read(f['rdhc']) & MASK48
        count = f['immu6']
        first = f['rbha'] if op in _RB_MSTORES else f['rdha']
        eas = [(base + idx + i * width) & MASK48 for i in range(count)]
        for ea in eas:
            _check_align(ea, width)
        for i, ea in enumerate(eas):
            src = (st.rb_read(first + i) if op in _RB_MSTORES
                   else st.rd_read(first + i))
            st.store_mem(ea, width, src & ((1 << (width * 8)) - 1))
        return

    # ── control flow (spec §5) ────────────────────────────────────────────────
    rb0 = st.rb_read(0) & MASK48
    if op in (0x28, 0x29, 0x2A, 0x2B, 0x2C, 0x2D):    # single-reg branch (§5.1)
        if _cond(mn, st.rd_read(f['rdha'])):
            st.pc_next = (rb0 + (f['imms18'] << 2)) & MASK48
        return
    if op in (0x2E, 0x2F):                            # breq / brne (§5.2)
        eq = st.rd_read(f['rdha']) == st.rd_read(f['rdhb'])
        taken = eq if op == 0x2E else not eq
        if taken:
            st.pc_next = (rb0 + (f['imms12'] << 2)) & MASK48
        return
    if op == 0x64:                                    # jump imms24 (§5.3)
        st.pc_next = (rb0 + (f['imms24'] << 2)) & MASK48
        return
    if op == 0x65:                                    # jump rbha,rdhb,imm (§5.3)
        st.pc_next = ((st.rb_read(f['rbha']) & MASK48) +
                      (st.rd_read(f['rdhb']) & MASK48) +
                      (f['imms12'] << 2)) & MASK48
        return
    if op == 0x6C:                                    # call imms24 (§5.4)
        _ras_push(st, rb0)
        st.pc_next = (rb0 + (f['imms24'] << 2)) & MASK48
        return
    if op == 0x6D:                                    # call rbha,rdhb,imm (§5.4)
        _ras_push(st, rb0)
        st.pc_next = ((st.rb_read(f['rbha']) & MASK48) +
                      (st.rd_read(f['rdhb']) & MASK48) +
                      (f['imms12'] << 2)) & MASK48
        return
    if op == 0x6E:                                    # ret (§5.5)
        ret_addr = _ras_pop(st)                        # may raise RASUF
        st.pc_next = ret_addr & MASK48
        st.rd_write(f['rdha'], f['imms18'] & MASK64)   # rdha=rd0 discards (legal)
        return

    raise Unsupported(mn, rec['format'])


def run(word, input_state=None, pc=DEFAULT_PC, state=None):
    """Execute a single instruction word.

    Returns (State, fault_kind_or_None). On fault the returned state is the
    pre-execution snapshot (precise: no architectural side effect, spec §2.7).
    Raises Unsupported for out-of-phase instructions."""
    if state is None:
        state = build_state(input_state, pc)
    # IALIGN precheck (spec §2.1)
    if state.pc & 0x3:
        return state, 'IALIGN'
    import copy
    work = copy.deepcopy(state)
    try:
        _exec(word, work)
    except Fault as ex:
        return state, ex.kind          # discard partial work: precise (§2.7)
    return work, None


if __name__ == '__main__':
    import sys
    w = int(sys.argv[1], 16)
    rec, f = decode(w)
    print(f"0x{w:08X} -> {rec['mnemonic']}({rec['format']}) fields={f}")
