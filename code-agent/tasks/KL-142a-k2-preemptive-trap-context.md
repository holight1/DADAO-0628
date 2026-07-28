# KL-142a：K2 supervisor 抢占式 trap full-context（QEMU + gem5）

**执行者**：Codex
**依赖**：KL-140a、KL-141a（已完成）
**后续依赖者**：KL-143a～KL-145a

## 背景

KL-140a 已冻结 preemptive trap context 的所有权、栈窗协议、
198-word/0x630-byte frame 和 K2 结构化 report；KL-141a 已证明同一
ROM/RAM image 下 cooperative context 与完整 RegRAS 可在 QEMU/gem5
FullSystem 一致保存恢复。本任务补齐异步 trap dispatcher：timer 可在任意
指令边界打断 supervisor task，软件先无 scratch 保存全部 live 状态，再
执行 handler 主体并严格逆序恢复。

## 目标

实现一份双后端共享的 bare-metal probe，证明：

1. timer 异步 entry 使用 KL-140a 冻结的 198-word frame，保存
   `rd1..rd63`、`rb1..rb63`、`ra0..ra63` 和 cg5 六字段诊断副本；
2. trap prologue 在全部 RD/RB 落栈前不 clobber live scratch，`rb1`
   最后下压；epilogue 恢复顺序为 RA、RD、RB2..63、RB1、立即 escape；
3. handler 可执行真实 call/ret 并污染通用寄存器，而被中断 task 的
   通用状态、RegRAS 与真实返回链保持透明；
4. guest fail-closed、host 独立 oracle、QEMU/gem5 raw report compare
   三层均通过。

## 实现要求

### 1. 抢占现场与真实控制流

- 从现有 hypv→supv handoff 启动，不绕过真实 supervisor/CFX 状态。
- task 在至少三层真实 call 链的最深处解除 timer mask，由 timer 在明确的
  poison 边界异步打断；恢复后 poison 不得执行，并必须经原 call 链真实
  `ret` 到 task continuation。
- entry 前给 `rd1..rd63`、`rb1..rb63` 写入按寄存器号唯一、含非零高
  16 位的 poison；timer entry 的 rd62/rd63 是唯一例外，分别承载
  `MASK_ALL` self-mask 与精确 cause-unmask 值，但仍作为 live context
  原值保存并逐 word 验证；`rb1` 使用带上下 guard 的 resident stack
  window。
- 原 call 链的完整 RegRAS 必须保存到 frame；handler 至少执行一层真实
  call/ret 并显式污染 RA/RD/RB，返回 task 后完整 RegRAS 和逐寄存器状态
  必须与 entry 时一致。

### 2. 冻结 frame/prologue/epilogue

- frame 精确位于 `[old_sp-0x630, old_sp)`，共 198 个 big-endian u64：
  w0..w7 metadata，w8..w70=`rd1..63`，
  w71..w133=`rb1..63`，w134..w197=`ra0..63`。
- prologue 顺序严格遵守 KL-140a §1.2：
  0. timer level/pending relatch 场景先用预装 live RD 执行一条不修改
     RD/RB/RA 的 self-cause mask，防止第一条 store 前同 cfx 重入覆盖 cg5；
  1. 仅用 `sto rdN,rb1,signed12` 保存 rd1..63；
  2. 仅用 `sto rbN,rb1,signed12` 保存 rb1..63，rb1 不变；
  3. 之后才允许用已保存 RD scratch 和两条 `stmo-ra` 保存 ra0..62/ra63；
  4. 复制 cg5 rc0..rc5、owner_cfx、nest_level；
  5. 最后 `rb1 -= 0x630`，之后才能进入 handler body/call。
- epilogue 必须严格逆序：两条 `ldmo-ra` → rd1..63 → rb2..63 →
  rb1 最后 → 紧邻 `escape`。恢复路径不得写 cg5 伪造返回现场。
- guest 必须逐 word 校验完整 frame、cg5 metadata、stack/report guards、
  entry/return 次数和真实 continuation；任一不符使
  `mismatch_count != 0` 且最终 `FAIL`。

### 3. report 与独立 oracle

- 直接复用 `tests/scripts/k2_report.py` 及 KL-141a 已验证的 raw report
  transport，不平行定义 schema。
- 正例记录 INIT、每次成对的 TRAP_ENTER/TRAP_RETURN、FINAL；seq 连续，
  checkpoint 不超过 64。
- checkpoint 钉住 task、timer cause、saved/resume PC、完整 198-word
  frame digest、关键 guest 内存摘要。
- host expected checkpoint 与 frame poison 必须从场景常量独立生成，
  不得读取 backend report 反推期望。
- QEMU/gem5 使用字节完全一致的 ROM/RAM，记录 SHA-256/canonical
  identity；两端均从 guest memory 取得原始 report bytes。

### 4. 正负验收

- positive：同一 image 连续至少 10 轮，QEMU、gem5、host oracle、
  cross-backend 全部 PASS。
- negative：在一次真实 trap save 后破坏一个 full-context word，再执行
  真实 restore；QEMU/gem5 guest 均必须 FAIL、mismatch 非零，host 不得
  将 guest FAIL 升格。恢复正例后重新 PASS。
- 回归：KL-140a self-test、KL-141a、KL-139a、lit E2E、普通 ISA
  differential 按风险比例复跑；`git diff --check` 通过。

## 嵌套 E1

用独立子场景复核 KL-140a 已冻结的跨 CFX 两层 LIFO：

- 外层 frame 在 SP 下压后才允许内层 entry；
- 内层使用新的 `[sp-0x630,sp)` frame，先恢复并 escape；
- 外层随后恢复自己的 frame 并 escape；
- 两层 owner/nest_level、cg5 `prev_cfx_code` 与 report 顺序均由 guest 和
  host oracle 核对。

若 timer 自重入会覆盖同一 cfx cg5，则保持同 cfx recursion non-claim，
不得用它代替跨 CFX E1。

## 范围与 non-claim

- 单 hart、supervisor kernel task；MMU 可关闭或 identity mapping。
- 不验证 PTBR/TLB task switch、user↔supervisor、RF、Atomics/SMP、
  多 hart、真实 UART/PLIC、Linux scheduler/driver API、Minor/O3 或性能。
- 本任务是 K3 前的架构/ABI 行为 oracle，不声称真实 Linux trap entry
  已完成。
- 不修改或提交无关的 `gcc-torture-results.json`。

## 记录与 review

完成后在本文件末尾记录实现、内存图、命令、hash、pass/skip/fail、
non-claim 和剩余风险。主体自审后单独启动 subagent 独立 review；
reviewer 必须检查实际 diff、独立运行正负例，并临时 mutation 一个原负例
之外的关键字段后恢复。所有意见和处理写入本任务 MD。

## 参考

- `docs/reviews/k2-baremetal-regression-contract-20260728.md`
- `tests/scripts/k2_report.py`
- `tests/scripts/run_kl141a_coop_switch.py`
- `tests/scripts/run_kl133a_cfx_timer_probes.py`
- `contracts/isa/spec.md` §5、§8.2、§8.5.2、§8.5.5

---

## 完成区

### 实现与关键设计

- 新增 `tests/scripts/run_kl142a_preemptive_trap.py`：
  - 同一 64 KiB ROM + 2 MiB RAM image 跑 QEMU/gem5 FullSystem；
  - timer 在三层真实 call 链最深处的 UNIMP poison 边界抢占；
  - 外层 timer frame 与内层 PTW E1 frame 均严格为 198 words；
  - guest 逐 word 检查 metadata、rd1..63、rb1..63、ra0..63，handler
    helper 真实 call/ret 并污染 RD/RB；
  - INIT、timer ENTER、PTW ENTER/RETURN、timer RETURN、FINAL 共 6 个
    checkpoint，raw report 经 KL-141a 已验证的 QMP/checkpoint transport
    取回，再调用 KL-140a oracle/comparator。
- 修复 `run_kl141a_coop_switch.py::write_load_patch()` 的潜在 label
  materialization 缺陷：全零 placeholder 的每个 wyde 都是 SETZW，resolved
  非零 label 必须重新按 `load_reg` 规则选择 SETZW/ORW；否则 handler
  `0x101028` 会被截为 `0x1028`。KL-141a 完整正负例回归通过。
- timer private pending 会在 common pending 清除前 relatch；若第一条
  `sto` 前不 self-mask，会立刻同 cfx 重入并覆盖唯一 cg5 frame。契约已
  明确仅允许一条使用预装 live rd62、且不写 RD/RB/RA 的 entry-exclusion
  `cfx2rc`，随后原值仍进入完整 frame；未开放一般 scratch 豁免。
- RB immediate 仅能直接物化 48 位；测试通过 full-u64 RD→`rd2rb`
  建立非零高 16 位 RB poison，避免生成错误的“64 位 RB”测试。

### 内存与事件图

- task stack resident range：`[0x80014000,0x80018000)`；
- outer timer frame：`[0x800179d0,0x80018000)`；
- inner PTW frame：`[0x800173a0,0x800179d0)`；
- outer/inner immutable expected table：
  `0x8001a000` / `0x8001a800`；
- control/MDW：`0x8000f000` / `0x8000f100`；
- report window：`[0x801f0000,0x801f2000)`，canonical report area 与
  identity mirror 沿用 KL-140a/KL-141a。
- E1 顺序：
  `timer ENTER(owner=18,nest=0) → PTW ENTER(owner=4,nest=1,
  prev_cfx=18) → PTW RETURN → timer RETURN`。

### 正负验收

主命令：

```text
python3 tests/scripts/run_kl142a_preemptive_trap.py --rounds 10
```

结果：

- positive：QEMU/gem5 **10/10**，guest/oracle/cross-backend 全 PASS；
- checkpoints：每轮 6/6，seq 连续；
- ROM SHA-256：
  `caaf3c4b45e27be50c3185c8d7052c0192abcb9a5c1cd1ac280c680e1b113188`；
- RAM SHA-256：
  `f75d1989936ea710c20a8542271d1c8947af3f25bccc12d6f93889e081ab582b`；
- canonical identity：`0x9e10c3a63d3b93ee`；
- default negative `rd17`：真实 outer save 后翻转并真实 restore，
  QEMU/gem5 均 `status=FAIL`、`mismatch=UINT64_MAX`，dual verdict 为预期
  FAIL；恢复 positive 后 PASS；
- 额外 sensitivity：`--mutation rb41`、`--mutation ra0` 均在双后端
  形成同样的 guest FAIL，覆盖另一 RB 字段和 RegRAS 边界字段。

### 回归

- KL-140a self-test：**70/70 × 10 PASS**；
- KL-141a：positive、rd40 negative、post-restore 全 PASS；
- KL-139a：QEMU/gem5 **3/3 PASS**；
- lit E2E：**81/81 PASS**；
- differential：
  `AGREE(3-way)=200, gem5-SKIP=2, DIVERGE=0`，
  `AGREE(4-way)=200, Sail-SKIP=2, SAIL-DIVERGE=0`；
- manifest、issues、wiki drift/refs：PASS（wiki refs 保留 3 条既有
  non-blocking UNPARSEABLE warning）；
- Python compile、`git diff --check`：PASS；
- `make check` 的 aggregate 仍在既有 `validate-vectors` coverage 缺口
  停止：ldmo-ra、stmo-ra、cfx2rd、cfx2rc、escape；与本任务 diff 无关，
  分项 required checks 已通过。

### Pass / skip / fail / non-claim

- pass：单 hart supervisor timer 抢占、完整两层 trap frame、所有
  software-writable RD/RB、full RegRAS、真实 call/ret、跨 CFX E1 LIFO、
  双后端 raw-report oracle、三类 mutation fail-closed；
- skip：无；
- fail：无本任务失败；aggregate vector coverage 为既有仓库缺口；
- non-claim：same-CFX recursion、PTBR/TLB task switch、user↔supervisor、
  RF、Atomics/SMP、多 hart、真实 UART/PLIC、Linux trap ABI、Minor/O3、
  性能。

### 独立 review

独立 reviewer：subagent `Anscombe`（2026-07-29）。

结论：**PASS（核心验收通过；无 blocker/high/medium，1 项 low 已关闭）**。

核对结果：

- 198-word/0x630 offset、无 scratch 保存、`rb1` 最后恢复并紧邻
  `escape` 符合冻结契约；
- RA 边界由 `ra0..62` 与独立 `ra63` 两段保存/恢复，覆盖 w134/w197；
- timer self-mask 只在第一条使用预装 live rd62，不修改 RD/RB/RA；
- timer→PTW 在外层 SP 下压后进入，两层 frame 不重叠；PTW
  restore/escape 在前，timer restore/escape 在后，owner/nest/prev_cfx
  和 checkpoint LIFO 一致；
- guest fail-closed、host 静态 oracle、QEMU pmemsave/gem5 checkpoint
  raw transport 与双端比较成立；
- 任务记录没有把已知失败的 aggregate `make check` 误写为 PASS。

reviewer 独立执行：

```text
python3 tests/scripts/run_kl142a_preemptive_trap.py --rounds 1
python3 tests/scripts/run_kl142a_preemptive_trap.py --rounds 1 --mutation rb41
git diff --check
```

两次正例、默认 rd17/rb41 负例和 post-restore 均符合预期；QEMU/gem5
positive raw report SHA-256 相同，mutation raw report SHA-256 亦相同；
ROM/RAM hash 与完成区一致。

唯一 low：本文件原第 3–4 行有 trailing whitespace。已删除，并在文件
纳入 staged diff 后重新执行 `git diff --cached --check` 验证。
