/* Adapted from llvm-test-suite SingleSource/UnitTests/2003-05-31-CastToBool.c
 * (pinned commit 68d03c39d62c2ef9ec663530066bdb66ca5cc4f6, ADR-0012 D4).
 * Upstream prints each _Bool cast result via printf; this freestanding
 * slice accumulates the same _Bool conversions (byte/short/int/long long
 * != 0, plus the boolean-op test) into one running value returned via
 * process exit code. The cast/comparison expressions are unchanged.
 * Expected value derived by running this adapted file under host gcc -O0. */
static int acc;
static void testCastOps(int y) {
  acc = acc * 3 + (((_Bool)(y == 2)) || ((_Bool)(y == 0)));
  acc = acc * 3 + (((_Bool)(y < 2)) && ((_Bool)(y > -10)));
  acc = acc * 3 + ((_Bool)(y ^ 2 ^ ~5));
}
static void testBool(_Bool X) { acc = acc * 3 + X; }
static void testByte(char X) { acc = acc * 3 + X; testBool(X != 0); }
static void testShort(short X) { acc = acc * 3 + X; testBool(X != 0); }
static void testInt(int X) { acc = acc * 3 + X; testBool(X != 0); }
static void testLong(long long X) { acc = acc * 3 + (int)X; testBool(X != 0); }
int main() {
  testByte(0);
  testByte(123);
  testShort(0);
  testShort(1234);
  testInt(0);
  testInt(1234);
  testLong(0);
  testLong(123121231231231LL);
  testLong(0x1112300000000000LL);
  testLong(0x11120LL);
  testCastOps(2);
  return acc & 0xFF;
}
