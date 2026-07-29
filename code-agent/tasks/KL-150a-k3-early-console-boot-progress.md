# KL-150a：K3 QEMU early console 与可验证 boot progress

**状态**：完成（PASS，4/4，FAIL=0，SKIP=0）
**日期**：2026-07-29
**前置**：KL-149a
**后续**：KL-151a（trap/syscall entry 或由本任务 evidence 决定的首个阻塞）

## 背景与边界

KL-149a 已在精确 QEMU binary 上证明 HBI hypv→supv、Linux `_start`、
linked `Image` 和 guest-authored mode marker，但当前 `dadao-m1` machine
只有 ROM、RAM、exit MMIO 和测试 alias，**没有输出设备**。SEE 只定义
`cfx_uart` 的异常/pending 骨架，没有冻结 UART0 的设备寄存器协议。因此本
任务不能凭空把某套 8250 或旧项目 UART 常数声称为 architecture UART。

本任务只建立一个明确标成 **DADAO M1 test-machine debug console** 的
write-only byte sink，用于 K3 early printk。它不是 `cfx_uart`、不是正式
UART ABI、没有 RX/IRQ/baud/FIFO，也不构成 gem5 FullSystem parity。

## 目标

1. 在 QEMU `dadao-m1` 增加最小、固定地址、write-only 的 debug-console
   byte sink，并把字节送到 QEMU chardev/`-serial` 输出；
2. 在 Linux fresh `arch/dadao` 增加与该 test-machine contract 对应的
   early console，在 `setup_arch()` 早期注册，使 generic
   `start_kernel` printk 可观察；
3. 增加 guest-authored boot-progress words，至少区分：
   - 已进入 `setup_arch`；
   - `setup_arch` 的 memblock/zone 准备已完成；
   - 已进入 `mem_init`；
4. 用 QMP raw-memory oracle 作为主 verdict，并以 console 中的精确有序
   anchors 作为第二通道；不能仅因 QEMU 仍运行、日志非空或出现 head marker
   判 PASS；
5. QEMU/Linux component 变更分别用普通 commit、导出 patch 并追加各自
   series；新增 fail-closed runner 和完整 task/evidence 记录。

## 设计约束

- debug-console 地址必须位于独立的 M1 test-machine MMIO window，与
  ROM、exit MMIO、RAM、PTW alias、KL-149 scratch 不重叠；QEMU 和 Linux
  共享一个清晰常量/合同说明；
- 只接受 1-byte TX 写；其它 width/offset/read 必须有确定且无能力扩张的
  行为，不得伪装成 16550；
- Linux console 仅在 `CONFIG_DADAO_M1_DEBUG_CONSOLE` 下构建/注册，
  defconfig 可关闭；必须明确是 pre-MMU identity-mapped bring-up transport；
- progress words 位于 KL-149 已保留 scratch 中未使用的地址，正例运行前
  由 QMP 证明全零；每个阶段由真正负责该阶段的 C 函数写，禁止 head.S 一次
  预填所有里程碑；
- runner 继续固定 `KCFLAGS=-O0`，不混入 KL-148b；
- 不为“多打印几行”加入 fake scheduler/trap/timer/TLB/context-switch
  实现。若 boot 在更后阶段遇到真实阻塞，本任务在达到上述 progress 后如实
  记录并为 KL-151a 指出第一个阻塞；
- 不修改 gem5；不声称双后端 console、正式 UART、IRQ、TTY、login 或
  userspace。

## 验收

新增 `tests/scripts/run_kl150a_linux_early_console.py`（名称可等价调整），
必须：

1. 先验证 KL-149a frozen evidence/identity，不静默接受漂移；
2. 精确核对当前 QEMU/Linux patch 名称、完整 commit ID、stable patch-id，
   source worktree clean；
3. 对最终 QEMU source 做可追溯 rebuild，或以同等强度绑定最终 binary
   HEAD/hash/version；不得只记录身份；
4. 从 `mrproper` 重建 Linux `Image`，检查 ELF/Image/scratch non-overlap
   和 KL-149 正/负 HBI oracle不回归；
5. QEMU 以 `-S` 启动，先读取 progress window 全零，再 `cont`；
6. PASS 必须从 QMP 读到三个按约定值填写的 progress words，且顺序/阶段
   语义与 source 对应；
7. console log 必须包含有序、唯一、非 host 伪造的 anchors，至少包括
   DADAO early-console online marker、Linux banner、setup_arch 完成；
8. 负向判别至少覆盖“console transport 被关闭/错误地址”不会被日志门误判；
   可以使用独立 no-console config/image 或等价 mutation，但不得改写正式
   positive Image；
9. evidence 保存命令、patch/component/QEMU/Image identity、progress raw
   bytes、console bytes及明确 PASS/FAIL 计数；无 SKIP。

## 非声明

本任务不要求 kernel 完成所有 initcalls，也不声明 mem_init 之后的第一个
故障已修复。它不实现正式 `cfx_uart` 设备协议、interrupt-driven serial、
TTY、timer、Linux trap/syscall、context switch、MMU enable、initramfs、
login 或用户态 hello。

## 实施记录

### Component 实现与身份

- QEMU `dadao-m1` 在独立窗口 `0x10001000..0x10001fff` 增加
  **M1 test-machine debug console**。仅 offset 0 的单字节写送入 machine
  serial chardev；read 返回 0，其它 offset 写被丢弃，其它 width 不被
  MemoryRegionOps 接受。该 transport 没有 RX/status/baud/FIFO/IRQ，明确
  不是 `cfx_uart` 或 16550。
- QEMU ordinary commits/patches：
  - `247344a110fa99e18e66b4e2ce373e9ddb96d8f7` /
    `0037-hw-dadao-add-M1-test-machine-debug-console.patch` /
    stable patch-id `1e8d1730f84776a0e50db4f77afe14d2c3ac9c58`；
  - `dfc7842229c139cc606141b82845ecf20086e657` /
    `0038-target-dadao-log-precise-exception-state.patch` /
    stable patch-id `b9bb21ea84eac178d7957cfa2faa4e793e9f101e`。
    第二个 patch 只记录精确 exception index/PC/mode/cfx，供 evidence
    定位，不扩张任何 console、CFX 或 interrupt 能力。
- Linux `CONFIG_DADAO_M1_DEBUG_CONSOLE` 注册 boot console，并在启用时
  从同一 test-machine transport 直接发出 online/setup-done 锚点；
  defconfig 可关闭。Linux ordinary commits/patches：
  - `fdfdb9ca682c8839a7d59595a1b9d5fc9c46da5b` /
    `0006-dadao-add-M1-early-console-and-boot-progress.patch` /
    stable patch-id `44ff19d0599cc24b3715e88f587ca3a4e9b3dc87`；
  - `06c3d571a8ae249e451dc4f2151e6bfd8e8a5873` /
    `0007-dadao-harden-K3-O0-early-boot-progress.patch` /
    stable patch-id `d4a778294298992ca7255c96972b24d72c05aea0`。
- Linux 在 KL-149 scratch 中由真实 C 阶段写入：
  - `0x87fd0010 = 0x4b4c313530534145`（`setup_arch` enter）；
  - `0x87fd0018 = 0x4b4c313530534144`（`setup_arch` done）；
  - `0x87fd0020 = 0x4b4c3135304d494e`（`mem_init` enter）。
  `head.S` 与 handoff ROM 均不包含/预填这些值。

### progress word 阻塞定位与修复

最初运行并非停在 banner：QMP 只能看到 `setup_arch enter`，QEMU 精确
trace 显示 DADAO LLVM bring-up backend 在 `KCFLAGS=-O0` 下把若干 C
`bool` return 临时量放入非自然对齐的单字节栈槽，却用八字节 `ldo` 重新
加载，产生 `EXCP_MALIGN`。首个位置是
`mm/memblock.c::should_skip_region`；继续执行后同一缺陷依次暴露于 early
printk、mutex fastpath、kernel parameter matching、obsolete setup
matching 和 page-init predicate。

patch 0007 仅在既有 `CONFIG_DADAO_K3_O0_LINK_COMPAT` 下把这些启动必经
路径的真假 carrier 改为自然字宽，逻辑真假语义不变，普通配置仍使用
`bool`。setup-done 锚点也直接使用受 config 控制的 M1 transport，避免把
generic printk 是否已越过后续编译器缺陷误当作该阶段 progress。修复后
三个 progress word 均由对应 C 阶段实际写入。

### Runner 与 evidence

最后执行：

```sh
python3 tests/scripts/run_kl150a_linux_early_console.py
```

结果：`PASS: KL-150a early console and boot progress (4/4, SKIP=0)`；
`FAIL=0`。runner 从 `mrproper` fresh build 正例，并用独立 output tree
构建关闭 console config 的负例。QEMU rebuild identity：

- HEAD `dfc7842229c139cc606141b82845ecf20086e657`；
- version `QEMU emulator version 10.0.0 (v10.0.0-38-gdfc7842)`；
- binary SHA256
  `2326a4b69f3f8dc3e0c1b5c2f335d0df4c71182a481dd7f6071e4a38f6ac8240`。

正例在 vCPU 启动前由 QMP 读到 40 字节全零；最终 raw bytes：

```text
4b4c31343941484500000000000000004b4c3135305341454b4c3135305341444b4c3135304d494e
```

即 KL-149 marker、failure=0 和三个有序 KL-150a progress words。console
第二通道的三个 anchors 计数为 `[1,1,1]`，位置为 `[0,58,317]`：
M1 test-machine online、`Linux version 5.4.0`、setup_arch complete。

负控全部 fail-closed：

- 独立 `CONFIG_DADAO_M1_DEBUG_CONSOLE=n` Image：QMP progress 完整，
  console 0 字节、anchors `[0,0,0]`、console verdict=false；
- 正例 Image 加 `-serial none`：QMP progress 完整，console 0 字节、
  anchors `[0,0,0]`、console verdict=false；
- wrong previous-mode HBI ROM：最终 raw 为
  `00000000000000004b4c313439424144000000000000000000000000000000000000000000000000`，
  即 marker=0、`KL149BAD`、三个 progress=0，且 QEMU shutdown。

完整机器可读证据：
`.work/evidence/kl150a-linux-early-console/summary.json`，SHA256
`844f5ece4ea5b837e7ada01e4b2c841aecf7118ffb18b814de55eb24fe28d83c`；
同目录保留 build/QEMU 命令日志、raw progress、console bytes 和 exception
trace。

### 首个后续真实阻塞

达到 `mem_init enter` 后，当前 `-O0` Image 的首个异常是
`EXCP_MALIGN`，PC `0x80284100`，位于
`mm/page_alloc.c::free_pcp_prepare`（symbol start `0x8028352c`）。
反汇编仍是单字节 slot（`sp+207`）经 `ldo` 加载的同类 LLVM backend
bool/stack-slot 问题。它发生在本任务三个 QMP progress 全部完成之后，
因此不降级 KL-150a verdict；它是 KL-151a/后续编译器兼容工作的第一个
实证阻塞。本任务仍不声明 mem_init 完成、trap/syscall、正式 UART、
timer/IRQ、TTY、initramfs 或 userspace。

## Review

### 独立 reviewer

独立 reviewer 首轮结论为 **Not Accepted**，无 Blocker、一个 High、无
Medium、两个 Low：

- High：任务记录的 evidence summary SHA256 与最终文件不一致；功能
  evidence 本身未发现 false-green，但记录无法完整性校验；
- Low：QEMU 历史 patch 队列 0001..0036 已知不能完整 stable patch-id
  重放。KL-150a runner 已冻结 KL-149 parent、总数、新增 0037/0038
  commit/patch-id、最终 HEAD/binary/version，因此这是既有队列可重放性
  债务，不阻塞 KL-150a；
- Low：顶层既有未跟踪 `gcc-torture-results.json` 与本任务无关，必须
  排除在提交外。

reviewer 同时确认：三个 progress 由对应 C 函数的 volatile 写产生，保存的
QMP snapshots 呈现逐级前缀；console 只作为 secondary；no-console、
`-serial none` 和 wrong-mode negatives 有效；debug transport 未扩张为
UART；config-gated natural-width carrier 在当前静态 kernel 内语义/ABI
可接受；四个新增 component patch 与 commits 精确匹配；KL-149 回归绑定
充分。

### 主控二次复核与修复

主控接受 reviewer 的 High 并在最终回归后重新计算、记录上方 summary
SHA256。另外主动收紧 runner：

- source contract 现在隔离 `setup_arch()` 与 `mem_init()` 函数体，明确
  要求 `setup enter -> paging_init -> setup done` 以及
  `mem_init enter -> memblock_free_all` 的源码顺序；
- 达到三个 progress 后延迟采集的最终 QMP 快照必须再次精确等于
  `(KL149AHE, 0, KL150SAE, KL150SAD, KL150MIN)`，防止里程碑随后被覆盖
  仍误判 PASS。

修复后完整执行
`python3 tests/scripts/run_kl150a_linux_early_console.py`，结果仍为
`PASS 4/4，FAIL=0，SKIP=0`；两 component source worktree 均 clean，
`git diff --check` 与 runner `py_compile` 通过。独立 reviewer 唯一
阻止项已关闭，主控二次复核结论：**Accepted**。
