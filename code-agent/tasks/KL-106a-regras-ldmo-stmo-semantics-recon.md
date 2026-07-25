# KL-106a：调研 `ldmo-ra`/`stmo-ra`（整 bank RA 访问指令）的完整语义

**执行环境**：本地 subagent，纯调研，不修改 QEMU/gem5/LLVM/kernel/contracts/wiki

## 背景

`KL-105a`（`docs/reviews/kernel-regras-save-restore-20260721.md`，架构师已独立
复核确认结论可信）判断：K1 阶段内核进程切换需要保存/恢复完整 `ra0-ra63`
（AEE 外部契约要求），M1 当前完全没有指令能做到这件事——`ldmo-ra`/`stmo-ra`
（整 bank RA↔内存访问）和 `rd2ra`/`ra2rd`（RA↔RD 单槽搬移）全部被
`contracts/isa/spec.md` §7 排除在 M1 之外（`ldo`/`sto` 不能替代，它们不访问
RA bank）。KL-105a 推荐的 K1 方向是**方案 A：重新纳入 `ldmo-ra`/`stmo-ra`**，
但这意味着要推翻一个既有架构决定。

架构师核实了这个排除决定的出处：`contracts/isa/spec.md` 里这条排除记录来自
项目最早的 spec 定稿提交（`8c6c0cc`，2026-06-29，wiki pin `13a414d`，
SimRISC 0.4.1）——是 **M1 范围定义从一开始就排除了这些指令**，不是后来从
"能用"退化成"被排除"。这个排除本身**不代表 wiki 里没有这些指令的完整定义**
——只代表当时的 M1 范围规划没有采纳它们。本任务要弄清楚：这两条指令在
**当前 wiki pin**（`9f378f4426e131903d60a208766086ae74a53c89`）里到底有没有
现成的、完整的指令语义定义（编码/槽位顺序/原子性/对齐/越界 fault），如果有，
K1 只是"启用一条既有指令"；如果没有，K1 需要走一次新的 spec 设计决策。

## 目标

1. **在当前 wiki pin 里定位 `ldmo-ra`/`stmo-ra` 的所有出现**（不只是排除记录，
   要找指令编码表、ISA 章节、任何提及这两个助记符的地方）。判断这两条指令
   是否有**完整**定义（不是只出现在一张指令列表里当占位符）：
   - 编码格式（哪个 instruction format，字段含义）
   - 单次访存操作的槽位数/宽度（"整 bank"具体是一次搬 64 槽还是分批）
   - 槽位顺序（`ra0` 对应内存里最低地址还是最高地址；是否与 DADAO 大端序
     约定有交互）
   - 引用计数字段（wiki 提到 RA 槽带 refcount，见
     `contracts/isa/spec.md §1.5`）在整 bank 搬移时如何处理——是否原样
     搬移，还是有特殊语义（比如清零/校验）
   - 原子性（整 bank 操作是否要求不可分割，还是允许被异常打断后恢复）
   - 对齐要求、越界/非法访问的 fault 行为
   - 是否与 `contracts/isa/spec.md` 现有 §1.5/§2.6.3/§2.7 的 RA 模型描述
     兼容或冲突
2. **确认这两条指令是否有 SimRISC 或更早期 wiki 版本的历史定义**（如果当前
   wiki pin 本身就没有完整定义，检查是否有更早的 wiki 版本/commit 曾经有过，
   帮助判断"这是要恢复历史设计"还是"这是从未被完整设计过的占位符"——但只读
   `~/DADAO-wiki` 的 git 历史，不修改任何文件）。
3. **产出明确的判定**：
   - 情形 A："wiki 当前 pin 已有完整语义定义，K1 只需要按 wiki 原文实现"
     ——如果是这个情形，把完整定义原文摘录整理成可直接指导后续实现任务的
     格式（编码表、伪代码，参照本项目其它 ISA 章节任务的引用规范）。
   - 情形 B："wiki 只有指令名称/排除记录，没有完整语义"——如果是这个情形，
     明确列出缺失的具体维度（上面第1条列的那些），这些是需要新的 spec
     decision 才能补全的，不能由实现任务自行拍板。
   - 不要在两者之间和稀泥——如果部分维度有定义、部分没有，逐项列清楚哪些
     有依据、哪些没有。

## 约束

- 只做调研，不修改任何文件（`contracts/`、`docs/issues.yaml`、wiki 本身、
  QEMU/gem5/LLVM 源码全部不动）。
- 不查阅 `~/toolchain`、`~/knowledge-graph`（按 KL-101a/102a/105a 已建立的
  惯例，只用当前仓库 `contracts/`/`docs/` 与当前 wiki pin，以及只读检查
  `~/DADAO-wiki` 的 git 历史）。
- 关键结论都要有文件/章节/行号引用，或可复核的只读命令（`grep -n`/`git log`
  等），不能只给结论不给依据。
- 明确区分"wiki 正式文本"、"contracts 仓库现有约定"和"你自己的推断/建议"，
  参照 KL-101a/102a 已经在用的 `[正式契约]`/`[已有实现]`/`[推断]` 标签约定。
- 完成后必须写「完成区」+ subagent 自审「审阅记录」，不需要启动嵌套 subagent，
  不需要独立 reviewer（架构师会亲自复核，参照 KL-101a/102a/105a 已经验证过的
  复核标准——会真的去核对你引用的每一处 wiki 原文行号）。

## 验收

- 产出 `docs/reviews/kernel-regras-ldmo-stmo-semantics-20260725.md`，结构
  参照 `docs/reviews/kernel-hypv-supv-handoff-20260721.md`/
  `docs/reviews/kernel-cfx-state-patch-surface-20260721.md` 的证据标签+
  可复核命令写法。
- 报告结尾要给出清晰的"情形 A / 情形 B"判定（或如果是混合情况，逐维度判定），
  供架构师和用户决定下一步是"直接照 wiki 实现"还是"先做一次 spec decision"。
- 任务文件「完成区」总结关键结论（详细内容留在 review 报告里）。

## 参考指针

- `docs/reviews/kernel-regras-save-restore-20260721.md`（KL-105a 原始判断，
  本任务是它的直接后续）
- `contracts/isa/spec.md` §1.5、§2.6.3、§2.7、§7（现有 RA 模型描述 + M1
  排除记录，第 63-80、208-240、947-960 行附近，架构师已核对过这些行号
  准确）
- `docs/reviews/kernel-hypv-supv-handoff-20260721.md`、
  `docs/reviews/kernel-cfx-state-patch-surface-20260721.md`（本项目 K1
  阶段已确立的调研报告格式和证据标签规范，照此写）
- `~/DADAO-wiki/`（当前 wiki pin 内容 + 可用 `git log`/`git show` 查历史
  版本，只读）
- `manifests/components.lock.toml`（wiki pin 具体 commit：
  `9f378f4426e131903d60a208766086ae74a53c89`）
