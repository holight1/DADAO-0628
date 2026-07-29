# KL-151a：K3 `mem_init` 完成与首个 post-memory 边界

**状态**：待执行  
**日期**：2026-07-29  
**前置**：KL-150a  
**后续**：KL-152a（由本任务 evidence 冻结的首个 post-memory 阻塞）

## 背景

KL-150a 已以 QMP raw memory 为主 oracle，证明 Linux 真实进入
`setup_arch()`、完成 `paging_init()` 并进入 `mem_init()`。最终 frozen
QEMU HEAD 为 `dfc7842229c139cc606141b82845ecf20086e657`，Linux HEAD 为
`06c3d571a8ae249e451dc4f2151e6bfd8e8a5873`。

当前第一个实证阻塞是 DADAO LLVM `KCFLAGS=-O0` 的 bool stack-slot
lowering：QEMU 报 `EXCP_MALIGN pc=0x80284100`，符号位于
`mm/page_alloc.c::free_pcp_prepare`。现有源码在非 `CONFIG_DEBUG_VM`
路径以 `bool` 返回 `free_pages_prepare()` 的结果；后端把单字节栈槽以
八字节 `ldo` 重新加载。

本任务只关闭这条实证链并证明 `mem_init()` 真正完成。不得把它扩大为
“Linux 已完成 early boot”、trap/syscall、timer/IRQ、调度、MMU 用户页表、
initramfs、TTY、login 或用户态能力。

## 目标

1. 在既有 `CONFIG_DADAO_K3_O0_LINK_COMPAT` 边界内修复
   `free_pcp_prepare` 当前实证的 natural-width carrier 问题；
2. 如继续执行后在 `mem_init()` 返回前遇到同类 `-O0` bool/stack-slot
   MALIGN，可按“一个实证位置、一个窄修复”的方式继续关闭，但必须逐项记录
   PC、符号、反汇编/栈槽依据；禁止预防性批量改写全部 generic bool；
3. 在 `arch/dadao/mm/init.c::mem_init()` 的最后一个真实初始化动作之后，
   写入新的 guest-authored progress word：
   - 地址 `0x87fd0028`；
   - 值 `0x4b4c3135314d4944`（ASCII `KL151MID`，mem-init done）；
4. 用 QMP 证明旧 KL-149/KL-150 progress 保持有序且新 word 只在
   `memblock_free_all()` 和 `mem_init_print_info()` 返回后出现；
5. 达到新 progress 后继续观察并冻结第一个真实 post-memory 阻塞，作为
   KL-152a 输入。

## 实施约束

- Linux component 必须用普通 commit；导出新 patch，追加
  `components/linux/patches/series`，记录完整 commit 与 stable patch-id。
- 预计不修改 QEMU；若确有不可回避的诊断需求，先在任务记录中说明原因，
  且不得借机扩张设备或体系结构能力。
- 所有 generic Linux 改动必须受 `CONFIG_DADAO_K3_O0_LINK_COMPAT`
  控制；普通配置保持原 `bool` 类型和语义。
- 跨编译单元接口若改变 carrier，声明与定义必须同步；只能返回规范化
  `0/1`，不得改变结构布局、持久数据格式、UAPI、模块 ABI 声明或函数参数。
- 继续固定 `KCFLAGS=-O0`，不处理 KL-148b 的默认 `-O2` 问题。
- progress 必须由 `mem_init()` C 函数在末尾写入；禁止在 `head.S`、
  HBI ROM、runner、QEMU 或更早函数预填。
- 保留 `0x87fd0000..0x88000000` bring-up scratch reservation，检查 Image、
  ELF、stack 与扩展后的 48-byte oracle window 不重叠。
- 不显式参考 `~/toolchain` 或 `~/knowledge-graph`。
- 不修改、不提交顶层既有未跟踪 `gcc-torture-results.json`。

## 验收

新增 `tests/scripts/run_kl151a_mem_init_completion.py`，必须 fail-closed：

1. 验证 KL-150a 根提交/任务记录和 frozen summary
   `.work/evidence/kl150a-linux-early-console/summary.json` 的 SHA256
   `844f5ece4ea5b837e7ada01e4b2c841aecf7118ffb18b814de55eb24fe28d83c`；
   精确检查其中 `PASS 4/4, FAIL=0, SKIP=0`、QEMU/Linux identity、正例
   五个旧 words、console anchors 和 wrong-mode oracle；
2. 检查 Linux/QEMU source worktree clean；精确绑定 Linux 全 patch queue
   的名称、commit、stable patch-id；QEMU 至少固定 KL-150a parent/HEAD、
   38 个 commit/patch 总数及 0037/0038 身份。历史 QEMU 0001..0036
   replay mismatch 作为既有债务记录，不得静默声称已修复；
3. 从 `mrproper` fresh build Linux `Image`，拒绝 forbidden diagnostics，
   验证 ELF64 big-endian、`EM_DADAO`、入口、无 undefined symbol、
   Image/scratch non-overlap，并记录 Image/vmlinux SHA256；
4. QEMU 用 `-S` 启动，`cont` 前 QMP 读取完整 48-byte oracle 全零；
5. 正例逐轮拒绝非法/跳级状态，并最终精确得到：
   `(KL149AHE, 0, KL150SAE, KL150SAD, KL150MIN, KL151MID)`；
   达标后延迟采集的最终快照必须再次精确匹配；
6. source contract 必须隔离 `mem_init()` 函数体并验证
   `KL150MIN -> memblock_free_all -> mem_init_print_info -> KL151MID`
   的顺序；扫描 `head.S` 与两份 HBI ROM，拒绝新值被预填；
7. console 仅为 secondary observation。正例要求 KL-150a anchors 仍唯一
   有序，并出现真实 `mem_init_print_info()` 的 `Memory:` 行；使用同一
   positive Image 加 `-serial none` 时，QMP 必须仍完整而 console verdict
   必须为 false；
8. wrong-mode ROM 必须保持
   `(0, KL149BAD, 0, 0, 0, 0)` 并 shutdown；
9. evidence 保存命令、component/patch/QEMU/Image identity、initial/final
   raw bytes、逐级 snapshots、console bytes、异常 trace、首个下一阻塞及
   明确 `PASS/FAIL/SKIP` 计数；不得把 QEMU 仍运行、日志非空或旧 progress
   当成 PASS；
10. 完整 runner 至少执行一次并为 `PASS 3/3, FAIL=0, SKIP=0`；结束时两个
    component source worktree仍 clean。

## 非声明

本任务只声明 `mem_init()` 的真实完成和第一个 post-memory 观察边界。即使
console 打印继续前进，也不声明 scheduler 可切换、trap/syscall 正确、
timer/外部中断可用、MMU 用户地址空间可用、initramfs `/init` 可执行、
TTY/login 或用户态 hello。

## 实施记录

worker 完成后填写。

## Review

worker 返回后由单独 reviewer subagent 只读审查，再由主控二次复核。
