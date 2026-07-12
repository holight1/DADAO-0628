# ADR-0013: Wiki 升级流程（① 事件的一致性再验证）

**状态**：Accepted（2026-07-12）
**日期**：2026-07-12
**关联**：ADR-0009（验证链·①/② 正交一致性）、ADR-0007（独立预期值/向量分层）、ADR-0011（Sail 作 ① oracle 候选）；先例 DL-039a/b/c（wiki-ref audit）

---

## 背景

wiki（`github.com/gxt/DADAO.wiki`，只读跟踪）是我们 spec.md 的上游。spec.md 是 wiki 的 M1 归一化投影，`manifests/spec.lock.toml` pin 一个 wiki commit 作合约基线。wiki 会持续演进（本 ADR 时点：本地 pin `13a414d` vs 远端 `9f378f4`，8 commits ahead）。

**核心认知**：验证链有两个正交一致性（ADR-0009）——**② spec→impl**（四方差分强覆盖）、**① upstream→spec**（差分盲）。**一次 wiki 升级恰是一次 ① 事件**（上游变了，问 spec 跟不跟得上）。差分对"① 正确性"盲，但它是**"这次改动有没有动到任何已测语义"的灵敏回归探测器**——本流程建于此。

## 决策：五阶段升级流程

### Phase 0 — 探测 delta
`git fetch` wiki；`git log/diff <pinned>..<new>` = 变更集。

### Phase 1 — 分类（域 × M1相关性，diff-audit，仿 DL-039）
逐 commit/hunk 归入域（SimRISC-01 RD标量 / SimRISC-02 RB地址 / FP-RF / 异常 / SEE / SBI / MMU / AEE）+ 标 M1相关性。产出分类表。

### Phase 2 — 三桶 triage
- **A · M1核心语义变更**（碰 SimRISC-01/02 或已验证 legality/encoding）→ 走 Phase 3 再验证环。
- **B · deferred域变更**（FP/异常/MMU/SEE/SBI 未实现）→ 记入该域未来基线，当下不动。
- **C · 装饰**（重命名/示例修正/typo/格式）→ 记录，可选同步 spec.md 措辞，无需验证。

### Phase 3 — A 桶再验证环（复用全套机器，独立性铁律不破）
每个 M1 核心语义变更：
1. **更新 spec.md** 按新 wiki + 新 commit §引用。
2. **先更新独立黄金模型 `tools/dadao_interp.py`** 到新语义（黄金模型领跑，勿默认 QEMU 权威——feedback_golden_model_oracle_trap）。
3. **重 derive 向量期望值**（ADR-0007 独立预期值：期望来自新 spec，非重跑实现取）。
4. **重跑 `tools/run_differential.py`**：真语义变更 → QEMU/gem5/Sail 与更新后 interp/向量 DIVERGE（= 它们该更新的信号）；**各实现独立按新 spec 更新（互不抄）**；重跑到新向量四方重新 AGREE。
5. 新向量四方 AGREE = 该变更被吸收（spec 跟上 ① + 4 实现忠实实现 ②）。

### Phase 4 — ① 残差（工具关不掉，必须补）
- **未测角落**：变更落在无向量覆盖的语义 → **强制补一条向量**（变更暴露覆盖洞）。
- **① 本身**（我们读 wiki 对不对）：无工具闭合 → **架构师逐条读 wiki delta 对 spec.md**（不可约人工环）。Sail（ADR-0011 定位 B）是长期机械 ① oracle 候选，但仍 spec-derived、不单独闭 ①。

### Phase 5 — 重锁 & 记录
- **推进 pin 的条件**：A 桶全部走完再验证环（四方仍 AGREE）+ B/C 桶记录在案。
- 更新 `spec.lock.toml` 到新 commit；升级审计记录进 `docs/reviews/wiki-upgrade-<hash>.md`；更新 `docs/issues.yaml`（可能 resolve C-编号开放问题或新增）。

## Pin 策略
**单 wiki pin 作合约基线**（简单、可复现），**triage 按域相关性**。A 桶空（M1 核心零变更）时，差分重跑确认无回归即可推进 pin（近零成本）；B 桶变更记入各域未来基线（该域启动时才吸收）。**不搞每域多 pin。**

## 工具化
- 半自动 diff-classify 脚本（吐 `git log/diff` + 分类表模板，域/桶人工填）。
- `run_differential.py` = 现成"动没动已测语义"回归探测器，A 桶更新后重跑即验收。

## 后果

**正面**：wiki 升级从"凭感觉"变成机械流程；差分复用为回归网；① 残差显式交架构师人工 + Sail 未来兜底；pin 推进有明确门槛。

**负面 / 限制**：Phase 4 的 ① 人工读不可约（工具关不掉）；A 桶再验证环需 4 实现各自独立更新，成本随语义变更大小走；B 桶延迟吸收意味着 deferred 域启动时要补一次历史 delta 吸收。

## 参考
- ADR-0009（①/②）、ADR-0007（独立预期值）、ADR-0011（Sail ① oracle）；DL-039a/b/c（wiki-ref audit 先例）；`feedback_golden_model_oracle_trap`（黄金模型不默认 QEMU 权威）
- 首次执行：WU-001a（13a414d→9f378f4，8 commits）
