# KL-152a：K3 `mm_init` 完成与 allocator 初始化边界

**状态**：待执行
**日期**：2026-07-29
**前置**：KL-151a
**后续**：KL-153a（由本任务 evidence 冻结的首个 post-`mm_init` 阻塞）

## 背景

KL-151a 已用六个 guest-authored QMP words 证明 Linux
`mem_init()` 完成，并冻结首个下一阻塞：

- `EXCP_MALIGN`，PC `0x8027985c`；
- `mm/page_alloc.c::prepare_alloc_pages+0x1c8`；
- `rb1+71` 单字节 slot 由 `stb` 写入、由八字节 `ldo` 读取；
- positive 与 `-serial none` 两个场景身份一致。

KL-151a 最终根提交为 `81b21dd`，frozen summary SHA256 为
`e6682d902e067e69ce0384d468ec3067e831999d2c573633be1ca6d2a093cd08`。

Linux 5.4 的 `init/main.c::mm_init()` 在 `mem_init()` 之后继续初始化
SLUB、kmemleak、pgtable、debug objects、vmalloc、ioremap 和架构空实现。
本任务只证明这个真实函数边界完成，不把它扩大为 scheduler、interrupt、
initcall、login 或用户态能力。

## 目标

1. 在既有 `CONFIG_DADAO_K3_O0_LINK_COMPAT` 边界内关闭
   `prepare_alloc_pages` 的实证 bool stack-slot MALIGN；
2. 若到 `mm_init()` 返回前继续遇到同类缺陷，只能按“一个实证位置、一个窄
   修复”推进，并为每个新增 patch 保存修复前 Linux HEAD、Image、QMP raw、
   trace、symbol、disassembly、PC/slot 与 size/SHA256；
3. 在 `init/main.c::mm_init()` 的最后一个真实初始化动作
   `pti_init()` 返回后写入：
   - 地址 `0x87fd0030`；
   - 值 `0x4b4c3135324d4d44`（ASCII `KL152MMD`）；
4. 用 QMP 证明旧六个 words 无回归，新 word 只在完整 `mm_init()` 返回边界
   出现；
5. 达到 marker 后继续观察并冻结首个真实 post-`mm_init` 阻塞，作为
   KL-153a 输入。

## 实施约束

- Linux component 使用普通 commit；每个实证修复独立导出 patch 并追加
  `components/linux/patches/series`。预计不修改 QEMU。
- generic Linux carrier 修改必须受 `CONFIG_DADAO_K3_O0_LINK_COMPAT`
  控制；普通配置保留原 `bool`、结构布局、UAPI、模块 ABI 和语义。
- carrier 返回必须规范化为 `0/1`；跨翻译单元声明/定义必须同步。
- 禁止预防性批量改写 generic bool；禁止用 head.S、ROM、QEMU 或 runner
  预填 progress。
- 继续固定 `KCFLAGS=-O0`；不处理 KL-148b 的默认优化问题。
- runner/evidence 必须采用 KL-151a 已收紧的干净单次运行、RUNNING/FAILED、
  原子 summary 和无循环 artifact manifest 语义。
- 临时 historical worktree 清理必须检查命令返回码、路径消失和 Git 注册表。
- 不显式参考 `~/toolchain` 或 `~/knowledge-graph`。
- 不修改、不提交顶层既有未跟踪 `gcc-torture-results.json`。

## 验收

新增 `tests/scripts/run_kl152a_mm_init_completion.py`，必须：

1. 精确验证根提交 `81b21dd`、KL-151a summary SHA256、`PASS 3/3`、旧六词
   oracle、negative、Linux/QEMU identity、runner 与 85-item manifest；
2. 检查 Linux/QEMU component clean，精确绑定 Linux 全 patch queue；
   QEMU 固定 KL-150a HEAD/binary/0037/0038 身份，并如实保留 0001..0036
   历史 replay 债务；
3. fresh `mrproper` 构建 `Image`，验证 ELF64 big-endian、`EM_DADAO`、
   entry、undefined symbol、forbidden diagnostics，以及扩展为 56 bytes
   后的 Image/scratch/stack non-overlap；
4. QEMU `-S` 启动，`cont` 前读取 56-byte oracle 全零；正例逐级拒绝非法或
   跳级状态，最终并延迟复读精确得到：
   `(KL149AHE, 0, KL150SAE, KL150SAD, KL150MIN, KL151MID, KL152MMD)`；
5. source contract 隔离 `mm_init()`，验证
   `mem_init -> kmem_cache_init -> kmemleak_init -> pgtable_init ->
   debug_objects_mem_init -> vmalloc_init -> ioremap_huge_init ->
   init_espfix_bsp -> pti_init -> KL152MMD`，并要求 marker 是函数最后一条
   真实语句；
6. 扫描 `head.S` 与两份 HBI ROM，拒绝新 progress value 被预填；
7. console 仅作为 secondary；正例保留既有四 anchors，并增加真实 SLUB
   初始化锚点。`-serial none` 使用同一 Image，QMP 完整而 console
   verdict=false；
8. wrong-mode 必须保持
   `(0, KL149BAD, 0, 0, 0, 0, 0)` 并 shutdown；
9. 每个中间 carrier 修复都必须由 runner 在对应 pre-fix detached worktree
   重建并复现，写入 `carrier_fix_evidence`；最终 blocker 需在 positive 与
   `-serial none` 两场景一致；
10. summary 绑定 runner 和最终 Image/vmlinux/QEMU，artifact manifest
    覆盖本轮 evidence 目录全部非循环产物并逐项校验；失败不得保留旧 PASS；
11. 最终明确 `PASS 3/3, FAIL=0, SKIP=0`，两个 component clean，临时
    worktree/output 全部清除。

## 非声明

本任务只声明 `mm_init()` 的真实完成及首个 post-`mm_init` 边界。它不声明
`sched_init()` 完成、上下文切换、Linux trap/syscall、timer/IRQ、用户页表、
initramfs `/init`、TTY/login 或用户态 hello。

## 实施记录

worker 完成后填写。

## Review

worker 返回后由单独 reviewer subagent 只读审查，再由主控二次复核。
