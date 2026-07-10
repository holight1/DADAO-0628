# SL-001a: Sail 调研（M2b 定位 B · 真实芯片项目流程 · 只调研不实现）

**执行环境**: 本地 DS · DADAO-0628（调研任务）

**状态**: 已完成

**依据**: ADR-0009 §M2b（Sail 彩排）；架构决策 2026-07-10：定位 B（Sail 作权威可执行 spec）、目标=为后续真实芯片项目走通「权威 spec → 模拟器/形式化/RTL tandem」流程

---

## 目标与边界

**只调研、产出报告，不写任何 Sail 代码、不装工具链改动系统。** 目的是把「用 Sail 作**权威可执行 spec**（定位 B）」这条路的做法、工具链、流程、对 DADAO 的可行性摸清，供架构师据此写 M2b charter + 垂直切片任务。

**定位 B**：Sail 不是第 4 个从 spec.md 派生的模拟器，而是**新的权威源**——spec.md/QEMU/gem5/interp 最终都对 Sail 校验。这堵住验证链里 ①（上游→spec）唯一薄弱环。

**首要动机**：**为真实芯片项目走通全流程**（不只服务 DADAO 当下）——重点在 RTL tandem 与形式化证明的可行性与工具链。

---

## 调研问题（逐条给结论 + 来源）

1. **Sail 工具链**：语言概况；`sail` 编译器安装（opam/OCaml 依赖）；后端——生成 C 模拟器（`sail -c`）、OCaml、**Coq/Isabelle/HOL4/Lem** 定理证明导出。各后端成熟度、依赖、许可证。
2. **sail-riscv = 定位 B 的范例**（重点）：sail-riscv 如何成为 **RISC-V 官方权威形式化 spec**；RISC-V International 的 ratification 流程怎么与它挂钩；它与 prose ISA 手册的主从关系；仓库结构 / 维护模式 / 谁背书。**这是我们定位 B 的直接蓝本，扒细。**
3. **RTL tandem 流程**（首要动机核心）：Sail 生成的模型如何用作 RTL 验证的 golden model / 协同仿真（tandem）——调研 **RVVI / riscv-dv / tandem verification** 等实践；Sail 模型如何和 RTL DUT 对拍（step-and-compare）；真实芯片 DV 流程里 Sail 处于什么位置。
4. **形式化证明流程**：Sail → Coq/Isabelle 实际证过哪些 ISA 级性质（异常完备性、无 UB、编码无歧义、寄存器不变量…）；sail-riscv 或 sail-cheri 的形式化成果举例；投入产出。
5. **DADAO 在 Sail 的表达可行性**：DADAO 特性能否在 Sail 干净建模——**双寄存器组 RD/RB**、**48 位有效地址 + 16 位保留**、**big-endian**、**fault 模型（ILLI/MALIGN/UNDI）+ 精确异常**、**RA 栈（RegRAS）**。有无对应的 Sail 惯用法 / 已知难点（对比 sail-riscv 的寄存器/内存/异常建模）。
6. **定位 B 的治理**：Sail 成为权威源后，`spec.md`（现权威契约）、wiki（散文上游）、三个实现（interp/QEMU/gem5）、opcodes.yaml 的关系如何重排；wiki 团队如何参与背书；迁移路径（spec.md 是渐进被 Sail 取代，还是并存互校）。
7. **垂直切片方案草案 + 工作量**：建议的 ~5 指令切片（算术/load-store/分支/fault 各一）；从写 Sail → `sail -c` 生成 C 模拟器 → 包 `run_sail_test.py`（对标 run_gem5_test）→ run_differential 加第 4 列 → 4 方 AGREE 的最小闭环；工具链前置、预估工作量、主要风险。

---

## 约束
- **纯调研**：不装 Sail 到系统、不写 Sail 代码、不改仓库源码（除产出报告 md）。
- 引用来源（Sail 官方 repo/manual、sail-riscv、相关论文/RVVI 文档），结论标出处。
- 对比锚点：处处以 **sail-riscv** 为参照系（它是定位 B 的成品）。

---

## 交付
产出调研报告 **`docs/reviews/sail-recon-2026-07.md`**（或 code-agent/knowledge/ 下），含：
- 逐条 7 个问题的结论 + 来源
- **对 DADAO 的建议**：定位 B 可行性、迁移路径、垂直切片方案、工作量/风险
- 一页"决策所需信息"摘要，供架构师写 M2b charter

（纯调研、无代码改动，可跳过 Codex review，架构师直接读报告。）

---

## 参考指针
- ADR-0009 §M2b / §独立性 / ①上游→spec 与 ②spec→实现 的区分（本仓 docs/adr/0009）
- 知识图谱 `~/knowledge-graph/isa-design/04-multi-implementation-differential.md`（①/② 框架）、`fpga-soc-bringup/*`（RTL 线索）
- 外部：Sail 官方（github.com/rems-project/sail）、sail-riscv（github.com/riscv/sail-riscv）、RVVI、相关形式化论文
- DADAO 特性锚点：`contracts/isa/spec.md`（§1.3 RB 48位、§2.1 big-endian、§2.5-2.6 fault、§5.6 RAS）

---

## 完成区

**状态**：已完成
**修改文件**：
- `docs/reviews/sail-recon-2026-07.md`（新增，调研报告）
- `code-agent/tasks/SL-001a-sail-recon.md`（状态更新）
**验收结果**：
- 7 个调研问题全部覆盖，逐条结论 + 来源
- sail-riscv 全程作为对比锚点
- DADAO 5 个特性逐项评估可行（双寄存器组 RD/RB、48 位 EA、big-endian、精确异常、RAS）
- 治理迁移路径 4 阶段，垂直切片方案 ~20-30 条指令，工作量 ~3-4 周
- 一页决策摘要 + M2b charter 要点已给出
- 约束合规：纯调研，未安装 Sail、未写 Sail 代码、未改仓库源码
- Codex review: PASS（2 minor notes：riscv-dv 未明确覆盖、sail-cheri 仅间接引用；均非阻塞）
**遗留问题**：
- riscv-dv 与 TestRIG 的互补性未讨论（minor，不影响 M2b charter）
- sail-cheri 仓库未直接引用为形式化成果例证（minor，Morello 填补了同等证据）
- 部分引用粒度较粗（如 "Sail manual 相关章节"），如需精确校验可后续 tighten
