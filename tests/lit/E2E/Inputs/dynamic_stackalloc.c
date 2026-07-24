typedef unsigned long u64;
typedef unsigned char u8;

volatile u64 small_size = 13;
volatile u64 large_size = 5003;
volatile u64 call_seed = 3;

#define PARAMS10(P)                                                            \
  u64 P##0, u64 P##1, u64 P##2, u64 P##3, u64 P##4, u64 P##5, u64 P##6,     \
      u64 P##7, u64 P##8, u64 P##9
#define ARGS10(X) X, X, X, X, X, X, X, X, X, X

// Sixteen arguments use RD16-RD31; the remaining 284 occupy a 2272-byte
// outgoing area.  Reading both sides of the register/stack boundary and the
// final two stack slots makes a low-address or truncated-offset store visible.
__attribute__((noinline))
u64 verify_large_outgoing(
    PARAMS10(a), PARAMS10(b), PARAMS10(c), PARAMS10(d), PARAMS10(e),
    PARAMS10(f), PARAMS10(g), PARAMS10(h), PARAMS10(i), PARAMS10(j),
    PARAMS10(k), PARAMS10(l), PARAMS10(m), PARAMS10(n), PARAMS10(o),
    PARAMS10(p), PARAMS10(q), PARAMS10(r), PARAMS10(s), PARAMS10(t),
    PARAMS10(u), PARAMS10(v), PARAMS10(w), PARAMS10(x), PARAMS10(y),
    PARAMS10(z), PARAMS10(aa), PARAMS10(ab), PARAMS10(ac), PARAMS10(ad)) {
  return a0 + a9 + b5 + b6 + ad8 + ad9;
}

__attribute__((noinline))
static u64 verify_after_call(volatile u8 *p, u64 n, u64 a0, u64 a1, u64 a2,
                             u64 a3, u64 a4, u64 a5, u64 a6, u64 a7, u64 a8,
                             u64 a9, u64 a10, u64 a11, u64 a12, u64 a13,
                             u64 a14, u64 a15, u64 a16) {
  return p[0] + p[n - 1] + a0 + a1 + a2 + a3 + a4 + a5 + a6 + a7 + a8 +
         a9 + a10 + a11 + a12 + a13 + a14 + a15 + a16;
}

int main(void) {
  volatile u64 fixed = 0x12345678UL;
  u64 n = small_size;
  u64 first_address;

  if ((n & 7) == 0)
    return 2;

  {
    volatile u8 first[n];
    first[0] = 11;
    first[n - 1] = 19;
    if (((u64)&first[0] & 7) != 0)
      return 3;

    {
      volatile u8 nested[n + 5];
      nested[0] = 31;
      nested[n + 4] = 47;
      if (nested[0] != 31 || nested[n + 4] != 47)
        return 4;
      if (first[0] != 11 || first[n - 1] != 19)
        return 5;
    }

    if (verify_after_call(first, n, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11,
                          12, 13, 14, 15, 16, 17) != 183)
      return 6;
    if (first[0] != 11 || first[n - 1] != 19)
      return 7;
  }

  {
    volatile u8 sequential[n + 3];
    sequential[0] = 53;
    sequential[n + 2] = 59;
    first_address = (u64)&sequential[0];
    if (sequential[0] != 53 || sequential[n + 2] != 59)
      return 8;
  }

  {
    volatile u8 restored[n + 3];
    restored[0] = 61;
    restored[n + 2] = 67;
    if ((u64)&restored[0] != first_address)
      return 9;
    if (restored[0] != 61 || restored[n + 2] != 67)
      return 10;
  }

  {
    u64 big = large_size;
    u64 seed = call_seed;
    volatile u8 large[big] __attribute__((aligned(16)));
    large[0] = 71;
    large[big / 2] = 73;
    large[big - 1] = 79;
    u64 call_result = verify_large_outgoing(
        ARGS10(seed + 0), ARGS10(seed + 1), ARGS10(seed + 2),
        ARGS10(seed + 3), ARGS10(seed + 4), ARGS10(seed + 5),
        ARGS10(seed + 6), ARGS10(seed + 7), ARGS10(seed + 8),
        ARGS10(seed + 9), ARGS10(seed + 10), ARGS10(seed + 11),
        ARGS10(seed + 12), ARGS10(seed + 13), ARGS10(seed + 14),
        ARGS10(seed + 15), ARGS10(seed + 16), ARGS10(seed + 17),
        ARGS10(seed + 18), ARGS10(seed + 19), ARGS10(seed + 20),
        ARGS10(seed + 21), ARGS10(seed + 22), ARGS10(seed + 23),
        ARGS10(seed + 24), ARGS10(seed + 25), ARGS10(seed + 26),
        ARGS10(seed + 27), ARGS10(seed + 28), ARGS10(seed + 29));
    if (((u64)&large[0] & 15) != 0)
      return 11;
    if (large[0] != 71 || large[big / 2] != 73 || large[big - 1] != 79)
      return 12;
#ifdef NEGATIVE_CONTROL
    if (call_result != 77)
      return 1;
#else
    if (call_result != 78)
      return 13;
#endif
  }

  if (fixed != 0x12345678UL)
    return 14;
  return 42;
}
