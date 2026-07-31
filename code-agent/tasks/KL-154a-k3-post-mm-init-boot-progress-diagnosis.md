# KL-154a：K3 `mm_init` 之后启动阻塞点精确诊断

**状态**：待执行
**日期**：2026-07-31
**前置**：KL-153a（LLVM `-O0` bool/i1 根因已修复并撤除全部 workaround）
**后续**：待本任务诊断结果确定（可能是 KL-155a 真正装配 CFX trap vector +
timer clockevent，也可能是别的更简单的阻塞——不预设）

## 背景

KL-153a 完成后，同一份七词 oracle 通过、guest 在扩展观察窗口（8秒、手工
15秒复测）内持续 `running`，不再有新的 `EXCP_MALIGN`。控制台最后一行停在
`NR_IRQS: 64`（`init_IRQ()` 附近），此后再无新 console 输出或 QEMU
异常，但也没有 shutdown——guest 处于"活着但不再产出可观测进展"的状态。
KL-153a 明确把"精确定位卡在哪个函数/PC"列为未完成事项，交给本任务，
不允许凭 8/15 秒窗口内的现象猜测性冒认"首个真实阻塞"。

**当前 `arch/dadao` 现状**（已核对源码，非猜测）：

- `arch/dadao/kernel/traps.c` 的 `trap_init()` 是显式空函数，注释写明
  "CFX exception vectors are installed by the later Linux trap task"——
  也就是说 Linux 启动路径里**目前没有安装任何真实的 CFX 异常/中断向量**。
- `arch/dadao/kernel/time.c` 的 `time_init()` 同样是显式空函数，注释写明
  "The CFX timer clocksource/clockevent is introduced after the linked
  image gate"——**没有工作中的 clocksource/clockevent**，`jiffies` 没有
  任何驱动它前进的机制。
- `arch/dadao/kernel/irq.c` 的 `init_IRQ()` 只是把一个软件旗标清零，不
  涉及任何硬件中断控制器。
- `arch/dadao/kernel/head.S` 里唯一出现的 `trap`/`escape` 只是 KL-149a
  自证 supervisor mode 交接用的一次性技巧，随后立即执行
  `call start_kernel`，**不是常驻异常入口**。

据此，**一个值得优先验证、但不能预设为定论的假设**：Linux 标准启动路径
在 `calibrate_delay()`（多数架构由 `start_kernel()`→箭头附近的
early_boot code 调用，用于校准 `loops_per_jiffy`）一类"忙等 `jiffies`
发生变化"的代码上可能会永久自旋——因为没有任何东西会让 `jiffies`
前进。这只是一个需要证据支持的猜测，不是本任务的既定结论；也可能是别的
更早或更晚的阻塞点。**本任务的核心交付是拿到证据，不是验证这个猜测。**

## 目标

1. **不猜测、用证据定位**：复用 `arch/dadao/include/asm/dadao-m1.h` 已有
   的 `dadao_m1_progress_write()` 机制（同一套 `CONFIG_DADAO_M1_PROGRESS`
   guest 自写 QMP 证据字的约定，只读地址在 `0x87fd00xx` scratch window
   顺序分配，值取 8 字节 ASCII magic），在 `NR_IRQS: 64` 之后、
   `start_kernel()` 剩余路径的若干关键里程碑插入新的 progress marker
   （候选点：`calibrate_delay()` 进入/完成、`rest_init()` 进入、
   `sched_init()` 进入/完成、`kernel_init` 内核线程真正开始执行、
   `cpu_startup_entry`/idle 循环进入——实际选哪些点、插几个，由执行者
   根据 `start_kernel()` 源码的真实控制流决定，不要照抄这个候选列表当
   成必须全部命中的清单）。
2. 用带上全部新 marker 的 fresh `-O0` Image 重跑同一个 QEMU 启动流程，
   通过 QMP 精确读出**最后一个被写入的 marker**，从而把"卡在哪个函数
   之前"精确到具体 C 源码位置，而不是"某个 8/15 秒窗口内没有更多输出"
   这种模糊描述。
3. 基于精确定位到的位置，诊断根因：是"忙等一个永远不会发生的事件"
   （比如上面提到的 `jiffies`/`calibrate_delay` 假设，如果证据指向这里）、
   还是其它原因（某处代码访问了未初始化的架构状态、某个尚未实现的
   arch hook 被调用触发了未处理的异常且没有 trap vector 去承接、或
   其它）。诊断要给出可验证的证据（反汇编/寄存器状态/源码路径），
   不能只给"很可能是……"的叙述。
4. **范围边界（重要）**：如果诊断结果确认是"需要真正安装 CFX 异常/中断
   向量 + 接通 timer clockevent 才能继续前进"这类大工程，本任务**只需要
   精确冻结这个诊断结论**（具体卡在哪、为什么、需要哪些子系统才能解锁），
   不需要在本任务内就把 trap vector 安装 + timer clockevent 驱动全部
   实现——那是下一个里程碑（很可能是 KL-155a）的范围，参照
   `KL-146a` 定的 K3 阶段划分"3. precise trap/syscall, timer/irq and
   scheduler integration"本身就是独立一大步，不要在诊断任务里顺手把
   整个阶段做完导致范围失控、难以验证。如果诊断过程中发现真正的阻塞
   出乎意料地简单（例如只是一行遗漏的初始化、不需要装配trap vector
   就能绕过），当然可以直接修掉并往前推进，按实际情况判断，不要为了
   "保持任务小"而放着唾手可得的修复不做。

## 约束

- 延续 KL-146a~153a 的证据纪律：guest 自证优先于日志断言、正负例对照、
  `-serial none` 独立复核 console 是次要观察通道、wrong-mode 负例继续
  保持 `KL149BAD`-only。
- 新增 marker 使用 `CONFIG_DADAO_M1_PROGRESS` 同一个 Kconfig 开关下的
  机制，不要新建一套平行的进展观测手段。
- 不得在诊断阶段就动 QEMU/gem5 ISA 语义（K1 的 cfx_timer/cfx_hart_cycle_lo/
  异步分派机制已经在模拟器侧完整实现——`KL-131a`/`133a`/`137a`——如果
  最终需要真正的 timer clockevent，那是 Linux 侧接线的问题，不是模拟器
  缺失功能）。
- 不得引入新的 LLVM `-O0` bool-carrier workaround（`KL-153a` 已把根因
  修好，若诊断中再撞到同类 `EXCP_MALIGN`，先确认是否为
  `KL-153a` 修复范围外的新 pattern，若是真的新缺陷，参照 `KL-153a` 的
  方法论走根因路线，不要重新引入 Linux 侧 typedef workaround）。
- 完成后写「实施记录」+ 自审记录，继续沿用"自己开 reviewer subagent
  复核"的方法。
- 不修改、不提交顶层既有未跟踪 `gcc-torture-results.json`。

## 验收

- 新增/扩展的探针脚本（可以是 `tests/scripts/run_kl153a_llvm_o0_bool_stack_fix.py`
  的后续版本或独立新文件，命名自定）必须：
  1. 验证 KL-153a 冻结的根提交/patch queue/QEMU 身份不变（复用既有验证
     函数，不重新发明）；
  2. 精确报告新增每一个 progress marker 的 (地址, 值, 触发的源码位置)；
  3. 报告本次启动**实际到达的最后一个 marker**，以及之后经过的确定性
     观察窗口内是否还有更多 marker/console 输出/新异常/shutdown；
  4. 若诊断出具体阻塞原因，给出可复核证据（反汇编片段、调用路径、
     或对应的 Linux 源码位置引用）；
  5. 全量 lit E2E、`tools/run_differential.py`、`manifest_check.py`、
     `check_issues.py` 无回归；
  6. 若有源码改动（LLVM 和/或 Linux）：commit + patch + patch-series
     bare-pin replay（tree-hash 比对），沿用既定方法。
- 明确、诚实地报告本任务实际做到了哪一步——精确定位不等于完全解决，
  按实际结果如实分类："定位到了、也顺手修掉了" vs "定位到了、修复是
  下一个里程碑的范围，本任务只冻结诊断结论"。

## 参考指针

- `code-agent/tasks/KL-153a-llvm-o0-bool-stack-slot-root-fix.md` 完成区
  "QEMU 验证"小节（本任务要突破的现状：8/15秒窗口 running 但无新输出，
  最后 console 行 `NR_IRQS: 64`）
- `arch/dadao/kernel/traps.c`/`time.c`/`irq.c`（当前均为显式占位/no-op，
  非本任务要填的坑，只是诊断时需要知道的现状）
- `arch/dadao/include/asm/dadao-m1.h`（`dadao_m1_progress_write()` 机制、
  已用的 marker 地址表，本任务新 marker 从下一个未用地址继续分配）
- `arch/dadao/kernel/setup.c`/`mm/init.c`（既有 marker 插入方式的代码
  范例）
- `tests/scripts/run_kl152a_mm_init_completion_probes.py`、
  `run_kl153a_llvm_o0_bool_stack_fix.py`（既有 QEMU QMP 读取/oracle
  比对/evidence 落盘方法，直接复用）
- `docs/development-roadmap.md` "K3 started" (KL-146a) 条目列出的六阶段
  K3/K4 链条，本任务处于第2阶段收尾/第3阶段（"precise trap/syscall,
  timer/irq and scheduler integration"）开端的诊断步骤

## 实施记录

### 结论（先说结果）

**精确定位到了，且是任务背景里提出的假设——用证据确认，不是采信假设。** 卡点是
`init/calibrate.c` 的 `calibrate_delay_converge()` 函数入口后第一条语句：

```c
ticks = jiffies;
while (ticks == jiffies)
    ; /* nothing */
```

一个等待 `jiffies` 发生变化的忙等循环。由于 `arch/dadao` 目前没有任何工作中的
timer clockevent（`time_init()` 显式空函数）也没有真实的 CFX 异常/中断向量
（`trap_init()`/`init_IRQ()` 均为占位），`jiffies` 永远不会被
`do_timer()`/tick 路径推进，这个循环因此永久自旋——与观测到的"活着、无新
`EXCP_MALIGN`、无新 console 输出、不 shutdown"现象完全吻合。

**本任务只冻结这个诊断，没有实现修复**（按任务范围边界：真正解除需要装配
CFX 异常向量 + 真实 timer clockevent，属于 K3 阶段 3，留给下一个任务
——很可能是 KL-155a）。诊断过程中额外发现并**用一次性、未提交的诊断实验**确认
了绕过这一层之后的下一个真实阻塞点（见下），同样不在本任务修复范围内。

### 证据 1：新增 14 个 progress marker，精确定位卡点

复用 `arch/dadao/include/asm/dadao-m1.h` 的 `dadao_m1_progress_write()` 机制，
在 `0x87fd0038`–`0x87fd00a0`（紧接 KL-150a~152a 已用到 `0x87fd0030` 的下一个
未用偏移）新增 14 个字：13 个按 `start_kernel()`/`rest_init()`/`kernel_init()`
真实控制流顺序插入的里程碑（读 `init/main.c` 源码后决定，不是照抄任务文件
候选列表），外加 1 个插在**通用**文件 `init/calibrate.c` 的
`calibrate_delay_converge()` 函数体最开头（沿用 `init/main.c` 里
`mm_init()`/`MM_INIT_DONE` 已有的"在通用文件里加 `#ifdef
CONFIG_DADAO_M1_PROGRESS` guard"先例，非 arch-only 特判）：

| marker | 地址 | 值(ASCII) | 触发位置 |
|---|---|---|---|
| `sched_init_done` | `0x87fd0038` | `KL154SCD` | `init/main.c`：`sched_init()` 之后 |
| `early_irq_init_done` | `0x87fd0040` | `KL154IRQ` | `init/main.c`：`init_IRQ()` 之后 |
| `tick_init_done` | `0x87fd0048` | `KL154TCK` | `init/main.c`：`tick_init()` 之后 |
| `timekeeping_init_done` | `0x87fd0050` | `KL154TKI` | `init/main.c`：`timekeeping_init()` 之后 |
| `time_init_done` | `0x87fd0058` | `KL154TMI` | `init/main.c`：`time_init()` 之后 |
| `console_init_done` | `0x87fd0060` | `KL154CON` | `init/main.c`：`console_init()` 之后 |
| `locking_selftest_done` | `0x87fd0068` | `KL154LKT` | `init/main.c`：`locking_selftest()` 之后 |
| `calibrate_enter` | `0x87fd0070` | `KL154CAE` | `init/main.c`：调用 `calibrate_delay()` 之前 |
| `calibrate_done` | `0x87fd0078` | `KL154CAD` | `init/main.c`：调用 `calibrate_delay()` 之后 |
| `rest_init_enter` | `0x87fd0080` | `KL154RIE` | `init/main.c`：`rest_init()` 入口 |
| `rest_init_pid` | `0x87fd0088` | (原始值,非magic) | `init/main.c`：`rest_init()` 内 `kernel_thread(kernel_init,...)` 返回值，符号扩展后原样写入 |
| `kernel_init_enter` | `0x87fd0090` | `KL154KIE` | `init/main.c`：`kernel_init()` 入口（fork 出的线程体） |
| `idle_enter` | `0x87fd0098` | `KL154IDL` | `init/main.c`：`rest_init()` 内 `cpu_startup_entry()` 之前 |
| `calibrate_converge_enter` | `0x87fd00a0` | `KL154JFL` | `init/calibrate.c`：`calibrate_delay_converge()` 入口，`while(ticks==jiffies)` 之前 |

`rest_init_pid` 特意不是 ASCII magic，而是 `kernel_thread()` 返回值本身
（符号扩展写入），这样负 errno 能直接从 oracle 里读出来，不需要另外推断。

**实测（`tests/scripts/run_kl154a_post_mm_init_boot_progress_diagnosis.py` 正例
QEMU 运行，fresh `KCFLAGS=-O0` Image，`-serial file:` 与 `-serial none` 两次独立
运行结果逐字节一致）**：markers 依序点亮到 `calibrate_converge_enter` 为止
（`sched_init_done → early_irq_init_done → tick_init_done →
timekeeping_init_done → time_init_done → console_init_done →
locking_selftest_done → calibrate_enter → calibrate_converge_enter`，共 9
个），`calibrate_done` 及其后的 `rest_init_enter`/`rest_init_pid`/
`kernel_init_enter`/`idle_enter` 全部保持 `0`（未到达）。10 秒扩展观察窗口内
`query-status` 全程 `running=true`，QEMU trace 全程只有 1 条异常
（`index=5 pc=0x0000000080000014 mode=2 cfx=63`，KL-149a hypv→supv mode
handoff 既有机制，非新异常），无 shutdown。既有 KL-149a~152a 七词 oracle
（`KL149AHE, 0, KL150SAE, KL150SAD, KL150MIN, KL151MID, KL152MMD`）与
console 五锚点顺序全部不回归。wrong-mode 负例保持
`(0, KL149BAD, 0×19)` 并 shutdown。

### 证据 2：为何不是"print 被吞了所以看起来卡在更早的地方"

`calibrate_delay()` 在进入 `calibrate_delay_converge()` 之前会先
`pr_info("Calibrating delay loop... ")`（`init/calibrate.c`
`calibrate_delay()` 里 `else` 分支），但该行文本**没有出现在 console
捕获里**——一度怀疑是卡在了这行 print 之前的某处，而非 converge 循环本身。
用新增的 `calibrate_converge_enter` marker（插在 `calibrate_delay_converge()`
函数体第一行，即该 `pr_info` **之后**才可能执行到的位置）直接证伪了这个
担忧：marker 确实点亮，证明执行流程已经越过那行 `pr_info` 调用、真正进入了
`calibrate_delay_converge()`。console 里看不到那行文本的合理解释是 Linux
printk 的 continuation 缓冲机制（该 `pr_info` 不带尾随换行，等待后续
`pr_cont()` 补上 BogoMIPS 数值才会作为完整行落盘/刷新到 console driver）——
由于执行永远到不了那个后续 `pr_cont()` 调用，这段不完整的行永远留在
continuation 缓冲区里未被刷新，这本身是佐证而非矛盾。

### 证据 3（诊断实验，未提交）：绕开这一层之后的下一道真实阻塞

用一次性、**未提交**的诊断构建（单独输出目录
`.work/build/linux-kl154a-lpj-diagnostic`，跑完后探针脚本自动
`rm -rf` 清理，不留痕迹；只在该构建的 `.config` 里手工把
`CONFIG_CMDLINE` 追加 `lpj=1000000`——`lpj=` 是 Linux 标准的、专为"启动早期
没有工作定时器"场景设计的机制，本身不需要真实校准）验证：一旦绕开
`calibrate_delay_converge()` 的忙等（`preset_lpj` 分支跳过 converge 循环），
markers 继续前进到 `rest_init_enter`、`rest_init_pid`（原始值
`0xffffffffffffffda` = **有符号 `-38` = `-ENOSYS`**）、`idle_enter`，随后
在 10 秒观察窗口内保持不变、无新异常。

这precisely 印证了任务背景之外、本任务在读源码时发现的第二个既有事实：
`arch/dadao/kernel/process.c` 的 `copy_thread()`（第 31 行起）无条件
`return -ENOSYS;`，注释原文写明"Context creation is intentionally
fail-closed until the assembly ret_from_fork path exists"；同文件
`__switch_to()`（第 41 行起）里 `BUG_ON(prev != next);`（第 44 行）意味着
即使 fork 成功也无法真正切换到不同任务。`rest_init()` 里
`kernel_thread(kernel_init, NULL, CLONE_FS)` 因此返回 `-ENOSYS`，
`find_task_by_pid_ns(-38, ...)` 找不到对应 pid 返回 `NULL`，`rest_init()`
后续对 `NULL` task_struct 的使用（`set_cpus_allowed_ptr`）在这台裸机上没有
观测到任何新异常——大概率是因为此时内核还在物理直接映射、地址 0 附近未必
真正"不可访问"，所以 NULL 解引用没有触发可观测的 fault，执行"悄无声息"地
一路走到 `cpu_startup_entry()` 的 idle 循环，而 `kernel_init`/`kthreadd`
从未真正被创建过。

这是一堵**更深、且明显更大**的墙（真实 fork/context-switch 汇编），同样落在
K3 阶段 3（"precise trap/syscall, timer/irq and scheduler integration"）范围
内，不在本任务修复范围——本任务只把它作为"验证了任务范围边界判断正确"的
补充证据记录，`lpj=` 预设本身不采纳进已提交的配置（避免制造"内核现在能跑得
更远"的假象：那条路径最终仍然是一个从未被正确处理的 NULL 解引用，而非真正
可用的下一步）。

### 源码改动与 patch

`init/main.c`（13 个新 marker 调用点）+ `init/calibrate.c`（1 个新 marker
调用点，`calibrate_delay_converge()` 入口）+
`arch/dadao/include/asm/dadao-m1.h`（14 个新地址/值常量），单个普通 commit：

- Linux commit `76f2a87852a8e71d4168af4a18df159bff86b723`（父提交
  `83992fe62ac26252622ca888421602abafe20b44` = KL-153a 冻结 Linux HEAD）
- patch `components/linux/patches/0032-dadao-add-KL-154a-post-mm_init-boot-progress-markers.patch`
  （11472 bytes，SHA256
  `fefff84f088a158044edf1925a3ddf5502a5b4a2dc8f8afcecdbae63fa9eea7a`，
  stable patch-id `5eaabd8959a16a10447ec72d6d1f093c98577987`，series 第 32 项）
- `components/linux/patches/series` 追加第 32 行；`components/linux/README.md`
  与 `docs/development-roadmap.md` 各补一段短摘要指向本任务
- 32-patch 完整队列在独立临时 worktree（`manifests/components.lock.toml`
  锁定的 linux pin `219d54332a09e8d8741c1e1982f5eae56099de85`）里
  `git am` 完整重放，`git rev-parse HEAD^{tree}` = 开发树 HEAD 的
  tree hash（均为 `6f6719c632f73375846c818485a013609c6eea1d`），逐字节一致；
  worktree 已 `git worktree remove --force` + `prune` 清理
- QEMU（`dfc7842229c139cc606141b82845ecf20086e657`）、LLVM
  （`d52f215cdd8af366bf497664750f241e5ef83f99`）本任务未改动，探针脚本
  重建后 SHA256/HEAD 均与 KL-153a 冻结值一致
- 根仓（`/home/holight/DADAO-0628`）未创建任何新 commit——HEAD 保持
  `5b18b53a89e38bc809e7d0ff41a99669d82f7fef`（KL-153a fix commit）不变；
  任务文件、新 patch、`series`、`README.md`、roadmap 条目、探针脚本均为
  未提交的工作树改动，留给架构师独立复核后提交

### 回归验证

`python3 tests/scripts/run_kl154a_post_mm_init_boot_progress_diagnosis.py`：

```
PASS: KL-154a K3 post-mm_init boot progress diagnosis (3/3, FAIL=0, SKIP=0)
Last marker reached: calibrate_converge_enter
```

- `tests/lit/E2E/`：81/81，无 Failed/Unsupported
- `tools/run_differential.py`：`AGREE(3-way)=200 gem5-SKIP=2 DIVERGE=0
  HARNESS=0 QEMU-SKIP=0`，`AGREE(4-way)=200 SAIL-SKIP=2 SAIL-DIVERGE=0`
  ——与 KL-153a 冻结时一致，无回归（[[feedback_differential_harness_stale_for_new_k1_work]]
  适用：这套 200/200 只验证基础 ISA 没被误伤，对 K3 boot-progress 这类新机制
  零信息量，不作为本任务诊断正确性的证据，只作为回归门槛）
- `scripts/manifest_check.py`：`manifest validation: PASS`
- `scripts/check_issues.py`：`ISSUE REGISTRY: PASS`
- KL-153a 冻结证据（144-item manifest、summary SHA256
  `f45f9c675a7998389cb4a33a518d450dae229f94cd7b54fa0b6bd2656a700edd`）逐字节
  核对未变
- evidence 目录 `.work/evidence/kl154a-post-mm-init-boot-progress-diagnosis/`，
  63-item artifact manifest，外部排他锁/run-id/staging/current-state/原子
  summary 均沿用 KL-152a/153a 约定
- 三个 source 仓库（linux/qemu/llvm）跑完后 `git status` 均 clean，
  `.work/source/linux` 无残留 worktree

### 执行过程中的一次事故（已恢复，记录在案）

探针脚本第一次编写时有一处真实 bug：`KNOWN_HANDOFF_EXCEPTION` 字典缺少
`pc` 字段，导致与 `scan_trace_exceptions()` 产出的字典（含 `pc`）永远不相等，
使已知的、无害的 KL-149a handoff 异常被误判为"意外新异常"而 FAIL。此外，
本次执行中有两次后台进程管理失误（用 shell 级 `nohup ... &` 而非工具自带的
`run_in_background`，导致一次误判进程已死、一次探针脚本仍在合法运行时被
误当作卡死），过程中一度产生了一个陈旧的 lock/current-state 文件，已确认
清理干净、未影响最终探针以独立进程重新跑出的绿色结果。修复
`KNOWN_HANDOFF_EXCEPTION` 后重新完整跑通探针，上述"回归验证"一节的结果
即为修复后的最终、单次、干净运行的结果。

## Review

### 自审

- 重新核对 `init/main.c`/`init/calibrate.c` 里全部 14 处新增
  `dadao_m1_progress_write()` 调用点的行号与 `dadao-m1.h` 里对应地址/值
  常量一一对应，无手误。
- 核对 `analyze_marker_reach()` 的校验逻辑：对 5 个既有 KL-150~152a
  字要求全部达到（否则 FAIL），对新 13+1 个字允许"到某个前缀停止"，且
  显式拒绝任何"跳跃"（某字为非 0/非期望值）或"不该到的地方到了"
  （`calibrate_done` 被点亮时显式 FAIL，防止未来 diagnosis 被无声回归掩盖）。
- `-serial file:` 与 `-serial none` 两次独立运行的 marker 序列做了逐字比对
  （`positive_words == serial_none_words`），确认 marker 观测与 serial 后端
  无关，不是 console 缓冲的副作用。
- lpj 诊断实验专门检查了重建后的 `vmlinux` 里 `strings` 确实包含
  `lpj=1000000`，避免"以为改了但没生效"的假阳性；用完 `finally` 块
  `rm -rf` 临时构建目录，探针跑完后未在 `.work/build/` 下留下该目录。
- 确认了根仓 `git status` 只有预期的 7 类改动（README/series/roadmap 三个
  `M`，任务文件/patch/探针脚本/既有未跟踪的 `gcc-torture-results.json`
  四个 `??`），未新增或遗漏任何文件；`gcc-torture-results.json` 全程未被
  读写。

### 独立 reviewer（subagent）

按流程要求，实现完成后先自审（见上），再派独立只读 subagent 复核（未共享
我方推理过程，独立读代码/独立跑实验）。该 reviewer 实际执行了：

- 独立读取 `init/main.c`/`init/calibrate.c` 当前完整源码（非 diff hunk），
  逐一核对全部 14 处新增 `dadao_m1_progress_write()` 调用点确实落在声称的
  控制流位置，包括 `calibrate_converge_enter` 确实在 `calibrate_delay()`
  的 `pr_info("Calibrating delay loop... ")` 调用之后才可能执行到；
- 独立核对 14 个新地址（`0x87fd0038`–`0x87fd00a0`）与既有
  KL-149a~152a 地址（`0x10`–`0x30`）无冲突、互不相同；
- 独立读取 `arch/dadao/kernel/time.c`/`traps.c`/`irq.c` 确认根因链条
  （无 timer/无 trap vector → jiffies 不会前进）逐字与源码相符；
- 独立读取 `arch/dadao/kernel/process.c`，确认 `copy_thread()`
  第 31 行返回 `-ENOSYS`、`__switch_to()` 第 44 行 `BUG_ON(prev != next)`，
  行号与本记录所述一致；
- 独立解析 `summary.json`：确认 `marker_analysis.last_marker_reached ==
  "calibrate_converge_enter"`、9 个新 marker 到达、`calibrate_done`
  及之后保持 0；`positive_runtime.exceptions_observed` 只含唯一已知的
  KL-149a handoff 异常；`lpj_diagnostic_experiment.marker_analysis.
  rest_init_pid_signed == -38`；抽查引用的原始 artifact 文件存在且与
  summary 描述一致；
- **独立重做 patch-series 重放**（未采信记录的结论）：在独立临时
  worktree 里以 `manifests/components.lock.toml` 锁定的 linux pin 为基线，
  完整 `git am` 32-patch 队列，确认 `HEAD^{tree}` 与开发树
  `76f2a87852a8e71d4168af4a18df159bff86b723^{tree}` 逐字节一致
  （均为 `6f6719c632f73375846c818485a013609c6eea1d`），跑完后
  `git worktree remove --force` + `prune` 清理干净；
- 独立核对根仓 `git status`：HEAD 未变（`5b18b53a...`），只有预期的
  3 个 `M` + 4 个 `??`（含未被触碰的既有 `gcc-torture-results.json`）；
  `.work/source/{linux,qemu,llvm}` 均 clean，`linux` 只有一个 worktree；
- **独立完整重跑一遍探针脚本**（非采信日志），复现
  `PASS (3/3, FAIL=0, SKIP=0)` 与 `Last marker reached:
  calibrate_converge_enter`，以及 `manifest_check.py`/`check_issues.py`
  两个 PASS；
- 对"范围边界"判断给出独立评估：任务文件自身第 4 条明确允许"若确认需要
  大工程则只冻结诊断"，本任务的处理与此一致；确认 `lpj=` 诊断实验产出的
  `lpj=1000000` 字符串**不存在于** patch 0032 的 diff 里（即未被采纳进
  已提交改动），判断该实验"越界但合理、且未污染交付物"成立。

**结论：PASS**。唯一指出的一点是"Review 小节此前只有占位句、缺少实际
subagent 复核记录内容"这一**文档性**缺口（非正确性缺陷），已在本节补齐。

### 架构师二次复核（2026-07-31，独立执行，非采信 subagent 自评）

**结论：PASS。**

- 独立读取 `arch/dadao/kernel/process.c` 全文：确认 `copy_thread()`
  确系第31行起、第38行 `return -ENOSYS;`；`__switch_to()` 确系第41行起、
  第44行 `BUG_ON(prev != next);`——与记录逐字节一致。
- 独立读取 `init/calibrate.c` 第190-207行：确认新增的
  `dadao_m1_progress_write(DADAO_M1_PROGRESS_CALIBRATE_CONVERGE_ENTER,...)`
  调用确实位于 `calibrate_delay_converge()` 函数体最开头、`ticks = jiffies;
  while (ticks == jiffies);` 忙等循环之前——与"marker 点亮即证明已越过
  该函数入口的 pr_info、真正进入 converge 忙等"这一论证逐字吻合。
- 独立完整重跑探针脚本（非读取既有 evidence，独立进程从头执行，含重新
  跑一遍 fresh `-O0` Linux 构建 + QEMU 正例/`-serial none`/wrong-mode 三次
  启动）：结果为
  `PASS: KL-154a K3 post-mm_init boot progress diagnosis (3/3, FAIL=0,
  SKIP=0)` / `Last marker reached: calibrate_converge_enter`，与记录完全
  一致。
- 独立重跑全量 `tests/lit/E2E/`（81/81）、`manifest_check.py`、
  `check_issues.py`，均 PASS，与记录一致。
- 独立执行 32-patch Linux 队列 bare-pin replay（`git worktree add
  --detach` 到 manifest pin `219d54332a09e8d8741c1e1982f5eae56099de85`，
  完整 `git am`）：replay tree hash 与开发树 HEAD tree hash 均为
  `6f6719c632f73375846c818485a013609c6eea1d`，逐字节一致；临时 worktree
  已清理。
- 确认根仓无新 commit（HEAD 仍为 `5b18b53`），`.work/source/linux`
  `git status` clean、无残留 worktree。
- 诊断与范围判断（冻结诊断、不在本任务内实现 trap vector/timer
  clockevent/context-switch）合理，留给下一个里程碑（K3 阶段3，很可能
  `KL-155a`）。
