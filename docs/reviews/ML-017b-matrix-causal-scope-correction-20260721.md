# ML-017b matrix causal scope correction report

日期：2026-07-21（Asia/Shanghai）  
任务：DADAO-0628 ML-017b（本轮第 28 任务）  
状态：**worker 已完成；待独立 review**

## Review purpose

本报告是 ML-017a 的新 scope-correction 记录，不改写
[`ML-017a 原 task`](../../code-agent/tasks/ML-017a-post-frame-musl-object-matrix.md)
或 [`ML-017a 原 report`](ML-017a-post-frame-musl-object-matrix-20260721.md)，以保留
审计历史。它只修正因果范围和任务记录，不修改生产代码、已有证据或 30-task tracker。

## Evidence-by-evidence correction

### ML-017a：结果事实成立，但范围是 final-head matrix

[`ML-017a task`](../../code-agent/tasks/ML-017a-post-frame-musl-object-matrix.md)
记录 nested LLVM final HEAD `d3bd9c15434fd7a48c0b7bab87354778cd932a72` 的 fresh
1347-object matrix，结果为 `1166 success / 181 failure`。它与 ML-016u 逐对象对齐
得到：

```text
success -> failure = 0
failure -> success = 0
failure-cluster movement = 0
```

这个 ledger、freshness 和有限范围的静态 prologue 结果保留有效；它证明的是
**相对 ML-016u aggregate baseline 的 0 regression / 0 migration**。

### ML-016u：aggregate baseline 的 identity 不是 d3bd parent

[`ML-016u task`](../../code-agent/tasks/ML-016u-post-i1-musl-object-matrix.md)
记录 baseline 工具为 LLVM revision
`40bc313742b00848d341e77e1a38441211971729`（`40bc`），并记录 1347-object
`1166/181` 结果。该 baseline 具备逐对象可比性，但它不是 d3bd 的直接 parent
构建，因此只能作为 aggregate baseline 使用。

### Nested graph：缺失的是 be99 baseline

[`ML-017a independent review`](ML-017a-independent-review-20260721.md) 的独立图核对
为：

```text
40bc -> be99 -> d3bd
```

`be99e5505abe341100c62d70cd955b2df7e4711e` 是
`d3bd9c15434fd7a48c0b7bab87354778cd932a72` 的 parent。由此，ML-017a 实际比较
是 `40bc → d3bd`，而不是隔离单一 frame commit 的 `be99 → d3bd`。
[`ML-016y frame report`](ML-016y-frame-rounding-fix-20260721.md) 同样记录 d3bd/be99
的 parent 关系；[`ML-016z review`](ML-016z-independent-review-20260721.md) 记录
d3bd final-head 的 source、tool 和 targeted runtime provenance。

### Independent review：finding 的处理选择

[`ML-017a independent review`](ML-017a-independent-review-20260721.md) 的结论为
`Accepted-with-findings`：fresh ledger 和有限静态结论成立，但指出 ML-016u 的
工具身份是 `40bc`、本轮是 `d3bd`，所以没有 be99 baseline 时不能宣称 d3bd
frame rounding commit 的完全因果隔离。该 review 要求“补 be99 parent baseline，或
收窄为 ML-016u aggregate baseline”；ML-017b 选择收窄，不进行重型实验。

## Corrected claim

### 保留

> d3bd final HEAD 的 fresh 1347-object matrix 为 1166/181；相对记录中的
> ML-016u（40bc）aggregate baseline，逐对象为 0 regression / 0 migration。

### 撤销的因果外推

不得把上述结果写成“d3bd frame fix 的 frame-only parent-vs-child causal isolation
已完成”，也不得使用任何把 0 migration 直接归因于 d3bd frame fix 的同义表述。
`be99 → d3bd` 的 causal isolation **未完成**。

## ML-016x/y/z evidence boundary

ML-016x/y/z 另有与 d3bd frame behavior 相关的 static/runtime 或 final-head
provenance probes：

- [`ML-016x review`](ML-016x-independent-review-20260721.md) 支持 `_Exit`、frame
  shape 与双后端 targeted probe 的各自结论；
- [`ML-016y review`](ML-016y-independent-review-20260721.md) 记录 frame lowering 的
  静态布局与当时的 provenance 限制；
- [`ML-016z review`](ML-016z-independent-review-20260721.md) 核验 d3bd final-head
  的 source/tool/runtime provenance，并明确 odd/padding=4 只保留静态边界分析。

这些是有边界的 frame-specific probes，不能替代在 be99 parent 上使用同一工具和
同一 1347-object matrix 的完整 baseline；因此它们不改变 ML-017b 对 causal claim
的收窄。

## Follow-up and gate disposition

要恢复 frame-only causal claim，后续实验必须在 `be99` parent 上独立构建同一工具，
对同一 musl source/configuration 运行同一受控 1347-object matrix，并保留两端完整
provenance 与逐对象比较。本轮不做该重型实验。

ML-017a 的结果仍可进入**targeted archive/QEMU gate**，但仅限 fresh、成功且有
artifact hash 的对象和显式 probe；当前可以进入该 gate，**不能宣称 frame-only
causal isolation**。这也不等于完整 libc archive、完整 link/runtime 或完整 1347
object acceptance。

## Acceptance and status

### Worker acceptance

- [x] 新增 canonical ML-017b task 与本 report；未改 ML-017a 原 report。
- [x] 写明 `ML-016u aggregate baseline → d3bd` 的 0 regression / 0 migration。
- [x] 写明 `be99 parent → d3bd child` causal isolation 尚未完成。
- [x] 逐项记录 nested graph、ML-016x/y/z probe 边界、be99/1347 后续实验和 gate 限制。
- [x] 未修改生产代码、禁改目录、已有 `/tmp` 证据或 30-task tracker。

### Independent-review acceptance

- [ ] 核对事实来源和 revision graph。
- [ ] 核对 canonical wording 未恢复 frame-only 因果宣称。
- [ ] 核对“be99 parent + 同一工具 + 1347 matrix”的后续要求、本轮不执行的状态，
      以及 targeted archive/QEMU gate 的边界。

当前 reviewer 状态：**待独立 review**。
