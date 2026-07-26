# K1 收尾项调研：MMU/TLB（PTBR/PTHI/PAHI）与完整中断分派

**日期**：2026-07-26

**范围**：只读核对 wiki、当前 QEMU/gem5 和旧项目结论；未修改
QEMU、gem5、LLVM、kernel、contracts 或 wiki，未运行测试、未编译。

**证据标签**：`[正式契约]`=当前 wiki/ADR 原文；`[已有实现]`=当前
QEMU/gem5 源码事实；`[推断]`=据此形成的任务边界或待决结论。

## 结论先行

1. `[正式契约]` K1 剩余范围不是“增加几个 SBI 调用”。wiki 定义的是：
   64 个由 `VA[47:42]` 选择的地址空间、硬件两级 page walk、512 MiB 超页与
   64 KiB 普通页、fragment、R/W/X、硬件 A/D 原子回写、可选硬件 TLB、
   `cfx_ptw`/`cfx_tlb` 两条故障入口，以及一套含 mask/pending/counter 的
   通用精确异常状态机。ADR-0015 也明确要求 QEMU+gem5 双后端并拆成增量任务
   （`docs/adr/0015-kernel-bringup-charter.md:32-40`）。
2. `[正式契约]` wiki 采用**硬件 page walker + 硬件 TLB fill**，不是软件
   TLB-refill 架构：TLB miss 后硬件继续 page walk，成功后填充；仅命中后的
   fragment/权限故障进入 `cfx_tlb`，再由其 guest handler 委托 `cfx_ptw`
   （`DADAO-12-SEE-主管系统运行环境.md:96-110,137-156,480-495`；
   `DADAO-22-SBI-主管系统二进制接口.md:316-390`）。
3. `[已有实现]` 当前 QEMU 仍把 VA 恒等映射为 PA，`cpu_exec_interrupt()`
   永远返回 false，机器也没有 timer/UART IRQ 设备
   （`.work/source/qemu/target/dadao/cpu.c:452-469`；
   `.work/source/qemu/target/dadao/translate.c:1504-1517`；
   `.work/source/qemu/hw/dadao/dadao-machine.c:49-90`）。当前 gem5 TLB
   明确只调用 SE process page table，FullSystem 直接 panic；中断控制器恒定
   “无中断”，现有 runner 是 SE + AtomicSimpleCPU
   （`~/DADAO-gem5/src/arch/dadao/tlb.cc:14-37`；
   `~/DADAO-gem5/src/arch/dadao/interrupts.hh:12-21`；
   `~/DADAO-gem5/tests/dadao/dadao_se.py:18-24,40-51`）。因此 gem5 侧在
   MMU port 前还需要一个独立 bare-metal/FullSystem carrier 任务。
4. `[已有实现]` KL-116a/KL-117a 只实现了 `cfx_smon/CFXTRAP` 的步骤7-10
   窄切片，明确没有步骤2-6和通用 cg4/cg5 基础设施
   （`.work/source/qemu/target/dadao/cpu.c:148-164`）。现有 `cfx2rc`
   也是 O1/O2/O3 所需的窄白名单；`cfx2rd` 在 QEMU/gem5 都没有指令实现。
   SBI 示例大量依赖 `cfx2rd`，所以“通用 CFX 寄存器访问 + 通用异常现场”
   必须先于 MMU、timer 和外部中断。
5. `[正式契约]` page fault 全部不可屏蔽，进入后跳过步骤3-5；真正首次覆盖
   mask/pending 的最小场景是 TIMER/UART/IPI 等异步可屏蔽中断
   （`DADAO-12-SEE-主管系统运行环境.md:440-461,480-493,593-600,617-628,
   693-699`）。因此同步 PTW/TLB fault 与异步分派可以在共享基础设施后分两条
   链推进，最后再做组合回归。
6. `[推断]` 不能立即下发一个“大 MMU+中断实现任务”。先要收敛至少五个
   真实 wiki 空白：通用 pending 的寄存器落点、同一 cfx 内多个 cause 的
   优先级、嵌套 cfx 返回时 `inner_cfx_code` 的恢复、timer 的计数/触发/
   清除语义，以及外部中断/UART 设备协议。建议先做一个契约冻结任务，再按
   报告末尾的 QEMU-first / gem5-port 序列推进。

---

## §1 MMU/PTW/TLB 正式契约

### 1.1 地址空间、PTBR/PTHI/PAHI 与页表格式

`[正式契约]` CPU 内部 VA 有效 48 位；`VA[47:42]` 同时选择 64 个 PTBR
之一。对应 PTBR 未使能时不做转换，只能访问核内资源；使能后才产生 64 位
外部 PA（`DADAO-12-SEE-主管系统运行环境.md:54-58,75-94`）。

| 项 | wiki 定义 | 访问位置 |
|---|---|---|
| PTBR 权限 | U/J 默认全禁，S/H 默认全允，按 64 个 PTBR 的位图控制 | `cfx_ptw` cg8/rc0-3（`:425-435`） |
| PTBR enable | 64 位位图；0=核内地址，1=虚拟地址转换 | cg8/rc8（`:435`） |
| PTBR[0..63] | 一级页表基址 bits[63:16]，64 KiB 对齐 | cg9/rc0-63（`:436`） |
| PTHI[0..63] | page walk 访问页表结构时的 PA[63:48] | cg10/rc0-63（`:437`） |
| PAHI[0..63] | 最终数据/取指 PA[63:48] | cg11/rc0-63（`:438`） |
| TLB enable | 按 PTBR 集合使能；复位值等于硬件 `exist` | `cfx_tlb` cg8/rc8（`:463-476`） |
| TLB invalidate | 全部或按 `start/size` 范围 | cg12/rc0,2,3（`:471-478`） |

`[正式契约]` L1 有 8192 个 8-byte PTE。L1 可直接描述 512 MiB 超页，也可
指向同样有 8192 项的 L2；L2 描述 64 KiB 普通页
（`:81-85,121-126,165-219`）。超页/普通页又分别用 SPF/GPF 分成 8 个
64 MiB/8 KiB fragment（`:194-219,229-231`）。PTE 的 A/D 位由硬件同时
更新 TLB 和主存 PTE，主存更新必须是原子 read-modify-write（`:198,217`）。

`[推断]` 实现验收不能只覆盖“VA→PA 算对”：至少要分别钉住普通页/超页、
取指/读/写权限、fragment、A/D、PTHI 与 PAHI 不混用，以及异常优先级。
wiki 已给出 page fault 内部优先级：mode permission → L1 present →
SPF → L2 present → GPF → R/W/X（`:242-263`）。

### 1.2 硬件与 SBI guest handler 的分工

`[正式契约]` 硬件负责：

- 按 mode/PTBR-enable 选择核内访问或地址转换；
- 查 TLB；miss 时做 page walk 并 fill；
- 读取 L1/L2 PTE、检查 present/fragment/R/W/X、形成 64 位 PA；
- 更新 A/D；
- 根据故障发生在 walk 还是 TLB hit 路由到 `cfx_ptw` 或 `cfx_tlb`
  （`:89-117,130-163,689-690,756-759`）。

`[正式契约]` SBI guest handler 负责配置/读取 PTBR、权限、enable、
PTHI、PAHI，提供 PTE 更新/故障处理服务，以及按范围 invalid TLB
（`DADAO-22-SBI-主管系统二进制接口.md:133-150,293-300`）。所以“SBI式
操作”是硬件 walker 上的软件管理接口，不能把 TLB miss 误实现成软件 refill。

`[正式契约]` `cfx_ptw` 的 18 类原因（含通用 CFXTRAP/CFXMEM/CFXREG）
全部不可屏蔽；`cfx_tlb` 只保留权限和 fragment fault 子集，也全部不可屏蔽
（`DADAO-12-SEE-主管系统运行环境.md:440-461,480-495`）。TLB-hit fault
先进入 `cfx_tlb`，handler 调用 `SBI_PTW_HANDLE_FAULT`，成功后 invalid/
重新取得表项并尝试 `escape ...,0` 重试，失败则跳过（SBI `:316-390`）。
但这段委托的**返回链本身未闭合**，见 §1.3。

### 1.3 SBI 中未闭合的部分

`[正式契约]` SBI 的函数表完整列出了 `SET_PTE` 和 `HANDLE_FAULT`
（`:137-146`），但正文实现仍是 TODO/省略号（`:248-256`）；下游依赖的
`cfx_pmem` 物理页枚举/分配/释放同样全部是 TODO（`:440-509`）。

`[正式契约]` SBI 还要求 `cfx_tlb` handler 通过 `trap cfx_ptw` 嵌套委托，
ptw 返回后由 tlb handler invalid 并 `escape cfx_tlb,0`（`:353-372`）。
然而 SEE 的 `escape` 明确用**当前** `inner_cfx_code` 选择 frame，只恢复
mode/mask/PC，从未恢复 `inner_cfx_code`
（`DADAO-12-SEE-主管系统运行环境.md:813-844`）。因此 PTW self-escape 后
`inner_cfx_code` 仍为 ptw，继续执行 tlb handler 时再
`escape cfx_tlb,0` 会把“操作数 cfx_tlb”当成 cross-cfx escape，却仍读取
ptw frame。`[推断]` 这是 SBI 示例与 SEE 退出状态机之间的阻断级缺口；
在定义 prev-cfx 栈/寄存器或等价恢复规则前，不能声称 TLB→PTW→TLB 委托
已闭环。

`[推断]` 这不阻止先实现并验证硬件 walk、静态 PTE 和 fault 分类，但它阻止
当前任务替未来 Linux 自行发明“缺页时如何分配/装载 fragment/PTE 如何映射”
的固件策略，也阻止直接照抄 SBI 的嵌套返回示例。K1 可先用预建页表和
ptw self-handler 验证 walk-origin fault；TLB-hit 委托必须等嵌套返回契约冻结
后再验 retry/skip。真正内核 fault policy 必须在后续 kernel ABI 任务中
另行定义。

---

## §2 完整异常/中断分派正式契约

### 2.1 步骤2-6与现有 O3 的关系

`[正式契约]` 所有同步异常和异步中断都是精确异常；同步 PC 指向触发指令，
异步 PC 指向下一指令边界，访存/寄存器/RA 无副作用。中断为电平触发，
多个 cfx 同时 pending 时低 cfxcode 优先（SEE `:650-660`）。但同一句提到
“多个 pending 位”，没有规定**同一个 cfx 内**多个 cause 同时 pending 时
选择最低位、最高位还是其它优先级；这是异步分派前必须冻结的独立空白。

entry flow 在选出目标 cfx 后执行：

1. nonmaskable 位为 1：跳过 mask，直接到步骤6；
2. 否则依次检查 `inner_cfx_mask`、共享 `global_cfx_mask` 和该 mode 的
   `excp_cause_mask`；同步被前两级挡住转 ILLI，异步被挡住 OR 到 pending；
3. 递增 trap/sync/async counter；
4. 保存 prev mode/mask，切换 mode/mask/cfx，保存 cause id/ip/info，跳向量
   （SEE `:678-706,763-810`）。

`[已有实现]` QEMU O3 代码自己明确声明只覆盖 `cfx_smon/CFXTRAP` 的步骤7-10，
因为该 cause 不可屏蔽；步骤6 counter 也排除在外
（`.work/source/qemu/target/dadao/cpu.c:148-164`）。CPU state 只有
`cfx_power` 三字段和 `cfx_smon` 一份窄 frame
（`.work/source/qemu/target/dadao/cpu.h:59-78,119-152`）。gem5 同样只有
这两份窄状态（`~/DADAO-gem5/src/arch/dadao/isa.hh:54-73,95-108`）。

`[推断]` 后续应先把 O3 的专用函数提升为共享 entry/exit carrier，再挂 PTW、
TLB、timer、UART；若各设备各复制一份入口逻辑，mask 优先级、精确 PC、
counter 和 nested frame 很容易漂移。

### 2.2 timer 与外部中断

`[正式契约]` `cfx_timer` 有 pending、mask、ctrl 和 8 个 counter：
pending 写0清位；mask 0=允许；ctrl bit0 enable、bit1 one-shot/periodic、
bit2 decrement/increment。TIMER 是 maskable cause bit10
（SEE `:582-600`）。SBI 初始化还要求设置 supv vector 并清共享
`global_cfx_mask` 的 cfx18 位（SBI `:521-560`）。

`[正式契约]` wiki 没有定义 PLIC/通用外部中断控制器。它只说外设按中断源
路由到相应 cfx（SEE `:40-42`），并具体定义 UART0..31 为 cfx_uart 的
maskable cause bit32..63及 `uart_pending`（SEE `:602-628`）。UART0 的
64 个设备寄存器却只写“参照硬件协议”，SBI 也没有给出 IRQ 拉高/撤销、
source clear 与 pending ack 的顺序（SEE `:606-615`；SBI `:625-680`）。
因此 `[推断]` K1 不能凭空实现 PLIC，也不能仅凭 cause 表声称 UART0 设备
协议已经定义：要么先冻结最小 UART0 协议，要么把首个外部中断切片明确标成
“合成外部 IRQ source”，不声称 UART 实现。

### 2.3 真正的 wiki 空白/矛盾

以下只给出 `docs/wiki-deviations.md` 候选草稿，不在本任务直接修改该文件。

#### 候选A：通用 `pending` 的寄存器落点未定义

- **wiki 状态**：SILENT/CONTRADICTS-BY-OMISSION
- **wiki 原文引用**：异常流程要求
  `cfx_⟨cfxname⟩_pending |= cause` 并可写0清除
  （SEE `:694-699,767-785`）；共有 cg4/cg5 表只有 counters/frame，没有
  pending（`:337-364`）。timer/UART/power 各有专用 pending
  （`:588,608,636`），但例如带可屏蔽 IPI 的 cfx_hart 没有 pending 寄存器
  （`:515-536`）。
- **建议决定**：在实现步骤2-5前，由架构任务明确“所有 cfx 的通用 pending”
  还是“只有产生异步原因的 cfx 有专有 pending”，冻结其 cg/rc，并规定
  同一 cfx 多个 cause 同时 pending 时的 cause 优先级；禁止后端自选。
- **影响范围**：QEMU/gem5 CFX state、`cfx2rd/cfx2rc`、timer/UART/IPI、
  FPEXCP pending 与中断重入。
- **状态**：OPEN。

#### 候选B：timer 的时间基准、到期和 ack/reload 语义未闭合

- **wiki 状态**：CONTRADICTS-BY-OMISSION
- **wiki 原文引用**：函数表称“在 timeout（周期计数值）时触发”
  （SBI `:516-519`），示例称“timeout 周期后”
  （`:583-591`），实现却把 timeout 写入 counter 后设为 decrement one-shot
  （`:565-576`）。SEE 只定义 ctrl 位和 pending 写0清，不定义到0/溢出时机、
  one-shot 是否自动停、periodic reload 值、counter 与 hart cycle 的关系
  （SEE `:582-600`）。中断 handler 只 `escape ...,0`，没有清 pending
  （SBI `:578-580`），与电平触发语义组合后可能立即重入。
- **建议决定**：K1 先冻结一个最小可测 profile：counter0 相对递减；
  0→pending bit10；one-shot 自动停；software write-0 ack；periodic 的 reload
  来源在单独条款中明确。`GET_TIME` 是否为 wall-cycle 必须与“读 counter0”
  二选一。
- **影响范围**：QEMU timer、gem5 event、SBI timer handler、kernel clockevent。
- **状态**：OPEN。

#### 候选C：TLB 容量/替换策略未定义（非架构阻断）

- **wiki 状态**：SILENT
- **wiki 原文引用**：只规定 64 个逻辑集合和“硬件可简化集合数量，但必须与
  软件约定一致”（SEE `:463-478`），未规定每集合容量、相联度或替换策略。
  集合是否存在并非空白：`cfx_tlb_exist` 已提供集合存在位图，enable 也按其
  复位（`:467-470`）。
- **建议决定**：K1 功能模型只承诺架构可见 hit/miss/invalidate/fault 语义，
  容量与替换不作为性能声明；QEMU/gem5 采用同一固定测试 profile，并在探针
  中公开其 `tlb_exist`/enable 约定。
- **影响范围**：双后端差分测试与后续性能声明。
- **状态**：OPEN，但不阻断 PTW/异常基础设施。

#### 候选D：K1“外部中断”没有通用控制器或完整 UART 协议

- **wiki 状态**：SILENT
- **wiki 原文引用**：SEE 仅给出按设备 cfx 路由原则（`:40-42`）和 UART
  原因表（`:602-628`），全文无 PLIC/通用外部中断控制器定义；UART0
  寄存器只写“参照硬件协议”，SBI handler 没有 source clear/ack 流程
  （SBI `:625-680`）。
- **建议决定**：若 K1 要把外部中断称为 UART0，先冻结最小数据/状态寄存器、
  IRQ 拉高/撤销和 source/pending ack 顺序；否则只做“合成外部 IRQ source”
  验证通用分派，不声称 UART 实现。其它控制器另立 ADR/wiki 条目。
- **影响范围**：QEMU machine、gem5 platform、kernel irqchip/serial。
- **状态**：OPEN。

#### 候选E：嵌套 cfx 调用没有 `inner_cfx_code` 返回恢复语义
（应升级既有 `docs/wiki-deviations.md` #9，不另起重复条目）

- **wiki 状态**：CONTRADICTS
- **wiki 原文引用**：SBI 要求 `cfx_tlb → cfx_ptw → cfx_tlb` 嵌套委托
  （SBI `:353-372`）；SEE `escape` 却按当前 `inner_cfx_code` 选择 frame，
  只恢复 mask/mode/PC，不恢复前一个 cfxcode（SEE `:813-844`）。共有
  exception frame 也没有 `prev_cfx_code`（SEE `:351-364`）。
- **建议决定**：在任何嵌套 handler probe 前冻结一个可嵌套的 cfx return
  规则，并明确单层/多层、跨 cfx shortcut 和同 cfx recursion 的关系；QEMU/
  gem5 必须共享同一规则。
- **影响范围**：SBI TLB→PTW、PTW→PMEM、所有 A→B→C handler 链、escape
  权限检查和 nested frame。
- **状态**：OPEN，阻断 TLB-hit fault 委托闭环。

#### 既有访问控制偏离对通用载体的约束

`[已有实现]` `contracts/isa/spec.md:1021-1031` 已记录：cross-cfx
`cfx2rc_cfx_mask` 的字面检查会使 HBI boot stub 非法，`cg_reg_deleg`
拒绝语义也尚未实现。`[推断]` KL-119a 必须确认沿用现有
`docs/wiki-deviations.md` #10/#11；后续“通用寄存器载体”只能先交付
K1 所需的存储/读写/CFXREG 路由，不得把它描述成完整访问控制实现。

---

## §3 当前实现缺口

### 3.1 QEMU

`[已有实现]`

- `dadao_cpu_mmu_index()` 恒为0，`dadao_cpu_tlb_fill()` 直接把同一 page
  address 作为 VA/PA，只有 fetch 时补 EXEC 权限
  （`.work/source/qemu/target/dadao/cpu.c:452-469`）。
- `dadao_cpu_exec_interrupt()` 永远返回 false
  （`.work/source/qemu/target/dadao/translate.c:1504-1507`）。
- machine 只有 ROM、exit MMIO、mmap arena 和 RAM，没有 timer/UART/IRQ 线
  （`.work/source/qemu/hw/dadao/dadao-machine.c:49-90`）。
- `CPUArchState` 没有 PTBR/PTHI/PAHI/TLB/timer/pending/counters；只有
  O1/O2/O3 窄状态（`.work/source/qemu/target/dadao/cpu.h:119-152`）。
- decode 表只定义 `cfx2rc`；全 target 搜索没有 `cfx2rd` 指令实现
  （`.work/source/qemu/target/dadao/insn.decode:170-172`）。

### 3.2 gem5

`[已有实现]`

- TLB 的 atomic/functional translation 都转交 SE process page table；
  FullSystem 明确 panic，flush/demap 是空操作
  （`~/DADAO-gem5/src/arch/dadao/tlb.hh:13-34`；
  `~/DADAO-gem5/src/arch/dadao/tlb.cc:14-45`）。
- `MMU` 只是通用 `MMUTranslationGen` 包装
  （`~/DADAO-gem5/src/arch/dadao/mmu.hh:13-27`）。
- `Interrupts::checkInterrupts()` 恒 false、`getInterrupt()` 恒 NoFault
  （`~/DADAO-gem5/src/arch/dadao/interrupts.hh:12-21`）。
- 现有 DADAO runner 固定 `DADAOAtomicSimpleCPU`、`mem_mode=atomic`、
  `SEWorkload`、`full_system=False`
  （`~/DADAO-gem5/tests/dadao/dadao_se.py:18-24,40-51`）。
- 当前 CFX ISA state 和 QEMU 一样只覆盖 handoff/O3 窄切片；全
  `src/arch/dadao` 搜索没有 `cfx2rd` 实现
  （`~/DADAO-gem5/src/arch/dadao/isa.hh:54-73,95-108`）。

`[推断]` “QEMU 任务完成后直接 port 到 gem5”只对纯指令状态成立。MMU 和
外设中断的 gem5 port 前，必须先建立可加载 bare-metal image、提供物理内存/
退出设备并允许 FullSystem TLB/interrupt 路径工作的 carrier；否则所谓 gem5
MMU 测试仍会被 SE process page table 吞掉，形成错误绿灯。

---

## §4 旧项目仅继承的教训

`[已有实现]` 旧设计证明“无 MMU 时低 VA 用户 ELF 不能落到 RAM”是有效问题
（`~/toolchain/DADAO/code-agent/designs/dadao-mmu-enable-design.md:11-17`），
也识别了 MMU 打开后 early console/IO 映射必须预先准备
（同文件 `:31-38`）。它采用的顺序——页表格式与 TLB flush → 初始映射/
MMU enable → page fault handler——作为依赖方向仍合理（`:64-73`）。

但以下具体内容全部不可复用：

- 32-bit VA、4 MiB/4 KiB 页、32-bit PTE（`:19-60`），与当前 48-bit VA、
  512 MiB/64 KiB、64-bit PTE 不兼容；
- CP0 全局 TLB flush（`:149-163`），已被当前 cfx_tlb cg12 接口取代；
- `CSR_SATP`/`CSR_SSTATUS` 使能和固定 UART 映射（`:167-215`），与
  PTBR/PTHI/PAHI/CFX 模型不兼容；
- `CSR_STVAL`/DMMU fault 入口（`:227-248`），与 cfx_ptw/cfx_tlb 精确异常
  不兼容；
- IRQ/timer 当时明确延期（`:264-272`），不能当成已有结论。

`[推断]` 本轮真正应继承的是“低 VA 必须有真实翻译”“打开翻译前先保证
取指、栈、页表自身、异常向量、console/exit IO 都可达”“先 bare-metal
逐层验收再碰 Linux”，而不是旧代码中的任何常数、寄存器或 patch。

---

## §5 建议的增量任务序列

下列编号为**建议占位号**，正式任务文件下发时可调整。每一步都必须记录
spec oracle、显式 PASS/FAIL 数量和实际 backend；gem5 任务是独立 port，
不是同一任务的附带要求。

| 顺序 | 建议任务 | 范围与验收方向 | 后端/依赖 |
|---:|---|---|---|
| 1 | KL-119a 契约冻结 | 决定候选A-E：pending/cause 优先级、timer K1 profile与完整范围、TLB 测试 profile、外部源协议、嵌套 cfx return；确认沿用访问控制 deviation #10/#11。只写契约/偏离，不写实现。 | 无后端；除明确非阻断的 TLB 容量外，后续语义任务依赖 |
| 2 | KL-120a 通用 CFX 寄存器载体（QEMU） | 只把 K1 所需 common state、`cfx2rd`、受支持 `cfx2rc`、counter/frame 读回建成共享存储/路由载体；不声称补齐 cross-cfx/delegation 访问控制，回归 O1-O3 不变。 | QEMU；依赖119a |
| 3 | KL-121a 通用 CFX 寄存器载体（gem5） | 独立 port KL-120a，用同一寄存器探针验证 reset/read/write/非法访问。 | gem5 SE 可先验；依赖120a |
| 4 | KL-122a 通用精确异常入口（QEMU） | 将 O3 专用步骤7-10提升为任意 cfx 的共享不可屏蔽同步入口/exit，并补步骤6 counter；除精确 PC/frame 外，用合成 A→B→A 链验证 KL-119a 冻结的 cfx return。 | QEMU；依赖119a/120a |
| 5 | KL-123a 通用精确异常入口（gem5） | 独立 port KL-122a，保持 AtomicSimpleCPU 精确 fault/PC 与 nested return 语义。 | gem5；依赖121a/122a |
| 6 | KL-124a gem5 bare-metal/FullSystem carrier | 建立 DADAO bare-metal image loader、物理内存与退出 oracle，使 FullSystem translation/interrupt 路径可运行；仍保持 identity、无 MMU 功能。 | gem5；依赖123a，后续所有 gem5 MMU/IRQ任务依赖 |
| 7 | KL-125a PTW 成功路径（QEMU） | 实现 PTBR/PTHI/PAHI、mode/enable、TLB-off hardware walk；静态页表分别验证普通页/超页及取指/读/写的 VA→PA。 | QEMU；依赖122a |
| 8 | KL-126a PTW 成功路径（gem5） | port KL-125a 到 FullSystem carrier；同一 image/页表给出双后端差分结果。 | gem5；依赖124a/125a |
| 9 | KL-127a PTW fault/A-D（QEMU） | 增加 present/fragment/RWX/A-D、优先级和 `cfx_ptw` 精确入口；预建 guest handler 验证 retry/skip，不实现 Linux 分页策略。 | QEMU；依赖125a |
| 10 | KL-128a PTW fault/A-D（gem5） | 独立 port KL-127a，逐 cause 对齐 QEMU 的 cause id/info/IP 和 PTE A/D。 | gem5；依赖126a/127a |
| 11 | KL-129a TLB/invalid/命中故障（QEMU） | 实现 enable/exist、miss 后硬件 fill、hit、全量/范围 invalid；hit-origin fault 必须用真实 `cfx_tlb→cfx_ptw→cfx_tlb` probe 验证委托返回后再 retry/skip。 | QEMU；依赖119a/122a/127a |
| 12 | KL-130a TLB/invalid/命中故障（gem5） | port KL-129a；同一操作序列验证 hit/miss/invalidate/nested fault，不作性能声明。 | gem5；依赖128a/129a |
| 13 | KL-131a 可屏蔽异步分派核心（QEMU） | 实现步骤2-10的 inner/global/cause mask、pending、async counter、跨 cfx 与同 cfx cause 优先级、指令边界精确 PC；先用可控合成源验收。 | QEMU；依赖119a/122a |
| 14 | KL-132a 可屏蔽异步分派核心（gem5） | port KL-131a 到 gem5 interrupt carrier，用同一 masked→pending→unmask probe。 | gem5；依赖124a/131a |
| 15 | KL-133a cfx_timer（QEMU） | 按 KL-119a 冻结 profile 实现 counter0/ctrl/mask/pending/IRQ；验证 one-shot、ack、被屏蔽后 pending、解除后精确进入。 | QEMU；依赖131a |
| 16 | KL-134a cfx_timer（gem5） | port KL-133a，使用 gem5 event/interrupt 路径复现同一 guest oracle。 | gem5；依赖132a/133a |
| 17 | KL-135a timer 完整范围收口（QEMU，条件任务） | 若 KL-119a 未正式把 counters1-7、periodic/increment 延期，则补齐并验收；若正式延期，本任务改为记录 non-claim/roadmap 而不伪造全实现。 | QEMU；依赖119a/133a |
| 18 | KL-136a timer 完整范围收口（gem5，条件任务） | port KL-135a 的已承诺范围，或同步其正式 non-claim；不得把 counter0 one-shot 证据外推为完整 timer。 | gem5；依赖134a/135a |
| 19 | KL-137a 外部中断源（QEMU） | 若 KL-119a 冻结最小 UART0 协议，则实现 source→cause/pending→设备撤销/ack；否则只做明确命名的合成外部 IRQ probe，不声称 UART/PLIC。 | QEMU；依赖119a/131a |
| 20 | KL-138a 外部中断源（gem5） | port KL-137a 的同一已冻结 source 和 ack 语义。 | gem5；依赖132a/137a |
| 21 | KL-139a K1→K2 双后端集成探针 | 一个 bare-metal image 组合验证 MMU on、向量页常驻、normal/superpage、fault retry、TLB nested invalid、timer mask/pending、已冻结外部源及两级优先级；显式列出两端 pass/skip/fail/non-claim。 | QEMU+gem5 验收；依赖126/128/130/134/136/138 |

并行边界：KL-125a~130a 的 MMU 链与 KL-131a~138a 的异步链在共享
KL-119a/KL-122a/KL-124a 后可并行；KL-139a 是唯一汇合点。Linux 页表分配、
真实 page-fault policy、clocksource/clockevent 和 irqchip 接入属于 K2
oracle 全绿后的 kernel 任务，不应提前塞进上述 simulator 切片。
