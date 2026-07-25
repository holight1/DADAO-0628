# KL-117a：O3（`trap cfx_smon` 真实进入流程）移植到 gem5

**执行环境**：远端 Codex（本仓库），gem5 源码改动（`~/DADAO-gem5`，
非 `.work/source/gem5`——两者不是同一 checkout，`.work/source/gem5`
只是裸 pin replay 验证用的一次性 clean-room，开发在 `~/DADAO-gem5`
里做，这是 `KL-109a`/`KL-113a` 已确立的惯例）

## 背景

O3（移交后真实受控操作：`trap cfx_smon`→guest handler→`escape` 往返）
已经在 QEMU 完整实现并独立验证（`KL-115a` 调研 + `KL-116a` 实现，
QEMU commit `8dc9d5a`）。本任务把同样的语义移植到 gem5——延续
`KL-110a`/`KL-112a`(QEMU O1/O2) → `KL-113a`(gem5 移植) 的先例节奏。

**gem5 当前状态**（`KL-113a` 已经把 O1+O2 设计1/3 移植过，本任务在此
基础上继续）：`src/arch/dadao/isa.hh`/`isa.cc` 已有 `RunMode` 枚举、
`CfxCodePower`/`CfxHypvCgRegDelegCg/Rc`/`CfxMaskRegEscape` 常量、
`CfxPowerFrame` 结构体，`ISA` 类已有 `innerRunMode`/`innerCfxCode`/
`innerCfxMask`/`cfxPowerFrame`/`cfxHypvCgRegDeleg[64]`/
`cfxEscapeCfxMask[64][4]` 六个字段；`decoder.cc` 已有 `CFX2RCInst`
(`0x73`)/`EscapeInst`(`0x77`)；`TrapInst::execute()`
（`decoder.cc:703-` 附近）目前对 `cfxcode==2` 无条件执行 host/SE
syscall 直通捷径（与 QEMU `cpu.c:157` 改动前完全同构），其它 cfxcode
静默 `return NoFault`（注意：这一点和 QEMU"未知 cfxcode→0x82 panic"不
完全对称，是 gem5 侧早已存在、与本任务无关的既有差异，不用管）。

**QEMU KL-116a 的确切实现是本任务的语义参照物**（不是重新设计）：
`.work/source/qemu/target/dadao/{cpu.h,cpu.c,helper.c,helper.h,
translate.c}`，commit `8dc9d5a3c39856b70f718ec0075e0110c9078852`。
关键结论（架构师已独立复核确认属实，直接复用不用重新调研）：

1. wiki 异常进入流程步骤2-6（不可屏蔽判断/`inner_cfx_mask`/
   `global_cfx_mask`/`excp_cause_mask`/陷入计数）对 `trap cfx_smon`
   场景可合法整体跳过——`CFXTRAP` 对 `cfx_smon` 硬件固化为不可屏蔽
   （wiki `DADAO-12-SEE-主管系统运行环境.md:402/419`），步骤6无存储
   基础设施（类比 `escape_num`）。
2. 真正的核心是步骤7-10：保存现场→模式切换→保存异常信息→跳异常向量。
3. `trap` 的 `cfxcode==2` 分支和现有 host/SE 捷径互斥，需要一个默认
   关闭的开关来区分——**QEMU 侧用了 CPU 属性
   `cfx-smon-real`（QOM `Property`，默认 `false`）**。gem5 目前没有
   任何等价的 Param 机制用于这个 arch（`DADAOISA.py`/`DADAOCPU.py`
   都还没有定义任何 `Param`）——这是本任务需要新建的部分，具体走
   `DADAOISA`（SimObject，`isa.hh` 的 `ISA::Params` 目前只是转发声明
   `DADAOISAParams`，从未真正使用过）还是 `DADAOCPU`
   （`DADAOAtomicSimpleCPU`/`DADAOO3CPU` 等 SimObject 类）挂这个开关，
   由你决定——**目标是"默认关闭时行为与现在完全一致，打开时
   `TrapInst::execute()` 对 `cfxcode==2` 改走真实进入流程"**，具体
   gem5 Param 布线方式（`.py` 文件加 `Param.Bool`、C++ 侧
   `ISA::Params`/`BaseCPUParams` 消费）不是本任务文件要规定的实现细节，
   由你按 gem5 既有惯例判断。

## 目标

1. **新增开关**（gem5 等价于 QEMU `cfx-smon-real` CPU 属性，默认
   `false`）。默认关闭时 `TrapInst::execute()` 现有的 `cfxcode==2`
   host/SE 捷径逻辑一行不改、行为逐字节不变。
2. **新增 `cfx_smon` 专属异常现场帧**（`ISA` 类新字段，镜像 QEMU
   `DADAOCfxSmonFrame`：`prevRunMode`/`prevCfxMask`/`causeId`/
   `causeIp`/`causeInfo` 五字段，比 `CfxPowerFrame` 多 `causeId`/
   `causeInfo` 两个——QEMU 侧这两个字段是本 O3 系列第一次有任何 cfx
   拥有过的 HW-only 字段存储）。
3. **新增 `cfxSmonSupvExcpVector` 的 `cfx2rc` 写入支持**（`(cg,rc)=
   (2,10)`，`CFX2RCInst::execute()` 新增一支，镜像 QEMU
   `helper_cfx2rc` 的 `(cfxcode==DADAO_CFX_CODE_SMON, cg==2, rc==10)`
   分支）。
4. **实现真实 `trap` 进入流程状态机**（开关打开、`cfxcode==2` 时，
   逐步镜像 QEMU `dadao_cfx_smon_trap_enter()`）：
   - 跳过步骤2-6（同 QEMU 理由）。
   - 步骤7：`cfx_smon` 帧的 `prevRunMode<=innerRunMode`、
     `prevCfxMask<=innerCfxMask`（切换前）。
   - 步骤8：`innerRunMode<=Supv`（wiki `switch_run_mode` 默认值）、
     `innerCfxMask<=全1`（wiki `switch_cfx_mask` 默认值）、
     `innerCfxCode<=CfxCodeSmon`（新增常量，值2）。
   - 步骤9：`causeId<=CFXTRAP`(`1<<0`)、`causeIp<=` 触发 `trap` 的
     指令自身地址、`causeInfo<=` 该 `trap` 指令的原始32位编码（gem5
     侧需要把原始指令字从 `decode()`/`TrapInst` 构造函数一路带到
     `execute()`——QEMU 是在 `translate.c` 新增一个 `ctx->opcode`
     参数传给 helper，gem5 的等价做法是在 `TrapInst` 构造时多存一个
     `rawInsn` 字段，`decoder.cc` 的 `decode()` 分派处传入解码用的
     完整指令字）。
   - 步骤10：`pc<=cfxSmonSupvExcpVector`（用 `PCState` 设置，同
     `EscapeInst` 已有的跳转写法）。
5. **`EscapeInst::execute()` 恢复分支扩展**：新增 `cfxcode_ ==
   CfxCodeSmon` 分支，从 `cfx_smon` 帧恢复 `prevRunMode`/
   `prevCfxMask`/`causeIp`（`causeId`/`causeInfo` 不参与恢复，同
   `cfx_power` 既有惯例）。

## 约束

- **只做 QEMU KL-116a 已实现的部分**，不要扩大范围（不做候选A、O2
  设计2、`trap_cfx_mask` 通用检查、`cfxld`/`cfxst`/`cfx2rd`、MMU/TLB、
  多层嵌套 trap）。
- **不要修改 `TrapInst::execute()` 里 `cfxcode==2` 捷径本身的任何现有
  行为**——开关关闭时必须逐字节不变，这是硬性验收项。
- 状态转换逻辑集中在 `TrapInst`/`EscapeInst`/`CFX2RCInst` 的
  `execute()` 里（gem5 这个 arch 是手写 decoder，没有 QEMU 那种
  translate/helper 两层分离，`execute()` 本身就是唯一的状态转换点，
  同 `KL-113a` 已确立的写法）。
- 完整 patch-series bare-pin replay（tree-hash 比对）是硬性验收项，
  patch 落 `components/gem5/patches/`。
- 完成后写「完成区」+ 自审记录；不需要嵌套 subagent。
- gem5 SE 模式没有 bare-metal reset vector 概念——验证方式参照
  `KL-113a` 的先例（独立写一个够用的 SE 探针 runner，复用/改造 QEMU
  侧 `gen_kl116a_o3_probe.py` 的裸指令流，只重新计算跳转目标基址，
  不强求和 QEMU 探针字节级一致）。

## 验收

- **开关默认关闭**：gem5 侧现有 lit E2E 后端（`GEM5_SE`）、
  `tools/run_differential.py` 全部零回归。
- **开关打开时的 O3 探针**（镜像 QEMU 侧已验证的 A/B 对照）：
  - 关闭：走现有 host/SE 捷径，观测不到"真实进入流程"的 trace/状态
    变化（同 QEMU exit=0x99 的负例对照逻辑）。
  - 打开：`inner_run_mode` 保持 supv、`inner_cfx_code` 变成 `smon`
    （第一次非 `power` 的值）、PC 落在 `cfxSmonSupvExcpVector`；
    guest handler 往返后 `escape cfx_smon,1` 精确落地
    `causeIp+4`；全程不调用任何 host/SE syscall API。
- 完整 patch-series bare-pin replay，tree hash 与开发树一致。
- 现有 gem5 相关 lit E2E、`run_differential.py` 数字不变。

## 参考指针

- `.work/source/qemu/target/dadao/{cpu.h,cpu.c,helper.c,helper.h,
  translate.c}`（QEMU commit `8dc9d5a3c39856b70f718ec0075e0110c9078852`，
  本任务的确切语义参照物）
- `code-agent/tasks/KL-116a-cfx-smon-o3-real-entry-qemu.md` 完成区
  （QEMU 实现细节、wiki 引用行号、A/B 探针设计与验证方法论）
- `code-agent/tasks/KL-113a-implement-hypv-supv-handoff-gem5.md`
  完成区（gem5 CFX 状态容器的既有设计决策、carrier-point 写法、
  gem5 SE 探针验证先例）
- `docs/reviews/kernel-cfx-smon-o3-recon-20260725.md`（KL-115a，O3
  精确范围来源）
- `~/DADAO-gem5/src/arch/dadao/{isa.hh,isa.cc,decoder.cc,DADAOISA.py,
  DADAOCPU.py}`（当前 gem5 dadao arch 现状，`TrapInst`/`CFX2RCInst`/
  `EscapeInst` 是本任务的直接落脚点）
- `~/DADAO-wiki/DADAO-12-SEE-主管系统运行环境.md` 第678-811行（完整
  异常进入流程）、第351-364行（cg5 异常现场表）、第313-330行（cg2/
  supv 表）、第396-419行（`cfx_umon`/`cfx_smon` 异常原因表）

---

## 完成区（2026-07-26）

### 实现结果

已在开发 checkout `~/DADAO-gem5` 完成 KL-117a，范围严格限定为
KL-116a 已实现的 O3 子集：

1. `DADAOISA.py` 新增默认 `False` 的 `cfx_smon_real` ISA Param；
   `ISA` 构造时固化为只读配置 `cfxSmonReal`。`tests/dadao/dadao_se.py`
   新增显式 `--cfx-smon-real` 测试入口，未传参数时仍显式使用默认关闭
   配置。
2. 新增 `CfxCodeSmon=2`、`CfxCauseCfxtrap=1<<0`、
   `CfxSmonFrame` 五字段和 `cfxSmonSupvExcpVector`；`clear()` 按 QEMU
   KL-116a 的 reset 值清零，`copyRegsFrom()` 搬运全部新增架构状态，
   但不搬运只读配置开关。
3. `CFX2RCInst` 支持 `(cfxcode,cg,rc)=(2,2,10)`，写入值按 48 位地址
   截断。
4. `TrapInst` 保存完整 32 位原始指令。默认路径保留原有顺序
   `advancePC()`（独立 review 后修正，避免破坏 O3 front-end 的顺序取指
   契约）；真实入口把 vector 预置为 NPC，使同一次通用推进后精确落到
   vector。开关关闭时既有 `if (cfxcode == 2)` host/SE syscall 分支内部
   代码未改；开关打开时，在进入该分支前完成保存 mode/mask、切换
   Supv/all-ones/smon、写入 `causeId/causeIp/causeInfo` 并跳向量。
5. `EscapeInst` 新增 smon frame 恢复分支，恢复 trap 前 mode/mask，并
   按 `causeIp + imm*4` 返回；未实现通用 mask、嵌套 trap、MMU/TLB、
   其它 cfx 帧或候选设计。

### 判别性 A/B 探针

新增 `tests/scripts/run_kl117a_gem5_probe.py`。它直接复用
`gen_kl116a_o3_probe.py` 的指令流，仅把 QEMU ROM 基址重定位到 gem5
SE ELF 基址，并映射 guard/handler marker 页。证据保存在
`.work/evidence/kl117a-probe/`：

- profile off：guest exit `153 (0x99)`；无
  `dadao: trap cfx_smon` trace；`rd31=0xffffffffffffffda`
  （既有 host shortcut 的 `-ENOSYS`），handler marker 未写。
- profile on：guest exit `43`；handler 把 `0x1234/0x5678` 写回 marker；
  `rd31=0`；探针把 trap 前 mask 特意设为
  `0x0123456789abcdef`（非 all-ones 判别值）；进入 trace 精确为
  `mode 2->2, inner_cfx_code=2, cause_id=1,
  cause_ip=0x80000234, cause_info=0x76080000,
  vector=0x80000400`；escape trace 精确返回
  `0x80000238 = causeIp+4`，并恢复
  `mask=0x0123456789abcdef`。

这组 A/B 使用同一个 ELF；唯一变量是 ISA Param，因而能区分默认
host/SE 捷径与真实 guest handler 往返。

### 构建与回归

- `scons build/DADAO/gem5.opt -j4`：PASS（仅 gem5 既有可选依赖和
  decoder warning）。
- `python3 tests/scripts/run_kl117a_gem5_probe.py`：PASS，off=`0x99`，
  on=`43`。
- `python3 tests/scripts/run_kl113a_gem5_probes.py all`：PASS，O1、
  design1、design3、O1-regression 的结果仍为 `42/130/134/42`。
- `.work/build/llvm/bin/llvm-lit -sv tests/lit/E2E/`：`81/81 PASS`。
- `python3 tools/run_differential.py`：
  `AGREE(3-way)=200`、`gem5-SKIP=2`、`DIVERGE=0`；
  `AGREE(4-way)=200`、`Sail-SKIP=2`、`SAIL-DIVERGE=0`，与 KL-113a
  记录口径一致。
- `python3 scripts/manifest_check.py`：PASS。
- `python3 scripts/check_issues.py`：PASS（Open 24 / Closed 43 /
  Total 67）。
- gem5 与根仓库 `git diff --check`：PASS。

### patch series 与可重放性

- gem5 commit：
  `e877c5aaee50a8c8ec879aa0be90a94fdbf92007`
  （`arch/dadao: implement real cfx_smon trap entry (KL-117a)`）。
- 导出 patch：
  `components/gem5/patches/0019-arch-dadao-implement-real-cfx_smon-trap-entry-KL-117.patch`，
  并作为第 19 项加入 `components/gem5/patches/series`。
- commit 与导出 patch 的 stable patch-id 均为
  `ab682ab3fe680be70ae9d5bb373de87f2875f273`。
- 从 manifest pin
  `c8222cc67a399bfc01e8658dd14b30d5bfd634f9` 创建独立 detached
  worktree，按 series plain `git am` 全部 19 个 patch：`19/19 PASS`；
  replay tree 与开发树均为
  `6ffa9fbfea2b127c13e8ba957f4c273b690286b2`，完全一致；临时 worktree
  已清理。

## 自审记录

结论：**PASS，可以进入独立 review**。

- 逐项对照 KL-117a 目标及 QEMU KL-116a 状态机，新增字段、reset/copy、
  vector carrier、trap 保存/切换/跳转和 escape 恢复均闭合。
- 专门检查默认关闭路径：host/SE syscall switch 内部没有改动；独立
  review 发现初版把 PC 推进搬进 `execute()` 会破坏 O3 front-end，
  已恢复既有 `advancePC()`；真实入口仅在 profile on 分支内预置
  vector NPC。修正后 81 项 E2E 和 200 项 gem5 differential 覆盖均零
  回归，A/B off 仍产生 `-ENOSYS` 和 `0x99`。
- 专门检查 precise PC：`causeIp` 在写顺序 PC 前采样，frame 保存 trap
  指令自身地址，escape `imm=1` 返回唯一正确的下一条指令。
- 专门检查生命周期：Param 在 `createThreads()` 后设置、`m5.instantiate()`
  前消费；初版探针曾在 `createThreads()` 前索引空的 `isa[]`，已修正并
  重新完成全部验证。
- 未修改 spec/wiki/issues、未引入 O3 范围外状态；根仓库既有未跟踪
  `gcc-torture-results.json` 未触碰。

## 独立 subagent review

独立 reviewer 对初版给出 **FAIL**，主要 finding 是初版把
`TrapInst::advancePC()` 改为空、在 `execute()` 内自行推进 PC，会使
`DADAOO3CPU` front-end 的非分支顺序取指停滞；这个 finding 接受并已修复。
修复方式不是扩大 O3 CPU 支持，而是恢复 trap 原有 `advancePC()` 契约，
真实 profile 通过 `pc=vector-4/npc=vector` 的 carrier 让通用推进精确
落到 vector。修正后重新完成构建、A/B、KL-113a、81 项 E2E、四方
differential 和 19-patch replay。

reviewer 另指出两个非阻塞边界：

1. 原探针 trap 前后都是 Supv/all-ones，mask 恢复缺少判别力。已接受并
   把 runner 的 handoff mask 改为 `0x0123456789abcdef`，profile-on
   escape trace 确认恢复该非平凡值；mode 仍按 O3 场景合法保持
   Supv→Supv。
2. CFX 架构状态没有 checkpoint serialize/unserialize，且
   `DADAOO3CPU` 的 profile-on 推测提交/回滚未建模。这两点均是
   KL-113a 以来整个 CFX 状态容器/现有手写 decoder 的既有系统边界，
   不属于本任务明确要求的 AtomicSimpleCPU SE 验收，也不在 KL-116a
   镜像子集内；本任务不宣称 checkpoint 或 DADAOO3CPU profile-on
   支持，未擅自扩大实现范围。

修复后由**同一位独立 reviewer** 做 delta re-review，最终结论：
**PASS**。reviewer 独立复跑 Atomic A/B（off=153/on=43），确认
`advancePC()` 阻塞已消除、vector carrier 精确、非平凡 mask 恢复有效，
并复核 patch-id 与 19/19 replay tree；未发现新阻塞、未修改文件。
