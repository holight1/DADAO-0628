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

**Open blockers** (corrected 2026-07-14 by DG-007a — an earlier note claimed
both goals hit "the same" gem5 crash; that was a truncated-output misread,
they are two independent bugs):
- `gem5-se-heap-not-covered-by-elf-segment` (blocks goal②): `dadao.ld`'s
  `__heap_start`/`__heap_end` aren't inside any `PT_LOAD` segment's `memsz`,
  so gem5 SE's page table (built strictly from ELF segments) faults on the
  first heap access. QEMU is unaffected because it loads a flat binary with
  no ELF segment parsing at all.
- `codegen-indirect-call-rb0-misuse` (blocks goal①): `CALL_PSEUDO_INDIRECT`'s
  expansion uses `rb0` (architecturally PC+4, not zero) as the base for an
  absolute-address indirect call — the stdout put-function-pointer callback
  hits this. QEMU "works" only because of the separate, already-tracked
  `QEMU-rb0-not-maintained` defect (QEMU never updates rb0, reads 0), which
  coincidentally cancels the miscompilation; gem5 correctly maintains rb0 and
  so exposes the real bug. This is a genuine miscompilation, not gem5-specific.

**Neither picolibc goal is dual-backend verified yet** — both are QEMU-only
until their respective blocker is fixed.

**★ Status (2026-07-14, closed out)**: the whole DG-007/DL-066/ML-005/DL-067
chain landed. `printf_hello.test`/`malloc_hello.test` now pass real dual-backend
(QEMU+gem5) assertions — **picolibc goal①(printf)/goal②(malloc) are fully
verified on both backends for the first time since ADR-0014**. Along the way
this surfaced and fixed two more unrelated bugs beyond the original two:
- `picolibc-libc-rebuild-blocked` (ML-005a): a stale prebuilt `libc.a` didn't
  actually exercise the DL-066a fix; unblocked a clean rebuild (added a
  `jmp_buf` type for DADAO; confirmed the `atold_engine.c` long-double gap is
  a real structural issue, not a config toggle, and correctly left it alone).
- `codegen-string-fn-promote-crash` (DL-067a/b): a *from day one* backend bug
  where `ISD::BR_CC` was registered in two places (a Custom-legalize path that
  had never actually been consulted due to a wrong VT, silently propped up by
  a redundant pre-legalize DAG combine) — this crashed basic `string.h`
  functions (strlen, memset, memchr, strcat, strchr, strstr) at `-O0`,
  unrelated to floating point. Fixed; a new, separate, still-open issue
  (`codegen-global-addr-const-offset-dropped`) was found and deferred during
  verification.

`syscall_hello.test` has one pre-existing, unrelated failure tracked as issue
`syscall-hello-write-output-missing` (not investigated further — out of
scope for this chain).

## M2.6: dual-backend unblock + llvm-test-suite on-ramp (2026-07-14 architect roadmap)

Architect-proposed sequence, executed via subagent (not DS — the first thread
is gem5-internal work, which per `feedback_ds_gem5_semantic_unreliable` goes to
a subagent that owns the gem5 component, not DS):

1. **DG-007 / DL-066 / ML-005 / DL-067 (dual-backend blockers) — ✅ done.**
   DG-007a's root-cause pass found two independent bugs, not one, and fixing
   them surfaced two more:
   - DG-007a: root-cause — see "Open blockers" above.
   - DG-007b: fixed `gem5-se-heap-not-covered-by-elf-segment` — gave
     the linker-script heap region a `NOLOAD` output section inside the
     `:data` `PT_LOAD` segment so gem5's page table covers it; zero-cost on
     the QEMU flat-binary path.
   - DL-066a: fixed `codegen-indirect-call-rb0-misuse` — stopped using
     `rb0` as the call base; materializes the absolute target into reserved
     scratch register `rb5` via the existing rd2rb bridge (DL-051a) and emits
     `CALL_RRII rb5, RD0, 0` instead. New regression test `indirect_call.test`
     locks this down on both backends.
   - ML-005a: unblocked `picolibc-libc-rebuild-blocked` so `libc.a` could
     actually be rebuilt with the fixed compiler; found the deeper
     `codegen-string-fn-promote-crash` bug in the process.
   - DL-067a/b: root-caused and fixed the BR_CC premature-combine +
     wrong-legalize-VT bug; new regression test `align_strfn.test`.
   - DG-007c/DL-066b: dual-backend re-verify — `printf_hello.test` and
     `malloc_hello.test` now genuinely pass on both QEMU and gem5.
2. **DL-065 (`dadao-oz-undef-physreg`, -O1+ codegen gap) — ✅ done.**
   Root-caused and fixed in one pass: `CALL_IIII`/`CALL_RRII`/
   `CALL_PSEUDO_INDIRECT` had a static tablegen `Uses=[RD16..RD30]` list
   unconditionally attached to every call regardless of real argument count;
   `-O1+`'s `LiveIntervals` (never run at `-O0`) flagged the ones with no
   reaching definition. Fixed via the standard LLVM pattern (per-call-site
   explicit register operands from `LowerCall`, RISC-V style). A sweep of all
   963 picolibc `.c` files at `-O1` now shows zero remaining "undefined
   physical register" failures (down from ~63 in `argz_insert.c` alone). A
   separate, deeper gap was found and correctly left alone: 113 files still
   crash on `LowerCall emitted a return value for a tail call!` — DADAO's
   `LowerCall` never implemented tail-call opt-out — tracked as new issue
   `codegen-tailcall-lowercall-assert` (needed before `-O1+` picolibc builds
   end-to-end, not before this narrower fix).
3. **ML-004 (llvm-test-suite SingleSource wiring, ADR-0012 T3) — first round done.**
   - ML-004a (2026-07-15): wired the build/run infrastructure for a small
     SingleSource subset. 3/8 passed; 5/8 hit a real silent miscompile
     (`x & 0xFF` on a big-endian value reading the wrong byte).
   - DL-068a/b: first attempt (DL-068a) went off scope — an agent attempted
     an unauthorized rebuild of the LLVM patch-series git history, lost real
     work, then hit the account's weekly usage limit; the architect caught
     it before a background build could bake the regression into the
     installed compiler, and restored `.work/llvm` to the last verified-good
     commit (see `feedback_subagent_scope_drift_git_history` memory).
     Redispatched (DL-068b, 2026-07-16) with an explicit ban on touching git
     history — root cause turned out to be a global-address constant offset
     silently dropped in `DADAOAsmPrinter`, not the DAG-combine byte-offset
     logic originally suspected; fixed cleanly, and the fix also closed a
     second, previously separate open issue with the identical root cause.
   - **ML-004b (2026-07-16) — done.** 9 more tests wired and passing
     dual-backend (12/22 total now in `tests/lit/E2E/llvm-test-suite/`).
     The remaining 10 failures collapse into 4 distinct root causes, the
     biggest being a genuinely systemic register-allocation bug: `CALL_IIII`/
     `CALL_PSEUDO_INDIRECT` (the only two CALL instructions the register
     allocator sees) never attach a `RegMask` from `getCallPreservedMask()`,
     so it doesn't know GPRB (address-bank) registers above rb7 are
     caller-saved and lets stale addresses survive across calls that clobber
     them — affects 8 of the 10 failures. Tracked as
     `codegen-call-clobbers-gprb-not-declared` (root-caused with a verified
     minimal repro, not yet fixed — needs a `RegMask` operand on `LowerCall`
     plus full differential+E2E re-verification). The other 2 failures are 3
     independently-tracked, not-yet-investigated issues (a switch-dispatch
     MALIGN, a no-call wrong-value bug, and a QEMU/gem5 backend divergence).
   - **ML-004c (2026-07-16) — done. ★ 20/20 in `tests/lit/E2E/llvm-test-suite/`.**
     Fixed `codegen-call-clobbers-gprb-not-declared`: `LowerCall` now attaches
     a `RegMask` from `getCallPreservedMask()` to the CALL SDNode (standard
     LLVM pattern), closing 8 of the 10 outstanding failures at once. Found
     and fixed a second latent bug in the process: `storeRegToStackSlot`/
     `loadRegFromStackSlot` routed GPRB (address-bank) spills through the
     RD-bank encoding (silently corrupting the register index) — never
     triggered before because nothing had ever forced the allocator to
     spill a live-across-call GPRB value until this fix made that happen for
     the first time. Full differential + E2E re-verified (broad change,
     touches every call site) — zero regression.
   - **ML-004d (2026-07-16) — done. ★★ `tests/lit/E2E/` 54/54 — 100% pass,
     zero known failures, project-wide, for the first time ever.**
     Triaged the remaining 3 issues: `codegen-switch-dispatch-malign-in-callee`
     was a genuinely new root cause — three independent bugs stacked, all
     first exposed by jump-table dispatch (the first construct to reference
     same-`.text`-section symbols from same-section code; all prior
     `rela`/`addi_rb` use had been cross-section, for `.data` globals): (1)
     `DADAOAsmBackend::applyFixup`'s `FK_Data_8` case ignored `IsResolved`
     and wrote a raw pre-link value for "same-section" symbols, dropping a
     needed relocation; (2) `rela_page`/`rela_lo`'s same-section fast path
     (added in ML-003j chasing an unrelated bug, never fully validated) used
     an unsound formula — page-masking/low-12-bits aren't invariant under a
     constant shift from other object files, unlike the `call24`/`branch*`
     fast paths; (3) `BRIND` (jump-table dispatch) used `JUMP_RRII` with
     `RB0` directly as base — the same `rb0`-means-`PC+4` hazard DL-066a
     fixed for indirect calls, just for jump tables. All three fixed (the
     AsmBackend fix *removed* the unsound fast path entirely, deferring to
     the long-verified real-relocation path — simplification, not added
     complexity). **Side effect: this also fixed the long-standing,
     unrelated `syscall-hello-write-output-missing` bug** (same root cause,
     single object file) — closed too. The other two issues
     (`codegen-misha-sum-wrong-value-no-call`,
     `gem5-sign-conversions-backend-divergence`) turned out to already be
     fixed incidentally by ML-004c, re-verified with multiple independent
     inputs to rule out coincidence.
   - **ML-004e (2026-07-16) — done. Confirmed already covered, no new gate
     built.** Checked whether a separate `make check-suite`-style target was
     actually needed (as this list originally speculated) before building
     one. Finding: `tests/lit/E2E/llvm-test-suite/` is a plain subdirectory
     of `tests/lit/E2E/`, `tests/lit/E2E/lit.cfg` has no `config.excludes` or
     path-restricting glob, and lit recurses into subdirectories by default
     — so `llvm-lit tests/lit/E2E/` (the existing, only E2E entry point;
     there is no CI script or workflow file in this repo that separately
     globs `.test` files) already discovers and runs all 23
     `llvm-test-suite/*.test` cases as part of the same 54/54 run. Building
     a parallel `check-suite` target would have just re-run the identical
     command under a new name. Per the task's explicit instruction not to
     manufacture redundant machinery, no Makefile change was made; this
     entry (plus ADR-0012 D4) is the documentation lock-in instead —
     `llvm-test-suite/` is regular T2 E2E regression, not experimental/
     optional content. `make check` itself is unaffected (E2E has always
     run via the independent `llvm-lit` command, never through `make
     check`). Continue expanding the SingleSource pure-compute slice per D4.

This list is a plan, not a contract — findings at any step may re-scope later
steps. Progress and any re-scoping is tracked in the task files
(`code-agent/tasks/DG-007*`, `DL-065*`, `DL-068*`, `ML-004*`) and folded back
into this section as it lands.

## Ultimate CodeGen/libc target: full gcc-c-torture pass (ADR-0012 D5, 2026-07-16)

The user's stated end goal is the full C test suite passing, with every
non-passing case having a clear, defensible reason. `~/toolchain/llvm-unicore`
(the archived predecessor project) already proved this is achievable on this
architecture: running `SingleSource/Regression/C/gcc-c-torture` (llvm-test-suite's
bundled GCC C torture suite) via a CMake-integrated build against a real musl
libc, it reached **1617/1708 passing (94.7%)**, and a dedicated deep-dive
(`DL-028a-torture-failure-deep-dive.md`) confirmed **zero DADAO ISel/backend
bugs** among the remaining 91 failures — 51 are clang frontend limitations on
GCC extensions (nested functions, VLA-in-struct, unknown GCC builtins, `asm`
constraints, decimal float — would fail on any clang target, not DADAO-specific),
32 are test-suite companion files with no `main()` (not real link failures),
and 8 are QEMU emulation timeouts. Zero missing compiler-rt symbols, zero
runtime miscompiles among anything that compiled and linked.

DADAO-0628 should treat this failure taxonomy (not the old code) as the
acceptance template for "done" on gcc-c-torture. Two implications for
sequencing, per ADR-0012 D5:
- Reaching comparable coverage will very likely require **musl** (ADR-0014
  phase 2), not just picolibc — a large fraction of gcc-c-torture exercises a
  fairly complete hosted libc surface (`printf`, `malloc`, `string.h`,
  `setjmp`, ...) that picolibc's current phase-1 scope doesn't aim to cover.
  This doesn't change picolibc-first sequencing, it just names the real
  prerequisite for the *full* torture-suite milestone.
- The current ML-004 SingleSource pure-compute slice (no libc I/O) is the
  first rung of the ladder toward this — it exercises CodeGen correctness
  without needing musl first, and every real bug it surfaces (like
  `codegen-call-clobbers-gprb-not-declared`) is exactly the kind of gap that
  would otherwise resurface later, at much higher cost to diagnose, inside a
  full gcc-c-torture run.

### musl integration recon (ML-006a, 2026-07-16) — `docs/reviews/musl-recon-2026-07-16.md`

Pure research, no code written. Key findings:
- **TLS is not a blocker** (better news than ADR-0014 D5.1 originally worried):
  `contracts/abi/spec.md` §1.2 already defines `rb4 = rbtp`, and the LLVM
  backend already reserves RB4. Writing it needs no new instruction (an
  ordinary RB-bank register copy). musl's own source has **zero** uses of the
  compiler `__thread` keyword — its internal per-thread state is entirely
  derived from the TP register — so getting musl itself running needs no ELF
  TLS relocation types at all; those are only needed for *user* `__thread`
  variables, which can be deferred.
- **Current syscall surface gap**: only `write`/`exit`/`exit_group`/`brk` are
  implemented in the `cfx_smon` responder (QEMU + gem5). musl's mallocng
  allocator hard-requires real `mmap` (no brk fallback) — `mmap`/`munmap` are
  P0, `mprotect` is P1. Thread/signal syscalls can be deferred entirely for a
  static single-threaded first milestone.
- **ADR-0014 D2's syscall ABI does not need to change** — ADR-0014-D2's
  register convention was already chosen for zero-friction musl adoption; only
  the responder's `switch(sysno)` case tables need incremental additions.
- Rough estimate: **8-12 tasks** across phase A (syscall handlers, low risk)
  and phase B (musl arch skeleton + first E2E, medium risk — crt0 auxv
  synthesis is the one genuinely new piece of work, everything else has a
  "conclusion-level" precedent from the archived toolchain's port). Phase C
  (threading, signals, `__thread`, dynamic linking) explicitly deferred.
- **Concrete next tasks** (see report §7 for the full list): `cfx_smon`
  mmap/munmap handler → mprotect handler → musl crt0 auxv synthesis → musl
  `arch/dadao/` skeleton (syscall_arch.h/reloc.h/bits) → TLS stubs
  (`get_tp.s`/`__set_thread_area.s`) → `atomic_arch.h` (`__sync_*` builtins,
  not hardware LL/SC, per an old-toolchain lesson) → musl configure
  integration → two E2E milestones (bare `exit(N)`, then `malloc`+`printf`).

### Phase A complete (ML-007a, 2026-07-17): `cfx_smon` mmap/munmap/mprotect handlers

All three P0/P1 syscall handlers musl's mallocng allocator needs are now
implemented identically in QEMU and gem5, in a single task (not the 2-3 task
estimate above): `mmap` (bump allocator over a fixed `0x100000000` arena,
page-aligned), `munmap`/`mprotect` (both no-op, return 0 — no real reclaim or
protection tracking needed for the static single-thread milestone). Verified
with a hand-written discriminating probe (`tests/lit/E2E/mmap_probe.test`) that
asserts exact address deltas via register subtraction, not just "doesn't
crash" — E2E 55/55, differential AGREE(3-way)=200/Sail(4-way)=200 unchanged.
**Phase A is done.** Next up is Phase B: musl crt0 auxv synthesis, then the
`arch/dadao/` skeleton, per the task list above.

### Phase B, step 1 complete (ML-008a, 2026-07-17): musl crt0 auxv synthesis

A new crt0 variant (`tests/scripts/crt0_auxv.s`) hand-builds the
argc/argv/envp/auxv stack layout musl's `crt1.c` / `_start_c(long *p)`
protocol expects, entirely in user-mode `_start` — no simulator/loader
changes needed (this was the recon's predicted "genuinely new work" item,
since the old toolchain relied on a real QEMU linux-user/gem5 loader to
synthesize argv/auxv, which this project's system-mode harness doesn't have).
Validated with a discriminating probe (`tests/lit/E2E/musl_crt0_auxv.test`):
real ASCII byte compare for argv[0], a genuine auxv walk-and-dispatch loop,
and a match counter that catches both missing keys and wrong values —
confirmed via an independent architect-run mutation test (corrupted
AT_PAGESZ → exit 6, the expected fail code). E2E 56/56, differential
unchanged. **This was the one genuinely new piece of work in Phase B; the
remaining steps (syscall_arch.h/reloc.h/bits skeleton, TLS stub,
atomic_arch.h, configure integration, static-link E2E) all have
conclusion-level precedent from the archived toolchain to draw on.**

### Phase B, step 2 complete (ML-009a, 2026-07-17): musl arch/dadao compile-time skeleton

musl is now formally enabled in this repo's component-lock system (same
model as llvm/qemu/gem5/llvm-test-suite): pinned to upstream v1.2.5
(`0784374d`), with `syscall_arch.h`/`reloc.h`/`bits/*.h` added under
`components/musl/patches/`. These map cleanly against the *current*
ADR-0014 D2 ABI and `contracts/elf/spec.md`'s 10 relocation types — not the
archived toolchain's incompatible register/relocation numbering. A
full-tree `make -k lib/libc.a` compiles 766 of ~1600 candidate files;
zero remaining failures are attributable to the new headers — the rest is
the already-deferred `atomic_arch.h` and pre-existing backend codegen
limits (soft-float libcalls, `dynamic_stackalloc`, and the already-tracked
`codegen-tailcall-lowercall-assert` hitting a few new call sites, not a new
bug). The subagent's own review caught and fixed a real defect before
architect review even started: an early `CRTJMP` draft treated `ret`'s
compile-time-literal operand as a substitutable register, which would have
silently failed to transfer control once a follow-up task unblocks its
(currently unreachable) call sites.

**Side fix**: enabling a brand-new component surfaced a second `fetch.py`
bootstrap bug (independent of the 2026-07-15/16 patch-history incident) —
a fresh `--no-checkout` clone's dirty-check always fired (empty working
tree vs. populated HEAD tree reads as "every file deleted"), so `fetch.py`
could never actually bootstrap a component on its first run. Fixed
directly (`scripts/fetch.py`, commit `7d98b21`): the freshly-cloned case
now goes straight to `checkout --detach <pin>`, skipping both the dirty
check and the ancestor check (neither applies to a clone this same call
just created).

### Phase B, step 3 complete (ML-010a, 2026-07-17): musl atomic_arch.h

Probed `__sync_*`/`__atomic_*` builtins against the DADAO backend first
(as the task required, before assuming the old toolchain's approach would
just work) and confirmed a broad, genuine codegen gap: `ATOMIC_FENCE`/
`ATOMIC_LOAD`/`ATOMIC_STORE`/`ATOMIC_LOAD_ADD`/`ATOMIC_SWAP` all hit
"Cannot select", and `ATOMIC_CMP_SWAP` falls through to the same
unimplemented-libcall path already known from soft-float. Not a
one/two-pattern fix, so per the task's hard constraint, no backend code
was touched — tracked as `codegen-atomic-ops-unimplemented`. Since the
current milestone (ADR-0014 D5.2) is explicitly static single-threaded
(no `pthread_create` yet, so nothing can race), `atomic_arch.h` implements
`a_cas`/`a_swap`/`a_fetch_add`/etc. as plain non-atomic load-modify-store
C, loudly documented as not thread-safe and must be replaced before
multithreading is enabled. Compiled file count 766 → 778;
`atomic_arch.h`-related errors 198 → 0. This unblocked enough of the tree
to newly expose the next blocker (`pthread_arch.h` missing, 183 files) and
8 previously-hidden backend internal assertion crashes across 4 distinct
sites — all registered as new tracked issues, none diagnosed further
(that's follow-up work, not this task). E2E 56/56, differential
unchanged. Note: this subagent's session hit the account's weekly usage
limit mid-task (after the probe and the file write, before verification/
commit) — recovered cleanly by resuming the same agent via its transcript
rather than starting over, after confirming the repo was in a clean,
undamaged state first.

### Phase B, step 4 complete (ML-011a, 2026-07-17): musl pthread_arch.h + TP register read/write

Adds `arch/dadao/pthread_arch.h` + `get_tp.s`/`__set_thread_area.s`
reading/writing `rb4` (rbtp). Two real discoveries, both reported and
logged rather than fixed (out of scope): (1) a clang frontend gap —
`DADAOTargetInfo::getGCCRegNames()` omits the entire RB register bank, so
the usual "inline C asm with a named register variable" pattern every
other musl arch uses for this doesn't work here; worked around with real
standalone `.s` functions instead. (2) a genuine QEMU/gem5 divergence in
RB-bank block-copy instruction fidelity when the source's high 16 bits
are nonzero — gem5's masking depends on which *read* instruction is used,
QEMU's depends on which *write* instruction was used earlier; both
internally consistent, but disagreeing with each other, and tangled up
with a wording/vector inconsistency between `contracts/isa/spec.md §4.7`
and `tests/vectors/isa/rd-wyde-block.yaml`. Irrelevant to this task (real
musl TP/pointer values are always 48-bit-clean, verified on both
backends), logged as `blockcopy-rb-source-64bit-fidelity-backend-divergence`
for a dedicated follow-up. Compiled file count 778 → 937,
`pthread_arch.h`-related errors 183 → 0. E2E 57/57, differential
unchanged.

### Phase B, step 5 complete (ML-012a, 2026-07-17): musl crt_arch.h + first real static-link E2E milestone (exit 42)

`int main(void){return 42;}` compiled with clang and linked against
musl's real `crt1.o` + a 1166-of-1346-file `libc.a` subset now exits 42
on **both QEMU and gem5** via the real `crt1.c → _start_c →
__libc_start_main → __init_libc/__init_tls/__init_tp →
libc_start_main_stage2 → exit() → SYS_exit_group` chain — the first time
any musl program has actually run end to end on this project.

**Major discovery, ADR-level decision needed**: `DADAOCallingConv.td`
("GPRD only, Phase 5 spike") passes *all* i64-representable arguments,
pointers included, in the RD bank (`rd16`) — never the RB bank (`rb16`)
that `contracts/abi/spec.md §2.1` documents for pointer/address
parameters. Confirmed by reading the TableGen source, both
`AnalyzeCallOperands`/`AnalyzeFormalArguments` call sites (so caller and
callee sides are mutually consistent with each other, just not with the
written spec), and a disassembled probe. This was invisible until now
because every previous test had hand-written assembly calling *other*
hand-written assembly on both ends of a call — this task is the first
time hand-written asm (`crt_arch.h`) called a real compiler-generated
function with a pointer argument, which is exactly the boundary that
exposes the mismatch. Routed around on the musl side only (`crt_arch.h`,
and a genuine latent bug in ML-011a's `__set_thread_area.s` that had
never been exercised against a real compiled caller — fixed here); zero
LLVM changes. Logged as
`dadao-callingconv-pointer-args-use-rd-bank-not-rb-bank`. **Two paths
forward, neither decided by this task**: (a) implement the real RB-bank
pointer calling convention in the backend, or (b) formally revise
`contracts/abi/spec.md §2.1` via ADR to record current behavior (pointers
share the RD bank with scalars) as the accepted convention. This will
resurface at the next musl E2E milestone (malloc+printf, which mixes
compiled and hand-written code at more boundaries), so it's worth
resolving before then rather than routing around it repeatedly.

### DL-069a complete (2026-07-18): RB bank pointer calling convention implemented

User decided route (a): implement the real RB-bank pointer convention
rather than revise the ABI contract. `DADAOCallingConv.td` gained
`CCIfPtr` rules (RB16..RB31 for params, RB31 for returns) ahead of the
existing integer rules; `LowerFormalArguments` now derives the incoming
argument's register class from which bank `CC_DADAO` actually assigned.
Verified with a dedicated probe reproducing `contracts/abi/spec.md §2.3`'s
exact cross-bank overflow example (16 ints + 16 pointers + one more of
each + a third int → stack offsets 0/8/16 by declaration order regardless
of bank) — confirmed byte-exact, not just plausible. `check_codegen_abi.py`
now MATCHes on both pointer rules (was INFO); differential unchanged
(200/200/0); full E2E shows exactly the two predicted new failures
(`malloc_hello.test`/`printf_hello.test`, both linking
`tests/scripts/pico_stubs.s`'s hand-written `_write` stub which still
assumes the old all-RD convention — confirmed via an isolated rerun that
it's a real crash, i.e. genuinely broken by the ABI fix as expected, not a
silent wrong-exit-code artifact). This is the first task in the whole musl
port where LLVM backend code itself was changed, rather than routed
around.

**Follow-up needed (ML-013a)**: update `tests/scripts/pico_stubs.s`
(`_write`'s `buf` param moves rd17→rb16; `_sbrk`'s pointer return moves to
rb31), `.work/source/musl/arch/dadao/crt_arch.h` and
`src/thread/dadao/__set_thread_area.s` (both currently work around the old
convention, should revert to the RB-bank form — ML-011a's original
`__set_thread_area.s` was actually correct and got "fixed" into wrongness
by ML-012a only because the backend hadn't implemented RB bank yet), and
`tests/lit/E2E/tp_probe.test`; then rebuild musl and confirm
`malloc_hello.test`/`printf_hello.test` pass again.

### ML-013a complete (2026-07-18): downstream files reconciled, full E2E back to 58/58

All 4 files updated as planned. Two real issues found and root-caused
along the way: (1) **stale build artifacts** — `.work/picolibc/build-dadao/
libc.a` and `.work/build/musl`'s objects were compiled by the pre-DL-069a
clang; incremental builds don't track the compiler binary itself, only
source mtimes, so they silently kept mixing old- and new-ABI object files
until a clean rebuild was forced (see
`feedback_stale_build_artifacts_after_toolchain_rebuild` memory — worth
remembering for any future LLVM-backend-touching task). (2) **a genuine
new LLVM gap**: variadic functions' save-area logic only spills the RD
bank, so pointer varargs are silently lost post-DL-069a (confirmed via
disassembly — a 3-pointer-arg `printf` call places everything in
`rb16/rb17/rb18`, entirely missed by the RD-only save area). Not a
regression (varargs was always excluded from M1 scope); worked around at
the test level (`fputs` instead of variadic `printf`) and logged as
`varargs-pointer-args-lost-rb-bank-save-area` for a future task. Full E2E
58/58, differential unchanged, all 6 musl patches independently
reproducible from the pin commit.

**Side finding (unrelated, tracked separately)**: replaying the full
38-patch LLVM series from the bare pin commit fails at patch 0005 (long
predates this session) — nobody had verified a full from-scratch replay
before; DL-069a's own patch (0038) replays cleanly on its immediate
predecessor, so this doesn't block anything here, but it's a real
reproducibility risk worth its own follow-up
(`llvm-patch-series-full-replay-corrupt-at-0005`).

Two more already-tracked backend gaps were routed around musl-side only:
`-fno-optimize-sibling-calls` in a new `arch/dadao/arch.mak` (works around
`codegen-tailcall-lowercall-assert`; as a side effect also unblocked
~229 other musl files tree-wide), and a `volatile`-qualified barrier
replacing an inline-asm operand trick DADAO can't allocate a register for
(`musl-inline-asm-empty-clobber-reg-alloc`). One new link-time-only gap
was found and routed around: a PC-relative relocation for "address of a
weak-undefined external symbol" has no wide-range fallback
(`dadao-pcrel-reloc-no-farsym-fallback`) — safe to route around here
because the affected code path (`_DYNAMIC`/`PT_DYNAMIC`) is also
runtime-dead in this static-only, no-dynamic-linker configuration.

A `make build-musl` target was added (configure + best-effort `make -k` +
archive-what-compiled, mirroring `build-picolibc`'s existing pattern) so
this milestone is reproducible from a clean checkout. E2E 58/58,
differential unchanged.

### Scheduling decision (2026-07-18): fix varargs pointer-arg loss before the torture sweep

`varargs-pointer-args-lost-rb-bank-save-area` (found during ML-013a) is
scheduled: **not** an immediate priority (ML-014a's malloc+printf
milestone works around it fine with `puts`/integer-only `printf`), but
**not deferred indefinitely** either — it needs to land after ML-014a and
before the first large-scale gcc-c-torture/llvm-test-suite sweep or
kernel K1 work, so this known gap doesn't get conflated with genuine
torture-suite failures at scale (`printf`/`sprintf`-with-`%s` diagnostic
output is pervasive in gcc-c-torture). Fix direction: mirror
`contracts/abi/spec.md §2.3`'s shared-overflow-area rule (one save area
ordered by original declaration sequence across both banks, not two
separate per-bank save areas) — this is the same mechanism that already
solves "how does the callee know which bank the next value came from"
for the stack-overflow case, independently re-verified during DL-069a's
ground-truth review with a probe matching §2.3's own cross-bank example.
See `contracts/abi/spec.md §6` and `docs/open-spec-issues.md` for the
now-annotated Varargs entry.

### Infrastructure fix found while reviewing ML-006a: `scripts/fetch.py` silently discarded applied patches

While spot-checking the recon report's QEMU source citations, found
`.work/source/qemu`'s `target/dadao/` directory entirely missing — `git log`
showed HEAD reset to bare upstream, `git reflog` confirmed `fetch.py`'s
`git checkout --detach <pinned commit>` had silently discarded all 16 applied
QEMU patch commits (likely triggered when ML-004a re-ran `make fetch` to pull
in the new `llvm-test-suite` component — the loop touches *every* enabled
component, not just the new one). This is almost certainly the same root cause
behind the earlier DL-068a incident (`.work/llvm`'s history getting mangled) —
that agent likely encountered `.work/llvm` already silently reset by this same
bug and misdiagnosed it as needing a full patch-series rebuild. Recovered
`.work/source/qemu` via `git reset --hard` to the last-known-good commit found
in reflog (matching patch 0016 exactly), and fixed `fetch.py`'s root cause: it
now checks `git merge-base --is-ancestor <pinned-commit> HEAD` before doing
anything, and skips the checkout entirely if the pinned commit is already an
ancestor of HEAD (i.e. patches are already applied on top) — verified against
the real repo state (`llvm`/`qemu` correctly detected as "already patched,
leaving alone"). `make fetch` is now safe to re-run at any time. See
`feedback_subagent_scope_drift_git_history` memory for the full incident
retrospective.

## Deferred Milestones

- `codegen-tailcall-lowercall-assert` (`LowerCall` never implemented
  tail-call opt-out; 113/963 picolibc files still crash on it at `-O1+`,
  found during DL-065a's verification sweep).
- Function-pointer indirect call (deferred 2026-07-12, decision C — the
  general `CALL_INDIRECT_PSEUDO`/scheduler case, distinct from the simpler
  mechanism DL-066a fixed).
- Complete ABI and runtime; aggregate/struct-by-value, struct return,
  `llvm.mem*` intrinsic inline-expansion (all gated on clang, now available —
  not yet started).
- `syscall-hello-write-output-missing` (pre-existing, unrelated to any
  recent work; `syscall_hello.test`'s SYS_write produces no output on QEMU
  despite a correct exit code).
- Dynamic linking, signals, atomics, SMP, and user `__thread` TLS relocations
  (musl's own static-single-thread subset does NOT wait on these — see
  ADR-0014 D5.2 / ML-006a; only genuinely thread/kernel-dependent features
  are deferred here).

## Kernel bring-up (ADR-0015, 2026-07-18)

The project's ultimate milestone is QEMU + kernel + a real userspace
application (the musl work already substantially completed is the
"userspace application" half of that). Kernel bring-up itself has not
started yet; ADR-0015 charters it based on a survey of the archived
`~/toolchain/DADAO` predecessor's three kernel bring-up attempts
(V1/V2-V4/V5), none of which reached stable userspace execution — V1 got
as far as printing `Run /init as init process` before crashing on a never-
activated page table switch (built against an ISA guess later overturned
by the official spec); V2/V4 (rebuilt against spec, with a bare-metal-TDD-
first discipline) got architecturally further but stalled before that
point on RA-stack/interrupt-polarity bugs; V5 (a further spec rewrite)
never got past QEMU exception-entry plumbing before the project was
archived. No kernel source/patches are reusable (5+ incompatible ISA
revisions since); only the ~20-item pitfall list and design conclusions
carry forward — same "conclusions only" pattern used for the musl port.

**Decisions**: target kernel = Linux 5.4 (non-binding, matches the old
project's choice); no firmware/SBI-monitor layer for now (continue direct
`-kernel`/ELF loading, no bootloader handoff — this wasn't what blocked
the old attempts, so it's not a prerequisite for the milestone).

**Phased plan**:
- **K0 (recon, next up)**: survey the current wiki pin's (`9f378f4`) full
  SEE §5/interrupt-model/MMU-SBI definitions against what DADAO-0628 has
  today (only the `cfx_smon` syscall trap) — produce a gap list; confirm
  the Linux 5.4 target; distill the old project's ~20 pitfalls into a
  "required reading" checklist for the tasks that follow. Same shape as
  the `ML-006a` musl recon that worked well.
- **K1**: complete the SEE/interrupt/MMU-SBI infrastructure (timer
  interrupts, page faults, real privilege-mode switching, PTBR/PTHI/PAHI-
  style TLB ops) on both backends, broken into incremental tasks the way
  musl Phase A/B was.
- **K2**: bare-metal kernel-mode regression *before* touching real Linux
  source — context switch, trap dispatch, MMU enable/disable, all pinned
  down with dual-backend + differential verification first. This is the
  single biggest lesson from the old project: V2/V4's TDD-first discipline
  got further than V1's "just try to boot it" approach.
- **K3**: the real `arch/dadao` Linux port, written fresh against the
  current spec (lessons only, no ported code), targeting `do_initcalls`/
  `kernel_init` as the first real milestone.
- **K4 (the actual "QEMU+kernel+userspace app" milestone)**: `Run /init`
  actually executing a real musl-linked program — directly consuming the
  musl work already done.

ADR-0012 D5's gcc-c-torture goal is expected to keep progressing mostly
independently of this (most torture cases are single-process compute that
doesn't need a real kernel); kernel bring-up mainly unblocks the
fork/exec/signal-dependent subset.

### K0 complete (KL-001a, 2026-07-18): kernel bring-up recon

Full report at `docs/reviews/kernel-bringup-recon-2026-07-18.md`. Two
high-value findings (both independently re-verified against the wiki
source):

1. **SEE §5 is a complete spec at the current pin, not a draft** — but
   DADAO-0628's existing `cfx_smon` implementation is a pure host-side
   shortcut (QEMU C code directly simulating write/exit/brk); `escape`,
   `cfx2rd`/`cfx2rc`, `cfxld`/`cfxst`, `inner_run_mode`, and cg5 exception-
   state registers are entirely unimplemented in both backends (confirmed:
   zero matches grepping either patch series). K1 is "upgrade the shortcut
   to the real mechanism," not "start from zero."
2. **HBI §3 mandates hardware always resets into hypv mode**, requiring a
   small hypv→supv handoff stub before reaching S-mode — see ADR-0015 D2's
   clarification. **New finding beyond the original ~20-pitfall list**:
   `contracts/isa/spec.md §7` excludes both `ldmo-ra`/`stmo-ra` (RA↔memory)
   and `rd2ra`/`ra2rd` (RA↔RD) from M1, while the AEE wiki mandates saving/
   restoring all of `ra0-ra63` on process switch — there is currently no
   ISA-level mechanism at all to persist the RegRAS bank. This is more
   fundamental than any of the old project's context-switch pitfalls
   (which at least had *some*, if misused, instruction available) and is
   the top-priority open item before K1 implementation starts.

The old project's ~20 pitfalls were re-verified one by one for continued
applicability and condensed to a 10-item checklist (report §4.2); the
`linux-0504` tree was confirmed to be essentially clean vanilla 5.4.0
(`arch/dadao` is an external symlink, the only 7 commits ahead of `v5.4`
are trivial uapi/Makefile tweaks) and reusable as the port baseline
without re-fetching upstream. The report proposes a 10-task K1 breakdown
(KL-101a..KL-110a, first task = the hypv→supv handoff stub + privilege-
mode state modeling) with dependency ordering.
