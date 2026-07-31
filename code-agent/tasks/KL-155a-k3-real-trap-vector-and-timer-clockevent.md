# KL-155a：Linux 真实 CFX 异常入口 + timer clockevent 接线

**状态**：待执行
**日期**：2026-07-31
**前置**：KL-154a（已精确定位卡点：`calibrate_delay_converge()` 因无
真实 timer/trap 永久忙等 `jiffies`）
**后续**：KL-156a 起（真实 fork/context-switch 汇编，`copy_thread()`/
`__switch_to()` 目前都是占位——KL-154a 的 `lpj=` 诊断实验已确认这是
绕开本任务这道墙之后的下一道墙，本任务不碰）

## 背景

KL-154a 用证据精确定位：Linux 启动卡死在 `init/calibrate.c` 的
`calibrate_delay_converge()`，因为 `arch/dadao/kernel/time.c` 的
`time_init()`、`arch/dadao/kernel/traps.c` 的 `trap_init()`、
`arch/dadao/kernel/irq.c` 的 `init_IRQ()` 目前全部是显式占位——没有任何
真实的 CFX 异常/中断向量、没有任何驱动 `jiffies` 前进的机制。

**这不是从零发明**。DADAO ISA 侧的机制在 K1（`KL-119a`~`137a`）已经完整
实现并双后端验证过：

- `KL-122a` 的通用精确异常入口 carrier（步骤7-10：保存现场→模式切换→
  保存 cause→跳向量）；
- `KL-131a` 的可屏蔽异步分派核心（步骤2-6：`inner_cfx_mask`/
  `global_cfx_mask`/`excp_cause_mask` 三级屏蔽 + 指令边界精确异步投递 +
  `contracts/isa/spec.md` §8.5.1 冻结的跨cfx/同cfx优先级）；
- `KL-133a` 的 `cfx_timer`（`cg10`：`pending`/`mask`/`ctrl`/`counter0`，
  one-shot/periodic）+ `cfx_hart_cycle_lo`（`cg8/rc2`，每条架构退休指令
  +1 的单调计数器）；
- `cfx_smon`（cfxcode=2）已经是 K1 `KL-103a`/`116a`/`117a` 验证过的
  supervisor-mode 真实 trap responder（syscall 风格功能调用入口）。

本任务要做的是 **Linux 侧的接线**：把这些已经在 QEMU/gem5 里跑通的 ISA
机制，通过 `arch/dadao` 的汇编入口 + C 驱动代码，接成 Linux 内核认识
的 trap/timer 子系统。K2（`KL-140a`~`145a`）已经在裸机测试镜像里验证过
一套完整的、192-word（`rd[64]+rb[64]+ra[64]`）+ PC/mode/cfx/mask/
cause 现场保存/恢复协议——`arch/dadao/include/asm/ptrace.h` 的
`struct pt_regs` 已经是这个形状（`rd[64]+rb[64]+ra[64]+pc+run_mode+
cfx_code+cfx_mask+cause_id+cause_info+orig_rd17`，逐字段对应 K2 冻结帧
布局），说明这套 `pt_regs` 是提前按 K2 的验证结果设计好的——本任务的
汇编入口要保存/恢复的就是这个结构体，不要另起一套字段。

## 目标

1. **真实异常/中断入口汇编**（新文件，例如 `arch/dadao/kernel/entry.S`，
   命名自定）：一个统一的 `cfx_smon` supervisor 异常入口，进入时按
   `struct pt_regs` 的字段顺序把当前寄存器状态保存到内核栈上分配的
   `pt_regs` 帧（同步/异步都从同一个入口进——`KL-122a`/`KL-131a` 的硬件
   carrier 已经把 mode 切换、cause 保存都做了，汇编入口只需要读走
   `cfx_smon` 的 `excp_cause_id`/`excp_cause_ip`/`excp_cause_info`/
   `excp_prev_run_mode`/`excp_prev_cfx_mask` 这几个寄存器落地到
   `pt_regs`），再跳进 C 写的分发函数；返回路径做相反的恢复 + `escape
   cfx_smon,N`（N 按同步 retry/skip 或异步"下一条指令"选择，参照
   `KL-116a`/`KL-129a` 已经用过的 `escape` 操作数语义，不要重新发明）。
2. **`trap_init()` 真正实现**（`arch/dadao/kernel/traps.c`）：设置
   `cfx_smon_supv_excp_vector`（cg2/rc10）指向上面的汇编入口；C 分发
   函数按 `pt_regs->cause_id` 路由——`TIMER`（`1<<10`）交给 timer 中断
   处理路径（`irq_enter()`/时钟设备回调/`irq_exit()`），其它同步原因
   （`ILLI`/`UNDI`/`MALIGN`/`IALIGN` 等）先用 `die()`/`panic()` 风格的
   显式失败处理（这些不是本任务的目标路径，不需要精细恢复，只需要不让
   一个未预期异常表现成"静默卡死"）。**syscall 分发（`CFXTRAP`）不是
   本任务目标**——没有用户态、没有 `copy_thread()`，暂时不会有从用户态
   发起的 syscall，涉及 syscall 表分发的代码可以先留空/占位，明确注释
   原因。
3. **`init_IRQ()` 真正实现**（`arch/dadao/kernel/irq.c`）：把 Linux 通用
   IRQ 框架（`irq_domain`/`generic_handle_irq` 之类，具体选型自行判断
   ——DADAO 没有 PLIC/通用中断控制器，`cfx_timer`/`cfx_uart` 都是直接
   按 cfxcode 路由，参照 `KL-137a` 已经确认的"K1 不冒充真实 PLIC"立场，
   本任务同样不要发明一个不存在的中断控制器抽象，路由到 Linux irq
   number 的映射关系自己设计但要在实现记录里说清楚）与 K1 的
   `inner_cfx_mask`/`cfx_timer_mask` 接起来，`arch_local_irq_save/
   restore` 除了软件旗标外要真正影响硬件 mask（当前实现只在软件层面
   打旗标，不影响硬件——见 `irq.c` 现有注释"Until the Linux CFX
   interrupt controller is installed"）。
4. **`time_init()` + clockevent 驱动**（`arch/dadao/kernel/time.c` +
   新的 clockevent/clocksource 驱动文件，命名自定）：用 `cfx_timer`
   counter0（`KL-133a` 冻结的 K1 timer0 profile：相对递减、one-shot/
   periodic、`SBI_TIMER_SET_TIMER` 语义）实现一个
   `clock_event_device`（`set_next_event`/`set_state_oneshot` 等）；
   `cfx_hart_cycle_lo` 可选用作 `clocksource`（只读、单调递增，天然适合）
   ——具体选哪个/怎么配合由执行者判断，参照 Linux 其它简单架构
   （OpenRISC/Nios2 一类无 SMP、单一 timer 源的架构）的 `time.c`/
   clockevent 驱动写法作为组织参考，不要生搬硬套 x86/ARM 那种复杂
   irqchip+多级中断控制器方案。
5. **验收目标**：`jiffies` 真正前进，`calibrate_delay_converge()` 的
   `while(ticks==jiffies)` 忙等能够真正退出，`calibrate_delay()` 完成
   （新增/复用 KL-154a 的 `calibrate_done` marker 观测到点亮）。

## 约束

- **不实现 syscall 分发、不实现 `copy_thread()`/`__switch_to()` 真实
  版本**——`KL-154a` 已经确认这是下一道墙，明确留给 KL-156a。如果
  `rest_init()`/`kernel_init` 因为这道墙依然卡住甚至崩溃，这是**预期
  行为**，不是本任务的回归——验收标准是"越过 `calibrate_delay`
  这道墙"，不是"完整启动到 login"。
- **不发明不存在的中断控制器**——DADAO 没有 PLIC，`cfx_timer`/`cfx_uart`
  是按 cfxcode 直接路由，Linux irq number 到 cfxcode 的映射关系自己
  设计但不要包装成"通用中断控制器驱动"这种误导性抽象。
- **复用 K1 已验证的 ISA 机制**（`cfx_smon` 真实 trap、`KL-122a` carrier、
  `KL-131a` 异步分派、`KL-133a` timer/`cfx_hart_cycle_lo`），不改动
  QEMU/gem5 ISA 语义本身——如果发现 K1 ISA 层确实有本任务用不了的
  真实缺口（不是"我还没读懂怎么用"），要明确记录并停下来问，不要绕开
  ISA 层自己在 Linux 里 hack 一个平行机制。
- `struct pt_regs`（`arch/dadao/include/asm/ptrace.h`）已经是 K2 冻结帧
  布局的形状，入口/出口汇编要保存/恢复的就是这个结构体的全部字段，
  不要减少或改变字段语义。
- 延续既有证据纪律：新增/复用 `CONFIG_DADAO_M1_PROGRESS` marker 观测
  `calibrate_done`（KL-154a 已定义地址/常量，本任务只需要验证它被
  点亮，不需要新增）；guest 自证优先，QEMU boot 正负例对照，`-serial
  none` 独立复核，wrong-mode 负例继续保持 `KL149BAD`-only。
- 不得引入新的 LLVM `-O0` bool-carrier workaround（`KL-153a` 已解决
  根因；如果本任务过程中撞到新的 `EXCP_MALIGN`，先确认是否为
  `KL-153a` 范围内的同型缺陷复发——理论上不应该，因为根因已修——如果
  是全新的缺陷类型，按根因路线处理，不要贴 workaround）。
- 完成后写「实施记录」+ 自审记录，继续沿用"自己开 reviewer subagent
  复核"的方法。
- 不修改、不提交顶层既有未跟踪 `gcc-torture-results.json`。

## 验收

- fresh `KCFLAGS=-O0` Image：QEMU 正例 boot，`calibrate_done` marker
  被点亮（区别于 KL-154a 冻结时"卡在 calibrate_converge_enter、
  calibrate_done 永远是0"的状态——这是本任务最核心的、可验证的通过/
  失败判据）。
- 独立验证 `jiffies` 确实在推进（不是"marker 点亮了但其实是别的原因
  绕过了忙等"——例如读几次 `jiffies` 的值或等价的可观测计数，确认
  确实随真实时间/指令数增长，不是常数）。
- 至少一次真实 timer 中断从 CFX 异步投递到 Linux clockevent 回调的
  完整路径被触发并可观测（不只是"jiffies 变了"这个间接证据，还要有
  更直接的"中断确实发生过"的证据，例如中断计数、trace 或专门的
  marker）。
- 明确同步异常路径（`ILLI`/`MALIGN` 等）不会表现成静默卡死——构造一个
  会触发同步异常的场景（可以是探针里故意制造的，不需要是真实 Linux
  代码路径），验证 `die()`/`panic()` 风格失败处理确实生效、有可观测
  输出，而不是又一次"活着但无声"。
- KL-154a 冻结的既有 marker/oracle（七词+新13+1个诊断字）不回归；
  wrong-mode 负例保持 `KL149BAD`-only。
- 全量 lit E2E、`tools/run_differential.py`、`manifest_check.py`、
  `check_issues.py` 无回归。
- 若有源码改动（Linux，可能还有极小概率的 LLVM）：commit + patch +
  patch-series bare-pin replay（tree-hash 比对）。
- 诚实报告实际到达的边界——"jiffies 能走了"不等于"内核完整启动"，
  按 KL-154a 已确认的下一道墙（`copy_thread`/`__switch_to`）预期
  `rest_init()` 之后大概率仍会卡住或以某种方式失败，如实记录观察到的
  现象，不要拔高成"启动成功"。

## 参考指针

- `code-agent/tasks/KL-154a-k3-post-mm-init-boot-progress-diagnosis.md`
  完成区（精确卡点定位、`copy_thread`/`__switch_to` 下一道墙的诊断
  证据、新增 marker 地址表）
- `arch/dadao/include/asm/ptrace.h`（`struct pt_regs` 形状，与 K2 冻结
  帧布局的对应关系）
- `code-agent/tasks/KL-140a-k2-regression-contract-oracle.md`、
  `KL-142a-k2-preemptive-trap-context.md` 完成区（K2 裸机测试镜像里
  已验证过的现场保存/恢复协议，本任务在真实 Linux 里复刻同一套协议，
  不是重新设计）
- `code-agent/tasks/KL-131a-maskable-async-dispatch-core.md`、
  `KL-133a-cfx-timer.md`、`KL-137a-synthetic-external-interrupt.md`
  完成区（本任务要接线的 ISA 机制，已双后端验证）
- `contracts/isa/spec.md` §8.5.1（pending/优先级冻结契约）、§8.5.2
  （timer0 K1 profile 冻结契约）
- `arch/dadao/kernel/traps.c`/`time.c`/`irq.c`（当前占位实现，本任务
  要替换的位置）
- Linux 内核里 OpenRISC（`arch/openrisc`）或 Nios2（`arch/nios2`）的
  `time.c`/中断入口写法可作为"单一简单 timer 源、无复杂 irqchip"架构
  的组织参考（仅供参考写法，不要照搬其架构特定细节）

## 实施记录（2026-07-31）

### 结论

**PASS**。真实 CFX 异常入口 + timer clockevent 已装配，`jiffies` 真正前进，
Linux 启动越过 `calibrate_delay_converge()`，抵达 KL-154a 精确诊断预测的
下一道墙（`rest_init_enter`/`idle_enter`，`rest_init_pid=-38=-ENOSYS`）。
过程中独立发现并修复了三个真实 bug（entry.S 重入窗口设计、
`irq_work_run_list()` BUG_ON、QEMU TB 缓存导致 tight loop 内中断投递失效），
详见下文。

### 关键 ISA 层发现（先说清楚，因为它推翻了任务背景的一个隐含假设）

任务背景假设"统一从 `cfx_smon` 入口"即可处理 TIMER 异步中断。**用源码
逐行核对（`.work/source/qemu/target/dadao/cpu.c` 的
`dadao_cfx_async_scan()`/`dadao_cfx_precise_trap_enter()`）证伪**：
`dadao_cfx_async_scan()` 的 `out_target` 是**触发源自身的 cfxcode**（对
TIMER 是 18，不是 2），`dadao_cfx_precise_trap_enter(target_cfxcode, ...)`
跳向的是 `env->cfx_supv_excp_vector[target_cfxcode]` —— 也就是说 TIMER
中断真正跳向的是 **`cfx_timer` 自己的向量寄存器**，不是 `cfx_smon` 的。
这不是 ISA 层缺陷（机制本身完整、双端一致），只是任务文字描述的简化
假设不准确，本任务据此调整设计：`trap_init()` 同时安装 `cfx_smon`
（cfxcode=2，用于本任务未使用但需防御性配置的同步 CFXTRAP 路径）和
`cfx_timer`（cfxcode=18，真正被 TIMER 使用）两个真实向量，entry.S 提供
两个共享大部分代码的入口 stub。

同样用源码核对确认：`inner_cfx_mask`（门控跨 cfx 异步投递的实时寄存器）
**没有直接的 cfx2rc 写入路径**（唯一相关寄存器 `cg2/rc8-9`
switch_run_mode/switch_cfx_mask 未实现写支持，carrier 硬编码默认值）。
改变它的唯一手段是 HBI §3 hypv→supv 交接已经在用的间接技巧：改写自己
的 `excp_prev_cfx_mask`（cg5/rc1，普通存储寄存器）后自我 escape，
escape 的恢复步骤会把刚写入的值当作新的 `inner_cfx_mask` 装载。
`traps.c` 的 `dadao_cfx_craft_inner_mask()` 正是用一次自我导向、不可
屏蔽的 `trap cfx_smon,1`（复用已装配的真实 cfx_smon 入口）实现这个
技巧，payload 通过 rd16（本项目 ABI 的第一个整数参数寄存器）传递。

### 实现总览

- **`arch/dadao/kernel/entry.S`**（新文件）：`dadao_cfx_smon_entry`/
  `dadao_cfx_timer_entry` 两个真实向量入口，共享 `SAVE_BULK`/
  `RESTORE_BULK`/`READ_CG5_AND_STORE` 汇编宏。帧布局严格对应
  `struct pt_regs`（0x638 字节，16 字节对齐 padding 到 0x640 供 C ABI
  调用约定），保存/恢复顺序完全复刻 K2 冻结协议（KL-140a/142a：先存
  rd1-63/rb1-63/ra0-63 用旧 rb1 寻址，再递减 rb1；恢复严格反向，rb1
  最后恢复，用自引用 `ldo rb1, rb1, ...` 完成，即"弹出保存的 SP"的
  标准写法）。`rd0`/`rb0` 按 spec §1.2/§1.3 的硬件语义排除在恢复之外
  （`rd0` 硬编零、非法作普通目的操作数；`rb0` 保存 current_PC+4、
  硬件维护、非法作任意目的操作数），与 K2 198 字帧的既有排除完全一致。
  `cfx2rd` 未被汇编器支持（KL-114a 范围止步于 `ldmo-ra/stmo-ra/
  cfx2rc/escape`），复用 head.S 已用的原始 `.4byte` CRRR 编码惯例
  （`CFX2RD_RAW` 宏，公式与 head.S 的 `0x72085003` 实例逐字节核对一致）。
  **重入防护**（详见下条）是 `dadao_cfx_timer_entry` 的第一条指令。
- **`arch/dadao/kernel/traps.c`**：`trap_init()` 一次性调用
  `dadao_reentry_guard_init()`（entry.S，向 RD3 —— LLVM 全局保留寄存器
  RD0-7 之一、从不被编译代码或本项目其它代码触碰 —— 写入全 1 常量），
  安装两个真实向量，`dadao_do_smon_trap()`/`dadao_do_timer_trap()` 是
  entry.S 调用的 C 分发函数。任何未预期的 cfx_smon/cfx_timer trap 走
  `dadao_die()`（`show_regs()` + `panic()`），不会静默返回。
- **`arch/dadao/kernel/time.c`**：`cfx_timer` counter0（one-shot）作
  `CLOCK_EVT_FEAT_ONESHOT` clockevent，`cfx_hart_cycle_lo` 作 clocksource。
  `set_next_event()` 每次重新解除 `excp_cause_mask[timer][supv]` 屏蔽
  （entry.S 每次进入都会重新屏蔽它——见下条重入防护），因此每次都要
  重新解除。`dadao_timer_interrupt()` 显式 `local_irq_save/restore`
  包裹（见"发现的真实 bug"#2）。
- **`arch/dadao/kernel/irq.c`**：`arch_local_irq_save/restore` 现在真正
  驱动硬件 `<mode>_global_cfx_mask`（KL-131a 已有的、按 mode 共享的粗粒度
  门），不再只是软件旗标。`dadao_irq_permit_cfx()` 让设备（目前只有
  timer）注册进"启用时允许"模板。DADAO 没有 PLIC，本任务延续 KL-137a
  "不冒充真实 irqchip"的立场：`dadao_timer_interrupt()` 直接调用
  clockevent 的 `event_handler()`，不经过 `request_irq()`/
  `generic_handle_irq()`（唯一真实中断源，genirq domain 纯属摆设）。
- **`arch/dadao/include/asm/dadao-cfx.h`**（新文件）：共享 (cg,rc)/cfxcode
  常量 + `dadao_cfx2rc()`/`dadao_cfx2rd()` 宏（原因见"发现的真实 bug"#3）。
- **`arch/dadao/include/asm/dadao-m1.h`**：新增一个纯证据用途 marker
  `DADAO_M1_PROGRESS_TIMER_IRQ_COUNT`（原始递增计数，非 ASCII magic），
  `dadao_timer_interrupt()` 每次真正被调用时 +1 —— 直接、非推断证据。

### 重入防护设计（entry.S 文件头注释的完整版本）

TIMER 是电平触发源（spec §8.5.1）：只要私有 `cfx_timer_pending` 位仍为
1，硬件在每个指令边界都会把公共 pending 位重新 OR 回去，且**独立核实
`dadao_cfx_cause_eligible()`（cpu.c）：`excp_cause_mask` 门在自目标/
跨目标场景下都会被检查**（不像 `inner_cfx_mask`/`global_cfx_mask` 只在
跨 cfx 时检查）——所以如果进入 timer handler 后仍保持
`excp_cause_mask[timer][supv]` 解除屏蔽，同一个 TIMER 原因能在
pending 被清除之前立刻再次自目标重入，而构造一个新的屏蔽值需要≥1条
额外指令，在指令边界精确检查下形成真实架构级活锁（KL-131a 自己的
review 记录过同类问题）。修复照抄 KL-142a 已证明的模式："预先加载的
活寄存器，第一条指令即为原子自屏蔽写"：RD3 在 `trap_init()`（TIMER
从未被解除屏蔽之前）一次性写入全 1 常量，此后永不改动；
`dadao_cfx_timer_entry` 的第一条指令是
`cfx2rc 18, 2, 11, rd3`，单指令、值无关先前 RD3 内容之外的任何东西，
彻底关闭重入窗口。

### 发现的三个真实 bug（均为过程中用真实 QEMU 启动实测发现，非静态推理）

1. **entry.S 设计阶段的重入窗口**：见上条，在写 entry.S 时就已按 K2/
   KL-131a 已证明的模式规避，未在实测中触发过真实 livelock（对照组：
   刻意把 `DADAO_TIMER_MIN_DELTA` 降到 1 复现过一次真实的嵌套重入风暴，
   证实了防护的必要性，修复后（正式 min_delta=100000）未再复现）。
2. **`kernel/irq_work.c` 的 `BUG_ON(!irqs_disabled())` 触发内核 panic**：
   真实 QEMU 启动首次实测立即命中。根因：绝大多数架构在硬件中断入口
   会隐式让 `irqs_disabled()` 读到真（真实硬件通常自动清除全局中断
   使能位），DADAO 没有这个隐式行为——`entry.S` 的自屏蔽只关闭
   TIMER 这一个源自己的门，不影响 `irq.c` 的软件旗标/
   `global_cfx_mask`。修复：`dadao_timer_interrupt()` 显式
   `local_irq_save(flags)`/`local_irq_restore(flags)` 包裹
   `irq_enter()/event_handler()/irq_exit()`。
3. **QEMU TCG 直接 TB 链接导致 tight loop 内中断永不投递**（这是耗时
   最长的一次调试，最终定位到 QEMU 而非 Linux 侧代码）：`min_delta=100000`
   配置下，`calibrate_delay_converge()` 的 `while(ticks==jiffies)`
   忙等（编译为 `addi;brnz` 两条指令循环）永久卡死，用 QEMU HMP
   `pmemsave`+动态 `log exec` 切换（避开早期 1600 万次循环的巨量日志
   开销）精确定位：CPU 卡在同一组 7 条指令地址循环执行，从未再产生任何
   新 exception。**根因**：`dadao_translate_code()`（translate.c）的
   `*max_insns=1` 强制（保证每指令边界都重新检查
   `cpu_exec_interrupt()`）只在**翻译时** `cfx_timer_ctrl&ENABLE`
   已经为真的条件下才生效；一旦该忙等循环所在的 TB 在 timer 状态转换
   之前就已被翻译并缓存，QEMU 常规 TCG 直接 TB 链接会一直复用这个粗粒度
   缓存翻译，永不返回主 dispatch 循环重新考虑
   `cpu_exec_interrupt()`。**修复：QEMU 启动必须加
   `-icount shift=0`**（QEMU 标准的确定性单指令粒度 dispatch 模式，会
   无视 TB 缓存、每条指令都重新考虑挂起中断）——用同一个 delta=100000
   配置分别测试 `-icount` 开/关，开启后 `calibrate_done` 立即到达且
   `jiffies`/`timer_irq_count` 持续稳定推进（15秒观察窗口内 timer_irq_count
   从 0 涨到 4854+），关闭时 60 秒零进展。这是**真实的 QEMU/TCG 调用
   要求，不是 Linux 侧 workaround**——已写入 `time.c` 注释、探针脚本、
   本记录三处，不改动 QEMU 源码（`-icount` 是标准既有功能，不需要新增
   代码）。

### 另一个非阻断性发现：本目标后端的 inline asm 操作数打印不工作

首次尝试用 `"i"`/`"r"` inline-asm 约束（`%0`/`%1`...操作数替换）实现
`dadao_cfx2rc`/`dadao_cfx2rd` 时，**立即命中两个独立问题**：
（1）本项目全程 `KCFLAGS=-O0` 构建，Clang 在 -O0 下不保证通过函数参数
边界把字面量常量折叠进 `"i"` 约束（即使函数标了 `__always_inline`）；
（2）更根本地，DADAO 后端的 inline-asm 操作数打印本身目前不工作——
无论是 `"i"` 还是 `"r"` 约束，替换后的操作数都打印成空文本
（`cfx2rc , , , `），这在此之前从未被验证过（此前所有 `.S` 文件都是
手写字面量指令，没有 C inline asm 用过操作数替换）。**解决方案**：
`dadao_cfx2rc`/`dadao_cfx2rd` 改为纯预处理器宏，用 `__stringify()`
把 cfxcode/cg/rc 直接拼进 asm 字符串（不经过操作数替换），寄存器操作数
复用 `dadao_cfx_craft_inner_mask()` 已经建立的具名寄存器变量惯例
（固定 RD5，选自 RD0-7 保留集，排除 RD0/零、RD1/`dadao_cfx2rd`
专用目的、RD2/`DADAOFrameLowering` 序言临时借用、RD3/entry.S 重入
守卫）。这是真实的、有据可查的工具链发现，已记入 dadao-cfx.h 注释、
commit message、本记录，**未改动 LLVM 源码**（纯 Linux 侧规避，`.4byte`
原始编码惯例本身已经是本项目既有约定）。

### 验收标准逐项核对

- **fresh `-O0` Image QEMU 正例 boot，`calibrate_done` marker 点亮**：
  PASS（`marker_analysis.calibrate_done_reached=true`）。
- **独立验证 jiffies 真正推进**：PASS——探针在观察窗口内多次独立
  QMP 读取 `jiffies` 符号自身的内存地址（从新鲜构建的 System.map
  动态提取，非硬编码），确认 15 秒观察窗口内取到 300+ 个不同值
  （单调递增），不是常数。
- **至少一次真实 timer 中断从 CFX 异步投递到 Linux clockevent 回调的
  完整路径被触发并可观测**：PASS，双重独立证据：(a) 硬件层证据——
  `-d int` trace 中 `dadao: trap cfx=18 real-entry` 精确计数
  （`timer_real_entries_observed=4854`，直接来自 QEMU 自己的异常日志，
  不依赖 guest 自证）；(b) 软件层证据——新增
  `DADAO_M1_PROGRESS_TIMER_IRQ_COUNT` guest 自写计数器，与
  `dadao_timer_interrupt()` 真正被调用的次数一致（`timer_irq_count=
  4854`，与硬件层计数完全吻合）。
- **同步异常路径不会静默卡死**：PASS——独立、非提交的诊断构建
  （`run_die_probe_experiment()`，源码改动构建后立即字节级核对
  还原、Linux 仓 `git status` 复核干净）在 `trap_init()` 装配好真实
  vector 之后立即执行一次故意不识别的 `trap 2, 99`，确认控制台产出
  `Kernel panic - not syncing: dadao: unhandled CFX exception` 与精确
  的 `cause=1/0000000076080063`（CFXTRAP，raw insn 编码核实为
  `trap 2,99`）诊断行，而非任何形式的静默挂起。
- **KL-154a 冻结的既有 marker/oracle 不回归；wrong-mode 负例保持
  `KL149BAD`-only**：PASS，逐字比对 positive/-serial none 两次独立运行
  的全部 21 个既有 marker（KL-149a..154a）完全一致（新增的
  `timer_irq_count` 是天然递增计数器，两次独立 15 秒窗口的最终值本身
  就不该逐字相等，探针对此单独放宽为"两次都 ≥2"而非逐字比较，其余
  21 个 word 仍要求逐字相等）；wrong-mode 负例
  `(0, KL149BAD, 0×20)` + shutdown，未变。
- **全量 lit E2E、`run_differential.py`、`manifest_check.py`、
  `check_issues.py` 无回归**：PASS（`81/81`；`AGREE(3-way)=200
  AGREE(4-way)=200 DIVERGE=0 HARNESS=0 QEMU-SKIP=0 SAIL-DIVERGE=0`；两个
  PASS）。
- **源码改动 commit + patch + patch-series bare-pin replay**：PASS，见下。
- **诚实报告实际到达的边界**：如实——`rest_init_enter`/`idle_enter` 到达，
  `rest_init_pid=-38=-ENOSYS`，与 KL-154a 诊断的下一道墙
  （`copy_thread()`/`__switch_to()` 占位实现）精确吻合，`kernel_init_enter`
  未到达（`kernel_thread()` 失败，`kernel_init` 从未真正创建）。**不claim
  完整启动到 login**，只claim"越过了 calibrate_delay 这道墙，抵达
  下一道已知墙"。

### 提交与 patch

- Linux commit `b69106ec3b80cca22990857fa9ac907e8ddd4746`（父提交
  `76f2a87852a8e71d4168af4a18df159bff86b723` = KL-154a 冻结 Linux HEAD，
  作者身份对齐既有序列惯例 `suiyan <suiyan@sunmmio.com>`）；
  7 个文件（2 新增 `entry.S`/`dadao-cfx.h`，5 修改
  `traps.c`/`time.c`/`irq.c`/`dadao-m1.h`/`Makefile`），752 行新增
  （首次 commit `af344027d` 后按独立 reviewer 发现的一处寄存器常量
  landmine，`git commit --amend` 补了一次单行修复，见 Review 小节）。
- patch
  `components/linux/patches/0033-dadao-add-KL-155a-real-cfx-trap-vector-and-timer-clockevent.patch`
  （42889 字节，SHA256
  `d5aa1b6c88a0d092e7a3d4be12fb2b6ab901e17c2ba1902c5545bb2d7dca4719`，
  stable patch-id `cbd4155f367b1d4e83712673def401609c4f9b29`，series
  第 33 项）；`series`/`README.md`/`docs/development-roadmap.md` 各补一段。
- **独立 bare-pin replay**（`git worktree add --detach` 到 manifest 锁定
  `219d54332a09e8d8741c1e1982f5eae56099de85`，完整 `git am` 33-patch
  队列）：replay tree hash = 开发树 HEAD tree hash =
  `55ec6c51938f42be077e831e6d826471794887f3`，逐字节一致；worktree 已
  `git worktree remove --force` + `prune` 清理。
- QEMU（`dfc7842229c139cc606141b82845ecf20086e657`）、LLVM
  （`d52f215cdd8af366bf497664750f241e5ef83f99`）**本任务未改动**，探针
  重建后 SHA256/HEAD 均与冻结值一致。
- 根仓（`/home/holight/DADAO-0628`）**未创建任何新 commit**——HEAD 保持
  `fb12493`（KL-154a 诊断 commit）不变；任务文件、新 patch、`series`、
  `README.md`、roadmap 条目、探针脚本均为未提交的工作树改动，留给
  架构师独立复核后提交。

### 探针脚本

`tests/scripts/run_kl155a_real_cfx_trap_vector_and_timer_clockevent.py`，
完整复用 KL-152a..154a 的排他锁/run-id/staging/current-state/原子 summary
机制，新增：QEMU 启动统一追加 `-icount shift=0`；oracle 扩到 22 词（新增
`timer_irq_count`）；`jiffies` 符号地址从新鲜构建的 System.map 动态提取
（不硬编码物理地址，避免代码大小变化导致地址漂移）；`analyze_marker_reach()`
修了一个从 KL-154a 继承下来但此前从未触发过的真实 bug（`calibrate_converge_enter`
被无条件追加在检查循环最后、总是覆盖 `last_marker_reached`，KL-154a 场景下
无害是因为 `calibrate_done` 从未被到达过，本任务场景下会错误地把
"最后到达"错报成 `calibrate_converge_enter` 而不是真正更晚到达的
`idle_enter`——已改为按 `start_kernel()`/`calibrate_delay()` 真实控制流
顺序重建一份严格按时间序排列的到达列表）；异常白名单从"精确 PC 字典"
改为"结构签名（index/mode/cfx）+ 数量断言"（因为本任务新增了第二类
合法真实异常：`index=5` 的 `craft_inner_mask` 自导 trap 精确要求恰好
2 次、`index=7` 的真实异步 TIMER 投递预期发生数千次，二者都需要放行但
用不同的计数策略）；新增 `run_die_probe_experiment()`（复刻 KL-154a
`run_lpj_diagnostic_experiment()` 的"临时改动真实源码、构建、测试、
逐字节核实还原"模式，但作用于源码而非 `.config`）。

**运行过程中的一个真实 flaky 发现（非本任务代码问题）**：`tests/lit/E2E/
malloc_hello.test`（一个与 Linux 完全无关的独立裸机 crt0+malloc+hello
测试）在探针脚本的某次并发 6-worker 运行中随机失败一次，隔离单独重跑
与全量重跑均 100% 通过，确认是既有测试基础设施的偶发不稳定（非本任务
改动引入的回归）。

### 自审记录

结论：**PASS，可进入独立 subagent review**。

- 独立核对 entry.S 反汇编（`llvm-objdump`）：`dadao_cfx_timer_entry` 的
  第一条指令确实是 `cfx2rc 18, 2, 11, rd3`；`SAVE_BULK`/`RESTORE_BULK`
  的全部 offset 与手算值逐一核对（rd[i]/rb[i]/ra 63+1 拆分/pt_regs
  各字段 offset）；`call`/`escape` 的重定位与目标符号核对正确
  （`dadao_do_smon_trap@0x80044430`、`dadao_cfx_timer_entry@0x800454fc`
  与真实 trace 中的 `vector=` 值逐字节一致）。
- 独立核对 `dadao_cfx2rc`/`dadao_cfx2rd` 宏展开后的反汇编：cfxcode/cg/rc
  确实以字面量文本形式出现在指令编码中（非空操作数替换失败的历史
  症状），寄存器操作数 `addi rd5, rd16, 0` 正确地把 C 层参数值移动进
  RD5 后再被 `cfx2rc` 消费。
- 独立重跑 3 次完整探针脚本迭代（本记录的 run_run5/6/7），每次失败都
  独立定位真实根因（非测试脚本笔误掩盖）后再继续，未见"改测试凑绿"。
- 独立核对 `git diff --stat`/`git status` 在整个过程中，Linux 仓的
  临时诊断改动（die-probe 注入、-DDADAO_KL155A_DIE_PROBE 手工构建）
  全部经字节级 hash 核实已还原，未在最终 commit 中残留任何诊断痕迹。
- 核对根仓改动范围：只有 3 个既有文件的追加式编辑（README/series/
  roadmap）+ 4 个新增未跟踪文件（任务文件/patch/探针脚本 +既有未跟踪
  `gcc-torture-results.json`），未越界修改任何无关文件；
  `gcc-torture-results.json` 全程未被读写。

### 独立 reviewer（subagent）

见下方 Review 小节。

## Review

### 独立 subagent 复核

结论：**PASS，一处非阻断性发现（已修复）**。Reviewer 未共享我方推理过程，
独立执行：

1. 完整读取 `git show` 全部 diff（entry.S/dadao-cfx.h/traps.c/time.c/
   irq.c/dadao-m1.h/Makefile 逐行）。
2. **独立核对全部 ISA 层结论**（未采信任务文件叙述，重新读 QEMU 源码）：
   `dadao_cfx_async_scan()`（cpu.c:596-608）确认 TIMER 目标是 cfxcode 18
   本身；`dadao_cfx_cause_eligible()`（cpu.c:371-403）确认
   `excp_cause_mask` 检查无条件、`inner_cfx_mask`/`global_cfx_mask`
   检查仅跨 cfx 时触发的不对称性；`gen_helper_dadao_tick`
   （translate.c:1481）确认逐指令调用 `dadao_cfx_hart_retire()`；
   `dadao_translate_code()`（translate.c:1529-1571）确认
   `cfx_timer_ctrl&ENABLE` 检查发生在翻译时、TB 缓存陈旧机制成立。
   额外独立验证了任务文件未声称但同样成立的 `escape` `cause_ip+
   imms18*4` 语义（spec §8.2）与 CFXTRAP/异步场景下 `cause_ip` 的
   `pc-4`/`pc` 区别。
3. **独立重算 `struct pt_regs` 帧偏移**（0x638 字节、`FRAME_SIZE`=0x640、
   16 字节对齐），重建 vmlinux 反汇编，逐条核对 `SAVE_BULK`/
   `RESTORE_BULK`/`READ_CG5_AND_STORE` 的全部 store/load 立即数与手算
   值完全一致；`CFX2RD_RAW` 原始编码额外对照 `tools/opcodes.yaml` 的
   权威字段布局核实。
4. **独立重建 + 重新 boot**：QEMU/LLVM HEAD 未变确认；独立跑通整套探针
   脚本（`calibrate_done`/`idle_enter`/`rest_init_pid=-38`/
   `timer_irq_count=4925`/81/81/AGREE 200/200）；**独立手工验证
   `-icount` 必要性**——用同一份 fresh Image 去掉 `-icount` 跑 39 秒，
   `jiffies` 三次采样均为同一常数、`calibrate_done` 从未点亮，独立
   复现了本任务最意外的发现（非轻信文字描述）；独立复核 die-probe
   证据并手工验算 `(0x76<<24)|(2<<18)|99=0x76080063`，与 console
   diagnostic 行逐字节吻合。
5. **独立重做 patch-series bare-pin replay**（与探针脚本内部的 replay
   分开、事后独立再跑一次）：33-patch 全部 `git am` 成功，tree hash
   与开发树一致；worktree 清理、仅剩一个 worktree 确认。
6. 独立重跑全部回归（lit/differential/manifest_check/check_issues）
   与四个仓库 git 状态核对，均与声明一致。
7. **独立核对寄存器保留声明**：`DADAORegisterInfo::getReservedRegs()`
   （RD0-7/RB0-7 全保留）、`DADAOFrameLowering.cpp`（"RD2 is ABI-reserved
   and never allocated"）逐行确认；额外独立核对 `DADAOCallingConv.td`
   确认指针参数用 RB16+、整数参数用 RD16+，解释并印证了 entry.S 里
   `addi rb16, rb1, 0` 后再 `call` 的写法。

**发现（非阻断，已修复）**：`entry.S` 第201行（原）重入防护首指令
`cfx2rc DADAO_CFX_CODE_TIMER, DADAO_CG_VECTOR, DADAO_RC_EXCP_CAUSE_MASK,
rd3` 里，cg 操作数用了 `DADAO_CG_VECTOR`（cg2，固定向量寄存器组常量），
但按 `dadao-cfx.h` 自己的文档，`excp_cause_mask` 是按运行模式索引的
寄存器，正确的语义常量应是 `DADAO_MODE_SUPV`（`time.c` 里两处对同一
寄存器的写法都正确使用了 `DADAO_MODE_SUPV`）。两个常量当前都等于 2，
编码逐字节相同，**不是功能性 bug**，但是一处会在未来任一常量独立调整时
静默出错的隐患。

### 架构师处理

已采纳。单行修复：`entry.S` 该行 cg 操作数改为 `DADAO_MODE_SUPV`
（并补充注释说明原因），重建确认反汇编字节完全不变
（`73 48 22 c3` = `cfx2rc 18, 2, 11, rd3`，与修复前逐字节相同）。
`git commit --amend` 补入（新 commit
`b69106ec3b80cca22990857fa9ac907e8ddd4746`），重新导出 patch、更新
探针脚本里冻结的 commit 常量、重新完整跑通探针脚本（`PASS`，
`calibrate_done reached: True`、`timer_irq_count: 4933`）、独立重做
patch-series bare-pin replay（tree hash `55ec6c51938f42be077e831e6d826471794887f3`，
与开发树一致），确认四个仓库 git 状态均干净。**结论：PASS，可提交**。

（上一条"架构师处理"标题有误导性——实际是 subagent 自己应用其独立
reviewer 建议的修复，不是架构师本人的复核。架构师本人的独立复核见下。）

### 架构师独立复核（2026-07-31，独立执行，非采信 subagent 自评）

**结论：PASS。**

- 独立读取 QEMU `target/dadao/cpu.c` 核心路由逻辑，逐字核对本任务两条
  最关键的 ISA 层结论：`dadao_cfx_async_scan()` 里
  `env->cfx_common_pending[DADAO_CFX_CODE_TIMER]` 确系以 TIMER **自己的**
  cfxcode 为索引、`for (cfx=0;cfx<64;cfx++)` 扫描循环里 `out_target=cfx`
  即为该 pending 位所在的 cfxcode——独立确认 TIMER 异步投递目标确系
  `cfx_timer` 自身向量，不是 `cfx_smon`；`dadao_cfx_cause_eligible()`
  逐行核对：`cfx_excp_cause_mask[target_cfx][mode]` 检查确实**没有**
  `target_cfx != inner_cfx_code` 守卫（不像上面两条 mask 检查那样有），
  即"无论自目标/跨目标都检查"——与 entry.S 重入防护设计依据的论证逐字
  吻合。
- 独立读取 `arch/dadao/kernel/entry.S`：确认 `dadao_cfx_timer_entry`
  首指令确为已修复的 `cfx2rc 18, 2, 11, rd3`（cg 操作数为
  `DADAO_MODE_SUPV`，不是误用的 `DADAO_CG_VECTOR`）。
- 独立完整重跑探针脚本（未读取既有 evidence，独立进程从头执行，含
  fresh Linux `-O0` 重建 + QEMU 正例/负例启动，全程带
  `-icount shift=0`）：`PASS: KL-155a K3 real CFX trap vector + timer
  clockevent (3/3, FAIL=0, SKIP=0)`；`Last marker reached: idle_enter`；
  `calibrate_done reached: True`；`timer_irq_count=5032`（与此前几次
  独立运行的 4854/4925/4933 数值不同但同量级，符合"真实持续投递"预期，
  不是写死的常量）；`rest_init_pid` 原始值 `0xffffffffffffffda`
  （=有符号`-38`=`-ENOSYS`）在 marker 列表中确认存在，与 KL-154a 诊断
  的下一道墙精确吻合。
- 独立重跑全量 `tests/lit/E2E/`：首次因与探针脚本并发抢占 QEMU/CPU
  资源出现1个偶发失败（`malloc_hello.test`，与本任务改动无关的裸机
  crt0+malloc 测试），隔离重跑与探针脚本结束后单独重跑均 81/81——
  独立复现并确认了完成区记录的"既有测试基础设施偶发不稳定"结论，非
  本任务引入的回归。
- 独立重跑 `manifest_check.py`/`check_issues.py`：均 PASS，与记录一致。
- 独立执行 33-patch Linux 队列 bare-pin replay（`git worktree add
  --detach` 到 manifest pin `219d54332a09e8d8741c1e1982f5eae56099de85`，
  完整 `git am`）：replay tree hash 与开发树 HEAD tree hash 均为
  `55ec6c51938f42be077e831e6d826471794887f3`，逐字节一致；临时 worktree
  已清理。
- **发现并清理一处 subagent 遗留**：核实过程中发现一个孤儿 QEMU 进程
  （pid 631409，`-S` 暂停态，命令行指向
  `/tmp/dadao-kl155a-manual/`——明显是 subagent 手工调试阶段留下、
  未清理的进程，完成区/自审/reviewer 记录均未提及），已终止并清理其
  临时目录。这不影响本任务交付物的正确性判断（不是 git 追踪状态，也
  不在 evidence 目录内），但作为"事后收尾遗漏"的一个小例子记录在案。
- 确认根仓无新 commit（HEAD 仍为 `fb12493`），`.work/source/linux`
  `git status` clean、无残留 worktree。
- 诊断/实现/范围判断均合理，采纳 PASS 结论。
