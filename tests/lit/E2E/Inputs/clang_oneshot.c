/* clang driver one-shot (DL-064b): clang compiles C and links (crt0.o + hello.o,
   SEPARATE objects) via ld.lld — the first cross-object `call main` (crt0's call
   to main in another object) exercises the R_DADAO_CALL24 relocation the linker
   must resolve. main returns 42. */
int add(int a, int b) { return a + b; }
int main(void) { return add(30, 12); }
