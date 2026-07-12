/* clang integration smoke: real C -> clang -emit-llvm -> llc -> lld -> both backends.
   int is i32, long/pointer i64, big-endian — the frontend ABI must match the
   backend. main returns 42; a mix of int and long exercises the type widths. */
int add(int a, int b) { return a + b; }
int main(void) {
  int x = add(30, 8);      /* 38, i32 arithmetic */
  long s = 0;
  for (int i = 1; i <= 4; i++) s += i;  /* 10, long accumulate */
  return x + (int)s - 6;   /* 38 + 10 - 6 = 42 */
}
