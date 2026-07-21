# ML-015f：llvm-test-suite 子集独立门禁

**日期**：2026-07-21

**状态**：Accepted（30-task run：23/30）

## 背景

ML-015e 已确认完整 `tests/lit/E2E/` fresh 为 59/59，但该入口同时包含
普通 E2E、musl、fault probe 和仓库内改写的 `llvm-test-suite` SingleSource
切片。需要单独运行子目录，确认 23 个 llvm-test-suite 用例的数字和完整 E2E
计数关系，避免把“完整 E2E 通过”误说成 upstream 全量 suite 通过。

## 目标与 ownership

worker 只负责运行证据、task 完成区和
`docs/reviews/ML-015f-llvm-test-suite-isolated-gate-20260721.md`，不修改实现。

1. 统计 `tests/lit/E2E/llvm-test-suite/*.test`，记录清单数量。
2. 运行 `PATH=.work/build/llvm/bin:$PATH llvm-lit -v
   tests/lit/E2E/llvm-test-suite/`，记录原始 rc 和 fresh PASS/FAIL/SKIP。
3. 对照 ML-015e 的完整 59/59，只说明当前仓库切片覆盖范围；不宣称
   upstream llvm-test-suite 或 gcc-c-torture 全量通过。

## 约束

- 不修改 LLVM/QEMU/vector/kernel/spec、`docs/issues.yaml` 或 wiki。
- 不访问或引用 `~/toolchain`、`~/knowledge-graph`，不修改 ML-014a。
- 不以 `|| true` 遮蔽失败，不用历史数字替代本轮结果。

## 完成区

完成于 2026-07-21。

- 统计命令：`bash -lc 'files=(tests/lit/E2E/llvm-test-suite/*.test); printf "test_count=%s\n" "${#files[@]}"'`；rc=`0`；结果：`23` 个 `.test`。
- 测试命令：`PATH=.work/build/llvm/bin:$PATH llvm-lit -v tests/lit/E2E/llvm-test-suite/`；rc=`0`。
- 本轮真实结果：`23` discovered，`23` PASS，`0` FAIL，`0` SKIP（输出中的 23 个用例均为 PASS；Testing Time `2.84s`）。
- 范围说明：这是 `tests/lit/E2E/llvm-test-suite/` 的隔离子集 `23/23`，与完整 E2E 的 `59/59` 分开记录；不据此声称 upstream 全量 `llvm-test-suite` 或 `gcc-c-torture` 已通过。

### 独立 review

`docs/reviews/ML-015f-independent-review-20260721.md`，结论 **Accepted**；
reviewer 独立核对 `23` 个 `.test`、`23 PASS/0 FAIL/0 SKIP` 和 `rc=0`，确认
范围表述没有越界到 upstream 全量测试。
