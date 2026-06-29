# ADR-0006: QEMU Upstream Baseline for Phase 3 Simulation

Status: Accepted

## Context

Phase 3 requires a functional system simulation capability built on QEMU's
TCG (Tiny Code Generator) framework. The following components depend on a
stable upstream QEMU baseline:

- TCG frontend: target CPU instruction decoding and translation
- Target skeleton: `target/dadao/` directory with CPUState, helpers, disassembly
- decodetree: QEMU's instruction decode generator
- Bare-metal machine: `hw/dadao/` with memory map, device tree, loader

Multiple reference targets exist in QEMU upstream (riscv, arm, mips) that
provide design patterns for the DADAO port. Using a stable upstream commit
ensures reproducible builds and predictable TCG interfaces throughout Phase 3.

Dependencies: `ADR-0004` (test machine memory map), `contracts/isa/spec.md`
(instruction encoding).

## Decision

- **Version**: QEMU v10.0.0 (released April 2026)
- **Commit SHA**: `385b0a7d9785c8f3ac7b116d7f31d61502b55183`
- **Commit URL**: <https://github.com/qemu/qemu/commit/385b0a7d9785c8f3ac7b116d7f31d61502b55183>

## Rationale

1. **Stability**: v10.0.0 is a tagged stable release on a release branch,
   guaranteeing that the baseline does not change due to upstream rebases
   or force-pushes.

2. **TCG API stability**: QEMU 9.x and 10.x series have mature TCG interfaces
   (`TCGv`, `gen_helper_*`, `tcg_gen_*`). The opcode dispatch and translation
   block APIs are well-documented across multiple reference targets.

3. **Build verification**: `./configure --target-list=riscv64-softmmu
   --enable-tcg` succeeds with this commit, confirming that the build system,
   meson, and TCG dependencies are functional.

## Consequences

1. All Phase 3 patches (target skeleton, decodetree, machine model, loader)
   will be developed against this exact commit.

2. No QEMU version bump during Phase 3. If a severe upstream bug is
   encountered, a targeted cherry-pick will be applied and documented via a
   new ADR (ADR-0006 amendment or ADR-00XX).
