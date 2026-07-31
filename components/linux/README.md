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
