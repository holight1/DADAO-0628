# KL-141a：K2 supervisor cooperative context switch（QEMU + gem5）

**执行者**：DS（未完成）→ Codex 接手
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

---

## 完成区（Codex 接手，2026-07-29）

### 接手审计与修复

DS 留下了两个未纳入版本控制的脚本，但首轮实际执行为
QEMU 启动后 RASUF、gem5 无 doorbell，不能形成任何 K2 证据。接手后按
guest 控制流、report transport、host oracle 三层逐项定位并修复：

1. 初始 frame/table 原先放在 ROM，再由 supervisor 数据 load 读取；当前
   FullSystem carrier 下两端均读到零，第一次 bootstrap `ret` 因空
   RegRAS 触发 RASUF。最终把初始 frame 和只读参考 table 放进同一份
   canonical RAM image，ROM 仍保留 canonical identity slot。
2. QEMU QMP transport 原先生成未加引号的 `pmemsave /tmp/...` 命令；
   HMP 实际返回解析错误，脚本又忽略了非空返回。最终对文件名加引号并把
   非空 HMP 返回强制归为 HARNESS-ERROR。
3. report cursor 原先从 header 起点写 checkpoint，FINAL header 会覆盖
   第一条记录；现从 `REPORT_PA + 72` 开始。
4. B leaf continuation 原先重复执行 B_M7 的 marker/stack cleanup，导致
   rb1 每轮漂移；现由真实 owning caller B_M7 唯一清理。
5. RESTORE 曾同时在 switch primitive 和 task continuation 记录，超过
   64-entry 上限并覆盖 report canonical 区；现统一在 `SW_RESTORE`
   恢复前记录一次。
6. host oracle 修正 outgoing-save 时的 pre-increment switch count、首次
   B initial restore，以及 A yield 时 B 尚未 unwind 的 progress 时序；
   期望仍完全从场景常量生成，不读取 backend report 反推。
7. 场景暴露 gem5 `rb2rd`/`rb2rb` 仍按旧逻辑截断 RB bits[63:48]，与
   `contracts/isa/spec.md` §4.7 的 full-64-bit copy 和 QEMU 行为冲突。
   未降低 poison 强度规避，而是在 gem5 做了最窄修复并保留非零 RB 高位
   的双后端验收。

### 实现与内存图

- `tests/scripts/run_kl141a_coop_switch.py`
  - 同一 64 KiB ROM + 2 MiB RAM image；
  - 25 次真实 transition（A 13 次 outgoing，B 12 次 outgoing）；
  - A 为三层 call + 两次同址递归压缩，保存 frame 中实际出现
    refcount=2；B 为七层不同地址 call chain；
  - 每次 switch 保存/恢复冻结的 135 words：metadata、rb1-rb4、
    rd32-rd63、rb32-rb63、ra0-ra62 + ra63 边界；
  - INIT + 25 SAVE + 25 RESTORE + FINAL = 52 个连续 checkpoint；
  - guest mismatch fail-closed、独立 host oracle、QEMU↔gem5 raw report
    compare。
- `tests/scripts/k2_fs_report.py`
  - gem5 FullSystem test-only transport；按 tick chunk checkpoint 物理
    RAM，host 只复制 report window 原始字节，不解释 guest checkpoint。
- 关键 RAM：
  - control/MDW：`0x8000f000` / `0x8000f100`；
  - A stack：`[0x80010000,0x80012000)`，B stack：
    `[0x80014000,0x80016000)`，两端均有 guard；
  - A/B frame：`0x80018000` / `0x80019000`，各 1080 bytes，独立 guard；
  - immutable expected tables：`0x8001a000` 起，stride `0x800`；
  - report window：`[0x801f0000,0x801f2000)`，doorbell
    `0x801f1ff8`。
- canonical identity：
  - ROM slot：offset `0xfff8`（物理 `0x10fff8`）；
  - RAM report canonical 排除区保持 KL-140a 的 5704 bytes；
  - guest-readable mirror 位于该排除区尾部 `0x801f1640`，不改变
    canonical hash，也不形成设备/架构 ABI。

### 正负验收

命令：

```text
python3 tests/scripts/run_kl141a_coop_switch.py --rounds 10
```

结果：

- positive：QEMU 10/10、gem5 10/10、host oracle 10/10、
  cross-backend 10/10；每轮 25 transitions、52 checkpoints；
- ROM SHA-256：
  `c93ca40c6f141e2ea50bf3427a34816148dd8069b837a2f75de6287f3f93fb21`；
- RAM SHA-256：
  `994004a021ad01a6481528c36a07b7a64f5127eca9f896494b47c8ea40b3e2f6`；
- canonical identity：`0xa705d27268b062fb`；
- negative：transition 7 的真实 SAVE 后破坏 A frame 的 rd40 word，
  QEMU/gem5 均为 `status=FAIL, mismatch_count=UINT64_MAX`，dual verdict
  为预期 FAIL；
- 恢复 positive image 后再次 PASS。

raw report 位于 `.work/evidence/kl141a-coop/report-*.bin`，由 QEMU QMP
`pmemsave` 和 gem5 physical-memory checkpoint 直接取得。guest 先写
doorbell 再 architectural halt；QEMU `-no-shutdown` 等到
`query-status=shutdown` 后只读一次，gem5 在 terminal event 后只生成一次
checkpoint。stdout、正常退出码和 trace 不参与 PASS verdict；异常退出和
超时直接 HARNESS-ERROR。

### gem5 组件修复与 replay

- commit：
  `eede9a05d03edbe8c51ea408aaf1deac27c5ff72`；
- stable patch-id：
  `562eb22bf2ee524d6fccda72bbdac15fd20ebc85`；
- patch：
  `components/gem5/patches/0030-arch-dadao-preserve-RB-high-bits-in-block-copies.patch`；
- `scons build/DADAO/gem5.opt -j4`：PASS；
- binary SHA-256：
  `d7189e042aa37ef4923e21b12cb14f9d444713b81216f0758e76c2ec272b5443`；
- 从 manifest pin
  `c8222cc67a399bfc01e8658dd14b30d5bfd634f9` plain `git am`：
  30/30 PASS；
- development/replay tree：
  `eec7176b2a62c0494af62cc887316a398e28b81a`（一致）；
- gem5 component 工作树 clean。QEMU 无组件修改。

### 回归

- `run_kl140a_k2_report_selftest.py --rounds 10`：
  **70/70 × 10 PASS**；
- `run_kl139a_k1_k2_integration.py --rounds 3`：
  QEMU/gem5 **3/3**；
- `llvm-lit -sv tests/lit/E2E/`：**81/81 PASS**；
- `tools/run_differential.py`：
  `AGREE(3-way)=200, gem5-SKIP=2, DIVERGE=0`；
  `AGREE(4-way)=200, Sail-SKIP=2, SAIL-DIVERGE=0`；
- manifest、issues、wiki refs（3 条既有 warning）、wiki drift：PASS；
- Python compile、根仓/组件 `git diff --check`：PASS。

### Pass / skip / fail / non-claim

- pass：单 hart supervisor cooperative task switch、完整冻结 frame、
  full RegRAS、真实 call/ret 与 refcount=2、25 transitions、双后端
  raw-report oracle、负变异 fail-closed；
- skip：无；
- fail：无；
- non-claim：异步抢占、完整 trap frame、PTBR/TLB address-space switch、
  user↔supervisor、RF、Atomics/SMP、多 hart、真实 UART/PLIC、Linux
  scheduler/driver API、Minor/O3、性能。

独立 subagent review 与额外关键字段 mutation 记录见下方 review 区。

### 独立 review R1 与闭环

独立 reviewer 首轮判定 NEEDS-FIX，并实际确认 positive、默认 rd40
negative/post-restore、额外 `rb40@t9` negative 均满足预期；额外 rb40
变异在 QEMU/gem5 均为 guest FAIL、mismatch 非零、dual FAIL。它同时提出：

- **Blocker**：host 未重算实跑文件 identity；修改不可达 ROM padding
  仍可沿用旧 embedded/mirror/oracle identity 而 PASS；
- **High**：guest FINAL 未检查最终 progress/switch/restore/bitmap/seq；
  A/B progress 同时提前可在 3 transitions 后写死 52 count，guest 自身
  仍 PASS，只有 host oracle 失败；
- **Medium**：旧 transport 边运行边轮询 report，且异常退出检查不足，
  不符合 KL-140a“guest 终止后读取”的冻结规则。

闭环：

1. `verify_run_image()` 在任一 backend 启动前读取确切 ROM/RAM，重算
   canonical identity，并同时核对 ROM slot、RAM mirror、oracle。
   临时翻转不可达 ROM offset `0x7000` 后得到
   `HARNESS-ERROR`，computed identity 与另外三者不同，且两个 backend
   均未运行。
2. FINAL 在形成 status 前逐项检查 current task、A/B progress、
   switch count、A/B done、A/B restore count、A/B bitmap 和实际 seq；
   header count 改为 guest 实际 seq，不再写死 52。以
   `initial_progress=11` 构造提前结束 image 后，两端均
   `status=FAIL, mismatch=0x3f, checkpoint_count=8`，dual FAIL。
3. guest doorbell 后执行 architectural halt；QEMU 使用
   `-no-shutdown`，仅在 QMP `shutdown` 后 `pmemsave`；gem5 仅在 terminal
   event 后 checkpoint。backend 提前退出、非零退出和超时均
   HARNESS-ERROR。

R1 修复后的 positive 重新执行 10/10，默认 negative 与 post-restore
继续通过。独立 reviewer 复审结论见下方 R2。

### 独立 review R2 / R3 最终结论

R2 独立复核确认 identity drift 和 early-progress 两项闭环，也实测正常
terminal 顺序为 QEMU `query-status=shutdown → pmemsave → quit`，gem5
`halt → 唯一 checkpoint`。R2 仅剩一个 Medium：QMP `readline()` 缺少
socket timeout，且 gem5 尚未拒绝非 `halt` terminal cause。

最终修复：

- QMP connect 后设置最长 5 秒的 socket timeout；greeting 和所有
  roundtrip 的 `OSError/TimeoutError` 统一转成 `TransportError`；
- gem5 只有 `terminal_cause == "halt"` 才生成 checkpoint；其他异常
  terminal cause 或 chunk limit exhausted 均抛出 `RuntimeError`，backend
  非零退出并由 host 归为 HARNESS-ERROR。

R3 独立 reviewer 静态复核上述代码，并结合最终 positive、rd40 negative、
post-restore 实跑，判定 **PASS**；剩余 blocker/high/medium/low finding
均为 **无**。reviewer 未修改或提交仓库。
