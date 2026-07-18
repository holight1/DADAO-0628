# ML-014ac：修复 DADAO RELA_PAGE 与 signed-low 的页舍入协同

**执行环境**：本地 subagent worker；承接 ML-014ab 的三布局阈值诊断

**状态**：Ready（30-task run：9/30）

## 目标

修复 DADAO lld `R_DADAO_RELA_PAGE` 在目标地址低 12 位达到 `0x800` 时仍使用
未舍入目标页的问题，使 `rela(page) + sign-extended RELA_LO` 重建真实目标地址。
先保证 ML-014aa 的 startup→main 交接恢复，再回归 ML-014ab 的 success/failure/
boundary 三布局；不扩展到 allocator 语义。

## Ownership

- worker 负责外部 LLVM 源树 `.work/source/llvm` 中 DADAO lld relocation 实现及
  对应测试；任务记录写入本 task MD，并记录 source commit/hash。
- 不修改 root `docs/issues.yaml`、wiki pin、`ML-014a`、已有 patch manifest 或
  `~/toolchain`、`~/knowledge-graph`；不回滚他人改动。
- 修复应保持低位 `0x000..0x7ff` 的既有成功行为，同时使 `0x800..0xfff` 使用
  下一页基址；不得通过改 simulator、改 linker script 或硬编码 startup 地址绕过。

## 执行阶梯

1. 在 DADAO target relocation handler 中实现与 sign-extended 12-bit low half
   一致的目标页舍入，并保留 PC+4 place 语义；补充针对低位 `0x7ff/0x800`、跨页
   和正/负 PC page delta 的单元或 lld regression coverage。
2. 构建锁定 lld，使用 ML-014ab 成功/失败/边界 probe 重链；保存 object/ELF/map/
   disassembly 与 QEMU/gem5 结果，确认不再跳到栈地址。
3. 回归 ML-014y 的单大块 malloc/free probe，确认修复没有破坏已通过的基本链路。
4. 记录事实、source commit、测试限制和未决项；不在本任务宣称双大块 allocator
   已完成。

## 验收

- lld 代码和测试可审计，source commit 可复现。
- ML-014ab 三布局在两后端均按预期进入 `main`/返回 42，或明确记录具体环境阻塞。
- ML-014y 双后端仍返回 42。
- 必须由不同 subagent 独立 review 实现和证据。

## 完成区

（由 worker 填写；完成后由不同 subagent 独立 review）

### Completion / limitation (2026-07-19)

- Source fix commit: `f5a06de8135832a56d14b677ccfbf08d8121064a` (`f5a06de`).
- The rebuilt `.work/build/llvm/bin/ld.lld` was present, but this run was stopped
  before relinking the ML-014ab probes or running QEMU/gem5; no new task-owned
  ML-014ac runtime artifacts were produced.
- Therefore ML-014ac does not claim the fix works at runtime. The only available
  test evidence remains the pre-fix ML-014ab record: success reached `main`/42,
  while boundary/failure reached `0x7ffff800`/`0x7ffff804` (QEMU 130; gem5 0).
- ML-014y was not rerun in this stopped run; its existing record reports QEMU and
  gem5 exit 42 for the prior locked artifact, not validation of this source fix.
