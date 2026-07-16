/* Adapted from llvm-test-suite SingleSource/UnitTests/2008-04-18-LoopBug.c
 * (pinned commit 68d03c39d62c2ef9ec663530066bdb66ca5cc4f6, ADR-0012 D4).
 * Upstream foo() printf's `array` after shifting it in place; this slice
 * folds the printed fields into one checksum (acc) instead. `array`'s
 * address is a GPRB value taken once in main() and passed to foo() across
 * 6 separate calls in a loop, the direct discriminating shape for
 * codegen-call-clobbers-gprb-not-declared (fixed by ML-004c). Expected
 * value from host gcc -O0 (acc=135). */
static unsigned acc;
static void foo(unsigned int i, int array[4]) __attribute__((noinline));
static void foo(unsigned int i, int array[4]) {
  unsigned int j;
  for (j=3; j>i; j--)
    array[j] = array[j-1];
  acc = acc*131 + i + (unsigned)array[0] + (unsigned)array[1]*2 + (unsigned)array[2]*3 + (unsigned)array[3]*4;
}
int main(void) {
  int array[4], i;
  for (i=0; i<5; i++) {
    array[0] = 5; array[1] = 6; array[2] = 7; array[3] = 8;
    foo(i, array);
  }
  array[0] = 5; array[1] = 6; array[2] = 7; array[3] = 8;
  foo(0xffffffffu, array);
  return acc & 0xFF;
}
