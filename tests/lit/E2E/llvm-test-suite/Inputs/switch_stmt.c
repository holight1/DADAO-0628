/* Adapted from llvm-test-suite SingleSource/UnitTests/Integer/switch.c
 * (pinned commit 68d03c39d62c2ef9ec663530066bdb66ca5cc4f6, ADR-0012 D4).
 * Upstream test() dispatches on a switch statement (an 8-entry jump table
 * at -O0) and compares the result against the loop index via printf; this
 * freestanding slice drops stdio (no console I/O wired up here) and folds
 * every iteration's dispatched value into a running accumulator, asserted
 * via process exit code, per the polynomial-accumulator convention used by
 * Inputs/divrem.c and friends. The `__attribute__((bitwidth(N)))` markers
 * are a non-standard historical attribute unrecognized by both host gcc
 * and this project's clang (both emit an "unknown attribute ignored"
 * warning and treat int7/int3 as plain `unsigned int`); the switch/case
 * logic itself, `zero`, and `seven` are otherwise unchanged from upstream.
 * Originally failed with a MALIGN fault (0x81) inside the callee on both
 * QEMU and gem5 (codegen-switch-dispatch-malign-in-callee, ML-004b/ML-
 * 004d) — root cause was two independent bugs in the LLVM MC/AsmBackend
 * layer's "same-section fast path" (jump tables are the first construct
 * to reference same-.text-section symbols from same-.text-section code):
 * (1) DADAOAsmBackend::applyFixup's FK_Data_8 case unconditionally wrote
 * the raw (pre-link, section-relative) Value for same-section symbols
 * instead of honoring `IsResolved` (false whenever a symbol is involved,
 * per MCAssembler::evaluateFixup's non-PC-relative path), silently
 * dropping the needed relocation and baking wrong absolute addresses into
 * the `.quad` jump-table entries; (2) fixup_dadao_rela_page/rela_lo's
 * same-section fast path used an unsound ad-hoc formula (mixing up which
 * offset needed the "+4"/page-mask treatment) for computing the jump
 * table's own base address, which is not link-invariant in general once
 * multiple object files (e.g. crt0.o) contribute to the same final
 * section. Both fixed by always deferring same-section symbolic
 * fixups to a real ELF relocation, letting the linker's already-verified
 * R_DADAO_ABS64/R_DADAO_RELA_PAGE/R_DADAO_RELA_LO handlers (lld/ELF/
 * Arch/DADAO.cpp) compute the true final addresses — exactly as already
 * happened for the long-verified cross-section (global variable) case.
 * A separate, always-latent BRIND rb0-misuse bug (same family as
 * codegen-indirect-call-rb0-misuse/DL-066a, but for jump-table dispatch
 * instead of indirect calls: `jump rbha, rdhb, imm12` special-cases
 * rbha=rb0 as "relative", not "zero base") was fixed alongside it via a
 * JUMP_PSEUDO_INDIRECT pseudo (mirrors CALL_PSEUDO_INDIRECT's rd2rb-
 * bridge-into-scratch-RB5 fix). Expected value derived from host gcc -O0. */
typedef unsigned int __attribute__ ((bitwidth(7))) int7;
typedef unsigned int __attribute__ ((bitwidth(3))) int3;

const int7 zero = (int7)(1 << 8); /* constant 0 (attribute ignored: 256 as unsigned, truncated by the (unsigned char) cast below) */
static int3 seven = (int3)0xf; /* attribute ignored: plain unsigned int 15 */

int3 test(int3 c)
{
  switch (c) {
  case 0: return seven >> 3;
  case 1: return seven >> 2;
  case 2: return (seven >> 1) & 2;
  case 3: return (seven >> 1);
  case 4: return seven & 4;
  case 5: return seven & 5;
  case 6: return seven & 6;
  case 7: return seven;
  default: return (int3)-1;
  }
  return 0;
}

int main(void)
{
  unsigned char i;
  unsigned acc = 0;
  for (i = 0; i < ((unsigned char)zero) + 8; i++) {
    unsigned char c = (unsigned char)test((int3)i);
    acc = acc * 4 + c;
  }
  return acc & 0xFF;
}
