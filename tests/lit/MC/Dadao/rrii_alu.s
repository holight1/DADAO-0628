# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=obj %s -o %t
# RUN: llvm-objdump -d --triple=dadao-unknown-elf %t | FileCheck %s --check-prefix=OBJ
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=asm %s | FileCheck %s --check-prefix=ASM

# OBJ: 19 20 00 01 addi rd8, rd0, 1
# OBJ: 12 04 2f fd cmps rd1, rd2, -3
# OBJ: 13 0c 40 0a cmpu rd3, rd4, 10
# ASM: addi rd8, rd0, 1
# ASM: cmps rd1, rd2, -3
# ASM: cmpu rd3, rd4, 10

	addi rd8, rd0, 1
	cmps rd1, rd2, -3
	cmpu rd3, rd4, 10
