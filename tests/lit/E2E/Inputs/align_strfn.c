/* Runtime-correctness probe for DL-067b (BR_CC premature-combine fix).
   test_align mirrors the DL-067a minimal repro that used to crash the
   backend (ReduceLoadWidth narrows the alignment-check load to i8 before
   type legalization, and the redundant PerformDAGCombine BR_CC path used
   to fire on the still-illegal-typed br_cc before LegalizeTypes ran).
   This probe exercises the actual branch SEMANTICS (not just "compiles"):
     - an already 8-aligned pointer must skip the loop body entirely,
       even if the first byte is NUL (outer AND+brz test only).
     - a misaligned pointer with no NUL before the next 8-boundary must
       walk all bytes and return 1.
     - a misaligned pointer that hits NUL after 0 and after 2 iterations
       of str++ must return 0 in both cases (distinct trip counts).
   Alignment of each base buffer is forced purely by runtime pointer
   arithmetic (round up within a slack buffer), not by an `aligned(N)`
   attribute on a stack object or a nonzero-offset GEP into a file-scope
   global -- both of those hit separate, unrelated pre-existing backend
   gaps (stack over-alignment support / constant-GEP-offset-into-global
   folding, see completion report) that would otherwise confound this
   probe, which is specifically about br_cc/BRZ/BRNZ branch semantics. */
unsigned long test_align(char *str) {
    while ((unsigned long)str & 7) {
        if (!*str) return 0;
        str++;
    }
    return 1;
}

int main(void) {
    char raw1[24], raw2[24], raw3[24], raw4[24];
    char *aligned_nul   = (char *)(((unsigned long)raw1 + 7) & ~7UL);
    char *no_early_nul  = (char *)(((unsigned long)raw2 + 7) & ~7UL);
    char *nul_at_off0   = (char *)(((unsigned long)raw3 + 7) & ~7UL);
    char *nul_at_off2   = (char *)(((unsigned long)raw4 + 7) & ~7UL);

    aligned_nul[0] = 0;
    aligned_nul[1] = 'A';

    no_early_nul[3] = 'A'; no_early_nul[4] = 'A'; no_early_nul[5] = 'A';
    no_early_nul[6] = 'A'; no_early_nul[7] = 'A'; no_early_nul[8] = 0;

    nul_at_off0[3] = 0;

    nul_at_off2[3] = 'A'; nul_at_off2[4] = 'A'; nul_at_off2[5] = 0;

    unsigned long r1, r2, r3, r4;
    unsigned long res = 0;

    /* Case 1: pointer already 8-aligned, first byte NUL -> outer while
       condition false immediately, body (and the NUL check) never runs;
       expect return 1. */
    r1 = test_align(aligned_nul);
    if (r1 != 1) res |= 1;

    /* Case 2: misaligned by 3, bytes at offsets 3..7 all non-NUL -> loop
       runs to completion; expect return 1. */
    r2 = test_align(no_early_nul + 3);
    if (r2 != 1) res |= 2;

    /* Case 3: misaligned by 3, NUL on the very first checked byte (offset
       3, 0 iterations of str++) -> expect return 0. */
    r3 = test_align(nul_at_off0 + 3);
    if (r3 != 0) res |= 4;

    /* Case 4: misaligned by 3, NUL after 2 iterations of str++ (checked
       bytes at offsets 3,4,5) -> expect return 0. */
    r4 = test_align(nul_at_off2 + 3);
    if (r4 != 0) res |= 8;

    return (int)res;
}
