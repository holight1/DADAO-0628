# KL-127a：PTW 故障处理 + A/D 位硬件回写（QEMU + gem5）

**执行环境**：远端 Codex（本仓库），QEMU 源码改动
（`.work/source/qemu`）+ gem5 源码改动（`~/DADAO-gem5`，独立仓库）

## 背景

`KL-125a`/`KL-126a` 已在 QEMU/gem5 双后端实现了 `cfx_ptw` 的**成功路径**
（`dadao_ptw_translate()`/`ISA::ptwTranslate()`），显式排除了故障处理和
A/D 位回写。`KL-122a` 已把 O3 专用的精确异常入口提升为任意 cfx 都能调用
的通用 carrier（QEMU `dadao_cfx_precise_trap_enter(cpu, target_cfxcode,
cause_id, raw_insn)`，gem5 对称的 `cfxPreciseTrapEnter` 等价物）——它的
第 4 个参数在 CFXTRAP 场景下存的是指令编码，但函数本身对参数值没有任何
假设，本任务把它当成通用 `cause_info` 载体直接复用，不需要新造入口机制。

本任务把这两块拼起来：**PTW 成功路径未命中时的完整故障分类**，以及
**成功路径本该做但被推迟的 A/D 位硬件回写**。18 个 `cfx_ptw` 异常原因
（wiki 第442-461行）在 wiki 表里全部标注"是否可屏蔽=否"，`KL-118a`
的调研已独立确认这一点。其中 15 个是本任务 walker 会产生的故障；
`CFXTRAP`/`CFXMEM`/`CFXREG` 分别属于功能调用、核内存储和非法 CFX
寄存器访问，不是 page walk 失败分支。因此 walker 故障入口都走
`KL-122a` carrier 的不可屏蔽
路径（跳过步骤2-6 的 mask 检查/pending 处理），不需要额外发明屏蔽逻辑。

**QEMU+gem5 合并为一个任务**：两边算法必须逐位对称（沿用 `KL-125a`/
`KL-126a` 已验证过的对称关系），拆成两个任务只会增加下发开销而不提升
验证粒度——本任务的验收本身就要求双后端独立跑同一组故障场景并比对。

## 目标

### 1. 故障分类与路由（QEMU + gem5）

把 `dadao_ptw_translate()`/`ISA::ptwTranslate()` 现在"返回 false = 未定义
行为"的每一个失败分支，改成"识别具体故障原因 + 通过 `KL-122a` carrier
精确入口到 `cfx_ptw`"：

- PTBR mode-permission 不通过（`cfx_ptw_<mode>_perm` 对应位为0）→
  `NUPERM`/`NJPERM`/`NSPERM`/`NHPERM`（按 `inner_run_mode` 选择哪一个），
  cause info = 访存/取指地址。
- L1 PTE（superpage 路径）Present=0 → `ISPTRAP`/`DSPTRAP`（按访问类型是
  取指还是数据）。
- L1 PTE（superpage 路径）Present=1 但 SPF 对应小页标记位为0 →
  `ISPFTRAP`/`DSPFTRAP`。
- L1 PTE（normal 路径，SP=0）Present=0，或其指向的 L2 PTE Present=0 →
  两种情况**共用同一 cause**：`IGPTRAP`/`DGPTRAP`（wiki 原文如此，不要
  为 L1/L2 两层分别发明不同 cause）。
- L2 PTE Present=1 但 GPF 对应小页标记位为0 → `IGPFTRAP`/`DGPFTRAP`。
- 最终 leaf PTE 找到、Present/fragment 都通过，但 R/W/X 权限位不满足
  当前访问类型 → `NXPERM`（取指）/`NWPERM`（写）/`NRPERM`（读）。
- `cause info` 按 wiki 异常原因表（第442-461行）逐条填写"访存地址"或
  "取指地址"（即触发本次转换的原始 VA，不是 PA）。

enable=0 的核内地址空间路径（KL-125a/126a 已实现）不受本任务影响——那
条路径本来就不是故障。

### 2. A/D 位硬件回写（QEMU + gem5）

成功路径找到 leaf PTE 后（superpage 用 L1 PTE、normal page 用 L2 PTE），
硬件按 wiki §2.2.3/§2.2.4 描述负责把该 PTE 在主存中的 A 位（bit3）置1
（任意访问），D 位（bit2）在写访问时也置1，随后才形成最终物理地址返回
成功。这是对 `KL-125a`/`KL-126a` 已实现的成功路径的**扩展**（不是新增
独立函数）——A/D 回写发生在权限检查通过之后、返回成功之前。

- 当前功能模型是单 hart、无并发访问同一 PTE 的场景，"原子读-改-写"不
  需要真的用原子指令实现，普通 load-modify-store 语义上已经足够；不要
  为不存在的并发场景引入额外的原子操作原语。
- 没有架构 TLB（`KL-129a`/`130a` 的范围），所以当前每次访问都会重新
  walk 并重新回写 A/D——这是预期行为，不需要"跳过已经是1的情况"之类
  的优化，但如果 A/D 已经是1，写回值不变也不算错误（幂等）。

### 3. 测试用 self-handler（QEMU + gem5）

`KL-118a` 调研已明确：`cfx_tlb→cfx_ptw→cfx_tlb` 的委托返回契约仍未闭环
（多帧 escape 语义的独立空白，`docs/wiki-deviations.md` #9 里 E1 未覆盖
的部分），所以**本任务不实现/不测试跨 cfx 委托**。验收只需要 `cfx_ptw`
自己的 supv 异常向量指向一个探针自带的 self-handler（用 `KL-122a` 已有
的 per-cfx `cfx_supv_excp_vector` 机制），验证故障能精确进入、
`excp_cause_id`/`excp_cause_ip`/`excp_cause_info` 正确、`escape cfx_ptw,0`
能精确返回触发指令重试或跳过（探针自行选择，两种都要各验证至少一次）。

## 约束

- **不实现 TLB**（`KL-129a`/`130a` 范围）、**不实现跨 cfx 委托**
  （委托返回契约本身仍是 OPEN 状态，见 `docs/wiki-deviations.md` #9 剩余
  部分）、**不实现 Linux 分页策略**（内核任务范围）。
- 15 个 walker-generated `cfx_ptw` cause 全部不可屏蔽——入口精确、不经过 mask/pending，
  这点已由 `KL-118a` 独立确认，不要重新论证或引入屏蔽逻辑。
- 故障分类要逐位对照 wiki 原文（第425-461行），尤其注意 `IGPTRAP`/
  `DGPTRAP` 在 L1（SP=0，P=0）和 L2（P=0）两处复用同一 cause——不要
  分别发明新 cause。
- A/D 回写是对成功路径的扩展，不要复制一份新的 walk 逻辑。
- 复用 `KL-122a` 的通用精确异常入口（QEMU `dadao_cfx_precise_trap_enter`/
  gem5 对称的 helper），不要新造一套入口机制。
- QEMU 与 gem5 两侧算法要逐位对称——如果两边对同一 VA/页表内容/访问类型
  给出不同的 cause id 或不同的 A/D 结果，就是本任务的 bug。
- 完整 patch-series bare-pin replay（tree-hash 比对）是硬性验收项，
  QEMU/gem5 分别做。
- 完成后写「完成区」+ 自审记录；继续沿用"自己开 reviewer subagent
  复核"的方法。
- 现有全部 QEMU/gem5 探针（O1/O2/O3/`KL-120a`/`KL-122a`/`KL-124a`/
  `KL-125a`/`KL-126a`）零回归——尤其是 `KL-125a`/`126a` 的成功路径探针，
  加了 A/D 回写后预期物理地址结果不应改变，只是 PTE 内存内容多了 A/D
  位被置位，探针要能验证这一点没有破坏原有断言。

## 验收

- 15 个 walker-generated `cfx_ptw` 故障原因**逐条**用静态构造的页表触发并验证
  `excp_cause_id`/`excp_cause_ip`/`excp_cause_info` 精确正确（不要只挑
  几个代表性的就收工——这是本任务的核心交付）。
- A/D 回写：构造只读探测场景（读访问后 A=1/D=0）和写访问场景（A=1/D=1），
  分别验证 superpage leaf（L1 PTE）和 normal-page leaf（L2 PTE）两种
  PTE 在主存中被正确改写，不只是 log 断言，要真的重新读回 PTE 内存内容
  核对。
- 每类故障至少构造两个字段值不同的场景（不要用全零索引/全零 fragment，
  沿用 `KL-125a`/`126a` 已经建立的"避免假绿"惯例）。
- self-handler 验证 retry（修正后重新执行触发指令）和 skip（改写 PC
  跳过）两种 `escape` 语义都至少各验证一次。
- QEMU 与 gem5 对同一组故障/A-D 场景（不要求逐字节相同的 VA/页表数值，
  但覆盖的 cause 种类要对齐）给出一致结果。
- 现有全部探针零回归。
- 全量 lit E2E、`tools/run_differential.py`、`manifest_check.py`、
  `check_issues.py` 无回归。
- patch-series bare-pin replay，QEMU/gem5 tree hash 分别与各自开发树
  一致。

## 参考指针

- `docs/reviews/kernel-mmu-interrupt-recon-20260726.md` §1.3（TLB→PTW
  委托契约缺口，本任务不涉及的边界）、§5 第9/10行（`KL-127a`/`128a`
  原始范围描述，本任务合并两者）
- `~/DADAO-wiki/DADAO-12-SEE-主管系统运行环境.md` 第54-219行（VA→PA
  完整算法+故障分支）、第425-461行（`cfx_ptw` 寄存器表+18条异常原因表）
- `code-agent/tasks/KL-125a-ptw-success-path-qemu.md` /
  `KL-126a-ptw-success-path-gem5.md` 完成区（成功路径实现细节，本任务
  要扩展的位置）
- `.work/source/qemu/target/dadao/cpu.c` 的 `dadao_ptw_translate()`
  （KL-125a）、`dadao_cfx_precise_trap_enter()`（KL-122a，本任务直接
  复用的通用入口）
- `~/DADAO-gem5/src/arch/dadao/isa.cc` 的 `ISA::ptwTranslate()`
  （KL-126a）、`src/arch/dadao/decoder.cc` 的 `cfxPreciseTrapEnter` 等价
  helper（KL-122a）
- `docs/wiki-deviations.md` #9（嵌套 cfx 返回，E1 已实现的部分与仍
  OPEN 的多帧 escape 部分——本任务只依赖前者，不涉及后者）

---

## 完成区（2026-07-26）

**状态：PASS（两轮 finding 已修复，第三轮独立终审通过）。**

### 实现

- QEMU `69a025c4310b9d22cad326bda5a4ec50102feede`：
  `dadao_ptw_translate()` 对 mode permission、L1/L2 present、
  SPF/GPF、X/R/W permission 的全部失败分支返回精确 cause；`tlb_fill`
  先恢复 faulting PC，再以原始 VA 为 `cause_info` 进入通用
  `cfx_ptw` carrier。成功 leaf 在返回翻译前写回 A(bit3)，写访问同时
  写回 D(bit2)。
- gem5 `7eaa17d4b4bb9b2f769b1f9bb1054e73d3bf34e3`：
  `ISA::ptwTranslate()` 与 QEMU 逐分支对称，`TLB` 通过 `ReExec`
  承载 fault-handler retry，并共享提升后的 `ISA::cfxPreciseTrapEnter()`；
  FullSystem 增加一个仅供共享 superpage retry/A-D 探针使用的稀疏物理窗。
- 新增 `tests/scripts/run_kl127a_ptw_fault_ad_probes.py`。同一生成器对
  QEMU/gem5 构造 15 cause × 2 个非零字段变体，以及
  super/normal × read/write/read-then-write/clear-A-or-D-then-reaccess
  十个 A/D 内存读回场景；取指故障修 PTE 后 retry，数据故障改 PC 后
  skip。

### “18 cause”口径校正

wiki 的 `cfx_ptw` 表共有 18 项，其中 `CFXTRAP`、`CFXMEM`、`CFXREG`
是通用/显式 CFX 访问类原因；本任务目标列出的 PTW walker 失败分支对应
其余 **15 项**（4 mode + 3 access + 8 page/fragment）。`enable=0`
按任务约束仍为 identity success，`cfxld/cfxst` 又明确不在本任务范围，
所以不能诚实地产生额外三个 walker failure。本次完整覆盖 15/15
walk-generated causes；未用伪造入口把 15/18 写成 18/18。

### 验证证据

- KL-127a：`PASS: 30 fault probes (15 walker causes x 2 variants) +
  10 A/D probes; QEMU=gem5; retry+skip self-handler`；40 个场景均
  `QEMU=42, gem5=42`，160 份逐后端二进制/日志证据位于
  `.work/evidence/kl127a-ptw-fault-ad/`。
- 成功路径：KL-125a QEMU `8/8 PASS`；KL-126a gem5 `8/8 PASS`。
- 既有 FullSystem/CFX：KL-124a 全矩阵通过；KL-122a `46/46 PASS`；
  KL-120a 与 O1/O2/O3 结果保持既有值。
- 全量 E2E `81/81 PASS`。
- differential：三路 `AGREE=200, gem5-SKIP=2, DIVERGE=0`；四路
  `AGREE=200, Sail-SKIP=2, DIVERGE=0`。
- `manifest_check.py PASS`；`check_issues.py PASS`
  （Open 24 / Closed 43 / Total 67）；三棵工作树 `diff --check PASS`。
- patch-id：
  QEMU `c3751f1379acbfe289d66a2cf302289195e97620`；
  gem5 `cd90de76d549cf6338d01fa02f28c3eff79032c6`。
- bare-pin plain `git am`：QEMU 30/30，replay/dev tree 均为
  `cf001858708339a3effd879e12566c7182e7ac23`；gem5 24/24，
  replay/dev tree 均为 `98a2f8b2a58f945432cefabe6811d1ee263d572c`。

### 自审记录

- 逐分支核对 QEMU/gem5 cause 常量、super/normal 分流、permission 顺序
  及 A/D 更新时点，未发现双后端不对称。
- `cause_info` 始终为原始 48-bit VA，`cause_ip` 始终为实际触发指令；
  QEMU 在 carrier 前 `cpu_restore_state()`，gem5 用 `ReExec` 重试，
  两种 self-handler 返回均由 guest 内部核对 frame 后才允许 exit 42。
- A/D 断言从真实 leaf PTE 地址重新读取整字并精确比较，不依赖日志；
  两个变体均使用非零 PTBR/L1/L2/fragment，避免零索引假绿。
- 边界保持：没有加入 TLB、跨 CFX 委托、Linux 分页或 cfxld/cfxst。

### 首轮独立 review 与修复

- reviewer 结论 `NEEDS_FIX`，发现 QEMU 内部 softmmu TLB 在 R|W leaf
  的首次 read 后缓存 PAGE_WRITE，导致同 VA 后续 write 绕过 walker，
  D 位保持 0；独立探针得到 QEMU `154`、gem5 `42`。
- 修复：若非写 walk 观察到 leaf D=0，QEMU 只向内部缓存授予去掉
  PAGE_WRITE 的权限；首次写因而重新 walk、置 D 后再获得完整权限。这是
  host-side 缓存正确性处理，不是提前实现 KL-129a 的架构 TLB。
- 新增 super/normal 两个同页 `read→write→PTE readback` 探针；修复后
  与原 34 个场景一起双后端全部返回 42。
- 同轮接受两个文档 finding：把正文目标/验收从含混的 18 项明确修订为
  15 个 walker-generated cause，并修正 carrier 的 CFXTRAP-only 旧注释。

### 二轮独立 review 与修复

- reviewer 再次给出 `NEEDS_FIX`：局部 D=0/PAGE_WRITE 修复仍不能处理
  “软件通过 identity 地址清除 A 或 D 后再次访问同一 VA”，QEMU 命中
  host softmmu cache 而 gem5 重新 walk；super/normal 的独立 clear-A
  判别均为 QEMU `154`、gem5 `42`。
- 根因是任务明确处于“无架构 TLB、每次访问 walk”阶段，而 QEMU 的内部
  host cache 泄漏成了架构可见状态。最终修复在 PTW enable 时把 TB 限为
  单条 guest 指令，并在每个指令边界丢弃 host translation；enable 写入
  自身结束旧 profile TB。KL-129a 的架构 TLB 将位于 walker 上层，不依赖
  这个 host cache。
- 新增 super/normal × `clear-A→read` / `clear-D→write` 四个真实 PTE
  修改与回读探针；加上 read→write 两项及原四项，共 10 个 A/D 场景。
- 同轮修正 runner 数量注释及 “machine has no PTBR” 的过时注释。

### 第三轮独立终审

**结论：PASS。** 未发现 High/Medium/Low correctness finding。reviewer
独立确认 enable 前多指令 TB、enable 后单指令 TB、disable 后恢复多指令
TB，PC 精确推进且无死循环；重跑 clear-A/clear-D 的 super/normal 四项、
完整 40/40 双后端场景、KL-125a 8/8、KL-126a 8/8、KL-122a 46/46、
KL-124a 全矩阵、E2E 81/81、三/四路 differential 200/200 均通过。
它还独立完成 QEMU 30/30 与 gem5 24/24 bare-pin replay，核对 patch-id、
tree identity、160 份证据以及 fresh ROM/RAM 与仓内证据逐项一致。
