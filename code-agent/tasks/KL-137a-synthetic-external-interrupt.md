# KL-137a：合成外部中断源 K1_EXT0（QEMU + gem5）

**执行环境**：远端 Codex（本仓库），QEMU 源码改动
（`.work/source/qemu`）+ gem5 源码改动（`~/DADAO-gem5`，独立仓库）

**依赖**：`KL-131a`（异步分派核心——外部源走它的 mask/pending/优先级
机制，不新造）。若下发时 `KL-131a` 尚未完成，本任务暂不能开工。

## 背景

`KL-119a` 已裁定（`contracts/isa/spec.md` §8.5.4）：K1 **不**冻结、
**不**声称任何 UART 或 PLIC 设备协议——wiki 只定义了 UART0 是
`cfx_uart` 的 maskable cause bit32 和一个 `uart_pending` 私有锁存，
64 个 UART0 设备寄存器只写"参照硬件协议"，没有真实寄存器格式。K1 唯一
承诺的是一个**测试机器专用的合成电平源** `K1_EXT0`，路由为
`cfx_uart` source0：断言时置私有 `cfx_uart_pending` bit0 并 OR 公共
`UART0`（`1<<32`）cause bit 进 `cfx_uart_pending`（共有 cg4/rc7）；
撤销电平时两个锁存都不自动清（软件必须先清私有位再清公共位）；软件在
源仍然有效时清任一锁存都会在下一指令边界被重新 OR 回去。

## 目标

### 1. `cfx_uart` 最小寄存器（QEMU + gem5）

- `cg8/rc0`：`cfx_uart_pending`（RW，W0C，私有源锁存，本任务只用
  bit0）。
- `cg8/rc1`：`cfx_uart_exist`（RO——本任务的合成源存在，读1）。
- **不实现** `cg32-63` 的 UART0-31 设备寄存器块——那是真实协议，
  `KL-119a` 已明确不冻结，本任务不能替它发明格式。

### 2. `K1_EXT0` 合成源刺激机制（QEMU + gem5，测试专用，非架构可见）

参考 `KL-120a` 已有的 `cfx_common_pending_test_code/seed`
测试注入模式（QEMU CPU property / gem5 Param，默认关闭不影响任何现有
行为）：新增一个只用于本任务的电平断言/撤销控制接口（命名自定，例如
`k1-ext0-assert`/`k1-ext0-deassert` 或等价的 property/Param），显式标注
"仅测试基础设施，非 guest 可见 ISA"。语义：

- 断言：置私有 `cfx_uart_pending` bit0 = 1，OR 公共 `cfx_uart_pending`
  (`cg4/rc7`) 的 `UART0` (`1<<32`) 位 = 1。
- 撤销：清除电平本身，但**不**清任何锁存位——两个锁存都要靠软件自己
  写0清除。
- 电平仍然有效时，软件清了锁存也要在下一指令边界被重新 OR 回去（复用
  `KL-131a` 已经实现的电平重锁存机制，不要重复实现）。

### 3. 中断投递（QEMU + gem5）

`UART0` cause（`1<<32`）走 `KL-131a` 的通用异步分派核心——mask（
`cfx_uart_<mode>_excp_cause_mask`，本任务需要确保 `cfx_uart` 这个 cfx
也纳入 `KL-131a` 已建的通用 per-cfx 寄存器表，如果 `KL-131a` 完成时已
经是通用实现，这里不需要额外代码，只需要验证）、优先级、指令边界触发。
`UART0` 的 `excp cause info` 按 wiki 异常原因表定义为"全零"。

## 约束

- **不实现 UART0-31 真实设备寄存器/协议**，也**不声称**已实现任何
  串口。测试证据只能叫"合成外部中断源"，不能写成"UART 驱动/串口已支持"
  这类措辞。
- **不新造中断投递机制**——完全复用 `KL-131a`。
- 完整 patch-series bare-pin replay（tree-hash 比对），QEMU/gem5 分别做。
- 完成后写「完成区」+ 自审记录，继续沿用"自己开 reviewer subagent
  复核"的方法。
- 现有全部探针零回归。

## 验收

- 断言→（mask 允许时）指令边界精确触发→`excp_cause_id`/`info` 正确→
  `escape` 返回。
- 断言→屏蔽状态下只置 pending 不触发→解除屏蔽后下一边界触发。
- 撤销电平后，先清私有位、后清公共位的顺序验证（按 §8.5.1 冻结顺序）。
- 电平仍有效时提前清除锁存 → 下一边界重新锁存（至少验证一次）。
- 现有全部探针零回归。
- 全量 lit E2E、`tools/run_differential.py`、`manifest_check.py`、
  `check_issues.py` 无回归。
- patch-series bare-pin replay，QEMU/gem5 tree hash 分别与各自开发树
  一致。

## 参考指针

- `contracts/isa/spec.md` §8.5.1（应答顺序）、§8.5.4（K1_EXT0 完整
  冻结契约，本任务的规范来源）
- `~/DADAO-wiki/DADAO-12-SEE-主管系统运行环境.md` 第40-42行（设备按
  cfx 路由原则）、第602-628行（`cfx_uart` 专有寄存器表+异常原因表）、
  第650-656行（电平触发/重锁存语义）
- `code-agent/tasks/KL-131a-*.md` 完成区（异步分派核心，本任务复用
  其 mask/pending/优先级/指令边界/电平重锁存机制）
- `code-agent/tasks/KL-120a-*.md` 完成区（测试注入寄存器的既有写法，
  本任务的合成源刺激接口参考同一模式）

---

## 完成区（2026-07-28）

**状态**：PASS。实现、主验收与独立 reviewer 均已通过；根仓提交由主
agent 完成。

### 实现

- QEMU 与 gem5 均新增 `cfx_uart` 最小架构状态：
  - `cg8/rc0 cfx_uart_pending`：RW/W0C，只实现 source0/bit0；
  - `cg8/rc1 cfx_uart_exist`：RO 常量 1，写入无效果；
  - reset 时 private pending 为 0；gem5 `copyRegsFrom()` 同步复制该架构
    latch。
- 两端均未新增 `cg32-63` 分支，没有实现任何 UART0-31 设备寄存器。
- `K1_EXT0` 刺激是默认关闭的后端配置，不是 guest ABI：
  - QEMU QOM properties：
    `k1-ext0-test-enable`、`k1-ext0-assert-retired`、
    `k1-ext0-deassert-retired`；
  - gem5 DADAOISA Params 与 `dadao_fs.py --k1-ext0-schedule` 提供同样
    配置；
  - 电平在 `cycle_lo >= assert-retired` 且
    `cycle_lo < deassert-retired` 的指令边界有效，同一次运行可完成
    assert/deassert；guest 没有可写的合成源控制寄存器。
- 每次异步边界扫描先更新测试电平：有效时置 private bit0；随后只要
  private bit0 仍为 1，就无条件把 common `UART0` bit32 重新 OR 回
  `cfx_common_pending[cfx_uart]`。该反射不受电平已经撤销与否、三级通用
  mask 或其它 eligibility 条件影响。
- 撤销仅移除测试电平，不清 private/common latch。电平有效时软件提前
  清 private/common，下一边界会重新锁存；电平撤销后必须由 guest 先清
  private，再清 common。
- 中断选择、三级 mask、async counter、精确 entry、`cause_info=0`、
  cfx/cause 优先级完全复用 KL-131a。QEMU 仅在该默认关闭的 schedule
  启用时进入单指令 TB 边界模式；未新造第二套投递机制。

### 持久 guest 判别探针

新增
`tests/scripts/run_kl137a_synthetic_external_interrupt.py`，两个 flat
bare-metal image 均在 guest 内累积逐字段比较结果，只有所有断言成立才
halt 到成功码；runner 同时要求 QEMU 进程码、gem5 进程码及唯一
`SIM_END` guest code 精确匹配。

1. `lifecycle`（pass 137）：
   - 验证 reset private pending=0、exist=1 且 RO；
   - 在 cause/global mask 阻塞时按退休边界 assert，验证只置
     private/common pending 而不递交；
   - 电平仍有效时依次提前 W0C private/common，下一边界均读回重锁存；
   - 先放开 cause mask，最后一次 shared global-mask 写退休后必须在
     poison 指令执行前精确 entry；
   - 验证 `cause_id=UART0`、`cause_info=0`、`cause_ip=poison`、
     `excp_async_num=1`；
   - handler 两条指令中第一条先 mask self，第二条 `escape,1`；
     deassert 安排在 escape 退休后的边界，验证两个 latch 均未自动清；
   - guest 严格先 private 后 common ACK，之后两者保持 0。
2. `priority`（pass 138）：
   - 在 shared global mask 阻塞期间同时形成 TIMER 与 K1_EXT0 pending；
   - 一次 global-mask 写同时放开 cfx18/cfx62；
   - 两个相邻 poison 地址分别保存为 timer/uart `cause_ip`，证明
     lexicographic 选择为 cfx_timer(18) 先于 cfx_uart(62)，而不是只凭
     最终两个 counter 都为 1 推断顺序。

最终组件提交后的 runner 连续 **10/10** 轮双后端稳定通过：

```text
PASS: lifecycle(assert/mask/relatch/deliver/deassert/ack)=137/137;
priority(timer-cfx18-before-ext0-cfx62)=138/138
```

### 构建与回归

- QEMU：`ninja -C build qemu-system-dadao` PASS；仅有既存
  `-Wmissing-prototypes` warning。
- gem5：`scons build/DADAO/gem5.opt -j4` PASS；png/HDF5/protoc/
  capstone 等宿主可选依赖 warning 与本任务无关。
- 既有 K1 全回归 PASS：
  KL-113a/117a/120a/122a/124a/125a/126a/127a/129a/129b/131a/133a；
  其中 KL-127a 为 30 fault + 10 A/D，KL-129a 为 13/13，KL-129b
  为 4/4，KL-131a 为 131/131 与 132/132，KL-133a 七场景全过。
- E2E：`.work/build/llvm/bin/llvm-lit -sv tests/lit/E2E/`，
  **81/81 PASS**。
- differential：
  `AGREE(3-way)=200, gem5-SKIP=2, DIVERGE=0`；
  `AGREE(4-way)=200, Sail-SKIP=2, SAIL-DIVERGE=0`。
- `manifest_check.py` PASS；
  `check_issues.py` 为 `Open=24 Closed=43 Total=67`，PASS；
  ISA/ABI wiki refs PASS（ISA 3 条既有 UNPARSEABLE warning）；
  wiki drift 3/3 PASS。
- 根仓、QEMU、gem5 三仓 `git diff --check` 均 PASS。

### 组件提交、patch-id 与 bare-pin replay

- QEMU：
  - commit
    `eee0933b064014f3ab305eaa275883f025223d53`；
  - stable patch-id
    `4437ee8119f85eff3535de497321f05603b1d95e`；
  - patch
    `components/qemu/patches/0036-target-dadao-implement-synthetic-K1_EXT0-source-KL-1.patch`；
  - 从 manifest pin tag object
    `385b0a7d9785c8f3ac7b116d7f31d61502b55183`
    （commit `7c949c53e936aa3a658d84ab53bae5cadaa5d59c`）plain
    `git am` **36/36**；
  - dev/replay tree 均为
    `a0b9fc2ce42f17d07809f14f405082132e7db548`。
- gem5：
  - commit
    `c82f1b35fc3aa776520b6fcc1789664935421d89`；
  - stable patch-id
    `36cf671516cc977f7806781315dbed39f30f7804`；
  - patch
    `components/gem5/patches/0029-arch-dadao-implement-synthetic-K1_EXT0-source-KL-137.patch`；
  - 从 manifest pin
    `c8222cc67a399bfc01e8658dd14b30d5bfd634f9` plain
    `git am` **29/29**；
  - dev/replay tree 均为
    `d5663694d6706324d1c4e0be26dcb0c4ed50db3c`。

第一次 replay shell 尝试把 `series` 首行注释误作 patch 路径并立即
失败，尚未应用任何 patch；临时 worktree 由 trap 清理。修正为跳过注释
和空行后，以上两套完整 plain-`git am` replay 一次通过。

### 自审

**结论：PASS。**

- 逐项对照 `contracts/isa/spec.md` §8.5.1/§8.5.4：assert 设置
  private+common、deassert 不清 latch、active-level 与 private-latch
  两层重锁存、private→common ACK、UART0 bit32、最低 cfxcode/cause
  优先级均有双端同构实现及 guest 判别证据。
- schedule 只读取已冻结的 retired-instruction `cycle_lo`，三项配置默认
  inert；未增加 guest 可见 CFX test register。QEMU 的单指令 TB gate
  仅在 schedule enable 时打开，默认路径零影响。
- 两端 `cfx_uart_pending` 的 reset/W0C/read/copy 路径已审计；
  `cfx_uart_exist=1` 为 RO；没有 cg32-63 decode 分支。
- priority probe 用不同 `cause_ip` 证明顺序，lifecycle probe 同时证明
  “mask 只阻塞递交、不阻塞 pending”和“deassert 不等于 ACK”，未把
  双端同值或进程退出码当作充分证据。
- 未修改 KL-139a task MD 或 `gcc-torture-results.json`；按用户本轮明确
  指令不启动 reviewer。

### Non-claim

本任务只声明 FullSystem `DADAOAtomicSimpleCPU` 与 QEMU dadao-m1 的
合成外部中断接受链。明确不声明：UART/串口、PLIC、cg32-63 UART
设备寄存器、真实板级 IRQ wire、UART 驱动、Minor/O3、SE 异步投递、
Linux paging/中断驱动、SBI/HBI 完整固件、多 hart 路由或中断控制器
性能/时序。assert/deassert retirement schedule 也是测试基础设施，不是
架构 ABI。

### 独立 subagent review

**结论：PASS，无阻塞、高、中或低严重度问题。**

- 独立确认双端 `cg8/rc0` W0C、`rc1` RO=1、reset/copy/read/write
  一致，且不存在 `cg32-63` 设备寄存器 decode。
- K1_EXT0 三项配置默认关闭、仅后端可配置，电平切换在 retired-count
  对应的真实指令边界同步；默认关闭负向测试中双端均按 poison 进入
  ILLI，证明未误触发合成源。
- assert/deassert、active-level 重新置私有位、private-latch 重建共有位、
  deassert 不清 latch、private→common ACK 顺序全部通过复核，且不受
  mask 影响。
- 递交完全复用 KL-131a；UART0 bit32、cfx62、`cause_info=0`、
  `cause_ip`、async counter 均正确。priority 探针通过两个不同 poison
  PC 真实证明 cfx18 TIMER 先于 cfx62 UART，而非只检查最终计数。
- reviewer 独立完成专项连续 10/10、最终重编译后复跑、全 K1、E2E
  81/81、三/四方差分 200 零分歧；QEMU 36/36、gem5 29/29 replay
  tree 与开发树一致，patch-id 匹配。
- 文档未过度声明 UART、PLIC 或真实设备；non-claim 保持为真实
  UART/PLIC、cg32-63、板级 IRQ、Minor/O3、SE 异步投递、Linux 驱动、
  多 hart。
