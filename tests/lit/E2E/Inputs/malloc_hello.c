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

    printf("%s %s\n", p, q);
    return 0;
}
