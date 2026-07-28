# KL-139a：K1→K2 双后端集成探针（QEMU + gem5）

**执行环境**：远端 Codex（本仓库），探针脚本+文档，一般不需要改
QEMU/gem5 源码（除非集成时才暴露出的边界 bug，属于"发现问题先自己修
一轮"范围，见下方约束）

**依赖**：`KL-126a`（已完成）、`KL-127a`、`KL-128a`（若单独存在——
本轮 gem5 侧 PTW 故障是否并入 `KL-127a` 由该任务完成区决定）、
`KL-129a`、`KL-131a`、`KL-133a`、`KL-137a` 全部完成。**这是整条 K1
MMU/中断链的唯一汇合点，必须最后做。**

## 背景

`docs/reviews/kernel-mmu-interrupt-recon-20260726.md` §5 把 K1 收尾项
拆成了 MMU 链（`KL-125a~130a`）和异步链（`KL-131a~138a`），两条链在
共享基础设施（`KL-119a`/`122a`/`124a`）后可并行推进，但最终必须汇合成
一个**单一 bare-metal image**，验证所有机制组合在一起时仍然正确——
逐项验证过的机制不代表组合起来没有交互问题（例如 PTW 故障处理时机
撞上异步中断投递、TLB 失效时机撞上 timer 到期）。

## 目标

一个 QEMU+gem5 都能跑的 bare-metal 镜像（可以是多个小场景顺序执行，
不要求单一线性流程），组合验证：

1. MMU 开启（PTBR enable=1）、异常向量页常驻（向量所在页本身不缺页，
   wiki 明确硬件不提供向量缺失恢复机制，探针要保证这一点成立）。
2. 普通页和超页各至少一次成功转换（`KL-125a`/`126a`）。
3. 至少一类 walk-origin 故障（`KL-127a`）+ 一次 self-handler retry
   或 skip。
4. TLB hit/miss/invalidate 组合（`KL-129a`），含至少一次
   `cfx_tlb→cfx_ptw→cfx_tlb` 嵌套委托返回。
5. timer 从 mask 状态到期（只置 pending）到解除 mask 后精确投递
   （`KL-133a`）。
6. 已冻结的合成外部源 `K1_EXT0` 触发（`KL-137a`）。
7. 至少一次跨 cfx 优先级验证（两个不同 cfx 同时 pending，低编号优先，
   `KL-131a` 已验证过的机制在组合场景下再确认一次）和一次同 cfx 内
   多 cause 优先级验证。

## 约束

- **不是新实现任务**——每个机制本身的正确性已经在各自任务里验证过，
  本任务只验证"组合在一起不冲突"。如果发现真实的组合级 bug（例如某个
  机制的假设在另一个机制存在时不成立），按`不要一发现问题就直接转手`
  的既定工作流，架构师先尝试定位+修复一轮，修不成再拆独立任务。
- **不引入新的架构声明**——凡是前序任务已经明确 non-claim 的范围
  （counters1-7、真实 UART 协议、Linux 分页策略等）本任务同样不能声称
  已覆盖。
- 显式列出双后端各自的 pass/skip/fail/non-claim（不要只报一个笼统的
  "全部通过"）——这是 `docs/reviews/kernel-mmu-interrupt-recon-20260726.md`
  §5 对本任务的原始要求。
- 完成后写「完成区」+ 自审记录。若本任务改动了 QEMU/gem5 源码（而不
  只是探针/文档），额外需要 patch-series bare-pin replay。

## 验收

- 上述7类场景组合进同一次（或同一批顺序执行的）bare-metal 运行，
  QEMU/gem5 双后端各自跑通，结果一致。
- 显式 pass/skip/fail/non-claim 清单，覆盖本任务验证的每一类机制。
- 现有全部探针（整条 K1 链累积的所有探针）零回归。
- 全量 lit E2E、`tools/run_differential.py`、`manifest_check.py`、
  `check_issues.py` 无回归。
- 若有源码改动：patch-series bare-pin replay，QEMU/gem5 tree hash
  分别与各自开发树一致。

## 参考指针

- `docs/reviews/kernel-mmu-interrupt-recon-20260726.md` §5 最后一行
  （本任务原始范围描述）
- `docs/adr/0015-kernel-bringup-charter.md`（K1→K2→K3→K4 里程碑定义，
  本任务是 K1 收尾、K2 开始前的最后一道关）
- `code-agent/tasks/KL-125a`～`KL-137a` 各任务完成区（本任务组合验证
  的全部机制来源，不要重新发明验证方法，直接复用/组合已有探针脚本）

## 完成区（2026-07-28）

**状态：PASS。** 实现、主验收与独立 reviewer 均已通过；没有访问
`~/toolchain` 或 `~/knowledge-graph`，没有触碰
`gcc-torture-results.json`。

### 实现

新增
`tests/scripts/run_kl139a_k1_k2_integration.py`。它只复用前序脚本的指令
编码器和后端启动接口，不调用任何既有独立 probe。脚本生成并让两个后端
运行完全相同的：

- 单一 ROM image：
  `.work/evidence/kl139a-integration/kl139a-integration.bin`；
- 单一 RAM/page-table image：
  `.work/evidence/kl139a-integration/kl139a-integration-ram.bin`。

guest 从一次 hypv→supv handoff 开始，到最终 halt 139 之间不重启、不
清空架构状态。`rd29` 是跨全部阶段共享的 mismatch accumulator；任一
阶段的 guest 内检查失败都会使最终 halt 变为 163，而不是依赖两个后端
返回相同值来判定成功。

组合流程如下：

1. PTW/TLB 的 enable bitmap 同时设置为仅 `set6`，并由 guest 读回核对。
   cfx_ptw/cfx_tlb/cfx_timer/cfx_uart 的全部异常向量和 handler 均位于
   `0x00100000` ROM 的 set0；set0 未启用 PTW，因此向量页是常驻 identity
   页，不依赖发生故障的 set6 页表。
2. 同一个 set6 页表同时包含 normal L1→L2 leaf 与独立 super leaf；
   guest 逐值核对 normal/super 转换。
3. 一个首次访问的 normal leaf 只有 W permission，真实 PTW walk 产生
   `cfx_ptw.NRPERM`。self-handler 核对 `cause_id/cause_ip/cause_info`，
   修复 PTE、恢复 live operand，并 `escape cfx_ptw,0` retry；重试读值
   正确。
4. page13/page14 在同一 TLB 中经历 miss/fill/hit，软件修改两项 PTE 后
   使用 `start=page13+0xf000,size=0x2000` 做 range invalidate。guest
   判别 page13 重新 walk 到新值、page14 仍命中旧值，直接把 KL-129b
   low16 修复纳入集成回归。
5. 另一个 read-only TLB hit 在写访问时产生 `cfx_tlb.NWPERM`；
   cfx_tlb handler 执行真实 `trap cfx_ptw,1`，cfx_ptw handler 核对
   `prev_cfx_code=cfx_tlb` 后 E1 返回，随后修 PTE、invalidate，并
   `escape cfx_tlb,0` retry 原写操作。guest 再从物理 identity 地址核对
   写入值，证明真实 `cfx_tlb→cfx_ptw→cfx_tlb` 链完成。
6. K1_EXT0 在 retirement 0 assert、retirement 1 deassert；直到 MMU/TLB
   流程结束都不 ACK。guest 此后核对 `exist=1`、private pending=1、
   common UART0 pending=1，证明 deassert 不隐式清 latch。UART5 使用
   KL-131a 已冻结的持续 test level，和 UART0 一起形成同 cfx 双 cause。
7. timer0 先在 private mask=1 时 one-shot 到期；guest 在仍不可递交时
   核对 private/common TIMER pending，再解除 private mask。共享 global
   mask 的最后一次写同时放开 timer、UART0、UART5。
8. 三个不同 poison PC 由各自 frame 精确核对：先递交
   cfx_timer(18)/TIMER，再递交 cfx_uart(62)/UART0；UART0 handler ACK
   已 deassert 的 K1_EXT0 且保留 UART5，然后主流程只解除 UART5 cause
   mask，最后递交 UART5。由此同时证明跨 cfx 最低 cfxcode 优先和同 cfx
   最低 cause bit 优先。

首次开发运行已经正确走完以上链路，但最终误断言持续电平 UART5 在 W0C
后 common pending 应为 0，导致双端 guest fail=163。日志证明 UART5 按
规范在下一边界重新锁存；修正的是 probe 断言（改为核对 bit37
重锁存），没有放宽 guest 判别，也没有发现或修改组件实现。

### 双后端显式结果

最终脚本连续运行 10 轮；每轮都是上述完整单镜像，不是十组独立场景。

- QEMU：
  - pass：MMU enable/常驻向量、normal+super、walk fault self-retry、
    TLB miss/fill/hit、KL-129b low16 invalidate、真实 E1、mask 时 timer
    到期及精确递交、K1_EXT0 lifecycle/递交、cfx18<cfx62、
    UART0<UART5；**10/10**；
  - skip：无；
  - fail：无；
  - non-claim：Linux paging、向量页缺失恢复、TLB 性能/时序、
    disable→enable entry lifetime、timer1-7/increment、真实
    UART/PLIC/device protocol、Minor/O3/SE、多 hart。
- gem5 FullSystem `DADAOAtomicSimpleCPU`：
  - pass：与 QEMU 同一完整清单；**10/10**；
  - skip：无；
  - fail：无；
  - non-claim：与 QEMU 相同；额外明确不外推到 Minor/O3。

证据位于 `.work/evidence/kl139a-integration/`：

- `integration-{qemu,gem5}-round01.log`～`round10.log`；
- `kl139a-integration.bin` 与 `kl139a-integration-ram.bin`。

每个后端日志除 guest halt 139 外，还必须出现真实
`cfx_tlb miss-fill` 和 `cfx_tlb hit` trace；gem5 还要求恰好一条
`SIM_END ... code=139`。

### 回归

- 全部既有 K1：
  - KL-113a、117a、120a、122a、124a、125a、126a：PASS；
  - KL-127a：30 个 fault + 10 个 A/D 双端 PASS；
  - KL-129a：13/13 双端 PASS；
  - KL-129b：4/4 双端 PASS；
  - KL-131a：scenario A=131/131、B=132/132；
  - KL-133a：cycle/fault/one-shot/zero/periodic/mask/relatch 全部 PASS；
  - KL-137a：lifecycle=137/137、priority=138/138。
- `.work/build/llvm/bin/llvm-lit -sv tests/lit/E2E/`：**81/81 PASS**。
- `python3 tools/run_differential.py`：
  `AGREE(3-way)=200`、`gem5-SKIP=2`、`DIVERGE=0`；
  `AGREE(4-way)=200`、`Sail-SKIP=2`、`SAIL-DIVERGE=0`。
- manifest：PASS。
- issues：`Open=24 Closed=43 Total=67`，PASS。
- ISA wiki refs：PASS，只有3条既有 UNPARSEABLE warning；
  ABI wiki refs：PASS；wiki drift：3/3 PASS。
- 根仓、QEMU、gem5 `diff --check`：PASS（见最终自审复验）。

### 组件与 bare-pin replay

集成没有暴露组件 bug，因此 QEMU/gem5 源码、提交和 patch series 均未
改变，没有新增 0037/0030：

- QEMU 从 manifest pin
  `385b0a7d9785c8f3ac7b116d7f31d61502b55183`（解析到 commit
  `7c949c53e936aa3a658d84ab53bae5cadaa5d59c`）plain `git am`
  **36/36**；replay/dev tree 均为
  `a0b9fc2ce42f17d07809f14f405082132e7db548`。
- gem5 从 manifest pin
  `c8222cc67a399bfc01e8658dd14b30d5bfd634f9` plain `git am`
  **29/29**；replay/dev tree 均为
  `d5663694d6706324d1c4e0be26dcb0c4ed50db3c`。

### 自审

**结论：PASS。**

- 单一 ROM/RAM image 和单次 guest 运行可由证据路径直接核对；runner
  没有调用前序 probe 的 `main()`、generator 或 run loop。
- 所有功能判断都写入 guest mismatch accumulator；后端退出码、双方一致
  和 trace 只作附加证据。
- PTW enable bitmap 与 handler 地址共同证明向量常驻条件；没有声称硬件
  能恢复缺失向量页。
- walk fault 的 frame 字段、修 PTE 和 self-retry，TLB fault 的 frame、
  PTW trap frame、E1 previous-cfx、invalidate 与原指令 retry 都有独立
  guest 检查。
- 三个不同 `cause_ip` poison 槽证明实际递交顺序，不以最终计数代替
  priority 判别；K1_EXT0 与 timer 的 private/common pending 均在解除
  mask 前由 guest 读取。
- KL-129b low16 反例被原样组合进共享状态；disable→enable entry
  lifetime 仍是 non-claim，没有新增架构声明。
- 任务仅新增根仓 probe 并更新 task/roadmap；组件树保持 clean，根仓按
  用户要求不提交。

### 独立 subagent review

**结论：PASS，无阻塞、高、中或低严重度 finding。**

- 独立确认每轮只生成并启动同一份 ROM/RAM，guest 从 handoff 到 halt
  不重启且共享状态；runner 仅复用编码/启动 helper，没有调用旧 probe
  的执行链。
- guest mismatch accumulator 实际覆盖 MMU/PTW fault retry、TLB/E1、
  timer、K1_EXT0 和两级优先级。reviewer 故意篡改 normal-page RAM
  期望值后，QEMU/gem5 均从 pass 139 变为 guest fail 163，证明结论不
  依赖 trace、成功退出或双端一致；恢复后专项 5/5 通过。
- handler 布局、live operand 恢复、三个 poison `cause_ip`、
  trap/escape 以及 K1_EXT0 retirement schedule 未发现 off-by-one 或
  区段重叠。UART5 是 KL-131a 持续 test level，K1_EXT0 是带私有
  latch 的已撤销源，两者角色与 ACK 语义未混淆。
- reviewer 独立复跑全部前序 K1、E2E 81/81、三/四方差分 200 零分歧；
  QEMU 36/36 与 gem5 29/29 replay tree 分别匹配开发树，组件仓 clean。
- 双后端 pass/skip/fail/non-claim 清单准确；未外推到 Linux paging、
  向量页恢复、真实 UART/PLIC、性能/时序、Minor/O3/SE 或多 hart。
