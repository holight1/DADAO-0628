# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=obj %s -o %t
# RUN: llvm-objdump -d --triple=dadao-unknown-elf %t | FileCheck %s --check-prefix=OBJ
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=asm %s | FileCheck %s --check-prefix=ASM

# OBJ: 30 04 20 00 ldbs rd1, rb2, 0
# OBJ: 31 0c 40 08 ldws rd3, rb4, 8
# OBJ: 32 14 6f f0 ldts rd5, rb6, -16
# OBJ: 33 1c 80 20 ldo rd7, rb8, 32
# OBJ: 40 24 a0 40 ldbu rd9, rb10, 64
# OBJ: 41 2c cf 80 ldwu rd11, rb12, -128
# OBJ: 42 34 e0 ff ldtu rd13, rb14, 255
# ASM: ldbs rd1, rb2, 0
# ASM: ldws rd3, rb4, 8
# ASM: ldts rd5, rb6, -16
# ASM: ldo rd7, rb8, 32
# ASM: ldbu rd9, rb10, 64
# ASM: ldwu rd11, rb12, -128
# ASM: ldtu rd13, rb14, 255

	ldbs rd1, rb2, 0
	ldws rd3, rb4, 8
	ldts rd5, rb6, -16
	ldo rd7, rb8, 32
	ldbu rd9, rb10, 64
	ldwu rd11, rb12, -128
	ldtu rd13, rb14, 255
