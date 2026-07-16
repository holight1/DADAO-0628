/* Adapted from llvm-test-suite SingleSource/UnitTests/2002-12-13-MishaTest.c
 * (pinned commit 68d03c39d62c2ef9ec663530066bdb66ca5cc4f6, ADR-0012 D4).
 * Upstream prints "Sum is %d\n" via printf; this freestanding slice returns
 * Sum directly as the process exit code instead (no console I/O wired up
 * here), matching the reference output's value ("Sum is 1" -> exit 1).
 * The old K&R-style implicit-int/untyped-parameter `sum()` definition is
 * rewritten with explicit ANSI prototypes/types (this project's clang does
 * not support K&R declarations); the pointer-walk/accumulation logic is
 * otherwise unchanged from upstream.
 *
 * Originally reported as codegen-misha-sum-wrong-value-no-call
 * (ML-004b, host=1/dadao=2) — a claimed independent CodeGen bug distinct
 * from codegen-call-clobbers-gprb-not-declared because the hot loop inside
 * sum() itself makes no function calls. Re-verified by ML-004d against the
 * post-ML-004c toolchain: now passes both backends, matching host exactly
 * (confirmed with two independent inputs: NUM=2 -> 1, NUM=5 with a
 * different fill pattern -> 35). Root cause was evidently the *overall*
 * reproducer's call from main() to sum() with a GPRB (pointer) argument
 * used again after the call returns — the exact shape ML-004c's CALL
 * RegMask fix addresses — even though the specific *loop* doing the wrong
 * arithmetic has no call in it; the original triage's "no call in the hot
 * loop" observation was accurate but did not rule out a caller-side
 * clobber of the pointer argument itself. Issue closed by ML-004d,
 * resolved_by ML-004c (incidental fix, confirmed not a new bug). */
static int sum(short *to, short *from, short count)
{
  int i;
  for (i = 0; i != count; ++i)
    *to += *from++;
  return 0;
}

#define NUM 2
int main(void)
{
  short Array[NUM];
  short Sum = 0;
  int i;

  for (i = 0; i != NUM; ++i)
    Array[i] = i;

  sum(&Sum, Array, NUM);

  return Sum;
}
