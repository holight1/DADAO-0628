# ML-016e：musl archive object selection audit

**日期**：2026-07-21

**状态**：Audit-accepted-with-findings（ML-016 新 30-task run：5/30）

## 背景

ML-016d 发现当前 `.work/build/musl/lib/libc.a` 缺少源码中存在的
`fflush.o`、`fileno.o`、`__fdopen.o`，但 archive 中已有其他 stdio objects。
需要先确认这是构建输入/manifest、编译输出目录、archive 生成命令还是陈旧产物，
再决定是否修复；本任务不修改实现和当前 libc archive。

## 目标与 ownership

worker 负责只读审计与临时复现：

1. 检查当前 musl source、`.work/build/musl/obj`、archive、Makefile/生成清单和
   构建日志，建立 `src/stdio/*.c -> expected object -> archive member` 的完整
   对照，明确缺失对象在哪一层首次消失。
2. 在 `/tmp` 复制或独立构建一份最小、可复核的 archive 生成试验；不得写入主
   `.work/build/musl`、musl source 或任何受保护测试/规范文件。记录实际命令、
   输入清单、对象时间戳/哈希和原始退出码；不得用 `|| true` 掩盖失败。
3. 给出最小后续任务边界：是 manifest/构建修复、产物清理重建，还是当前证据
   不足；不要修改代码，也不要把 archive 可链接性推断成 writev runtime 已修复。

## 约束

- 只写本 task 完成区和
  `docs/reviews/ML-016e-musl-archive-object-selection-audit-20260721.md`；临时
  产物放 `/tmp`。
- 不修改 LLVM/QEMU/gem5/musl、contracts、vectors、issues、wiki 或 ML-014a。
- 不访问或引用 `~/toolchain`、`~/knowledge-graph`。
- 不重建或覆盖主 archive；不提交实现性变更。
- QEMU/Gem5 如需验证只运行已有产物或 `/tmp` 产物，分别记录退出码和 timeout。

## 完成区

（由 worker 填写；完成后由不同 subagent 独立 review）

### 完成（2026-07-21）

**状态**：Completed / Audit-accepted-with-findings；只读审计与 /tmp 独立复现完成，未修改实现、musl source、主 .work/build/musl 或受保护文件。

#### 结论

- 当前 musl Makefile 的 src/*/*.c wildcard 展开包含全部 116 个 src/stdio/*.c，对应的 116 个 obj/src/stdio/*.o 也都在 LIBC_OBJS/AOBJS 预期清单中；没有证据支持“stdio manifest 把这三个 object 排除”的结论。
- 当前 .work/build/musl/obj/src/stdio 只有 88/116 个预期 object，缺失 28 个；这 28 个的 source 存在、预期 object 存在于 Makefile 展开中，但 object 和 archive member 同时缺失，因此每个缺失对象首次消失在编译输出/object 层。
- /tmp 独立副本按同一 Makefile/config 编译这 28 个 source：25 个原始 rc=0（包括 __fdopen.o、fflush.o、fileno.o），puts.o、vfprintf.o、vfscanf.o 原始 rc=2，分别保留了 LLVM backend 原始诊断；这支持“当前是 partial/stale build output”，但没有历史构建日志，不能断言主构建当时是跳过还是编译失败。
- 当前 archive 有 1002 个 member，而当前 obj 输入有 1005 个 object；按 basename 对照额外发现已存在但未进入 archive 的 aio.o、aio_suspend.o、lio_listio.o。临时执行同形状的 llvm-ar packaging 会得到 1005/1005，故主 archive 至少不是当前 obj 快照的完整打包，存在陈旧或不同历史输入选择证据。

#### 最小后续边界

下一步应是带逐对象原始日志的 clean/controlled musl partial rebuild，并重新按实际 object 清单打包 archive；当前证据不要求修改 stdio manifest 或源码。补齐 archive 后仍需独立复验 link/runtime；本任务不把 archive 可链接性推断成 writev runtime 或 ML-014a 已修复。

完整 worker 证据、116 项 source/object/archive 对照、命令/退出码、输入 object 哈希/时间戳和临时 archive 结果见：
docs/reviews/ML-016e-musl-archive-object-selection-audit-20260721.md

独立 reviewer Avicenna the 2nd 的结论为 **Accepted-with-findings**，见：
`docs/reviews/ML-016e-independent-review-20260721.md`。review 保留了“具体历史
根因未定”和“当前证据不能证明 runtime 已修复”等边界。
