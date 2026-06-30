# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=obj %s -o %t
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=asm %s | FileCheck %s

# CHECK: orw rd1, 0, 65535
# CHECK: andnw rd2, 1, 4095
# CHECK: setzw rd3, 2, 255
# CHECK: setow rd4, 3, 0

	orw rd1, 0, 65535
	andnw rd2, 1, 4095
	setzw rd3, 2, 255
	setow rd4, 3, 0
