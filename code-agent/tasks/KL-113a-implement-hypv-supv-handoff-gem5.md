# KL-113a：hypv→supv 移交（O1 + O2 设计1/设计3）in gem5

**执行环境**：本地 subagent，gem5 源码改动（`.work/source/gem5` = `~/DADAO-gem5`
的 checkout，确认两者关系后再动手——见下方「背景」），产出 patch 落
`components/gem5/patches/`

## 背景

QEMU 侧的 hypv→supv 移交已经完整实现并独立复核通过：
`KL-110a`（O1 成功路径，commit `72cba5f`）+ `KL-112a`（O2 设计1"跨 cfx
escape 权限检查"+设计3"cfx2rc reserved (cg,rc)→CFXREG"，commit `4d8d9fa`，
设计2 因真实 wiki 矛盾主动撤回见 `docs/wiki-deviations.md` 第11条）。
gem5 侧目前**完全没有**这套机制——`~/DADAO-gem5` 的 `src/arch/dadao/`
里没有任何 `cfx2rc`/`escape`/`inner_cfx_code`/`inner_run_mode` 相关代码
（`grep -rl "cfx2rc\|inner_cfx_code\|escape" src/arch/dadao/` 零命中，
架构师已核实）；已有的 `TrapInst::execute()`（`decoder.cc:703-` 附近）
是 `cfx_smon` 的 host/SE syscall 直通捷径，和 QEMU 的 `EXCP_CFXTRAP`
捷径同构，与本任务的真实 CFX 状态机是两条独立路径（这条 legacy 捷径不能
删、不能改，见「约束」）。

这是 `KL-101a`/`KL-102a`（2026-07-21 调研，`docs/reviews/
kernel-hypv-supv-handoff-20260721.md` / `docs/reviews/
kernel-cfx-state-patch-surface-20260721.md`）当年已经规划好、但一直没有
排期的 gem5 半边——两份报告都判定"QEMU/gem5 双端当时均未实现"，QEMU 半边
已经在 KL-110a/112a 补齐，gem5 半边现在轮到。`kernel-cfx-state-patch-
surface-20260721.md` §3.3"建议顺序"给出的四步分解**直接可用**，本任务
就是照这个顺序执行 gem5 那一侧：

1. 先加状态容器（`isa.hh`/`isa.cc`/`registers.hh`），不改 host syscall 行为。
2. 再做 O1（`decoder.cc` → `isa.hh/.cc` → `faults.*`，只覆盖 `cfx2rc`
   delegation 和 `escape cfx_power,0`）。
3. 再做 O2（同一集中位置加权限判断，拒绝路径 ILLI/CFXREG，不改架构状态）。
4. 最后加短向量验收（O1 一个成功 handoff，O2 两个负例）。

**语义参照物是 QEMU 的实现，不是重新发明**——`.work/source/qemu/
target/dadao/{cpu.h,cpu.c,helper.c}` 里 KL-110a/KL-112a 加的代码就是
这次要在 gem5 上落地的确切语义（状态字段、reset 值、检查条件、fault
class、副作用范围），过 wiki 引用时可以直接复用 QEMU 代码注释里已经
核实过的行号，但**建议独立重新读一遍 wiki 原文**（不要只信任务文件转述）。

## 目标

在 gem5（`~/DADAO-gem5`，即 `.work/source/gem5`）实现：

1. **CFX 状态容器**：`inner_run_mode`/`inner_cfx_code`/`inner_cfx_mask`
   （对齐 QEMU `cpu.h` 同名字段的复位值：hypv/cfx_power/全1）；
   `cfx_power` 的 cg=5 异常帧（`prev_run_mode`/`prev_cfx_mask`/
   `cause_ip`，只做 HBI §3 stub 会写的这三个字段）；
   `cfx_hypv_cg_reg_deleg[64]`（cg=3/rc=12，复位全1，bit3 硬件强制1）；
   `cfx_escape_cfx_mask[64][4]`（cg≤3/rc=7，复位全1，索引
   `[cfxcode][mode]`）。存储位置由你判断——`isa.hh` 现有的
   `miscRegFile`（`std::vector<RegVal>` + `NumMiscRegs`）是给标量寄存器
   设计的，`[64]`/`[64][4]` 这种数组字段更适合作为 `ISA` 类的独立成员
   （参照 QEMU `CPUArchState` 是纯 C struct 字段的方式），不必强行塞进
   `miscRegFile`；决定后在完成区说明理由。
2. **O1（cfx2rc + escape 成功路径）**：`decoder.cc` 新增
   `CFX2RCInst`/`EscapeInst`（当前 opcode `0x73`/`0x77` 尚未被 gem5
   解码器识别，需要先确认解码入口怎么加——参照现有 `TrapInst`(`0x76`)
   等指令的注册方式）。语义对齐 QEMU `helper_cfx2rc`/`helper_escape`
   的 O1 子集：`cfx2rc` 只处理 `(cg,rc)=(3,12)` 委托寄存器和
   `cfx_power` 的 `(cg,rc)=(5,{0,1,3})` 异常帧；`escape` 处理
   `cfx_power` self-escape（恢复 mask/mode，PC 跳到
   `cause_ip+imms18*4`），其余组合静默 no-op（同 QEMU 惯例）。
3. **O2 设计1（跨 cfx escape 权限检查）**：`escape` 目标 cfxcode
   `!= inner_cfx_code` 时检查 `cfx_escape_cfx_mask[inner_cfx_code]
   [inner_run_mode]` 对应位，为1则触发 ILLI 且不执行任何恢复/跳转
   （PC/mode/mask 不变）——对齐 `.work/source/qemu/target/dadao/
   helper.c::helper_escape()` 里 KL-112a 加的那段检查。
4. **O2 设计3（cfx2rc reserved (cg,rc) → CFXREG）**：`cfx2rc` 目标是
   `cfx_power` 的 `cg=8` 且 `rc>1` 时触发新增的 `CfxregFault`（参照
   `faults.hh` 已有的 `IlliFault`/`MalignFault` 等类的写法新增一个，
   退出码沿用 QEMU 那边已定的 `0x86`，`faults.hh` 顶部注释里的编号表
   要同步更新）。**范围窄限于这一个组合**，不要把整个"未知 (cg,rc)"
   都改判成 CFXREG（QEMU 侧 KL-112a 完成区/审阅记录里详细写了为什么
   这么做——cg0-2/cg3 剩余寄存器 wiki 有定义只是没实现存储，不是
   "不存在"，混为一谈会产生假 CFXREG）。
5. **legacy `cfx_smon` syscall 捷径完全不动**——`TrapInst::execute()`
   里 `cfxcode==2` 的 host/SE responder 一行都不改，这是独立于本任务
   状态机的兼容路径（`kernel-cfx-state-patch-surface-20260721.md` §5.1
   "隔离原则"）。

## 约束

- 只做 O1 + O2 设计1/设计3，对齐 QEMU KL-110a/KL-112a 的确切范围——
  不要实现候选A（`cg_reg_deleg` 一般访问控制，`docs/wiki-deviations.md`
  第10条 OPEN）、不要实现设计2（跨 cfx `cfx2rc_cfx_mask` 检查，
  `docs/wiki-deviations.md` 第11条记录了它与 HBI §3 引导桩的真实矛盾，
  gem5 侧同样会撞上这个矛盾，不要重新踩一遍）、不要碰 `cfxld`/`cfxst`/
  `cfx2rd`/`trap`（`cfxcode` reserved 路由到 ILLI 那条也不做，QEMU 也
  没做）、不要实现嵌套 trap/多层 escape/MMU/权限之外的任何东西。
- 不修改 `TrapInst::execute()` 的 `cfxcode==2` host/SE syscall 路径
  任何一行。
- 状态转换/检查逻辑集中在指令的 `execute()` 实现和/或 `isa.cc` 里，
  参照 QEMU carrier-point 惯例的精神（不要把权限检查逻辑散落到多处）。
- gem5 侧目前的 lit E2E 后端（`tests/lit/E2E/lit.cfg` 里的
  `%gem5`/`%gem5_se`）用的是 SE 模式（`dadao_se.py`，ELF 直接从
  entry point 起跑，没有"hypv reset ROM"这个 bare-metal 概念）。
  QEMU 那边 O1/O2 的验收探针（`tests/scripts/gen_kl110a_o1_probe.py`/
  `gen_kl112a_o2_probes.py`）是 bare-metal ROM 风格（`-bios` 加载到
  reset vector）。gem5 要不要／怎么复现"reset 后 inner_run_mode=hypv"
  这个前提，由你判断最合适的验证方式——参考 `KL-109a` 当年独立构造
  `se_atomic.py`/`se_o3.py` 加手写 ELF 的先例（不依赖 lit 现成的
  `dadao_se.py` 配置，自己写一个够用的最小 SE Python config），只要能
  真实观测到 `inner_run_mode`/`inner_cfx_code` 从 CPU 架构复位值开始、
  执行 `escape`/`cfx2rc` 序列后产生正确的状态变化/fault 即可，不强求
  和 QEMU 探针字节级一致（两边指令编码方式/ELF 加载机制本来就不同）。
  完成区要说明你选的验证方式和为什么。
- 完整 patch-series bare-pin replay（tree-hash 比对）是硬性验收项，
  照 `KL-109a` 的标准执行（gem5 patch 落 `components/gem5/patches/`）。
- 完成后写「完成区」+「审阅记录（subagent 自审）」；不需要嵌套
  subagent、不需要独立 reviewer（架构师会亲自复核，含独立重建 gem5、
  独立构造/重跑探针）。

## 验收

- O1 正例：reset 后按 HBI §3 stub 顺序执行（12 条 delegation 清除 + 3
  条 power frame 写入 + `escape cfx_power,0`），观测到
  `inner_run_mode` 从 hypv 变成 supv，PC 落在预期的 supv 入口地址。
- O2 设计1负例：reset 后直接 `escape cfx_<非power>,0`（`inner_cfx_code`
  仍是 power），触发 ILLI，`inner_run_mode`/`inner_cfx_mask`/PC 均不变
  （不能只看"程序退出/出错"这么弱的断言，要能读到架构状态确实没被
  污染——参照 QEMU 那边 KL-112a 做的 A/B 负控制方法论，用类似手段证明
  "检查确实生效了"而不是巧合）。
- O2 设计3负例：`cfx2rc cfx_power,8,63,rdX` 触发 `CfxregFault`，不产生
  任何架构状态改变。
- gem5 侧改动通过完整 patch-series bare-pin replay（tree hash 比对）。
- 不影响现有 gem5 lit E2E 后端（`GEM5_OPT`/`GEM5_SE` 相关 lit 用例）和
  `tools/run_differential.py` 的既有数字（O1/O2 这几条指令不在当前
  差分向量集合里，预期数字不变，但要跑一遍确认真的没有回归）。

## 参考指针

- `.work/source/qemu/target/dadao/{cpu.h,cpu.c,helper.c}`
  （KL-110a/KL-112a 的确切实现，本任务的语义参照物——commit `72cba5f`
  和 `4d8d9fa`）
- `code-agent/tasks/KL-110a-implement-hypv-supv-handoff-o1-qemu.md`、
  `code-agent/tasks/KL-112a-implement-hypv-supv-handoff-o2-qemu.md`
  完成区（QEMU 侧实现细节、验收方法论、wiki 引用行号）
- `docs/reviews/kernel-hypv-supv-handoff-20260721.md`（KL-101a，O1/O2
  最初设计，gem5 现状核实）
- `docs/reviews/kernel-cfx-state-patch-surface-20260721.md`（KL-102a，
  §3.3"建议顺序"四步分解直接适用；§5.1 legacy 隔离原则）
- `docs/reviews/kernel-hypv-supv-o2-permission-recon-20260725.md`
  （KL-111a，设计1/2/3 的精确 wiki 依据）
- `docs/wiki-deviations.md` 第9条（`inner_cfx_code` 未被 escape 恢复）、
  第10条（候选A 排除依据）、第11条（设计2 与 HBI §3 的真实矛盾——
  gem5 侧不要重新踩这个坑）
- `code-agent/tasks/KL-109a-implement-ldmo-ra-stmo-ra-gem5.md` 完成区
  （gem5 独立验证方法论先例：从零手写探针/ELF，不只信复现证据；两轮
  独立 subagent review 的格式先例）
- `~/DADAO-gem5/src/arch/dadao/{isa.hh,isa.cc,registers.hh,decoder.cc,
  faults.hh,faults.cc}`（当前 gem5 dadao arch 现状——手写 decoder，非
  `.isa` DSL；`TrapInst`(`decoder.cc:703-`) 是最接近的现有 carrier-point
  先例）
- `~/DADAO-wiki/DADAO-12-SEE-主管系统运行环境.md`（第813-845行 escape
  硬件语义；第711-738行 entry-flow 检查）、
  `~/DADAO-wiki/DADAO-13-HEE-超管系统运行环境.md`（第7-26行 cg3 表）、
  `~/DADAO-wiki/DADAO-23-HBI-超管系统二进制接口.md`（第25-64行完整
  reset+引导序列）

---

## 完成区（2026-07-25）

**状态**：已完成。O1（成功移交）+ O2 设计1（跨 cfx escape 权限检查）+
设计3（`cfx2rc` reserved (cg,rc) → CFXREG）在 gem5 上全部实现并独立验证
通过；设计2 按约束不实现（与 QEMU KL-112a 一致，`docs/wiki-deviations.md`
第11条记录的矛盾在 gem5 侧同样存在，未重新踩坑）。

### wiki 原文复核（动手前，亲自读，非转述任务文件）

亲自用 Read 工具打开了任务文件引用的全部原文，行号与内容一致：

- `DADAO-23-HBI-超管系统二进制接口.md` 第23-64行：reset 初始值
  （`inner_run_mode=hypv`/`inner_cfx_code=power`/`inner_cfx_mask=全1`，
  第25行）与完整移交序列（12条 `cfx2rc cfx_*_hypv_cg_reg_deleg,rd2` +
  `cfx_power_excp_prev_run_mode=2` + `_prev_cfx_mask=-1` +
  `_cause_ip=target_addr` + `escape cfx_power,0`，第31-64行）——与 QEMU
  `dadao_cpu_reset_hold()`/`gen_kl110a_o1_probe.py` 的实现和探针逐条一致。
- `DADAO-13-HEE-超管系统运行环境.md` 第7-26行 cg3 表：`rc=12`"hypv cg reg
  delegation"复位全1、bit3固定为1（第24行）；`rc=7`"hypv escape cfx
  mask"复位全1（第19行）——与 `CfxHypvCgRegDelegCg/Rc`、
  `CfxMaskRegEscape` 的编号和复位值一致。
- `DADAO-12-SEE-主管系统运行环境.md`：
  - 第269-331行 cg0/cg1/cg2 表：`rc=7`"escape cfx mask"复位全1
    （第281/305/325行），与 hypv 侧同构，四个 mode 共用同一
    `cfxEscapeCfxMask[cfxcode][mode]` 布局成立。
  - 第351-362行 cg5 异常现场寄存器：`rc=0`prev_run_mode、`rc=1`
    prev_cfx_mask、`rc=3`cause_ip——与 O1 的 `cfxPowerFrame` 三字段一致
    （通用表面标复位值为0，QEMU 实际复位用 hypv/全1/0，本次按"语义参照物
    是 QEMU 实现"原则逐字段复刻，不是重新推导 wiki 默认值——这三个字段在
    HBI §3 stub 执行前就会被显式覆盖，复位值本身不影响 O1/O2 验收结果）。
  - 第630-637行 cfx_power 专有寄存器表（cg=8）：只定义 `rc=0`
    power_pending / `rc=1`power_ctrl——确认设计3验收场景
    `(cg,rc)=(8,63)` 是真正不存在的组合，不是"未实现"。
  - 第678-811行异常进入流程、第813-845行异常退出流程：确认
    步骤0（第824-827行）失败时 wiki 伪代码要求"goto
    check_nonmaskable"（重定向进入当前模式 monitor 的完整异常进入流程，
    而非单纯 ILLI 退出）——本实现与 QEMU 一致，**没有**实现这条完整
    monitor 重定向（本 M1 子集里没有任何 monitor/异常向量基础设施，其它
    ILLI/UNDI/MALIGN 同样只是 `exitSimLoop`，不是这条特有的简化）；此
    差异沿用 QEMU KL-112a 已确认的做法，未新增 wiki-deviations 条目
    （KL-112a 完成区已经明确这是"这个 M1 子集所有 ILLI 都是这样"，非
    escape 特有）。
- `SimRISC-00-指令系统设计.md` 第89-106行 opcode 表：`0111-0xxx` 行
  `x011`=`cfx2rc-crrr`、`x111`=`escape-ciii`——手工验算
  `01110011=0x73`（cfx2rc）、`01110111=0x77`（escape），与既有 QEMU
  实现、`decoder.cc` dispatch 一致。
- `SimRISC-04-系统类指令.md` 第85-103行寄存器传输指令：crrr 标准写法
  `ha=cfxcode`/`hb=cg`/`hc=rc`/`hd=rd寄存器`（均为立即数except hd），
  "读写不存在的 ... 组合时触发 CFXREG 异常"——设计3只用这一句，范围与
  QEMU 完全对齐。

### 状态容器设计决策

按任务文件指引判断：`isa.hh` 现有 `miscRegFile`（`std::vector<RegVal>`，
`NumMiscRegs=1`）是给标量寄存器设计的通用容器，`cfxHypvCgRegDeleg[64]`/
`cfxEscapeCfxMask[64][4]` 是按 cfxcode/mode 索引的定长数组，语义上更贴近
QEMU `CPUArchState` 的纯 C struct 字段——因此选择作为 `DADAOISA::ISA`
类的普通公开成员（`isa.hh`），不塞进 `miscRegFile`，不新增 gem5 misc-reg
ID。`RunMode` 枚举、`CfxCodePower`/`CfxHypvCgRegDelegCg/Rc`/
`CfxMaskRegEscape` 常量、`CfxPowerFrame` 结构体放在 `DADAOISA` 命名空间
（`isa.hh`），供 `decoder.cc` 的新指令类直接引用。

`ISA::clear()`（原来是头文件内联的一行，改为 `isa.cc` 里的带 CFX 重置逻辑
的实现）在构造函数（`ISA::ISA()`）和 `SimpleThread::clearArchRegs()`
（gem5 现有机制，`cpu/simple_thread.hh:250`，线程创建时调用一次）两处都会
被调用——SE 模式没有 bare-metal reset 向量，这是 gem5 这个 arch 能观测到
"reset 后"状态的最接近位置：ELF entry point 的第一条指令执行前，
CFX 状态已经被 `clear()` 设成 hypv/power/全1，等价于 QEMU
`dadao_cpu_reset_hold()` 的效果（仅入口地址来源不同：QEMU 是硬编码的
reset vector，gem5 是 ELF `e_entry`）。`copyRegsFrom()` 同步扩展了 CFX
状态搬运（此前只搬 int/float/PC），避免 SE clone/fork 路径悄悄丢失 CFX
状态（当前 M1 lit/differential 覆盖不触发这条路径，是面向未来的一致性
修正，非本任务验收必需，但成本低、和现有 int/float 逻辑同构）。

### gem5 实现（`~/DADAO-gem5`，普通 commit `635a70bd9d`）

严格对齐 QEMU `helper_cfx2rc()`/`helper_escape()`（KL-110a/KL-112a）的
承载点惯例——所有状态转换/权限检查集中在两个新 `StaticInst` 的
`execute()` 里，不散落到别处：

- `isa.hh`/`isa.cc`：新增 `RunMode` 枚举、`CfxCodePower`/
  `CfxHypvCgRegDelegCg/Rc`/`CfxMaskRegEscape` 常量、`CfxPowerFrame`
  结构体、`ISA` 类新增 `innerRunMode`/`innerCfxCode`/`innerCfxMask`/
  `cfxPowerFrame`/`cfxHypvCgRegDeleg[64]`/`cfxEscapeCfxMask[64][4]`
  六个字段；`ISA::clear()`（新增 out-of-line 实现）按 QEMU
  `dadao_cpu_reset_hold()` 字段对字段复刻复位值；`copyRegsFrom()`
  同步扩展。
- `decoder.cc`：新增 `#include "arch/dadao/isa.hh"`；新增
  `cfxIsa(ExecContext*)` 静态 helper（`xc->tcBase()->getIsaPtr()` 转型）；
  新增 `CFX2RCInst`（`0x73`，crrr 格式，`ha/hb/hc`=立即数
  cfxcode/cg/rc，`hd`=可选源寄存器，`hd=0`按现有 `StoreInst`/`BrnInst`
  惯例读常量0）——覆盖 deleg 写入（cg3/rc12，bit3 强制1）、power frame
  写入（cg5/rc0,1,3）、KL-112a 设计1的 escape mask 存储（cg≤3/rc7）、
  设计3的 CFXREG（cfx_power cg8 rc>1），其余组合静默 no-op；新增
  `EscapeInst`（`0x77`，riii 格式，`ha`=立即数 cfxcode，`imm18`=有符号
  偏移）——先做设计1跨 cfx 权限检查（检查失败立即 `RET_ILLI`，不做任何
  状态写入，PC/mode/mask 全部保持不变），通过后恢复 mask/mode（cfx_power
  用真实 frame，其它 cfxcode 用零 frame，同 QEMU）、计算并跳转目标 PC；
  `decoder.cc` 主 dispatch switch 新增 `case 0x73`/`case 0x77`。
- `faults.hh`：新增 `CfxregFault`（"CFXREG"，退出码 `0x86`，与 QEMU
  `EXCP_CFXREG` 一致）；顶部 SE 退出码编号表注释同步补上
  `RASOF=0x84`/`RASUF=0x85`/`CFXREG=0x86`（此前只列了 ILLI/MALIGN/UNDI
  三个，本次一并补全，非任务范围蔓延——纯注释更新）。
- **可观测性**：`EscapeInst` 在通过设计1检查、完成所有状态写入之后（成功
  路径末尾）向 `std::cerr`（非 `stdout`，不干扰 `dumpFinalState()` 的
  `DADAO_REGDUMP`/`DADAO_MEMDUMP` 解析）无条件打印一行 mode 转换 trace，
  仿 QEMU `CPU_LOG_INT` 的 `helper_escape()` 日志（gem5 dadao 当前没有
  等价的可开关 debug flag 基础设施，注册新 `DebugFlag` 超出本任务范围，
  改用无条件 stderr——`escape` 是全新指令，任何既有 lit/differential
  向量都不会执行到它，不会扰动任何既有测试的 stdout/exit code）。这行
  trace 的"出现与否"本身是 O2 设计1负例证据的一部分（见下）。
- **未触碰** `TrapInst::execute()` 的 `cfxcode==2` host/SE syscall 分支
  任何一行（`git diff` 确认该函数体逐字未改，只在其后新增了两个独立类）；
  未实现设计2（`cfxEscapeCfxMask`旁没有新增 `cfxCfx2rcCfxMask`
  之类的存储或检查代码）；未碰 `cfxld`/`cfxst`/`cfx2rd`/`trap` 本身。

### gem5 SE 验证方式选择（任务文件要求说明理由）

gem5 lit E2E 现有后端（`dadao_se.py`）是 SE 模式，ELF 直接从 `e_entry`
起跑，没有"hypv reset ROM"概念。参照 `KL-109a` 先例（独立手写 SE
探针，不依赖现成 lit 配置），本任务：

1. **直接复用** QEMU 侧 `tests/scripts/gen_kl110a_o1_probe.py`/
   `gen_kl112a_o2_probes.py`（KL-110a/KL-112a 已验证过的原始指令序列，
   已是仓库里的（已提交）文件）生成的**裸指令字节流**——这些是与后端
   无关的纯 opcode 编码，不依赖 QEMU 的 `-bios` 加载机制。
2. 新增 `tests/scripts/run_kl113a_gem5_probes.py`：把上述指令流通过
   `gen_min_elf.build_elf()`（`run_gem5_test.py` 已用的同一工具）包装成
   gem5 能识别的 DADAO ELF，用 `dadao_se.py` 跑在
   `DADAOAtomicSimpleCPU` 上（与 lit E2E `GEM5_SE` 后端同一 CPU 模型）。
   唯一的适配：QEMU 探针脚本里硬编码的 `ROM_BASE=0x00100000`（QEMU
   `-bios` reset vector）对 gem5 无意义（gem5 ELF 固定加载在
   `gen_min_elf.LOAD_ADDR=0x80000000`），运行前把
   `gen_kl110a_o1_probe.ROM_BASE`（及 `gen_kl112a_o2_probes.o1.ROM_BASE`）
   猴子补丁改成 `gen_min_elf.LOAD_ADDR`，让 `supv_entry` 落在实际加载的
   `.text` 段内——只改跳转目标地址的计算基准，不改任何指令编码/语义，
   任务文件明确允许"不强求和 QEMU 探针字节级一致"。
3. **"reset 后 inner_run_mode=hypv"前提的验证依据**：`ISA::clear()`
   在 `SimpleThread` 构造时无条件执行一次（先于 ELF entry PC 被设置/
   执行任何指令），把 CFX 状态设为 hypv/power/全1——这是 gem5 SE 这个
   arch 能观测"reset 后"状态的最接近位置（详见上文"状态容器设计决策"）。
   这个前提由 O2 设计1负例直接验证：探针的**唯一一条指令**就是
   `escape cfx_smon,0`，在它执行前没有任何其它指令跑过，如果
   `inner_cfx_code`/`cfxEscapeCfxMask` 复位值不是 power/全1，这条探针就
   不会产生 ILLI——它产生了，证明复位路径确实生效（不是巧合通过，见下面
   "证据独立性"）。
4. **KL-109a 已知的 gem5 SE 映射要求**：需要额外映射
   `0x80001000`（`.text` 加载页之后的一页，KL-109a 独立 review 发现的
   self-modifying-code guard 页要求）——O1 探针的 `MARKER_ADDR` 恰好就是
   这个地址（`gen_kl110a_o1_probe.py` 原样复用），`run_kl113a_gem5_probes.py`
   把它作为额外 ELF data segment 映射；O2 两个负例探针不写内存，不需要
   这个映射（O2 设计1负例甚至只有一条指令）。

### O1 正例结果

`.work/evidence/kl113a-probes/kl113a-o1-handoff.{bin,elf,log}`：

- gem5 exit code = **42**（十进制，即 `DADAO_REGDUMP`+`SIM_END: halt
  code=42`）——marker 写入 `0x80001000`、读回、`xor` 比对全部通过（不是
  只看"没有 fault"，探针本身就是自校验设计，沿用 KL-110a 惯例）。
  `rd4=0x2a`(42)、`rd6=0`（xor 结果为0=匹配）。
- stderr trace：`dadao: escape cfx=63 mode 3->2 mask=0xffffffffffffffff
  pc=0x80000200`——`inner_run_mode` 3(hypv)→2(supv)，PC 精确落在
  `supv_entry`（`gen_min_elf.LOAD_ADDR + 0x200 = 0x80000200`）。
- 同一份指令流（`gen_kl112a_o2_probes.o1.gen()`，`kl113a-o1-regression`
  探针）复跑：结果逐字节一致（exit=42，同一条 trace），确认 O2 设计1的
  权限检查代码不影响 O1 self-escape（`cfxcode==inner_cfx_code`时设计1
  检查条件天然不成立，两者不冲突）。

### O2 设计1负例结果 + A/B 负控制

`.work/evidence/kl113a-probes/kl113a-design1-negative.{bin,elf,log,
AB-disabled.log}`：

- 探针：reset 后**唯一一条指令** `escape cfx_smon,0`
  （`cfxcode=2≠inner_cfx_code=power(63)`）。
- **检查生效时（当前实现）**：gem5 exit code = **130**（`0x82`=ILLI）；
  日志里**没有**"`dadao: escape cfx=...`"这行 trace（该行只在通过设计1
  检查之后才会执行到，不出现证明代码在写任何架构状态之前就已经
  `return`）。
- **A/B 负控制**（仿 QEMU KL-112a 方法论，真实改代码+重编译，不是纸面
  推理）：临时把 `EscapeInst::execute()` 里的检查条件改成
  `if (0 && cfxcode_ != isa->innerCfxCode)`（恒假，等价禁用检查），
  `scons build/DADAO/gem5.opt` 完整重新编译，用**同一个**探针二进制重跑：
  - trace **确实出现**：`dadao: escape cfx=2 mode 3->0 mask=0x0 pc=0x0`
    ——`inner_run_mode` 被错误地从 hypv(3) 改成 user(0)、`inner_cfx_mask`
    变成0、PC 跳到0；
  - 随后 gem5 因为 PC=0 处没有映射页面而 `panic: Page table fault when
    accessing virtual address 0`，进程异常退出（rc=-6，不再是干净的
    `SIM_END`）。
  - 这证明"检查代码确实是导致行为差异的原因"，不是巧合——若只看退出码
    （禁用前 130 vs 禁用后异常终止），两者本来就明显不同，比 QEMU 那次
    "两种情况退出码碰巧相同"的陷阱更容易看出差异，但本次额外核对了
    trace 内容（有/无状态转换记录）作为更细粒度的因果证据，不仅仅依赖
    "程序表现不同"这一层。
  - 验证完成后用 Edit 工具精确撤销这处改动（不是 `git checkout`/`reset`
    这类可能牵连其它改动的操作），`cmp` 确认恢复后的 `decoder.cc` 与
    改动前的备份逐字节相同，重新 `scons` 编译，四个探针（O1/设计1/
    设计3/O1回归）全部重新跑过确认无残留影响，才继续后续的 commit/
    patch 导出步骤。

### O2 设计3负例结果

`.work/evidence/kl113a-probes/kl113a-design3-negative.{bin,elf,log}`：

- 探针：`cfx2rc cfx_power,8,63,rd2` + poison `halt rd9=0x77`
  （`gen_kl112a_o2_probes.py` 原样复用）。
- gem5 exit code = **134**（`0x86`=CFXREG）——**没有**到达 poison halt
  （若到达会是 `exit=0x77`），证明 CFXREG 在到达 poison 之前就中断了
  执行；`cfx_power_pending`/`cfx_power_ctrl`（真实的 `(cg,rc)=(8,0)/(8,1)`）
  在当前 gem5 实现里本来就没有任何存储字段，"状态不变"是平凡成立，重点
  验证的是"读写 `(8,63)` 这个不存在的组合没有被静默吞掉、没有落到
  default no-op 分支"。

### 回归验证

- `lit tests/lit/E2E`：**81/81 PASS**（改动前后一致，无回归）。
- `python3 tools/run_differential.py`：`AGREE(3-way)=200`、
  `gem5-SKIP=2`、`DIVERGE=0`；`AGREE(4-way)=200`、`Sail-SKIP=2`、
  `SAIL-DIVERGE=0`——与改动前基线完全一致（`cfx2rc`/`escape` 不在现有
  差分向量集合里，预期数字不变，已重新独立跑过确认非缓存结果）。
- `python3 scripts/manifest_check.py`：PASS。
- `python3 scripts/check_issues.py`：PASS（Open 24/Closed 43/Total 67，
  无变化——本任务未新增/关闭 issue）。
- `contracts/isa/spec.md`/`tools/opcodes.yaml`/`docs/wiki-deviations.md`/
  `docs/issues.yaml`：`git diff --stat` 确认零改动（本任务纯 gem5 侧
  代码 + 测试脚本 + patch series，不涉及契约/wiki 偏离登记——设计2撤回
  的矛盾已由 QEMU KL-112a 记录在 `docs/wiki-deviations.md` 第11条，
  gem5 侧同一矛盾不需要重复登记）。

### patch-series bare-pin replay（硬性验收项）

- `~/DADAO-gem5` 普通 `git commit`：`635a70bd9d74005b9e6b03d89a329b0427ec4f47`
  （"arch/dadao: implement hypv->supv handoff O1 + O2 design1/design3
  (KL-113a)"，4 files changed, 251 insertions(+), 1 deletion(-)，
  `git diff --check` 无空白问题）。
- `git format-patch` 导出
  `components/gem5/patches/0018-arch-dadao-implement-hypv-supv-handoff-O1-O2-design1.patch`
  （378 行），追加进 `components/gem5/patches/series`（第18项）。
- commit 与导出 patch 的 stable patch-id 均为
  `100030b091ee8aab4b95c75b6cfa8221c7e5e5d2`。
- 独立验证：`git worktree add --detach <tmp> c8222cc67a399bfc01e8658dd14b30d5bfd634f9`
  （manifest 锁定的 v25.1.0.1 pin commit）→ 对 `series` 里全部 18 个
  patch 依次 plain `git am`（无 `--3way`/`-C`，全部一次通过，18/18
  PASS）→ `git rev-parse HEAD^{tree}` 与开发树
  （`~/DADAO-gem5` 的 `git rev-parse HEAD^{tree}`）逐字符比对，两者均为
  `25739b63ab43956e82dcfc5fe90169fb916c94ad`——**tree hash 完全一致**。
  临时 worktree 验证完成后 `git worktree remove --force` 清理，未残留。

### 附带的小改动

- `tests/scripts/run_gem5_test.py`：`FAULT_CODES` 字典新增
  `'CFXREG': 0x86` 一行，对齐 QEMU 侧 `run_qemu_test.py`（KL-112a 已加）
  ——低风险纯增量改动，供后续差分向量编写者使用；本任务未把
  `cfx2rc`/`escape` 加进任何现有差分向量或 lit 用例。
- 新增 `tests/scripts/run_kl113a_gem5_probes.py`（本任务的 gem5 探针
  runner，见上），复用而非复制 `gen_kl110a_o1_probe.py`/
  `gen_kl112a_o2_probes.py` 的指令序列。

### 范围边界确认（对照约束逐条自查）

- 未实现候选A（`cg_reg_deleg` 一般访问控制，`docs/wiki-deviations.md`
  第10条 OPEN）。
- 未实现设计2（跨 cfx `cfx2rc_cfx_mask` 检查，第11条矛盾——gem5 侧同一
  矛盾必然存在，未重新验证/重新踩坑，直接沿用 QEMU 已确认的结论）。
- 未碰 `cfxld`/`cfxst`/`cfx2rd`/`trap` 本身；reserved cfxcode 路由到
  ILLI 未实现（QEMU 也没做）。
- 未实现嵌套 trap/多层 escape/MMU/权限之外的任何东西。
- `TrapInst::execute()` 的 `cfxcode==2` host/SE syscall 路径逐字未改
  （`git diff` 确认）。
- 状态转换/检查逻辑集中在 `CFX2RCInst`/`EscapeInst` 的 `execute()`
  里，未散落到 `isa.cc`/别处（比 QEMU 更集中——QEMU 是 `translate.c`
  只做操作数提取、`helper.c` 做状态转换的两层结构，gem5 手写 decoder
  没有等价的 translate/helper 分层，`execute()` 本身就是唯一的状态转换
  点）。
- `~/DADAO-gem5` 只有一次普通 `git commit`，一次 `git format-patch`
  导出；A/B 负控制的临时改动通过 Edit 工具精确改/精确撤销，未涉及任何
  `git rebase`/`reset --hard`/重放历史操作；bare-pin replay 用独立临时
  `git worktree`，验证完清理，不影响 `~/DADAO-gem5` 主工作树。
- 未 commit 到 DADAO-0628 根仓库——新增/改动的
  `components/gem5/patches/0018-*.patch`、`components/gem5/patches/
  series`、`tests/scripts/run_gem5_test.py`、
  `tests/scripts/run_kl113a_gem5_probes.py`、
  `.work/evidence/kl113a-probes/`、本任务文件均留在工作区等架构师复核
  （`git status --short` 确认根仓库工作树里没有任何 `git add`/
  `git commit` 操作）。

## 执行者自审：审阅记录

**判决**：自审通过，无阻断 finding。

- **wiki 引用逐项复核**：本次实现前用 Read 工具亲自打开了任务文件引用的
  全部原文（HBI §3 第23-64行、HEE §1 第7-26行、SEE §3 第269-362行/
  第630-637行、SEE §5 第678-845行、SimRISC-00 opcode 表、SimRISC-04
  寄存器传输指令），逐条核对内容与任务文件转述一致，未发现任务文件行号
  转述有误；额外发现并记录了一处任务文件未展开但对理解设计1"检查失败
  时的行为"很关键的信息——wiki 步骤0失败后的伪代码是"goto
  check_nonmaskable"（完整 monitor 重定向），而 QEMU/本实现都简化成单纯
  ILLI 退出，已在完成区"wiki 原文复核"小节明确记录这个简化范围（不是
  遗漏，是与 QEMU KL-112a 完全对齐的既有简化，未新增 wiki-deviations
  条目，因为 KL-112a 已经把这个简化定性为"M1 子集所有 ILLI 都这样"而非
  escape 特有）。
- **编码手工验算**：`01110||011=0x73`（cfx2rc）、`01110||111=0x77`
  （escape）——与 `decoder.cc` dispatch、QEMU `insn.decode`、任务文件
  三处记录一致。
- **QEMU 语义对齐核对逐条**：`helper_cfx2rc()`/`helper_escape()`
  （`.work/source/qemu/target/dadao/helper.c` 第109-298行）与
  `CFX2RCInst`/`EscapeInst` 的 `execute()` 逐分支比对——deleg 写入
  （含 bit3 强制1）、power frame 三字段（含 rc0 的 `&0x3`、rc3 的
  `&MASK48`）、escape mask 存储（`cg<=3`边界）、设计3 CFXREG 条件
  （`cfxcode==power && cg==8 && rc>1`）、设计1检查时机（恢复 mask/mode
  **之前**、用恢复前的 `inner_run_mode`/`inner_cfx_code` 索引 mask）、
  self-escape 时设计1检查天然跳过（`cfxcode==inner_cfx_code`）、非
  power cfxcode 的 escape 用零 frame——全部一一对应，未发现任何一处
  分支顺序/条件与 QEMU 不一致。
- **未触碰范围核对**：`grep -n "cfxcode == 2" decoder.cc` 确认
  `TrapInst::execute()` 分支内容与改动前 `git diff` 显示完全没有改动
  （新代码全部插入在该函数体**之后**，独立的两个新类）；`grep -n
  "cfxCfx2rcCfxMask\|cfx2rc_cfx_mask" isa.hh isa.cc decoder.cc`
  零命中，确认设计2确实未实现。
- **A/B 负控制的独立性核对**：不是纸面断言"应该不同"，而是真实用 Edit
  工具改代码（`if (0 && ...)`）、真实 `scons` 完整重新编译
  （非增量跳过）、用同一份探针二进制重新执行，观测到 trace 内容
  （mode/mask/pc 三个字段）和进程退出方式（干净 `SIM_END` vs `panic`
  异常终止）都发生了真实、可复现的变化；验证后用 `cmp` 逐字节确认
  `decoder.cc` 已恢复到改动前状态，重新编译并四个探针全部复跑通过后才
  继续（详见完成区"O2 设计1负例结果 + A/B 负控制"小节的完整记录）。
- **bare-pin replay 独立性核对**：replay worktree 用 `git worktree add
  --detach <path> <pin-commit>` 从 manifest 锁定的裸 commit
  （`c8222cc67a399bfc01e8658dd14b30d5bfd634f9`）开始，不是从
  `dadao-arch-skeleton` 开发分支分出去的；18 个 patch 全部用 `git am`
  （无 `--3way`/`-C` 宽松选项）逐条应用，一次成功；tree hash 用 `git
  rev-parse HEAD^{tree}` 独立计算两侧后逐字符比对（`25739b63ab439
  56e82dcfc5fe90169fb916c94ad`）；commit 与导出 patch 的 `git patch-id
  --stable` 也独立比对一致（`100030b091ee8aab4b95c75b6cfa8221c7e5e5d2`）；
  worktree 完成后 `git worktree remove --force` 清理，`git worktree
  list` 确认只剩主工作树。
- **回归范围核对**：`lit tests/lit/E2E`（81/81）、
  `run_differential.py`（AGREE(3-way)=200/DIVERGE=0，AGREE(4-way)=200/
  SAIL-DIVERGE=0）、`manifest_check.py`、`check_issues.py`均为本轮
  独立重跑（非沿用改动前的缓存结果），且是在 A/B 负控制验证、代码恢复、
  重新编译**之后**的最终状态上跑的，不是恢复前的中间状态。
- **未做事项确认**（对照约束逐条自查，见完成区"范围边界确认"小节）：
  未实现候选A/设计2；未碰 `cfxld`/`cfxst`/`cfx2rd`/`trap`；未碰
  `TrapInst` host/SE 捷径；检查逻辑未散落多处；未对 `~/DADAO-gem5`
  做除一次普通 commit 外的任何历史操作；未 commit 到 DADAO-0628
  根仓库。
