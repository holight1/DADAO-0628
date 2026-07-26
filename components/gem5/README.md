# gem5 Component

Functional **second reference** for the DADAO ISA. gem5 is a third independent
implementation (alongside the spec-derived Python golden model `tools/dadao_interp.py`
and QEMU) that runs the same `tests/vectors/isa/*.yaml` corpus for a three-way
differential (interp / QEMU / gem5). Semantics are derived only from
`contracts/isa/spec.md` and `tools/opcodes.yaml` — never copied from QEMU — so
agreement is meaningful. See ADR-0010.

Primary scope: functional ISA correctness in **SE mode** (AtomicSimpleCPU);
timing / microarchitecture is out of scope. KL-124a adds a minimal
FullSystem flat-image carrier for bare-metal semantic probes; KL-126a adds
the successful PTW path while PTW faults, A/D updates, an architectural TLB,
interrupts, and OS bring-up remain out of scope.

## Baseline

Upstream gem5 pinned at **v25.1.0.1** (`c8222cc67a399bfc01e8658dd14b30d5bfd634f9`),
recorded in `manifests/components.lock.toml`. A brand-new `src/arch/dadao/` is added
as a hand-written decoder arch (not the `.isa` DSL). Bring-up notes and "how to add
an instruction" live in the applied tree at `docs/gem5-arch-notes.md`.

## Patch series (application order)

| # | Patch | Milestone | 3-way AGREE |
|---|-------|-----------|-------------|
| 0001 | dadao-arch-skeleton    | buildable skeleton (SimObjects, RA/RD/RB, MMU/TLB, loader arch 0xda0) | build only |
| 0002 | dadao-core-isa         | halt/addi/add/jump + big-endian fetch | smoke 42/42/0 |
| 0003 | dadao-halt-regdump      | dump final RD/RB at halt for differential readout | — |
| 0004 | dadao-alu              | ~35 register-compute (logic/shift/compare/cond-assign/wyde/RB) | 77 |
| 0005 | dadao-memory           | load/store + block-copy (big-endian) | 131 |
| 0006 | dadao-faults           | ILLI 0x82 / MALIGN 0x81 / UNDI 0x83 + legality + div-by-zero | 162 |
| 0007 | dadao-controlflow-ras  | branches / jump_r / call / ret + RegRAS + block-copy | **198** |
| 0022 | FullSystem bare-metal carrier | flat image at 0x00100000, identity TLB, no-op interrupts | SE baseline unchanged |
| 0023 | PTW successful path | cfx_ptw registers, super/normal-page walk, X/R/W | SE baseline unchanged |

Current result: interp/QEMU/gem5 AGREE(3-way)=200, gem5-SKIP=2,
DIVERGE=0; the FullSystem KL-113a/117a/120a raw matrix and KL-126a's eight
PTW successful-path probes are also green.

## Build & run (after `make fetch` + `apply_series`)

```
scons build/DADAO/gem5.opt -j"$(nproc)"          # in .work/source/gem5
./build/DADAO/gem5.opt tests/dadao/dadao_se.py <flat-binary-as-ELF>
./build/DADAO/gem5.opt tests/dadao/dadao_fs.py <flat-image.bin>
```

Differential is driven from this repo: `tests/scripts/run_gem5_test.py` (adapter,
same interface as `run_qemu_test.py`) and `tools/run_differential.py` (three-way).
