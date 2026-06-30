# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=obj %s -o %t
# RUN: llvm-objdump -d --triple=dadao-unknown-elf %t | FileCheck %s --check-prefix=OBJ
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=asm %s | FileCheck %s --check-prefix=ASM

# OBJ: 10 20 92 8b and rd9, rd10, rd11
# OBJ: 10 24 c3 4e orr rd12, rd13, rd14
# OBJ: 10 28 f4 11 xor rd15, rd16, rd17
# OBJ: 10 2d 24 d4 xnor rd18, rd19, rd20
# ASM: and rd9, rd10, rd11
# ASM: orr rd12, rd13, rd14
# ASM: xor rd15, rd16, rd17
# ASM: xnor rd18, rd19, rd20

	and rd9, rd10, rd11
	orr rd12, rd13, rd14
	xor rd15, rd16, rd17
	xnor rd18, rd19, rd20
