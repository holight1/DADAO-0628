/* ML-038a: end-to-end `__int128` return value + call-result consumption.
 *
 * make_u128() exercises DADAOTargetLowering::LowerReturn's two-register
 * (rd31=high/rd30=low) split; main()'s call to it exercises LowerCall's
 * AnalyzeCallResult path (CallingConvLower.cpp:174 UNREACHABLE before this
 * fix) reading the result back out of the same two registers. Inputs come
 * from volatile globals so the compiler cannot constant-fold the whole
 * computation away at -O2 and must genuinely materialize + transfer both
 * 64-bit halves at runtime (see feedback_volatile_needed_for_memory_
 * verification_tests.md).
 */

typedef unsigned __int128 u128;
typedef __int128 s128;

static volatile unsigned long long g_hi = 0x0123456789abcdefULL;
static volatile unsigned long long g_lo = 0xfedcba9876543210ULL;
static volatile long long g_neg = -305419896LL; /* -0x12345678 */

__attribute__((noinline)) u128 make_u128(void) {
  u128 hi = g_hi;
  u128 lo = g_lo;
  return (hi << 64) | lo;
}

/* Sign-extends a genuinely negative 64-bit runtime value into 128 bits --
 * the high half must come out all-ones, not zero, proving the return path
 * carries real sign information and isn't just moving raw bit patterns
 * that happen to look right for the unsigned case above. */
__attribute__((noinline)) s128 make_s128_negative(void) {
  s128 v = g_neg;
  return v;
}

int main(void) {
  u128 v = make_u128();
  unsigned long long hi = (unsigned long long)(v >> 64);
  unsigned long long lo = (unsigned long long)v;

#ifdef NEGATIVE_CONTROL
  /* Deliberately wrong expectation: proves the positive-control check
   * above is not vacuously true (e.g. from a return path that always
   * yields 0 or silently truncates to 64 bits). */
  if (hi != g_hi + 1)
    return 1;
#else
  if (hi != g_hi)
    return 1;
  if (lo != g_lo)
    return 2;
#endif

  s128 n = make_s128_negative();
  if (n >= 0)
    return 3;
  if ((long long)(n >> 64) != -1)
    return 4;
  if ((long long)n != g_neg)
    return 5;

  return 42;
}
