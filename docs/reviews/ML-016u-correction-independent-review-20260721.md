# ML-016u 更正后独立复审

日期：2026-07-21（Asia/Shanghai）  
范围：复核 ML-016u task、根目录索引、详细 worker review、原 independent review，以及 `/tmp/ml-016u-post-i1-musl-object-matrix-20260721/` 中的结果证据。未修改实现、测试、规范、构建或 archive。

## 结论

**Accepted-with-findings**。

更正后的 canonical baseline 与 fresh 结果成立，原 independent review 所指出的核心验收错误已在 task 完成区和根目录索引中更正。fresh 结果支持进入受控、目标化 archive/link gate；不支持完整 libc archive、完整 link 或 runtime gate。

## 独立核对结果

- fresh matrix 为 1347 个唯一对象，1166 成功、181 失败；逐对象 `rc`、record、stderr 与 artifact provenance 可追溯。
- 重新统计得到 `rc=0/1 = 1166/181`，重复 output=0；成功 artifact 缺失=0、hash/size/mtime mismatch=0、非 fresh=0；record/stderr 缺失=0。
- fresh 失败簇仅四簇：`unsupported library call operation` 157、`machine verifier: undefined physical register` 16、`Cannot select: dynamic_stackalloc` 7、`SelectionDAG assertion: illegal result number` 1；合计 181，无新簇、无未分类失败。
- 相对 ML-016s 的 1165/182 逐对象比较为：仅 `obj/src/stdio/puts.o` fixed；`obj/src/string/explicit_bzero.o` 和 `obj/src/thread/__unmapself.o` 在 ML-016s 已成功，本轮 unchanged；regression=0。
- 相对 ML-016f 的 1163/184 才是 3 个 fixed：`puts.o`、`explicit_bzero.o`、`__unmapself.o`；regression=0。
- stdio 为 114/116；剩余失败为 `vfprintf.o`、`vfscanf.o`，均属 `unsupported library call operation`。
- configure `rc=0`，matrix make 保留原始 `rc=2`；未生成 archive。该证据不能宣称完整 libc 或 runtime 通过。

## Finding

详细 worker review `code-agent/docs/reviews/ML-016u-post-i1-musl-object-matrix-20260721.md` 仍保留旧的迁移表述：其“相对 ML-016s”段落把 1163/184 baseline 的三个对象迁移写成 ML-016s 的 transition。该表实际对应 ML-016f，不能作为 ML-016s 比较引用。

这是交付物之间的文档一致性 finding，不改变 fresh ledger、artifact provenance、正确的 ML-016s/ML-016f 独立对比或 gate 边界；本复审按用户约束不修改该文件。

## 判定

**Accepted-with-findings**：接受更正后的 ML-016u object-matrix 复审结论及其受控 gate 边界；保留上述 stale worker-review transition table 作为文档 finding。完整 archive/link/runtime gate 仍为不可进入。
