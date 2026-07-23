/* ML-025a: minimal real stdin-read E2E input, deliberately NOT using
   scanf()/any v*scanf() family function -- see musl_scanf_int.test (XFAIL)
   for why any scanf() call with a conversion specifier hits the separate,
   pre-existing varargs-pointer-args-lost-rb-bank-save-area bug. getchar()
   takes no pointer varargs at all, so it exercises the newly-added
   SYS_read(63) cfx_smon responder (added to both QEMU's target/dadao/cpu.c
   and gem5's arch/dadao/decoder.cc by this task) end-to-end without
   tripping that unrelated gap -- this is what actually proves the new
   host-stdin-to-guest-memory plumbing genuinely works on both backends,
   independent of the still-blocked scanf() runtime-correctness goal. */
#include <stdio.h>

int main(void) {
    int c1 = getchar();
    int c2 = getchar();
    printf("c1=%d c2=%d\n", c1, c2);
    return 42;
}
