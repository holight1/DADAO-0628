# Design 0001: LLVM MC + QEMU CPU Core + Basic CodeGen

Status: Accepted for implementation

SPEC candidate: `13a414da158dc780ae5501c1443acbffd15cbf4a` (SimRISC 0.4.1; supersedes original `7ddb632c`)

## Decision

The current Wiki is sufficient to start LLVM MC, the QEMU CPU core, and basic
LLVM CodeGen. Open ABI and system questions do not block this work because the
first milestone has an explicit exclusion boundary.

## Foundation Scope

The total scope below spans what the detailed roadmap calls M1 (MC + QEMU, Phases 2–4)
and M2 (Basic CodeGen, Phase 5). See `0002-detailed-roadmap.md` for the M1/M2 split.

### QEMU

- RD/RB/RF/RA architectural state and reset behavior.
- Fixed-width instruction fetch and decodetree decode.
- Scalar integer and address operations in the locked SimRISC subset.
- Big-endian instruction/data behavior.
- Width-specific load/store alignment and explicit MALIGN reporting.
- Compare, branch, jump, basic call/ret, and RegRAS-only behavior.
- MMU-off bare-metal memory plus deterministic test exit/signature support.

### LLVM MC

- Triple and target registration needed by MC tools.
- Register names, reserved registers, instruction formats, and operands.
- Assembler, printer, encoder, disassembler, and negative diagnostics.
- Exact encoding tests shared only through independent SPEC vectors.
- No claim of complete ELF/LLD support before the object ABI ADR is accepted.

### Basic CodeGen

- Big-endian LP64 DataLayout consistent with the locked AEE/ABI subset.
- GPRD integer values and GPRB pointer/address values.
- i64 arithmetic, constants, compare/branch, scalar load/store, and return.
- Simple stack objects, FrameIndex elimination, spills, and callee-save paths.
- Non-variadic scalar arguments and returns sufficient for freestanding tests.

## Hard Exclusions

- Varargs, HFA/HPA, complex aggregates, and mixed-bank multiple returns.
- Dynamic linking, TLS, EH/SJLJ, libc, and Linux syscalls.
- SBI/HBI, privileged cfx services, nested/cross-cfx escape.
- PTW, TLB, page tables, virtual memory, and Kernel bring-up.
- MemRAS memory faults, atomics, memory model, and SMP.

An excluded operation must produce an explicit unsupported result. It must not
be accepted by a stub that silently changes no state.

## Vertical Slices

1. Independent raw encoding vector executes in QEMU.
2. LLVM MC emits the same bytes from assembly text.
3. LLVM disassembler recovers the canonical assembly.
4. Basic CodeGen selects the instruction from a small LLVM IR function.
5. Emitted bytes execute in QEMU and produce the independent expected state.

The first slices cover constant construction, add/sub, one load/store width,
compare/branch, and call/ret. Broader instruction coverage follows only after
this path is reproducible.

## Required Gates

- `spec.lock.toml` points to the reviewed Wiki commit.
- LLVM and QEMU upstream commits are accepted through ADRs and locked.
- Encoding vectors are authored independently from both implementations.
- Every immediate has min/max and out-of-range tests.
- QEMU tests check source/destination overlap and immutable registers.
- MIR tests check GPRD/GPRB classes, not only printed mnemonics.
- Runtime tests report deterministic signatures instead of relying on timeout.

## Change Control

If the Wiki changes an included M1 rule, development stops at the affected
slice. Update the SPEC lock, impact matrix, vectors, and both consumers before
resuming. Changes to excluded areas do not invalidate M1 unless they alter an
included encoding, register, endian, alignment, or control-flow rule.

## Foundation Completion

Foundation (M1 + M2) is complete when a clean checkout can fetch pinned
upstreams, apply ordered patches, build LLVM MC/QEMU, and pass the independent
MC-to-QEMU scalar suite (M1); and Basic CodeGen demonstrates at least one
arithmetic, load/store, branch, and call/return function executing with the
expected result in QEMU (M2).

Detailed completion gates for M1 and M2 are in `0002-detailed-roadmap.md`.
