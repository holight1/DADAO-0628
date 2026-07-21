# ML-016l：i1 sign_extend_inreg 最小复现 review

## Review scope

本 review 针对 `/tmp/ml-016l-i1-sign-extend-minimal-repro-20260721/` 的 worker 证据，重点核对 O0/O3、C/IR、sign/zero extend、branch/select、volatile、i8/i32 对照，以及真实 `puts.c` 的 source/IR 交集。没有把单个 CodeGen probe 当作 libc、archive 或 runtime 验收。

## Evidence result

主 C 矩阵有 12 个 probe、两个优化级别和三个阶段。frontend 为 24/24 rc=0；clang backend 为 20/24 rc=0、4 条 rc=1；llc 为 20/24 rc=0、4 条 rc=134。失败只出现在 `bool_neg`、`bool_select_neg` 的 O0/O3，原始 stderr 都是 `Cannot select: ... sign_extend_inreg ... ValueType:ch:i1`。

逐函数 IR 矩阵有 18 个 probe、O0/O3 和 clang/llc 两个阶段，共 72 条记录。结果边界如下：

| 形状 | O0/O3 clang + llc | 结论 |
|---|---:|---|
| `sext i1 -> i8/i32/i64` | 4 组均失败 | i1 sign extend 的直接最小失败边界 |
| `zext i1 -> i8/i32/i64` | 6/6 成功 | zero extend 不是该失败触发器 |
| `zext i1; sub 0` | 两级别失败 | 会被 DAG 归约为 `sign_extend_inreg` |
| `bool_return`、branch、select | 全部成功 | i1 返回/控制流不是单独触发器 |
| volatile i1 load/store | 全部成功 | volatile memory path 不是单独触发器 |
| `sext/zext i8`、`sext/zext i32` 对照 | 全部成功 | 边界特定于 i1，而非一般整数扩展 |

原始逐条结果是 [`ir-singles-summary.tsv`](/tmp/ml-016l-i1-sign-extend-minimal-repro-20260721/results/ir-singles-summary.tsv)；失败 stderr 在 `logs/clang/ir-single.*` 与 `logs/llc/ir-single.*`，成功 asm 在 `probes/asm/`。

## puts intersection and singleton boundary

真实 source/IR 对照保存在 [`probes/puts/`](/tmp/ml-016l-i1-sign-extend-minimal-repro-20260721/probes/puts/)，结果表为 [`puts-summary.tsv`](/tmp/ml-016l-i1-sign-extend-minimal-repro-20260721/results/puts-summary.tsv)。frontend O0/O3 均成功；clang source backend O0/O3 均 rc=1；llc O0/O3 均 rc=134。O0 IR 中可见 `zext i1` 后 `sub 0`，O3 IR 中可见直接 `sext i1 -> i32`；两个版本的 backend stderr 都落在 `i64 = sign_extend_inreg ..., ValueType:ch:i1`。

因此，`puts.o` 与最小 probe 的交集是 i1 sign extension lowering，而不是 branch、select、volatile 或普通 i8/i32 extension。它是 ML-016g 该错误签名的单个 object 边界；结果不能外推到其他 failure cluster、全部 libc objects、任何 ABI 组合或 runtime。

## Follow-up boundary

后续修复/回归应最小化为：

- 为 i1 到 i8/i32/i64 的 sign extension，以及 DAG combiner 产生的 `SIGN_EXTEND_INREG`，建立独立 CodeGen regression；
- 固定保留 O0 `zext i1` + `sub 0` 与 O3 直接 `sext i1` 两个 source-shaped cases；
- 保留 zext、bool return、branch/select、volatile i1 load/store、i8/i32 sign/zero extend 成功对照；
- 修复后再回到 `puts.o` 单对象重编译；不能以 frontend IR、单个 llc 成功、asm 生成或 link 成功替代完整 libc/runtime 验收。

本 worker 交付未修改实现或规范文件，也未执行 link、archive、runtime 或 QEMU/gem5 验收。
