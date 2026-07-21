# ML-017b：ML-017a matrix causal scope correction

日期：2026-07-21（Asia/Shanghai）  
关联任务：DADAO-0628 ML-017b（本轮第 28 任务）

## 状态与范围

- worker：**已完成 scope correction 文档**。
- reviewer：**Lovelace the 2nd；Accepted-with-findings**。
- 本任务只新增本文件和
  [`docs/reviews/ML-017b-matrix-causal-scope-correction-20260721.md`](../../docs/reviews/ML-017b-matrix-causal-scope-correction-20260721.md)。
- 不修改 [ML-017a 原 task](ML-017a-post-frame-musl-object-matrix.md) 或
  [ML-017a 原 report](../../docs/reviews/ML-017a-post-frame-musl-object-matrix-20260721.md)，
  以保留审计历史；不修改 30-task tracker，交由主 agent 集成。
- 不修改生产代码或 `.work/source/llvm`、musl、QEMU/Gem5、spec、launcher、
  `docs/issues.yaml`、wiki，也不改写已有 `/tmp` 证据。

## 目的

本任务落实 ML-017a 独立 review 的 blocking finding：把可证明的 aggregate
baseline 结论与尚未完成的 frame-only 因果结论分开。选择的修复路径是**收窄措辞**，
本轮不补做 be99 parent 的重型 1347-object matrix。

## 逐项事实与来源

### 1. ML-017a final matrix

[`ML-017a task`](ML-017a-post-frame-musl-object-matrix.md) 记录的是 nested LLVM
final HEAD `d3bd9c15434fd7a48c0b7bab87354778cd932a72` 上的 fresh 1347-object
matrix：`1166 success / 181 failure`。其相对 ML-016u 的逐对象比较为：

- 1166 个旧成功全部保持成功；181 个旧失败全部保持失败；
- `success → failure = 0`，`failure → success = 0`，failure cluster 移动为 0；
- 未生成 archive，也未完成完整 link/runtime、QEMU 或 Gem5 gate。

因此本轮保留的结论是：**相对记录中的 ML-016u aggregate baseline，已证明
0 regression / 0 migration**。

### 2. ML-016u baseline identity

[`ML-016u task`](ML-016u-post-i1-musl-object-matrix.md) 明确记录其工具身份为 LLVM
revision `40bc313742b00848d341e77e1a38441211971729`（简称 `40bc`），并记录同一
`1166/181` matrix 及逐对象 provenance。ML-016u 不是 d3bd 的父提交实验，而是
较早工具身份上的 aggregate baseline。

### 3. nested commit graph

[`ML-017a independent review`](../../docs/reviews/ML-017a-independent-review-20260721.md)
独立检查 nested graph 得到：

```text
40bc -> be99 -> d3bd
```

其中 `be99e5505abe341100c62d70cd955b2df7e4711e` 是
`d3bd9c15434fd7a48c0b7bab87354778cd932a72` 的 parent。故 ML-017a 的
`40bc → d3bd` 对比跨越了 `be99` 与 `d3bd` 的提交差异，不能等同于
`be99 → d3bd` 的 parent-vs-child frame-only 实验。ML-016y 的 frame report 也把
d3bd 与 be99 parent 身份记录为同一 nested 提交链，ML-016z 则核验了 d3bd
final-head 的 source/runtime provenance：
[`ML-016y report`](../../docs/reviews/ML-016y-frame-rounding-fix-20260721.md)、
[`ML-016z review`](../../docs/reviews/ML-016z-independent-review-20260721.md)。

### 4. review finding 与本次处理

[`ML-017a independent review`](../../docs/reviews/ML-017a-independent-review-20260721.md)
接受 ledger 与有限范围静态结论，但明确指出：没有 be99 baseline 时，不能把
零迁移表述为 d3bd frame rounding commit 的完全因果隔离；可选修复是补 be99
baseline 或把主张限定为 ML-016u aggregate baseline。本任务选择后者。

## 结论边界（canonical wording）

允许写入后续索引或 gate 说明的表述：

> d3bd final HEAD 的 fresh 1347-object matrix 为 1166/181；相对记录中的
> ML-016u（40bc）aggregate baseline，逐对象结果为 0 regression / 0 migration。

必须避免的表述：

> “d3bd frame fix 已通过 frame-only parent-vs-child causal isolation”或任何
> 把 ML-017a 的 0 migration 直接归因于 d3bd frame fix 的等价措辞。

ML-016x、ML-016y、ML-016z 分别保留了 frame-specific static/runtime、final-head
provenance 与 targeted probe 证据；这些证据可支持各自明确的 probe 范围，但**不能
替代完整的 be99 parent 同工具、同方法、1347-object matrix**，也不能补足本任务
缺失的 causal isolation。

## 后续建议与 gate

若未来需要作出 frame-only causal claim，必须：

1. 在 `be99` parent 上独立构建同一工具身份；
2. 使用同一 musl source/configuration、同一受控方法和完整 1347-object matrix；
3. 保存 parent 与 d3bd 两端的 tool/source provenance，并逐对象比较 regression、
   migration、failure clusters 与 artifact freshness。

这是重型实验，本轮不执行。当前结果仍可进入**受控 targeted archive/QEMU gate**，
限定为 fresh、成功且有 artifact hash 的对象及显式 probe；但不得宣称
frame-only causal isolation。完整 1347-object archive、完整 libc link/runtime
acceptance 仍不由 ML-017a/ML-017b 提供。

## 验收标准

### Worker

- [x] 只新增本 canonical task 和对应新 report。
- [x] 逐项引用 ML-017a、ML-016u、nested graph 事实和 ML-017a independent review。
- [x] 明确写出已证明的 `ML-016u aggregate baseline → d3bd`：0 regression / 0 migration。
- [x] 明确写出未完成的 `be99 parent → d3bd child` frame-only causal isolation。
- [x] 记录 ML-016x/y/z probe 不能替代 be99 matrix，并记录后续重型实验建议与本轮 gate 边界。
- [x] 保持状态为“待独立 review”，不修改 tracker。

### Independent reviewer

- [ ] 核对两份新文件的来源链接、revision graph 和 canonical wording。
- [ ] 确认文档没有把 `40bc → d3bd` aggregate comparison 写成 `be99 → d3bd`
      causal experiment，也没有把 ML-016x/y/z probes 写成完整 matrix 替代品。
- [ ] 确认后续建议包含“be99 parent、同一工具、1347 matrix”，且本轮明确不做。
- [ ] 确认 targeted archive/QEMU gate 的允许范围和 frame-only 禁止宣称均已保留。
- [ ] 独立 review 完成后再更新本任务状态；当前状态仍为**待独立 review**。

最终状态：**Audit-accepted-with-findings**。无阻塞 finding；历史 ML-016u 详细 review
中的 stale transition 表保留不改，以维持历史审计记录。
