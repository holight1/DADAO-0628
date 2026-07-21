# ML-015h：QEMU-only llvm-test-suite fixture 的 Gem5 可行性探针

**日期**：2026-07-21

**状态**：Accepted-with-findings（30-task run：25/30）

## 背景

ML-015g 发现 `arrayresolution.test`、`bitops.test`、`minint.test` 只有 QEMU
退出码断言，不能计入 23 个双后端 fixture。先做独立、无语义修改的 Gem5 探针，
判断是否只是遗漏 RUN 行，还是存在需要单独处理的 ABI/loader/运行时边界。

## 目标与 ownership

worker 只负责运行现有编译链和 Gem5 probe、task 完成区及
`docs/reviews/ML-015h-qemu-only-gem5-probe-20260721.md`：

1. 使用每个 fixture 的现有 clang/llvm-mc/objcopy 命令生成 ELF，记录 rc。
2. 用当前 Gem5 SE 入口运行三个 ELF，记录实际退出码/timeout/output；同时保留
   QEMU 结果作为对照。
3. 结论只回答“能否安全补 Gem5 RUN”：不修改 `.test`，不把一次手工通过直接
   宣称为双后端测试已落地；若需要额外断言或存在不确定性，列为后续任务。

## 约束

- 不修改 LLVM/QEMU/Gem5/vector/kernel/spec、`docs/issues.yaml` 或 wiki。
- 不访问或引用 `~/toolchain`、`~/knowledge-graph`，不修改 ML-014a。
- 不用 `|| true` 遮蔽退出码；所有 rc/timeout 原样记录。

## 完成区

已完成 3 个 QEMU-only fixture 的独立 Gem5 feasibility probe（2026-07-21）。

- 对 `arrayresolution`、`bitops`、`minint`，现有 `llvm-mc`、`clang`、
  `llvm-objcopy` 构建步骤均为 `rc=0`。
- QEMU 对照结果分别为 `0`、`249`、`1`，与各 `.test` 的预期一致。
- 使用 `timeout 10s /home/holight/DADAO-gem5/build/DADAO/gem5.opt
  /home/holight/DADAO-gem5/tests/dadao/dadao_se.py <elf>`：三个 Gem5 进程
  均在 timeout 内退出，rc 分别为 `0`、`249`、`1`；输出均有 `SIM_END: halt
  code=N`，仅出现既有 Gem5 warning。
- 结论：这 3 个 fixture 当前具备补 Gem5 RUN 行的实证基础；但本任务不修改
  `.test`，下一任务应单独添加 3 条 Gem5 断言并做 lit/完整 E2E 回归。

报告：`docs/reviews/ML-015h-qemu-only-gem5-probe-20260721.md`。
本任务没有修改实现、测试语义、issues/wiki 或 ML-014a。

### 独立 review

`docs/reviews/ML-015h-independent-review-20260721.md`，结论
**Accepted-with-findings**；reviewer 核对三个 fixture 的 expected/QEMU/Gem5
结果、`SIM_END` marker 和 timeout 边界，确认没有使用 `|| true`，并确认本任务
没有把未修改的 `.test` 宣称为已完成双后端回归。
