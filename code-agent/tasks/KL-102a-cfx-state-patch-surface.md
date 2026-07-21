# KL-102a：cfx 状态与移交语义 patch surface 评估

**执行环境**：本地 subagent，只做实现前评估

**状态**：Accepted（30-task run：16/30）

## 背景

KL-101a 已确认 HBI/SEE 规定 reset→hypv→supv 的真实移交，而当前 QEMU/gem5
只有 host/SE `cfx_smon` shortcut。直接实现前，需要把 `inner_run_mode`、
`inner_cfx_mask`、`inner_cfx_code`、prev/cause 现场、`cfx2rc` 和 `escape` 的
最小范围映射到两个后端，避免把未冻结的语义扩散到完整 CFX/MMU。

## 目标

形成 KL-102a 的 contract-first 实施切片：明确 QEMU/gem5 各自需要新增/修改的
文件、状态字段、指令入口、异常/权限检查、最小 O1/O2 oracle 依赖，以及暂不
实现的范围。不提交实现 patch。

## 约束与 ownership

- worker 只写本 task MD、`docs/reviews/kernel-cfx-state-patch-surface-20260721.md`
  和 task-owned evidence。
- 不访问或引用 `~/toolchain`、`~/knowledge-graph`；不修改 `docs/issues.yaml`
  或 wiki pin。
- 必须区分 HBI/SEE 正式要求、当前源码事实、实现建议；不能把 patch 计划写成
  已实现功能。

## 调研问题

1. QEMU `CPUState/CPUDADAOState`、译码/helper、异常分派和 gem5 DADAO CPU
   状态/指令执行路径分别应在哪些文件承载最小字段和转移。
2. 只选 O1（成功 handoff）与 O2（授权/mask 非法路径）需要的最小语义；列出
   `cfx_smon` O3、MMU、完整 12 CFX、nested trap 留到哪些后续任务。
3. 给出不破坏现有 ML-014 syscall shortcut 的隔离方案，以及双后端统一的 trace
   字段和 return-code/marker 观测协议。

## 验收

- 所有文件路径和关键符号可复核。
- 有明确的“先改什么/暂不改什么/怎样证明”三段式结论。
- 完成后由不同 subagent 独立 review；Needs-fix 必须修订。

## 完成区

### 结果

- worker 报告：`docs/reviews/kernel-cfx-state-patch-surface-20260721.md`
- 结论：KL-102a 只先实现 O1/O2 所需的每 hart CFX 状态、power frame、
  delegation、`escape cfx_power,0` 和授权/mask fault；O3、MMU、完整 CFX、
  nested trap 留给后续任务。
- gem5 当前仅有 patch-defined surface，不是可直接复用的已应用实现；ML-014
  host shortcut 保留为 legacy profile，与 real handoff 在 dispatch 入口互斥。
- 统一 trace 字段已标为实现建议/验收草案，数值编码、event 状态机和 marker/rc
  来源须在实现任务中继续冻结。

### 独立 review

- 首轮 reviewer：`docs/reviews/KL-102a-independent-review-20260721.md`，
  `Needs-fix`；要求补足 gem5 patch-defined 限定、12 个 delegation 名单及
  未冻结的统一字段 schema。
- 修订后 reviewer：`docs/reviews/KL-102a-independent-review-20260721-r2.md`，
  `Accepted`；确认三项问题已解决，无阻断问题。

### 可复核命令

```bash
nl -ba contracts/isa/spec.md | sed -n '50,52p;947,959p;1146,1150p'
nl -ba .work/source/qemu/target/dadao/cpu.c | sed -n '40,57p;109,242p'
test -d .work/source/gem5/src/arch/dadao && find .work/source/gem5/src/arch/dadao \
  -maxdepth 1 -type f -print || echo NO_CURRENT_GEM5_DADAO_SOURCE
```
