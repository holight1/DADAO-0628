# ML-016k tail-call return assertion 最小复现 review

日期：2026-07-21  
范围：只读核验 worker 在 `/tmp/ml-016k-tail-call-return-assertion-repro-20260721/` 的
诊断产物；本 review 不修改 LLVM/TableGen、musl、build/archive、QEMU/gem5 或其他仓库
边界。

## 结果

本轮闭合了一个可重复的 SelectionDAG call-lowering assertion：

```text
LowerCall emitted a return value for a tail call!
```

主 C probe 是一个按 `-DPROBE` 单独编译的模板，覆盖 24 个形状：

| 返回类型 | direct/indirect 各自覆盖 |
|---|---|
| void | plain、volatile 后续 store、use-after-call |
| integer | plain、volatile 后续 store、use-after-call |
| pointer | plain、volatile 后续 store、use-after-call |
| f64 | plain、volatile 后续 store、use-after-call |

每个 probe 都运行 O0/O3、sibling enabled/disabled，并分别保存 frontend IR、成功项的
clang/llc asm，以及每条命令的原始 `argv`、`rc`、`stdout`、`stderr`；失败项保留其
预期 output 路径和完整失败日志。总记录为 24 × 2 × 2 × 3 = 288，见
[`results/summary.tsv`](/tmp/ml-016k-tail-call-return-assertion-repro-20260721/results/summary.tsv)。

结果是：frontend 96/96 成功；clang 和 llc 的 6 条失败集合完全相同，即 O3 sibling
enabled 下的 `direct/indirect × integer/pointer/f64 × plain`。clang 失败 rc=1，llc
abort rc=134；全部 void、volatile、use-after-call、O0 和 `-fno-optimize-sibling-calls`
组合成功。失败样本的原始 stderr 示例：
[`clang direct_int O3 enabled stderr`](/tmp/ml-016k-tail-call-return-assertion-repro-20260721/logs/clang/direct_int_plain.O3.enabled.stderr)
和 [`llc direct_int O3 enabled stderr`](/tmp/ml-016k-tail-call-return-assertion-repro-20260721/logs/llc/direct_int_plain.O3.enabled.stderr)。

## 显式 tail-call 标记

为避免把 C frontend 的 tail-call 推断误当作输入条件，另有 8 个显式 LLVM IR probe：
direct/indirect × void/integer/pointer/f64。逐项 O0/O3 运行 clang 与 llc 后，void 的
8 条记录全部为 rc=0；integer/pointer/f64 的 24 条记录全部失败（clang rc=1，llc
rc=134），stderr 为同一 assertion。权威汇总是
[`results/explicit-cases-summary.tsv`](/tmp/ml-016k-tail-call-return-assertion-repro-20260721/results/explicit-cases-summary.tsv)，
例如 [`tail_direct_int.ll`](/tmp/ml-016k-tail-call-return-assertion-repro-20260721/probes/ir/tail_direct_int.ll)。

这说明最小必要条件可表述为：call 被 SelectionDAG 作为 tail call lowering，且该 call
有返回值需要放入 `InVals`；返回值不必是 pointer 或 f64，也不要求任何 f64 arithmetic。
void tail call 的返回值集合为空，因而是成功对照。

需要保留一个实现层细节：C O3 的 volatile/use-after-call IR 中可能仍出现文字上的
`tail call`，但这些 call 不再构成触发本 assertion 的最终 tail-return lowering；它们的
backend 结果为 rc=0。故 regression 不应只做文本 grep，而应检查 clang/llc rc 和 stderr。
例如 [`direct_int_volatile` IR](/tmp/ml-016k-tail-call-return-assertion-repro-20260721/probes/ir/c/direct_int_volatile.O3.enabled.ll)
对应的成功 [`asm`](/tmp/ml-016k-tail-call-return-assertion-repro-20260721/probes/asm/clang/c/direct_int_volatile.O3.enabled.s)。

## 与 RB31 verifier 的分界

本轮自己的所有日志没有 `$rb31`、`$rd31`、`undefined physical register` 或
MachineVerifier 诊断。ML-016j 的 representative 是不同边界：O3、no-sibling 的 raw
machine dump 中，`CALL_IIII` 带 `implicit-def dead $rd31`，紧接着 call-result 路径读取
`$rb31`；该事实保留在 ML-016j 的
[`posix_memalign raw stderr`](/tmp/ml-016j-rb31-pointer-return-repro-20260721/logs/representatives/clang.posix_memalign.O3.stderr)。
而本轮最小 direct/indirect pointer-return 在 no-sibling O0/O3 均通过，并在 sibling
enabled 时改为更早的 tail-call assertion。因此不能把本 assertion 写成 RB31 根因，或
用它替代 RB31 的 verifier reproducer。

## 与 f64 generated-libcall 的分界

本轮 f64 probe 只做外部 `ext_f64` call、volatile store 或第二个观察 call；未构造 fadd、
转换或其他需要软浮点 generated-libcall 的 DAG operation。f64 plain 在默认 O3 的失败
stderr 是 tail-call assertion；同一 f64 call 在 O3 no-sibling、volatile、use-after-call
均可生成 asm，例如 [`direct_f64_volatile asm`](/tmp/ml-016k-tail-call-return-assertion-repro-20260721/probes/asm/llc/c/direct_f64_volatile.O3.enabled.s)。

ML-016h 的独立 probe 对照则明确报告 `unsupported library call operation`，例如
[`f64_add O0 llc stderr`](/tmp/ml-016h-f64-libcall-minimal-repro-20260721/results/f64_add.O0.llc.stderr)。
因此 f64 类型本身不是 libcall 证据；本轮的 f64 failure 应归到 tail-call assertion，
不能与 soft-float/generated-libcall lowering 合并。

## 后续 CodeGen regression 边界与限制

- 应保留 non-void direct/indirect explicit-tail IR 在 O0/O3 的 assertion regression，
  并以 void、no-sibling、volatile、use-after-call 作为成功对照。
- 应另外保留 C O3 plain-return 的 integer/pointer/f64 三类复现；这三类共同证明
  pointer 与 f64 都不是 assertion 的必要条件。
- RB31/RD31 verifier 和 f64 generated-libcall 应分别建测试与修复链路；它们不能由本轮
  的 rc、单个 asm 或 assertion 文本替代。
- 本轮没有链接、runtime、libc/archive 或 QEMU/gem5 验收；成功仅表示该独立 CodeGen
  probe 的 frontend/backend stage 结果。

所有原始证据入口：
[`/tmp/ml-016k-tail-call-return-assertion-repro-20260721/`](/tmp/ml-016k-tail-call-return-assertion-repro-20260721/)。
