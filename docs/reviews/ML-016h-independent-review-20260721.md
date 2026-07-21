# ML-016h 独立 review

日期：2026-07-21（Asia/Shanghai）

## 裁定

**Accepted-with-findings**

本 review 只核对任务说明、原 review 和
`/tmp/ml-016h-f64-libcall-minimal-repro-20260721/` 中的交付证据；未修改 LLVM、musl、
build/archive、测试或规范，也未访问或引用受禁止目录。

## 矩阵与证据核验

`results/summary.tsv` 有 34 行数据，正好覆盖 17 个 probe 的 O0/O3。逐行比对 summary
与对应 `.rc` 文件，34 行均一致；68 个矩阵 `.argv` 均指向同名输入和匹配的优化级别。
矩阵的独立计数为：

- 13 行 clang/llc 双成功：`0/0`；
- 18 行双失败：clang `1`、llc `-6`；
- 3 行 clang O3 独有失败：`1/0`，即 `libm_sin`、`libm_sin_bitcast`、
  `explicit_adddf3_call`。

因此原 review 和任务完成区中的 13/18/3 统计正确。双失败行的 clang/llc stderr 都含
`unsupported library call operation`，并落在 DADAO DAG instruction selection 的
`TargetLowering::makeLibCall`：

- [summary.tsv](/tmp/ml-016h-f64-libcall-minimal-repro-20260721/results/summary.tsv)
- [f64_add O0 clang stderr](/tmp/ml-016h-f64-libcall-minimal-repro-20260721/results/f64_add.O0.clang.stderr)
- [f64_add O0 llc stderr](/tmp/ml-016h-f64-libcall-minimal-repro-20260721/results/f64_add.O0.llc.stderr)
- [f64_add O0 clang argv](/tmp/ml-016h-f64-libcall-minimal-repro-20260721/results/f64_add.O0.clang.argv)

双成功行的 clang/llc stderr 均为空且两侧都有 asm；双失败行没有成功 asm；clang-only
行则只有 llc 有 asm。`llc -6` 与 stderr 中的 `LLVM ERROR`/abort 一致。O3 call 行的
clang 顶层 rc 是 `1`，stderr 内层诊断为 assertion 进程退出 `134`；这是记录层级差异，
不是统计冲突。

## f64、整数和指针对照

以下对照复核通过：

- `f64_identity`、`f64_const` 在 O0/O3 均为 `0/0`，分别覆盖 f64 传递和常量物化；
- `i64_add` 在 O0/O3 均为 `0/0`，说明纯整数 add 未触发该错误；
- `ptr_identity` 在 O0/O3 均为 `0/0`，说明纯指针传递未触发该错误；
- 单一 `fadd`/`fsub`/`fmul`/`fdiv`、f64↔i64、f64↔f32 以及
  `llvm.fmuladd.f64` 在 O0/O3 均为 `1/-6`。

这支持“若干 f64/f32 运算或转换进入未支持的 generated libcall/type legalization
路径”的高可信候选，但不能从 `makeLibCall` 的调用栈推出具体 RTLIB helper，也不能推出
所有失败对象共享一个 lowering 根因。

## call / tail-call 表述核验

O3 的 `libm_sin`、bitcast 变体和显式 `__adddf3` call 都是 clang `1`、llc `0`，stderr
包含：
`LowerCall emitted a return value for a tail call!`。显式 `-fno-optimize-sibling-calls`
变体仍为 rc `1`；只有加入 volatile store/load 的 IR 形状在 O3 clang/llc 都为 `0`。

所以原 review 将其列为独立的“call/tail-call lowering 候选”是可接受的，且没有把它写成
157 簇的已证实根因，也没有和 generic `makeLibCall` 错误合并。Finding 1：这里的
“tail-call”只能作为 assertion/现象标签；现有证据尚未证明 sibling-call 优化本身是
因果根因。bitcast 和 no-sibling 的负结果、volatile 形状的正结果，应在后续修复验证中
继续保持为独立回归边界。

## source-family 证据边界

`family-reps-summary.tsv` 的 18 行（9 个 representative、O0/O3）均为 frontend rc `0`
和 llc rc `-6`，对应 llc stderr 均含 generic libcall 错误。8 个顶层 family 的对象数
为 `127+22+1+2+2+1+1+1=157`；stdio 拆成 vfprintf/vfscanf 两个 representative
并不改变总数。`stdlib`/`vfscanf` 的 IR 可见 `fptrunc`，`legacy` 可见 `uitofp`+`fmul`，
`time` 可见 `sitofp`，`prng` 在 O0 可见 `fsub`；O3 可能将 `fsub x, 1.0` canonicalize
成 `fadd x, -1.0`。

- [family summary](/tmp/ml-016h-f64-libcall-minimal-repro-20260721/results/family-reps-summary.tsv)
- [stdlib O0 representative IR](/tmp/ml-016h-f64-libcall-minimal-repro-20260721/family-reps/stdlib.O0.ll)
- [stdio_vfscanf O0 representative IR](/tmp/ml-016h-f64-libcall-minimal-repro-20260721/family-reps/stdio_vfscanf.O0.ll)
- [family representative stderr](/tmp/ml-016h-f64-libcall-minimal-repro-20260721/family-reps/stdlib.O0.llc.stderr)

Finding 2：这些是 family-level candidate coverage，不是 157/157 的对象级根因闭合；原
review 已明确此限制，因此不构成拒绝理由。尤其 representative 的多个 operation、
外部 call/ABI 交互以及准确 DAG node/RTLIB 仍需逐对象定位。

## 结论

矩阵、rc/stderr/argv、双成功/双失败/O3 assertion 统计及 f64/整数/指针对照均核验通过。
原 review 对 soft-float/libcall 与 call/tail-call 的定位保持了“高可信候选”而非“已证实
根因”的边界；本次 findings 只要求后续继续区分 assertion 现象与真正 tail-call 因果，
并保留 representative 不等于逐对象证明的限制。
