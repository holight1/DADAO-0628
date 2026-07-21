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

## Review correction / audit sidecars（2026-07-21）

独立 review 初始指出 task 目录缺少原始 rc 与命令 sidecar。已补齐并复核：
`commands.txt`、`compile.rc`、`link.rc`、`objcopy.rc`、`qemu.rc`、
`gem5.rc`、两端 `stdout/stderr`、`qemu.timeout`、`gem5.timeout`、
`result.txt`、`validation.rc`、`artifacts.sha256` 与 `runtime-inputs.sha256`。
这些 sidecar 记录的结果为 compile/link/objcopy=`0`、QEMU=`42`、gem5=`42`、
两端 no-timeout，gem5 guest 为 `SIM_END: trap-exit code=42`；因此修正后的
结论可由 task-owned 原始记录独立复核。

## Independent review（2026-07-21）

**Verdict：Needs-fix。** 未运行新实验；现有证据支持 source/control-flow 与运行轨迹
已越过 startup，但不足以独立确认任务声称的全部精确 rc。

- `.work/ML-014af-dual-large-post-fix-runtime/malloc_dual_large_free.c` 与
  `.work/ML-014z-dual-large-allocation-free-probe/malloc_dual_large_free.c`
  `cmp=0`（同一 SHA-256），且保留 ML-014z 的 `131052`/`262144`、对齐/非重叠、
  page sentinel 首中尾写读、`free(b); free(a);` 和 phase-marker 合同。
- `gem5.exec.trace` 命中 `main@0x80000110`、两次 malloc（`0x8000011c`、
  `0x80000180`）、两次 reverse-free（`0x8000051c`、`0x80000570`），两次
  `munmap` 路径，并到达最终 `_Exit` trap；`qemu.trace` 命中 main、free、munmap
  代码块。两份 trace 均未出现旧错误目标 `0x7ffffc80`/`0x7ffffcb8`。
- 但 af `.work` 目录没有 `compile.rc`、`link.rc`、`objcopy.rc`、QEMU/gem5
  rc、stdout/stderr、timeout、commands 或 result/validation sidecar；因此
  `compile/link/objcopy=0` 与 QEMU/gem5 `rc=42` 只能由 task MD 声称，不能由现有
  产物独立复核。源代码的最终 `return 42` 加 gem5 的成功路径支持“若 guest rc=42
  已被保存，则 full contract 的控制流闭合”，但不能替代两端精确 guest/host rc
  记录，尤其不能独立确认 QEMU 的完整结果。

**Correction：** 保留同一 exact ML-014z source/contract 和现有 ELF/traces，补存
compile/link/objcopy rc、两端原始 rc 与 stdout/stderr/timeout、commands 及统一
result/validation sidecars；补齐后再将 verdict 改为 Accepted。

## Independent review (2026-07-21, follow-up)

**Verdict：Needs-fix。** 未运行实验。af source 与 ML-014z source `cmp=0`（SHA-256
`ed3551d57c4013779bebf147318b54a7f33ce578e9ec2a04ec71b880077d35b5`），保留
`131052`/`262144` 双块、sentinel、对齐/非重叠、逆序 free 与 phase-marker contract；
QEMU/gem5 均命中 `main`，且两份 trace 均无 `0x7ffffc80`/`0x7ffffcb8` wrong-target。
但现有 `.work/ML-014af-dual-large-post-fix-runtime/` 没有两端原始 process rc、
stdout/stderr 或 result sidecar；trace 到达最终 trap 加 source 的 `return 42`，仍不能
独立验证 QEMU/gem5 观测值确为 `42`。补齐原始 rc 与命令/结果记录后再 Accepted。

## Independent review (2026-07-21, final follow-up)

**Verdict：Accepted。** 未运行新实验；仅复核 task-owned sidecars 与现有产物。`compile.rc`、
`link.rc`、`objcopy.rc`、`validation.rc` 均为 `0`；`qemu.rc`/`gem5.rc` 均为 `42`，
两端均 `no-timeout`，且保存了 stdout/stderr、commands、result 与 runtime/artifact
hashes；两组 `sha256sum -c` 均通过，gem5 stdout 明确记录 `SIM_END: trap-exit code=42`。

源代码保留 exact dual-large contract：`131052`/`262144`、16-byte alignment、
overflow/non-overlap、page sentinel 首中尾写读、`free(b); free(a);`、phase-marker
检查及 `return 42`。两端 trace 均命中 `main`；gem5 明确命中两次 malloc、两次逆序
free、两次 munmap 与最终 `_Exit` trap，QEMU trace 对应计数为 malloc/free/munmap
各 2 次、main/_Exit 各 1 次；两份 trace 均无 `0x7ffffc80`/`0x7ffffcb8` wrong-target。
`result.txt` 报告完整 dual-large contract PASS，证据闭合。
