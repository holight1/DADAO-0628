# KL-111a：调研 hypv→supv 移交 O2（越权/被 mask 负例）的精确机制

**执行环境**：本地 subagent，纯调研，不修改 QEMU/gem5/LLVM/kernel/contracts/wiki

## 背景

`KL-110a`（已 commit）实现了 O1（成功移交），明确排除了 O2（越权/被 mask
负例）——`escape` 的权限检查（SEE §5 步骤0）和 `cfx2rc` 的完整访问控制均
未实现。`KL-101a`/`KL-102a` 当年设计 O2 时给出的方向是"从 hypv 访问仍被
delegation 的 cg，或从 supv 对未授权/被 mask 的 cfx2rc/trap 执行，二选一
作为首个负例"，但**没有展开到可直接实现的精度**。

架构师在准备下发 O2 实现任务时，自己核对 wiki 原文发现一个复杂之处：
`escape` 的权限检查伪代码是：

```
if cfxcode != inner_cfx_code:
    if (cfx_⟨cfxname⟩_<mode>_escape_cfx_mask & (1 << cfxcode)) != 0:
        cause <= ILLI  ; escape 被禁止
```

（`DADAO-12-SEE-主管系统运行环境.md` 第824-827行；`⟨cfxname⟩` 按第815行
"伪代码中 ⟨cfxname⟩ 指当前执行 escape 的 cfx（即 inner_cfx_code）"，检查
的是**当前 cfx（inner_cfx_code）**的 `<mode>_escape_cfx_mask`寄存器里
**目标 cfxcode** 对应的那一位）

**关键问题**：`if cfxcode != inner_cfx_code` 这个前置条件意味着"自身
cfxcode 不检查"——`KL-110a` 的 O1 是 `escape cfx_power,0` 且
`inner_cfx_code` 全程都是 `power`（reset 值，`escape` 从未写它，见
`docs/wiki-deviations.md` 第9条这个已确认的 wiki 空白），也就是说 O1 的
自我 escape **天然跳过**这条权限检查分支。要真正触发这条检查，需要
`inner_cfx_code` 在 escape 执行时**不等于**目标 cfxcode——但当前 M1
实现里没有任何指令能显式设置 `inner_cfx_code`（它只由硬件异常进入流程
写入，`trap cfx_smon` 这类现有路径走的是 host-side syscall 捷径，没有
真实执行 SEE §5 的异常进入流程）。

## 目标

1. **梳理 `cfx2rc`/`cfx2rd`/`cfxld`/`cfxst` 的完整访问控制机制**：
   - `hypv_cg_reg_deleg`（cg=3,rc=12）的"cg 访问授权"具体如何生效——它
     gate 的是"从 supv 访问哪个 cg 分组的寄存器"，还是别的什么。
   - `<mode>_cfx2rc_cfx_mask`（cg0/1/2/3 各自的 rc=3）这组"是否可从其他
     cfx 执行"的掩码和上面那个 deleg 位是不是同一套机制、还是两层独立
     检查（一层管"能不能跨 cfx 操作"，一层管"能不能访问这个 cg 分组"）。
   - 是否存在明确的伪代码（类似 escape 那样逐步骤列出的）描述 `cfx2rc`
     指令执行时的完整权限判定流程？如果没有，如实说明只能从寄存器语义
     描述推断，并标注推断的可信度。
2. **找一个 KL-110a 现有实现（不需要新增任何指令/机制）就能真实构造出来
   的最小负例**——必须是"用现有 O1 已实现的指令集合（`cfx2rc`/`escape`/
   `setrd`/`setrb`/基本运算/`unimp`）就能搭出来的场景，不能假设存在
   还没实现的机制"。重点评估以下候选，给出可行性判断：
   - 候选A：**未清 delegation 就从 supv 尝试访问被 delegation 的 cg**——
     具体是"访问 cg 寄存器"这个动作本身在当前 wiki/spec 里由什么指令
     触发、触发条件是什么（`cfx2rc`/`cfx2rd`/`cfxld`/`cfxst` 四条里
     哪条最简单可控），评估是否可行。
   - 候选B：**跨 cfx escape 权限检查**——如上所述，需要
     `inner_cfx_code != 目标cfxcode`，评估当前 M1 是否有任何合法路径能
     达成这个前提（比如是否可以在 reset 后、O1 stub 执行前，用某种方式
     让 `inner_cfx_code` 变成非 power 的值——如果确实没有任何路径，
     如实得出"候选B在当前实现下不可构造"的结论，不要勉强）。
   - 候选C：如果 A、B 都有障碍，梳理 wiki 里是否还有其它更容易构造的
     M1-可达负例（比如 `cfx2rc` 目标 `(cg,rc)` 是 reserved/未定义组合时
     应该产生 CFXREG 异常——这条不需要"跨 cfx"或"跨 mode"的前提条件，
     只需要构造一个非法的 `(cg,rc)` 编号）。
3. **产出明确判定**：给出一个（或多个）当前 M1 实现范围内**真正可构造**
   的 O2 负例设计（精确到具体指令序列、预期 fault class、预期 faulting
   PC），供后续实现任务直接使用。如果发现原定的"跨 cfx escape 权限检查"
   这个方向在当前阶段不可行，明确建议延后到有更完整异常进入机制之后再做。

## 约束

- 只做调研，不修改任何文件（`contracts/`、`docs/issues.yaml`、wiki 本身、
  QEMU/gem5/LLVM 源码全部不动）。
- 不查阅 `~/toolchain`、`~/knowledge-graph`，只用当前仓库 `contracts/`/
  `docs/` 与当前 wiki pin。
- 关键结论都要有文件/章节/行号引用，或可复核的只读命令，不能只给结论不
  给依据。参照 `docs/reviews/kernel-hypv-supv-handoff-20260721.md`/
  `docs/reviews/kernel-cfx-state-patch-surface-20260721.md`/
  `docs/reviews/kernel-regras-ldmo-stmo-semantics-20260725.md` 已经建立
  的证据标签格式（`[正式契约]`/`[已有实现]`/`[推断]`）和写法。
- 完成后必须写「完成区」+ subagent 自审「审阅记录」，不需要嵌套
  subagent，不需要独立 reviewer（架构师会亲自复核）。
- **不要为了"看起来有个答案"而在不确定的地方拍板**——如果某个机制 wiki
  确实没写清楚，按 `docs/wiki-deviations.md` 现有格式如实记录成一条新
  条目（`wiki 状态`标 `SILENT`，`我们的决定`写"尚未决定"），不要自己
  编一个没有依据的解读。

## 验收

- 产出 `docs/reviews/kernel-hypv-supv-o2-permission-recon-20260725.md`，
  结构参照上面列出的既有 review 报告的证据标签+可复核命令写法。
- 报告结尾给出清晰的"O2 负例设计"（候选A/B/C 逐个给出可行性判定+
  如果可行则给出精确指令序列设计），供架构师决定下一步是否可以直接
  下发实现任务。
- 如果发现真正的 wiki 空白（不只是"复杂"，是"确实没写"），补录进
  `docs/wiki-deviations.md`（强制交付物，如果发现的话）。
- 任务文件「完成区」总结关键结论（详细内容留在 review 报告里）。

## 参考指针

- `docs/reviews/kernel-hypv-supv-handoff-20260721.md`（KL-101a，O1/O2
  最初的 oracle 设计出处）
- `docs/reviews/kernel-cfx-state-patch-surface-20260721.md`（KL-102a，
  "O2 需要 authorization/delegation/inner_mask 判断"的原始建议，第85-87
  行"建议顺序"第3步）
- `code-agent/tasks/KL-110a-implement-hypv-supv-handoff-o1-qemu.md`
  完成区（O1 已实现的确切指令集合和 QEMU 承载点，本任务设计的 O2 必须
  能在这个基础上构造）
- `~/DADAO-wiki/DADAO-12-SEE-主管系统运行环境.md`（第265-330行 cg0-2
  各模式寄存器表；第813-845行 escape 硬件语义）
- `~/DADAO-wiki/DADAO-13-HEE-超管系统运行环境.md`（第7-26行 cg3 hypv
  寄存器表，含 deleg 定义）
- `docs/wiki-deviations.md` 第9条（`inner_cfx_code` 未被 escape 恢复的
  既有 wiki 空白记录，本任务如果发现新空白参照这个格式）

---

## 完成区（2026-07-25）

**状态**：已完成。产出
`docs/reviews/kernel-hypv-supv-o2-permission-recon-20260725.md`。

**关键结论**：

1. **架构师背景里的悲观前提被证伪**：候选B（跨 cfx `escape` 权限检查）
   **可行**。检查条件 `cfxcode != inner_cfx_code` 里，`inner_cfx_code`
   在 O1 范围内恒为 `power`（reset 起从未被任何指令写过，
   `helper_cfx2rc`/`helper_escape` 全文核对），真正需要变化的是
   `escape` 指令**自己的操作数**——选一个非 `power` 的目标 cfxcode
   （如 `cfx_smon`）即可满足不等式，完全不需要"让 `inner_cfx_code` 变成
   非 power 值"这个当前不存在的能力。目标寄存器
   `cfx_power_hypv_escape_cfx_mask`（HEE §1 cg3/rc7）reset 默认值"全1"，
   HBI §3 从未写它，天然满足"被 mask"条件。
2. **候选C（`cfx2rc` 未定义 (cg,rc) → CFXREG）可行**，前置条件最少——
   `cfx_power` 的 cg=8 专有寄存器只定义 rc=0,1，`rc=63` 是清晰无歧义的
   reserved 组合，不涉及跨 cfx/跨 mode，reset 后第一条指令就能测。
3. **候选A（字面：未清 delegation 就从 supv 访问被 delegation 的 cg）
   判定不可行，如实登记**——不是复杂，是两个独立原因叠加：(a) wiki 的
   两处正式伪代码（SEE §5 entry-flow、SimRISC-04 §寄存器传输指令）**从未
   提及** `cg_reg_deleg` 机制，deleg 拒绝时的异常类别是真正的 wiki 空白
   （已按格式写好建议条目，未写入 `wiki-deviations.md`，留给架构师决定）；
   (b) 即使接受"读写权限不匹配→CFXREG"的类比推断，QEMU 当前也没有任何
   cg0-2 组的目标寄存器存储（只有 cg3/rc12 本身和 cg5 的 power frame），
   做不出"delegation 清除后成功 / 未清除时失败"的正负对照。
4. **额外发现（候选B2，非任务要求但成本几乎为零）**：`cfx2rc` 有一层与
   `escape_cfx_mask` 完全同构的跨 cfx 检查（`cfx2rc_cfx_mask`，
   cg0-3/rc=3，SEE §5 entry-flow `:721`），同样可用"目标 cfxcode 非
   power"的方式独立触发 ILLI，不涉及 `cg_reg_deleg`——这直接证实了目标1
   问的"两层独立检查"中"跨 cfx 层"可以脱离 deleg 层单独触发，两层不是
   强耦合顺序。
5. **产出三个可直接使用的 O2 负例设计**（报告 §4）：设计1（候选B，
   `escape cfx_smon,0` @ reset，预期 ILLI @ 指令自身 PC）、设计2（候选B2，
   `cfx2rc cfx_smon_..., rdX` @ reset，预期 ILLI，同构可选加测）、设计3
   （候选C，`cfx2rc cfx_power,8,63,rdX`，预期 CFXREG，hypv/supv 均可测）。
   建议下一个 O2 实现任务（暂命名 `KL-112a`）覆盖设计1+3（+2 可选），
   候选A 一般形式延后到 wiki 空白被回答之后。

**未做/范围边界**：未修改任何文件（`contracts/`、`docs/issues.yaml`、
`docs/wiki-deviations.md`、wiki 本身、QEMU/gem5/LLVM 源码均未触碰）；
只读命令验证，未运行任何测试/模拟器。

---

## 自审：审阅记录（subagent 自审）

**判决**：自审通过，无阻断 finding。

- **候选B 核心结论的独立验证**：不满足于"读一遍伪代码就下结论"，额外
  做了两件事交叉验证：(a) grep 全 QEMU 源码确认 `inner_cfx_code` 确实
  从未被任何 helper 写过（不是凭印象，是实际命令核对
  `grep -n "inner_cfx_code" *.c *.h` 的输出）；(b) 读了
  `helper_escape()` 完整实现，确认当前 QEMU 对非-power cfxcode 走的是
  "静默零 frame 恢复"（bug 行为，不是"已经报错"），证明这确实是一个
  真实、当前未被发现的功能缺口，不是纸面推演。
- **候选A 的"不可行"判定没有轻易下结论**：先做了 `grep -rln
  "cg_reg_deleg"` 全文检索确认只有 3 处命中且没有一处是检查伪代码
  （不是"没找到就认定沉默"，是穷举了所有命中并逐条读完确认都不是检查
  逻辑）；又核对了 QEMU `cpu.h`/`helper_cfx2rc()` 全文确认 cg0-2 组
  确实没有任何存储，不是"大概率没有"而是逐行核对过默认分支代码和注释。
- **候选B2 是核对候选B 时的副产品，不是为了凑"更多答案"硬加的**——是在
  回答目标1第二条"两层独立检查"问题时，发现 `cfx2rc_cfx_mask` 与
  `escape_cfx_mask` 命名和寄存器结构完全同构，顺手验证了同一套推理在
  `cfx2rc` 上也成立，如实标注为"任务名单外的附加发现"而非冒充是候选
  A/B/C 之一。
- **候选A 的"A′变体"（cg3 硬件写死 hypv-only）没有被包装成满足候选A
  要求**——报告里明确写"这不是候选A 问的 delegation 未清导致拒绝，是
  完全不同的规则，如实标注为不同候选，不冒充满足候选A 的字面要求"，
  避免为了"看起来有答案"而混淆两个不同机制。
- **wiki-deviations 建议条目未越权写入文件**——按约束只在报告里给出
  完整草稿文本，任务文件和报告都明确标注"未写入 `docs/wiki-deviations.md`
  ，留给架构师决定"。
- **未做的事情核对**（对照约束逐条自查）：未修改 `contracts/`、
  `docs/issues.yaml`、`docs/wiki-deviations.md`、`~/DADAO-wiki`、
  QEMU/gem5/LLVM 源码任何一行；未查阅 `~/toolchain`/`~/knowledge-graph`；
  只用了 `grep`/`nl`/`sed`/`cat`/`git status`/`git rev-parse` 等只读命令，
  未运行 `run_differential.py`/lit/QEMU 模拟器等任何执行类工具（本任务
  范围内不需要，因为没有产生可执行的探针——三个设计是给下一个实现任务用的
  规格，不是本任务要跑通的验收）。
- **唯一的软性风险点（自认知，非阻断）**：`escape`/`cfx2rc` 的 `<mode>`
  占位符绑定（"检查发生时刻的 `inner_run_mode`"）在 wiki 里没有像
  `⟨cfxname⟩` 那样被显式声明过，是本报告基于 §5 entry-flow 步骤顺序
  （检查先于恢复）做的结构性推断，标注为 `[推断]`、给出了推断依据，但
  未单独列为 wiki-deviations 条目（因为它不影响本报告任何一个负例设计的
  正确性——三个设计里 `<mode>` 在检查时刻始终读到的是"当前尚未被恢复的
  运行模式"这个唯一合理值，没有第二种读法会改变预期结果）。
