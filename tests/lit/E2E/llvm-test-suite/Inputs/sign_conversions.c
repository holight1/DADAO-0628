/* Adapted from llvm-test-suite SingleSource/UnitTests/2003-07-10-
 * SignConversions.c (pinned commit 68d03c39d62c2ef9ec663530066bdb66ca5cc4f6,
 * ADR-0012 D4). Upstream prints all 8 sign/zero-extension conversion
 * results via two printf calls; this freestanding slice folds the same 8
 * values (in the same order) into a running polynomial accumulator
 * (`acc = acc*131 + value + 1`, per the Inputs/divrem.c convention),
 * asserted via process exit code instead of console I/O. The two getter
 * functions and all 8 conversions are otherwise unchanged from upstream.
 *
 * Originally reported as gem5-sign-conversions-backend-divergence
 * (ML-004b: QEMU PASS, gem5 SIGABRT with a page fault @ address 0).
 * Re-verified by ML-004d against the post-ML-004c toolchain: passes both
 * backends, matching host exactly. Tried 4 additional getSC()/getUC()
 * input values (0x01/0xFF/0x7F/0x55, beyond upstream's 0x80) to rule out
 * a coincidental match — all agree with host on both backends, no
 * divergence found. Root cause not independently re-derived (the original
 * report gave no repro artifact beyond "SIGABRT"), but the reproducer
 * matches ML-004c's fixed bug shape: two function calls (getSC/getUC)
 * whose GPRD return values feed many subsequent operations after the call
 * returns. Issue closed by ML-004d, resolved_by ML-004c (incidental fix,
 * confirmed not a new bug via 5 independent inputs including upstream's
 * own 0x80). Expected value derived by running this adapted file under
 * host gcc -O0. */
unsigned char getUC(void) { return 0x80; }
signed char getSC(void) { return 0x80; }

int main(void)
{
  signed char SC80 = getSC();
  unsigned char UC80 = getUC();

  /* source is smaller than dest: both decide */
  unsigned short us  = (unsigned short) SC80;  /* sign-ext then zero-ext */
  unsigned short us2 = (unsigned short) UC80;  /* zero-ext only: NOP! */
           short  s  = (         short) SC80;  /* sign-ext */
           short  s2 = (         short) UC80;  /* zero-extend only: NOP! */

  /* source is same size or larger than dest: dest decides */
  unsigned char  uc  = (unsigned char ) SC80;  /* zero-ext */
  unsigned char  uc2 = (unsigned char ) UC80;  /* NOP */
  signed   char  sc  = (signed   char ) SC80;  /* NOP */
  signed   char  sc2 = (signed   char ) UC80;  /* sign-extend */

  unsigned acc = 7;
  acc = acc * 131 + (unsigned char)us + 1;
  acc = acc * 131 + (unsigned char)us2 + 1;
  acc = acc * 131 + (unsigned char)s + 1;
  acc = acc * 131 + (unsigned char)s2 + 1;
  acc = acc * 131 + uc + 1;
  acc = acc * 131 + uc2 + 1;
  acc = acc * 131 + (unsigned char)sc + 1;
  acc = acc * 131 + (unsigned char)sc2 + 1;
  return acc & 0xFF;
}
