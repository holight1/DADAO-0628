/* Adapted from llvm-test-suite SingleSource/UnitTests/2003-08-20-FoldBug.c
 * (pinned commit 68d03c39d62c2ef9ec663530066bdb66ca5cc4f6, ADR-0012 D4).
 * Upstream calls abort() on failure and prints "All ok" via printf on
 * success; this freestanding slice returns 1/0 via process exit code
 * instead of calling abort()/printf. The masking expression under test
 * (x & 0x80ffffff compared against a sign-extended 32-bit constant) is
 * unchanged. Expected value derived by running this adapted file under
 * host gcc -O0. */
static int foo(int x) {
  if ((int)(x & 0x80ffffff) != (int)(0x8000fffe))
    return 0;
  return 1;
}
int main() { return foo(0x8000fffe); }
