# Design 0001: LLVM MC + QEMU CPU Core + Basic CodeGen

Status: Accepted for implementation

SPEC candidate: `7ddb632ca3b56f2033b7cbf26ceebd3e62b72fc6`

## Decision

The current Wiki is sufficient to start LLVM MC, the QEMU CPU core, and basic
LLVM CodeGen. Open ABI and system questions do not block this work because the
first milestone has an explicit exclusion boundary.

## M1 Scope

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

## M1 Completion

M1 is complete when a clean checkout can fetch pinned upstreams, apply ordered
patches, build LLVM MC/QEMU, and pass the independent MC-to-QEMU scalar suite.
Basic CodeGen then demonstrates at least one arithmetic, load/store,
branch, and call/return function executing with the expected result.
