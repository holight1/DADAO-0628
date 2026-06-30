# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=obj %s -o %t
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=asm %s | FileCheck %s

# CHECK: ret rd1, 0
# CHECK: rela rb2, 65536

	ret rd1, 0
	rela rb2, 65536
