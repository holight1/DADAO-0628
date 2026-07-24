/* ML-031a: aggregate (struct) parameter/return-value ABI, non-variadic
 * named-argument paths (contracts/abi/spec.md §2.4):
 *
 *   - HPA (homogeneous pointer aggregate) -> RB bank, one slot per leaf.
 *   - Non-HFA/HPA, <= 32 bytes -> RD bank, 1-4 opaque 8-byte blocks,
 *     including a partial trailing block (Tiny5/Five20, sizes not a
 *     multiple of 8) and the exact 32-byte boundary (Quad32).
 *   - > 32 bytes -> indirect: caller allocates an independent temporary and
 *     passes its address through the RB bank.
 *   - Aggregate return <= 64 bits -> scalar RD31; > 64 bits -> hidden sret.
 *
 * Inputs come from volatile storage so -O2 cannot replace the aggregate
 * transfer with compile-time constants. NEGATIVE_CONTROL changes the final
 * sret expectation after every earlier ABI path has executed, proving the
 * complete test reaches a genuinely discriminative failure.
 */

typedef struct { void *p, *q, *r; } HPA3;     /* 24B, 3 pointer leaves (HPA) */
typedef struct { void *p; } __attribute__((aligned(16))) HPAInner;
typedef struct { HPAInner i; void *q; } PaddedHPA; /* q is at byte offset 16 */
typedef struct { char c, d, e, f, g; } Tiny5; /* 5B,  1 RD block, partial   */
typedef struct { int a, b; } Pair8;           /* 8B,  1 RD block, exact    */
typedef struct { long a, b; } Pair16;         /* 16B, 2 RD blocks, exact   */
typedef struct { int a, b, c, d, e; } Five20; /* 20B, 3 RD blocks, partial */
typedef struct { long a, b, c, d; } Quad32;   /* 32B, 4 RD blocks, boundary*/
typedef struct { long a, b, c, d, e; } Big40; /* 40B, > 32B -> indirect    */

static int gx, gy, gz;
static void *volatile pointer_inputs[] = { &gx, &gy, &gz };
static volatile long input_values[] = {
    10, 20, 30, 40, 50,
    0x11111111, 0x22222222,
    0x1111111122222222LL, 0x3333333344444444LL,
    1, 2, 3, 4, 5, 100,
};

__attribute__((noinline)) static int check_hpa3(HPA3 v) {
  if (v.p != &gx)
    return 11;
  if (v.q != &gy)
    return 12;
  if (v.r != &gz)
    return 13;
  return 42;
}

__attribute__((noinline)) static int check_padded_hpa(PaddedHPA v) {
  if (v.i.p != &gx)
    return 14;
  if (v.q != &gy)
    return 17;
  return 42;
}

__attribute__((noinline)) static int check_tiny5(Tiny5 v) {
  if (v.c != 10 || v.d != 20 || v.e != 30 || v.f != 40 || v.g != 50)
    return 21;
  return 42;
}

__attribute__((noinline)) static int check_pair8(Pair8 v) {
  if (v.a != 0x11111111 || v.b != 0x22222222)
    return 31;
  return 42;
}

__attribute__((noinline)) static int check_pair16(Pair16 v) {
  if (v.a != 0x1111111122222222LL || v.b != 0x3333333344444444LL)
    return 41;
  return 42;
}

__attribute__((noinline)) static int check_five20(Five20 v) {
  if (v.a != 1 || v.b != 2 || v.c != 3 || v.d != 4 || v.e != 5)
    return 51;
  return 42;
}

__attribute__((noinline)) static int check_quad32(Quad32 v) {
  if (v.a != 1 || v.b != 2 || v.c != 3 || v.d != 4)
    return 61;
  return 42;
}

/* orig_addr lets us prove the callee's copy is independent of the caller's
 * storage (wiki: "caller 在栈上分配临时空间") -- if some future regression
 * accidentally passed a live alias instead of a copy, &v would equal it. */
__attribute__((noinline)) static int check_big40(Big40 v, long *orig_addr) {
  if ((long *)&v == orig_addr)
    return 71;
  if (v.a != 100 || v.b != 2 || v.c != 3 || v.d != 4 || v.e != 5)
    return 72;
  return 42;
}

__attribute__((noinline)) static void sink(long *p) {
  if (*p == -1)
    *p = 0;
}

__attribute__((noinline)) static Big40 make_big(long a) {
  Big40 r;
  /* Force an internal pointer-argument call: the callee must still restore
   * the hidden sret address to RB16 before returning. */
  sink(&a);
  r.a = a;
  r.b = 2;
  r.c = 3;
  r.d = 4;
  r.e = 5;
  return r;
}

__attribute__((noinline)) static Tiny5 make_tiny(void) {
  Tiny5 t;
  t.c = (char)input_values[0];
  t.d = (char)input_values[1];
  t.e = (char)input_values[2];
  t.f = (char)input_values[3];
  t.g = (char)input_values[4];
  return t;
}

int main(void) {
  HPA3 h;
  h.p = pointer_inputs[0];
  h.q = pointer_inputs[1];
  h.r = pointer_inputs[2];
  int r;
  if ((r = check_hpa3(h)) != 42)
    return r;

  PaddedHPA ph;
  ph.i.p = pointer_inputs[0];
  ph.q = pointer_inputs[1];
  if ((r = check_padded_hpa(ph)) != 42)
    return r;

  Tiny5 t;
  t.c = 10;
  t.d = 20;
  t.e = 30;
  t.f = 40;
  t.g = 50;
  if ((r = check_tiny5(t)) != 42)
    return r;

  Pair8 p8;
  p8.a = (int)input_values[5];
  p8.b = (int)input_values[6];
  if ((r = check_pair8(p8)) != 42)
    return r;

  Pair16 p16;
  p16.a = input_values[7];
  p16.b = input_values[8];
  if ((r = check_pair16(p16)) != 42)
    return r;

  Five20 f20;
  f20.a = (int)input_values[9];
  f20.b = (int)input_values[10];
  f20.c = (int)input_values[11];
  f20.d = (int)input_values[12];
  f20.e = (int)input_values[13];
  if ((r = check_five20(f20)) != 42)
    return r;

  Quad32 q32;
  q32.a = input_values[9];
  q32.b = input_values[10];
  q32.c = input_values[11];
  q32.d = input_values[12];
  if ((r = check_quad32(q32)) != 42)
    return r;

  Big40 b40 = make_big(input_values[14]);
  if ((r = check_big40(b40, (long *)&b40)) != 42)
    return r;

  Tiny5 rt = make_tiny();
  if (rt.c != 10 || rt.d != 20 || rt.e != 30 || rt.f != 40 || rt.g != 50)
    return 81;

  /* Two independent sret calls must not alias each other's storage. */
  Big40 a1 = make_big(1);
  Big40 a2 = make_big(2);
#ifdef NEGATIVE_CONTROL
  if (a1.a != 1 || a2.a != 3) /* deliberately wrong: a2.a is 2 */
    return 93;
#else
  if (a1.a != 1 || a2.a != 2)
    return 91;
#endif

  return 42;
}
