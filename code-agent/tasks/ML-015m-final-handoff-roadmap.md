# ML-015m：30-task handoff 与后续 roadmap 收口

**日期**：2026-07-21

**状态**：Completed（30-task run：30/30）

## 目标

汇总本轮 ML-015a～ML-015l 的可复核结果，形成 handoff 和后续路线建议；完成
后停止本轮连续 task 推进，不再自动启动第 31 个任务。

## worker ownership

worker 只写 `docs/reviews/ML-015m-final-handoff-roadmap-20260721.md` 和本 task
完成区，不修改实现、vectors、`docs/issues.yaml`、wiki 或现有 roadmap；不访问
或引用 `~/toolchain`、`~/knowledge-graph`，不修改 ML-014a。

报告必须明确：

1. 已解决：spec/vector/harness/QEMU consistency、ISA fresh 202/202、仓库
   llvm-test-suite 23/23、完整 E2E 59/59、3 个 fixture 的 Gem5 覆盖。
2. 未完成：ML-014a mallocng 真实双后端里程碑、upstream 全量
   llvm-test-suite/gcc-c-torture、UNDI/RASOF active vectors、PC/RA 观测、
   tail-call/varargs ABI 边界和 kernel 路线。
3. 后续优先级：继续 LLVM+QEMU/ABI 证据，先处理 mallocng 或明确的 codegen/ABI
   blocker，再考虑 kernel；不要把当前数字扩大解释。

## 完成区

### worker completion（2026-07-21）

已完成最终 handoff report：
[ML-015m-final-handoff-roadmap-20260721.md](/home/holight/DADAO-0628/docs/reviews/ML-015m-final-handoff-roadmap-20260721.md)。

- 已解决（当前覆盖范围）：spec/vector/harness consistency；QEMU build
  `rc=0`、ISA fresh `active=202/deferred=11/pass=202/fail=0`；完整仓库 E2E
  `59/59`；仓库内 llvm-test-suite 切片 `23/23`；三项 Gem5 fixture fresh
  `3/3`，退出码为 `0/249/1`。
- 未完成：ML-014a mallocng 真实双后端里程碑；upstream 全量
  llvm-test-suite/gcc-c-torture；active UNDI/RASOF vectors；PC/RA 观测；
  tail-call/varargs ABI 边界；kernel 路线。
- 口径：`23/23` 仅为仓库切片，不是 upstream 全量；`59/59` 仅为当前仓库
  E2E，不是 mallocng 已解决证明。
- 下一步优先 LLVM+QEMU/ABI（先处理 mallocng 或明确的 codegen/ABI blocker），
  再考虑 kernel；本 task 未修改实现、vectors、issues、wiki、roadmap 或
  ML-014a，未访问或引用 `~/toolchain`、`~/knowledge-graph`。

### 独立 review

`docs/reviews/ML-015m-independent-review-20260721.md`，结论 **Accepted**；
reviewer 确认已解决数字、未完成边界和路线顺序均无越界解释。本轮 30-task 推进
到此停止，不自动启动第 31 个任务。
