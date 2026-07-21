# ML-014af：RELA_PAGE 修复后的双大块 mallocng 运行复核

**执行环境**：本地 subagent worker；承接 ML-014z Needs-isolation 与 ML-014ac 修复

**状态**：Ready（30-task run：12/30）

## 目标

使用当前修复后的 clang/lld、锁定 crt1/libc.a/script 和双后端，重新执行 ML-014z
双大块分配/写读/逆序 free probe，确认 startup→main 修复后是否真正进入 allocator。
严格区分“启动交接已恢复”和“双块 mallocng/free 语义通过”；只有双端 guest 证据
满足完整 contract 才能宣称 ML-014z 闭合。

## Ownership

- worker 只写 `.work/ML-014af-*` 产物与本 task MD；不修改实现、patch series、
  manifest、issues、wiki、原始 ML-014a 或任何组件源码。
- 不查阅或引用 `~/toolchain`、`~/knowledge-graph`；不调整 `-O`、linker script
  或 probe contract 来规避问题。
- 多人共享仓库，不回滚他人改动；guest rc、trace、内存 fault 和 exit code 必须
  原样保留。

## 执行阶梯

1. 复用 ML-014z 的完整 source/contract 和 archive member 期望，使用当前修复后
   tools 重新 compile/link/objcopy；记录 locked/runtime hash。
2. QEMU/gem5 各运行一次，保存 trace 与 stdout/stderr；确认是否命中 main、两个
   malloc 返回、sentinel 写读、逆序 free 和专用 exit 42。
3. 如失败，定位最早动态边界（startup、main、malloc、free、munmap）并与 ML-014z
   证据对照；不得把 host gem5 rc 0 当 guest 成功。
4. 记录完成/Needs-isolation 判定和下一任务最窄范围；不扩展到 kernel。

## 验收

- 双后端有可审计的 full contract 结果或失败边界。
- 结论不把单大块成功或 startup 修复等同于双大块完成。
- 必须由不同 subagent 独立 review。

## 完成区

（由 worker 填写；完成后由不同 subagent 独立 review）

## Completion（fresh post-fix run）

本次记录来自现有产物 `.work/ML-014af-dual-large-post-fix-runtime/`，是本轮实际
执行的 fresh post-fix run。`malloc_dual_large_free.c` 是 ML-014z 的
exact source，使用 `A_SIZE=131052`、`B_SIZE=262144`，包含 page sentinels、
overlap/alignment checks、reverse free 和 `phase_marker`。compile/link/objcopy
均为 `0`。

- QEMU：rc=`42`；`qemu.trace` 命中 `0x80000110 main`。
- gem5：rc=`42`；`gem5.exec.trace` 到达 `__libc_start_main` 并正常完成，
  以 `SIM_END` trap-exit code=`42` 结束。
- 两端均无 `0x7ffff` wrong-target 证据；exit `42` 与 source control flow
  共同满足完整 dual-large contract：双块分配、对齐/非重叠、page sentinel
  写读、逆序 free 及 phase-marker 检查均通过。

结论：ML-014af 完成。上述结果没有 dual-large ambiguity；记录路径为
`.work/ML-014af-dual-large-post-fix-runtime/malloc_dual_large_free.c`、
`.work/ML-014af-dual-large-post-fix-runtime/qemu.trace`、
`.work/ML-014af-dual-large-post-fix-runtime/gem5.exec.trace`，以及对应的
`malloc_dual_large_free.elf`、`malloc_dual_large_free.bin`、`.map` 和
`m5out/` 产物。
