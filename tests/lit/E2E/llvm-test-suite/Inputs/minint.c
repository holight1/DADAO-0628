/* Adapted from llvm-test-suite SingleSource/UnitTests/2003-05-12-MinIntProblem.c
 * (pinned commit 68d03c39d62c2ef9ec663530066bdb66ca5cc4f6, ADR-0012 D4).
 * Upstream foo() prints "success" via printf when X+1 < 0 holds for
 * X == INT_MIN; this freestanding slice has no libc I/O wired up, so the
 * printf is replaced with a boolean return (1 == condition held, matching
 * upstream's implied pass signal) asserted via process exit code. The
 * INT_MIN + 1 signed-overflow-adjacent arithmetic is unchanged. Expected
 * value derived by running this adapted file under host gcc -O0. */
static int foo(int X) {
  if (X + 1 < 0)
    return 1;
  return 0;
}
int main() {
  return foo(-2147483648);
}
