# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=obj %s -o %t
# RUN: llvm-objdump -d --triple=dadao-unknown-elf %t | FileCheck %s --check-prefix=OBJ
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=asm %s | FileCheck %s --check-prefix=ASM

# OBJ: 14 04 ff ff orw rd1, 0, 65535
# OBJ: 15 09 0f ff andnw rd2, 1, 4095
# OBJ: 16 0e 00 ff setzw rd3, 2, 255
# OBJ: 17 13 00 00 setow rd4, 3, 0
# ASM: orw rd1, 0, 65535
# ASM: andnw rd2, 1, 4095
# ASM: setzw rd3, 2, 255
# ASM: setow rd4, 3, 0

	orw rd1, 0, 65535
	andnw rd2, 1, 4095
	setzw rd3, 2, 255
	setow rd4, 3, 0
