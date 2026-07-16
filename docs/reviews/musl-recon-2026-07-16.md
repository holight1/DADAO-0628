# musl 移植路线图调研（ML-006a，ML-001a 后续深化）

**日期**：2026-07-16 · **任务**：ML-006a
**前置**：ADR-0014（libc/syscall charter）、ADR-0012 D5（终极目标=gcc-c-torture 全量通过，判定需要 musl）、ML-001a（`docs/reviews/musl-recon-2026-07.md`，早期调研）
**性质**：纯调研/规划，不含代码实现，不改 DADAO-0628 任何源码

---

## 0. 结论先行

| 问题 | 结论 |
|------|------|
| 旧 musl 移植可参考什么 | `~/toolchain/musl/arch/dadao/`（~24 文件）+ 20 条踩坑记录（`sysmode-debug-lessons.md`），**只取结论，ABI 数字已知不同，不能抄寄存器号/trap 编码** |
| 当前 syscall 面够 musl 用吗 | **不够**——只有 write(64)/exit(93)/exit_group(94)/brk(214)，musl mallocng **硬依赖 mmap**（当前无），`__init_libc` 静态单线程路径下可绕开 poll/clone/futex |
| TLS 卡不卡 | **不卡，且好消息比预期多**——DADAO-0628 ABI contract **已经**把 `rb4=rbtp`（Thread Pointer）定义好（与旧工具链一致），LLVM 后端已 reserve RB4；musl 自身源码 **零处**使用编译器 `__thread` 关键字（全靠 `__pthread_self()` 从 TP 寄存器算出），意味着"跑通 musl 本体"不需要 TLS 重定位类型，只需要一条能写 rb4 的用户态指令（已有 ISA 能力，无需新指令） |
| 分阶段是否可行 | 可行：**静态单线程程序**（无 `__thread`/无 pthread_create/无 signal）是天然的第一站，且不需要 mmap 之外几乎任何新 syscall |
| ABI（ADR-0014 D2）要不要改 | **不用改寄存器约定，需要扩表**——现有 4 个 syscall 号沿用；需要按 asm-generic 编号新增 mmap/munmap/mprotect 等 handler，不改变"rd16=号/rd17-22=参数/rd31=返回/`trap cfx_smon`"这套已定 ABI |
| 量级 | **中等**——比 picolibc 阶段（3 stub）明显大，但比"从零造 OS"小；粗估 **8-12 个任务**分 3 个阶段（见 §5、§6） |

---

## 1. 旧 musl 移植调研：结构、ABI、坑（结论/坑，不抄代码）

### 1.1 `~/toolchain/musl/arch/dadao/` 目录结构（旧工具链，供参照量级，不抄内容）

```
arch/dadao/
  atomic_arch.h        # 用 __sync builtin，非硬件 LL/SC（见坑 B03）
  bits/*.h(.in)         # alltypes/errno/fcntl/mman/signal/stat/... 共 ~18 个头
  crt_arch.h, crt_arch.s # _start，v5 ABI: 指针参数进 RB bank
  kstat.h
  pthread_arch.h        # TLS_ABOVE_TP + rb4 作线程指针
  reloc.h                # R_DADAO_{NONE,ABS,JUMP,32} 四种 + CRTJMP
  syscall_arch.h         # __syscall0..6，NR=rd15，参数 rd16-21，返回 rd31
```
共 **24 个文件**（`find | wc -l`），量级与 ML-001a 早期估算的"~10-20 arch 文件"一致。

### 1.2 旧 ABI 与当前 ADR-0014 D2 的差异（重要：不是同一套，不能照抄寄存器号）

| 项 | 旧工具链（`~/toolchain/musl`） | DADAO-0628（ADR-0014 D2） |
|----|-------------------------------|---------------------------|
| syscall number 寄存器 | `rd15` | `rd16` |
| 参数寄存器 | `rd16`-`rd21`（6 个） | `rd17`-`rd22`（6 个） |
| 返回值 | `rd31` | `rd31`（一致） |
| 陷入方式 | 裸 `.4byte 0x76000000`（无 cfxcode 参数，直接固定编码） | `trap cfx_smon`（cfxcode=2，SEE spec 定义的 CFXTRAP 机制） |
| syscall 号来源 | Linux asm-generic（write=64/exit=93/brk=214，与新 ABI 一致） | 同一套 asm-generic 编号（未变） |

**结论**：syscall **号表**两代一致（都用 asm-generic），但**寄存器分配整体右移一位** + **陷入机制从裸编码变成 spec 定义的 cfx 机制**。这是 DADAO-0628 greenfield 重建的正常结果（ADR-0014 D1 已决定不沿用旧 v5 的裸编码，改走 SEE spec 的 trap→CFXTRAP），意味着 `syscall_arch.h`/`crt_arch.s` 等**必须按当前 ABI 重写，不能直接复制旧文件**（连 `__syscall1` 里的寄存器号都要全部改一位）。

### 1.3 旧工具链 20 条踩坑（`sysmode-debug-lessons.md`）中与 musl 直接相关的

| 坑号 | 内容 | 对 DADAO-0628 musl 移植的启示 |
|------|------|------------------------------|
| **B18** | musl `__set_thread_area` 曾经"空实现或写错寄存器"，导致所有用 TLS 的用户态程序（pthread/errno）crash；根因是没把 rb4(rbtp) 真正写上 | DADAO-0628 写 `__set_thread_area.s`/`get_tp.s` 时必须**用真实汇编验证 rb4 确实被写入并能读回**（不能只凭"编译通过"判定完成——这也是本项目一贯的"ground-truth 复跑"要求） |
| **B06/B07** | LLVM 集成汇编器（IAS）的 AsmParser 与 InstPrinter 不对称：`ret` 带操作数、`ra2rd`/`rd2ra` 助记符在旧后端 IAS 里都不被接受，只能退化成 `.4byte` 裸编码写汇编 | DADAO-0628 的 musl arch 汇编文件（setjmp/longjmp/clone/get_tp 等）**先用真实 `clang -c` 试跑每条要用到的助记符**，别假设 InstPrinter 打印的格式就是 AsmParser 能吃的格式；如遇到同类不对称，是 CodeGen/MC 层任务，不是 musl 任务 |
| **B08** | kernel/musl 内联汇编里的 `+Rb`/`+Rd`（RB/RD bank 专用大写约束前缀）编译器一开始不认，需要在 `ISelLowering.cpp`/`Dadao.h` 补注册 | DADAO-0628 若 musl 的 C 代码里用内联汇编约束访问 RB bank 寄存器（比如某些 atomic 操作），要提前确认后端约束字符表是否已覆盖 RB bank；这是当前 DADAO-0628 backend 的一个待验证点 |
| **B09** | LL/SC（`lro`/`sco`）8 个变体最初完全没进 MC 层（AsmParser+Emitter），kernel atomic 编译期报 unknown instruction | musl 的 atomic_arch.h 若要用硬件 LL/SC 而非 `__sync` builtin，需要先确认 DADAO-0628 MC 层是否已支持对应指令；**旧工具链最终选择绕过 LL/SC、全用 `__sync_*` builtin**（`atomic_arch.h` 见 §1.1），这是一个可直接复用的"结论"（不是代码）：DADAO-0628 musl 移植的 `atomic_arch.h` 大概率也应该先走 `__sync` builtin 路线，不要一上手就赌硬件 LL/SC |
| **B10** | clang `--target=dadao-linux-musl` 能识别 triple 字符串，但 driver 不知道路由到哪个 linker/assembler——只在 `Triple.h` 加枚举不够，还要在 `Gnu.cpp getLDMOption`/`Linux.cpp` 里显式注册 | DADAO-0628 目前 clang driver（DL-064b）是 freestanding 路由（无 `-linux-musl` OS 后缀），一旦要支持 `dadao-unknown-linux-musl` 三元组，同样要过"triple 枚举 + driver 路由 + 链接器路径"三步，不能只加字符串 |
| **L1**（busybox） | 曾假设 ELF 加载 VA=0x400000（"标准"值），实测 busybox musl 静态链接默认起始 VA=0x10000，设计因此推倒重来 | 提醒：**任何"假设某个地址/布局"的设计前，先 `readelf -l` 实测**，不要凭经验；DADAO-0628 现有 `dadao.ld` 固定 `.text` 于 `0x80000000`（ADR-0004 测试机约定），musl 静态链接到该基址不冲突，但真正验证要等第一个 musl 二进制链出来后跑 `readelf -l` 核对 |

### 1.4 有意不继承的旧设计

- 旧 v5 ABI 是"扁平"寄存器传参（`rd16` 直接传指针），DADAO-0628 是 RD/RB 分 bank ABI（指针走 RB bank，DL-050a 起）。**musl 的所有手写汇编 stub（`crt_arch.s`/`get_tp.s`/`__set_thread_area.s`/`setjmp.s`/`longjmp.s`/`clone.s`）都要按新 ABI 从零写**，旧文件仅供理解"这一类 stub 大概要做什么事"，寄存器分配和调用约定不可复用。
- 旧 syscall 陷入是裸指令编码（不经过 spec 定义的异常机制），DADAO-0628 走 SEE `trap→CFXTRAP`（ADR-0014 D1，spec-first）；这是架构决策层面的既定差异，调研到此为止不重复讨论。

---

## 2. DADAO-0628 当前 syscall 面缺口清单（具体依据）

### 2.1 现状（逐行核对源码）

- `tests/scripts/pico_stubs.s`：仅 `_write`（sysno=64）、`_exit`（sysno=93）、`_sbrk`（sysno=214，get/set program break）三个 picolibc stub。
- QEMU 侧 responder：`components/qemu/patches/0013-dadao-trap-syscall.patch`（`target/dadao/cpu.c` `dadao_cpu_do_interrupt` 的 `EXCP_CFXTRAP` 分支）：`switch(sysno)` 只有 `case 64/93/94/214`，**default 返回 `-ENOSYS`（-38）**。
- gem5 侧 responder：`components/gem5/patches/0010-dadao-trap-syscall.patch`（`src/arch/dadao/decoder.cc` 的 `TrapInst::execute`）：**逐字对应同一张表**（64/93/94/214/default=-38），双后端一致。
- 结论：**当前实现的 syscall 集合 = {write, exit, exit_group, brk}**，其余任何 syscall 号一律 -ENOSYS。

### 2.2 musl 静态单线程启动路径实际会碰到的 syscall（引用 musl 1.2.6 源码，`~/toolchain/musl`）

| 阶段 | 会调用的 syscall | 依据（文件:行为） | DADAO-0628 现状 |
|------|-----------------|-------------------|-----------------|
| `_start_c` → `__libc_start_main` → `__init_libc` | **无强制 syscall**（若 `aux[AT_UID]==aux[AT_EUID] && aux[AT_GID]==aux[AT_EGID] && !aux[AT_SECURE]` 提前 return） | `src/env/__libc_start_main.c` L38-52：只有这个条件不成立时才会走 `SYS_poll`/`SYS_ppoll` + `open("/dev/null")` 检查 fd 0/1/2 | **可绕开**——只要 crt 合成的 auxv 里 `AT_UID==AT_EUID==0`、`AT_GID==AT_EGID==0`、`AT_SECURE=0`（或干脆不填=默认 0），就不会触发 poll/open |
| `__init_tls`（`__init_libc` 内部调用） | 无 syscall（纯内存操作，从 `_DYNAMIC`/`aux` 计算 TLS 镜像并 `memcpy`） | `src/env/__init_tls.c` | 无缺口 |
| `__init_tp(__copy_tls(mem))` | **无 syscall**——`__set_thread_area` 在大多数架构（包括旧 dadao port）是**纯寄存器写指令**，不是系统调用 | `arch/dadao/pthread_arch.h` + 旧 `__set_thread_area.s`：直接 `setrb rb4, arg`，返回 0；riscv64/arm64 等主流架构同理 | 无 syscall 缺口，但需要**新写**一个按当前 ABI 的汇编 stub（见 §3） |
| `malloc()`（mallocng，musl 1.2.x 默认分配器） | **`mmap(NULL, n*pagesize, PROT_READ\|PROT_WRITE, MAP_PRIVATE\|MAP_ANON, -1, 0)`** —— 硬依赖，不会退化到 brk | `src/malloc/mallocng/malloc.c` L82/L249/L310（`mmap(...)` 直接调用，无 brk fallback 路径） | **缺口：mmap 完全未实现**（sysno=222，任何 mmap 调用当前直接 -ENOSYS） |
| 有 guard page 的大块分配 | `mmap(..., PROT_NONE, ...)` 建 guard，之后可能 `mprotect`/`munmap` 收缩 | `src/malloc/mallocng/malloc.c` L72-82 | **缺口：munmap（215）、mprotect（226）均未实现** |
| `printf`/`stdio` 首次使用 | 已知只需 `write`（现有） | `src/stdio/*` | 无缺口 |
| 程序正常退出 | `exit`/`exit_group`（现有） | — | 无缺口 |
| **仅当程序用到** `pthread_create`/`raise`/`signal`/`alarm` 等 | `clone`(220)、`set_tid_address`(96)、`rt_sigprocmask`(135)、`rt_sigaction`(134)、`futex`(98)、`set_robust_list`(99)、`tgkill`(131)、`getpid`(172)/`gettid`(178) | `src/thread/pthread_create.c` L161/202/206/258；`src/thread/dadao`（旧）无 clone.s（说明旧工具链当时可能也没做完整 clone，只做了 setjmp/get_tp/__set_thread_area 三个） | **缺口，但阶段1可延后**——gcc-c-torture 的绝大多数用例是单线程、不 fork、不发信号 |
| 环境/文件类调用（部分 C 库函数间接触发） | `read`(63)、`close`(57)、`fstat`/`newfstatat`(80/79)、`ioctl`(29，isatty 用）、`getcwd`(17) 等 | 各自 `src/unistd`/`src/stdio` | **缺口，但阶段1若测试只做纯计算+`printf`退出，基本不触发** |

### 2.3 缺口清单（按优先级）

**P0（阻塞 musl malloc，几乎所有非 trivial C 程序都会触发）**：
- `mmap`（222）
- `munmap`（215）

**P1（mallocng guard page / realloc 路径会用到，规模变大后必现）**：
- `mprotect`（226）

**P2（阶段1若程序含文件/环境交互、`errno` 相关路径会触发，非阻塞但迟早要补）**：
- `read`（63）、`close`（57）、`fstat`/`newfstatat`（80/79）、`ioctl`（29）、`writev`（66）
- `getrandom`（278，`__init_ssp` 栈保护熵源；缺失时退化路径需确认不 crash）

**P3（多线程/信号，明确延后到"阶段2 之后"）**：
- `clone`（220）、`set_tid_address`（96）、`futex`（98）、`set_robust_list`（99）
- `rt_sigaction`（134）、`rt_sigprocmask`（135）、`tgkill`（131）、`sigaltstack`（132）
- `getpid`（172）、`gettid`（178）

**当前 `brk`（214）实现的一个既有小问题**（顺带记录，非本任务范围内修）：`set` 分支把内部 `brk_base` 设成 `arg0+0x100000`（留一段 slack）而不是精确等于 `arg0`，之后 `brk(0)` 查询会返回 `arg0+0x100000` 而非上次设置值，与真实 Linux `brk` 语义不完全一致。**但 musl mallocng 本身不调用 brk**（只有程序直接调用 `sbrk()`/`brk()` 这类遗留 legacy 接口才会触发），所以这不是 musl 移植的阻塞项，只是一个已知的实现细节偏差，供未来处理 legacy `sbrk()` 测试用例时参考。

---

## 3. TLS / 线程指针现状 vs DADAO M1 spec

### 3.1 好消息：ABI contract 已经定义了 rbtp

`contracts/abi/spec.md` §1.2（RB — Base Registers）：

```
| rb4 | rbtp | Thread pointer | — |
```

与旧工具链的 `pthread_arch.h`（"DADAO uses RB4 as the thread pointer (rbtp)"）**完全一致**——这不是巧合复用，是当前 ABI 契约本来就已经把这个位置留给了 TP。

`llvm/lib/Target/DADAO/DADAORegisterInfo.cpp` 的 `getReservedRegs()` 已经 `Reserved.set(DADAO::RB4)`（连同 rb0-rb3/rb5-rb7 一起保留不分配），`DADAOInstrInfo.cpp` 里也有注释显式提到 "rb3/rb4=gp/tp"。**后端已经在按这个 ABI 角色对待 rb4，只是还没有任何代码去读/写它**（无 `__builtin_thread_pointer`、无 TLS 访问 codegen、无汇编 stub）。

### 3.2 写 rb4 不需要新指令

DADAO ISA 的 RB-bank 寄存器写指令（`rd2rb`/`rb2rb`，`contracts/isa/spec.md` §4.7 RB Block Copy）**唯一的合法性限制是目的寄存器不能是 `rb0`**（`rbha ≠ rb0` / `rbhb ≠ rb0`，ILLI 否则），rb4 不在任何额外禁止名单里。也就是说：**用户态程序本来就能用一条普通指令把任意值写进 rb4**，不需要特权模式、不需要新的 trap/cfx 机制。旧工具链的 `__set_thread_area.s` 正是这么做的（`setrb %rb4, %rd16` + 直接返回，全程没有 syscall）。

**唯一要做的新工作**：按当前 ABI（指针参数走 RB bank，不是旧 v5 的 RD bank）重写这个 stub——大概率是一条 `rb2rb rb4, rb16, 1`（把入参 rb16 整块拷贝进 rb4）+ 返回，而不是旧文件里的 `setrb %rb4, %rd16`（旧 ABI 参数在 rd16）。`get_tp.s` 同理是反向的 `rb2rb`/`rd2rb` 读出 rb4。

### 3.3 musl 本体不需要 TLS 重定位类型

`grep -rl '__thread ' ~/toolchain/musl/src` **零匹配**。musl 自己的 errno/locale 等每线程状态，全部通过 `__pthread_self()`（`(pthread_t)(__get_tp() - sizeof(struct __pthread) - TP_OFFSET)`，见 `src/internal/pthread_impl.h` L119）算出 TCB 指针再做结构体字段访问，**不依赖编译器生成的 TLS 访问指令（GD/IE/LE 模型），不依赖任何 `R_*_TPREL`/`R_*_DTPMOD`/`R_*_DTPOFF` 类重定位**。

`contracts/elf/spec.md` 当前定义的 10 种重定位类型里确实**没有任何 TLS 相关类型**（`R_DADAO_64`/`ABS_W0-3`/`PCREL18/24/12`/`RELA`/`NONE`），但**这不阻塞"跑通 musl 本体"**——只阻塞"用户代码里写 `__thread int x;`"这一类特性（这类特性在 gcc-c-torture 里占比很低，且可以按需后置）。

**结论**：TLS 需求分两个独立层次——
1. **musl 本体运行**：只需要 rb4 能被写入+读出（无新 ISA 工作，只需新写 2-3 个汇编 stub 文件）。
2. **用户代码 `__thread` 变量**：需要 ELF TLS 重定位类型 + LLVM 后端 TLS 访问 codegen，**明确可以延后**，不阻塞 gcc-c-torture 的绝大多数用例。

### 3.4 动态链接/ELF 现状

ADR-0014 D5 已定"musl 静态构建"（长期真 kernel 前不做动态链接）。当前 `dadao.ld` 是固定基址（`0x80000000`）静态可执行文件布局，无 `PT_INTERP`/`PT_DYNAMIC` 处理，与"musl 静态链接"目标一致，**不需要额外 ABI 工作**。旧工具链 `reloc.h` 里的 `CRTJMP`/`REL_GOT`/`REL_PLT`（供动态链接器跳转用）在静态链接场景下不会被触发，属于"以后做动态链接才需要"的范畴，本阶段可忽略。

---

## 4. syscall ABI（ADR-0014 D2）是否需要扩展/调整

**不需要改寄存器约定或陷入机制**（`rd16`=号/`rd17-22`=参数/`rd31`=返回/`trap cfx_smon`，D2 已经是为"musl 零改动接入"设计的，选 asm-generic 编号正是为此）。

**需要扩展的只是 responder 里的 `switch(sysno)` case 表**——QEMU 和 gem5 各自的 cfx_smon handler 都要按 §2.3 的缺口清单依次补 `case`。这是**纯增量式**扩展，不触碰已有 4 个 case，不影响 ADR-0014 已锁定的 ABI 契约本身。

一个需要架构师/ADR 层面明确的小决策点：**mmap 在这套"无 MMU、system-mode、固定基址"的模拟环境里怎么落地**——真实 Linux mmap 会分配新的虚拟地址区间，但 DADAO-0628 当前没有 MMU/分页（M1 排除 SEE 特权层），所以 cfx_smon 的 mmap handler 大概率和 brk 一样是"记账式"实现（维护一个简单的堆指针/区间分配器，返回递增地址，`PROT_NONE` guard page 可以直接假装成功而不真正做访问保护——因为没有 MMU 就没有页保护机制可言）。这个简化策略需要在具体实现任务里写清楚（"记账式 mmap，不做真实页保护，QEMU/gem5 双后端行为要一致"），供后续任务参考。

---

## 5. 建议的移植阶段划分

### 阶段 A：syscall 面补齐（P0/P1，无 musl 代码改动）
在现有 cfx_smon responder（QEMU `target/dadao/cpu.c` + gem5 `src/arch/dadao/decoder.cc`）里补 `mmap`/`munmap`/`mprotect` 三个 case（记账式实现，双后端一致），用手写 `trap cfx_smon` 汇编向量验证（不依赖 musl 本身）。

### 阶段 B：musl arch port 骨架（无 pthread/无 __thread，静态单线程）
1. 写 `arch/dadao/syscall_arch.h`（按 ADR-0014 D2 当前寄存器号，`rd16`=号/`rd17-22`=参数）
2. 写 `arch/dadao/reloc.h`（沿用 `contracts/elf/spec.md` 已有 10 种重定位类型，静态链接场景基本用不上大部分，先给最小可编译的占位）
3. 写 `arch/dadao/bits/*.h`（alltypes/syscall.h.in 等，规模照抄旧工具链的"文件清单"，内容需按当前类型宽度/ABI 重新核对，特别是指针类型走 RB bank 是否影响 `bits/alltypes.h` 里任何布局假设——大概率不影响，因为那是 C 类型层面，不涉及寄存器分配）
4. 写 `crt/crt1`/`crt_arch.h`/`crt_arch.s`：**关键工作项**——按 §2.2 的分析，需要在 `_start` 里合成一个满足 `_start_c(long *p)` 期待的最小栈布局：`argc=1, argv=["prog", NULL], envp=[NULL], auxv=[AT_PAGESZ=4096, AT_UID=0, AT_EUID=0, AT_GID=0, AT_EGID=0, AT_SECURE=0, AT_RANDOM=<指向16字节零缓冲区>, AT_NULL]`（不需要真的向 gem5 SE `argsInit`/QEMU 现有 trampoline 要求任何改动——完全在用户态 crt0 里合成，两个后端行为一致）
5. 写 `pthread_arch.h` + `get_tp.s` + `__set_thread_area.s`：按当前 ABI（rb2rb rb4）重写（§3.2），**不是 syscall，是纯寄存器指令**
6. 写 `atomic_arch.h`：沿用旧工具链结论——走 `__sync_*` builtin，不赌硬件 LL/SC（B03/B09 教训）
7. `musl configure` + Makefile 集成 dadao target（confirm `configure` 里已有 `dadao*) ARCH=dadao` 分支，来自旧仓库，需要在新仓库重新确认/迁移这一条 configure 规则，不能假设它还在)
8. E2E：`clang --target=dadao -static` 编一个 `int main(){return 0;}` 链 musl，双后端跑 `exit(0)`；再加一个 `malloc`+`printf` 的最小程序（真正触发 mmap 路径）

### 阶段 C：延后特性（明确排后，不阻塞阶段 A/B 验收）
- `pthread_create`/多线程（`clone`/`futex`/`set_tid_address`）
- `signal`/`raise`/`setjmp`跨 signal（`rt_sigaction`/`sigaltstack`）
- `__thread` 用户变量（TLS 重定位类型 + LLVM TLS codegen）
- 动态链接（`ldso`/`CRTJMP`/`R_DADAO_{GOT,PLT}`）
- `getrandom`/真随机熵源（当前可用零缓冲区代替，`__init_ssp` 弱化路径需要在阶段B验证不 crash）

---

## 6. 工作量/风险量级（粗量级，非精确估算）

| 阶段 | 任务数量级 | 风险 |
|------|-----------|------|
| A（syscall 补齐） | **2-3 个任务**（mmap/munmap 一组、mprotect 一组，QEMU+gem5 各需双后端验证） | 低——纯记账式实现，模式与现有 write/exit/brk handler 完全一致，无新 ISA 语义 |
| B（musl 骨架 + E2E） | **5-7 个任务**（crt/auxv 合成、syscall_arch.h、pthread_arch.h+TLS stub、atomic_arch.h、configure 集成、最小 E2E、malloc/printf E2E） | 中——crt0 合成 auxv 是全新工作（旧工具链没有对应经验可抄，因为旧工具链靠真实 QEMU linux-user/gem5 loader 生成 auxv，DADAO-0628 现在的 system-mode 极简 harness 需要自己在用户态合成）；其余项目均有旧工具链"结论级"参照，风险可控 |
| C（延后特性） | 每项独立评估，**未纳入本次量级**（大概率各自 2-4 个任务，视 gcc-c-torture 实际失败分类倒推是否需要） | 中高——多线程/信号涉及 context-switch/RAS 交互，需重新走一遍 ADR-0012 D2 的"双后端必带"验证节奏 |
| **合计（阶段 A+B）** | **约 8-12 个任务** | 整体中等——比 picolibc 阶段（3 stub）明显大，但因为 TLS 这个最担心的"卡点"实际上不卡（§3），整体风险比 D5.1 早期"musl 现在上是早的"判断时预想的要低一些；真正的新工作集中在 crt0 auxv 合成 + mmap 记账式实现 |

---

## 7. 建议的下一步任务清单（供架构师拆分派发）

1. **任务：cfx_smon mmap/munmap handler**（QEMU+gem5 双后端，记账式堆区间分配器，手写汇编向量验证，不涉及 musl 代码）
2. **任务：cfx_smon mprotect handler**（记账式返回成功，无需真实页保护语义，双后端一致）
3. **任务：musl crt0 auxv 合成**（`_start` 在跳到 `_start_c` 前，在栈上构造 argc/argv/envp/auxv 最小集合，§5 阶段B第4条给出具体 auxv 字段清单）
4. **任务：musl arch/dadao syscall_arch.h + reloc.h + bits/ 骨架**（按当前 ADR-0014 D2 寄存器号重写，参照旧文件清单但不抄内容）
5. **任务：musl pthread_arch.h + get_tp.s + __set_thread_area.s**（rb2rb 读写 rb4，真实汇编验证 TP 可写可读，ground-truth 复跑）
6. **任务：musl atomic_arch.h**（`__sync_*` builtin 路线，沿用旧工具链结论）
7. **任务：musl configure/Makefile dadao target 集成**（确认/迁移 `configure` 里的 `dadao*) ARCH=dadao` 规则）
8. **任务：musl 静态链接 E2E #1**（`int main(){return N;}` 链 musl-static，双后端 `exit(N)`）
9. **任务：musl 静态链接 E2E #2**（`malloc`+`printf`最小程序，真正触发 mmap 路径，验证阶段A的 handler 被真实调用到）
10.（延后，视上面结果决定是否派）**任务：pthread_create 最小可用性调研**（clone/futex/set_tid_address 记账式 or 真实实现的选择）

---

## 参考

- `docs/adr/0014-libc-syscall-charter.md`（现有 syscall ABI D2）
- `docs/reviews/musl-recon-2026-07.md`（ML-001a 早期调研：SEE trap/cfx_uart/cfx_power、libc 三维对比、ABI 草案）
- `docs/adr/0012-test-tiering-strategy.md` D5（gcc-c-torture 终极目标判定）
- `~/toolchain/musl/arch/dadao/`（旧工具链 musl 移植，仅取结论/坑，不抄代码）
- `~/toolchain/DADAO/code-agent/designs/sysmode-debug-lessons.md`（B03/B06/B07/B08/B09/B10/B18、L1，20 条坑之 7 条与本次相关）
- `~/DADAO-0628/contracts/abi/spec.md` §1.2（rb4=rbtp 定义）、`contracts/isa/spec.md` §4.7（RB block copy 合法性）、`contracts/elf/spec.md`（10 种重定位类型，无 TLS 类）
- `~/DADAO-0628/components/qemu/patches/0013-dadao-trap-syscall.patch`、`~/DADAO-0628/components/gem5/patches/0010-dadao-trap-syscall.patch`（当前 cfx_smon responder 实现，write/exit/exit_group/brk）
- `~/DADAO-0628/tests/scripts/pico_stubs.s`、`crt0.s`、`dadao.ld`（当前 picolibc 阶段 syscall/crt 现状）
- musl 1.2.6 源码：`src/malloc/mallocng/malloc.c`（mmap 硬依赖）、`src/env/__libc_start_main.c`/`__init_tls.c`（启动路径 syscall 触发条件）、`src/internal/pthread_impl.h`（`__pthread_self()` 定义，TLS 无关重定位）、`src/thread/pthread_create.c`（clone/futex 等仅线程创建时触发）
