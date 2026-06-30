# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=obj %s -o %t
# RUN: llvm-objdump -d --triple=dadao-unknown-elf %t | FileCheck %s --check-prefix=OBJ
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=asm %s | FileCheck %s --check-prefix=ASM

# OBJ: 28 04 01 00 brn rd1, 256
# OBJ: 29 08 02 00 brnn rd2, 512
# OBJ: 2a 0f ff 80 brz rd3, -128
# OBJ: 2b 10 04 00 brnz rd4, 1024
# OBJ: 2c 14 08 00 brp rd5, 2048
# OBJ: 2d 1b f0 00 brnp rd6, -4096
# ASM: brn rd1, 256
# ASM: brnn rd2, 512
# ASM: brz rd3, -128
# ASM: brnz rd4, 1024
# ASM: brp rd5, 2048
# ASM: brnp rd6, -4096

	brn rd1, 256
	brnn rd2, 512
	brz rd3, -128
	brnz rd4, 1024
	brp rd5, 2048
	brnp rd6, -4096
