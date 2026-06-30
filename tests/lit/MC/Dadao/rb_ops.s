# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=obj %s -o %t
# RUN: llvm-objdump -d --triple=dadao-unknown-elf %t | FileCheck %s --check-prefix=OBJ
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=asm %s | FileCheck %s --check-prefix=ASM

# OBJ: 49 04 20 08 addi rb1, rb2, 8
# OBJ: 43 04 20 08 ldo rb1, rb2, 8
# OBJ: 4b 04 20 00 sto rb1, rb2, 0
# OBJ: 48 04 00 01 rela rb1, 1
# OBJ: 4e 04 ab cd setzw rb1, 0, 43981
# OBJ: 4f 04 20 41 stmo rb1, rb2, rd1, 1
# OBJ: 10 a4 a0 41 rd2rb rb10, rd1, 1
# OBJ: 10 a8 a0 41 rb2rd rd10, rb1, 1
# OBJ: 10 ac a0 41 rb2rb rb10, rb1, 1
# OBJ: 10 b8 10 81 add rb1, rb2, rd1
# OBJ: 10 bc 10 81 sub rb1, rb2, rd1
# OBJ: 10 b4 10 42 cmp rd1, rb1, rb2
# ASM: addi rb1, rb2, 8
# ASM: ldo rb1, rb2, 8
# ASM: sto rb1, rb2, 0
# ASM: rela rb1, 1
# ASM: setzw rb1, 0, 43981
# ASM: stmo rb1, rb2, rd1, 1
# ASM: rd2rb rb10, rd1, 1
# ASM: rb2rd rd10, rb1, 1
# ASM: rb2rb rb10, rb1, 1
# ASM: add rb1, rb2, rd1
# ASM: sub rb1, rb2, rd1
# ASM: cmp rd1, rb1, rb2

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
