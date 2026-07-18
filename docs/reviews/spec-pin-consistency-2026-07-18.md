# IN-002a：spec pin 一致性审计（2026-07-18）

## 结论

当前合同的真实来源是 Wiki commit `13a414da158dc780ae5501c1443acbffd15cbf4a`（短 hash `13a414d`）：`contracts/isa/spec.md` 和 `contracts/abi/spec.md` 的 `**Source**` 头都明确记录它，且合同中的 C-item 解析说明也引用 `13a414d`。`~/DADAO-wiki` 当前 checkout 同样是该 commit，工作树干净。

`manifests/spec.lock.toml` 却锁定了 `9f378f4426e131903d60a208766086ae74a53c89`（短 hash `9f378f4`）。该 commit 是 `13a414d` 的后继（中间有 8 个提交），不是同一 commit。故当前 `make check` 漂移的直接原因是 **lock 已推进，但合同来源标记和本地 checkout 没有同步完成**；不是合同内容被当前实现反推，也不能仅凭已有升级报告把 `9f378f4` 视为已完成的合同来源。

升级记录本身也不完整：`docs/reviews/wiki-upgrade-9f378f4.md` 声称 Phase 5 已重锁到 `9f378f4`，但 `code-agent/tasks/WU-001a-wiki-upgrade-9f378f4.md` 的状态仍为“待执行”，本地 wiki 仍停在 `13a414d`。这说明记录/落地状态至少需要一次架构师决策后的 reconciliation。

## 命令级证据

### lock、合同头和当前 checkout

```text
$ nl -ba manifests/spec.lock.toml | sed -n '1,10p'
     3 status = "frozen"
     5 local_reference = "/home/holight/DADAO-wiki"
     6 commit = "9f378f4426e131903d60a208766086ae74a53c89"  # WU-001a ...
     7 simrisc_version = "0.4.1"

$ nl -ba contracts/isa/spec.md | sed -n '1,5p'
     3 **Version**: 0.4.0
     4 **Source**: Wiki commit `13a414da158dc780ae5501c1443acbffd15cbf4a` (SimRISC 0.4.1)

$ nl -ba contracts/abi/spec.md | sed -n '1,5p'
     3 **Version**: 0.1.0
     4 **Source**: Wiki commit `13a414da158dc780ae5501c1443acbffd15cbf4a` (SimRISC 0.4.1)

$ git -C /home/holight/DADAO-wiki status --porcelain=v1
(无输出)
$ git -C /home/holight/DADAO-wiki rev-parse HEAD
13a414da158dc780ae5501c1443acbffd15cbf4a
$ git -C /home/holight/DADAO-wiki merge-base --is-ancestor 9f378f4 13a414d; echo $?
1
$ git -C /home/holight/DADAO-wiki merge-base --is-ancestor 13a414d 9f378f4; echo $?
0
$ git -C /home/holight/DADAO-wiki show -s --format='%H %ad %s' --date=iso-strict 13a414d
13a414da158dc780ae5501c1443acbffd15cbf4a 2026-06-29T00:31:51+00:00 DADAO/Guide文件名Unicode连字符→ASCII统一 + SBI内引用修正
$ git -C /home/holight/DADAO-wiki show -s --format='%H %ad %s' --date=iso-strict 9f378f4
9f378f4426e131903d60a208766086ae74a53c89 2026-06-30T00:46:42+00:00 phymem→pmem全局重命名
```

### 13a414d..9f378f4 的 delta 与 A 桶

```text
$ git -C /home/holight/DADAO-wiki diff --stat 13a414d..9f378f4
5 files changed, 126 insertions(+), 129 deletions(-)

$ git -C /home/holight/DADAO-wiki diff --stat 13a414d..9f378f4 -- '*SimRISC-01*' '*SimRISC-02*' '*SimRISC-03*'
(无输出)

$ git -C /home/holight/DADAO-wiki log --reverse --oneline 13a414d..9f378f4
bc39c7c MISC-RF子表全部浮点指令补格式后缀(-orrr/-orri)
b3d6c82 cg4重组: excp_num拆为sync_num+async_num，escape_num移至rc5
ea10f5e CFXMEM触发条件增加内部储存块非法访问，全表描述更新
6079ecd 异常进入退出: 文本伪代码统一、cfxld/cfxst路由简化、check_nonmaskable标签、not sync计数
defdd96 §5重构+FE→FPEXCP，中断模型前移，指令行为/escape说明整理
10929f7 cfx_power_ctrl去重 + PTBR/PTHI/PAHI跳转表rb→rd中转
b1a5f7f ftcls/focls格式orrr→orri、add补rd0、popcnt→TODO、escape指代、ALLOC_PAGE返回值
9f378f4 phymem→pmem全局重命名
```

逐提交的 `git show --stat` 结果表明：`bc39c7c` 只改 SimRISC-00 的 FP 格式后缀；`b3d6c82`、`ea10f5e`、`6079ecd`、`defdd96` 改 SEE/异常；`10929f7` 改 SBI 与 SimRISC-04 CSR 名；`b1a5f7f` 改 FP/SEE/SBI 及 SBI 示例；`9f378f4` 改 SEE/SBI/HBI 的 `phymem`→`pmem`。没有 SimRISC-01/02/03 文件变更。因此本批 A 桶（M1 标量/地址核心语义、编码、legality）为空；其余是 B 桶 deferred 域或 C 桶装饰/示例修正。

### 当前门禁与回归

```text
$ python3 scripts/check_wiki_drift.py
ERROR: contracts/abi/spec.md: Wiki commit 13a414da158d… != locked 9f378f4426e1…
ERROR: contracts/isa/spec.md: Wiki commit 13a414da158d… != locked 9f378f4426e1…
check_wiki_drift_exit=1

$ make check
...
manifest validation: PASS
validate_encoding: 87 records OK
validate_vectors: 10 files, 212 cases, 87/87 opcodes covered OK
ERROR: contracts/abi/spec.md: Wiki commit 13a414da158d… != locked 9f378f4426e1…
ERROR: contracts/isa/spec.md: Wiki commit 13a414da158d… != locked 9f378f4426e1…
make: *** [Makefile:122: check-wiki-drift] Error 1
make_check_exit=2

$ python3 tools/run_differential.py
=== AGREE(3-way)=200 ... DIVERGE=0 HARNESS=6 QEMU-SKIP=0 ===
=== SAIL 4th column: AGREE(4-way)=200 Sail-SKIP(out-of-slice)=0 SAIL-DIVERGE=0 ===
run_differential_exit=0
```

差分回归证明当前实现相对既有 M1 向量没有新分歧，但它不能证明上游到合同的 ① 一致性；A 桶判断仍以 Wiki 的实际 diff 为准。当前 `make check` 的失败仅诊断为 provenance mismatch，未为变绿修改门禁或合同。

### 受保护范围与已有工作区改动

任务开始前和审计过程中，`git diff --name-only -- contracts manifests docs/issues.yaml` 均只有：

```text
docs/issues.yaml
```

该文件的 93 行 diff 是任务开始前已存在的 ML-014a mmap issue 修改；本任务没有修改它、`contracts/` 或 `manifests/`。`~/DADAO-wiki` 也没有工作树改动。

## 两种可行收口方案

### 方案 A：保留 `9f378f4`

需要在架构师批准后：

1. 将 `contracts/isa/spec.md` 和 `contracts/abi/spec.md` 的 `**Source**` 更新为完整 `9f378f4`；由于 A 桶为空，不应伪造 M1 语义变更，正文只需按实际 wiki 引用审查。ISA 中“由 `13a414d` 解决”的历史说明应改成明确的历史/升级说明，避免与新的头部来源产生歧义。
2. 将 `/home/holight/DADAO-wiki` checkout 到 `9f378f4`（只读参考目录的 checkout 操作，不修改 wiki 内容），并保持干净。
3. 把 `WU-001a` 状态、升级审计的 Phase 5 记录和 `docs/issues.yaml` 中“pin 已推进”的记录对齐；这些是记录文件，不应继续出现“待执行”和“已完成”两种状态。
4. 在上述同步后重跑 `make check`、ISA/ABI wiki-ref 检查，并重跑 `git diff 13a414d..9f378f4 -- '*SimRISC-01*' '*SimRISC-02*'` 与四方差分。验收证据应为 drift PASS、A 桶零 diff、`AGREE(4-way)=200 / DIVERGE=0`。

风险：`9f378f4` 的 SEE/SBI/HBI/FP 变化仍属于当前 foundation 的 deferred 基线；它们不能被合同头更新掩盖，相关域启动时必须按 ADR-0013 回放吸收。另有 local checkout 变更带来的可复现性与审计操作风险。

### 方案 B：回退/保留 `13a414d`

需要在架构师批准后：

1. 将 `manifests/spec.lock.toml` 恢复为完整 `13a414da158dc780ae5501c1443acbffd15cbf4a`；`simrisc_version` 等版本字段保持不变。
2. 合同文件不变；当前 `~/DADAO-wiki` checkout 已经正确，无需操作。
3. 在升级任务/审计/issue 记录中明确 `13a414d→9f378f4` 只是已审计但未落地的候选升级，或补一条 reconciliation，不能继续声称当前 pin 已为 `9f378f4`。
4. 重跑 `make check`，并保留 `9f378f4` 的 B/C delta 清单作为下次升级的输入；A 桶仍按现有证据为空，四方差分仍应复跑确认。

风险：lock 暂不包含 9f378f4 的 B/C 变化，未来 SEE/SBI/HBI/FP 启动时必须重新吸收这 8 个提交；但这不会丢失当前 M1 合同的真实 provenance。

## 推荐

推荐先采用方案 B，恢复“lock = 合同头 = 当前 wiki checkout = `13a414d`”的可审计基线，再单独由架构师决定是否正式完成 WU-001a 的 `9f378f4` 升级。理由是当前合同和本地 checkout 都明确来自 `13a414d`，而升级任务仍标记为待执行；在没有完成 checkout、合同 provenance 和任务记录三方同步前，不应把 lock 单独保留在 `9f378f4`。这只是 pin 选择建议，不在 IN-002a 中擅自修改规范。
