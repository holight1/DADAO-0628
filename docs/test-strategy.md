# Test Strategy

## Independent Oracle Rule

Encoding tests must not derive expected bytes from LLVM or QEMU. Semantic tests
must not copy formulas or constants from either implementation.

## Layers

1. Static contract validation.
2. LLVM MC positive, boundary, and negative tests.
3. QEMU raw-encoding state-transition tests.
4. LLVM MIR tests for opcode and register-class selection.
5. MC-to-QEMU interface tests.
6. Freestanding runtime tests with deterministic pass/fail signatures.

## Required Instruction Cases

- Normal values and zero.
- Signed immediate minimum and maximum.
- Source/destination overlap.
- Immutable register destinations.
- Invalid register fields and reserved encodings.
- Alignment faults for each memory width.
- PC-relative boundaries and next-PC semantics.
