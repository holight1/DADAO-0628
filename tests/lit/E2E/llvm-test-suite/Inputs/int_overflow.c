/* Adapted from llvm-test-suite SingleSource/UnitTests/2003-07-06-IntOverflow.c
 * (pinned commit 68d03c39d62c2ef9ec663530066bdb66ca5cc4f6, ADR-0012 D4).
 * Upstream compareOvf/divideOvf/divideNeg/subtractOvf printf their results;
 * this slice folds them into one checksum (acc) instead of printing, each
 * still a real noinline call taking int args computed just before the call
 * (codegen-call-clobbers-gprb-not-declared shape, fixed by ML-004c).
 * Expected value from host gcc -O0 (acc=108). */
static unsigned acc;
static void compareOvf(int x,int y) __attribute__((noinline));
static void compareOvf(int x,int y){
  int sum=x*x+y*y;
  acc = acc*131 + (unsigned)(sum < (1<<22) ? 1 : 0);
}
static void divideOvf(int x,int y) __attribute__((noinline));
static void divideOvf(int x,int y){
  int sum=x*x+y*y;
  int rem=(1<<31)/sum;
  acc = acc*131 + (unsigned)rem;
}
static void divideNeg(int x,int y) __attribute__((noinline));
static void divideNeg(int x,int y){
  int sum=x*x-y*y;
  int rem=sum/(1<<18);
  acc = acc*131 + (unsigned)rem;
}
static void subtractOvf(int x,int y) __attribute__((noinline));
static void subtractOvf(int x,int y){
  int sum=x*x+y*y;
  int rem=(1u<<31)-sum;
  acc = acc*131 + (unsigned)rem;
}
int main(void){
  int b21=1<<21;
  compareOvf(b21,b21);
  divideOvf(b21+1,b21+2);
  divideNeg(b21+1,b21+2);
  subtractOvf(b21+1,b21+2);
  return acc & 0xFF;
}
