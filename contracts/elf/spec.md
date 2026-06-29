# ELF Contract — DADAO SimRISC (M1 Scope)

**Version**: 0.1.0
**Source**: ADR-0003 (`docs/adr/0003-object-abi.md`, 2026-06-29)
**Status**: Candidate

M1 scope is defined by `code-agent/designs/0002-detailed-roadmap.md` §Scope
Matrix. This contract covers ELF header fields, relocation types, overflow
policy, relaxation policy, section alignment, and the artifact pipeline for M1
freestanding binaries.

---

## §1 ELF Header Fixed Fields

All decisions in this section are architecture custom per the greenfield
principle (ADR-0001). No wiki basis exists for any ELF or object-ABI field.

### 1.1 EI_CLASS

`ELFCLASS64 = 2`. All DADAO registers are 64-bit (`contracts/isa/spec.md §1.1`).
The instruction word is 32 bits but the register and address model is 64-bit;
`Elf64_Ehdr` and `Elf64_Rela` structures are required.

[ADR-0003 §D1]

### 1.2 EI_DATA

`ELFDATA2MSB = 2` (big-endian). Matches ISA big-endian instruction fetch and
data access (`contracts/isa/spec.md §2.1`).

[ADR-0003 §D1]

### 1.3 e_machine

`EM_DADAO = 0x0DA0`. **Project-custom** — not registered in upstream LLVM,
IANA/SysV, or any public ELF registry. The value exists only in the legacy
DADAO toolchain fork (`llvm-unicore`) and is preserved within the project
ecosystem. `e_flags = 0x1` provides the machine-readable ABI version so M1
consumers can distinguish themselves from legacy tooling.

[ADR-0003 §D1]

### 1.4 e_flags

`e_flags = 0x00000001` (M1 ABI version flag).

| Bit | Meaning |
|-----|---------|
| 0   | ABI version (M1 = 1) |
| 1–31| Reserved (must be 0) |

Bit 0 distinguishes M1 objects from legacy `EM_DADAO` objects (`e_flags = 0`).
A consumer encountering `e_machine = 0x0DA0` with `e_flags = 0` must reject the
object. The linker must error on unrecognised or mismatched flag bits.

[ADR-0003 §D1]

### 1.5 EI_OSABI

`ELFOSABI_NONE = 0`. M1 is freestanding (bare-metal); no OS-specific ABI
extensions are needed.

[ADR-0003 §D1]

---

## §2 M1 Relocation Types

M1 defines 10 relocation types (including `R_DADAO_NONE`). Each entry specifies
the number, name, field width and bit position, S/A/P formula, applicable
instructions, and overflow policy.

Notation:
- `S`: symbol value
- `A`: addend (from `Elf64_Rela::r_addend`)
- `P`: place being relocated (address of the instruction or data word)

All rwii-format instructions encode a 16-bit unsigned immediate at bits[15:0]
and a 2-bit wyde-position (`ww`) at bits[17:16] (`contracts/isa/spec.md §2.3`,
`§3.13`). For each `ABS_W*` relocation, the wyde-position is implicitly
determined by the relocation type; the assembler must produce an rwii
instruction whose `ww` field matches, and the linker applies the value to
bits[15:0] without modifying `ww`.

### 2.1 Complete Relocation Table

| # | Name | Field | S/A/P formula | Applicable instructions | Overflow |
|---|------|-------|---------------|------------------------|----------|
| 0 | `R_DADAO_NONE` | — | — | — | — |
| 1 | `R_DADAO_64` | 8 bytes at `P` (full 64-bit word) | `S + A` | `.quad`, pointer-sized data | None (64-bit field) |
| 2 | `R_DADAO_ABS_W3` | `immu16` at bits[15:0] (rwii, ww=3) | `((S+A) >> 48) & 0xFFFF` | `setzw`, `orw` (RD/RB) (`contracts/isa/spec.md §3.13`, `§4.6`) | None (16-bit slice) |
| 3 | `R_DADAO_ABS_W2` | `immu16` at bits[15:0] (rwii, ww=2) | `((S+A) >> 32) & 0xFFFF` | `setzw`, `orw` (RD/RB) | None (16-bit slice) |
| 4 | `R_DADAO_ABS_W1` | `immu16` at bits[15:0] (rwii, ww=1) | `((S+A) >> 16) & 0xFFFF` | `setzw`, `orw` (RD/RB) | None (16-bit slice) |
| 5 | `R_DADAO_ABS_W0` | `immu16` at bits[15:0] (rwii, ww=0) | `(S+A) & 0xFFFF` | `setzw`, `orw` (RD/RB) | None (16-bit slice) |
| 6 | `R_DADAO_PCREL18` | `imms18` at bits[17:0] (riii) | `((S+A) - (P+4)) >> 2` | `brn`, `brnn`, `brz`, `brnz`, `brp`, `brnp` (`contracts/isa/spec.md §5.1`) | Link-time error |
| 7 | `R_DADAO_PCREL24` | `imms24` at bits[23:0] (iiii) | `((S+A) - (P+4)) >> 2` | `call` (iiii), `jump` (iiii) (`contracts/isa/spec.md §5.3`, `§5.4`) | Link-time error |
| 8 | `R_DADAO_RELA` | `imms18` at bits[17:0] (riii) | `((S+A) >> 12) - ((P+4) >> 12)` | `rela` (`contracts/isa/spec.md §4.8`) | Link-time error |
| 9 | `R_DADAO_PCREL12` | `imms12` at bits[11:0] (rrii, hc:hd) | `((S+A) - (P+4)) >> 2` | `breq`, `brne` (`contracts/isa/spec.md §5.2`) | Link-time error |

### 2.2 Per-Type Derivation

#### R_DADAO_64 (#1)

Standard ELF64 absolute data relocation. The 64-bit field accommodates any
`S + A` value. Applicable sections: `.data`, `.rodata` (initialiser values,
jump tables, pointer arrays). NOBITS `.bss` has no stored field to relocate.
Overflow: none.

#### R_DADAO_ABS_W3 / W2 / W1 / W0 (#2–#5)

rwii format per `contracts/isa/spec.md §3.13` (RD) and `§4.6` (RB). Each type
extracts one 16-bit slice of the 64-bit target address and writes it into
bits[15:0] of the instruction word. The `ww` field (bits[17:16]) is verified
by the assembler and must match the relocation type (ww=3 for W3, ww=2 for W2,
etc.); the linker does not modify `ww`. Applicable instructions: `setzw`
(preferred for initial construction), `orw` (for merging), both RD and RB
register variants. Overflow: none — any 64-bit value decomposes into four
16-bit slices.

#### R_DADAO_PCREL18 (#6)

riii format per `contracts/isa/spec.md §5.1`. The instruction encodes
`imms18` at bits[17:0] (hb:hc:hd concatenated). Branch target formula:

```
imms18 = ((S + A) - (P + 4)) >> 2
```

Constraints:
1. `(S+A) - (P+4)` must be a multiple of 4 (instruction alignment,
   per `contracts/isa/spec.md §2.1`).
2. The result must fit in 18-bit signed: `[-131072, 131071]`
   (byte-displacement range `[-524288, 524284]`).

Overflow: link-time error if either constraint is violated.

#### R_DADAO_PCREL24 (#7)

iiii format per `contracts/isa/spec.md §5.3` (jump) and `§5.4` (call).
The instruction encodes `imms24` at bits[23:0] (ha:hb:hc:hd concatenated).

```
imms24 = ((S + A) - (P + 4)) >> 2
```

Constraints:
1. `(S+A) - (P+4)` must be a multiple of 4.
2. The result must fit in 24-bit signed: `[-8388608, 8388607]`
   (byte-displacement range `[-33554432, 33554428]`).

Overflow: link-time error if either constraint is violated.

One relocation type serves both `call` iiii-format and `jump` iiii-format.

#### R_DADAO_PCREL12 (#9)

[ADR-0003 §D2 extended — derived from ISA spec §5.2; `breq`/`brne` use
rrii/imms12 format absent from the original 9-type table.]

rrii format per `contracts/isa/spec.md §5.2`. The instruction encodes
`imms12` at bits[11:0] (hc:hd concatenated, 6+6 bits).

```
imms12 = ((S + A) - (P + 4)) >> 2
```

Constraints:
1. `(S+A) - (P+4)` must be a multiple of 4 (instruction alignment).
2. The result must fit in 12-bit signed: `[-2048, 2047]`
   (byte-displacement range `[-8192, 8188]`).

Overflow: link-time error if either constraint is violated.

Applicable instructions: `breq` and `brne` (`contracts/isa/spec.md §5.2`).
Both compare two RD source registers and branch on equality/inequality using
the same rrii encoding structure and relocation formula.

#### R_DADAO_RELA (#8)

riii format per `contracts/isa/spec.md §4.8`. The instruction encodes
`imms18` at bits[17:0]. The `rela` semantic computes a 4 KB-aligned page
address:

```
imms18 = ((S + A) >> 12) - ((P + 4) >> 12)
```

This is the page-number difference. The result is always 4 KB-aligned
(low 12 bits zero). A companion `orw` instruction with `R_DADAO_ABS_W0`
sets the low bits of the address.

Constraints:
1. The page-number difference must fit in 18-bit signed: `[-131072, 131071]`
   (byte-displacement range `[-536870912, 536866816]` in 4 KB steps).
2. No alignment constraint on `S+A` low bits — the `rela` instruction
   produces a page-aligned value; low bits are filled by separate
   instructions.

Overflow: link-time error if the page-number difference is out of range.

[ADR-0003 §D2]

---

## §3 Overflow Policy

Two-tier policy:

| Relocation type | Overflow behavior |
|-----------------|-------------------|
| `R_DADAO_64` | No overflow check needed. |
| `R_DADAO_ABS_W*` | No overflow check needed (16-bit slices of a 64-bit value). |
| `R_DADAO_PCREL18` | **Link-time error** if `((S+A)-(P+4))>>2` exceeds 18-bit signed range or is not a multiple of 4. |
| `R_DADAO_PCREL24` | **Link-time error** if `((S+A)-(P+4))>>2` exceeds 24-bit signed range or is not a multiple of 4. |
| `R_DADAO_PCREL12` | **Link-time error** if `((S+A)-(P+4))>>2` exceeds 12-bit signed range or is not a multiple of 4. |
| `R_DADAO_RELA` | **Link-time error** if `((S+A)>>12) - ((P+4)>>12)` exceeds 18-bit signed range. |

Rationale: DADAO hardware discards overflow silently (48-bit wrap, per
`contracts/isa/spec.md §4`/`§5`). The linker must catch cases where the
immediate field is too small to hold the computed offset; otherwise the linked
program would produce incorrect addresses with no diagnostic. Enforcing at link
time is the only point where all symbol values are final.

[ADR-0003 §D3]

---

## §4 Relaxation

**M1 prohibits relaxation.** The linker must not shrink or rewrite instruction
sequences.

Rationale: DADAO has no nop-removal, branch-range expansion, or
instruction-pair compression patterns that would require relaxation. All
instruction widths are fixed at 32 bits (`contracts/isa/spec.md §2.1`). The
`setzw` + `orw` × 3 sequence for absolute address construction is the
canonical form and must not be modified by the linker. Assembly source
provides the exact sequence; the linker's only role is filling relocation
immediates.

[ADR-0003 §D4]

---

## §5 Section Alignment and Loading

### 5.1 Section Alignment

| Section  | Alignment | Reason |
|----------|-----------|--------|
| `.text`  | 4 bytes   | Instruction alignment per `contracts/isa/spec.md §2.1` |
| `.rodata`| 8 bytes   | Natural alignment for 64-bit constants (`ldo` requires 8-byte, `contracts/isa/spec.md §3.1`) |
| `.data`  | 8 bytes   | Same as `.rodata` |
| `.bss`   | 8 bytes   | Same |

`.text` starts at a 4-byte-aligned address. All other sections are
8-byte-aligned. Sections are laid out in the order above (text, rodata, data,
bss) by default. Linker scripts may reorder as long as per-section alignment
constraints are respected.

### 5.2 Loading (Freestanding)

M1 is a bare-metal test machine (ADR-0004 defines the memory map). No virtual
memory, page table, or load-time relocation exists:

- **VA = PA**: The virtual address in the ELF segment is the physical load
  address.
- **No dynamic linking**: All relocations are resolved statically by the
  linker. `Elf64_Rela` entries are resolved to final values in the output
  file; no `.rela` section survives into the loaded image.
- **No program headers beyond LOAD**: PHDR, DYNAMIC, INTERP, NOTE are not
  emitted for M1 freestanding binaries.

### 5.3 Entry Point

`e_entry` in the ELF header is the `_start` symbol address in `.text`. For M1
freestanding: VA = PA, so `e_entry` is also the physical entry address. It is
informational for host tooling (debuggers, ELF utilities).

[ADR-0003 §D5]

---

## §6 Artifact Pipeline

The QEMU test machine (ADR-0004) loads a flat binary — not an ELF — and always
enters at the flat binary's load base (0x80000000). `e_entry` is NOT read by
the test machine. The end-to-end pipeline is:

```
1. Assembler → ET_REL object          (relocatable, per-file)
2. Static linker: -Ttext=0x80000000 → ET_EXEC ELF binary (fully linked)
3. objcopy --output-target=binary   → flat binary (raw bytes at load base)
4. QEMU: -bios trampoline.bin -kernel flat.bin  → ROM sets SP=0x87FF0000, jumps to 0x80000000
```

The static linker and `objcopy` are LLVM tools selected at Phase 1. LLD
(`ld.lld`) handles the same-TU link; no multi-object cross-TU linking is
required for M1 tests.

[ADR-0003 §D5]

---

## Appendix: References

| § | Content | Source |
|---|---------|--------|
| 1.1 | EI_CLASS | ADR-0003 §D1 |
| 1.2 | EI_DATA | ADR-0003 §D1 |
| 1.3 | e_machine | ADR-0003 §D1 |
| 1.4 | e_flags | ADR-0003 §D1 |
| 1.5 | EI_OSABI | ADR-0003 §D1 |
| 2 | Relocation types | ADR-0003 §D2 |
| 3 | Overflow policy | ADR-0003 §D3 |
| 4 | Relaxation | ADR-0003 §D4 |
| 5 | Section alignment and loading | ADR-0003 §D5 |
| 6 | Artifact pipeline | ADR-0003 §D5 |
