/* ML-022a: real integer-format printf E2E input. Deliberately restricted to
   %d/%u (integer format specifiers only) -- deliberately avoids any pointer
   varargs (%s/%p), which would hit the already-tracked, unrelated
   varargs-pointer-args-lost-rb-bank-save-area gap (docs/issues.yaml).

   printf("%d", ...) does not itself need any floating-point arithmetic at
   runtime, but musl's vfprintf.c/printf_core is a single translation unit
   that also contains the %f/%g/%e code paths, so the object file references
   double-precision soft-float libcalls regardless of which specifier is
   used at runtime. This is exactly the ML-020a/ML-021a/ML-022a link gap:
   those symbols were undefined until this task's arch/dadao soft-float
   shim (src/internal/dadao/softfloat_shim.c) supplied them. */
#include <stdio.h>

int main(void) {
    printf("value=%d\n", 42);
    return 42;
}
