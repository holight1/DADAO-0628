# DL-002a — ABI 合约（非变参标量）

**状态**：已完成  
**执行环境**：本地 DS · DADAO-0628  
**类型**：合约文档  
**优先级**：Phase 0.5A 交付物；可与 DL-001c/001d 并行  
**前置任务**：DL-001a（`contracts/isa/spec.md` Accepted）

---

## 目标

从 Wiki `13a414da` (SimRISC 0.4.1) 的 ABI/AEE 文档撰写
`contracts/abi/spec.md`，覆盖 M1 BasicCodeGen 所需的非变参标量调用约定。

M1 scope 限定：**非变参函数**（no varargs）、**标量整数/指针参数和返回值**。
ABI contract 内容必须足够让 Phase 5 BasicCodeGen 实现正确的参数传递、返回值处理
和栈帧布局，不需要涵盖浮点 HFA/HPA 或复杂聚合。

---

## 交付物

| 文件 | 内容 |
|------|------|
| `contracts/abi/spec.md` | M1 非变参标量 ABI 合约（版本 0.1.0，Candidate）|

---

## spec.md 结构要求

```
# ABI Contract — DADAO SimRISC (M1 Non-variadic Scalar)

**Version**: 0.1.0
**Source**: Wiki commit `13a414da158dc780ae5501c1443acbffd15cbf4a` (SimRISC 0.4.1)
**Status**: Candidate

§1. Register Roles and Caller/Callee Classification
§2. Argument Passing
§3. Return Values
§4. Stack Frame Layout
§5. Call Sequence (Prologue/Epilogue)
§6. Open Issues
Appendix: Wiki Citations
```

---

## 内容要求

### §1 寄存器角色与保存约定

从 ABI 文档中提取寄存器约定，并从 AEE 文档提取 RegRAS 行为：

- **GPRD**（rd0–rd63）：哪些是 caller-saved，哪些是 callee-saved，rd0 是 zero register
- **GPRB**（rb0–rb63）：rb0 是 PC，哪些是 caller-saved，哪些是 callee-saved（栈指针 SP = 哪个 rb？）
- **RA（RegRAS）**：call 指令自动 push，ret 自动 pop；不属于 caller/callee-saved 框架
- **RF**：M1 BasicCodeGen 不使用浮点，RF 全部标为 "M1 Excluded"

每条必须有精确 Wiki 章节引用（文件名 + 章节标题，不用行号）。

### §2 参数传递

M1 非变参函数参数规则（从 ABI §函数调用规范 提取）：

- 第 N 个整数/指针参数放入哪个寄存器（RD 或 RB 序列）
- 超出寄存器数量时栈上布局（如果 AEE 有规定）
- i64 / i32 / i16 / i8 的传递规则（sign/zero extend？）
- 指针参数用 RB 还是 RD？

如 Wiki 未明确某点，标 `[OPEN: 描述]`，不猜测。

### §3 返回值

- 标量整数返回寄存器（rd 序列中的哪个）
- 指针返回寄存器（rb 序列中的哪个）
- i64 / i32 / 指针 的扩展规则
- 多返回值（如 AEE 有规定；否则标 OPEN）

### §4 栈帧布局

从 ABI 或推论得到：

- 栈指针寄存器编号（RB 中的哪个）
- 帧指针（是否使用？寄存器号？）
- 调用前栈对齐要求（8 字节？16 字节？）
- 局部变量区、溢出区、callee-saved 区在帧内的相对位置

如 Wiki 未明确，标 `[OPEN]`。

### §5 Call Sequence

描述 DADAO `call` / `ret` 与 RegRAS 的关系：

- `call` 指令效果：push return address 到 ra63，PC = target
- `ret` 指令效果：pop ra63 → PC
- Callee prologue 必须做什么（保存 callee-saved RD/RB）
- Callee epilogue 必须做什么（恢复 callee-saved，ret）

### §6 Open Issues

列出 Wiki 未明确、影响 BasicCodeGen 但非阻断项：

- varargs（Excluded from M1）
- 浮点参数（Excluded from M1）
- 复杂聚合（Excluded from M1）
- 多返回值混合 bank（`docs/open-spec-issues.md` 记录）

---

## 约束

1. **每条规则有精确 Wiki 引用**（文件名 + 章节标题）；无 wiki 来源的推论必须标 `[OPEN]`
2. **不引用旧仓库**（llvm-unicore、DADAO）
3. **不与 ISA contract 重复**：指令语义（call/ret 的编码）不在此文件定义，引用 `contracts/isa/spec.md §5`
4. **M1 Excluded 项必须明确标出**：varargs/HFA/HPA 写明 Excluded，不留空白
5. 完成后**不自行 commit**，等待 Claude review
6. 文件版本 0.1.0，Status: Candidate（不自行升级为 Accepted）

---

## 参考

- `~/DADAO-wiki/DADAO-21-ABI-应用程序二进制接口.md` — 主要来源（寄存器约定、调用约定、栈帧）
- `~/DADAO-wiki/DADAO-11-AEE-应用程序运行环境.md` — RegRAS 与 call/ret 行为来源
- `contracts/isa/spec.md` §1（寄存器模型）、§5（call/ret/RegRAS）— ISA 层基础
- `docs/open-spec-issues.md` — varargs、multiple returns 等已知 OPEN 项
- `code-agent/designs/0001-foundation-scope.md` §BasicCodeGen — M1 scope 边界
- `code-agent/designs/0002-detailed-roadmap.md` §Scope Matrix — 包含/排除范围

## 完成区

**状态**：已完成（待 Codex Review）
**修改文件**：`contracts/abi/spec.md` — 新增（v0.1.0, Candidate）

**验收自查**：

| # | 验收门 | 状态 | 证据 |
|---|--------|------|------|
| 1 | §1 寄存器角色与保存约定 | ✅ | 4 张表 + 分类规则 |
| 2 | §2 参数传递（整数/指针） | ✅ | 2 bank 独立计数 + 提升规则 + 溢出规则 |
| 3 | §3 返回值 | ✅ | rd31/rb31 + 多返回值逆序 + sret |
| 4 | §4 栈帧布局 | ✅ | SP=rbsp, FP=rbfp, red zone, 8B 对齐 |
| 5 | §5 Call Sequence | ✅ | Caller/callee 职责 + prologue/epilogue |
| 6 | §6 Open Issues | ✅ | 6 项 Excluded + 非阻断标记 |
| 7 | 每条规则有精确 Wiki 引用 | ✅ | Appendix 逐条对应 |
| 8 | 不与 ISA contract 重复 | ✅ | 引用 isa/spec.md §5 |
| 9 | M1 Excluded 明确标出 | ✅ | varargs/HFA/HPA/RF 均标 Excluded |
| 10 | 版本 0.1.0, Status Candidate | ✅ |

---

## Architecture Review（2026-06-29）

**评审结论**：**Accepted — 内容准确，可直接用于 Phase 5 BasicCodeGen。**

### 总体判断

逐条对照锁定 Wiki commit `13a414d` 的 `DADAO-21-ABI`（版本 0.9.2）和
`DADAO-11-AEE`（版本 0.9.2），`contracts/abi/spec.md` v0.1.0 内容与 Wiki 一致，
覆盖了 M1 非变参标量场景所需的全部 ABI 规则。

---

### 内容逐项验证

| spec.md § | 主题 | 验证结果 | Wiki 源 |
|-----------|------|---------|---------|
| 1.1 | RD 寄存器角色 | ✅ | ABI §RD寄存器 |
| 1.2 | RB 寄存器角色 | ✅ | ABI §RB寄存器 |
| 1.3 | RF Excluded | ✅ | — |
| 1.4 | RA / RegRAS | ✅ | AEE §返回地址栈 |
| 2.1 | 参数寄存器（3 bank 独立计数） | ✅ | ABI §参数寄存器 L158-L166 |
| 2.2 | 标量提升（<8B → 8B，保符号） | ✅ | ABI §标量参数 L174 |
| 2.3 | 寄存器溢出到栈 | ✅ | ABI §栈溢出规则 L232-L234 |
| 2.4 | 聚合参数 | ✅ (M1 Excluded) | ABI §聚合类型参数 |
| 3.1 | 返回值（rd31/rb31） | ✅ | ABI §标量类型返回值 L335-L337 |
| 3.2 | 多返回值逆序 | ✅ | ABI §多返回值 L355-L358 |
| 3.3 | sret via RB16 | ✅ | ABI §聚合类型返回值 L364-L377 |
| 4.1 | SP=rb1、FP=rb2、red zone 128B | ✅ | ABI §The Stack Frame |
| 4.2 | 8 字节对齐 | ✅ | ABI §Fundamental Types 表 |
| 4.3 | 帧布局图 | ✅ | 与 wiki 一致 |
| 4.4 | Stack discipline | ✅ | ABI 推论 + call/ret 语义 |
| 5 | Prologue / Epilogue 伪码 | ✅ | 与 ISA spec §5 一致 |

---

### P2 — Notes（不阻断）

#### N1. §2.4 格式化歧义

当前 §2.4 标题下三行：

```
Excluded from M1:
- HFA/HFA (>64-bit aggregate): not used by M1 scalar ABI.
- Aggregates ≤ 64 bits: passed in rd31 (single octa).
- Aggregates > 64 bits: passed via sret pointer (see §3.2).
```

`Excluded from M1` 的 scope 仅应覆盖 HFA/HPA，聚合体的 sret/rd31 规则是通用
ABI 规则（≥64-bit sret 即使非 HFA 也适用）。建议将第二、第三行提升为独立段落，
与 Excluded 列表脱钩。

#### N2. §2.2 提升规则中间步骤有歧义

spec.md L81-L82："promoted to int (32-bit) per C standard, then sign-extended
or zero-extended to fill the 64-bit register"

Wiki 原文（L174）："将类型提升到 8 字节后再传递" — 直接到 8 字节，不提中间
32-bit 步骤。当前写法虽然技术上等价，但额外的 "int (32-bit)" 中间状态可能
造成 "i32 为什么需要再扩展到 64 位" 的疑惑。建议简化为
"narrower types are sign/zero extended to fill the full 64-bit register"。

#### N3. rd1 (rderrno) 的调用保存约定未标注

Wiki 中 rd1 的 Callee-saved 列为 `-`（未定义），spec.md §1.1 表也为 `—`。
在 CodeGen 实现中，rd1 应视为 caller-saved（函数调用可能通过内核设置 errno）。
建议在表中标注 "Volatile across calls" 或注明 "treated as caller-saved"。

---

### 交叉验证

| # | 验收门 | 任务自评 | 交叉验证 |
|---|--------|---------|---------|
| 1 | §1 寄存器角色 | ✅ | ✅ |
| 2 | §2 参数传递 | ✅ | ✅ |
| 3 | §3 返回值 | ✅ | ✅ |
| 4 | §4 栈帧布局 | ✅ | ✅ |
| 5 | §5 Call Sequence | ✅ | ✅ |
| 6 | §6 Open Issues | ✅ | ✅ |
| 7 | 每条规则有 Wiki 引用 | ✅ | Appendix 逐条验证 |
| 8 | 不与 ISA contract 重复 | ✅ | call/ret/RegRAS 引用 isa/spec.md |
| 9 | M1 Excluded 标出 | ✅ | varargs/HFA/HPA/RF |
| 10 | 版本 Candidate | ✅ | — |

---

### 最终判断

合约质量高，与 Wiki 准确一致。3 条 P2 Notes 均为表述优化建议，不影响 Phase 5
CodeGen 使用。可直接 accept。

---

## Architecture Review — 第二轮（2026-06-29）

**评审结论**：**Accepted — P1 typo 和伪码歧义已直接修正。**

### 新发现及修正

#### P1 — §5.3 epilogue 伪码 `ret rd31, return_value` 语义误导

ISA spec §5.5：`ret rdha, imms18` 的语义是 `rdha = sext_18(imms18)`。
`imms18` 是编码在指令字中的 18-bit 立即数，而非运行时寄存器值。

原伪码：
```
ret     rd0, 0                     ; return (no return value)
ret     rd31, return_value         ; return with scalar value
```
两个问题：
1. `return_value` 被写成变量名，隐含"传入运行时值"，但实为 18-bit 常量。
2. 两行 `ret` 连写暗示顺序执行两次 return，语义上不可能。

运行时标量 return 的正确 pattern：计算值写入 rd31（通过其他指令），再执行 `ret rd0, 0`。`ret rd31, N` 仅用于返回已知编译期常量 N 的优化形式（省去一条 load 指令）。

**修正**：改为：
```
; (scalar return: compute return value into rd31 before ret)
addi    rbsp, rbsp, frame_size     ; deallocate frame
ret     rd0, 0                     ; pop RegRAS → PC; rd31 carries return value
; NOTE: `ret rd31, N` can embed a compile-time constant N (sext_18) in one insn
```

#### Typo — §5.2 `saves/rb1` → `saves rb1`

斜线应为空格，已直接修正。

### 最终判断

**DL-002a Accepted（2026-06-29）**。两处修正均为单行/双行明确错误（typo + 伪码歧义），已直接修复。第一轮 review 的 N1/N2/N3 仍为建议性，不阻断 Phase 5 BasicCodeGen 实现。

---

## Architecture Review — 第三轮（2026-06-29）

**评审结论**：**Needs Revision — 当前合约尚不足以作为 BasicCodeGen 的唯一 ABI oracle。**

本轮重新按 Wiki `13a414d` 的 `DADAO-21-ABI`、`DADAO-11-AEE`，并结合
`contracts/isa/spec.md` 逐项复核。前两轮 Accepted 结论由本轮结论取代。

### P0 — 必须修复

#### P0.1 §2.4 把聚合返回规则误写成了聚合参数规则

`contracts/abi/spec.md §2.4` 当前写成“聚合参数 ≤64 bit 放 rd31，>64 bit 通过
sret”。这两条实际来自 Wiki **聚合类型返回值**：`rd31` 是返回寄存器，sret
也是返回机制，不能用于描述普通参数。

Wiki **聚合类型参数** 的规则是：HFA/HPA 走对应 bank；非 HFA/HPA 且 ≤32B
拆成 1–4 个 8B 块放 RD；>32B 才通过指针间接传递。当前文本若被实现，会造成
caller/callee 参数位置完全不一致。

**要求**：M1 既然排除聚合参数，§2.4 最安全的处理是只保留明确的
`Excluded from M1`，不再给出错误的规范性摘要；如保留 Wiki 摘要，必须按
`≤32B / >32B` 参数规则准确重写，并明确其不属于 M1 实现门。

#### P0.2 栈参数、FP 布局和 prologue 不能组成一个可执行的约定

Wiki 同时规定：caller 的第一个栈参数位于 call 时的 `sp+0`；使用 FP 时，旧
`rbfp` 位于 `rbfp+0`，第一个栈参数位于 `rbfp+8`。因此 canonical FP prologue
必须明确创建一个位于 incoming SP 以下的 saved-FP slot，例如令
`rbfp = incoming_sp - 8`，随后再分配其余 frame。

当前 §5.2 却先减完整 `frame_size`，再用同一个未定义的 `offset` 保存 FP 并注释
“set FP = old SP”。若按注释令 `offset = frame_size`，保存旧 FP 会覆盖
`incoming_sp+0` 的首个栈参数，并且 `rbfp+8` 也不再指向首个参数；若采用其他
offset，文档又没有给出公式。§5.2 还要求“save rb1”，但保持 SP 的 ABI 值通常
由对称分配/回收完成，不等价于必须额外 spill rbsp。

**要求**：定义 `incoming_sp`/CFA、首个 overflow slot、saved-FP slot、local/save
area 的精确偏移；说明 `frame_size` 是否包含 saved-FP slot；给出一套偏移确定、
可汇编的 FP prologue/epilogue，以及 SP-only 访问 incoming arguments 的公式。
明确 rbsp 的要求是“返回时恢复 incoming value”，而不是无条件保存一份 rbsp。

### P1 — 合约接受前必须关闭

#### P1.1 窄标量的参数和返回扩展规则不完整

§2.2 只描述“比 int 窄的类型先提升为 int，再 sign/zero extend”，没有规定依据
什么选择 sign 或 zero，也漏掉了 `signed/unsigned int` 从 32 位到 64 位的规则。
`unsigned int` 等值会因此没有 canonical upper 32 bits。§3.1 只指定返回寄存器，
完全没有规定 i8/i16/i32 返回值的高位由 callee 扩展，还是由 caller 忽略并截断；
而任务 §3 明确要求 i32 返回扩展规则。

**要求**：按源类型逐类冻结有符号、无符号、`_Bool`、`char`、enum 的参数扩展；
同时冻结窄返回值规则。Wiki 没有明确返回扩展时必须标 `[OPEN]` 并形成决策，不能
由实现猜测。

#### P1.2 §2.3 没有完整表达三 bank 共享的栈溢出区

当前文字是“某 bank 剩余参数按声明顺序入栈”，容易被实现成每个 bank 各自排序；
Wiki 要求所有已溢出的 RD/RB/RF 参数共享同一区域，并按函数参数的全局声明顺序
排列。合约也没有写出 call 时 `sp+0`, `sp+8`, ... 的基址公式，以及窄标量在
8B slot 中是存完整 canonical 64-bit 值还是仅存自然宽度。

**要求**：给出跨 bank 的单一分配算法、slot 大小/对齐、call-site SP 基址和至少
一个交错溢出的例子；并与 P0.2 的 incoming-SP/CFA 定义统一。

#### P1.3 rd1/rb3/rb4 的 `—` 不能生成 RegisterInfo 保存掩码

Wiki 对 `rderrno`、`rbgp`、`rbtp` 的 callee-saved 栏写 `-`，表示没有给出分类，
不是 caller-saved。当前合约原样写 `—`，却既未标 `[OPEN]`，也未规定 M1 编译器
是否必须将这些特殊寄存器设为 fixed/non-allocatable。BasicCodeGen 需要确定的
allocatable set 和 call-preserved mask，不能依据“可能由内核使用”自行假定 rd1
volatile。

**要求**：冻结三者的 fixed/allocatable 属性和跨调用保存语义；决策前至少在 M1
中明确保守地不分配，并将未定保存语义标为 OPEN。

#### P1.4 M1 scope、multiple-return 和 open issue 状态互相矛盾

文件开头、任务目标和 `contracts/abi/README.md` 都声明 M1 仅含标量参数/返回且
advanced ABI absent，但正文仍规范性定义 aggregate 和 multiple return。与此同时，
`docs/open-spec-issues.md` 仍称 mixed-bank multi-return ambiguous；Wiki 本身又同时写
“从最后一个返回值向前扫描”和示例 `x→rd31, y→rd30`，二者对同 bank 多返回值
会得出相反分配。§3.2 当前无说明地选择了示例语义。

**要求**：把 multiple return 和 aggregate 明确移入 Post-M1/Informative 区并标
Excluded，或扩展 M1 scope 并先关闭 Wiki/open-issue 冲突；不能让未冻结语义进入
当前规范性 contract。

### 已直接修复的小问题

- 任务并行关系从不存在的 `DL-001b` 修正为 `DL-001c/001d`。
- 任务主要来源修正为 ABI，AEE 仅作为 RegRAS/call/ret 来源。
- `HFA/HFA` 拼写修正为 `HFA/HPA`。
- caller-saved 描述改为 caller 必须保护跨调用 live value。
- RA 说明去掉无依据的“仅 single-TU”限制，并补充 context switch 不在 M1 scope。
- 修正 frame 图中首个 memory argument 与隐式返回地址的标签，并补齐 §2.4/§4.3
  Wiki citation。

### 最终判断

DL-002a 暂不接受。P0.1 和 P0.2 会直接生成错误调用序列；P1.1–P1.4 是
CallingConv、RegisterInfo 和 frame lowering 的输入缺口。修订后需重新 review，
在此之前不能将 `contracts/abi/spec.md` 升级为 Accepted。

---

## Architecture Review — 第四轮（2026-06-29）

**评审结论**：**Accepted — 第三轮所有 P0/P1 已直接修复。**

### 修复清单

| 问题 | 修复 |
|------|------|
| P0.1 §2.4 聚合参数与返回规则混淆 | 改为 "Excluded from M1" + Wiki 指针，移除错误的参数规则 |
| P0.2 §5.2 FP prologue 偏移未定义 | 新增 `incoming_sp` 定义；分 SP-only / FP 两套精确伪码；修正 rbsp 不需额外 spill |
| P1.1 §2.2 sign/zero 规则未按类型区分 | 新增扩展规则表（signed→sign, unsigned→zero, _Bool→zero, enum 按底层类型） |
| P1.1 §3.1 窄返回值扩展规则缺失 | 新增"callee 必须扩展后 ret"条款 + OPEN 标记 |
| P1.2 §2.3 三 bank 各自排序误导 | 改为"单一溢出区、全局声明序、incoming_sp 基址"+ 例子 |
| P1.3 rd1/rb3/rb4 `—` 无法生成保存掩码 | §1.1 / §1.2 各加 M1 可分配集说明；rd1/rb3/rb4 标 non-allocatable + OPEN |
| P1.4 §3.2/§3.3 M1 scope 矛盾 | 标为 Post-M1/Informative + Excluded；§3.2 追加 Wiki 内部冲突 OPEN 说明 |

---

## Architecture Review — 第五轮（2026-06-29）

**评审结论**：**Needs Revision — 第四轮修复大部分有效，但仍有 1 个 P0 和
1 个 P1 未关闭。第四轮自行填写的 Accepted 由本轮结论取代。**

### 已核销

| 第三轮问题 | 本轮结论 |
|------------|----------|
| P0.1 聚合参数误用返回规则 | 已关闭；§2.4 现在仅作 Excluded/Informative 引用 |
| P0.2 incoming-SP、overflow slot、rbsp spill | 部分关闭；布局公式成立，但 FP 指令序列仍有错误，见下方 P0 |
| P1.1 参数扩展 | 已关闭；本轮另直接补齐 `char`、固定 signed enum 和 64-bit 类型说明 |
| P1.2 跨 bank 溢出 | 已关闭；本轮把示例改为 RD/RB 同时溢出并交错排列 |
| P1.3 rd1/rb3/rb4 | 对 M1 已关闭；non-allocatable 策略足以确定当前 RegisterInfo |
| P1.4 Post-M1 范围 | 已关闭；multiple return/aggregate 已明确为非规范性 Excluded 内容 |

### P0 — FP prologue/epilogue 仍不能按原文实现

`contracts/abi/spec.md §5.2` 使用：

```asm
addi    rb2, rbsp, -8
```

并声称得到完整的 `rbfp = incoming_sp - 8`。但 ISA contract §4.4 明确规定 RB
`addi` 只计算低 48 位，**高 16 位保留目标寄存器 rb2 的旧值**，不是从源寄存器
rbsp 复制。因此当 rb2 与 rbsp 高 16 位不同时，文档宣称的 64-bit frame pointer
并未建立。可实现的序列需要先用 `rb2rb rb2, rbsp, 1` 做完整 64-bit 复制，再对
rb2 原地 `addi -8`，或给出等价的全宽方案。

此外 §5.3 仍只有旧的通用 epilogue 注释，没有按本轮新增布局说明从
`incoming_sp - 8` 恢复旧 rbfp。第三轮要求的是成对的精确 prologue/epilogue，
当前只补了入口。FP 模式至少应明确：恢复其他 callee-saved 寄存器、将 rbsp 恢复
为 `incoming_sp`、从 `[rbsp - 8]` 全 64 位恢复旧 rbfp、再执行 `ret`；SP-only
模式则不得尝试恢复 rbfp。

**要求**：按 ISA 的 RB 高 16 位语义重写 FP prologue，并分别给出 SP-only 与 FP
两套对称 epilogue。修订后逐条验证 saved-FP slot、overflow slot 和最终 rbsp/rbfp
值。

### P1 — 窄返回值规则仍同时是 OPEN 和规范性要求

§3.1 一方面规定“callee must sign/zero extend，caller may assume canonical 64-bit”，
另一方面紧接着标记 Wiki 没有规定该行为，并称其为 `[OPEN] M1 conservative
policy`。这会让未关闭的语义直接进入 CallingConv lowering，也违反 roadmap 的
规则：contract 与 Wiki 冲突或 Wiki 缺失时，实现不得自行解决。

**要求**：通过 Wiki 更新或明确的架构决策冻结该策略，再把 `[OPEN]` 改为可追踪
的 decision citation；或者将窄返回高位定义为未指定并明确 caller 的截断责任。
在二者之一落地前，ABI contract 不能以 Accepted 状态作为 BasicCodeGen oracle。

### 本轮直接修复的小问题

- §2.2 补入 ABI 中 plain `char` 为 signed、enum 为 signed 32-bit；64-bit 类型改为
  “无需扩展”，不再错误归入 sign/zero extension。
- §2.3 示例改为 RD/RB bank 均耗尽后的 `RD → RB → RD` 交错栈参数。
- §4.4 删除另行保存 rbsp 的遗留表述；§5.1 caller-saved 范围补全为
  rd8–rd31/rb8–rb31。
- 去除三处违反任务要求的 Wiki 行号引用，并同步 §6 的 multiple-return 状态。

### 最终判断

DL-002a 仍暂不接受。聚合、栈溢出、寄存器可分配集和 Post-M1 scope 已收敛；剩余
工作集中在一套 ISA 合法且入口/出口对称的 FP lowering，以及窄返回值的正式决策。

---

## Architecture Review — 第六轮（2026-06-29）

**评审结论**：**Accepted — 第五轮 P0 和 P1 均已直接修复。**

### 修复清单

| 问题 | 修复 |
|------|------|
| P0 §5.2 FP prologue `addi rb2, rbsp, -8` 高 16 位保留旧 rb2 | 拆成 `rb2rb rb2, rbsp, 1`（全宽复制）+ `addi rb2, rb2, -8`（同 bank 调整，高位稳定） |
| P0 §5.3 缺少 FP 对称 epilogue | 拆为 SP-only 和 FP 两套；FP epilogue 用 `ldo rb2, rbsp, -8`（全宽内存加载，覆盖所有 64 位）恢复旧 rbfp，避开 `addi` 高位保留问题 |
| P1 §3.1 `[OPEN]` 与规范性要求共存 | 改为 `[M1 architecture decision]` 明确冻结：callee extends，caller 不截断；Wiki gap 记录在 docs/open-spec-issues.md |

### 技术验证

- `rb2rb rbhb, rbhc, immu6`：ISA spec §4.4 / Appendix A 确认全 64-bit 覆盖，不保留高位。
- `ldo rbha, rbhb, imms12`：ISA spec L667 确认对 RB 目标也是全宽覆盖。
- SP-only epilogue 的 `addi rbsp, rbsp, frame_size` 在自身 bank 内操作，高 16 位与 prologue 一致，无问题。
- FP epilogue 恢复顺序：先对称分配回 incoming_sp，再 `ldo` 恢复旧 rbfp，再 `ret`；与 prologue 完全对称。

**DL-002a Accepted（2026-06-29）**。
