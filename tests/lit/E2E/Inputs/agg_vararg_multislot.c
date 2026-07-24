/* ML-031a: variadic aggregate parameters spanning multiple 8-byte save-area
 * slots (wiki §可变参数 "大于 8 字节的聚合变参"): a 16-byte struct (exact
 * multiple of 8, 2 slots) and a 12-byte struct (rounds up to 2 slots,
 * exercising the same partial-trailing-block padding direction as the
 * named-argument RD-split path in agg_args_named.c) each followed by a
 * plain int vararg, proving the save-area slot accounting advances by the
 * right amount so the trailing scalar reads land on the correct slot.
 */
#include <stdarg.h>

typedef struct { long a, b; } Pair16;
typedef struct { int a, b, c; } Triple12;
typedef struct { long a, b, c, d, e; } Big40;
static volatile long input_values[] = {
    0x1111111122222222LL, 0x3333333344444444LL,
    777, 1, 2, 3, 888,
    10, 20, 30, 40, 50, 999,
};

__attribute__((noinline)) static int probe(int n, ...) {
  va_list ap;
  va_start(ap, n);

  Pair16 p = va_arg(ap, Pair16);
  int tail1 = va_arg(ap, int);

  Triple12 t = va_arg(ap, Triple12);
  int tail2 = va_arg(ap, int);

  Big40 b = va_arg(ap, Big40);
  int tail3 = va_arg(ap, int);

  va_end(ap);

  if (p.a != 0x1111111122222222LL || p.b != 0x3333333344444444LL)
    return 1;
  if (tail1 != 777)
    return 2;
  if (t.a != 1 || t.b != 2 || t.c != 3)
    return 3;
  if (b.a != 10 || b.b != 20 || b.c != 30 || b.d != 40 || b.e != 50)
    return 5;
  if (tail3 != 999)
    return 6;
#ifdef NEGATIVE_CONTROL
  if (tail2 != 889) /* deliberately wrong: the transferred value is 888 */
    return 9;
#else
  if (tail2 != 888)
    return 4;
#endif
  return 42;
}

int main(void) {
  Pair16 p;
  p.a = input_values[0];
  p.b = input_values[1];
  Triple12 t;
  t.a = (int)input_values[3];
  t.b = (int)input_values[4];
  t.c = (int)input_values[5];
  Big40 b;
  b.a = input_values[7];
  b.b = input_values[8];
  b.c = input_values[9];
  b.d = input_values[10];
  b.e = input_values[11];
  return probe(6, p, (int)input_values[2], t, (int)input_values[6],
               b, (int)input_values[12]);
}
