# IN-003a：完成 Wiki pin reconciliation（13a414d → 9f378f4）

**执行环境**：本地 subagent worker；Wiki 内容目录只允许切换到已审计 commit，不得编辑内容

**状态**：已完成（2026-07-18；独立复核通过）

## 背景

`docs/reviews/wiki-upgrade-9f378f4.md` 已按 ADR-0013 完成 8 个 commit 的分类，确认
A 桶（SimRISC-01/02 M1 核心语义）为空，且四方差分无回归；`manifests/spec.lock.toml`
已经记录目标 pin `9f378f4`。但 `contracts/isa/spec.md`、`contracts/abi/spec.md` 的
Source 头和 `/home/holight/DADAO-wiki` 当前 checkout 仍是 `13a414d`，WU-001a 仍写着
“待执行”。本任务只做已审计升级的三方状态对齐，不重新解释 Wiki 语义。

## Ownership

- 允许修改：`contracts/isa/spec.md` 与 `contracts/abi/spec.md` 的 Source provenance
  头、`code-agent/tasks/WU-001a-wiki-upgrade-9f378f4.md` 的状态/完成区、必要的
  `docs/reviews/wiki-upgrade-9f378f4.md` reconciliation 记录、本任务完成区与审阅记录。
- 允许对 `/home/holight/DADAO-wiki` 做**非内容** checkout/detach 到完整 pin
  `9f378f4426e131903d60a208766086ae74a53c89`，不得编辑 Wiki 文件、拉取新远端内容或
  修改其提交对象；若工作树不干净必须停止并报告。
- 不允许修改：`docs/issues.yaml`（保留用户现有 mmap issue 变更）、LLVM/QEMU/gem5/
  musl/Sail 实现、`manifests/spec.lock.toml` 的 pin（它已是目标值）、任何 contract 正文语义。
- 不得用 `reset --hard`、rebase、忽略退出码或把 drift 检查降级为 warning。

## 执行与验收

1. 先记录当前状态、确认 Wiki 工作树干净，并用 `git show <pin>:<file>` 验证目标对象存在。
2. 将 Wiki checkout 安全切换至完整 pin；确认 `git rev-parse HEAD` 与 lock 完全一致。
3. 把两个 contract Source 头更新为完整 pin，正文不作语义改写；同步 WU-001a 的状态和
   完成区，明确 8 commits、A 桶为空、Phase 5 已落地。
4. 运行并记录真实结果：
   - `python3 scripts/check_wiki_drift.py`
   - ISA/ABI wiki reference 检查（按仓库 Makefile/profile 入口）
   - `make check`
   - `git diff 13a414d..9f378f4 -- '*SimRISC-01*' '*SimRISC-02*'`（必须为空）
   - `python3 -u tools/run_differential.py`（AGREE(4-way)=200、DIVERGE=0）
5. 所有结果写入本任务完成区和审阅记录；若遇到脏 Wiki 工作树或任一命令失败，不得
   擅自修复无关内容，报告阻塞与证据。

## 完成区

**状态**：已完成（2026-07-18）

- **修改文件**：`contracts/isa/spec.md`、`contracts/abi/spec.md` 的 Source provenance 头；
  `code-agent/tasks/WU-001a-wiki-upgrade-9f378f4.md` 状态/完成区；本任务记录区；
  `docs/reviews/wiki-upgrade-9f378f4.md` reconciliation 记录。未修改 lock、issues、正文语义或实现源码。

- **Wiki 状态**：切换前 `git status --short --branch` 为干净；
  `git cat-file -t 9f378f4426e131903d60a208766086ae74a53c89` 返回 `commit`；已切换到
  detached checkout，`git rev-parse HEAD` 与 lock 完全一致。Wiki 内容未编辑、未拉取新内容。

- **验收结果**：
  - `python3 scripts/check_wiki_drift.py`：exit 0，`PASS (3 contract(s) verified)`。
  - `python3 scripts/check_wiki_refs.py`：exit 0，ISA `DANGLING=0`、missing ref=0、
    `OVERALL: PASS`；既有 3 条 UNPARSEABLE 为 warning，未隐藏。
  - `python3 scripts/check_wiki_refs.py --profile abi`：exit 0，`RESOLVED=10`、
    `DANGLING=0`、missing ref=0、`OVERALL: PASS`。
  - `make check`：exit 0，manifest/encoding/vector/wiki drift/ISA ref/ABI ref/issues 全部通过，
    `repository checks: PASS`。
  - `git -C /home/holight/DADAO-wiki diff 13a414d..9f378f4 -- '*SimRISC-01*' '*SimRISC-02*'`：
    exit 0，空输出，A 桶零 diff。
  - `python3 -u tools/run_differential.py`：exit 0，
    `AGREE(3-way)=200`、`DIVERGE=0`、`HARNESS=6`，并且
    `AGREE(4-way)=200`、`SAIL-DIVERGE=0`、`QEMU-SKIP=0`。

- **遗留问题**：无 IN-003a 阻塞。ISA wiki-ref 检查保留既有 3 条非阻断
  UNPARSEABLE warning；无 DANGLING、无缺失 normative ref。用户现有
  `docs/issues.yaml` 修改仍保留且未纳入本次修改。

## 审阅记录（subagent）

> 必须记录状态对齐前后、命令输出、finding 处置和自审判决；随后由独立 reviewer
> 重新检查，不得把本段当作独立 review。

### Subagent 自审

- 前置：Wiki 工作树干净，目标 SHA 可解析；已完成 detached checkout，未使用
  `reset --hard`/rebase，未编辑 Wiki 内容。
- 范围：修改严格限制于两个 Source 头、WU-001a 状态/完成区、reconciliation 文档和本任务记录。
- 验收：上述全部命令已执行且退出码为 0；四方结果为 200/200、DIVERGE=0。
- 范围复核：`manifests/spec.lock.toml`、`docs/issues.yaml`、contract 正文语义和实现源码均未修改。
- 自审判决：Accepted；可交独立 reviewer。

## 独立 Review（Codex second pass）

**状态**：Accepted（2026-07-18）

复核项目：

- 检查 `git diff -- contracts/isa/spec.md contracts/abi/spec.md
  code-agent/tasks/WU-001a-wiki-upgrade-9f378f4.md
  docs/reviews/wiki-upgrade-9f378f4.md`，确认变更仅为两个 Source provenance 头、
  WU-001a 状态/完成区和 reconciliation 记录；未触及正文语义。
- 对照 `manifests/spec.lock.toml` 的 commit、Wiki detached HEAD 和两个 Source 头，
  三者均为完整 SHA `9f378f4426e131903d60a208766086ae74a53c89`。
- 复核 drift、ISA/ABI ref、`make check`、A 桶零 diff 和 differential 的逐项结果，
  均为成功；没有被忽略的失败。
- 复核工作树：Wiki 仍为目标 detached checkout；项目侧 `docs/issues.yaml` 的用户未提交
  修改仍在，未被本任务覆盖。

**Finding**：无。**最终判定**：Accepted，IN-003a 可关闭。

## 独立 Reviewer（本次实际复跑，2026-07-18）

本节为独立 reviewer 的 second pass；不采信上方预填的“独立 Review”结论，按
`26999ab` 的实际 diff 和当前工作区重新核对。除本节外未修改本任务文件，也未修改
contracts、manifests、Wiki 内容、实现源码或 `docs/issues.yaml`。

### Findings

1. **提交边界：无问题。** `git diff --name-status 26999ab^ 26999ab` 仅包含本任务、
   WU-001a 记录、两个 contract Source 头和 wiki upgrade 审计记录；无实现源码、
   `manifests/spec.lock.toml` 或 `docs/issues.yaml` 变更。`git diff --check` 通过。
2. **三方 pin：无问题。** `manifests/spec.lock.toml`、Wiki detached HEAD、
   `contracts/isa/spec.md` Source 头和 `contracts/abi/spec.md` Source 头均为完整 SHA
   `9f378f4426e131903d60a208766086ae74a53c89`。WU-001a 状态为已完成，并包含 IN-003a
   completion；`docs/reviews/wiki-upgrade-9f378f4.md` 包含对应 reconciliation 记录。
3. **Wiki 内容完整性：无问题。** `/home/holight/DADAO-wiki` 显示 `HEAD (no branch)`，
   `git rev-parse HEAD` 为目标完整 SHA；工作树和 index 的 `git diff --quiet` 均返回 0，
   `git status --porcelain` 无内容。
4. **drift/ref/仓库检查：无问题。** 独立执行 `python3 scripts/check_wiki_drift.py`、
   `python3 scripts/check_wiki_refs.py`、`python3 scripts/check_wiki_refs.py --profile abi`
   和 `make check` 均 exit 0；分别得到 drift `PASS (3 contract(s) verified)`、ISA
   `DANGLING=0`/missing ref=0、ABI `RESOLVED=10`/`DANGLING=0`/missing ref=0，及
   `repository checks: PASS`。ISA 的既有 3 条 UNPARSEABLE 仍明确作为 warning 输出，未被隐藏。
5. **A 桶：无问题。** 独立执行
   `git -C /home/holight/DADAO-wiki diff --exit-code 13a414d..9f378f4426e131903d60a208766086ae74a53c89 -- '*SimRISC-01*' '*SimRISC-02*'`，exit 0 且无输出。
6. **四方回归：无问题。** 独立执行 `python3 -u tools/run_differential.py`，exit 0，
   `AGREE(3-way)=200`、`DIVERGE=0`、`HARNESS=6`、`AGREE(4-way)=200`、
   `SAIL-DIVERGE=0`、`QEMU-SKIP=0`。

**独立 reviewer 判定：Finding=0，Accepted。** IN-003a 的实际变更和验收证据一致，
可以关闭；不需要修复或扩大范围。
