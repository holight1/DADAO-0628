# KL-105a：RegRAS 全栈保存/恢复机制前置调研

**执行环境**：本地 subagent，纯调研，不写实现

**状态**：Ready（30-task run：14/30）

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

（由 worker 填写；完成后由不同 subagent 独立 review）
