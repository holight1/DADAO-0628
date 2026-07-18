# IN-002a: wiki pin 与 contracts 一致性审计

**执行环境**：本地 subagent（纯审计/调研，禁止修改规范与 pin）

**状态**：已完成

## 目标

解释并核实当前 `make check` 的 wiki drift：

- `manifests/spec.lock.toml` 锁定的 wiki commit；
- `contracts/isa/spec.md` 与 `contracts/abi/spec.md` 文件头记录的来源 commit；
- `~/DADAO-wiki` 当前 checkout 与历史升级记录；
- `docs/reviews/wiki-upgrade-9f378f4.md`、ADR-0013 及相关 issue。

产出一份短报告 `docs/reviews/spec-pin-consistency-2026-07-18.md`，明确：

1. 哪个 commit 是当前合同真正的来源；
2. 当前漂移是合同未更新、lock 错误、还是 wiki upgrade 记录不完整；
3. 若选择保留 `9f378f4`，需要更新哪些文件、如何证明 A 桶不回归；
4. 若选择回退/保留 `13a414d`，需要哪些相反操作；
5. 推荐方案及其风险。

## 硬约束

- 不修改 `contracts/`、`manifests/`、`docs/issues.yaml`、ADR 或任何组件源码。
- 不修改 `~/DADAO-wiki`。
- 不把实现代码或旧项目结论当作 pin 证据。
- 必须使用真实命令输出；不能只根据现有文档叙述下结论。
- 完成后必须填写完成区，并在任务 md 追加 `## 审阅记录（subagent）`，由独立 reviewer 复核证据链。

## 验收

- 报告包含 commit、文件和命令级证据。
- 明确区分“合同来源 commit”和“当前 wiki checkout”。
- `git diff -- contracts manifests docs/issues.yaml` 为空（本任务自身不应改这些文件）。
- `make check` 的失败原因只做诊断，不得为了变绿修改门禁或合同。

## 参考

- `CODEX.md`、`DS.md`、`reviewer.md`
- `manifests/spec.lock.toml`
- `contracts/isa/spec.md`
- `contracts/abi/spec.md`
- `docs/adr/0013-wiki-upgrade-process.md`
- `docs/reviews/wiki-upgrade-9f378f4.md`
- `~/DADAO-wiki`

> 本次按架构约束不查阅、不引用 `~/toolchain` 或 `~/knowledge-graph`；证据仅来自当前仓库、当前任务明确文件和 `/home/holight/DADAO-wiki`。

## 完成区

**状态**：已完成

**修改文件**：`docs/reviews/spec-pin-consistency-2026-07-18.md`；本任务 md 仅补充执行记录、完成区和 review 记录。

**验收结果**：报告已给出 lock、合同头、wiki checkout、8 个升级 commit、A 桶零 diff、`make check` 漂移和四方差分的真实命令证据。`check_wiki_drift.py` 退出 1、`make check` 退出 2，均为预期诊断结果；四方差分退出 0，`AGREE(4-way)=200 / DIVERGE=0`。受保护范围未新增任务改动。

**遗留问题**：需要架构师决定保留 `9f378f4` 并完成三方同步，或先回退/保留 `13a414d`；本任务不擅自修改规范、pin 或 wiki。

## 审阅记录（subagent）

### 审阅记录（subagent · 判决 = 通过）

- 独立 reviewer 已重新读取 `reviewer.md`、任务验收与本任务 diff；本任务只新增审计报告、任务执行记录和 review 记录，未改 `contracts/`、`manifests/`、`docs/issues.yaml`、ADR、组件源码或 `/home/holight/DADAO-wiki`。
- 证据链核验：lock=`9f378f4`、两个合同头=`13a414d`、wiki HEAD=`13a414d`、`13a414d` 是 `9f378f4` 的祖先 ✓；`13a414d..9f378f4` 的 SimRISC-01/02/03 diff 为空 ✓；8 个 commit 的域/桶分类与逐提交 stat 证据已写入报告 ✓。
- 验收命令核验：`scripts/check_wiki_drift.py` 真实退出 1，原因正是两份合同 provenance 与 lock 不同 ✓；`make check` 真实退出 2 且停在同一 drift gate ✓；`tools/run_differential.py` 真实退出 0，AGREE(4-way)=200、DIVERGE=0 ✓。
- 未测边界推敲：分别检查了“合同真实来源 vs 当前 checkout”“lock 指向后继但 checkout 未跟随”“历史升级报告与 WU-001a 状态冲突”三种状态；结论均记录为 reconciliation/pin 选择问题，不把差分结果误当作 upstream→spec 证明。
- finding：无。当前 drift 是任务目标要诊断的事实，不是本任务应擅自修复的 finding；推荐方案 A/B 已分别列出文件、操作、验证门槛和风险。

## Codex Review

### 重跑记录

独立 review 复跑了 `python3 scripts/check_wiki_drift.py`、`make check`、`python3 tools/run_differential.py`，并核对 `git diff --name-only -- contracts manifests docs/issues.yaml`；输出与上方验收结果一致：drift 退出 1、make 退出 2、四方差分 `AGREE(4-way)=200 / DIVERGE=0`，受保护范围只有既有 `docs/issues.yaml`。

### 约束核验

- 只写任务要求的审计报告和任务 md：通过。
- 没有修改 contracts、manifests、issues、ADR、组件源码或 wiki：通过。
- 报告同时区分合同来源 commit（13a414d）与当前 wiki checkout（13a414d）：通过。
- 报告提供 lock、合同头、wiki ancestry、8 commit delta、drift 和差分命令级证据：通过。
- 未自行选择或修改 pin；仅给出证据和建议：通过。

### 判决

Accepted：验收证据完整，约束无违反；pin 选择被明确留给架构师。

## 架构师复核（ground-truth，2026-07-18）

**判决：Accepted**

独立复核结果：

- `python3 scripts/check_wiki_drift.py` → 两个合同 provenance mismatch，退出码 `1`。
- `make check` → manifest、encoding、vector 前置检查通过，停在同一 wiki drift gate，退出码 `2`。
- 独立核对 `/home/holight/DADAO-wiki`：HEAD=`13a414da158dc780ae5501c1443acbffd15cbf4a`，工作树无输出；`13a414d` 是 `9f378f4` 的祖先。
- 独立列出 `13a414d..9f378f4` 的变更文件，只有 SEE/SBI/HBI、MISC-RF 和 SimRISC-04 文件；没有 `SimRISC-01/02/03`，A 桶为空。
- 当前受保护范围 diff 仍只有任务开始前已有的 `docs/issues.yaml`；本任务没有修改 contracts、manifests、ADR、组件源码或 wiki。

报告正确区分了“当前合同真实 provenance”“lock 单独推进”“上游 delta 已审计但未完成落地”三件事，并且没有擅自选择或修正 pin。推荐先恢复一致基线属于架构师决策建议，不是 worker 越权修改，因此接受。
