# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=obj %s -o %t
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=asm %s | FileCheck %s

# CHECK: addi rb1, rb2, 8
# CHECK: ldo rb1, rb2, 8
# CHECK: sto rb1, rb2, 0
# CHECK: rela rb1, 1
# CHECK: setzw rb1, 0, 43981
# CHECK: stmo rb1, rb2, rd1, 1
# CHECK: rd2rb rb10, rd1, 1
# CHECK: rb2rd rd10, rb1, 1
# CHECK: rb2rb rb10, rb1, 1
# CHECK: add rb1, rb2, rd1
# CHECK: sub rb1, rb2, rd1
# CHECK: cmp rd1, rb1, rb2

	addi rb1, rb2, 8
	ldo rb1, rb2, 8
	sto rb1, rb2, 0
	rela rb1, 1
	setzw rb1, 0, 43981
	stmo rb1, rb2, rd1, 1
	rd2rb rb10, rd1, 1
	rb2rd rd10, rb1, 1
	rb2rb rb10, rb1, 1
	add rb1, rb2, rd1
	sub rb1, rb2, rd1
	cmp rd1, rb1, rb2
