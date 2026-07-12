# ADR-0014: libc / syscall charter — SEE trap-based syscall + picolibc 先行

**状态**：Accepted（2026-07-12）
**日期**：2026-07-12
**关联**：ML-001a（recon 报告 `docs/reviews/musl-recon-2026-07.md`）、ADR-0004（测试机 exit MMIO）、ADR-0009（四方验证链）、ADR-0012（测试分层 T0-T3）、ADR-0013（wiki 升级流程）、WU-001a（pin→9f378f4）

---

## 背景

DL-064a/b 后 clang 一条龙 freestanding 通（`clang hello.c` → 双后端 halt 退出码）。真 C（printf/malloc/string.h/llvm-test-suite）需 libc，落地前必须先定 **syscall/console/exit 层**。ML-001a recon（Gemini，架构师验）查清：
- **wiki AEE**（DADAO-11-AEE）无 syscall/ecall。
- **wiki SEE**（DADAO-12-SEE §5）**已定义完整 `trap`→CFXTRAP 机制**：`trap cfxcode` 指令陷入目标核芯功能扩展；`cfx_smon`（supervisor monitor）作 User→S-mode syscall 入口；`cfx_uart`（cfxcode=62）console；`cfx_power`（cfxcode=63）POWEROFF/RESET。
- **syscall 软件 ABI（寄存器约定）wiki 未定义** → 本 ADR 定。
- M1（spec §7）排除的是 **RF 浮点异常**，**不排除 trap/异常机制**——trap 与 RF 无关，M1 可用。

## 决策

### D1：syscall 机制 = SEE `trap cfx_smon`（spec-first，非半主机/MMIO-hack）
用户程序 `trap cfx_smon` → CFXTRAP → cfx_smon responder 处理 syscall。**理由**：
- **spec-first**：用 SEE §5 已定义的 trap/cfx 基础设施，不自造机制（符合项目"权威 spec→实现"定位）。
- **未来零迁移**：真 kernel/musl 复用同一 SEE trap→cfx 接口；半主机/MMIO-console 是 hack，将来推倒重来。
- 拒绝的替代：(a) 半主机（无现成 DADAO semihosting，双后端各造，且非 spec）、(b) MMIO console 端口（最小但是 test-machine hack、非 ABI、未来重建）。

### D2：syscall 软件 ABI（**本 ADR 定，wiki 未定义**）
| 项 | 约定 |
|----|------|
| syscall number | `rd16` |
| 参数 arg0..arg5 | `rd17` `rd18` `rd19` `rd20` `rd21` `rd22` |
| 返回值 | `rd31` |
| 陷入指令 | `trap cfx_smon` |
| syscall 编号 | **Linux asm-generic**（`write=64` `exit=93` `exit_group=94` `brk=214` `read=63` …）——为未来 musl 直接映射其 asm-generic syscall table |

> 这是**我们的软件 ABI 约定**（类比 ADR-0004 的 exit 码——数字是我们定的、机制来自 spec）。选 asm-generic 编号是为 musl 阶段零改动接入。

### D3：console/exit/heap 的 cfx 落地
- `write(fd,buf,len)` → cfx_smon handler → **cfx_uart** 写字节（MVP：fd=1/2 → 宿主 stdout/stderr）。
- `exit(code)`/`exit_group` → **cfx_power POWEROFF**，退出码 = code（沿用 ADR-0004 退出码协议；与现 halt-exit 并存，libc 程序走 cfx_power）。
- `brk`/`sbrk` → 简单堆（MVP：cfx_smon 维护一个 program-break，向 dadao.ld 预留的 heap 区推进）。

### D4：cfx_smon responder — MVP 模拟器侧，未来真 SEE monitor firmware
- **MVP**：QEMU/gem5 在 `trap cfx_smon`→CFXTRAP 时，模拟器侧 responder 读 ABI 寄存器、经 cfx_uart/cfx_power 设备做 I/O（类比现 exit-port MMIO 是模拟器设备）。**双后端都实现**（syscall 层进入 dual-backend 一致性验证）。
- **实现 `trap`→CFXTRAP 进入机制**：QEMU/gem5 需实现 `trap` 指令 + CFXTRAP 异常进入（M1 曾 defer 异常，此处按需实现 syscall 所需最小子集）。**参最新 pin 9f378f4 的 SEE §5**（WU-001a 记的 B 桶 `wiki-9f378f4-sbi-see-deferred-delta`：§5 重构/中断模型前移/FPEXCP——SEE-trap 实现时吸收相关部分）。
- **未来**：换成 guest 侧真 SEE monitor firmware（OpenSBI 式）+ 真 cfx 设备（做完整 SEE/kernel 时）。

### D5：libc = picolibc 先行 → musl 后续（分阶段）
- **阶段 1（MVP：printf + malloc + llvm-test-suite SingleSource）= picolibc**：最小路径——3 stub（`_write`→SYS_write、`_exit`→SYS_exit、`_sbrk`→SYS_brk）+ tinystdio（printf 不依赖 malloc）。`clang -target dadao` 编 picolibc → `-lpicolibc` 链。crt 用现有 `crt0.s`（`_start`→`main`，picolibc 风格）。
- **阶段 2（长期：真 kernel）= musl**：SEE/SBI handler 完善（mmap/brk/clone…）后切 musl（行业标准、真 OS 必选，arch 移植层 `arch/dadao/`）。**用户里程碑仍是 musl**；picolibc 是打通 printf/malloc 的过渡。

### D6：验证 = dual-backend + 分层（接 ADR-0012）
- syscall 层双后端一致：同一 `trap cfx_smon` 程序，QEMU 与 gem5 **console 输出一致 + 退出码一致**（syscall 层进入 T2 dual-backend gate）。
- 分片：先 **syscall 机制**（手写 asm `trap`-write "hi"+`trap`-exit → 双后端）→ 再 **picolibc port**（真 `printf("hello")` + malloc）→ 再 **llvm-test-suite SingleSource**（ADR-0012 T3）。

## 后果

**正面**：syscall 走 spec 定义的 SEE trap→cfx，未来真 kernel 零迁移；ABI 明确（asm-generic 编号为 musl 铺路）；picolibc 最短路径打通 printf/malloc；双后端一致性延伸到 syscall 层。

**负面 / 限制**：实现 `trap`→CFXTRAP 进入机制是 M1 曾 defer 的异常机制的一部分（双后端各实现最小子集）——比 MMIO-hack 大，但是正路。picolibc→musl 两阶段意味着 musl 是后续里程碑非当下。SEE B 桶 delta（9f378f4）需在 SEE-trap 实现时吸收。

## 参考
- ML-001a `docs/reviews/musl-recon-2026-07.md`（SEE §5 trap/cfx_uart/cfx_power、libc 三维对比、ABI 草案）
- wiki（pin 9f378f4）DADAO-12-SEE §5（trap→CFXTRAP）、§cfx_uart（62）、§cfx_power（63）；WU-001a issues `wiki-9f378f4-sbi-see-deferred-delta`
- ADR-0004（exit 码协议）；picolibc（github.com/picolibc/picolibc）；Linux asm-generic unistd（syscall 编号）
- 首个实现任务：ML-002a（syscall 层 trap cfx_smon + cfx_uart/cfx_power，双后端 + asm 测试）
