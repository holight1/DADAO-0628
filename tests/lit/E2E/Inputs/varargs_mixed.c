#include <stdarg.h>

static int x;
static int y;

__attribute__((noinline))
static int probe(int a, int b, void *c, int d, ...) {
  va_list ap;
  va_start(ap, d);
  int e = va_arg(ap, int);
  void *p = va_arg(ap, void *);
  int f = va_arg(ap, int);
  va_end(ap);
  return a == 1 && b == 2 && c == &x && d == 4 && e == 5 && p == &y &&
                 f == 6
             ? 42
             : 1;
}

int main(void) { return probe(1, 2, &x, 4, 5, &y, 6); }
