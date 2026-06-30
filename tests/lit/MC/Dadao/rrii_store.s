# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=obj %s -o %t
# RUN: llvm-objdump -d --triple=dadao-unknown-elf %t | FileCheck %s
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=asm %s | FileCheck %s

# CHECK: stb rd1, rb2, 0
# CHECK: stw rd3, rb4, 16
# CHECK: stt rd5, rb6, -32
# CHECK: sto rd7, rb8, 48

	stb rd1, rb2, 0
	stw rd3, rb4, 16
	stt rd5, rb6, -32
	sto rd7, rb8, 48
