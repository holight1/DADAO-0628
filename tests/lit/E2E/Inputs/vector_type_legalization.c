/* ML-040a: runtime E2E regression guard for DADAO's vector type
   legalization fix (DADAOTargetLowering::getSetCCResultType override,
   .work/llvm/llvm/lib/Target/DADAO/DADAOISelLowering.cpp). Before this fix,
   clang crashed with

     TargetLoweringBase.cpp:1905: getSetCCResultType(...): Assertion
     `!VT.isVector() && "No default SetCC type for vectors!"' failed.

   compiling any gcc-c-torture file using clang/GCC's `vector_size`
   attribute together with an operator (division/remainder in particular)
   that target-independent DAG combining expands via an internal SETCC-based
   sequence while the operand is still a vector type. DADAO has no vector
   register class (it is a pure scalar RD/RB/RF-bank architecture) -- the
   fix does not add any "vector hardware" concept, it only tells the
   *already-automatic* split/scalarize type-legalization path (which needs
   no DADAO-specific opt-in beyond this) what integer type each per-lane
   boolean should use.

   The three vector shapes/values below are taken directly from the
   gcc-c-torture files this fix makes PASS for real (compile + link + run
   under both QEMU and gem5, not just "compiles without crashing"):
     - v2si: pr23135.c's `vecint` (`int __attribute__((vector_size(8)))`)
       with i={150,100}, j={10,13}.
     - v4si: simd-1.c's `vecint` (`int __attribute__((vector_size(16)))`)
       with i={150,100,150,200}, j={10,13,20,30}.
     - v8hi: simd-2.c's `vecint` (`short __attribute__((vector_size(16)))`)
       with i={150,100,150,200,0,0,0,0}, j={10,13,20,30,1,1,1,1}.
   Every integer result below is independently re-derivable by hand (or
   cross-checked against the corresponding torture file's own `verify()`
   calls) -- this is not "whatever the compiler currently produces", it is
   the actual expected arithmetic result. (This test deliberately stays
   integer-only and nostdlib, matching the project's existing
   negative_polarity_bitand_mask.test convention -- a float vector shape
   equivalent to scal-to-vec1.c's `vector(4, float)` is separately covered
   by llvm/test/CodeGen/DADAO/vector-type-legalization.ll's `fdiv_v4sf`
   case, which needs no libc softfloat runtime to link since it only runs
   through `llc`, not a real linked/executed binary.)

   x0/y0 (feeding element 0 of every vector) are volatile so a compiler
   cannot constant-fold the whole computation away at compile time (per
   feedback_volatile_needed_for_memory_verification_tests);
   NEGATIVE_CONTROL corrupts x0, which must flip element-0 of every
   vector's expected value below -- proving each check is a real,
   input-sensitive assertion and not accidentally tautological. */

typedef int __attribute__((vector_size(8)))  v2si;   /* 2 x i32,  64-bit  */
typedef int __attribute__((vector_size(16))) v4si;   /* 4 x i32, 128-bit  */
typedef short __attribute__((vector_size(16))) v8hi; /* 8 x i16, 128-bit  */

__attribute__((noinline)) static int bad_i(int a, int b) { return a != b; }

int main(void) {
  volatile int x0 = 150;
  volatile int y0 = 10;
#ifdef NEGATIVE_CONTROL
  x0 = 151; /* every element-0 expected value below is now wrong */
#endif

  int bad = 0;

  /* ---- v2si (pr23135.c shape) ---- */
  v2si a2 = { x0, 100 };
  v2si b2 = { y0, 13 };

  v2si add2 = a2 + b2;
  bad |= bad_i(add2[0], 160);  bad |= bad_i(add2[1], 113);
  v2si sub2 = a2 - b2;
  bad |= bad_i(sub2[0], 140);  bad |= bad_i(sub2[1], 87);
  v2si mul2 = a2 * b2;
  bad |= bad_i(mul2[0], 1500); bad |= bad_i(mul2[1], 1300);
  v2si div2 = a2 / b2;   /* the actual getSetCCResultType trigger */
  bad |= bad_i(div2[0], 15);   bad |= bad_i(div2[1], 7);
  v2si rem2 = a2 % b2;
  bad |= bad_i(rem2[0], 0);    bad |= bad_i(rem2[1], 9);
  v2si and2 = a2 & b2;
  bad |= bad_i(and2[0], 2);    bad |= bad_i(and2[1], 4);
  v2si or2  = a2 | b2;
  bad |= bad_i(or2[0], 158);   bad |= bad_i(or2[1], 109);
  v2si xor2 = a2 ^ b2;
  bad |= bad_i(xor2[0], 156);  bad |= bad_i(xor2[1], 105);
  v2si neg2 = -a2;
  bad |= bad_i(neg2[0], -150); bad |= bad_i(neg2[1], -100);
  v2si not2 = ~a2;
  bad |= bad_i(not2[0], -151); bad |= bad_i(not2[1], -101);

  /* ---- v4si (simd-1.c shape) ---- */
  v4si a4 = { x0, 100, 150, 200 };
  v4si b4 = { y0, 13, 20, 30 };

  v4si add4 = a4 + b4;
  bad |= bad_i(add4[0], 160); bad |= bad_i(add4[1], 113);
  bad |= bad_i(add4[2], 170); bad |= bad_i(add4[3], 230);
  v4si mul4 = a4 * b4;
  bad |= bad_i(mul4[0], 1500); bad |= bad_i(mul4[1], 1300);
  bad |= bad_i(mul4[2], 3000); bad |= bad_i(mul4[3], 6000);
  v4si div4 = a4 / b4;
  bad |= bad_i(div4[0], 15); bad |= bad_i(div4[1], 7);
  bad |= bad_i(div4[2], 7);  bad |= bad_i(div4[3], 6);
  v4si and4 = a4 & b4;
  bad |= bad_i(and4[0], 2); bad |= bad_i(and4[1], 4);
  bad |= bad_i(and4[2], 20); bad |= bad_i(and4[3], 8);
  v4si not4 = ~a4;
  bad |= bad_i(not4[0], -151); bad |= bad_i(not4[1], -101);
  bad |= bad_i(not4[2], -151); bad |= bad_i(not4[3], -201);

  /* ---- v8hi (simd-2.c shape) ---- */
  v8hi a8 = { (short)x0, 100, 150, 200, 0, 0, 0, 0 };
  v8hi b8 = { (short)y0, 13, 20, 30, 1, 1, 1, 1 };

  v8hi add8 = a8 + b8;
  bad |= bad_i(add8[0], 160); bad |= bad_i(add8[1], 113);
  bad |= bad_i(add8[4], 1);   bad |= bad_i(add8[7], 1);
  v8hi div8 = a8 / b8;
  bad |= bad_i(div8[0], 15); bad |= bad_i(div8[1], 7);
  bad |= bad_i(div8[2], 7);  bad |= bad_i(div8[3], 6);
  bad |= bad_i(div8[4], 0);  bad |= bad_i(div8[7], 0);
  v8hi xor8 = a8 ^ b8;
  bad |= bad_i(xor8[0], 156); bad |= bad_i(xor8[1], 105);
  bad |= bad_i(xor8[4], 1);   bad |= bad_i(xor8[7], 1);

  if (bad) return 1;
  return 42;
}
