# ML-016s：LLVM 修复后 musl object matrix 复验

**日期**：2026-07-21

**状态**：Audit-accepted-with-findings（ML-016 新 30-task run：19/30）

## 背景

ML-016p 修复了 AsmPrinter external symbol，ML-016q 修复了 generic inline-asm `r`
constraint mapping，ML-016r 又完成了 fresh 等价链路验证。需要在隔离目录用当前
新编译器重跑 musl object matrix，量化原 184 个 backend failures 的变化，避免只看
最小 probe 就宣称 libc 已恢复。

## 目标与 ownership

worker 只在 `/tmp/ml-016s-post-fix-musl-object-matrix-20260721/` 工作：

1. 固定新 clang/llc 的路径、版本、hash，并从 ML-016f 的 source/config/command
   恢复 object matrix；优先重跑原 184 个失败对象，若成本可接受再跑完整 1347 object
   matrix。保留每个 object 的 compile rc、stderr、argv、产物 hash/mtime。
2. 对比 ML-016f 原始 1163/184 结果，按旧 7 簇统计哪些变为成功、哪些仍失败、是否
   出现新簇；单独报告 `__unmapself`、`explicit_bzero` 和 stdio objects。
3. 不打包或替换主 archive；给出下一步是继续 backend 修复、受控重建 archive，还是
   进入 link/runtime 复验的客观边界。

## 约束

- 只写本 task 完成区和 `docs/reviews/ML-016s-post-fix-musl-object-matrix-20260721.md`；
  其他源/obj/log/summary 放 `/tmp`。
- 不修改主 `.work/build/musl`、musl source、LLVM/QEMU/gem5、contracts、vectors、
  issues、wiki 或 ML-014a；不访问或引用 `~/toolchain`、`~/knowledge-graph`。
- 不使用 `|| true`；每个阶段和 object 保留原始 rc。不要把旧产物或单个 probe 当作
  修复后结果。

## 完成区

worker 已在 `/tmp/ml-016s-post-fix-musl-object-matrix-20260721/` 完成新工具隔离
object matrix；未生成 archive，未修改主 build/archive 或其他受限内容。完整 review
见 [`docs/reviews/ML-016s-post-fix-musl-object-matrix-20260721.md`](../../docs/reviews/ML-016s-post-fix-musl-object-matrix-20260721.md)。

- 工具固定为 `/home/holight/DADAO-0628/.work/build/llvm/bin/clang` 和 `llc`；
  clang/LLVM 22.1.8，clang 版本 commit `10690fc4d40dd7d30757b344c2e259cd9c89a5c4`；
  clang SHA-256 `9c5450b37bc3447879f247e435d611f545f49b240cba6a9ee8051176e31bdd71`，
  llc SHA-256 `ed5bd8155a45b7b1b5933cb7505ef08abc5bb243dc945bbca13464ce4c15f8e3`。
  前后 hash 比对 `rc=0`；完整版本、mtime、hash 见 `logs/metadata/`。
- 新 source commit 为 `4741d4d1105849adf551a7998503866ed4f8b961`，configure
  `rc=0`；configure 前后 `.o` inventory 均为 0。新 config、argv 和阶段环境见
  `/tmp/ml-016s-post-fix-musl-object-matrix-20260721/build/config.mak` 与 `logs/`。
- 优先重跑旧 184 failures：make 原始 `rc=2`，184/184 有逐对象新记录，2 个成功、
  182 个失败。随后重跑其余 1163 个基线成功对象：make 原始 `rc=0`，1163/1163
  成功。合并后的新鲜矩阵为 1347 个唯一对象：1165 成功、182 失败；1165 个成功
  对象均有新产物且 `artifact_fresh=yes`，没有成功对象缺产物，没有重复 output，
  没有生成隔离 `libc.a`。
- 旧 7 簇变化：`unsupported library call operation` 157→157、
  `machine verifier: undefined physical register` 16→16、
  `Cannot select: dynamic_stackalloc` 7→7、
  `Cannot select: sign_extend_inreg from i1` 1→1、
  `SelectionDAG assertion: illegal result number` 1→1；
  `DADAO AsmPrinter: unknown operand type` 1→0（`__unmapself` 成功），
  `inline asm: input register constraint allocation` 1→0（`explicit_bzero` 成功）。
  失败从 184 降至 182；未出现新簇。逐对象转移和汇总见 `results/old-7-cluster-*`
  与 `results/baseline-to-fresh-*`。
- 专项结果：`obj/src/thread/__unmapself.o` `rc=0`；
  `obj/src/string/explicit_bzero.o` `rc=0`；stdio 共 116 个，113 成功、3 失败。
  `__fdopen.o`、`fflush.o`、`fileno.o` 均为新 clang `rc=0`；`puts.o` 仍为
  `Cannot select: sign_extend_inreg from i1`，`vfprintf.o` 与 `vfscanf.o` 仍为
  `unsupported library call operation`。完整表见 `results/special-objects.tsv` 和
  `results/stdio-object-results.tsv`。
- 原始每对象 `rc`、stderr、argv、stderr hash、产物 hash/mtime 和 record 路径均保留在
  `results/object-results.tsv`；原始逐参数 argv、stderr 和 record 在 `logs/compiler/`，
  阶段 rc 在 `logs/configure.rc`、`logs/priority184/make.rc`、`logs/rest1163/make.rc`。
- 验收边界：当前不能进入“完整 archive 重建”，因为仍有 182 个 backend object
  failures；本 task 未打包或替换任何 archive。可对已成功对象做受控、目标化 link
  复验，但不能据此宣称完整 libc link；full link/runtime 仍不可进入，下一步优先
  继续处理剩余 backend 簇，再做受控 archive，随后才进行完整 link/runtime 复验。

独立 reviewer Mill the 2nd 的结论为 **Accepted-with-findings**，见
`docs/reviews/ML-016s-independent-review-20260721.md`。review 确认 1347 条账本和
2 个修复迁移成立；findings 为任务文件 dated 路径不一致，以及两条汇编对象的 source
metadata 缺失/错位，不影响 rc/hash/freshness 结论。
