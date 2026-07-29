# KL-150a：K3 QEMU early console 与可验证 boot progress

**状态**：待执行
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

worker 完成后填写。

## Review

worker 返回后由独立 reviewer subagent 审核，再由主控二次复核。
