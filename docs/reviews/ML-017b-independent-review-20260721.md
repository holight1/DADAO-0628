# ML-017b 独立 Review

日期：2026-07-21（Asia/Shanghai）  
角色：ML-017b independent reviewer

## 结论

**Accepted-with-findings**。

ML-017b 已正确把 ML-017a 的结论收窄为相对 ML-016u aggregate baseline 的
object-matrix 事实；没有把它写成 `be99 → d3bd` 的 frame-only causal isolation。
没有阻塞性 finding。唯一 finding 是历史引用卫生问题，见下文；按本轮范围不改写
该历史记录。

本轮只读核对了 ML-017b task/report、ML-017a independent review、ML-016u task 与
canonical report/index、ML-016x/y/z 相关 review，以及 nested LLVM 的提交元数据。
未查阅或引用 `~/toolchain`、`~/knowledge-graph`；未修改生产代码、旧 task/report、
tracker、QEMU/Gem5、spec 或 launcher。

## 阻塞 findings

无。

## 核对结果

### 1. 1166/181 与 0 regression / 0 migration 的范围准确

ML-017a task/report 记录的是 nested LLVM final HEAD
`d3bd9c15434fd7a48c0b7bab87354778cd932a72` 上 fresh 的 1347-object matrix：
`1166 success / 181 failure`。ML-016u task 与更正后的 canonical index/report
确认 aggregate baseline 同样是 `1166/181`，工具身份为 LLVM revision
`40bc313742b00848d341e77e1a38441211971729`（`40bc`）。

ML-017b 保留的 canonical wording：

> d3bd final HEAD 的 fresh 1347-object matrix 为 1166/181；相对记录中的
> ML-016u（40bc）aggregate baseline，逐对象为 0 regression / 0 migration。

该表述准确。它描述的是两个已记录的、逐对象可比的 aggregate 结果，没有把
ML-016f 的历史 `1163/184` 或三个旧迁移对象混入 ML-016u transition。

### 2. nested graph 与 causal 边界准确

只读检查 nested LLVM 得到：

```text
40bc313742b00848d341e77e1a38441211971729
  -> be99e5505abe341100c62d70cd955b2df7e4711e
  -> d3bd9c15434fd7a48c0b7bab87354778cd932a72
```

`d3bd` 的直接 parent 是 `be99`；`be99` 的 parent 是 `40bc`。`be99 → d3bd` 的
commit 主题为 frame-size ABI alignment，且该 commit 修改了 frame-lowering 源和
regression 文件。ML-017a 实际使用的是 `40bc → d3bd` 的已有 aggregate baseline
对比，而不是在 `be99` parent 上用同一工具和同一方法重跑的 parent-vs-child
实验。

ML-017b 明确写出 `be99 → d3bd` frame-only causal isolation **尚未完成**，并
明确禁止将 0 migration 直接归因于 d3bd frame fix；这正确闭合了 ML-017a
independent review 的 blocking finding。

### 3. ML-016x/y/z 没有被越界当成替代矩阵

ML-017b 对 ML-016x/y/z 的定位正确：

- ML-016x 是 `_Exit`/syscall frame shape 的窄范围 static/runtime 对照；
- ML-016y 的历史 provenance blocking finding 已由 ML-016z 针对 final HEAD
  的 provenance 重跑处理，但 odd/padding=4 仍是静态边界，不是 runtime 通过；
- 这些 targeted probe 支持各自明确的 frame-specific 观察，不能替代
  `be99` parent、同一工具身份、同一 source/configuration、完整 1347-object
  matrix 的 baseline。

因此 ML-017b 没有把 ML-016x/y/z targeted evidence 写成完整 causal isolation，
也没有用它们替代缺失的 `be99` matrix。

### 4. gate 与完整验收边界保留正确

ML-017b 允许继续进入受控 targeted archive/QEMU gate，但范围限于 fresh、成功且
有 artifact hash 的对象及显式 probe。报告同时明确本轮没有提供完整 archive、完整
libc link/runtime 或完整 1347-object acceptance，也不能据此宣称 frame-only causal
isolation。

这与 ML-017a independent review 及 ML-016u 的 gate 边界一致；`1166/181` 是
object compile matrix 结果，不是完整 archive/full link/runtime 结果。

### 5. 历史审计记录保持不变

ML-017b task/report 都声明不修改 ML-017a 原 task/report、tracker 或既有证据。
本次审阅没有改写 ML-017a independent review，也没有修改 ML-017a 原 report；本文件
是唯一新增的 independent-review 文件。

## 非阻塞 finding

### NB-1：ML-016u 详细 worker review 仍有已知 stale transition 表

ML-016u 更正复审已指出，`code-agent/docs/reviews/ML-016u-post-i1-musl-object-matrix-20260721.md`
的详细 worker review 仍保留把 `1163/184` 的三个对象迁移写成 ML-016s transition
的旧表述；根目录 ML-016u canonical index 与更正复审已明确正确的 ML-016u
aggregate baseline 是 `1166/181`，且相对 ML-016s 只有 `puts.o` fixed。

ML-017b 没有复制这一 stale transition，也正确使用了 ML-016u aggregate identity，
所以该问题不阻塞本次 scope correction。为保持历史审计记录，本轮不修改该旧文件；
后续引用 ML-016u transition 时应继续以更正后的 canonical index/review 为准。

## 后续要求

若要恢复 frame-only causal claim，必须在 `be99` parent 上独立构建同一工具，使用同一
musl source/configuration、同一受控方法和完整 1347-object matrix，并保留 parent 与
d3bd 两端的 tool/source provenance 及逐对象 regression、migration、failure-cluster
比较。本轮没有执行该重型实验。

**最终判定：Accepted-with-findings；阻塞 finding：0；非阻塞 finding：1。**
