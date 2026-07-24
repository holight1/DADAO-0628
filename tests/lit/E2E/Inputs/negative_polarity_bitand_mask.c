/* ML-036a: runtime discriminating probe for
   docs/issues.yaml `dadao-o0-negative-polarity-bitand-mask-dropped`.

   At -O0 only, a single-bit AND-and-compare-to-zero test written in
   NEGATIVE polarity (true/if.then branch taken when the masked bits are
   ZERO -- `(x & mask) == 0` or `!(x & mask)`) silently dropped the
   `and rd,rd,mask` masking instruction and branched on the raw unmasked
   byte/word instead. `in = 2` (0b10: bit 0 clear, byte/word non-zero) is
   the discriminating input: a compiler that forgot the mask sees a
   non-zero raw value and takes the WRONG branch, while a correct compiler
   correctly observes bit 0 is clear.

   volatile inputs force a real runtime load (per
   feedback_volatile_needed_for_memory_verification_tests, -O2's
   store-to-load forwarding/constant folding must not be able to prove the
   branch outcome at compile time). NEGATIVE_CONTROL flips the input to
   in=3 (bit 0 SET), which must flip every check's outcome -- this proves
   the checks below are not tautologically true regardless of what the
   compiler does with the mask. */

typedef unsigned int u32;
typedef unsigned long u64;
typedef unsigned char u8;
typedef unsigned short u16;

__attribute__((noinline)) static int negEq0Mask1_i32(u32 l) {
  if ((l & 1) == 0) { return 1; } else { return 0; }
}

__attribute__((noinline)) static int negNotMask1_i64(u64 l) {
  if (!(l & 1)) { return 1; } else { return 0; }
}

__attribute__((noinline)) static int negEq0Mask1_i8(u8 l) {
  if ((l & 1) == 0) { return 1; } else { return 0; }
}

__attribute__((noinline)) static int negEq0Mask1_i16(u16 l) {
  if ((l & 1) == 0) { return 1; } else { return 0; }
}

__attribute__((noinline)) static int negEq0Mask2_i32(u32 l) {
  if ((l & 2) == 0) { return 1; } else { return 0; }
}

/* Positive-polarity sibling of negEq0Mask1_i32 -- this shape already
   worked correctly before the fix and must keep working (regression guard
   against over-correcting the fix onto the wrong polarity). */
__attribute__((noinline)) static int posNe0Mask1_i32(u32 l) {
  if ((l & 1) != 0) { return 0; } else { return 1; }
}

int main(void) {
  /* in32/in64/in8/in16 = 2 (0b10): bit 0 CLEAR, byte/word non-zero -- the
     discriminating input for the mask=1 tests below.
     in32b = 4 (0b100): bit 1 CLEAR, byte/word non-zero -- the discriminating
     input for the mask=2 test (proves the fix is not special-cased to
     bit 0 / mask=1). */
  volatile u32 in32 = 2;
  volatile u64 in64 = 2;
  volatile u8 in8 = 2;
  volatile u16 in16 = 2;
  volatile u32 in32b = 4;

#ifdef NEGATIVE_CONTROL
  in32 = 3;
  in64 = 3;
  in8 = 3;
  in16 = 3;
  in32b = 6;
#endif

  /* Accumulate (not short-circuit) so every check below genuinely runs on
     both the positive and negative-control build -- a short-circuiting
     `if (...) return N;` chain would let the negative control's first
     failing check mask whether the LATER checks are real assertions or
     accidentally tautological. */
  int bad = 0;
  bad |= (negEq0Mask1_i32(in32) != 1);
  bad |= (negNotMask1_i64(in64) != 1);
  bad |= (negEq0Mask1_i8(in8) != 1);
  bad |= (negEq0Mask1_i16(in16) != 1);
  bad |= (negEq0Mask2_i32(in32b) != 1);
  bad |= (posNe0Mask1_i32(in32) != 1);

  if (bad) return 1;
  return 42;
}
