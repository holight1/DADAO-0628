/* Adapted from llvm-test-suite SingleSource/UnitTests/2003-05-26-Shorts.c
 * (pinned commit 68d03c39d62c2ef9ec663530066bdb66ca5cc4f6, ADR-0012 D4).
 * Upstream prints a dozen masking/sign-extension results (across
 * int/short/char, signed/unsigned) via printf; this freestanding slice
 * accumulates the same values into one running total returned via process
 * exit code. getL()'s "move the value here to prevent constant folding"
 * trick and all the narrow-type arithmetic are unchanged. Expected value
 * derived by running this adapted file under host gcc -O0. */
static unsigned long long getL() { return 0xafafafafc5c5b8a3ull; }
int main(void) {
  unsigned long long UL = getL();
  long long L = (long long)UL;

  unsigned int ui = (unsigned int)UL;
  int i = (int)UL;
  unsigned short us = (unsigned short)UL;
  short s = (short)UL;
  unsigned char ub = (unsigned char)UL;
  signed char b = (signed char)UL;

  long long acc = 0;
  acc = acc * 131 + (int)(UL - ui);
  acc = acc * 131 + (int)(UL / ui);
  acc = acc * 131 + (int)(L - i);
  acc = acc * 131 + (int)(L / i);
  acc = acc * 131 + (int)(UL - us);
  acc = acc * 131 + (int)(UL / us);
  acc = acc * 131 + (int)(L - s);
  acc = acc * 131 + (int)(L / s);
  acc = acc * 131 + (int)(UL - ub);
  acc = acc * 131 + (int)(UL / ub);
  acc = acc * 131 + (int)(L - b);
  acc = acc * 131 + (int)(L / b);

  unsigned int uiprod = (ui + 1u) * (ui + 1u) - (unsigned int)(ui << 2) - 1u;
  unsigned short usprod =
      (unsigned short)((us + 1u) * (us + 1u) - (unsigned short)(us << 2) - 1u);
  unsigned char ubprod =
      (unsigned char)((ub + 1u) * (ub + 1u) - (unsigned char)(ub << 2) - 1u);
  int iprod = (i + 1) * (i + 1) - (int)(i << 2) - 1;
  short sprod = (short)((s + 1) * (s + 1) - (short)(s << 2) - 1);
  signed char bprod = (signed char)((b + 1) * (b + 1) - (char)(b << 2) - 1);

  unsigned int uidiv = (unsigned int)(UL / ui) * (unsigned int)(UL / ui);
  unsigned short usdiv =
      (unsigned short)(UL / us) * (unsigned short)(UL / us);
  unsigned char ubdiv = (unsigned char)(UL / ub) * (unsigned char)(UL / ub);
  int idiv = (int)(L / i) * (int)(L / i);
  short sdiv = (short)((short)(L / s) * (short)(L / s));
  signed char bdiv = (signed char)((signed char)(L / b) * (signed char)(L / b));

  acc = acc * 131 + uiprod + uidiv + usprod + usdiv + ubprod + ubdiv + iprod +
        idiv + sprod + sdiv + bprod + bdiv;
  return (int)acc & 0xFF;
}
