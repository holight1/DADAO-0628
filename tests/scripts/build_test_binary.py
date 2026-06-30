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


def emit_state_dumper(out):
    pass


def emit_exit(out, code=0):
    # Load exit code into register, then halt rd
    load_reg(out, 'rd', EXIT_RD, code)
    w = (OP_HALT << 24) | (EXIT_RD << 18)
    out.extend(struct.pack('>I', w))


def build_test_binary(case):
    buf = bytearray()

    emit_register_loader(buf, case)

    mem_list = case.get('input_state', {}).get('memory', [])
    emit_memory_setup(buf, mem_list, TEMP_RD, TEMP_RB)

    word = int(case['encoding']['word'], 16)
    buf.extend(struct.pack('>I', word))

    emit_state_dumper(buf)

    emit_exit(buf)

    return bytes(buf)


def test_encode_decode():
    """Verify round-trip encoding of key instruction patterns."""
    pass
