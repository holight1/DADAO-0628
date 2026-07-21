# KL-101a：hypv→supv 移交机制调研

**执行环境**：本地 subagent，先调研，不直接修改 QEMU、gem5、LLVM、kernel 或 spec

**状态**：Accepted（30-task run：15/30）

## 背景

KL-001a 的 kernel bring-up recon 指出：当前 CPU reset 直接进入 hypv，而 HBI §3
要求通过移交序列进入 supv；`inner_run_mode`、`inner_cfx_mask`、
`inner_cfx_code` 等隐藏状态若未建模，后续所有从 S/supv 视角设计的 kernel
任务都可能建立在错误的启动状态上。

## 目标

基于当前仓库契约和已有 QEMU/gem5 实现，厘清 reset→hypv→supv 的最小状态机、
移交指令/异常路径、隐藏状态生命周期，以及最小双后端可验证 oracle。只做
证据调研和任务拆分，不实现代码。

## 约束与 ownership

- worker 只写本 task MD、`docs/reviews/kernel-hypv-supv-handoff-20260721.md`
  和 task-owned evidence。
- 不查阅或引用 `~/toolchain`、`~/knowledge-graph`；只使用当前仓库
  `contracts/`、`docs/`、`qemu/`、`gem5/` 与当前 wiki pin 可核对资料。
- 明确区分正式 contract、已有实现、历史经验和待决推断；不擅自修改
  `docs/issues.yaml` 或 wiki pin。

## 调研问题

1. HBI/SEE 对 reset mode、hypv→supv 移交顺序、权限/状态变化的正式要求是什么。
2. 当前 QEMU 与 gem5 是否已经实现这些路径；若未实现，指出准确代码位置和
   最小缺口，不把 host-side syscall 捷径误认为真实移交。
3. 给出最小状态转移图和三个 oracle：成功移交、非法顺序/权限、移交后
   `cfx_smon` 或等价最小受控操作；说明预期双后端观测结果。
4. 拆出 KL-102a/103a 的前置依赖与下一任务建议，不提交实现 patch。

## 验收

- 关键结论都有文件/章节/行号或可复核命令。
- 同时覆盖 QEMU 与 gem5，不以单一模拟器行为代替契约。
- 有独立 reviewer；若首轮 Needs-fix，必须修订后再收口。

## 完成区

### 结果

- worker 报告：`docs/reviews/kernel-hypv-supv-handoff-20260721.md`
- 结论：HBI/SEE 规定 reset→hypv→supv 的真实移交顺序；当前 QEMU/gem5 都只有
  host/SE `cfx_smon` shortcut，没有 SEE 级权限、现场、模式、guest vector 和
  `escape` 状态机。
- 已冻结下一步边界：KL-102a 先做 cfx 状态/指令语义最小实现，KL-103a 再做
  guest-side `cfx_smon` handler；O1/O2/O3 是双后端验收草案，其中 O2/O3 尚非
  当前实现结果。

### 独立 review

- 首轮 reviewer：`docs/reviews/KL-101a-independent-review-20260721.md`，
  `Needs-fix`；指出 O2/O3 标签、QEMU `EXCP_CFXTRAP` 表述和 early-escape
  负例依据需收紧。
- 修订后 reviewer：`docs/reviews/KL-101a-independent-review-20260721-r2.md`，
  `Accepted`；确认三项问题均已解决。

### 可复核命令

```bash
rg -n -i 'inner_run_mode|inner_cfx|cfx2rc|cfx2rd|escape|cfx_smon|reset_hold|run_mode' \
  .work/source/qemu/target/dadao components/gem5/patches components/qemu/patches
rg --files -uu .work/source/gem5 | rg '(^|/)src/arch/dadao/'
```
