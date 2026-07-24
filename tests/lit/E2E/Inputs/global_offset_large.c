// ML-030a: a compile-time constant added to a global address must never be
// folded straight into the RELA_RIII/ADDI_RBRRII imms18 operand pair (range
// [-131072,131071], contracts/isa/spec.md §2.2) when the constant itself is
// too large for that field. Each case below has the exact "array indexed by
// (runtime value +/- large literal constant)" shape that let the DAG-level
// GlobalAddress+Constant fold bake an out-of-range symbol expression
// directly into the relocation (gcc-c-torture 960321-1.c/pr79286.c). The
// runtime index always lands back in-bounds; only the *compile-time*
// literal is large. Magnitudes cover: just past the 18-bit boundary,
// ~2^31 (the original torture-case magnitude), and ~2^42 (spans more than
// two 16-bit wydes of DADAOInstrInfo::materializeImm64). Both signs
// (subtraction and addition of the literal) are covered.

typedef long long s64;

char a[10] = "deadbeef"; // 'd','e','a','d','b','e','e','f',0,0

__attribute__((noinline)) char sub_boundary(long i) { return a[i - 200000LL]; }
__attribute__((noinline)) char add_boundary(long i) { return a[i + 200000LL]; }
__attribute__((noinline)) char sub_giga(long i) { return a[i - 2000000000LL]; }
__attribute__((noinline)) char add_giga(long i) { return a[i + 2000000000LL]; }
__attribute__((noinline)) char sub_tera(long i) { return a[i - 4000000000000LL]; }
__attribute__((noinline)) char add_tera(long i) { return a[i + 4000000000000LL]; }

#ifdef NEGATIVE_CONTROL
// Deliberately corrupt one expected value so the harness proves this test
// can actually detect a wrong answer instead of trivially returning 42.
#define EXPECT_GIGA 'X'
#else
#define EXPECT_GIGA 'e'
#endif

int main(void) {
  if (sub_boundary(200003L) != 'd')
    return 1; // i-200000 = 3 -> a[3] = 'd'
  if (add_boundary(-199997L) != 'd')
    return 2; // i+200000 = 3 -> a[3] = 'd'
  if (sub_giga(2000000005LL) != EXPECT_GIGA)
    return 3; // i-2e9 = 5 -> a[5] = 'e'
  if (add_giga(-1999999995LL) != 'e')
    return 4; // i+2e9 = 5 -> a[5] = 'e'
  if (sub_tera(4000000000007LL) != 'f')
    return 5; // i-4e12 = 7 -> a[7] = 'f'
  if (add_tera(-3999999999993LL) != 'f')
    return 6; // i+4e12 = 7 -> a[7] = 'f'
  return 42;
}
