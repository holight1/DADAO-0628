# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=obj %s -o %t
# RUN: llvm-objdump -d --triple=dadao-unknown-elf %t | FileCheck %s --check-prefix=OBJ
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=asm %s | FileCheck %s --check-prefix=ASM

# KL-114a: RegRAS whole-bank RA-register load/store (contracts/isa/spec.md
# §4.9, op=0x67/0x6F). Mnemonic is bare "ldmo"/"stmo", overloaded on the
# destination operand's register class exactly like the existing
# RD-bank (op=0x37/0x3F) and RB-bank (op=0x47/0x4F) forms below it in
# rrri.s/rb_ops.s — spec.md's "ldmo-ra"/"stmo-ra" table label is a
# documentation-only disambiguation (same convention as its "ldo-rb"/
# "ldmo-rb"/"stmo-rb" labels for the already-implemented bare "ldo"/
# "ldmo"/"stmo" RB-bank forms), not a distinct assembler token.
#
# Encoding cross-checked bit-for-bit against the project's
# scripts/check_legality_matrix.py `encode()` helper (the same
# op<<24|ha<<18|hb<<12|hc<<6|hd packing QEMU's target/dadao/insn.decode
# and gem5's src/arch/dadao/decoder.cc use) and against
# tools/opcodes.yaml's `ldmo-ra`/`stmo-ra` field layout (raha=[23:18]
# dst, rbhb=[17:12] src, rdhc=[11:6] src, immu6=[5:0]).

# OBJ: 67 04 20 c5{{.*}}ldmo ra1, rb2, rd3, 5
# OBJ: 6f 04 20 c5{{.*}}stmo ra1, rb2, rd3, 5
# OBJ: 67 ff ff ff{{.*}}ldmo ra63, rb63, rd63, 63
# OBJ: 6f 00 10 81{{.*}}stmo ra0, rb1, rd2, 1
# ASM: ldmo ra1, rb2, rd3, 5
# ASM: stmo ra1, rb2, rd3, 5
# ASM: ldmo ra63, rb63, rd63, 63
# ASM: stmo ra0, rb1, rd2, 1

	ldmo ra1, rb2, rd3, 5
	stmo ra1, rb2, rd3, 5
	ldmo ra63, rb63, rd63, 63
	stmo ra0, rb1, rd2, 1
