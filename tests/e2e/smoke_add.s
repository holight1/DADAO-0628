# tests/e2e/smoke_add.s
# rd1 = 10, rd2 = 32; add rd0,rd3,rd1,rd2; rd3 = 42
.text
addi rd1, rd0, 10
addi rd2, rd0, 32
add  rd0, rd3, rd1, rd2
halt rd3
