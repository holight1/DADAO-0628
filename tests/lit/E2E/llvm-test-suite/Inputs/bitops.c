/* Adapted from llvm-test-suite SingleSource/UnitTests/2003-07-08-BitOpsTest.c
 * (pinned commit 68d03c39d62c2ef9ec663530066bdb66ca5cc4f6, ADR-0012 D4).
 * Upstream test() prints its 5 results via printf; this freestanding slice
 * has no libc I/O wired up, so the printf call is replaced with a summed
 * return value asserted via process exit code. The bitwise computation
 * itself (xor/or/and/andnot/ornot over test(7, 8, -5, 5)) is unchanged.
 * Expected value derived by running this adapted file under host gcc -O0. */
static int test(int A, int B, int C, int D) {
  int bxor = A ^ B ^ C ^ D;
  int bor  = A | B | C | D;
  int band = A & B & C & D;
  int bandnot = (A & ~B) ^ (C & ~D);
  int bornot  = (A | ~B) ^ (C | ~D);
  return bxor + bor + band + bandnot + bornot;
}
int main() {
  int r = test(7, 8, -5, 5);
  return r & 0xFF;
}
