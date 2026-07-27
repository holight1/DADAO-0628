# KL-131a：可屏蔽异步分派核心（QEMU + gem5）

**执行环境**：远端 Codex（本仓库），QEMU 源码改动
（`.work/source/qemu`）+ gem5 源码改动（`~/DADAO-gem5`，独立仓库）

**依赖**：仅 `KL-119a`/`KL-122a`（均已完成）。**不依赖** `KL-127a`/
`129a`（PTW/TLB 链）——`docs/reviews/kernel-mmu-interrupt-recon-20260726.md`
§5 已明确 MMU 链和异步链共享 `KL-119a`/`122a`/`124a` 后可并行；本任务
可以和 `KL-127a`/`129a` 并行推进，不必等它们完成。

## 背景

`KL-122a` 把 SEE §5 异常进入流程的**步骤7-10**（保存现场→模式切换→
保存异常信息→跳向量）提升成了任意 cfx 都能调用的通用 carrier
（QEMU `dadao_cfx_precise_trap_enter`），但**步骤2-6**——不可屏蔽判断、
`inner_cfx_mask`、`global_cfx_mask`、`excp_cause_mask` 三级屏蔽检查、
陷入计数——完全没有实现。当前所有调用点（O3 的 CFXTRAP、`KL-127a` 的
PTW 故障）都是"无条件直接进入"，等价于把所有异常当成不可屏蔽处理。

本任务补上步骤2-6，并且是 K1 第一次实现**真正的异步中断**（此前所有
入口都是被当前指令同步触发的）。这意味着需要在 QEMU/gem5 的主执行循环
里挂一个指令边界检查点，不只是新增一个被动调用的 helper 函数。

## 目标

### 1. 新增寄存器存储（QEMU + gem5）

- `cg{0,1,2,3}/rc1`：`cfx_⟨cfxname⟩_<mode>_global_cfx_mask`——**注意
  这是共享寄存器**：wiki 明确"`<mode> global` 开头的寄存器为全局寄存器，
  即所有核芯功能扩展共享同一个寄存器"（例如 `supv_global_cfx_mask` 是
  全系统唯一一份，不是每个 cfx 各自一份）。每种 mode 各一份（4份
  共享寄存器），不要按 cfxcode 建 64 份数组。复位值全1（屏蔽）。
- `cg{0,1,2,3}/rc11`：`cfx_⟨cfxname⟩_<mode>_excp_cause_mask`——这个**是**
  按 cfx 各自一份（每个 cfx 64位，对应它自己异常原因表里的位）。复位值
  全1（屏蔽）。
- `cg5/rc63`：`cfx_⟨cfxname⟩_excp_cause_nonmaskable`（RO，硬件按各 cfx
  的异常原因表静态设置——`cfx_ptw` 的18个原因全部不可屏蔽（`KL-118a`
  已确认）、`cfx_umon/jmon/smon/hmon` 里只有 `FPEXCP` 可屏蔽、
  `cfx_tlb` 的8个原因全部不可屏蔽、`cfx_timer` 里只有 `TIMER` 可屏蔽、
  `cfx_uart` 里只有 `UART0-31` 可屏蔽、`cfx_power` 里只有 `SOFT_RESET`
  可屏蔽——具体位置自己核对各 cfx 在 wiki 里的异常原因表，不要凭记忆）。
- `cg4/rc2-4`：`cfx_⟨cfxname⟩_trap_num`/`excp_sync_num`/`excp_async_num`
  （HW，per-cfx，按步骤6规则递增：`CFXTRAP`→trap_num，异步→
  excp_async_num，其余同步→excp_sync_num）。

### 2. 步骤2-6 的判定逻辑（QEMU + gem5）

给 `KL-122a` 的精确入口 carrier 前面加一道共享的"能否进入"判定（不要
新造一套独立机制，也不要在每个调用点各自复制判定逻辑）：

1. 不可屏蔽（`excp_cause_nonmaskable` 对应位=1）：跳过下面所有检查，
   直接进入 carrier（步骤7起）。
2. `inner_cfx_mask` 屏蔽（仅当 target≠`inner_cfx_code` 时检查）：同步
   异常改发 `ILLI`（重定向到当前运行模式对应的 monitor，wiki 步骤1
   伪代码 `U/J/S/H-mode: temp_cfx_code<=0/1/2/3`），异步中断 OR 进
   `cfx_<name>_pending`（`KL-120a` 已有存储）。
3. `global_cfx_mask` 屏蔽（同上，仅当 target≠自身时检查，用共享寄存器）：
   处理方式同上。
4. `excp_cause_mask` 屏蔽：同步异常（仅 `FPEXCP` 可能走到这——其它同步
   异常在硬件层面已经不可屏蔽）OR 进 pending；异步中断同样 OR 进
   pending。
5. 全部通过：递增对应计数器，进入 `KL-122a` carrier。

### 3. 指令边界异步分派（QEMU + gem5）

这是本任务真正的新机制：在每个指令边界检查是否有已解除屏蔽的 pending
异步原因，若有则按 `contracts/isa/spec.md` §8.5.1 已冻结的优先级
（**先选最低 pending 且未屏蔽的 cfxcode，该 cfx 内再选最低已置位的
原因位**）触发对应入口，`cause_ip` 用**下一条指令地址**（不是当前
指令地址，这点和同步异常相反）。查阅 QEMU 里其它 target 如何在主执行
循环/TB 边界检查 `cs->interrupt_request`、gem5 里其它 ISA 如何在
`checkInterrupts`/等价钩子里检查未屏蔽中断，把 DADAO 的检查接入同一
位置，不要发明新的执行循环挂钩方式。

### 4. 电平触发语义（QEMU + gem5）

pending 位由软件写0清除；若底层源仍然有效（`KL-119a`/`120a` 的
`cfx_common_pending_test_code/seed` 测试注入或本任务新增的合成源），
硬件在下一指令边界检查时重新 OR 回 pending（wiki: "若一个电平源仍然
有效，硬件在下一指令边界检查前重新 OR 该位"）。

## 约束

- 只做分派核心本身，**不实现 timer/UART 真实设备**（`KL-133a`/`137a`
  范围）——本任务用可控合成源验收（例如复用/扩展 `KL-120a` 已有的
  common-pending 测试注入机制，或新增一个专门用于本任务的合成异步源，
  命名自定但必须明确标注"仅测试用，非架构可见"）。
- `global_cfx_mask` 是**共享寄存器**，不要误按 per-cfx 数组实现——这是
  wiki 明确写出的特殊点，见目标1。
- QEMU/gem5 两侧算法要逐位对称，尤其是优先级选择（低 cfxcode 优先、
  同 cfx 内低位优先）和电平重锁存语义。
- 完整 patch-series bare-pin replay（tree-hash 比对），QEMU/gem5 分别做。
- 完成后写「完成区」+ 自审记录，继续沿用"自己开 reviewer subagent
  复核"的方法。
- 现有全部探针零回归（O1/O2/O3/`KL-120a`/`KL-122a`/`KL-124a`，以及若
  `KL-127a`/`129a` 此时已完成则一并回归）。

## 验收

- 步骤2/3/4 三级屏蔽各至少一个同步异常场景（验证改发 `ILLI`）+一个
  异步场景（验证 OR 进 pending 且不入口）。
- 不可屏蔽异常跳过三级检查、直接进入——用 `cfx_ptw` 或 `CFXTRAP` 作为
  已知不可屏蔽的例子验证。
- 陷入计数器（trap_num/excp_sync_num/excp_async_num）在对应场景下
  精确递增。
- 异步中断真正在指令边界触发（不是被当前指令同步触发），`cause_ip`
  为下一条指令地址；构造跨多条指令的场景验证不是"立即触发"而是"下一个
  边界触发"。
- 优先级：构造至少两个不同 cfx 同时 pending、以及同一 cfx 内至少两个
  cause 同时 pending 的场景，验证低编号优先。
- 电平重锁存：mask 解除但源仍有效时，pending 应在下一边界重新置位。
- 现有全部探针零回归。
- 全量 lit E2E、`tools/run_differential.py`、`manifest_check.py`、
  `check_issues.py` 无回归。
- patch-series bare-pin replay，QEMU/gem5 tree hash 分别与各自开发树
  一致。

## 参考指针

- `~/DADAO-wiki/DADAO-12-SEE-主管系统运行环境.md` 第650-811行（SEE §5
  完整异常进入流程正文+伪代码，步骤1-10）、第269-330行（cg0-3 mode
  寄存器表，`global_cfx_mask`/`excp_cause_mask` 的精确 cg/rc）、
  第341-347行（cg4 计数器）、第362行（cg5/rc63 nonmaskable）
- `contracts/isa/spec.md` §8.5.1（pending/优先级冻结契约）
- `docs/reviews/kernel-mmu-interrupt-recon-20260726.md` §2.1（步骤2-6
  与现有 O3 的关系分析）
- `code-agent/tasks/KL-122a-*.md` 完成区（步骤7-10 carrier，本任务在
  它前面接一道判定）
- `code-agent/tasks/KL-120a-*.md` 完成区（`cfx_<name>_pending` 存储，
  本任务复用）

## 完成区（2026-07-27）

**状态**：PASS。目标1-4全部完成；QEMU/gem5 双后端实现、独立探针、完整
回归、两套 bare-pin patch-series replay 均通过。

### 实现

- **新增寄存器存储**（QEMU `cpu.h`/`cpu.c`，gem5 `isa.hh`/`isa.cc`）：
  - `cg0-3/rc1` `<mode>_global_cfx_mask`：**共享**寄存器，4 份（按 mode
    索引，不按 cfxcode），QEMU `cfx_mode_global_cfx_mask[4]`、gem5
    `cfxModeGlobalCfxMask[4]`。cfx2rc/cfx2rd 写读时 cfxcode 操作数被
    忽略（helper.c/decoder.cc 均已注释说明）。复位全 1。
  - `cg0-3/rc11` `<mode>_excp_cause_mask`：per-cfx per-mode（`[64][4]`）。
    复位全 1。
  - `cg5/rc63` `excp_cause_nonmaskable`：RO，`dadao_cfx_excp_cause_
    nonmaskable_for()`（QEMU）/`cfxExcpCauseNonmaskableFor()`（gem5）
    按 wiki §4 各 cfx 异常原因表逐位复核后静态构造（cfx_umon/jmon/smon/
    hmon 仅 FPEXCP 可屏蔽；cfx_ptw 全 18 项不可屏蔽；cfx_tlb 全 10 项
    不可屏蔽——独立重读 wiki 确认任务原文"8"个是欠计，未含 CFXMEM/CFXREG
    两行，wiki 表格本身以 10 项为准；cfx_hart/timer/uart 仅 IPI/TIMER/
    UART0-31 可屏蔽；cfx_power 仅 SOFT_RESET 可屏蔽；其余含 cache/llc/
    pmem 及保留 cfxcode 仅 CFXTRAP/CFXMEM/CFXREG 三项不可屏蔽）。
  - `cg4/rc2-4` `trap_num`/`excp_sync_num`/`excp_async_num`：HW 计数器，
    per-cfx，写口保持既有"未占用 (cg,rc) 静默 no-op"惯例（未新增
    CFXREG）。
- **共享判定门 `dadao_cfx_dispatch()`**（QEMU `cpu.c`）/`ISA::cfxDispatch()`
  （gem5 `isa.cc`）：实现 SEE §5 步骤2-6，前置于 KL-122a 的
  `dadao_cfx_precise_trap_enter()`/`cfxPreciseTrapEnter()`（步骤7-10）。
  纯谓词 `dadao_cfx_cause_eligible()`/`ISA::cfxCauseEligible()` 被判定门
  与异步扫描共用，保证语义单一来源。同步调用在 steps3-4 阻塞时改发
  ILLI 重定向到当前模式 monitor（最多重试一次，因 ILLI 在任意 monitor
  内恒不可屏蔽）；step5 阻塞（同步仅 FPEXCP 可能触达，异步任意情形）一律
  OR 进 pending、不入口。QEMU 既有 3 个调用点（cfx_smon CFXTRAP、cfx_ptw
  CFXTRAP-as-call、cfx_ptw/cfx_tlb 故障）全部改走此判定门；三者原因均
  不可屏蔽，行为不变，仅新增计数器递增。gem5 同构改造
  `decoder.cc`（TrapInst 两处）与 `tlb.cc`（PTW/TLB 故障）。
- **指令边界异步分派**：
  - QEMU：`dadao_cpu_exec_interrupt()`（`translate.c`）改为真实调用
    `dadao_cfx_async_step()` → `dadao_cfx_async_scan()`（`cpu.c`），后者
    实现 `contracts/isa/spec.md` §8.5.1 冻结的优先级（先最低 pending 且
    eligible 的 cfxcode，同 cfx 内再选最低 eligible 的原因位——扫描时对
    每个已置位的原因位逐位测试 eligible，非只取全局最低置位位）。
    `CPU_INTERRUPT_HARD` 改为在 reset 时**无条件**置位（不再仅在测试
    level source 配置时置位）：理由是普通 guest cfx2rc 写就能产生真正
    pending 且刚解除屏蔽的原因（如 A4 探针本身），QEMU 必须与 gem5 的
    `Interrupts::checkInterrupts()`（FullSystem 模式下逐指令无条件轮询）
    行为一致；该扫描在全零 pending 时开销可忽略（64 项快速失败循环），
    经全量回归验证未产生可观测性能问题。仅 `max_insns=1`（指令边界精度
    强制单指令 TB）继续由 `dadao_cfx_async_active()` 门控（仅测试 level
    source 配置时为真），避免对全部既有回归引入单指令 TB 的性能代价。
  - gem5：`Interrupts::checkInterrupts()`/`getInterrupt()`（`interrupts.hh`，
    此前恒为 `false`/`NoFault` 的占位实现）改为真实调用
    `ISA::cfxAsyncScan()`；新增 `AsyncInterruptFault`（`faults.hh`/`.cc`），
    其 `invoke()` 调用 `ISA::cfxDispatch(isSync=false)`。gem5
    `AtomicSimpleCPU` 本身逐 tick（=逐指令）检查中断，无需 QEMU 式
    `max_insns` 强制。但 `BaseCPU::checkInterrupts()` 仅在 `FullSystem`
    模式下轮询，故本任务异步探针改用 `tests/dadao/dadao_fs.py`
    （KL-124a FullSystem 裸机 carrier）而非既有 SE 模式 harness；
    `dadao_fs.py` 新增 `--cfx-async-level-a/-b <cfxcode> <seed>` CLI
    透传到新增 SimObject 参数。
- **TEST-ONLY 合成源**（均明确标注非架构可见）：
  - 同步测试触发器 `cg4/rc60`（QEMU `helper_cfx2rc` 新分支、gem5
    `CFX2RCInst` 新分支）：因 M1 唯一真实可屏蔽同步原因 FPEXCP 无可达
    执行路径（RF 排除在 M1 外），此触发器让测试程序直接以任意
    `(target, cause, is_sync=true)` 调用判定门，是验收步骤2/3/4/5 同步
    分支的唯一手段。QEMU 侧发现并修复一个真实 bug：`dadao_cfx_dispatch()`
    改为返回 bool（是否真的入口），触发器仅在入口发生时才
    `cpu_loop_exit()`——此前无条件 `cpu_loop_exit()` 会在判定门阻塞
    （未入口）时使 env->pc 停留在触发指令本身，导致同一条指令被
    无限重新取指执行。tlb_fill 故障调用点也补充了同款防御性注释（该
    路径原因恒不可屏蔽，数学上不可达，但记录了同一 bug 类别的风险）。
  - 两路独立"持续电平触发"合成异步源
    `cfx-async-test-level-{a,b}-{code,seed}`（QEMU CPU 属性 + gem5
    SimObject 参数）：seed 非零时，每次异步扫描无条件把 seed（按目标
    cfx 有效原因位过滤）OR 进 `cfx_common_pending`，为整个运行周期持续
    生效（不同于 KL-120a 一次性 raw seed 注入）。驱动全部异步验收场景
    （边界精度、跨 cfx/同 cfx 优先级、电平重锁存）。

### 探针与验证

新增 `tests/scripts/run_kl131a_async_dispatch_probes.py`（QEMU+gem5 双
后端），两个场景：

- **场景A（同步掩码，via 测试同步触发器）**：
  - A1 步骤2 不可屏蔽绕过（`cfx_ptw`/NUPERM，默认全屏蔽状态下仍入口）。
  - A2 步骤3 `inner_cfx_mask` 阻塞（默认全1，跨 cfx UART0 → 改发
    ILLI@cfx_smon）。
  - A3 步骤4 隔离验证：通过"escape 帧伪造"技巧（向未真正进入的
    `cfx_ptw` 帧写入 `prev_run_mode`/`prev_cfx_mask`/`cause_ip` 后执行
    非自身 `escape cfx_ptw,0`，利用 SEE §5 退出流程"恢复 mask 后模式"
    且非自身 escape 不改写 `inner_cfx_code` 的既有语义）单独清除
    `inner_cfx_mask` 的 uart 位，`global_cfx_mask` 仍默认阻塞 → 同样
    改发 ILLI，但此时可归因于步骤4；A3 正控制额外清除
    `global_cfx_mask`+`excp_cause_mask[uart]` 后同一目标真正入口成功，
    两者对照证明步骤4 确系阻塞点。
  - A4 步骤5 自目标阻塞（`cfx_power`/SOFT_RESET，自身目标绕过步骤3/4，
    excp_cause_mask 默认阻塞 → OR 进 pending 不入口）；正控制清除
    excp_cause_mask 后重触发真正入口。
  - 各分支精确核对 `trap_num`/`excp_sync_num`/`excp_async_num`。
- **场景B（异步分派，两路合成 level source）**：
  - 电平重锁存两段：masked 状态下 pending 持续被重新 OR（跨边界仍为
    1）；显式 W0C 清除后跨一个边界立即重新观测到置位。
  - 跨 cfx 优先级：`craft_inner_cfx_mask` 一次性同时解锁 hart(15)+
    uart(62)，验证低 cfxcode（hart）优先入口，`cause_ip` 精确等于
    "本应执行的下一条指令地址"（该地址处放置 `UNIMP` 毒药，从未真正
    执行，证明分派抢占而非延后触发）。
  - 同 cfx 多原因优先级：uart 内 UART0(bit32)+UART5(bit37) 同时 pending，
    先 UART0（低位）后 UART5，且 UART5 之所以能被选中是因为扫描对
    UART0 单独重新屏蔽后逐位测试跳过了它，而非全局最低置位位规则。
  - **调试过程记录**（自审关键发现，另见下文"自审记录"）：本场景经历
    三轮设计迭代才收敛，因为"电平源持续存在 + 自目标绕过 steps3-4"
    在指令边界精确检查下会造成 handler 对自身的无限重入——这是架构
    的真实属性（cfx2rc 写值恒为寄存器来源，无法一条指令内完成"构造
    掩码值+写入"），不是模拟器 bug；最终收敛方案是在"安全区"预加载
    全1寄存器，令每个 handler 的第一条指令即为原子屏蔽写，避免任何
    构造窗口，并显式改写 `prev_cfx_mask` 使 escape 恢复时不会带回
    "刚好解锁"的状态。

结果：`PASS: scenario-A(sync masks 2/3/4/5+nonmaskable+counters)=131/131;
scenario-B(async boundary+priority+electrics)=132/132`。

### 回归

- 既有 K1 探针零回归：`run_kl120a_cfx_carrier_probes.py`
  （`register=44/44; rd0 ILLI=130/130; pending profiles=7x45/45;
  nested=43/43`）、`run_kl122a_generic_carrier_probes.py`
  （`generic cfx_ptw frame/vector/escape=46/46`）、
  `run_kl124a_gem5_fs_probes.py`、`run_kl125a_ptw_success_probes.py`、
  `run_kl126a_gem5_ptw_success_probes.py`、
  `run_kl127a_ptw_fault_ad_probes.py`、`run_kl129a_tlb_probes.py`、
  `run_kl113a_gem5_probes.py`、`run_kl117a_gem5_probe.py` 全部 PASS，
  数值与基线完全一致。
- `.work/build/llvm/bin/llvm-lit -sv tests/lit/E2E/`：81/81 PASS。
- `python3 tools/run_differential.py`：`AGREE(3-way)=200
  AGREE(interp+QEMU, gem5-SKIP)=2 DIVERGE=0`；
  `AGREE(4-way)=200 Sail-SKIP=2 SAIL-DIVERGE=0`——与基线完全一致。
- `python3 scripts/manifest_check.py`：PASS。
- `python3 scripts/check_issues.py`：`Open=24 Closed=43 Total=67`，PASS。
- `python3 scripts/check_wiki_refs.py --profile isa`/`--profile abi`：
  PASS（3 条既有 UNPARSEABLE warning，非本任务引入）。
- `python3 scripts/check_wiki_drift.py`：PASS（3 份契约核实）。

### 提交与 replay

- QEMU commit `fd77795e897183b7988a74b8b494576ddc65ea09`；
  patch `components/qemu/patches/0032-target-dadao-implement-maskable-async-dispatch-c.patch`；
  stable patch-id `81ec81aff088159909661bb27d5a156169c27514`。
  从 manifest pin `385b0a7d9785c8f3ac7b116d7f31d61502b55183`
  plain `git am` 32/32 PASS；开发树与 replay 树 tree-hash 均为
  `617d4d561f351facefc21c6854d867469fd0aa1b`。
- gem5 commit `3e1eb762232b5e9d51ce33e18cb4d87762fceff3`；
  patch `components/gem5/patches/0026-arch-dadao-implement-maskable-async-dispatch-cor.patch`；
  stable patch-id `ebcf20cc2e8273565c86abae824d72d2a2506ac9`。
  从 manifest pin `c8222cc67a399bfc01e8658dd14b30d5bfd634f9`
  plain `git am` 26/26 PASS；开发树与 replay 树 tree-hash 均为
  `f5d569bd99ecbc7b91aba52d0ff9d455d70af82f`。
- 两个临时 replay worktree（`/tmp/kl131a-qemu-replay`、
  `/tmp/kl131a-gem5-replay`）已清理。

### 自审记录

结论：**PASS，可进入独立 subagent review**。

- 逐条核对 QEMU/gem5 寄存器存储、判定门、异步扫描、优先级选择算法
  位级对称；`global_cfx_mask` 共享寄存器语义（cfxcode 操作数被忽略）
  两端一致。
- `dadao_cfx_excp_cause_nonmaskable_for()`/`cfxExcpCauseNonmaskableFor()`
  逐 cfx 独立重读 wiki §4 异常原因表核对，发现并记录任务原文对
  cfx_tlb"8个原因"的欠计（wiki 表格实际 10 项），未凭记忆行事。
- 探针开发过程中先后遇到并定位修复了两类真实 bug（非测试脚本笔误）：
  （1）`dadao_cfx_dispatch()` 判定门阻塞（无入口）时调用方若无条件
  `cpu_loop_exit()`，会造成同一指令被无限重新取指——已改为返回 bool
  并在 TEST-ONLY 触发器分支正确判断；（2）持续电平源+自目标绕过
  steps3-4 造成的 handler 自重入，通过"安全区预加载寄存器+atomic
  第一条指令屏蔽写+显式修复 prev_cfx_mask"收敛，属架构真实属性
  （cfx2rc 值恒为寄存器来源，构造掩码值需≥1条额外指令，指令边界精确
  检查下这构成真实竞争窗口），已在场景B文档与代码注释中详细记录，
  不是"凑绿"式规避。
- 范围未扩展到 timer/UART 真实设备（KL-133a/137a）或
  `switch_run_mode`/`switch_cfx_mask` 写支持。

### 独立 subagent 审阅记录

Reviewer 结论：**PASS**（代码正确性无阻塞项）。独立复核内容：

1. 独立重读 wiki §DADAO-12-SEE 全部相关行号，逐 cfx 核对 nonmaskable
   表构造，确认与实现完全一致（含独立验证 cfx_tlb 10 项而非任务原文
   "8"项）。
2. 逐行比对 QEMU `dadao_cfx_dispatch`/`dadao_cfx_cause_eligible` 与 gem5
   `ISA::cfxDispatch`/`ISA::cfxCauseEligible`，确认算法结构完全对称
   （屏蔽检查顺序、两遍 ILLI 重定向重试、步骤6计数器选择规则）。
3. 独立确认 `cg0-3/rc1` 共享寄存器实现两端均忽略 cfxcode 操作数。
4. 独立枚举 QEMU `dadao_cfx_dispatch()` 全部 5 个调用点，逐一核对
   返回值处理正确性（3 处数学上恒不可屏蔽故可忽略返回值，TEST-ONLY
   触发器正确检查返回值避免无限重取指）。
5. 独立核对 gem5 全部 5 个调用点的 `stageSequentialAdvance` 参数取值
   语义正确性。
6. 通读探针脚本全文，手工验算 `craft_inner_cfx_mask` 地址算术
   （`assert` 断言）无 off-by-one；确认场景A/B 断言具备真实区分力
   （非平凡恒真、非零输入陷阱）。
7. 独立重跑：`run_kl131a_async_dispatch_probes.py`（131/131、132/132）、
   `run_kl120a_cfx_carrier_probes.py`、`run_kl122a_generic_carrier_probes.py`
   （零回归）、`llvm-lit tests/lit/E2E/`（81/81）、
   `tools/run_differential.py`（AGREE(3-way)=200/DIVERGE=0，
   AGREE(4-way)=200/SAIL-DIVERGE=0）、`manifest_check.py`、
   `check_issues.py`（均 PASS）。

非阻塞发现（已处理）：探针脚本中 `craft_inner_cfx_mask` 函数被定义两次
（旧版本死代码，Python 静默使用后定义覆盖前定义，不影响正确性但影响
可读性）——已删除死代码，删除后重跑确认 131/131、132/132 不变。

Reviewer 全程只读，未修改文件。

### 架构师独立复核（2026-07-27）

**结论：PASS，无需修改。**

- 独立读取 QEMU/gem5 全部 diff（`cpu.c`/`cpu.h`/`helper.c`/`translate.c`；
  `isa.hh`/`isa.cc`/`decoder.cc`/`faults.hh`/`faults.cc`/`interrupts.hh`/
  `tlb.cc`）。
- 独立重读 wiki 验证 `dadao_cfx_excp_cause_nonmaskable_for()`（QEMU）/
  `cfxExcpCauseNonmaskableFor()`（gem5）逐 cfx 的位掩码：umon/jmon/smon/
  hmon（僅 FPEXCP 可屏蔽）、cfx_ptw（18项全不可屏蔽）、cfx_tlb（10项全
  不可屏蔽，独立确认任务文件原文"8"确系欠计）、cfx_hart（僅 IPI 可屏蔽，
  独立读取 wiki `cfx_hart` 异常原因表核实第8位 IPI 确为"可"屏蔽）、
  cfx_power（僅 SOFT_RESET 可屏蔽）——均与 wiki 原文逐位一致。
- 独立核对 `dadao_cfx_async_scan()`/`ISA::cfxAsyncScan()` 的优先级算法：
  按 cfxcode 升序扫描、每个 cfx 内取最低置位且当前 eligible 的原因位
  （非全局最低置位位规则）——与 `contracts/isa/spec.md` §8.5.1 冻结的
  "先最低 pending 且未屏蔽的 cfxcode，同 cfx 内再选最低已置位原因位"
  完全一致。
- 独立核对 `cause_ip` 时序：QEMU `dadao_cpu_do_interrupt()`的
  `EXCP_CFX_ASYNC` 分支在 `cpu_exec_interrupt` 钩子内、下一条指令对应
  TB 开始前读取 `env->pc`；gem5 `AsyncInterruptFault::invoke()` 在
  `BaseSimpleCPU::checkForInterrupts()`（fetch 之前）读取
  `tc->pcState().instAddr()`——两者在各自模拟器生命周期里都精确等于
  "下一条指令地址"，与 wiki 异步 cause_ip 规则一致。
- 独立重建 QEMU/gem5（干净编译，无新增警告），独立重跑
  `run_kl131a_async_dispatch_probes.py`（131/131、132/132，与声明一致）
  和全部既有 K1 探针（`kl113a`/`kl117a`/`kl120a`/`kl122a`/`kl124a`/
  `kl125a`/`kl126a`/`kl127a`/`kl129a`）——零回归，数值与各自基线完全
  一致。
- 独立重跑全量 `llvm-lit tests/lit/E2E/`（81/81）、
  `tools/run_differential.py`（AGREE 3-way=200/4-way=200，DIVERGE=0）、
  `manifest_check.py`、`check_issues.py`、`check_wiki_refs.py --profile
  isa`、`check_wiki_drift.py`——全部 PASS，与完成区声明一致。
- 独立执行 QEMU/gem5 patch-series bare-pin replay（`git worktree add
  --detach` 到 manifest pin，`git am` 全部 patch）：QEMU 32/32、tree
  hash `617d4d561f351facefc21c6854d867469fd0aa1b`；gem5 26/26、tree
  hash `f5d569bd99ecbc7b91aba52d0ff9d455d70af82f`——均与开发树及完成区
  声明完全一致。临时 worktree 已清理。
- `docs/development-roadmap.md` 的 KL-131a 条目按既定惯例精简为短摘要+
  指向本任务完成区（原始版本偏长，已改写）。
- 未发现需要修改代码的问题；两处子agent自审记录中的真实 bug 发现（判定门
  阻塞时无条件 `cpu_loop_exit()` 导致无限重取指；持续电平源+自目标绕过
  steps3-4 的 handler 自重入架构属性）均已正确定位修复并有充分文档。
