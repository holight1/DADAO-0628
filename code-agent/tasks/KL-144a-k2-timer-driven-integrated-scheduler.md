# KL-144a：K2 timer 驱动综合调度切换（QEMU + gem5）

**状态**：进行中  
**日期**：2026-07-29  
**依赖**：KL-140a～KL-143a（均已完成）  
**后续依赖者**：KL-145a

## 目标

用一份字节完全一致的 ROM/RAM 镜像，在 QEMU 与 gem5 FullSystem 上把
KL-141a～KL-143a 已分别验证的机制组合起来：

1. supervisor task A 在真实 call/ret 链中被 timer 异步打断；
2. timer handler 按冻结的 198-word trap frame 完整保存、核对并恢复
   RD/RB/RA，设置 `need_resched` 后 `escape` 回到同一被中断任务；
3. task A 在 trap 返回后的 cooperative boundary 执行调度切换，按冻结的
   135-word task frame 保存 A；
4. 调度器写入 task B 的 PTBR，执行完整 ASID 范围 TLB invalidate，
   `tlb_gen++`，再恢复 B 的 task frame；
5. task B 在自己的地址空间读取与 A 相同 VA，得到不同的物理映射值，并
   形成 FINAL PASS。

## 所有权边界

- timer handler 只拥有硬件 trap frame、timer acknowledge 与
  `need_resched`；它必须恢复同一现场并用 `escape` 返回。
- task/PTBR 切换只在 escape 后的 cooperative boundary 发生。
- timer handler 与 scheduler 路径禁止写 cg5 rc0/rc1/rc3/rc5
  伪造返回，也禁止从 timer handler 直接改写 cg5 跳到另一任务。
  镜像启动阶段继续复用 KL-131a/KL-142a 已验收的 K1
  `craft_inner_cfx_mask` fixture；它只在任务运行前建立初始
  `inner_cfx_mask`，不参与 timer 返回或任务选择。
- cooperative switch 的顺序固定为：
  `save outgoing -> COOP_SAVE -> write target PTBR -> full-set invalidate
  -> tlb_gen++ -> translated load -> AS_SWITCH -> COOP_RESTORE
  -> restore incoming -> ret`。

## 场景与 report

- 单 hart、supervisor kernel task only；task A/B 使用同一 ASID、不同
  PTBR root，同一 VA 映射到不同物理值，确保漏 invalidate 会形成真实
  stale hit。
- checkpoint 顺序固定为：
  `INIT, TIMER, TRAP_ENTER, TRAP_RETURN, COOP_SAVE, AS_SWITCH,
  COOP_RESTORE, FINAL`。
- TIMER/TRAP 事件绑定完整 198-word trap frame；COOP 事件绑定完整
  135-word task frame。所有事件均记录当前 PTBR/ASID 与 `tlb_gen`。
- guest 必须独立 fail-closed；host 使用 KL-140a `k2_report.py`
  独立 oracle；双后端各自对 oracle PASS 后再比较规范化 report。

## 负向测试

单独生成 mutation 镜像，在 A→B PTBR 写入后省略显式 TLB invalidate。
因为 A 已先访问同一 VA 并填充 TLB，B 必须观察到 stale A 映射；同时
guest 的 `tlb_gen` 不满足不变量。QEMU、gem5 guest 与 host oracle 均须
FAIL，恢复原镜像后须再次 PASS。

## 验收

1. 正向至少 10 轮：QEMU PASS、gem5 PASS、guest PASS、oracle PASS、
   cross-backend PASS。
2. 漏 invalidate 负向：两后端均明确 FAIL 且 mismatch 非零。
3. 恢复正向镜像后再次 PASS。
4. KL-140a self-test、KL-141a～KL-143a 正负/恢复场景、KL-139a、
   lit E2E 与普通 ISA differential 不回归。
5. 独立 subagent review；所有 blocker/medium 闭环后才能进入 KL-145a。

## Non-claim

不声称 user↔supervisor、RF、Atomics/SMP、多 hart、真实 UART/PLIC、
Linux scheduler/trap/clockevent/pgtable API、TLB 性能、gem5 Minor/O3
或性能。

## 完成记录

### 实现（2026-07-29）

新增 `tests/scripts/run_kl144a_timer_scheduler.py`：

- task A 先启用 ASID 6/root A 并读取共享 VA，真实填充 TLB；
- A 在三层 call/ret 链最深处被 one-shot timer 打断；handler 首条指令
  只关闭自身 cause，随后保存冻结的 198-word frame、设置
  `need_resched=1`、ack timer、污染全部 caller context，再严格逆序恢复并
  `escape`；
- A 从同一 PC/同一 RegRAS 返回，核对完整 trap frame，真实退完三层调用
  链后才进入 cooperative boundary；
- switch 保存 A 的冻结 135-word frame 并发出 COOP_SAVE，写 root B、
  full-set invalidate、`tlb_gen 1→2`、读取同一 VA 的 B 值，再发
  AS_SWITCH/COOP_RESTORE，恢复预置 B frame 并用真实 `ret` 进入 task B；
- 8 条 report checkpoint 严格为 INIT/TIMER/TRAP_ENTER/TRAP_RETURN/
  COOP_SAVE/AS_SWITCH/COOP_RESTORE/FINAL；每条同时绑定 task、frame
  digest、memory digest、PTBR/ASID 与 generation。

正向规范镜像：

- ROM SHA-256：
  `720676eee42849366ca43375f5bb2dc50f24d926e0ca2029c1b98db6237a9ce5`
- RAM SHA-256：
  `0aaafc1c222495970745de46ff81ee980e0ba204e13500ac9326a822b930a6bc`
- canonical identity：`0xde21141152d3c246`

漏 invalidate mutation：

- ROM SHA-256：
  `043273fa1a9a66d0f5fef72576749d02f98810f09f1955a3866da7b34976d1b0`
- RAM SHA-256：
  `c690b9677cb06e4bc1e4296646c43e7bb8a1c5310d4c59fd91bf3b38051dbcdc`
- canonical identity：`0x02aba4a0a60469b6`

### 验证

- `python3 tests/scripts/run_kl144a_timer_scheduler.py --rounds 10`
  → 正向 QEMU/gem5/oracle/cross **10/10 PASS**；
  omit-invalidate 负向两端均 `status=FAIL`、
  `mismatch=281474976710659`；恢复正向镜像再次 PASS。
- KL-141a、KL-142a、KL-143a 各自正向、负向、恢复后正向全部 PASS。
- `python3 tests/scripts/run_kl140a_k2_report_selftest.py --rounds 10`
  → **70/70 ×10 PASS**。
- `python3 tests/scripts/run_kl139a_k1_k2_integration.py --rounds 3`
  → **3/3 PASS**。
- `.work/build/llvm/bin/llvm-lit -sv tests/lit/E2E/`
  → **81/81 PASS**。
- `python3 tools/run_differential.py`
  → AGREE(3-way)=200、AGREE(4-way)=200、DIVERGE=0、
  SAIL-DIVERGE=0（两项 out-of-slice SKIP 保持既有口径）。
- manifest/issues/wiki refs/wiki drift 均 PASS；wiki refs 仅保留 3 条既有
  UNPARSEABLE warning。
- QEMU 与 gem5 组件工作树 clean；本任务没有组件源码改动。

### Pass / fail / non-claim

- PASS：单 hart、supervisor task A→B 的 timer-driven reschedule；
  trap full-context 透明性；escape 后 cooperative ownership；
  task frame + PTBR/TLB 协议；guest/oracle/cross-backend 三层判定。
- FAIL（预期负向）：漏 invalidate 后两后端都观察 stale root A 值，
  generation 不变量也失败；没有 skip 或结果升格。
- non-claim：保持任务书列出的 user/RF/SMP/真实设备/Linux API/
  Minor/O3/性能边界不变。

### 独立 review

独立 subagent R1 结论为 **NEEDS-FIX（0 blocker、2 medium、1 low）**：

1. mutation oracle 曾随漏 invalidate 路径接受 `tlb_gen=1` 与 stale
   `VALUE_A`，削弱 host oracle 独立性；
2. 初版 PTBR 写入使用模块常量，没有从 incoming FRAME_B w1/w2 消费
   地址空间绑定；
3. cg5 禁令文字未明确启动阶段既有 `craft_inner_cfx_mask` fixture
   例外。

闭环：

- mutation 仍使用自己的 identity/解析后 PC，但 oracle 语义固定要求
  `tlb_gen=2` 与 `VALUE_B`；实跑时 host 独立捕获 checkpoint 5～7 的
  generation 与 memory-digest 偏差，同时 guest 保持 FAIL；
- switch 先逐 word 核对 FRAME_B，再从 w1/w2 读取并核对 ASID/root，
  PTBR 使用实际读取的 root；B 入口增加恢复后 rb1 核对；
- 所有权文字限定到 timer/scheduler 路径，并说明 boot fixture。

focused R2 复审与正负实跑后结论：**PASS；原 2 medium + 1 low 全部
闭环，无新 blocker/medium。KL-145a 可放行。**
