/* Adapted from llvm-test-suite SingleSource/UnitTests/2002-05-19-DivTest.c
 * (pinned commit 68d03c39d62c2ef9ec663530066bdb66ca5cc4f6, ADR-0012 D4).
 * Upstream test()/testL() printf div-by-power-of-2 results for 4 fixed
 * inputs; this slice folds them into one checksum (acc) instead, keeping
 * test()/testL() as real noinline calls (codegen-call-clobbers-gprb-not-
 * declared shape, fixed by ML-004c — this was the one of the original 4
 * that failed with a wrong *value* rather than MALIGN). Expected value
 * from host gcc -O0 (acc=131). int64_t swapped for `long long` (see
 * crc8_le.c header re: cross stdint.h). */
static unsigned acc;
static void test(int Arg) __attribute__((noinline));
static void test(int Arg){
  acc = acc*131 + (unsigned)(Arg/(1<<0)) + (unsigned)(Arg/(1<<4)) + (unsigned)(Arg/(1<<18)) + (unsigned)(Arg/(1<<30));
}
static void testL(long long Arg) __attribute__((noinline));
static void testL(long long Arg){
  acc = acc*131 + (unsigned)(int)(Arg/((long long)1<<4)) + (unsigned)(int)(Arg/((long long)1<<46));
}
int main(void){
  int B20 = -(1<<20);
  long long B53 = -((long long)1<<53);
  test(B20+32);
  test(B20+33);
  testL(B53+64);
  testL(B53+65);
  return acc & 0xFF;
}
