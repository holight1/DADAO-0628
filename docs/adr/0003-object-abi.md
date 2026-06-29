# ADR-0003: ELF Object ABI for DADAO SimRISC M1

Status: Accepted

## Context

The ELF object file format requires architecture-specific fields in the ELF
header (`e_machine`, `e_flags`, `EI_CLASS`, `EI_DATA`, `EI_OSABI`) and a
relocation type table with precise field-width formulas. The ISA Wiki
(SimRISC 0.4.1) defines instruction encoding but does not specify ELF
header constants or relocation semantics. These must be decided before
`contracts/elf/spec.md` (DL-004a) can be written.

No wiki basis exists for any ELF/object-ABI field; all decisions below are
architecture custom per the greenfield principle (`ADR-0001`).

Dependencies: `contracts/isa/spec.md` §2 (encoding), Appendix A (mask/value),
§4.8 (rela), §5 (branch/call/jump), `docs/open-spec-issues.md` §ELF/object ABI
(reference only; not modified by this ADR).

---

## D1. ELF Header Fixed Fields

### EI_CLASS

`ELFCLASS64 = 2`. All DADAO registers are 64-bit (`spec.md §1.1`). The
instruction word is 32 bits but the register and address model is 64-bit;
64-bit ELF structure (`Elf64_Ehdr`, `Elf64_Rela`) is required.

### EI_DATA

`ELFDATA2MSB = 2` (big-endian). ISA §2.1 specifies big-endian instruction
fetch and data access.

### e_machine

`EM_DADAO = 0x0DA0`. This value is **project-custom** — not registered in
upstream LLVM, IANA/SysV, or any public ELF registry. It exists only in
the legacy DADAO toolchain fork (`llvm-unicore`). The value is preserved
because it has established meaning within the DADAO project ecosystem;
`e_flags = 0x1` (see below) provides machine-readable ABI versioning so
M1 consumers can distinguish themselves from any legacy tooling.

### e_flags

`e_flags = 0x00000001` (M1 ABI version bit).

Bit 0 is the **M1 ABI version flag**: set to 1 for all M1 objects. This
distinguishes M1 objects from legacy `EM_DADAO` objects produced by the
pre-greenfield toolchain (which used `e_flags = 0`). A consumer encountering
`e_machine = 0x0DA0` with `e_flags = 0` must reject the object as an
incompatible legacy version, preventing silent relocation misinterpretation.

Future ABI versions may increment this field or define higher bits.

Bit layout for M1:

| Bit | Meaning |
|-----|---------|
| 0   | ABI version (M1 = 1) |
| 1–31 | Reserved (must be 0) |

Linker must error on unrecognised or mismatched flag bits.

### EI_OSABI

`ELFOSABI_NONE = 0`. M1 is freestanding (bare-metal test machine). The
generic System V ABI value is appropriate; no OS-specific ABI extensions
are needed.

---

## D2. M1 Relocation Types

M1 defines 10 relocation types (including `R_DADAO_NONE`). Each entry
specifies: number, name, description, field width and bit position within
the instruction, the S/A/P formula, the applicable instructions, and the
overflow policy.

Notation:
- `S`: symbol value
- `A`: addend (from `Elf64_Rela::r_addend`)
- `P`: place being relocated (address of the instruction or data word)

### rwii Instruction Field Layout

rwii format encodes a 16-bit unsigned immediate (`immu16`) at bits[15:0]
of the instruction word and a 2-bit wyde-position (`ww`) at bits[17:16].

For each `ABS_W*` relocation, the wyde-position (`ww`) is implicitly
determined by the relocation type. The assembler must produce an rwii
instruction whose `ww` field matches the relocation type; the linker
applies the value to bits[15:0] (the `immu16` portion) and does not
modify the `ww` field.

| Relocation | Appl. instrs | wyde-pos | Target bits |
|------------|-------------|----------|-------------|
| `R_DADAO_ABS_W3` | setzw, orw (RD/RB) | 3 | `(S+A)[63:48]` |
| `R_DADAO_ABS_W2` | setzw, orw (RD/RB) | 2 | `(S+A)[47:32]` |
| `R_DADAO_ABS_W1` | setzw, orw (RD/RB) | 1 | `(S+A)[31:16]` |
| `R_DADAO_ABS_W0` | setzw, orw (RD/RB) | 0 | `(S+A)[15:0]` |

### Complete Table

| # | Name | Description | Field | S/A/P formula | Appl. instrs | Overflow |
|---|------|-------------|-------|---------------|--------------|----------|
| 0 | `R_DADAO_NONE` | No relocation | — | — | — | — |
| 1 | `R_DADAO_64` | Absolute 64-bit data reference | 8 bytes at `P` (full 64-bit word) | `S + A` | `.quad`, pointer-sized data | None (64-bit field) |
| 2 | `R_DADAO_ABS_W3` | rwii wyde-pos 3, bits[63:48] | `immu16` at bits[15:0] | `((S+A) >> 48) & 0xFFFF` | setzw, orw (RD/RB) | None (16-bit slice) |
| 3 | `R_DADAO_ABS_W2` | rwii wyde-pos 2, bits[47:32] | `immu16` at bits[15:0] | `((S+A) >> 32) & 0xFFFF` | setzw, orw (RD/RB) | None (16-bit slice) |
| 4 | `R_DADAO_ABS_W1` | rwii wyde-pos 1, bits[31:16] | `immu16` at bits[15:0] | `((S+A) >> 16) & 0xFFFF` | setzw, orw (RD/RB) | None (16-bit slice) |
| 5 | `R_DADAO_ABS_W0` | rwii wyde-pos 0, bits[15:0] | `immu16` at bits[15:0] | `(S+A) & 0xFFFF` | setzw, orw (RD/RB) | None (16-bit slice) |
| 6 | `R_DADAO_PCREL18` | PC-relative offset ×4 (riii) | `imms18` at bits[17:0] | `((S+A) - (P+4)) >> 2` | brn, brnn, brz, brnz, brp, brnp | Link-time error |
| 7 | `R_DADAO_PCREL24` | PC-relative offset ×4 (iiii) | `imms24` at bits[23:0] | `((S+A) - (P+4)) >> 2` | call (iiii), jump (iiii) | Link-time error |
| 8 | `R_DADAO_RELA` | PC-relative page address ×4096 (riii) | `imms18` at bits[17:0] | `((S+A) >> 12) - ((P+4) >> 12)` | rela | Link-time error |
| 9 | `R_DADAO_PCREL12` | PC-relative offset ×4 (rrii branch) | `imms12` at bits[11:0] (hc:hd) | `((S+A) - (P+4)) >> 2` | breq, brne | Link-time error |

### Per-Type Derivation

#### R_DADAO_64

- **Encoding derivation**: Standard ELF64 absolute data relocation.
- **Field**: 8 contiguous bytes starting at `P`.
- **Applicable sections**: `.data`, `.rodata` (initialiser values, jump tables,
  pointer arrays). NOBITS `.bss` has no stored field to relocate.
- **Overflow**: None. The 64-bit field accommodates any `S+A` value.

#### R_DADAO_ABS_W3 / W2 / W1 / W0

- **Encoding derivation**: rwii format per `spec.md §3.13` / `§4.6`. The
  instruction word has `immu16` at bits[15:0] and `ww` (wyde-position) at
  bits[17:16]. Each `ABS_W*` relocation extracts one 16-bit slice of the
  64-bit target address and writes it into bits[15:0]. The `ww` field is
  verified by the assembler but not modified by the linker.
- **Applicable instructions**: `setzw` (preferred for initial construction),
  `orw` (for merging). Both RD and RB register variants (`spec.md §2.8`)
  are valid targets.
- **Overflow**: None. Any 64-bit value decomposes into four 16-bit slices.

#### R_DADAO_PCREL18

- **Encoding derivation**: riii format per `spec.md §5.1`. The instruction
  word encodes `imms18` at bits[17:0] (hb:hc:hd, concatenated). The branch
  target formula from `spec.md §5.1`:
  ```
  PC_next[47:0] = (rb0[47:0] + (sext_18(imms18) << 2)) mod 2^48
  ```
  where `rb0 = P + 4`. Solving for `imms18`:
  ```
  imms18 = ((S + A) - (P + 4)) >> 2
  ```
- **Constraints**:
  1. `(S+A) - (P+4)` must be a multiple of 4 (instruction alignment,
     per `spec.md §2.1`).
  2. The result must fit in 18-bit signed: `[-131072, 131071]`.
     The corresponding byte-displacement range is
     `[-524288, 524284]`.
- **Overflow**: Link-time error if either constraint is violated.

#### R_DADAO_PCREL24

- **Encoding derivation**: iiii format per `spec.md §5.3`, `§5.4`. The
  instruction word encodes `imms24` at bits[23:0] (ha:hb:hc:hd,
  concatenated). The jump/call target formula from `spec.md §5.3`/`§5.4`:
  ```
  PC_next[47:0] = (rb0[47:0] + (sext_24(imms24) << 2)) mod 2^48
  ```
  ```
  imms24 = ((S + A) - (P + 4)) >> 2
  ```
- **Constraints**:
  1. `(S+A) - (P+4)` must be a multiple of 4.
  2. The result must fit in 24-bit signed: `[-8388608, 8388607]`.
     The corresponding byte-displacement range is
     `[-33554432, 33554428]`.
- **Overflow**: Link-time error if either constraint is violated.
- **Applicable instructions**: `call` iiii-format (`spec.md §5.4`), `jump`
  iiii-format (`spec.md §5.3`). Both share the same encoding and
  relocation formula; one relocation type serves both.

#### R_DADAO_PCREL12

- **Encoding derivation**: rrii format per `spec.md §5.2`. The instruction
  encodes `imms12` at bits[11:0] (hc:hd concatenated, 6+6 bits). The branch
  target formula from `spec.md §5.2`:
  ```
  PC_next[47:0] = (rb0[47:0] + (sext_12(imms12) << 2)) mod 2^48
  ```
  where `rb0 = P + 4`. Solving for `imms12`:
  ```
  imms12 = ((S + A) - (P + 4)) >> 2
  ```
- **Constraints**:
  1. `(S+A) - (P+4)` must be a multiple of 4 (instruction alignment).
  2. The result must fit in 12-bit signed: `[-2048, 2047]`.
     Byte-displacement range: `[-8192, 8188]`.
- **Overflow**: Link-time error if either constraint is violated.
- **Applicable instructions**: `breq` (§5.2), `brne` (§5.2). Both compare
  two RD source registers and branch on equality/inequality using the same
  rrii encoding structure and relocation formula.

#### R_DADAO_RELA

- **Encoding derivation**: riii format per `spec.md §4.8`. The instruction
  word encodes `imms18` at bits[17:0]. The `rela` semantic from `§4.8`:
  ```
  base[47:0] = (rb0[47:0]) & ~0xFFF
  offset = sext_18(imms18) << 12
  rbha[47:0] = (base[47:0] + offset) mod 2^48
  ```
  Solving for `imms18`:
  ```
  imms18 = ((S + A) >> 12) - ((P + 4) >> 12)
  ```
  This is the page-number difference. The result is always 4 KB-aligned
  (low 12 bits zero). A companion `orw` instruction with `R_DADAO_ABS_W0`
  sets the low bits of the address. A subsequent `addi` is equivalent only
  when the low-part adjustment fits its signed 12-bit immediate.
- **Constraints**:
  1. The page-number difference must fit in 18-bit signed: `[-131072, 131071]`
     (byte-displacement range `[-536870912, 536866816]` in 4 KB steps).
  2. No alignment constraint on `S+A` low bits — the `rela` instruction
     produces a page-aligned value; low bits are filled by separate
     instructions.
- **Overflow**: Link-time error if the page-number difference is out of
  range.

---

## D3. Overflow Strategy

Two-tier policy:

| Relocation type | Overflow behavior |
|-----------------|-------------------|
| `R_DADAO_64` | No overflow check needed. |
| `R_DADAO_ABS_W*` | No overflow check needed (16-bit slices of a 64-bit value). |
| `R_DADAO_PCREL18` | **Link-time error** if `((S+A)-(P+4))/4` exceeds 18-bit signed range or is not a multiple of 4. |
| `R_DADAO_PCREL24` | **Link-time error** if `((S+A)-(P+4))/4` exceeds 24-bit signed range or is not a multiple of 4. |
| `R_DADAO_PCREL12` | **Link-time error** if `((S+A)-(P+4))/4` exceeds 12-bit signed range or is not a multiple of 4. |
| `R_DADAO_RELA` | **Link-time error** if `((S+A)>>12) - ((P+4)>>12)` exceeds 18-bit signed range. |

Rationale: DADAO hardware discards overflow silently (48-bit wrap, per
`§4`/`§5`). The linker must catch cases where the immediate field is too
small to hold the computed offset; otherwise the linked program would
produce incorrect addresses with no diagnostic. Enforcing at link time is
the only point where all symbol values are final.

---

## D4. Relaxation

**M1 prohibits relaxation.** The linker must not shrink or rewrite
instruction sequences.

Rationale: DADAO has no nop-removal, branch-range expansion, or
instruction-pair compression patterns that would require relaxation.
All instruction widths are fixed at 32 bits (`spec.md §2.1`). The
`setzw`+`orw`×3 sequence for absolute address construction is the
canonical form and must not be modified by the linker (e.g., converting
to a shorter sequence). Assembly source provides the exact sequence;
the linker's only role is filling relocation immediates.

---

## D5. Section Alignment and Loading

### Section Alignment

| Section | Alignment | Reason |
|---------|-----------|--------|
| `.text` | 4 bytes | Instruction alignment per `spec.md §2.1` |
| `.rodata` | 8 bytes | Natural alignment for 64-bit constants (`ldo` requires 8-byte, `§3.1`) |
| `.data` | 8 bytes | Same as `.rodata` |
| `.bss` | 8 bytes | Same |

`.text` starts at a 4-byte-aligned address. All other sections are
8-byte-aligned. Sections are laid out in the order above (text, rodata,
data, bss) by default. Linker scripts may reorder as long as per-section
alignment constraints are respected.

### Loading (Freestanding)

M1 is a bare-metal test machine (`ADR-0004` defines the memory map).
There is no virtual memory, page table, or relocation at load time.
The ELF image is loaded directly into physical memory:

- **VA = PA**: The virtual address in the ELF segment is the physical
  load address.
- **No dynamic linking**: All relocations are resolved statically by the
  linker. `Elf64_Rela` entries are resolved to final values in the
  output file; no `.rela` section survives into the loaded image.
- **No program headers beyond LOAD**: PHDR, DYNAMIC, INTERP, NOTE are
  not emitted for M1 freestanding binaries.

### Entry Point and M1 Artifact Pipeline

`e_entry` in the ELF header is the `_start` symbol address in `.text`.
For M1 freestanding: VA = PA, so `e_entry` is also the physical entry
address. It is informational for host tooling (debuggers, ELF utilities).

**M1 artifact pipeline.** The QEMU test machine (ADR-0004) loads a flat
binary — not an ELF — and always enters at the flat binary's load base
(0x80000000). `e_entry` is NOT read by the test machine. The end-to-end
pipeline is:

```
1. Assembler → ET_REL object (relocatable, per-file)
2. Static linker: -Ttext=0x80000000 → ET_EXEC ELF binary (fully linked)
3. objcopy --output-target=binary → flat binary (raw bytes at load base)
4. QEMU: -kernel flat.bin → loads to 0x80000000, enters at 0x80000000
```

The static linker and `objcopy` are LLVM tools selected at Phase 1. LLD
(`ld.lld`) handles the same-TU link; no multi-object cross-TU linking is
required for M1 tests.

---

## Consequences

1. `EM_DADAO = 0x0DA0` is a project-custom value (not registered in the
   official IANA/SysV ELF namespace). It is carried forward from the legacy
   DADAO toolchain fork. `e_flags = 0x00000001` (M1 ABI version) prevents
   silent misinterpretation of M1 objects by legacy consumers expecting
   `e_flags = 0`; any consumer must reject version mismatch.
2. M1 relocation types are a clean subset (10 types, including `R_DADAO_NONE`)
   derived from ISA spec Appendix A. Numbers 0–9 are chosen fresh for the
   M1 namespace; `e_flags = 1` ensures these numbers are interpreted in the
   M1 context, not in the legacy `Dadao.def` namespace where the same
   numbers had different meanings.
3. All bounded relocations are overflow-checked at link time, preventing
   silent address corruption in freestanding binaries.
4. No relaxation simplifies the linker implementation: no nop-removal,
   branch-range expansion, or instruction-pair rewriting logic.
5. The `R_DADAO_RELA` formula uses page-number difference (not byte
   offset), matching the `rela` instruction's 4 KB page-base semantics.
6. `docs/open-spec-issues.md` entry "ELF/object ABI" transitions from
   open to closed by this ADR.
