# gem5 Component

Functional **second reference** for the DADAO ISA. gem5 is a third independent
implementation (alongside the spec-derived Python golden model `tools/dadao_interp.py`
and QEMU) that runs the same `tests/vectors/isa/*.yaml` corpus for a three-way
differential (interp / QEMU / gem5). Semantics are derived only from
`contracts/isa/spec.md` and `tools/opcodes.yaml` — never copied from QEMU — so
agreement is meaningful. See ADR-0010.

Primary scope: functional ISA correctness in **SE mode** (AtomicSimpleCPU);
timing / microarchitecture is out of scope. KL-124a adds a minimal
FullSystem flat-image carrier for bare-metal semantic probes; KL-126a/KL-127a
add the PTW success path, precise walk-fault delivery, and leaf A/D updates.
KL-129a adds the bounded K1 architectural TLB and single-layer PTW delegation
needed by the bare-metal profile. KL-131a adds SEE §5 steps 2-6 mask/pending/
priority arbitration and the project's first real instruction-boundary
asynchronous interrupt dispatch (`Interrupts::checkInterrupts()`/
`getInterrupt()`, previously a stub always returning false/NoFault) --
FullSystem-mode only, per `BaseCPU::checkInterrupts()`'s own gate. KL-133a
adds `cfx_hart_cycle_lo` and `cfx_timer` counter0. The configured
`DADAOAtomicSimpleCPU` advances them from the successful macro-instruction
retirement funnel, not pre-fetch `checkInterrupts()`; precise faults do not
count, and expiry is delivered at the following boundary. An asserted private
timer source re-latches common TIMER at every boundary until acknowledged,
independent of enable and masks. Timer delivery is FullSystem-only. Real
devices and full OS bring-up remain out of scope. KL-137a adds the same
test-machine-only `K1_EXT0` acceptance source: default-off retirement-schedule
Params assert/deassert cfx_uart source0, whose private pending latch reflects
into common UART0 and reuses KL-131a arbitration. It is not a UART or PLIC
device implementation.

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
| 0024 | PTW faults and A/D | precise cfx_ptw carrier, 15 walker causes, leaf A/D writeback | SE baseline unchanged |
| 0025 | Architectural TLB | 64×16 true LRU, invalidate, 7 hit causes, PTW delegation | SE baseline unchanged |
| 0026 | Maskable async dispatch core | SEE §5 steps 2-6 gate + real instruction-boundary async delivery (FullSystem) | SE baseline unchanged |
| 0027 | cfx_hart_cycle_lo + cfx_timer counter0 | successful-retirement counter, fault exclusion, decrement/one-shot/periodic state machine, private-to-common relatch and timer-mask gate (FullSystem/AtomicSimpleCPU) | SE baseline unchanged |
| 0028 | TLB range-invalidate review fix | ignore `addr_start[15:0]`, preserve size0 no-op, clamp oversized range to selected 4-TiB set | SE baseline unchanged |
| 0029 | Synthetic external source K1_EXT0 | scheduled test-only level, cfx_uart private pending/exist, UART0 relatch through shared async dispatch | SE baseline unchanged |
| 0030 | RB block-copy high bits | preserve all 64 bits in `rb2rd`/`rb2rb`, as required by ISA §4.7 | 200 |

Current result: interp/QEMU/gem5 AGREE(3-way)=200, gem5-SKIP=2,
DIVERGE=0; the FullSystem KL-113a/117a/120a raw matrix, KL-126a's eight
PTW success probes, KL-127a's 30 fault/10 A-D probes, KL-129a's 13
dual-backend TLB/delegation probes, KL-131a's dual-backend sync-mask +
async-priority/electrics probes, and KL-133a's dual-backend cycle_lo/
retire-fault/one-shot/periodic/mask/private-relatch probes (10 stable loops)
are also green. KL-129b adds four guest-decided dual-backend probes for the
unaligned-start counterexample, zero size, set-end clamp, and fault-hit LRU
touch. Disable→enable cache preservation remains a non-claim because the
frozen contract defines lookup gating but not entry lifetime across toggles.
KL-137a adds two guest-decided dual-backend scenarios: a 10-loop-stable
assert/mask/relatch/delivery/deassert/ack lifecycle and TIMER-vs-K1_EXT0
cross-CFX priority. No UART/PLIC protocol or cg32-63 device registers are
claimed. KL-141a additionally closes a stale gem5-only 48-bit truncation in
RB-source block copies that contradicted ISA §4.7; the cooperative-switch
probe keeps non-zero RB high bits live across 25 context transitions.

## Build & run (after `make fetch` + `apply_series`)

```
scons build/DADAO/gem5.opt -j"$(nproc)"          # in .work/source/gem5
./build/DADAO/gem5.opt tests/dadao/dadao_se.py <flat-binary-as-ELF>
./build/DADAO/gem5.opt tests/dadao/dadao_fs.py <flat-image.bin>
```

Differential is driven from this repo: `tests/scripts/run_gem5_test.py` (adapter,
same interface as `run_qemu_test.py`) and `tools/run_differential.py` (three-way).
