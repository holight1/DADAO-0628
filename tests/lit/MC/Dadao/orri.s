# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=obj %s -o %t
# RUN: llvm-objdump -d --triple=dadao-unknown-elf %t | FileCheck %s --check-prefix=OBJ
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=asm %s | FileCheck %s --check-prefix=ASM

# OBJ: 10 64 10 83{{.*}}shlu rd1, rd2, 3
# OBJ: 10 68 31 05{{.*}}shrs rd3, rd4, 5
# OBJ: 10 6c 51 87{{.*}}shru rd5, rd6, 7
# OBJ: 10 70 72 09{{.*}}exts rd7, rd8, 9
# ASM: shlu rd1, rd2, 3
# ASM: shrs rd3, rd4, 5
# ASM: shru rd5, rd6, 7
# ASM: exts rd7, rd8, 9

	shlu rd1, rd2, 3
	shrs rd3, rd4, 5
	shru rd5, rd6, 7
	exts rd7, rd8, 9
