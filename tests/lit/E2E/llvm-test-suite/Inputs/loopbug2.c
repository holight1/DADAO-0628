/* Adapted from llvm-test-suite SingleSource/UnitTests/2008-04-20-LoopBug2.c
 * (pinned commit 68d03c39d62c2ef9ec663530066bdb66ca5cc4f6, ADR-0012 D4).
 * Same as Inputs/loopbug.c but with foo()'s inner loop rewritten as
 * do/while (the actual upstream difference between LoopBug.c/LoopBug2.c).
 * Expected value from host gcc -O0 (acc=83). */
static unsigned acc;
static void foo(unsigned int i, int array[4]) __attribute__((noinline));
static void foo(unsigned int i, int array[4]) {
  unsigned int j=3;
  do {
    array[j] = array[j-1];
    j--;
  }  while (j>i);
  acc = acc*131 + i + (unsigned)array[0] + (unsigned)array[1]*2 + (unsigned)array[2]*3 + (unsigned)array[3]*4;
}
int main(void) {
  int array[4], i;
  for (i=0; i<5; i++) {
    array[0] = 5; array[1] = 6; array[2] = 7; array[3] = 8;
    foo(i, array);
  }
  array[0] = 5; array[1] = 6; array[2] = 7; array[3] = 8;
  foo(0xffffffffU, array);
  return acc & 0xFF;
}
