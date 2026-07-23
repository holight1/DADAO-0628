/* ML-024c: lite_malloc small-allocation memory-discrimination test.
   See Inputs/musl_malloc_sizeclass.c's header comment for the full root
   cause (crt_arch.h's AT_PAGESZ auxv entry silently wrapped 4096 to 0 via
   an out-of-range `addi` immediate, leaving libc.page_size==0 at runtime).

   This translation unit deliberately references ONLY `malloc()`, never
   `free()` or any other mallocng-specific symbol, anywhere in the link
   (confirmed by `llvm-nm`: this binary resolves `malloc` as the WEAK
   symbol at musl's src/malloc/lite_malloc.c's `default_malloc` ->
   `__simple_malloc`, not mallocng's strong entry point -- an earlier,
   consolidated version of this test that put a malloc-only check in the
   same translation unit as a malloc+free check was caught by independent
   review to actually link mallocng for BOTH checks, because `free()`
   anywhere in the link pulls in mallocng/malloc.o whose strong `malloc`
   symbol then wins over lite_malloc's weak one for the ENTIRE binary, not
   just the call site that needed it). This is the scenario the diagnosis
   found silently exercises musl's separate lite_malloc.c bump allocator
   (PAGE_SIZE-based req/brk arithmetic) instead of mallocng, and is a
   genuinely distinct code path from musl_malloc_sizeclass.test's
   malloc+write+free (mallocng) scenario.

   Volatile first/last-byte stores and loads are intentional. Checking only
   for a non-NULL result allowed the old AT_PAGESZ=0 state to pass on gem5
   with an unbacked pointer. */
#include <stdlib.h>
#include <stdio.h>

int main(void) {
    volatile unsigned char *p = (volatile unsigned char *)malloc(8);
    if (!p) return 11;
    p[0] = 0x5a;
    p[7] = 0xa5;
    if (p[0] != 0x5a) return 12;
    if (p[7] != 0xa5) return 13;
    puts("SIZECLASS_LITE_OK");
    return 42;
}
