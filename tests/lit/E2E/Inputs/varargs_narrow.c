#include <stdarg.h>

__attribute__((noinline))
static int probe(int named, ...) {
  va_list ap;
  va_start(ap, named);
  int first = va_arg(ap, int);
  int second = va_arg(ap, int);
  va_end(ap);
  return named == 7 && first == 0x11223344 && second == -2 ? 42 : 1;
}

int main(void) { return probe(7, 0x11223344, -2); }
