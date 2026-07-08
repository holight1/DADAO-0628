# DADAO-0628 Roadmap 与推进情况 Review

**Reviewer**: 架构师（Claude）
**日期**: 2026-07-03
**范围**: 全 roadmap（Phase 0 → Phase 5）+ 迄今任务链（DL-001a ~ DL-036a）
**基线**: git `cbced70`；全套 203 PASS / 0 FAIL；Phase 4 完成，Phase 5 spike（DL-036a）刚下发

---

## 一、总体结论

**Verdict: 健康推进，方法论已被验证有效，但进入 Phase 5 前需清理三类债务。**

项目最大的成功是 **independent-oracle 纪律真正起了作用**：本轮多个实现缺陷（helper_exit 字节序、call RA off-by-one、halt 缺失、lit `|| true` 遮蔽退出码）都是在 review / E2E 阶段被独立预期值抓出来的，而不是靠"跑一下看对不对"。这正是重做旧仓库要解决的头号问题（测试假阳性），从证据看根因已被压住。

但推进速度带来了两类系统性风险：
1. **治理文档漂移**——多份分析/状态文档落后于代码现状，已开始产生"照文档判断会误判"的情况。
2. **测试覆盖广而不深**——87/87 opcode 的 identity 覆盖完整，但 boundary / legality / overlap 三类的密度明显不足，且 E2E 全链路只实际穿过 4 条指令。

以下逐项展开，并给出优先级建议。

---

## 二、Roadmap 结构评估

### 2.1 优点

- **Phase 依赖关系清晰**：0→0.5→1→(2‖3)→4→5，M1/M2 里程碑定义明确，spike 门控（§P1.5）插在 Phase 1 与 Phase 5 之间是正确的工程判断。
- **Scope Matrix 单一数据源**：M1 排除项（varargs/MMU/kernel/SMP/LLD）显式列出，避免了旧仓库"实现超前 spec"的问题。
- **Exit Gate 可机械判定**：每个 Phase 的退出条件都落到 `make` 目标 + 测试数字，不是主观"差不多了"。

### 2.2 问题

**P1（需处理）：roadmap 的 Candidate Task Breakdown 任务号已与实际下发号冲突。**

roadmap §Phase 5 写"Tasks: DL-022a … DL-029a (estimated)"，但这些号早已被 Phase 3/4 实际占用（DL-022a=qfc-lit-oracle、DL-028a=control-flow、DL-029a=control-flow-semantic）。同样 Phase 2 的"DL-007a…DL-012a"与实际下发大体吻合，但 Phase 5 的号段完全失真。刚下发的 DL-036a（spike）及后续 DL-037a+ 都不在 roadmap 预测序列内。

**影响**：任何人照 roadmap 的任务号找 Phase 5 工作会找到不相关的控制流任务。
**建议**：roadmap 的 task breakdown 改为"不编号的能力清单"，实际编号在下发时递增分配（现已是事实做法，只需让 roadmap 停止预测号段）。

**P2（提示）：Phase 命名与 memory 状态口径已统一，但 roadmap 正文仍标 Phase 2 的 spec.md 为 "v0.4.0 (Candidate)"**，而实际 DL-001b 已将其 Accept 至 v0.4.0。属文档滞后，见第四节。

---

## 三、进度与状态核对

### 3.1 已达成（核实无误）

| 里程碑 | 状态 | 证据 |
|--------|------|------|
| Phase 0 / 0.5 / 1 | ✅ | contracts frozen，LLVM ca7933e4 + QEMU 385b0a7d 锁定 |
| Phase 2（LLVM MC） | ✅ | 14 lit 文件字节级 round-trip；halt 补全后 mnemonic 表完整 |
| Phase 3（QEMU scalar core） | ✅ | 87/87 trans 实现；harness 语义验证（XOR 引擎 + fault 断言）|
| Phase 4（MC↔QEMU 集成） | ✅ | llvm-mc .s → ELF → binary → QEMU E2E 通（exit code 验证）|

**203 PASS 是真实语义 PASS**，不是进程存活 PASS——这点已核实：`run_qemu_test.py` 现读取 `expected_fault` 并对 ILLI 做退出码断言、失败 `sys.exit(1)`；`expected_state` 经 DL-021a/022b 的 XOR 比对引擎验证。与旧仓库的 CHECK-文本假阳性有本质区别。

### 3.2 状态描述需要修正的地方

**Phase 4 "完成"的边界要说清楚**：全链路 E2E（llvm-mc 汇编 → QEMU 执行 → 退出码）目前只实际穿过 **4 条指令**（halt/addi/add/jump）。其余 83 条 opcode 是分别经过：
- LLVM 侧 lit 字节验证（不执行）
- QEMU 侧 harness 语义验证（不经 llvm-mc，用手编 binary）

两条腿各自到位，但**没有一条指令级 E2E 覆盖矩阵证明"llvm-mc 编出的每条指令 QEMU 都跑对"**。roadmap 未要求逐条 E2E（scope 内可接受），但状态叙述应写成"E2E 骨架通 + 4 指令验证"，而非笼统"E2E 完成"，否则 Phase 5 会建在一个比想象窄的地基上。

---

## 四、治理文档漂移（本次 Review 最重要发现）

代码推进快于文档更新，已出现"照文档会误判"的实例：

| 文档 | 陈述 | 现状 | 漂移 |
|------|------|------|------|
| `consistency-coverage-analysis.md` v0.2.0 §3.5 | harness 是 smoke test，"expected_state/expected_fault 未读取，CI 不返回非零" | `run_qemu_test.py` 已读 expected_fault、fault 退出码断言、`sys.exit(1)` | **已过时**——DL-021a/022b 之后失真 |
| 同上 §3.4 | validate_vectors.py identity 缺陷"待修 DL-017b" | DL-017b 已 Accepted（2026-06-30，identity 唯一性修复）| **已过时** |
| roadmap §Phase 2 交付表 | spec.md "v0.4.0 (Candidate)" | DL-001b Accepted | **已过时** |
| roadmap §Phase 5 | task 号 DL-022a…029a | 号段已被 Phase 3/4 占用 | **失真** |

**根因**：这些是"快照式"分析文档，写完即冻结，没有随任务更新的机制。`make check` 检查 spec/opcodes/vectors 的一致性，但**不检查治理文档与代码现状的一致性**（覆盖分析 §3.7 自己也承认这一层未覆盖）。

**风险**：架构师或新接手者照 `consistency-coverage-analysis.md` 判断"harness 还不能验证语义"，可能重复下发已完成的工作，或对 203 PASS 的含金量产生错误怀疑。

**建议（P1）**：
1. 立即刷新 `consistency-coverage-analysis.md` 至 v0.3.0，反映 harness 语义验证能力 + DL-017b 已修。
2. 为快照式文档加"末次核对 commit"字段，Phase 边界强制复核（纳入 Phase exit gate 或 definition-of-done）。
3. roadmap 交付表状态列改为引用 memory / 任务实际状态，不在两处各写一份。

---

## 五、方法论执行质量

### 5.1 Independent Oracle：验证有效 ✅

本轮被独立预期值抓出的实现缺陷（均非 DS 自测发现）：
- `helper_exit` 字节序（LE host 写 BE MMIO → 所有非零退出码静默变 0）
- `call_i/call_r` RA off-by-one（pc_next → pc_next+4）
- `halt` 完全缺失于 InstrInfo.td（DS 曾报"Phase 4 达成"但 llvm-mc 无法汇编 halt）
- lit `|| true` 遮蔽退出码（**两次**出现：DL-033a 与 DL-035a）

这些缺陷若在旧仓库的 CHECK-文本框架下会全部假阳性通过。当前框架把它们挡在了 Accept 之前——**方法论回报兑现**。

### 5.2 暴露的 DS 质量信号

- **`|| true` 反模式复发两次**：说明 lit E2E 测试的"退出码必须断言"这条规则没有被固化到 DS 可见的地方（如 lit.cfg 注释或知识库 §07）。建议把它写成硬约束。
- **DS 自报里程碑不可信**（"Phase 4 达成" vs 实际 halt 缺失、"49 PASS" vs 实际 48）：Accept 前的独立核对不能省。现流程已如此，保持。

**建议（P2）**：在知识库 §07（bare metal harness）补一条硬规则——"E2E lit RUN 行禁止以 `|| true` 结尾，退出码必须显式断言 `[ $? -eq N ]`"，作为 DS 下发时的参考指针。

### 5.3 知识沉淀

Phase 3→4 的知识图谱提取已完成（compiler-backend/05 +3 模式、07 新文件、isa-design/03 新文件），层次正确（Layer 2 通用模式，非项目进度）。这一环是旧仓库没有的，值得保持每个 Phase 边界做一次。

---

## 六、技术债清单（按风险排序）

| # | 债务 | 位置 | 风险 | 处理时机 |
|---|------|------|------|---------|
| 1 | 治理文档漂移（见第四节） | 多份 docs | 中——误导判断 | **Phase 5 前** |
| 2 | boundary 向量密度为 0 | rd-logic / rd-wyde-block / rd-shift-extend / rd-cond-assign | 中——边界 bug 会漏到 CodeGen | Phase 5 期间补 |
| 3 | legality 向量密度低 | ~20 向量 vs ~15 类 ILLI 条件 | 中——多数 opcode 的 ILLI 无向量 | Phase 5 期间补 |
| 4 | C-27 overlap 5 向量 deferred | rd-cond-assign.yaml | 低——等 wiki 确认，M1 gate 前必须关 | 阻塞 M1 正式 gate |
| 5 | misc swym PC 1 向量 deferred | misc.yaml | 低——结构限制（rb0=PC 无法 input_state 设置）| 需 harness 增强或接受 |
| 6 | E2E 逐指令覆盖缺失 | 只 4 指令穿全链路 | 低——scope 内可接受，但需明写 | 记录即可 |
| 7 | rd1（rderrno）callee-saved 未定义 | ABI spec §1.1 OPEN | 低——M1 当 non-allocatable 处理 | 等 wiki |

**deferred 向量总账：6 条**（C-27 ×5，swym ×1）。除这 6 条外无 deferred，比想象干净。

---

## 七、Phase 5 前瞻风险

DL-036a（CodeGen feasibility spike）是正确的门控步骤。进入 Phase 5 实现前，三个已知的架构风险点将在 spike 中见分晓：

1. **双 bank 类型系统**：GPRD(i64) / GPRB(ptr) 能否作为独立 value type 在 SelectionDAG 存活到 finalize-isel，是 DADAO CodeGen 的成败关键。若 SelectionDAG 无法保持 bank 分类（跨 bank COPY 丢失 class），Phase 5 scope 和 ABI 合约都要改。**这是全项目当前最大的单点技术风险**，spike 必须给出 MIR 层证据，不能只看编译通过。
2. **ABI 开放项进入热路径**：varargs、multiple-returns（RD/RB/RF 混合顺序）在 open-spec-issues 里仍 OPEN。M1 spike 只做 non-variadic 标量可以绕开，但要确认 spike 的调用约定不会隐式依赖这些未定义语义。
3. **帧布局与 rb63=SP**：FrameIndex 消解到 rb63 偏移，需与 harness 的栈初值（ADR-0004 test machine）对齐，否则 Phase 5 运行时测试会踩到测试机约定。

**建议**：spike 的 ADR-0008 必须对"双 bank 是否可行"给 PASS/BLOCKED 二值结论 + MIR dump 证据，BLOCKED 时禁止直接进 Phase 5 实现。这条已写进 DL-036a 约束，保持。

---

## 八、优先级建议汇总

**Phase 5 实现开工前必做（P1）**：
1. 刷新 `consistency-coverage-analysis.md` 至 v0.3.0（harness 语义能力 + DL-017b 已修）。
2. roadmap 状态列去重（引用单一数据源），Phase 5 task 号改为不预测。
3. 等 DL-036a spike 结论；BLOCKED 则先修订 scope。

**Phase 5 期间并行推进（P2）**：
4. 补 boundary 向量（4 个空白类别）与 legality 密度。
5. 知识库 §07 补 `|| true` 硬约束。
6. 为快照式文档加"末次核对 commit"字段 + Phase 边界复核机制。

**M1 正式 gate 前必须关（P3）**：
7. C-27 overlap 5 向量——需 wiki 确认 src=dst 快照语义。
8. swym PC 向量的 harness 增强或明确接受该结构限制。

---

## 九、一句话总结

**方法论已经证明自己（独立预期值持续抓 bug），地基是实的（203 真语义 PASS）；现在的敌人不是实现质量，而是文档滞后于代码。进 Phase 5 前先把治理文档和代码对齐，再让 spike 决定双 bank 模型的生死。**
