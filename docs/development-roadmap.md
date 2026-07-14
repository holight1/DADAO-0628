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
