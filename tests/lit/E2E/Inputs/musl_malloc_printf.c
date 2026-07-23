/* ML-023a: real mallocng E2E milestone (originally ML-014a, blocked since
   2026-07-18 across ML-014f/j/m/n/o/p -- see
   code-agent/tasks/archive/2026-07-ml014-malloc-e2e-run/ for the full
   history). Two direct-mmap allocations (mallocng's MMAP_THRESHOLD is 131052
   bytes, src/malloc/mallocng/meta.h -- confirmed by ML-014f/j; both sizes
   below deliberately chosen >= threshold so this exercises the real mmap(222)
   path, not the size-class slab pool), each written/read-back-verified at
   page granularity plus both edge bytes, then freed, then a real puts()
   through musl's buffered stdio -> SYS_writev(66) path (ML-019a).

   This exact program is what walled off the "0x90001000 gem5 page-table
   fault" / QEMU exit 13/14 chain in ML-014m -- it now runs clean on both
   backends because of four independently-landed fixes that ML-014m predates:
   DL-070a (CALL instruction Defs missing RB31), ML-018a (musl -O0 workaround
   removal), ML-019a (SYS_writev responder), and ML-021a (ISD::CALLSEQ_START/
   END glue-chain fix -- mallocng's allocator path makes several consecutive
   calls within one basic block, exactly the pattern ML-021a's bug hit). See
   this task's completion notes in code-agent/tasks/
   ML-014a-musl-e2e-malloc-printf.md for the address-level verification that
   the mmap path (not the slab pool) is really what serves these two
   allocations.

   IMPORTANT: check_block accesses the block through a `volatile char *`.
   ML-023a's independent subagent review found that with a plain (non-
   volatile) `char *` at -O2, LLVM proves via store-to-load forwarding that
   every read in check_block equals the value just written in the same
   invocation, and folds nearly all of the read-back comparisons to
   compile-time-true -- confirmed by IR inspection: only 1 real `load` was
   emitted for the whole program (the block-2 spaced loop survived only
   because it exceeds the full-unroll threshold), and the `return 12`
   (block-1 failure) path was entirely dead/unreachable. That would let this
   test pass even if the historical class of bug it exists to catch (mmap
   arena silently unbacked / writes not really landing, see
   docs/issues-archive.yaml `mmap-arena-unbacked-real-memory-qemu-gem5`)
   recurred but only affected block 1 or the edge bytes. The `volatile`
   qualifier forces LLVM to emit genuine load instructions for every
   comparison (confirmed: 37 `load`s in the -O2 IR, and `return 12` is
   reachable again). A deliberate negative-control build (corrupting the
   expected value for the `p[1]` edge check) was independently verified to
   make the test fail with exit=12 rather than passing, proving the check is
   load-bearing rather than vacuously true. */
#include <stdlib.h>
#include <stdio.h>

static int check_block(char *p, size_t n, int seed) {
    volatile char *vp = (volatile char *)p;
    for (size_t i = 0; i < n; i += 4096) vp[i] = (char)((i + seed) & 0x7f);
    vp[1] = (char)(0x10 + seed);
    vp[n-1] = (char)(0x20 + seed);
    for (size_t i = 0; i < n; i += 4096) if (vp[i] != (char)((i + seed) & 0x7f)) return 0;
    if (vp[1] != (char)(0x10 + seed)) return 0;
    if (vp[n-1] != (char)(0x20 + seed)) return 0;
    return 1;
}

int main(void) {
    char *p = malloc(131052UL);
    if (!p) return 11;
    if (!check_block(p, 131052UL, 1)) return 12;
    free(p);

    char *q = malloc(262144UL);
    if (!q) return 21;
    if (!check_block(q, 262144UL, 2)) return 22;
    free(q);

    puts("MALLOC_CHAIN_OK");
    return 42;
}
