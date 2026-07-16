/* Adapted from llvm-test-suite SingleSource/UnitTests/2002-10-13-BadLoad.c
 * (pinned commit 68d03c39d62c2ef9ec663530066bdb66ca5cc4f6, ADR-0012 D4).
 * Upstream prints test()'s result via printf; this freestanding slice
 * returns it directly via process exit code. The global load is
 * unchanged. Expected value derived by running this adapted file under
 * host gcc -O0. */
unsigned long window_size = 0x10000;
static unsigned test(void) { return (unsigned)window_size; }
int main() { return test() & 0xFF; }
