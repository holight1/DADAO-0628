# ML-016l：i1 sign_extend_inreg 最小复现

**日期**：2026-07-21

**状态**：Audit-accepted-with-findings（ML-016 新 30-task run：12/30）

## 背景

ML-016g 将 `puts.o` 单独归为 `Cannot select: sign_extend_inreg from i1`。需要区分
bool return、i1→i8/i32/i64 扩展、有符号/无符号 cast、branch/select、load/store
及 O0/O3 的最小触发条件，避免把单例错误归入 f64/libcall 或 tail-call。

## 目标与 ownership

worker 只做 `/tmp` 诊断：

1. 生成 C/LLVM IR probes 覆盖 `i1` sign/zero extend 到各整数宽度、bool return/use、
   branch/select、volatile store/load 以及 i8/i32 对照，按 O0/O3 保存 clang/llc rc、
   stderr、argv、IR/asm。
2. 对真实 `puts.o` source/IR 做只读对照，确认其失败节点是否与最小 probe 相交；至少
   保存一个成功对照和一个可解释的失败边界。
3. 给出后续 backend legalize/CodeGen regression 边界，不修改 LLVM。

## 约束

- 只写本 task 完成区和 `docs/reviews/ML-016l-i1-sign-extend-minimal-repro-20260721.md`；
  probe/日志/脚本均放 `/tmp/ml-016l-i1-sign-extend-minimal-repro-20260721/`。
- 不修改 LLVM、musl、主 build/archive、QEMU/gem5、contracts、vectors、issues、wiki
  或 ML-014a。
- 不访问或引用 `~/toolchain`、`~/knowledge-graph`；不使用 `|| true`。
- 不把 frontend-only、单个 llc 成功或 asm 生成当作完整 libc/runtime 验收。

## 完成区

（由 worker 填写；完成后由不同 subagent 独立 review）

### worker 交付（2026-07-21）

状态：诊断完成，待独立 review；不预置 Accepted。

本轮只在 [`/tmp/ml-016l-i1-sign-extend-minimal-repro-20260721/`](/tmp/ml-016l-i1-sign-extend-minimal-repro-20260721/) 生成 probes、脚本和原始日志；未修改 LLVM/TableGen、musl、主 build/archive、QEMU/gem5、contracts、vectors、issues、wiki 或 ML-014a，也未访问受保护目录。仓库内只写本完成区和指定 review 文档。

证据包含 C/LLVM IR probes 的原始 argv、rc、stdout、stderr、frontend IR、成功 asm，以及失败调用的空/部分 asm 输出。主 C 矩阵为 12 个 probe × O0/O3 × frontend/clang/llc：frontend 24/24 成功；clang 20/24 成功、4 条 rc=1；llc 20/24 成功、4 条 rc=134。唯一失败的 C 形状是 `bool_neg` 与 `bool_select_neg`，均在 O0/O3 失败并报告 `Cannot select: ... sign_extend_inreg ... ValueType:ch:i1`；`bool_return`、branch、select、volatile i1 load/store、i8/i32 signed/unsigned 对照均成功。

显式单函数 IR 矩阵为 18 个 probe × O0/O3 × clang/llc，共 72 条记录。`sext i1 -> i8/i32/i64` 与 `zext i1; sub 0` 在两个优化级别均失败；clang rc=1、llc rc=134，原始节点均为 `sign_extend_inreg` from `i1`。`zext i1 -> i8/i32/i64`、`bool_return`、branch/select、volatile i1 store/load，以及 `sext/zext i8 -> i32/i64`、`sext/zext i32 -> i64` 全部 O0/O3 双成功。逐项结果在 [`results/ir-singles-summary.tsv`](/tmp/ml-016l-i1-sign-extend-minimal-repro-20260721/results/ir-singles-summary.tsv)，输入 IR 在 [`probes/ir/singles/`](/tmp/ml-016l-i1-sign-extend-minimal-repro-20260721/probes/ir/singles/)。

对真实 `puts.o` source/IR 做了只读对照：源快照为 [`probes/puts/puts.c.readonly-snapshot`](/tmp/ml-016l-i1-sign-extend-minimal-repro-20260721/probes/puts/puts.c.readonly-snapshot)，frontend O0/O3 均 rc=0；clang source backend O0/O3 均 rc=1，llc O0/O3 均 rc=134，逐条 argv/rc/stderr 在 [`results/puts-summary.tsv`](/tmp/ml-016l-i1-sign-extend-minimal-repro-20260721/results/puts-summary.tsv)。O0 IR 的 `zext i1` 后 `sub 0` 与 O3 IR 的直接 `sext i1` 都与最小失败形状相交；真实 O0 `-c` 诊断的 wrapper rc=1、frontend 报告 exit code 70，原始 stderr 保留在 `logs/puts_object/`。这确认 `puts.o` 是 ML-016g 中该签名的单例边界，不证明其他失败簇或所有 i1 ABI 形状。

后续 backend/regression 边界：分别覆盖 `SIGN_EXTEND`/combiner 产生的 `SIGN_EXTEND_INREG` 从 i1 到 i8/i32/i64，以及 O0 的 `zext i1`+整数减法和 O3 的直接 `sext i1`；保留 zext、bool return、branch/select、volatile load/store、i8/i32 对照作为成功回归。不得将该单例与 f64/libcall、tail-call、RB31、dynamic_stackalloc 或完整 libc/runtime 验收合并。本轮未执行 link、archive、runtime 或 QEMU/gem5 验收。

独立 reviewer Sagan the 2nd 的结论为 **Accepted-with-findings**，见
`docs/reviews/ML-016l-independent-review-20260721.md`。review 修正了一个计数表述：
`sext i1 -> i8/i32/i64` 是 12/12 条 raw records（6 个 shape×opt 组合）失败，不是
4 组；技术边界不变。
