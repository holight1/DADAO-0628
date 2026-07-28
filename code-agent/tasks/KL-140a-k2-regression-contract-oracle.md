# KL-140a：K2 裸机内核态回归契约与结构化 oracle

**执行者**：DS  
**依赖**：KL-139a（已完成）  
**后续依赖者**：KL-141a～KL-145a

## 背景

KL-139a 已经用同一 bare-metal ROM/RAM image 在 QEMU 与 gem5
FullSystem 上组合验证 K1 的 MMU、TLB、trap、timer 和合成外部中断链。
K2 接下来要在接触真实 Linux 前，先用裸机内核态程序钉死：

1. cooperative context switch；
2. trap dispatcher 与 preemptive full context；
3. PTBR 地址空间切换与显式 TLB invalidate；
4. timer 驱动的 context/MMU 综合切换。

旧 K0 调研提出扩展单指令 YAML、通用 breakpoint+dump 和测试页表生成器。
当前工程已经具备 FullSystem carrier、页表/image 生成、guest 自校验和双后端
单镜像运行，因此 K2 不再优先建设单指令 privileged YAML 或通用断点调试
设施，而是冻结一套适用于多指令内核流程的结构化 guest report/oracle。

## 目标

冻结 K2 的验证契约，并实现后续任务可以直接复用的最小 host-side
report 编解码与比较基础设施。不得在本任务实现 context switch、调度器、
page-fault policy，亦不得修改 QEMU/gem5 的架构语义。

## 必须冻结的契约

### 1. 上下文类别

文档必须明确区分以下状态所有权，后续任务不得混用：

- **cooperative task context**：
  - resume PC/control state；
  - `rb1` SP、`rb2` FP；
  - `rb3` GP、`rb4` TP：K2 完整任务上下文必须保存/恢复；这不把它们
    外推为普通函数调用 ABI 的 callee-saved 寄存器；
  - `rd32`～`rd63`、`rb32`～`rb63`；
  - 完整 `ra0`～`ra63`，通过现行 `ldmo-ra`/`stmo-ra` contract；
  - 不包含 RF（M1 明确排除）。
- **preemptive trap context**：
  - trap 必须对所有软件可写、可能 live 的 RD/RB 状态透明，不能只保存
    cooperative callee-saved 集合；
  - 明确列出实际保存范围以及 immutable/read-only/reserved 寄存器的处理；
  - 完整 RegRAS；
  - CFX 自动保存的 previous mode/mask/cause/IP 与软件 trap frame 的职责
    分界；
  - 嵌套 E1 时每层 frame 的所有权与恢复顺序。
- **address-space context**：
  - PTBR/root 与 task 的绑定；
  - 切换 PTBR 后必须执行显式 TLB invalidate 才能恢复目标 task；
  - `disable→enable` 是否保留旧 TLB entry 继续保持 non-claim，不能作为
    K2 正确性的前提。

必须写出一次性完整 frame layout，包含字段、宽度、对齐、顺序和总大小；
不得在后续任务中按发现问题逐步扩容。

### 2. 结构化 guest report

定义版本化、定长或可严格界定长度的内存 report，至少含：

- magic、schema version、scenario id、image identity；
- final status（PASS/FAIL/SKIP）和 mismatch count；
- checkpoint count、单调 sequence number；
- event kind、task id、mode/CFX/cause、saved/resume PC；
- context/frame 摘要与关键内存状态摘要；
- PTBR/address-space id、TLB protocol generation；
- 明确的 endian、字段宽度、对齐、容量上限及越界处理。

report 只能增强诊断，**不能代替 guest 内 fail-closed 判定**。正常后端退出、
QEMU/gem5 结果相同或日志 trace 相同，均不能单独构成 PASS。

### 3. 差分与 oracle 口径

K2 privileged 流程的正式口径必须是：

1. QEMU/gem5 使用字节完全一致的 ROM/RAM image，并记录 hash；
2. guest 独立计算 mismatch/final status；
3. host 独立场景 oracle 校验 checkpoint 顺序和关键字段；
4. QEMU、gem5 各自先与 oracle 比较，再互相比较规范化 report；
5. 每类后续场景至少有一个故意破坏 guest 状态或 oracle 期望的负向测试，
   证明判定具有敏感性。

现有 interpreter/Sail 不建模 privileged CFX/MMU 状态。因此现有
`tools/run_differential.py` 的三/四方差分仅作为普通 ISA 零回归门，
不得被表述为 K2 privileged 四方 oracle。

### 4. 范围边界

本轮 K2 首先只覆盖单 hart、supervisor kernel task。以下均保持 non-claim：

- user↔supervisor task switch；
- RF、Atomics/SMP、多 hart；
- 真实 UART/PLIC/device protocol；
- Linux clocksource/clockevent/irqchip API；
- TLB 性能/时序和 gem5 Minor/O3 异步行为；
- Linux paging allocator 或真实 Linux page-fault policy。

K2 可以使用 K1 timer 与 `K1_EXT0` 测试源验证内核软件策略，但不能把它们
外推为真实设备驱动证据。

## 实现交付

1. 新增 K2 契约文档：
   `docs/reviews/k2-baremetal-regression-contract-20260728.md`。
2. 新增一个可由 KL-141a～145a 复用的 Python 模块，位置由现有
   `tests/scripts/` 组织方式决定，提供：
   - schema 常量及字段定义；
   - report 编码/解码；
   - 边界、magic/version、长度、sequence 校验；
   - report 与独立 expected-checkpoint 列表比较；
   - QEMU/gem5 规范化 report 比较；
   - 清楚区分 PASS/FAIL/SKIP/HARNESS-ERROR。
3. 新增本任务自测 runner，至少覆盖：
   - 正常 encode→decode→compare；
   - bad magic/version/length；
   - checkpoint overflow 或截断；
   - sequence/event/task/PTBR 等字段不一致；
   - 双后端 report 一致但同时不符合 oracle 时必须 FAIL；
   - mutation sensitivity：修改一个关键字段后必须从 PASS 变为 FAIL。
4. 更新 `docs/development-roadmap.md`，记录 K2 contract 已冻结的范围、
   non-claim、明确结果和下一任务 KL-141a。
5. 在本任务文件末尾填写完成区、命令、pass/skip/fail/non-claim、变更列表
   和提交信息。

## 验收

- 新模块和自测不依赖某一后端日志字符串才能判断成功。
- 所有失败输入均 fail-closed，不得被当作 SKIP 或普通 PASS。
- 自测连续运行至少 10 轮稳定通过。
- 现有 KL-139a 单镜像集成探针双后端通过。
- 全量 lit E2E、现有三/四方普通 ISA 差分、manifest/issues/wiki 检查无回归。
- 根仓 `git diff --check` 通过；QEMU/gem5 无源码改动且工作树保持 clean。
- 不修改或提交无关的 `gcc-torture-results.json`。

## 工作流与 review

1. DS 直接完成本任务的调研、实现、验证和任务 MD 完成区。
2. DS 完成自审后，必须由 DS **单独新开一个 subagent** 做独立 review；
   reviewer 需要读取实际 diff、独立运行关键自测，并至少实施一次临时
   mutation 后恢复，不能只阅读 DS 的总结。
3. reviewer 意见和 DS 的处理结果写入本任务 MD 尾部。
4. DS 确认独立 review 无未解决 blocker 后再返回架构师。
5. 架构师进行二次 review；二次 review 通过前不得开始 KL-141a。

## 参考

- `docs/adr/0015-kernel-bringup-charter.md`
- `docs/reviews/kernel-bringup-recon-2026-07-18.md` §4、§6
- `docs/reviews/kernel-mmu-interrupt-recon-20260726.md`
- `code-agent/tasks/KL-139a-k1-k2-integration-probe.md`
- `contracts/abi/spec.md` §1
- `contracts/isa/spec.md` §4.9、§5.6、§8
