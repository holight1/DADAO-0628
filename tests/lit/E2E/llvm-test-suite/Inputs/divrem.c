/* Adapted from llvm-test-suite SingleSource/UnitTests/2006-02-04-DivRem.c
 * (pinned commit 68d03c39d62c2ef9ec663530066bdb66ca5cc4f6, ADR-0012 D4).
 * Upstream test() prints X, Y, X/(8<<(Y&15)), X%(8<<(Y&15)) via printf for
 * each iteration of `for(i=10; i<139045193; i*=-3) { test(i, i^12345); i++; }`;
 * this freestanding slice has no libc I/O wired up, so the printf is replaced
 * with a polynomial accumulator (folding X, Y, quotient and remainder from
 * every iteration into one running value with a multiplicative mix, so no
 * single term's contribution cancels out) asserted via process exit code.
 * The division/modulo-by-runtime-shift computation (`X / (8 << (Y&15))`)
 * and the loop control are unchanged. Originally failed under
 * codegen-global-byte-mask-load-wrong-endian-offset (ML-004a); now passes
 * both backends after DL-068b. Expected value derived by running this
 * adapted file under host gcc -O0. NOTE (ML-004b): a simpler accumulator
 * (`acc += test(...)` with the division done inside a separate `test()`
 * function, called once per loop iteration) was tried first and diverged
 * (host=5, QEMU=gem5=141 -- both backends agree with each other but not
 * with host). That shape is consistent with the `codegen-call-clobbers-
 * gprb-not-declared` issue (docs/issues.yaml): a per-iteration function
 * call with a GPRB-bank address value needed again afterward. The inline
 * form below has no function call in the loop body, sidesteps that issue,
 * and is independently verified triple-matching. */
int i;
int main(void) {
  unsigned acc = 0;
  for (i = 10; i < 139045193; i *= -3) {
    unsigned X = (unsigned)i, Y = (unsigned)(i ^ 12345);
    unsigned q = X / (8 << (Y & 15));
    unsigned r = X % (8 << (Y & 15));
    acc = acc * 131 + X + Y + q + r;
    i++;
  }
  return acc & 0xFF;
}
