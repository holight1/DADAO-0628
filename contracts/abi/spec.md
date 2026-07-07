# ABI Contract — DADAO SimRISC (M1 Non-variadic Scalar)

**Version**: 0.1.0
**Source**: Wiki commit `13a414da158dc780ae5501c1443acbffd15cbf4a` (SimRISC 0.4.1)
**Status**: Candidate

M1 BasicCodeGen scope: non-variadic functions, scalar integer and pointer
arguments/returns only. Floating-point, HFA/HPA, varargs, and complex
aggregates are excluded.

---

## §1 Register Roles and Caller/Callee Classification

[wiki §DADAO-21-ABI-应用程序二进制接口.md §寄存器规范]

### 1.1 RD — Data Registers

| Register | ABI Name | Role | Callee-saved? |
|----------|----------|------|---------------|
| rd0      | rdzero   | Hardwired zero | Immutable |
| rd1      | rderrno  | Error number (optional kernel use) | — |
| rd2–rd7  | —        | Reserved (compiler must not allocate) | — |
| rd8–rd15 | rdt0–rdt7| Temporary | No |
| rd16–rd31| rda0–rda15| Argument / temporary | No |
| rd32–rd63| —        | General purpose | **Yes** |

**M1 allocatable set**: rd8–rd15 (caller-saved temporaries), rd16–rd31
(argument/return), rd32–rd63 (callee-saved). Non-allocatable: rd0 (hardwired
zero), rd1 (kernel-reserved; [OPEN: callee-saved undefined in wiki — M1
treats as non-allocatable]), rd2–rd7 (ABI-reserved).

### 1.2 RB — Base Registers

| Register | ABI Name | Role | Callee-saved? |
|----------|----------|------|---------------|
| rb0      | rbip     | Instruction pointer (read-only) | — |
| rb1      | rbsp     | Stack pointer | **Yes** |
| rb2      | rbfp     | Frame pointer (optional) | **Yes** |
| rb3      | rbgp     | Global pointer | — |
| rb4      | rbtp     | Thread pointer | — |
| rb5–rb7  | —        | Reserved | — |
| rb8–rb15 | rbt0–rbt7| Temporary | No |
| rb16–rb31| rba0–rba15| Argument / temporary | No |
| rb32–rb63| —        | General purpose | **Yes** |

**M1 allocatable set**: rb8–rb15 (caller-saved temporaries), rb16–rb31
(argument/return), rb32–rb63 (callee-saved). Non-allocatable: rb0 (PC),
rb1 (stack pointer, frame management only), rb2 (frame pointer, managed by
prologue/epilogue), rb3 ([OPEN: callee-saved undefined — M1 non-allocatable]),
rb4 ([OPEN: callee-saved undefined — M1 non-allocatable]), rb5–rb7 (reserved).

### 1.3 RF — Float Registers

Excluded from M1. RF register ABI roles are documented in the wiki for
completeness but must not be used by M1 BasicCodeGen.

### 1.4 RA — Return Address Stack

[wiki §DADAO-11-AEE §返回地址栈]

RA registers are managed entirely by the `call`/`ret` instruction pair
(see `contracts/isa/spec.md §5.6`). They are not part of the
caller-saved/callee-saved framework:
- `call` pushes the return address onto RegRAS (automatic).
- `ret` pops the return address from RegRAS (automatic).
- No software save/restore of RA registers is needed for normal leaf or
  non-leaf function calls; process/context switching is outside M1 scope.

---

## §2 Argument Passing

[wiki §DADAO-21-ABI §函数调用规范 §传参]

### 2.1 Parameter Registers

Arguments are dispatched by type into the corresponding register bank:

| Argument type | Register bank | Register range |
|---------------|---------------|----------------|
| Integer / scalar (i8/i16/i32/i64, enum, _Bool) | RD | rd16–rd31 |
| Pointer / address | RB | rb16–rb31 |
| Floating-point | RF | rf16–rf31 (Excluded from M1) |

The three banks count independently starting from register 16. There is no
shared slot numbering. [wiki §DADAO-21-ABI §传参 §参数寄存器]

### 2.2 Scalar Argument Promotion

Arguments narrower than 64 bits are extended to fill the full 64-bit register.
The extension rule depends on signedness:

| Source type | Extension |
|-------------|-----------|
| `char` (signed in the DADAO ABI), `signed char`, `short`, `int` | sign-extend |
| `unsigned char`, `unsigned short`, `unsigned int` | zero-extend |
| `_Bool` | zero-extend (value is 0 or 1) |
| `enum` (signed 32-bit in the DADAO ABI) | sign-extend |
| `long`, `unsigned long`, `long long`, `unsigned long long` | no extension (already 64-bit) |

The caller is responsible for providing the canonical extension. The callee
may rely on it without re-extending. [wiki §DADAO-21-ABI §传参 §标量参数]
Pointer arguments always fill all 64 bits of the RB register.

### 2.3 Register Overflow

When all registers of a bank are exhausted, overflow arguments of that bank
are placed in a **single shared overflow area** on the caller's frame.
All overflow arguments — regardless of bank — are ordered by their **global
declaration sequence**, not per-bank order.

Each slot is 8 bytes wide (canonical extension per §2.2 applies; narrow values
occupy the full 8-byte slot with appropriate extension). The overflow area
starts at `incoming_sp + 0` from the callee's perspective (see §4):

```
incoming_sp + 0:  first  overflow argument (by declaration order)
incoming_sp + 8:  second overflow argument
...
```

**Cross-bank overflow example**:
`f(int i1, …, int i16, void *p1, …, void *p16, int r, void *s, int t)`.
The first 16 integers fill rd16–rd31 and the first 16 pointers fill rb16–rb31.
The remaining arguments share one area in global declaration order:
- `r` (RD overflow) → `incoming_sp + 0`
- `s` (RB overflow) → `incoming_sp + 8`
- `t` (RD overflow) → `incoming_sp + 16`

[wiki §DADAO-21-ABI §传参 §栈溢出规则]

### 2.4 Aggregate Arguments

**Excluded from M1.** M1 BasicCodeGen handles scalar integers and pointers only.
Aggregate parameter passing rules (HFA/HPA, ≤32B register unpacking,
>32B indirect pointer) are defined in wiki §DADAO-21-ABI §聚合类型参数
but are not used by M1 BasicCodeGen.

---

## §3 Return Values

[wiki §DADAO-21-ABI §返回值]

### 3.1 Scalar Return Registers

| Return type | Register |
|-------------|----------|
| Integer / scalar (i8/i16/i32/i64, enum, _Bool) | **rd31** |
| Pointer / address | **rb31** |
| Floating-point | **rf31** (Excluded from M1) |

**Narrow return extension**: the callee must sign- or zero-extend the return
value using the same rules as §2.2 before executing `ret`. The caller may
assume rd31 / rb31 holds a canonical 64-bit value.
[M1 architecture decision: callee extends; caller does not truncate. Wiki
§DADAO-21-ABI §返回值 is silent on this requirement; the decision is adopted
because any other policy produces undefined behavior at call boundaries.
Wiki gap tracked in docs/open-spec-issues.md.]

### 3.2 Multiple Return Values (Post-M1 / Informative)

**Excluded from M1 BasicCodeGen.** Provided here for reference only; not
normative for M1 implementation.

Wiki §DADAO-21-ABI §多返回值 defines multiple-return semantics:
- Primary return value in rd31 / rb31 (by type); additional values in rd30,
  rd29, … / rb30, rb29, … toward rd16 / rb16.
- Mixed-bank: each bank counted independently from its highest slot.

[OPEN: wiki §DADAO-21-ABI §多返回值 contains an internal inconsistency —
the "scan from last declaration" rule and the example `(int x, int y, …)
→ x=rd31, y=rd30` give opposite same-bank ordering. This conflict is tracked
in `docs/open-spec-issues.md` and must be resolved before M1 can implement
multiple returns. §3.2 is therefore Excluded from M1.]

### 3.3 Structure Return (sret) (Post-M1 / Informative)

**Excluded from M1 BasicCodeGen.** Provided here for reference only.

Aggregates > 64 bits use hidden sret [wiki §DADAO-21-ABI §返回值 §聚合类型返回值]:
- Caller pre-allocates space and passes the address as a hidden first
  argument in **rb16**.
- Callee writes the result through `rb16` and preserves `rb16` after return.

Aggregates ≤ 64 bits are returned in rd31.

---

## §4 Stack Frame Layout

[wiki §DADAO-21-ABI §函数调用规范 §The Stack Frame]

### 4.1 Stack Pointers

- **Stack pointer (SP)**: rb1 (`rbsp`). Points to the current stack top
  (lowest valid address in the current frame). Grows downward.
- **Frame pointer (FP)**: rb2 (`rbfp`). Optional. If used, points to the
  saved previous-FP value. If unused, all frame accesses use SP-relative
  addressing.
- **Red zone**: 128 bytes below SP are reserved (not modified by signal
  handlers). Leaf functions may use the red zone as their entire frame,
  avoiding SP adjustment.

### 4.2 Alignment

- SP must be 8-byte aligned before `call`.
- Stack arguments and saved registers are 8-byte aligned.
- Aggregate alignment: minimum 8 bytes.

### 4.3 Frame Layout (high to low address)

```
        +--------------------------+
        | callee memory arguments  |  ← previous frame
        | (if register overflow)   |  ← first argument at rbfp + 8
        +--------------------------+
        | saved rbfp (if FP used)  |  ← no memory return-address slot
        +--------------------------+  ← rbfp (callee's frame pointer)
        | callee-saved registers   |
        | (rd32+, rb32+ as needed) |
        | local variables          |
        +--------------------------+  ← rbsp (current stack top)
        | red zone (128 B)         |  ← rbsp - 128 (reserved)
        +--------------------------+
```

### 4.4 Stack Discipline

1. Caller adjusts SP downward to allocate argument overflow space (if any)
   before `call`.
2. `call` pushes return address via RegRAS (no memory write).
3. Callee saves callee-saved registers it will modify (rd32–rd63 and
   rb32–rb63), plus the previous rb2 value when using a frame pointer.
4. Callee allocates local frame by subtracting from SP.
5. On return: callee deallocates frame, restores saved registers, `ret`.
6. Caller deallocates argument overflow space after return.

---

## §5 Call Sequence (Prologue/Epilogue)

[wiki §DADAO-21-ABI §函数调用规范]

### 5.1 Caller Responsibilities

1. Evaluate arguments and place in rd16–rd31 (integer) / rb16–rb31 (pointer).
   If a bank's 16 registers are insufficient, spill remaining arguments to
   stack (caller's frame).
2. Execute `call` (see `contracts/isa/spec.md §5.4`). Return address is
   automatically pushed to RegRAS.
3. After return, reclaim argument spill space (if any).

The caller must preserve any values live across the call in rd8–rd31 or
rb8–rb31; these registers are caller-saved temporaries/argument registers.

### 5.2 Callee Prologue

Let `incoming_sp` denote the value of rbsp at callee entry (= SP just after
`call`). Caller's first overflow argument (if any) is at `incoming_sp + 0`.

**SP-only frame** (no FP):
```
addi    rbsp, rbsp, -frame_size    ; allocate: frame_size = saved_regs + locals, 8B aligned
; save callee-saved RD registers (rd32+) at rbsp + ...
; save callee-saved RB registers (rb32+) at rbsp + ...
; access incoming overflow args at rbsp + frame_size, rbsp + frame_size + 8, ...
```

**FP frame** (rbfp used):
```
sto     rb2, rbsp, -8              ; save old rbfp at [incoming_sp - 8]
rb2rb   rb2, rbsp, 1               ; full 64-bit copy: rb2 = rbsp (= incoming_sp)
addi    rb2, rb2, -8               ; rbfp = incoming_sp - 8 (points to saved-FP slot)
addi    rbsp, rbsp, -frame_size    ; frame_size = 8(FP slot) + saved_regs + locals, 8B aligned
; save callee-saved registers at rbfp - 8, rbfp - 16, ...
; access incoming overflow args at rbfp + 8, rbfp + 16, ...
; access locals at rbsp ... rbfp - 8
```

Registers rd32+ and rb32+ that the callee modifies must be saved and restored.
rbsp must be restored to `incoming_sp` on return (via symmetric frame
deallocation — no separate spill of rbsp is required).

### 5.3 Callee Epilogue

**SP-only epilogue** (no FP):
```
; restore callee-saved RB registers (rb32+)
; restore callee-saved RD registers (rd32+)
; (scalar return: compute return value into rd31 before ret)
addi    rbsp, rbsp, frame_size     ; rbsp = incoming_sp (symmetric deallocation)
ret     rd0, 0                     ; pop RegRAS → PC; rd31 carries return value
; NOTE: `ret rd31, N` can embed a compile-time constant N (sext_18) in one insn
```

**FP epilogue** (rbfp used):
```
; restore callee-saved RB registers (rb32+, NOT rb2 yet)
; restore callee-saved RD registers (rd32+)
; (scalar return: compute return value into rd31 before ret)
addi    rbsp, rbsp, frame_size     ; rbsp = incoming_sp (symmetric deallocation)
ldo     rb2, rbsp, -8              ; full 64-bit restore: old rbfp from [incoming_sp - 8]
ret     rd0, 0                     ; pop RegRAS → PC; rd31 carries return value
```

The `ret` instruction pops the return address from RegRAS and transfers
control (§5.5 of ISA contract). The `ldo` instruction overwrites all 64 bits
of rb2, avoiding the high-16-bit preservation issue of `addi` (ISA §4.4).

---

## §6 Open Issues

| Issue | Impact | Reference |
|-------|--------|-----------|
| Varargs | Excluded from M1; varargs save area layout defined in wiki but not needed for scalar non-variadic | `docs/open-spec-issues.md` |
| HFA/HPA | Excluded from M1; aggregate classification rules defined in wiki | `docs/open-spec-issues.md` |
| Mixed-bank multi-return | [OPEN] Excluded from M1; Wiki ordering conflict must be resolved before Advanced CodeGen | `docs/open-spec-issues.md` |
| Complex aggregate ABI | Struct splitting rules for >64-bit non-HFA/HPA aggregates; deferred post-M2 | — |
| Dynamic linking TLS | Excluded from M1 | `docs/open-spec-issues.md` |
| Frame pointer convention | Optional rbfp use is a CodeGen optimization choice; this contract does not mandate either strategy | — |

---

## Appendix: Wiki Citations

| § | Content | Wiki source |
|---|---------|-------------|
| 1.1 | RD register roles | `DADAO-21-ABI §寄存器规范 §RD寄存器` |
| 1.2 | RB register roles | `DADAO-21-ABI §寄存器规范 §RB寄存器` |
| 1.4 | RA / RegRAS | `DADAO-11-AEE §返回地址栈` |
| 2.1 | Parameter register banks | `DADAO-21-ABI §传参 §参数寄存器` |
| 2.2 | Scalar promotion | `DADAO-21-ABI §传参 §标量参数` |
| 2.3 | Register overflow to stack | `DADAO-21-ABI §传参 §栈溢出规则` |
| 2.4 | Aggregate arguments | `DADAO-21-ABI §传参 §聚合类型参数` |
| 3.1 | Return registers | `DADAO-21-ABI §返回值 §标量类型返回值` |
| 3.2 | Multiple returns | `DADAO-21-ABI §返回值 §多返回值` |
| 3.3 | sret | `DADAO-21-ABI §返回值 §聚合类型返回值` |
| 4.1 | SP/FP/red zone | `DADAO-21-ABI §The Stack Frame` |
| 4.2 | Alignment | `DADAO-21-ABI §数据表示 §Fundamental Types` |
| 4.3 | Frame layout | `DADAO-21-ABI §函数调用规范 §The Stack Frame` |
