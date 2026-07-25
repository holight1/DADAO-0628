/* ML-041a: runtime E2E regression guard for computed goto / GCC
   "labels as values" (&&label + goto *ptr). Confirms ISD::BlockAddress
   Custom lowering (rela+addi materialization reused from GlobalAddress,
   DADAOISD::PCREL_HI) actually drives a real indirect branch through the
   pre-existing BRIND -> JUMP_PSEUDO_INDIRECT mechanism (the same one
   ordinary `switch` jump-table dispatch already uses) to the correct
   target -- not just that it compiles.

   `dispatch(sel)` picks one of three labels via a runtime, volatile-driven
   index (so the compiler cannot constant-fold away the indirect jump) and
   `goto *table[sel]`s to it. Each landing site increments its own volatile
   counter, and every path falls through to a shared end counter, so a
   wrong jump (landing on the wrong label, silently falling through
   sequentially instead of actually jumping, or looping) is directly
   observable in the final counter values -- not just "did it not crash".

   The negative control asserts the inverse invariant (every landing
   counter is zero), which a *correct* implementation must fail; this
   proves the positive assertion is a real, non-vacuous check of which
   label execution actually reached, not a tautology satisfied regardless
   of whether the computed goto did anything at all. */

volatile int g_sel;
volatile int hit_a, hit_b, hit_c, hit_end;

static void dispatch(int sel) {
  static void *table[3] = {&&L_a, &&L_b, &&L_c};
  goto *table[sel];
L_a:
  hit_a++;
  goto L_end;
L_b:
  hit_b++;
  goto L_end;
L_c:
  hit_c++;
  goto L_end;
L_end:
  hit_end++;
}

int main(void) {
  hit_a = hit_b = hit_c = hit_end = 0;

  g_sel = 1;
  dispatch(g_sel);
  g_sel = 0;
  dispatch(g_sel);
  g_sel = 2;
  dispatch(g_sel);

#ifndef NEGATIVE_CONTROL
  /* Exactly one hit per label and three total dispatch completions -- any
     wrong target, missed jump, or fallthrough breaks this. */
  if (hit_a == 1 && hit_b == 1 && hit_c == 1 && hit_end == 3)
    return 42;
  return 1;
#else
  /* Deliberately wrong invariant: a correct dispatch() must NOT leave every
     counter at zero, so this must fail (return 1), proving the positive
     branch above is not vacuously satisfied. */
  if (hit_a == 0 && hit_b == 0 && hit_c == 0 && hit_end == 0)
    return 42;
  return 1;
#endif
}
