/* Adapted from llvm-test-suite SingleSource/UnitTests/2006-12-07-Compare64BitConstant.c
 * (pinned commit 68d03c39d62c2ef9ec663530066bdb66ca5cc4f6, ADR-0012 D4).
 * Upstream prints "Works."/"Doesn't." via printf; this freestanding slice
 * returns 1/0 via process exit code instead. The large-constant comparison
 * is unchanged. Expected value derived by running this adapted file under
 * host gcc -O0. */
long long Large = 5LL << 48;
int main(void) {
  if (((Large >> 48) & 7LL) == 5LL)
    return 1;
  return 0;
}
