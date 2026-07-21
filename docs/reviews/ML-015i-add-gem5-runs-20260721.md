# ML-015i：三个 llvm-test-suite fixture 补齐 Gem5 RUN

日期：2026-07-21

## 变更范围

仅新增三条 Gem5 `RUN` 行：

- `arrayresolution.test`：Gem5 expected rc `0`
- `bitops.test`：Gem5 expected rc `249`
- `minint.test`：Gem5 expected rc `1`

没有改动 C 输入、期望值、QEMU 行或其他实现文件；未访问或引用
`~/toolchain`、`~/knowledge-graph`，未修改 issues/wiki/ML-014a。

## 真实验收结果

| 检查 | rc | PASS | FAIL | SKIP |
|---|---:|---:|---:|---:|
| `PATH=.work/build/llvm/bin:$PATH llvm-lit -v tests/lit/E2E/llvm-test-suite/` | 0 | 23 | 0 | 0 |
| `PATH=.work/build/llvm/bin:$PATH llvm-lit -v tests/lit/E2E/` | 0 | 59 | 0 | 0 |
| `git diff --check` | 0 | — | — | — |

两项 llvm-lit 均真实完成，无未完成测试、FAIL 或 SKIP。
