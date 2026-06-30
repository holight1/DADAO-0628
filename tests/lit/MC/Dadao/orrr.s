# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=obj %s -o %t
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=asm %s | FileCheck %s

# CHECK: and rd9, rd10, rd11
# CHECK: orr rd12, rd13, rd14
# CHECK: xor rd15, rd16, rd17
# CHECK: xnor rd18, rd19, rd20

	and rd9, rd10, rd11
	orr rd12, rd13, rd14
	xor rd15, rd16, rd17
	xnor rd18, rd19, rd20
