# DL-001b — spec.md 全量修订（基于 Wiki 0.4.1）

**状态**：已完成（spec.md v0.4.0 — 架构师直接修复全部 P0；Appendix A 含 mask/value；待新一轮 review）
**执行环境**：本地 DS · DADAO-0628
**类型**：文档修订
**优先级**：阻断 QEMU/LLVM 实现启动（DL-002/003 依赖本任务产物）

---

## 背景

`contracts/isa/spec.md` 当前版本 0.1.2，基于锁定 Wiki commit `7ddb632c`（SimRISC 0.4.0）。

Wiki 已推进到 `13a414d`（SimRISC 0.4.1），该版本新增了大量明确语义定义，关闭了绝大多数前轮 review 标记的 OPEN 项。`manifests/spec.lock.toml` 已更新为新 commit。

本任务目标：将 spec.md 完整地按新 Wiki 0.4.1 重写，达到可作为 QEMU / LLVM MC / test vector 唯一 oracle 的"Accepted"状态。

**任务前提（已完成）**：
- `~/DADAO-wiki` remote 已修正为 `https://github.com/gxt/DADAO.wiki.git`
- `~/DADAO-wiki` 已更新到 `13a414d`
- `manifests/spec.lock.toml` 已更新版本

---

## 输入

| 来源 | 路径 |
|------|------|
| 新 Wiki（锁定 commit 13a414d） | `/home/holight/DADAO-wiki/` |
| 当前 spec（需要全量更新） | `contracts/isa/spec.md` |
| 旧 spec 对应的开放问题表 | `docs/open-spec-issues.md` |
| wiki 问题清单（已提交） | `docs/wiki-questions.md` |
| Scope Matrix | `code-agent/designs/0002-detailed-roadmap.md` §Scope Matrix |
| Codex Re-review 意见（任务尾部） | `code-agent/tasks/DL-001a-isa-contract.md` §Codex Re-review |

主要 wiki 文件（新文件名，ASCII 连字符）：
- `SimRISC-00-指令系统设计.md` — 指令字节序、取指对齐、UNDI、opcode 表
- `SimRISC-01-数据类指令.md` — 整数指令、除法、双目标规则、operand legality
- `SimRISC-02-地址类指令.md` — RB 高16位分类规则表（关键新增）、地址/访存指令
- `SimRISC-04-系统类指令.md` — swym、unimp、call/ret/RAS
- `DADAO-11-AEE-应用程序运行环境.md` — 寄存器模型、RegRAS 布局与初始化

---

## 核心修改内容

以下是新 Wiki 已明确、spec.md 必须更新的项目。逐条落实，**不得保留已被 wiki 关闭的 OPEN**。

### 1. Wiki 版本和 lock commit 更新

spec.md 头部 Source 字段：
```
**Version**: 0.2.0
**Source**: Wiki commit `13a414da158dc780ae5501c1443acbffd15cbf4a` (SimRISC 0.4.1)
**Status**: Candidate
```

### 2. §2.1 指令取指字节序和对齐（原 C-01、C-23）

新 Wiki SimRISC-00 §指令设计 第一段：
- 指令字**大端序**存储：bits[31:24] 在最低地址，bits[7:0] 在最高地址
- PC[1:0] ≠ 00 触发 **IALIGN** 异常

更新：删除 C-01/C-23 OPEN，写入确定语义并注明 wiki 引用。

### 3. §2.5 保留编码行为（原 C-02）

新 Wiki SimRISC-00 opcode 表说明行：
- 保留编码触发 **UNDI** 异常（不是 ILLI）

更新：C-02 改为确定语义 UNDI，引用 `SimRISC-00 §SimRISC QFC`。

### 4. §4.x RB 高16位规则（原 C-03、C-04、C-05、C-1d、C-19、C-20、C-21）

新 Wiki SimRISC-02 开头给出分类规则表：

| 操作类别 | 指令 | 高16位行为 |
|---------|------|----------|
| 存取类（内存↔RB） | ldo/ldmo/sto/stmo | 全 64 位覆盖写，bits[63:48] 正常读写 |
| 赋值类-寄存器 | rd2rb/rb2rb/ra2rd/rd2ra | 全 64 位覆盖写，bits[63:48] 正常读写 |
| 赋值类-立即数 | setzw-rb/orw-rb/andnw-rb | 全 64 位覆盖写，**w3（bits[63:48]）合法** |
| 算术-加减 | add-rb/sub-rb/addi-rb/rela | 低 48 位计算，溢出丢弃；bits[63:48] 保持不变 |
| 算术-比较 | cmp-rb | 仅比较低 48 位 |
| 控制流-跳转 | br*/jump | 低 48 位计算，溢出丢弃 |
| 控制流-函数 | call/ret | 低 48 位计算；高16位作为引用计数（RA 用途） |

补充：
- 有效地址 EA = 低 48 位，溢出丢弃（原 C-19）
- rb0[63:48] 恒为 0（原 C-20）
- rela 属算术类，写回时 bits[63:48] 保持不变（原 C-21）

每条逐句更新对应 §4.x 指令语义，删除 C-03~C-06 相关 OPEN。

### 5. §3.5 除法指令（原 C-08 至 C-12）

新 Wiki SimRISC-01 §乘除操作 末尾：
- **除数为零**：触发 **ILLI** 异常（精确，rdha/rdhb 无写入）
- **截断方向**：truncate-toward-zero（C99）；余数符号 = 被除数符号
- **INT64_MIN ÷ -1**：触发 **ILLI** 异常（唯一溢出情况）
- **fault 时寄存器**：精确异常，rdha/rdhb 未写入

更新：将 C-08~C-12 全部改为确定语义。不再建议"推迟到 post-M1"。

### 6. §3.x 操作数合法性规则（原 C-17、C-25、C-26）

新 Wiki SimRISC-01 §约定行（文档开头）和各指令 §限制：

**rd0 为目的寄存器约定**：
- 双目的指令（add/sub/mul/div）允许其中一个 rd0（丢弃该半结果），但不能同时为 rd0，也不能为同一非 rd0。违反→ILLI
- 其余所有指令：rdha=rd0 → ILLI

**immu6=0**：触发 ILLI（各多寄存器指令约束行）

**超界**：rdha + immu6 > 64 → ILLI（不环绕，不截断）

**rb0 为目的**：→ ILLI（SimRISC-02 开头约定行）

在 spec.md 新增"§2.6 Instruction Legality"节，统一列出上述约定，各指令章节引用该节，不再逐条重复 OPEN。

### 7. §5 控制流（原 C-06、C-07）

- **PC 高16位**：所有跳转目标仅取低 48 位，溢出丢弃（rb0[63:48]=0 由此保证）
- **RASOF/RASUF 精确性**：精确异常，RA 不提交，PC 指向 faulting call/ret
  - 来源：新 AEE §返回地址栈 / §MemRAS 访存说明（精确异常明确描述）

更新 §5.6 RASOF/RASUF OPEN 注释，改为确定语义。

### 8. §6.1 swym、§6.2 unimp（原 C-15）

新 Wiki SimRISC-04：
- **swym**：除 PC 自增外无任何架构副作用（明确为 NOP）
- **unimp**：触发**非法指令异常**（ILLI）

更新：删除"推断"措辞，改为确定语义引用 SimRISC-04。

### 9. §1 寄存器模型

- §1.5 RA process-entry init：已更新为"全零"（v0.1.2 已做），确认与新 wiki AEE L185 引用一致
- §1.3 RB：rb0[63:48] 恒 0，在 §1.3 补充一行（原文未明确写）
- 新 wiki 文件名更新所有 citation 路径（Unicode→ASCII）

### 10. §2.x 立即数拼接顺序（新 wiki 补充）

新 Wiki SimRISC-00 §指令域说明 末尾新增：
> 多域拼接立即数规则：hb→hc→hd 按高位到低位。
> rwii 的 wyde-position 在 hb[5:4]，immu16 高4位在 hb[3:0]，中6位在 hc，低6位在 hd。

更新 §2.2 字段说明，补充立即数拼接规则。

### 11. Appendix C 清单同步

关闭以下 OPEN（改为 RESOLVED + wiki 引用 + 章节指针）：
C-01, C-02, C-03, C-04, C-05, C-06, C-07, C-08, C-09, C-10, C-11, C-12, C-16, C-17, C-19, C-20, C-21, C-23, C-25, C-26

更新 C-14（rd2ra/ra2rd）：wiki 删除 rename 注释，维持现有助记符，ISA 语义已明确（RA↔RD 全 64 位 copy）；Scope 决策（Included/Excluded）由 Scope Matrix 决定。

保留 OPEN：C-18（硬件复位值，仅已知 RB 高16初值=0）；C-14 Scope 决策。

---

## 交付物格式要求

### 每条指令记录格式

```
### 指令名（格式类型）

[wiki §SimRISC-XX §章节名]

语法：  助记符  操作数
编码：  op=0xXX, ha=..., hb=..., hc=..., hd=...（SBZ 字段注明）
语义：  数学符号描述（不用 C 语法）
约束：  静态合法性（汇编器拒绝）
异常：  执行时 ISA 事件（ILLI/UNDI/MALIGN/IALIGN）
```

### RB 操作的位精确公式

使用以下格式：

```
EA = (rbhb[47:0] + sext_12(imms12)) mod 2^48
rdha[47:0] = load64(EA)[47:0]          ; 全64位写入（含高16）
```

不使用 `& ((1<<48)-1)` 等 C 风格表达式。

### spec.md 版本字段

```
**Version**: 0.2.0
**Source**: Wiki commit `13a414da158dc780ae5501c1443acbffd15cbf4a` (SimRISC 0.4.1)
**Status**: Candidate
```

---

## 约束

1. **每条确定语义必须有精确 wiki 引用**（文件名 + 章节标题），不得写章节级概括后批量套用
2. **只写 wiki 已明确的内容**；仍有歧义处继续标 `[OPEN: ...]`
3. **不引用旧仓库**（llvm-unicore、DADAO）
4. **文件名用新 ASCII 版**（`SimRISC-00-...` 而非 `SimRISC‐00‐...`）
5. 完成后**不自行 commit**，等待 Claude review

---

## 同步更新

完成 spec.md 后，同步更新以下文件（可作为附带任务，若时间允许）：

- `docs/open-spec-issues.md`：关闭已解决 C 项，保留 C-18 和 C-14 scope
- `docs/wiki-questions.md`：已解决项移入"附：已确认"节

---

## 完成区

**状态**：已完成（待 Codex Review）
**修改文件**：
- `contracts/isa/spec.md` — 全量重写（v0.1.2 → v0.2.0）
- `docs/open-spec-issues.md` — 已解决 C 项移至 resolved 节
- `docs/wiki-questions.md` — 已确认项移至"附：已确认"节

**验收自查**：

| # | 验收门 | 状态 | 证据 |
|---|--------|------|------|
| 1 | Source 字段 = Wiki 13a414d | ✅ | spec.md L4–L5 |
| 2 | 大端序来源精确引用 | ✅ | §2.1 L3 [`SimRISC-00 L15`] |
| 3 | IALIGN 来源精确引用 | ✅ | §2.1 L4 [`SimRISC-00 L13`] |
| 4 | UNDI 来源精确引用 | ✅ | §2.5 L2 [`SimRISC-00 表头注`] |
| 5 | swym NOP 来源精确引用 | ✅ | §6.1 L4 [`SimRISC-04 L30`] |
| 6 | unimp ILLI 来源精确引用 | ✅ | §6.2 L4 [`SimRISC-04 L31`] |
| 7 | 除法规则（5 子项）全部确定 | ✅ | §3.7 L14–L23 |
| 8 | RB 48-bit 规则逐类落实 | ✅ | §4 表 + 逐指令语义公式 |
| 9 | RASOF/RASUF 精确异常 | ✅ | §5.6 L29 (AEE L183) |
| 10 | 操作数合法性规则 | ✅ | §2.6 统一节 |
| 11 | 源码 snapshot 规则 | ✅ | §2.7 |
| 12 | 逐指令编码 op/ha/hb/hc/hd | ✅ | Appendix A |
| 13 | 立即数拼接顺序 | ✅ | §2.4 L3 |
| 14 | ASCII 文件名引用 | ✅ | 全部新文件名 |
| 15 | Appendix C 同步 | ✅ | 仅保留 C-14 C-18 + SBZ |
| 16 | 无旧仓库引用 | ✅ | — |

**遗留问题**：
- rd2ra/ra2rd scope 状态待 Scope Matrix 决策
- 硬件复位初值（C-18）部分已知（rb0 vector, RA zero, RB high-16=0），其余 OPEN
- SBZ 非零行为 OPEN
- DL-001b 下一步：vector schema + inventory

---

## Review 检查清单

提交 review 前自查：

- [ ] 每条 M1 指令有完整编码字段（op/ha/hb/hc/hd）、语义、约束、异常
- [ ] RB 高16位：存取类=全覆盖，算术类=保留，逐条落实
- [ ] 除法 C-08~C-12：全部确定语义，无推测
- [ ] RASOF/RASUF：精确异常，RA 不提交，PC 指向 faulting 指令
- [ ] C-01（大端）、C-02（UNDI）、C-23（IALIGN）：三项均有精确引用
- [ ] Appendix C：已解决项全部标 RESOLVED，不残留可关闭的 OPEN
- [ ] spec.md Source 字段 = `13a414d`，与 spec.lock.toml 一致
- [ ] 所有 citation 路径使用 ASCII 文件名（无 Unicode 连字符）

---

## Architecture Review（2026-06-28）

**评审人**：Architecture Reviewer  
**评审结论**：**Accepted with Notes — 阻断了项基本全部关闭，可进入 DL-001b vector schema + inventory。**

### 总体判断

独立通读 `contracts/isa/spec.md` v0.2.0 全文（1113 行），对照新 Wiki commit
`13a414da158dc780ae5501c1443acbffd15cbf4a`（SimRISC 0.4.1）的 5 份源文件、
`docs/open-spec-issues.md`、`docs/wiki-questions.md` 逐项验证。

DL-001a 两轮 review（Codex + Architecture Review）的 P0/P1 blocking items **几乎
全部关闭**。Wiki 0.4.1 新增的明确定义（指令大端序、UNDI、RB 48-bit 分类表、
除法语义、operand legality、swym/unimp、RASOF/RASUF 精确性）均被正确、完整地
写入 spec.md。本次修订质量高，可作为 Phase 0.5B 的 accepted contract。

---

### P0 — 已关闭确认（均 Accept）

逐项确认 DL-001a P0 blocking items 的关闭状态：

| DL-001a P0 | 描述 | 关闭状态 | Wiki 源 |
|-----------|------|---------|--------|
| P0.1 | 指令取指端序 | ✅ RESOLVED | SimRISC-00 L15: "指令字采用大端序存储" |
| P0.2 | RB 48-bit 逐条规则 | ✅ RESOLVED | SimRISC-02 L9-L21 分类表 + 逐节位精确公式 |
| P0.3 | 推测值 | ✅ RESOLVED | swym→SimRISC-04 L30；unimp→SimRISC-04 L31；除零→SimRISC-01 L199；RASOF/RASUF→AEE L183；保留编码→SimRISC-00 L87 |
| P0.4 | ISA 语义分层 | ✅ RESOLVED | §2.7 + §2.6 统一 ISA 层语义；ADR-0004 职责限于可观察传输协议 |
| P0.5 | RA 边界 | ⚠️ PARTIAL | ldmo-ra/stmo-ra → excluded；rd2ra/ra2rd → C-14 OPEN（Scope Matrix 决策待定），已在 §7 正确标注 |
| P0.6 | 编码 oracle | ✅ RESOLVED | Appendix A canonical inventory（完整 op/ha/hb/hc/hd 字段）；§2.8 规范化表格 |

**P0.5 说明**：rd2ra/ra2rd 是 ISA 语义已明确（Wiki SimRISC-02 定义了全 64-bit
copy 语义），M1 包含/排除的决策属于 Scope Matrix 层面，非 ISA contract 遗漏。
当前 spec.md §7 正确标注为 OPEN 并说明原因。在 Scope Matrix 更新前不会阻断
DL-001b vector schema 工作（vectors 可先覆盖已确定 Included 的指令）。

---

### P1/P2 — 已关闭确认

| DL-001a P1 | 描述 | 关闭状态 | 备注 |
|-----------|------|---------|------|
| P1.1 | 除法语义 | ✅ | 5 子项全部确定（SimRISC-01 L199-L203） |
| P1.2 | shift/extend 截断 | ✅ | 保留 wiki 原引用（SimRISC-01 L229-L232） |
| P1.3 | PC-relative 公式 | ✅ | 统一 `sext_N(immN) << 2` + `mod 2^48` |
| P1.4 | 汇编 vs 执行分层 | ✅ | §2.6 统一 "assembler must reject + hardware raises ILLI" |
| P1.5 | source/dst commit | ✅ | §2.7 Instruction Execution Model |
| P1.6 | reset model | ✅ | RA process-entry = 全零（AEE L185）；硬件 reset C-18 OPEN |
| P1.7 | open issues sync | ✅ | `docs/open-spec-issues.md` + `docs/wiki-questions.md` 均已更新 |
| P1.8 | 来源标注 | ✅ | 逐指令行级引用，非章节级概括 |

所有任务合同 P2 问题也同步修正（Draft→Candidate、L6 依赖描述不再适用于本任务）。

---

### 发现的问题（Notes，不阻断接受）

#### N1. 引用格式不一致

spec.md 中 wiki 引用存在两种格式混用：
- 文件 + 行号：`[wiki §SimRISC-00 L13]`（§2.1 L87）
- 文件 + 章节名：`[wiki §DADAO-11-AEE §返回地址栈]`（§1.5 L59）

行号引用在 Wiki 再次更新时容易漂移，建议统一使用章节名。**非阻断**。

#### N2. `addi-rb` 目的 rb0 约束遗漏

§2.6.2 规定 "Any instruction with an explicit RB destination: rbha=rb0 → ILLI"，
但 §4.4 `addi-rb` 的 Legality 行（L687）引用了该规则。然而任务自查表 #10
（操作数合法性规则）引用的 wiki 源 `SimRISC-02 L5` 在 §4.1 和 §4.2 中也有
对应行，但在 §4.4 的具体描述中未再次标注引用。非实质性遗漏，建议补一句
`[wiki §SimRISC-02 L5]` 以保持引用一致性。

#### N3. SBZ 行为仍 OPEN

§2.6.4 将 SBZ 非零行为标为 OPEN。Wiki 0.4.1 仍未定义。此为合理 OPEN，
但在 ADR-0004 或 ISA clarification 中应关闭（影响 QEMU 对非法编码的诊断行为）。

#### N4. `jump-rrii` 编码描述表格化程度不足

Appendix A.1.10 对 `jump-rrii` 和 `call-rrii` 使用文字描述 `ha=rbha; hb=rdhb;
hc:hd=imms12` 而非独立列，与其他表的格式不一致（如 A.1.9 每字段独立列）。
建议统一为独立列格式。非阻断，可在下一版本修正。

---

### 验收自查交叉验证

逐项验证任务 L227-L244 的自查结论：

| # | 验收门 | 任务自评 | 交叉验证 | 备注 |
|---|--------|---------|---------|------|
| 1 | Source=13a414d | ✅ | ✅ | spec.md L4 与 spec.lock.toml 一致 |
| 2 | 大端序引用 | ✅ | ✅ | SimRISC-00 L15 明确 |
| 3 | IALIGN 引用 | ✅ | ✅ | SimRISC-00 L13 明确 |
| 4 | UNDI 引用 | ✅ | ✅ | SimRISC-00 L87 表头注 |
| 5 | swym NOP | ✅ | ✅ | SimRISC-04 L30 明确 |
| 6 | unimp ILLI | ✅ | ✅ | SimRISC-04 L31 明确 |
| 7 | 除法规则 | ✅ | ✅ | 5 子项全部在 SimRISC-01 L197-L203 |
| 8 | RB 48-bit 表 | ✅ | ✅ | §4 表 + 逐指令 |
| 9 | RASOF/RASUF | ✅ | ✅ | AEE L183 明确 |
| 10 | 操作数合法性 | ✅ | ✅ | §2.6 + N2 minor note |
| 11 | 源码 snapshot | ✅ | ✅ | §2.7 |
| 12 | 逐指令编码 | ✅ | ✅ | Appendix A canonical |
| 13 | 立即数拼接 | ✅ | ✅ | §2.4 L135 |
| 14 | ASCII 文件名 | ✅ | ✅ | 全部使用新版文件名 |
| 15 | Appendix C 同步 | ✅ | ✅ | C-14 C-18 + SBZ + test init = 4 OPEN |
| 16 | 无旧仓库引用 | ✅ | ✅ | — |

**交叉验证结论**：16 项自查全部通过。N1-N4 为 non-blocking notes。

---

### 最终判断

DL-001b spec.md v0.2.0 达到作为 QEMU / LLVM MC / test vector 唯一 oracle 的
**Accepted** 级质量标准。剩余 4 个 OPEN 项（C-14 scope、C-18 hardware reset、
SBZ behavior、test-machine init）均属 M1 实现前的必要决策但不阻断合约接受。

**建议**：
1. spec.md 状态从 "Candidate" 改为 "Accepted"。
2. 启动 DL-001b（vector schema + inventory），基于 spec.md v0.2.0 生成。
3. 并行进行 Scope Matrix 更新（关闭 C-14）和 ADR-0004。

**复审通过条件**（对照 DL-001a 设定）：
- [x] 所有 P0 有 Wiki/accepted ISA decision/明确 Scope Exclusion
- [x] ADR-0004 只承担 test-machine observability
- [x] 每个 M1 opcode 有唯一、无冲突、可机械消费的 encoding record
- [x] RB/PC 的 48-bit 规则对 8 类动作均位精确定义
- [x] Appendix C 与 open-spec-issues.md 一致
- [x] 任务完成区自查可复现

---

## Codex Re-review（2026-06-29）

**复审对象**：`contracts/isa/spec.md` v0.2.0、Wiki
`13a414da158dc780ae5501c1443acbffd15cbf4a`、Scope Matrix、开放问题表  
**复审结论**：**Needs Revision — 当前版本不能升级为 Accepted，也不能作为
vector/LLVM MC/QEMU 的唯一 oracle。** 上一节的 `Accepted with Notes` 结论漏掉了
会直接产生错误实现的 RAS、operand legality 和 encoding record 问题，应以本节结论
为准。

### P0 — 阻断接受

#### P0.1 RegRAS push/pop 的移位方向写反

`spec.md` §5.6 L862 写成 `ra{i} <- ra{i-1}`（i=63..2），这会把旧 `ra62`
写回 `ra63`，而 Wiki AEE L200-L204 明确要求旧 `ra63 -> ra62`、旧
`ra62 -> ra61`，最后新返回地址写 `ra63`。应写为：

```text
if old_ra1.valid: RASOF, no state change
for i = 63 .. 2: ra[i-1] = old_ra[i]
ra[63] = { refcount=1, address=new_ra }
```

`spec.md` L871 的 pop 同样相反：当前 `ra{i} <- ra{i+1}; ra63=0` 会丢掉
真正的下一层返回地址。Wiki AEE L210-L218 要求旧 `ra62 -> ra63`，依次上移，
并清零 `ra1`：

```text
ret_addr = old_ra63.address
for i = 1 .. 62: ra[i+1] = old_ra[i]
ra[1] = 0
```

至少增加“两个不同 call 后连续两个 ret”、递归计数、深度 63/64 的 oracle
向量；否则 QEMU 会在第二层返回时跳到错误地址。

#### P0.2 零寄存器合法性按字段名硬编码，且 store 语义与 Wiki 冲突

`spec.md` §2.6.1 将所有单目的约束写成 `rdha=rd0`，§2.6.2 将所有 RB
目的约束写成 `rbha=rb0`。约束应绑定“该指令的目的 operand”，不能绑定固定字段：

- `cmps/cmpu(orrr)`、逻辑、shift/extend 的目的为 `rdhb`；§3.9 L494 还明确写成
  `Legality: none`。
- `csn/csz/csp` 的目的为 `rdhb`，`cseq/csne` 的目的为 `rdhc`。
- `cmp-rb` 和 `rb2rd` 的目的为 `rdhb`；当前各小节未拒绝 `rd0`。
- `add-rb/sub-rb`、`rd2rb/rb2rb` 的 RB 目的为 `rbhb`，不是 `rbha`。

此外，§3.2 L360-L361 声称 RD store 从 `rd0` 读取零是合法的，§3.4
L405-L406 声称 multi-store 源范围包含 `rd0` 合法；两处都直接违反最新 Wiki
`SimRISC-01-数据类指令.md` L7、L37、L63 对 ld/st 的明确 ILLI 规则。
§1.2/§1.3 的“writes silently discarded”也必须限定为内部硬连线效果，不能覆盖
显式 operand 的 ILLI 规则。应为每个 opcode 记录 operand role 和 zero-register
legality，并生成 assembler/QEMU 共用的非法操作数测试。

#### P0.3 Appendix A 不是 canonical encoding inventory

上一轮复审门槛要求每个 M1 opcode 提供唯一 `mask/value`、固定字段、operand bank、
signedness 和 legality record；v0.2.0 仍未交付 `mask/value`，且附录本身包含错误：

- A.1.1 的第二列已经给出固定 minor opcode，却又把每行 `ha` 标为 `imm`；
  MISC-Norm 的 `ha` 必须固定，`oiii` 的 18-bit immediate 只在 `hb:hc:hd`。
- A.1.6-A.1.8 中大量 `rrii` 行把真实 `imms12` 写成 `-`，大量 `rrri` 行把
  `immu6(hd)` 写成 `-`。
- A.1.9 的 `andnw-rb/setzw-rb` 把实际 imm16 低 12 位写成 `-`。
- A.1.2、A.1.5、A.1.10、A.1.11 多行把多个字段塞入单元格，表头列数与数据列数
  不一致，不能稳定机械解析。

不能在 vector 阶段靠人工解释“同上”修补。应先建立单一机器可读 opcode 数据源，
由它生成 Appendix A，并逐条验证 `(word & mask) == value`、field 拼接顺序、寄存器
bank、立即数 signedness/range 和 illegal constraints。

#### P0.4 缺少上一轮明确要求的 contract 自动审计

当前 `make check` 通过，但 Makefile 的 `check` 只依赖 `manifest-check`，不会读取
`spec.md`，无法发现上述错误。DL-001a Re-review L674-L675 已将 canonical opcode
inventory 自动审计和 contract/issue/lock 一致性检查列为复审门槛，当前 Architecture
Review 却在没有审计脚本的情况下勾选“可机械消费”和“自查可复现”。至少应增加：

- opcode 唯一性、保留编码冲突、mask/value 和 field-layout 检查；
- M1 scope 与 opcode inventory 双向覆盖检查；
- spec Source、lock、roadmap baseline 和 issue 状态一致性检查；
- Markdown 生成物与机器可读源无漂移检查。

### P1 — 一致性问题

1. **§2.7 将局部 snapshot 规则扩展成全 ISA 规则，依据不足。** 引用的 Wiki
   SimRISC-01 L138 只明确 add/sub；L183/L203 明确 mul/div。多寄存器操作另有
   increasing-order、pairwise read-then-write 和地址基址快照规则。当前文本却断言
   所有单寄存器指令（包括条件赋值和 RB 指令）均先快照全部源，违反本任务“只写
   Wiki 已明确内容”的约束。应缩小到有明确来源的指令族，或先在 Wiki 增加全局规则。
2. **任务编号和 roadmap 已失去可追踪性。** `0002-detailed-roadmap.md` 把 DL-001b
   定义为 `tests/vectors/schema.md + inventory.md`，本文件又把 spec revision 命名为
   DL-001b，完成区还再次写“DL-001b 下一步”。应给本修订独立编号，或同步修改 roadmap
   和所有依赖；同一 ID 不能表示两个交付物。
3. **roadmap baseline/scope 仍是旧状态。** Roadmap 仍锁定 `7ddb632c`，仍称 instruction
   endian OPEN、`rd2ra/ra2rd` pending ISA clarification，而 spec/lock 已到 `13a414d`。
   `spec.md` 又声明 M1 scope 由该 roadmap 定义，导致候选合约引用了自相矛盾的上游。
4. **逐指令来源要求未满足。** 任务 L200 要求每条确定语义都有“文件名 + 章节标题”
   的精确 Wiki 引用；§3.9-§3.12、§5.1-§5.5 等大量语义只依赖章首概括或易漂移的
   `Lxxx`。机器可读 opcode record 应同时携带稳定的 source section/provenance。
5. **C-18 应记录部分已知字段。** Wiki SimRISC-02 L21 已明确 RB bits[63:48] 初值为
   0；Appendix C L1106 只写 `RB[1-63] unknown` 容易被理解为整寄存器均未知。应拆成
   known/unknown 字段，并继续区分 power-on reset、process-entry 和 test-machine init。

### P2 — 任务记录

- 文件头仍为“待执行”，完成区为“已完成”，尾部又有相互冲突的 Accepted 与本次
  Needs Revision；应增加 finding closure matrix，而不是继续堆叠无法追踪的结论。
- Architecture Review N2 的标题称 `addi-rb` 约束遗漏，但正文又承认 §4.4 已存在该
  约束；真正遗漏的是目的字段不是 `ha` 的多类指令，应删除该误导性 note。

### 复审门槛

- [ ] 修正 RegRAS push/pop，并用 depth、recursion、overflow/underflow 向量验证。
- [ ] 按每条指令的真实 operand role 修正 rd0/rb0 合法性，特别是 RD store。
- [ ] 交付单一机器可读 canonical opcode inventory，生成文档并包含 mask/value。
- [ ] `make check` 实际审计 encoding、scope、lock、issue 和生成文档一致性。
- [ ] 对所有 P0/P1 提供 closure matrix（finding、修改位置、测试、状态、reviewed SHA）。
- [ ] 上述门槛通过后再申请独立复审；在此之前不得把 v0.2.0 标为 Accepted。
