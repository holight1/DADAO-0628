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

## 完成区（2026-07-28）

**状态：PASS（DS 自审、独立 review、架构师二次 review 均已完成；
二次 review 的 3 个 blocker、2 个澄清、1 个 low 已全部闭环，架构师
复审小修与最终证据见文末）。** 没有访问
`~/toolchain` 或 `~/knowledge-graph`，没有触碰
`gcc-torture-results.json`；QEMU/gem5/LLVM 零源码改动。

### 实现

1. 契约文档 `docs/reviews/k2-baremetal-regression-contract-20260728.md`：
   - §1 三类上下文所有权：cooperative task context（含 rb3/rb4 仅作任务
     上下文保存、不外推为 ABI callee-saved 的限定；完整 ra0-63 经现行
     `ldmo-ra`/`stmo-ra` contract；RF 排除）、preemptive trap context
     （rd1-63/rb1-63/ra0-63 全量透明保存；rd0/rb0/RF 的不保存处理；
     硬件 cg5 frame 与软件 frame 的职责分界；嵌套 E1 每层所有权与 LIFO
     恢复顺序；同 cfx 递归与多层 escape shortcut 保持 non-claim）、
     address-space context（PTBR/asid 绑定落点、切换必须先显式 TLB
     invalidate、TLB protocol generation、disable→enable non-claim）。
   - §2 一次性完整 frame layout：cooperative frame 135 word/1080 字节、
     trap frame 198 word/1584 字节，逐字段 offset/宽度/对齐/顺序/总大小；
     后续任务不得扩容。
   - §3 结构化 guest report：9 word header（magic `DDAOK2RP`、
     schema_version=1、scenario_id、规范化 image_identity、
     final_status、mismatch_count、checkpoint_count、flags、
     capacity）+ 11 word checkpoint（seq/event/task/mode_cfx/cause/
     saved+resume PC/context+memory digest/ptbr_asid/tlb_gen），全部
     u64 big-endian，容量 64 条、上界 5704 字节，越界 drop+flag；word
     级 FNV-1a-64 digest；PASS/FAIL/SKIP/HARNESS-ERROR 判定词汇，全部
     非 PASS 输入 fail-closed。
   - §4 差分与 oracle 五步正式口径 + "report 不代替 guest 内
     fail-closed 判定" + `run_differential.py` 仅作普通 ISA 零回归门
     的定位声明。
   - §1.4/§6 non-claim 汇总与 KL-141a～145a 挂钩表。
2. 可复用模块 `tests/scripts/k2_report.py`（沿用 tests/scripts 扁平
   组织 + `sys.path.insert(0, HERE)` 互导入惯例）：schema 常量、
   `fnv1a64`、`image_identity`、`encode_report`/`decode_report`
   （结构问题抛 `ReportStructureError`→HARNESS-ERROR）、
   `validate_sequence`/`validate_content`（→FAIL）、
   `compare_with_oracle`（wildcard 字段支持）、
   `compare_backend_reports`/`compare_dual_backend`（先各自对 oracle、
   再互相比；HARNESS-ERROR > FAIL > SKIP > PASS）、`Verdict` 四值。
3. 自测 runner `tests/scripts/run_kl140a_k2_report_selftest.py`：70 项
   检查/轮（修复轮后计数），纯 host-side、不启动后端、不读任何日志
   字符串。
4. `docs/development-roadmap.md` 追加 KL-140a 条目（冻结范围、
   non-claim、结果、下一任务 KL-141a）。

### 命令与结果

- `python3 tests/scripts/run_kl140a_k2_report_selftest.py --rounds 10`
  → **70/70 × 10 轮稳定 PASS**（架构师复审小修后计数，见文末）。
  覆盖：正常 encode→decode→compare；
  bad magic/version/capacity/count/截断/拖尾→HARNESS-ERROR；
  image identity 不符→HARNESS-ERROR；seq gap/重排、event/task/
  run_mode/cfx/cause/saved+resume PC/context+memory digest/asid/ptbr/
  tlb_gen 13 项单字段 mutation 全部 PASS→FAIL；scenario_id/status/
  mismatch/flags/MBZ/未知枚举/超 48 位 PC→FAIL；双后端一致但违反
  oracle→FAIL（两端理由均带标签）；oracle wildcard 字段双后端不一致
  →仅 cross-compare 捕获 FAIL；容量满+overflow flag 在显式期望下
  PASS、默认期望下 FAIL；guest FAIL 永不升格；运行前预声明
  SKIP 不掩盖另一端失败，且单端 PASS 不外推为双后端 PASS。
- 回归：
  - `python3 tests/scripts/run_kl139a_k1_k2_integration.py --rounds 3`
    → QEMU/gem5 均 139，**3/3**；
  - `.work/build/llvm/bin/llvm-lit -sv tests/lit/E2E/` → **81/81**；
  - `python3 tools/run_differential.py` → AGREE(3-way)=200、
    gem5-SKIP=2、DIVERGE=0；AGREE(4-way)=200、Sail-SKIP=2、
    SAIL-DIVERGE=0（与 KL-139a 完成区基线一致）；
  - `scripts/manifest_check.py` PASS；`check_issues.py` Open=24
    Closed=43 Total=67 PASS；`check_wiki_refs.py` ISA PASS（仅 3 条
    既有 UNPARSEABLE warning）、ABI PASS；`check_wiki_drift.py`
    3/3 PASS；
  - 根仓 `git diff --check` PASS；`.work/source/qemu` 与
    `~/DADAO-gem5` 工作树 clean、`diff --check` PASS（零组件改动）。

### pass/skip/fail/non-claim

- pass：契约冻结（§1 三类上下文/§2 layout/§3 report/§4 口径）；
  `k2_report.py` 编解码+校验+oracle/双后端比较；自测 70 项 ×10 轮；
  上述全部回归项。
- skip：无。
- fail：无。
- non-claim：user↔supervisor task switch；RF、Atomics/SMP、多 hart；
  真实 UART/PLIC/device 协议（K1 timer/K1_EXT0 仅作软件策略验证源）；
  Linux clocksource/clockevent/irqchip API；TLB 性能/时序与 gem5
  Minor/O3 异步行为；Linux paging allocator 与真实 page-fault policy；
  同 cfx 递归重入与多层 escape shortcut；report 检索的宿主机制
  （KL-141a 起按场景落地，本任务只冻结格式与读取时序规则）。

### 变更列表

- 新增 `docs/reviews/k2-baremetal-regression-contract-20260728.md`
- 新增 `tests/scripts/k2_report.py`
- 新增 `tests/scripts/run_kl140a_k2_report_selftest.py`
- 修改 `docs/development-roadmap.md`（文末追加 KL-140a 条目）
- 修改本任务文件（完成区与 review 记录）

### 提交信息（建议）

`KL-140a: freeze K2 bare-metal regression contract + structured report oracle`

### 自审

**结论：PASS。**

- 契约四项"必须冻结"逐条核对：上下文类别（含 rb3/rb4 限定、trap 透明
  性范围、immutable/read-only/reserved 处理、E1 嵌套所有权）、一次性
  frame layout（offset 表经算术复核：1080=0x438、1584=0x630，与
  word 数一致）、report 必备字段八项全在 §3.2/§3.3、差分口径五步全在
  §4；non-claim 清单与任务书 §4 逐项对应。
- 模块常量与契约逐字一致（magic/version/72/88/64/5704），自测常量
  断言钉死；digest 实现对齐公开 FNV-1a-64 测试向量。
- 所有失败路径 fail-closed：结构错误→HARNESS-ERROR、内容错误→FAIL、
  双后端一致不能挽救 oracle 违反、oracle wildcard 不能挽救双后端分歧、
  SKIP 只能预声明。自测不依赖任何后端日志字符串。
- `make check` 在 validate-vectors 处对 5 条特权指令（ldmo-ra/
  stmo-ra/cfx2rd/cfx2rc/escape）报 COVERAGE MISSING；已核实为**既有
  状态**（git 跟踪文件零修改，HEAD 上即失败，源于 KL-114a 起这些
  指令无单指令 YAML 向量，正是本契约 §0 所述不优先建设单指令
  privileged YAML 的背景），不在本任务验收口径（lit E2E/差分/
  manifest/issues/wiki 全部 PASS）内，如实记录未修复。
- 未触碰 `gcc-torture-results.json`（保持 untracked 原状）；组件树
  无改动；根仓未提交（按既定规则等待架构师指令）。

### 独立 subagent review（2026-07-28）

**结论：PASS，无 blocker/high/medium finding；2 条 low。**

reviewer 独立执行（非阅读总结）：

- 逐条核对任务书 §1-§4 与契约文档：三类上下文所有权、frame layout
  offset 表（亲手核算 135 word=0x438=1080B、198 word=0x630=1584B
  自洽）、report 八类必备字段、endian/对齐/容量/越界、判定词汇、
  差分五步口径、`run_differential.py` 定位声明、non-claim 清单——
  全部在案且与 `contracts/abi/spec.md` §1、`contracts/isa/spec.md`
  §4.9/§8.5.5 的术语机制吻合。
- 模块常量与契约逐字一致；FNV 实现钉在公开 FNV-1a-64 测试向量上；
  verdict 分类逻辑实证（结构→HARNESS-ERROR、内容→FAIL、SKIP 仅
  预声明、双后端先各自对 oracle 再互比、HARNESS>FAIL>SKIP>PASS）。
- 独立复跑：自测 60/60×10（review 于 one-hot 修复前执行）；
  lit E2E 81/81；KL-139a 双端 139（1 轮）；差分 AGREE(3-way)=200/
  DIVERGE=0、AGREE(4-way)=200/SAIL-DIVERGE=0；manifest/issues/
  wiki ISA/ABI/drift 全 PASS；根仓 `diff --check` PASS；QEMU/gem5
  工作树 clean；`gcc-torture-results.json` 保持 untracked 原状。
- 三次临时 mutation 均检出并恢复（备份-恢复-diff 验证，结束时
  `git status` 与基线一致）：`MAX_CHECKPOINTS` 64→63 被 2 项检查
  检出；image-identity 分类 HARNESS→FAIL 被检出；oracle 侧
  tlb_gen 期望 0→1 被 3 处翻转检出。
- 额外边界探针：count=0 空 report、恰好 64 条 5704B roundtrip、
  encode 65 条 ValueError/decode HARNESS-ERROR、HARNESS+SKIP→
  HARNESS-ERROR、SKIP+SKIP→SKIP、全 wildcard oracle 不退化
  （content/seq/status/count 仍强制）。

**Findings 与 DS 处理**：

1. [low] `validate_content` 未校验 `cause` one-hot（契约 §3.3 w4 已
   定义为"one-hot；无则为 0"）。**已修复**：`k2_report.py` 增加
   `cause & (cause-1)` 内容校验（→FAIL）；自测新增 "cause not
   one-hot" 用例（打在 oracle wildcard cause 的 checkpoint[1] 上，
   精确隔离该路径）。修复后自测 **61/61 × 10 轮 PASS**，并复核
   lit E2E 81/81 无回归。
2. [low] `task_id` 无范围约束。**不修复（设计意图）**：任务 id 空间
   由场景定义，契约有意留白；canonical oracle 已示范显式钉住
   task_id，KL-141a～145a 的 oracle 同样必须逐 checkpoint 钉死。

**DS 复核结论**：无未解决 blocker；reviewer 对契约文档、模块、自测、
roadmap 条目、完成区声称的逐项判定均为"准确/属实"。lit E2E 在
one-hot 修复后复跑仍为 81/81（模块/自测为纯 host-side 新文件，
不影响后端）。

### 架构师二次 review（2026-07-28）

**结论：NEEDS-FIX。** KL-140a 暂不提交，KL-141a 暂不放行。DS 与其
独立 reviewer 的常规回归结果可以复现，但新 oracle 契约存在以下三个
blocker 和两个冻结前必须澄清的问题。

#### Blocker

1. **guest FAIL 可被 oracle 升格成 PASS，违反 fail-closed。**
   `ScenarioOracle.expected_status/expected_mismatch_count` 允许把
   `final_status=FAIL,mismatch_count=3` 配成预期值，
   `compare_with_oracle()` 随后返回 `Verdict.PASS`；自测
   `negative scenario expected` 还把该行为钉成了成功。任务合同和契约
   §3.5/§4 明确规定 PASS 必须要求 guest `final_status=PASS` 且
   `mismatch_count=0`，任何 guest FAIL 均不得升格。负向 mutation 的
   meta-test 应当断言 comparator 返回 FAIL/HARNESS-ERROR，而不是修改
   oracle 后让失败 report 返回 PASS。
2. **SKIP 会覆盖已经观察到的失败。**
   `compare_with_oracle()` 在任何内容校验前直接处理 `oracle.skip`；
   因而实际传入一个 `final_status=FAIL,mismatch_count>0` 的可信 report
   仍返回 SKIP。契约要求 SKIP 只能是运行前、逐后端声明，且事后失败
   不得重标。应把 skip 建模移到运行调度层：被预声明 skip 的后端不运行、
   不产生 report；一旦获得 report 就必须正常 fail-closed 校验。双后端
   API 还需区分每个 backend 的 skip，不能用一个全局 bool 同时覆盖两端。
3. **`image_identity` 定义自引用，真实 image 无法按当前文字生成。**
   契约定义 identity 为 `SHA-256(ROM || RAM)` 前 8 字节，同时要求把
   identity 嵌入 image 供 guest 拷贝；嵌入动作会改变 ROM/RAM 字节，
   使最终 image 的 hash 不再等于嵌入值。当前 host self-test 没有把
   identity 实际嵌入 ROM/RAM，因此没有覆盖此问题。必须冻结可实现的
   canonical hash，例如：计算时把 image 中专门的 identity slot 和
   writable report 区规范化为全零，并让 host/guest/image generator
   使用同一规则；同时新增真实嵌入后的正反自测。

复现结果：

```text
expected-FAIL comparator: PASS
failing-report with skip: SKIP
embedded_identity=67895cbc5906fac8
actual_image_identity=2143414b4ebf363e
equal=False
```

#### 冻结前必须澄清

1. **trap frame 首段保存流程尚未证明可实现。** 契约一方面要求
   rd1-63/rb1-63 全部视为 live，另一方面规定“handler prologue 第一动作”
   把 cg5 复制到静态 per-cfx frame；但读取 cg5、取得静态 frame 地址都
   需要先使用并覆盖一个 RD/RB scratch。建议冻结成基于当前 `rb1` 的
   downward trap-stack frame：先用 signed-12 store 将全部 live RD/RB
   保存到 `old_sp-0x630` 范围，再保存 RegRAS、更新 SP、读取 cg5；并要求
   该栈区 resident/aligned、保存窗口不可重入。若坚持静态 frame，则必须
   明确定义一个不属于 live context 的专用 trap scratch 入口机制。
2. **cooperative switch checkpoint 的 source/target 所有权不清。**
   当前 `task_id` 被定义为即将运行的 target，`saved_pc` 却属于 outgoing
   source，`context_digest` 示例又取 target frame；单条记录不能明确证明
   outgoing frame 已正确保存且 incoming frame 已正确恢复。应冻结为两个
   checkpoint（SAVE/RESTORE，各自绑定 task/frame），或给 schema 增加明确
   的 source/target 与双 digest 表达，不能留给 KL-141a 临时解释。

另有一处 low 文档不一致：`scenario_id` 文字示例写 `KL-141a`（7 字节），
实际十六进制和自测编码的是去掉连字符的 `KL141a`（6 字节）；需统一并加
编码 helper/self-test。

#### 二次 review 实测

- `run_kl140a_k2_report_selftest.py --rounds 10`：61/61 × 10 PASS，
  但包含上述把预期 guest FAIL 升格为 PASS 的错误断言，故不能作为最终
  放行证据。
- KL-139a 双后端共享 image：QEMU=139、gem5=139，1/1 PASS。
- manifest、issues、wiki drift、ISA/ABI wiki refs、`git diff --check`
  均 PASS；QEMU/gem5 工作树 clean。
- 未触碰无关 `gcc-torture-results.json`。

### DS 修复轮（2026-07-28，响应架构师二次 review）

三个 blocker、两个澄清、一个 low 全部响应完毕；改动只涉及契约文档、
`k2_report.py`、自测与 roadmap/任务文件，组件树零改动。

#### Blocker 1（guest FAIL 升格 PASS）——已修复

- `ScenarioOracle` 删除 `expected_status`/`expected_mismatch_count`
  字段（不再存在豁免配置）；`compare_with_oracle()` 把
  `final_status==PASS`、`mismatch_count==0` 实现为硬条件，任何 guest
  FAIL/NONE/非零 mismatch 一律 FAIL，并在理由中注明"§3.5 hard
  condition, no upgrade"。
- 自测删除原 `negative scenario expected`/`negative scenario
  mismatched count` 两个错误用例，新增 `guest fail never upgraded`
  （final_status=FAIL+mismatch=3、checkpoint 全部符合 oracle → 仍
  FAIL）。
- 契约 §3.5 PASS 条目写明"硬条件，oracle 不提供任何豁免配置"；§4.5
  写明负向测试的宿主侧断言必须是 comparator 返回 FAIL/HARNESS-ERROR，
  不得改 oracle 期望使失败 report 返回 PASS。

#### Blocker 2（SKIP 覆盖已观察失败）——已修复

- `ScenarioOracle` 删除 `skip`/`skip_reason`；`compare_with_oracle()`
  永不返回 SKIP，任何已产生的 report 一律完整 fail-closed 校验。
- skip 建模移至运行调度层：`compare_dual_backend()` 的
  `qemu_bytes`/`gem5_bytes` 接受 `None`（该端预声明 skip：不运行、
  无 report），逐后端独立；verdict 优先级
  HARNESS-ERROR > FAIL > PASS > SKIP，SKIP 仅在两端均未运行时成立；
  一端 skip 时以运行端的 oracle 比较为结论，无互比。
- 自测新增 4 项：两端 skip→SKIP；一端 skip+一端 PASS→PASS；
  skip 不掩盖另一端 FAIL；skip 不掩盖另一端 HARNESS-ERROR。
- 契约 §3.5 SKIP 条目重写为调度层语义；§4.4 补"任一端可预声明
  skip，只有一端运行时以该端 oracle 比较为结论"。

#### Blocker 3（image_identity 自引用）——已修复

- `image_identity()` 增加 `rom_identity_slot`/`ram_report_area` 规范化
  参数：hash 前把 ROM identity slot 与 RAM report 区置零；新增
  `embed_image_identity()`（先算后写回 slot 生成最终 ROM）。
- 自测 ROM/RAM fixture 真实执行"规范化→计算→嵌入"全流程并覆盖：
  嵌入后重算不变（正）；朴素整 image hash ≠ 规范化 hash（证明自引用
  真实存在且被消除）；slot 外篡改被检出；slot 内任意内容被规范化
  吸收；report 区写入不改变 identity；report 区外 RAM 篡改被检出。
- 契约 §3.2 w3 重写为规范化定义；§4.1 host 记录口径同步为规范化
  SHA-256。

#### 澄清 1（trap frame 首段保存可实现性）——已冻结 trap-stack 方案

采纳架构师建议，契约 §1.2 重写并新增"prologue 保存序列"与"栈窗协议"
两段，§2.2 落点改为当前栈 `[old_sp-0x630, old_sp)`：

- prologue 顺序：rb1 基址 signed-12 字节偏移 `sto` 存 rd1-63 → 同法
  存 rb1-63（`sto rb1, rb1, imm` 基址不变）→ 用已保存 rd 作 scratch
  两条 `stmo-ra` 存 ra0-62/ra63 → `cfx2rd` 读 cg5 六字段写 frame 头 →
  最后更新 rb1。已按 `contracts/isa/spec.md` §3.2/§4.1 核实 EA=
  `rb+sext_12(imm)`（±2048 字节，0x630=1584 在范围内）、§4.9
  stmo-ra EA 与 immu6≤63 限制，序列无需任何未保存 scratch。
- 栈窗协议：trap 可到达的任意时刻 `[rb1-0x630, rb1)` 必须 writable/
  resident/8 字节对齐；第 5 步前不得解除异步 mask、不得执行窗口外
  可能 fault 的访存（窗口不可重入）；嵌套 entry 只能发生在 SP 更新
  之后，天然 LIFO。恢复严格逆序、rb1 最后、立即 escape。
- 原"静态 per-cfx slot"表述全部移除；同 cfx 递归保持 non-claim。

#### 澄清 2（cooperative switch 记录所有权）——已冻结双 checkpoint

- `event_kind` 重编号：1=INIT、2=COOP_SAVE、3=COOP_RESTORE、
  4=TRAP_ENTER、5=TRAP_RETURN、6=AS_SWITCH、7=TIMER、8=FINAL（模块
  与契约 §3.3 同步；schema_version 保持 1——KL-141a 尚未开始，无
  既有消费者）。
- COOP_SAVE 绑定 outgoing：saved_pc=写入 outgoing frame 的
  resume_pc、context_digest=保存后 outgoing frame；COOP_RESTORE 绑定
  incoming：resume_pc=实际恢复 PC、context_digest=恢复前核对的
  incoming frame。契约 §3.3 明确二者 seq 相邻（允许间隔 AS_SWITCH）、
  oracle 必须成对钉住；§6 KL-141a 挂钩同步更新。
- 自测 canonical 序列改为 10 条 checkpoint（两对 SAVE/RESTORE）。

#### low（scenario_id 文字不一致）——已统一

契约示例改为"去连字符的 6 字节 ASCII（KL-141a → "KL141a"）"；模块
新增 `scenario_id_for()` helper；自测断言
`scenario_id_for("KL140a") == 0x4B4C313430610000`。

#### 修复轮复测

- `run_kl140a_k2_report_selftest.py --rounds 10`：**68/68 × 10 PASS**
  （修复轮首轮暴露 1 个自测自身错误——RAM 篡改偏移落在 report 区内
  部，修正为区外 7000 后全绿）。
- lit E2E：**81/81**；KL-139a 双后端 139（1/1）；差分
  AGREE(3-way)=200/DIVERGE=0、AGREE(4-way)=200/SAIL-DIVERGE=0；
  manifest/issues/wiki ISA/ABI/drift 全 PASS；根仓
  `git diff --check` PASS；QEMU/gem5 工作树 clean。
- roadmap KL-140a 条目已同步（68 项计数、栈窗 prologue、双
  checkpoint、三项硬化说明）。
- 仍未触碰 `gcc-torture-results.json`；根仓未提交（等架构师复核）。

### 架构师最终复审与小修（2026-07-28）

**结论：PASS，KL-141a 可放行。**

上轮三个 blocker 均已通过代码与负向复现关闭：

- guest `final_status=FAIL,mismatch_count=3` 始终得到 FAIL；
- SKIP 只在运行调度层以无 report 表达，不再覆盖已产生的失败 report；
- image identity 使用 ROM identity slot + RAM report area 归零后的
  canonical hash，真实嵌入后重算稳定，slot/report 区外篡改可检出。

trap frame 已冻结为 `rb1` 相对的 0x630-byte downward resident stack
window；保存 RD/RB 后再使用 scratch 保存 RegRAS 与复制 cg5，恢复时 rb1
最后恢复，保存序列在现行 signed-12 store 和 `stmo-ra` 限制内可实现。
cooperative switch 使用成对 COOP_SAVE/COOP_RESTORE checkpoint，分别
绑定 outgoing/incoming frame，source/target 所有权已明确。

架构师直接修复两个小问题：

1. K2 是双后端 gate，一端预声明 SKIP 时即使另一端 PASS，场景也保持
   SKIP，不能把单端证据外推为双后端 PASS；
2. `scenario_id_for()` 严格接受冻结的六字节 `KLnnna` 格式，拒绝带
   连字符或长度错误的 tag。

最终实测：

- KL-140a self-test：**70/70 × 10 PASS**；
- fail-closed 定向复现：guest FAIL→FAIL、单端 PASS+另一端 SKIP→SKIP、
  双端 PASS→PASS；
- KL-139a：QEMU/gem5 **3/3**；
- lit E2E：**81/81**；
- differential：AGREE(3-way)=200、AGREE(4-way)=200、DIVERGE=0、
  SAIL-DIVERGE=0；
- manifest/issues/wiki drift/ISA refs/ABI refs、Python compile、
  `git diff --check` 全部 PASS；
- QEMU/gem5 工作树 clean，组件源码零改动；
- 无关 `gcc-torture-results.json` 保持 untracked。
