/* ML-024a: mallocng size-class (small-object/slab-pool) path E2E test.
   ML-023a closed the mallocng *direct-mmap* path (allocations >=
   MMAP_THRESHOLD=131052 bytes); this test covers the complementary
   size-class path (small allocations below that threshold, served by
   src/malloc/mallocng/donate.c + malloc.c's size_classes[]/alloc_group()
   pooling logic instead of a per-allocation mmap).

   Root cause this test guards against (ML-024a diagnosis): DADAO's `addi`
   instruction has a signed 12-bit immediate (imms12, -2048..2047,
   contracts/isa/spec.md SS3.6/SS1011). arch/dadao/crt_arch.h synthesized
   the AT_PAGESZ=4096 auxv entry with `addi rd8, rd0, 4096`, which silently
   wrapped to 0 (4096 does not fit in 12 bits) instead of erroring. This
   made libc.page_size==0 at runtime instead of 4096, which cascades into:
     - src/malloc/lite_malloc.c's PAGE_SIZE-based arithmetic (PAGE_SIZE-1
       underflows to SIZE_MAX, -PAGE_SIZE becomes 0), zeroing out its
       computed `req` and corrupting its brk bookkeeping, ending in a
       zero-length mmap(0, 0, ...) call;
     - mallocng's alloc_group() reading PGSZ (== libc.page_size) directly
       (its sibling alloc_meta() only clamps a *local* copy, which does not
       propagate back to libc.page_size), so pagesize/2==0 forces every
       size class down the "individually mmapped" branch and the rounded
       `needed` size collapses to 0, again yielding mmap(0, 0, ...).
   QEMU's mmap syscall responder (target/dadao/cpu.c case 222) correctly
   rejects a zero-length request with -EINVAL, so malloc() returned a
   clean NULL on QEMU. gem5's mmap responder did not reject the zero-length
   request the same way and returned a non-NULL but entirely unbacked
   address; a program that only checks the returned pointer for NULL (and
   never dereferences it) would appear to "succeed" on gem5 while any
   program that actually reads/writes through the pointer would fault
   (observed as SIM_END: MALIGN). The fix (crt_arch.h) uses `setzw rd8, 0,
   4096` (an unsigned 16-bit-immediate instruction, contracts/isa/spec.md
   SS607/SS617) to materialize 4096 exactly.

   This test exercises the real mallocng allocator specifically: it calls
   `malloc()` then `free()`, and independent review (ML-024a) confirmed via
   `llvm-nm` that referencing `free` anywhere in a translation unit's link
   pulls in mallocng/malloc.o, whose strong `malloc` entry point then wins
   over musl's separate lite_malloc.c bump allocator's weak `malloc` symbol
   for the WHOLE binary -- so a malloc-only call in the SAME link (as an
   earlier version of this file had) would NOT actually exercise
   lite_malloc as intended; that scenario needs its own, separate
   translation unit with no `free`/mallocng-specific reference anywhere in
   the link. See musl_malloc_sizeclass_liteonly.test /
   Inputs/musl_malloc_sizeclass_liteonly.c for that scenario -- both must
   pass, independently, for the size-class path to be considered fixed.
   Writes go through a `volatile char *` (see musl_malloc_printf.c's header
   comment and
   [[feedback-volatile-needed-for-memory-verification-tests]] for why
   non-volatile reads/writes can be folded away by -O2 store-to-load
   forwarding). */
#include <stdlib.h>
#include <stdio.h>

static int malloc_write_free(size_t n, int seed) {
    char *p = malloc(n);
    if (!p) return 0;
    volatile char *vp = (volatile char *)p;
    for (size_t i = 0; i < n; i++) vp[i] = (char)((i + seed) & 0x7f);
    for (size_t i = 0; i < n; i++)
        if (vp[i] != (char)((i + seed) & 0x7f)) return 0;
    free(p);
    return 1;
}

int main(void) {
    if (!malloc_write_free(8, 1)) return 21;
    if (!malloc_write_free(500, 2)) return 22;
    if (!malloc_write_free(4095, 3)) return 23;
    puts("SIZECLASS_OK");
    return 42;
}
