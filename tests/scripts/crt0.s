# DADAO freestanding crt0 / _start
# Trampoline sets SP (rb1) = 0x87FF0000, then jumps to 0x80000000
# _start calls main(), then halts with main's return value

.text
.globl _start
_start:
    call main
    halt rd31
    .size _start, . - _start
