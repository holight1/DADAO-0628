# DADAO-0628

DADAO-0628 is a greenfield implementation of the DADAO software stack.

The repository starts from a versioned specification contract. Legacy DADAO
repositories are references for lessons and repository orchestration only;
legacy implementation code is not an implementation source.

## Initial Scope

The first executable milestone is intentionally narrow:

- LLVM target registration, MC, and basic scalar CodeGen.
- QEMU CPU state, decode, scalar execution, and MMU-off bare-metal tests.
- Independent ISA vectors shared by LLVM MC and QEMU tests.

SBI/HBI, MMU, Kernel, varargs, dynamic linking, and SMP are outside the first
milestone. See `code-agent/designs/0001-foundation-scope.md`.

## Quick Start

```sh
make manifest-check
make doctor
make status
```

Component source trees, build trees, sysroots, logs, and generated artifacts
live under `.work/` and are never committed.

## Authority Order

1. The specification commit in `manifests/spec.lock.toml`.
2. Accepted ADRs and contracts in this repository.
3. Independent test vectors and interface tests.
4. Implementation and comments.
