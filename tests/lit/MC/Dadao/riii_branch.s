# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=obj %s -o %t
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=asm %s | FileCheck %s

# CHECK: brn rd1, 256
# CHECK: brnn rd2, 512
# CHECK: brz rd3, -128
# CHECK: brnz rd4, 1024
# CHECK: brp rd5, 2048
# CHECK: brnp rd6, -4096

	brn rd1, 256
	brnn rd2, 512
	brz rd3, -128
	brnz rd4, 1024
	brp rd5, 2048
	brnp rd6, -4096
