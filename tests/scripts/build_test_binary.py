"""Build raw test binary from YAML test case — no llvm-mc dependency."""

import struct
import yaml

OP_SETZW_RD = 0x16
OP_ORW_RD = 0x14
OP_SETZW_RB = 0x4E
OP_ORW_RB = 0x4C
OP_STO_RR = 0x3B
OP_HALT = 0x00


def write_rwii(out, op, reg, ww, imm16):
    imm_hi = (imm16 >> 12) & 0xF
    imm_mid = (imm16 >> 6) & 0x3F
    imm_lo = imm16 & 0x3F
    w = (op << 24) | (reg << 18) | ((ww & 3) << 16) | (imm_hi << 12) | (imm_mid << 6) | imm_lo
    out.extend(struct.pack('>I', w))


def write_rrii(out, op, ha, hb, imms12):
    imm12 = imms12 & 0xFFF
    imm_mid = (imm12 >> 6) & 0x3F
    imm_lo = imm12 & 0x3F
    w = (op << 24) | (ha << 18) | (hb << 12) | (imm_mid << 6) | imm_lo
    out.extend(struct.pack('>I', w))


def load_reg(out, bank, reg_num, value):
    if bank == 'rd':
        n_wydes = 4
        op_setzw = OP_SETZW_RD
        op_orw = OP_ORW_RD
    else:
        n_wydes = 3
        op_setzw = OP_SETZW_RB
        op_orw = OP_ORW_RB
    for pos in range(n_wydes - 1, -1, -1):
        chunk = (value >> (pos * 16)) & 0xFFFF
        if pos == n_wydes - 1 or (value >> ((pos + 1) * 16)) == 0:
            write_rwii(out, op_setzw, reg_num, pos, chunk)
        else:
            write_rwii(out, op_orw, reg_num, pos, chunk)


def emit_memory_setup(out, memory_list, tmp_rd, tmp_rb):
    if not memory_list:
        return
    for entry in memory_list:
        addr = int(entry['address'], 16)
        value_str = entry['value']
        width = entry.get('width', 8)
        val = int(value_str, 16) if isinstance(value_str, str) else value_str
        load_reg(out, 'rd', tmp_rd, val)
        load_reg(out, 'rb', tmp_rb, addr)
        if width == 1:
            write_rrii(out, 0x38, tmp_rd, tmp_rb, 0)
        elif width == 2:
            write_rrii(out, 0x39, tmp_rd, tmp_rb, 0)
        elif width == 4:
            write_rrii(out, 0x3A, tmp_rd, tmp_rb, 0)
        else:
            write_rrii(out, OP_STO_RR, tmp_rd, tmp_rb, 0)


TEMP_RB = 63
TEMP_RD = 63
EXIT_RD = 62
OP_HALT = 0x00


def emit_register_loader(out, case):
    rd = case.get('input_state', {}).get('rd', {})
    for name, value_str in sorted(rd.items()):
        reg_num = int(name.replace('rd', ''))
        val = int(value_str, 16)
        load_reg(out, 'rd', reg_num, val)
    rb = case.get('input_state', {}).get('rb', {})
    for name, value_str in sorted(rb.items()):
        reg_num = int(name.replace('rb', ''))
        val = int(value_str, 16)
        load_reg(out, 'rb', reg_num, val)


def emit_exit(out, code=0):
    # Load exit code into register, then halt rd
    load_reg(out, 'rd', EXIT_RD, code)
    w = (OP_HALT << 24) | (EXIT_RD << 18)
    out.extend(struct.pack('>I', w))


BINARY_BASE = 0x80000000
SWYM_ENCODING = 0x10000000
UNIMP_ENCODING = 0x10FC0000


def emit_state_compare(out, expected_state):
    """Generate inline comparison code via accumulation and self-modifying guard.

    After the test instruction, for each expected register:
      XOR expected ^ actual → 0 if match, ORR into accumulator rd29.
    Then patch a guard instruction at a forward address:
      If all match (rd29==0): patch with swym (NOP) → fall through to halt → PASS
      If mismatch (rd29!=0):  patch with unimp → ILLI (exit 0x82) → FAIL
    """
    rd = expected_state.get('rd', {}) if expected_state else {}
    rb = expected_state.get('rb', {}) if expected_state else {}

    memory = expected_state.get('memory', []) if expected_state else []
    if not rd and not rb and not memory:
        emit_exit(out, 0)
        return

    # Initialize mismatch accumulator
    load_reg(out, 'rd', 29, 0)

    # Emit comparison: xor each actual reg with expected, OR into rd29
    for name, value_str in sorted(rd.items()):
        reg_num = int(name.replace('rd', ''))
        val = int(value_str, 16)
        load_reg(out, 'rd', 31, val)
        # xor rd31, rd31, reg
        w = 0x10280000 | (31 << 12) | (31 << 6) | reg_num
        out.extend(struct.pack('>I', w))
        # or rd29, rd29, rd31
        w = 0x10240000 | (29 << 12) | (29 << 6) | 31
        out.extend(struct.pack('>I', w))

    for name, value_str in sorted(rb.items()):
        reg_num = int(name.replace('rb', ''))
        val = int(value_str, 16)
        # rb2rd rd30, rb_reg  (copy actual rb value to rd30)
        w = 0x10A80000 | (30 << 12) | (reg_num << 6) | 1
        out.extend(struct.pack('>I', w))
        load_reg(out, 'rd', 31, val)
        w = 0x10280000 | (31 << 12) | (31 << 6) | 30
        out.extend(struct.pack('>I', w))
        w = 0x10240000 | (29 << 12) | (29 << 6) | 31
        out.extend(struct.pack('>I', w))

    # Memory comparison
    memory = expected_state.get('memory', []) if expected_state else []
    for entry in memory:
        addr = int(entry['address'], 16)
        expected_val = int(entry['value'], 16)
        width = entry.get('width', 8)

        # Load address into rb30
        load_reg(out, 'rb', 30, addr)

        # Load memory value into rd30 using appropriate unsigned load
        if width == 1:
            # ldbu rd30, rb30, 0 → op=0x40, ha=30, hb=30, hc:hd=0
            word = (0x40 << 24) | (30 << 18) | (30 << 12)
            out.extend(struct.pack('>I', word))
        elif width == 2:
            # ldwu rd30, rb30, 0 → op=0x41
            word = (0x41 << 24) | (30 << 18) | (30 << 12)
            out.extend(struct.pack('>I', word))
        elif width == 4:
            # ldtu rd30, rb30, 0 → op=0x42
            word = (0x42 << 24) | (30 << 18) | (30 << 12)
            out.extend(struct.pack('>I', word))
        else:
            # ldo rd30, rb30, 0 → op=0x33
            word = (0x33 << 24) | (30 << 18) | (30 << 12)
            out.extend(struct.pack('>I', word))

        # Load expected value into rd31
        load_reg(out, 'rd', 31, expected_val)

        # XOR: rd31 = rd31 ^ rd30
        word = (0x10 << 24) | (0x0A << 18) | (31 << 12) | (31 << 6) | 30
        out.extend(struct.pack('>I', word))

        # OR: rd29 = rd29 | rd31
        word = (0x10 << 24) | (0x09 << 18) | (29 << 12) | (29 << 6) | 31
        out.extend(struct.pack('>I', word))

    # --- Self-modifying guard patching ---
    # Count instructions emitted so far (before patching) to locate guard
    n_before = len(out) // 4
    n_patch = 4 + 4 + 1 + 3 + 1 + 3 + 1  # rd1+rd2+csz+rb1+sto+rb2+sto2
    guard_offset = (n_before + n_patch) * 4
    guard_addr = BINARY_BASE + guard_offset

    load_reg(out, 'rd', 1, UNIMP_ENCODING)   # rd1 = unimp (FAIL)
    load_reg(out, 'rd', 2, SWYM_ENCODING)    # rd2 = swym (PASS)
    # csz rd1, rd29, rd2, rd1  →  rd1 = (rd29 == 0) ? rd2 : rd1
    # QEMU maps: ha=cond, hb=dest, hc=true_val, hd=false_val
    w = (0x22 << 24) | (29 << 18) | (1 << 12) | (2 << 6) | 1
    out.extend(struct.pack('>I', w))
    load_reg(out, 'rb', 1, guard_addr)
    # Force TB exit by storing to a different page BEFORE patching guard
    load_reg(out, 'rb', 2, 0x80001000)         # rb2 = scratch page
    write_rrii(out, 0x3B, 29, 2, 0)            # sto rd29, rb2, 0  → force TB exit
    write_rrii(out, 0x3A, 1, 1, 0)             # stt rd1, rb1, 0  → patch guard (32-bit BE: preserves 4-byte instr encoding)

    # Guard instruction (initially swym, patched to unimp on mismatch)
    out.extend(struct.pack('>I', SWYM_ENCODING))

    # PASS path — reached after swym NOP if all comparisons matched
    emit_exit(out, 0)


def build_branch_test_binary(case):
    """Build binary for branch/jump semantic tests using poison pattern.

    taken pattern:
        [setup] [branch/jump +1] [unimp] [exit(0)]
        Branch/jump taken → skips unimp → exit=0 → PASS
        NOT taken → hits unimp → ILLI → FAIL

    not_taken pattern:
        [setup] [branch +1] [exit(0)] [unimp]
        Branch NOT taken → fall through → exit=0 → PASS
        Taken → skips exit → hits unimp → ILLI → FAIL
    """
    buf = bytearray()
    mnemonic = case['mnemonic']
    fmt = case['format']
    behavior = case['branch_behavior']
    word = int(case['encoding']['word'], 16)

    if mnemonic == 'jump' and fmt == 'rrii':
        ha = (word >> 18) & 0x3F
        hb = (word >> 12) & 0x3F
        load_reg(buf, 'rb', ha, BINARY_BASE)
        pos_after_rb = len(buf)
        exit_offset_bytes = pos_after_rb + 16 + 4 + 4
        load_reg(buf, 'rd', hb, exit_offset_bytes)
    elif mnemonic == 'jump' and fmt == 'iiii':
        pass
    else:
        emit_register_loader(buf, case)

    buf.extend(struct.pack('>I', word))

    if behavior == 'taken':
        buf.extend(struct.pack('>I', UNIMP_ENCODING))
        emit_exit(buf, 0)
    else:
        emit_exit(buf, 0)
        buf.extend(struct.pack('>I', UNIMP_ENCODING))

    return bytes(buf)


def build_test_binary(case):
    if 'branch_behavior' in case:
        return build_branch_test_binary(case)

    buf = bytearray()

    emit_register_loader(buf, case)

    mem_list = case.get('input_state', {}).get('memory', [])
    emit_memory_setup(buf, mem_list, TEMP_RD, TEMP_RB)

    word = int(case['encoding']['word'], 16)
    buf.extend(struct.pack('>I', word))

    expected_state = case.get('expected_state')
    if expected_state:
        emit_state_compare(buf, expected_state)
    else:
        emit_exit(buf)

    return bytes(buf)


def test_encode_decode():
    """Verify round-trip encoding of key instruction patterns."""
    pass
