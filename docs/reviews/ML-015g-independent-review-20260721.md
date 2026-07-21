# ML-015g 独立 review

日期：2026-07-21

结论：**Accepted-with-findings**

根据 `code-agent/tasks/ML-015g-llvm-suite-coverage-contract.md` 与
`docs/reviews/ML-015g-llvm-suite-coverage-contract-20260721.md` 的范围核对，静态
计数与报告一致：

- `tests/lit/E2E/llvm-test-suite/*.test` 共 23 个；23 个都有 QEMU
  `test $? -eq N` 退出码断言。
- 20 个都有 Gem5 `test $? -eq N` 断言/RUN。
- `arrayresolution.test`、`bitops.test`、`minint.test` 是 3 个 QEMU-only
  fixture，缺少 Gem5 RUN，因此不能表述为 23 个双后端通过。
- 在本次 ML-015g 检查范围（上述 fixture 与 `tests/lit/E2E/lit.cfg`）内未发现
  `|| true`。

报告的边界表述正确：23 个是仓库内从 upstream SingleSource 改写/裁剪的切片，
没有把它说成 upstream `llvm-test-suite` 或 `gcc-c-torture` 全量，也没有把
`23/23` 说成 23 个双后端结果。现有 finding 是 3 个 fixture 尚无 Gem5 RUN；
这不阻塞当前切片覆盖契约的接受，但在扩大双后端覆盖前仍需补齐并独立验证。

本 review 未运行测试，未修改实现、测试语义或 ML-014a。
