# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=obj %s -o %t
# RUN: llvm-objdump -d --triple=dadao-unknown-elf %t | FileCheck %s
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=asm %s | FileCheck %s

# CHECK: ldbs rd1, rb2, 0
# CHECK: ldws rd3, rb4, 8
# CHECK: ldts rd5, rb6, -16
# CHECK: ldo rd7, rb8, 32
# CHECK: ldbu rd9, rb10, 64
# CHECK: ldwu rd11, rb12, -128
# CHECK: ldtu rd13, rb14, 255

	ldbs rd1, rb2, 0
	ldws rd3, rb4, 8
	ldts rd5, rb6, -16
	ldo rd7, rb8, 32
	ldbu rd9, rb10, 64
	ldwu rd11, rb12, -128
	ldtu rd13, rb14, 255
