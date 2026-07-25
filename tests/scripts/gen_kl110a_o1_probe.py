"""KL-110a Oracle O1 probe: HBI §3 hypv->supv handoff success path.

Builds a raw ROM image (loaded via `-bios` at the reset vector 0x00100000)
that executes the exact HBI §3 minimal handoff stub:

    setrd rd2, 0
    cfx2rc  cfx_umon_hypv_cg_reg_deleg, rd2
    cfx2rc  cfx_jmon_hypv_cg_reg_deleg, rd2
    cfx2rc  cfx_smon_hypv_cg_reg_deleg, rd2
    cfx2rc  cfx_ptw_hypv_cg_reg_deleg, rd2
    cfx2rc  cfx_tlb_hypv_cg_reg_deleg, rd2
    cfx2rc  cfx_cache_hypv_cg_reg_deleg, rd2
    cfx2rc  cfx_hart_hypv_cg_reg_deleg, rd2
    cfx2rc  cfx_llc_hypv_cg_reg_deleg, rd2
    cfx2rc  cfx_pmem_hypv_cg_reg_deleg, rd2
    cfx2rc  cfx_timer_hypv_cg_reg_deleg, rd2
    cfx2rc  cfx_uart_hypv_cg_reg_deleg, rd2
    cfx2rc  cfx_power_hypv_cg_reg_deleg, rd2
    setrd rd2, 2
    cfx2rc  cfx_power_excp_prev_run_mode, rd2
    setrd rd2, -1
    cfx2rc  cfx_power_excp_prev_cfx_mask, rd2
    setrd rd2, supv_entry
    cfx2rc  cfx_power_excp_cause_ip, rd2
    ; rb16 = fdt_addr = 0 -- already the reset value, no instruction needed
    escape cfx_power, 0

then verifies escape actually landed at `supv_entry` rather than falling
through by accident: the gap between the end of the stub and `supv_entry`
is poisoned with `unimp` (UNDI, exit 0x83). `supv_entry` writes a unique
marker to a RAM scratch address and halts with a distinctive exit code
(only reachable if escape computed the correct mode/PC restoration).

Usage: python3 gen_kl110a_o1_probe.py [output.bin]
"""

import struct
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from build_test_binary import load_reg, write_rrii, UNIMP_ENCODING

ROM_BASE = 0x00100000
SUPV_ENTRY_OFFSET = 0x200
MARKER_ADDR = 0x80001000
MARKER_VALUE = 0xCAFEF00DC0FFEE42
EXIT_CODE = 42

# SEE §1 cfx table: the 12 named in HBI §3 (excludes hmon=3, per wiki text
# "允许 supv 访问所有 cg（cg3 固定禁止，bit3 硬件忽略写入）" -- hmon itself
# is never delegation-cleared by the stub).
CFX_DELEG_TARGETS = [
    ('umon', 0), ('jmon', 1), ('smon', 2), ('ptw', 4), ('tlb', 5),
    ('cache', 6), ('hart', 15), ('llc', 16), ('pmem', 17), ('timer', 18),
    ('uart', 62), ('power', 63),
]
CFX_POWER = 63

OP_CFX2RC = 0x73
OP_ESCAPE = 0x77
OP_HALT = 0x00
OP_STO = 0x3B


def write_crrr(out, op, ha, hb, hc, hd):
    w = (op << 24) | ((ha & 0x3F) << 18) | ((hb & 0x3F) << 12) | \
        ((hc & 0x3F) << 6) | (hd & 0x3F)
    out.extend(struct.pack('>I', w))


def write_ciii(out, op, ha, imm18):
    imm18 &= 0x3FFFF
    hb = (imm18 >> 12) & 0x3F
    hc = (imm18 >> 6) & 0x3F
    hd = imm18 & 0x3F
    w = (op << 24) | ((ha & 0x3F) << 18) | (hb << 12) | (hc << 6) | hd
    out.extend(struct.pack('>I', w))


def gen():
    out = bytearray()
    supv_entry = ROM_BASE + SUPV_ENTRY_OFFSET

    # --- HBI §3 handoff stub ---
    load_reg(out, 'rd', 2, 0)
    for _name, cfxcode in CFX_DELEG_TARGETS:
        # cfx2rc cfx_<name>_hypv_cg_reg_deleg, rd2  (HEE §1 cg=3, rc=12)
        write_crrr(out, OP_CFX2RC, cfxcode, 3, 12, 2)

    load_reg(out, 'rd', 2, 2)
    # cfx2rc cfx_power_excp_prev_run_mode, rd2  (SEE §3 cg=5, rc=0)
    write_crrr(out, OP_CFX2RC, CFX_POWER, 5, 0, 2)

    load_reg(out, 'rd', 2, 0xFFFFFFFFFFFFFFFF)
    # cfx2rc cfx_power_excp_prev_cfx_mask, rd2  (SEE §3 cg=5, rc=1)
    write_crrr(out, OP_CFX2RC, CFX_POWER, 5, 1, 2)

    load_reg(out, 'rd', 2, supv_entry)
    # cfx2rc cfx_power_excp_cause_ip, rd2  (SEE §3 cg=5, rc=3)
    write_crrr(out, OP_CFX2RC, CFX_POWER, 5, 3, 2)

    # escape cfx_power, 0
    write_ciii(out, OP_ESCAPE, CFX_POWER, 0)

    # --- poison gap ---
    if len(out) > SUPV_ENTRY_OFFSET:
        raise ValueError('handoff stub overflowed SUPV_ENTRY_OFFSET')
    while len(out) < SUPV_ENTRY_OFFSET:
        out.extend(struct.pack('>I', UNIMP_ENCODING))
    assert len(out) == SUPV_ENTRY_OFFSET

    # --- supv_entry: write marker to RAM, read it back, and only exit
    # with the distinctive success code if the readback matches -- this is
    # a self-contained assertion, not just "the store didn't fault". ---
    load_reg(out, 'rd', 3, MARKER_VALUE)
    load_reg(out, 'rb', 3, MARKER_ADDR)
    write_rrii(out, OP_STO, 3, 3, 0)          # sto rd3, rb3, 0
    write_rrii(out, 0x33, 5, 3, 0)            # ldo rd5, rb3, 0 (readback)
    # xor rd6, rd5, rd3  (MISC-Norm orrr: op=0x10, ha=0x0A, hb=dest,
    # hc=src1, hd=src2)
    w = (0x10 << 24) | (0x0A << 18) | (6 << 12) | (5 << 6) | 3
    out.extend(struct.pack('>I', w))
    load_reg(out, 'rd', 7, EXIT_CODE)         # success code
    load_reg(out, 'rd', 8, 0x99)              # mismatch code (readback bug)
    # csz rd4, rd6, rd7, rd8  ->  rd4 = (rd6 == 0) ? rd7 : rd8
    w = (0x22 << 24) | (6 << 18) | (4 << 12) | (7 << 6) | 8
    out.extend(struct.pack('>I', w))
    w = (OP_HALT << 24) | (4 << 18)
    out.extend(struct.pack('>I', w))          # halt rd4

    return bytes(out)


if __name__ == '__main__':
    data = gen()
    out_path = sys.argv[1] if len(sys.argv) > 1 else 'kl110a-o1-handoff.bin'
    with open(out_path, 'wb') as f:
        f.write(data)
    supv_entry = ROM_BASE + SUPV_ENTRY_OFFSET
    print(f'Wrote {len(data)} bytes to {out_path}')
    print(f'supv_entry=0x{supv_entry:x} marker_addr=0x{MARKER_ADDR:x} '
          f'marker_value=0x{MARKER_VALUE:x} exit_code={EXIT_CODE}')
