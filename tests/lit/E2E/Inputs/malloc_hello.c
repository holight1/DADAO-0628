#include <stdio.h>
#include <stdlib.h>

static void *my_memset(void *s, int c, unsigned long n) {
    unsigned char *p = s;
    for (unsigned long i = 0; i < n; i++) p[i] = (unsigned char)c;
    return s;
}

static int my_strcmp(const char *a, const char *b) {
    while (*a && *a == *b) { a++; b++; }
    return *(unsigned char *)a - *(unsigned char *)b;
}

int main(void) {
    char *p = malloc(32);
    if (!p) { printf("FAIL1\n"); return 1; }

    my_memset(p, 0, 32);
    p[0] = 'O'; p[1] = 'K'; p[2] = 0;
    if (my_strcmp(p, "OK") != 0) { printf("FAIL2\n"); return 2; }

    char *q = malloc(32);
    if (!q) { printf("FAIL3\n"); return 3; }
    if (p == q) { printf("FAIL4\n"); return 4; }

    q[0] = 'O'; q[1] = 'K'; q[2] = '2'; q[3] = 0;

    /* ML-013a: use fputs (fixed, non-variadic pointer args), not
     * printf("%s %s\n", p, q). contracts/abi/spec.md SS1/SS(Varargs row)
     * explicitly excludes varargs from M1 scope; verified (during this
     * task, with a real disassembly trace) that the DADAO backend's
     * variadic-argument save area is RD-bank-only and never captures
     * pointer varargs placed in the RB bank by DL-069a's (correct, in-M1-
     * scope) fixed/named-argument calling convention -- so
     * printf("%s %s", p, q) silently reads stale/unrelated RD register
     * contents instead of p/q (confirmed: produced "OK2 OK", a plausible-
     * looking but wrong swap, from leftover heap-pointer values still
     * sitting in RD registers -- not a crash, just silently wrong data).
     * This is a real, newly-exposed instance of the already-tracked, open,
     * explicitly-out-of-M1-scope docs/issues.yaml "Varargs" gap (see also
     * the more specific "varargs-pointer-args-lost-rb-bank-save-area"
     * entry this task adds) -- not a regression in anything this task (or
     * DL-069a) was chartered to fix. fputs is a fixed 2-argument (non-
     * variadic) function, both of whose arguments are pointers correctly
     * handled by the real (in-scope) RB-bank calling convention, so this
     * change keeps testing exactly what this test's title promises
     * (malloc/free correctness) without depending on unsupported variadic
     * pointer-argument forwarding.
     */
    fputs(p, stdout);
    fputs(" ", stdout);
    fputs(q, stdout);
    fputs("\n", stdout);
    return 0;
}
