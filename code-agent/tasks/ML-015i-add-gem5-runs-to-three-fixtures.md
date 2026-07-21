# ML-015i：补齐 3 个 llvm-test-suite fixture 的 Gem5 RUN

**日期**：2026-07-21

**状态**：Accepted（30-task run：26/30）

## 背景

ML-015g 发现 `arrayresolution.test`、`bitops.test`、`minint.test` 只有 QEMU
断言；ML-015h 已用当前构建链和 Gem5 独立复现预期退出码 `0/249/1`。现在做
最小一致性修复，使这三个仓库切片 fixture 也有双后端门禁。

## 目标与 ownership

worker 只修改以下三个 `.test` 文件，并更新本 task 完成区及
`docs/reviews/ML-015i-add-gem5-runs-20260721.md`：

- `tests/lit/E2E/llvm-test-suite/arrayresolution.test`
- `tests/lit/E2E/llvm-test-suite/bitops.test`
- `tests/lit/E2E/llvm-test-suite/minint.test`

每个文件只新增一条与 QEMU 预期相同的 Gem5 `RUN` 退出码断言；不得改 C 输入、
QEMU 命令、期望值或其他 fixture。完成后运行三项隔离 lit 和完整
`PATH=.work/build/llvm/bin:$PATH llvm-lit -v tests/lit/E2E/`，记录原始 rc/数字。

## 约束

- 不修改 LLVM/QEMU/Gem5 源码、vectors、kernel、spec、`docs/issues.yaml` 或 wiki。
- 不访问或引用 `~/toolchain`、`~/knowledge-graph`，不修改 ML-014a。
- 不用 `|| true`，不把手工 probe 或历史数字冒充 fresh lit 结果。

## 完成区

（由 worker 填写；完成后由不同 subagent 独立 review）

**状态**：已完成（待独立 review）

**实现**：仅在以下三个 fixture 各新增一条 Gem5 `RUN` 行，期望码分别保持
QEMU 的 `0`、`249`、`1`；未修改 C 输入、期望值、QEMU 行或其他文件。

- `tests/lit/E2E/llvm-test-suite/arrayresolution.test`
- `tests/lit/E2E/llvm-test-suite/bitops.test`
- `tests/lit/E2E/llvm-test-suite/minint.test`

**真实验收结果**：

| 命令 | rc | PASS | FAIL | SKIP |
|---|---:|---:|---:|---:|
| `PATH=.work/build/llvm/bin:$PATH llvm-lit -v tests/lit/E2E/llvm-test-suite/` | 0 | 23 | 0 | 0 |
| `PATH=.work/build/llvm/bin:$PATH llvm-lit -v tests/lit/E2E/` | 0 | 59 | 0 | 0 |
| `git diff --check` | 0 | — | — | — |

未完成测试：无；两项指定 llvm-lit 命令均已完成，未出现 FAIL 或 SKIP。

### 独立 review

`docs/reviews/ML-015i-independent-review-20260721.md`，结论 **Accepted**；
reviewer 独立确认三条新增 Gem5 命令实际展开执行，隔离 `3/3`、子目录 `23/23`、
完整 E2E `59/59` 和 `git diff --check` 均通过。
