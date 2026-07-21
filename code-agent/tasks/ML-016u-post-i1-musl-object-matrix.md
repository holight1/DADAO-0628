# ML-016u：i1 修复后 musl object matrix 复验

**日期**：2026-07-21

**状态**：Audit-accepted-with-findings（ML-016 新 30-task run：21/30）

## 背景

ML-016t 已修复 `SIGN_EXTEND_INREG/i1`，并在隔离 include 路径下使 puts O0/O3
通过。需要使用包含 p/q/t 修复的新 clang/llc 重跑完整 1347 object matrix，确认
单例迁移、失败簇和 stdio 状态，决定是否可以开始目标化 archive/link 复验。

## 目标与 ownership

worker 只在 `/tmp/ml-016u-post-i1-musl-object-matrix-20260721/` 工作：

1. 固定新 clang/llc hash/version，使用 fresh clean object 输出重跑 1347 个对象；
   保存逐对象 rc、stderr、argv、产物 hash/mtime 和阶段 rc。
2. 对比 ML-016s 的 1165/182 结果，确认 `puts.o` 是否转为成功、旧簇是否出现新
   迁移/新簇；单独报告 stdio 116 项和剩余五簇。
3. 不打包或替换主 archive；只有在完整 object matrix 和 provenance 通过后，给出
   下一步受控 archive/link gate，不宣称 runtime 已通过。

## 约束

- 只写本 task 完成区和 `docs/reviews/ML-016u-post-i1-musl-object-matrix-20260721.md`；
  其他产物放 `/tmp`。
- 不修改主 `.work/build/musl`、musl source、LLVM/QEMU/gem5、contracts、vectors、
  issues、wiki 或 ML-014a；不访问或引用 `~/toolchain`、`~/knowledge-graph`。
- 不使用 `|| true`；不使用旧 object/archive 冒充修复后结果，逐对象保存原始 rc。

## 完成区

### worker 交付（2026-07-21）

状态：已完成，待不同 subagent 独立 review。

本轮仅在 [`/tmp/ml-016u-post-i1-musl-object-matrix-20260721/`](/tmp/ml-016u-post-i1-musl-object-matrix-20260721/) 使用 fresh clean build 重跑完整 1347 object；未修改主 `.work/build/musl`、musl source、LLVM/QEMU/gem5、contracts、vectors、issues、wiki 或 ML-014a，未生成或替换 archive。

- 工具固定为当前 ML-016t 修复后 clang/llc：LLVM 22.1.8，LLVM revision `40bc313742b00848d341e77e1a38441211971729`；clang SHA-256 `d1c6e0026741e45f7ae98f13d4057a6838f9ef049d6b9d110152a2f90ce94bdc`，llc SHA-256 `ac7a71404061254b68f7d43cd343f4b121952af77b0ef7cb2428a15231ad2f9c`。before/after hash 相同；configure `rc=0`，matrix make 原始 `rc=2`。
- 1347/1347 个唯一对象均有原始 rc、stderr、record/argv、source hash、artifact hash/mtime 记录；1166 成功、181 失败。1166 个成功对象均有 fresh artifact，成功缺 artifact=0、非 fresh=0、失败残留 artifact=0、重复 output=0、未分类失败=0；isolated archive=0。
- 相对 ML-016s 的 1165/182：1165 个旧成功中 1165 保持成功，**仅 1 个旧失败迁移为成功**（`obj/src/stdio/puts.o`），181 个失败保持失败，无旧成功回归、无新簇。`explicit_bzero.o` 与 `__unmapself.o` 在 ML-016s 已经成功，本轮相对 ML-016s 为 unchanged。
- 另行说明：若与 ML-016f 的原始 1163/184 baseline 比较，确有 3 个对象（`puts.o`、`explicit_bzero.o`、`__unmapself.o`）从失败转为成功；该 3-object 迁移不能标注为 ML-016s transition。
- stdio 116 项中 114 成功、2 失败；`puts.o` 已成功，剩余失败为 `vfprintf.o` 和 `vfscanf.o`，均为 `unsupported library call operation`。fresh 剩余簇为 unsupported library call operation=157、undefined physical register=16、dynamic_stackalloc=7、illegal result number=1。
- 完整逐对象结果、旧簇迁移、stdio、special objects、阶段 rc 和 provenance 位于 `/tmp` results/logs；review 见 [`docs/reviews/ML-016u-post-i1-musl-object-matrix-20260721.md`](../docs/reviews/ML-016u-post-i1-musl-object-matrix-20260721.md)。

结论：**可进入受控、目标化 archive/link gate**，范围限于已成功对象和明确的 link probe；**不可进入完整 libc archive 重建、完整 link 或 runtime gate**，也不能据此宣称 runtime 通过，因为仍有 181 个 backend object failures。

### 基线更正（独立 review 后）

ML-016u 初始完成区把 ML-016f 的 184-failure transition 误写成 ML-016s 的
1165/182 transition。已按独立 review 更正为上面的两个明确基线：相对 ML-016s
只有 `puts.o` fixed；相对 ML-016f 才是三个对象 fixed。详细 worker review 原始文件
误落在 `code-agent/docs/reviews/ML-016u-post-i1-musl-object-matrix-20260721.md`；
根目录索引见 `docs/reviews/ML-016u-post-i1-musl-object-matrix-20260721.md`。

更正后的详细 worker report 已同步修正迁移表。更正复审结论为
**Accepted-with-findings**，见 `docs/reviews/ML-016u-correction-independent-review-20260721.md`；
finding 仅保留历史旧 report 的 stale wording 已被修正这一审计事项。
