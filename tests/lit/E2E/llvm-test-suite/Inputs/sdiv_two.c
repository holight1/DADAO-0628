/* Adapted from llvm-test-suite SingleSource/UnitTests/2005-05-13-SDivTwo.c
 * (pinned commit 68d03c39d62c2ef9ec663530066bdb66ca5cc4f6, ADR-0012 D4).
 * Upstream prints ((signed char)i)/(signed char)2 for i=0..257 via printf;
 * this freestanding slice accumulates the same 258 division results into
 * one running value returned via process exit code. The division
 * expression and loop bound are unchanged. Expected value derived by
 * running this adapted file under host gcc -O0. */
int main() {
  int i;
  int acc = 0;
  for (i = 0; i != 258; ++i)
    acc = acc * 3 + (((signed char)i) / (signed char)2);
  return acc & 0xFF;
}
