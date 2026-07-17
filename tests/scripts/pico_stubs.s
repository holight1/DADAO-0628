.text
# Syscall stubs for picolibc — DADAO trap ABI
# Function call ABI (contracts/abi/spec.md SS2.1/SS3.1): integer/scalar
# params/returns use the RD bank (rd16..rd31), pointer params/returns use
# the RB bank (rb16..rb31), each bank counted independently. This is
# DISTINCT from the DADAO trap/syscall ABI below, which is its own
# separate, RD-only convention untouched by DL-069a/ML-013a.
# Trap ABI: rd16=sysno, rd17=arg0, rd18=arg1, rd19=arg2, rd31=ret

.globl _write
_write:
    # Function-call ABI: int fd=rd16 (int param 1), char *buf=rb16
    # (pointer param 1, independently counted), int len=rd17 (int param 2).
    # DL-069a made this the real backend calling convention (see
    # tests/scripts/stdout_min.c's `_write(1, &ch, 1)` call site).
    addi rd19, rd17, 0     # trap arg2=len
    rb2rd rd18, rb16, 1    # trap arg1=buf (RB bank param -> RD-bank trap arg slot)
    addi rd17, rd16, 0     # trap arg0=fd
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
    # Function-call ABI: void *_sbrk(ptrdiff_t incr) — incr is a scalar
    # (rd16, int param 1, unaffected), but the return value is a pointer
    # so it must go in rb31 (contracts/abi/spec.md SS3.1), not rd31.
    # NOTE: currently unreferenced by any linked test (malloc_hello.test's
    # nano-malloc is actually backed by picolibc's own libos/fallback/sbrk.c
    # __fallback_sbrk, an in-image bump allocator over the linker-defined
    # __heap_start/__heap_end region — see tests/scripts/dadao.ld — not by
    # this trap-based stub); corrected for ABI self-consistency per
    # ML-013a, verified dead-code-safe (no caller of the exact symbol
    # `_sbrk` exists anywhere in tests/ or .work/source/musl).
    addi rd20, rd16, 0     # save incr
    addi rd17, rd0, 0      # arg=0
    addi rd16, rd0, 214    # sysno=brk, get current
    trap 2, 0
    addi rd18, rd31, 0     # cur = rd31 (trap ABI return register, unaffected)
    addi rd16, rd0, 214    # sysno=brk
    addi rd17, rd18, 0     # rd17=cur
    add rd0, rd17, rd17, rd20  # rdha=rd0(discard carry), rdhb=rd17=cur+incr
    trap 2, 0
    rd2rb rb31, rd18, 1    # return old cur as a pointer (RB bank return, SS3.1)
    ret rd0, 0
