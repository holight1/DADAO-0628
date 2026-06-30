# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=obj %s -o %t
# RUN: llvm-objdump -d --triple=dadao-unknown-elf %t | FileCheck %s --check-prefix=OBJ
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=asm %s | FileCheck %s --check-prefix=ASM

# OBJ: 64 ff ff ff jump -1
# OBJ: 6c ff ff ff call -1
# OBJ: 65 04 20 00 jump rb1, rd2, 0
# OBJ: 6d 0c 40 08 call rb3, rd4, 8
# ASM: jump -1
# ASM: call -1
# ASM: jump rb1, rd2, 0
# ASM: call rb3, rd4, 8

	jump -1
	call -1
	jump rb1, rd2, 0
	call rb3, rd4, 8
