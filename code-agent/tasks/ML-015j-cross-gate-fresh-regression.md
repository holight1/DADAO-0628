# ML-015j：双后端覆盖修复后的跨门禁 fresh 回归

**日期**：2026-07-21

**状态**：Accepted（30-task run：27/30）

## 背景

ML-015i 为 3 个 llvm-test-suite fixture 补齐 Gem5 RUN 后，需要重新验证 QEMU
ISA、隔离 llvm-test-suite 和完整 E2E 三个门禁没有互相污染或计数漂移。

## 目标与 ownership

worker 只负责运行证据、task 完成区和
`docs/reviews/ML-015j-cross-gate-fresh-regression-20260721.md`，不改实现：

1. 重新构建 QEMU，记录 rc/version/source HEAD。
2. 运行 QEMU ISA vector 目录并记录 active/deferred/pass/fail/skip/input_errors。
3. 运行 `tests/lit/E2E/llvm-test-suite/` 和完整 `tests/lit/E2E/`，分别记录
   fresh rc 与 PASS/FAIL/SKIP。
4. 检查 `git diff --check`，确认本任务不改变 source/vector 语义。

## 约束

- 不修改 LLVM/QEMU/Gem5/vector/kernel/spec、`docs/issues.yaml` 或 wiki。
- 不访问或引用 `~/toolchain`、`~/knowledge-graph`，不修改 ML-014a。
- 不使用历史数字，不用 `|| true` 隐藏失败。

## 完成区

已完成 ML-015i 后的跨门禁 fresh 回归，等待独立 review。

- `ninja -C .work/source/qemu/build qemu-system-dadao` → `rc=0`。
- QEMU：`10.0.0 (v10.0.0-19-gac58f31-dirty)`；source HEAD
  `ac58f31acddc7f583e5087002df100297f2f87f9`。
- `python3 tests/scripts/run_qemu_test.py tests/vectors/isa/ --qemu
  .work/source/qemu/build/qemu-system-dadao` → `rc=0`；
  `active=202 deferred=11 pass=202 fail=0 skip=0 input_errors=0`。
- `PATH=.work/build/llvm/bin:$PATH llvm-lit -v
  tests/lit/E2E/llvm-test-suite/` → `rc=0`；`23/23` pass，`0` fail，`0` skip。
- `PATH=.work/build/llvm/bin:$PATH llvm-lit -v tests/lit/E2E/` → `rc=0`；
  `59/59` pass，`0` fail，`0` skip。
- `git diff --check` → `rc=0`。

未修改实现、vector 语义、issues/wiki 或 ML-014a；没有使用 `|| true` 或历史
数字替代本轮结果。

报告：`docs/reviews/ML-015j-cross-gate-fresh-regression-20260721.md`。

### 独立 review

`docs/reviews/ML-015j-independent-review-20260721.md`，结论 **Accepted**；
reviewer 确认 QEMU ISA、llvm-test-suite 和完整 E2E 的数字彼此独立且与报告一致。
