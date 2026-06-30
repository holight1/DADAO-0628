# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=obj %s -o %t
# RUN: llvm-objdump -d --triple=dadao-unknown-elf %t | FileCheck %s
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=asm %s | FileCheck %s

# CHECK: jump -1
# CHECK: call -1
# CHECK: jump rb1, rd2, 0
# CHECK: call rb3, rd4, 8

	jump -1
	call -1
	jump rb1, rd2, 0
	call rb3, rd4, 8
