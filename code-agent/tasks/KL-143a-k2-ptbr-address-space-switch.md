# KL-143a：K2 PTBR 地址空间切换与显式 TLB invalidate（QEMU + gem5）

**执行者**：Codex
**依赖**：KL-140a～KL-142a（已完成）
**后续依赖者**：KL-144a、KL-145a

## 目标

实现一份 QEMU/gem5 FullSystem 共用的 bare-metal supervisor probe，钉死
KL-140a §1.3 的 address-space context 协议：

1. 两个 task descriptor 的 cooperative frame w1/w2 分别绑定
   `(asid, ptbr_root)`；
2. 恢复目标 task 前严格执行
   `write PTBR[asid] → invalidate target asid full set → restore/use target`；
3. 每次真实 invalidate 后 `tlb_gen += 1`，并在 AS_SWITCH checkpoint 中
   记录目标 task、asid/root 和 generation；
4. 同一 VA 在两个 root 下映射不同 PA/value，证明切换后实际使用目标
   地址空间，而非只读回控制寄存器。

## 场景

- 单 hart、supervisor，ROM/report/control 位于不翻译的 set0。
- task A/B 使用相同 asid=6 和相同 VA，但绑定两个不同 L1/L2 root：
  - root A → PA_A → VALUE_A；
  - root B → PA_B → VALUE_B。
- 使用相同 asid 是有意设计：若只写 PTBR 而省略 invalidate，旧 TLB entry
  会直接暴露为错误值，不能靠不同 TLB set 隔离掩盖协议缺失。
- 至少 12 次 A/B 交替 AS_SWITCH；每次先从对应 cooperative frame 读取
  w1/w2，再写 PTBR、执行覆盖该 asid 4 TiB set 的显式 range invalidate、
  增加 generation，最后访问共享 VA 并逐值自检。
- INIT、每次 AS_SWITCH、FINAL 写入 KL-140a report；context digest 绑定
  目标 135-word cooperative descriptor，memory digest 绑定 seq/current
  task/A-B 进度/switch count/tlb_gen。

## 正负验收

- positive：同一 image 连续至少 10 轮，QEMU/gem5、guest fail-closed、
  host 独立 oracle、cross-backend 全 PASS。
- negative：独立 image 在一次 PTBR root 变化后故意省略一次 invalidate，
  但仍继续真实 VA load。必须由旧 TLB value 触发 guest FAIL，且 host 还
  要从 tlb_gen/checkpoint 协议差异判 FAIL；两端一致不能升格。
- 恢复 positive image 后重新 PASS。
- 回归 KL-140a～142a、KL-139a、lit E2E、普通 ISA differential；
  manifest/issues/wiki 与 diff checks 通过。

## 范围与 non-claim

- 本任务隔离验证 address-space switch protocol，不重新声称 KL-141a
  cooperative register switch 或 KL-142a async trap context。
- `disable→enable` 后旧 TLB entry 生命周期仍为 non-claim，不参与正确性。
- user↔supervisor、RF、Atomics/SMP、多 hart、Linux paging allocator/
  scheduler、真实设备、Minor/O3、性能均不验证。
- 不修改或提交无关的 `gcc-torture-results.json`。

## 记录与 review

完成后在本文件记录实现、内存图、hash、确切命令、正负结果、回归与
non-claim。主体自审后单独启动 subagent review；reviewer 必须检查实际
diff，独立运行正负例，并临时把另一轮 invalidate 省略或破坏一个 descriptor
root 后验证 fail-closed。意见与处理写入本文件。

## 参考

- `docs/reviews/k2-baremetal-regression-contract-20260728.md` §1.3、§3
- `tests/scripts/k2_report.py`
- `tests/scripts/run_kl129a_tlb_probes.py`
- `tests/scripts/run_kl139a_k1_k2_integration.py`
- `tests/scripts/run_kl141a_coop_switch.py`

---

## 完成区

### 实现

- 新增 `tests/scripts/run_kl143a_address_space_switch.py`：
  - task A/B descriptor 使用冻结 135-word cooperative frame，w1=asid6，
    w2 分别为 root A/root B；
  - 两个 root 把同一 VA 映射到不同 PA/value；
  - 12 次 A/B 交替，每次从 descriptor 读取 binding，按
    `PTBR write → full-set range invalidate → tlb_gen++ → translated load`
    顺序执行；
  - INIT + 12 AS_SWITCH + FINAL 共 14 个 guest checkpoint；
  - context digest 绑定目标 descriptor，memory digest 绑定
    seq/current/progress/switch-count/tlb-gen；
  - 沿用 KL-141a raw QMP/gem5 checkpoint transport 和 KL-140a
    `compare_dual_backend()`。

### 内存图

- root A：L1 `0x80010000`、L2 `0x80020000`；
- root B：L1 `0x80030000`、L2 `0x80040000`；
- translated targets：PA_A `0x80100000`、PA_B `0x80110000`；
- task descriptors：`0x80060000` / `0x80061000`；
- control/MDW：`0x8000f000` / `0x8000f100`；
- report：`[0x801f0000,0x801f2000)`；
- shared VA：
  `asid6 | l1[9] | l2[13] | fragment3 | 0x100`；
- invalidate：start=`6<<42`，size=`1<<42`，control command=2。

### 正负结果

主命令：

```text
python3 tests/scripts/run_kl143a_address_space_switch.py --rounds 10
```

- positive：QEMU/gem5 **10/10**，guest/oracle/cross 全 PASS；
- ROM SHA-256：
  `819d48fed0de6af3374c86e503d2a2e66e2710792f67914b9aa286847cf28d66`；
- RAM SHA-256：
  `8495b5cc5f4165c8ad08b7efac23176f7fca6dc4f9f2f0644a6e9e9bede77b03`；
- canonical identity：`0x9a845df8a421d55b`；
- negative omit-invalidate@6：PTBR 改为 B 后保留 A 的 stale TLB entry，
  QEMU/gem5 均 `status=FAIL`、`mismatch=281474976710663`，host
  tlb_gen/oracle 同时判 FAIL；
- `--omit-switch 8` 独立 sensitivity 同样双端 FAIL；
- 恢复 positive image 后 PASS。

### 回归

- KL-140a：**70/70 × 10 PASS**；
- KL-141a：positive/negative/post-restore PASS；
- KL-142a：positive/negative/post-restore PASS；
- KL-139a：QEMU/gem5 **3/3 PASS**；
- lit E2E：**81/81 PASS**；
- differential：
  `AGREE(3-way)=200, gem5-SKIP=2, DIVERGE=0`，
  `AGREE(4-way)=200, Sail-SKIP=2, SAIL-DIVERGE=0`；
- manifest/issues/wiki drift/refs：PASS（3 条既有 non-blocking wiki
  UNPARSEABLE warning）；
- Python compile、`git diff --check`：PASS；
- QEMU/gem5 无组件源码改动。

### Pass / skip / fail / non-claim

- pass：same-ASID dual-root、descriptor PTBR binding、full-set explicit
  invalidate、monotonic tlb_gen、真实 translated value、自包含 stale-hit
  negative、双后端 raw-report oracle；
- skip：无；
- fail：无；
- non-claim：integrated register context switch、async trap context、
  disable→enable TLB lifetime、user mode、RF、Atomics/SMP、多 hart、Linux
  paging/scheduler、真实设备、Minor/O3、性能。

### 独立 review

独立 reviewer：subagent `Mill`（2026-07-29）。

首轮结论：**NOT PASS，1 个 medium；无 blocker/high/low**。

medium：FINAL 前 guest 已确认 current task 为 B，但 guest checkpoint 与
host oracle 都把 FINAL `task_id` 写成 0，二者虽自洽却违反 KL-140a §3.3
“INIT/FINAL=当前任务”的冻结事件所有权。PTBR 字段本身已正确记录
`asid6/rootB/gen12`。

处理：guest FINAL 与独立 oracle 均改为 `task_id=TASK_B`；重新执行完整
10 轮、omit@6 negative 和 post-restore，全部符合预期。修复改变 image，
本完成区 hash/identity 已同步更新。

reviewer 其余核对均通过：

- descriptor 135 words，w1/w2 与实际 PTBR write 一致；
- same-ASID/same-VA dual-root 映射及每轮
  `PTBR→full-set invalidate→gen++→load` 顺序成立；
- omit@8 日志真实命中旧 PA_A，mismatch 精确包含 stale value XOR 与
  `11^12` generation；
- raw report、guest fail-closed、host oracle、双后端比较成立；
- 新文件 whitespace check 无问题。

focused follow-up 最终结论：**PASS，首轮 medium CLOSED，无新增问题**。

reviewer 独立重跑：

```text
python3 tests/scripts/run_kl143a_address_space_switch.py --rounds 1
```

positive 双后端/oracle/cross PASS，omit@6 双端按要求 FAIL，post-restore
PASS；QEMU/gem5 raw FINAL 均为
`seq=13, task=2, asid=6, ptbr=0x8003, tlb_gen=12`，status PASS、
mismatch 0。实跑 ROM/RAM/identity 与本完成区一致。最终无未关闭
blocker/high/medium/low。
