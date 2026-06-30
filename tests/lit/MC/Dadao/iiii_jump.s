# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=obj %s -o %t
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=asm %s | FileCheck %s

# CHECK: jump 16777215
# CHECK: call 16777215
# CHECK: jump rb1, rd2, 0
# CHECK: call rb3, rd4, 8

	jump 16777215
	call 16777215
	jump rb1, rd2, 0
	call rb3, rd4, 8
