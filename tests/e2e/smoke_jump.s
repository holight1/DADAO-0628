# tests/e2e/smoke_jump.s
# jump +1 skips halt rd1 (exit 1) and goes to exit 0
.text
jump    1
halt    rd1
addi    rd1, rd0, 0
halt    rd1
