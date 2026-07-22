# ML-017d：最终 handoff 与后续 roadmap

日期：2026-07-21（Asia/Shanghai）  
关联任务：DADAO-0628 ML-017d（本轮第 30 任务）

## 状态

**Audit-accepted-with-findings。** Worker completed；独立 review 为 Nash the 2nd。
puts-success 仍为后续 A 路线的 blocking 子目标。

本任务只新增本文件和
[`docs/reviews/ML-017d-final-handoff-roadmap-20260721.md`](../../docs/reviews/ML-017d-final-handoff-roadmap-20260721.md)。
不修改生产代码、旧 task/report、`docs/issues.yaml`、wiki、launcher/spec、LLVM、
musl、QEMU、Gem5 或 tracker；不修改原有未跟踪的
`code-agent/tasks/ML-014a-musl-e2e-malloc-printf.md`。没有查阅或引用
`~/toolchain`、`~/knowledge-graph`。

## worker 完成记录

- 汇总 ML-016a~z、ML-017a~c 的 canonical task/report 与独立 review，并形成最终
  handoff/report。
- 文件级 worker 交付计数为 **30/30**：ML-016a~z 26 项、ML-017a~c 3 项、本
  ML-017d 1 项。
- 既有输入的独立 review 为 **29/30**；本 ML-017d 的独立 review 尚未完成。
- `ML-016-30-task-run-20260721.md` 的原有 `29–30 Pending` 行保持原样，本任务
  不以改写 tracker 来替代独立 review。

## 交付验收

- [x] 记录 30-task worker 交付数、独立 review 数和各阶段状态。
- [x] 记录 final nested LLVM commit `d3bd9c...`、四项已落地修复、1347-object
      结果 `1166/181`、四簇和 stdio `114/116`。
- [x] 明确 `llvm-lit` 因缺少 `llvm-config` 未启动，不能宣称 full LLVM suite。
- [x] 记录 final-head varargs QEMU/Gem5 `0/0`、1166-member partial archive
      的 ar/ranlib/link 与目标化运行结果，以及 QEMU/Gem5 输入形态差异。
- [x] 明确 puts marker 缺失、errno bypass 非零失败、ML-017c puts-success
      blocking finding。
- [x] 明确 ML-014a/mallocng 本轮没有重新解决或接受，kernel 尚未进入。
- [x] 给出按 A→E 阻塞顺序的 roadmap；每项均含验收门槛与禁止越界声明。
- [x] 将事实、推断和边界分开；保留原 ML-014a 未跟踪文件和全部旧审计记录。

## 独立 review 结果

- [x] 核对本文件与最终 report 是否只引用允许的 ML-016/017 文档和 `/tmp` 证据
      索引，且未触碰禁用目录。
- [x] 核对 30/30 worker、29/30 reviewed、tracker 未改写的状态口径。
- [x] 核对 puts-success 阻塞、be99→d3bd isolation 未做，以及 A→E 每项的边界。

最终状态：**Audit-accepted-with-findings**。artifact 计数、独立 review 和主 tracker
均已完成 30/30；review 时的原始 `29–30 Pending` 已由主 agent 集成更新。puts-success
仍未闭合。
