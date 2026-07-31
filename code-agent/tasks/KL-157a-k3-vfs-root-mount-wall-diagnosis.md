# KL-157a：K3 VFS 根挂载墙诊断与最小推进

**执行环境**：DS（本仓库）
**状态**：待执行
**日期**：2026-07-31
**前置**：KL-156a（真实 fork/context-switch，`kernel_init` 真正执行，
boot 抵达 `prepare_namespace()` 的根挂载环节）
**后续**：待本任务诊断结果确定（真正的用户态执行/syscall 分发大概率是
更后面独立的里程碑，不预设本任务能走到那一步）

## 背景

KL-156a 精确诊断+架构师独立复核确认：`kernel_init` 现在真正执行到
`prepare_namespace()`，在挂载根文件系统这一步 panic：
`Kernel panic - not syncing: VFS: Unable to mount root fs on
unknown-block(0,0)`。`ROOT_MOUNT_ATTEMPT`（`KL156RMA`）marker 点亮，
`EXEC_INIT_ATTEMPT`（`KL156EIA`）未点亮——即卡在挂载根文件系统这一步，
还没到"找 `/init` 并尝试执行"那一步。

**已知现状**（已核对源码，非猜测）：
`arch/dadao/configs/dadao_defconfig` 已经设置了
`CONFIG_BLK_DEV_INITRD=y`/`CONFIG_DEVTMPFS=y`/`CONFIG_DEVTMPFS_MOUNT=y`，
但**没有配置任何真实的 initramfs 内容来源**（没有
`CONFIG_INITRAMFS_SOURCE`，没有 bootloader 提供的 initrd 镜像，
`arch/dadao` 目前也没有任何块设备驱动）——这条 panic 的精确触发路径
（是"完全没有可挂载的根"，还是"命令行/配置强制指向了一个不存在的
`root=` 设备、绕过了 Linux 默认的空 rootfs 兜底"）需要本任务去精确定位，
不要凭这段描述直接下结论。

## 目标

1. **精确定位这条 panic 的真实触发路径**：读 `init/do_mounts.c`/
   `init/initramfs.c` 相关代码，结合 `arch/dadao` 当前的 boot 配置
   （defconfig、`bootargs`/cmdline 传递方式——目前 K3 是否传了
   `root=` 之类的参数需要核实），确认这是"根本没有 rootfs 内容"、
   "有 `root=` 指向不存在设备被拒绝走默认兜底"、还是其它原因。
2. **用最小、诚实的手段越过这道墙**——目标只是"让 VFS 根挂载这一步
   成功"，不是"让完整用户态跑起来"：
   - 若诊断确认"配置一个真正为空/无实际内容的内建 initramfs 即可让
     Linux 走默认的 rootfs 兜底路径成功挂载"，就这么做（`CONFIG_
     INITRAMFS_SOURCE=""` 配合已有的 `CONFIG_BLK_DEV_INITRD=y` 通常已
     经是这个路径，具体需要核实为什么现在没生效）。
   - 若诊断发现还需要别的最小配置调整（例如 cmdline 参数、某个当前
     configs 里遗漏的选项），照做，但**不要**为了"看起来走得更远"而
     引入一个真实的块设备驱动、一个真实填充过用户程序的 initramfs、
     或任何本任务诊断之外的额外工程——那些如果确实需要，应该拆成
     后续独立任务。
3. **诚实报告下一道真实阻塞**：越过 VFS 根挂载这一步之后，Linux 大概率
   会走到"根目录挂载成功但找不到 `/init`"（`run_init_process()` 系列
   尝试 `/sbin/init`/`/etc/init`/`/bin/init`/`/bin/sh` 全部失败）的
   `Kernel panic - not syncing: No working init found` ——这**是**预期
   的、合理的下一道墙（K3 目前完全没有用户态、没有 syscall 分发、没有
   真实 ELF 加载/exec 路径，KL-155a/156a 都明确把这些排除在范围之外），
   不代表本任务失败。用 `CONFIG_DADAO_M1_PROGRESS` marker 精确记录
   到达的是这一步还是别的现象，不要笼统地写"启动继续了"。

## 约束

- **不实现真实用户态 exec/syscall 分发**——这需要页表切换到用户地址
  空间、真实 CFXTRAP 分发、ELF loader 的完整路径，K3 目前完全没有这些
  （`KL-155a` 已明确排除 CFXTRAP 分发，`KL-156a` 的 `copy_thread` 只覆盖
  内核线程），这些属于更后面独立的里程碑，本任务不碰。
- **不引入真实块设备驱动**——如果诊断发现"必须有一个块设备才能挂载根"，
  这是一个比"配置对空 initramfs 兜底"大得多的工程，应该停下来记录诊断
  结论、不要自己动手实现块设备驱动。
- **不往 initramfs 里塞任何真实用户程序**（musl-linked hello world 之类
  是 K4 的范围，需要真实 exec/syscall 支持后才有意义）——本任务的
  initramfs（如果需要）只应该是空的或者纯粹用于验证挂载机制本身。
- 延续既有证据纪律：`CONFIG_DADAO_M1_PROGRESS` marker、guest 自证优先、
  正负例对照、`-serial none` 独立复核、wrong-mode 负例 `KL149BAD`-only、
  QEMU 启动带 `-icount shift=0`（`KL-155a` 已确认的要求）。
- 不得引入新的 LLVM `-O0` bool-carrier workaround；如果撞到 inline asm
  操作数替换打印空文本这个已知缺口（`docs/issues.yaml` 的
  `dadao-inline-asm-operand-printer-empty-substitution`），继续沿用
  `KL-155a`/`156a` 已经建立的 workaround 惯例。
- 完成后写「实施记录」+ 自审记录，继续沿用"自己开 reviewer subagent
  复核"的方法。
- 不修改、不提交顶层既有未跟踪 `gcc-torture-results.json`。

## 验收

- fresh `KCFLAGS=-O0` Image：QEMU 正例 boot，越过当前的
  "Unable to mount root fs" panic（新增 marker 观测到根挂载真正成功，
  不是从 console 文本猜测）。
- 诚实报告越过这道墙之后到达的下一个现象——如果是预期的"No working
  init found" panic，明确记录并解释为什么这是合理的下一道墙；如果是
  别的现象（成功、别的 panic、静默卡死），如实记录，不要往好的方向
  拔高。
- KL-149a~156a 冻结的既有 marker/oracle 不回归；wrong-mode 负例保持
  `KL149BAD`-only。
- 全量 lit E2E、`tools/run_differential.py`、`manifest_check.py`、
  `check_issues.py` 无回归。
- 若有源码/配置改动：commit + patch + patch-series bare-pin replay
  （tree-hash 比对）。

## 参考指针

- `code-agent/tasks/KL-156a-k3-real-fork-and-context-switch.md` 完成区
  （`ROOT_MOUNT_ATTEMPT`/`EXEC_INIT_ATTEMPT` marker 定义、当前卡点的
  原始诊断证据）
- `arch/dadao/configs/dadao_defconfig`（当前 `BLK_DEV_INITRD`/
  `DEVTMPFS` 配置状态）
- `init/do_mounts.c`、`init/initramfs.c`（VFS 根挂载/initramfs 展开的
  通用 Linux 逻辑，本任务需要读这里理解精确触发路径，不要凭猜测）
- `code-agent/tasks/KL-154a-k3-post-mm-init-boot-progress-diagnosis.md`
  完成区（同类"先精确诊断、不预设结论"方法论的既有范例）

## 实施记录（2026-07-31）

### 结论

**PASS。** 精确诊断了 KL-156a 冻结的 "Unable to mount root fs on
unknown-block(0,0)" panic 的真实触发路径（**不是** `root=` 指向不存在设备，
而是完全没有可挂载的根），用最小手段（内建 initramfs 里的空占位 `/init`）
越过这道墙：`prepare_namespace()` 被跳过、初始 rootfs 即根（
`ROOTFS_FALLBACK` marker 点亮）。随后诚实观测到**与任务预期不同的下一道墙**：
`run_init_process("/init")` 进入 exec/mm 机制后撞上 fail-closed 的
`local_flush_tlb_all()` BUG（cfx_tlb 里程碑），`NO_WORKING_INIT` 未点亮（
该墙还没到）。

### 目标1：panic 触发路径的精确诊断

逐行读 `init/do_mounts.c`/`init/do_mounts_initrd.c`/`init/initramfs.c` +
当前 boot 配置：

- cmdline 为 `console=dadao0 init=/init panic=-1`，**无 `root=`**。
- `saved_root_name[0]==0` → `prepare_namespace()` 跳过 `root=` 分支。
- `initrd_load()`：无外部 initrd（`mount_initrd` 路径的
  `rd_load_image("/initrd.image")` 因无 /initrd.image 返回 false）→ 返回
  false。
- `mount_root()`：ROOT_DEV=0（默认），`mount_block_root("/dev/root")` →
  设备 0:0 不存在（无块设备驱动）→ **panic "VFS: Unable to mount root fs on
  unknown-block(0,0)"**。
- **关键诊断（推翻任务背景隐含假设）**：任务的假设"空的内建 initramfs 即可
  让 Linux 走默认 rootfs 兜底"**不成立**——空 initramfs（默认只有 dev/
  dev/console/root）早已存在（`CONFIG_INITRAMFS_SOURCE=""` 时
  `usr/initramfs_data.cpio` 就 512 字节），但 rootfs 兜底机制
  （`kernel_init_freeable` 里 `ksys_access(ramdisk_execute_command="/init",0)`
  成功 → 跳过 `prepare_namespace()`）**要求 /init 存在**。空 rootfs 无 /init
  → ksys_access 失败 → prepare_namespace 必然执行 → panic。所以
  "rootfs 可用" 与 "找不到 /init" 在机制上矛盾：要 rootfs 兜底生效，/init
  必须存在。

### 目标2：最小、诚实的推进

内建 initramfs 加一个**空占位 `/init`**（纯机制验证，无任何真实用户程序、
无块设备驱动）：

- `arch/dadao/initramfs.list`（gen_initramfs 规范文件：默认 dev/dev/console/
  root + `file /init arch/dadao/initramfs/init 0755 0 0`）+ 
  `arch/dadao/initramfs/init`（空文件，0755）。
- `dadao_defconfig`：`CONFIG_INITRAMFS_SOURCE="arch/dadao/initramfs.list"`
  （`INITRAMFS_ROOT_UID/GID=0`）；`CONFIG_CMDLINE` 去掉 `init=/init`（
  任务预期的 "No working init found" 墙需要 execute_command=NULL；当前
  exec TLB 墙下该参数不改变观测，属前瞻性对齐，任务允许最小 cmdline 调整）。
- **构建系统修复**：kbuild 的 `cmd_initfs` 以 **objtree** 为 CWD 解析
  `CONFIG_INITRAMFS_SOURCE`，全新 objtree（O=）构建找不到 srctree 里的
  initramfs 源（实测 `Cannot open 'arch/dadao/initramfs.list'`）。
  `arch/dadao/Makefile` 在 `prepare` 阶段把源镜像进 objtree
  （`$(abs_objtree)/...`，两阶段一致、objtree==srctree 时自依赖无害）。
  用全新空 objtree 实测验证可复现。
- 效果：`ksys_access("/init")` 成功 → `prepare_namespace()` 跳过 →
  `ROOTFS_FALLBACK` marker 点亮 → 初始 rootfs 即根。**根挂载墙越过。**
  负向证据：console 不再有 "Unable to mount root fs"。

### 目标3：下一道墙的诚实观测（与任务预期不同，如实报告）

`kernel_init` 继续：`ramdisk_execute_command="/init"` →
`run_init_process("/init")` → console 出现 **"Run /init as init process"**
→ `INIT_EXEC` marker 点亮 → exec 路径进入 mm 机制 → 撞上
**`BUG: failure at arch/dadao/include/asm/tlbflush.h:13/local_flush_tlb_all()`**
→ `Kernel panic - not syncing: BUG!`。**不是**任务预期的 "No working init
found"。

- **精确到调用链**（临时诊断实证，已清除）：空文件在 ELF magic 检查处
  `-ENOEXEC` 失败，但 `do_execve` 的 `alloc_bprm` 已创建 bprm->mm（含
  arg-page 栈 VMA）；清理时 `free_bprm`→`mmput`→`exit_mmap`→
  `tlb_finish_mmu`→`tlb_flush_mmu`→`tlb_flush_range`→`local_flush_tlb_all()`
  BUG。在 `exit_mmap` 临时埋 marker 确认其先于 BUG 触发（`__builtin_
  return_address` 在 DADAO 上读的是栈返回槽、因 DADAO 用硬件 RAS 而恒为 0，
  弃用改用 marker）。
- 这是 **cfx_tlb 范围失效（TLB flush）里程碑**——`tlbflush.h` 明确注释
  "later K3 milestone"，fail-closed 是设计意图。exec 在 cfx_tlb 落地前
  无法工作（任何 exec 都建/拆 mm、必然需要 flush），所以 "No working init
  found" 当前不可达。`NO_WORKING_INIT` marker 保留为未来观测点。
- 任务预期与实测的差异根源：任务的 "根挂载成功但找不到 /init" 假设与 rootfs
  兜底机制矛盾（机制要求 /init 存在才能跳过 prepare_namespace）。实测更
  进一步：/init 找到、exec 尝试、卡在 mm/TLB 里程碑。

### 验收逐项核对（探针 `tests/scripts/run_kl157a_k3_vfs_root_mount_wall_diagnosis.py`）

- **越过 "Unable to mount root fs" panic + marker 观测根挂载成功**：
  `ROOTFS_FALLBACK`（KL157RFB）点亮 = `prepare_namespace()` 被跳过、初始
  rootfs 即根；console 五锚点正常且 **不含** "Unable to mount root fs"。
  ✓
- **下一道墙诚实报告**：`INIT_EXEC`（KL157XEC）点亮 + console
  "Run /init as init process" + `local_flush_tlb_all()` BUG +
  "Kernel panic - not syncing: BUG!"；`NO_WORKING_INIT`（KL157NWI）未点亮
  （正确：cfx_tlb 墙在 /sbin/init 链之前）。不 claim 启动到 login。✓
- **KL-149a~156a 冻结 marker/oracle 零回归**：rest_init_pid=1、
  kernel_init_enter、idle_enter、SWITCH_FROM/TO_IDLE、SWITCH_COUNT=1124、
  ROOT_MOUNT_ATTEMPT 全部照旧；wrong-mode 负例 `KL149BAD`-only。✓
- **异常签名**：index=5 恰 2 次、index=7 千余次、index=1 为 0（exec 的
  BUG 是 `BUG()` 直接 panic，非非法指令异常，trace 里无 index=1）。✓
- **负例**：`-serial none` 写一次 marker（含 KL-157a 三个）与 positive 逐字
  一致；wrong-mode 负例 KL149BAD-only。✓
- **全量回归**：lit E2E 81/81；`run_differential.py` AGREE 200/200、
  DIVERGE=0；`manifest_check.py` PASS；`check_issues.py` PASS。✓
- **commit + patch + bare-pin replay**：Linux commit `ae32e45d1`（父
  `78601a1d2`=KL-156a HEAD，作者对齐 suiyan@sunmmio.com），6 文件 +2 新增
  （initramfs.list/init）。patch `0035-...patch`（SHA256
  `c20ef4772f73088faf0bf7a2999b6b0dafdbeedb3565786cda2e4fe4bc15fdf1`，
  stable patch-id `25ef60900df63df626348da032ac01d7b3c000fd`，与 commit
  一致）。35-patch bare-pin replay（manifest 锁定
  `219d54332a09e8d8741c1e1982f5eae56099de85`）：replay tree hash = 开发树
  tree hash = `fde246f78fd033b66004b51d412d35b03ef54797`，逐字节一致；
  worktree 已清理。✓
- **探针脚本**：完整复用 KL-152a..156a 的排他锁/run-id/staging/
  current-state/原子 summary 机制；oracle 扩到 30 词（+ROOTFS_FALLBACK/
  NO_WORKING_INIT/INIT_EXEC）；console 断言改为"旧墙消失（无 VFS panic）+
  新墙出现（Run /init + tlbflush BUG + BUG panic）"；异常签名 index=1=0
  负向断言保留；idle 保存帧回读保留作切换机制回归。✓

### 遗留/诚实边界

- `NO_WORKING_INIT` marker 已埋好但当前 cfx_tlb 墙下不点亮，等 TLB flush
  里程碑落地后成为下一观测点。
- exec 的 mm/TLB flush（cfx_tlb）是更后面独立里程碑，本任务明确不实现。
- 占位 /init 是空文件、纯机制验证；塞真实用户程序是 K4 范围。
- `CONFIG_CMDLINE` 去掉 `init=/init` 在当前墙下不影响观测（exec BUG 在
  ramdisk_execute_command 路径先行），是为跨过 cfx_tlb 后的预期墙做的前瞻
  对齐。

### 自审记录

结论：**PASS，可进入独立 subagent review**。

- 独立核对 do_mounts.c/do_mounts_initrd.c/initramfs.c 触发路径与实测 panic
  逐行对应（ROOT_DEV=0、initrd_load false、mount_root 设备 0）。
- 独立验证 rootfs 兜底机制：kernel_init_freeable 的 ksys_access("/init")
  必须成功才跳过 prepare_namespace；空 initramfs 无 /init → 必 panic；
  加占位 /init 后 ROOTFS_FALLBACK 点亮 + VFS panic 从 console 消失（正反
  对照）。
- 独立验证构建系统修复：全新空 objtree `make Image` 从
  `Cannot open 'arch/dadao/initramfs.list'` 到成功，initramfs 含 /init；
  abs_objtree/abs_srctree 两阶段一致。
- 独立实证 exec 下一道墙调用链：exit_mmap 临时 marker 先于 BUG 触发；
  空文件 -ENOEXEC 但 bprm->mm 已建、清理时 mmu_gather flush。
  `__builtin_return_address` 在 DADAO 恒 0 的结论已记录。
- 临时诊断全部逐字节还原（tlbflush.h/mmap.c/process.c 均回到基线，git
  diff 核对）；根仓改动范围：3 个既有文件追加式编辑 + 4 个新未跟踪文件
  （任务文件/patch/探针脚本 + 既有 gcc-torture-results.json），未越界。
- 探针正式跑结果（fresh -O0 重建 + 全量回归）即本记录数据，非伪造。

## Review

### 独立 subagent 复核

**判决：Accepted。** 诊断与实现全部经独立重跑/源码逐行核对成立；1 个
medium finding（in-tree 构建被 Makefile prepare 规则弄坏，O= 工作流不受
影响）+ 2 个 low（marker 语义注释、探针脚本注释过时）+ 若干信息级记录。
无 blocker/high。

#### 重跑记录（本人执行，非采信 worker 叙述）

1. **fresh O= objtree 全量 `Image` 构建**：`make O=/tmp/opencode/kl157-objtest
   ARCH=dadao CC='clang --target=dadao' ... dadao_defconfig` exit=0；
   `Image` exit=0。`usr/initramfs_data.cpio.gz` 解开含 `/init`(0755,0 字节)、
   `dev/console`、`root`（2 blocks）。`arch/dadao/initramfs.list` 及
   `initramfs/init` 均被 prepare 规则镜像进 objtree。构建系统修复在全新
   objtree 下可复现。
2. **in-tree 构建反例**：git worktree c348cacae 下 `make dadao_defconfig` +
   `make prepare` → **失败**：
   `make: Circular .../initramfs.list <- .../initramfs.list dependency
   dropped.` + `cp: '.../initramfs.list' and '.../initramfs.list' are the
   same file` + `make: *** [arch/dadao/Makefile:33] Error 1`。
   → Makefile 注释"objtree == srctree 时自依赖无害"**不成立**（见 finding
   M-1）。
3. **探针脚本全量重跑**：`python3 tests/scripts/run_kl157a_...py` →
   `PASS: KL-157a ... (3/3, FAIL=0, SKIP=0)`，run_id
   `1785500389402035183-965586-d1592582b642011b`。重跑后证据：
   - positive console：`Kernel command line: console=dadao0 panic=-1`（无
     `root=`/`init=`）；`Run /init as init process` → `BUG: failure at
     arch/dadao/include/asm/tlbflush.h:13/local_flush_tlb_all()!` →
     `Kernel panic - not syncing: BUG!`；**无** VFS panic；五锚点
     `[1,1,1,1,1]` 唯一有序。
   - markers（oracle 内存回读，非 console 推断）：
     `rootfs_fallback=True init_exec=True no_working_init=False`；
     KL156 冻结项 `root_mount_attempt=True exec_init_attempt=False
     switch_from/to_idle=True switch_count=1124` 零回归。
   - 异常签名：positive/serial-none 均 index=5 恰 2、index=7 千余（1453/1458）、
     **index=1 为 0**（BUG() 走 printk+panic，非非法指令异常）。
   - `-serial none`：console size 0、marker 序列与 positive 逐字一致。
   - wrong-mode：`final_raw_hex` 仅含 `4b4c313439424144`（KL149BAD），
     status=shutdown。
   - 回归：lit E2E 81/81；`run_differential.py` AGREE 200/200 DIVERGE=0；
     `manifest_check.py` PASS；`check_issues.py` PASS；patch bare-pin
     replay tree-hash `fde246f7...` match。
4. **patch 身份**：`0035-...patch` SHA256
   `c20ef4772f73088faf0bf7a2999b6b0dafdbeedb3565786cda2e4fe4bc15fdf1`；
   `git patch-id --stable` = `25ef60900df63df626348da032ac01d7b3c000fd`，
   与 commit c348cacae 的 patch-id 一致。
5. **防造假/清理**：linux 源树 `git status` 干净（临时诊断
   tlbflush.h/mmap.c/process.c 无残留）；根仓未跟踪
   `gcc-torture-results.json` mtime 07-25（先于本任务，未动）。

#### 诊断正确性逐条核验（读代码，非采信叙述）

- ✓ **无 root= 触发路径**：`arch/dadao/kernel/setup.c:45`
  `strlcpy(boot_command_line, CONFIG_CMDLINE, ...)`——cmdline 完全来自
  defconfig，新 console 实证 `console=dadao0 panic=-1` 无 `root=`。
  `do_mounts.c:571 prepare_namespace` 中 `saved_root_name[0]` 为 0 → 跳过
  root= 分支，`ROOT_DEV` 保持 0。
- ✓ **initrd_load 返回 false**：`do_mounts_initrd.c:128` 依赖
  `rd_load_image("/initrd.image")`；`do_mounts_rd.c rd_load_image` 首个
  `ksys_open(from)` 对不存在文件失败 → return false（无外部 initrd）。
- ✓ **mount_root → 设备 0 panic**：`do_mounts.c:534 mount_root` →
  `create_dev("/dev/root", ROOT_DEV=0)` +
  `mount_block_root("/dev/root")` → `do_mount_root` 的 `ksys_mount` 失败 →
  `panic("VFS: Unable to mount root fs on %s", "unknown-block(0,0)")`
  （`CONFIG_BLOCK` 路径）。
- ✓ **核心诊断（rootfs 兜底要求 /init 存在）**：
  `init/main.c kernel_init_freeable`：
  `ramdisk_execute_command = "/init"` → `ksys_access("/init", 0) != 0` →
  `ramdisk_execute_command = NULL; prepare_namespace();`。空 initramfs
  （默认只有 `dir /dev`/`nod /dev/console`/`dir /root`，
  `usr/gen_initramfs_list.sh:45-56`）**无 /init** → ksys_access 失败 →
  prepare_namespace 必然执行 → panic。任务的"空 initramfs 即可兜底"假设
  确实被推翻，worker 的诊断正确。
- ✓ **占位 /init 越过墙**：`arch/dadao/initramfs.list` 复刻默认三行 +
  `file /init arch/dadao/initramfs/init 0755 0 0`；`populate_rootfs`
  （rootfs_initcall）先于 kernel_init_freeable 的 ksys_access 展开内建
  initramfs → ksys_access 成功 → 跳过 prepare_namespace →
  ROOTFS_FALLBACK 点亮（= 初始 rootfs 即根，直接内存证据）。
- ✓ **下一道墙调用链**（source + 实证）：
  `run_init_process("/init")` → `do_execveat_common`（`fs/exec.c`）→
  `bprm_mm_init` 建新 mm（mm_users=1）→ 空文件在 `binfmt_elf.c:1184-1187`
  `kernel_read` 不足 `sizeof(elfhdr)` → `-ENOEXEC` → `out:` 分支
  `mmput(bprm->mm)`（`exec.c:1843`）→ `__mmput` → `exit_mmap`
  （`mmap.c:3108`）→ `tlb_gather_mmu(0,-1)`（fullmm=1）→ `tlb_finish_mmu`
  → `tlb_flush_mmu` → `tlb_flush_mmu_tlbonly` → `tlb_flush` → fullmm 时
  `flush_tlb_mm` → `local_flush_tlb_all()`（`tlbflush.h:13 BUG()`）。
  BUG()= printk("BUG: failure at %s:%d/%s()!")+panic("BUG!")
  （`asm-generic/bug.h:54`），与 console 逐字吻合；故无 index=1 异常。
  fail-closed 是设计意图（tlbflush.h 注释"later K3 milestone"），
  与"不实现 cfx_tlb"边界一致。
- ✓ **markers 布局/触发时机**：dadao-m1.h 偏移
  0xd8/0xe0/0xe8 = oracle 词 27/28/29，与探针 IDX 对应。ROOTFS_FALLBACK
  位于 ksys_access 块之后且 `if (ramdisk_execute_command)` 门控 → 仅在兜底
  路径点亮；NO_WORKING_INIT 位于 "No working init found" panic 之前，
  当前被 exec BUG 抢先 → 不点亮，正确。
- ✓ **cmdline 去 init=/init 的合理性**：`init=` 只设 `execute_command`
  （`main.c:341`），不设 ramdisk_execute_command；当前墙下
  ramdisk_execute_command="/init" 路径先行 BUG，去掉与否观测不变；去掉后
  未来越过 cfx_tlb 时可走到 `No working init found`（NO_WORKING_INIT），
  属诚实前瞻，任务允许最小 cmdline 调整。

#### Findings

- **M-1（medium）`arch/dadao/Makefile:31-33`**：prepare 规则在
  objtree==srctree 时是真·循环自依赖，GNU make 丢弃依赖并告警后 recipe 仍
  执行 `cp 同一文件到同一文件` → Error 1（已实证）。Makefile 注释
  "no-op self-prereq when objtree == srctree" 是错误陈述。本项目全流程
  O= 构建（全部证据日志均 O=），故验收不受影响；但该提交后的 in-tree 构建
  会挂。建议加 `ifneq ($(abs_objtree),$(abs_srctree))` 门控或对 recipe
  做存在性保护。
- **L-1（low）`init/main.c` INIT_EXEC**：marker 置于
  `if (ramdisk_execute_command)` 分支之前，语义是"kernel_init 到达 exec
  阶段"而非"exec 已发生"；当前配置下两者重合，无误导风险，注释也已说明。
  仅记过。
- **L-2（low）`tests/scripts/run_kl157a_...py:88`**：注释 "Word indexes
  within the 27-word oracle" 与实际 `ORACLE_WORDS=30` 不符，纯注释过时。
- **I-1（info）`__builtin_return_address` 在 DADAO 恒 0（硬件 RAS）**：
  来自已清除的临时诊断，无法独立复核，不影响交付物，按记录采信。
- **I-2（info）console 中 `WARNING: fs/sysfs/group.c:115` 与
  "Warning: unable to open an initial console."**：两者在 KL-156a 证据
  console 中同样存在，非 KL-157a 引入的回归。
- **I-3（info）正例 Image/vmlinux hash 在两次运行间不同**（a86448e9 vs
  761717ef）：系每次 mrproper 重建嵌入时间戳所致，属预期，非证据漂移。

#### 未测输入推敲

- `CONFIG_INITRAMFS_SOURCE` 指向 srctree 相对路径 + O= objtree 是唯一经
  实测的路径；绝对路径/带空格多源未测（kbuild 语义未变，低风险）。
- 未来 cfx_tlb 落地后 NO_WORKING_INIT 的触发、`init=/init` 移除后
  execute_command 路径的 panic 文案（"Requested init failed" vs
  "No working init found"）未测——属下一里程碑范围，本任务不要求。
- in-tree 构建（上述 M-1）为**已实测失败**的输入，已列 finding。

#### AC 逐项核验

- ✓ fresh `KCFLAGS=-O0` Image：QEMU 正例 boot 越过 "Unable to mount
  root fs"（ROOTFS_FALLBACK 内存证据 + console 无 VFS panic，非文本推断）。
- ✓ 下一墙诚实报告：INIT_EXEC + "Run /init as init process" +
  tlbflush.h:13 BUG + "Kernel panic - not syncing: BUG!"；NO_WORKING_INIT
  未点亮并说明为什么（cfx_tlb 墙在 /sbin/init 链之前）；不 claim 用户态
  启动。与任务预期的 "No working init found" 差异已明确解释（兜底机制
  要求 /init 存在，故二者机制性互斥；实测更靠后到 exec/mm）。
- ✓ KL-149a~156a 冻结 marker/oracle 零回归（探针 `KL-149 回归`、prior
  5/5、switch_count=1124、wrong-mode KL149BAD-only 全部过）。
- ✓ 全量回归：lit E2E 81/81、differential AGREE 200/200、manifest PASS、
  check_issues PASS（本 review 重跑后同值）。
- ✓ commit c348cacae + patch（SHA256/patch-id 吻合）+ 35-patch bare-pin
  replay（tree-hash `fde246f78fd033b66004b51d412d35b03ef54797` match）。
- ✓ 约束：无真实用户态 exec/syscall 分发、无块设备驱动、initramfs 仅空
  占位 /init、无新 O0 bool-carrier workaround、gcc-torture-results.json
  未动、临时诊断已清除。

## 架构师处理

### 实施者对 subagent findings 的逐条处置（2026-07-31）

| finding | 处置 | 改了什么 | 复验证据 |
|---|---|---|---|
| M-1（medium）`arch/dadao/Makefile` prepare 规则在 objtree==srctree（in-tree）时是循环自依赖（目标==自身前置），recipe 仍执行同名 `cp` → Error 1；注释 "no-op self-prereq" 是错误陈述 | ✅已修 | 用 `ifneq ($(abs_objtree),$(abs_srctree))` 门控整段规则（O= 才镜像） | in-tree `make -p` 数据库确认规则不再定义（无循环）；全新空 O= objtree 完整 Image 构建通过、initramfs 含空 /init |
| L-1（low）`init/main.c` INIT_EXEC marker 语义是"到达 exec 阶段"而非"exec 已发生" | ❌不修 | 它恰好放在 `run_init_process(ramdisk_execute_command)` 之前、正是观测点；注释已说明（"reached the point of exec'ing"） | 无 |
| L-2（low）探针 docstring/注释残留 "27-word oracle" 与实际 30 不符 | ✅已修 | 探针注释改为 30-word | 全文 grep 无残留 |
| I-1 `__builtin_return_address` 恒 0（硬件 RAS）来自已清除的临时诊断 | ⏸延后 | 结论已记入实施记录；临时诊断已逐字节还原 | git diff 核对 |
| I-2 sysfs WARNING / "unable to open an initial console" | ❌不修 | KL-156a 证据中同样存在，非本任务回归 | 对照 KL-156a summary console |
| I-3 两次运行 Image/vmlinux hash 不同 | ❌不修 | 重建时间戳差异，非证据漂移 | 探针按组件 HEAD/SHA 冻结校验，非 Image 本身 |

对 M-1 的处理：真改（门控）+ 双向复验（in-tree 规则消失、O= 可复现）。L-2
注释修正。无 blocker/high/medium 遗留（M-1 已闭环）。

### 架构师独立复核（2026-07-31，独立执行，非采信自评，用户明确要求 review）

**结论：PASS，未发现需要修复的问题。**

- 独立读取 `init/main.c` 第1309-1315行：确认 rootfs 兜底机制精确如实施
  记录所述——`ramdisk_execute_command="/init"`、`ksys_access(...)!=0`
  时才置 `NULL` 并执行 `prepare_namespace()`；成功则跳过。核心诊断（
  "空 initramfs 不能触发兜底，因为兜底本身要求 /init 存在"）逐字确认。
- 独立读取 `arch/dadao/include/asm/tlbflush.h` 第11-14行：确认
  `local_flush_tlb_all()` 确系 `BUG()`，注释"later K3 milestone"，与
  下一道墙的诊断一致。
- 独立读取 `arch/dadao/Makefile`：确认 `ifneq ($(abs_objtree),
  $(abs_srctree))` 门控确实已加在 prepare 规则外层，与 M-1 的处置记录
  一致（现有文件已是修复后状态，非仍待修复）。
- 独立完整重跑探针脚本（未读取既有 evidence，独立进程从头执行，含
  fresh Linux `-O0` 重建 + QEMU 正例/`-serial none`/wrong-mode 三次
  启动）：`PASS: KL-157a K3 VFS root-mount wall bypass (3/3, FAIL=0,
  SKIP=0)`；`summary.json` 核对
  `marker_analysis.kl157={rootfs_fallback:true, init_exec:true,
  no_working_init:false}`、`console_has_vfs_panic=false`、
  `console_has_tlbflush_bug=true`、KL-156a 冻结项（`switch_count=1124`
  等）零回归——与完成区声明逐项一致。
- 独立重跑 `manifest_check.py`/`check_issues.py`：均 PASS。
- 独立执行 35-patch Linux 队列 bare-pin replay（`git worktree add
  --detach` 到 manifest pin `219d54332a09e8d8741c1e1982f5eae56099de85`，
  完整 `git am`）：replay tree hash 与开发树 HEAD tree hash 均为
  `7e31f6e74529620c907f09d34c10a07f7cac90a4`，逐字节一致；临时 worktree
  已清理。
- 未重复独立复现 in-tree 构建负例（会触碰真实 dev tree 的构建产物，
  且 worker 与其独立 reviewer 已各自实测过一次，风险收益不对等），
  改为只核实"修复后的 Makefile 确实带门控"这一更直接、无副作用的
  证据，已足够确认 M-1 的处置真实生效。
- 确认根仓无新 commit（HEAD 仍为 `af20c4c`），`.work/source/linux`
  `git status` clean、无残留 worktree。
- 诊断/实现/范围判断均合理，PASS，可提交。

