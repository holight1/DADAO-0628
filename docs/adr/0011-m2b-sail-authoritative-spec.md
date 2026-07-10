# ADR-0011: M2b Sail — 权威可执行 spec（定位 B · 真实芯片流程 · 时间盒彩排）

**状态**：Accepted（2026-07-10）
**日期**：2026-07-10
**关联**：ADR-0009（验证链·§M2b）、ADR-0010（gem5 功能第二参考）、调研报告 `docs/reviews/sail-recon-2026-07.md`（SL-001a）

---

## 背景

验证链有两个正交一致性（见 `knowledge-graph/isa-design/04`）：**② spec→实现**（差分强覆盖，interp/QEMU/gem5 三方已在 198 向量全 AGREE、打满）、**① 上游→spec**（差分完全盲——spec.md 误读 wiki 时三个实现一致继承）。① 是链子唯一薄弱环。

Sail（Cambridge REMS）是 ISA 形式化规格语言，可从单一形式化生成 C 模拟器、定理证明定义、RTL tandem 参考模型、文档。**sail-riscv 是 RISC-V International 官方 golden model**——定位 B（Sail 作权威可执行 spec）的直接蓝本。

**为何现在**：ISA 已三方验证稳定（198/198）、204 向量 + run_differential 框架就绪 → 形式化成本最低、Sail 落地即可插第 4 列验证。**首要动机不止服务 DADAO 当下，而是为后续真实芯片项目走通「权威 spec → 模拟器/形式化/RTL tandem」全流程。**

---

## 决策

### D1 — 定位 B：Sail 作权威源；权威性来自 wiki 背书，**不是**来自形式化

Sail 不是第 4 个从 spec.md 派生的模拟器，而是新的权威源，② 差分 target 最终从 spec.md 迁到 Sail。

**关键澄清（调研报告未锐化处）**：Sail 若从 wiki 人工翻译而来，它**继承与 spec.md 相同的 wiki→Sail 翻译风险**。形式化只让 Sail **内部精确、可执行、可判定**，不自动保证翻译忠于 wiki。**定位 B 里 Sail 的权威性 = wiki 团队对 wiki→Sail 的背书**。故：切片可先并存推进（不等背书），但「Sail 成为权威源」这步**以 wiki 团队背书为显式前置门**。

### D2 — 目标=真实芯片流程；RTL tandem 是**后续阶段**，不在彩排切片

调研报告把两个目标搅在一起，本 ADR 拆开：
- **即时（彩排切片）**：Sail 加入**现有 4 方向量差分**——`run_sail_test.py`（对标 run_gem5_test）跑同一批 204 向量，`run_differential` 加第 4 列，目标 4 方 AGREE。复用现成基建、最快见效。
- **后续（真实芯片流程核心）**：RTL tandem via **RVFI-DII/TestRIG**（Sail 作 RTL 对拍 golden model，step-and-compare）+ 形式化证明导出（Coq/Isabelle/Lean）。这是本 ADR 首要动机的落点，但**是切片跑通后的独立阶段**。

**不采纳**报告"切片直接用 RVFI-DII 绕开 ELF"的建议——那是过早优化，会让 Sail 列脱离现有向量差分框架另起炉灶。

### D3 — 彩排切片 ~6-8 条指令，命中 DADAO 特有风险（不是半个 ISA）

调研报告提 20-30 条 / 3-4 周——那是实现阶段的量。去风险只需证三件事：**工具链能装能跑、DADAO 难点能在 Sail 干净表达、4 方差分能集成**。故切片只挑踩中 DADAO 特有风险面的指令（见下 §切片范围），跑通再决定扩全 87。

### D4 — 独立性

Sail 语义从 **spec.md §/wiki + opcodes.yaml** 派生，**绝不抄 QEMU/gem5**（差分独立性；否则第 4 列退化成自证）。Sail 作者独立于 QEMU/gem5 作者。

### D5 — 分阶段

1. **彩排切片**（本 charter）：~6-8 指令 → Sail → C 模拟器 → run_sail_test.py → 4 方向量差分 AGREE。
2. **全 87 Sail**：扩全量；encoding vector / legality 矩阵改从 Sail `mapping clause encdec` 派生（渐进取代 opcodes.yaml 的生成角色）。
3. **权威化**（前置门=wiki 背书）：Sail 正式成权威源；spec.md 退为 human-readable 注释 + 决策记录（并存双轨，不删——承载 prose 解释/ADR 决策/历史 open issue）。
4. **真实芯片流程**：RTL tandem（RVFI-DII/TestRIG）+ 形式化证明导出。

### D6 — 止损与移交

- **止损**（提前终止彩排）：工具链无法安装；或 2 周无实质进展；或 DADAO 某特性证明 Sail 无法干净表达。
- **移交**（成功产出）：Sail 切片模型 + C 模拟器 + `run_sail_test.py` + 4 方差分报告 + Sail 学习笔记（入 knowledge-graph）。

---

## 彩排切片范围（~6-8 指令 + fault 探针）

覆盖 DADAO 特有风险面，每条对应一个"Sail 能不能干净表达 DADAO 这个点"：

| 指令 | 命中的 DADAO 风险 | spec |
|------|------------------|------|
| **add**（orrr 双目标）| RD 双寄存器目标 + **128 位中间值**在 Sail 显式表达 | §3.5 |
| **addi**（rrii）| 基线 RD + 立即数 + rd0 恒 0 | §3.6 |
| **ldo**（rrii）| **RB bank** EA=rbhb[47:0]+imm（**48 位有效地址**）+ **big-endian** 读 + **MALIGN** 对齐异常 | §3.1/§2.1 |
| **sto**（rrii）| big-endian 写 + store-from-rd0→**ILLI** | §3.2/§2.6 |
| **brz**（riii）| 条件分支 + **PC 相对**（PC+sext<<2）| §5.1 |
| **call/ret**（iiii/riii）| **RA 栈（RegRAS）** push/pop + RASOF/RASUF | §5.4-§5.6 |
| **fault 探针** | 保留编码→**UNDI**（≠ILLI，精确异常无副作用）| §2.5/§2.7 |

覆盖：双寄存器组、128 位中间值、48 位 EA、big-endian、MALIGN/ILLI/UNDI、精确异常、RAS、PC 相对分支。这就是 DADAO 相对 sail-riscv 的全部新风险点。

## 最小闭环（复用现有基建）

```
spec.md §/wiki  →(人工，标 §)→  Sail (.sail + .sail_project)
   →  sail -c  →  C 模拟器 (dadao_sail_sim, big-endian ELF/flat 载入 + 寄存器/内存 dump)
   →  run_sail_test.py (对标 run_gem5_test：同 204 向量，取终态比对)
   →  run_differential 第 4 列  →  4 方 AGREE (interp/QEMU/gem5/Sail)  →  分叉=真 bug
```

## 工具链（一次性）
`opam`（OCaml ≥5.2）+ `libgmp-dev z3 pkg-config` → `opam install sail` → `sail --help` 验证。C 后端需 GMP/zlib。

## 验收（切片彩排通过条件）
- Sail 切片模型 `sail -c` 生成的 C 模拟器可跑 ~6-8 指令覆盖的向量。
- `run_sail_test.py` + `run_differential` 第 4 列：切片指令覆盖处 **4 方 AGREE、DIVERGE=0**（分叉如实报——可能 Sail bug / 已知 QEMU 洞 / 向量疑点，走三查）。
- DADAO 5 风险特性在 Sail 中均干净表达（否则触发 D6 止损或记为难点）。
- Sail 学习笔记 + 4 方差分报告移交。

---

## 开放依赖 / 风险
- **wiki 团队背书**（D1/阶段 3 前置门）：外部依赖、节奏不可控——彩排/全 87 可先并存推进，权威化才卡此门。
- big-endian ELF/flat 载入：Sail C harness 需自写 loader（DADAO 无现成），或复用 gem5 侧 `gen_min_elf` 的单段 ELF 范式（已 big-endian 就绪）。
- Sail 学习曲线（OCaml 生态 + 轻量依赖类型）——切片首要就是趟这个。

---

## 后续
1. **SL-002a 切片实现任务**（下发）：装 Sail + ~6-8 指令 Sail 模型 + C 模拟器 + run_sail_test.py + 4 方差分。
2. 切片通过 → 决策扩全 87（阶段 2）。
3. RTL tandem（RVFI-DII/TestRIG）+ 形式化证明作真实芯片流程的后续 ADR。

> 本 ADR 为 M2b charter 基线；切片彩排通过前不承诺全 87 / 权威化 / RTL tandem。
