# tests/e2e/smoke_arith.s
# addi + halt: rd1 = 42, exit 42
.text
addi rd1, rd0, 42
halt rd1
