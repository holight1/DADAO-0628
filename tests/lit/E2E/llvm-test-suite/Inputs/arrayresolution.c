/* Adapted from llvm-test-suite SingleSource/UnitTests/2002-10-09-ArrayResolution.c
 * (pinned commit 68d03c39d62c2ef9ec663530066bdb66ca5cc4f6, ADR-0012 D4).
 * Upstream main() prints Foo via printf after filling Array[]; this
 * freestanding slice has no libc I/O wired up, so the printf is replaced
 * with a direct return of Foo asserted via process exit code. The
 * tentative-then-sized array redeclaration (`int Array[]; int Array[NUM];`)
 * and the loop writing Array[i] are unchanged -- the test's actual point is
 * that writing Array[] must not clobber the adjacent global Foo. Expected
 * value (0, i.e. Foo stays untouched) derived by running this adapted file
 * under host gcc -O0. */
#define NUM 32
int Array[];
int Array[NUM];
int Foo;
int main() {
  unsigned i;
  for (i = 0; i != NUM; ++i)
    Array[i] = 5;
  return Foo & 0xFF;
}
