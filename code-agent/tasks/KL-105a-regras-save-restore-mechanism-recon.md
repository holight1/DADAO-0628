# KL-105a：RegRAS 全栈保存/恢复机制前置调研

**执行环境**：本地 subagent，纯调研，不写实现

**状态**：Accepted（30-task run：14/30）

## 背景

KL-001a 的 kernel bring-up recon 发现：当前 M1 将 `ldmo-ra`/`stmo-ra` 以及
`rd2ra`/`ra2rd` 列为 Excluded，但 wiki AEE 又要求进程切换保存/恢复全部
`ra0-ra63`。这可能是后续 Linux context switch 的硬阻塞，必须先厘清 ISA 契约
和可行的过渡机制。

## 目标

只回答“在当前 ISA/spec 约束下，OS 如何可靠保存/恢复完整 RegRAS bank”：确认
正式 spec 与 wiki 的要求是否一致，枚举不改变 ISA/修改 ISA/软件 workaround 三类
方案，给出 K1/K2 的推荐决策与验证门槛。不直接改 QEMU、gem5、LLVM、kernel、spec
或 patch series。

## Ownership 与约束

- worker 只写本 task MD、`docs/reviews/kernel-regras-save-restore-20260721.md`
  和 task-owned evidence；不修改实现或 contracts。
- 不查阅或引用 `~/toolchain`、`~/knowledge-graph`；原始依据使用当前仓库
  `contracts/`、`docs/` 与当前 wiki pin 可核对内容。
- 必须区分：正式定义、M1 Excluded、历史草案、推断方案；不可把旧 ISA 代码当作
  当前可复用实现。

## 调研阶梯

1. 读取当前 ISA contract 中 RegRAS、特权级、context switch 相关章节与 Excluded
   表；核对 KL-001a 报告引用的 wiki AEE/HBI 原文。
2. 评估至少三类方案：增加/启用整栈指令、用现有指令逐槽搬运、将 RegRAS 现场交给
   trap/hardware context frame；逐项列出指令/ABI/异常嵌套/性能/可验证性风险。
3. 画出 Linux context switch 最小需要保存的现场清单，指出仅保存 GPR/CSR 而不
   保存 RegRAS 的具体失败模式。
4. 给出推荐的 K1 任务拆分、必须先解决的 spec open issue、以及最小 bare-metal
   oracle；不提交任何实现 patch。

## 验收

- 每个关键结论有具体章节/文件路径依据。
- 至少三种方案有明确权衡和淘汰/保留理由。
- 输出可直接供后续 KL-106/KL-107 任务使用，并由独立 reviewer 复核。

## 完成区

### 结果

- worker 报告：`docs/reviews/kernel-regras-save-restore-20260721.md`
- 结论：当前 M1 没有可读写 RegRAS bank 的通路；K1 推荐把整 bank save/restore
  作为独立 ISA/spec decision，优先评估 `ldmo-ra`/`stmo-ra`，不把硬件 trap
  frame 假定为现有行为。
- 三个 bare-metal 测试已明确标注为“contract 冻结后的验收草案”，当前 M1
  尚不可执行；需先冻结指令、布局、初始化/读取通路及精确异常语义。

### 独立 review

- 首轮 reviewer：`docs/reviews/KL-105a-independent-review-20260721.md`，
  `Needs-fix`；指出 AEE 外部要求、现行 ISA 契约、待决方案和测试可执行性
  的边界混淆。
- 修订后 reviewer：`docs/reviews/KL-105a-independent-review-20260721-r2.md`，
  `Accepted`；确认上述边界已收紧，无阻断问题。

### 可复核命令

```bash
nl -ba docs/reviews/kernel-regras-save-restore-20260721.md
rg -n -i 'AEE|RegRAS|ra0|ra63|ldmo-ra|stmo-ra|rd2ra|ra2rd|M1 Excluded' \
  contracts/isa/spec.md docs/reviews/kernel-bringup-recon-2026-07-18.md
```
