# KL-126a：PTW（页表步进）成功路径 in gem5

**执行环境**：远端 Codex（本仓库），gem5 源码改动
（`~/DADAO-gem5`，独立仓库，不是本仓库子目录）

## 背景

`KL-125a` 已在 QEMU 里实现了 `cfx_ptw` 的完整成功路径（VA→PA 转换，
超页+普通页两条路径），并独立验证通过（8/8 判别性探针 + 29/29
patch-series 重放）。本任务是**同一套语义在 gem5 里的移植**——
gem5 目前完全没有 `cfx_ptw` 的任何存储/寄存器/转换逻辑：
`src/arch/dadao/tlb.cc` 的 `translateAtomic`/`translateFunctional`
在 `FullSystem` 模式下恒等映射 VA→PA（`KL-124a` 引入，当时明确是
临时占位，专为 FullSystem carrier 打通退出路径服务）。

**范围边界与 QEMU 侧完全一致**：只做成功路径，故障处理
（PTBR 权限不符/未使能之外的失败、Present=0、SPF/GPF=0、R/W/X 权限
不符）和 A/D 位硬件回写都不在本任务范围（`KL-128a`，gem5 侧的
fault/A-D 对应任务）。TLB 缓存也不在范围内（当前无存储，"每次都
走完整 walk" 是预期行为，不需要额外代码"关闭 TLB"）。

**SE 模式完全不碰**——`translateAtomic`/`translateFunctional` 里
`FullSystem` 为 false 时走 `tc->getProcessPtr()->pTable->translate()`
的分支必须保持原样，本任务只改 `FullSystem` 分支。

## 目标

把 QEMU 侧 `dadao_ptw_translate()` 的算法在 gem5 里逐字段移植一遍，
接口形态遵循 gem5 已有的 carrier 惯例（参考 `KL-122a` 的
`cfxPreciseTrapEnter()`——复杂状态机逻辑集中在一个独立、可测试的
helper 函数里，不要把算法直接摊开写进 `TLB::translateAtomic` 函数体）：

1. **寄存器存储**：在 `ISA`（`src/arch/dadao/isa.hh`/`isa.cc`）里加上
   与 QEMU 对称的 `cfx_ptw` 状态：4 种 run mode 的 permission、PTBR
   enable、PTBR（48位）、PTHI/PAHI（各16位）。reset 默认值与 QEMU
   一致（user/jail perm=0，supv/hypv perm=全1，enable/PTBR/PTHI/PAHI=0）
   ——具体寄存器编号/复位值以 wiki 原文和 `KL-125a` 完成区描述的
   `cg8`(perm/enable)/`cg9`(PTBR)/`cg10`(PTHI)/`cg11`(PAHI) 映射为准，
   自己核对 wiki，不要凭记忆。
2. **寄存器读写接入**：在 `CFX2RCInst::execute()`/`CFX2RDInst::execute()`
   （`src/arch/dadao/decoder.cc`）里加上对应 `(cg,rc)` 分支，写法参考
   同文件里 `KL-122a` 的 cg5 分支（`switch (rc_) { case ...: return NoFault; }`
   风格）。
3. **转换逻辑**：新增一个 helper（例如 `ISA::ptwTranslate()` 或独立
   自由函数，命名自定，但要跟现有 `cfxPreciseTrapEnter` 之类的命名
   风格保持一致），实现与 QEMU `dadao_ptw_translate()` 完全对称的算法：
   PTBR permission 检查 → enable=0 时48位 identity+RWX → enable=1 时
   读 L1 PTE（big-endian）→ SP=1 超页分支（Present/SPF/权限检查 +
   `PAHI|L1.PPN|VA[28:0]` 拼 PA）→ SP=0 普通页分支（读 L2 PTE，
   Present/GPF/权限检查 + `PAHI|L2.PPN|VA[15:0]` 拼 PA）。gem5 里
   "读物理内存"用 `tc`/`ThreadContext` 的现有内存访问接口
   （参考 `src/arch/dadao` 目录里其它需要旁路读内存的代码找惯用
   模式，不要自己发明新的内存访问路径）。
4. **接入 `translateAtomic`/`translateFunctional`**：`FullSystem`
   分支里，PTBR enable=1 时调用上面的 helper 做转换，替换掉当前的
   恒等映射；PTBR enable=0 时仍是恒等映射（这与 QEMU 的 enable=0
   语义一致，不是巧合）。

## 约束

- **只实现成功路径**，故障/A-D 是 `KL-128a` 的范围，本任务不产生
  任何异常，失败场景行为未定义也没关系。
- **不实现 TLB 缓存**。
- **不改动 SE 模式路径**。
- 转换算法要与 QEMU `dadao_ptw_translate()`（`.work/source/qemu/target/dadao/cpu.c`，
  `KL-125a` 引入）逐位对称——如果两边对同一 VA/页表内容算出不同的
  PA，就是本任务的 bug，不是"gem5 有自己的实现自由度"。
- 完整 patch-series bare-pin replay（tree-hash 比对）是硬性验收项
  （gem5 侧惯例，参考 `KL-124a`/`KL-117a` 完成区的重放方法）。
- 完成后写「完成区」+ 自审记录；继续沿用"自己开 reviewer subagent
  复核"的方法。
- 现有全部 gem5 探针（`KL-113a`/`KL-117a`/`KL-120a`/`KL-122a`/`KL-124a`）
  零回归。

## 验收

- 复用/改编 `KL-125a` 的 8 个判别性场景（静态预建 L1/L2 页表，超页
  X/R/W 各一、普通页 X/R/W 各一、PTBR-disabled identity、寄存器
  读写往返），在 gem5 `dadao_fs.py` FullSystem 跑法下逐一重建，**用
  跟 QEMU 侧不同但等价的 VA/页表项数值**（不要直接照搬同一组数字，
  避免"复制粘贴期望值"掩盖真实实现差异）。
- 与 `KL-125a` 一样，验证 `pthi`/`pahi` 没有被混用——构造两者取不同
  值的场景。
- 与 `KL-125a` 一样，L1/L2 index 和 SPF/GPF fragment 用非零值（不要
  用全零索引/全零 bit 位置——`KL-125a` 的独立 reviewer 抓到过这个
  假绿风险，这里同样要避免）。
- 现有全部 gem5 探针零回归。
- patch-series bare-pin replay，tree hash 与开发树一致。

## 参考指针

- `code-agent/tasks/KL-125a-ptw-success-path-qemu.md` 完成区
  （QEMU 侧实现细节、判别性验证方法、独立 reviewer 抓到的两个
  Medium 发现——gem5 侧移植要主动规避同样的假绿模式）
- `~/DADAO-wiki/DADAO-12-SEE-主管系统运行环境.md` 第54-219行（完整
  地址空间/VA→PA转换算法）、第425-461行（`cfx_ptw` 专有寄存器表+
  异常原因表）
- `~/DADAO-gem5/src/arch/dadao/tlb.cc`（现有 `translateAtomic`/
  `translateFunctional`，本任务要改动的位置）
- `~/DADAO-gem5/src/arch/dadao/decoder.cc`（`CFX2RCInst`/`CFX2RDInst`
  的 `KL-122a` cg5 分支，作为新增 `(cg,rc)` 分支的写法参考；
  `cfxPreciseTrapEnter` 作为独立 helper 函数的命名/组织风格参考）
- `~/DADAO-gem5/tests/dadao/dadao_fs.py`（FullSystem 探针跑法，
  三段 `SimpleMemory` range 的既有写法；如需新增高物理地址 alias
  供判别性测试用，参考本文件里现有 range 的加法）

## 完成区（2026-07-26）

### 实现

- gem5 `ISA` 新增与 QEMU 对称的 cfx_ptw private storage：
  `cfxPtwPerm[4]`、`cfxPtwPtbrEnable`、`cfxPtwPtbr[64]`、
  `cfxPtwPthi[64]`、`cfxPtwPahi[64]`。reset 为 user/jail=0、
  supv/hypv=全1，其余为0；`copyRegsFrom()` 同步复制全部状态。
- `cfx2rc`/`cfx2rd` 仅在 cfxcode=4 时接入 cg8/9/10/11。PTBR 保留
  48 位，PTHI/PAHI 截为16位；原有其它 CFX 分支及 SE 模式不变。
- `ISA::ptwTranslate()` 集中实现 permission→enable→L1→超页/普通页
  的成功路径。PTE 通过 `System::physProxy` 按 big-endian 读取：
  - enable=0：48-bit identity；
  - 超页：SP/P/SPF/单项 R/W/X，`PAHI | L1.PPN | VA[28:0]`；
  - 普通页：用 PTHI 拼 L2 PTE 物理地址，检查 P/GPF/单项 R/W/X，
    再用 PAHI 拼最终 `PA | VA[15:0]`。
  `translateAtomic()`/`translateFunctional()` 的 FullSystem 分支共用该
  helper；SE 的 process page-table 分支未改。
- 按任务范围，失败检查不进入精确异常/A-D 回写；当前以明确的
  “failure handling not implemented” simulator panic 阻止伪造成功
  translation。没有架构 TLB。
- `DADAOBareMetal` 支持可选 raw data image，使静态 L1/L2 PTE 可由
  FullSystem workload 在启动时加载到 `0x80000000`。
- `dadao_fs.py` 使用无 cache/coherent requestor 的 `IOXBar`，并通过
  `RangeAddrMapper` 提供两个64 KiB alias：
  - L2 structure `0x0003_0000_8500_0000` → backing `0x80200000`；
  - final leaf `0x0004_0000_8060_0000` → backing `0x80400000`。
  因而忽略或互换 PTHI/PAHI 都不能命中正确 backing。

### 判别性验证

新增 `tests/scripts/run_kl126a_gem5_ptw_success_probes.py`，8/8 PASS，
每项 gem5 process rc 与 `SIM_END` code 均为42：

- private register write/readback：四种 mode permission、enable、48-bit
  PTBR、16-bit PTHI/PAHI truncation；
- PTBR disabled identity：PTBR[0] 写无效值后仍可 identity 访问
  `0x80002000`；
- superpage X/R/W：PTBR index=3、L1 index=9、SPF fragment=5，
  三个 PTE 分别只给 X/R/W 单一权限；
- normal-page X/R/W：PTBR index=4、L1 index=11、L2 index=13、
  GPF fragment=6，PTHI=3、PAHI=4，三个 PTE 分别只给 X/R/W；
- runner 精确断言每条 trace 的 VA、leaf PTE physical address、最终
  PA、access=2/0/1 和 prot=4/1/2。上述数值与 KL-125a 不同。

原始日志位于 `.work/evidence/kl126a-gem5-ptw/`。

### 回归

- `scons build/DADAO/gem5.opt -j4`：PASS（仅既有依赖/代码 warning）。
- KL-124a FullSystem raw matrix：
  KL-113a=`42/130/134/42`、KL-117a=`153/43`、
  KL-120a=`44/130 + 7x45 + 43`，每项 FS=SE。
- KL-122a generic cfx_ptw frame/vector/escape：`46/46`。
- `.work/build/llvm/bin/llvm-lit -sv tests/lit/E2E/`：81/81 PASS。
- `tools/run_differential.py`：
  `AGREE(3-way)=200`、gem5-SKIP=2、DIVERGE=0；
  `AGREE(4-way)=200`、Sail-SKIP=2、SAIL-DIVERGE=0。
- `scripts/manifest_check.py`、`scripts/check_issues.py`
  （Open 24 / Closed 43 / Total 67）、gem5 源码及根仓 task/runner/docs
  `git diff --check`：PASS。根仓若把新增的 serialized format-patch
  本身再次作为源码检查，会像既有 0022/0029 一样把 unified-diff
  context 空行前缀误报为 trailing whitespace；这不是被应用源码中的
  空白，0023 的 plain `git am` 与 replay tree 证据见下。

### 提交、patch series 与重放

- gem5 commit：
  `c845a02eb2bc4a2d27dba7f4b974862e65c9eb02`；
  patch
  `components/gem5/patches/0023-arch-dadao-implement-PTW-success-path-KL-126a.patch`。
- commit/patch stable patch-id 均为
  `ca5015c006062b597b5db1960691207ba18d152d`。
- 从 manifest pin `c8222cc67a399bfc01e8658dd14b30d5bfd634f9`
  plain `git am` 23/23 PASS；replay HEAD
  `aef88608b8995b9614c06f8cf933ec584bcf8f8e`，replay/development
  tree 均为 `b545288e991a840e0d5385b64d2568fe79cf82d7`。
  临时 replay worktree 已清理。

### 自审记录

结论：**PASS，可以进入独立 subagent review**。

- 逐位复核 QEMU `dadao_ptw_translate()` 与 wiki §2.2：48-bit VA mask、
  PTBR/L1/L2 index、SP/P、PPN mask、SPF/GPF fragment、R/W/X 位和
  PTHI/PAHI 拼接一致；PTE 读取显式为 big-endian。
- PTBR permission 在 enable 判断之前；默认 hypv permission 允许
  index0，所以 reset ROM identity 取指仍成立。
- `translateAtomic()` 与 `translateFunctional()` 共用同一 helper；
  `FullSystem == false` 的原 SE page-table 路径字节级未改。
- alias 是真实总线映射，不是 trace-only oracle；normal write 通过
  disabled index0 读取 low backing 验证，能判别 PAHI 路由。
- 没有扩大到 failure exception、A/D、architectural TLB、interrupt、
  firmware 或 kernel。

### 独立 subagent 审阅记录

结论：**PASS，无 findings**。

独立 reviewer 只读核对 wiki、QEMU KL-125a、gem5 实现、runner 和任务
声明，复跑专项 8/8（每项 rc/SIM_END 均42），确认 SE page-table 路径
未变、PTHI=3/PAHI=4 使用真实 alias/backing 且没有 trace 假绿。它还
独立核对 commit/patch stable patch-id
`ca5015c006062b597b5db1960691207ba18d152d`，从 manifest pin plain
`git am` 23/23 后 replay/development tree 均为
`b545288e991a840e0d5385b64d2568fe79cf82d7`。审阅过程未修改文件，
临时 replay worktree已清理。
