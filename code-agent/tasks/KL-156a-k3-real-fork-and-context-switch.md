# KL-156a：真实 fork/context-switch（`copy_thread()`/`__switch_to()`/`ret_from_fork`）

**状态**：待执行
**日期**：2026-07-31
**前置**：KL-155a（真实 CFX 异常入口 + timer clockevent，`jiffies` 已能
前进，启动抵达 `rest_init_enter`/`idle_enter`，`rest_init_pid=-38`）
**后续**：待本任务结果确定（`kernel_init` 真正跑起来之后，Linux 会继续
往前走到哪一步、下一道墙是什么，本任务之后才能知道，不预设）

## 背景

KL-154a 精确诊断、KL-155a 独立复核确认：`rest_init()` 里
`kernel_thread(kernel_init, NULL, CLONE_FS)` 返回 `-38`（`-ENOSYS`），
因为 `arch/dadao/kernel/process.c` 的 `copy_thread()` 无条件
`return -ENOSYS;`，`__switch_to()` 里 `BUG_ON(prev != next);`——也就是说
**真实的 fork/上下文切换汇编目前完全不存在**，`kernel_init`（进而
`do_basic_setup()`、驱动初始化、`/init` 加载尝试）从未真正被创建/执行过。

**这不是从零发明**——K2（`KL-140a`~`145a`）已经在裸机测试镜像里、双后端
（QEMU+gem5）验证过一套完整的协作式任务切换协议：

- `KL-140a` 冻结的 1080-byte 协作帧（`rb1-rb4`/`rd32-rd63`/`rb32-rb63`
  + 完整 `ra0-ra63` 经 `ldmo-ra`/`stmo-ra` 整bank 访问）；
- `KL-141a` 用两个独立栈的任务在 25 次真实交替切换里验证了这套帧
  save/restore 协议，包括 RegRAS refcount-2 递归槽；
- K2 的这套协议是**手写的裸机 oracle，不是 Linux `__switch_to`**（`KL-141a`
  自己完成区原文如此声明）——本任务是把同一套已验证的 save/restore
  逻辑，第一次真正接到 Linux 的 `switch_to()`/`copy_thread()` 调用
  约定上。

`arch/dadao/include/asm/Kbuild` 里 `switch_to.h` 走的是
`generic-y`（`include/asm-generic/switch_to.h`）：

```c
#define switch_to(prev, next, last) \
    do { (last) = __switch_to((prev), (next)); } while (0)
```

——也就是说**全部真正的寄存器切换工作都必须在 `__switch_to()` 内部完成**
（没有额外的汇编宏层可以分担），且因为要切换的是"当前正在执行的 C
函数所在的那个栈"，纯 C 代码不可能安全做到"切到另一个线程的栈之后再从
这个 C 函数里 return"——`__switch_to()` 的真实实现必然需要手写汇编
（可以是 `__switch_to()` 本身用内联汇编，也可以是一个 C 包装函数调用
一个独立的 `.S` 汇编函数，具体组织形式自行判断）。

## 目标

1. **`__switch_to()` 真实实现**（`arch/dadao/kernel/process.c` + 新增
   汇编，文件组织自定）：把当前线程需要跨切换保留的状态（照抄 K2
   `KL-140a`/`141a` 已冻结的协作帧字段集合——`rb1`/内核栈指针、
   `rb2-rb4`、`rd32-rd63`、`rb32-rb63`、完整 `ra0-ra63`）保存到
   `prev`（`struct task_struct`）的内核栈上（`thread_struct.kernel_sp`
   指向的位置），切到 `next->thread.kernel_sp`，从那里恢复同一组
   字段，更新 `dadao_current`（`WRITE_ONCE`，现有代码已经这么做），
   返回 `prev`（generic `switch_to()` 宏要求的语义）。
2. **`copy_thread()` 真实实现**（同文件）：**只需要覆盖内核线程这一种
   情形**（`kernel_thread(fn, arg, flags)` 风格，`rest_init()` 已经在用
   这条路径；`copy_thread` 签名是 `(clone_flags, usp, arg, task_struct*)`，
   `arch/dadao` 目前**没有**选 `HAVE_COPY_THREAD_TLS`，签名不需要改）。
   在新任务的内核栈上构造一个"假的 `__switch_to()` 保存帧"，使得当
   `__switch_to()` 第一次把这个新任务当 `next` 切换过去、按目标1 的
   恢复路径把它的（伪造的）保存状态恢复出来后，会"返回"进一个新的
   汇编入口 `ret_from_fork`（不是 `copy_thread()` 自己的调用点——这是
   `copy_thread()`/`__switch_to()` 配合完成"一个从未真正跑过的新线程
   如何拿到第一次被调度的机会"这个标准 Linux 内核移植手法，可以参照
   `arch/openrisc`/`arch/nios2`/`arch/riscv` 等架构的 `copy_thread`+
   `ret_from_fork` 组织方式，但不要照搬其架构特定寄存器约定）。`fn`/
   `arg`（内核线程要执行的函数指针和参数）需要通过伪造帧里的某个/某几个
   保留字段传给 `ret_from_fork`，具体传递机制自定但要在实现记录里讲清楚。
   **用户态 fork（`usp`/`CLONE_VM` 之外的普通进程复制路径、`pt_regs`
   拷贝）不是本任务目标**——K3 现在没有用户态、没有 syscall 分发
   （`KL-155a` 已经明确 CFXTRAP 分发是 KL-156a+ 范围），本任务只覆盖
   `kernel_thread()` 这一条路径，用户态 fork 留给更后面的任务，需要在
   实现里明确注释这个范围边界（例如：非内核线程路径可以先
   `return -ENOSYS`或等价的显式占位，不要悄悄放行一个没验证过的路径）。
3. **`ret_from_fork`**（新汇编，可以放进 `entry.S` 或新文件）：内核线程
   场景下，从目标2 传来的 `fn`/`arg` 出发，调用 `fn(arg)`；若 `fn`
   返回（内核线程正常结束的情形），调用 `do_exit()`（或该版本 Linux
   等价的收尾路径，自行核对 5.4 期望的确切调用）。用户态路径（进
   `ret_from_syscall`/恢复 `pt_regs`）不在本任务范围，可以留一个明确
   注释的占位/`BUG()`，不需要实现。
4. **验收目标**：`kernel_thread(kernel_init, NULL, CLONE_FS)` 真正返回
   一个有效 pid（不是 `-38`），`kernel_init` 函数体真正开始执行（用
   `CONFIG_DADAO_M1_PROGRESS` 新增一个 marker 观测——例如
   `kernel_init` 函数体第一行——比"pid 不是负数"更直接的证据）。

## 约束

- **不实现用户态 fork/exec、不实现 syscall 分发、不实现信号处理**——
  这些都需要真实用户态 `pt_regs` 往返，K3 目前完全没有用户态（`KL-155a`
  已经把 CFXTRAP 分发排除在外），本任务同样不碰。
- **复用 K2 已验证的帧字段集合**（`KL-140a` 冻结的 1080-byte 协作帧
  字段清单），不要发明一套新的"需要保留哪些寄存器"的判断——除非发现
  K2 的协作帧本身遗漏了某个 Linux `__switch_to()` 场景下才会暴露的
  真实必要字段，那种情况下要明确记录原因，不能默默改。
- **不改动 QEMU/gem5 ISA 语义**——`ldmo-ra`/`stmo-ra` 整 bank RA 访问、
  RegRAS 机制在 K1/K2 已经双后端验证过，本任务只是复用。
- 延续 KL-149a~155a 的证据纪律：`CONFIG_DADAO_M1_PROGRESS` marker、
  guest 自证优先、正负例对照、`-serial none` 独立复核、wrong-mode 负例
  `KL149BAD`-only。QEMU 启动继续按 `KL-155a` 确认的要求带
  `-icount shift=0`（否则 timer 可能静默不投递，会污染本任务的观测）。
- 不得引入新的 LLVM `-O0` bool-carrier workaround；如果撞到 inline asm
  操作数替换打印空文本这个已知缺口（`docs/issues.yaml` 的
  `dadao-inline-asm-operand-printer-empty-substitution`），继续沿用
  `KL-155a` 已经建立的 `__stringify()` 宏 + 具名寄存器变量惯例，不要
  重新踩一遍同一个坑。
- 完成后写「实施记录」+ 自审记录，继续沿用"自己开 reviewer subagent
  复核"的方法。
- 不修改、不提交顶层既有未跟踪 `gcc-torture-results.json`。

## 验收

- fresh `KCFLAGS=-O0` Image：QEMU 正例 boot，新增 marker 证明
  `kernel_init` 函数体真正被执行到（不是"pid 看起来有效"这种间接
  推断）。
- `kernel_thread()` 返回值本身也要被观测到（读回真实 pid，非负数），
  与"kernel_init 真正执行"两条证据互相印证，不能只有一条。
- 至少验证一次完整的"从 boot/idle 上下文切换到 kernel_init"往返没有
  破坏原 boot 上下文该保留的状态——可以参照 K2 `KL-141a` 的验证思路
  （切换前后关键寄存器值的可复核比对），具体怎么在真实 Linux 里做这个
  观测由执行者设计。
- 明确报告本任务实际走到哪一步——`kernel_init` 真正跑起来之后大概率
  会撞上更多新墙（`do_basic_setup()`/驱动初始化/找不到 `/init` 之类），
  如实记录观察到的下一个阻塞现象，不要拔高成"启动成功"。
- KL-149a~155a 冻结的既有 marker/oracle 不回归；wrong-mode 负例保持
  `KL149BAD`-only。
- 全量 lit E2E、`tools/run_differential.py`、`manifest_check.py`、
  `check_issues.py` 无回归。
- 若有源码改动（Linux，可能还有极小概率的 LLVM）：commit + patch +
  patch-series bare-pin replay（tree-hash 比对）。

## 参考指针

- `code-agent/tasks/KL-154a-k3-post-mm-init-boot-progress-diagnosis.md`
  完成区（`copy_thread`/`__switch_to` 墙的原始诊断证据，`rest_init_pid=
  -38` 的来源）
- `code-agent/tasks/KL-155a-k3-real-trap-vector-and-timer-clockevent.md`
  完成区（`-icount shift=0` 要求、inline asm 操作数打印缺口的 workaround
  惯例、entry.S 的组织方式可作为本任务新汇编的写法参考）
- `code-agent/tasks/KL-140a-k2-regression-contract-oracle.md`、
  `KL-141a-k2-cooperative-context-switch.md` 完成区（1080-byte 协作帧
  字段清单、25 次真实交替切换的验证方法，本任务在真实 Linux 里复用
  同一套字段集合）
- `arch/dadao/include/asm/processor.h`（`struct thread_struct`，目前只有
  `kernel_sp`/`user_sp` 两个字段——可能需要扩展来存"伪造保存帧"用到的
  额外状态，自行判断是否够用）
- `arch/dadao/include/asm/thread_info.h`（`struct thread_info`、
  `THREAD_SIZE`）
- `arch/dadao/include/asm/current.h`（`dadao_current`，`setup.c:23`
  静态初始化为 `&init_task`，即 boot/idle 上下文的"第一个 prev"）
- `arch/dadao/kernel/process.c`（`copy_thread()`/`__switch_to()` 现有
  占位，本任务要替换的位置；`start_thread()`已有实现，供参考"pt_regs
  怎么摆放"但不是本任务直接要用的路径）
- `include/asm-generic/switch_to.h`（`switch_to()` 宏的确切契约，
  `arch/dadao` 通过 `Kbuild` 的 `generic-y` 选用）
- `include/linux/sched/task.h`（`copy_thread()` 精确签名；`arch/dadao`
  未选 `HAVE_COPY_THREAD_TLS`）
- Linux 内核里 OpenRISC（`arch/openrisc`）、Nios2（`arch/nios2`）或
  RISC-V（`arch/riscv`）的 `copy_thread`/`__switch_to`/`ret_from_fork`
  写法可作为"简单架构如何组织这三者配合"的参考，不要照搬架构特定寄存器
  约定

## 实施记录（2026-07-31）

### 结论

**PASS。** `kernel_thread(kernel_init, NULL, CLONE_FS)` 现在返回真实 pid（1，
不再是 -38），`kernel_init` 函数体真实执行，真实调度器运行了 1100+ 次上下文
切换（kthreadd、workqueue worker 全链路），idle→kernel_init→idle 完整往返
被 marker 观测到，boot 诚实推进到下一道墙（VFS 根挂载 panic，本机无
rootfs）。过程中发现并修复了一个**真实的栈重叠 bug**（切换帧与 trap 帧在栈上
重叠，见下）。

### 设计总览（帧布局与三件套配合）

- **复用 K2 KL-140a/141a 冻结的协作帧**：字节级对齐 K2 §2.1 的 135-word/
  1080-byte 帧（0x000 w0/w1/w2 为 padding，w0/w1 在伪造帧里兼任 fn/arg
  载体；0x018 rb1 / 0x020 rb2 / 0x028 rb3 / 0x030 rb4；0x038 rd32-63；
  0x138 rb32-63；0x238 ra0-63）。帧常量共享在新增的
  `arch/dadao/include/asm/dadao-switch.h`（switch.S 与 process.c 共用，
  杜绝两处漂移）。
- **`dadao_switch_to_asm(prev,next)`**（新 `switch.S`，prev→rb16、
  next→rb17，ABI §2.1 指针走 RB 组）：在当前栈顶下保存 K2 帧
  （`addi rb1,rb1,-0x438` 后 `kernel_sp` 指向帧基），把 prev 帧基写入
  `prev->thread.kernel_sp`（偏移来自 `asm-offsets.c` 新增的
  `THREAD_KERNEL_SP_OFFSET`，setzw/orw 拆 16 位半构建），读
  `next->thread.kernel_sp` 切栈，按 K2 顺序恢复（ra→rd32-63→rb32-63→
  rb4/3/2→rb1 最后，自引用 `ldo rb1,rb1,0x18`），最后 `ret rd0,0`——
  **弹的是 next 的 RegRAS**，即"返回到 next 被挂起的位置"。入口先把
  `prev` 抄进 rb31（rb31 不在帧内、是唯一跨切换存活的载体），供
  `ret_from_fork` 取 `schedule_tail(prev)`。
- **`dadao_ret_from_fork`**（`switch.S`）：`rb31`→`rb16` 调
  `schedule_tail`，从伪造帧 w0/w1（`rb1-0x438+0x000/0x008`）取 fn/arg，
  `call rb8, rd0, 0` 调 `fn(arg)`（call-rrii 间接调用，LLVM `CALL_RRII`），
  fn 返回则 `do_exit(0)`；用户态路径不在范围（copy_thread 非 kthread
  分支显式 `return -ENOSYS` fail-closed，带注释）。
- **`__switch_to`**（process.c，C 包装）：`WRITE_ONCE(dadao_current,next)` →
  marker 写入 → `local_irq_save` → `dadao_switch_to_asm` →
  `local_irq_restore` → `return prev`。`prev`/`next`/`flags` 全部由 -O0
  编译器 spill 到本函数栈帧（已用实际反汇编逐条验证：
  `addi rb1,rb1,-120`、`prev`@[rb1+88]、`next`@[rb1+80]、
  `flags`@[rb1+72]，`return prev` 从栈重载再 `ret`），跨切换存活。
- **`copy_thread`**：仅 kthread（`task->flags & PF_KTHREAD`，dup_task_struct
  从 init_task 继承，已验证）。`sp = task_stack_page+THREAD_SIZE`，伪造帧在
  `[sp-0x438, sp)`，`memset` 清零，w0=fn、w1=arg、0x18=sp（恢复后的
  SP）、0x430=(1ULL<<48)|dadao_ret_from_fork（ra63 refcount=1，
  spec §5.6：ret 要求顶槽 refcount≥1，QEMU `helper_ras_pop` 逐行核对）。

### 发现的真实 bug：切换帧与 trap 帧在栈上重叠（必须修的根因）

任务第一版实现（无 IRQ 屏蔽）在加入 round-trip 观测后**确定性崩溃**：
`dadao: exception index=1 pc=0x0`（ILLI 在地址 0），紧跟 finish_task_switch
内的 timer escape 之后，异常签名 index=5 恰 2 次、index=7 千余次、index=1
恰好 0→5 次，三跑全复现。用 `-d in_asm,int` 指令级 trace 定位到崩溃发生在
切换后恢复任务的 `finish_task_switch` 里。**根因**：K2 切换帧
`[SP-0x438, SP)` 与 entry.S 真实 trap 帧 `[SP-0x640, SP)` 在栈上**重叠**——
`dadao_switch_to_asm` 的 SAVE 执行期间（`addi rb1,rb1,-0x438` 之前）若
TIMER 异步投递，entry.S SAVE_BULK 会把 trap 帧盖在 `[SP-0x640, SP)` 上，
**覆盖已写入的 K2 帧低段**（rd32-63/rb32-63/ra 槽），被切换任务的保存上下文
被静默损坏，恢复后崩溃。K2 裸机探针从没触发过是因为 KL-141a 是纯协作切换、
无异步中断参与（preemptive trap 上下文是 KL-142a 分开测的，两者从不在同一次
切换中叠加）。

**修复**：`__switch_to` 用 `local_irq_save`/`local_irq_restore` 把切换做成
掩码临界区（全局 CFX mask 门控跨 cfx 异步投递，KL-131a 机制；切换期间到期
的 TIMER 保持挂起，解除后下一指令边界立即投递，不丢 tick）。修复后 index=1
归零、三跑稳定、SWITCH_TO_IDLE/SWITCH_FROM_IDLE 都点亮。这是 Linux 侧纪律，
不改 ISA。已在 process.c 注释里完整记录论证链。

### 验收逐项核对（探针 `tests/scripts/run_kl156a_k3_real_fork_and_context_switch.py`）

- **`kernel_thread()` 返回值被直接观测**：`rest_init_pid = 1`（raw
  `0x1`，不是 -38）。✓
- **`kernel_init` 函数体真实执行**：`kernel_init_enter`（KL154KIE，函数体
  第一行，KL-154a 已预埋）点亮。✓
- **idle→kernel_init 完整往返**：`SWITCH_FROM_IDLE`（KL156SFI，切换离开
  init_task）+ `SWITCH_TO_IDLE`（KL156STI，调度器切回 init_task）+
  `IDLE_ENTER`（KL154IDL，idle 恢复执行 rest_init 余下代码）三者全亮。✓
- **真实切换量**：`SWITCH_COUNT=1124`，且 boot 全程 kthreadd/workqueue
  机制真实运行（console 出现 devtmpfs、io schedulers 等 initcall 输出）。
  ✓
- **往返未破坏 boot/idle 上下文**：K2 风格回读——从 guest 内存读
  `init_task.thread.kernel_sp`（=0x87fef8c0，位于 boot 栈区 0x87ff0000
  下方），逐字段核验保存帧：`saved_rb1=0x87fefcf8` 在 boot 栈区、8 对齐；
  `saved_ra63=0x0001000080043984`（refcount=1 + 地址落在 kernel text）。
  加上 1123 次真实切换零 ILLI 崩溃，往返保真。✓
- **下一道墙诚实报告**：`ROOT_MOUNT_ATTEMPT`（KL156RMA）点亮 + console
  出现 `Kernel panic - not syncing: VFS: Unable to mount root fs`——kernel_init
  跑完 `kernel_init_freeable`（含 do_basic_setup 全驱动初始化）后，在
  `prepare_namespace` 根挂载失败处 panic（本机无 rootfs、无用户态）。
  `EXEC_INIT_ATTEMPT` 未点亮（正确：根挂载墙在 exec 之前）。**不 claim
  启动到 login。** ✓
- **负例**：`-serial none` 与 positive 的写一次 marker 逐字一致（仅两个
  天然递增计数器 timer_irq_count/switch_count 按量级比较）；wrong-mode
  负例保持 `KL149BAD`-only。✓
- **异常签名**：index=5 恰 2 次（KL-149a handoff 探针 + craft_inner_mask）、
  index=7 千余次（真实 TIMER 异步）、index=1 为 0。✓
- **全量回归**：lit E2E 81/81；`run_differential.py`
  AGREE(3-way)=200 / AGREE(4-way)=200 / DIVERGE=0 / HARNESS=0 /
  QEMU-SKIP=0 / SAIL-DIVERGE=0；`manifest_check.py` PASS；`check_issues.py`
  PASS（Open=25 Closed=43 Total=68，+1 是 d92a5e6 已登记的 inline-asm
  操作数打印缺口，非本任务引入）。✓
- **commit + patch + bare-pin replay**：Linux commit `78601a1d2`
  （父 `b69106ec3`=KL-155a HEAD，作者对齐 suiyan@sunmmio.com），7 文件
  +2 新增。patch `0034-...patch`（SHA256
  `d4685ca6715097c1e74e9399f4c6dee429c6a2abafde82679f9ecf353e37dec4`，
  stable patch-id `e830a81b89da7b63ede0ac02e3552b1a86563279`，与 commit
  一致）。独立 bare-pin replay（manifest 锁定
  `219d54332a09e8d8741c1e1982f5eae56099de85`，完整 34-patch `git am`）：
  replay tree hash = 开发树 tree hash（与开发树逐字节一致，探针 summary
  内记录完整 hash），worktree 已清理。✓
- **探针脚本**：完整复用 KL-152a..155a 的排他锁/run-id/staging/current-state/
  原子 summary 机制；oracle 扩到 27 词（KL-156a 新增
  ROOT_MOUNT_ATTEMPT/EXEC_INIT_ATTEMPT/SWITCH_FROM_IDLE/SWITCH_TO_IDLE/
  SWITCH_COUNT）；新增 idle 保存帧回读验证；异常签名检查 index=1 必须为 0
  （正是本任务发现的崩溃的负向断言）。✓

### 提交与 patch

- Linux commit `78601a1d2`（detached HEAD，延续 KL-155a 惯例），7 个文件
  （2 新增 `dadao-switch.h`/`switch.S`，5 修改 `dadao-m1.h`/`Makefile`/
  `asm-offsets.c`/`process.c`/`init/main.c`），308 行新增。首版
  `71436ccc9` 后按自审发现的一处 `ret_from_fork` 脆弱性（fn/arg 在
  `schedule_tail()` 之后才读帧、可能被其调用链覆盖），`git commit --amend`
  改为先读入 callee-saved 寄存器 rb32/rb33（ABI 保证跨 schedule_tail 存活），
  见自审记录。
- patch `0034-dadao-add-KL-156a-real-fork-and-context-switch.patch`，series
  第 34 项；`components/linux/README.md`/`docs/development-roadmap.md` 各补
  一段。
- **独立 bare-pin replay**（临时 worktree 完整 `git am` 34-patch）：tree hash
  与开发树逐字节一致，已清理。
- QEMU/LLVM 本任务未改动（探针重建后 SHA256/HEAD 均与冻结值一致）。
- 根仓未创建新 commit——HEAD 保持 `d92a5e6`（KL-155a inline-asm 发现，
  架构师已提交）；任务文件、新 patch、series、README、roadmap、探针脚本
  均为未提交工作树改动，留给架构师独立复核后提交。

### 遗留/诚实边界

- 用户态 fork/exec、syscall 分发、信号处理不在本任务范围（copy_thread 非
  kthread 路径显式 `-ENOSYS`）。
- `EXEC_INIT_ATTEMPT` 标记已埋好但当前根挂载墙下不会点亮，等跨过 VFS 墙后
  成为下一个观测点。
- idle 保存帧回读只核验结构不变量（rb1 在 boot 栈区、ra63 refcount=1+text
  地址），不逐字比对全部 135 word（K2 KL-141a 能逐字比对是因为裸机探针有
  预置表；真实 Linux 的寄存器初值不可预测，结构不变量 + 1123 次零 ILLI
  切换已足够证明保存/恢复正确）。
- round-trip 观测用的 `schedule_timeout_uninterruptible(10)` 是
  CONFIG_DADAO_M1_PROGRESS 门控的诊断 yield（让调度器在 kernel_init 主动
  让出后真实切回 idle），非真实 boot 路径行为。

### 自审记录

结论：**PASS，可进入独立 subagent review**。

- 独立核对 switch.S 反汇编：保存/恢复的全部 store/load 立即数与 K2 §2.1
  偏移逐槽核对（rd32@-0x400、rb32@-0x300、ra0@-0x200、ra63@-0x8、
  rb1@-0x420 等）；`ret` 前 rb1 最后恢复；重定位（`call schedule_tail`/
  `call do_exit`/`call rb8,rd0,0`）链接后目标符号逐字节核对。
- 独立核对 `__switch_to` -O0 编译产物：prev/next/flags 均 spill 到本函数
  栈帧（[rb1+88]/[rb1+80]/[rb1+72]），`return prev` 从栈重载后 `ret`；
  `local_irq_save` 展开为 `arch_local_irq_save()`（capture+disable，调用
  链 `call arch_local_save_flags`+`call arch_local_irq_restore(0)` 逐符号
  核对），`local_irq_restore` 在 next 上下文用 next 自己的 flags 恢复。
- 独立核对伪造帧：copy_thread 里 frame[0x430/8]=(1<<48)|ret_from_fork、
  frame[0x18/8]=sp、w0/w1=fn/arg，与 switch.S 恢复路径的 ldmo/ldo 槽位
  一一对应。
- **自审发现并修复一处脆弱性**：`ret_from_fork` 首版在 `call schedule_tail`
  之后才从伪造帧读 fn/arg（`rb1-0x438` 处）——schedule_tail 的调用链从
  rb1 向下压栈，若深度超过 0x438 会覆盖 fn/arg。改为先把 fn/arg 读入
  callee-saved rb32/rb33（伪造帧恢复时为零，C ABI 保证 schedule_tail 及其
  callee 不动 callee-saved），`call schedule_tail` 之后再装填 arg 到 rb16、
  `call rb32,rd0,0`。amended 后反汇编逐条核对。
- 独立复跑探针（本记录即探针正式跑的结果，fresh -O0 重建 + 双后端零回归），
  非伪造。
- 根仓改动范围：只有 3 个既有文件追加式编辑 + 4 个新未跟踪文件
  （任务文件/patch/探针脚本 + 既有 `gcc-torture-results.json`），未越界；
  `gcc-torture-results.json` 全程未被读写。

### 独立 reviewer（subagent）

见下方 Review 小节。

## Review

### 独立 subagent 复核

**判决：PASS（Accepted）**。无 blocker/high finding；3 个 low + 若干 info/note。
核验全部基于 reviewer 自己的命令执行（重跑 QEMU、逐字节反汇编、patch
replay tree-hash 比对、证据 summary 独立交叉核对），非采信 worker 叙述。

#### 重跑记录（reviewer 自己的输出）

1. **独立 QEMU 正例重跑**（复用既有 `Image`/`kl156a-handoff.bin`，去掉 `-S`
   并等待自然跑完，避免原脚本用 QMP `cont` 的差异）：
   - 命令：`qemu-system-dadao -M dadao-m1 -icount shift=0 -global
     dadao-cpu.cfx-smon-real=on -bios <handoff> -kernel <Image> -display none
     -serial file:... -no-shutdown -d int -D ...`
   - 输出：console 到 `Kernel panic - not syncing: VFS: Unable to mount root
     fs on unknown-block(0,0)`（`[211.488000]`），**与证据文件
     `positive-console.bin` 逐字节一致**（`cmp` 通过，均为 2876 字节）。
   - 自己的 `-d int` 异常签名：`exception index=5` = 2、`index=7` = 1376、
     `index=1` = 0 —— 与证据 summary 完全一致（index=1 为零正是本任务
     修复后"无 ILLI 崩溃"的负向断言）。
2. **patch bare-pin replay**：在临时 worktree 对父提交 `b69106ec3` `git apply`
   0034 patch → `write-tree` = `8bbab5e5917070c5185da06e2ea5d3d13cf7b40b`，
   与 commit `bc06926f9^{tree}` 逐字节一致；worktree 已清理。patch SHA256
   `b1f2bac6...` 与任务记录一致。
3. **反汇编复核**（`llvm-objdump --triple=dadao-unknown-unknown`）：
   - `switch.o`：保存/恢复全部 `sto/ldmo` 立即数与 K2 §2.1 偏移逐槽核对
     （rd32@-0x400→frame+0x38、rb32@-0x300→frame+0x138、ra0@-0x200→
     frame+0x238、ra63@-0x8→frame+0x430、rb1@-0x420→frame+0x18、
     rb2@-0x418、rb3@-0x410、rb4@-0x408、SP 最后 `ldo rb1,rb1,0x18`、
     结尾 `ret rd0,0`）。relocation 表确认 `call schedule_tail`(0x188)/
     `call do_exit`(0x198) 目标正确。
   - `process.o` `__switch_to`：`addi rb1,rb1,-120`；`prev`@[rb1+88]、
     `next`@[rb1+80]、`flags`@[rb1+72]；marker 分支对比 `init_task` 符号；
     `local_irq_save` 走 `arch_local_irq_save` 出线副本（reloc 0x468/0x474
     为 `arch_local_save_flags`/`arch_local_irq_restore`）；switch 调用前
     `rd2rb rb16/rb17` = prev/next（reloc 0x390 → `dadao_switch_to_asm`）；
     `return prev` 在切回后从 [rb1+88] 重载 → rb31 → `ret`。
   - `vmlinux` 链接解析：`__switch_to`=0x800437a0、`dadao_switch_to_asm`=
     0x80045a50、`dadao_ret_from_fork`=0x80045bcc；`__switch_to` 内
     `call 2099`@0x80043980 → 0x80045a50。**关键真实性证明**：idle 保存帧
     `saved_ra63=0x0001000080043984` 的地址字段 = `call dadao_switch_to_asm`
     （0x80043980）的下一条指令 0x80043984 —— 正是 init_task 被挂起的
     __switch_to 返回点，且 refcount=1；`saved_rb1=0x87fefcf8 =
     kernel_sp(0x87fef8c0)+0x438`（帧基+帧长=被保存的 SP，与 K2 帧构造
     完全自洽）。该帧不可能是伪造的。
   - `asm-offsets.h`：`THREAD_KERNEL_SP_OFFSET_LO=1504=0x5E0`、HI=0，
     与 switch.S 内 `setzw rd9,0,1504; orw rd9,1,0` 一致。
4. **IRQ 屏蔽机制核对**：`local_irq_save/restore` 经 `arch_local_irq_restore`
   写 cg2/rc1 全局 CFX mask（irq.c:41-64），mask=ALL 期间 TIMER 保持 latch，
   解除后下一指令边界投递。**fresh task 的 IRQ 恢复路径已核实**：
   `ret_from_fork → schedule_tail → finish_task_switch → finish_lock_switch
   → raw_spin_unlock_irq`（kernel/sched/core.c:3115-3121）会 `local_irq_enable`
   重新打开全局 mask——所以 kernel_init 首次运行确实能收到 timer
   （证据 `timer_irq_count=1376`、`schedule_timeout_uninterruptible(10)`
   按时唤醒）。
5. **copy_thread 传参核对**：`kernel_thread(fn,arg)` 设 `args.stack=fn、
   args.stack_size=arg`（fork.c:2444-2454），`copy_thread(usp=stack,
   arg=stack_size,...)`，即 `frame[0]=usp=fn`、`frame[1]=arg=arg` 正确。
   `task->flags & PF_KTHREAD` 的判定基于 dup_task_struct 从父进程继承 flags；
   init_task 本身带 `PF_KTHREAD`（init/init_task.c:68），kthreadd/kworker
   链式继承，本 boot 全部 kthread 路径均命中（已验证证据：pid=1 真实创建、
   1124 次切换）。非 kthread 路径显式 `-ENOSYS` fail-closed，符合任务约束。
6. **探针脚本断言核对**（run_kl156a_...py）：异常签名白名单仅允许
   {index:5, mode:2, cfx:63}（恰 EXPECTED_SYNC=2 次）与 {index:7,...}，任何
   index=1 等其它异常直接 raise（第 822-834 行）——"index=1 必须为 0"是
   脚本里的硬断言，不是 summary 事后声称。idle 帧回读核验 rb1 落在 boot
   栈区 + ra63 refcount=1 且在 kernel text 区（1109-1133 行）。
7. **证据 summary 交叉核对**（kl156a.../summary.json）：`rest_init_pid_signed`
   =1（raw `0x1`）、`switch_count`=1124、`timer_irq_count`=1376、index{5:2,
   7:1376, 1:0}、`switch_from_idle`/`switch_to_idle`=true、`root_mount_attempt`
   =true、`exec_init_attempt`=false（根挂载墙在 exec 之前，符合预期）、
   console 五锚点各 1 次、`-serial none` 负例 console 0 字节且异常签名与
   正例一致、wrong-mode 负例 `KL149BAD`-only、e2e 81/81、differential
   AGREE 200/200、manifest/issues PASS。全部与任务记录一致。
   （注：任务记录正文写 `SWITCH_COUNT=1124`，summary/我的日志为 1124——
   计数器逐次运行自然浮动，任务文件数字是某次较早运行的旧值，非证据问题，
   归档时建议顺手改成与 summary 一致的 1124。）

#### 逐条核验点（每项 ✓）

- ✓ `dadao_switch_to_asm` 保存/恢复偏移与 K2 §2.1 帧逐槽一致（反汇编逐条
  比对，见上）。
- ✓ `ret rd0,0` 弹 next 的 RegRAS：真实任务弹挂起点返回地址（
  `call dadao_switch_to_asm` 压入的地址，evidence 中 saved_ra63 正是此点）；
  fresh task 弹 copy_thread 伪造的 ra63（refcount=1 + ret_from_fork），
  与 ISA §5.6 pop/refcount 语义一致（QEMU `helper_ras_pop` 的 refcount 处理
  已在任务记录核对）。
- ✓ 伪造帧与恢复路径槽位一一对应：copy_thread 写 w0/w1(=fn/arg)、
  0x18(=sp)、0x430(=(1<<48)|ret_from_fork)；switch.S 恢复读 0x238/0x430/
  0x38/0x138/0x30/0x28/0x20/0x18；ret_from_fork 读 (rb1-0x438)+0x000/0x008。
- ✓ ra63 refcount 构造：`(1UL<<48)|addr`，高 16 位 refcount=1、低 48 位地址；
  kernel text 地址 < 2^48 故不冲突（saved_ra63 实测 0x0001000080043984）。
- ✓ `__switch_to` return-prev 语义：prev 由 -O0 spill 到 [rb1+88]，切回后
  重载；即使未来换 -O2，prev 也只能放 callee-saved reg（帧会保存恢复）或
  本函数栈帧（正偏移、不受切换帧影响），机制成立。
- ✓ IRQ 屏蔽的理由与正确性：K2 切换帧 [SP-0x438,SP) ⊂ entry.S trap 帧
  [SP-0x640,SP)，SAVE 执行期间 TIMER 投递必然覆盖已存帧低段（rd32-63/
  rb32-63/ra 槽）——根因分析成立，`local_irq_save/restore` 掩码临界区修复
  合理；latch 语义保证不丢 tick（实测 1376 次 timer）。此 bug 的发现与修复
  过程记录可信（第一版无屏蔽时 index=1 5 次崩溃、修复后归零，我自己的重跑
  也确认 index=1=0）。
- ✓ ret_from_fork 的 fn/arg 经 callee-saved rb32/rb33 在 `call schedule_tail`
  之前读入，规避 schedule_tail 深栈覆盖伪造帧——amended 后正确；trap
  （timer）会全量保存/恢复 rb32/33，故跨中断也安全。
- ✓ marker 写入/屏蔽顺序无重叠风险：marker 在 irq_save 之前、切换帧尚不
  存在时写入，此时 trap 落在正常 [SP-0x640,SP) 窗口，无冲突。
- ✓ init_task 首次切换：`dadao_current` 静态初始化为 &init_task（setup.c:23），
  首个 switch_to(init_task, kernel_init) 保存 init_task 帧并置 kernel_sp；
  idle 帧回读证明（kernel_sp+saved_rb1/ra63 结构不变量）。
- ✓ 异常签名 index=5 恰 2（0x80000014=KL-149a handoff 探针 + 0x800444f4=
  dadao_cfx_craft_inner_mask 内 `trap 2,1` 之后）、index=7 千余、index=1 为 0。
- ✓ 负例纪律：`-serial none`（console 0 字节、异常签名一致）、wrong-mode
  `KL149BAD`-only。

#### Findings

- **[LOW] `WRITE_ONCE(dadao_current, next)` 先于实际切换执行 + -O0 下降级为
  memcpy()**（process.c:60，反汇编 0x2d0 = `call memcpy`）。窗口内（current
  已指向 next 但仍在 prev 栈上、IRQ 未关）若 TIMER 投递，tick handler 里基于
  `current` 的记帐（account_system_time 等）会记到 next 头上；理论上 memcpy
  若按窄字撕裂写，trap 读到半新半旧指针。实测 1376 次 timer + 1124 次切换
  零故障、单核无并发读，故只算 low。建议：把 WRITE_ONCE 移进
  dadao_switch_to_asm 的 `ret` 之前，或改用显式 8 字节 volatile 指针写以避开
  memcpy 降级。
- **[LOW] 切换只屏蔽异步（TIMER），不排除切换中途同步 fault**（switch.S/
  process.c 注释只写了 timer）。若 SAVE/RESTORE 的帧存取触发 PTW/TLB 同步
  fault，trap 帧仍会盖在未完成的 0x438 帧上。当前无实际故障源——依赖 K2
  §1.2 的"栈窗 [SP-0x640,SP) 必须 resident"不变式（所有栈存取都在该窗内，
  K2 已双后端验证）。建议注释里把这条不变式依赖写明。
- **[LOW/NOTE] fresh kthread 的 rb2/rb3/rb4 从伪造帧恢复为 0**（memset）。
  rb2 是可选 FP：当前 DADAO 无栈回溯实现（console 的 "stack trace
  unavailable" 即此），故无影响；若未来加基于 rb2 链的 unwind，kthread 栈
  会显示空帧。RISC-V 的 ret_from_kernel_thread 同型（s0=0），属常规做法。
- **[NOTE] 下一道墙旁的一处真实 WARN**：console 在 kernel_init_freeable 期
  间 `WARNING: CPU: 0 PID: 1 at fs/sysfs/group.c:115`——sysfs/kobject 侧
  内核告警，boot 继续，与切换实现无关；另 `hrtimer: interrupt took
  40876000 ns` 为慢仿真环境延迟告警。
- **[INFO] `THREAD_KERNEL_SP_OFFSET` 构建只覆盖 < 2^32**（setzw/orw 只做
  quarter0/1，asm-offsets.c 注释已声明）；当前 0x5E0，足够。
- **[INFO] gem5 侧未跑本 Linux boot**（验收/证据均为 QEMU；differential 是
  ISA 级回归非完整 Linux boot）。K2 帧本身双后端验证过，但 Linux
  __switch_to 在 gem5 上尚无证据——留给后续任务或 K2 探针补充。

#### 未测输入/边界推敲（推敲过的场景）

- 切换中途 TIMER 打断：已由屏蔽封死；解除屏蔽后 latch 投递（实测 1376 次
  timer 投递到新上下文、零 ILLI）。
- 嵌套切换：屏蔽期间异步不能进入；同步故障无来源（栈窗 resident）；切换体
  内无 call/ret 不碰 RAS，无重入路径。
- rd8/rd9 暂存与 trap 透明性：切换期间屏蔽无 trap；解除后 rd8/rd9 为
  caller-saved 可 clobber；trap 全量保存/恢复 rd1-63，透明。
- `schedule_timeout_uninterruptible(10)` 诊断 yield：M1_PROGRESS 门控、非
  真实 boot 路径；其产生的 idle→kernel_init→idle 往返正是 SWITCH_TO_IDLE/
  IDLE_ENTER 证据来源，符合验收意图。
- 未来 -O2 编译：prev/flags 只能存活于 callee-saved reg（由帧保存恢复）或
  本函数栈帧正偏移（不受切换帧影响），return-prev 语义仍成立。
- fresh task 首次 IRQ 打开路径已核实（finish_lock_switch→raw_spin_unlock_irq，
  见上），非巧合。
- 全部 135-word 逐字回读未做（K2 裸机可逐字比是因为有预置表；真实 Linux
  寄存器初值不可预测）——结构不变量（saved_rb1=kernel_sp+0x438、saved_ra63=
  __switch_to 返回点+refcount1、rb1 在 boot 栈区）+ 1124 次零 ILLI 切换 +
  saved_ra63 精确命中返回点，已足够证明保存/恢复正确。此边界在任务记录已
  诚实声明。

## 架构师处理

### 实施者对 subagent findings 的逐条处置（2026-07-31）

| finding | 处置 | 改了什么 | 复验证据 |
|---|---|---|---|
| [LOW] `WRITE_ONCE(dadao_current, next)` 先于切换执行，且 -O0 下降级为 memcpy 式复制，窗口内 current≠实际运行任务 | ✅已修 | `__switch_to` 把 `WRITE_ONCE(dadao_current, next)` 移到 `local_irq_save` 之后（掩码内、实际切栈前）更新 current，窗口彻底关闭 | 反汇编核对：`call arch_local_irq_save`@0x80043844 先于 WRITE_ONCE 机器码（0x80043854+，size-dispatch+8B store）与 `call dadao_switch_to_asm`；冒烟：index=1=0、VFS panic 到达、SWITCH_TO_IDLE/ROOT_MOUNT_ATTEMPT 点亮 |
| [LOW] 切换只屏蔽异步，同步 fault（PTW/TLB）中途仍会盖 0x640 trap 帧 | ✅已修（注释级） | process.c 掩码注释补充 K2 §1.2 栈窗 resident 不变式说明（帧存取全部落在已 resident 的 [SP-0x640,SP) 窗内，同步 fault 无来源） | 无代码路径变化；K2 §1.2 该不变式已双后端验证 |
| [LOW/NOTE] fresh kthread 的 rb2/rb3/rb4 从伪造帧恢复为 0 | ❌不修 | 与 RISC-V `ret_from_kernel_thread`（s0=0）同型属常规做法；当前无 rb2 链 unwind（console "stack trace unavailable"），无实际影响；copy_thread 注释已说明 | 无 |
| [NOTE] `sysfs/group.c:115` WARN（PID 1） | ❌不修 | 下一道墙旁的内核告警，boot 继续，与切换实现无关；已记入实施记录 | console 证据 |
| [INFO] `THREAD_KERNEL_SP_OFFSET` 构建仅覆盖 <2^32 | ❌不修 | asm-offsets.c 注释已声明；当前 0x5E0，足够 | 无 |
| [INFO] gem5 侧未跑本 Linux boot | ⏸延后 | K2 帧本身双后端验证过；Linux `__switch_to` 在 gem5 上的完整 boot 证据留给后续任务（本任务验收口径为 QEMU + ISA 级差分回归） | 已记入实施记录"遗留/诚实边界" |
| [归档小修] 实施记录 `SWITCH_COUNT=1124` 与 summary 的 1124 不一致 | ✅已修 | 实施记录数字改为与冻结 summary 一致的 1124 | summary 复核 |

上述处置均已同步回实施记录与代码注释。对 subagent 的三条 low 处理结论：
一条真改（WRITE_ONCE 移入掩码内）、一条注释级澄清（栈窗不变式）、一条
明确不修（rb2/rb3/rb4 与 RISC-V 同型）。无 blocker/high/medium 遗留。

（上面这条"架构师处理"标题有误导性——实际是本任务实施方自己对独立
reviewer 意见的处置，不是架构师本人的复核。架构师本人的独立复核见下。）

### 架构师独立复核（2026-07-31，独立执行，非采信自评，用户明确要求 review）

**结论：PASS，未发现需要修复的问题。**

- 独立读取 `process.c`：确认 `local_irq_save(flags)` 确实在
  `WRITE_ONCE(dadao_current, next)` 之前（`local_irq_save(flags);
  WRITE_ONCE(...); dadao_switch_to_asm(...); local_irq_restore(...)`），
  与处置表声明一致。
- **独立提出并核查一个额外的可疑点**（reviewer/自审记录均未提及）：
  `switch.S` 用的是 `stmo`/`ldmo`（不带 `_ra`/`_rb` 后缀）对 `ra0`/`ra63`
  寄存器存取，而 `DADAOInstrInfo.td` 里 `STMO_RA_RRRI`/`LDMO_RA_RRRI`
  的 opcode 是 `0x6F`/`0x67`，与操作 RD bank 的普通 `stmo`/`ldmo`
  （`do_stm`/`do_ldm`，QEMU `trans_stmo`/`trans_ldmo`）是不同 opcode——
  一度怀疑"用同一个助记符名字会不会选错寄存器组，导致 RA bank 从未被
  真正保存/恢复"。**独立核实为假警报**：LLVM tablegen 里
  `STMO_RA_RRRI`/`LDMO_RA_RRRI` 的第一操作数类型是 `GPRA`（RA 寄存器
  类），MC 汇编器按操作数寄存器类消歧同名助记符（同一个 "stmo"/"ldmo"
  文本，操作数是 `raN` 就选 RA-bank 编码，是 `rdN`/`rbN` 就选对应的
  RD/RB-bank 编码）——这是本项目一贯的、合理的 tablegen 设计，不是 bug。
  用已构建的 `.work/build/linux/arch/dadao/kernel/switch.o` 反汇编逐字节
  核实：`stmo ra0,...` 实际机器码首字节为 `0x6f`、`ldmo ra0,...` 为
  `0x67`，与同一函数里 `ldmo rd32,...`（`0x37`）/`ldmo rb32,...`
  （`0x47`）的 opcode 明确不同——RA bank 确实被真实存取，不是误用了
  RD/RB bank 的空操作。
- 独立完整重跑探针脚本（未读取既有 evidence，独立进程从头执行，含 fresh
  Linux `-O0` 重建 + QEMU 正例/负例启动，`-icount shift=0`）：
  `PASS: KL-156a K3 real fork + context switch (3/3, FAIL=0, SKIP=0)`；
  `rest_init_pid=1`、`kernel_init_enter=True`、`switch_to_idle=True`、
  `switch_count=1124`、`root_mount_attempt=True`——与记录及独立 reviewer
  的数值逐一一致（`switch_count`/`timer_real_entries_observed` 在
  `-icount shift=0` 确定性调度下天然可复现，不是巧合）。
- 独立重跑 `manifest_check.py`/`check_issues.py`：均 PASS，与记录一致。
- 独立执行 34-patch Linux 队列 bare-pin replay（`git worktree add
  --detach` 到 manifest pin `219d54332a09e8d8741c1e1982f5eae56099de85`，
  完整 `git am`）：replay tree hash 与开发树 HEAD tree hash 均为
  `a2e54796ccaee9e7d7581357c530eed909e17404`，逐字节一致；临时 worktree
  已清理。
- 确认根仓无新 commit（HEAD 仍为 `d92a5e6`），`.work/source/linux`
  `git status` clean、无残留 worktree/进程。
- 已有的三条 low finding 处置（WRITE_ONCE 移位、栈窗不变式注释、
  rb2/3/4 不修）判断合理，未发现遗漏；栈重叠这个根因 bug 的发现与修复
  过程记录可信，独立验证了其证据链（saved_ra63/saved_rb1 的结构不变量
  推导正确）。诊断/实现/范围判断均合理，PASS，可提交。
