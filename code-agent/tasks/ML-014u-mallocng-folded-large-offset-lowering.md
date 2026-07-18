# ML-014u：隔离 mallocng 末端访问的大偏移折叠 lowering

**执行环境**：本地 subagent worker；承接 ML-014s/t

**状态**：Ready（30-task run：1/30）

## 目标

解释为什么真实 `malloc_rw_after` 的 `p[131051]` 最终形成
`stb/ldbu ..., -21`，而 ML-014t 将同一数学偏移先物化为完整 RD 加法后双后端
通过。任务只建立 source → LLVM IR → SelectionDAG/MIR（能取得多少记录多少）→
ELF 的差异链，确定是否是 DADAO load/store 地址折叠的立即数合法性判断或其他
具体 lowering 环节；不直接修改实现。

## Locked inputs 与 Ownership

- 使用当前主线、ML-014m 真实 mallocng-linked source/ELF 与 ML-014t probe。
- worker 只可新增本任务 `.work/ML-014u-mallocng-folded-large-offset-lowering/`
  诊断产物，并完成本 task MD 的完成区；不得修改 LLVM/QEMU/gem5/musl、patch
  series、tests、docs/issues、contracts、manifests 或用户原始 ML-014a。
- 外部架构资料不在 worker scope；只使用本仓库和合同锁定产物。
- 其他 agent 可能同时工作；不得回滚、覆盖或整理他人的改动。

## 执行阶梯

1. 精确固定 `malloc_rw_after.c`、ML-014t source、编译器、参数和链接产物身份。
2. 生成可审计的 IR、汇编/反汇编；如当前工具支持，保留关键 SelectionDAG/MIR
   或 `llc -stop-*` 产物。不可用时记录真实错误，不以猜测补齐。
3. 新增最小 source 变体，仅改变“偏移直接用于 load/store”与“先保存 q 再访问”
   的形态，确认触发条件；变体只放本任务 `.work`，不替代真实 mallocng 证据。
4. 定位最窄可疑实现函数/模式和立即数范围，给出下一实现任务的文件、测试与
   非目标边界。
5. 记录命令、退出码、证据层级、未验证项和 worker 自审，等待独立 reviewer。

## 验收

- 真实路径和最小变体都具有 source/IR/ELF 证据；明确 `131051 -> -21` 在哪一层
  首次出现，或严格说明尚缺哪一层。
- 结论足以决定是否开启一个有最小回归测试的 LLVM 专项修复任务。
- 无实现、patch series、测试主线、issues 或 ML-014a 变更；不得宣称 mallocng、
  ML-014f 或 ML-014a 完成。

## 完成区

（由 worker 填写；完成后必须由不同 subagent 独立 review）
