# ADR-0004: M1 Bare-Metal Test Machine

Status: Accepted

## Context

QEMU Phase 3 (Scalar Core) needs a bare-metal machine to execute ISA test
vectors without an OS, SEE, or exception vectors. Every observable outcome
must be assertable via QEMU exit code or guest register state — no host log,
no stderr, no timeout.

The legacy `dadao-virt` machine (ENV-qemu-v2 `virt.c`) provides a ROM, RAM,
and UART MMIO but no exit port, no test harness protocol, and no exception
observability contract. Its reset PC is `VIRT_RAM` (kernel-loaded).

This ADR defines the M1 test machine (named `dadao-m1` to distinguish from
the legacy `dadao-virt`) with a frozen hardware model covering memory map,
reset state, exit protocol, and precise-exception observability.

## Decision

### D1. Memory Map

```
Start       End         Size    Attr    Description
0x00100000  0x0010FFFF  64 KB   ROM     Boot trampoline, constant data
0x10000000  0x10000007  8 B     MMIO    Exit port (write-only)
0x80000000  0x87FFFFFF  128 MB  RAM     Test code, stack, data
otherwise   otherwise    —       unmapped All remaining addresses
```

**ROM (0x00100000, 64 KB).** Matches the legacy virt.c ROM base and size.
Holds the reset trampoline that jumps to the test entry point in RAM.
64 KB is generous for boot code; unused ROM space reads as zero.

**RAM (0x80000000, 128 MB).** Matches legacy. Test binaries are loaded here
by `load_image_targphys`. 128 MB provides ample room for code, stack, and
scratch data. Default size matches the legacy `default_ram_size`.

**Exit port MMIO (0x10000000, 8 B).** An 8-byte write-only MMIO region at
the legacy UART base. Legacy used this address for a 16550 serial port; M1
bare-metal tests have no serial requirement, so the address is repurposed
for the exit protocol. The region is 8 bytes (one `sto` width) and must be
accessed as an 8-byte aligned store — see D3.

**Unmapped area.** Any load/store to an address outside ROM, RAM, or the
exit port MMIO region causes QEMU to exit with exit code 0x8F (unmapped
access fault). This satisfies the roadmap requirement that excluded
behaviors produce "an explicit, assertable error — not a silent no-op,
host abort, or timeout."

**Rationale for reusing UART address.** The legacy UART at 0x10000000 is
unused in M1 bare-metal (no OS, no driver, no console output). Using the
same address for the exit port avoids adding a new top-level MMIO region
and keeps the physical address map compact. A future machine for system
QEMU would reintroduce UART at a different address.

### D2. Reset Vector and Entry Point

**Reset PC (rb0).** On power-on reset, `rb0 = 0x00100000` (ROM base).
This departs from the ISA spec's `cfx_power_hypv_excp_vector` (SEE §2.1),
which is a full-system hypervisor address. For the M1 bare-metal machine:

- There is no SEE, no hypervisor, no exception vectors — the machine
  begins executing at ROM.
- The ROM trampoline performs minimal init (see D6) then jumps to the
  test entry point in RAM.
- This decision is marked as **no wiki basis, architecture custom**:
  the ISA wiki specifies the SEE context, but M1 lacks SEE entirely.

**Test program load address.** The test binary is loaded as a **flat binary**
via `load_image_targphys` at RAM base (0x80000000). ELF loading is not
required for M1 tests (no relocations needed); a flat binary is simpler
and sufficient for all test classes.

The `-kernel` command-line option loads the binary to 0x80000000. The entry
point is always 0x80000000 (no ELF entry parsing). The ROM trampoline at
0x00100000 jumps to 0x80000000 after init.

**RD registers reset.** All 64 RD registers are zero (`rd0` is already
hardwired zero; `rd1`–`rd63` = 0). This eliminates test non-determinism
from unknown initial state.

**RB registers reset.** `rb0 = 0x00100000` (reset vector, see above).
`rb1`–`rb63` = 0. `rb0[63:48]` is always 0 (per ISA spec).

**RA registers reset.** All 64 RA registers are zero (`ra[63:48]` = 0,
all entries invalid). This matches the process-entry initialization in the
ISA spec (`DADAO-11-AEE` §返回地址栈) and is appropriate for bare-metal entry.

**RF registers.** The RF bank is excluded from M1 (Scope Matrix). At reset,
all `rf1`–`rf63` = 0; `rf0` is initialized to `0x7FF800007FC00000`
(matching the wiki rf0 layout: bits[63:51]=0b0_1111_1111_1111_1 = double
QNaN marker, bits[31:22]=0b0_1111_1111_11 = single QNaN marker, all other
bits 0). This ensures no floating-point state causes spurious faults.

### D3. Exit Port Protocol

**Address.** `0x10000000`, 8-byte aligned.

**Width.** Exactly 8 bytes (one `sto` instruction). Writes of other widths
to this address trigger ILLI (exit code 0x82): `stb`, `stw`, `stt` are
valid opcodes, but the exit port MMIO enforces an 8-byte access constraint.
This is an illegal operand/width violation (ILLI), not an unrecognized
encoding (UNDI, which is reserved for opcode/minor-opcode cells left blank
in the ISA table).

**Encoding.**

| Value     | Meaning                |
|-----------|------------------------|
| 0x0000000000000000 | PASS — test completed successfully |
| 0x0000000000000001 – 0x000000000000007F | FAIL — test-specific error code |
| ≥ 0x80    | Reserved for future use (currently treated as FAIL) |

The upper 56 bits are available for encoding test identifiers or sub-case
numbers if desired, but the harness only checks the low byte for pass/fail.
Convention: bits[7:0] = exit classification; bits[63:8] = test number or
debug info.

**QEMU behavior.** On an 8-byte aligned store to 0x10000000, QEMU:
1. Reads the written 8-byte value from the guest memory write.
2. Sets the QEMU process exit code to the low byte of the written value.
3. Requests a clean shutdown with the exit code propagated to the host
   process (`$?`). The exact shutdown API — e.g.,
   `qemu_system_shutdown_request_with_code(reason, code)` or equivalent —
   is confirmed when the Phase 1 QEMU baseline commit is locked (ADR-0005/
   ADR-0006). The implementation must verify `$? == written_value & 0xFF`
   for values 0, 1, 0x7F, 0x81, and 0x8F as part of Phase 3 machine bringup.

**Zero host dependency.** The test harness runs `qemu-system-dadao -machine
m1 -kernel test.bin`, checks `$?`. Exit code 0 = pass, non-zero = fail or
fault (see D4/D5 for fault codes). No log parsing, no timeout, no stderr.

### D4. MALIGN Observable Behavior

The ISA spec (§3.1–§3.4) defines MALIGN as a precise exception: no
destination register is written, PC points to the faulting instruction.
Since the M1 test machine has no OS exception vectors, this ADR chooses
**option (b): QEMU directly exits with a specific fault code**.

**Fault exit code.**

| Condition | Exit code | Meaning |
|-----------|-----------|---------|
| Misaligned 16-bit load/store | 0x81 | Width=2, boundary misaligned |
| Misaligned 32-bit load/store | 0x81 | Width=4, boundary misaligned |
| Misaligned 64-bit load/store | 0x81 | Width=8, boundary misaligned |

All misalignment widths produce the same exit code (0x81). The test
structure encodes the expected width and offset in the test binary, so
the harness identifies which misalignment was intended.

**Guest-visible state at exit.**
- **Precision confirmed:** the destination register is NOT written (RD or
  RB target unchanged). The source register snapshot may or may not have
  been read, but no register update is committed.
- **Faulting PC:** `rb0` at exit is the address of the faulting instruction
  (not advanced past it). The harness can dump register state if the exact
  PC needs verification; for routine pass/fail the exit code suffices.
- **Memory:** no store to memory is committed.

**Rationale for exit-over-handler.** The alternative (writing fault info
to a fixed memory address then jumping to a handler) would require defining
a handler address, a fault info structure layout, and a separate return
mechanism — all of which depend on an exception ABI that M1 does not have.
Direct exit is simpler, satisfies the testability requirement, and avoids
presupposing a future exception model.

### D5. ILLI/UNDI Observable Behavior

Same structure as D4: QEMU exits with a fault code on detection, with no
destination register committed.

**ILLI (illegal instruction) exit code: 0x82.**
Triggers include:
- `rd0` as destination where illegal (§2.6.1)
- `rb0` as destination (§2.6.2)
- `immu6 = 0` for multi-register instructions (§2.6.3)
- Register bank overflow (`first_reg + immu6 > 64`, §2.6.3)
- Divide-by-zero (§3.7)
- `divs INT64_MIN ÷ -1` (§3.7)
- `unimp` instruction (§6.2)
- **Non-zero SBZ fields** (see below)

**UNDI (undefined instruction) exit code: 0x83.**
Triggers include:
- Reserved opcode (blank opcode table cells, §2.5)
- Reserved MISC-Norm/RF/AMO minor-opcodes (§2.5)

**SBZ behavior: ILLI (exit code 0x82).**
No wiki basis; this ADR makes the decision. Rationale:

- SBZ fields occur within a known, valid opcode — the instruction format
  is recognized, but a field that should be zero is non-zero.
- This is analogous to an illegal operand (ILLI), not an unrecognized
  encoding (UNDI). The assembler could statically reject SBZ violations
  (just as it rejects `rd0` destinations), matching the "static" language
  in §2.6.
- UNDI is reserved for opcode/minor-opcode cells that the architecture
  has explicitly left blank. SBZ is a field constraint on a defined cell.

**Guest-visible state at exit (both ILLI and UNDI).**
- Destination registers not written (precise, per §2.7).
- `rb0` = address of the faulting instruction.
- No memory committed.

**Distinguishing from normal exit.** Normal test exit writes to the exit
port MMIO and produces code 0x00 (pass) or 0x01–0x7F (fail). Fault exits
produce 0x81–0x8F. The harness checks: if `$? ≥ 0x80`, the test is a fault
test; compare `$?` against the expected fault code. If `$?` is 0x00 or
0x01–0x7F but the test expected a fault, the harness reports failure.

### D6. Test Signature Specification

**Semantic test pattern.** A test program that verifies instruction
semantics. Uses concrete register names: `rb1` = stack pointer (per ABI),
`rb16` = exit port address, `rd16` = result, `rd17`/`rd18` = temporaries.

```asm
; --- Entry: rb0=current PC, rb1-rb63=0, rd0=0, all others=0 ---
; (ROM trampoline has set rb1; if no ROM, set here)

; 1. Construct exit port address in rb16 = 0x10000000
setzw  rb16, 1, 0x1000   ; rb16 = 0x0000_0000_1000_0000

; 2. Set up test input: rd17 = 0, rd18 = 42
setzw  rd18, 0, 42       ; rd18 = 42

; 3. Execute instruction under test: rd16 = rd17 + 42
addi   rd16, rd17, 42

; 4. Check result: rd16 must equal 42
;    Use rd19 as destination (never rd0: ILLI)
addi   rd19, rd18, 0           ; rd19 = expected (42)
cmps   rd19, rd16, 0           ; rd19 = rd16 - rd19 (0 if match)
brnz   rd19, fail              ; non-zero → mismatch

; 5. Pass: write 0 to exit port
setzw  rd16, 0, 0              ; rd16 = 0 (PASS)
sto    rd16, rb16, 0           ; write to exit port

; 6. Fail: write 1
fail:
setzw  rd16, 0, 1              ; rd16 = 1 (FAIL)
sto    rd16, rb16, 0
```

The test binary is a flat binary loaded at 0x80000000. The entry point
label (`_start`) is at 0x80000000 in the linker script.

**Fault test pattern.** A test program that expects a specific fault.
All registers start at 0 (from ROM trampoline + D2 reset):

```asm
; 1. Construct exit port address in rb16 = 0x10000000
setzw  rb16, 1, 0x1000   ; rb16 = 0x1000_0000

; 2. Construct aligned base in rb17 = 0x80000000 (RAM base)
setzw  rb17, 1, 0x8000   ; rb17 = 0x8000_0000

; 3. Trigger expected fault: misaligned 64-bit load (offset=1 byte)
ldo    rd16, rb17, 1     ; effective address = 0x80000001 → MALIGN (exit 0x81)

; 4. If execution reaches here, fault did NOT occur → FAIL
setzw  rd16, 0, 1
sto    rd16, rb16, 0     ; write FAIL (code 1)
```

The harness expects exit code 0x81 (MALIGN). Exit code 0 or 1–0x7F
indicates the fault did not occur.

**ROM trampoline.** The 64 KB ROM at 0x00100000 holds a minimal boot stub.
The trampoline is a separate small flat binary loaded via `-bios`; the test
binary is loaded via `-kernel` at 0x80000000. This is the **frozen Phase 3
boot protocol**: both `-bios` and `-kernel` are always supplied.

```asm
; ROM trampoline — flat binary linked at 0x00100000, loaded by QEMU -bios.
; On entry: rb0=0x00100000 (reset vector), all other regs=0 (per D2).
.org 0x00100000

; 1. Set rb1 (stack pointer / rbsp) near RAM top
;    setzw rb1, ww=1, immu16 sets bits[31:16]; all other wydes → 0
;    Result: rb1 = 0x0000_0000_87FF_0000 = ~128MB below RAM end
setzw  rb1, 1, 0x87FF    ; rb1 = 0x87FF_0000

; 2. Construct RAM entry address in rb2 = 0x80000000
;    0x80000000 has wyde-1 = 0x8000, all others = 0
setzw  rb2, 1, 0x8000    ; rb2 = 0x8000_0000

; 3. Absolute jump to RAM entry (rrii format; PCREL24 cannot span 128 MB gap)
;    jump rbha, rdhb, imms12: PC = rbha + rdhb + sext_12(imms12)×4
;    rd0 is always 0, imms12=0 → PC = rb2 + 0 + 0 = 0x80000000
jump   rb2, rd0, 0       ; PC ← 0x80000000
```

If `-bios` is not provided, QEMU initializes ROM to zero (reads as `swym`
nop instructions), eventually reaching the unmapped area beyond ROM, which
exits with code 0x8F. The harness must always supply both flags.

Entry convention at `_start` (0x80000000), after ROM trampoline:
- `rb0` = 0x80000000 + 4 (next-PC after first RAM instruction, per ISA)
- `rb1` = 0x87FF0000 (stack pointer, set by trampoline)
- `rb2` = 0x80000000 (used by jump, may be reused by `_start`)
- All other RD, RB, RA registers = 0 (per D2 reset + trampoline)

The test program's `_start` may assume this state.

### Summary of Exit Code Layout

| Range         | Source     | Meaning        |
|---------------|------------|----------------|
| 0x00          | Exit port  | PASS           |
| 0x01 – 0x7F   | Exit port  | FAIL           |
| 0x80          | —          | Reserved       |
| 0x81          | QEMU fault | MALIGN         |
| 0x82          | QEMU fault | ILLI           |
| 0x83          | QEMU fault | UNDI           |
| 0x84          | QEMU fault | IALIGN         |
| 0x85          | QEMU fault | RASOF          |
| 0x86          | QEMU fault | RASUF          |
| 0x87 – 0x8E   | QEMU fault | Reserved       |
| 0x8F          | QEMU fault | Unmapped access|

## Consequences

- **SBZ behavior closed.** Non-zero SBZ fields now definitively trigger
  ILLI (exit code 0x82). The entry in `docs/open-spec-issues.md` can be
  marked "Resolved by ADR-0004".

- **Hardware reset frozen.** RD, RB, RA, and RF reset values are fully
  specified (D2). The C-18 open issue in `contracts/isa/spec.md` Appendix
  C has M1-specific answers; the full-system answer remains open.

- **Test harness contract.** Any Phase 3 or Phase 4 test harness can be
  built on `$?` inspection alone. No log parsing or timeout logic is
  needed for pass/fail/fault assertion.

- **Diagnostic limitation.** The exit code encodes fault type but not the
  exact faulting address or operand values. Tests that need precise PC
  verification must either (a) use the test structure to infer it, or
  (b) dump register state via the harness using QEMU's `-d cpu` or GDB
  stub. This is acceptable for M1: encoding/legality/semantic/boundary
  tests have known expected PC from the test binary layout.

- **Deviates from ISA on reset rb0.** The ISA's `cfx_power_hypv_excp_vector`
  is an SEE concept; M1 has no SEE. This is explicitly noted in D2.

- **SBZ = ILLI is a prospective decision.** If the wiki later specifies
  SBZ = UNDI, this ADR must be updated. The decision is recorded with
  "no wiki basis" annotation.

- **Unmapped access behavior is architecture custom.** The ISA does not
  specify physical address map behavior; this is machine-dependent.
