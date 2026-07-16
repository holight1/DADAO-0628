/* Adapted from llvm-test-suite SingleSource/UnitTests/2003-05-31-LongShifts.c
 * (pinned commit 68d03c39d62c2ef9ec663530066bdb66ca5cc4f6, ADR-0012 D4).
 * Upstream Test() printf's ashr/lshr/shl of `Vals[]` (8 fixed long long/int
 * pairs, `volatile struct`); this slice drops `volatile` (no I/O side effect
 * to preserve ordering for) and folds the three shift results into one
 * running checksum (acc) instead of printing, keeping Test() a real
 * noinline call per array element (codegen-call-clobbers-gprb-not-declared
 * shape, fixed by ML-004c). Expected value from host gcc -O0 (acc=208). */
struct P{ long long A; int V; };
static long long acc;
static void Test(long long Val, int Amt) __attribute__((noinline));
static void Test(long long Val, int Amt){
  acc = acc*131 + (Val>>Amt) + (long long)((unsigned long long)Val>>Amt) + (Val<<Amt);
}
static struct P Vals[] = {
  {123,4},{123,34},{-4,4},{-5,34},
  {-6000000000LL,4},{-6000000000LL,34},{6000000000LL,4},{6000000000LL,34}
};
int main(void){
  for(int i=0;i<8;i++) Test(Vals[i].A, Vals[i].V);
  return (int)(acc & 0xFF);
}
