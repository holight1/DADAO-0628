# musl 里程碑调研 — syscall/console/exit ABI + libc 移植策略

**日期**: 2026-07-12 · **任务**: ML-001a
**wiki 基线**: 本地锁定 `13a414d`（DADAO-11-AEE 0.9.2, DADAO-12-SEE 0.7.1）
**wiki 远端最新**: `9f378f4`（8 commits ahead，见 §1.3 diff）

---

## 1. wiki AEE/SEE 定义了什么

### 1.1 AEE（本地锁定 DADAO-11-AEE 0.9.2）

**结论：AEE 为纯应用执行环境，未定义任何 syscall/ecall 机制。**

- 定义内容：数据表示（byte/wyde/tetra/octa）、存储模型（48-bit VA, 64-bit PA）、寄存器（rd/rb/rf/ra 各 64 个）、RAS 栈（call/ret 压弹栈）、浮点状态寄存器
- **无**：环境调用指令、syscall ABI、异常向量、特权模式切换
- **无**：任何形式的 ecall/trap/syscall 指令定义
- AEE 定位：用户态（user-mode）程序视角的 ISA，不涉及操作系统的交互接口

### 1.2 SEE（本地锁定 DADAO-12-SEE 0.7.1）

**结论：SEE 定义了完整的异常/系统调用机制——`trap` 指令 + CFXTRAP + cfx monitor model。**

关键发现（逐项回答任务问题）：

**Q: 定义了 syscall 机制吗？**
**A: 是。** SEE §5 定义 `trap` 指令触发 `CFXTRAP` 异常：

> "trap 指令可以在任意运行模式下执行，陷入到任意已定义核芯功能扩展中"（SEE §5, 异常进入流程 step 1）

`trap` 指令格式：携带 `cfxcode`（6-bit 目标核芯功能扩展编号）参数。用户程序 `trap` 某 cfxcode → 硬件按 §5 进入流程跳转到异常向量。

**Q: AEE/SEE 有 ecall 类指令吗？**
**A: 等价物为 `trap` 指令。** 无 RISC-V 式的 `ecall` mnemonic，但 `trap` 指令功能一致：
- User→S-mode：`trap cfx_smon` → 硬件切换到 `cfx_smon_user_switch_run_mode` 指定的运行模式（默认为 supv）+ 跳转到 `cfx_smon_user_excp_vector`
- 传递参数：异常原因 `CFXTRAP`（`1<<0`）、触发指令编码在 `excp_cause_info` 中
- 返回：`escape` 指令恢复 user 上下文

**Q: syscall ABI（哪个寄存器传号/参数/返回）？**
**A: wiki 未定义。** SEE 有硬件机制但没有软件 ABI 约定——无 syscall number 寄存器分配、参数传递规范、返回值寄存器。这些需 ADR 确定。

**Q: SEE 定义了什么？M1 是否可用？**
**A: SEE 定义了完整特权架构。** 四模式（U/J/S/H-mode）、cfx 核芯功能扩展模型（64 个）、页表/MMU、异常处理流程。
- M1（spec §7）排除的是 **RF（浮点寄存器）异常**，**不排除 trap/异常机制**——trap 与 RF 无关
- M1 可以用 SEE 定义的 `trap`→CFXTRAP 做 syscall，**不需 ecall 指令、不依赖 RF**

**Q: UART/console 是否已定义？**
**A: 是。** SEE §cfx_uart 定义了 UART 核芯功能扩展（cfxcode=62），有专用寄存器表，通过 `cfx2rd`/`cfx2rc` 指令读写 UART 寄存器。Gem5/QEMU 可据此实现 console I/O。

**Q: exit/关机机制？**
**A: 是。** SEE §cfx_power 定义了电源管理 cfx（cfxcode=63），支持关机（`POWEROFF`）、硬复位（`HARD_RESET`）、软复位（`SOFT_RESET`）。

### 1.3 wiki 远端更新（`13a414d` → `9f378f4`，8 commits）

与锁定版本的关键差异（仅列影响 syscall/libc 决策的变更）：

| 变更 | commit | 影响 |
|------|--------|------|
| cfx_power_ctrl 去重 + PTBR 跳转表 rb→rd 中转 | `10929f7` | exit 机制不变 |
| §5 重构 + FPEXCP 重命名 | `defdd96` | 异常流程重写，需根据最新版确认 trap→CFXTRAP 语义是否变更 |
| 中断模型前移 | `defdd96` | 异步中断模型与同步 trap 分路更清晰 |
| cg4 重组：excp_num 拆为 sync/async | `b3d6c82` | 异常计数分拆，不影响 trap 语义 |
| phymem→pmem 全文件重命名 | `9f378f4` | 纯文本重命名，无功能变更 |

**关键不变项**（远端最新版确认）：trap→CFXTRAP syscall 机制、UART cfx、power cfx 均保留。

---

## 2. syscall/console/exit 层选项

基于 SEE 已有的 `trap→CFXTRAP` + `cfx_uart` + `cfx_power` 基础设施，syscall 方案天然选择 **SEE trap-based**，而非半主机。

### 2.1 方案对比

| 维度 | (a) 半主机 semihosting | (b) MMIO console + exit | (c) 最小 SEE/SBI |
|------|----------------------|------------------------|-------------------|
| **核心机制** | QEMU/gem5 拦特定 MMIO/指令 | 扩 exit MMIO 加写端口 | `trap→CFXTRAP` + cfx handler |
| **双后端一致性** | QEMU/Gem5 各有独立 semihosting 实现，需对齐 | MMIO 最一致（存一个地址） | SEE 是 spec 标准接口，天然一致 |
| **需异常/trap？** | 不 | 不 | **是——但 SEE 已有 trap 指令** |
| **M1 兼容** | ✅ | ✅ | ✅（trap 不依赖 RF） |
| **对真 OS 延展性** | 弱（仅调试/仿真用） | 中（可映射到真实 console MMIO） | **强（SEE 本就面向真 OS kernel）** |
| **QEMU 改动量** | 需实现 semihosting trap 拦截 + stdout → 宿主 write | 加 1 个 MMIO 端口 handler | **利用现有 SEE trap 框架，无需新语义** |
| **Gem5 改动量** | 需实现 semihosting（无现成 DADAO semihosting） | 加 1 个 MMIO 端口 | 同 QEMU——用 SEE trap 框架 |
| **libc 适配** | `_write()` = semihosting call；`_exit()` = semihosting exit | `_write()` = MMIO store；`_exit()` = MMIO store | `_write()` = trap cfx_uart write；`_exit()` = trap cfx_power POWEROFF |

### 2.2 推荐：SEE trap-based + cfx_uart（方案 c，最小 SEE responder）

**理由**：
1. **SEE 已定义基础设施**——`trap` 指令、CFXTRAP 异常、UART cfx、power cfx 都已写好在 spec 里，只是 QEMU/gem5 还没实现
2. **远期零迁移**——未来真 kernel 直接复用同一套 SEE trap→cfx 接口，半主机/MMIO 方案要推倒重来
3. **双后端一致**——QEMU 和 gem5 都实现同一套 SEE cfx 寄存器，libc 不感知后端差异
4. **最小实现**：MVP 只需实现 `cfx_smon` 的 CFXTRAP handler 处理两个 syscall——`SYS_write`（→`cfx_uart` 写）和 `SYS_exit`（→`cfx_power` shutdown）

**代价估计**：
- QEMU：在 `target/dadao/` 加 cfx_smon trap handler（~200 行）+ cfx_uart 寄存器读写（~50 行）+ cfx_power POWEROFF（~20 行）
- Gem5：同样在 DADAO CPU model 加 cfx handler + uart + power
- libc：定义 syscall ABI（`trap cfx_smon` + 寄存器传参），写 `syscall.h` + `write`/`exit` stubs

---

## 3. libc 选型：musl vs picolibc/newlib

| 维度 | **musl** | **picolibc** | **newlib** |
|------|----------|-------------|------------|
| **导向** | Linux-syscall（需 kernel/syscall 模拟） | 嵌入式/freestanding | 嵌入式/freestanding |
| **最小 syscall** | write/exit/brk（或 mmap 替代） | `_write`/`_sbrk`/`_exit`（3 个 stub） | `_write`/`_sbrk`/`_exit`/`_open`/`_close`/`_lseek`/`_read`/`_fstat`/`_isatty` |
| **架构 port** | 需写 `arch/dadao/` 目录（syscall.h + crt1 + reloc.h + pthread_arch.h 等 ~10 文件） | `machine/dadao/` 选项文件 + meson build | `libc/machine/dadao/` 目录 |
| **printf("hi") 成本** | 较高——musl printf 依赖 FILE*/malloc 完整实现 | **最低**——tinystdio 可选，不依赖 malloc | 中——stdio 依赖 malloc |
| **malloc 成本** | musl mallocng 需 brk/mmap syscall | **最小**——`_sbrk` 一个 syscall | 需 `_sbrk` |
| **对真 OS 延展** | **最正统**——Linux/musl 是行业标准，未来真 kernel 直接换 syscall 实现 | 非 Linux 导向，重定向到嵌入式接口 | 非 Linux 导向 |
| **移植总工作量** | 中（~10 arch 文件 + syscall stubs） | **小**（~5 meson 文件 + 3 stubs） | 中小（~8 文件） |

### 3.1 推荐：musl + picolibc 分阶段

**第一阶段（MVP：printf + malloc + llvm-test-suite SingleSource）→ picolibc**：
- 3 个 stub（`_write`→trap cfx_uart write, `_exit`→trap cfx_power shutdown, `_sbrk`→simple heap）即可打通
- meson 构建，arch port 约 5 个文件
- 最小实现量，最大化验证覆盖率

**第二阶段（长期：真 kernel）→ musl**：
- 当 SEE/SBI handler 完善（mmap/brk/clone 等 syscall 有对应 cfx 实现）后，切换到 musl
- musl 是行业标准 libc，未来真 OS 必选

---

## 4. 移植路线（不实现，只估成本）

### 4.1 阶段 1：picolibc + SEE trap minimal

```
1. SEE trap syscall ABI:
   - syscall number: rd16
   - args: rd17-rd22
   - return: rd31
   - trap instruction: "trap cfx_smon"

2. QEMU cfx_smon handler:
   - intercept trap CFXTRAP → read rd<syscall num>
   - SYS_write (1): read buffer addr+len from args, write to cfx_uart → stdout
   - SYS_exit (93): call cfx_power POWEROFF
   - SYS_brk (for sbrk): simple heap MMIO

3. picolibc port:
   - machine/dadao/machine.ld (link script)
   - machine/dadao/meson.build
   - newlib/libc/machine/dadao/ (syscall stubs)
   - crt0.s (not crt1 — picolibc uses _start→main)

4. driver 链:
   clang --target=dadao -nostdlib -Wl,-T,dadao.ld crt0.o hello.o -lpicolibc -o hello.elf
```

### 4.2 阶段 2：musl（真 kernel 后）

成本估算：
- arch/dadao/ 目录：syscall.h, bits/alltypes.h, crt1.s, reloc.h, signal.h, clone.s, setjmp.s, vfork.s, pthread_arch.h, syscall_cp.s (~10 文件)
- syscall 映射：trap→cfx_smon → read/write/open/close/mmap/brk/clone 等 ~20 个 syscall
- 构建：configure/Makefile 需识别 `dadao` triple
- 总估：独立任务 `ML-00Xa`，依赖 SEE trap handler 完整实现

---

## 5. 推荐总结

| 决策项 | 选择 | 理由 |
|--------|------|------|
| **syscall 层** | SEE `trap→CFXTRAP` + cfx_smon handler | wiki 已有标准机制，双后端一致，远期正交 |
| **console** | cfx_uart（SEE 已有定义） | 标准 UART cfx，通过 cfx2rd/cfx2rc 驱动 |
| **exit** | cfx_power POWEROFF（SEE 已有定义） | 标准 shutdown 机制 |
| **第一阶段 libc** | **picolibc** | 3 stub 打通 printf+malloc，最小编译验证 |
| **第二阶段 libc** | **musl** | 行业标准，真 kernel 后切换 |
| **crt** | crt0→main（freestanding，同现有 E2E） | picolibc 无需 crt1/_start→__libc_start_main 链 |
| **syscall ABI** | rd16=sysno, rd17-22=args, rd31=retval, `trap cfx_smon` | ADR 待定 |

---

*注：本报告纯调研，不包含代码实现。wiki 引用据章节号（§N），不用行号。wiki 未定义项明确标注。*
