# DADAO musl-style crt0 variant (ML-008a).
#
# Distinct from tests/scripts/crt0.s (the picolibc-stage `call main` stub,
# which does not build any stack table) -- the two coexist for different
# pipeline stages. This variant synthesizes, entirely in user-mode `_start`
# (no simulator/loader support required), the argc/argv/envp/auxv stack
# layout that musl's crt1.c / `_start_c(long *p)` expects, then calls
# `_start_c(p)`. `_start_c` is provided by whatever object is linked
# alongside this file (see tests/lit/E2E/musl_crt0_auxv.test for the probe
# used to validate the layout).
#
# Trampoline sets SP (rb1) = 0x87FF0000 before `_start` runs (ADR-0004).
#
# Stack layout built at rb1 (after reservation), 8-byte cells, low->high
# address, matching the musl `_start_c(long *p)` protocol where p[0] is
# argc:
#
#   [0]  argc              = 1
#   [1]  argv[0]           = &prog_str  ("prog", NUL-terminated placeholder)
#   [2]  argv terminator   = 0 (NULL)
#   [3]  envp terminator   = 0 (NULL; empty environment)
#   [4]  AT_PAGESZ  (6)     [5]  4096
#   [6]  AT_UID     (11)    [7]  0
#   [8]  AT_EUID    (12)    [9]  0
#   [10] AT_GID     (13)    [11] 0
#   [12] AT_EGID    (14)    [13] 0
#   [14] AT_SECURE  (23)    [15] 0
#   [16] AT_RANDOM  (25)    [17] &rand_buf (16-byte buffer, content unspecified)
#   [18] AT_NULL    (0)     [19] 0
#
# Total: 20 cells * 8 bytes = 160 bytes. p = rb1 after reservation (passed
# as the pointer argument in rb16 per contracts/abi/spec.md §2.1).

.text
.globl _start
_start:
    addi rb1, rb1, -160

    # Resolve the two data addresses we need up front (PC-relative
    # rela+addi pair, per contracts/isa/spec.md §4.8; same pattern as
    # tests/lit/E2E/mmap_probe.test's msg_data).
    rela rb8, prog_str
    addi rb8, rb8, prog_str
    rela rb9, rand_buf
    addi rb9, rb9, rand_buf

    # [0] argc = 1
    addi rd8, rd0, 1
    sto rd8, rb1, 0

    # [1] argv[0] = &prog_str (RB-form store: pointer value)
    sto rb8, rb1, 8

    # [2] argv terminator = NULL
    addi rd8, rd0, 0
    sto rd8, rb1, 16

    # [3] envp terminator = NULL (empty envp: just the one NULL entry)
    sto rd8, rb1, 24

    # [4..5] AT_PAGESZ = 4096
    addi rd8, rd0, 6
    sto rd8, rb1, 32
    addi rd8, rd0, 4096
    sto rd8, rb1, 40

    # [6..7] AT_UID = 0
    addi rd8, rd0, 11
    sto rd8, rb1, 48
    addi rd8, rd0, 0
    sto rd8, rb1, 56

    # [8..9] AT_EUID = 0
    addi rd8, rd0, 12
    sto rd8, rb1, 64
    addi rd8, rd0, 0
    sto rd8, rb1, 72

    # [10..11] AT_GID = 0
    addi rd8, rd0, 13
    sto rd8, rb1, 80
    addi rd8, rd0, 0
    sto rd8, rb1, 88

    # [12..13] AT_EGID = 0
    addi rd8, rd0, 14
    sto rd8, rb1, 96
    addi rd8, rd0, 0
    sto rd8, rb1, 104

    # [14..15] AT_SECURE = 0
    addi rd8, rd0, 23
    sto rd8, rb1, 112
    addi rd8, rd0, 0
    sto rd8, rb1, 120

    # [16..17] AT_RANDOM = &rand_buf
    addi rd8, rd0, 25
    sto rd8, rb1, 128
    sto rb9, rb1, 136

    # [18..19] AT_NULL terminator
    addi rd8, rd0, 0
    sto rd8, rb1, 144
    sto rd8, rb1, 152

    # p = rb1 (pointer argument -> RB bank, contracts/abi/spec.md §2.1)
    rb2rb rb16, rb1, 1
    call _start_c

    # _start_c is expected to halt and never return. If it somehow does
    # return, halt with a distinguishing sentinel (99) instead of falling
    # through into the data below.
    addi rd31, rd0, 99
    halt rd31
    .size _start, . - _start

    .align 8, 0
prog_str:
    .asciz "prog"

    .align 8, 0
rand_buf:
    .fill 16, 1, 0
