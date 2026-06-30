# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=obj %s -o %t
# RUN: llvm-objdump -d --triple=dadao-unknown-elf %t | FileCheck %s --check-prefix=OBJ
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=asm %s | FileCheck %s --check-prefix=ASM

# OBJ: 6e 04 00 00 ret rd1, 0
# OBJ: 48 09 00 00 rela rb2, 65536
# ASM: ret rd1, 0
# ASM: rela rb2, 65536

	ret rd1, 0
	rela rb2, 65536
