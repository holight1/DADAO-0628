typedef unsigned long long u64;

static int marker;

__attribute__((noinline))
static int exercise_large_frame(u64 seed, void *pointer) {
  volatile u64 values[800];
  void *volatile pointers[40];

  for (u64 i = 0; i < 800; ++i)
    values[i] = seed ^ (i * 0x10101ULL);

  for (u64 i = 0; i < 40; ++i)
    pointers[i] = (i & 1) ? pointer : (void *)&values[799 - i];

  u64 checksum = 0;
  for (u64 i = 0; i < 800; ++i)
    checksum ^= values[i];

  u64 expected = 0;
  for (u64 i = 0; i < 800; ++i)
    expected ^= seed ^ (i * 0x10101ULL);

#ifdef NEGATIVE_CONTROL
  expected ^= 1;
#endif

  if (checksum != expected)
    return 1;
  if (pointers[1] != pointer || pointers[39] != pointer)
    return 2;
  if (pointers[0] != (void *)&values[799] ||
      pointers[38] != (void *)&values[761])
    return 3;
  return 42;
}

int main(void) {
  return exercise_large_frame(0x123456789abcdef0ULL, &marker);
}
