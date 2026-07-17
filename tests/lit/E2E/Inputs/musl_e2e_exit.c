/* ML-012a: first real musl E2E milestone input. Deliberately minimal --
   no headers, no libc calls beyond the implicit crt/__libc_start_main
   dispatch -- this test is about proving the crt1.c/_start_c/
   __libc_start_main/exit() startup path itself works end to end, not
   about exercising any particular libc function. */
int main(void) {
    return 42;
}
