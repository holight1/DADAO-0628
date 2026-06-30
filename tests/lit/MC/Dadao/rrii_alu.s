# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=obj %s -o %t
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=asm %s | FileCheck %s

# CHECK: addi rd8, rd0, 1
# CHECK: cmps rd1, rd2, -3
# CHECK: cmpu rd3, rd4, 10

	addi rd8, rd0, 1
	cmps rd1, rd2, -3
	cmpu rd3, rd4, 10
