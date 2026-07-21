# ML-015g llvm-test-suite coverage contract

日期：2026-07-21

## Inventory

- `tests/lit/E2E/llvm-test-suite/*.test`：`23` 个，inventory rc=`0`。
- 每个 fixture 都有 `// RUN:` 行并引用 `Inputs/*.c`。
- `tests/lit/E2E/lit.cfg` 提供显式的 clang、llvm-mc、llvm-objcopy、QEMU 和
  Gem5 substitution；本目录 fixture 未发现 `|| true`。
- 23 个 fixture 都有 QEMU `test $? -eq N` 退出码断言。
- 20 个 fixture 有 Gem5 `test $? -eq N` 断言；以下 3 个只有 QEMU 断言：
  `arrayresolution.test`、`bitops.test`、`minint.test`。

## Boundary

该目录是仓库内从 upstream SingleSource 改写/裁剪的 23 个 fixture。它不是
upstream 全量 `llvm-test-suite`，也不是 `gcc-c-torture` 全量通过证明。
ML-015f 的 `23/23` 只能作为该仓库切片的 lit 结果；其中 3 个还不能声称
双后端覆盖。

扩大全量前仍需单独处理完整 suite 的构建集成、libc/ABI 依赖，以及 roadmap
中已知的 tail-call lowering 和 varargs RB-bank save-area 边界。

本审计只读，无实现或测试语义修改。
