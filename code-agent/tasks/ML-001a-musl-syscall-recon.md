# ML-001a: musl 里程碑调研 — syscall/console/exit ABI + libc 移植策略

**执行环境**: 本地 DS · DADAO-0628（调研，只读 wiki/参考，不改代码）

**状态**: 已完成

**前置**: DL-064a/b（clang 前端 + driver 一条龙 freestanding 通）。转 musl 里程碑，但需先定 **syscall/console/exit 层**——这是 musl 落地的关键设计决策。

---

## 完成区

**状态**：已完成
**产出**：`docs/reviews/musl-recon-2026-07.md`
**调研结论**：

1. **wiki AEE**（DADAO-11-AEE 0.9.2）：纯应用执行环境，无 ecall/syscall 定义
2. **wiki SEE**（DADAO-12-SEE 0.7.1）：定义了完整 trap→CFXTRAP 机制（`trap` 指令 + cfx monitor model），cfx_uart（console）、cfx_power（exit/shutdown）均已定义
3. **syscall 推荐**：SEE `trap→CFXTRAP` + cfx_smon handler（wiki 已有标准机制，不需额外异常/M1 支持）
4. **libc 推荐**：第一阶段 picolibc（3 stub 打通 printf+malloc）→ 第二阶段 musl（真 kernel 后）
5. **wiki 远端更新**（8 commits ahead）：trap→CFXTRAP、UART cfx、power cfx 均保留，变更不影响 syscall 决策

**wiki 差异**：本地锁定 `13a414d` vs 远端 `9f378f4`（8 commits，见报告 §1.3）。trap/CFXTRAP/uart/power 均保留。`phymem→pmem` 纯重命名。

**遗留**：syscall ABI 细节（寄存器分配）需 ADR 确定；trap cfx 序号约定需设计文档

---

## 背景 / 为什么先调研
真 C（printf/malloc/string.h/llvm-test-suite）需 libc，但落地前有个**必须先定的设计决策**：DADAO 程序怎么做 `write()`/`exit()`/`brk()`？
- 现测试机（ADR-0004）**只有 halt-exit MMIO**（0x10000000 写退出码），**无 console/write、无 syscall 机制**。
- **M1 排除了异常/RF**（spec §7）——ecall/trap 式 syscall 机制可能不可用。
- wiki 有 **DADAO-11-AEE（应用程序运行环境）+ SEE（Supervisor EE）** 概念，需查清它们定义了什么。

**这是纯调研任务**：只读 wiki/参考项目，产出 recon 报告，**不改代码、不下结论式实现**。架构师据报告写 ADR 定方案（仿 SL-001a→ADR-0011 的 Sail 流程）。

## 调研清单（逐项回答，带出处）

### 1. wiki AEE/SEE 定义了什么
- `~/DADAO-wiki/`（锁定 commit，只读）查 **DADAO-11-AEE（应用程序运行环境）**：定义了 syscall/环境调用机制吗？有 ecall 类指令吗？syscall ABI（哪个寄存器传号/参数/返回）？
- **SEE（Supervisor EE）**：定义了什么？是否 RISC-V SBI 式的 supervisor 接口？M1 是否可用（异常机制排除的影响）。
- 章节号引用（§N），不用行号。**有则据实、无则明确写"wiki 未定义"**。

### 2. syscall/console/exit 层选项（M1 无异常）——各自可行性/代价
- **(a) 半主机（semihosting）**：QEMU/gem5 拦特定指令/MMIO 做宿主 I/O（write→宿主 stdout、exit）。查 QEMU/gem5 现有 semihosting 机制（ARM/RISC-V semihosting），DADAO 加一个要多少改动（QEMU target + gem5）。**双后端都要支持**。
- **(b) MMIO console + exit（扩测试机）**：加一个 console-write MMIO 端口（仿现有 exit 端口），libc `write()`→MMIO store 字节。最贴现有 halt-exit 风格、不需异常/trap。查 QEMU/gem5 加一个 console MMIO 的量。
- **(c) 最小 SEE/SBI**：实现小 supervisor（RISC-V OpenSBI 式）处理 ecall syscall——**需异常/trap 机制（M1 排除）**，重。
- 每项：需要改 QEMU/gem5 什么、是否需 M1 缺的异常机制、双后端一致性代价、对未来真 OS 的延展性。

### 3. libc 选型：musl vs picolibc/newlib
- **musl**：Linux-syscall 导向（需 kernel 或 syscall 模拟）；静态移植 DADAO 需哪些 arch 文件（syscall.h/arch stubs/crt1）；`printf("hi")`+`malloc` 最小 syscall 集（write/exit/brk 或 mmap）。
- **picolibc / newlib**：freestanding/嵌入式导向，retarget 靠几个 stub（`_write`/`_sbrk`/`_exit`），**semihosting 友好、比 musl 轻**。查它们移植到新 arch 的成本。
- **给出对比 + 倾向**：哪个对"先跑通 printf/malloc + llvm-test-suite SingleSource"最省，哪个对"未来真 kernel/musl"最正统。用户提"musl"，但若 picolibc 明显更省作为过渡也要说清。

### 4. 移植/构建路线（不实现，只调研成本）
- 选定 libc + syscall 层后，端到端路线：libc 源 → clang -target dadao 编译成 libc.a → driver 链（crt1 + libc + user）→ 半主机/MMIO 让 printf 输出、exit 退出码 → QEMU+gem5 验证。
- crt1（`_start`→`__libc_start_main`→`main`）vs 现有 crt0（裸 `call main; halt`）的差异。
- 参考：RISC-V bare-metal + picolibc/newlib semihosting 的最小 hello-world 工具链。

## 参考指针
- `~/DADAO-wiki/`（AEE/SEE，只读，§引用）；`contracts/exception/`（deferred）、`contracts/abi/`；`docs/adr/0004-test-machine.md`（halt-exit MMIO、无 console）；spec §7（RF/异常 M1 排除）
- QEMU/gem5 semihosting：`.work/source/qemu`（ARM/RISCV semihosting）、gem5 semihosting；现有 exit-port MMIO（QEMU target/dadao、gem5 dadao_se）
- picolibc（github.com/picolibc/picolibc，semihosting retarget）、newlib、musl（arch 移植层）
- 流程范式：SL-001a（Sail 调研）→ ADR-0011（charter）；本任务是 musl 版的 SL-001a

## 产出
- **recon 报告** `docs/reviews/musl-recon-2026-07.md`（仿 `sail-recon-2026-07.md` 若有）：逐项回答 1-4 + **明确推荐**（syscall 层选哪个、libc 选哪个、最小路线），带 wiki §出处 + QEMU/gem5 改动估算。
- 架构师据此写 **ADR（musl/libc charter）** 定方案，再拆实现任务。

—— **纯调研，不改代码**。§引用不用行号；wiki 未定义的明确标注不猜。

---

## 审阅记录（subagent）

**判决**: ✅ **Accepted**（通过）

### 重跑记录

| # | 核验项 | 命令/来源 | 结果 |
|---|--------|-----------|------|
| 1 | wiki AEE 无 syscall | 通读 `DADAO-11-AEE-应用程序运行环境.md`（218 行） | ✅ 确认：仅含数据表示/存储/寄存器/RAS/浮点状态，无 ecall/trap/syscall |
| 2 | wiki SEE 有 trap→CFXTRAP | `grep "CFXTRAP"` 在锁定版 SEE 命中 cfx_umon 异常表 `1<<0 = CFXTRAP`；§5 伪码 `instruction == TRAP → cause <= CFXTRAP` | ✅ 确认 |
| 3 | wiki SEE 有 cfx_uart | 锁定版 cfx_uart 专有寄存器表（cg8/cg32-cg63），cfxcode=62 | ✅ 确认 |
| 4 | wiki SEE 有 cfx_power | 锁定版 cfx_power，bit0=关机/POWEROFF，cfxcode=63 | ✅ 确认 |
| 5 | syscall ABI 未定义 | 锁定版 SEE 全文无 syscall number 寄存器/参数规范 | ✅ 确认 |
| 6 | wiki 远端仍有 CFXTRAP | `git show 9f378f4:DADAO-12-SEE-... \| grep CFXTRAP` → 所有 cfx 异常表均保留 `1<<0 = CFXTRAP` | ✅ 确认 |
| 7 | wiki 远端仍有 uart + power | `git show 9f378f4:... \| grep "cfx_uart\|cfx_power"` → 均保留 | ✅ 确认 |
| 8 | 远端 commits 数量 | `git log --oneline 13a414d..9f378f4` 返回 8 条 | ✅ 确认（与报告一致） |
| 9 | cfx_smon 用户态 syscall 支持 | 锁定版 SEE 第 289 行：`硬件应至少支持 cfx_umon_user_* … 或 cfx_smon_user_*` | ✅ 确认 |

### 约束核验（逐条）

| 约束 | 来源 | 状态 |
|------|------|------|
| §引用不用行号 | 任务文件第 42/70 行 | ✅ PASS — 全报告无行号引用，使用 SEE §5、SEE §cfx_uart 等 |
| wiki 未定义明确标注 | 任务文件第 42/70 行 | ✅ PASS — syscall ABI 标注 "wiki 未定义" |
| 纯调研，不改代码 | 任务文件第 70 行 | ✅ PASS — git diff 确认无代码变更 |
| 逐项回答 1-4 + 推荐 | 产出要求第 67 行 | ✅ PASS — §1-§4 分别对应四个问题，§5 给出推荐总结 |
| 带 wiki §出处 | 产出要求第 67 行 | ✅ PASS |
| QEMU/gem5 改动估算 | 产出要求第 67 行 | ✅ PASS — §2.2 给出 QEMU ~270 行估算 |

### 逐题核验

**Q1（AEE/SEE）**: ✅ 报告 §1.1 正确判定 AEE 无 syscall；§1.2 正确识别 SEE trap/CFXTRAP/cfx_uart/cfx_power；syscall ABI 正确标为 "wiki 未定义"；M1 排除 RF 的解读正确（trap 不依赖浮点寄存器，M1 可用）。

**Q2（syscall 选项）**: ✅ §2 覆盖三种方案（semihosting/MMIO/SEE trap），有双后端对比表，推荐理由充分且在 SEE wiki 中有据可查。唯一微瑕：§2.2 推荐 `trap cfx_smon` 但未讨论 cfx_umon 替代路由——不过这属于设计选择细节，不影响调研报告完整性，可在 ADR 中补。

**Q3（libc 选型）**: ✅ §3 覆盖 musl/picolibc/newlib 三维对比，推荐分阶段（picolibc → musl）与 musl 为长期目标一致，有理有据。

**Q4（移植路线）**: ✅ §4 给出 picolibc 阶段 1 + musl 阶段 2 路线，包含 ABI 草案（rd16/rd17-22/rd31）、构建命令、文件清单。

**Q5（wiki 远端差异）**: ✅ §1.3 列表覆盖 5 项关键变更 + 确认不变项，表头标注 "仅列影响 syscall/libc 决策的变更"，合理解释了为何只列 5/8 commits。

### 备注（非阻塞）

- §1.3 表格将 `defdd96` 拆为两行（§5 重构 + 中断模型前移），属同一 commit 的两个变更，合理但建议在后续 ADR 查阅时确认远端 §5 异常进入流程伪代码是否与锁定版完全等价。
- 推荐方案依赖 `trap cfx_smon` 从 user mode 触发 syscall——这一机制已由 SEE 第 289 行 "硬件应至少支持 cfx_umon_user_* 或 cfx_smon_user_*" 支撑，wiki 证据充足。
- 路线 §4.1 提到 "SYS_exit (93)"——93 是 RISC-V/Linux exit syscall 编号，DADAO 最终 syscall table 需 ADR 定义，报告未声称 wiki 定义了此编号，无问题。
