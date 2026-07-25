# KL-111a：hypv→supv 移交 O2（越权/被 mask 负例）精确机制调研

**日期**：2026-07-25　　**范围**：本地只读调研；未修改 QEMU、gem5、LLVM、
kernel、`contracts/`、`docs/issues.yaml`、`docs/wiki-deviations.md` 或
`~/DADAO-wiki`，未运行测试（仅执行只读 `grep`/`nl`/`sed` 命令）。本任务是
`KL-110a`（已 commit 的 O1 成功移交实现）的直接后续。

**证据标签**：`[正式契约]`=wiki 原文或 `contracts/` 现有约定；`[已有实现]`=
当前 `.work/source/qemu` 源码事实；`[推断]`=据此给出的判断，标注可信度。

**wiki pin 核对**：`manifests/spec.lock.toml:6` 锁定
`commit = "9f378f4426e131903d60a208766086ae74a53c89"`；`~/DADAO-wiki` 当前
`git rev-parse HEAD` = 同一 commit，`git status --short` 干净，无本地改动。

```bash
cd ~/DADAO-wiki && git rev-parse HEAD && git status --short
# → 9f378f4426e131903d60a208766086ae74a53c89 / (clean)
```

## 结论先行

**架构师在任务背景里的悲观前提被证伪**：候选B（跨 cfx `escape` 权限检查）
**在当前 M1 实现范围内确实可构造**，且不需要"让 `inner_cfx_code`
变成非 power 值"这个（不存在的）能力——只需要 `escape` 指令自身操作数选一个
**不等于** `inner_cfx_code`（在 O1 范围内恒为 `power`）的目标 cfxcode 即可，
这正是 `escape` 指令当前已支持的普通用法，不需要新指令/新机制。同构地，
`cfx2rc` 也有一层完全平行、同样可构造的跨 cfx 负例（`cfx2rc_cfx_mask`，
`(cg,rc)=(0/1/2/3, 3)`）——这正好回答了目标1第二条问的"两层独立检查"问题：
**确认是两层独立机制**，且都在当前 M1 实现下可构造。

**候选A（字面意义上的"未清 delegation 就从 supv 访问被 delegation 的
cg"）判定为当前不可清晰构造**：不是因为"复杂"，而是因为 (1) wiki 的两处
正式伪代码（SEE §5 异常进入流程、SimRISC-04 §寄存器传输指令）都**从未提及**
`cg_reg_deleg` 这个机制——它只在 HEE §1 的寄存器定义行和 HBI §3
引导代码注释里出现，从未被写入任何检查/异常路由的伪代码；(2) 即便忽略这层
沉默、直接类比"读写权限不匹配→CFXREG"，QEMU 里也没有任何 cg0-2 组的目标
寄存器存储（唯一已实现的 cg 组是 cg3/rc12 本身和 cg5 的 power frame）——
无法构造出一对"delegation 清除后成功 / 未清除时失败"的可比较负例。这是本次
调研发现的**真正 wiki 空白**，已按格式写好建议条目（见下）。

**候选C（`cfx2rc` 目标 `(cg,rc)` reserved/未定义 → CFXREG）判定为可构造**，
且是三个候选里前置条件最少的一个（不需要任何模式切换或跨 cfx，从 reset
起的第一条指令就能测）。

**总体建议**：下一个 O2 实现任务应实现并验收**候选B + 候选C**（外加与B同构的
`cfx2rc` 跨 cfx 负例，本报告称为"B2"）；候选A的一般形式建议延后，先走
wiki 空白记录流程；本报告末尾给出三个可直接使用的精确指令序列设计。

---

## 1. `cfx2rc`/`cfx2rd`/`cfxld`/`cfxst` 完整访问控制机制梳理（目标1）

### 1.1 `hypv_cg_reg_deleg`（cg=3,rc=12）"cg 访问授权"具体 gate 什么

`[正式契约]` `DADAO-13-HEE-超管系统运行环境.md:24`：

```
| 3 | 12 | hypv cg reg delegation | cfx_⟨cfxname⟩_hypv_cg_reg_deleg | 全1 | RW | cg访问授权，bit=0时允许supv访问。bit3固定为1 |
```

这是**每个 cfx 各自一份**的 64 位寄存器（cg3 属于该 cfx 自己，不是全局
共享——HEE §1 没有"global"前缀，对照 SEE §3 cg0-2 表格里明确标注
"`user global` 开头的寄存器为全局寄存器"的写法，`cg_reg_deleg` 没有这个
前缀，是 per-cfx 状态）。**其"位"按 cg 编号索引**（bit0=cg0、bit1=cg1、
bit2=cg2、bit3=cg3……），而不是按 cfxcode 索引——`DADAO-23-HBI-超管系统
二进制接口.md:32` 的注释直接证实了这个读法："清除各 cfx 的 cg reg
delegation，允许 supv 访问所有 cg（cg3 固定禁止，bit3 硬件忽略写入）"，
这里"cg3 固定禁止"对应的正是寄存器自身"bit3固定为1"的硬件行为——bit 索引
和 cg 编号是同一个数轴。

`[正式契约]` `DADAO-22-SBI-主管系统二进制接口.md:701`（唯一一处给出具体
生效场景的正文）："`power_ctrl` 寄存器的默认访问权限为 hypv；HBI 引导代码
（§3）将 `cfx_power_hypv_cg_reg_deleg` 设为 0 以委托给 supv，因此 supv
可直接通过 `cfx2rc`/`cfx2rd` 操作该寄存器。"——`power_ctrl` 是 cfx_power
的 cg=8（专有寄存器）成员（`DADAO-12-SEE-主管系统运行环境.md:637`），
这句话证实：**deleg 位 gate 的是"从 supv 通过 `cfx2rc`/`cfx2rd` 访问某个
cfx 的某个 cg 分组寄存器"这个动作整体**，不是访问单个 (cg,rc) 的细粒度控制。

**关键发现（wiki 沉默，见 §3）**：以上是 wiki 里能找到的**全部**关于
`cg_reg_deleg` 的文字——只有 (a) 寄存器本身的定义行，(b) HBI 的一句引导
代码注释，(c) SBI 这一句"生效后允许访问"的正面例子。全文 grep 找不到第四
处提及：

```bash
cd ~/DADAO-wiki
grep -rln "cg_reg_deleg\|cg reg delegation" *.md
# → DADAO-13-HEE-超管系统运行环境.md（定义）
#   DADAO-22-SBI-主管系统二进制接口.md（唯一正面用例）
#   DADAO-23-HBI-超管系统二进制接口.md（HBI §3 引导代码 ×12 + 该行注释）
```

**没有任何一处**说明：deleg 位=1（未委托/仍被拒绝）时，`cfx2rc`/`cfx2rd`
应该产生什么异常类别（CFXREG？ILLI？还是别的）、检查发生在指令执行的哪个
阶段、是否与 §1.3 的"读写权限不匹配→CFXREG"通用条款是同一件事。详见 §3。

### 1.2 `<mode>_cfx2rc_cfx_mask`（cg0/1/2/3 各自 rc=3）与 deleg 位的关系

`[正式契约]` SEE §3 cg0-2 的寄存器表（`DADAO-12-SEE-主管系统运行环境.md`
`:277`/`:301`/`:321`，cg3 见 `DADAO-13-HEE-超管系统运行环境.md:15`）：

```
| 0 | 3 | user cfx2rc cfx mask | cfx_⟨cfxname⟩_user_cfx2rc_cfx_mask | 全1 | RW | cfx2rc 指令是否可从其他 cfx 执行，0=可，1=不可。自身 cfxcode 对应位硬件忽略 |
| 1 | 3 | jail cfx2rc cfx mask | cfx_⟨cfxname⟩_jail_cfx2rc_cfx_mask | 全1 | RW | 同上 |
| 2 | 3 | supv cfx2rc cfx mask | cfx_⟨cfxname⟩_supv_cfx2rc_cfx_mask | 全1 | RW | 同上 |
| 3 | 3 | hypv cfx2rc cfx mask | cfx_⟨cfxname⟩_hypv_cfx2rc_cfx_mask | 全1 | RW | 同上 |
```

`[正式契约]` 这组寄存器**确实在正式的异常进入流程伪代码里被引用**——
`DADAO-12-SEE-主管系统运行环境.md:711-738`（§5 异常进入流程，"1. 确定核芯
功能扩展"）：

```
if instruction ∈ {TRAP, ESCAPE, CFXLD, CFXST, CFX2RD, CFX2RC}:
    if cfxcode ∈ {7..14, 19..61}:
        cause <= ILLI                          ; reserved → ILLI
        ...
    elif cfxcode != inner_cfx_code and cfx_⟨cfxname⟩_<mode>_<instr>_cfx_mask & (1 << cfxcode):
        cause <= ILLI                          ; 指令类型 cfx mask 禁止 → ILLI
        ...
    elif instruction ∈ {CFX2RD, CFX2RC}:
        ; cause 已由硬件执行阶段确定（CFXREG），此处仅路由
        temp_cfx_code <= cfxcode
    ...
```

`⟨cfxname⟩` 在这段（entry-flow 全局）的绑定虽未像 escape 那样显式声明，
但 `<instr>_cfx_mask` 命名与 `escape_cfx_mask`（见下）、`trap_cfx_mask`
完全同构，而且 §5 步骤7"保存现场"用的是 `inner_run_mode`/`inner_cfx_mask`
（当前架构状态，而非 target 的状态），所以 `⟨cfxname⟩` 只能读作
**当前正在执行该指令的 cfx（`inner_cfx_code`）**——与 escape 明确声明的
绑定方式（`DADAO-12-SEE-主管系统运行环境.md:815`："伪代码中 ⟨cfxname⟩
指当前执行 escape 的 cfx（即 `inner_cfx_code`）"）是同一套记号约定。

**判定：这是与 deleg 位完全独立的第二层检查**。`cfx2rc_cfx_mask` gate 的
是"我（`inner_cfx_code`，当前正在执行的 cfx）能不能对**另一个 cfx**
（cfxcode 操作数指定的目标）发起 `cfx2rc` 这个动作"——是**跨 cfx 执行权限**
（与运行模式无关，是 cfx 之间的隔离墙）；`cg_reg_deleg` gate 的是"**supv
模式**能不能访问某个 cfx 的某个 cg 分组寄存器"（与是否跨 cfx 无关，是
运行模式之间的特权墙，专门解决 hypv 保留哪些寄存器组不给 supv 用）。两者
是正交的两道闸门，`§1.1` 找到的所有 wiki 文字都没有说这两道闸门谁先谁后、
或者是否两个都要通过——但由于 deleg 位从未出现在**任何**检查伪代码里（同
`§1.1` 结论），这个"先后顺序"问题本身也无法回答，只能确认"是两层独立
机制"这一半的问题（目标1第二条问的原话），"是否两个都要通过"是 wiki 沉默
的一部分。

**观察（非阻断，仅记录内部文档结构提示）**：`§5` 异常进入流程把 `ESCAPE`
也列进了"`if instruction ∈ {TRAP, ESCAPE, CFXLD, CFXST, CFX2RD, CFX2RC}`"
这个受 `<instr>_cfx_mask` 通用检查覆盖的指令集合（`:712`），而 `escape`
自己的 §5 退出流程步骤0（`:824-827`）又单独把同一条规则（`escape_cfx_mask`
检查）重新写了一遍。这两段文字描述的是**同一条规则**（同一个寄存器、同一个
触发条件、同一个后果），不是两条独立规则——`:738` 的注释"ESCAPE（非
reserved）：由异常退出流程处理，不在此处路由"说明入口流程的这个分支对
escape 只走到"reserved cfxcode → ILLI"这一步，真正的 mask 检查逻辑由 §5
自己的步骤0 承接，两处文字是同一条硬件行为的两次描述（一次在"指令入口"总览
里提前预告，一次在 escape 自己的专门章节里逐步展开），不影响候选B 的设计
结论。

### 1.3 是否有 `cfx2rc` 执行时完整权限判定流程的逐步骤伪代码

`[正式契约]` **没有**类似 `escape` 那样从 0 到 4 逐步编号的独立伪代码块。
`cfx2rc`/`cfx2rd` 的语义描述分散在两处：

1. `SimRISC-04-系统类指令.md:72-103`（§寄存器传输指令，指令语法+一句话
   异常规则）：
   ```
   读写不存在的 cfx_<cfxname>_cghb_rchc 组合时触发 CFXREG 异常；
   cfx_<cfxname> 为 reserved 核芯功能扩展（7-14、19-61）时触发 ILLI 异常；
   读写权限不匹配时，触发非法核芯功能扩展寄存器访问异常（CFXREG）。
   ```
   （`:87`，三个分句对应三种不同触发条件，但都只有"结论"没有"检查顺序/
   检查时机"这层过程描述）
2. `DADAO-12-SEE-主管系统运行环境.md:711-738`（§5 异常进入流程，前面引用
   过的那段）——这段是**跨 6 种指令共用的路由总览**（reserved 检查 +
   `<instr>_cfx_mask` 检查 + 各指令类型分支），不是 `cfx2rc` 专属的逐步骤
   流程；线733 "cause 已由硬件执行阶段确定（CFXREG），此处仅路由"这句话
   **明确承认** CFXREG 的判定逻辑本身（哪些 (cg,rc) 存在、哪些"权限不匹配"）
   发生在这段伪代码**之外**、由某个未展开的"硬件执行阶段"决定——即 wiki
   自己承认这部分留了一个未展开的黑盒。

**判定**：`cfx2rc`/`cfx2rd` **没有** `escape` 那种粒度的完整伪代码，只有
"结论性规则 + 一处入口路由总览"。第三个分句"读写权限不匹配"没有说明它和
`cg_reg_deleg`/`<mode>_cfx2rc_cfx_mask` 是不是同一件事——如 `§1.2` 已指出，
`<mode>_cfx2rc_cfx_mask` 已经有独立、明确的触发条件（"cause<=ILLI"，不是
CFXREG），所以"读写权限不匹配→CFXREG"更可能指的是**寄存器自身"访问"列**
（RO/RW/HW/WO）的读写方向不匹配（比如对 `cfx_power_ctrl`——WO——执行
`cfx2rd` 读取，或对某个 HW-only 字段如 `excp_cause_id` 执行 `cfx2rc`
写入），而不是 `cg_reg_deleg` 的委托状态。**这是一个可信度中等的
`[推断]`**——没有反例，但也没有正面文字确认；`cg_reg_deleg` 拒绝时的真实
异常类别仍然是空白（见 §3 的 wiki-deviations 建议条目）。

### 1.4 `cfxld`/`cfxst` 简述（目标1提到但非本任务重点）

`[正式契约]` `cfxld`/`cfxst` 访问的是 cfx **内部 SRAM 块**（cg7 控制），
不经过 cg/rc 寻址，走的是完全不同的 `CFXMEM` 异常路径（`SimRISC-04:105-
109`；`DADAO-12-SEE-主管系统运行环境.md:378-382`）。它们与 `cfx2rc`/
`cfx2rd` 的权限模型不是同一套，且 `contracts/isa/spec.md:992` 已把两条
都列入 M1 Excluded、`KL-110a` 也未启用——本任务不深挖，仅确认它们不适合
用来构造 O2 负例（候选清单里也没有把它们列为主选项）。

---

## 2. 候选评估（目标2）

### 2.1 候选A：未清 delegation 就从 supv 访问被 delegation 的 cg

**判定：字面形式当前不可清晰构造，判定为不可行（不是不能想象，是没有可
执行的正/负对照）**。理由：

1. **触发指令确认**：`cfx2rc`（写）是四个候选指令里"访问 cg 寄存器"这个
   动作最简单可控的一个——`cfxld`/`cfxst` 走 CFXMEM/SRAM 路径（§1.4）
   与"cg 分组访问"完全无关；`cfx2rd`（读）在 M1 仍是 Excluded
   （`contracts/isa/spec.md:992`），当前 QEMU 连解码都没有（`KL-110a`
   只启用了 `cfx2rc`/`escape`，`cfx2rd` 仍是 `0x72` 未译码）。所以唯一
   可用的触发指令是 `cfx2rc`。
2. **wiki 没有说清楚检查机制**（`§1.1`/`§1.3` 已证实）：deleg 位从未出现
   在任何检查伪代码里，"读写权限不匹配→CFXREG"这句通用条款与 deleg 位的
   关系是 `[推断]`，不是确证。即使接受这个推断，也没有文字说明检查**在
   哪个阶段**发生（是 entry-flow §5 的 `<instr>_cfx_mask` 检查之后单独
   一步？还是"硬件执行阶段"隐含在 CFXREG 判定里，和"不存在的 (cg,rc)"
   共用同一条 CFXREG 触发路径？）。
3. **QEMU 无目标寄存器存储**（`[已有实现]`，
   `.work/source/qemu/target/dadao/cpu.h:78-92` 全文核对）：`CPUArchState`
   只有 `inner_run_mode`/`inner_cfx_code`/`inner_cfx_mask`/
   `cfx_power_frame`（3 个 field）/`cfx_hypv_cg_reg_deleg[64]`——**没有
   任何 cg0/cg1/cg2/cg4/cg6/cg7 的寄存器存储，对任何 cfx 都没有**。
   `helper_cfx2rc()`（`.work/source/qemu/target/dadao/helper.c:118-164`）
   只识别两种 `(cg,rc)` 组合：`(3,12)`（deleg 数组本身）和
   `(63,5,{0,1,3})`（`cfx_power` 的 frame）；**其它任何组合，包括所有
   cg0-2 的寄存器，一律静默 no-op**（`:159-163` 注释明确写"not reachable
   by the HBI §3 handoff stub"）。这意味着：即使我们不管 deleg 检查该走
   哪条异常，也**没有一个真实存在的"成功写入"目标**可以对照——写一个
   cg0 寄存器，delegation 清或不清，QEMU 今天都是同一个结果（静默
   no-op），做不出"正例 vs 负例"的差分。

**结论**：候选A 需要先补齐（a）至少一个 cg0-2 寄存器的真实存储 + （b）
一次 wiki 空白的 spec-decision（deleg 拒绝时的异常类别），这两件事本身
就是下一个实现任务的核心工作量，不是"用现有 O1 实现搭"就能做出来的——如实
判定**不可行**，不勉强凑一个"看起来能测但其实测不出区别"的场景。

**候选A 的一个更小、确实可构造的近亲（记为 A′，供参考，非任务要求的
候选）**：`HEE §1` 第9行（`DADAO-13-HEE-超管系统运行环境.md:9`）单独给出
一条**与 delegation 机制完全独立**的规则："这部分寄存器的读写，只有当前
运行环境是 hypv 时才能进行，否则触发非法指令异常"——即 **cg3 本身**
（不是 cg0-2）被硬件写死为"仅 hypv 可访问"，与 delegation 状态无关（回忆
`cg_reg_deleg` 的 bit3 本身也被硬件强制为1，两者互相印证：cg3 是唯一被
彻底排除在委托机制之外的分组）。这条规则是**显式文字**（不是推断），且
`cfx_hypv_cg_reg_deleg` 寄存器本身（cg3/rc12）目前已有 QEMU 存储（O1
新增的 `cfx_hypv_cg_reg_deleg[64]` 数组）。也就是说，从 supv 执行
`cfx2rc cfx_power_hypv_cg_reg_deleg, rdX`（读写 cg3 自己的寄存器）应该
无条件触发 ILLI——但这**不是**候选A 问的"delegation 未清导致访问被拒"，
是完全不同的"cg3 分组硬件写死 hypv-only"规则，如实标注为不同候选，不
冒充满足候选A 的字面要求。

### 2.2 候选B：跨 cfx `escape` 权限检查

**判定：可行，且架构师背景描述里的前置假设是错误的，予以更正**。

背景原话："当前 M1 实现里没有任何指令能显式设置 `inner_cfx_code`……要真正
触发这条检查，需要 `inner_cfx_code` 在 escape 执行时不等于目标 cfxcode"——
这个说法把检查条件 `cfxcode != inner_cfx_code` 理解成了"需要让
`inner_cfx_code` 变成别的值"，但实际上 `inner_cfx_code` 在这个不等式里
是**固定不变的那一边**（O1 范围内它从 reset 起恒为 `power`(63)，见下方
证据），真正需要变化的是 `escape` **指令自己的操作数**——只要选一个不是
`power` 的目标 cfxcode（比如 `cfx_smon`），不等式天然成立，完全不需要
`inner_cfx_code` 本身发生任何变化。

**证据链**：

1. `[已有实现]` `inner_cfx_code` 从 reset 到 O1 结束，全程没有任何写入点：
   ```bash
   grep -n "inner_cfx_code" .work/source/qemu/target/dadao/*.c .work/source/qemu/target/dadao/*.h
   ```
   命中：`cpu.h:85`（字段声明）；`cpu.c` 的 reset 路径把它初始化为
   `DADAO_CFX_CODE_POWER`（HBI §3 reset 初态，`KL-101a` 已核对）；
   `helper_cfx2rc()`/`helper_escape()` 全文都**不写** `inner_cfx_code`
   （`helper.c:200-206` 的注释明确记录了这一点，对照
   `docs/wiki-deviations.md` 第9条）。**没有任何指令能写它**这个前提本身
   是对的，但它不影响候选B——因为候选B 不需要写它。
2. `[正式契约]` §5 退出流程步骤0（`DADAO-12-SEE-主管系统运行环境.md:
   824-827`）：
   ```
   if cfxcode != inner_cfx_code:
       if (cfx_⟨cfxname⟩_<mode>_escape_cfx_mask & (1 << cfxcode)) != 0:
           cause <= ILLI
   ```
   `⟨cfxname⟩` = `inner_cfx_code`（`:815` 显式声明）= `power`（O1 范围内
   恒定）；`<mode>` = 执行 `escape` 时的 `inner_run_mode`（检查发生在步骤
   1-2 恢复 mode/mask **之前**，此时 `inner_run_mode` 还是 escape 前的当前
   值——`O1` 场景下是 `hypv`，reset 初态，`KL-101a`
   已核对）。所以完整寄存器名是
   `cfx_power_hypv_escape_cfx_mask`——`DADAO-13-HEE-超管系统运行环境.md:19`
   定义了这个寄存器：`cg=3, rc=7`，**初始值"全1"**。
3. `[已有实现]` HBI §3 的 12 条 delegation 清除 + 3 条 power frame 写入
   （`DADAO-23-HBI-超管系统二进制接口.md:29-45`）**没有一条写这个寄存器**
   （`(cg,rc)=(3,7)` 从未出现在 HBI §3 原文，`KL-110a` 完成区也确认 O1
   实现只处理 `(3,12)` 和 `(63,5,{0,1,3})` 两组）——所以
   `cfx_power_hypv_escape_cfx_mask` 在 O1 之后仍保持 reset 默认值"全1"，
   即**对所有非自身 cfxcode 位均为1**（"escape 指令是否可从其他 cfx
   执行，0=可，1=不可"，`:19`）。
4. 结论：从 reset 起，只要在 hypv 模式下执行 `escape cfx_<非power>, N`
   （任选一个非 reserved 的 cfxcode，如 `cfx_smon`=2），`cfxcode(2) !=
   inner_cfx_code(63)` 恒成立，`cfx_power_hypv_escape_cfx_mask` 位2
   恒为1（从未被清除）→ 按 wiki 步骤0 应触发 ILLI。**这个场景只用
   `escape` 一条已实现指令、不需要任何前置状态搭建、甚至不需要先跑完
   O1 的 12 条 delegation 清除**——是三个候选里对"现有实现"依赖最少的
   一个。

`[已有实现]` 交叉核对当前 QEMU 是否已经（哪怕意外）实现了这条检查：
`helper_escape()`（`.work/source/qemu/target/dadao/helper.c:169-214`）
完全没有步骤0——直接进入 `if (cfxcode == DADAO_CFX_CODE_POWER) {...} else
{prev_run_mode=USER; prev_cfx_mask=0; cause_ip=0;}`，即目标 cfxcode 非
power 时，**当前实现会静默用全零 frame 完成"恢复"并跳到 pc=0**（错误但
不会报错的行为），这正是 O2 需要堵住的缺口，与 `KL-110a` 完成区"escape
mask 权限检查（SEE §5 步骤0）明确不实现（O2 范围）"的自述一致。

### 2.3 候选C：`cfx2rc` 目标 `(cg,rc)` reserved/未定义 → CFXREG

**判定：可行，三个候选里前置条件最少**。

`[正式契约]` `SimRISC-04-系统类指令.md:87`："读写不存在的
`cfx_<cfxname>_cghb_rchc` 组合时触发 CFXREG 异常"——不涉及跨 cfx 或跨
mode，只需要一个合法 cfxname + 不存在的 (cg,rc)。

`[正式契约]` `cfx_power` 的专有寄存器表（`DADAO-12-SEE-主管系统运行环境.md
:634-637`，§4"专有寄存器设计"，cg=8）：

```
| 8 | 0 | power pending | cfx_power_pending | 0 | RW | ... |
| 8 | 1 | power ctrl    | cfx_power_ctrl    | 0 | WO | ... |
```

`cfx_power` 的 cg=8 只定义了 rc=0,1 两个寄存器；`rc=2..63` 在这个 cg 组
里**没有定义**——是"存在的 cg（因为 cg8 本身被 cfx_power 使用）+ 不存在的
rc"这种最清晰、无歧义的 reserved 组合，不依赖"这个 cg 编号本身是否合法"
这种更容易起争议的边界情况。

`[已有实现]` `helper_cfx2rc()` 目前对这种组合的处理：不匹配
`(3,12)`/`(63,5,{0,1,3})` 两种硬编码模式，落入
`helper.c:159-164` 的默认分支——**静默 no-op，不产生任何异常**，与 wiki
要求的 CFXREG 不符，是待实现的 O2 缺口。

`[已有实现]` 该测试**不依赖任何模式切换**——可以在 reset 后、hypv 模式下
直接作为第一条指令执行（因为目标 cfxcode 是 `power` = `inner_cfx_code`，
不受 §5 entry-flow 的 `cfx2rc_cfx_mask` 跨 cfx 检查约束，见 `§1.2`），
也可以在 O1 handoff 之后从 supv 模式执行（cfx2rc 对自身 cfx 的合法性判断
与运行模式无关，wiki 没有给出与运行模式相关的额外限制条款）——是唯一
一个"跨模式都成立"的候选，验收覆盖面最大。

### 2.4 附加发现：候选B 的 `cfx2rc` 同构版本（"B2"）

`§1.2` 已证实 `cfx2rc_cfx_mask`（cg0-3/rc=3）与 `escape_cfx_mask` 是
完全同构的机制（同一套 `<instr>_cfx_mask` 通用规则的两个实例）。用与
候选B 完全相同的推理：从 hypv 模式对**非自身**cfx 执行 `cfx2rc`（比如
`cfx2rc cfx_smon_user_global_cfx_mask, rd2`，任选 smon 内一个 (cg,rc)），
`cfxcode(2) != inner_cfx_code(63)`，检查
`cfx_power_hypv_cfx2rc_cfx_mask`（cg3/rc3，reset="全1"，HBI §3 从未写它）
位2 = 1 → 按 §5 entry-flow（`:721`）应触发 ILLI。这是一个**额外的、同样
可行**的负例，直接回答了目标1第二条问题里"是否两个都要通过"这个子问题的
一半——至少可以确认：**跨 cfx 执行权限（`cfx2rc_cfx_mask`）这一层，脱离
`cg_reg_deleg` 也能独立触发，两层不是"必须先过 deleg 才检查 cfx_mask"
这种强耦合顺序**（因为这个测试完全不涉及 deleg 位，直接命中 cfx_mask 层
就已经产生 ILLI）。这个候选不在任务列出的 A/B/C 名单里，作为交叉验证的
副产品列出，供架构师参考是否并入 O2 实现任务。

---

## 3. wiki 空白发现（建议条目，未写入 `docs/wiki-deviations.md`）

按任务约束，本任务不修改 `docs/wiki-deviations.md`，以下是建议新增条目的
完整内容草稿，供架构师决定是否采纳：

```
### 10. `cg_reg_deleg` 委托状态被拒绝时的异常类别与检查时机未定义（KL-111a，2026-07-25）

- **wiki 状态**：SILENT（寄存器语义"bit=0 时允许 supv 访问"有明确定义，
  且有一个"委托后允许访问"的正面用例，唯独"未委托/仍被拒绝时应该产生什么
  异常、检查发生在指令执行的哪个阶段"全文未提及）
- **wiki 原文引用**：`DADAO-13-HEE-超管系统运行环境.md:24`（寄存器定义）；
  `DADAO-22-SBI-主管系统二进制接口.md:701`（唯一正面用例，"因此 supv
  可直接通过 cfx2rc/cfx2rd 操作该寄存器"，只说委托后能访问，不说委托前
  访问会怎样）；`DADAO-23-HBI-超管系统二进制接口.md:32`（HBI 引导代码
  注释，同样只描述"清除委托"这个动作，不描述不清除的后果）。全文 grep
  `cg_reg_deleg`/`cg reg delegation` 只有这 3 处命中，`DADAO-12-SEE-
  主管系统运行环境.md` 的两处正式伪代码（§5 异常进入流程
  `:678-811`、SimRISC-04 §寄存器传输指令 `:72-103`）均未提及这个寄存器，
  与同一文档里 `escape_cfx_mask`/`<instr>_cfx_mask` 这组"跨 cfx 执行权限"
  机制形成对比——后者被写入了正式检查伪代码（`:721`），前者完全没有。
- **我们的决定**：尚未决定。
- **理由**：`KL-111a`（本报告）在设计 O2 负例时发现，候选A
  （"未清 delegation 就从 supv 访问被 delegation 的 cg"）无法构造出一个
  wiki 有依据的精确负例——SimRISC-04:87 的"读写权限不匹配→CFXREG"是唯一
  可能相关的条款，但它与 `cg_reg_deleg` 的关系是 `[推断]`，不是 wiki
  显式陈述，且这条条款本身更可能指向寄存器"访问"列（RO/RW/HW/WO）的
  读写方向不匹配，而不是委托状态。
- **影响范围**：O2 实现任务的候选A 范围（cg0-2/cg4/cg6/cg7 的 supv
  委托访问控制）——建议 O2 优先实现候选B/C（本报告已证实可行、有明确
  wiki 依据），候选A 的一般形式延后到这条空白被回答之后。
- **状态**：OPEN——待架构师/用户决定是否需要 wiki 团队澄清，或项目自行
  拍板（如"deleg 拒绝统一按 CFXREG 处理，等同§1.3三个分句的第三句"）。
- **详见**：`docs/reviews/kernel-hypv-supv-o2-permission-recon-20260725.md`
  §2.1
```

---

## 4. O2 负例设计（目标3，供后续实现任务直接使用）

以下三个设计均只使用 `escape`/`cfx2rc`/`setrd`/`setrb`/基本运算/`unimp`
（已实现指令），不需要新增任何指令或解码规则。三个都建议纳入下一个 O2
实现任务（暂命名 `KL-112a`）的验收范围；候选A 的一般形式不在本清单内
（判定不可行，见 §2.1）。

### 设计1（推荐主负例）：候选B——跨 cfx `escape` 权限检查

- **前置条件**：无需 O1 handoff 的 12 条 delegation 清除——reset 直接
  测（`inner_run_mode=hypv`, `inner_cfx_code=power`, PC 落在
  `cfx_power_hypv_excp_vector` 即 `0x00100000`，`KL-101a` 已核对的
  reset 初态）。
- **指令序列**：reset vector 处放一条指令：
  ```
  escape  cfx_smon, 0        ; cfxcode=2 != inner_cfx_code=63(power)
  ```
  （`cfx_smon` 只是示例，任何非 reserved、非 power 的 cfxcode 都成立；
  `imms18=0` 任意，因为按 wiki 步骤0 检查失败时根本不会执行到步骤4）
- **wiki 依据**：`DADAO-12-SEE-主管系统运行环境.md:824-827`（步骤0）+
  `:815`（`⟨cfxname⟩` 绑定）+ `DADAO-13-HEE-超管系统运行环境.md:19`
  （`cfx_power_hypv_escape_cfx_mask` 定义，reset="全1"）。
- **预期 fault class**：ILLI（wiki 步骤0 明文），QEMU 侧建议复用现有
  `EXCP_ILLI`/退出码 `0x82` 惯例（`unimp`、非法解码默认分支均已用这个
  约定，`.work/source/qemu/target/dadao/cpu.c` 的 `default:` 分支）——
  这是本报告给出的建议，非 wiki 强制，留给 O2 实现任务定夺是否需要
  区分独立退出码。
- **预期 faulting PC**：`escape` 指令自身的地址（同步异常，"触发异常的
  指令地址"，`DADAO-12-SEE-主管系统运行环境.md:703`）——本例中即
  `0x00100000`。
- **可观察断言**：`inner_run_mode` 应保持 `hypv`（不应变成 `supv`）；
  不应有 `escape cfx=... mode X->Y` 的 trace 行（因为步骤1-4 不应执行）；
  与 `KL-110a` 已验证的正例（`escape cfx_power,0` 成功落地 supv_entry）
  形成对照，用 KL-110a 同款"读回 marker + 退出码编码比对结果"方法即可
  复用现成探针框架（`gen_kl110a_o1_probe.py` 的模式）。

### 设计2：候选B2——跨 cfx `cfx2rc` 权限检查（与设计1 同构，可选加测）

- **指令序列**（同样 reset 后立即可测）：
  ```
  cfx2rc  cfx_smon_user_global_cfx_mask, rd2   ; 目标 cfxcode=smon(2) != inner_cfx_code=63
  ```
  （具体 (cg,rc) 目标寄存器不重要，只要落在 `cfx_smon` 名下、不是 reserved
  即可；`rd2` 内容也不重要，因为检查应在写入前失败）
- **wiki 依据**：`DADAO-12-SEE-主管系统运行环境.md:711-728`（§5 entry-flow
  的 `<instr>_cfx_mask` 通用检查，`<instr>=cfx2rc`）+ 寄存器定义
  （`:277`/`:301`/`:321`/`DADAO-13-HEE:15`）。
- **预期 fault class/PC**：同设计1（ILLI，faulting PC=该 `cfx2rc`
  指令自身地址）。
- **状态**：本报告新识别的附加负例，不在任务列出的 A/B/C 名单内，供
  架构师决定是否并入 O2 验收范围（建议纳入，因为它直接验证了 §1.2 的
  "两层独立检查"结论中"跨 cfx 层"这一半，成本几乎为零——复用设计1同一套
  探针框架，只换一行指令）。

### 设计3：候选C——`cfx2rc` 未定义 `(cg,rc)` → CFXREG

- **前置条件**：无——可在 hypv（reset 后）或 supv（O1 handoff 之后）
  任一模式测试，两次都应该产生相同结果（本报告未发现任何 wiki 条款说
  CFXREG 的触发与运行模式相关）。
- **指令序列**：
  ```
  cfx2rc  cfx_power, 8, 63, rd2   ; cg=8 是 cfx_power 的合法 cg（rc=0,1 已定义），rc=63 未定义
  ```
- **wiki 依据**：`SimRISC-04-系统类指令.md:87`（"读写不存在的
  `cfx_<cfxname>_cghb_rchc` 组合时触发 CFXREG 异常"）+
  `DADAO-12-SEE-主管系统运行环境.md:634-637`（`cfx_power` cg=8 专有寄存器
  表，只定义 rc=0,1）。
- **预期 fault class**：CFXREG（wiki 明文，异常原因编码 `1<<2`，
  `DADAO-12-SEE-主管系统运行环境.md:404` 等多处异常原因表一致）。
- **预期 faulting PC**：该 `cfx2rc` 指令自身地址。
- **需要 O2 实现任务额外决定的点（非本任务范围，如实标注）**：当前
  QEMU 的 `EXCP_*` 枚举（`cpu.h:8-12`）没有 `EXCP_CFXREG`，退出码惯例
  目前只有 `0x81`(MALIGN)/`0x82`(ILLI 兜底)/`0x83`(UNDI)/`0x84`(RASOF)/
  `0x85`(RASUF)——CFXREG 是否新增独立退出码（比如 `0x86`，延续既有编号
  规律）还是复用 `0x82` 兜底，是 O2 实现任务需要做的一个小型项目惯例
  决定，不是 wiki 空白（wiki 只定义了异常原因编码 `1<<2`，从不涉及
  DADAO-0628 项目自己的 QEMU 退出码惯例）。

---

## 附：可复核命令汇总（只读）

```bash
cd /home/holight/DADAO-0628

# wiki pin 核对
cd ~/DADAO-wiki && git rev-parse HEAD && git status --short && cd -

# §1.1 deleg 全文命中范围
cd ~/DADAO-wiki
grep -rln "cg_reg_deleg\|cg reg delegation" *.md
grep -n "deleg\|委托\|授权" DADAO-22-SBI-主管系统二进制接口.md DADAO-23-HBI-超管系统二进制接口.md
nl -ba DADAO-13-HEE-超管系统运行环境.md | sed -n '1,26p'
nl -ba DADAO-22-SBI-主管系统二进制接口.md | sed -n '699,702p'

# §1.2/§2.4 cfx2rc_cfx_mask / escape_cfx_mask 寄存器与 entry-flow
nl -ba DADAO-12-SEE-主管系统运行环境.md | sed -n '265,335p;670,845p'

# §1.3 cfx2rc/cfx2rd 语义正文
nl -ba SimRISC-04-系统类指令.md | sed -n '60,105p'

# §2.3 cfx_power cg=8 专有寄存器表
nl -ba DADAO-12-SEE-主管系统运行环境.md | sed -n '628,650p'
cd -

# §2.2/§2.3 QEMU 当前实现事实核对
grep -n "inner_cfx_code" .work/source/qemu/target/dadao/*.c .work/source/qemu/target/dadao/*.h
sed -n '78,92p' .work/source/qemu/target/dadao/cpu.h
sed -n '95,214p' .work/source/qemu/target/dadao/helper.c
grep -n "EXCP_ILLI\|EXCP_UNDI\|EXCP_MALIGN\|EXCP_CFXTRAP\|EXCP_EXIT" .work/source/qemu/target/dadao/cpu.h
sed -n '105,145p;300,340p' .work/source/qemu/target/dadao/cpu.c

# contracts 侧已形式化范围（KL-110a）
nl -ba contracts/isa/spec.md | sed -n '982,1062p'
grep -n "Cross-cfx-escape" docs/issues.yaml
sed -n '274,280p' docs/issues.yaml

# KL-110a 完成区（O1 实现细节 ground truth）
sed -n '133,355p' code-agent/tasks/KL-110a-implement-hypv-supv-handoff-o1-qemu.md
```
