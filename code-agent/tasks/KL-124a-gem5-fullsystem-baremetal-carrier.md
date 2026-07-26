# KL-124a：gem5 bare-metal/FullSystem carrier

**执行环境**：远端 Codex（本仓库），gem5 源码改动（`~/DADAO-gem5`）

## 背景

`KL-118a`（调研）§3.2 已确认：gem5 当前**只有 SE 模式**——`TLB` 的
`atomic`/`functional` translation 都直接转交 SE process page table，
`panic_if(FullSystem, ...)`（`src/arch/dadao/tlb.cc:18,27`）明确写死
"FullSystem 模式下会 panic"；现有 DADAO runner
（`tests/dadao/dadao_se.py`）固定
`DADAOAtomicSimpleCPU`/`SEWorkload`/`full_system=False`。

QEMU 侧从一开始就是 bare-metal（`-bios` 加载裸二进制到固定物理地址
`0x00100000`，没有 SE 概念）——这正是 O1/O2/O3/`KL-120a` 全部探针
使用的模式。gem5 侧至今为止的所有探针（`KL-113a`/`117a`/`120a` 的
gem5 runner）都是靠"把同一段裸指令流硬塞进 SE 模式的 ELF 包装"这个
变通手法在跑，不是真的 bare-metal。

`KL-118a` §3.2 明确判定："'QEMU 任务完成后直接 port 到 gem5' 只对
纯指令状态成立。MMU 和外设中断的 gem5 port 前，必须先建立可加载
bare-metal image、提供物理内存/退出设备并允许 FullSystem TLB/
interrupt 路径工作的 carrier；否则所谓 gem5 MMU 测试仍会被 SE
process page table 吞掉，形成错误绿灯"。本任务就是建这个 carrier——
是后续所有 gem5 MMU/PTW/TLB/timer/外部中断 port 任务（`KL-126a`/
`128a`/`130a`/`132a`/`134a`/`136a`/`138a`）的共同前置。

## 目标

1. **建立 gem5 FullSystem 模式下的 DADAO bare-metal 配置**：新的
   Python config（参照 `tests/dadao/dadao_se.py` 的组织方式，但
   `full_system=True`，不用 `SEWorkload`/`Process`）——能把一段裸
   二进制（不是 ELF）加载到固定物理地址（对齐 QEMU `-bios` 的
   `0x00100000` 惯例），CPU reset PC 指向这个地址。参考 gem5 上游
   其它极简 arch（RISC-V/其它 minimal FS 目标）的 FullSystem 最小
   配置模式，不需要照抄任何具体上游 arch 的设备树/固件层，DADAO
   目前明确"不引入固件层"（`ADR-0015` D2）。
2. **提供物理内存**：FullSystem 下 gem5 需要显式的 `PhysicalMemory`/
   内存映射配置（SE 模式下这些由 `Process`/host OS 隐式处理，
   FullSystem 下需要显式声明）。
3. **提供退出 oracle**：现有 `halt` 指令的 `exitSimLoop(code)` 机制
   （SE 模式下已验证工作）在 FullSystem 下必须同样可用——可能需要
   确认/调整这条路径在 FullSystem CPU/内存模型下是否需要任何改动
   （比如是否需要显式的 exit MMIO 设备，类比 QEMU 的
   `exit MMIO`，而不能继续依赖 SE 模式的隐式 host 调用）。
4. **确认现有指令语义在 FullSystem 下逐条不变**：`TLB`/
   `Interrupts` 目前对 FullSystem 是 `panic_if`/恒定值——本任务
   **不实现真正的 FullSystem 转换语义**，只是先让"identity 映射、
   TLB 不做任何事、interrupt 恒无"这套行为能在 FullSystem 模式下
   正常跑通（`panic_if(FullSystem,...)` 这几行需要改成 FullSystem
   下也能正常工作的 identity/no-op 行为，而不是继续 panic）。
5. **回归验证**：现有 `KL-113a`/`117a`/`120a` 的裸指令流探针
   （目前靠 SE+ELF 包装跑），改造成走这条新的 FullSystem carrier
   （裸二进制加载，不再需要 `gen_min_elf.py` 的 ELF 包装），验证
   结果与 SE 模式下逐位一致——这是本任务证明"carrier 真的可用"
   的关键证据。SE 模式的现有 runner **不要删除**（保留作为回归
   基线/对照）。

## 约束

- **不实现真正的地址转换/TLB/中断功能**——`TLB`/`Interrupts` 在
  FullSystem 下的行为目标是"能跑，但仍是 identity/no-op"，和现在
  SE 模式的行为等价，只是换了个能运行 MMU/中断后续任务的地基。
  真正的 PTW/TLB/timer/中断实现是后续任务（`KL-126a` 起）的范围。
- **不引入固件层**（`ADR-0015` D2 既有决定）——不需要设备树解析、
  多核唤醒协商等复杂固件功能，只要能加载一段裸二进制并从固定
  地址开始执行。
- 不要修改现有 SE 模式 runner（`dadao_se.py`）的行为——新增一个
  FullSystem 配置文件，不是替换现有的。
- 完整 gem5 patch-series bare-pin replay（tree-hash 比对）是硬性
  验收项。
- 完成后写「完成区」+ 自审记录；继续沿用"自己开 reviewer subagent
  复核"的方法。

## 验收

- `KL-113a`/`117a`/`120a` 的裸指令流探针，改用 FullSystem carrier
  跑一遍（裸二进制加载，不走 ELF/SE），退出码/trace 与现有 SE 模式
  结果逐位一致。
- SE 模式现有全部 gem5 相关 lit E2E、`tools/run_differential.py`
  数字不变（本任务不改变 SE 模式的任何行为）。
- gem5 patch-series bare-pin replay，tree hash 与开发树一致。
- 任务文件「完成区」清楚说明新配置文件的位置、如何调用、以及
  "identity/no-op 语义在 FullSystem 下仍成立"这条判断的验证依据。

## 参考指针

- `docs/reviews/kernel-mmu-interrupt-recon-20260726.md`（KL-118a，
  §3.2 gem5 现状确认+"必须先建FullSystem carrier"的判定、§5
  KL-124a 原始范围描述）
- `~/DADAO-gem5/src/arch/dadao/tlb.cc`（`panic_if(FullSystem,...)`
  当前位置）、`src/arch/dadao/interrupts.hh`（恒 false/NoFault 的
  中断控制器桩）
- `~/DADAO-gem5/tests/dadao/dadao_se.py`（现有 SE 配置，作为组织
  方式的参照，不是要复制的目标）
- `docs/adr/0004-test-machine.md`（QEMU 侧 bare-metal 惯例：
  ROM 基址 `0x00100000`、flat binary 加载、exit MMIO 设计，gem5
  FullSystem carrier 应该在能观测行为上与此对齐，方便后续任务
  复用同一套探针指令流）
- `docs/adr/0015-kernel-bringup-charter.md` D2（"不引入固件层"的
  既有决定）

## 完成区（2026-07-26）

### 实现

- gem5 新增 `DADAOBareMetal` workload
  （`src/arch/dadao/DADAOBareMetal.py`、`bare_metal.{hh,cc}`）：
  `loader::createObjectFile(..., true)` 读取 flat binary，将 raw
  `MemoryImage` 平移到 `0x00100000`，清空线程架构状态、把 PC 显式设为
  同一地址并激活线程。没有 ELF、`SEWorkload`、`Process` 或固件层。
- 新增 `tests/dadao/dadao_fs.py`。它使用
  `DADAOSystem`/`DADAOAtomicSimpleCPU`/`Root(full_system=True)`，并以
  三段 `SimpleMemory` 显式覆盖低地址 image、既有
  `0x80001000/0x80002000` marker 和 halt oracle 的
  `0x87fef000..0x87ff1fff` differential dump window；不为中间空洞分配
  连续 2 GiB host memory。
- `src/arch/dadao/tlb.cc` 的 atomic/functional FullSystem 路径改为
  `paddr=vaddr` 后返回 `NoFault`；SE 路径仍走 process page table。
  `Interrupts` 未改，继续恒 `false`/`NoFault`。这就是本任务限定的
  identity/no-op 地基，不包含 PTW、TLB cache 或真实中断源。
- `halt` 实现未改。FullSystem 探针均得到唯一
  `SIM_END: halt code=<n>`（fault 探针为相应 fault cause）且 gem5
  process rc 与 guest code 相同，证明既有 `exitSimLoop(code)` 无需
  额外 exit MMIO。
- 根仓库新增
  `tests/scripts/run_kl124a_gem5_fs_probes.py`，直接写出并加载既有 raw
  streams，不调用 `gen_min_elf.py`；同一脚本另行构造 SE baseline，
  自动比较归一化后的 REGDUMP、完整 MEMDUMP、CFX trace、唯一
  `SIM_END` cause/code 和 process rc。原有三个 SE runner 均保留且
  行为未修改。

调用方式：

```text
~/DADAO-gem5/build/DADAO/gem5.opt \
  ~/DADAO-gem5/tests/dadao/dadao_fs.py <probe.bin>
python3 tests/scripts/run_kl124a_gem5_fs_probes.py
```

### 验证

- gem5 build：`scons build/DADAO/gem5.opt -j8`，PASS。
- FullSystem raw matrix：
  - KL-113a O1/design1/design3/O1-regression =
    `42/130/134/42`；
  - KL-117a profile off/on = `153/43`，真实入口地址为
    `cause_ip=0x100234`、`vector=0x100400`、返回 `0x100238`；
  - KL-120a register/rd0/pending/nested =
    `44/130 + 7x45 + 43`。
- SE 对照复跑：KL-113a=`42/130/134/42`、KL-117a=`153/43`、
  KL-120a=`44/130 + 7x45 + 43`，guest code 与 FullSystem 逐项一致；
  脚本把 SE code-window 地址从 `0x80000000` 归一化到 FullSystem
  `0x00100000`，并明确排除执行环境固有差异 `rb1`
  （SE process stack=`0x7fffffffe000`，firmware-free FS reset=0）；
  其余寄存器、完整 `0x87fef000` MEMDUMP 和归一化 CFX trace 全部
  自动逐项相等。正例 cause 锁定为 `halt`，负例锁定为
  `ILLI`/`CFXREG`，不允许同码错误路径假绿。
- `.work/build/llvm/bin/llvm-lit -sv tests/lit/E2E/`：81/81 PASS。
- `python3 tools/run_differential.py`：
  `AGREE(3-way)=200`、gem5-SKIP=2、DIVERGE=0；
  `AGREE(4-way)=200`、Sail-SKIP=2、SAIL-DIVERGE=0。
- `manifest_check.py`、`check_issues.py`（Open 24 / Closed 43 /
  Total 67）及根/gem5 `git diff --check` 均 PASS。

### 提交、patch series 与重放

- gem5 commit：
  `cfa40355052e63482412cdce2c8ea66472c6031b`；
  patch
  `components/gem5/patches/0022-arch-dadao-add-FullSystem-bare-metal-carrier-KL-124a.patch`。
- commit/patch stable patch-id 均为
  `943a9e46e7fc86c4d6c0d0f6c9eaeaee53d6fa02`。
- 从 manifest pin
  `c8222cc67a399bfc01e8658dd14b30d5bfd634f9` plain `git am`
  22/22 PASS；replay HEAD
  `1a5af9c6d326730b3abf6b01a5de6ce43b3abd89`，replay/development
  tree 均为 `01a49f61bc9c1aa871a91914d0aa87aad8baec04`。临时
  replay worktree 已清理。

### 自审记录

结论：**PASS，可以进入独立 subagent review**。

- raw loader 的 load address 与 reset PC 都由同一个参数控制，默认值
  精确为 QEMU `-bios` 惯例 `0x00100000`；探针 trace 证明不是从
  PC=0 或 SE ELF entry 偶然启动。
- 三类 FullSystem translation（取指、load、store）都实际经过
  `TLB` identity 分支：O1 同时执行低地址取指与高地址 marker
  store/load；任一仍走 SE page table 或未设置 paddr 都会失败。
- `dadao_se.py` 和 interrupts 实现未改；SE 三组专项回归、81项 E2E、
  200项 differential 均保持原数字。
- 范围严格停在 carrier：没有实现页表步进、A/D、fault route、TLB
  缓存、timer/UART/外部中断或 firmware/kernel。

### 独立 subagent 审阅记录

首轮结论为 **NEEDS CHANGES**，实现本身无问题，指出两项测试证据缺口：

1. FullSystem runner 当时只断言退出码，没有自动比较 SE 的寄存器、
   memory dump 和 trace，且完成区忽略了 SE/FS `rb1` 栈初值差异；
2. `SIM_END` 只解析 code，未锁定 cause，同码错误路径可能假绿。

已补为每例 FS raw + 独立 SE baseline 双跑：只归一化 code-window
装载基址、明确排除 `rb1` 环境差异，其余 REGDUMP、完整 MEMDUMP 和
CFX trace 全比较，并锁定 `halt`/`ILLI`/`CFXREG`。同一 reviewer
delta review 独立解析 16 组保存日志后确认两项 finding 全部关闭，
最终结论为 **PASS，无剩余 findings**。审阅过程只读，未修改文件。
