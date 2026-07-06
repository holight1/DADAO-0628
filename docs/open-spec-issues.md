# Open Specification Issues

These issues remain open after Wiki update to `13a414d` (SimRISC 0.4.1).

| Area | Open issue | Blocks |
|------|-----------|--------|
| Conditional assign overlap (C-27) | csn/csz/csp/cseq/csne snapshot rule on src=dst: non-overlap behavior is definite; overlap OPEN | Overlap test vectors (must close before M1 gate) |
| TLB fault return | Successful repair currently appears to skip instead of retry the faulting instruction | System QEMU, Kernel |
| PTW SBI ABI | PTE/PTHI/PAHI register-bank classification is inconsistent with scalar ABI | SBI, Kernel |
| VA2PA result | Signed error encoding conflicts with full 64-bit physical addresses | SBI, MMU tools |
| Varargs | Save area, overflow area, aggregate values, and incoming-SP base need one layout | Complete ABI, libc |
| Cross-cfx escape | Previous cfx state and nested return policy are not fully specified | Exception nesting |
| Multiple returns | Mixed RD/RB/RF ordering is ambiguous | Advanced CodeGen |
| ~~ELF/object ABI~~ | **Closed by ADR-0003** (2026-06-29): EM_DADAO=0x0DA0, e_flags=0x1 (M1), ELFCLASS64/ELFDATA2MSB, 10 relocation types | — |
| Hardware reset | Power-on values for RD/RB/RF/RA beyond process-entry init | QEMU, test machine |
| ~~SBZ behavior~~ | **Closed by ADR-0004** (2026-06-29): SBZ → ILLI (exit 0x82); analogy to illegal operand in known opcode | — |
| Integer division fault (found by M1 audit DL-039) | spec §3.7 asserts div-by-zero and `divs INT64_MIN÷-1` → ILLI, but wiki §乘除操作 does not define it (the DZ bit in DADAO-11-AEE is FP-only). Marked `[spec-decision]` pending wiki-team confirmation. | M1 spec-fidelity |

**Resolved by Architecture Decision (2026-06-29):**
- rd2ra/ra2rd scope → Excluded (M1 scope decision; ISA semantics clear per SimRISC-02)
- Instruction fetch byte order → Included big-endian (SimRISC-00 L15)
- ELF/object ABI → Closed by ADR-0003 (EM_DADAO=0x0DA0, e_flags=1 for M1, 10 relocation types)
- SBZ behavior → Closed by ADR-0004 (SBZ → ILLI; see D5)

**Resolved in Wiki `13a414d` (SimRISC 0.4.1):**
- C-01 instruction big-endian
- C-02 reserved encoding → UNDI
- C-03~C-06 RB 48-bit rules table
- C-07 RASOF/RASUF precise
- C-08~C-12 division semantics
- C-13 RA process-entry init (all zero)
- C-15 swym NOP
- C-16 multi-register bank overflow → ILLI
- C-17 immu6=0 → ILLI
- C-19 effective address 48-bit mod
- C-20 rb0[63:48]=0
- C-21 rela high-16 preserve
- C-23 IALIGN exception
- C-25 operand legality (rd0→ILLI, etc.)
- C-26 dual-dest overlap ILLI
