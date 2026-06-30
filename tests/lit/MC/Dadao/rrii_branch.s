# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=obj %s -o %t
# RUN: llvm-objdump -d --triple=dadao-unknown-elf %t | FileCheck %s --check-prefix=OBJ
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=asm %s | FileCheck %s --check-prefix=ASM

# OBJ: 2e 04 20 08 breq rd1, rd2, 8
# OBJ: 2f 0c 4f f0 brne rd3, rd4, -16
# ASM: breq rd1, rd2, 8
# ASM: brne rd3, rd4, -16

	breq rd1, rd2, 8
	brne rd3, rd4, -16
