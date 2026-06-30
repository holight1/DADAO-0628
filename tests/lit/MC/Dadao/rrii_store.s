# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=obj %s -o %t
# RUN: llvm-objdump -d --triple=dadao-unknown-elf %t | FileCheck %s --check-prefix=OBJ
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=asm %s | FileCheck %s --check-prefix=ASM

# OBJ: 38 04 20 00 stb rd1, rb2, 0
# OBJ: 39 0c 40 10 stw rd3, rb4, 16
# OBJ: 3a 14 6f e0 stt rd5, rb6, -32
# OBJ: 3b 1c 80 30 sto rd7, rb8, 48
# ASM: stb rd1, rb2, 0
# ASM: stw rd3, rb4, 16
# ASM: stt rd5, rb6, -32
# ASM: sto rd7, rb8, 48

	stb rd1, rb2, 0
	stw rd3, rb4, 16
	stt rd5, rb6, -32
	sto rd7, rb8, 48
