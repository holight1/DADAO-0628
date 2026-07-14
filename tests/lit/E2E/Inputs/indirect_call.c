/* DL-066a regression probe: indirect call through a function pointer, no
   malloc/heap involved. Locks down the fix for codegen-indirect-call-rb0-misuse
   (CALL_PSEUDO_INDIRECT wrongly used rb0, meaning PC+4, as the call base for
   an absolute-address indirect call, computing PC+4+target instead of target).
   Dual backend: QEMU was accidentally correct only because of the separate
   QEMU-rb0-not-maintained defect; gem5 correctly maintains rb0 and used to
   land at a garbage address here before the fix. */
static int add2(int x) { return x + 2; }

int (*fp)(int) = add2;

int main(void) { return fp(40); /* expect 42 */ }
