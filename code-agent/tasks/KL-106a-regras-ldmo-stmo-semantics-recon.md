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
- **如果调研结论是"情形 B"（wiki 只有排除记录、没有完整语义）**，必须在
  `docs/wiki-deviations.md` 里补一条正式条目（格式参照该文件已有的 7 条，
  `wiki 状态` 标 `SILENT`，`我们的决定` 部分写"尚未决定，等待 spec
  decision"，`状态` 标 `OPEN`）——这是本任务的强制交付物之一，不是可选项。
  如果调研结论是"情形 A"（wiki 已有完整定义），**不需要**补录到该文件
  （这属于"启用既有定义"而非"自定义决策"）。

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

## 完成区（2026-07-25）

**产出**：
- `docs/reviews/kernel-regras-ldmo-stmo-semantics-20260725.md`（完整调研，
  逐维度证据+行号引用+可复核命令）
- `docs/wiki-deviations.md` 补录第 8 条（`ldmo-ra`/`stmo-ra` 引用计数处理
  未定义），并清理了原"尚待补录"占位段落

**判定：混合，不是纯 A 或纯 B**。7 个维度里 6 个是**情形 A**（wiki 已有
完整定义或可通过与已被 `contracts/isa/spec.md` 采纳的同构指令
`ldmo-rb`/`stmo-rb`、RD `ldmo`/`stmo` 直接类比确定，标准与 contracts 现有
做法一致）：

- 编码格式：`op=0x67`(ldmo-ra)/`0x6F`(stmo-ra)，格式 `rrri`，字段
  `ha=raha,hb=rbhb,hc=rdhc,hd=immu6`（`SimRISC-00-指令系统设计.md:103-104`；
  `SimRISC-02-地址类指令.md:47-63`）
- 单次访存槽位数：1-63 个/条指令（不是一次搬 64 个），覆盖全部 64 槽需
  至少 2 条指令；`ra0` 未被专门排除
- 槽位顺序：寄存器序号递增 ↔ 地址递增，大端序，无 RA 专属例外
- 原子性：由 `contracts/isa/spec.md §2.7` 通用精确异常规则 + 固定 8 字节
  步长对齐检查的数学性质保证，无需额外设计
- 对齐/越界：8 字节对齐 MALIGN；`immu6=0`/越界 ILLI，与
  `ldmo-rb`/`stmo-rb` 同构
- 与既有 §1.5/§2.6.3/§2.7 RA 模型：无冲突

**唯一情形 B 的维度：引用计数（`bits[63:48]`）在整 bank 搬移时如何处理**
——`SimRISC-02-地址类指令.md:9-21` 的高16位行为分类表逐类列出了 RB/RA
相关指令（含单槽 `ra2rd`/`rd2ra`明确"全64位覆盖"），**唯独没有 RA↔内存
这一行**，且 wiki 从文件创建（2024-04-17）至今全部 21 次相关 commit 从未
补上，包括专门"统一高16位规则"的提交（`c1c4e44`）。历史核查确认这不是
回归——最初版本（`ldmra`/`stmra`，`a05261a`）连对齐/越界规则都没有，是
逐步补齐的，但引用计数这一项始终缺失。有类比证据（`ra2rd`/`rd2ra` 已定义
"全64位覆盖"）支持"应为全64位原样拷贝"，但这是类比不是显式条款。

**这个缺口恰好是 K1 最关心的点**：KL-105a oracle #1（全槽 round-trip）
明确要求"尤其不得丢 `bits[63:48]` 引用计数"，目前无 wiki 原文可以直接
支撑这条要求，需要 K1 在实现前由架构师/用户显式做一次 spec decision
（二选一：(a) 全64位原样拷贝 vs (b) 其它语义——目前无证据支持 (b)）。

**给 K1 的建议（非拍板）**：编码/对齐/越界/顺序可以直接形式化进
`contracts/isa/spec.md` 新增 §4.x（仿 §4.2 `ldmo-rb`/`stmo-rb` 写法）；
引用计数这一点需要先决策再写入 contracts。

## 审阅记录（subagent 自审）

- 逐条核对了报告里引用的每一处 wiki 行号（`SimRISC-00:89,103-104`；
  `SimRISC-02:9-21,44-46,47-63`；`SimRISC-01:12-13,63-64`；
  `DADAO-11-AEE:167-219`）与实际文件内容一致，未凭空编造行号
- 核对了 wiki pin：`~/DADAO-wiki` `git rev-parse HEAD` 与
  `manifests/spec.lock.toml:6` 锁定的 commit 完全一致，`git status` 干净
- 历史核查用了 `git log -S`/`git show` 而非猜测；发现的
  `pushra`/`popra`（已删除的 HTML 注释）是一个真实存在但与主结论方向不同
  的旁证，报告里明确标注它"排除了 push/pop 语义候选"而非"回答了引用计数
  问题"，没有过度引申
- 交叉核对了 `contracts/isa/spec.md` 现有对 `ldmo-ra`/`stmo-ra` 的两处引用
  （§2.6.3 通用规则、§7 排除记录），确认现有 contracts 对这两条指令没有
  正式编码记录（Appendix A 的 `0110-0xxx`/`0110-1xxx` 两行只到
  `jump`/`call`/`ret`，没有 `0x67`/`0x6F`），没有误报"contracts 已经有
  定义"
- 未修改 `contracts/`、`docs/issues.yaml`、wiki 本身、QEMU/gem5/LLVM 源码；
  只新增了 review 报告和 `docs/wiki-deviations.md` 的一条正式记录（任务
  要求的强制交付物）；未 commit
- 局限：引用计数缺口的"是否原样拷贝"判断留了两个选项给用户，没有代为
  拍板（按任务要求，这不是本任务能自行决定的范围）
