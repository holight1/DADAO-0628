#include <stdarg.h>

static int marker;

__attribute__((noinline))
static int fixed_overflow(int a0, int a1, int a2, int a3, int a4, int a5,
                          int a6, int a7, int a8, int a9, int a10, int a11,
                          int a12, int a13, int a14, int a15, int a16, ...) {
  va_list ap;
  va_start(ap, a16);
  void *p = va_arg(ap, void *);
  int v = va_arg(ap, int);
  va_end(ap);
  return a0 == 0 && a16 == 16 && p == &marker && v == 42;
}

__attribute__((noinline))
static int variadic_overflow(int named, ...) {
  va_list ap;
  va_start(ap, named);
  int ok = 1;
  for (int i = 0; i < 17; ++i)
    ok &= va_arg(ap, int) == i;
  va_end(ap);
  return ok;
}

int main(void) {
  int a = fixed_overflow(0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13,
                         14, 15, 16, &marker, 42);
  int b = variadic_overflow(9, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13,
                            14, 15, 16);
  return a && b ? 42 : 1;
}
