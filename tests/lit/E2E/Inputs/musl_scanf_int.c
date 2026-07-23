/* ML-025a: real integer-format scanf E2E input. This is the literal
   scanf("%d", &x) repro the task's own acceptance criteria describe --
   asserts the INTENDED (bug-fixed) behavior: read "42" from stdin, parse
   it, print it back, exit with that value. See the .test file's XFAIL
   directive and comment for why this currently fails on both backends
   (a confirmed, pre-existing, separately-tracked bug -- not related to
   the 6 softfloat symbols this task added, which are independently
   verified correct; see docs/issues-archive.yaml's closed
   musl-vfscanf-missing-single-precision-and-divide-softfloat-symbols
   entry and docs/issues.yaml's open
   varargs-pointer-args-lost-rb-bank-save-area entry for the full
   writeup). */
#include <stdio.h>

int main(void) {
    int x = 0;
    int n = scanf("%d", &x);
    if (n != 1)
        return 1;
    printf("got=%d\n", x);
    return x;
}
