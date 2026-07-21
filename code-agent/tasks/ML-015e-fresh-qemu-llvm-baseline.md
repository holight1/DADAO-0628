# ML-015e：一致性修复后的 fresh QEMU + LLVM 基线

**日期**：2026-07-21

**状态**：Accepted（30-task run：22/30）

## 背景

ML-015d 已修复 QEMU vector harness 的目录聚合和 fail-closed 门禁，ML-015c
已把 cold RegRAS `ret` 与合法 control-flow 的 vector 期望对齐 spec。需要在
这些修复之后重新取得可复核的 LLVM + QEMU 基线，不能继续引用旧的 203/204
或 E2E 历史数字。

## 目标与 ownership

worker 只负责 fresh build/test evidence、此 task MD 完成区和
`docs/reviews/ML-015e-fresh-qemu-llvm-baseline-20260721.md`，不修改实现代码。

1. 重新执行 QEMU 构建并记录原始 rc、QEMU binary/version/commit 信息。
2. 使用当前 `tests/scripts/run_qemu_test.py tests/vectors/isa/` 跑全量 ISA，
   记录 active/deferred/pass/fail/skip/input_errors 和原始 rc。
3. 运行 `PATH=.work/build/llvm/bin:$PATH llvm-lit -v tests/lit/E2E/`，记录
   原始 rc、完整 fresh 数字；若超时或环境问题必须明确区分，不用历史数字替代。
4. 不运行或修改 kernel、LLVM upstream test-suite、`docs/issues.yaml`、wiki；
   不访问或引用 `~/toolchain`、`~/knowledge-graph`，不修改 ML-014a。

## 验收

- QEMU build、ISA 目录和 E2E 均有命令、原始 rc、结果或明确阻塞原因。
- 不把 deferred 当 active，不把 QEMU vector 通过冒充 LLVM E2E 通过。
- 独立 reviewer 复核数字和测试入口，确认没有错误测试被引入。

## 完成区

已取得一致性修复后的 fresh LLVM + QEMU 基线，等待不同 subagent 独立 review。

### QEMU

- `ninja -C .work/source/qemu/build qemu-system-dadao` → `rc=0`。
- QEMU version：`10.0.0 (v10.0.0-19-gac58f31-dirty)`；source HEAD：
  `ac58f31acddc7f583e5087002df100297f2f87f9`；binary size `34065128`，
  本轮构建时间 `2026-07-21 10:13:52 +0800`。
- `python3 tests/scripts/run_qemu_test.py tests/vectors/isa/ --qemu
  .work/source/qemu/build/qemu-system-dadao` → `rc=0`。
- fresh 汇总：`active=202 deferred=11 pass=202 fail=0 skip=0 input_errors=0`。
  deferred 没有被计入 active；两个 cold-ret vector 均作为预期 `RASUF` 通过。

### LLVM E2E

- `PATH=.work/build/llvm/bin:$PATH llvm-lit -v tests/lit/E2E/` → `rc=0`。
- fresh 结果：`Total Discovered Tests: 59; Passed: 59 (100.00%)`，用时约
  `5.89s`。这是本轮实际执行结果，不沿用 ML-015a 的历史数字。
- 本任务没有运行 kernel、LLVM upstream test-suite 或其他未纳入当前门禁的
  测试集合。

### 约束检查

- 没有修改 QEMU/LLVM/spec/vectors 语义、`docs/issues.yaml` 或 wiki。
- 没有修改用户原有未跟踪的 `code-agent/tasks/ML-014a-musl-e2e-malloc-printf.md`。
- 未访问或引用 `~/toolchain`、`~/knowledge-graph`。

### 独立 review

`docs/reviews/ML-015e-independent-review-20260721.md`，结论 **Accepted**；
reviewer 确认 QEMU `active=202/deferred=11` 与 LLVM E2E `59/59` 相互独立、
命令和结果自洽，未发现把 QEMU vector 结果混入 LLVM E2E 的问题。
