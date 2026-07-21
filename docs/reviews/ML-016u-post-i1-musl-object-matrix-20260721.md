# ML-016u worker review 索引

详细 worker 证据因 worker 使用了错误的相对路径，原始文件位于：
[`code-agent/docs/reviews/ML-016u-post-i1-musl-object-matrix-20260721.md`](../../code-agent/docs/reviews/ML-016u-post-i1-musl-object-matrix-20260721.md)。

本任务的独立 review 位于：
[`ML-016u-independent-review-20260721.md`](ML-016u-independent-review-20260721.md)。

更正复审位于：
[`ML-016u-correction-independent-review-20260721.md`](ML-016u-correction-independent-review-20260721.md)。

独立 review 发现并要求修正一个基线表述错误：1347 fresh matrix 是 1166 成功、181
失败；相对 ML-016s（1165/182）只有 `puts.o` fixed，`explicit_bzero.o` 与
`__unmapself.o` 已在 ML-016s 成功；相对 ML-016f（1163/184）才是三个对象 fixed。
archive/link/runtime 边界判断不变：未生成 archive，完整 gate 仍不可进入。
