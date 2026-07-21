# KL-102a：kernel CFX state / patch-surface 评估

日期：2026-07-21。范围是只读实现前评估；本次只写本报告，不修改 QEMU、gem5、patch、contract 或测试文件，不运行长测试。

证据标签：

- **[正式契约]**：`contracts/*` 或 KL-101a 对 HBI/SEE 的已核对引用。
- **[源码事实]**：`.work/source/qemu` 当前源码、`.work/source/gem5` 当前源码，或现有 patch 的明确内容。
- **[实现建议]**：KL-102a 的最小后续 patch 设计，不代表已实现。

## 结论

当前两端都没有可证明的真实 CFX 状态机。QEMU 只有 `EXCP_CFXTRAP` 加 host-side `cfx_smon` responder；gem5 当前 checkout 没有 `src/arch/dadao`，只能以 `components/gem5/patches` 中的拟议架构代码为事实依据，且 `0010` 直接在 `TrapInst::execute()` 中调用 SE/host 行为。

KL-102a 的最小交付应只覆盖：每 hart 的 mode/mask/code、`cfx_power` 的 prev/cause 现场、`cfx2rc` delegation、`escape cfx_power,0` 的 O1 handoff，以及一个可复核的未授权或被 mask 的 O2 fault。`cfx_smon` 的真实 guest handler、MMU、完整 CFX 指令集和 nested trap 不应进入本切片。

## 1. 契约边界

### 1.1 正式要求

`docs/reviews/KL-101a-independent-review-20260721-r2.md` 已接受的基线是：HBI/SEE 要求 reset 后 `inner_run_mode=hypv`、`inner_cfx_code=cfx_power`、`inner_cfx_mask=全 1`，PC 进入 `cfx_power_hypv_excp_vector`；最小 hypv→supv 顺序为清 delegation、写 `cfx_power_excp_prev_run_mode= supv`、写 `cfx_power_excp_prev_cfx_mask=全 1`、写 `cfx_power_excp_cause_ip`，再 `escape cfx_power,0`。该报告的源码核对与顺序见 `docs/reviews/kernel-hypv-supv-handoff-20260721.md:15-36`、`:98-115`。

### 1.2 仓库契约的限制

`contracts/isa/spec.md:50-52` 只冻结 `rb0` 的 SEE reset-vector 关系，并把完整 power-on state 标为 C-18 partial/open；`:947-959` 明确将 `trap`、`escape`、`cfx2rd`、`cfx2rc`、`cfxld`、`cfxst` 排除在 M1 之外。`contracts/exception/README.md:3-4` 明确 full CFX routing、masking、nesting、escape deferred。因此下文 O1/O2 是后续实现建议，不能倒写成现行 M1 contract 已实现。

## 2. 具体承载点

### 2.1 QEMU

| 语义 | 当前事实 | KL-102a 建议承载点 |
|---|---|---|
| `inner_run_mode`、`inner_cfx_mask`、`inner_cfx_code` | `CPUDADAOState` 当前只有 RD/RB/RF/RA、`pc` 和 `trap_*` scratch（`target/dadao/cpu.h:49-59`），没有 inner state。 | 仍放 `target/dadao/cpu.h` 的 `struct CPUArchState`，作为每个 QEMU CPU 的架构状态；用明确的 mode/code/mask 类型，避免复用 RB 或 `trap_*`。 |
| reset 初值 | `dadao_cpu_reset_hold()` 只清四个 register bank，设置 `env->pc=0x00100000`（`target/dadao/cpu.c:40-57`）。 | 在 `target/dadao/cpu.c` 的 reset hold 同时初始化 hypv、power code、全 1 mask 和 power frame；测试机 `0x00100000` 入口必须继续作为显式 test-machine profile，不得无声地冒充 HBI power vector。 |
| decode / 指令入口 | `trap` 的 pattern 在 `target/dadao/insn.decode:165-168` 附近，当前 `trans_trap()` 在 `target/dadao/translate.c:452-464` 写 next PC 后调用 helper；没有 `cfx2rc`/`escape`。 | 只在 `insn.decode` 增加 O1/O2 所需的 opcode pattern；`translate.c` 只负责提取 code/operands、保持 precise PC，并调用新的 state-transition helper，不在 TCG 中复制权限/现场逻辑。 |
| helper / 状态转移 | `helper_trap()` 仅把 code/function 放入 scratch，设置 `EXCP_CFXTRAP` 并退出 loop（`target/dadao/helper.c:99-108`）；`helper_raise_exception()` 负责 precise PC（`:8-31`）。 | 在 `helper.c/.h` 增加集中式 `cfx2rc`、`escape`、enter/fault helper；所有 prev/cause 写入和恢复只从这一处完成。`helper_trap` 先保留为异常入口，不能继续直接等价于 host syscall。 |
| exception dispatch | `dadao_cpu_do_interrupt()` 在 `target/dadao/cpu.c:109-242` 分派；`EXCP_CFXTRAP` 的 `cfxcode==2` 直接读 `rd16..rd19`，写 host stdout、shutdown、brk/mmap 等（`:124-223`）；当前 `EXCP_ILLI` 没有独立 case，落入 default 的 panic code `0x82`（`:232-240`）。 | 在 `cpu.c` 增加独立的 SEE-style CFX enter/guest-vector dispatch：先保存 `prev_*`/cause，再更新 inner state 和 PC；O2 的 unauthorized/masked 结果走统一 fault class。现有 `cfx_smon` host responder 不应被改造成 O1/O2 的状态机。 |
| prev/cause 现场 | 当前不存在。 | 在 `CPUArchState` 增加按 CFX code 索引的最小 frame（至少 `prev_run_mode`、`prev_cfx_mask`、`cause_ip`）；O1 只需可靠实现 `cfx_power` slot，O2 对被测 code 使用同一结构。不要把现场塞进 `rb[]`、`trap_func` 或 host static 变量。 |

QEMU 的现有 patch series 是 18 项；trap/syscall 从 `components/qemu/patches/0013-dadao-trap-syscall.patch` 开始，后续 `0014-0018` 是 PC、brk、mmap 等配套，series 见 `components/qemu/patches/series:14-19`。没有现成的 inner state、`cfx2rc` 或 `escape` patch。

### 2.2 gem5

**源码事实：** `.work/source/gem5/src/arch/dadao` 当前不存在；
`components/gem5/patches/0001-dadao-arch-skeleton.patch` 只是拟议架构代码的
形状来源，不是当前可构建或可直接复用的实现。该 patch 的 `DADAOISA`、
`Decoder`、`faults`、`registers` 等文件路径可由其 `diff --git` 条目复核；例如
其中 `ISA::copyRegsFrom()` 仍有未定义的 `tc` 变量，说明 patch 链本身还需先
修复才能作为实现基线。已有 patch series 见 `components/gem5/patches/series:2-13`。

| 语义 | 现有拟议承载点 | KL-102a 建议 |
|---|---|---|
| `inner_run_mode`、`inner_cfx_mask`、`inner_cfx_code` | `src/arch/dadao/isa.hh/.cc` 已有 `ISA` 类和 `miscRegFile`；`registers.hh` 当前只定义一个 misc register。 | 把 inner state 作为 ISA/每-thread 的架构状态，优先扩展 `isa.hh/.cc` 的字段和 accessor；在 `registers.hh` 分配稳定的 CFX misc IDs 仅用于 trace/ThreadContext 观察，不占 RD/RB flat integer bank。 |
| reset / copy | `isa.cc` 构造函数调用 `clear()`，`isa.hh` 的 `clear()` 只清 `miscRegFile`；`copyRegsFrom()` 只复制 int/float/PC。 | 在 `ISA::clear()` 初始化 hypv/power/all-ones 和 frame，在 `copyRegsFrom()` 一并复制；O1 测试若仍使用 SE `0x00100000`，必须显式区分 SE test entry 与 HBI reset vector。 |
| decode / execute | `src/arch/dadao/decoder.hh/.cc` 是当前 decoder/StaticInst 入口；已有 `0002` 在 `decoder.cc` 译码算术，`0007` 增加 control-flow，`0010` 增加 `TrapInst`。`0010` 的 `TrapInst::execute()` 在 `cfxcode==2` 直接读 `RD_BASE+16..19` 并 host 处理。 | 在 `decoder.cc` 只加 O1/O2 所需 `cfx2rc`、`escape` 和 trap 的 StaticInst；execute 通过 ISA/CfxState helper 做状态转移，不能继续在 `TrapInst` 中直接 `std::cout`/`exitSimLoop`。 |
| prev/cause 现场 | 当前不存在；`isa.hh` 的 misc file 是最近的架构状态容器。 | 在 `isa.hh/.cc` 的 CFX state 中增加 per-code frame，至少包含 `prev_run_mode`、`prev_cfx_mask`、`cause_ip`；O1 先实现 power slot，O2 使用被测 code slot。 |
| exception dispatch / fault | `faults.hh/.cc` 目前定义 `IlliFault`、`MalignFault`、`UndiFault` 等；patch 说明 `invoke()` 以 SE exit code 结束模拟。 | 增加带 CFX code/PC/class 的 fault 或 dispatch helper；`faults.cc` 负责把 unauthorized/masked CFX 交给 ISA 的统一 enter-fault 路径，并保留 `ILLI=0x82` 等可观测 code。不要让 O2 直接用 generic `UnimplFault`（该类是 SKIP sentinel，不是架构 fault）。 |
| Python wiring | `DADAOCPU.py` 只把 CPU、Decoder、ISA、MMU 类连起来。 | O1/O2 状态应留在 C++ ISA/fault/decode 层；`DADAOCPU.py` 只需在确有参数时暴露 profile，不承载状态机。 |

gem5 的结论因此是“patch-defined surface”，不是“当前 gem5 已有实现”。现有 `0001` 自述 skeleton，`0006` 是 ILLI/MALIGN/UNDI fault，`0007` 是 control-flow/RAS，`0010` 才是 host/SE trap shortcut；没有可直接复用的 CFX dispatch。

## 3. 最小语义与 patch 顺序

### 3.1 O1：成功 handoff

**所需最小语义：**

1. reset 初始化 `hypv / cfx_power / mask=ALL-1 / power_vector`，并保留独立的测试机入口配置。
2. 仅实现 HBI 桩所需的 `cfx2rc` delegation 写入；至少能清除这 12 个列出的
   delegation：`umon`、`jmon`、`smon`、`ptw`、`tlb`、`cache`、`hart`、`llc`、
   `pmem`、`timer`、`uart`、`power`，而不实现 `cfx2rd/cfxld/cfxst`。这些是
   HBI §3 的逻辑字段名；当前 M1 排除 `cfx2rc`，所以本报告不声称存在可直接
   核验的 opcode/encoding，编码和 operand 形状必须在 KL-102a spec decision
   中冻结。
3. 仅实现 `escape cfx_power,0`：恢复 power frame 的 prev mode/mask，并跳到 `cause_ip+0`；power frame 的写入顺序必须先于 escape。
4. 给 handoff vector、supv entry、marker、PC 和 mode 产生可观察事件。O1 不需要真实 `cfx_smon` handler、MMU 或 nested trap。

### 3.2 O2：unauthorized / masked fault

**所需最小语义：** 从 hypv 访问仍被 delegation 的 CG，或从 supv 执行未授权/被 mask 的 `cfx2rc/trap`，二选一作为首个负例；两端必须判为同一 fault class、保留同一 faulting PC、不写成功 marker。这里沿用 KL-101a 的 `[推断/验收草案]` 标签。不要把“未建立 prev/cause 就 early escape 必须是 ILLI”当作已冻结语义；KL-101a r2 已指出 SEE escape 文字不足以证明该断言。

### 3.3 建议顺序

1. **先加状态容器和可观察协议：** QEMU `cpu.h/cpu.c`；gem5 `isa.hh/isa.cc/registers.hh`；定义 mode/code/mask、power frame 和统一字段。此步不改 host syscall 行为。
2. **再做 O1：** QEMU `insn.decode → translate.c → helper.c → cpu.c`；gem5 `decoder.cc → isa.hh/.cc`，再接 `faults.*` 的非 host 路由。先只覆盖 `cfx2rc` delegation 和 `escape cfx_power,0`。
3. **再做 O2：** 在两端同一集中 helper/ISA transition 中加入 authorization、delegation 和 inner/global mask 判断；拒绝路径返回 ILLI/相应 fault，且不改变架构状态或成功 marker。
4. **最后加短向量验收：** O1 一个成功 handoff，O2 一个负例；只做定向 smoke/差分，不跑长测试。两端通过后才由后续任务接 O3。

## 4. 明确留给后续任务的范围

- **O3 / `cfx_smon`：** 留给 KL-103a 或等价后续任务。现有 QEMU `cpu.c:130-223` 和 gem5 `0010:24-40` 是 host/SE shortcut，不计入真实 O3；后续必须由 guest handler 处理，再 `escape cfx_smon`。
- **MMU：** 当前 QEMU `dadao_cpu_tlb_fill()` 是 identity TLB、全读写（`target/dadao/cpu.c:244-262`）；gem5 patch 的 `DADAOMMU/TLB` 仍是 SE skeleton。KL-102a 不添加页表、权限或地址转换。
- **完整 CFX：** `cfx2rd/cfx2rc` 的完整寄存器语义、`cfxld/cfxst`、所有 monitor/delegation 组合以及完整 cfx code 生命周期留后续；本切片只实现 O1/O2 必要子集。
- **nested trap：** 不实现多层 frame、重入、嵌套计数或复杂 escape 恢复；本切片最多证明单层 power frame 和一个 O2 fault。

## 5. ML-014 shortcut 隔离与统一验收字段

### 5.1 隔离原则

KL-102a 不删除也不重写现有 shortcut。QEMU `EXCP_CFXTRAP` 的 `cfxcode==2` host responder 与 gem5 `TrapInst` 的 SE responder 保留为显式 legacy/compatibility 路径；真实 O1/O2 使用独立的 CFX state/dispatch 分支。后续若增加 profile 开关，应使 `legacy_cfx_smon` 与 `real_cfx_handoff` 互斥，并在输出中标注 profile，不能用 host syscall 成功替代 O1/O2 marker。

### 5.2 最小统一字段

以下是 **[实现建议/推断验收草案]**，不是现有协议；在 KL-102a 实现前，数值
编码、event 状态机、marker/rc 来源和 profile 互斥点都尚未冻结。两端拟使用
相同字段名和含义：

`backend`, `profile`, `event`, `pc`, `mode`, `cfx_code`, `cfx_mask`, `prev_mode`, `prev_mask`, `cause_ip`, `fault_class`, `marker`, `rc`。

在现有 contract 可复用的部分只固定 `hypv=3`、`supv=2` 的 mode 值和已有
fault convention；`cfx_mask` 位含义、event 枚举、marker/rc 生产点需在实现
任务中逐项冻结。O1 至少检查：`event=reset` 为 hypv/power，随后 `event=escape`，
`mode=supv`、`pc=supv_entry`、两端 marker 相同、`rc=0`。O2 至少检查：
`fault_class` 与 faulting `pc` 相同、marker 缺失/保持未写、rc 使用现有 fault
convention（ILLI 为 `0x82`；MALIGN/UNDI 仍分别为 `0x81/0x83`），差异只允许
在日志包装格式。`SIM_START`/`SIM_END` 可继续作为 gem5 外层包装，但不能代替
上述状态事件；real profile 还必须在 CFX dispatch 入口拒绝走 legacy host
responder，形成可审计的互斥检查点。

## 6. 可复核命令（只读）

```bash
cd /home/holight/DADAO-0628

# 契约与 KL-101a 基线
nl -ba contracts/isa/spec.md | sed -n '45,55p;947,959p;1143,1150p'
nl -ba contracts/exception/README.md
nl -ba docs/reviews/KL-101a-independent-review-20260721-r2.md
nl -ba docs/reviews/kernel-hypv-supv-handoff-20260721.md | sed -n '15,36p;40,74p;98,138p'

# QEMU state/reset/translate/helper/dispatch
nl -ba .work/source/qemu/target/dadao/cpu.h | sed -n '49,84p'
nl -ba .work/source/qemu/target/dadao/cpu.c | sed -n '40,57p;109,242p;244,262p'
nl -ba .work/source/qemu/target/dadao/helper.c | sed -n '8,31p;99,108p'
nl -ba .work/source/qemu/target/dadao/translate.c | sed -n '452,464p;1297,1382p'
nl -ba components/qemu/patches/series | sed -n '14,19p'

# gem5 当前 checkout 是否已有 DADAO；以及 patch-defined surface
test -d .work/source/gem5/src/arch/dadao && find .work/source/gem5/src/arch/dadao -maxdepth 1 -type f -print || echo 'NO_CURRENT_GEM5_DADAO_SOURCE'
rg -n '^diff --git|cfx|CFX|class ISA|class Decoder|class .*Inst|IlliFault|invoke\(' \
  components/gem5/patches/0001-dadao-arch-skeleton.patch \
  components/gem5/patches/0002-dadao-core-isa.patch \
  components/gem5/patches/0006-dadao-faults.patch \
  components/gem5/patches/0007-dadao-controlflow-ras.patch \
  components/gem5/patches/0010-dadao-trap-syscall.patch
nl -ba components/gem5/patches/series

# 只读检查本次目标文件与其他人的既有改动
git status --short --untracked-files=all
```

以上命令不访问 `~/toolchain` 或 `~/knowledge-graph`，也不启动模拟器或长测试。
