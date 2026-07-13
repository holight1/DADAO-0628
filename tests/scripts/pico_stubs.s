.text
# Syscall stubs for picolibc — DADAO trap ABI
# Calling convention: args in rd16, rd17, rd18, ...
# Trap ABI: rd16=sysno, rd17=arg0, rd18=arg1, rd19=arg2, rd31=ret

.globl _write
_write:
    addi rd19, rd18, 0     # arg2=len
    addi rd18, rd17, 0     # arg1=buf
    addi rd17, rd16, 0     # arg0=fd
    addi rd16, rd0, 64     # sysno=write
    trap 2, 0
    ret rd0, 0

.globl _exit
_exit:
    addi rd17, rd16, 0     # arg0=code
    addi rd16, rd0, 93     # sysno=exit
    trap 2, 0

.globl _sbrk
_sbrk:
    addi rd20, rd16, 0     # save incr
    addi rd17, rd0, 0      # arg=0
    addi rd16, rd0, 214    # sysno=brk, get current
    trap 2, 0
    addi rd18, rd31, 0     # cur = rd31
    addi rd16, rd0, 214    # sysno=brk
    addi rd17, rd18, 0     # rd17=cur
    add rd0, rd17, rd17, rd20  # rd17=cur+incr
    trap 2, 0
    addi rd31, rd18, 0     # return old cur
    ret rd0, 0
