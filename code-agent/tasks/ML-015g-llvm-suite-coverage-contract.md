# ML-015g：llvm-test-suite 切片覆盖契约审计

**日期**：2026-07-21

**状态**：Accepted-with-findings（30-task run：24/30）

## 背景

ML-015f 已证明仓库内 `tests/lit/E2E/llvm-test-suite/` 的 23 个切片可独立
运行，但这些文件是从 upstream SingleSource 改写/裁剪后纳入的 fixture，不能
仅凭目录名推断覆盖了 upstream 全量。下一步先把测试来源、构建模式和断言边界
写成可复核契约，再决定是否扩大范围。

## 目标与 ownership

worker 只负责 inventory、task 完成区和
`docs/reviews/ML-015g-llvm-suite-coverage-contract-20260721.md`，不修改实现或
测试语义：

1. 对 23 个 `.test` 记录来源注释、输入文件、编译/链接路径和最终断言方式。
2. 检查 lit 配置是否会静默 skip、是否有 `|| true` 或不检查退出码的路径。
3. 明确当前覆盖的是仓库切片，而非 upstream 全量 `llvm-test-suite`/
   `gcc-c-torture`；给出下一步扩大测试所需的前置条件和阻塞项。

## 约束

- 不修改 LLVM/QEMU/vector/kernel/spec、`docs/issues.yaml` 或 wiki。
- 不访问或引用 `~/toolchain`、`~/knowledge-graph`，不修改 ML-014a。
- 不以历史数字替代本轮检查，不把目录名当作 upstream 全量证明。

## 完成区

已完成仓库内 llvm-test-suite 切片的只读覆盖契约审计（2026-07-21）。

- `tests/lit/E2E/llvm-test-suite/*.test` 共 `23` 个；每个都有 `RUN` 行并引用
  对应 `Inputs/*.c`，统计命令 rc=`0`。
- `tests/lit/E2E/lit.cfg` 使用显式的 clang/llvm-mc/objcopy/QEMU/Gem5 路径。
  23 个 fixture 均有 QEMU `test $? -eq N` 断言；未发现 `|| true`。
- 其中 20 个同时有 Gem5 `test $? -eq N` 断言；
  `arrayresolution.test`、`bitops.test`、`minint.test` 当前只有 QEMU 断言，
  因此“llvm-test-suite 子集 23/23”不能表述为 23 个双后端通过。
- 这 23 个是仓库内从 upstream SingleSource 改写/裁剪的切片，不代表 upstream
  全量 `llvm-test-suite` 或 `gcc-c-torture`；扩大范围前仍需完整 suite 的构建
  集成、libc/ABI 和已知 tail-call/varargs 边界处理。

报告：`docs/reviews/ML-015g-llvm-suite-coverage-contract-20260721.md`。
本任务只读检查，没有修改实现、测试语义、issues/wiki 或 ML-014a。

### 独立 review

`docs/reviews/ML-015g-independent-review-20260721.md`，结论
**Accepted-with-findings**；reviewer 复核了 23 个 QEMU 断言、20 个 Gem5 断言、
3 个 QEMU-only fixture 和无 `|| true`，确认边界表述准确。3 个 QEMU-only fixture
作为后续双后端覆盖缺口保留，不在本任务中擅自补测试。
