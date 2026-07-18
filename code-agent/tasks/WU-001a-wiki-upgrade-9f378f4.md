# WU-001a: Wiki 升级审计（首次执行 ADR-0013）— 13a414d → 9f378f4

**执行环境**: subagent · DADAO-0628（wiki 只读 + 差分回归 + spec.lock/审计文档）

**状态**: 已完成（IN-003a reconciliation，2026-07-18）

**前置**: ADR-0013（wiki 升级流程）；ML-001a（recon 发现远端 8 commits ahead）。首次按 ADR-0013 五阶段走一遍。

---

## 背景 / 目标
本地 wiki pin `13a414d`（SimRISC 0.4.1，`manifests/spec.lock.toml`），远端 `origin/master = 9f378f4`（8 commits ahead）。**按 ADR-0013 执行升级流程**：分类 delta → 三桶 triage → A 桶（若有）再验证 → 差分回归确认 → 推进 pin + 审计记录。

架构师初查（需你复核确认）：SimRISC-01/02（M1 核心标量/地址指令）**疑零变更**，8 commits 多落 FP(排除)/异常(排除)/SEE-SBI-HBI(deferred)/重命名/示例修正——**A 桶疑为空**。你的任务是**系统坐实**并执行。

## 做什么（ADR-0013 Phase 0-5）

### Phase 1 — 分类（域 × M1相关性）
`~/DADAO-wiki`（只读）：
```
git log --oneline 13a414d..9f378f4          # 8 commits
git diff --stat 13a414d..9f378f4            # 改了哪些文件
```
逐 commit 归域（SimRISC-01 RD标量 / SimRISC-02 RB地址 / SimRISC-00 概览 / SimRISC-04 系统类 / FP-RF / 异常 / SEE / SBI / HBI / MMU / AEE）+ 标 M1相关性。产出**分类表**。

### Phase 2 — 三桶 triage
每 commit/关键 hunk 归：
- **A M1核心语义变更**：碰 SimRISC-01(RD load/store/算术/移位/比较/条件/wyde) 或 SimRISC-02(RB) 的**语义/编码/legality**（我们 200 向量 + CodeGen 验证过的）。
- **B deferred域**：FP-RF / 异常 / MMU / SEE / SBI / HBI（未实现）。
- **C 装饰**：重命名(如 phymem→pmem) / 示例修正(如 `add rd3,..`→`add rd0,rd3,..` 补 4 操作数) / typo / 格式后缀(-orrr/-orri)。

**重点坐实 A 桶**：
- `git diff 13a414d..9f378f4 -- "*SimRISC-01*" "*SimRISC-02*"` —— 有无实质语义 diff？（预期无，但要**贴命令输出证实**，别口头说无）
- 逐一检查 8 commit 里任何提及 M1 指令名（add/sub/mul/div/shift/cmp/cs*/ld*/st*/wyde/call/jump/br*/rela/rd2rb 等）的 hunk：是**语义变更**还是**示例/文档修正**？如 `b1a5f7f` 的 "add补rd0" 是示例补全 4 操作数（印证我们 CodeGen 一直生成的 `add rd0,...`），非语义变更——**逐个判定并给证据**。

### Phase 3 — A 桶再验证环（若 A 桶非空）
若坐实出**真 M1 核心语义变更**：**不要自己改 spec/impl**——如实报告"发现 A 桶变更 X（wiki §Y）",交架构师定夺（可能拆实现任务走 ADR-0013 Phase 3 完整环）。本任务范围内**只分类+回归确认**，A 桶实现变更不在此任务做。

### Phase 4 — 覆盖 & 回归探测
- **差分回归确认**（核心）：
  ```
  cd ~/DADAO-0628 && python3 tools/run_differential.py 2>&1 | tail -3
  ```
  确认 **AGREE(4-way)=200 / DIVERGE=0 / HARNESS=6** 不变（当前基线，升级不应动它——因 M1 impl 未改；这步是"新 wiki 没让已测语义回归"的探测）。
- **覆盖 note**：Phase 1 中若发现某 wiki 变更落在**我们无向量覆盖**的 M1 语义角落 → 记入审计"覆盖洞"清单（架构师后续补向量），本任务不补。

### Phase 5 — 推进 pin + 审计记录
**仅当 A 桶为空（或全部只 B/C）+ 差分不回归**：
1. **更新 `manifests/spec.lock.toml`** wiki commit `13a414d` → `9f378f4`（+版本号若变；**只改 pin，不改 spec.md 语义**——M1 核心未变）。
2. **审计记录** `docs/reviews/wiki-upgrade-9f378f4.md`：8 commits 分类表 + 三桶归属 + A桶结论(空/非空+证据) + 差分回归结果 + B桶变更清单(SEE/异常/FP，记入各域未来基线，标"该域启动时吸收") + C桶清单。
3. **`docs/issues.yaml`**：若某 C-编号开放问题被这批 commit resolve/影响，记一行；SEE 相关变更为 musl 里程碑铺垫，note 一条。
若 **A 桶非空** → **不推 pin、不改 lock**，报告交架构师。

## 约束
- **wiki 只读**（`~/DADAO-wiki` 不改）；本任务**不改 spec.md 语义、不改任何 impl（interp/QEMU/gem5/Sail）**——A 桶为空的前提下只动 spec.lock + 审计文档。
- 分类/判定**贴命令输出为证**（`git diff`/`git show` 片段），不口头断言"无变更"。
- §引用用章节号，不用行号。

## 验收（架构师复核）
- `docs/reviews/wiki-upgrade-9f378f4.md`：8 commits 全分类 + A桶结论带 `git diff SimRISC-01/02` 证据 + 差分 200 不回归 + B/C 清单。
- `spec.lock.toml` pin = 9f378f4（若 A 空）。
- 差分仍 AGREE(4-way)=200/DIVERGE=0（架构师重跑）。
- 未改 spec.md 语义 / 未改 impl（`git diff` 确认）。

## 参考指针
- ADR-0013（五阶段流程 + 三桶判据 + pin 策略）；ML-001a recon（远端差异初判）
- `~/DADAO-wiki`（git log/diff/show，只读）；`manifests/spec.lock.toml`（pin）；`tools/run_differential.py`（回归探测）
- M1 核心 spec：`contracts/isa/spec.md`（对照 wiki SimRISC-01/02 的投影）；`tools/opcodes.yaml`（编码 legality）
- DL-039a/b/c（wiki-ref audit 先例，同类分类方法）

—— 这是**审计+回归确认**任务，A 桶实现变更不在此做（如有交架构师）。**只读 wiki、只动 lock+审计文档、贴证据不口头断言**。返回前自审（读自己的分类表：每 commit 判定有 git 证据吗？A 桶结论有 SimRISC-01/02 diff 证实吗？）。

## 完成记录（IN-003a reconciliation）

- 目标完整 pin `9f378f4426e131903d60a208766086ae74a53c89` 已在 `/home/holight/DADAO-wiki` 安全切换为 detached checkout；切换前工作树干净，未编辑 Wiki 内容、未拉取新内容。
- Phase 5 的 lock pin 已由既有 WU-001a 记录落地；本次仅将 ISA/ABI provenance Source 头与该 pin 对齐，未修改 `manifests/spec.lock.toml` 或 contract 正文语义。
- 完整命令与结果见 `code-agent/tasks/IN-003a-wiki-pin-reconciliation.md` 及 `docs/reviews/wiki-upgrade-9f378f4.md` 的 reconciliation 记录。
