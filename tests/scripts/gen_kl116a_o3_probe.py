"""KL-116a Oracle O3 probe: real `trap cfx_smon` entry -> guest handler ->
`escape cfx_smon,1` round trip, gated behind the (default-off) QEMU CPU
property `cfx-smon-real`.

Reuses the exact HBI §3 hypv->supv handoff stub from gen_kl110a_o1_probe.py
verbatim (O1, already verified) to reach supv mode, then adds the O3-specific
sequence KL-115a report §4.1 designed:

    supv_entry:
        cfx2rc  cfx_smon_supv_excp_vector, rd2   ; (cg=2, rc=10) -- new
                                                   ; write support (KL-116a)
        setrd   rd16, SYSNO_CONST                 ; ABI param (rd16-19, §3)
        setrd   rd17, ARG0_CONST
        trap    cfx_smon, 0                       ; -> real entry state
                                                   ; machine (profile on) or
                                                   ; the pre-existing host/SE
                                                   ; syscall shortcut
                                                   ; (profile off)
    after_trap:                                   ; = cause_ip + 4
        setrd   rd18, SUCCESS_TAG                  ; proves *precise* landing
        ldo     rd19, rb21, 0                      ; handler-written sysno
        ldo     rd20, rb21, 8                      ; handler-written arg0
        ; mismatch_acc = (rd18^TAG) | (rd19^SYSNO) | (rd20^ARG0)
        ; exit 43 if mismatch_acc==0, else exit 0x99

    ; --- poison gap (unimp) ---

    smon_handler:                                  ; only reached when the
                                                     ; profile is ON and the
                                                     ; real entry state
                                                     ; machine jumped here
        sto     rd16, rb21, 0                       ; store sysno for the
        sto     rd17, rb21, 8                       ; tail to verify
        setrd   rd31, 0
        escape  cfx_smon, 1                         ; -> after_trap

This single binary is deliberately also the A/B negative control: run WITHOUT
`-global dadao-cpu.cfx-smon-real=on`, `trap cfx_smon,0` falls into the
pre-existing host/SE syscall shortcut instead (sysno=SYSNO_CONST matches no
case, default -ENOSYS, env->rd[31] set, execution resumes at the same
pc_next+4 address as the real-entry path -- trans_trap stores that
unconditionally, regardless of profile). `smon_handler` is *never reached* in
that run (nothing routes execution there), so the RAM cells at
HANDLER_MARKER_ADDR are never written and stay 0 -- rd19/rd20 read back 0,
mismatch_acc != 0, and the run exits 0x99 instead of 43. Landing (rd18) still
matches in both runs (same pc_next+4 value either way), isolating the
assertion specifically to "did the guest handler really run with the real
parameters", not merely "did execution resume after trap".

Usage: python3 gen_kl116a_o3_probe.py [output.bin]
"""

import struct
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from build_test_binary import load_reg, write_rrii, UNIMP_ENCODING
import gen_kl110a_o1_probe as o1

ROM_BASE = 0x00100000
SUPV_ENTRY_OFFSET = 0x200
SMON_HANDLER_OFFSET = 0x400

CFX_SMON = 2
CFX_POWER = 63

OP_CFX2RC = 0x73
OP_TRAP = 0x76
OP_ESCAPE = 0x77
OP_HALT = 0x00
OP_MISC = 0x10
MISC_ORR = 0x09
MISC_XOR = 0x0A
OP_LDO = 0x33
OP_STO = 0x3B
OP_CSZ = 0x22

SYSNO_CONST = 0x1234
ARG0_CONST = 0x5678
SUCCESS_TAG = 0xABCD1234ABCD5678
HANDLER_MARKER_ADDR = 0x80002000

EXIT_SUCCESS = 43
EXIT_MISMATCH = 0x99


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


def write_orrr(out, misc_ha, hb, hc, hd):
    w = (OP_MISC << 24) | ((misc_ha & 0x3F) << 18) | ((hb & 0x3F) << 12) | \
        ((hc & 0x3F) << 6) | (hd & 0x3F)
    out.extend(struct.pack('>I', w))


def gen():
    out = bytearray()
    supv_entry = ROM_BASE + SUPV_ENTRY_OFFSET
    smon_handler = ROM_BASE + SMON_HANDLER_OFFSET

    # --- HBI §3 handoff stub (verbatim, KL-110a) -> escape cfx_power,0 ---
    load_reg(out, 'rd', 2, 0)
    for _name, cfxcode in o1.CFX_DELEG_TARGETS:
        write_crrr(out, OP_CFX2RC, cfxcode, 3, 12, 2)
    load_reg(out, 'rd', 2, 2)
    write_crrr(out, OP_CFX2RC, CFX_POWER, 5, 0, 2)
    load_reg(out, 'rd', 2, 0xFFFFFFFFFFFFFFFF)
    write_crrr(out, OP_CFX2RC, CFX_POWER, 5, 1, 2)
    load_reg(out, 'rd', 2, supv_entry)
    write_crrr(out, OP_CFX2RC, CFX_POWER, 5, 3, 2)
    write_ciii(out, OP_ESCAPE, CFX_POWER, 0)

    if len(out) > SUPV_ENTRY_OFFSET:
        raise ValueError('handoff stub overflowed SUPV_ENTRY_OFFSET')
    while len(out) < SUPV_ENTRY_OFFSET:
        out.extend(struct.pack('>I', UNIMP_ENCODING))
    assert len(out) == SUPV_ENTRY_OFFSET

    # --- supv_entry: KL-116a O3 setup + trap ---
    # cfx2rc cfx_smon_supv_excp_vector, rd2  (SEE §3 cg=2, rc=10)
    load_reg(out, 'rd', 2, smon_handler)
    write_crrr(out, OP_CFX2RC, CFX_SMON, 2, 10, 2)
    # ABI params (rd16/rd17), same registers the host/SE shortcut already
    # uses -- shared convention, not a new one (KL-115a report §3).
    load_reg(out, 'rd', 16, SYSNO_CONST)
    load_reg(out, 'rd', 17, ARG0_CONST)
    # trap cfx_smon, 0
    write_ciii(out, OP_TRAP, CFX_SMON, 0)

    # --- after_trap: return landing point (cause_ip + 4) ---
    # rd18 = SUCCESS_TAG -- only set if execution actually resumes exactly
    # here (not skipped/misplaced by a wrong cause_ip/escape computation).
    load_reg(out, 'rd', 18, SUCCESS_TAG)
    # rb21 = HANDLER_MARKER_ADDR (same constant smon_handler uses below)
    load_reg(out, 'rb', 21, HANDLER_MARKER_ADDR)
    write_rrii(out, OP_LDO, 19, 21, 0)   # ldo rd19, rb21, 0 -> handler sysno
    write_rrii(out, OP_LDO, 20, 21, 8)   # ldo rd20, rb21, 8 -> handler arg0

    # mismatch_acc (rd23) = (rd18^TAG) | (rd19^SYSNO) | (rd20^ARG0)
    load_reg(out, 'rd', 23, 0)
    load_reg(out, 'rd', 24, SUCCESS_TAG)
    write_orrr(out, MISC_XOR, 25, 18, 24)   # rd25 = rd18 ^ rd24
    write_orrr(out, MISC_ORR, 23, 23, 25)   # rd23 |= rd25

    load_reg(out, 'rd', 24, SYSNO_CONST)
    write_orrr(out, MISC_XOR, 25, 19, 24)
    write_orrr(out, MISC_ORR, 23, 23, 25)

    load_reg(out, 'rd', 24, ARG0_CONST)
    write_orrr(out, MISC_XOR, 25, 20, 24)
    write_orrr(out, MISC_ORR, 23, 23, 25)

    # exit code = (mismatch_acc == 0) ? EXIT_SUCCESS : EXIT_MISMATCH
    load_reg(out, 'rd', 26, EXIT_SUCCESS)
    load_reg(out, 'rd', 27, EXIT_MISMATCH)
    w = (OP_CSZ << 24) | (23 << 18) | (28 << 12) | (26 << 6) | 27
    out.extend(struct.pack('>I', w))   # csz rd28, rd23, rd26, rd27
    w = (OP_HALT << 24) | (28 << 18)
    out.extend(struct.pack('>I', w))   # halt rd28

    # --- poison gap: only reachable by a wrong (too-far) PC computation ---
    if len(out) > SMON_HANDLER_OFFSET:
        raise ValueError('after_trap block overflowed SMON_HANDLER_OFFSET')
    while len(out) < SMON_HANDLER_OFFSET:
        out.extend(struct.pack('>I', UNIMP_ENCODING))
    assert len(out) == SMON_HANDLER_OFFSET

    # --- smon_handler: guest-side handler at the excp_vector ---
    load_reg(out, 'rb', 21, HANDLER_MARKER_ADDR)
    write_rrii(out, OP_STO, 16, 21, 0)   # sto rd16, rb21, 0
    write_rrii(out, OP_STO, 17, 21, 8)   # sto rd17, rb21, 8
    load_reg(out, 'rd', 31, 0)
    write_ciii(out, OP_ESCAPE, CFX_SMON, 1)   # escape cfx_smon, 1

    return bytes(out)


if __name__ == '__main__':
    data = gen()
    out_path = sys.argv[1] if len(sys.argv) > 1 else 'kl116a-o3-probe.bin'
    with open(out_path, 'wb') as f:
        f.write(data)
    print(f'Wrote {len(data)} bytes to {out_path}')
    print(f'supv_entry=0x{ROM_BASE + SUPV_ENTRY_OFFSET:x} '
          f'smon_handler=0x{ROM_BASE + SMON_HANDLER_OFFSET:x} '
          f'EXIT_SUCCESS={EXIT_SUCCESS} EXIT_MISMATCH=0x{EXIT_MISMATCH:x}')
