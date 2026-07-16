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

#### D5.1：为什么 tinystdio（stdio 表面最小化）+ 实施发现（ML-003a de-risk，2026-07-13）

**为什么 tinystdio 不用经典 newlib stdio**（也是"为什么 picolibc 先于 musl"的同一理由——**小 stdio 表面先行**）：

| 维度 | tinystdio | newlib 经典 stdio / musl stdio |
|------|-----------|------------------------------|
| printf 依赖 | 直接格式化到 putc 钩子，**不需 malloc** | 完整 FILE* 缓冲，**需 malloc + `_reent`/`_impure_ptr` + `__sinit`** |
| syscall stub | 基本只 `_write`（字符输出钩子） | 全套 POSIX：`_write/_read/_lseek/_fstat/_isatty/_close`+`_sbrk` |
| 体积/init | KB 级、stdout 是 putc 指针薄壳 | 大一圈、stdout 走重入机制重 init |

`printf("hi")` 在 tinystdio 只需 `_write` 一个 syscall——这正是阶段 1"3 stub 打通 printf"成立的前提。用 newlib/musl 的重 stdio 则拖进 malloc+reent+全套 POSIX stub，"最小路径"不成立。**picolibc = tinystdio**（本版 1.8.11 已删 `newlib-tinystdio` 开关，tinystdio 为唯一 stdio 引擎；`libc/tinystdio/`=格式化核心、`libc/stdio/`=公共 API 包装+POSIX 层，**非另一套 stdio**）。

**实施发现（ML-003a，纠正）**：
- picolibc 为 novel dadao target 用 clang 构建时，**卡的墙 80% 是 DADAO 后端 codegen 缺口**（mem* intrinsic 展开、VASTART/varargs、跳转表/常量池/多个 Expand、间接调用），**非 picolibc/libc 特有**——换 musl 一个不少且更多。**这验证了 D5「小 libc 先趟后端」的判断**：picolibc 廉价逮出并修了这批后端 bug，给 musl 交 de-risked 后端。
- 链接 `undefined stdout/vfprintf` **是 picolibc 控制台配置缺口**（`stdout` 在 `posixiob_stdout.c`，受 `posix-console` 等选项门控），**非 libc 选型问题**——修法=给 tinystdio stdout 走最小输出（`FDEV_SETUP_STREAM` 绑 `_write`）或按需开 console 选项。
- **musl 现在上是早的**：syscall 面不够（malloc 要 mmap、`__init_libc` 要 TLS/线程指针，现 SEE 只有 write/exit/brk）+ arch 移植大（`arch/dadao/` ~15-20 文件 vs picolibc 1 machine dir+3 stub）+ 后端墙相同还更多。musl 仍是终点，时机在"kernel + SEE syscall 面扩起来"之后。

#### D5.2：musl 阶段2 时机更正（ML-006a 调研，2026-07-16）——不必等真 kernel

D5.1 当时判断"musl 时机在 kernel 之后"，是因为设想 TLS/syscall 面缺口很大。**ML-006a 深化调研（`docs/reviews/musl-recon-2026-07-16.md`）推翻了这个悲观预期**：

- **TLS 不卡**：`contracts/abi/spec.md` §1.2 已定义 `rb4=rbtp`，LLVM 后端已 reserve RB4；musl 源码本体零处使用编译器 `__thread` 关键字（全靠 `__pthread_self()` 从 TP 寄存器算出），意味着"跑通 musl 本体"完全不需要 TLS 重定位类型或真 kernel 提供的线程/信号机制，只需要给用户态写 rb4 补 2-3 个汇编 stub。
- **syscall 面缺口比预想小**：静态单线程程序只缺 `mmap`/`munmap`（P0，mallocng 硬依赖）+ `mprotect`（P1）三个 handler，不需要 `clone`/`futex`/`set_tid_address` 等线程/信号类 syscall——这些在 ADR-0012 D5 终极目标（gcc-c-torture 里绝大多数用例单线程不 fork）驱动下可以继续延后。
- **推论：musl 阶段2 的"静态单线程"子集不需要等真 kernel**，触发条件改为"驱动力=ADR-0012 D5 全量测试目标"而非"kernel 完成后自然轮到"。多线程/信号/`__thread`/动态链接（真正需要 kernel 级机制的部分）仍按原计划延后。
- 已有具体分阶段任务清单（§ML-006a 报告 §5-7）：阶段A（syscall handler 补齐，2-3 任务，低风险）→阶段B（musl arch 骨架+E2E，5-7 任务，中风险，crt0 auxv 合成是唯一真正的新工作）→阶段C（多线程/信号/`__thread`/动态链接，明确延后）。

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
