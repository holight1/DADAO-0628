/* Minimal tinystdio stdout for DADAO — bridges FILE.put to _write syscall.
 *
 * Include local-stdio.h (sibling of stdio.h) to get FDEV_SETUP_STREAM and
 * the internal struct __file layout.  The caller must provide _write (a
 * trap-based syscall stub, e.g. pico_stubs.s) and _exit at link time.
 *
 * Link order: crt0.o + stubs.o + stdout_min.o + hello.o + libc.a
 */
#include <stdio.h>
#include "local-stdio.h"

static int my_putc(char c, FILE *f) {
    (void)f;
    char ch = c;
    extern int _write(int, const void *, unsigned long);
    _write(1, &ch, 1);
    return (unsigned char)c;
}

static struct __file __my_stdout = FDEV_SETUP_STREAM(my_putc, NULL, NULL, __SWR);
FILE *const stdout = &__my_stdout;

/* memset — needed by picolibc nano-malloc */
void *memset(void *s, int c, unsigned long n) {
    unsigned char *p = s;
    for (unsigned long i = 0; i < n; i++) p[i] = (unsigned char)c;
    return s;
}
