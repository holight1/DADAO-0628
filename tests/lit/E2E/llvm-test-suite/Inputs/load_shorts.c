/* Adapted from llvm-test-suite SingleSource/UnitTests/2003-07-09-LoadShorts.c
 * (pinned commit 68d03c39d62c2ef9ec663530066bdb66ca5cc4f6, ADR-0012 D4).
 * Upstream malloc()s a struct with narrow-typed fields (stresses load/store
 * masking and sign-extension through struct field access rather than bare
 * locals, see 2003-05-26-Shorts.c); this freestanding slice replaces the
 * malloc with a plain stack-allocated struct (no libc allocator wired up
 * here) and accumulates the printf'd results into one running value
 * returned via process exit code. The field types and arithmetic are
 * unchanged. Expected value derived by running this adapted file under
 * host gcc -O0. */
typedef struct ShortsSet_struct {
  unsigned int ui;
  int i;
  unsigned short us;
  short s;
  unsigned char ub;
  signed char b;
} ShortsSet;

static unsigned long long getL() { return 0xafafafafc5c5b8a3ull; }

int main(void) {
  unsigned long long UL = getL();
  long long L = (long long)UL;

  ShortsSet Sbuf;
  ShortsSet *S = &Sbuf;
  S->ui = (unsigned int)UL;
  S->i = (int)UL;
  S->us = (unsigned short)UL;
  S->s = (short)UL;
  S->ub = (unsigned char)UL;
  S->b = (signed char)UL;

  long long acc = 0;
  acc = acc * 131 + (int)(UL - S->ui);
  acc = acc * 131 + (int)(UL / S->ui);
  acc = acc * 131 + (int)(L - S->i);
  acc = acc * 131 + (int)(L / S->i);
  acc = acc * 131 + (int)(UL - S->us);
  acc = acc * 131 + (int)(UL / S->us);
  acc = acc * 131 + (int)(L - S->s);
  acc = acc * 131 + (int)(L / S->s);
  acc = acc * 131 + (int)(UL - S->ub);
  acc = acc * 131 + (int)(UL / S->ub);
  acc = acc * 131 + (int)(L - S->b);
  acc = acc * 131 + (int)(L / S->b);
  return (int)acc & 0xFF;
}
