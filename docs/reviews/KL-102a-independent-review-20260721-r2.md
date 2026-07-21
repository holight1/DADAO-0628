# KL-102a 独立 review r2（2026-07-21）

## 结论

**Accepted**。

对照上一轮 `docs/reviews/KL-102a-independent-review-20260721.md`，修订后的
`docs/reviews/kernel-cfx-state-patch-surface-20260721.md` 已解决三项 Needs-fix，
未发现阻断问题。

## 三项 Needs-fix 复核

1. **gem5 的 patch-defined 限定已补足。**

   修订报告明确说明当前 checkout 不存在 `src/arch/dadao`，`0001` 仅是拟议架构
   代码的形状来源，并非当前可构建或可直接复用的实现；同时列出
   `ISA::copyRegsFrom()` 中未定义的 `tc` 变量作为 patch 链仍需修复的证据
   （修订报告第 44–49 行）。报告还明确总结为 “patch-defined surface”，并指出
   没有可直接复用的 CFX dispatch（第 60 行）。该项已解决。

2. **O1 的 12 个逻辑 delegation 与 opcode 未冻结状态已明确。**

   修订报告逐项列出 12 个逻辑字段：`umon`、`jmon`、`smon`、`ptw`、`tlb`、
   `cache`、`hart`、`llc`、`pmem`、`timer`、`uart`、`power`；并明确这些是 HBI
   §3 的逻辑字段名，当前 M1 排除 `cfx2rc`，不存在可直接核验的 opcode/encoding，
   编码及 operand 形状必须在后续 spec decision 中冻结（第 69–74 行）。该项已解决。

3. **统一字段的非冻结性质及 legacy/real 互斥点已声明。**

   修订报告将统一字段标为 **[实现建议/推断验收草案]**，明确其不是现有协议，且
   数值编码、event 状态机、marker/rc 来源和 profile 互斥点尚未冻结（第 104–106
   行）。同时明确 `legacy_cfx_smon` 与 `real_cfx_handoff` 应互斥（第 100 行），
   并要求 real profile 在 CFX dispatch 入口拒绝走 legacy host responder，形成可审计
   的互斥检查点（第 112–118 行）。该项已解决。

## 审阅范围

本次仅读取修订报告与上一轮独立 review，并写入本文件；未修改原报告，未访问
`~/toolchain` 或 `~/knowledge-graph`，未运行模拟器或长测试。
