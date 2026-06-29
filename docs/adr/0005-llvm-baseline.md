# ADR-0005: LLVM Baseline for Phase 2 (MC Framework)

Status: Accepted

## Context

Phase 2 requires a full upstream LLVM baseline providing:

- **MC framework**: `MCTargetDesc`, `MCCodeEmitter`, `MCObjectWriter`,
  `MCAsmBackend`, `ELFObjectWriter` — the core infrastructure for assembling
  and emitting ELF relocatable objects for the DADAO target.
- **TableGen**: `.td`-based instruction definitions, register info, and
  MC-level code generation table files.
- **lit**: LLVM-integrated test runner used for MC and assembly tests.

DADAO is a new target from scratch (`ADR-0001`). No legacy DADAO toolchain
code is reused. All Phase 2 patches apply to the clean upstream commit
selected here.

## Decision

| Field | Value |
|-------|-------|
| LLVM version | 22.1.8 |
| Commit SHA | `ca7933e47d3a3451d81e72ac174dcb5aa28b59d1` |
| GitHub URL | <https://github.com/llvm/llvm-project/tree/ca7933e47d3a3451d81e72ac174dcb5aa28b59d1> |
| Tag | `llvmorg-22.1.8` |

## Rationale

1. **Stability**: The 22.1.x release branch provides a stable, tested
   baseline. Using a release tag (not `main`) eliminates churn from
   ongoing upstream development and ensures reproducible builds across
   developer machines and CI. Release 22.1.8 (June 2026) is the latest
   22.x patch release with all accumulated bugfixes.

2. **MC framework availability**: LLVM 22.x has mature, stable APIs for
   `MCTargetDesc`, `MCCodeEmitter`, `MCELFObjectTargetWriter`, and
   `ELFObjectWriter`. The MC layer has been stable since the LLVM 15–17 era
   and is well-documented in the LLVM source tree. LLVM 22.x adds no
   breaking changes to the MC interfaces used by a new target.

3. **Build verification**: The tag `llvmorg-22.1.8` is an official LLVM
   release commit in the `llvm-project` repository, verified by
   `git ls-remote` against `https://github.com/llvm/llvm-project.git`.
   The full SHA `ca7933e47d3a3451d81e72ac174dcb5aa28b59d1` resolves to a
   reachable tagged tree.

## Consequences

1. All Phase 2 patches (MC framework, ELF emitter, TableGen definitions,
   lit tests) target this exact commit as the base.
2. No LLVM version bump during Phase 2. If a severe upstream bug is
   discovered, a cherry-pick of the fix is documented in a new ADR;
   otherwise the baseline is frozen for the duration of Phase 2.
3. The `llvm` component is marked `enabled = true` in
   `manifests/components.lock.toml` and will be fetched by `make prepare`
   at this commit.
