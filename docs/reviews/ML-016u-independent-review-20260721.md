# ML-016u 独立 Review

日期：2026-07-21（Asia/Shanghai）  
范围：只审阅任务说明、既有 review 与 `/tmp/ml-016u-post-i1-musl-object-matrix-20260721/` 证据；未访问或引用 `~/toolchain`、`~/knowledge-graph`，未修改 LLVM、musl、build、archive、测试或规范。

## 结论

**Rejected**。

Fresh matrix 的编译账本、artifact provenance、stdio 结果和 archive/link/runtime 边界基本成立；但交付物把一个来自 ML-016f 的 184-failure baseline 当成 ML-016s，并据此错误宣称相对 ML-016s 正好修复 `puts/explicit_bzero/__unmapself` 三个对象。该比较是本任务的核心验收项，不能接受为 ML-016u 的独立结论。

## 独立核对通过项

- `results/targets.all1347.txt` 有 1347 个对象；`results/object-results.tsv` 有 1347 个唯一 output，`rc=0` 为 1166、`rc=1` 为 181，故 **1166+181=1347**。
- 实际 fresh `.o` 数为 1166，与 `results/final-artifact-inventory.txt` 一致。逐一对成功对象重新计算 artifact SHA-256、size、mtime：hash mismatch=0、size mismatch=0、mtime mismatch=0、missing=0。成功对象 `artifact_fresh` 非 yes=0，失败对象残留 artifact=0，重复 output=0；1347 条 record/stderr 路径均存在，source/argv hash 字段无空值。
- `logs/metadata/tool-hashes.before.tsv` 与 `tool-hashes.after.tsv` 完全相同；clang mtime/hash 为 `1784630810` / `d1c6e0026741e45f7ae98f13d4057a6838f9ef049d6b9d110152a2f90ce94bdc`，llc mtime/hash 为 `1784630734` / `ac7a71404061254b68f7d43cd343f4b121952af77b0ef7cb2428a15231ad2f9c`；llvm-ar/llvm-ranlib 两行也未变化。configure 为 `rc=0`，matrix make 保留原始 `rc=2`。
- fresh failure clusters 只有四簇：`unsupported library call operation` 157、`machine verifier: undefined physical register` 16、`Cannot select: dynamic_stackalloc` 7、`SelectionDAG assertion: illegal result number` 1，合计 181；未分类/新簇为 0。
- `special-objects.tsv` 的三个对象均为 fresh success：`puts.o` hash `7aab018823cae63b10ab7154e73f7d7f053e627e0e5c19420acbc691a40dab23`，`explicit_bzero.o` hash `c69684202e57dfd30c6ecc416c826449824e4213b09121a161d6133203137f24`，`__unmapself.o` hash `07f8f9c4f2ad34f2f57635c2ac468a295a130a57e84b78ecdad53ca05e32efdb`。
- stdio ledger 为 **114/116**；唯一失败为 `obj/src/stdio/vfprintf.o` 和 `obj/src/stdio/vfscanf.o`，二者均为 `unsupported library call operation`。

## 基线核对与 finding

直接读取 `/tmp/ml-016s-post-fix-musl-object-matrix-20260721/results/object-results.tsv` 得到 ML-016s 为 1165 success / 182 failure。三个候选对象的真实状态是：

| object | ML-016s | ML-016u | 相对 ML-016s transition |
|---|---:|---:|---|
| `obj/src/stdio/puts.o` | failure | success | fixed |
| `obj/src/string/explicit_bzero.o` | success | success | unchanged |
| `obj/src/thread/__unmapself.o` | success | success | unchanged |

因此对 ML-016s 的逐对象比较实际为：1165 个原成功保持成功、181 个原失败保持失败、**1 个 fixed（puts）**、0 regressions；即 1166/181，而不是“三个 fixed”。

ML-016u 临时目录中的 `baseline/object-results.success.tsv` 与 `baseline/object-results.failed.tsv` 则是 1163/184；其 record 路径明确指向 `/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/`。这套 184-failure baseline 的 `old-7-cluster-summary.tsv` 与 `old-7-cluster-comparison.tsv` 内部一致，确实得到三个迁移对象：`puts.o`、`explicit_bzero.o`、`__unmapself.o`，但它不能被标注为 ML-016s comparison。既有 ML-016u task 完成区和 dated review 同时使用“ML-016s 1165/182”文字与“184 old failures / 3 fixed”表格，构成基线 provenance 与结论不一致的高严重度 finding。

另有路径可追溯性 finding：用户指定的 `/home/holight/DADAO-0628/docs/reviews/ML-016u-post-i1-musl-object-matrix-20260721.md` 不存在；实际既有 review 位于 `/home/holight/DADAO-0628/code-agent/docs/reviews/ML-016u-post-i1-musl-object-matrix-20260721.md`。

## Archive / link / runtime gate

此边界判断本身正确：临时目录没有 `.a` 或 `libc.a`，没有执行 archive/link/runtime 验收；既有 review 明确只建议进入范围受限的目标化 archive/link probe，并明确不宣称完整 libc archive、完整 link 或 runtime 通过。181 个 backend failures 仍阻止完整 gate。

在修正 ML-016s 基线引用并重新发布 transition 结论前，本次交付不应被标记为 accepted。

