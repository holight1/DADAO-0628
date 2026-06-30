# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=obj %s -o %t
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=asm %s | FileCheck %s

# CHECK: add rd1, rd2, rd3, rd4
# CHECK: sub rd5, rd6, rd7, rd8
# CHECK: muls rd9, rd10, rd11, rd12
# CHECK: mulu rd13, rd14, rd15, rd16
# CHECK: divs rd17, rd18, rd19, rd20
# CHECK: divu rd21, rd22, rd23, rd24

	add rd1, rd2, rd3, rd4
	sub rd5, rd6, rd7, rd8
	muls rd9, rd10, rd11, rd12
	mulu rd13, rd14, rd15, rd16
	divs rd17, rd18, rd19, rd20
	divu rd21, rd22, rd23, rd24
