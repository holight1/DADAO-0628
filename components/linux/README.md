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
