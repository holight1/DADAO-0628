# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=obj %s -o %t
# RUN: llvm-objdump -d --triple=dadao-unknown-elf %t | FileCheck %s
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=asm %s | FileCheck %s

# CHECK: shlu rd1, rd2, 3
# CHECK: shrs rd3, rd4, 5
# CHECK: shru rd5, rd6, 7
# CHECK: exts rd7, rd8, 9

	shlu rd1, rd2, 3
	shrs rd3, rd4, 5
	shru rd5, rd6, 7
	exts rd7, rd8, 9
