# ML-016u post-i1 musl object matrix review

日期：2026-07-21

## 结论

本轮 fresh clean matrix 的对象账本与 provenance 完整，可作为 ML-016u 的 worker evidence 交付；结果支持进入受控、目标化 archive/link gate，不支持完整 libc archive、完整 link 或 runtime gate。

## 执行与固定输入

工作目录为 [`/tmp/ml-016u-post-i1-musl-object-matrix-20260721/`](/tmp/ml-016u-post-i1-musl-object-matrix-20260721/)。build 在 configure 前为空，configure 后仍无 object；source snapshot commit 为 `4741d4d1105849adf551a7998503866ed4f8b961`。

工具固定为 LLVM 22.1.8、revision `40bc313742b00848d341e77e1a38441211971729`：

- clang SHA-256：`d1c6e0026741e45f7ae98f13d4057a6838f9ef049d6b9d110152a2f90ce94bdc`
- llc SHA-256：`ac7a71404061254b68f7d43cd343f4b121952af77b0ef7cb2428a15231ad2f9c`

before/after tool hash 比对通过。configure `rc=0`；唯一 1347-object make 阶段保留原始 `rc=2`，并继续收集每个 object 的真实结果。

## 1347 结果

1347/1347 个唯一对象都有逐对象 record。结果为 1166 成功、181 失败；1166 个成功对象均有新生成 artifact 且 `artifact_fresh=yes`。逐对象 `rc`、stderr 路径/hash、raw argv record/hash、source hash/mtime、artifact hash/mtime 见 [`results/object-results.tsv`](/tmp/ml-016u-post-i1-musl-object-matrix-20260721/results/object-results.tsv)。独立 provenance 校验结果：

- record 缺失：0；stderr 缺失：0；argv hash 缺失/非法：0；source hash 缺失：0。
- 成功对象缺 artifact：0；成功对象非 fresh：0；失败对象残留 artifact：0。
- unique output=1347，duplicate output=0，unclassified failure=0。
- 未生成 isolated `libc.a`，未打包 archive。

fresh failure clusters 为：

| cluster | count |
|---|---:|
| unsupported library call operation | 157 |
| machine verifier: undefined physical register | 16 |
| Cannot select: dynamic_stackalloc | 7 |
| SelectionDAG assertion: illegal result number | 1 |

## 相对 ML-016s 的迁移

ML-016s 基线为 1165 成功 / 182 失败。本轮相对该基线为 1165 个旧成功保持成功、181 个旧失败保持失败、**1 个旧失败转成功**、0 个旧成功回归、0 个新失败簇。旧簇逐对象比较见 [`results/old-7-cluster-comparison.tsv`](/tmp/ml-016u-post-i1-musl-object-matrix-20260721/results/old-7-cluster-comparison.tsv)，汇总如下：

| 旧簇 | 旧数 | 转成功 | 仍在同簇 |
|---|---:|---:|---:|
| unsupported library call operation | 157 | 0 | 157 |
| machine verifier: undefined physical register | 16 | 0 | 16 |
| Cannot select: dynamic_stackalloc | 7 | 0 | 7 |
| Cannot select: sign_extend_inreg from i1 | 1 | 1 | 0 |
| SelectionDAG assertion: illegal result number | 1 | 0 | 1 |

相对 ML-016s 唯一迁移对象为：

- `obj/src/stdio/puts.o`：`rc=1` → `rc=0`，fresh artifact；这是 i1 `SIGN_EXTEND_INREG` 修复后的目标迁移。

为避免与前一基线混淆：相对 ML-016f 的原始 1163/184 baseline，历史上确有
`puts.o`、`explicit_bzero.o`、`__unmapself.o` 三个对象转成功；其中后两个在 ML-016s
已经成功，所以不属于本轮相对 ML-016s 的 transition。

## stdio

stdio 共 116 项，114 成功、2 失败；完整表见 [`results/stdio-object-results.tsv`](/tmp/ml-016u-post-i1-musl-object-matrix-20260721/results/stdio-object-results.tsv)。`puts.o` 已迁移为成功；剩余 `vfprintf.o`、`vfscanf.o` 均为 `unsupported library call operation`。

## Gate 判定

结论为：**受控、目标化 archive/link gate：可进入**，但仅限已成功对象和明确的 link probe，且本轮没有执行 archive/link。**完整 archive/link/runtime gate：不可进入**；181 个 backend failures 仍在四个失败簇中，不能以本矩阵宣称完整 libc 或 runtime 已通过。下一步应由 gate owner 明确目标对象范围后再进行受控验证。

原始阶段日志、逐对象记录、迁移与汇总、stdio/special-object 结果以及 evidence hash 清单均保留在 [`/tmp/ml-016u-post-i1-musl-object-matrix-20260721/`](/tmp/ml-016u-post-i1-musl-object-matrix-20260721/)。
