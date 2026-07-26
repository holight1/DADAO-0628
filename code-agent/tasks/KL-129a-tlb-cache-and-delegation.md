# KL-129a：cfx_tlb 缓存 + 失效 + 命中故障委托（QEMU + gem5）

**执行环境**：远端 Codex（本仓库），QEMU 源码改动
（`.work/source/qemu`）+ gem5 源码改动（`~/DADAO-gem5`，独立仓库）

**依赖**：`KL-127a`（PTW 故障入口+A/D 位，本任务的 miss-path 硬件 walk
复用它）。若下发时 `KL-127a` 尚未完成，本任务暂不能开工——先完成
`KL-127a` 再做这个。

## 背景

`KL-125a`/`KL-126a`/`KL-127a` 已实现 `cfx_ptw` 的完整硬件 walk（成功+
故障+A/D）。wiki 定义了一层 `cfx_tlb`（第463-495行）：64 个逻辑集合
（按 `VA[47:42]` 即 PTBR index 分组），命中时直接检查缓存的 PTE 的
SPF/GPF 和 R/W/X（不重新 walk），未命中时走完整硬件 walk 并把结果填入
对应集合。`KL-119a` 已冻结 K1 的 TLB 测试 profile（`contracts/isa/spec.md`
§8.5.3）：全部 64 个集合存在（`cfx_tlb_exist=UINT64_MAX`），每集合
16 路全相联、真 LRU 替换——这是测试 profile 选择，不是性能声明。

`KL-118a` 调研当时认为 `cfx_tlb→cfx_ptw→cfx_tlb` 的嵌套委托返回契约
未闭环（阻断委托测试）。**这个阻断已被解除**：`KL-119a`/`KL-120a` 冻结
并实现的 E1（`excp_prev_cfx_code`，`contracts/isa/spec.md` §8.5.5）明确
覆盖的正是这个"单层嵌套返回"场景（"exactly what SBI's `cfx_tlb ->
cfx_ptw -> cfx_tlb` example does"）。因此本任务**必须**实现并验证真实的
`trap cfx_ptw` 嵌套委托 + 返回后 `escape cfx_tlb,0` 恢复，不能再用
"委托契约未闭环"当理由跳过。

## 目标

### 1. 寄存器存储（QEMU + gem5）

- `cg8/rc0`：`cfx_tlb_exist`（RO，K1 profile 全1）。
- `cg8/rc8`：`cfx_tlb_enable`（RW，复位值等于 `cfx_tlb_exist`）。
- `cg12/rc0`：`cfx_tlb_control`（WO，bit0=invalidate all，bit1=invalidate
  by addr range）。
- `cg12/rc2`：`cfx_tlb_addr_start`（RW）。
- `cg12/rc3`：`cfx_tlb_addr_size`（RW，复位值65536）。

### 2. 缓存查找/填充（QEMU + gem5）

按集合（`VA[47:42]`）+ 集合内索引键（superpage 用 L1 index、normal page
用 L1+L2 index 组合）组织，16 路全相联 + 真 LRU（`KL-119a` 冻结的
K1 test profile）：

- `cfx_tlb_enable` 对应集合位为0：跳过 TLB，直接走 `KL-127a` 的硬件
  walk（现有行为不变）。
- 使能且命中：直接用缓存的 PTE 检查 SPF/GPF 和 R/W/X（不重新访存读
  PTE）——失败时触发 `cfx_tlb` 自己的故障（见下），不是 `cfx_ptw` 的。
- 使能但未命中：调用 `KL-127a` 的硬件 walk；walk 本身产生的故障（mode
  perm、present 缺失等）按 `KL-127a` 的路由进 `cfx_ptw`（本任务不改这条
  路径）；walk 成功后把结果（含 A/D 更新后的 PTE 内容）填入对应集合
  （LRU 满时按 LRU 淘汰，不需要写回被淘汰条目——PTE 本身已经在
  `KL-127a` 的 walk 里同步回写过主存）。

### 3. TLB 命中故障（QEMU + gem5）

`cfx_tlb` 自己的异常原因表（wiki 第482-495行）共有 10 项：通用的
`CFXTRAP`/`CFXMEM`/`CFXREG` 加上 hit 专有的 `NXPERM`/`NWPERM`/
`NRPERM`/`IGPFTRAP`/`ISPFTRAP`/`DGPFTRAP`/`DSPFTRAP` 7 项。TLB hit
本身实际产生后 7 项；不包含 mode-perm 或 present 缺失（那些只在硬件
walk 里，属于 `cfx_ptw`）。命中但 fragment/权限检查失败时，
入口目标是 `cfx_tlb`（cfxcode=5，wiki 步骤1伪代码 `elif from_tlb:
temp_cfx_code <= 5`），复用 `KL-127a`/`KL-122a` 已有的精确异常入口
carrier，不新造机制。

### 4. 失效（QEMU + gem5）

`cfx_tlb_control` 写入触发：bit0 invalidate-all 清空全部64个集合；bit1
invalidate-by-range 只清 `cfx_tlb_addr_start[47:42]` 指定集合内、
`cfx_tlb_addr_start[41:16]`+`cfx_tlb_addr_size` 覆盖范围的条目。

### 5. TLB→PTW→TLB 委托验证（QEMU + gem5）

构造真实的嵌套场景：`cfx_tlb` handler 因 present 缺失类故障（这类故障
只能从 walk 产生，需要先让 TLB miss 后 walk 触发）或直接构造一个
"TLB hit 但 fragment=0" 场景触发 `cfx_tlb` 自身故障，handler 内
`trap cfx_ptw` 委托处理（例如调用 PTW 侧的 fault-handling 服务），
`escape cfx_ptw,0` 返回后 `inner_cfx_code` 应借助 E1 恢复为 `cfx_tlb`，
再 `escape cfx_tlb,0` 完成最终返回——验证这条链路整体可用。

## 约束

- **不实现 Linux 分页策略**——handler 逻辑只是验证委托返回机制正确，
  不代表真实内核会怎么处理缺页。
- **不新造异常入口机制**——复用 `KL-122a`/`KL-127a` 已有 carrier。
- **不改动 `KL-125a`/`126a`/`127a` 的硬件 walk 本体**——本任务只是在它
  外面加一层缓存和命中检查，miss 后仍然完整调用现有 walk。
- 16路/LRU 只是 K1 测试 profile（`KL-119a` 已冻结），不要声称是性能/
  微架构结论。
- QEMU 与 gem5 两侧对同一操作序列（hit/miss/invalidate/nested fault）
  要给出一致结果。
- 完整 patch-series bare-pin replay（tree-hash 比对），QEMU/gem5 分别做。
- 完成后写「完成区」+ 自审记录，继续沿用"自己开 reviewer subagent
  复核"的方法。
- 现有全部探针零回归（O1/O2/O3/`KL-120a`/`KL-122a`/`KL-124a`/`KL-125a`/
  `KL-126a`/`KL-127a`）。

## 验收

- hit（权限/fragment 通过）、hit-fault（fragment=0 和 R/W/X 不符各至少
  一例）、miss-then-fill、invalidate-all、invalidate-by-range 五类场景
  各至少一个判别性探针（非零索引/非零 fragment，避免假绿）。
- 真实 `cfx_tlb→cfx_ptw→cfx_tlb` 委托返回链路至少验证一次，确认 E1
  让 `inner_cfx_code` 正确恢复、两层 `escape` 都精确返回。
- 现有全部探针零回归。
- 全量 lit E2E、`tools/run_differential.py`、`manifest_check.py`、
  `check_issues.py` 无回归。
- patch-series bare-pin replay，QEMU/gem5 tree hash 分别与各自开发树
  一致。

## 参考指针

- `contracts/isa/spec.md` §8.5.3（K1 TLB 测试 profile）、§8.5.5（E1，
  本任务依赖的委托返回机制）
- `~/DADAO-wiki/DADAO-12-SEE-主管系统运行环境.md` 第463-495行（`cfx_tlb`
  专有寄存器表+异常原因表）、第83-105行（TLB 查找步骤，SEE §2.2 第二步）
- `~/DADAO-wiki/DADAO-22-SBI-主管系统二进制接口.md` 第353-372行
  （`cfx_tlb→cfx_ptw→cfx_tlb` 委托示例）
- `code-agent/tasks/KL-127a-ptw-fault-and-ad-bits.md` 完成区（硬件 walk
  的故障分类实现，本任务 miss-path 直接复用）
- `code-agent/tasks/KL-120a-*.md` 完成区（E1 的 `excp_prev_cfx_code`
  实现细节）

---

## 完成区（2026-07-26）

**状态：worker PASS，等待主 agent 独立验收。**

### 实现

- QEMU `d32ceed48010ead30274cb8d36d1843125abfbab`：
  在 KL-127 walker 外层增加 64 sets × 16-way 架构 TLB。entry 缓存
  super/normal tag、A/D 后 PTE、leaf PTE 地址和物理页基址；hit、fault
  hit 和 fill 都更新全局单调时钟，实现真实 LRU。QEMU host softmmu
  仍在 PTW enable 时逐指令 flush，架构命中不会被 host cache 绕过。
- gem5 `45fef8c02f96aceb5cfeefc5f02cbed2ed59b3b4`：
  `ISA::mmuTranslate()` 与 QEMU 按相同顺序执行 mode/enable、lookup、
  fragment、permission、A/D、fill/LRU；FullSystem `TLB` 根据返回的
  source cfxcode 精确进入 `cfx_ptw` 或 `cfx_tlb`。
- 两端均实现 `cfx_tlb_exist`、`enable`、`control`、`addr_start`、
  `addr_size`。invalidate-all 清 64 个集合；range 只在 start 指定集合
  内按 super 512 MiB / normal 64 KiB 区间相交清除，控制写同时清 QEMU
  host TLB。
- hit 权限/fragment 判断只使用缓存 PTE；A/D 的内存可见更新单独对当前
  leaf PTE 做 RMW，只合并 A/D 位，不让陈旧缓存覆盖软件更新的其他位。
  这也保留了 KL-127 的 clear-A/clear-D 后重访语义。
- `trap cfx_ptw` 作为 SBI 风格功能调用进入现有 carrier，frame 的
  `cause_ip` 为 trap 后顺序 PC；因此 `escape cfx_ptw,0` 返回下一条，
  E1 恢复调用者 `cfx_tlb`，之后 `escape cfx_tlb,0` 可重试原访存。
  未新增 carrier 或多帧 shortcut。

### cause 口径

wiki `cfx_tlb` 表是 **10 项总表**：3 个通用 CFX 原因加 7 个
TLB-hit 专有原因。本任务逐条实现/验证 7/7 hit-generated cause；
`CFXTRAP` 在真实 `trap cfx_ptw` 委托中验证，`CFXMEM`/`CFXREG` 不是
TLB lookup 的 permission/fragment 分支，未伪造成 hit fault。

### 判别性验证

新增 `tests/scripts/run_kl129a_tlb_probes.py`，13 个场景均由 guest
逐值检查后才允许 halt 42，QEMU/gem5 结果完全一致：

- register reset/readback、normal miss-fill + stale-PTE hit；
- `enable=0` 绕过、invalidate-all、只命中目标 64 KiB entry 的
  invalidate-range；
- 同集合填 16 路、touch way0、填第17路后证明 way1 被淘汰且 way0
  保留的 true-LRU 场景；
- `NXPERM/NWPERM/NRPERM/IGPFTRAP/ISPFTRAP/DGPFTRAP/DSPFTRAP`
  7/7 hit cause，handler 内核对 cause id、原始 VA 与精确 fault IP；
- 真实 `cfx_tlb→trap cfx_ptw→escape ptw,0→cfx_tlb→escape tlb,0`
  链路，PTW frame 内核对 `CFXTRAP`、raw trap、顺序 cause IP 和
  `prev_cfx_code=5`，修 PTE+range invalidate 后原 STO 成功重试。

最终输出：
`PASS: 13 probes; ... 7/7 hit causes + TLB->PTW->TLB E1; QEMU=gem5`。
52 份 ROM/RAM/逐后端日志证据在 `.work/evidence/kl129a-tlb/`。

### 回归与可重放性

- QEMU/gem5 构建 PASS（仅既有 warning）。
- KL-120a：`44/44, 130/130, 7x45/45, 43/43`；KL-122a：
  `46/46`；KL-124a FullSystem 全矩阵与 SE 一致。
- KL-125a QEMU `8/8`；KL-126a gem5 `8/8`；KL-127a：
  `30 fault + 10 A/D` 全部 QEMU=gem5=42。
- E2E `81/81 PASS`。
- differential：三路 `AGREE=200, gem5-SKIP=2, DIVERGE=0`；
  四路 `AGREE=200, Sail-SKIP=2, SAIL-DIVERGE=0`。
- `manifest_check.py PASS`；`check_issues.py PASS`
  （Open 24 / Closed 43 / Total 67）；三棵工作树 `diff --check PASS`。
- stable patch-id：
  QEMU `b4bd61286929f33d036a09667c5f0fade1a6b8c3`；
  gem5 `2aac796b6c71532957b8d7d1f1bfb8ddec62ab8a`。
- bare-pin plain `git am`：
  QEMU 31/31，replay/dev tree 均为
  `955ebe684451e360198e8e0c563234ceee04164e`；
  gem5 25/25，replay/dev tree 均为
  `4c2f42d9e21d4c43c876fa05aef3ba07a05bb68b`。

### 自审记录

- 逐位核对两端 set/tag、super/normal offset、fragment 位、R/W/X 位、
  cause 常量、LRU touch/fill、range-overlap 和 A/D RMW，未发现不对称。
- walker 本体仅增加两个成功输出（A/D 后 PTE 与 leaf 地址）；所有失败
  分类和 miss-path carrier 保持 KL-127 原逻辑。
- runner 曾发现 nested handler 在 retry 前未恢复 faulting STO 的
  `rd2/rb3` 活跃操作数；修复后双后端真实写入并返回 42。这个失败证明
  探针不是只看两层 escape 日志的假绿。
- 按 worker 派发约束未启动 reviewer subagent；独立 review 留给主
  agent。

### 架构师独立复核（2026-07-27）

**结论：PASS（发现并修复一处 cause_ip 语义偏差后通过）。**

- 独立读取 QEMU/gem5 全部 diff，逐条对照 wiki §2.2.3/§2.2.4/第442-495行
  的 PTE 位域和 `cfx_tlb` 异常原因表，未发现算法本体问题；两端结构
  对称。
- 独立重建 QEMU/gem5，重跑 13/13 探针、KL-120a/122a/124a/125a/126a/127a
  全部回归、全量 lit E2E（81/81）、`run_differential.py`（200/200）、
  `manifest_check.py`/`check_issues.py`，结果与完成区声明逐项一致。
- **发现问题**：`trap cfx_ptw` 委托调用（`cfx_tlb→cfx_ptw`）把
  `cause_ip` 设成了 trap 指令**之后**一条指令的地址（QEMU `env->pc`
  未减4；gem5 `pc.instAddr()+4`），而 wiki SEE §5 步骤9明确"同步异常
  为触发指令地址"——CFXTRAP 是同步异常，`cause_ip` 应为 `trap` 指令
  **自身**地址，与本仓库已有的 `cfx_smon` CFXTRAP 先例（`KL-116a`，
  `env->pc - 4`）完全一致。这导致探针里 `escape cfx_ptw, 0`（wiki 定义
  为"重新执行触发异常的指令"）实际表现成了"跳过触发指令"（wiki 定义
  的 `escape cfx_ptw, 1` 语义）——数值上凑巧算对了返回地址，但违反了
  wiki 对 escape 操作数含义的定义，且与 `KL-116a` 已确立的
  `escape cfx_smon, 1`（trap-as-call 场景下正确的"跳过"写法）不一致，
  未作为 spec-decision 记录。
- **修复**（QEMU `target/dadao/cpu.c`、gem5
  `src/arch/dadao/decoder.cc`，各一行语义改动+注释）：`cause_ip` 改回
  `trap` 指令自身地址（QEMU `env->pc - 4`；gem5 `pc.instAddr()`，不再
  `+4`），probe 相应把 `excp_cause_ip` 期望值从 `trap_offset+4` 改回
  `trap_offset`、把返回用的 `escape cfx_ptw, 0` 改成
  `escape cfx_ptw, 1`（与 `KL-116a` 的 `escape cfx_smon, 1` 同一惯例）。
  两处改动均已 amend 进原 KL-129a commit（未新增独立 commit，因为这是
  提交前的语义修正，不是既成事实的追加变更）。
- **修复后独立复核**：13/13 探针（含 `nested-tlb-ptw-tlb`）、全部回归、
  E2E、differential、manifest/issues 全部重新通过；bare-pin replay
  重新执行，tree hash 仍与开发树完全一致
  （QEMU `cfdd97ed45459278fb1606d920a091da0db9b474`，
  gem5 `7d050393526439eabac37b3194230467630eec11`）。
- 修复后最终 commit：
  QEMU `599efb6c19f66b2846e4be8ab8084890e5e65679`
  （patch-id `7aedb2fecd9227ec5cd277ab9903448ab82a0f60`）；
  gem5 `1092fa331b29b80b95bee93df9d0a09a12a7b1e5`
  （patch-id `512dc1baa4ab41ca9780de0022a95677e772baca`）。
- 只改了 `cause_ip` 计算这一处；A/D、fault分类、LRU、invalidate等其余
  实现原样保留，未发现其它问题。
