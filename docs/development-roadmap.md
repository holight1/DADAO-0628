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

### Current route decision (2026-07-21)

After the mallocng chain closed, the next priority is to stabilize the LLVM + QEMU
side independently: rebuild QEMU after each scoped patch, keep the M1 bare-metal
harness green, and maintain a fresh `tests/lit/E2E/` baseline including the
`llvm-test-suite/` subdirectory. Kernel/SEE/CFX implementation is intentionally
paused at the accepted KL-101a/KL-102a recon and KL-102b QEMU state scaffold until
this baseline and the remaining LLVM ABI gaps are under control. This is a route
decision, not a claim that the kernel prerequisites are complete; the task ledger
and fresh-test artifacts remain authoritative.

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

### ML-014 mmap backing and musl malloc follow-up status (2026-07-18)

The original ML-014a malloc milestone exposed that the fixed mmap arena had
only address accounting, not real backing. This has now been split and closed
as follows:

- ML-014c (QEMU) and ML-014d (gem5) add backend-specific arena backing;
- ML-014e adds `tests/lit/E2E/mmap_backing_probe.test`, including real
  `sto/ldo`, cross-page markers, cursor/error-path checks, and
  `munmap`/`mprotect` checks. It passes both backends, and the full E2E gate is
  59/59 with four-way differential `AGREE(4-way)=200/DIVERGE=0`;
- the former open issue `mmap-arena-unbacked-real-memory-qemu-gem5` is archived
  with the complete discovery and resolution evidence;
- ML-014f is the continuation of ML-014a. It confirmed the mallocng direct
  `mmap` threshold (`131052`) and generated a musl-side `-O0/optnone`
  candidate, but its malloc/free/output runtime still fails to reach exit 42
  (QEMU 130/hang, gem5 0). The candidate test and patch are not in the main
  series; ML-014a remains open and must not be reported as complete until an
  independent rerun reaches both-backend exit 42.

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

## Codex handoff episode (2026-07-18~22): musl malloc+printf milestone continuation, then cleanup

A session context reset handed the ML-014a (musl malloc+printf E2E) milestone
to an independently operating agent ("codex") for 2026-07-18~21. It produced
~60 task files (`ML-014b..q/r..z/aa..ag`, `ML-016a..z`, `ML-017a..d`) and
several genuine, independently-reviewed fixes: QEMU mmap arena backing
(`ac58f31`, patch `0018`), gem5 mmap/SYS_brk VMA backing (`6dd0d7c9f1`/
`e6a6b9cdc9`/`c7e92c7f80`, patches `0012-0014`), an lld `RELA_PAGE`
cross-page fix (`92dd91c67c08`, patch `0039`+`0041`), 4 LLVM CodeGen fixes
(AsmPrinter external symbol, inline asm register constraint, i1 sign
extension, frame alignment — patches `0042-0045`), and a wiki-pin-drift
reconciliation (`IN-002a`/`IN-003a`) that restored `make check` to green.
**The milestone itself remains incomplete** — its own final handoff
(`docs/reviews/ML-017d-final-handoff-roadmap-20260721.md`) honestly reports
`puts`/stdout still produces no output marker on either backend; that
report's own A/B/C/D/E roadmap (stdio runtime → vfprintf/libcall →
optional be99→d3bd causal isolation → mallocng e2e → kernel) is the
reference for whoever picks ML-014a back up.

An architect audit (`docs/reviews/codex-run-integrity-audit-2026-07-21.md`,
task `IN-004a`) found the technical output real but patch-export/disclosure
discipline had drifted over the ~60-task run: 7 real commits (LLVM×4,
gem5×2, QEMU×1) were never exported to `components/*/patches/`, with the
QEMU one being an *uncommitted dirty working tree* backed by a patch file
using a fabricated all-zero commit hash (genuine data-loss risk — any
`git checkout`/`clean`/`reset --hard` would have silently destroyed it);
a since-Blocked task's project-wide musl `-O0` CFLAGS override
(`arch/dadao/arch.mak`) silently became the undisclosed baseline every
subsequent ML-016/017 object-matrix number depended on, masking a real
unfixed backend bug; and a legitimate vector correction (`ML-015c`)'s
differential-baseline side effect (`gem5-SKIP` 0→2) was never re-verified
by any later task. See `feedback_codex_handoff_discipline_drift` memory
for the full retrospective.

Cleanup (`IN-005a`+`DL-070a`, 2026-07-22): exported all 7 pending patches
(QEMU's dirty tree committed first, verified byte-identical to the old
fake patch via `git apply --check --reverse` before committing); then
fixed the real bug the `-O0` workaround was hiding — `DADAOInstrInfo.td`'s
`CALL_IIII`/`CALL_RRII`/`CALL_PSEUDO_INDIRECT` never had their `Defs` list
updated after `DL-069a` routed pointer returns to `rb31`, so
MachineVerifier (active at `-O1`+) flagged the caller-side `$rb31` copy
after any pointer-returning call as reading an undefined physical
register. Fixed (patch `0046`), independently verified: a full musl tree
rebuild's "undefined physical register" failure count drops from 16 to 0.
Registered `gem5-differential-harness-stale-blanket-skip-rasuf` in
`docs/issues.yaml` documenting the `gem5-SKIP=2` root cause (a stale
harness rule, not a real gem5 regression). Full E2E 59/59, differential
`AGREE(3-way)=200/gem5-SKIP=2/DIVERGE=0` (this is now the accepted
baseline going forward, not a regression to chase back to `HARNESS=6`)
unchanged throughout.

### ML-018a complete (2026-07-22): musl `-O0` workaround fully removed

An exploratory (not foregone-conclusion) verification of whether
`arch.mak`'s project-wide `-O0` override could be dropped now that
DL-070a fixed the RB31 bug it was masking. Method mattered here: musl's
`OPTIMIZE_GLOBS` forces `internal/*.c`/`malloc/*.c`/`string/*.c` to `-O3`
regardless of `arch.mak` (clang's last `-O` flag wins), so DL-070a's own
2 representative files were never actually protected by `-O0` — the real
open question was the rest of the tree (`stdio/`, `stdlib/`, `unistd/`,
etc.), stuck at `-O0` and never tested at `-O1`+ since ML-014f landed.
Clean, serial (`-j1`) from-scratch rebuilds both with and without the
line (parallel `-j6` builds were found to have real nondeterministic
target-discovery gaps and were discarded) showed removing `-O0` takes
total failures 165→176, but every one of the 11 net-new failures matches
an already-open `docs/issues.yaml` entry discovered at real `-O2` back in
ML-010a/ML-011a (2026-07-17, before `-O0` ever existed) — no new/unknown
failure category appeared, and RB31 held at 0 failures across the full
1170/1346-object sweep, confirming DL-070a's fix tree-wide. Decision:
fully removed (not partial); also exported the two prior un-exported
musl commits (`8ecf6f6e`, `4741d4d1`) IN-004a's audit had flagged,
alongside this task's own change, as `components/musl/patches/0007-0009`.

**Next**: tackle the real remaining ML-014a blocker (stdio/`puts`
runtime, roadmap item A above) with the project's usual one-task-at-a-
time, architect-ground-truth-reviewed rigor rather than another large
autonomous run.

### ML-019a complete (2026-07-22): roadmap A (stdio/writev/stdout) closed

Root cause (architect-diagnosed by reading the code directly, before
dispatch): musl's buffered stdio write path (`__stdio_write.c`) calls
`syscall(SYS_writev, ...)`, not `SYS_write` — but both QEMU's
(`target/dadao/cpu.c`) and gem5's (`src/arch/dadao/decoder.cc`) cfx_smon
syscall responder only ever implemented `case 64`
(`write`)/`93`/`94`(exit)/`214`(`brk`)/`222`(`mmap`)/`215`(`munmap`)/`226`
(`mprotect`); anything else, `writev`(66) included, fell through to
`default: ret = -ENOSYS`. That is exactly why `puts`/`fputs`/integer
`printf` returned negative with nonzero errno on both backends
(ML-017d's blocking finding) while a raw `write()` control test worked.

Fix: added a differential-equal `case 66` to both responders (16-byte
big-endian `struct iovec` parsed with each backend's existing
byte-read primitive, sum of `iov_len` returned on success, matching
`__stdio_write.c`'s `cnt==rem` contract; only `fd==1/2` write/count,
deliberately overriding gem5's pre-existing unconditional-stdout quirk
in `case 64` so the two backends agree on `writev`). New
`tests/lit/E2E/musl_puts_writev.test` asserts the actual output marker
via FileCheck, not just exit code — closing the exact blind spot that
let ML-017c's "targeted gate" pass while stdout stayed broken.
QEMU `cf5c06b`, gem5 `ca12f826`; patches exported immediately
(`components/qemu/patches/0020-...`, `components/gem5/patches/0015-...`).
E2E 59→60/60 zero regression, differential AGREE=200/DIVERGE=0
unchanged, manifest/issues PASS — all re-verified independently by the
architect (fresh `ninja`/`scons` rebuilds + reruns) before commit
(`3b943f7`), not just taken on the subagent's report.

Roadmap B (`vfprintf`/`vfscanf`/157-cluster libcall), C (optional
be99→d3bd causal isolation), D (mallocng e2e / ML-014a itself), E
(kernel) remain untouched and unblocked by this task's scope.

### ML-020a complete (2026-07-22): roadmap B partial — f64 libcall names fixed, deeper CodeGen defect found

`DADAOISelLowering.cpp` had never registered any f32/f64 register class
or operation action, so DADAO had zero floating-point support. The
first real `double` comparison in musl (`vfprintf.c`'s `printf_core`)
hit `report_fatal_error: unsupported library call operation` — LLVM's
new TableGen-based `RTLIB::LibcallImpl` infrastructure
(`llvm/include/llvm/IR/RuntimeLibcalls.td`) had no entry telling it
GNU-style soft-float libcalls (`__adddf3`, `__eqdf2`, ...) exist for the
`dadao` triple. Fixed with a 16-line `DADAOSystemLibrary` entry mirroring
Lanai's soft-float-only pattern (`components/llvm/patches/0047-...`,
commit `9bb9dffdaeb7`) — no `DADAOISelLowering.cpp` changes needed,
since not registering a float register class already routes f32/f64
through LLVM's generic softening path once a libcall name resolves.

This unblocked compilation broadly (`vfscanf.o` now compiles; musl
fresh-build failures for the two relevant issue clusters went from 9
combined trigger files to 103) but exposed a real, pre-existing,
unrelated SelectionDAG glue-chain defect once floating-point code
actually type-legalizes: any block with 2+ independent
libcall-originated `CALL`s breaks DADAO's hand-built glue chain in
`DADAOISelDAGToDAG.cpp` (`ScheduleDAGSDNodes` assertion — same assertion
as the deferred 2026-07-12 `DL-063c` indirect-call investigation, though
that specific indirect-call issue has since been independently resolved
via a `Pat<>`-based `CALL_PSEUDO_INDIRECT`; the *direct*-call path
(`CALL_IIII`) never got the same treatment and still hand-builds its
`MachineNode`, which is the prime suspect). `vfprintf.o` itself still
fails to compile on this. Recorded with full reproduction evidence
(2-line minimal case, gdb-located faulty glue operand) in
`docs/issues.yaml`'s `musl-backend-assert-illegal-result-number` /
`musl-backend-assert-node-already-inserted` entries.

E2E 60/60, differential AGREE=200/DIVERGE=0, manifest/issues PASS
(architect-verified independently: rebuilt clang/llc/lld, reproduced
both the 2-line minimal case and the `vfprintf.o` failure signature
directly, commit `253a84f`).

**Follow-up dispatched**: `ML-021a` — attempt to convert the direct-call
path to `Pat<>`-based selection (mirroring the already-working indirect
path) to fix the glue-chain defect. Explicitly flagged as a third
attempt at a related class of bug (after two deferred DL-063b/c rounds)
with permission to stop and report rather than force a low-confidence
fix.

### ML-021a complete (2026-07-23): the real root cause, much bigger win than scoped

The actual bug was different from the `Pat<>`-vs-hand-built hypothesis
this task was dispatched to test (that hypothesis had, in fact, already
been tried and failed independently before — see the task's own
completion section). Found via SelectionDAG debug dumps
(`llc -debug-only=isel`), as the task's hard constraints required
before any fix attempt: `DADAOISelDAGToDAG.cpp::Select()` hand-special-
cased `ISD::CALLSEQ_START`/`END` — deleting the node and redirecting
only its **chain** result (ResNo 0) to the input chain, never its
**glue** result (ResNo 1). Invisible with one call per block; with a
second independent call (direct, indirect, or libcall) in the same
block, the freed node's memory got reused and a dangling glue edge
corrupted the DAG, tripping the exact assertion `DL-063c` hit in 2026
(a different, since-independently-resolved cause) and `ML-020a`'s f64
libcall fix re-exposed at scale.

Fix: converted `callseq_start`/`end` to standard `Pat<>`-based selection
via new `ADJCALLSTACKDOWN`/`UP` pseudos (mirroring RISC-V's reference
pattern) instead of hand-rolled node surgery, so `InstrEmitter`'s
generic multi-result rewrite threads both chain and glue automatically.
Wired `DADAOInstrInfo`'s `CFSetup`/`CFDestroy` (previously literal `0`)
to the new pseudos so `PrologEpilogInserter` actually elides them.
Commit `4b812d2f9930`, patch `0048`.

Impact far exceeded the task's own scope (fixing `vfprintf.o`
specifically): a **fresh full musl rebuild dropped from ~180 failing
objects to 10** — 3 existing issues (`illegal-result-number`,
`node-already-inserted`, `asmprinter-unmapself`) fully resolved and
archived; 7 objects newly exposed a real, unrelated, pre-existing gap
(`ISD::DYNAMIC_STACKALLOC` was never implemented — new open issue
`musl-backend-dynamic-stackalloc-unimplemented`); 2 pre-existing,
unrelated failures (`unanalyzable-fallthrough`, `instrinfo-unreachable`)
untouched. `vfprintf.o` now compiles with musl's real `-O2` build flags.

E2E 60→61/61 (new non-float regression test
`direct_call_multicall_block.test`), differential AGREE=200/DIVERGE=0
unchanged, manifest/issues PASS — architect-verified independently
(rebuilt toolchain, reproduced both the crash and the fix on the
2-line minimal case, reran the full musl fresh-build matrix from
scratch and confirmed all 10 remaining failures by name match exactly).

**Compile succeeding is not roadmap B's finish line** — the architect
independently attempted linking a real integer-format `printf` test
right after this task closed and confirmed exactly 7 missing link-time
symbols (`__adddf3`/`__subdf3`/`__nedf2`/`__fixdfdi`/`__fixunsdfdi`/
`__floatsidf`/`__floatunsidf`), matching `ML-020a`'s "option A" (small
shim) threshold precisely. **Follow-up dispatched**: `ML-022a` — a
minimal 7-symbol soft-float shim in `musl/arch/dadao/`, algorithm
reference only from `compiler-rt/lib/builtins` (not a vendored
component), to actually link and run an integer-format `printf` E2E
test end to end.

### ML-022a complete (2026-07-23): roadmap B closed — printf actually links and runs

Re-running the architect's 7-symbol repro against the current `libc.a`
turned up **10** undefined symbols, not 7 (`printf_core` references the
full double-precision family — `%f`/`%g`/`%e` handling code type-
legalizes alongside `%d`/`%u` regardless of which format string a
caller actually uses at runtime). Also corrected the task's own wrong
assumption about where to put the file: `arch/dadao/` is never
auto-globbed into the musl build (only `src/*/dadao/`, `crt/dadao/`,
`ldso/dadao/`, and the mallocng `dadao/` subdirectory are) — landed at
`src/internal/dadao/softfloat_shim.c` instead, following the existing
`src/internal/i386/` precedent.

Self-contained IEEE-754 binary64 implementation (526 lines, commit
`fe3f43b6`, patch `0010`) covering `__adddf3`/`__subdf3`/`__muldf3`/
`__nedf2`/`__eqdf2`/`__unorddf2`/`__fixdfdi`/`__fixunsdfdi`/
`__floatsidf`/`__floatunsidf` — every operation implemented as pure
bit-pattern integer arithmetic (deliberately never `+`/`-`/`==`/`!=` on
a native `double` anywhere in the file, since DADAO has no f64 register
class and any such operator would itself re-legalize into a recursive
libcall against the very symbol being defined). `__subdf3`'s
tail-call into `__adddf3` relies on the tree-wide
`-fno-optimize-sibling-calls` musl already builds with (ML-012a),
avoiding the pre-existing, unrelated `codegen-tailcall-lowercall-assert`
gap. Fuzz-verified against native hardware doubles (~200k random values
+ boundary cases: subnormals, ±inf, NaN, 2^63/2^64 overflow) with zero
mismatches.

The architect's exact repro (`printf("value=%d\n", 42); return 42;`)
now **links and runs correctly on both QEMU and gem5**, printing
`value=42` and exiting 42 — new `tests/lit/E2E/musl_printf_int.test`
asserts the real output content via FileCheck, not just the exit code.
E2E 61→62/62, differential AGREE=200/DIVERGE=0 unchanged, manifest/
issues PASS, musl fresh-build object count 1336→1337 with the same 10
pre-existing, unrelated failures — architect-verified independently
(rebuilt musl from scratch, reproduced the link failure→success
boundary directly with the same command, confirmed the vfscanf gap by
hand). Commit `f442d1a`.

`vfscanf`/`floatscan.c` needs a different, larger symbol set
(single-precision f32 family + `__divdf3`/`__gedf2`) not covered here —
recorded as a new open issue
(`musl-vfscanf-missing-single-precision-and-divide-softfloat-symbols`),
deliberately out of scope (a new precision family + division algorithm,
not "a few more of the same kind").

**Roadmap B is now closed for its stated scope** (integer-format
`printf` links and runs on both backends with real output verified).
`scanf` integer format remains open (separate symbol gap above).
Roadmap C (optional be99→d3bd causal isolation) and E (kernel) remain
untouched.

### ML-014a / roadmap D complete (2026-07-23): mallocng e2e milestone closed for real

Blocked since 2026-07-18 across `ML-014f`/`j`/`m`/`n`/`o`/`p` (archived
in `code-agent/tasks/archive/2026-07-ml014-malloc-e2e-run/`): a real
`mallocng` allocation chain hit a gem5 page-table fault at `0x90001000`
and QEMU follow-up-probe failures (exit 13/14), root cause never found
("needs a separate investigation"). The architect independently
reproduced the exact historical repro on current HEAD (post `DL-070a`/
`ML-018a`/`ML-019a`/`ML-021a`/`ML-022a`) *before dispatching any task*
and found it now passes cleanly on both backends — strong evidence
`ML-021a`'s `CALLSEQ_START/END` glue-chain fix was the real root cause
of the old gem5 fault all along (mallocng's allocator makes several
consecutive calls within one basic block, exactly that bug's shape).

`ML-023a` independently re-verified this (its own fresh compile/link/
run, not trusting the architect's numbers) and formalized it as
`tests/lit/E2E/musl_malloc_printf.test`: two real allocations (131052
and 262144 bytes, both `>= MMAP_THRESHOLD` so both take the real
`mmap(222)` path, not the size-class slab pool), page-granularity
write/read-back verification, `free`, `puts()` output, exit 42 on both
QEMU and gem5. mmap-triggering verified discriminatively — both
pointers land inside the dedicated mmap arena with monotonically
increasing addresses; a `malloc(8)` negative control does not.

An independent review caught a real defect worth remembering: the
first draft's `check_block` used a plain `char *`, and `-O2`'s
store-to-load forwarding proved the read-back always matches what was
just written, folding nearly every check to a compile-time constant
(only 1 real `load` survived in the whole IR; the failure branch was
unreachable) — silently defeating the "verify content, not just that
it ran" requirement this milestone had from day one. Fixed with
`volatile char *` access; architect-independently-verified (37 real
loads in the `-O2` IR, and a genuine negative control — one check's
expected value deliberately wrong — reproducibly fails at exit 12
rather than passing). This is a durable lesson for any future E2E test
in this project that verifies memory content at `-O2` or higher: a
plain-pointer round-trip check inside a single function is exactly the
shape LLVM's store-forwarding will optimize away.

E2E 62→63/63, differential AGREE=200/DIVERGE=0 unchanged, manifest/
issues PASS. No LLVM/QEMU/gem5/musl source changes were needed — pure
verification + test formalization on top of four already-landed
fixes. `code-agent/tasks/ML-014a-musl-e2e-malloc-printf.md` is marked
complete for the first time since the milestone was defined. Commit
`a84348d`.

A new, unrelated, deliberately out-of-scope gap was found and left
open: `malloc(8)` (the size-class slab-pool path, below
`MMAP_THRESHOLD`) returns `NULL` and gem5 subsequently `MALIGN`-faults
— this milestone only ever exercised the `>= MMAP_THRESHOLD` mmap
path by design; not registered as an issue yet, left for a future
decision on whether it warrants its own task.

**Status**: roadmap A/B/D are now all closed. Remaining: roadmap C
(optional, not blocking), roadmap E (kernel bring-up, ADR-0015 charter),
and the newly-found `malloc(8)` size-class gap (undecided scope).

### Post-ML-024 stabilization complete (2026-07-23)

The small-allocation gap was traced to a real crt0 defect rather than a
mallocng algorithm bug: `AT_PAGESZ=4096` was materialized with an out-of-range
signed-12-bit `addi`, silently encoding zero. ML-024a replaced it with
`setzw`, fixed the compensating error in the auxv probe, and added separate
mallocng and lite_malloc E2E coverage. ML-024b independently accepted the
fix; ML-024c strengthened the lite_malloc case with volatile memory
write/read so gem5 can no longer pass on an unbacked non-NULL pointer.

ML-025a established that the current QEMU and gem5 responders already agree
on raw zero-length mmap (`-EINVAL` before cursor/VMA side effects) and locked
that behavior with a direct syscall probe. No duplicate simulator fix or
empty component commit was created.

Two reproducibility defects found during these reviews were repaired:

- IN-006a/b restored the LLVM component series to plain `git am` **49/49**
  from the manifest pin, with final tree identity against LLVM HEAD.
- IN-007a restored the missing QEMU `e7639ea...` history patch; the QEMU
  series now replays **21/21** with final tree identity.

DL-071a then eliminated the systemic cause of the crt0 bug: DADAO MC now
rejects out-of-range constants for every explicit encoded immediate field,
while preserving symbol/fixup expressions. It added positive/negative MC
tests and corrected two illegal `addi 0x5A5A` instances in `tp_probe.test`
to use `setzw`. The LLVM series remains 49/49 after this new patch.

Accepted final gate: project MC **14/14**, E2E **66/66** (including the 23
thin-wrapper llvm-test-suite cases), differential
`AGREE(3-way)=200`, `AGREE(4-way)=200`, `DIVERGE=0`, manifest/issues PASS.
This is not a claim that the full upstream LLVM or llvm-test-suite suites
have run; native LLVM lit still lacks `llvm-config` in the current build
tree. Follow-up DL-071b records the narrower multi-load/store `count=0`
instruction-legality gap. Kernel roadmap E remains paused pending the next
compiler-coverage decision.

**Architect note (2026-07-23)**: the above six items (ML-024b/c, IN-006a/b,
IN-007a, DL-071a) were dispatched and committed directly by an independently
running Codex session, bypassing the project's normal "Claude reviews then
commits" flow. The architect independently re-verified all six after the
fact (fresh full rebuild, behavioral MC-immediate tests, full E2E/
differential/manifest/issues, and a clean full bare-pin `git am` replay of
both the 49-patch LLVM series and the 21-patch QEMU series with tree-hash
comparison against live HEAD) and confirmed everything is correct. The user
has since confirmed this was a one-off exception, not a new default
workflow — see `feedback_codex_direct_commit_special_case_only.md`.

### ML-025a complete (2026-07-23): scanf softfloat gap closed; a real, unconditional scanf blocker isolated

Closes `musl-vfscanf-missing-single-precision-and-divide-softfloat-symbols`
(ML-022a's remaining 6-symbol gap: `__extendsfdf2`/`__truncdfsf2`/
`__floatsisf`/`__mulsf3`/`__divdf3`/`__gedf2` — the single-precision family,
division, and one ordered comparison) in the same self-contained shim,
fuzz-verified against native hardware arithmetic (2.1M cases, 0 mismatches)
with disassembly-confirmed zero self-recursion. `scanf`'s link gap is fully
closed (commit `0b28784a`, patch `0012`).

Along the way, discovered neither QEMU nor gem5 had ever implemented
`SYS_read` — no DADAO program could read real host stdin through any
buffered stdio path. Added a symmetric `case 63` responder to both
backends (commits `79ee086`/`62c1264698`, patches `0022`/`0016`), verified
with a `getchar()`-based dual-backend probe.

`scanf`'s actual runtime correctness remains blocked by a **separate,
pre-existing, already-tracked issue**: `varargs-pointer-args-lost-rb-bank-
save-area`. `scanf`'s output pointer argument is corrupted because LLVM's
varargs save-area prologue only spills the RD register bank, never the RB
bank a pointer argument lives in. Isolated via negative control
(`sscanf` with zero pointer varargs runs clean on both backends, proving
`vfscanf`/`intscan` parsing itself is sound). Unlike `printf`'s `%d`
(pass-by-value, no pointer vararg — how `musl_printf_int.test` dodged this
same gap), `scanf` has no format specifier that avoids a pointer vararg, so
**this blocks every real `scanf`/`vscanf` call unconditionally, not just
some format specifiers** — a materially larger blast radius for this
long-known bug than previously documented. `musl_scanf_int.test` is kept,
`XFAIL`-marked asserting the *intended* fixed behavior, so it flips to an
unexpected pass the day this lands.

E2E 66→68 (67 PASS + 1 honest XFAIL), differential AGREE=200/DIVERGE=0
unchanged, manifest/issues PASS — architect-verified independently
(rebuilt musl/QEMU/gem5 from scratch, reproduced the link success and the
`getchar` E2E pass directly, independently `git am`'d all three patches on
clean pin checkouts, commit `e048f96`).

**Status**: both small musl loose ends from the 2026-07-23 sequence
(`malloc(8)` size-class, scanf softfloat symbols) are now closed. The
`varargs-pointer-args-lost-rb-bank-save-area` bug is the most concretely
scoped, highest-confirmed-impact open item (blocks all `scanf`/`vscanf`,
and historically also blocked `printf("%s", ptr)`-style calls) — a
candidate for the next dispatch alongside the previously-recommended
gcc-c-torture/llvm-test-suite scan, pending user direction.

### DL-072a complete (2026-07-23): varargs-pointer-args-lost-rb-bank-save-area closed per wiki, exactly per ADR-0012 D5's ordering

Per the user's explicit direction to follow ADR-0012 D5's original sequencing
(fix this before the torture-suite sweep, not after) and to follow the wiki
literally rather than the architect's own two candidate designs (an x86-64-
style split-counter `va_list`, or a RISC-V-style "force all variadic args
through one bank"): the architect located the actual authoritative mechanism
in `~/DADAO-wiki/DADAO-21-ABI-应用程序二进制接口.md` §可变参数, which specifies
a third, different design neither candidate matched — **the caller**, not the
callee, writes every named and unnamed argument (in original call-site order,
one per 8-byte slot, dual-written alongside normal register passing) into a
single unified save area; `va_start` just offsets past the named-argument
slot count into that caller-populated area, and `va_arg` advances 8 bytes at
a time with big-endian narrow values right-adjusted in each slot.

Implemented (LLVM commit `3aa546d1d0cd`, patch `0050`): `LowerCall` now emits
the caller-side save-area stores for `IsVarArg` calls; the old callee-side
RD-only register-spill in `LowerFormalArguments` is deleted entirely; a new
`clang/lib/CodeGen/Targets/DADAO.cpp` gives DADAO a custom `EmitVAArg` via
Clang's existing `emitVoidPtrVAArg` helper (slot size 8, `ForceRightAdjust`)
matching the wiki's big-endian rule exactly. Along the way, found and fixed
a real, subtle frame-corruption bug: the side-effect-free `ADJCALLSTACKDOWN/
UP` pseudos were being deleted by generic dead-MI elimination before PEI
could measure the maximum outgoing call frame, undersizing it so save-area
stores clobbered caller locals — fixed by marking them `hasSideEffects=1`
and giving `DADAOFrameLowering` `hasReservedCallFrame() = true`.

Honestly flagged, not silently resolved: the wiki text itself has an
internal contradiction (one passage places the save area at the *highest*
frame address, after locals; another defines `va_start`'s base as the
incoming stack pointer, which cannot be reconciled with the first without
inventing a second base the callee doesn't have). DL-072a kept incoming-SP
as the implementable anchor and recorded the conflict in
`docs/wiki-questions.md` (§5) for the wiki team, rather than picking a
resolution unilaterally and calling the ABI settled.

Architect-verified independently, including scenarios beyond what the task
asked for: a self-constructed mixed int/pointer variadic probe (interleaved
`int, void*, int` variadic tail — the exact shape that exposes bank
confusion), real musl `printf("%s %s\n", "left", "right")` (correct order,
not swapped), real musl `scanf("%d", &x)` end to end, and the 17-fixed-arg /
17-unnamed-variadic-arg overflow edge cases the task's own test suite
added (`varargs_overflow.test`) — all pass on both QEMU and gem5. Full E2E
68→72/72, differential AGREE=200/DIVERGE=0 unchanged, manifest/issues PASS.
Independently replayed the full 50-patch LLVM series from a bare manifest-
pin checkout (`git am` 50/50) and confirmed the final tree hash matches
live `.work/llvm` HEAD exactly. `musl_scanf_int.test`'s `XFAIL` marker was
removed (the task it tracked no longer fails); `varargs-pointer-args-lost-
rb-bank-save-area` closed and archived.

**Status**: roadmap A/B/D and the varargs pointer-loss bug are all closed.
Per ADR-0012 D5's own sequencing, the gcc-c-torture/llvm-test-suite sweep
is now unblocked and is the user-directed next step.

### ML-026a complete (2026-07-24): first full gcc-c-torture sweep (scan only)

All 1708 `execute/` corpus files run through the real clang→ld.lld→QEMU
pipeline (pure recon, no source changes, per ADR-0012 D5): **PASS 1328
(77.8%)**, FAIL_COMPILE 113 (84 match known upstream-denylist causes —
nested functions, VLA-in-struct, gnu89-inline, etc. — 29 real backend
candidates), FAIL_LINK 217 (123 explainable, mostly companion-no-main;
94 real candidates, dominated by one missing-softfloat-symbol cluster —
92 files), FAIL_RUN 49 (includes a real methodology finding:
`-ffreestanding` suppresses C11's implicit `return 0` in `main`,
producing ~12 false failures unrelated to DADAO), TIMEOUT 1
(`pr56866.c`, hangs identically and independently on both QEMU and gem5
— the highest-confidence real bug candidate in the whole sweep).

Deliverables: `tests/scripts/gcc_torture_sweep.py` (reusable scan tool)
and `docs/reviews/ML-026a-gcc-c-torture-sweep-2026-07-24.md` (full
classification + an 11-item prioritized follow-up list). Architect-
verified independently: re-ran the entire sweep from scratch
(identical counts), confirmed the `abort()`→127/`exit(0)`→0 convention,
the `-ffreestanding` finding, the `pr56866.c` dual-backend hang, the
softfloat symbol-miss counts, and the `nestfunc-4.c` RASOF exception
with direct probes — commit `020b24b`.

Top of the follow-up list (see the report for the full ranked list):
P0 `pr56866.c` infinite-loop root cause; P0 finish the softfloat
symbol family (single-precision + the remaining ordered-comparison
symbols `__gtdf2`/`__ltdf2`/`__ledf2`) — highest-leverage single fix,
~90+ files; P1 verify DL-072a's varargs fix covers struct-by-value
variadic args (12 `FAIL_RUN` files cluster here); P1 a relocation/
large-constant-addressing bug (2 concrete repros, likely wider blast
radius); P1 re-evaluate whether `-ffreestanding` is still the right
default now that a real musl libc exists. This scan did not attempt
any fixes; prioritization and dispatch order is pending user direction.

**User direction (2026-07-24)**: fix in priority order; the goal is every
test in the suite either passing or having a documented, reasonable reason
it doesn't (echoing ADR-0012 D5 verbatim). Both P0 items are now closed.

### ML-027a/ML-028a/ML-029a complete (2026-07-24): both P0 items closed, gcc-c-torture 1328→1412/1708 (+84)

**ML-027a** (diagnosis only) found `pr56866.c`'s hang was not a rotate/
narrow-width bug at all: bisection showed every rotate width passes alone,
only mixed-width combinations (which push the stack frame past ~2KB) fail.
QEMU execution tracing (TB-chaining disabled) pinpointed the exact looping
PC; hand-decoding the instruction bytes bit-by-bit against the ISA's field
layout proved the *encoded* immediate was wrong, not a disassembler
artifact. Root cause: `DADAOFrameLowering::emitPrologue/emitEpilogue` and
all of `DADAORegisterInfo::eliminateFrameIndex`'s frame-index pseudo cases
baked `StackSize`/`FrameOff` straight into 12-bit signed `imms12` operands
with **no range check anywhere in the pipeline** — not in frame lowering,
not in the register-info fixup sites, not in `DADAOMCCodeEmitter::
getImm12OpValue` itself. Any function with a stack frame or offset outside
`[-2048,2047]` got silently wrapped mod 4096 at encode time, sometimes
flipping the sign of the stack-pointer adjustment entirely (confirmed: a
real `StackSize=6192` encoded as `+2000` instead of `-6192`). Not specific
to gcc-c-torture — a general correctness gap for any function using more
than ~2KB of stack, with some then-"passing" tests (e.g. a large frame
alone) only passing because the wraparound happened to land somewhere
inert. Registered as `frame-offset-no-imms12-range-check-silent-
wraparound`; diagnosis-only per the ML-020a/021a precedent given the scope.

**ML-028a** closed the 92-file softfloat symbol gap: added the full
single-precision arithmetic/compare/conversion family plus the remaining
double ordered-comparison symbols (`__gtdf2`/`__ltdf2`/`__ledf2`) to the
same self-contained shim (commit `f6ba5f43`, patch `0013`). Found and
added two symbols beyond the original file list (`__unordsf2`,
`__floatdisf`) discovered during verification rather than stopping short.
Deferred `__divsc3` (complex division) as a new, separate open issue —
only 1 of 92 files needs it and its algorithm (Smith's method + full C99
Annex G special-casing) is qualitatively harder than everything else here.
~4.87M fuzz checks against native hardware arithmetic (0 mismatches) plus
5 confirmed negative controls; disassembly confirms exactly 2 `call`
instructions in the whole file (both pre-existing/expected tail-call
patterns), zero self-recursion.

**ML-029a** implemented the actual fix for ML-027a's finding: `LowerCall`-
adjacent frame code now checks `isInt<12>` before encoding any frame
offset, falling back to materializing the value into an ABI-reserved
scratch register (reusing the existing GPRD constant-materialization
pattern from `CONST_WYDE`) and computing the final address via the
existing cross-bank `ADDRB_ORRR` add instruction — no new instructions
needed. A same-day follow-up commit (`032fab81c9bf`) fixed a subtler
bug the first pass missed: the naive `estimateStackSize() > 2047` check
for reserving an emergency register-scavenger spill slot didn't account
for large fixed-object offsets or large GEP offsets on an otherwise-small
frame, so `processFunctionBeforeFrameFinalized` now scans every frame-
index pseudo's actual worst-case total offset. New MIR/IR regression
tests lock the exact `2047`/`2048` boundary behavior, and a new E2E test
(`frame_offset_large.test`) with a genuine negative control confirms the
check isn't vacuous.

Architect-verified independently (not just trusting the implementer's or
Codex's own review): rebuilt the toolchain from scratch, reproduced
`pr56866.c` flipping from `TIMEOUT` to `PASS` directly, reran the full
1708-file gcc-c-torture sweep myself and got the exact same breakdown
(`1412/113/133/50/0`) as both the implementer and the independent
reviewer reported, replayed the full 52-patch LLVM series from a bare
manifest-pin checkout with tree-hash identity confirmed, and independently
verified the musl patch and self-recursion claims. E2E 72→73/73,
differential AGREE=200/DIVERGE=0 unchanged, manifest/issues PASS.

**gcc-c-torture running total: 1328→1412/1708 (82.7%)**, zero regressions
across all three tasks (confirmed via full-corpus before/after file-level
diffing, not just aggregate counts). Both `frame-offset-no-imms12-range-
check-silent-wraparound` and the original 92-file softfloat gap are closed
and archived. Remaining open items from ML-026a's original list: P1
verify DL-072a's varargs fix covers struct-by-value args, P1 the
relocation/large-constant-addressing bug, P1 re-evaluate `-ffreestanding`,
P2 VLA/`__int128`/vector-legalize/`alloca`/`BlockAddress`, plus the new
`musl-softfloat-shim-missing-divsc3` issue from ML-028a.

## ML-030a: relocation-range overflow for large GlobalAddress constant offsets (2026-07-24)

Root cause: `DADAOTargetLowering` never overrode `TargetLowering::
isOffsetFoldingLegal`, so it inherited the base class's permissive
default (`true`). `SelectionDAG::FoldSymbolOffset` used that to fold
`ADD(GlobalAddress, Constant)` into a single `GlobalAddress(offset)` node
with no check on the constant's magnitude. Source patterns like
`a[i - 2000000000L]` (`960321-1.c`/`pr79286.c`) folded the huge constant
straight into the symbol expression, which both `RELA_RIII` and
`ADDI_RBRRII` encode into an 18-bit-range relocation field (`imms18`,
`contracts/isa/spec.md` §2.2, range `[-131072,131071]`) — `ld.lld` then
correctly rejected `a-2000000000` as an out-of-range relocation.

Fix: override the hook to unconditionally return `false`, matching the
established convention across AArch64/RISC-V/MIPS/Sparc/LoongArch (all
read directly to confirm none of them fold either — they keep the ADD
node separate and rely on an as-yet-nonexistent-for-DADAO peephole to
re-fold small/mid-range offsets later "when profitable"). This forces
large offsets through the existing `ISD::Constant → CONST_WYDE →
materializeImm64` register-materialization path established by ML-029a —
no new materialization machinery needed, pure reuse. A same-day
self-review follow-up commit (`fada3562a00e`, comment-only) disclosed a
finding the implementer's own subagent caught: offsets in the
`(2047,131071]` mid-range, which used to fold into the relocation for
free, now cost two extra instructions (`setzw`/`orw` + `add`) since the
hook has no visibility into the post-fold magnitude and must reject
unconditionally — the same tradeoff every peer backend accepts, now
explicitly documented rather than just implied by "small offsets remain
cheap."

Architect-verified independently end-to-end: rebuilt the toolchain from
scratch, reran the 6 directed `CodeGen/DADAO` lit tests (6/6 PASS,
including the new `large-global-offsets.ll`), reran the full E2E suite
(74/74 PASS, including the new `global_offset_large.test` with its
negative control), directly reproduced `960321-1.c`/`pr79286.c` flipping
to `PASS`, reran the full 1708-file gcc-c-torture sweep myself and got
the exact same breakdown (`1414/113/131/50/0`) the implementer reported,
replayed the full 54-patch LLVM series from a bare manifest-pin checkout
with tree-hash identity confirmed, and reran `run_differential.py`/
`manifest_check.py`/`check_issues.py` (AGREE unchanged, all PASS).

**gcc-c-torture running total: 1328→1414/1708 (82.8%)**, zero regressions
(exactly the two targeted files flipped, confirmed via full-corpus sweep
re-run, not just aggregate counts). Remaining open items from ML-026a's
original list: **P1 aggregate/struct-by-value ABI parameter passing
(ML-031a, in progress)**, P1 re-evaluate `-ffreestanding` (user decided
2026-07-24 to remove it and switch to hosted mode — not yet started),
P2 VLA/`__int128`/vector-legalize/`BlockAddress`, plus the open
`musl-softfloat-shim-missing-divsc3` issue from ML-028a.

## ML-031a/ML-032a/ML-033a: aggregate ABI, Embench corpus, dynamic stack alloc (2026-07-24)

Three tasks landed via a parallel Codex session (Codex both implemented
and ran an independent review/re-review cycle on each before committing
directly — outside the normal "architect reviews before commit" flow;
the architect performed full ground-truth re-verification after the
fact for all three, described below).

**ML-031a — aggregate/struct-by-value ABI parameter passing** (LLVM
commits `9079603c93f3`/`ac7c52aa6cd4`/`53e5e16e829a`/`36abcbd6369d`/
`86656a445241`, patches `0055`-`0059`): implements the wiki's full
aggregate ABI — HPA (homogeneous-pointer aggregates) via RB bank, ≤32B
RD-bank splitting, >32B indirect-pointer passing, hidden-sret returns,
and multi-slot variadic aggregate save-area extension. HFA (RF bank)
correctly refused and registered as its own issue rather than faked,
per the task's hard constraint (DADAO has no float register class at
all). A first independent review round found and required fixing 4
blocking issues (padded/nested HPA losing non-contiguous fields, >32B
variadic misclassification, sret pointer not restored to RB16 after an
internal call, and an incomplete-tail-call assertion at -O2); all four
were fixed and the final re-review accepted. A genuine mid-task
regression (`pr28982b.c`, a 256KB by-value struct) was caught and
traced to a *pre-existing*, unrelated defect this work newly exercised:
`MaxStoresPerMemcpy/Memset/Memmove` had been left at `UINT_MAX` since
the earliest DADAO patches (a workaround for a call-selection bug that
no longer exists), so a real `llvm.memcpy` lowering blew up trying to
expand 32768+ inline stores; bounding it to 16 (matching Lanai) fixed
it. Also flagged, not fixed: `pr38151.c`'s `_Complex int` variadic
struct corruption (orthogonal to this task, new issue registered).
Result: 15 of the original 15 target torture files now PASS plus one
bonus file (`20040703-1.c`) the general implementation happened to
cover — architect-reproduced exactly.

**ML-032a — Embench-IoT functional corpus** (new component, pinned at
`09c2ed8c3b7008c95d08b038de4a3f6dc103ed70`, one upstream patch for
MD5's little-endian word decode): brings the project's own fresh,
version-locked 19-benchmark functional sweep (`tests/scripts/
embench_sweep.py`), run at both -O0 and -O2 through the real
clang→lld→musl→QEMU/gem5 pipeline — explicitly a correctness corpus,
not a performance benchmark. An independent review round found and
required fixing 4 issues in the sweep tool itself (a `--resume` that
didn't check whether the query identity had actually changed before
reusing stale results being the most serious), all closed with a
fingerprint-based cache-invalidation scheme. Final, fully independent
result: O0 19/19 PASS, O2 18/19 PASS with a single known, undisguised
failure (`qrduino` at -O2, diagnosed to a specific buffer-content
mismatch, kept red rather than "fixed" by disabling optimization on
the file). Architect independently reran the entire 38-build sweep
from scratch and reproduced this exact O0/O2 split, including the
qrduino failure on both backends.

**ML-033a — dynamic stack allocation (VLA)** (LLVM commit
`dd80ef109bbb`, patch `0060`): implements `DYNAMIC_STACKALLOC`/
`STACKSAVE`/`STACKRESTORE` lowering plus a new `rb2`-based frame-pointer
convention for functions with a variable-length stack allocation or a
`__builtin_frame_address` use, following `contracts/abi/spec.md` §4
exactly. An independent review round caught a real High-severity bug
the work's own tests hadn't reached: with a >2047-byte outgoing
call-frame *and* a live VLA at the same time, the physical `rb1`
(stack pointer) was fed into a generic RD-bank `ADD` as if it were an
ordinary integer, losing its RB-bank tag and silently reading the
wrong register — verified with a 300-argument-call probe that faulted
on real hardware paths (QEMU exit 1 / gem5 page-table fault). Fixed by
routing both ordinary large stack-argument addresses and the vararg
save-area through a shared `getOutgoingStackAddress` helper that
explicitly emits a bank-correct `DADAOISD::ADDRB` for out-of-imms12-range
offsets. Closes the 9-file VLA gap from ML-026a's original P2 list.

**Architect independent verification (all three, after the fact)**:
rebuilt the toolchain from the final HEAD; ran the 11 directed
`CodeGen/DADAO` + Clang DADAO lit tests (11/11 PASS); ran the full E2E
suite (77/77 PASS, up from 74/74, including the 3 new aggregate/VLA
tests); reran the full 1708-file gcc-c-torture sweep from scratch and
got the exact reported `PASS=1438 FAIL_COMPILE=104 FAIL_LINK=131
FAIL_RUN=35` (1414→1438, +24, matching +15 from ML-031a and +9 from
ML-033a exactly); reran `run_differential.py` (AGREE 3-way=200,
4-way=200, DIVERGE=0, unchanged) and `manifest_check.py`/
`check_issues.py` (both PASS); replayed the full 60-patch LLVM series
from a bare manifest-pin checkout in a clean worktree and confirmed the
tree hash matches `.work/llvm` HEAD exactly; independently re-ran the
entire Embench sweep from scratch (not just read the report) and
reproduced the exact same 19/19 O0 / 18/19 O2 split with the same
`qrduino` failure on both backends.

**gcc-c-torture running total: 1328→1438/1708 (84.2%)**. Remaining open
items: P1 re-evaluate `-ffreestanding` (user decided 2026-07-24 to
remove it, switch to hosted mode — not yet started), P2 `__int128`/
vector-legalize/`BlockAddress`, `qrduino`-O2 and the `_Complex` variadic
corruption as new, explicitly-documented-not-fixed defects, plus the
still-open `musl-softfloat-shim-missing-divsc3` (`__divsc3`) and
`dadao-hfa-argument-not-implemented` issues.

## ML-034a: remove `-ffreestanding` from test/scan compilation (2026-07-24)

The project's gcc-c-torture sweep and E2E lit tests compiled user
programs with `-ffreestanding`, a holdover from before the project had a
real libc. `-ffreestanding` disables C11's guarantee that a `main()`
falling off the end implicitly returns 0 — since the project now links a
real, statically-linked musl (`_start`/`__libc_start_main` since
ML-007a..012a), that guarantee is both available and correct, and its
absence was misclassifying logically-correct torture files as
`FAIL_RUN` (the exact false-failure source ML-026a's original scan
flagged). Removed from `tests/scripts/{gcc_torture_sweep,embench_sweep}.py`
and the 10 E2E lit tests that used it; musl's own build
(`-ffreestanding` in its own `Makefile`) is untouched — that's normal
upstream musl practice, unrelated to how test programs get compiled.

Result: gcc-c-torture PASS 1438→1461 (25 files flip to PASS: 6
FAIL_LINK→PASS, 19 FAIL_RUN→PASS — more than ML-026a's original ~12-15
estimate, confirmed exact by file-level diff, not estimated). Also
surfaced 2 genuine, non-fake regressions (`20050604-1.c` — MMX/SSE-style
vector union arithmetic; `pr63302.c` — `__int128` bit-masking), both
root-caused to the same mechanism via a standalone IR/asm diff: hosted
mode's dead `%retval` slot shifts `main()`'s stack frame from 0 bytes to
an 8-byte (non-16-byte-multiple) adjustment, and the callee functions
holding the actual 128-bit-wide locals compute their frame offsets
assuming a 16-byte-aligned incoming stack pointer — an assumption that
was only ever true by luck across the previously-exercised call chains,
not an enforced invariant. `DADAOFrameLowering.h` declares `Align(8)`,
which matches the wiki's ABI type table exactly (`DADAO-21-ABI`'s
sizeof/Alignment table tops out at 8-byte types — `long`/pointer/
`double` — with aggregates "at least 8-byte aligned"; 128-bit types
have no defined DADAO ABI alignment contract at all). Presented to the
user as a genuine ABI-scope decision (same shape as the HFA exclusion):
extend the ABI to define 128-bit alignment and add dynamic stack
realignment support to the backend, or register it as a permanent,
documented exclusion. **User chose exclusion** — registered in
`docs/issues.yaml` (`dadao-frame-lowering-8byte-align-insufficient-for-
16byte-locals`, reworded to state `DADAOFrameLowering`'s `Align(8)` is
correct per spec, not a bug) alongside the existing HFA exclusion; these
2 files are expected to remain permanently non-PASS with this documented
reason.

Architect independently verified: confirmed the exact file list (12
files touched, `-ffreestanding` fully gone from test-compilation scope,
musl's own Makefile untouched); reran the full 1708-file gcc-c-torture
sweep and got the exact reported `1461/104/125/18`; computed the
file-level diff programmatically against the pre-task baseline JSON and
confirmed exactly 25 improvements + 2 regressions + 0 other changes,
matching the subagent's report line for line; independently reproduced
the root cause with a fresh `-emit-llvm`/`llc` diff for `pr63302.c`
(confirmed the dead `%retval` slot, the 8-byte `main()` frame adjustment,
and that `foo()`'s own prologue is byte-for-byte identical between hosted
and freestanding); reran the full E2E suite (77/77) and
`run_differential.py`/`manifest_check.py`/`check_issues.py` (all
unchanged/PASS).

**gcc-c-torture running total: 1328→1461/1708 (85.6%)**.

## ML-035a: refresh gcc-c-torture gap classification (2026-07-24)

A pure scan/classification task (no source changes) to re-derive the
current FAIL_COMPILE(104)/FAIL_LINK(125)/FAIL_RUN(18) breakdown, since
ML-026a's original categorization was done at PASS=1328 and is now
stale after seven fix rounds moved PASS to 1461. Result: FAIL_COMPILE's
84 known/explainable + 20 real-candidate split is byte-for-byte
unchanged from ML-026a (nothing in `ML-027a`-`ML-034a` touched that
path); FAIL_LINK is now 100% accounted for by known causes (no new
leads — `ML-028a`/`ML-030a` already mined that vein dry).

The significant find is in FAIL_RUN: a correction to ML-026a's original
report. `931102-1.c`/`931102-2.c` had been lumped into the 12-file
"struct-by-value vararg" cluster, but neither file actually uses
`va_arg` at all (direct source inspection) — they're K&R-style
union/bitfield "count trailing zero bit" tests. The other 10 files in
that original cluster are confirmed genuinely PASS now (via `ML-031a`'s
aggregate ABI + `ML-034a`'s hosted-mode fixes), including `pr38151.c`.

`931102-1.c`/`931102-2.c` are a previously-unrecorded, genuine
correctness bug: at **-O0 only**, a single-bit AND test written in
*negative* polarity (`if ((x & 1) == 0)` / `if (!(x & 1))`) silently
drops the `and rd,rd,1` masking instruction and branches on the raw,
unmasked byte instead — for x=2 (bit 0 clear, byte value nonzero) this
produces the wrong branch outcome with no compile/link/fault error at
all, just a silently wrong answer. `960608-1.c` (a bitfield read) is
suspected to be the same root-cause family but wasn't isolated to a
single minimal trigger. Architect independently reproduced with a
from-scratch 3-line repro run end-to-end through QEMU: an -O0 build
exits 0 (wrong, expected 1), an -O2 build of the identical source exits
1 (correct) — confirming both the bug and its -O0-only scope.

Registered as `dadao-o0-negative-polarity-bitand-mask-dropped` and
immediately escalated to P0 ahead of the rest of ML-035a's priority
list, despite only hitting 2-3/1708 torture files: this is a *silent*
wrong-answer defect for extremely common real C idioms (parity checks,
find-lowest-set-bit loops, single-bit flag tests), not a torture-corpus
edge case — the low hit count in this specific corpus is likely luck,
not evidence the real-world risk is small.

Updated priority list (P1 downward): `__divsc3` (1 file, already
tracked), vector-legalizer + `__int128` calling-convention failures
(17 files combined, possibly one shared "128-bit return value CC
allocation" crash site), `BlockAddress`/computed-goto (3 files), plus
two low-priority singletons not worth their own task.

## ML-036a: fix P0 -O0 negative-polarity single-bit AND mask drop (2026-07-24)

Root cause: `DADAOTargetLowering` never called `setBooleanContents()`,
defaulting to `UndefinedBooleanContent` — wrong for this target, whose
real invariant is `ZeroOrOneBooleanContent` (`lowerSETCC` always
materializes a genuine 0-or-1 value across the full register width, and
the actual `BRNZ`/`BRZ` branch instructions test the whole register for
non-zero-ness, not just bit 0 — they never mask themselves). Under the
wrong default, `TargetLowering::promoteTargetBoolean` widens a narrower
i1 boolean for `BRCOND` consumption via `ANY_EXTEND` instead of
`ZERO_EXTEND`. At `-O0` (clang forces `optnone` → `CodeGenOptLevel::
None` for the whole SelectionDAG pipeline regardless of `llc`'s own `-O`
flag — verified directly: the same `optnone`-tagged IR produces
identical, identically-wrong assembly under both `llc -O0` and
`llc -O2`), `DAGCombiner`'s generic combines collapse a negative-
polarity single-bit AND-and-compare-to-zero pattern (`(x & 1) == 0`,
true branch is the `else` arm) first via the standard `xor(setcc,true)
-> setcc-with-negated-cc` fold, then further into a bare
`truncate(loadedByte, i1)` (valid, since truncating to i1 is exactly bit
0). Re-widening that i1 for `BRCOND` under `ANY_EXTEND` then
algebraically cancels straight through the truncate — legal precisely
because `ANY_EXTEND` permits garbage upper bits — producing an unmasked
load that `BRNZ` tests against the *whole* byte instead of just bit 0.
Positive-polarity forms (`if (x & 1)`) never reach this DAGCombine shape
(the `and`+`setcc` survive intact to instruction selection) and were
never affected.

Fix: `llvm/lib/Target/DADAO/DADAOISelLowering.cpp` — one line,
`setBooleanContents(ZeroOrOneBooleanContent)`, plus a 24-line comment
explaining the mechanism. Forces the same widening through
`ZERO_EXTEND`, under which `ZERO_EXTEND(TRUNCATE(X))` cannot cancel for
free — it must materialize a real mask — restoring the dropped
`and rd,rd,<mask>`.

Verified with a 1152-vector (4 widths × 4 mask values × 4 comparison
forms × 2 polarities × 9 inputs) host-native-vs-QEMU ground-truth
differential, not hand-computed expected values (the task's own
self-review caught and discarded two flawed test-generation scripts
along the way — an exit-code-overflow bug and a hand-derived-expected-
value sign error — before settling on this method): 45/1152 vectors
diverge before the fix, all from the 9/128 function shapes with
`mask=1` (matching the diagnosed DAGCombine trigger exactly — the
combine only fires for this shape) and covering int/char/short but
never `long`; 0/1152 after. `960608-1.c` (a bitfield read) was
confirmed — not just inferred from "flipped to PASS" — to be the same
root cause via direct before/after `.s` comparison, finding the identical
missing-`and`-after-`shru` signature at the same instruction position.

Architect independently verified: rebuilt the toolchain; reproduced the
original 3-line minimal repro directly (now exits 1, correct, was 0);
ran the 10 directed CodeGen lit tests (10/10, including the new
`negative-polarity-bitand-mask.ll`) and the full E2E suite (78/78,
including the new project-level test); reran the full 1708-file
gcc-c-torture sweep twice for repeatability and got the exact reported
`1464/104/125/15` both times, plus confirmed the 3 target files
individually via `--filter`; reran `run_differential.py` (unchanged, as
expected for a codegen-only fix) and `manifest_check.py`/
`check_issues.py` (both PASS, issue correctly moved from `issues.yaml`
to `issues-archive.yaml`); replayed the full 61-patch LLVM series from a
bare manifest-pin checkout and confirmed the tree hash matches
`.work/llvm` HEAD exactly.

**gcc-c-torture running total: 1328→1464/1708 (85.7%)**. This closes out
the single highest-priority item on ML-035a's list; remaining: `__divsc3`
(1 file), the vector-legalizer/`__int128` calling-convention cluster (17
files), `BlockAddress` (3 files), and two low-priority singletons.

## ML-037a: implement `__divsc3` (2026-07-24) — see `code-agent/tasks/ML-037a-implement-divsc3-softfloat-shim.md` 完成区

Closes the last known FAIL_LINK gap (`complex-5.c`, single-precision
complex division per C99 Annex G). gcc-c-torture: 1464→1465/1708
(85.8%), zero regressions. Full E2E/differential/manifest/issues pass;
musl 14-patch series replays clean with matching tree hash.

## ML-038a: fix `__int128` return-value CallingConv crash (2026-07-24) — see `code-agent/tasks/ML-038a-fix-int128-calling-convention.md` 完成区

Splits `__int128` returns across `rd31`/`rd30`. 4/6 target files PASS;
the other 2 hit a newly-registered, separate gap (missing
`__fixsfti`/`__udivti3` libcalls,
`musl-softfloat-shim-missing-int128-arith-libcalls`). 2 vector-return
files flip to PASS as a side effect (vector legalization itself
untouched). gcc-c-torture: 1465→1471/1708 (86.1%), zero regressions.
`check_codegen_abi.py` caught a real ABI-doc/schema drift, fixed in the
same commit. Full E2E (79/79), CodeGen+MC lit (13/13) pass; 62-patch
LLVM series replays clean with matching tree hash.
