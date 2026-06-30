# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=obj %s -o %t
# RUN: llvm-objdump -d --triple=dadao-unknown-elf %t | FileCheck %s
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=asm %s | FileCheck %s

# CHECK: breq rd1, rd2, 8
# CHECK: brne rd3, rd4, -16

	breq rd1, rd2, 8
	brne rd3, rd4, -16
