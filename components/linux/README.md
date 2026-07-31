# Linux Component

Enabled by KL-146a after the K2 closure gate.

- Upstream baseline: Linux 5.4, commit
  `219d54332a09e8d8741c1e1982f5eae56099de85`.
- Source worktree: `.work/source/linux`.
- Patch queue: `components/linux/patches/series`.
- Porting rule: `arch/dadao` is written fresh against the current frozen DADAO
  contracts. Historical ports are retrospective evidence only and are not
  imported as source or patches.
- K3 first target: deterministic single-hart QEMU boot through
  `do_initcalls`/`kernel_init`.
- End-to-end target requested for this task chain: initramfs user mode,
  `hello world`, and a console `login` prompt.

The empty series at KL-146a is intentional: this task pins and fetches the
clean upstream baseline before the first architecture patch is created.

KL-153a (patches 0021-0031) removes every Linux-side
`CONFIG_DADAO_K3_O0_LINK_COMPAT` bool-carrier workaround for the DADAO LLVM
`-O0` i1 stack-slot defect fixed in the same task (10 commits the task
enumerated, plus 8 further pre-existing carriers found by a tree-wide sweep
that predate that list). `CONFIG_DADAO_K3_O0_LINK_COMPAT` itself,
`arch/dadao/mm/o0-link-compat.c`, and the legitimate disabled-feature use in
`include/linux/huge_mm.h` are untouched. See
`code-agent/tasks/KL-153a-llvm-o0-bool-stack-slot-root-fix.md`.

KL-154a (patch 0032) adds fourteen more `CONFIG_DADAO_M1_PROGRESS` words
diagnosing exactly where boot is stuck beyond `mm_init_done`: the guest
spins forever in `calibrate_delay_converge()`'s `while (ticks == jiffies)`
busy-wait (`init/calibrate.c`), because `arch/dadao`'s `time_init()`/
`trap_init()`/`init_IRQ()` install no working clockevent or exception
delivery to ever advance `jiffies`. See
`code-agent/tasks/KL-154a-k3-post-mm-init-boot-progress-diagnosis.md`.

KL-155a (patch 0033) fills that gap: `arch/dadao/kernel/entry.S` installs
real CFX exception vectors for both `cfx_smon` (cfxcode=2) and `cfx_timer`
(cfxcode=18) -- async TIMER delivery targets `cfx_timer`'s own vector, not
`cfx_smon`'s -- and `time.c` drives a real `cfx_timer`-backed
`CLOCK_EVT_FEAT_ONESHOT` clockevent plus a `cfx_hart_cycle_lo` clocksource.
`jiffies` now genuinely advances and boot passes
`calibrate_delay_converge()`, reaching `rest_init_enter`/`idle_enter` with
`rest_init_pid=-ENOSYS` exactly as KL-154a's diagnosis predicted (the next
wall, `copy_thread()`/`__switch_to()`, is explicitly out of scope, KL-156a+).
Requires booting QEMU with `-icount shift=0` for the timer interrupt to
reliably reach guest code running in a tight loop (a real QEMU/TCG
invocation requirement, not a source workaround -- see `time.c` and the
task record). See
`code-agent/tasks/KL-155a-k3-real-trap-vector-and-timer-clockevent.md`.
