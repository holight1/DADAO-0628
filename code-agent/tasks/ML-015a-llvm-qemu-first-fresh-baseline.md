# ML-015a：LLVM + QEMU 优先路线的 fresh baseline

**日期**：2026-07-21

**状态**：Needs-fix（30-task run：18/30）

## 决策记录

当前阶段优先保证 LLVM + QEMU 的编译、裸金属和用户态 E2E 链路；kernel/SEE/CFX
实现暂不继续扩展。原因是当前 kernel 侧仍处于 CFX 状态机和 RegRAS 保存机制的
前置设计阶段，而 LLVM + QEMU 是最终 `qemu + kernel + 用户态` 链路中可以先独立
收敛、且能提供稳定故障基线的部分。

## 本任务目标

在 QEMU CFX scaffold `0019` 之后，重新建立可审计的 fresh baseline：

1. 重编当前 QEMU，确认 `0019` 可应用且不破坏已有 M1 模拟器。
2. 跑 QEMU 裸金属 ISA harness，记录 active case、PASS/FAIL/SKIP、退出码和
   版本/构建来源。
3. 跑 `tests/lit/E2E/`，重点记录其中 23 个 llvm-test-suite thin-lit 用例；
   不把历史 59/59 记录冒充本轮 fresh 结果。
4. 复核 full upstream llvm-test-suite/gcc-c-torture 尚未启动，以及 tail-call
   和 varargs RB pointer save-area 仍是扩大测试前的已知边界。

## 约束与 ownership

- worker 只负责构建/测试和 task-owned evidence，不改 LLVM、QEMU、gem5、kernel、
  contracts、`docs/issues.yaml` 或 wiki。
- 不访问或引用 `~/toolchain`、`~/knowledge-graph`；不修改用户原有未跟踪的
  `code-agent/tasks/ML-014a-musl-e2e-malloc-printf.md`。
- 所有失败必须保留原始命令、rc、stdout/stderr 摘要；禁止用 `|| true` 掩盖失败。
- 若测试耗时或环境缺失，记录为环境事实，不臆造通过。

## 验收

- QEMU build rc=0，且使用 root patch series 的当前 `0019`。
- 裸金属 harness 有明确总数和结果分类。
- full E2E 有明确总数和结果分类，llvm-test-suite 子目录单独列出。
- 由不同 subagent 独立 review 证据和“fresh/历史”边界。

## 完成区

（由 worker 填写；完成后由不同 subagent 独立 review）

### worker evidence（2026-07-21）

- Review 报告：[ML-015a-llvm-qemu-first-fresh-baseline-20260721.md](/home/holight/DADAO-0628/docs/reviews/ML-015a-llvm-qemu-first-fresh-baseline-20260721.md)。
- `components/qemu/patches/series` 已确认包含最后一项 `0019-dadao-cfx-state-scaffold.patch`；`.work/source/qemu` 对该 patch 的 `git apply --reverse --check` 为 `rc=0`，源码 marker 与 patch 一致。
- 实际执行 `ninja -C .work/source/qemu/build qemu-system-dadao`，`rc=0`；QEMU 来源为 `.work/source/qemu` HEAD `ac58f31acddc7f583e5087002df100297f2f87f9`，构建产物报告版本为 `10.0.0 (v10.0.0-19-gac58f31)`。
- 实际执行 `python3 tests/scripts/run_qemu_test.py tests/vectors/isa/`，因目录参数在 case 构建前触发 `AttributeError: 'str' object has no attribute 'get'`，`rc=1`。只读 inventory 为 212 总向量、206 active、6 deferred；按现有 harness 逐 YAML 执行得到 fresh `PASS=204 / FAIL=2 / SKIP=0 / timeout=0`，两个 FAIL 均为预期 `ILLI` 实得 `RASUF(0x85)` 的 control-flow case。
- 实际执行 `PATH=.work/build/llvm/bin:$PATH llvm-lit -v tests/lit/E2E/`；本轮由用户在约 0.1 秒后中断，工具未产生数值 rc，事后无残留 llvm-lit 进程，因此没有伪造 full E2E 或其中 23 个 `llvm-test-suite` 用例的 fresh 统计。
- 明确边界：历史 `59/59` 与历史 `203 PASS` 不属于本轮 fresh 结果；full upstream `llvm-test-suite`、`gcc-c-torture` 尚未启动；tail-call 与 varargs RB pointer save-area 仍为 open boundary。
- 未访问 `~/toolchain`、`~/knowledge-graph`，未修改 LLVM/QEMU/gem5/kernel/contracts/docs/issues/wiki，也未修改用户原有未跟踪的 `code-agent/tasks/ML-014a-musl-e2e-malloc-printf.md`。

### 独立 review

- `docs/reviews/ML-015a-independent-review-20260721.md`：`Needs-fix`。
- 关键 finding：`control-flow.yaml` 两个 cold-RegRAS `ret` 用例将期望写成
  `ILLI(0x82)`，但 `contracts/isa/spec.md §5.6` 明确规定应为
  `RASUF(0x85)`；不得把这两项计为 QEMU 失败，也不得在本任务中擅自修改向量。
- 因此本轮只接受“QEMU 构建成功、206 active 中其余 204 项通过”的事实记录；
  fresh E2E 因中断无数值结果，不能接受为完整回归基线。
