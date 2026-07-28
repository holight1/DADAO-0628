# KL-141a：K2 supervisor cooperative context switch（QEMU + gem5）

**执行者**：DS  
**依赖**：KL-140a（已完成，提交 `a08fdfe`）  
**后续依赖者**：KL-142a～KL-145a

## 背景

KL-140a 已冻结 K2 cooperative frame、COOP_SAVE/COOP_RESTORE
checkpoint、canonical image identity 和双后端 fail-closed oracle。
本任务实现第一个真正的 K2 裸机内核态场景：两个 supervisor kernel task
在同一个 image、同一次运行中反复主动让出和恢复，证明完整 cooperative
context 可以在 QEMU 与 gem5 FullSystem 上正确保存/恢复。

本任务只做 cooperative switch，不实现异步抢占、trap full-context 或
PTBR 地址空间切换；这些分别属于 KL-142a/KL-143a。

## 目标

实现一个可复用的最小 supervisor cooperative switch primitive 和双任务
bare-metal probe，严格使用 KL-140a 冻结的 135-word/1080-byte frame：

- resume PC；
- asid/PTBR metadata；
- rb1 SP、rb2 FP、rb3 GP、rb4 TP；
- rd32～rd63、rb32～rb63；
- 完整 ra0～ra63。

同一份 ROM/RAM image 必须在 QEMU 与 gem5 FullSystem 上运行，guest
fail-closed、host 独立 oracle 和双后端 report 互比三层均通过。

## 实现要求

### 1. supervisor 双任务与切换原语

1. 从现有 hypv→supv handoff/FullSystem carrier 启动，不绕过真实
   supervisor 状态。
2. 至少两个任务 A/B：
   - 使用互不重叠、带 guard/poison 的栈；
   - 使用互不重叠的 cooperative frame；
   - rb2/rb3/rb4 使用任务唯一值；
   - rd32～rd63、rb32～rb63 每槽使用可定位寄存器号和 task id 的唯一
     poison，不得只统一填一个常数。
3. switch primitive 必须按冻结 offset 保存 outgoing frame，再从 incoming
   frame 恢复；可使用 caller-saved RD/RB 作 scratch，但不得偷偷扩大 frame
   或把 callee-saved 状态藏在 host/backend。
4. ra0～ra63 必须通过现行 RA multi-load/store contract 完整保存/恢复。
   因 immu6 最大为 63，ra0～ra62 与 ra63 的边界必须显式处理，不能遗漏
   ra0 或 ra63。
5. 至少完成 **24 次 task transition**（A→B/B→A 交替），不能通过重启
   image、重置 CPU 或 host 代写寄存器来模拟切换。

### 2. RegRAS 必须用真实控制流验收

不能只做内存 round-trip：

- A/B 分别使用不同地址、不同深度的真实 `call` 嵌套链，在链中最深处
  yield；
- task 恢复后必须从自己的 yield continuation 继续，并通过真实 `ret`
  逐层返回到任务专属 continuation；
- 多轮切换中交替建立/拆除调用链，证明另一任务的 RegRAS 没有泄漏；
- guest 对完整 64 槽 save/restore frame 做逐 word 检查，包含
  bits[63:48]，同时由实际 `ret` 落点提供不依赖 frame digest 的控制流
  oracle；
- 至少覆盖一次非零 reference-count 槽或递归压缩；如果现有 call 序列
  无法可靠形成，则在完成区明确说明并把它列为 non-claim，不得伪造。

### 3. frame layout 与 guest 自校验

guest 必须在运行中检查：

- outgoing frame 的每个冻结 offset 都写到正确位置；
- incoming 恢复后 rb1/rb2/rb3/rb4、rd32～63、rb32～63 逐槽与该任务
  期望一致；
- 完整 RA frame 与该任务上一次保存值一致；
- 两个 stack guard、frame guard 和 report guard 未被覆盖；
- 当前任务 id、switch count、A/B 各自进度严格符合预期；
- 任一不符增加 mismatch_count，并最终形成 `final_status=FAIL`，不得只靠
  backend exit code、stdout marker 或双方一致判 PASS。

### 4. KL-140a report/oracle 必须真实接入

1. 直接复用 `tests/scripts/k2_report.py`，不得平行重写 schema/comparator。
2. 正常场景至少记录：
   - INIT；
   - 每次 transition 的 COOP_SAVE(outgoing)；
   - 对应 COOP_RESTORE(incoming)；
   - FINAL。
3. SAVE/RESTORE 必须绑定正确 task、resume/saved PC 和 full-frame digest；
   checkpoint 总数不得超过 64，seq 必须连续。
4. ROM identity slot、RAM report area 与 initial image 必须按 KL-140a
   canonical hash 规则生成并校验；QEMU/gem5 使用字节完全一致的
   ROM/RAM，记录完整 SHA-256 和 canonical identity。
5. host oracle 的 checkpoint 期望、frame poison、PC/任务顺序必须从场景
   常量独立生成，不能从 backend report 反推“期望值”。
6. 必须从两端取得 guest 实际写入的**原始 report bytes**再调用
   `compare_dual_backend()`；不得根据 trace/exit code 在 host 端重建一份
   report。若当前 FullSystem carrier 缺少 report 取回通路，可增加最小
   test-only/default-off transport，但：
   - QEMU/gem5 两端语义必须一致；
   - transport 只搬运指定物理窗口原始字节，不解释 checkpoint；
   - 缺失、截断、重复或越界必须 HARNESS-ERROR；
   - 不得形成 guest-visible 架构 ABI 或真实设备声明；
   - 若修改组件，必须补 patch series、manifest bare-pin replay 与 tree
     hash 证据。

### 5. 正负场景

- **positive**：同一 image 连续至少 10 轮；每轮 24 transitions，QEMU、
  gem5、host oracle、cross-backend compare 全部 PASS。
- **negative mutation**：生成一份独立、双后端字节一致的 mutation image，
  在一次真实 outgoing save 后破坏一个冻结 context word（优先选择
  rd32～63、rb32～63 或 RA 槽），随后继续真实 restore。要求：
  - guest 最终 FAIL 且 mismatch_count 非零；
  - host comparator 返回 FAIL，不能通过修改 oracle 把 guest FAIL 升格；
  - QEMU/gem5 均检出；
  - 恢复正例 image 后重新 PASS。

## 范围与 non-claim

- 单 hart、supervisor kernel task only。
- 本任务可保持 MMU off 或固定 identity mapping；不验证 PTBR/TLB
  address-space switch。
- 不验证异步 timer 抢占、完整 trap frame、user↔supervisor、RF、
  Atomics/SMP、多 hart、真实 UART/PLIC、Linux scheduler/driver API、
  Minor/O3 或性能时序。
- 不得把手写裸机 switch 直接声称为 Linux `__switch_to` 已完成；它只是
  K3 前的架构/ABI 行为 oracle。

## 验收

- positive 双后端 10/10，且每轮确有 24 次 transition。
- guest self-check、host oracle、QEMU↔gem5 report 三层均 PASS。
- negative mutation 双后端均真实 FAIL，恢复后重新 PASS。
- report transport fail-closed；缺 report/坏 magic/截断不能降级为
  exit-code PASS。
- KL-140a self-test 70/70×10、KL-139a 至少 3/3、全量 lit E2E 81/81、
  普通 ISA 三/四方差分 200 零分歧。
- manifest/issues/wiki、Python compile、`git diff --check` 通过。
- 若组件有改动：组件专项构建、patch series bare-pin replay、开发树与
  replay tree hash 一致，组件工作树 clean。
- 不修改或提交无关的 `gcc-torture-results.json`。

## 记录与 review

1. DS 在本文件末尾填写完成区：实现、frame/stack/报告内存图、确切命令、
   pass/skip/fail/non-claim、positive/negative 结果、提交和剩余风险。
2. DS 自审完成后，必须单独新开一个 subagent 做独立 review。reviewer
   必须检查实际 diff、独立运行 positive 和 negative、核对 report 是从
   guest memory 取得，并至少临时破坏一个未被原 mutation 覆盖的关键
   context 字段后恢复。
3. DS 闭环 reviewer blocker/high/medium；review 意见与处理写入本任务
   MD 尾部。
4. 架构师二次 review 通过前不得开始 KL-142a。

## 参考

- `docs/reviews/k2-baremetal-regression-contract-20260728.md`
- `tests/scripts/k2_report.py`
- `code-agent/tasks/KL-139a-k1-k2-integration-probe.md`
- `contracts/abi/spec.md` §1
- `contracts/isa/spec.md` §3.3、§3.4、§4.2、§4.9、§5.6
- `code-agent/tasks/KL-108a-implement-ldmo-ra-stmo-ra-qemu.md`
- `code-agent/tasks/KL-109a-implement-ldmo-ra-stmo-ra-gem5.md`
