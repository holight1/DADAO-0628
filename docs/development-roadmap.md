# Development Roadmap

## M0: Reproducible Foundation

- Repository checks run on a clean host or development container.
- SPEC and component commits are locked.
- Independent instruction vectors have a documented schema.

## M1: MC and CPU Core

- QEMU executes hand-encoded scalar programs in MMU-off bare-metal mode.
- LLVM MC assembles and disassembles the same vectors.
- Invalid encodings and immediate boundaries are rejected consistently.

## M2: Basic CodeGen

- LLVM lowers scalar integer and pointer functions to verified instructions.
- Load/store, branch, direct call, return, frame, and spill paths execute.
- The object ABI needed by this milestone is written and tested.

## M2 status + sequencing decision (2026-07-12)

M2 basic CodeGen is done and extended well past the original scope: integer
arithmetic (add/sub/mul/div/rem/shift), all comparison predicates, control flow
(branches/loops/if-else), select→cs* (branchless), function calls (calling conv,
callee-save, nested, RAS), stack arrays, globals via standard lld linking,
sub-i64 types (i8/i16/i32 narrow ld/st + sign/zero extend), global address as a
value (arrays/strings/address-of-global). In flight: function-pointer indirect
call (DL-063b, CALL_RRII).

**Next milestone = clang integration (real-C frontend), not more aggregate
CodeGen.** Decision (2026-07-12): after indirect call, prioritize wiring a clang
DADAO target (triple / TargetInfo / ABI / driver) over the remaining aggregate
gaps, because:
- Without clang we only feed hand-written `.ll` to `llc`; the aggregate features
  below are only *exercised* once a C frontend emits them — doing them first is
  spinning wheels.
- clang is the true bottleneck for "real C", and it also opens the
  llvm-test-suite path (ADR-0012 T3).

**memcpy/memset — two layers, don't conflate (2026-07-12):**
- The `llvm.memcpy`/`llvm.memset` **intrinsics** (emitted by clang for
  struct-by-value copy and aggregate init) are lowered by the **backend**:
  inline-expand small constant sizes into load/store (set MaxStoresPerMem*),
  no libc needed. Deferred — done alongside aggregates once clang emits them.
- The libc `memcpy`/`memset` **symbols** (the large/variable-size libcall
  fallback) belong to **musl** (libc milestone), not the backend.

Deferred until clang: aggregate/struct-by-value handling, struct return
(sret/multi-reg), `llvm.mem*` intrinsic inline-expansion.

**Function-pointer indirect call — deferred (2026-07-12, decision C).** Three
rounds (DL-063b×2, DL-063c debug) did not crack it: the indirect path crashes in
the scheduler (`ScheduleDAGSDNodes::BuildSchedUnits`, getValueType "Illegal
result number"). Structural root cause: CALL_INDIRECT_PSEUDO is built by hand via
DAGToDAG `getMachineNode` (unlike RET_PSEUDO which is pattern-selected), and the
`Select()` override intercepts every `DADAOISD::CALL` before `SelectCode`, so a
tablegen pattern can't take over (attempts gave "Node already inserted"). The
fix is to go pure pattern-based like RISC-V `PseudoCALLIndirect` (remove the
manual CALL interception), but after three rounds the ROI dropped, so per
decision C we pivot to clang first and revisit indirect call later. WIP is
`git stash`ed in `.work/llvm` (stash@{0}); the root-cause analysis is preserved
in the DL-063c task. Committed patch series stops at 0019 (clean, no broken
0020); lit 24/24.

## M2.5: clang frontend + libc MVP (2026-07-12 ~ 07-14)

clang integration landed (DL-064a/b): `clang hello.c -o hello` freestanding
one-shot (driver → assembler → `ld.lld`) produces a real DADAO ELF, no host
fallback. Fixed an MC cross-object `call` relocation gap surfaced by driver
separate-compilation linking (patch llvm/0022).

**ADR-0014 libc/syscall charter** (2026-07-12): syscall = SEE `trap cfx_smon`
(spec-first, not a semihosting/MMIO hack); software ABI defined (rd16=sysno,
rd17-22=args, rd31=ret, Linux asm-generic numbering); libc staged
picolibc (phase 1: printf+malloc+llvm-test-suite) → musl (phase 2: after a
real kernel). ML-002a/b/c implemented `trap`→CFXTRAP + cfx_smon responder
(write/exit/brk) on both backends.

**picolibc goal① (printf) and goal② (malloc) done on QEMU** (ML-003a-m,
2026-07-13/14): real C `printf("hello, dadao\n")` and `malloc`/`free` via
picolibc's own static-heap `sbrk` fallback (`dadao.ld` `__heap_start`/
`__heap_end`, matching ADR-0014 D3) both run correctly on QEMU with no
workarounds and no prebuilt binaries checked in. Five real backend bugs were
found and fixed along the way: QEMU TB-stop not advancing PC for non-branch
single-instruction TBs (infinite `cpu_io_recompile` loop), QEMU exceptions
never calling `cpu_restore_state` (imprecise fault PC), LLVM varargs frame
size omitting `VarArgsSaveSize` (stack overflow into caller frame), LLVM MC
`applyFixup` double-offsetting `FK_Data_8`/generic-fallback fixups (fragment
memory corruption), and LLVM AsmPrinter skipping jump-table target labels
when a target block coincidentally looks like a fallthrough at `-O0`.

**Open blocker**: issue `gem5-se-lld-elf-load-crash` — gem5 SE cannot load a
real `ld.lld`-produced multi-segment ELF; it panics (page-table fault) before
`main()` runs, independent of malloc/heap. All existing gem5 dual-backend
tests instead go through `gen_min_elf` (a synthesized single-segment ELF from
a raw `.text` binary), so this path was never exercised until the picolibc
E2E tests tried to run on gem5. **Neither picolibc goal is dual-backend
verified yet** — both are QEMU-only until this is fixed.

## M2.6: dual-backend unblock + llvm-test-suite on-ramp (2026-07-14 architect roadmap)

Architect-proposed sequence, executed via subagent (not DS — the first thread
is gem5-internal work, which per `feedback_ds_gem5_semantic_unreliable` goes to
a subagent that owns the gem5 component, not DS):

1. **DG-007 (gem5 ELF load crash)** — highest priority: blocks dual-backend
   verification of work already claimed done (picolibc goal①/②).
   - DG-007a: root-cause `gem5-se-lld-elf-load-crash` (subagent, read/diagnose
     only — gem5 generic ELF loader vs. DADAO-specific loader hook vs.
     memory-layout collision with `argsInit`).
   - DG-007b: fix based on root cause.
   - DG-007c: dual-backend re-verify `printf_hello.test` + `malloc_hello.test`
     on gem5, full E2E + differential regression.
2. **DL-065 (`dadao-oz-undef-physreg`, -O1+ codegen gap)** — needed before
   llvm-test-suite can run above -O0.
   - DL-065a: root-cause the "undefined physical register" at -O1+.
   - DL-065b: fix.
   - DL-065c: verify -O1 E2E + regression (does not need to reach -O2 yet).
3. **ML-004 (llvm-test-suite SingleSource wiring, ADR-0012 T3)** — first real
   large-scale regression surface once 1-2 are unblocked.
   - ML-004a: wire the build/run infrastructure (cross-compile via clang,
     execute via QEMU, collect pass/fail) for a small SingleSource subset.
   - ML-004b: run the subset, triage failures (real backend bugs vs. missing
     libc surface vs. test-suite assumptions that don't hold for a freestanding
     target).
   - ML-004c: fix whatever is cheaply fixable from the triage.
   - ML-004d: lock in as a `make check-suite`-style gate (not part of `make
     check`, same pattern as `check-golden`/`check-legality`) and record what's
     still open for a later round.

This list is a plan, not a contract — findings at any step may re-scope later
steps (e.g. DL-065's root cause may turn out to be multiple independent bugs,
or ML-004a's wiring may surface gaps that reorder the triage). Progress and any
re-scoping is tracked in the task files (`code-agent/tasks/DG-007*`,
`DL-065*`, `ML-004*`) and folded back into this section as it lands.

## Deferred Milestones

- Fix `gem5-se-lld-elf-load-crash` (unblocks dual-backend verification for
  the whole picolibc/clang pipeline).
- Function-pointer indirect call (deferred 2026-07-12, decision C).
- Complete ABI and runtime; aggregate/struct-by-value, struct return,
  `llvm.mem*` intrinsic inline-expansion (all gated on clang, now available —
  not yet started).
- `dadao-oz-undef-physreg` (-O1+ codegen gap, needed before llvm-test-suite
  at -O2).
- musl (phase 2 libc; provides the large/variable-size `memcpy`/`memset`
  libcall symbols; gated on a real kernel).
- llvm-test-suite SingleSource (ADR-0012 T3).
- Kernel bring-up.
- Dynamic linking, TLS, signals, atomics, and SMP.
