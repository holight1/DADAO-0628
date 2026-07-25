# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=obj %s -o %t
# RUN: llvm-objdump -d --triple=dadao-unknown-elf %t | FileCheck %s --check-prefix=OBJ
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=asm %s | FileCheck %s --check-prefix=ASM

# KL-114a: hypv->supv cfx register-transfer/exit instructions
# (contracts/isa/spec.md §8.1/§8.2, op=0x73 crrr / op=0x77 ciii).
# Only the bare-numeral cfxcode/cg/rc operand form is covered — the
# `cfx_<cfxname>_regname` symbolic shorthand (wiki SimRISC-04-系统类指令
# L91-97) is out of scope for this task.
#
# `cfx2rc 63, 8, 1, rd2` is the numeric form of wiki's own worked example
# ("等价的标准写法: cfx2rc cfx_power, 8, 1, rd2", cfx_power=cfxcode 63).
# `escape 63, 0` is the exact final instruction of the KL-110a HBI §3
# handoff probe (tests/scripts/gen_kl110a_o1_probe.py OP_ESCAPE/CFX_POWER,
# "escape cfx_power, 0"). Encoding cross-checked bit-for-bit against that
# script's write_crrr()/write_ciii() helpers
# (op<<24|(ha&0x3F)<<18|(hb&0x3F)<<12|(hc&0x3F)<<6|(hd&0x3F), with ciii's
# hb/hc/hd built from imm18's 18 bits) and tools/opcodes.yaml's
# cfx2rc/escape field layout.

# OBJ: 73 fc 80 42{{.*}}cfx2rc 63, 8, 1, rd2
# OBJ: 73 00 00 00{{.*}}cfx2rc 0, 0, 0, rd0
# OBJ: 77 fc 00 00{{.*}}escape 63, 0
# OBJ: 77 17 ff fc{{.*}}escape 5, -4
# ASM: cfx2rc 63, 8, 1, rd2
# ASM: cfx2rc 0, 0, 0, rd0
# ASM: escape 63, 0
# ASM: escape 5, -4

	cfx2rc 63, 8, 1, rd2
	cfx2rc 0, 0, 0, rd0
	escape 63, 0
	escape 5, -4
