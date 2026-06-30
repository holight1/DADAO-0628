# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=obj %s -o %t
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=asm %s | FileCheck %s

# CHECK: ldmbs rd1, rb2, rd3, 0
# CHECK: ldmws rd4, rb5, rd6, 7
# CHECK: ldmts rd7, rb8, rd9, 15
# CHECK: ldmo rd10, rb11, rd12, 31
# CHECK: stmb rd13, rb14, rd15, 0
# CHECK: stmw rd16, rb17, rd18, 63
# CHECK: stmt rd19, rb20, rd21, 1
# CHECK: stmo rd22, rb23, rd24, 2
# CHECK: ldmbu rd25, rb26, rd27, 3
# CHECK: ldmwu rd28, rb29, rd30, 4
# CHECK: ldmtu rd31, rb32, rd33, 5

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
