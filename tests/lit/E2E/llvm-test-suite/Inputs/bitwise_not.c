/* Adapted from llvm-test-suite SingleSource/UnitTests/2002-05-03-NotTest.c
 * (pinned commit 68d03c39d62c2ef9ec663530066bdb66ca5cc4f6, ADR-0012 D4).
 * Upstream testBitWiseNot()/testBooleanNot() print their results via printf;
 * this freestanding slice folds both into a single accumulated int returned
 * via process exit code. The bitwise-not and boolean-not expressions over
 * (1, 2, -3, 5) are unchanged. Expected value derived by running this
 * adapted file under host gcc -O0. */
static int testBitWiseNot(int A, int B, int C, int D) {
  return ~A + ~B + ~C + ~D;
}
static int testBooleanNot(int A, int B, int C, int D) {
  return !(A > 0 && B > 0) + !(A > 0 && C > 0) + !(A > 0 && D > 0) +
         !(B > 0 && C > 0) + !(B > 0 && D > 0) + !(C > 0 && D > 0);
}
int main() {
  int r = testBitWiseNot(1, 2, -3, 5) + testBooleanNot(1, 2, -3, 5);
  return r & 0xFF;
}
