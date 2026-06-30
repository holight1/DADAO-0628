# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=obj %s -o %t
# RUN: llvm-objdump -d --triple=dadao-unknown-elf %t | FileCheck %s --check-prefix=OBJ
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=asm %s | FileCheck %s --check-prefix=ASM

# OBJ: 1a 04 20 c4 add rd1, rd2, rd3, rd4
# OBJ: 1b 14 61 c8 sub rd5, rd6, rd7, rd8
# OBJ: 1c 24 a2 cc muls rd9, rd10, rd11, rd12
# OBJ: 1d 34 e3 d0 mulu rd13, rd14, rd15, rd16
# OBJ: 1e 45 24 d4 divs rd17, rd18, rd19, rd20
# OBJ: 1f 55 65 d8 divu rd21, rd22, rd23, rd24
# ASM: add rd1, rd2, rd3, rd4
# ASM: sub rd5, rd6, rd7, rd8
# ASM: muls rd9, rd10, rd11, rd12
# ASM: mulu rd13, rd14, rd15, rd16
# ASM: divs rd17, rd18, rd19, rd20
# ASM: divu rd21, rd22, rd23, rd24

	add rd1, rd2, rd3, rd4
	sub rd5, rd6, rd7, rd8
	muls rd9, rd10, rd11, rd12
	mulu rd13, rd14, rd15, rd16
	divs rd17, rd18, rd19, rd20
	divu rd21, rd22, rd23, rd24
