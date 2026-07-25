# ISA Contract — DADAO SimRISC (M1 Scope)

**Version**: 0.4.0
**Source**: Wiki commit `9f378f4426e131903d60a208766086ae74a53c89` (SimRISC 0.4.1)
**Status**: Accepted (2026-06-29)

M1 scope is defined by `code-agent/designs/0002-detailed-roadmap.md` §Scope
Matrix. This document does not duplicate that list; excluded behaviors are
annotated inline.

---

## §1 Register Model

[wiki §DADAO-11-AEE-应用程序运行环境.md §寄存器]

### 1.1 Bank Overview

Four register banks, each 64 registers of 64 bits. Register numbers are encoded
in 6-bit fields.

| Bank | Name              | Count | Width | Purpose                     |
|------|-------------------|-------|-------|-----------------------------|
| RD   | Data registers    | 64    | 64    | Scalar integer operands     |
| RB   | Base registers    | 64    | 64    | Address base values         |
| RF   | Float registers   | 64    | 64    | Floating-point operands     |
| RA   | Return address    | 64    | 64    | Return address stack        |

### 1.2 RD — Data Registers

- 64 registers `rd0`–`rd63`, each 64 bits.
- `rd0` is hardwired to zero. Reads always return 0. Encoding `rd0` as a
  destination where it is not legal → **ILLI** (see §2.6.1). The only legal [wiki §SimRISC-01 §rd0 为目的寄存器约定]
  destination-position uses of `rd0` are: dual-destination instructions (result
  half discarded) and `ret rdha=rd0` (return value discarded); in those cases
  the write is a no-op.
- Reserved register names: none beyond `rd0`.

### 1.3 RB — Base Registers

- 64 registers `rb0`–`rb63`, each 64 bits.
- `rb0` holds the address of the instruction immediately after the currently
  executing instruction (i.e., `current_PC + 4`). Hardware-maintained; software
  cannot write to `rb0`. Any instruction that encodes `rb0` as a destination
  (rbha=rb0 or rbhb=rb0 where rb0 would be written) → **ILLI** (see §2.6.2). [wiki §SimRISC-02 §存取类]
  `rb0[63:48]` is always zero. [wiki §DADAO-11-AEE §基址寄存器]
- Effective address width is 48 bits (bits[47:0]). Bits[63:48] are ignored in
  address calculations; register write-back behavior depends on instruction
  class (see §4). [wiki §SimRISC-02 §地址类指令]
- Hardware reset value for `rb0`: `cfx_power_hypv_excp_vector` (SEE §2.1).
  [C-18a — PARTIALLY KNOWN; full hardware reset state see Appendix C C-18b;
  M1 test-machine init defined by ADR-0004]
- `rb0[63:48]` is always 0. Arithmetic results that would produce non-zero
  bits[63:48] are discarded (48-bit wrap). [wiki §SimRISC-02 §控制流指令]

### 1.4 RF — Float Registers

- 64 registers `rf0`–`rf63`, each 64 bits.
- `rf0` is the floating-point status register.
- RF execution is excluded from M1 (see §7). The register model is documented
  here for completeness.

### 1.5 RA — Return Address Stack

[wiki §DADAO-11-AEE §返回地址栈]

- 64 registers `ra0`–`ra63`, each 64 bits.
- `ra1`–`ra63` form the Register Return Address Stack (RegRAS). `ra63` is the
  stack top.
- Each RA register (except `ra0`) splits as:
  - Bits[63:48]: reference count (> 0 = valid, 0 = invalid)
  - Bits[47:0]: return address (48-bit PC value)
- `ra0` low 48 bits: MemRAS pointer (0 = RegRAS only). Bits[63:48]: push/pop
  count (16-bit unsigned, initial 0).
- M1 operates exclusively in RegRAS-only mode (`ra0` low = 0). MemRAS is
  excluded.
- Process-entry initialization: all RA registers zero (`ra[63:48]` = 0,
  all invalid). [wiki §DADAO-11-AEE L185]
- Hardware reset: [OPEN C-18 — process-entry init applies after OS setup;
  power-on reset values not fully specified].

---

## §2 Instruction Encoding

[wiki §SimRISC-00-指令系统设计.md §指令设计]

### 2.1 Instruction Width, Endianness, and Alignment

- Each instruction is exactly 32 bits (4 bytes).
- Instructions must be 4-byte aligned. If `PC[1:0] ≠ 00`, an **IALIGN** [wiki §DADAO-12-SEE §精确异常]
  exception is raised (precise, instruction not fetched).
  [wiki §SimRISC-00 L13]
- Instruction fetch is **big-endian**: bits[31:24] at the lowest address,
  bits[7:0] at the highest address. [wiki §SimRISC-00 L15]
- Data access is also big-endian. [wiki §DADAO-21-ABI §数据表示]

### 2.2 Field Layout

```
31      24 23   18 17   12 11    6 5      0
+---------+-------+-------+-------+-------+
|  op[8]  | ha[6] | hb[6] | hc[6] | hd[6] |
+---------+-------+-------+-------+-------+
```

- `op[7:0]` (bits 31–24): Major opcode.
- `ha[5:0]` (bits 23–18): Minor opcode or first operand.
- `hb[5:0]` (bits 17–12): Second operand.
- `hc[5:0]` (bits 11–6): Third operand.
- `hd[5:0]` (bits 5–0): Fourth operand.

Operand type letters:
- `o`: 6-bit minor opcode in `ha`
- `r`: 6-bit register number
- `i`: signed or unsigned immediate
- `w`: wyde-position (`hb[5:4]`) + 4-bit high immediate (`hb[3:0]`)
- `z`: must be zero (SBZ) [wiki §SimRISC-04] [spec-decision: ADR-0004 D5]

### 2.3 Operand Format Types

| Format | Meaning                    | Field usage                    |
|--------|----------------------------|--------------------------------|
| `iiii` | 24-bit immediate           | `ha:hb:hc:hd` = imm24         |
| `oiii` | minor-op + 18-bit imm      | `ha`=minor-op; `hb:hc:hd`=imm |
| `orii` | minor-op + reg + 12-bit imm| `ha`=minor-op; `hb`=reg; `hc:hd`=imm |
| `orri` | minor-op + 2 regs + 6-bit  | `ha`=minor-op; `hb`=reg1; `hc`=reg2; `hd`=imm |
| `orrr` | minor-op + 3 regs          | `ha`=minor-op; `hb`=dest; `hc:hd`=src |
| `rrrr` | 4 regs                     | `ha`=rd1; `hb`=rd2; `hc`=rd3; `hd`=rd4 |
| `rrri` | 3 regs + 6-bit imm         | `ha`=reg1; `hb`=reg2; `hc`=reg3; `hd`=imm |
| `rrii` | 2 regs + 12-bit imm        | `ha`=reg1; `hb`=reg2; `hc:hd`=imm |
| `riii` | 1 reg + 18-bit imm         | `ha`=reg; `hb:hc:hd`=imm      |
| `rwii` | reg + wyde-pos + imm16     | `ha`=reg; `hb[5:4]`=wyde-pos; `hb[3:0]`=imm[15:12]; `hc`=imm[11:6]; `hd`=imm[5:0] |
| `ciii` | cfxcode + 18-bit imm       | `ha`=cfxcode; `hb:hc:hd`=imm  |
| `crrr` | cfxcode + 3 regs           | `ha`=cfxcode; `hb`=reg1; `hc`=reg2; `hd`=reg3 |
| `crii` | cfxcode + reg + 12-bit imm | `ha`=cfxcode; `hb`=reg; `hc:hd`=imm |

### 2.4 Immediate Formats and Ranges

All signed immediates are two's complement. Multi-field immedates are
concatenated high-to-low: `hb[5:0] → hc[5:0] → hd[5:0]`.
[wiki §SimRISC-00 §指令域说明 末行]

| Mnemonic | Width | Signed?       | Decimal range                | Fields               |
|----------|-------|---------------|------------------------------|----------------------|
| imms24   | 24    | Signed        | -8388608 to 8388607          | ha:hb:hc:hd          |
| imms18   | 18    | Signed        | -131072 to 131071            | hb:hc:hd             |
| imms12   | 12    | Signed        | -2048 to 2047                | hc:hd                |
| immu18   | 18    | Unsigned      | 0 to 262143                  | hb:hc:hd             |
| immu16   | 16    | Unsigned      | 0 to 65535                   | hb[3:0]:hc:hd        |
| immu12   | 12    | Unsigned      | 0 to 4095                    | hc:hd                |
| immu6    | 6     | Unsigned      | 0 to 63                      | hd                   |
| wyde-pos | 2     | Unsigned      | 0 to 3                       | hb[5:4]              |

Note: `immu6` for multi-load/store and block-copy has effective range 1–63;
  value 0 triggers ILLI (see §2.6). [wiki §SimRISC-01 §存取RD寄存器]

### 2.5 Reserved Encoding Behavior

All opcode table cells marked as reserved (blank in opcode tables) trigger the
**UNDI** exception when executed (precise, no architectural side effect). [wiki §SimRISC-00 §SimRISC QFC]
[wiki §SimRISC-00 §SimRISC QFC 表头注: "执行保留编码触发 UNDI 异常"]

All `ha` minor-opcode encodings not listed in MISC-Norm/RF/AMO subtables are
also reserved and trigger UNDI. [wiki §SimRISC-00 §SimRISC QFC]

### 2.6 Instruction Legality

Unified rules for all M1 instructions. Violations are **static**: the
assembler must reject them. If a hand-encoded instruction reaches execution [wiki §SimRISC-02 §存取类]
with an illegal operand, the hardware raises **ILLI** (precise, no side [wiki §SimRISC-01 §rd0 为目的寄存器约定]
effect). [wiki §SimRISC-01 开头约定行; §SimRISC-02 开头约定行]

#### 2.6.1 RD Destination Rules

The destination register field varies by instruction format. Binding the
constraint to the correct field:

- **`rdha`-destination instructions** (ld*, addi, cmps(i)/cmpu(i),
  orw/andnw/setzw/setow): `rdha = rd0` → ILLI. [wiki §SimRISC-01 §rd0 为目的寄存器约定]
  Exception: `ret` with `rdha = rd0` is legal (return value discarded).
  [wiki §SimRISC-01 L7]
- **Branch condition source** (brn/brnn/brz/brnz/brp/brnp): `rdha` is read as
  the condition input, not a destination. `rdha = rd0` is legal (reads as 0;
  e.g., `brz rd0` is always taken, `brnz rd0` never taken).
- **`rdhb`-destination instructions** (`orrr`/`orri` format: and/orr/xor/xnor,
  shlu/shrs/shru, exts/extz — register form; cmps(r)/cmpu(r); rb2rd; cmp-rb;
  csn/csz/csp): destination is `rdhb`, so `rdhb = rd0` → ILLI. [wiki §SimRISC-01 §rd0 为目的寄存器约定]
  [wiki §SimRISC-01 L87]
- **`rdhc`-destination instructions** (cseq, csne): destination is `rdhc`, so
  `rdhc = rd0` → ILLI. [wiki §SimRISC-01 §rd0 为目的寄存器约定]
- **Store data source** (st*, stm*): `rdha` is the data register, not a
  destination — but `rdha = rd0` → ILLI. Storing from rd0 is not legal. [wiki §SimRISC-01 §rd0 为目的寄存器约定]
  [wiki §SimRISC-01 L37]
- **Dual-destination instructions** (add, sub, muls, mulu, divs, divu):
  - At most one of `rdha, rdhb` may be `rd0` (discards that half-result).
  - `rdha` and `rdhb` must not be the same non-`rd0` register. [wiki §SimRISC-01 §加减操作]
  - Violation → ILLI. [wiki §SimRISC-01 §加减操作]
  [wiki §SimRISC-01 L147, L195]

#### 2.6.2 RB Destination Rules

The destination RB field also varies by format:

- **`rrii`/`riii`-format RB destinations** (ldo-rb, addi-rb, rela): destination
  is `rbha` → `rbha = rb0` → ILLI. [wiki §SimRISC-02 L5]
- **`orrr`/`orri`-format RB destinations** (add-rb, sub-rb, rd2rb, rb2rb):
  destination is `rbhb` → `rbhb = rb0` → ILLI. [wiki §SimRISC-02 L5]

#### 2.6.3 Multi-Register Range Rules

For all multi-register instructions (ldm/stm*, rd2rd, rd2rb, rb2rd, rb2rb,
rd2ra, ra2rd, ldmo-rb, stmo-rb, ldmo-ra, stmo-ra):
- `immu6 = 0` → ILLI. [wiki §SimRISC-01 §存取RD寄存器]
- `first_reg + immu6 > 64` (exceeds bank boundary) → ILLI. No wrap, no [wiki §SimRISC-01 §存取RD寄存器]
  truncation.
  [wiki §SimRISC-01 L63–L65; §SimRISC-02 L41–L45, L60–L62, L85–L89]

#### 2.6.4 SBZ Fields

Fields marked SBZ (Should Be Zero) in encoding tables must be zero in valid [wiki §SimRISC-04]
encodings. Non-zero SBZ: [OPEN — behavior not specified in wiki; suggested:
ILLI or UNDI]. [spec-decision: ADR-0004 D5]

### 2.7 Instruction Execution Model

- **Source snapshot for add/sub**: All source registers are read before any
  destination is written; src/dst overlap uses the pre-execution value.
  [wiki §SimRISC-01 L138]
- **Source snapshot for mul/div**: Same rule; dual destinations computed from
  the same snapshot, written atomically. [wiki §SimRISC-01 L183, L203]
- **Multi-register sequential order**: Each element of a multi-register
  operation is processed in increasing-register order, element read-then-write
  (per-element overlap well-defined). Base register snapshotted before loop.
  [wiki §SimRISC-01 §SimRISC-02, respective instruction sections]
- **Exceptions during execution**: All ISA-defined exceptions (ILLI, UNDI, [wiki §DADAO-12-SEE §精确异常]
  MALIGN, IALIGN, RASOF, RASUF) are **precise**: the faulting instruction [wiki §DADAO-12-SEE §精确异常]
  has no architectural side effect (destination registers and memory are not
  updated; RA is not modified; PC points to the faulting instruction).
  [wiki §DADAO-11-AEE L183; §SEE L248–L253]

### 2.8 M1-Covered Opcode Map

Row-by-row reference. Entries not listed are reserved (UNDI) or excluded (§7). [wiki §SimRISC-00 §SimRISC QFC]

| `op[7:3]` | `op[2:0]` | Instruction(s)                        | Format   |
|-----------|-----------|---------------------------------------|----------|
| 00010     | 000       | MISC-Norm (subtable, see §2.8.1)      | —        |
| 00010     | 010       | cmps-rrii                             | rrii     |
| 00010     | 011       | cmpu-rrii                             | rrii     |
| 00010     | 100       | orw-rwii (RD)                         | rwii     |
| 00010     | 101       | andnw-rwii (RD)                       | rwii     |
| 00010     | 110       | setzw-rwii (RD)                       | rwii     |
| 00010     | 111       | setow-rwii (RD)                       | rwii     |
| 00011     | 001       | addi-rrii (RD)                        | rrii     |
| 00011     | 010       | add-rrrr (RD)                         | rrrr     |
| 00011     | 011       | sub-rrrr (RD)                         | rrrr     |
| 00011     | 100       | muls-rrrr                             | rrrr     |
| 00011     | 101       | mulu-rrrr                             | rrrr     |
| 00011     | 110       | divs-rrrr                             | rrrr     |
| 00011     | 111       | divu-rrrr                             | rrrr     |
| 00100     | 000       | csn-rrrr                              | rrrr     |
| 00100     | 010       | csz-rrrr                              | rrrr     |
| 00100     | 100       | csp-rrrr                              | rrrr     |
| 00100     | 110       | cseq-rrrr                             | rrrr     |
| 00100     | 111       | csne-rrrr                             | rrrr     |
| 00101     | 000       | brn-riii                              | riii     |
| 00101     | 001       | brnn-riii                             | riii     |
| 00101     | 010       | brz-riii                              | riii     |
| 00101     | 011       | brnz-riii                             | riii     |
| 00101     | 100       | brp-riii                              | riii     |
| 00101     | 101       | brnp-riii                             | riii     |
| 00101     | 110       | breq-rrii                             | rrii     |
| 00101     | 111       | brne-rrii                             | rrii     |
| 00110     | 000–111   | RD load signed (ldbs…ldmo)            | rrii/rrri|
| 00111     | 000–111   | RD store (stb…stmo)                   | rrii/rrri|
| 01000     | 000–111   | RD load unsigned + RB load            | rrii/rrri|
| 01001     | 000       | rela-riii                             | riii     |
| 01001     | 001       | addi-rb-rrii                          | rrii     |
| 01001     | 011       | sto-rb-rrii                           | rrii     |
| 01001     | 100       | orw-rb-rwii                           | rwii     |
| 01001     | 101       | andnw-rb-rwii                         | rwii     |
| 01001     | 110       | setzw-rb-rwii                         | rwii     |
| 01001     | 111       | stmo-rb-rrri                          | rrri     |
| 01100     | 100       | jump-iiii                             | iiii     |
| 01100     | 101       | jump-rrii                             | rrii     |
| 01100     | 111       | ldmo-ra-rrri                          | rrri     |
| 01101     | 100       | call-iiii                             | iiii     |
| 01101     | 101       | call-rrii                             | rrii     |
| 01101     | 110       | ret-riii                              | riii     |
| 01101     | 111       | stmo-ra-rrri                          | rrri     |

#### 2.8.1 MISC-Norm Subtable (op[7:3]=00010, op[2:0]=000)

`ha[5:0]` selects the operation:

| `ha[5:0]` | Mnemonic    | Format | M1? |
|-----------|-------------|--------|-----|
| 00_0000   | swym        | oiii   | Yes |
| 00_1000   | and         | orrr   | Yes |
| 00_1001   | orr         | orrr   | Yes |
| 00_1010   | xor         | orrr   | Yes |
| 00_1011   | xnor        | orrr   | Yes |
| 01_0001   | shlu (reg)  | orrr   | Yes |
| 01_0010   | shrs (reg)  | orrr   | Yes |
| 01_0011   | shru (reg)  | orrr   | Yes |
| 01_0100   | exts (reg)  | orrr   | Yes |
| 01_0101   | extz (reg)  | orrr   | Yes |
| 01_1001   | shlu (imm)  | orri   | Yes |
| 01_1010   | shrs (imm)  | orri   | Yes |
| 01_1011   | shru (imm)  | orri   | Yes |
| 01_1100   | exts (imm)  | orri   | Yes |
| 01_1101   | extz (imm)  | orri   | Yes |
| 10_0100   | cmps (reg)  | orrr   | Yes |
| 10_0101   | cmpu (reg)  | orrr   | Yes |
| 10_1000   | rd2rd       | orri   | Yes |
| 10_1001   | rd2rb       | orri   | Yes |
| 10_1010   | rb2rd       | orri   | Yes |
| 10_1011   | rb2rb       | orri   | Yes |
| 10_1101   | cmp-rb      | orrr   | Yes |
| 10_1110   | add-rb      | orrr   | Yes |
| 10_1111   | sub-rb      | orrr   | Yes |
| 11_0001   | rd2ra       | orri   | [Excluded — see §7] |
| 11_0010   | ra2rd       | orri   | [Excluded — see §7] |
| 11_1111   | unimp       | oiii   | Yes |

All other `ha` values within MISC-Norm → UNDI. [wiki §SimRISC-00 §SimRISC QFC]

---

## §3 Scalar Integer Instructions (RD)

[wiki §SimRISC-01-数据类指令.md]

### 3.1 RD Single Load (rrii)

```
ldbs    rdha, rbhb, imms12      ; byte, sign-extend
ldbu    rdha, rbhb, imms12      ; byte, zero-extend
ldws    rdha, rbhb, imms12      ; wyde (16-bit), sign-extend
ldwu    rdha, rbhb, imms12      ; wyde, zero-extend
ldts    rdha, rbhb, imms12      ; tetra (32-bit), sign-extend
ldtu    rdha, rbhb, imms12      ; tetra, zero-extend
ldo     rdha, rbhb, imms12      ; octa (64-bit)
```

Encoding: §2.8 row 00110 (signed) / 01000 (unsigned). Format `rrii`.
- `op` = per opcode map; `ha` = rdha; `hb` = rbhb; `hc:hd` = imms12.

EA: `ea[47:0] = (rbhb[47:0] + sext_12(imms12)) mod 2^48`
Semantic: `rdha[63:0] = extend_N(memory_be[ea : ea+N-1])`
- N=1→byte, N=2→wyde, N=4→tetra, N=8→octa.
- Signed loads: sign-extend to 64. Unsigned loads: zero-extend to 64.
- `ldo`: full 64-bit load, no extension.

Alignment:
| Width | Mnemonic      | Min alignment | Unaligned |
|-------|---------------|---------------|-----------|
| 8-bit | ldbs, ldbu    | 1             | No fault  |
| 16-bit| ldws, ldwu    | 2             | MALIGN    | [wiki §SimRISC-01 §对齐要求]
| 32-bit| ldts, ldtu    | 4             | MALIGN    | [wiki §SimRISC-01 §对齐要求]
| 64-bit| ldo           | 8             | MALIGN    | [wiki §SimRISC-01 §对齐要求]

MALIGN is precise: no register write, PC at faulting instruction. [wiki §SimRISC-01 §对齐要求]
[wiki §SimRISC-01 L35; §SEE L248–L253]

Legality: `rdha ≠ rd0` (else ILLI). [wiki §SimRISC-01 L37]

### 3.2 RD Single Store (rrii)

```
stb     rdha, rbhb, imms12      ; store bits[7:0]
stw     rdha, rbhb, imms12      ; store bits[15:0]
stt     rdha, rbhb, imms12      ; store bits[31:0]
sto     rdha, rbhb, imms12      ; store bits[63:0]
```

Encoding: §2.8 row 00111. Format `rrii`.

EA: `ea[47:0] = (rbhb[47:0] + sext_12(imms12)) mod 2^48`
Semantic: `memory_be[ea : ea+N-1] = rdha[N×8-1 : 0]`

Alignment: same as loads (MALIGN if violated). [wiki §SimRISC-01 §对齐要求]

Legality: `rdha ≠ rd0` (ILLI; storing from rd0 is not legal). [wiki §SimRISC-01 L37]

### 3.3 RD Multi Load (rrri)

```
ldmbs   rdha, rbhb, rdhc, immu6 ; multi byte, sign-extend
ldmbu   rdha, rbhb, rdhc, immu6 ; multi byte, zero-extend
ldmws   rdha, rbhb, rdhc, immu6 ; multi wyde, sign-extend
ldmwu   rdha, rbhb, rdhc, immu6 ; multi wyde, zero-extend
ldmts   rdha, rbhb, rdhc, immu6 ; multi tetra, sign-extend
ldmtu   rdha, rbhb, rdhc, immu6 ; multi tetra, zero-extend
ldmo    rdha, rbhb, rdhc, immu6 ; multi octa
```

Encoding: §2.8 row 00110 or 01000. Format `rrri`.
- `op` per opcode map; `ha`=rdha; `hb`=rbhb; `hc`=rdhc; `hd`=immu6.

EA for register i: `ea_i = (rbhb[47:0] + rdhc[47:0] + i × N) mod 2^48`
where N = element size in bytes.
Registers: `rd(ha)` through `rd(ha + count - 1)`.

Processing: ordered by increasing i, each element read-then-write (overlap
well-defined). Address uses original `rdhc` (snapshotted before any write).
[wiki §SimRISC-01 L68]

Alignment: same element rules as single load.

Legality: `rdha ≠ rd0`; `immu6 ∈ [1,63]`; `rdha + immu6 ≤ 64` (all → ILLI). [wiki §SimRISC-01 §存取RD寄存器]
[wiki §SimRISC-01 L63–L66]

### 3.4 RD Multi Store (rrri)

```
stmb    rdha, rbhb, rdhc, immu6
stmw    rdha, rbhb, rdhc, immu6
stmt    rdha, rbhb, rdhc, immu6
stmo    rdha, rbhb, rdhc, immu6
```

Encoding: §2.8 row 00111. Format `rrri`.

EA for register i: same as multi load.
Semantic: `memory_be[ea_i : ea_i+N-1] = rd(ha+i)[N×8-1 : 0]`

Legality: `rdha ≠ rd0`; `immu6 ∈ [1,63]`; `rdha + immu6 ≤ 64` (all → ILLI). [wiki §SimRISC-01 §存取RD寄存器]
[wiki §SimRISC-01 L63–L66]

### 3.5 RD Arithmetic — add/sub (rrrr)

```
add     rdha, rdhb, rdhc, rdhd  ; rdha:rdhb = rdhc + rdhd
sub     rdha, rdhb, rdhc, rdhd  ; rdha:rdhb = rdhc - rdhd
```

Encoding: §2.8 row 00011 col 010/011. Format `rrrr`.
- `ha`=rdha; `hb`=rdhb; `hc`=rdhc; `hd`=rdhd.

Semantic:
1. Sign-extend both `rdhc` and `rdhd` from 64 to 128 bits.
2. Perform 128-bit addition/subtraction.
3. `rdha = result[127:64]`; `rdhb = result[63:0]`.

Source snapshot: rdhc, rdhd read before any write. [wiki §SimRISC-01 L138]

Legality: `rdha` and `rdhb` may each be `rd0` individually (discarding that
half), but not both simultaneously, and not the same non-zero register. ILLI [wiki §SimRISC-01 §加减操作]
if violated. [wiki §SimRISC-01 L147]

### 3.6 RD addi (rrii)

```
addi    rdha, rdhb, imms12      ; rdha = rdhb + sext(imms12)
```

Encoding: §2.8 row 00011 col 001. Format `rrii`.
- `ha`=rdha; `hb`=rdhb; `hc:hd`=imms12.

Semantic: 64-bit addition. `rdha[63:0] = rdhb[63:0] + sext_12(imms12)`.
No overflow detection (overflow is architectural; software must check). [spec-decision: ADR-0004]

Legality: `rdha ≠ rd0` (ILLI). [wiki §SimRISC-01 §rd0 为目的寄存器约定]

### 3.7 RD Multiply/Divide (rrrr)

```
muls    rdha, rdhb, rdhc, rdhd  ; signed multiply
mulu    rdha, rdhb, rdhc, rdhd  ; unsigned multiply
divs    rdha, rdhb, rdhc, rdhd  ; signed divide (rdha=rem, rdhb=quot)
divu    rdha, rdhb, rdhc, rdhd  ; unsigned divide
```

Encoding: §2.8 row 00011 col 100–111. Format `rrrr`.

**Multiply**: `rdha:rdhb = rdhc × rdhd` (128-bit result). Source snapshot.
Legality: same dual-destination rule as add/sub (§2.6.1).

**Divide** [wiki §SimRISC-01 L197–L203]:
- `divs`: signed. Quotient truncates toward zero (C99).
  Remainder sign = dividend sign: `rem = dividend - trunc(dividend/divisor) × divisor`
- `divu`: unsigned.
- Divide-by-zero: **ILLI** (precise, rdha/rdhb not written). [spec-decision: 整数除零 fault，wiki 未定义（DZ 为 FP 状态位），见 open-spec-issues]
- `divs INT64_MIN ÷ -1`: **ILLI** (precise, only overflow case). [spec-decision: divs INT64_MIN÷-1 fault，wiki 未定义，见 open-spec-issues]
- `divu` has no overflow.
- Source snapshot: rdhc, rdhd read before any write.
- Legality: same dual-destination rule.

### 3.8 RD Compare — Immediate Form (rrii)

```
cmps    rdha, rdhb, imms12      ; signed: compare rdhb with sext(imms12)
cmpu    rdha, rdhb, immu12      ; unsigned: compare rdhb with zext(immu12)
```

Encoding: §2.8 row 00010 col 010/011. Format `rrii`.

Semantic: `rdha = -1 if a < b; 0 if a == b; 1 if a > b`, where (a, b) =
(rdhb, immediate). Comparison is signed for cmps, unsigned for cmpu.

Legality: `rdha ≠ rd0` (ILLI). [wiki §SimRISC-01 §rd0 为目的寄存器约定]

### 3.9 RD Compare — Register Form (orrr)

```
cmps    rdhb, rdhc, rdhd        ; signed: compare rdhc vs rdhd
cmpu    rdhb, rdhc, rdhd        ; unsigned: compare rdhc vs rdhd
```

Encoding: §2.8.1 ha=10_0100/10_0101. Format `orrr`.
- `hb`=rdhb; `hc`=rdhc; `hd`=rdhd.

Semantic: `rdhb = -1 if a < b; 0 if a == b; 1 if a > b`, with (a,b) =
(rdhc, rdhd).

Legality: `rdhb ≠ rd0` (ILLI; destination is rdhb). [wiki §SimRISC-01 L87]

### 3.10 RD Logical (orrr)

```
and     rdhb, rdhc, rdhd        ; bitwise AND
orr     rdhb, rdhc, rdhd        ; bitwise OR
xor     rdhb, rdhc, rdhd        ; bitwise XOR
xnor    rdhb, rdhc, rdhd        ; bitwise XNOR
```

Encoding: §2.8.1 ha=00_1000–00_1011. Format `orrr`.

Semantic: 64-bit bitwise operations.

Note: `xnor` with one operand = rd0 produces bitwise NOT of the other
operand.

Legality: `rdhb ≠ rd0` (ILLI; destination is rdhb). [wiki §SimRISC-01 L87]

### 3.11 RD Shift/Extend

**Register form** (orrr):
```
shlu    rdhb, rdhc, rdhd        ; logical left shift
shrs    rdhb, rdhc, rdhd        ; arithmetic right shift
shru    rdhb, rdhc, rdhd        ; logical right shift
exts    rdhb, rdhc, rdhd        ; sign extend
extz    rdhb, rdhc, rdhd        ; zero extend
```

Encoding: §2.8.1 ha=01_0001–01_0101. Format `orrr`.

Shift amount: `rdhd[5:0]` (bits 5–0, range 0–63).
[wiki §SimRISC-01 L229]

**Immediate form** (orri):
```
shlu    rdhb, rdhc, immu6
shrs    rdhb, rdhc, immu6
shru    rdhb, rdhc, immu6
exts    rdhb, rdhc, immu6
extz    rdhb, rdhc, immu6
```

Encoding: §2.8.1 ha=01_1001–01_1101. Format `orri`. Shift amount in `hd`.

**Semantic**:
- `shlu`: logical left shift. Low bits filled with 0.
- `shrs`: arithmetic right shift. High bits filled with original bit 63.
- `shru`: logical right shift. High bits filled with 0.
- `exts`: keep low `64 - hd` bits, sign-extend to 64.
  Equivalent to `(x << hd) >>s hd` (arithmetic).
- `extz`: keep low `64 - hd` bits, zero-extend to 64.
  Equivalent to `(x << hd) >>u hd` (logical).

Examples: `exts rd, rd, 56` → 8-bit sign extension. `exts rd, rd, 48` →
16-bit sign extension. `exts rd, rd, 32` → 32-bit sign extension.
[wiki §SimRISC-01 L231–L232]

Legality: `rdhb ≠ rd0` (ILLI; destination is rdhb). [wiki §SimRISC-01 L87]

### 3.12 RD Conditional Assign (rrrr)

```
csn     rdha, rdhb, rdhc, rdhd  ; if N(rdha): rdhb=rdhc, else rdhb=rdhd
csz     rdha, rdhb, rdhc, rdhd  ; if Z(rdha): rdhb=rdhc, else rdhb=rdhd
csp     rdha, rdhb, rdhc, rdhd  ; if P(rdha): rdhb=rdhc, else rdhb=rdhd
cseq    rdha, rdhb, rdhc, rdhd  ; if EQ(rdha,rdhb): rdhc=rdhd
csne    rdha, rdhb, rdhc, rdhd  ; if NE(rdha,rdhb): rdhc=rdhd
```

Encoding: §2.8 row 00100. Format `rrrr`.

Conditions per §Appendix B.

Non-overlapping operands: source registers read, then destination written
(standard sequential behavior; no wiki citation needed for the non-overlap case).

Overlap behavior (src = dst register): **OPEN (C-27)** — whether the
pre-write source value is used has no confirmed Wiki reference for rrrr-format
conditional assignment. Non-overlapping vectors are definite; overlap vectors
are deferred pending C-27 resolution.

Legality:
- csn/csz/csp: `rdhb ≠ rd0` (ILLI; destination is rdhb). [wiki §SimRISC-01 §rd0 为目的寄存器约定]
- cseq/csne: `rdhc ≠ rd0` (ILLI; destination is rdhc). [wiki §SimRISC-01 §rd0 为目的寄存器约定]

### 3.13 RD Wyde Immediate (rwii)

```
setow   rdha, ww, immu16        ; set wyde, others = 1
setzw   rdha, ww, immu16        ; set wyde, others = 0
orw     rdha, ww, immu16        ; OR into wyde
andnw   rdha, ww, immu16        ; AND-NOT into wyde
```

Encoding: §2.8 row 00010 col 100–111. Format `rwii`.
- `ha`=rdha; `hb[5:4]`=ww; `hb[3:0]`=imm[15:12]; `hc`=imm[11:6];
  `hd`=imm[5:0].

Wyde position: `ww == 0 → bits[15:0]`, `1 → bits[31:16]`,
`2 → bits[47:32]`, `3 → bits[63:48]`.

Semantic:
- `setow`: target wyde = immu16; other wydes = 0xFFFF.
- `setzw`: target wyde = immu16; other wydes = 0.
- `orw`: target wyde |= immu16; other wydes unchanged.
- `andnw`: target wyde &= ~immu16; other wydes unchanged.

Legality: `rdha ≠ rd0` (ILLI). [wiki §SimRISC-01 §rd0 为目的寄存器约定]

### 3.14 RD Block Copy — rd2rd (orri)

```
rd2rd   rdhb, rdhc, immu6       ; copy immu6 regs from rdhc to rdhb
```

Encoding: §2.8.1 ha=10_1000. Format `orri`.
- `hb`=rdhb; `hc`=rdhc; `hd`=immu6.

Semantic: Copy `immu6` consecutive 64-bit values from `rdhc` to `rdhb`.
Processing: increasing i, read-then-write per pair. Overlap well-defined.

Legality: `immu6 ∈ [1,63]`; `rdhb ≠ rd0`; `rdhb + immu6 ≤ 64`;
`rdhc + immu6 ≤ 64`. ILLI if violated. [wiki §SimRISC-01 L86–L90]

---

## §4 Address/Memory Instructions (RB and RA Memory Transfers)

[wiki §SimRISC-02-地址类指令.md]

RB high-16-bit behavior by instruction class [wiki §SimRISC-02 L9–L21]:

| Instruction class | Instructions | bits[63:48] behavior |
|-------------------|-------------|----------------------|
| Memory ↔ RB       | ldo/ldmo/sto/stmo (RB target) | Full 64-bit overwrite |
| Reg copy → RB     | rd2rb, rb2rb, rd2ra, ra2rd (RB target) | Full 64-bit overwrite |
| Wyde immediate RB | setzw-rb, orw-rb, andnw-rb | Full 64-bit; w3 legal |
| RB arithmetic     | add-rb, sub-rb, addi-rb, rela | Low 48 only; bits[63:48] preserved |
| RB compare        | cmp-rb | Compare low 48 only; bits[63:48] ignored |
| Control flow      | br*, jump, call, ret | Low 48 only; PC bits[63:48]=0 |

EA and PC computation for all address/control-flow instructions:
`result[47:0] = (operand[47:0] + offset) mod 2^48`
Overflow beyond 48 bits is discarded (no carry into bit 48).

### 4.1 RB Single Load/Store (rrii)

```
ldo     rbha, rbhb, imms12      ; load octa to RB
sto     rbha, rbhb, imms12      ; store octa from RB
```

Encoding: §2.8 row 01000 col 011 (ldo-rb) / 01001 col 011 (sto-rb).
Format `rrii`. `ha`=rbha; `hb`=rbhb; `hc:hd`=imms12.

EA: `(rbhb[47:0] + sext_12(imms12)) mod 2^48`

Semantic:
- `ldo`: `rbha[63:0] = memory_be[ea : ea+7]` (full 64-bit overwrite).
- `sto`: `memory_be[ea : ea+7] = rbha[63:0]`.

Alignment: 8-byte; unaligned → MALIGN. [wiki §SimRISC-01 §对齐要求]

Legality: `rbha ≠ rb0` (ILLI for ldo; sto to rb0 is also ILLI per §2.6.2). [wiki §SimRISC-02 §存取类]

### 4.2 RB Multi Load/Store (rrri)

```
ldmo    rbha, rbhb, rdhc, immu6 ; multi load to RB
stmo    rbha, rbhb, rdhc, immu6 ; multi store from RB
```

Encoding: §2.8 row 01000 col 111 / 01001 col 111. Format `rrri`.

EA for register i: `(rbhb[47:0] + rdhc[47:0] + i × 8) mod 2^48`
Full 64-bit overwrite per register.

Alignment: 8-byte per element.

Legality: `rbha ≠ rb0`; `immu6 ∈ [1,63]`; `rbha + immu6 ≤ 64`. ILLI if [wiki §SimRISC-02 §存取RB寄存器]
violated. [wiki §SimRISC-02 L41–L45]

### 4.3 RB Arithmetic — add/sub (orrr)

```
add     rbhb, rbhc, rdhd        ; rbhb[47:0] = (rbhc[47:0] + rdhd[47:0]) mod 2^48
sub     rbhb, rbhc, rdhd        ; rbhb[47:0] = (rbhc[47:0] - rdhd[47:0]) mod 2^48
```

Encoding: §2.8.1 ha=10_1110/10_1111. Format `orrr`.
- `hb`=rbhb; `hc`=rbhc; `hd`=rdhd.

Semantic: Low 48 bits only. Overflow discarded. `rbhb[63:48]` unchanged
(preserved from prior value). [wiki §SimRISC-02 L109]

### 4.4 RB addi (rrii)

```
addi    rbha, rbhb, imms12      ; rbha[47:0] = (rbhb[47:0] + sext_12(imms12)) mod 2^48
```

Encoding: §2.8 row 01001 col 001. Format `rrii`.

Semantic: Low 48 bits only. `rbha[63:48]` unchanged.
Legality: `rbha ≠ rb0` (ILLI). [wiki §SimRISC-02 §存取类]

### 4.5 RB Compare (orrr)

```
cmp     rdhb, rbhc, rbhd        ; unsigned compare: low 48 bits
```

Encoding: §2.8.1 ha=10_1101. Format `orrr`.
- `hb`=rdhb; `hc`=rbhc; `hd`=rbhd.

Semantic: Compare `rbhc[47:0]` vs `rbhd[47:0]` as unsigned 48-bit values.
`rdhb = -1 if a < b; 0 if a == b; 1 if a > b`.
Bits[63:48] of RB operands are ignored. [wiki §SimRISC-02 L134]

### 4.6 RB Wyde Immediate (rwii)

```
setzw   rbha, ww, immu16        ; set wyde, others = 0
orw     rbha, ww, immu16        ; OR into wyde
andnw   rbha, ww, immu16        ; AND-NOT into wyde
```

Encoding: §2.8 row 01001 col 100–110. Format `rwii`.

Semantic: same as RD wyde immediate (§3.13), operating on RB.
Full 64-bit overwrite; wyde-pos=3 (bits[63:48]) is legal.
[wiki §SimRISC-02 L15]

Legality: `rbha ≠ rb0` (ILLI). [wiki §SimRISC-02 §存取类]

### 4.7 RB Block Copy (orri)

```
rb2rd   rdhb, rbhc, immu6       ; RB → RD, full 64-bit copy
rd2rb   rbhb, rdhc, immu6       ; RD → RB, full 64-bit copy
rb2rb   rbhb, rbhc, immu6       ; RB → RB, full 64-bit copy
```

Encoding: §2.8.1 ha=10_1010/10_1001/10_1011. Format `orri`.

Semantic: Copy `immu6` consecutive 64-bit values. No type conversion.
`rd2rb`/`rb2rb`/`rb2rd` all transfer full 64 bits.
[wiki §SimRISC-02 §寄存器组之间块赋值]

Legality: `immu6 ∈ [1,63]`; for RB target: `rbhb ≠ rb0`;
`start_reg + immu6 ≤ 64` for both source and destination banks. ILLI. [wiki §SimRISC-01 §寄存器组之间块赋值]
[wiki §SimRISC-02 L86–L89]

### 4.8 PC-Relative Address (riii)

```
rela    rbha, imms18
```

Encoding: §2.8 row 01001 col 000. Format `riii`.

Semantic:
```
base[47:0] = (rb0[47:0]) & ~0xFFF         ; 4KB-aligned
offset = sext_18(imms18) << 12             ; 30-bit signed
rbha[47:0] = (base[47:0] + offset) mod 2^48
rbha[63:48] = unchanged                    ; preservation rule
```

`rb0` = address of instruction after `rela`.
Effective offset range: -536870912 to 536805376 (approx ±512 MB, 4KB step).
[wiki §SimRISC-02 L159–L161; high-16 preservation per L15/L161]

### 4.9 RA Multi Load/Store (rrri)

```
ldmo-ra raha, rbhb, rdhc, immu6 ; multi load to RA
stmo-ra raha, rbhb, rdhc, immu6 ; multi store from RA
```

Encoding: §2.8 row 01100 col 111 (`0x67`) / 01101 col 111 (`0x6F`).
Format `rrri`. `ha`=raha; `hb`=rbhb; `hc`=rdhc; `hd`=immu6.

EA for element i: `(rbhb[47:0] + rdhc[47:0] + i × 8) mod 2^48`,
where `i ∈ [0, immu6-1]`.

Semantic:
- `ldmo-ra`: copy `memory_be[ea_i : ea_i+7]` to
  `ra[raha+i][63:0]`.
- `stmo-ra`: copy `ra[raha+i][63:0]` to
  `memory_be[ea_i : ea_i+7]`.
- Each pair is processed in increasing `i` order, reading that pair's source
  before writing its destination. [wiki §SimRISC-02 §存取RA寄存器 L47–L63]
- Each RA slot is transferred as an opaque, unchanged 64-bit value.
  `bits[63:48]` are not cleared, validated, or otherwise specially handled.
  [spec-decision: KL-107a, 2026-07-25; the wiki does not define the
  reference-count-field behavior for RA↔memory transfers; decision basis:
  KL-106a and docs/wiki-deviations.md #8]

Alignment: 8-byte per element; an unaligned element raises **MALIGN**. [wiki §SimRISC-02 §存取RA寄存器 L47–L63]

Legality: `immu6 ∈ [1,63]`; `raha + immu6 ≤ 64`. A violation raises
**ILLI**. [wiki §SimRISC-02 §存取RA寄存器 L47–L63]

---

## §5 Control Flow

[wiki §SimRISC-02-地址类指令.md §控制流指令]

All branch/jump/call/ret addresses are computed in 48-bit arithmetic with
overflow discarded. `PC` (rb0) has bits[63:48] = 0.

Branch offsets are shifted left by 2 (instruction alignment).

### 5.1 Single-Register Condition Branch (riii)

```
brn     rdha, imms18             ; branch if negative
brnn    rdha, imms18             ; branch if non-negative
brz     rdha, imms18             ; branch if zero
brnz    rdha, imms18             ; branch if non-zero
brp     rdha, imms18             ; branch if positive
brnp    rdha, imms18             ; branch if non-positive
```

Encoding: §2.8 row 00101 col 000–101. Format `riii`.

Condition per §Appendix B.
Target if taken: `PC_next[47:0] = (rb0[47:0] + (sext_18(imms18) << 2)) mod 2^48`
If not taken: `PC_next = rb0` (fall through).

Special case: `rdha = rd0` → `brz` always taken, `brnz` never taken.

### 5.2 Dual-Register Condition Branch (rrii)

```
breq    rdha, rdhb, imms12       ; branch if equal
brne    rdha, rdhb, imms12       ; branch if not equal
```

Encoding: §2.8 row 00101 col 110/111. Format `rrii`.

Target if taken: `PC_next[47:0] = (rb0[47:0] + (sext_12(imms12) << 2)) mod 2^48`

### 5.3 Unconditional Jump

**Relative (iiii):**
```
jump    imms24
```
Encoding: §2.8 row 01100 col 100. Format `iiii`.
Target: `PC_next[47:0] = (rb0[47:0] + (sext_24(imms24) << 2)) mod 2^48`

**Absolute (rrii):**
```
jump    rbha, rdhb, imms12
```
Encoding: §2.8 row 01100 col 101. Format `rrii`.
Target: `PC_next[47:0] = (rbha[47:0] + rdhb[47:0] + (sext_12(imms12) << 2)) mod 2^48`
Special: `rbha = rb0` → relative jump.

### 5.4 Call

**Relative (iiii):**
```
call    imms24
```
Encoding: §2.8 row 01101 col 100. Format `iiii`.
Target: `PC_next[47:0] = (rb0[47:0] + (sext_24(imms24) << 2)) mod 2^48`
Return address pushed: `rb0` (address of instruction after call).

**Absolute (rrii):**
```
call    rbha, rdhb, imms12
```
Encoding: §2.8 row 01101 col 101. Format `rrii`.
Target: `PC_next[47:0] = (rbha[47:0] + rdhb[47:0] + (sext_12(imms12) << 2)) mod 2^48`
Return address pushed: `rb0`.

RAS push: see §5.6.

### 5.5 Return

```
ret     rdha, imms18
```

Encoding: §2.8 row 01101 col 110. Format `riii`.

Semantic:
1. Pop return address from RegRAS (§5.6).
2. `PC_next[47:0]` = popped address (48 bits).
3. `rdha = sext_18(imms18)` (return value; `rdha=rd0` discards it — legal).

### 5.6 RAS Behavior (RegRAS)

[wiki §DADAO-11-AEE §返回地址栈]

**RegRAS layout**: `ra1`–`ra63`; `ra63` = stack top.
- Bits[63:48]: reference count (0 = invalid, 1 = valid, >1 = recursion).
- Bits[47:0]: return address (48-bit PC).
- `ra0` low = 0 (RegRAS-only mode, M1 assumption).

**Call (push)** [wiki §DADAO-11-AEE L193–L204]:
1. If `ra63[63:48] == 0`:
   `ra63[63:48] = 1; ra63[47:0] = rb0[47:0]`
2. Else if `ra63[63:48] ∈ [1, 0xFFFE]` and `ra63[47:0] == new_ra`:
   `ra63[63:48] += 1` (recursion)
3. Else:
   If `ra1[63:48] ≠ 0` (valid before shift) → **RASOF** (precise, RA unchanged). [wiki §DADAO-11-AEE §返回地址栈]
   Else: shift entries down: `ra{i-1} ← ra{i}` for i=2..63
   (ra1←ra2, ra2←ra3, …, ra62←ra63)
   `ra63[63:48] = 1; ra63[47:0] = rb0[47:0]`

**Return (pop)** [wiki §DADAO-11-AEE L208–L218]:
1. If `ra63[63:48] > 1`:
   `ra63[63:48] -= 1; ret_addr = ra63[47:0]`
2. Else if `ra63[63:48] == 1`:
   `ret_addr = ra63[47:0]`
   Shift entries up: `ra{i+1} ← ra{i}` for i=62..1
   (ra63←ra62, ra62←ra61, …, ra2←ra1); `ra1 = 0`
3. Else (`ra63[63:48] == 0`):
   **RASUF** (precise, RA unchanged). [wiki §DADAO-11-AEE §返回地址栈]

RASOF/RASUF are precise: PC stays at faulting call/ret; RA registers are not [wiki §DADAO-11-AEE §返回地址栈]
modified. [wiki §DADAO-11-AEE L183]

---

## §6 NOP and Reserved

### 6.1 swym

```
swym    immu18
```

Encoding: §2.8.1 ha=00_0000. Format `oiii`.

Semantic: No architectural effect other than PC increment (PC ← PC + 4).
The 18-bit immediate has no semantic meaning; users may use it for debugging
tags. The assembler provides `nop` as a pseudo-instruction for `swym 0`.
[wiki §SimRISC-04-系统类指令.md L30]

### 6.2 unimp

```
unimp   immu18
```

Encoding: §2.8.1 ha=11_1111. Format `oiii`.

Semantic: Triggers **ILLI** exception (illegal instruction, precise). [wiki §SimRISC-04 §unimp]
The immediate has no semantic meaning.
[wiki §SimRISC-04 L31]

---

## §7 M1 Excluded

M1 scope per `code-agent/designs/0002-detailed-roadmap.md` §Scope Matrix.
Excluded operations must produce an explicit, assertable error (not silent [spec-decision: ADR-0007]
no-op). The exact test-machine observable protocol is defined in ADR-0004.

| Area | Instructions excluded | Matrix reference |
|------|----------------------|------------------|
| RF execution | All MISC-RF subtable (op 01010–01011); csn-rf, csz-rf, csp-rf, csp1, csnp1; rd2rf, rf2rd, rf2rf; ldt-rf, ldo-rf, ldmt-rf, ldmo-rf; stt-rf, sto-rf, stmt-rf, stmo-rf; ftmadd, fomadd; setw | §Floating-point |
| Atomics | fence; lro_nn/nr/an/ar; sco_nn/nr/an/ar | §Atomics |
| System cfx | trap, escape; cfx2rd, cfx2rc; cfxld, cfxst | §SBI/HBI |
| RA register move | rd2ra, ra2rd | Excluded (M1 scope decision, 2026-06-29; ISA semantics clear per SimRISC-02 §RA↔RD; not needed for non-variadic scalar ABI) |

---

## Appendix A: Canonical Encoding Inventory

### A.1 M1 Encoding Records

Each record: `op`, `ha` (minor, if applicable), format, operand fields, and 32-bit
encoding oracle (`mask`/`value`).

**Encoding oracle columns** (32-bit big-endian instruction word):
- `mask`: bits that must match to identify the instruction (fixed opcode bits set to 1). [spec-decision]
- `value`: the fixed bits' expected values (all variable bits are 0).
- Computed from layout: op=[31:24], ha=[23:18], hb=[17:12], hc=[11:6], hd=[5:0].
- For MISC-Norm (op=0x10): `mask=0xFFFC0000` (op+ha both fixed).
- For all others: `mask=0xFF000000` (op byte only fixed).

#### A.1.1 Row 0001-0xxx (op[7:3]=00010, op[2:0]=xxx)

| `op[7:0]` | ha[5:0]   | Mnemonic  | Format | ha    | hb      | hc       | hd       | mask       | value      |
|-----------|-----------|-----------|--------|-------|---------|----------|----------|------------|------------|
| 0x10      | 00_0000   | swym      | oiii   | fixed | imm     | imm      | imm      | 0xFFFC0000 | 0x10000000 |
| 0x10      | 00_1000   | and       | orrr   | fixed | rdhb    | rdhc     | rdhd     | 0xFFFC0000 | 0x10200000 |
| 0x10      | 00_1001   | orr       | orrr   | fixed | rdhb    | rdhc     | rdhd     | 0xFFFC0000 | 0x10240000 |
| 0x10      | 00_1010   | xor       | orrr   | fixed | rdhb    | rdhc     | rdhd     | 0xFFFC0000 | 0x10280000 |
| 0x10      | 00_1011   | xnor      | orrr   | fixed | rdhb    | rdhc     | rdhd     | 0xFFFC0000 | 0x102C0000 |
| 0x10      | 01_0001   | shlu(r)   | orrr   | fixed | rdhb    | rdhc     | rdhd     | 0xFFFC0000 | 0x10440000 |
| 0x10      | 01_0010   | shrs(r)   | orrr   | fixed | rdhb    | rdhc     | rdhd     | 0xFFFC0000 | 0x10480000 |
| 0x10      | 01_0011   | shru(r)   | orrr   | fixed | rdhb    | rdhc     | rdhd     | 0xFFFC0000 | 0x104C0000 |
| 0x10      | 01_0100   | exts(r)   | orrr   | fixed | rdhb    | rdhc     | rdhd     | 0xFFFC0000 | 0x10500000 |
| 0x10      | 01_0101   | extz(r)   | orrr   | fixed | rdhb    | rdhc     | rdhd     | 0xFFFC0000 | 0x10540000 |
| 0x10      | 01_1001   | shlu(i)   | orri   | fixed | rdhb    | rdhc     | immu6    | 0xFFFC0000 | 0x10640000 |
| 0x10      | 01_1010   | shrs(i)   | orri   | fixed | rdhb    | rdhc     | immu6    | 0xFFFC0000 | 0x10680000 |
| 0x10      | 01_1011   | shru(i)   | orri   | fixed | rdhb    | rdhc     | immu6    | 0xFFFC0000 | 0x106C0000 |
| 0x10      | 01_1100   | exts(i)   | orri   | fixed | rdhb    | rdhc     | immu6    | 0xFFFC0000 | 0x10700000 |
| 0x10      | 01_1101   | extz(i)   | orri   | fixed | rdhb    | rdhc     | immu6    | 0xFFFC0000 | 0x10740000 |
| 0x10      | 10_0100   | cmps(r)   | orrr   | fixed | rdhb    | rdhc     | rdhd     | 0xFFFC0000 | 0x10900000 |
| 0x10      | 10_0101   | cmpu(r)   | orrr   | fixed | rdhb    | rdhc     | rdhd     | 0xFFFC0000 | 0x10940000 |
| 0x10      | 10_1000   | rd2rd     | orri   | fixed | rdhb    | rdhc     | immu6    | 0xFFFC0000 | 0x10A00000 |
| 0x10      | 10_1001   | rd2rb     | orri   | fixed | rbhb    | rdhc     | immu6    | 0xFFFC0000 | 0x10A40000 |
| 0x10      | 10_1010   | rb2rd     | orri   | fixed | rdhb    | rbhc     | immu6    | 0xFFFC0000 | 0x10A80000 |
| 0x10      | 10_1011   | rb2rb     | orri   | fixed | rbhb    | rbhc     | immu6    | 0xFFFC0000 | 0x10AC0000 |
| 0x10      | 10_1101   | cmp-rb    | orrr   | fixed | rdhb    | rbhc     | rbhd     | 0xFFFC0000 | 0x10B40000 |
| 0x10      | 10_1110   | add-rb    | orrr   | fixed | rbhb    | rbhc     | rdhd     | 0xFFFC0000 | 0x10B80000 |
| 0x10      | 10_1111   | sub-rb    | orrr   | fixed | rbhb    | rbhc     | rdhd     | 0xFFFC0000 | 0x10BC0000 |
| 0x10      | 11_1111   | unimp     | oiii   | fixed | imm     | imm      | imm      | 0xFFFC0000 | 0x10FC0000 |

#### A.1.2 Row 0001-1xxx (op[7:3]=00011)

| `op[7:0]` | Mnemonic | Format | ha    | hb    | hc         | hd         | mask       | value      |
|-----------|----------|--------|-------|-------|------------|------------|------------|------------|
| 0x19      | addi     | rrii   | rdha  | rdhb  | imms12(hc) | imms12(hd) | 0xFF000000 | 0x19000000 |
| 0x1A      | add      | rrrr   | rdha  | rdhb  | rdhc       | rdhd       | 0xFF000000 | 0x1A000000 |
| 0x1B      | sub      | rrrr   | rdha  | rdhb  | rdhc       | rdhd       | 0xFF000000 | 0x1B000000 |
| 0x1C      | muls     | rrrr   | rdha  | rdhb  | rdhc       | rdhd       | 0xFF000000 | 0x1C000000 |
| 0x1D      | mulu     | rrrr   | rdha  | rdhb  | rdhc       | rdhd       | 0xFF000000 | 0x1D000000 |
| 0x1E      | divs     | rrrr   | rdha  | rdhb  | rdhc       | rdhd       | 0xFF000000 | 0x1E000000 |
| 0x1F      | divu     | rrrr   | rdha  | rdhb  | rdhc       | rdhd       | 0xFF000000 | 0x1F000000 |

#### A.1.3 Row 0001-0xxx remaining (op[7:3]=00010, non-MISC-Norm)

| `op[7:0]` | Mnemonic | Format | ha    | hb       | hc:hd     | mask       | value      |
|-----------|----------|--------|-------|----------|-----------|------------|------------|
| 0x12      | cmps(i)  | rrii   | rdha  | rdhb     | imms12    | 0xFF000000 | 0x12000000 |
| 0x13      | cmpu(i)  | rrii   | rdha  | rdhb     | immu12    | 0xFF000000 | 0x13000000 |
| 0x14      | orw      | rwii   | rdha  | ww+himm  | imm(11:0) | 0xFF000000 | 0x14000000 |
| 0x15      | andnw    | rwii   | rdha  | ww+himm  | imm(11:0) | 0xFF000000 | 0x15000000 |
| 0x16      | setzw    | rwii   | rdha  | ww+himm  | imm(11:0) | 0xFF000000 | 0x16000000 |
| 0x17      | setow    | rwii   | rdha  | ww+himm  | imm(11:0) | 0xFF000000 | 0x17000000 |

#### A.1.4 Row 0010-0xxx (op[7:3]=00100)

| `op[7:0]` | Mnemonic | Format | ha    | hb    | hc    | hd    | mask       | value      |
|-----------|----------|--------|-------|-------|-------|-------|------------|------------|
| 0x20      | csn      | rrrr   | rdha  | rdhb  | rdhc  | rdhd  | 0xFF000000 | 0x20000000 |
| 0x22      | csz      | rrrr   | rdha  | rdhb  | rdhc  | rdhd  | 0xFF000000 | 0x22000000 |
| 0x24      | csp      | rrrr   | rdha  | rdhb  | rdhc  | rdhd  | 0xFF000000 | 0x24000000 |
| 0x26      | cseq     | rrrr   | rdha  | rdhb  | rdhc  | rdhd  | 0xFF000000 | 0x26000000 |
| 0x27      | csne     | rrrr   | rdha  | rdhb  | rdhc  | rdhd  | 0xFF000000 | 0x27000000 |

#### A.1.5 Row 0010-1xxx (op[7:3]=00101)

| `op[7:0]` | Mnemonic | Format | ha    | hb         | hc         | hd         | mask       | value      |
|-----------|----------|--------|-------|------------|------------|------------|------------|------------|
| 0x28      | brn      | riii   | rdha  | imms18(hb) | imms18(hc) | imms18(hd) | 0xFF000000 | 0x28000000 |
| 0x29      | brnn     | riii   | rdha  | imms18(hb) | imms18(hc) | imms18(hd) | 0xFF000000 | 0x29000000 |
| 0x2A      | brz      | riii   | rdha  | imms18(hb) | imms18(hc) | imms18(hd) | 0xFF000000 | 0x2A000000 |
| 0x2B      | brnz     | riii   | rdha  | imms18(hb) | imms18(hc) | imms18(hd) | 0xFF000000 | 0x2B000000 |
| 0x2C      | brp      | riii   | rdha  | imms18(hb) | imms18(hc) | imms18(hd) | 0xFF000000 | 0x2C000000 |
| 0x2D      | brnp     | riii   | rdha  | imms18(hb) | imms18(hc) | imms18(hd) | 0xFF000000 | 0x2D000000 |
| 0x2E      | breq     | rrii   | rdha  | rdhb       | imms12(hc) | imms12(hd) | 0xFF000000 | 0x2E000000 |
| 0x2F      | brne     | rrii   | rdha  | rdhb       | imms12(hc) | imms12(hd) | 0xFF000000 | 0x2F000000 |

#### A.1.6 Row 0011-0xxx (op[7:3]=00110)

| `op[7:0]` | Mnemonic | Format | ha    | hb    | hc         | hd         | mask       | value      |
|-----------|----------|--------|-------|-------|------------|------------|------------|------------|
| 0x30      | ldbs     | rrii   | rdha  | rbhb  | imms12(hc) | imms12(hd) | 0xFF000000 | 0x30000000 |
| 0x31      | ldws     | rrii   | rdha  | rbhb  | imms12(hc) | imms12(hd) | 0xFF000000 | 0x31000000 |
| 0x32      | ldts     | rrii   | rdha  | rbhb  | imms12(hc) | imms12(hd) | 0xFF000000 | 0x32000000 |
| 0x33      | ldo      | rrii   | rdha  | rbhb  | imms12(hc) | imms12(hd) | 0xFF000000 | 0x33000000 |
| 0x34      | ldmbs    | rrri   | rdha  | rbhb  | rdhc       | immu6(hd)  | 0xFF000000 | 0x34000000 |
| 0x35      | ldmws    | rrri   | rdha  | rbhb  | rdhc       | immu6(hd)  | 0xFF000000 | 0x35000000 |
| 0x36      | ldmts    | rrri   | rdha  | rbhb  | rdhc       | immu6(hd)  | 0xFF000000 | 0x36000000 |
| 0x37      | ldmo     | rrri   | rdha  | rbhb  | rdhc       | immu6(hd)  | 0xFF000000 | 0x37000000 |

#### A.1.7 Row 0011-1xxx (op[7:3]=00111)

| `op[7:0]` | Mnemonic | Format | ha    | hb    | hc         | hd         | mask       | value      |
|-----------|----------|--------|-------|-------|------------|------------|------------|------------|
| 0x38      | stb      | rrii   | rdha  | rbhb  | imms12(hc) | imms12(hd) | 0xFF000000 | 0x38000000 |
| 0x39      | stw      | rrii   | rdha  | rbhb  | imms12(hc) | imms12(hd) | 0xFF000000 | 0x39000000 |
| 0x3A      | stt      | rrii   | rdha  | rbhb  | imms12(hc) | imms12(hd) | 0xFF000000 | 0x3A000000 |
| 0x3B      | sto      | rrii   | rdha  | rbhb  | imms12(hc) | imms12(hd) | 0xFF000000 | 0x3B000000 |
| 0x3C      | stmb     | rrri   | rdha  | rbhb  | rdhc       | immu6(hd)  | 0xFF000000 | 0x3C000000 |
| 0x3D      | stmw     | rrri   | rdha  | rbhb  | rdhc       | immu6(hd)  | 0xFF000000 | 0x3D000000 |
| 0x3E      | stmt     | rrri   | rdha  | rbhb  | rdhc       | immu6(hd)  | 0xFF000000 | 0x3E000000 |
| 0x3F      | stmo     | rrri   | rdha  | rbhb  | rdhc       | immu6(hd)  | 0xFF000000 | 0x3F000000 |

#### A.1.8 Row 0100-0xxx (op[7:3]=01000)

| `op[7:0]` | Mnemonic | Format | ha    | hb    | hc         | hd         | mask       | value      |
|-----------|----------|--------|-------|-------|------------|------------|------------|------------|
| 0x40      | ldbu     | rrii   | rdha  | rbhb  | imms12(hc) | imms12(hd) | 0xFF000000 | 0x40000000 |
| 0x41      | ldwu     | rrii   | rdha  | rbhb  | imms12(hc) | imms12(hd) | 0xFF000000 | 0x41000000 |
| 0x42      | ldtu     | rrii   | rdha  | rbhb  | imms12(hc) | imms12(hd) | 0xFF000000 | 0x42000000 |
| 0x43      | ldo-rb   | rrii   | rbha  | rbhb  | imms12(hc) | imms12(hd) | 0xFF000000 | 0x43000000 |
| 0x44      | ldmbu    | rrri   | rdha  | rbhb  | rdhc       | immu6(hd)  | 0xFF000000 | 0x44000000 |
| 0x45      | ldmwu    | rrri   | rdha  | rbhb  | rdhc       | immu6(hd)  | 0xFF000000 | 0x45000000 |
| 0x46      | ldmtu    | rrri   | rdha  | rbhb  | rdhc       | immu6(hd)  | 0xFF000000 | 0x46000000 |
| 0x47      | ldmo-rb  | rrri   | rbha  | rbhb  | rdhc       | immu6(hd)  | 0xFF000000 | 0x47000000 |

#### A.1.9 Row 0100-1xxx (op[7:3]=01001)

| `op[7:0]` | Mnemonic | Format | ha    | hb          | hc            | hd            | mask       | value      |
|-----------|----------|--------|-------|-------------|---------------|---------------|------------|------------|
| 0x48      | rela     | riii   | rbha  | imms18(hb)  | imms18(hc)    | imms18(hd)    | 0xFF000000 | 0x48000000 |
| 0x49      | addi-rb  | rrii   | rbha  | rbhb        | imms12(hc)    | imms12(hd)    | 0xFF000000 | 0x49000000 |
| 0x4B      | sto-rb   | rrii   | rbha  | rbhb        | imms12(hc)    | imms12(hd)    | 0xFF000000 | 0x4B000000 |
| 0x4C      | orw-rb   | rwii   | rbha  | ww+himm(hb) | imm(11:0)(hc) | imm(11:0)(hd) | 0xFF000000 | 0x4C000000 |
| 0x4D      | andnw-rb | rwii   | rbha  | ww+himm(hb) | imm(11:0)(hc) | imm(11:0)(hd) | 0xFF000000 | 0x4D000000 |
| 0x4E      | setzw-rb | rwii   | rbha  | ww+himm(hb) | imm(11:0)(hc) | imm(11:0)(hd) | 0xFF000000 | 0x4E000000 |
| 0x4F      | stmo-rb  | rrri   | rbha  | rbhb        | rdhc          | immu6(hd)     | 0xFF000000 | 0x4F000000 |

#### A.1.10 Row 0110-0xxx (op[7:3]=01100)

| `op[7:0]` | Mnemonic | Format | ha                  | hb    | hc         | hd         | mask       | value      |
|-----------|----------|--------|---------------------|-------|------------|------------|------------|------------|
| 0x64      | jump     | iiii   | imms24(ha:hb:hc:hd) | —     | —          | —          | 0xFF000000 | 0x64000000 |
| 0x65      | jump     | rrii   | rbha                | rdhb  | imms12(hc) | imms12(hd) | 0xFF000000 | 0x65000000 |
| 0x67      | ldmo-ra  | rrri   | raha                | rbhb  | rdhc       | immu6(hd)  | 0xFF000000 | 0x67000000 |

#### A.1.11 Row 0110-1xxx (op[7:3]=01101)

| `op[7:0]` | Mnemonic | Format | ha                  | hb    | hc         | hd         | mask       | value      |
|-----------|----------|--------|---------------------|-------|------------|------------|------------|------------|
| 0x6C      | call     | iiii   | imms24(ha:hb:hc:hd) | —     | —          | —          | 0xFF000000 | 0x6C000000 |
| 0x6D      | call     | rrii   | rbha                | rdhb  | imms12(hc) | imms12(hd) | 0xFF000000 | 0x6D000000 |
| 0x6E      | ret      | riii   | rdha                | imms18(hb) | imms18(hc) | imms18(hd) | 0xFF000000 | 0x6E000000 |
| 0x6F      | stmo-ra  | rrri   | raha                | rbhb  | rdhc       | immu6(hd)  | 0xFF000000 | 0x6F000000 |

---

## Appendix B: Condition Flag Reference

[wiki §SimRISC-00-指令系统设计.md §标识位说明]

| Mnemonic | Condition     | Test                          | Instructions                |
|----------|---------------|-------------------------------|-----------------------------|
| `N`      | negative      | bit[63] = 1                   | csn, brn                    |
| `NN`     | non-negative  | bit[63] = 0                   | brnn                        |
| `Z`      | zero          | all 64 bits = 0               | csz, brz                    |
| `NZ`     | non-zero      | any bit ≠ 0                   | brnz                        |
| `P`      | positive      | bit[63]=0 AND [62:0] ≠ 0      | csp, brp                    |
| `NP`     | non-positive  | bit[63]=1 OR all zero         | brnp                        |
| `EQ`     | equal         | all 64 bits equal (2 regs)    | cseq, breq                  |
| `NE`     | not equal     | at least one bit differs      | csne, brne                  |

---

## Appendix C: Open Issues

Issues that remain unresolved after Wiki 0.4.1. All other C-items from
previous reviews are RESOLVED by wiki commit `13a414d`.

| ID  | Area | Issue | Status |
|-----|------|-------|--------|
| C-14 | Scope | rd2ra/ra2rd M1 inclusion (RA file move, not RAS) | RESOLVED — Excluded by architecture decision 2026-06-29; see §7 and Scope Matrix |
| C-18a | Reset | Known: rb0 reset vector (SEE); RA process-entry = zero (AEE L185); RB bits[63:48] power-on = 0 (SimRISC-02 L21) | PARTIALLY KNOWN |
| C-18b | Reset | Unknown: RD, RB[1-63] (non-high bits), RF, RA power-on low-level reset state | OPEN — test-machine init defined by ADR-0004 |
| C-27 | Execution | Conditional assignment (csn/csz/csp/cseq/csne) source snapshot on src/dst overlap: spec §3.12 asserts "all sources read before write" but no wiki reference found | OPEN — blocks overlap test vectors |
| — | SBZ | Behavior of non-zero SBZ fields in opcode encoding | OPEN — wiki defines SBZ but not fault type (ILLI vs UNDI) | [spec-decision: ADR-0004 D5]
| — | Reset | M1 test-machine initialization values vs architectural reset | OPEN — ADR-0004 to define test entry state |

All other C-items (C-01 through C-13, C-15 through C-17, C-19 through C-26)
are **RESOLVED** by Wiki commit `13a414d`. See specific resolution in each
section above. Central issue tracking in `docs/open-spec-issues.md` and
`docs/wiki-questions.md` is updated accordingly.
