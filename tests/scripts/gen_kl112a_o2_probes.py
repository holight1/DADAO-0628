"""KL-112a Oracle O2 probes: hypv->supv handoff negative/masked paths.

Builds three raw ROM images (each loaded via `-bios` at the reset vector
0x00100000, same convention as gen_kl110a_o1_probe.py):

1. `o1-regression`  -- re-emits the exact KL-110a O1 handoff stub verbatim
   (imported from gen_kl110a_o1_probe), to confirm the O2 permission check
   this task adds does not regress the O1 success path (O1's self-escape has
   cfxcode == inner_cfx_code == power, so the new cross-cfx escape check
   should never fire for it).
2. `design1-negative` -- KL-111a report §4 design 1 (candidate B): at reset
   (hypv mode, inner_cfx_code=power), `escape cfx_smon, 0` -- cfxcode(2) !=
   inner_cfx_code(63), and cfx_power_hypv_escape_cfx_mask defaults to
   all-ones (never cleared) -- SEE §5 exception-exit step 0 should fire ILLI
   before any of steps 1-4 execute.
3. `design3-negative` (candidate C) -- `cfx2rc cfx_power, 8, 63, rd2`
   (cfx_power's cg=8 group only defines rc=0/1 -- rc=63 is genuinely
   undefined) followed by a poison `halt` with a distinctive sentinel exit
   code that must NOT be reached if the CFXREG check fires correctly.

Design 2 (candidate B2, cross-cfx `cfx2rc` permission check) was evaluated
and deliberately NOT implemented in QEMU -- enforcing it as a blanket check
breaks the O1 regression, since HBI §3's own boot stub performs cross-cfx
`cfx2rc` calls without ever clearing that mask (see helper_cfx2rc()'s
comment in target/dadao/helper.c and docs/wiki-deviations.md #11).
`gen_design2_negative()` below is kept only as a record of the probe that
would have been used had design 2 been implemented; it is not part of
`gen_all()`'s required set and is not expected to raise ILLI against the
current QEMU build.

Usage: python3 gen_kl112a_o2_probes.py <outdir>
Writes <outdir>/kl112a-{o1-regression,design1-negative,design3-negative}.bin
"""

import struct
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from build_test_binary import load_reg, write_rrii
import gen_kl110a_o1_probe as o1

ROM_BASE = 0x00100000

OP_CFX2RC = 0x73
OP_ESCAPE = 0x77
OP_HALT = 0x00

CFX_SMON = 2
CFX_POWER = 63

# Poison sentinel: reached only if a permission/CFXREG check that should
# fire does NOT fire (silent no-op regression). Distinct from every real
# fault exit code (0x81-0x86) and from the O1 success code (42).
POISON_EXIT_CODE = 0x77
POISON_RD = 9


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


def gen_design1_negative():
    """escape cfx_smon, 0 as the very first (and only meaningful)
    instruction at reset. No poison-fallthrough is used here: `escape`
    always computes a *new* target PC (it never falls through
    sequentially), so a poison instruction placed after it in program order
    would not be reached by a buggy fallthrough anyway. The differentiating
    evidence for this scenario is exit code 0x82 plus the -d int trace log
    showing no 'escape cfx=... mode X->Y' line (see task evidence)."""
    out = bytearray()
    write_ciii(out, OP_ESCAPE, CFX_SMON, 0)
    return bytes(out)


def gen_design2_negative():
    """cfx2rc cfx_smon, 0, 1, rd2 (cg=0/rc=1 = user_global_cfx_mask, a real
    but QEMU-unbacked register) then a poison halt. cfx2rc never changes
    PC, so a missed check falls through sequentially into the poison."""
    out = bytearray()
    load_reg(out, 'rd', 2, 0)
    write_crrr(out, OP_CFX2RC, CFX_SMON, 0, 1, 2)
    load_reg(out, 'rd', POISON_RD, POISON_EXIT_CODE)
    w = (OP_HALT << 24) | (POISON_RD << 18)
    out.extend(struct.pack('>I', w))
    return bytes(out)


def gen_design3_negative():
    """cfx2rc cfx_power, 8, 63, rd2 (cg=8 only defines rc=0/1) then the same
    poison-halt pattern."""
    out = bytearray()
    load_reg(out, 'rd', 2, 0)
    write_crrr(out, OP_CFX2RC, CFX_POWER, 8, 63, 2)
    load_reg(out, 'rd', POISON_RD, POISON_EXIT_CODE)
    w = (OP_HALT << 24) | (POISON_RD << 18)
    out.extend(struct.pack('>I', w))
    return bytes(out)


def gen_all(outdir):
    os.makedirs(outdir, exist_ok=True)
    probes = {
        'o1-regression': o1.gen(),
        'design1-negative': gen_design1_negative(),
        'design3-negative': gen_design3_negative(),
    }
    for name, data in probes.items():
        path = os.path.join(outdir, f'kl112a-{name}.bin')
        with open(path, 'wb') as f:
            f.write(data)
        print(f'Wrote {len(data)} bytes to {path}')
    return probes


if __name__ == '__main__':
    outdir = sys.argv[1] if len(sys.argv) > 1 else '.'
    gen_all(outdir)
    print(f'POISON_EXIT_CODE=0x{POISON_EXIT_CODE:02x} '
          f'(reached only if a check that should fire does not)')
