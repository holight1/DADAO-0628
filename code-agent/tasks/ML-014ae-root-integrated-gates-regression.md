# ML-014ae：root patch 集成后的门禁与关键运行回归

**执行环境**：本地 subagent worker；承接 ML-014ad patch series 集成

**状态**：Ready（30-task run：11/30）

## 目标

验证 0040/0041 纳入 root patch series 后，仓库门禁和关键用户态链路仍然成立：
确认 root patch 内容、manifest/issues/wiki 检查与 ML-014ac 已通过的启动边界及
single-large malloc/free 双后端回归没有漂移。

## Ownership

- worker 只写 `.work/ML-014ae-*` 产物与本 task MD；可以运行已有锁定构建/测试工具，
  不修改 LLVM/QEMU/gem5/musl 实现，不修改 patch series、manifest、issues、wiki
  或原始 ML-014a。
- 不查阅或引用 `~/toolchain`、`~/knowledge-graph`；不把双大块 allocator 标为完成。
- 多人共享仓库，不回滚他人改动；runtime 结果必须保存 guest 证据，不能只记录 host rc。

## 执行阶梯

1. 核对 0040/0041 与 source hash、series 顺序、root worktree scope；运行
   `scripts/manifest_check.py`、`scripts/check_issues.py`、`scripts/check_wiki_drift.py`
   或仓库对应门禁，原样记录结果。
2. 使用当前锁定 clang/lld/crt1/libc.a/script 重跑 ML-014ab 的 success/boundary/
   failure 三布局和 ML-014y single-large probe，保存 compile/link/objcopy、QEMU
   trace、gem5 trace 与 guest exit 结果。
3. 对比 ML-014ac 结果：三布局应均双端返回 42 并命中 main；single-large 应双端
   返回 42。若环境阻塞，精确区分工具链、模拟器、门禁或脚本原因。
4. 记录事实、差异、限制与下一任务边界；不修改实现。

## 验收

- 门禁结果和 runtime guest 证据可审计。
- root patch integration 没有引入已验证链路回归，或明确记录失败。
- 不宣称 ML-014z 双大块 allocator 已完成；需独立 subagent review。

## 完成区

（由 worker 填写；完成后由不同 subagent 独立 review）

## Completion / bounded integrated-gates regression (2026-07-19)

### Fresh repository gates

The three gates were run in the current root worktree before closing this task.
Raw command output and exact return codes are preserved under
`.work/ML-014ae-root-integrated-gates-regression/gates/`:

- `python3 scripts/manifest_check.py`: `rc=0`; frozen spec
  `9f378f4426e131903d60a208766086ae74a53c89`, 6 references, `PASS`.
- `python3 scripts/check_issues.py`: `rc=0`; Open 23, Closed 31, Total 54,
  `PASS`.
- `python3 scripts/check_wiki_drift.py`: `rc=0`; 3 contracts verified,
  `PASS`.

### Locked inputs and runtime evidence

Current locked input hashes are recorded in
`.work/ML-014ae-root-integrated-gates-regression/locked-current.sha256`.
The post-fix `ld.lld` hash is
`c345424c32040dadbd529bd83a581436285ece63a3cbfbedd9b1a2fe98438956`;
the other locked clang/crt1/libc.a/script identities match the identities
recorded by the accepted ML-014y/ML-014ac chain. No locked input was modified.

Per the bounded-run direction, the QEMU/gem5 matrix was not freshly rerun.
Instead, the verified ML-014ac runtime evidence was reused and copied
byte-for-byte under
`.work/ML-014ae-root-integrated-gates-regression/reused-ML-014ac-runtime/`.
The source record reports the following exact guest results:

| probe | QEMU rc | gem5 rc | guest evidence |
|---|---:|---:|---|
| ML-014ab success | 42 | 42 | `main` at `0x80000110`; gem5 `SIM_END` / `trap-exit code=42` |
| ML-014ab boundary | 42 | 42 | `main` at `0x80000110`; gem5 `SIM_END` / `trap-exit code=42` |
| ML-014ab failure | 42 | 42 | `main` at `0x80000110`; gem5 `SIM_END` / `trap-exit code=42` |
| ML-014y single-large | 42 | 42 | gem5 `SIM_END` / `trap-exit code=42` |

The copied QEMU and gem5 traces are the guest evidence for those results;
their provenance and exact rc record is
`reused-ML-014ac-runtime/runtime-reuse.txt`. This is reuse of ML-014ac’s
post-fix verification, not a new ML-014ae runtime execution.

### Comparison and scope audit

Compared with ML-014ac’s verified-results section, there is no reported
runtime drift: success, boundary, failure, and single-large all remain at
guest rc 42, with the startup layouts reaching `main` and the single-large
probe completing its recorded free path. The new fresh evidence is the three
root gates and the current locked-input hash capture.

This task wrote only `.work/ML-014ae-root-integrated-gates-regression/` and
this task MD. It did not modify implementation, root patch series, manifests,
issues, wiki, or ML-014a, and did not inspect `~/toolchain` or
`~/knowledge-graph`. The copied probe sources/scripts are task-owned reuse
artifacts. This result does not claim that the dual-large allocator is solved;
that remains outside this task and requires independent review.

**Status: Complete (bounded runtime reuse; gates freshly passed).**
