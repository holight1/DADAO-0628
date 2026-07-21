# ML-016k 独立 review

日期：2026-07-21  
范围：只读检查任务说明、既有 review，以及 `/tmp/ml-016k-tail-call-return-assertion-repro-20260721/` 的 summary、explicit-tail-summary、explicit-cases-summary、原始 argv/rc/stderr、C IR/asm 和 explicit IR 对照。本 review 未修改 LLVM、musl、build/archive、测试或规范。

## 结论

**Accepted-with-findings**

该交付已经闭合了一个可重复、边界清楚的 DADAO SelectionDAG tail-call return assertion reproducer；finding 只涉及 explicit IR 结果的表述范围，不阻塞本 task 的 CodeGen 诊断结论。

## 独立证据核对

主矩阵 `summary.tsv` 有 288 条 stage 记录：frontend 96/96 为 `rc=0`；clang 与 llc 各 96 条，其中各有 6 条非零。非零集合精确为：O3、sibling enabled、direct/indirect × integer/pointer/f64 × plain return。clang 为 `rc=1`，llc 为 `rc=134`；失败 raw stderr 的首诊断均为：

```text
LowerCall emitted a return value for a tail call!
```

抽查的 C O3 IR 与 no-sibling IR 分别是 `tail call` 与普通 `call`。integer、pointer、f64 的 plain failure 与 void、volatile、use-after-call、O0、`-fno-optimize-sibling-calls` 的成功对照相互吻合。volatile/use-after-call 的成功项确实有 `rc=0` 和生成的 asm，不能仅凭 IR 中仍出现文字 `tail call` 判定为同一最终 lowering 形状。

`explicit-cases-summary.tsv` 的 32 条逐 probe 记录也一致：direct/indirect void 在 O0/O3 的 clang/llc 均为 `rc=0`；direct/indirect integer/pointer/f64 的 O0/O3 均为 clang `rc=1`、llc `rc=134`，raw stderr 为同一 assertion。`explicit-tail-summary.tsv` 只有 4 条 aggregate 记录（两种优化级别 × 两个 stage），两种优化级别均失败；逐函数归因应以 `explicit-cases-summary.tsv` 为准，而不能由 aggregate summary 单独推出。

## 与 RB31 verifier 的分离

ML-016k 自身的相关 stderr 没有 `RB31`、`RD31`、undefined physical register 或 MachineVerifier 诊断。ML-016j 的代表性 raw machine dump 则明确有 `CALL_IIII` 的 `implicit-def dead $rd31`，随后 `COPY $rb31`，并报告 `Using an undefined physical register`。此外，ML-016k 的 pointer plain 在 no-sibling O3 能以 `call ext_ptr` / `ret rd0` 生成 asm；sibling enabled 的 pointer case 是更早的 tail-call assertion。因此两者是不同 reproducer，不能把本 assertion 写成 RB31 根因。

## 与 f64 generated-libcall 的分离

ML-016k 的 f64 probe 只调用外部 `ext_f64`，没有 fadd、转换或其他需要 generated libcall 的 DAG 运算。其失败项 stderr 是 tail-call assertion；成功的 no-sibling、volatile、use-after-call f64 case 均能生成 asm。ML-016h 的 `f64_add` 对照则报告 `LLVM ERROR: unsupported library call operation`，stack 位于 `TargetLowering::makeLibCall` / 类型合法化路径。ML-016k 证据支持将这两类问题分开，且 f64 类型本身不是 libcall 证据。

## Finding：explicit IR 推论需收窄

既有 review 中“最小必要条件可表述为 call 被 SelectionDAG 作为 tail call lowering，且该 call 有返回值需要放入 `InVals`”作为当前 assertion 的实现语义是合理的；断言文本本身也包含 `CLI.IsTailCall` 与 `InVals.empty()` 条件。但 explicit IR 只覆盖当前 build、当前 target、direct/indirect 以及四种返回类型，且 `explicit-tail-summary.tsv` 是 aggregate 结果。因此它证明的是：**在本次 target/build 与这些所测签名中，显式 `tail` 的 non-void call 会触发该 assertion，而 void 是成功对照**；它没有证明所有 ABI/返回形状的普遍最小充分条件，也没有覆盖 `musttail`、aggregate 或其他调用约束。

后续 regression 可以保留这些 explicit non-void/void probes，但实现或 issue 描述应使用上述受限措辞；不要把 explicit IR 结果扩大为完整 tail-call ABI 验收。主 C 矩阵同样只闭合 frontend/backend stage，不代表 link、libc/archive、runtime 或 QEMU/gem5 通过。

## 建议的 regression 边界

- 保留 non-void direct/indirect tail-call assertion，至少覆盖 integer、pointer、f64；void 作为成功对照。
- 保留 C O3 plain-return failure，以及 volatile、use-after-call、no-sibling 的成功对照。
- RB31 verifier 与 f64 generated-libcall 各自维护独立的 reproducer、诊断和修复链路。

证据入口：[`summary.tsv`](/tmp/ml-016k-tail-call-return-assertion-repro-20260721/results/summary.tsv)、[`explicit-tail-summary.tsv`](/tmp/ml-016k-tail-call-return-assertion-repro-20260721/results/explicit-tail-summary.tsv)、[`explicit-cases-summary.tsv`](/tmp/ml-016k-tail-call-return-assertion-repro-20260721/results/explicit-cases-summary.tsv)。
