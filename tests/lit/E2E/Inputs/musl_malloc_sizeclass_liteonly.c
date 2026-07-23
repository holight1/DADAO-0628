/* ML-024a: mallocng size-class E2E test, lite_malloc-linked variant.
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
   malloc+write+free (mallocng) scenario -- both must pass, independently,
   for the size-class path to be considered fixed. */
#include <stdlib.h>
#include <stdio.h>

int main(void) {
    void *p = malloc(8);
    if (!p) return 11;
    puts("SIZECLASS_LITE_OK");
    return 42;
}
