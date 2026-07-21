# ML-016l 独立 review（2026-07-21）

## 结论

**Accepted-with-findings**

worker 证据足以支持“DADAO backend 的失败边界是 i1 sign extension lowering / `SIGN_EXTEND_INREG`，不是所有 sign extension，也不是已证明的 ABI 根因”。现有 review 的技术结论可接受，但结果表有一处计数错误，需更正后再作为精确审计记录使用。

## 审查范围与方法

我独立阅读了任务说明、已有 review，并抽查了 `/tmp/ml-016l-i1-sign-extend-minimal-repro-20260721/` 中的原始 `argv`、`rc`、`stderr`、IR 和 asm。未修改 LLVM、musl、build/archive、测试或规范；未访问或引用 `~/toolchain`、`~/knowledge-graph`。

## 原始证据核对

| 形状 | O0/O3 原始结果 | 独立判断 |
|---|---|---|
| `sext i1 -> i8/i32/i64` | clang 全部 rc=1；llc 全部 rc=134；stderr 为 `Cannot select: ... sign_extend_inreg ... ValueType:ch:i1` | 直接失败边界成立 |
| `zext i1 -> i8/i32/i64` | clang/llc 在 O0、O3 全部 rc=0；asm 有输出 | zero extension 不是该触发器 |
| `zext i1; sub 0` / `bool_neg_use` | clang rc=1、llc rc=134，O0/O3 均同样失败 | DAG 归约可重现同一失败 |
| branch/select 使用 i1 | clang/llc 在 O0、O3 全部 rc=0；asm 分别出现 branch/`csz` | branch/select 本身不是触发器 |
| volatile i1 load/store | clang/llc 在 O0、O3 全部 rc=0；asm 有 `ldo`/`stb` | volatile memory path 本身不是触发器 |
| i8/i32 `sext`/`zext` 对照 | clang/llc 在 O0、O3 全部 rc=0；asm 有 `exts` 或 mask | 不能泛化为一般整数 sign extension |

代表性原始文件包括：[`ir-singles-summary.tsv`](/tmp/ml-016l-i1-sign-extend-minimal-repro-20260721/results/ir-singles-summary.tsv)、[`i1_width_matrix.ll`](/tmp/ml-016l-i1-sign-extend-minimal-repro-20260721/probes/ir/i1_width_matrix.ll)、[`sext_i1_i8.ll`](/tmp/ml-016l-i1-sign-extend-minimal-repro-20260721/probes/ir/singles/sext_i1_i8.ll)、[`sext_i1_i8` clang O0 stderr](/tmp/ml-016l-i1-sign-extend-minimal-repro-20260721/logs/clang/ir-single.sext_i1_i8.O0.stderr)、[`sext_i1_i8` llc O3 stderr](/tmp/ml-016l-i1-sign-extend-minimal-repro-20260721/logs/llc/ir-single.sext_i1_i8.O3.stderr)、[`zext_i1_i8` clang O0 asm](/tmp/ml-016l-i1-sign-extend-minimal-repro-20260721/probes/asm/clang/ir.zext_i1_i8.O0.s)、[`branch_i1` llc O3 asm](/tmp/ml-016l-i1-sign-extend-minimal-repro-20260721/probes/asm/llc/ir.branch_i1.O3.s) 和 [`sext_i32_i64` llc O3 asm](/tmp/ml-016l-i1-sign-extend-minimal-repro-20260721/probes/asm/llc/ir.sext_i32_i64.O3.s)。这些原始文件中的 argv 同时固定了 target、优化级别、输入 IR 和输出路径。

主 C probe 的失败也只落在 `bool_neg`、`bool_select_neg` 的 O0/O3；`bool_return`、`bool_to_i64`、branch/select、volatile load/store 和 i8/i32 对照均成功。这里的 O0 C IR 是显式 `zext i1` 后整数 `sub`，O3 C IR 是直接 `sext i1`，所以 C→IR→backend 的形状交集与 IR singleton 结果一致。

## `puts.o` O0/O3 对照

[`puts-summary.tsv`](/tmp/ml-016l-i1-sign-extend-minimal-repro-20260721/results/puts-summary.tsv) 与原始日志显示：

- frontend O0/O3 均 rc=0；
- clang source backend O0/O3 均 rc=1；
- llc O0/O3 均 rc=134；
- object compile O0/O3 均 rc=1。

[`puts.O0.ll`](/tmp/ml-016l-i1-sign-extend-minimal-repro-20260721/probes/puts/puts.O0.ll) 的 `%lor.ext = zext i1` 后接 `sub i32 0`；[`puts.O3.ll`](/tmp/ml-016l-i1-sign-extend-minimal-repro-20260721/probes/puts/puts.O3.ll) 的 `%lor.ext.neg = sext i1 ... to i32`。对应的 [`puts_clang` O0 stderr](/tmp/ml-016l-i1-sign-extend-minimal-repro-20260721/logs/puts_clang/puts.O0.stderr)、[`puts_clang` O3 stderr](/tmp/ml-016l-i1-sign-extend-minimal-repro-20260721/logs/puts_clang/puts.O3.stderr)、[`puts_llc` O0 stderr](/tmp/ml-016l-i1-sign-extend-minimal-repro-20260721/logs/puts_llc/puts.O0.stderr) 和 [`puts_llc` O3 stderr](/tmp/ml-016l-i1-sign-extend-minimal-repro-20260721/logs/puts_llc/puts.O3.stderr) 均落在 `sign_extend_inreg ... ValueType:ch:i1`。失败 backend 没有成功 asm；相关输出文件为空/未生成，这与 rc 非零一致。

`puts` 的函数接口仍是 `i32 (ptr)`，失败值是函数内部逻辑比较产生的 `i1`。stderr 中 DAG 节点显示的 `i64` 是 target lowering 的内部值宽度，不能据此推出 ABI 根因。再结合 `i1` 返回、branch/select、volatile path 和 zero extension 成功，以及 i8/i32 sign extension 成功，现有材料只支持 CodeGen selection 边界，不支持“所有 sign extension 失败”或“ABI 不匹配导致失败”的结论。

## Findings

1. **计数错误（低严重度，需修正文案）**：已有 review 的表格把 `sext i1 -> i8/i32/i64` 写成“4 组均失败”。原始 [`ir-singles-summary.tsv`](/tmp/ml-016l-i1-sign-extend-minimal-repro-20260721/results/ir-singles-summary.tsv) 中该形状是 3 个目标宽度 × 2 个优化级别 × 2 个 backend，共 **12/12 条失败记录**；若按 clang/llc 配对折算，则是 **6 个形状-优化组合**，不是 4。建议改为“12/12 raw records（6 个 shape×opt 组合）”。这不影响其“i1 特定失败边界”的实质结论。

## 后续边界

回归应保留 direct `sext i1` 到 i8/i32/i64、`zext i1`+整数减法、O3 direct `sext i1`，并保留 zext、bool return、branch/select、volatile load/store 和 i8/i32 sign/zero extend 成功对照。修复后应重新编译 `puts.o`；本证据不能替代 link、archive、runtime 或 QEMU/gem5 验收，也不能作为其他 failure cluster 或 ABI 组合的结论。

**最终 verdict：Accepted-with-findings。**
