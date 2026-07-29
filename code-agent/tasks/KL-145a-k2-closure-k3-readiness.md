# KL-145a：K2 组合收口与 K3 readiness 冻结

**状态**：进行中  
**日期**：2026-07-29  
**依赖**：KL-139a～KL-144a（均已完成）  
**后续依赖者**：K3 任务（本任务不得启动 K3）

## 目标

关闭 ADR-0015 的 K2 阶段，不新增 ISA、QEMU、gem5 或 Linux 功能：

1. 用一个 fail-closed closure runner 重跑 KL-140a～KL-144a 的完整
   正向/负向/恢复矩阵，并检查明确的 pass/fail 数量和关键文本，不能只看
   退出码；
2. 重跑 KL-139a、lit E2E、普通 ISA 三/四方 differential 与 manifest/
   issues/wiki 一致性门；
3. 汇总 K2 已证明、明确未证明和进入 K3 时仍需完成的事项；
4. 确认 Linux component 仍为 `enabled=false`，本任务不创建
   `arch/dadao`、不拉取/修改 Linux tree，完成后停在 K3 边界。

## Closure matrix

| 场景 | 正向稳定性 | 必须负向 | 恢复后 |
|---|---:|---|---|
| KL-140a report/oracle | 70/70 ×10 | schema/content/identity/SKIP 等内建 mutation | 内建 |
| KL-141a cooperative switch | 双后端 ×10 | rd40@transition7 | PASS |
| KL-142a preemptive trap | 双后端 ×10 | rd17 | PASS |
| KL-143a address-space switch | 双后端 ×10 | omit-invalidate@6 | PASS |
| KL-144a integrated scheduler | 双后端 ×10 | omit-invalidate | PASS |
| KL-139a K1→K2 integration | 双后端 3/3 | 不重复引入新 mutation | N/A |

runner 必须对每个场景检查：

- 期望轮数完整出现；
- QEMU、gem5、guest、oracle、cross-backend 明确 PASS；
- 负向明确为两后端 FAIL、guest `status=FAIL`、mismatch 非零；
- `post-restore round: PASS` 明确出现；
- 任一缺项、SKIP、HARNESS-ERROR、超时或输出格式漂移均整体失败。

## 交付

1. `tests/scripts/run_kl145a_k2_closure.py`：组合 runner，写
   `.work/evidence/kl145a-k2-closure/summary.json`。
2. `docs/reviews/k2-closure-20260729.md`：K2 closure 与 K3 readiness
   单一汇总入口。
3. 更新 `docs/development-roadmap.md`，将 K2 标记为完成并明确停止点。
4. 本任务 MD 完整记录命令、结果、独立 review 和最终提交。

## 验收

- closure runner 全项 PASS，且 JSON 明确列出每个 gate 的命令、退出码、
  关键计数与 verdict。
- `git diff --check` PASS；QEMU/gem5 组件工作树 clean。
- 独立 subagent review 确认 runner 不存在 exit-code-only false green、
  不放宽负向、K3 readiness/non-claim 没有越界。
- review 的 blocker/medium 全部闭环后才可声明 K2 完成。

## K2 范围边界

K2 只证明单 hart、supervisor kernel task 下的架构机制与裸机软件策略：
完整 cooperative/trap context、trap ownership、PTBR/TLB、timer 与 synthetic
external interrupt、双后端独立 oracle。

以下继续是 K3/K4 或更后的工作，不得在本任务升格：

- 真实 Linux `arch/dadao`、Linux ABI/API 接入与 boot；
- user↔supervisor、真实 process/user context、RF；
- Linux pgtable/page-fault policy、scheduler、clocksource/clockevent、
  irqchip、initramfs/ELF `/init` 链；
- Atomics/SMP、多 hart、真实 PLIC/UART/device protocol；
- gem5 Minor/O3、TLB timing/performance 与整体性能。

## 完成记录

### 实现（2026-07-29）

- 新增 `tests/scripts/run_kl145a_k2_closure.py`：
  - 固定 KL-141a～144a 正向轮数为 10，不允许降级 quick evidence；
  - 每项校验明确轮数、backend/oracle/cross、negative guest FAIL、
    mismatch 与 post-restore；不是 exit-code-only；
  - 任一场景失败立即停止昂贵后续 gate，但仍写 FAIL summary；
  - 全部场景通过后再跑 KL-139a、lit、ordinary differential、
    manifest/issues/wiki 与 K3 boundary；
  - JSON schema_version=1，记录 15 个 gate 的命令、exit code、耗时、
    checks、verdict、reason 和 log。
- 新增 `docs/reviews/k2-closure-20260729.md`，作为 K2 closure 与 K3
  readiness 的单一汇总入口。

### 完整实跑

`python3 tests/scripts/run_kl145a_k2_closure.py`：

- observed/expected gate：**15/15 PASS**；
- KL-140a：**70/70 ×10**；
- KL-141a～144a：各自双后端正向 **10/10**，指定负向均为
  QEMU/gem5 guest FAIL + mismatch 非零，恢复后均 PASS；
- KL-139a：**3/3**；
- lit E2E：**81/81**，无 unsupported/fail；
- differential：AGREE(3-way)=200、AGREE(4-way)=200、DIVERGE=0、
  SAIL-DIVERGE=0；
- manifest/issues/wiki refs/wiki drift：PASS；
- backend binding：禁止 QEMU/gem5/config override，实际 binary 与接受
  hygiene 检查的 source tree 绑定；
- known `make check` debt gate：预期 rc=2，并精确复现 5 条既有
  privileged vector coverage 缺口；
- Linux component：disabled、unpin；patch series empty；无
  `arch/dadao`；QEMU/gem5 component worktree clean。

证据：`.work/evidence/kl145a-k2-closure/summary.json` 与同目录逐 gate
日志。

### 已知非绿项

`make check` 复测仍仅在既有 `validate-vectors` coverage 缺口失败：
ldmo-ra、stmo-ra、cfx2rd、cfx2rc、escape。KL-142a 已记录同一集合；
本任务没有把 aggregate 冒充 PASS，也没有新增回归。

### 独立 review

独立 R1：**NEEDS-FIX（0 blocker、4 medium、2 low）**。

1. round 只计数，未验证严格 1..N；negative/post/final 分散匹配且未拒绝
   SKIP；
2. Linux patch check 硬编码目录、未消费 manifest `patch_series`、未递归；
3. clean tree 与环境覆盖后的实际 backend binary 未绑定；
4. review 时 summary 早于最新 runner；
5. `make check` 已知失败未保存本任务日志；
6. roadmap 尚未写 K2 closure。

闭环：

- 新增 ordered round parser；negative 由一条 anchored regex 绑定 QEMU/
  gem5 非零 mismatch；场景、KL-140a、KL-139a 均拒绝 SKIP；
- 在昂贵测试前禁止 QEMU/gem5/config override，并 resolve 实际 binary
  到随后检查 clean 的固定 source tree；
- 从 Linux manifest 消费并冻结 `patch_series`，要求文件存在、在仓内，
  并用 `rglob` 拒绝所有嵌套 payload；
- `make check` 作为 expected rc=2 的 known-debt gate，精确要求五项既有
  coverage 缺口并保存日志；
- 完整重跑刷新 15/15 summary；roadmap 与 closure 文档同步。

focused R2 mutation：duplicate round、out-of-order round、SKIP、
split negative、backend override、nested patch 与 alternate series
全部被拒绝。最终结论：**PASS；无 blocker/medium/low。**

### 最终状态

**KL-145a PASS，K2 closed。K3 未启动，按用户要求在此停止。**
