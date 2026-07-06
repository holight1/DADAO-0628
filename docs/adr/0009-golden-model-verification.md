# ADR-0009: 验证链机械化（wiki 审计 · golden model · legality 矩阵）

**状态**：Accepted（2026-07-06）
**日期**：2026-07-06
**关联**：ADR-0007（测试方法论·独立预期值）、ADR-0004（Test Machine·exit-MMIO）、ADR-0003（ELF ABI）、ADR-0001（Greenfield）

---

## 背景

### 现状是一条翻译链，不是差分

DADAO 的验证路径是 `wiki → spec → test → QEMU`，同时 `spec → LLVM`。它**不是** differential——差分靠两个独立实现对同一 spec 的**分叉**暴露错误；这条是**带人工步骤的传递翻译链**，无横向交叉校验。**某环误读上游，下游一致继承，无分叉可检测。**

| 环 | 类型 | 机械 backing | 强度 |
|----|------|------------|------|
| wiki → spec | 人工翻译 | `check_wiki_drift` 仅查 SHA，不查语义；§ 引用未验证指向存在 | **弱** |
| spec → YAML | 人工推导 | `validate_encoding` + 独立预期值纪律 + 87/87 opcode identity | 中 |
| YAML → QEMU | 机械 | harness XOR 比对 + fault 断言 + 非零退出 | 强 |

**根问题**：QEMU、LLVM、YAML **全部从 spec.md 派生**，spec.md 是**单点故障**——它一处误读 wiki，三者一起错、互相还都同意，无差分可抓。

### 框定（本 ADR 采用）

- **wiki 视为 ground truth**，其合理性不在本 ADR 讨论范围。
- **核心诉求 = 保证 `wiki → QEMU → LLVM` 一致性。**
- 决定性约束：`~/DADAO-wiki` 是 16 个纯 markdown（SimRISC 规格文档），**非可执行**。故不存在可机械对照的 wiki oracle，`wiki→X` 的忠实度**不可约地含一步人工翻译**。

---

## 项目定位与终局（决定 Sail 的取舍）

- **DADAO-0628 产品终点** = QEMU + LLVM（教学/研究工具链，不含 RTL）。
- **研究终局** = 下一个自定义 ISA + RTL。DADAO-0628 的真正交付物是**可迁移到下个项目的流程与工具**（同 ADR-0001 greenfield 定位、知识图谱抽取）。
- **推论**：Sail（RTL tandem / 形式化的黄金参照）是**下个项目**最需要、也最贵的一块。**现在是爬 Sail 学习曲线最便宜、最低风险的时刻**（87 条标量指令、无 MMU/RTL/流片风险）。故 Sail 以**方法论彩排**身份纳入 —— 不是 scope creep，正是本项目该产出的方法论资产。

---

## 决策

引入**相互独立的机制**，各机械化链上不同的环，**各自诚实标注射程**。不追求单一工具闭合全链。

### M1：wiki→spec 审计器（最弱环，最高优先，可迁移）

机械校验 spec.md 每个 `[wiki §…]` 引用**指向真实 wiki 内容**；揪出每一条**无 wiki 引用的规范性断言**（约 30 条）。是 `check_wiki_drift` 的升级版。**射程**：把"信任"改成"可审计"（每条断言可溯源、无凭空规则），**不保证** wiki 被正确理解——对高风险语义（RB 48-bit、RAS push/pop 方向、overlap/SBZ）辅以第二人独立读 wiki。此工具可直接迁移下个项目。

### M2：wiki 派生的独立黄金模型（双层，角色不同非冗余）

**共同要求**：黄金模型必须**从 wiki 直接派生、由不同于 QEMU 作者的人写**，encoding 层从 `opcodes.yaml` 生成/交叉校验（不造第三套编码真相）。只有 wiki 派生（不走 spec.md）才能让 `模型 vs QEMU` 差分抓到 **spec.md 翻译错误**，而非只是"拿 spec.md 跟自己比"。

- **M2a — Python 解释器（DADAO 自控的"工作黄金模型"，近期）**
  87 指令纯语义 + RD/RB/RF/RA bank + 内存 + fault。**DADAO 自控、快、随时可用**，开发期持续差分 QEMU 靠它。**非权威**（无 wiki 团队背书），但独立于 QEMU，抓 QEMU 实现 bug + 已入 QEMU 的 spec.md 翻译错误。同时**交叉校验/喂养 M2b 的编写**。

- **M2b — Sail 模型（"权威黄金模型"，彩排起步 → 跨下个项目）**
  Sail（通用 ISA 语义语言，非 RV 专用，可生成 C 仿真器 / 定理证明定义 / 文档；RISC-V 官方黄金模型即 sail-riscv）。**要成为权威，必须经 wiki 团队人工审核背书**——这是 DADAO 控制不了的外部依赖、节奏慢。故：
  - **现在**：限时**垂直切片彩排**（算术+load/store+控制流约 20–30 条），跑通 `wiki → Sail → 生成 C 仿真器 → 差分 QEMU`，作为下个项目的流程去风险。Type-A spike，crisp 目标 = "Sail 仿真器 vs QEMU 在编码向量 + 若干程序上 0 分叉（分叉即真 bug）"。
  - **完整 Sail（87 条）+ wiki 团队审核背书 + RTL tandem + 形式化** → 跨入/归属**下个项目**。

  **为何 M2a 与 M2b 都要**：Sail 权威性依赖外部 wiki 团队审核（慢、不可控）→ Python 是 DADAO 自控、随时可用的黄金模型，不阻塞于审核周期。二者分工 = **速度/自控（Python） vs 权威/背书（Sail）**。

### M3：生成式 legality 矩阵（fault 完备性，可迁移）

87 指令 × 每类非法输入（rd0 做目标、immu6=0、保留编码、SBZ 非零、非对齐…）机械生成编码 + 断言 QEMU 抛正确 fault。非法输入空间逐指令**可穷尽**。**射程**：fault 空间完备；不覆盖深层语义交互（属 M2 差分）。独立于 M1/M2。

---

## 射程总表

| 机制 | 保证 | 不保证 |
|------|------|--------|
| M1 wiki 审计 | 每条 spec 断言可溯源 wiki、无凭空断言 | wiki 被正确理解（需人 + 独立重读） |
| M2a Python 黄金模型 | QEMU 匹配 wiki 派生模型（生成式，含抓 spec.md 翻译错误）；DADAO 自控随时可用 | 非权威；模型与 QEMU 若对 wiki 相同误读则抓不到（相关性误差） |
| M2b Sail 黄金模型 | 同上 + **wiki 团队审核后成权威**；可生成形式化定义 | 权威性依赖外部审核；87 全量 + RTL tandem 属下个项目 |
| M3 legality 矩阵 | 每指令每类非法输入 QEMU 抛对 fault | 深层语义交互 |
| （下个项目）RTL tandem + 形式化 | QEMU/RTL/Sail 互证、可证明 | 需 RTL + Sail 权威版存在 |

**净效果**：机械保证不了"QEMU==wiki"（散文所限），但压缩成 **"QEMU==wiki 派生黄金模型（M2 生成式 / M3 穷尽 fault，DADAO 自控） + 黄金模型==wiki（M2b 经 wiki 团队审核 / M1 可审计引用）"**。这是散文 wiki + 外部团队下的诚实上限。

---

## 备选方案（已否决）

| 方案 | 否决理由 |
|------|---------|
| 直接引入 Spike | RV 专用，移植=重写；Sail 才是通用 ISA 语义语言 |
| 现在就上完整 Sail + RTL tandem + 形式化 | 单实现阶段无 tandem 对象；Sail 全功率收益要 RTL/SMP；且权威版需外部审核 |
| 只做 Sail、不要 Python | Sail 权威依赖外部 wiki 团队审核（慢/不可控），开发期需 DADAO 自控的黄金模型兜底 |
| 只做 Python、不碰 Sail | 研究终局是 ISA+RTL，Sail 迟早要；现在是最便宜的彩排时机 |
| 维持纯枚举向量 | 角落 bug 欠功率、无法证明完备、追不上 CodeGen 生成程序 |
| 信任现有翻译链 | spec.md 单点故障，一致性错误不分叉、无法检测 |

---

## 优先级与时序（含带宽纪律）

Phase 5 CodeGen 是当前主线，且其 spike 已磕三次（DS 报告失真）。**别在 CodeGen spike 收口前塞入 Sail 彩排**——带宽/注意力是真的。

1. **现在**（便宜、不抢 CodeGen 带宽）：M1 wiki 审计器 + M3 legality 矩阵。
2. **近期**：M2a Python 解释器 = 开发期工作黄金模型（wiki 直派、QEMU 独立、不同作者）。
3. **CodeGen spike 收口后**：独立、带 charter + 时间盒的 **M2b Sail 彩排 spike**（垂直切片）。
4. **下个项目**：完整 Sail + wiki 团队审核背书 + RTL tandem + 形式化。

---

## 影响

| 得到 | 代价 |
|------|------|
| 各弱环获机械 backing，射程诚实、不互相冒充 | 多条独立工作线 |
| 黄金模型枚举→生成，抓交互角落 + spec.md 翻译错误 | 黄金模型建两次（Python + Sail）——但角色不同（自控 vs 权威），非纯冗余 |
| Sail 流程在低风险小 ISA 上去风险，直接迁移下个 ISA+RTL 项目 | Sail 学习/集成一次性税 |
| fault 完备性可穷尽 | M3 随 spec legality 规则更新 |

---

## 与 ADR-0007 的关系

**扩展**非替代。独立预期值原则不变；本 ADR 把 oracle 从静态向量升级为可执行模型（M2）、wiki 忠实度从人工信任升级为可审计 + 外部背书（M1 + M2b）、fault 覆盖从手写升级为生成（M3）。核心动作一致：**把软目标绑到机械、可生成/可审计的证据上。**

---

## 待定（需拍板）

1. **M2a decode 生成程度**：语义手写不可免，decode 层从 opcodes.yaml 生成。
2. **M2a 作者独立性**：由不同于 QEMU 实现者的 DS 写，保证差分独立。
3. **M1 是否并入 `make check`**：倾向是（fail-closed，与 check_wiki_drift 并列）。
4. **M2b Sail 彩排的 charter/时间盒**：CodeGen spike 收口后单独定。

---

## 状态说明

**Accepted（2026-07-06）**。按优先级拆任务：**M1 审计器（DL-039a，进行中）** → M3 legality 矩阵 → M2a Python 黄金模型 + 差分 →（CodeGen spike 收口后）M2b Sail 彩排 → 下个项目：完整 Sail + wiki 团队审核 + RTL tandem。
