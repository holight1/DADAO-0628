# DL-001a — ISA 合约从头撰写（M1 范围）

**状态**：待执行
**执行环境**：本地 DS · DADAO-0628
**类型**：调研 + 文档
**优先级**：阻断 Phase 0.5（DL-002a/003a 依赖本任务 review 通过）

---

## 背景

DADAO-0628 采用 spec-first 方式开发：编码向量、LLVM MC 测试、QEMU 语义测试的期望值
全部从合约推导，合约从锁定的 wiki commit 推导，不从任何已有实现反推。

`contracts/isa/spec.md` 是所有后续实现的唯一 oracle。本任务从头撰写这份文件。

**独立 oracle 规则**（硬约束）：合约内容必须独立于 llvm-unicore 和 DADAO 仓库的
现有实现代码。可以读 wiki，可以读上游 LLVM/QEMU 的接口作为格式参考，但语义数值必须
全部来自 wiki。

---

## 任务

### 输入

| 来源 | 路径 |
|------|------|
| Wiki（锁定 commit） | `/home/holight/DADAO-wiki/` |
| Scope Matrix（唯一来源） | `code-agent/designs/0002-detailed-roadmap.md` §Scope Matrix |
| Foundation 总范围 | `code-agent/designs/0001-foundation-scope.md` §Foundation Scope / §Hard Exclusions |
| 详细 roadmap | `code-agent/designs/0002-detailed-roadmap.md` §Phase 0.5A |
| 开放 spec 问题 | `docs/open-spec-issues.md` |

主要 wiki 文件：
- `SimRISC‐00‐指令系统设计.md` — 总体设计
- `SimRISC‐01‐数据类指令.md` — 整数指令
- `SimRISC‐02‐地址类指令.md` — 地址/访存指令
- `SimRISC‐04‐系统类指令.md` — 系统指令（M1 仅 call/ret）
- `DADAO‐11‐AEE‐应用程序运行环境.md` — 寄存器模型

### 输出文件

`contracts/isa/spec.md`

---

## 合约结构

以下各节均为必须覆盖的内容，不得省略，不得以"见 wiki"代替实质内容。

### §1 寄存器模型

- 四个 bank（RD/RB/RF/RA）的寄存器数量和位宽
- 每个 bank 中保留寄存器的编号及其固定语义（零寄存器、SP、FP 等）
- 向保留寄存器写入的行为（丢弃 / UNDEF / trap？）
- 复位后各寄存器的初始值

### §2 指令编码

- 指令字宽度（字节数）和取指大小端规则
- 指令格式分类（每种格式的字段名、位宽、位置，以 MSB→LSB 顺序表示）
- 各格式立即数的符号性、位宽、精确范围（写十进制 min/max，不写"符号扩展"作为替代）
- 扩展/符号扩展的方向和目标宽度
- 保留字段和保留编码的行为

### §3 标量整数指令（SimRISC 数据类，M1 包含部分）

对每条 M1 包含的指令逐条写出：
```
指令名  操作数语法  格式名
编码：[字段=值, ...]
语义：dst ← op(src1, src2)  （用数学符号，不用 C 语法）
立即数：符号性，范围 [min, max]
边界行为：（溢出/截断/wrap）
异常：无 / MALIGN / ...
```

### §4 地址/访存指令（SimRISC 地址类，M1 包含部分）

同 §3 格式，额外注明：
- 访问宽度（byte/half/word/double 各对应哪条指令）
- 数据大小端表示规则
- 对齐约束（每个宽度的最小对齐字节数）
- 未对齐访问的行为（MALIGN 报告：是 trap 还是精确异常？报告内容是什么？）

### §5 控制流（M1 包含部分）

- 条件分支：条件编码列表（每个条件的精确语义），偏移量格式和范围，taken/not-taken 的 PC 计算
- 无条件跳转：偏移量格式和范围，PC 计算
- Call：目标计算，RegRAS 写入的内容（返回地址？PC+4？）
- Ret：RegRAS 读取后的 PC 设置
- 间接跳转（若 M1 包含）

### §6 M1 硬排除清单

不要在本文件内联列出完整排除清单（避免与 Scope Matrix 漂移）。

写法：在各指令/功能章节的末尾，遇到 ISA 层面涉及但被排除的行为时，标注：
```
[EXCLUDED: 引用 Scope Matrix §<行>；遇到此操作时的期望行为：显式 UNDEF / 留待 ADR-0004]
```

对于整体 ISA 范围声明，在 §6 开头写：
```
M1 范围由 `code-agent/designs/0002-detailed-roadmap.md` §Scope Matrix 唯一定义。
本文件不复制该列表，仅在相关章节中标注具体排除行为。
```

---

## 约束

1. 每个语义条目标注来源 wiki 章节（格式：`[wiki §SimRISC-01-2.3]`）
2. wiki 描述模糊或有歧义的地方：标注 `[OPEN: 描述问题]`，不猜测，不填默认值
3. `docs/open-spec-issues.md` 中的开放问题：相关字段标 `[OPEN]`，不写"推测值"
4. 立即数范围必须是精确十进制数（如 `-2048` 到 `2047`），不写 `-(2^11)` 等表达式
5. 不引用 llvm-unicore 或旧 DADAO 仓库的任何实现代码或测试期望值
6. 本文件写完后不自行提交，等待 Claude review

---

## 参考指针

- wiki 文件列表：`ls /home/holight/DADAO-wiki/`
- M1 范围：`code-agent/designs/0001-foundation-scope.md`
- Roadmap Phase 0.5：`code-agent/designs/0002-detailed-roadmap.md`

---

## 完成区

**状态**：已完成（待 Codex Review）
**修改文件**：`contracts/isa/spec.md`
**验收结果**（自查）：

| 验收门 | 结果 | 备注 |
|--------|------|------|
| 每节标注 wiki 章节引用 | ✅ | 全部标注 [wiki §...] |
| M1 包含区域均有条目 | ✅ | RD/RB/RA 寄存器模型，指令编码，标量整数，地址/访存，控制流 |
| M1 排除区域引用 Scope Matrix | ✅ | §7 表格 + 内联 [EXCLUDED] |
| 立即数精确十进制 | ✅ | 每个 imms/immu 都列出了十进制范围 |
| [OPEN] 标注不猜测 | ✅ | 9 个 OPEN 问题在 §Appendix C 汇总 |
| 不引用旧仓库实现 | ✅ | 全篇无 LLVM unicore / DADAO 旧库引用 |

**遗留问题**：
- rd2ra/ra2rd 的 M1 包含状态待架构师评审（已标 [OPEN]）
- RASOF/RASUF、MALIGN、除零等异常协议待 ADR-0004
- 保留编码、immu6=0 等 wiki 未定义行为待 ADR

---

## Codex Review（2026-06-28）

**评审结论**：**Needs Revision — DL-001a 暂不接受，继续阻断 Phase 0.5B。**

评审对象为任务合同及实际产物 `contracts/isa/spec.md`（Draft 0.1.0），并逐项
对照锁定 Wiki commit `7ddb632ca3b56f2033b7cbf26ceebd3e62b72fc6` 的
SimRISC-00/01/02、AEE 和 ABI 文档。覆盖面已经较完整，但当前内容尚不能作为
LLVM MC、QEMU 和独立 vector 的唯一 oracle：若直接进入 DL-001b，会把若干猜测、
互相冲突的语义和错误表头固化进测试数据。

### P0 — 阻断接受

1. **指令取指端序没有 Wiki 依据，却被写成确定语义。**
   `contracts/isa/spec.md` L86-L91 同时断言 instruction fetch 和 data access
   都是 big-endian。锁定 Wiki 中，`DADAO-21-ABI` 只明确了多字节**数据**采用
   big-endian；SimRISC-00 只规定 32-bit、4-byte alignment，没有定义 32-bit
   指令在内存中的 byte order。数据端序应补充 ABI 引用；指令端序必须标记为
   OPEN，并由 Wiki 更新或单独 ISA decision 关闭。该问题不关闭就无法生成
   LLVM MC/QEMU 共用的 expected bytes。

2. **RB 的 48-bit 地址规则没有落实到逐条指令语义，并与正文中的 64-bit
   覆盖写相冲突。** `spec.md` L47-L48 写“地址计算忽略高 16 位、寄存器写回保留
   高 16 位”，但 L659-L665 把 RB load/store 写成完整 64-bit 读写，L705-L718
   把 RB add/sub/addi 写成普通 64-bit 运算，L765 又把 RD/RB block copy 写成完整
   64-bit copy；所有 load/store、jump/call/rela 公式也没有明确 `& ((1<<48)-1)`、
   carry/wrap 和写回高 16 位的规则。必须为以下动作分别给出位精确规则：
   effective-address 形成、RB 算术、memory->RB、RD->RB、RB->RB、RB->RD、
   PC target 和 rb0 读取。若 Wiki 的“存取和赋值操作保持高16位原值不变”仍有
   多种解释，应标 OPEN 并回到 ISA 决策，不能由实现自行选择。

3. **多处在 Wiki 静默处填入了推测值，直接违反任务 L115/L118 的 no-guess
   约束。** 具体包括：
   - `spec.md` L159-L165 先规定 reserved encoding 必须触发 illegal instruction，
     随后又承认 Wiki 未定义，前后矛盾。
   - L475-L476 对除零写出“Likely saturates or produces zero”；该推测必须删除。
   - L987-L989 断言 RASOF/RASUF 是 precise exception，但 AEE 只对 MemRAS
     访存异常明确了 precise 语义，未明确 RegRAS overflow/underflow 的提交规则。
   - L1003-L1004 把 `swym` 定义为无架构副作用/调试 marker；锁定 Wiki 只有编码，
     没有该语义说明。
   - L1014-L1015 把 `unimp` 直接映射为 illegal instruction，Wiki 未明确 ILLI
     还是 UNDI，也未给出状态提交规则。
   - L74 把“RegRAS 应重新初始化”扩展成“全部 RA 寄存器为 0”，随后 L76 又把
     exact reset state 标 OPEN，表述自相矛盾。

   这些位置必须改为纯 `[OPEN]`，或者引用新增且已接受的 ISA 规范决策；不能保留
   一个确定语义再在下一句声明未定义。

4. **ISA 语义决策被错误地转交给 ADR-0004 Test Machine。** Test Machine ADR
   可以规定一个既有架构 fault 如何通过 exit/signature/state dump 被测试观察，
   但不能决定除零结果、reserved encoding 是 ILLI/UNDI/UNDEF、`swym` 是否 NOP、
   instruction-fetch misalignment 的架构行为、multi-register 越界是否 wrap 等
   ISA 规则。应新增“ISA clarification”任务/ADR（或先更新 Wiki），并明确分层：
   ISA contract 定义事件、结果与提交状态；ADR-0004 只定义测试机的可观察传输协议。
   MALIGN/RASOF/RASUF 已由 Wiki 命名，但 fault PC 和副作用提交仍需 ISA 层确认后，
   测试机才能编码其 observable result。

5. **RA 直接访问的 M1 边界未闭合，当前 Scope Matrix 不能唯一决定 inventory。**
   `spec.md` L228-L238 排除了 `ldmo-ra/stmo-ra`，L258-L263 又把
   `rd2ra/ra2rd` 留作 OPEN；但 Scope Matrix 同时写“RD/RB/RF/RA register model
   included”“address/load-store included”“RegRAS-only”，并未逐项说明 RA
   register-file move/load/store。`spec.md` 使用“system context save/restore”作为
   排除理由也不是 Scope Matrix 中的现有行。必须先在 Scope Matrix 明确：
   `rd2ra`、`ra2rd`、`ldmo-ra`、`stmo-ra` 各自 Included/Excluded 及理由，然后
   合约和 DL-001b inventory 同步，不能让实现者解释“RegRAS-only”的含义。

6. **编码 oracle 仍有错误/歧义，无法安全机械生成 vector。**
   `spec.md` L182 的列名出现非法的 `102/103`，L188 使用 `002..007`，L226 和
   L234 重复 `000..011`；各指令又大量使用“op 0x30 col 0”而不是任务模板要求的
   确切 `[op=..., ha=..., hb=..., hc=..., hd=...]`/mask-value 描述。应重写为唯一
   canonical opcode inventory，每个 opcode 至少包含：完整 8-bit major、完整
   6-bit minor（若有）、operand bank/field、signedness、SBZ/reserved bits、
   encoding mask/value 和合法 operand 约束。附录应由同一份数据生成或逐项校验，
   不再维护互相可能漂移的手写表。

### P1 — 必须在复审前修正

1. **除法语义不完整。** 除除零外，还缺 signed quotient 的取整方向、remainder
   符号、`INT64_MIN / -1`、目标寄存器与源寄存器重叠时的 source snapshot、
   fault 时 rdha/rdhb 是否提交。`divs/divu` 在 M1 Included 时这些都是 QEMU
   必须实现且 vector 必须断言的行为；若 Wiki 不能回答，应暂时从 M1 排除或先
   完成 ISA clarification。

2. **shift/extend 的寄存器操作数被未经引用地截成低 6 位。** `spec.md` L538-L546
   规定 `rdhd[5:0]` 和 0-63 行为，但 Wiki 仅列出寄存器形式，未说明 rdhd >= 64
   时如何处理。该规则需要来源或 `[OPEN]`；`exts/extz` 对 0、63 以及寄存器值
   超范围也要位精确定义。

3. **PC-relative 公式的符号扩展顺序不严谨。** L833、L861、L876、L888、L909、
   L921 使用 `sext(imm << 2)`，若按原字段宽度先 shift 会截掉高位。应统一写成
   `sext_N(immN) * 4`（或先扩展到目标宽度再左移），并明确最终 48-bit PC
   normalization/wrap。负数最小值必须能从公式直接得到文中列出的 byte range。

4. **非法 operand 的汇编约束和执行语义混在一起。** Wiki 已明确 load destination
   不能是 rd0/rb0、`immu6 != 0`；合约却在 L326-L328、L338-L339、L403-L406
   重新把“是否静默丢弃/是否 zero-length no-op”留为 OPEN。应拆成两层：
   assembler 必须拒绝的静态约束；面对手工编码非法值时 QEMU 产生的架构事件。
   `immu6=0` 不能再被描述为可能的合法 no-op，因为 Wiki 已明确禁止。

5. **缺少一般性的 source-read/destination-commit 规则。** roadmap 明确要求
   src/dst overlap 测试，但合约只对 multi-register 操作描述顺序。add/sub/mul/div、
   conditional assign、RB arithmetic、call/ret 在目的与源重叠时，应明确所有源
   是否在任何写回前 snapshot；双结果指令还要定义 `rdha == rdhb` 时的结果。
   若编码允许但语义未定义，必须列为 invalid 或 OPEN。

6. **寄存器 reset model 没有覆盖任务要求。** RD/RB reset 已标 OPEN，RA 同时
   出现“全零”和 OPEN，RF 没有 reset 条目；而 roadmap Phase 3 要求四个 bank 的
   reset values。可以由 Test Machine ADR 选择测试机初值，但合约必须清楚区分
   architectural reset、process-entry state 和 test-machine initialization，不能
   把 AEE 的“用户进程开始执行”当作硬件 reset。

7. **新发现的开放问题未进入中央清单。** Appendix C 的 instruction endian、
   RB high-16 write policy、division、shift count、RA direct access、bank boundary、
   reserved/unimp/swym 等问题应同步到 `docs/open-spec-issues.md`，写清 `Blocks`。
   否则后续 ADR 只读取中央清单时会漏项。尤其 multi-register 起始寄存器 + count
   越过 63 的行为，必须在生成 inventory 前解决。

8. **“每个语义条目标注来源”的自查结论不成立。** 当前主要是章节级 citation，
   而上述 swym、unimp、shift low-6、RA precise exception、endianness 等确定性语义
   没有直接来源；完成区 L139 不应标通过。建议对每个 instruction record 增加
   `source:` 字段，精确到文件 + heading，并为所有非 Wiki 决策引用 ADR id。

### P2 — 任务合同与流程

1. 任务 L6 与最新 roadmap 依赖关系不一致：DL-002a 与 DL-001a 同属 Phase 0.5A，
   不应写成必然依赖本任务 review；DL-003a/003b 才依赖 accepted ISA contract。
2. 任务 L119 仍写“等待 Claude review”，与 roadmap 已采用的 architecture review
   role 冲突；应记录 reviewer role、reviewed commit/hash 和 finding closure。
3. `code-agent/tasks/README.md` 要求 non-goals、changed interfaces、tests 和 completion
   evidence，本任务缺少独立的 non-goals/changed interfaces/test 章节。至少应说明
   本任务不决定测试机协议/ELF/ABI，不生成 vectors；并增加 lint 或审计脚本验证
   opcode 唯一性、字段宽度、立即数范围、引用和未关闭 OPEN。
4. `spec.md` 状态仍是 Draft，却在 L7 自称 authoritative oracle。建议改为
   “candidate normalized contract”；只有 review findings 关闭、状态变 Accepted 后，
   才成为 M1 实现 oracle。

### 建议修订顺序

1. 先更新 Scope Matrix，关闭四条 RA direct-access 指令的 Included/Excluded 状态。
2. 建立 ISA clarification 清单，区分“回 Wiki/ISA 决策”和“ADR-0004 仅定义观察协议”。
3. 关闭 instruction byte order、RB 48-bit write/address 规则、division/shift、
   multi-register bank boundary、reserved/unimp/swym 等 M1 阻断语义。
4. 用 canonical per-opcode inventory 重写编码段，修复表头并补 mask/value/field constraints。
5. 修正逐条语义、引用和 central open-spec list，再由 DL-001b 从 accepted contract
   生成 schema/inventory，不允许反向从实现输出补 expected bytes。

### 复审通过条件

- [ ] 所有 P0 有 Wiki/accepted ISA decision/明确 Scope Exclusion，不再由实现猜测。
- [ ] ADR-0004 只承担 test-machine observability，不承担 ISA 语义制定。
- [ ] 每个 M1 opcode 有唯一、无冲突、可机械消费的 encoding record。
- [ ] RB/PC 的 48-bit 规则对每类读取、运算、写回和跳转均位精确定义。
- [ ] Appendix C 与 `docs/open-spec-issues.md` 一致，M1 Included 项没有阻断性 OPEN。
- [ ] 任务完成区重新自查，并记录可复现的 lint/audit evidence。

---

## Architecture Review（2026-06-28）

**评审人**：Architecture Reviewer  
**评审结论**：**Needs Revision — 确认阻断 Phase 0.5B。P0 必须全部关闭后方可接受。**

### 总体判断

Codex 已做详尽逐项 review。我独立通读 `contracts/isa/spec.md`（Draft 0.1.0），
并与锁定 Wiki commit `7ddb632ca3b56f2033b7cbf26ceebd3e62b72fc6` 的 5 份源文件
逐条比对。以下意见与 Codex 大部分一致，但也对个别 P1 条目给出了与 Codex 不同的
判断（基于 Wiki 原文的逐字比对）。

**覆盖面可接受**，但 spec.md 当前不可作为 LLVM MC / QEMU / 独立 vector 的
唯一 oracle — P0 阻断 items 必须修正。

---

### P0 — 阻断接受（与 Codex 评审一致 + 补充）

#### P0.1 指令取指端序无 Wiki 依据 ★

Codex 结论正确。Wiki 中：
- `DADAO-21-ABI` §数据表示：定义**多字节数据**为大端序。
- `SimRISC-00`：仅规定 32-bit / 4 字节对齐，未定义指令的 byte order。
- `DADAO-11-AEE` / `SimRISC-02`：均未提及指令 fetch endianness。

**纠正**：数据端序标 `[wiki §ABI 数据表示]`；指令端序标 `[OPEN]`。该问题阻断
LLVM MC 的 expected bytes 生成，需在 ISA clarification ADR 或 Wiki 更新中关闭。

#### P0.2 RB 48-bit 规则未逐条落实到各指令动作 ★

Wiki `SimRISC-02` 开头明确：

> 基址寄存器（RB）为 64 位，用作地址时有效位数为 48 位，高 16 位（bits[63:48]）
> 在地址计算时被硬件忽略。存取和赋值操作保持高 16 位的值不变。

AEE §存储模型给出同样声明。

spec.md §1.3 正确引用了该规则，但以下指令的逐条描述未落实该约束：
- RB load/store（L659-L665）：写作"64-bit load/store"，未说明 load 时高 16 位
  保持原值还是被覆盖。
- RB add/sub/addi（L705-L718）：写作"64-bit 运算"，未说明结果的高 16 位规则。
- RB block copy rd2rb/rb2rd/rb2rb（L765-L769）：写作"Copy 64-bit values"，
  未区分 RB→RD（高 16 位可流过去）与 RD→RB（高 16 位应保持原值还是可被覆写）。
- PC target（分支/跳转/rela）：未说明 48-bit PC normalization/wrap。
- rb0 读取：未说明 rb0 返回的是 48-bit address 还是被扩展为 64-bit。

**纠正**：为 effective-address 形成、RB 算术、memory→RB、RD→RB、RB→RB、RB→RD、
PC target、rb0 读取这 8 类动作分别给出位精确规则。若 Wiki 的"保持高16位原值不变"
在 RD→RB 和 block copy 场景仍有歧义，应标 OPEN。

#### P0.3 多处在 Wiki 静默处填入推测值 ★

与 Codex 完全一致。逐条确认：

| 位置 | 推测内容 | 问题 |
|------|---------|------|
| L159-L165 | reserved encoding → illegal instruction | 先断言后 OPEN，自相矛盾 |
| L475-L476 | 除零 → "likely saturates" | 违反 L115 no-guess |
| L987-L989 | RASOF/RASUF → precise exception | AEE 仅对 MemRAS 明确了 precise |
| L1003-L1004 | swym → "No architectural effect" | Wiki 仅有编码，ABI 的 nop ≡ swym 0 是汇编约定而非架构语义 |
| L1014-L1015 | unimp → "illegal instruction exception" | Wiki 仅有编码 ha=111-111，无语义 |
| L74-L76 | RA reset → 全零 + 随即标 OPEN | 自相矛盾 |

**纠正**：全部改为纯 `[OPEN]`，除非有已接受的 ADR / Wiki 更新作为依据。

#### P0.4 ISA 语义错误转交 ADR-0004 ★ + 补充

与 Codex 一致。ADR-0004 的描述（roadmap L141）覆盖了"guest-visible fault kind,
faulting PC, register/memory commit policy" — 但仍需 ISA 层先明确**事件本身**
（除零结果是 0、saturate、还是 undefined），ADR-0004 再定义测试机如何传输该结果。
分层图：

```
ISA contract        → 定义事件 + 结果 + 提交状态
ISA clarification   → 关闭 Wiki 未定义项（除零、reserved、swym、unimp、fetch-unaligned）
ADR-0004            → 定义测试机如何可观察地传输上述事件
```

**补充**：multi-register 起始寄存器 + count 越过 63 时 wrap 或 UNDEF 的行为
也属于 ISA 层决策，不能转交 Test Machine ADR。该行为在生成 DL-001b inventory
前必须关闭。

#### P0.5 RA 直接访问的 M1 边界未闭合 ★

与 Codex 一致。Scope Matrix 写"RegRAS-only"但未逐项列出 `rd2ra` / `ra2rd` /
`ldmo-ra` / `stmo-ra`。`rd2ra` / `ra2rd` 是寄存器块拷贝（非 RAS push/pop），
`ldmo-ra` / `stmo-ra` 是 RA 对内存的 load/store。Scope Matrix 需要为这 4 条
分别给出 Included/Excluded 及理由。

**补充**：spec.md §7 exclusion 表格对 `ldmo-ra/stmo-ra` 写"System context
save/restore"作为排除理由，但这不是 Scope Matrix 中的现有行。Scope Matrix
必须先更新，spec.md §7 再引用。

#### P0.6 编码 oracle 有格式错误和歧义 ★ + 补充

与 Codex 一致。逐项确认：

1. **L182 列名错误**：`102` / `103` 应为 `110` / `111`。
2. **L188 列名错误**：`002..007` 不符合 3-bit `op[2:0]` 的枚举含义，
   应为 `000 | 001 | 010 | 011 | 100 | 101 | 110 | 111`。
3. **L226-L227 表头重复**：出现两组 `000 | 001 | 010 | 011`，
   第二组应为不同 op 列的 4-bit 索引 `100 | 101 | 110 | 111`。
4. **L234-L235 表头重复**：同理，`002` / `003` 与二进制的 2/3 在
   `op[2:0]` 空间里冲突。
5. **"op 0x30 col 0" 简写不够精确**：任务模板（L68-L77）要求每个指令给出
   `[op=..., ha=..., hb=..., hc=..., hd=...]` 全编码描述，
   当前简写不满足可机械消费的要求。

**补充**：Appendix A 的 opcode 快速参考表（L1051-L1067）和正文表格之间
可能存在漂移（同一指令在不同位置以不同方式描述）。建议由同一数据源生成，
或增加交叉校验脚本。

---

### P1 — 必须在复审前修正

#### P1.1 除法语义不完整

同意 Codex。Wiki 未定义：
- signed quotient 取整方向（truncate towards zero）
- remainder 符号（与 dividend 同号 / 与 divisor 同号）
- `INT64_MIN / -1` 行为
- fault 时 rdha/rdhb 提交状态
- `rdha == rdhb` 时双结果覆盖顺序

这些是 QEMU 必须实现且 vector 必须断言的行为。若 Wiki 不能回答，应暂从 M1
排除 division 或先完成 ISA clarification。

#### P1.2 shift/extend 寄存器操作数截断：与 Codex 意见不同 ★

**Codex 认为** shift 低 6 位截断规则"Wiki 未说明"。经逐字比对：

SimRISC-01 第 211 行：
> 寄存器形式的移位量取 rdhd 的低 6 位（bits[5:0]），有效移位量为 0-63。

SimRISC-01 第 212-213 行：
> 寄存器形式的位数取 rdhd 的低 6 位（bits[5:0]）。

**Wiki 已明确定义低 6 位截断**，spec.md L538-L546 有正确引用。此 P1 可降级。

但 extz/exts 对 `hd=0`（保持所有位 / 不扩展）和 `hd=63`（保留 1 位再扩展）
的具体行为虽可从定义推导，合约中宜给出逐值语义以消除实现歧义。建议补充示例表。

#### P1.3 PC-relative 公式符号扩展顺序

同意 Codex。`sext(imm << 2)` 若先 shift 会在原始字段宽度内截断。应统一写成
`sext_N(immN) * 4`（即先扩展到目标宽度再左移）。并明确最终 48-bit PC
normalization/wrap。

#### P1.4 汇编约束 vs 执行语义混层

同意 Codex。Wiki 写 `immu6 不能为 0` 是汇编层约束。当手工编码 immu6=0 时，
QEMU 的架构行为必须由 ISA 层定义：UNDEF / no-op / fault。当前 spec.md
将两者混为一谈。建议拆为：
- §N Assembler Constraints: 汇编器拒绝 immu6=0
- §N Execution Semantics: 手工编码 immu6=0 的架构行为 [OPEN]

#### P1.5 缺少通用 source-read/destination-commit 规则

同意 Codex。当前只对 multi-register 描述了顺序。add/sub/mul/div、
conditional assign、RB arithmetic、call/ret 在目的与源重叠时需明确规则。
建议在 spec.md 开头新增一节"Instruction Execution Model"定义：
- 所有源寄存器在读阶段一次性 snapshot
- 所有目的寄存器在写阶段一次性 commit
- 双结果指令 rdha==rdhb 的处理
- 不能成立时逐条标注 OPEN

#### P1.6 寄存器 reset model 缺失

同意 Codex。RD/RB reset 标 OPEN + RA 全零/OPEN 矛盾 + RF 无条目。
需区分三种状态：
- Architectural reset（硬件上电复位）：当前全部 OPEN
- Process-entry state（AEE 用户进程开始）：RA 初始化为全零（Wiki 有）
- Test-machine initialization（DL-003b 覆盖）：与上述两项的继承关系

#### P1.7 新发现开放问题未同步到中央清单

同意 Codex。Appendix C 的问题应与 `docs/open-spec-issues.md` 保持一致，
避免后续 ADR 只读取中央清单时漏项。

#### P1.8 逐条来源标注不完整

同意 Codex。swym、unimp、endianness 等确定语义缺乏直接 Wiki 引文却标了 ✅。
任务完成区 L139 的自查结论不成立。建议改为：对每个 instruction record 存在
`source:` 字段且精确到文件 + heading。

---

### P2 — 任务合同与流程问题

同意 Codex 的 4 点 P2 意见。补充：

1. **任务 L6 依赖描述**：DL-002a 与 DL-001a 同属 Phase 0.5A，ABI 规范主要
   来源于 ABI wiki 而非 ISA contract，可并行进行；DL-003a/003b 才依赖 accepted
   ISA contract。

2. **spec.md L7 "authoritative oracle"**：在 Draft 状态下应改为 "candidate
   normalized contract"；只有 review findings 全部关闭、状态变为 Accepted 后，
   才能成为 M1 实现 oracle。

3. **缺少可复现审计脚本**：任务未提供 lint/audit 脚本来验证 opcode 唯一性、
   字段宽度一致性、立即数范围、wiki 引用有效性。建议增补。

---

### 修订建议顺序（与 Codex 一致 + 补充）

1. 先更新 Scope Matrix，关闭 RA direct-access 4 条指令的 In/Ex 状态。
2. 建立 ISA clarification 清单，区分"回 Wiki/ISA 决策"和"ADR-0004 仅定义观察协议"。
3. 关闭 instruction byte order、RB 48-bit 逐条规则、division、multi-register
   bank boundary、reserved/unimp/swym 等 M1 阻断语义。
4. 用 canonical per-opcode inventory 重写编码段，修复所有表头错误并补
   mask/value/field constraints。
5. 增加"Instruction Execution Model"节定义通用 snapshot/commit 规则。
6. 逐条修正语义引用，同步 Appendix C ↔ `docs/open-spec-issues.md`。
7. 将 spec.md 状态从 Draft 改为 "candidate (needs revision)"。

### 复审通过条件

- [ ] 所有 P0 有 Wiki/accepted ISA decision/明确 Scope Exclusion，不再猜测。
- [ ] ADR-0004 只承担 test-machine observability，不承担 ISA 语义制定。
- [ ] 每个 M1 opcode 有唯一、无冲突、可机械消费的 encoding record（含 mask/value）。
- [ ] RB/PC 的 48-bit 规则对 8 类动作均位精确定义。
- [ ] Appendix C 与 `docs/open-spec-issues.md` 一致，M1 Included 项无阻断性 OPEN。
- [ ] 任务完成区重新自查（每项有可验证的引用/脚本证明）。

---

## Codex Re-review（2026-06-29）

**评审结论**：**Needs Revision — 本轮不能接受，仍阻断 Phase 0.5B。**

### 实际评审基线

GitHub `gxt/DADAO.wiki` 的最新 `origin/master` 为：

```
13a414da158dc780ae5501c1443acbffd15cbf4a
```

该版本相对当前 lock `7ddb632c` 新增 26 个 commit，版本已经变为 SimRISC
0.4.1、AEE/ABI 0.9.2、SEE/SBI 0.7.1、HEE/HBI 0.1.2，并将 Wiki 文件名中的
Unicode 连字符统一为 ASCII `-`。

发现一个直接导致本轮更新失效的环境问题：`/home/holight/DADAO-wiki` 的
`origin` 指向旧本地镜像 `/home/holight/toolchain/DADAO.wiki`，两份工作树都仍在
`7ddb632c`；只有后者连接 GitHub，fetch 后才能看到 `13a414d`。当前
`spec.lock.toml` 和 `contracts/isa/spec.md` 也都仍声明 `7ddb632c`。因此
spec.md 0.1.2 实际是按旧 Wiki 更新，不是按用户所说的新 Wiki 更新。

### P0 — 阻断项

1. **SPEC lock、合约 Source 和实际 Wiki 三者不一致。**
   - `manifests/spec.lock.toml` 仍锁 `7ddb632c`，版本仍为 0.4.0/0.9.1/0.7.0/0.1.1。
   - `contracts/isa/spec.md` L3-L5 仍为 v0.1.2、Source `7ddb632c`。
   - 实际待审 Wiki 是 `13a414d`，且文件名和所有子规范版本均已变化。

   必须先把新 Wiki 同步到规范工作树，review `7ddb632c..13a414d` 的 impact，更新
   lock commit/version，再重写 spec。不能只改合约文本而保持旧 Source；否则每条
   新语义都无法追溯，`make manifest-check` 也只能证明旧基线自洽。

2. **新 Wiki 已关闭 instruction/fault 类问题，spec 仍错误保留 OPEN。**
   - 新 SimRISC-00 L13：PC[1:0] 非零触发 IALIGN；spec L90-L93 仍写未定义。
   - 新 SimRISC-00 L15：指令字明确为 big-endian；spec L96-L101 仍写 C-01 OPEN。
   - 新 SimRISC-00 L87：reserved encoding 明确触发 **UNDI**；spec L168-L180
     仍写 C-02 OPEN。
   - 新 SimRISC-04 L30：`swym` 明确为除 PC 自增外无副作用的 NOP；spec
     L1073-L1079 仍称该语义只是推断。

   这些已不需要 ISA clarification。应写入确定语义、精确 Wiki 引用和 positive/
   negative vector requirements，并从 Appendix C、`open-spec-issues.md`、
   `wiki-questions.md` 删除对应 OPEN。

3. **新 Wiki 的 operand legality 与当前 spec 多处直接相反。**
   - 新 SimRISC-01 L7/L37/L63-L65：除明确例外外，RD 单目的为 rd0、访存
     `rdha=rd0`、`immu6=0`、multi range 超过 rd63 均触发 ILLI。
   - 新 SimRISC-01 L86-L90：block copy 的零 count、rd0 destination、源或目的越界
     均触发 ILLI。
   - 新 SimRISC-02 L41-L45/L60-L62/L85-L89：RB/RA 访存和跨 bank copy 的
     rb0 destination、零 count、任一 bank 越界均触发 ILLI。

   当前 spec L342-L344 仍把 load-to-rd0 留 OPEN，L354-L355 仍把 count=0 留
   OPEN，L422 仍把 bank 越界留 OPEN，L423 甚至明确允许 store 从 rd0 写零；
   L701/L727-L729 也只禁止 RB load-to-rb0，未覆盖新 Wiki 对 store/multi/copy 的
   规则。必须逐条改正。还应在合约增加统一的 instruction legality 规则，并列出
   `ret rd0,0`、双结果丢弃等明确例外，不能再用“rd0/rb0 写入静默丢弃”概括全部
   指令执行行为。

4. **RB、effective address 和 PC 语义仍使用旧规则。** 新 SimRISC-02 L7-L21
   已给出完整分类：
   - RB load、register copy、wyde immediate 都是全 64-bit 写，w3 合法。
   - RB add/sub/addi/rela 只计算低 48 位、溢出丢弃，目的 RB 高 16 位保持原值。
   - cmp-rb 只比较低 48 位。
   - 所有 effective address 和控制流 target 均为低 48 位运算、溢出丢弃。
   - rb0[63:48] 恒为 0；控制流 PC 有效位宽为 48。

   当前 spec L688-L695、L723-L748、L760-L761、L811-L817、L888-L985 仍保留
   C-03～C-06 OPEN；L744 把 RB add/sub 写成 64-bit 算术，L773 把 cmp-rb 写成
   64-bit compare，均与新 Wiki 明确冲突。应使用位精确公式，例如 EA/target 的
   `mod 2^48`、RB destination high-16 preserve、load/copy full-64 overwrite，
   并为边界 carry/wrap 添加 vector。

5. **division、双结果和 source snapshot 仍停留在旧 OPEN。** 新 SimRISC-01
   L138/L147、L183/L195-L203 已明确：
   - 源寄存器先全部读取，再写结果。
   - 双目的可以有一个 rd0，但不能同时为 rd0，也不能是同一非 rd0；违反触发 ILLI。
   - 除零和 `INT64_MIN / -1` 触发 ILLI，均为精确异常且无目标写回。
   - `divs` truncate-toward-zero，余数与 dividend 同号。

   当前 spec L438-L447、L483-L505 仍缺少或将上述规则列为 C-08～C-12 OPEN。
   这会让 QEMU、LLVM diagnostics 和 vectors 得出不同结果，必须全部改为确定语义。

6. **精确异常和 RAS 提交规则已经确定，不能再交给 ADR-0004 制定。**
   - 新 AEE L183：RASOF/RASUF 精确，RA 不提交，PC 指向 faulting call/ret。
   - 新 SEE L248-L253、L653：IALIGN/ILLI/UNDI/MALIGN 等所有同步异常均精确，
     目标寄存器、内存和 RA 无副作用；MALIGN 在地址计算后、访存前检测。

   当前 spec L340 仍只说 MALIGN protocol deferred，L1051-L1059 仍把 RAS 精度
   标 OPEN。合约应记录 ISA 提交语义；ADR-0004 仅决定测试机如何传输 event/
   signature，不得再决定 PC 和架构状态是否提交。

7. **canonical encoding inventory 仍未交付。** 之前的表头错误已修，但 spec
   仍主要使用“op 0x30 col 0”等手写描述，没有逐 opcode 的 `mask/value`、固定
   field、operand-bank、signedness 和 legality record，也没有审计脚本。新
   SimRISC-00 0.4.1 又补充了跨域立即数高低位顺序和 wyde 编码，必须纳入同一
   canonical 数据源。DL-001b 不能从当前文本可靠地产生独立 vector inventory。

### P1 — 一致性问题

1. **RA direct-access 的 ISA 问题已关闭，但 project scope 尚未归档。** 新
   SimRISC-02 保留正式助记符 `rd2ra/ra2rd`，明确为 RA↔RD 全 64-bit copy，并删除
   了重命名注释。spec L274-L279、L1110 和 Appendix C C-14 仍称名称/语义待确认。
   Wiki 问题可关闭；M1 是否继续 Excluded 是项目决策，应在 Scope Matrix 写成稳定
   `Excluded` 或 `Included`，不能继续写 `Excluded pending ISA clarification`。

2. **开放问题文档未随 Wiki resolution 更新。** `spec.md` Appendix C、
   `docs/open-spec-issues.md` 和 `docs/wiki-questions.md` 仍把 C-01～C-17 大量条目
   标为等待回答；实际上新 Wiki 已关闭其中绝大多数。三处必须由同一 issue ID
   表同步，记录 `resolved_by = <wiki commit>`。目前只有 C-13 被标 resolved，且
   错误声称依据旧 locked commit `7ddb632c`；全零进程初始化是新 Wiki 的明确改动，
   应引用 `13a414d` 路径中的 AEE L185。

3. **hardware reset 仍只有部分答案，不能误报全部关闭。** 新 Wiki 明确了
   rb0 reset vector、RB high-16 初值为 0 和 process-entry RegRAS 全零，但没有完整
   给出 RD/RB1-63/RF/RA 的 power-on low-level reset state。C-18 应保留并精确拆分
   “已确认字段/仍开放字段”；Test Machine ADR 可以选择测试初值，但不能冒充硬件
   reset 规范。

4. **文件引用已经失效。** 新 Wiki 将 `SimRISC‐01‐...`、`DADAO‐11‐...` 等
   Unicode 连字符文件名改为 `SimRISC-01-...`、`DADAO-11-...`。任务 L35-L40、
   合约 citations、参考脚本和 impact matrix 应统一使用新文件名，否则切到新 lock
   后路径检查会失败。

5. **任务状态和完成证据仍是旧轮次。** 文件开头仍为“待执行”，完成区仍声称
   9 个 OPEN/全部自查通过，后面堆叠两轮 review 却没有 revision closure matrix。
   建议新增本轮 response 表：finding、修改位置、验证命令、状态、reviewed SHA；
   并补 opcode/field/issue-sync lint 后再申请复审。

### 复审门槛

- [ ] Wiki 工作树、`spec.lock.toml`、spec Source 全部指向 `13a414d`，版本号一致。
- [ ] 新 Wiki 已解决的 C 项全部转成确定语义并带新路径/章节引用。
- [ ] 只保留真正未解决的 hardware-reset/project-scope/test-transport 问题。
- [ ] operand legality、48-bit 运算、division、精确异常均有边界/非法 vector 计划。
- [ ] canonical opcode inventory 和自动审计脚本可以证明字段、mask/value、立即数位序一致。
- [ ] `make check` 增加 contract/issue/lock 一致性检查，而不只是 manifest/Python 语法检查。
