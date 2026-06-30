# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=obj %s -o %t
# RUN: llvm-objdump -d --triple=dadao-unknown-elf %t | FileCheck %s --check-prefix=OBJ
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=asm %s | FileCheck %s --check-prefix=ASM

# OBJ: 34 04 20 c0 ldmbs rd1, rb2, rd3, 0
# OBJ: 35 10 51 87 ldmws rd4, rb5, rd6, 7
# OBJ: 36 1c 82 4f ldmts rd7, rb8, rd9, 15
# OBJ: 37 28 b3 1f ldmo rd10, rb11, rd12, 31
# OBJ: 3c 34 e3 c0 stmb rd13, rb14, rd15, 0
# OBJ: 3d 41 14 bf stmw rd16, rb17, rd18, 63
# OBJ: 3e 4d 45 41 stmt rd19, rb20, rd21, 1
# OBJ: 3f 59 76 02 stmo rd22, rb23, rd24, 2
# OBJ: 44 65 a6 c3 ldmbu rd25, rb26, rd27, 3
# OBJ: 45 71 d7 84 ldmwu rd28, rb29, rd30, 4
# OBJ: 46 7e 08 45 ldmtu rd31, rb32, rd33, 5
# ASM: ldmbs rd1, rb2, rd3, 0
# ASM: ldmws rd4, rb5, rd6, 7
# ASM: ldmts rd7, rb8, rd9, 15
# ASM: ldmo rd10, rb11, rd12, 31
# ASM: stmb rd13, rb14, rd15, 0
# ASM: stmw rd16, rb17, rd18, 63
# ASM: stmt rd19, rb20, rd21, 1
# ASM: stmo rd22, rb23, rd24, 2
# ASM: ldmbu rd25, rb26, rd27, 3
# ASM: ldmwu rd28, rb29, rd30, 4
# ASM: ldmtu rd31, rb32, rd33, 5

	ldmbs rd1, rb2, rd3, 0
	ldmws rd4, rb5, rd6, 7
	ldmts rd7, rb8, rd9, 15
	ldmo rd10, rb11, rd12, 31
	stmb rd13, rb14, rd15, 0
	stmw rd16, rb17, rd18, 63
	stmt rd19, rb20, rd21, 1
	stmo rd22, rb23, rd24, 2
	ldmbu rd25, rb26, rd27, 3
	ldmwu rd28, rb29, rd30, 4
	ldmtu rd31, rb32, rd33, 5
