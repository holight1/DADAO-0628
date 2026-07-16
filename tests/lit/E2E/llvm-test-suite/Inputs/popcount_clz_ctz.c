/* Adapted from llvm-test-suite SingleSource/UnitTests/2005-05-11-Popcount-ffs-fls.c
 * (pinned commit 68d03c39d62c2ef9ec663530066bdb66ca5cc4f6, ADR-0012 D4).
 * Simplified: the upstream test compares __builtin_clz/popcount/ctz against
 * hand-written reference implementations over an int loop AND a long long
 * loop, plus ffs/ffsl boundary cases, all via printf. This freestanding
 * slice keeps only the `int i` loop (`for(i=10;i<139045193;i*=-3)`) and
 * calls the three builtins through real noinline wrapper functions (forcing
 * an actual CALL per iteration, the codegen-call-clobbers-gprb-not-declared
 * shape fixed by ML-004c) instead of comparing against the reference tables;
 * results are folded into a checksum instead of printed. Expected value
 * from host gcc -O0 (acc=185). */
static int clzf(unsigned x) __attribute__((noinline));
static int clzf(unsigned x){ return __builtin_clz(x); }
static int popf(unsigned x) __attribute__((noinline));
static int popf(unsigned x){ return __builtin_popcount(x); }
static int ctzf(unsigned x) __attribute__((noinline));
static int ctzf(unsigned x){ return __builtin_ctz(x); }
int i;
int main(void){
  unsigned acc=0;
  for(i=10;i<139045193;i*=-3){
    acc = acc*131 + clzf((unsigned)i) + popf((unsigned)i) + ctzf((unsigned)i);
    i++;
  }
  return acc & 0xFF;
}
