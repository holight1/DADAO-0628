# KL-118a：调研 K1 收尾项——MMU/TLB(PTBR/PTHI/PAHI) + 完整中断分派的增量拆分

**执行环境**：远端 Codex（本仓库），纯调研，不修改 QEMU/gem5/LLVM/
kernel/contracts/wiki

## 背景

K1（ADR-0015 D3）的定义是"补完整异常/中断模型（timer中断、page fault、
真正中断分派，不只syscall trap）+ MMU/TLB SBI式操作（PTBR/PTHI/PAHI）+
特权级切换（User/S-mode），双后端（QEMU+gem5）实现，**拆成若干增量
任务**"。特权级切换这部分已经通过 hypv→supv 移交（`KL-110a`~`KL-117a`，
O1成功路径+O2两个负例+O3真实`trap cfx_smon`进入流程，QEMU+gem5 双后端）
完成。K1 剩下最后两块：MMU/TLB SBI式操作、完整中断分派（timer/外部
中断/page fault）——这是目前为止范围最大、最不清楚的部分，需要先调研
拆解，不能直接写一个大实现任务。

**当前已知的现状**（部分来自本 session 之前的调研，需要你重新核实，
不要照抄）：
- QEMU `dadao_cpu_tlb_fill()` 目前是 identity TLB，全读写，没有真正的
  页表遍历（`ADR-0004` D2 记录了"M1无SEE/PTBR"这个已经过时的早期假设——
  hypv→supv 移交已经证明这个假设不再成立，MMU 是本任务要补的）。
- gem5 的 `DADAOMMU`/`DADAOTLB` 目前也只是 SE 模式骨架。
- `trap cfx_smon` 的真实进入流程（`KL-116a`/`KL-117a`）目前只覆盖了
  `CFXTRAP`（同步、不可屏蔽）这一种异常原因；wiki 完整异常进入流程
  步骤2-6（不可屏蔽判断/`inner_cfx_mask`/`global_cfx_mask`/
  `excp_cause_mask`/陷入计数）目前完全没有实现——这些机制正是"完整
  中断分派"需要补的部分（timer/外部中断都是**异步**、大概率**可屏蔽**
  的，会真正走到这几个跳过的步骤）。
- `cfx_ptw`（页表步进异常）、`cfx_tlb`（TLB命中异常）是 wiki 定义的两个
  专用 cfx，目前在 QEMU/gem5 里都不存在任何存储/分派代码。

## 目标

1. **梳理 wiki 对 MMU/TLB/SBI 式操作的完整定义**：`PTBR`/`PTHI`/`PAHI`
   （具体在哪个 cg/rc、哪个指令访问、页表格式、页大小、多级页表结构、
   TLB miss/hit 时的软硬件分工）、`cfx_ptw`/`cfx_tlb` 的异常原因表和
   触发条件、地址转换的完整流程（虚拟地址→页表遍历→物理地址，或者
   硬件 TLB fill + 软件 refill 的分工模式，wiki 是怎么定义的）。
2. **梳理 wiki 对完整中断/异常分派的定义**：目前 O3 只覆盖了
   `CFXTRAP`（不可屏蔽）这一种情况，wiki 步骤2-6（不可屏蔽判断/两级
   mask/陷入计数）在异步中断和可屏蔽同步异常场景下具体如何运作，
   timer 中断的触发源/寄存器/使能方式，中断 pending/mask 寄存器
   （`cfx_⟨cfxname⟩_pending`，cg4 相关寄存器组，`KL-115a`/`KL-116a`
   已经确认这组寄存器目前完全没有存储）的完整语义。
3. **参考旧项目教训**（只看结论，不抄代码/patch）：
   `~/toolchain/DADAO/code-agent/designs/dadao-mmu-enable-design.md`——
   旧项目当年设计 MMU 使能时踩过什么坑、哪些假设后来被推翻，这次要
   避免重复。
4. **产出增量任务拆分方案**：按照 ADR-0015 D3"拆成若干增量任务"的
   要求，把 MMU/TLB + 中断分派这一大块拆成若干个像 `KL-106a→107a→
   108a→109a`（RegRAS）或 `KL-115a→116a→117a`（O3）那样的、范围明确、
   可独立验收的小任务序列，每个任务给出：大致范围、QEMU/gem5 是否
   需要分开任务（参照 O1/O2/O3 全部是"QEMU 先做，gem5 单独 port"的
   先例）、依赖顺序（哪个任务必须在哪个任务之前）。**不要在本任务里
   写具体实现方案或伪码**，只给出拆分和每个子任务的范围说明+验收
   方向（一两句话级别，供后续写正式任务文件时展开）。
5. 如果发现某个环节 wiki 沉默/矛盾，或者发现这个范围可能比 K1 憲章
   设想的更大（类似 `KL-115a` 发现 O3 比预期大很多的先例），如实
   报告，不要为了"看起来可控"而简化掉重要发现。

## 约束

- 只做调研，不修改任何文件。
- wiki 引用必须亲自读原文核实，给出文件+行号。
- 参照本项目既有 review 报告的证据标签格式（`[正式契约]`/
  `[已有实现]`/`[推断]`）和写法（`docs/reviews/
  kernel-cfx-smon-o3-recon-20260725.md` 是最近的同类先例）。
- 完成后写「完成区」+ 自审记录，不需要嵌套 subagent。
- 如果发现真正的 wiki 空白，按 `docs/wiki-deviations.md` 现有格式给出
  建议条目草稿（不直接写入文件）。

## 验收

- 产出 `docs/reviews/kernel-mmu-interrupt-recon-20260726.md`。
- 报告结尾给出清晰的增量任务拆分方案（任务序列+每个任务的范围/验收
  方向/QEMU-gem5 任务划分建议），供架构师决定下一步具体下发哪个
  任务、以什么顺序。
- 任务文件「完成区」总结关键结论。

## 参考指针

- `docs/adr/0015-kernel-bringup-charter.md` D3（K1 的官方范围定义）
- `code-agent/tasks/KL-115a-cfx-smon-guest-handler-o3-recon.md`（同类
  调研任务的格式先例，包括"发现规模比预期大"时如何呈现）
- `code-agent/tasks/KL-106a-*.md`（RegRAS 调研先例，"混合判定"写法）
- `code-agent/tasks/KL-116a-*.md`/`KL-117a-*.md` 完成区（当前 trap
  entry-flow 已实现到哪一步、`cfx_smon` 帧的确切字段，作为"中断分派"
  这块要在什么基础上扩展的起点）
- `~/toolchain/DADAO/code-agent/designs/dadao-mmu-enable-design.md`
  （旧项目 MMU 设计，仅供查阅踩坑教训，不可抄代码/patch）
- `~/DADAO-wiki/DADAO-12-SEE-主管系统运行环境.md`（异常进入流程完整
  10 步、cfx_ptw/cfx_tlb 相关章节，具体行号由你核实）
- `~/DADAO-wiki/DADAO-22-SBI-主管系统二进制接口.md`（PTBR/PTHI/PAHI
  相关 SBI 调用约定）

---

## 完成区（2026-07-26）

### 完成摘要

- 已产出
  `docs/reviews/kernel-mmu-interrupt-recon-20260726.md`，逐项核对当前 wiki
  的 48-bit VA/64-bit PA、PTBR/PTHI/PAHI、两级页表、普通页/超页、
  fragment、A/D、TLB fill/invalidate、`cfx_ptw`/`cfx_tlb` 路由以及异常
  entry-flow 步骤2-10。
- 已确认 wiki 是“硬件 page walker + TLB miss 后硬件 fill”，不是软件
  refill；SBI 是配置、invalid 和 guest-side fault service 接口。
- 已重新核实当前实现：QEMU 仍为 identity TLB 且无异步中断入口/定时器设备；
  gem5 仍为 SE process page-table TLB、FullSystem panic、interrupt 恒空，
  现有 DADAO runner 固定 SE+AtomicSimpleCPU；两端都没有 `cfx2rd` 指令实现。
- 已从旧项目只继承三条教训：低 VA 用户 ELF 需要真实翻译、MMU enable 前
  必须准备异常向量/页表自身/IO 映射、先 bare-metal 分层验证；明确排除旧
  32-bit/4KiB/CP0/CSR 具体设计。
- 已记录待架构冻结的 wiki 缺口草稿：通用 pending 与同 cfx cause 优先级、
  timer 计数/触发/ack/reload、TLB 非架构容量 profile、外部中断/UART
  协议，以及嵌套 cfx 返回缺失的 `inner_cfx_code` 恢复规则；未擅自修改
  wiki 或 `docs/wiki-deviations.md`。
- 报告结尾给出 21 个建议增量切片：契约冻结和共享 CFX/异常 carrier 先行，
  MMU 与异步中断两条链分别 QEMU-first、gem5 独立 port，最后用一个双后端
  bare-metal 集成探针汇合。

### 自审记录

- 范围：仅新增本任务要求的调研报告并填写本完成区；未修改
  QEMU、gem5、LLVM、kernel、contracts、wiki 或 issue/roadmap。
- 证据：wiki 结论均重新读取当前文件并带文件+行号；当前实现结论分别核对
  `.work/source/qemu` 与 `~/DADAO-gem5` 当前源码，没有沿用任务背景的
  未验证陈述。
- 边界：报告没有把 SBI TODO、timer 空白或“外部中断”自行实现化；只提出
  deviation 草稿与先决决策任务。没有把旧项目的代码、常数或 patch 带入。
- 任务质量：每个建议任务均给出范围、验收方向、后端划分和依赖；gem5
  FullSystem/bare-metal carrier 被明确列为 MMU/IRQ port 的前置，避免 SE
  process page table 造成错误绿灯。
- 工作树：保留既有无关未跟踪文件 `gcc-torture-results.json`，不纳入本任务。

### 独立 review 记录

- reviewer 首轮结论为 NOT PASS，指出一个阻断项：SBI 的
  `cfx_tlb→cfx_ptw→cfx_tlb` 委托与 SEE `escape` 不恢复
  `inner_cfx_code` 的语义无法闭环。已补入报告 §1.3、wiki-deviation 候选E、
  KL-119a 先决决策，并要求 KL-122a 合成 nested probe 与 KL-129a 真实
  TLB→PTW→TLB probe。
- 已接受并修正其余有证据意见：`cfx_ptw` 原因数量 20→18；KL-120a 降格为
  K1 所需纯存储/读写载体，不声称解决既有 access-control deviation；
  UART0 在协议冻结前改为合成外部 IRQ non-claim；加入同 cfx cause 优先级；
  timer 增加完整范围条件收口任务；删除“软件无法发现 TLB 集合”的过度判断
  （`cfx_tlb_exist` 已提供集合存在位图）。
- 修订后交由同一 reviewer 做 delta review；结论为 **PASS**，确认首轮
  1-7 项均已闭合，未发现残留阻断或高风险。reviewer 全程只读，未修改文件。
