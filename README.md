# DADAO-0628

DADAO-0628 is a **greenfield implementation of the DADAO software stack**, built
from a versioned specification contract. Legacy DADAO repositories are kept only
as references for lessons and repository orchestration; legacy implementation
code is not a source of truth.

The distinctive property of this repository is its **four-way ISA verification
chain**: the M1 instruction set (87 instructions) is implemented independently by
four executables, all derived only from the spec, and cross-checked on one shared
vector corpus. As of the current state they **agree on all 198 spec-semantic
vectors with zero divergence**.

## Spec provenance (pinned wiki version)

The ISA contract `contracts/isa/spec.md` is derived from the **DADAO wiki**
([`github.com/gxt/DADAO.wiki`](https://github.com/gxt/DADAO.wiki)), **pinned** at
commit [`13a414da158dc780ae5501c1443acbffd15cbf4a`](https://github.com/gxt/DADAO.wiki/commit/13a414da158dc780ae5501c1443acbffd15cbf4a):

| Component | Version |
|-----------|---------|
| SimRISC (ISA) | 0.4.1 |
| AEE-ABI | 0.9.2 |
| SEE-SBI | 0.7.1 |
| HEE-HBI | 0.1.2 |

The machine-readable lock is `manifests/spec.lock.toml` (`status = frozen`). The
wiki has continued to evolve upstream; **this repository is intentionally pinned to
that frozen version and does not yet integrate later wiki updates**. Re-basing onto
a newer wiki revision is a deliberate future step, not an automatic follow.

## Verification chain (what makes this repo unusual)

```
                 contracts/isa/spec.md   (authoritative contract)
        ┌──────────────┬──────────────┬──────────────┐
        ▼              ▼              ▼              ▼
   dadao_interp      QEMU          gem5           Sail
  (Python golden   (functional   (cycle sim,    (formal
   model, spec-     emulator)     SE mode)       exec spec)
   derived oracle)
        └──────────────┴──────────────┴──────────────┘
                 tools/run_differential.py
        4-way AGREE = 198 · DIVERGE = 0 · HARNESS-abstain = 6
```

- **`②` spec→implementation** is covered by the four-way differential — a bug in
  any one implementation diverges and is localized.
- **`①` upstream→spec** is what the differential cannot see; the **Sail formal
  model** is the mechanical-oracle candidate for it (authoritative once endorsed
  upstream). See `docs/adr/0011`.
- The independence rule is strict: every implementation derives semantics from
  `contracts/isa/spec.md §` and never copies another. Agreement is therefore
  meaningful. See `docs/adr/0009` and the knowledge-graph node
  `isa-design/04-multi-implementation-differential`.

## Repository layout

```
contracts/isa/spec.md      Authoritative ISA contract (§-numbered). Source of all semantics.
tools/
  opcodes.yaml             Encoding + legality contract (op/format/fields).
  dadao_interp.py          Spec-derived Python golden model (M2a, neutral referee).
  run_differential.py      4-way differential runner (interp/QEMU/gem5/Sail).
  legality_rules.yaml      Generative legality matrix rules (M3).
sail/                      Sail formal executable spec (.sail model + C harness + build.sh).
tests/
  vectors/isa/*.yaml       Shared independent test vectors (204 active).
  scripts/                 Per-backend adapters: run_qemu_test / run_gem5_test / run_sail_test / build_test_binary.
  lit/E2E/                 End-to-end lit tests (compiled program on QEMU + gem5 backends).
components/
  llvm/  qemu/  gem5/      Upstream selection + DADAO patch series (patches/ + series + README).
  musl/  linux/            Deferred.
manifests/                 Pinned upstream commits (components.lock.toml), spec lock, references.
scripts/                   apply_series / manifest_check / gen_e2e_binary etc.
docs/
  adr/                     Architecture Decision Records (see below).
  reviews/                 Research reports & roadmap reviews (e.g. sail-recon).
  *.md                     Strategy docs (test-strategy, development-roadmap, impact-matrix …).
  issues.yaml              Open/closed issue registry.
code-agent/
  tasks/                   Numbered task files (NNNx) — interface spec + constraints + pointers.
  knowledge/               Per-repo knowledge base + changelog.
.work/                     Upstream source/build trees, sysroots, artifacts. Never committed (gitignored).
```

Upstream source trees (`.work/source/<component>`) are reconstructed by
`make fetch` (pinned commit) + `apply_series` (the DADAO patches). The gem5 arch,
for example, lives entirely as `components/gem5/patches/*` on top of gem5 v25.1.0.1
— a reproducible `git am` yields the exact developed tree.

## Documents

**ADRs** (`docs/adr/`) — accepted decisions, source of truth after the spec:

| ADR | Topic |
|-----|-------|
| 0001 | Greenfield rebuild |
| 0002 | Build orchestration (manifest + patch series) |
| 0003 | Object/ELF ABI (EM_DADAO=0x0DA0) |
| 0004 | Test machine (exit-MMIO, fault codes) |
| 0005 / 0006 | LLVM / QEMU baselines |
| 0007 | Testing methodology (independent expected values) |
| 0008 | CodeGen feasibility spike (dual-bank GPRD survives to MIR) |
| 0009 | Verification-chain mechanization (golden model · legality matrix) |
| 0010 | gem5 functional second reference (three-way, SE mode) |
| 0011 | M2b Sail authoritative executable spec (positioning B) |

Also: `docs/reviews/` (research reports), `docs/issues.yaml` (issue registry),
`docs/development-roadmap.md`, `docs/test-strategy.md`, `contracts/isa/spec.md`.

## Development history

1. **M1 ISA** — LLVM target/MC + QEMU CPU/decode/execute + independent vectors;
   87 instructions, bare-metal MMU-off test machine.
2. **Verification chain** (ADR-0009) — a spec-derived Python golden model (M2a)
   and a generative legality matrix (M3) turn the translation chain into a real
   differential. Caught real bugs QEMU + vectors shared as blind spots
   (ldo-align, reserved→UNDI, PC-base register unmaintained).
3. **gem5 functional second reference** (ADR-0010) — a new `arch/dadao` brought
   up from scratch on gem5 v25.1.0.1 (SE mode); all 87 instructions, three-way
   AGREE=198, DIVERGE=0. gem5 also added as a second E2E backend.
4. **Sail formal spec** (ADR-0011) — a Sail executable spec (all 87 instructions)
   joins as the fourth independent implementation; four-way AGREE=198,
   DIVERGE=0. A formal model derived from the spec agreeing with three simulators
   is the strongest cross-validation, and the `①` authoritative-oracle candidate.
5. **Phase 5 CodeGen** (in progress) — real SelectionDAG lowering; dual-bank
   pointer (GPRB) survives to MIR (DL-050a). Sequence: load/store patterns →
   calling convention → asm emission → compile C to binary.

## Quick start

```sh
make manifest-check        # validate pinned upstream + spec lock
make doctor                # environment check
make status                # milestone status
make check                 # repository checks (structure, wiki drift, ABI, issue registry)
```

Four-way differential (needs QEMU/gem5/Sail sims built under `.work` / `~/DADAO-gem5` / `sail/`):

```sh
python3 tools/run_differential.py      # interp vs QEMU vs gem5 vs Sail
```

## Authority order

1. The specification commit in `manifests/spec.lock.toml`.
2. Accepted ADRs and contracts in this repository.
3. Independent test vectors and interface tests.
4. Implementation and comments.
