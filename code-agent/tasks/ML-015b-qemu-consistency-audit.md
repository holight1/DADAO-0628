# ML-015b：QEMU spec / vector / harness 一致性审计

**日期**：2026-07-21

**状态**：Accepted-with-findings（30-task run：19/30）

## 触发原因

ML-015a fresh baseline 发现两个 `ret` 用例的 expected fault 与 ISA spec 不一致：
测试声明 `ILLI`，而 `contracts/isa/spec.md §5.6` 对 cold RegRAS 明确规定
`RASUF`。在修复或扩大测试前，必须先完成一次 QEMU 一致性审计，避免把错误的
测试期望固化为回归门禁。

## 审计层次

### A. spec → vector

- 逐项核对 `tests/vectors/isa/*.yaml` 的 `wiki_cite`、`expected_fault`、
  `expected_state` 与 `contracts/isa/spec.md` 对应章节。
- 重点覆盖 ILLI/UNDI/MALIGN/RASOF/RASUF、精确异常、PC/RA 不变性、RegRAS
  cold/overflow、control-flow encoding vs semantic/legality 的分类。
- 不修改向量；发现不一致要给出最小修正建议和证据。

### B. vector → harness

- 核对 `tests/scripts/run_qemu_test.py` 的 fault code 映射、目录参数行为、
  active/deferred 计数和 fail-closed 规则。
- 确认 harness 不会把异常退出码、timeout、SKIP 或脚本错误误报为 PASS。

### C. harness → QEMU

- 对照 QEMU `helper.c`、`cpu.c`、control-flow/RAS 实现和 exit port 路径，确认
  harness 期望的 fault code 确实由当前 QEMU 产生，且优先级/精确异常行为一致。
- 复核当前 `0019` scaffold 只增加状态字段，不改变现有异常语义。
- 必要时运行已有 active vectors 作为观察，不引入或改写测试。

## 约束

- 只读审计；不得修改 QEMU、LLVM、vectors、harness、`docs/issues.yaml` 或 wiki。
- 不访问或引用 `~/toolchain`、`~/knowledge-graph`。
- 不把历史 203 PASS、59/59 当成本轮 fresh 证据；所有实际命令记录 rc。
- 由两个不同 subagent 分别审计 A/B 与 C，再由主线合并为一致性汇总。

## 验收

- 输出 spec/vector、vector/harness、harness/QEMU 三张问题表。
- 每个 finding 分类为：一致、spec/测试期望错误、harness 错误、QEMU 实现错误、
  证据不足。
- 在汇总前不推进新的实现任务。

## 完成区

### 结果

- A/B 审计：`docs/reviews/ML-015b-spec-vector-harness-20260721.md`。
- C 审计：`docs/reviews/ML-015b-harness-qemu-20260721.md`。
- 主线汇总：`docs/reviews/ML-015b-qemu-consistency-summary-20260721.md`。
- 主要结论：QEMU fault code 退出码层基本一致；主要阻断来自 vectors 的
  spec/class/expected_fault 错配和 harness 对 fault 来源、PC、RA 的观测不足。
- ML-015a 的两个 cold-ret 失败不得归因于 QEMU，也不得直接修改测试后宣布
  全绿；当前实现推进暂停，下一步先修复/审计测试与 harness 门禁。

### 可复核命令

```bash
nl -ba contracts/isa/spec.md | sed -n '883,914p;236,240p'
nl -ba tests/vectors/isa/control-flow.yaml | sed -n '434,520p'
nl -ba tests/scripts/run_qemu_test.py | sed -n '24,59p;96,140p'
nl -ba .work/source/qemu/target/dadao/helper.c | sed -n '45,97p'
nl -ba .work/source/qemu/target/dadao/cpu.c | sed -n '115,130p;236,246p'
