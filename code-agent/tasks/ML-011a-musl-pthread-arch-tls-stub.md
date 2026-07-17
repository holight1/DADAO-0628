# ML-011a: musl pthread_arch.h + TLS 读写 stub（阶段B任务5，解锁 pthread_arch.h 缺失的 183 处）

**执行环境**: 本地 subagent

**状态**: 已完成（subagent 自审：0 blocking finding，1 条 test-hardening 建议已现场处置；架构师 ground-truth 复核待定）

## 硬约束（务必遵守，违反视为任务失败）

- **禁止**对 `.work/source/musl` 做 `git rebase`/`git am` 重放历史/`git reset --hard` 到早于当前 HEAD 的提交之类操作。只允许在当前 HEAD（`5adeeac4`，ML-010a 落地的提交之上）基础上新增普通 `git commit`，`git format-patch` 追加到 `components/musl/patches/series`（当前已有 `0001`~`0003` 三条，本任务应产出 `0004`）。
- 本任务**不改动**任何 LLVM/QEMU/gem5 源码，除非探测阶段发现真正的后端缺口（同 ML-010a 的处置原则：不自己动手改后端，如实报告，交给架构师判断是否需要拆分独立任务）。
- 本任务**不实现**真正的多线程/`pthread_create`（那是阶段C，明确延后）——只做 `pthread_arch.h` 接口本身要求的 TP（thread pointer）寄存器读写，让 musl 静态单线程构建能过这一层。
- 完成后必须在任务文件里写「完成区」+ subagent 自审「审阅记录」（含逐条 finding + 判决）。

## 背景

ML-010a 落地 `atomic_arch.h` 后，全树 `make -k lib/libc.a` 编译成功文件数 766→778，同时暴露出下一层最大阻塞点：**`pthread_arch.h` file not found，183 处**（`docs/issues.yaml`/`code-agent/tasks/ML-010a-musl-atomic-arch.md`「完成区」已记录）。这是阶段B任务清单第5条。

**关键的项目基础**：`contracts/abi/spec.md` §1.2 已经定义 `rb4 = rbtp`（线程指针寄存器），LLVM 后端已经 reserve 这个寄存器（ML-006a 调研已确认，见 `docs/reviews/musl-recon-2026-07-16.md` §3）。musl 本体源码**零处**使用编译器 `__thread` 关键字——它的所有"每线程状态"都是通过 `__pthread_self()`（内部读 TP 寄存器）手工推导，不依赖 ELF TLS 重定位类型或链接器/加载器支持。这意味着本任务的范围很小：只需要让 musl 能读写 rb4，不需要处理任何 TLS 重定位。

**旧工具链参照的警告**：`~/toolchain/musl/src/thread/dadao/get_tp.s`/`__set_thread_area.s`（仅供接口形状参照，不可直接抄）用的是**完全不同、已废弃的汇编语法**（`%rd31` 带 `%` 前缀的寄存器名、`setrd`/`setrb` 这两个当前汇编器不存在的助记符、甚至因为当时汇编器不支持 `ret` 助记符而手写 `.4byte 0x6e000000` 机器码绕过）——这些细节全部不适用于当前工具链。当前 DADAO 汇编器语法以 `tests/scripts/crt0_auxv.s`/`tests/lit/E2E/mmap_probe.test` 为准（无 `%` 前缀寄存器名、`rb2rd`/`rd2rb`/`ret` 等助记符均已验证可用）。**此外，当前 DADAO 后端命名寄存器内联汇编已被 ML-009a 验证可行**（`register long x __asm__("rd16")` 模式在 `syscall_arch.h` 里真实工作），所以本任务应该先判断：读写 rb4 是否可以直接用 C 内联汇编（配合既有的 `rb2rd`/`rd2rb` 桥接指令）完成，而不必像旧工具链那样必须写独立 `.s` 文件——具体选择哪种方式由 subagent 根据实际验证结果决定。

## 目标

1. **`arch/dadao/pthread_arch.h`**：仿照旧工具链的接口形状（`TLS_ABOVE_TP`/`TP_OFFSET`/`GAP_ABOVE_TP` 宏定义、`MC_PC` 宏——**具体数值/含义以 musl 源码 `src/internal/pthread_impl.h`、其它成熟 arch 移植（如 `arch/riscv64/pthread_arch.h`）的定义为准，不要凭旧文件猜**）+ `__get_tp` 函数声明。
2. **`__get_tp` 的实现**：读 `rb4`（`rbtp`），返回给调用者（C 里通常是 `uintptr_t`/`unsigned long`）。用真实汇编验证这个函数返回值确实是 rb4 的当前内容（写一个独立于 musl 源码树的判别性探针：先用普通指令把某个已知值搬进 rb4，再调用 `__get_tp`，断言返回值等于该已知值——不能只验证"能编译/不崩溃"）。
3. 判断是否需要 `__set_thread_area`（`src/env/__init_tls.c`/`__libc_start_main.c` 里线程指针的初始化路径需要什么就实现什么，不要凭空猜测接口——以 musl 源码实际调用点为准）：如果需要，同样给出真实汇编验证（写入已知值到 rb4，再用 `__get_tp` 读回确认一致）。

## 验收

- `.work/build/musl`（或新建构建目录）里全树 `make -k lib/libc.a` 重跑：确认此前卡在 `pthread_arch.h` file not found 的 ~183 处不再报这个错误（可以编译通过，或者转移到其它已知/新发现的原因——但不能再是 `pthread_arch.h` 相关的错误）。
- 报告本任务后新的 `find obj/src -name '*.o' | wc -l` 编译成功文件数（相对 ML-010a 的 778，应有明显提升），并对新增失败逐一归类（不能笼统写"其它失败"，参照 ML-009a/ML-010a 完成区的归类粒度）。
- **必须有真实汇编判别性验证**（不是"能编译就算过"）：`__get_tp` 读回值与写入值一致的探针测试，双后端（QEMU + gem5）均需跑通，新增一个 `tests/lit/E2E/*.test`。
- 现有 `tests/lit/E2E/` 全量回归零变化。
- `python3 tools/run_differential.py`：如果本任务未改动任何 ISA/后端语义，此项应与基线完全一致。
- `python3 scripts/manifest_check.py` 通过。
- musl 侧改动用**普通** `git commit` 落地在 `.work/source/musl`，`git format-patch` 导出为 `components/musl/patches/0004-....patch`，追加进 `series`；三条既有 patch（0001-0003）+ 本次新增一条应能在干净 pin-commit checkout 上依次 `git am` 成功（独立验证一遍，不要只信任之前任务留下的结论）。

## 参考指针

- `docs/reviews/musl-recon-2026-07-16.md` §3（TLS/rb4 现状分析）、§5 阶段B 第5条
- `code-agent/tasks/ML-010a-musl-atomic-arch.md`「完成区」（`pthread_arch.h` 缺失的 183 处具体统计、`make -k` 复现方法）
- `contracts/abi/spec.md` §1.2（`rb4 = rbtp` 定义）
- `~/toolchain/musl/arch/dadao/pthread_arch.h`、`src/thread/dadao/get_tp.s`、`__set_thread_area.s`（**仅供接口形状参照，汇编语法已废弃不可直接抄**——见上方背景说明）
- `.work/source/musl/arch/dadao/syscall_arch.h`（ML-009a，命名寄存器内联汇编在当前后端可行的先例）
- `tests/scripts/crt0_auxv.s`、`tests/lit/E2E/mmap_probe.test`（当前汇编语法范例：无 `%` 前缀、`rb2rd`/`rd2rb`/`ret` 助记符用法）
- musl 源码 `src/internal/pthread_impl.h`、`src/env/__init_tls.c`、`src/env/__libc_start_main.c`（`pthread_arch.h`/`__get_tp`/`__set_thread_area` 的真实接口契约，以此为准）
- `docs/adr/0014-libc-syscall-charter.md` D5.2（当前阶段范围=静态单线程，多线程延后）

## 完成区

**状态**：已完成

### 探测阶段：确认了两个真正的后端/工具链缺口（均未自己修，如实报告）

1. **clang 前端缺口（真实，已验证，未修）**：`DADAOTargetInfo::getGCCRegNames()`
   （`.work/llvm/clang/lib/Basic/Targets/DADAO.cpp` L52-59）只列出
   `"rd0".."rd31"`，RB bank 寄存器名（包括 `"rb4"`）完全不在表里。直接验证：
   `register uintptr_t x __asm__("rb4");` → `error: unknown register name
   'rb4' in asm`。这意味着其它所有 musl arch（如 riscv64/aarch64）
   `pthread_arch.h` 用的"`static inline` + 具名寄存器内联汇编"套路在当前
   DADAO 后端**做不到**——本任务因此改用**独立汇编函数**（`get_tp.s`/
   `__set_thread_area.s`）绕过，而不是碰 clang 源码。
2. **gem5/QEMU 真实分歧（真实，已定位，未修，已登记）**：为写判别性探针
   最初用高 16 位非零的对抗性 64-bit 值（如 `0xCAFEBABE12345678`）过
   `rb2rb`/`rd2rb` 写 RB 寄存器再用 `rb2rd` 读回，QEMU 与 gem5 结果不一致
   （QEMU 保真，gem5 截断到 48 位）。逐层拆解（4 组独立最小探针 + 用
   `sto`/`ldo` 绕开 `rb2rd` 本身、直接 `od -tx1` 观察原始字节，避免分支
   比较逻辑本身出错的风险）后确认：**分歧依赖"写入该寄存器所用的指令
   类别"（rd2rb/rb2rb 的"Reg copy→RB" vs setzw-rb/orw-rb 的"Wyde
   immediate RB"），而非仅寄存器最终内容**——两个后端在不同写入/读出
   组合上甚至互相反着分歧（一个方向 QEMU 保真 gem5 截断，另一方向反过
   来），说明双方各自内部都有实现不一致，不是单纯"一方对一方错"。进一步
   发现这与 `tests/vectors/isa/rd-wyde-block.yaml` 的 `rb2rd`/`rb2rb`
   向量记法（"48-bit RB zero-extends"）本身就与
   `contracts/isa/spec.md §4.7` 正文（"rd2rb/rb2rb/rb2rd all transfer
   full 64 bits"）冲突——这是规范正文与既有独立向量之间的不一致，超出
   本任务范围，未擅自选边。**对本任务的实际影响为零**：musl 的 TP/指针
   值在这个目标上永远落在 48 位地址空间内（`contracts/isa/spec.md §1.3`
   "Effective address width is 48 bits"），高 16 位天然恒为 0；已用
   48-bit-clean 测试值验证 `__set_thread_area`/`__get_tp` 实际使用的
   指令序列（`rd2rb`→`rb2rb`→`rb2rd`）在双后端上字节级一致。详细分类
   记录见 `docs/issues.yaml`
   `blockcopy-rb-source-64bit-fidelity-backend-divergence`（新增）+
   `musl-backend-assert-asmprinter-unmapself`（新增，另一处独立的
   UNREACHABLE 断言位置）+ `musl-backend-assert-instrinfo-unreachable`
   （追加说明）。

### 实现

**路线**：`__get_tp`/`__set_thread_area` 不用 C 内联具名寄存器（clang
前端不支持 RB bank 寄存器名，见上），改用**独立汇编函数**，与
`syscall_arch.h`（ML-009a）的具名寄存器内联汇编路线是两条并存但互不冲突
的技术路径（前者受 C 内联汇编限制阻塞，后者不受影响，因为 syscall ABI
只涉及 RD bank）。

- **`arch/dadao/pthread_arch.h`**：`TLS_ABOVE_TP` + `GAP_ABOVE_TP=0`
  （与 riscv64 一致）；`TP_OFFSET`/`DTP_OFFSET` 保留默认值 0（不定义，
  显式注释说明——两者只影响编译器生成的 `__thread` 访问代码，musl 本体
  在这个 target 上零使用，`grep -rl '__thread ' src` 零匹配，已核验）；
  `MC_PC __gregs[0]`（与 riscv64 一致，`arch/dadao/bits/signal.h` 的
  `mcontext_t` 本身是已声明的 `[OPEN]` 占位结构，此处只是让
  `pthread_cancel.c` 的 `uc->uc_mcontext.MC_PC` 类型检查通过，非真实
  signal-frame ABI）；声明 `hidden uintptr_t __get_tp(void);`。
- **`src/thread/dadao/get_tp.s`**：`rb2rd rd31, rb4, 1` + `ret rd0, 0`。
  关键点（subagent 复核逐条验证）：`ret rdha, imms18`
  （`contracts/isa/spec.md §5.5`）把 `rdha` 设为**编译期立即数**
  `sext_18(imms18)`，不是"拷贝某个已算好的寄存器"——所以真正的返回值
  必须先算进 `rd31`，`ret` 必须以 `rd0`（合法 no-op 目的寄存器）收尾，
  否则会被 `ret rd31, 0` 的立即数覆盖清零，编译能过、有时甚至"看起来能
  工作"（返回 0），实际上悄悄破坏了 `__get_tp()` 的语义。
- **`src/thread/dadao/__set_thread_area.s`**：`rb2rb rb4, rb16, 1` +
  `ret rd31, 0`。指针参数按 ABI（`contracts/abi/spec.md §2.1`）落在 RB
  bank 的 `rb16`（不是 `rd16`）；返回值 0 是真正的编译期常量，所以这里
  用 `ret rd31, 0` 直接嵌入（`§5.3` 文档化的合法捷径），与 `get_tp.s`
  相反但都各自正确。**为什么必须是纯寄存器写而非 syscall**：musl 通用
  fallback（`src/thread/__set_thread_area.c`）在 `SYS_set_thread_area`
  未定义时返回 `-ENOSYS`；其调用者 `src/env/__init_tls.c` 的
  `__init_tp()` 把任何负返回值当致命错误处理（调用 `a_crash()`）——已
  端到端追踪确认，不是凭空猜测。

### 判别性探针

`tests/lit/E2E/tp_probe.test`（新增）：与 `get_tp.s`/
`__set_thread_area.s` **逐字节相同**的指令序列（`rb2rb rb4, rb16, 1` /
`ret rd31, 0` 和 `rb2rd rd31, rb4, 1` / `ret rd0, 0`），通过真实
`call`/`ret` 子程序边界验证：
1. 写入已知值（48-bit-clean，`0x0000BABE12345678`）→ 读回，断言相等；
2. 覆盖写入第二个不同的已知值（`0x0000112233445566`）→ 读回，断言相等
   （排除"卡在复位值/首次写入值"假阳性）；
3. **subagent 复核发现的加固点**：在 `set_tp_sub`/`get_tp_sub` 两次调用
   之间用 `rela`/`addi-rb` 把 rb16（携带待写值的参数寄存器）覆写成一个
   无关哨兵值，排除"写入是 no-op 且读指令源操作数误解析成 rb16"这种复合
   故障巧合通过的可能——已现场处置（见下方审阅记录）。

双后端结果：QEMU exit=42、gem5 exit=42，均输出 `tp-ok`。

### 修改文件

- `.work/source/musl`（独立 git 仓库，普通 commit）：新增
  `arch/dadao/pthread_arch.h`、`src/thread/dadao/get_tp.s`、
  `src/thread/dadao/__set_thread_area.s`，commit `f4b0c3d1`（HEAD 从
  `5adeeac4` 前进一位）。
- 主仓库：
  - `components/musl/patches/0004-dadao-add-arch-dadao-pthread_arch.h-get_tp.s-__set_t.patch`
    （新增）、`components/musl/patches/series`（追加第四行）。
  - `tests/lit/E2E/tp_probe.test`（新增判别性探针）。
  - `docs/issues.yaml`：新增
    `musl-backend-assert-asmprinter-unmapself`、
    `blockcopy-rb-source-64bit-fidelity-backend-divergence` 两条，
    `musl-backend-assert-instrinfo-unreachable` 追加说明。
  - 本任务文件。
- **未改动**任何 `.work/source/{llvm,qemu,gem5,llvm-test-suite}` 源码
  （`git status --porcelain` 四者均确认干净）。

### 验收结果（逐条对应「验收」小节）

1. **全树 `make -k lib/libc.a` 重跑**（`-j1`，避免并行日志交错计数误差，
   ML-010a 架构师复核已记录过这个坑）：`grep -c "pthread_arch.h"
   build_ml011a_j1.log` = **0**（此前 ML-010a 报告 183 处）。
2. **新编译成功文件数**：`find obj/src -name '*.o' | wc -l` = **937**
   （相对 ML-010a 的 778，+159）。剩余 **409** 个失败文件逐一归类（用
   python 脚本按"每个失败目标最近一次 clang 调用+错误文本"精确配对，
   不是宽窗口 grep，避免误关联）：

   | 类别 | 文件数 | 说明 |
   |---|---|---|
   | `unsupported library call operation`（libcall lowering 缺口） | 157 | 与 ML-009a/ML-010a 已知的 soft-float/math 缺口同类，数量**不变**（157→157），非本任务引入 |
   | 尾调用降低断言 `LowerCall emitted a return value for a tail call!` | 229 | 已知既有缺口（`docs/issues.yaml` `codegen-tailcall-lowercall-assert`），此前 ML-010a 报告 209，本任务 pthread_arch.h 解锁后又暴露 **20 个新触发点**（原来被 pthread_arch.h 缺失挡住，从未编译到这一步），非本任务新代码引入的 bug，只是新曝光 |
   | `Cannot select: ... dynamic_stackalloc ...`（VLA/alloca） | 7 | ML-010a 已知类别（此前 6），新增 1 个触发点 |
   | `Cannot select: ... sign_extend_inreg ...` | 2 | `putgrent.c`/`puts.c`，与 ML-010a 报告的**完全相同**两个文件，数量不变 |
   | 内联汇编寄存器分配失败（`couldn't allocate reg for constraint 'r'`） | 1 | `explicit_bzero.c`（ML-009a/ML-010a 已知）。`__libc_start_main.c` 同时命中这个错误**和**尾调用断言（同一文件两个独立既有 bug 叠加），按"主要卡点"归入尾调用类别（脚本按错误文本优先级分类，已在归类脚本里核实两个错误都存在，非误判） |
   | `Assertion 'N->getNodeId() == -1 && "Node already inserted!"'` | 6 | ML-010a 已知类别（此前 3），新曝光 3 个 |
   | `Assertion 'ResNo < NumValues && "Illegal result number!"'` | 3 | ML-010a 已知类别（此前 2），新曝光 1 个 |
   | `Assertion '... "Unexpected block with un-analyzable fallthrough!"'` | 2 | ML-010a 已知类别，数量不变 |
   | `UNREACHABLE executed at TargetInstrInfo.h:786`（`legacy/daemon.c`） | 1 | ML-010a 已知类别，数量不变 |
   | **新发现**：`UNREACHABLE executed at DADAOAsmPrinter.cpp:82`（`thread/__unmapself.c`，`lowerToMCInst: unknown operand type`，`CALL_IIII &abort` 伪指令降级失败） | 1 | 此前被 pthread_arch.h 缺失挡住从未编译到这一步，独立立项 `musl-backend-assert-asmprinter-unmapself` |

   归类总计 157+229+7+2+1+6+3+2+1+1 = **409**，与失败文件总数一致（
   `grep -c "\] Error 1" build_ml011a_j1.log` = 409）。总候选目标数
   937+409=1346，相对 ML-010a 的 778+567=1345 恰好 +1——核对原因：
   本任务新增 2 个源文件（`get_tp.s`/`__set_thread_area.s`），但
   `__set_thread_area.s` 按 musl `ARCH_GLOBS`/`REPLACED_OBJS` 机制
   **替换**了原本已存在且能编译成功的通用 fallback
   `src/thread/__set_thread_area.c`（已确认该文件仍在源码树里，只是被
   arch 版本覆盖排除出构建），净变化为 0；`get_tp.s` 是纯新增（无通用
   对应物），净 +1——与观察到的总数变化精确吻合，非计数误差。
3. **判别性探针**：`tests/lit/E2E/tp_probe.test`，QEMU/gem5 均 exit=42，
   见上文。
4. **`tests/lit/E2E/` 全量回归**：`llvm-lit tests/lit/E2E/` →
   **57/57 (100.00%)**（此前 ML-010a 报告 56/56，+1 为本任务新增的
   `tp_probe.test`，零回归）。
5. **`python3 tools/run_differential.py`**：`AGREE(3-way)=200
   DIVERGE=0 HARNESS=6`，`SAIL AGREE(4-way)=200 SAIL-DIVERGE=0`——与
   基线完全一致（本任务未改动任何 ISA/后端语义）。
6. **`python3 scripts/manifest_check.py`** → `manifest validation:
   PASS`。
7. **musl 侧改动**：`.work/source/musl` 新 commit `f4b0c3d1`（在
   `5adeeac4` 之上，普通 commit，非重写历史）；`git format-patch` 导出
   为 `components/musl/patches/0004-....patch`；`series` 已追加第四行。
   独立验证：全新 `git clone` + `checkout --detach` 到 pin commit
   `0784374d561435f7c787a555aeab8ede699ed298`，`git am` 依次应用
   `0001`→`0004` 四条 patch，全部 `Applying:` 成功。

### 遗留问题

- 剩余 409 个编译失败全部落在既有/已追踪的后端 codegen 缺口类别里
  （libcall lowering、尾调用降低、VLA、sign_extend_inreg、4 种 LLVM
  内部断言），本任务只是解锁了更深一层从而**曝光更多既有类别的实例**
  （尾调用 +20、dynamic_stackalloc +1、Node-already-inserted +3、
  Illegal-result-number +1）+ **1 个全新断言位置**
  （`DADAOAsmPrinter.cpp:82`，已登记），均非本任务范围，未做进一步根因
  定位，留给独立后端任务。
- **`blockcopy-rb-source-64bit-fidelity-backend-divergence`**（新发现，
  已登记 `docs/issues.yaml`）：QEMU/gem5 在 RB-bank block-copy 指令
  （`rd2rb`/`rb2rb` 写 → `rb2rd`/`rb2rb` 读）高 16 位非零时的保真行为
  上存在真实、依赖"写入指令类别"的分歧，且与
  `tests/vectors/isa/rd-wyde-block.yaml` 的既有向量记法本身就与
  `contracts/isa/spec.md §4.7` 正文冲突。不阻塞本任务交付（真实
  musl/TP 用途的值域天然 48-bit-clean，已验证双后端一致），但建议架构师
  评估是否需要单独的序列级差分回归覆盖 + 澄清规范正文与向量的不一致。
- pthread_arch.h/get_tp.s/__set_thread_area.s 只覆盖"读写 rb4"这一最小
  接口契约，**不实现**真正的多线程/`pthread_create`（阶段C，明确延后，
  ADR-0014 D5.2）。

### 审阅记录（subagent）

- subagent 已读 `reviewer.md`，逐行审查 `pthread_arch.h`/`get_tp.s`/
  `__set_thread_area.s`/`tp_probe.test`/`docs/issues.yaml` 新增两条，
  未采信完成区叙述，独立复核每一处关键断言：
  - 独立验证 `DADAOTargetInfo::getGCCRegNames()` 只列 `rd0`..`rd31`（读
    源码原文确认，非轻信任务描述）；独立验证 `grep -rl '__thread '
    src` 零匹配（确认 TLS_ABOVE_TP/GAP_ABOVE_TP/MC_PC 选择在本阶段无
    运行时后果的说法成立）。
  - 独立推演 `ret rdha, imms18` 语义（立即数覆盖，非拷贝已算值），确认
    `get_tp.s` 用 `ret rd0, 0`（非 `ret rd31, 0`）是必需的，若写反会
    是"编译通过、有时看起来能工作"的静默 bug——核实这与
    `contracts/abi/spec.md §5.3` 文档化的惯用法逐字吻合。
  - 独立确认 `__set_thread_area.s` 指针参数落在 `rb16`（非 `rd16`，读
    ABI §2.1 原文确认）；确认 `ret rd31, 0` 在这里是**因为返回值 0 本身
    是编译期常量**才对，与 `get_tp.s` 相反但两者各自正确，非随意。
  - 端到端追踪 `__set_thread_area` 为什么必须是纯寄存器写、不能是
    syscall（`src/thread/__set_thread_area.c` 通用 fallback → `-ENOSYS`
    → `__init_tls.c` `__init_tp()` 致命错误 → `a_crash()`），非凭空
    断言。
  - 确认 `tp_probe.test` 的两个子程序与 `get_tp.s`/
    `__set_thread_area.s` 逐字节相同（直接比对，非"风格类似"）。
  - **finding（非阻断，test-hardening 建议）**：`tp_probe.test` 原版
    在 `set_tp_sub`/`get_tp_sub` 两次调用之间未清空/覆盖 rb16（携带待
    写值的参数寄存器），理论上存在"写入是 no-op 且 `get_tp_sub` 读指令
    源操作数误解析成 rb16"这种复合故障巧合通过的可能性（低概率，且现
    有逐指令 ISA 差分 `AGREE=200` 已独立覆盖 `rb2rb`/`rb2rd` 操作数级
    正确性，非阻断）。
  - `docs/issues.yaml` 新增两条 + 追加说明：读来诚实、可执行、未越界
    建议修改 gem5/QEMU 源码，均显式声明"不阻塞本任务交付"、把决策权交
    给架构师。
  - 附带核实：RB bank 上电复位值本身是既有 `[OPEN]` 规范缺口（
    `docs/open-spec-issues.md`），`__get_tp()` 若在 `__set_thread_area()`
    从未运行前被调用会读到未定义值——但 musl 实际调用顺序（`__init_tp()`
    在 `__libc_start_main`/`__init_tls` 阶段写入 rb4，早于任何
    `__pthread_self()`/TP 读取）保证安全，这是继承的既有规范缺口，非本
    任务引入，无需处理。
  - **判决：通过（PASS）**——寄存器/ABI 逻辑层面未发现真实 bug；两个
    `.s` 文件里 `ret rd0,0` vs `ret rd31,0` 的相反选择均独立对照
    ISA/ABI 规范正文验证成立（非仅"自洽"）。

### finding 处置

| finding | 处置 | 改了什么 | 复验证据 |
|---|---|---|---|
| `tp_probe.test` 两次调用之间未清空 rb16，存在复合故障巧合通过的低概率风险 | ✅已修 | 在 `set_tp_sub`/`get_tp_sub` 两次调用之间插入 `rela rb16, sentinel` + `addi rb16, rb16, sentinel`，把 rb16 覆写成与两个测试值都不同的哨兵地址值（两处 check1/check2 均加固） | 重新 `llvm-mc`/`ld.lld`/`llvm-objcopy` 后双后端重跑：QEMU exit=42、gem5 exit=42，均输出 `tp-ok`；`llvm-lit tests/lit/E2E/` 重跑仍 57/57 (100%)，零回归 |

**完成区状态与审阅记录判决对账**：subagent 判决为"通过（PASS）"，唯一
一条 finding 是非阻断的 test-hardening 建议，已现场处置并复验（双后端
+ 全量 lit 重跑），故完成区状态标注为"已完成"，无遗留的未处置 finding。
剩余"遗留问题"小节列出的是任务书本身划定在范围外、或需要独立后端/ISA
任务跟进的项目，不是本次审阅遗留的未处置流程项。

## 架构师复核（ground-truth）

**独立验证方法**：不采信完成区/subagent 判决，从 git 状态开始逐项重跑。

- `git status`（主仓库 + `.work/source/{musl,llvm,qemu,gem5,llvm-test-suite}`）：仅预期文件改动，`.work/source/musl` 干净单提交 `f4b0c3d1` 落在 `5adeeac4` 之上，其余四个组件全干净——无越界改动、无历史损坏、无孤立进程。
- **独立复现 clang 前端缺口**：读 `.work/llvm/clang/lib/Basic/Targets/DADAO.cpp:52-59` 原文确认 `getGCCRegNames()` 只列 `rd0`..`rd31`；独立写探针 `register unsigned long x __asm__("rb4");` → `error: unknown register name 'rb4' in asm`，逐字复现——确认改用独立汇编文件的路线选择是必需的，不是图省事。
- 逐行读 `pthread_arch.h`/`get_tp.s`/`__set_thread_area.s`：`TLS_ABOVE_TP`/`GAP_ABOVE_TP=0` 选型理由合理（与 riscv64 一致 + musl 本体零用 `__thread` 使其在本阶段无运行时后果）；`ret rd0,0`（`get_tp.s`，因为返回值是运行时算出的必须先入 `rd31` 不能被 `ret` 的立即数覆盖）与 `ret rd31,0`（`__set_thread_area.s`，因为返回值 0 本身是编译期常量，用 §5.3 文档化的捷径）两处**相反的选择**都独立核对 `contracts/isa/spec.md §5.5`/`§5.3` 原文成立，非随意/不一致。
- **独立复现判别性探针**：`llvm-lit -v tests/lit/E2E/tp_probe.test` → PASS(1/1)；读测试逻辑确认两次不同值写入+读回+哨兵覆写 rb16 排除复合故障巧合通过——判别力充分。
- **独立全新构建目录重跑**（非复用产物，`-j1` 避免 ML-010a 已记录过的并行日志交错计数误差）：`configure` 通过；`make -k -j1 lib/libc.a` → `find obj/src -name '*.o' | wc -l` = **937**，与声称数字精确一致（较 ML-010a 778 净增 159）；`pthread_arch.h` 相关错误 = **0**（较此前 183 归零）。
- **失败分类逐项核对**（`-j1` 干净日志，避免并行交错误差）：总失败 = **409**（`] Error 1` 计数），与完成区总和精确一致；逐类精确匹配：`unsupported library call operation`=157、`dynamic_stackalloc`=7、`sign_extend_inreg`=2、`Illegal result number`=3、`Node already inserted`=6、`un-analyzable fallthrough`=2、`TargetInstrInfo.h:786`=1、`DADAOAsmPrinter.cpp:82`（新增 issue）=1、内联汇编寄存器分配失败=2（`explicit_bzero.c`+`__libc_start_main.c`）——**全部逐项精确匹配完成区数字，无出入**（本次用 `-j1` 干净日志，连 ML-009a/ML-010a 复核时因 `-j8` 交错产生的个位数误差这次都没有）。
- **`docs/issues.yaml` 新增两条 + 一条追加说明**：`check_issues.py` 通过（Open 20/Closed 29/Total 49，YAML 结构校验 PASS，无重复 key）；`musl-backend-assert-asmprinter-unmapself` 记录清晰、`resolved_by: null` 留待独立任务；`blockcopy-rb-source-64bit-fidelity-backend-divergence` 的分析我逐层核对了 gem5 侧根因（读 `components/gem5/patches/0007-dadao-controlflow-ras.patch` 的 `BlockCopyInst::execute()` 原文确认 `if (srcRb) v &= MASK48` 是**读时**按源寄存器所在 bank 掩码，与写入历史无关；结合 subagent 报告的四行为组合矩阵可推出：**gem5 是"读指令决定是否掩码，写时从不掩码"（内部自洽）**，**QEMU 则是"特定写指令（setzw-rb/orw-rb）在写时就已限制到 48 位，rd2rb 写时不限制，读指令本身从不额外掩码"（内部也自洽，但写时行为因指令而异）**——两者各自内部逻辑自洽但对"RB 寄存器该不该在什么时候截断到 48 位"这件事的实现假设不同，导致组合起来产生分歧，这是一个真实、非本任务引入的架构级不一致，`resolved_by: null` 留给专门任务处理是正确判断。**对 ML-011a 本身无影响**：`tp_probe.test` 用的两个测试值均 48-bit-clean，双后端在这个值域上语义一致，已验证。
- 全量 `llvm-lit tests/lit/E2E/` → **57/57（100%）**，与基线一致（56+1 新增），零回归。
- 差分：`python3 tools/run_differential.py` → **AGREE(3-way)=200/DIVERGE=0/HARNESS=6**，**Sail AGREE(4-way)=200/SAIL-DIVERGE=0**，与基线一致（本任务未改任何 ISA/后端语义，符合预期——`blockcopy-rb-source-64bit-fidelity-backend-divergence` 这个真实分歧之所以没有反映在这个全局差分基线里，是因为现有向量都是"直接注入寄存器初值"的单指令状态测试，不经过真实的"写指令→读指令"组合执行序列，这正是 issue 里指出的向量覆盖盲区，非本次验证的矛盾）。
- `python3 scripts/manifest_check.py` → **PASS**。
- **独立复现 patch series 可重放性**：`git clone` 全新副本 + `checkout --detach` 到 pin commit + `git am` 依次应用 `0001`→`0004` 四条 patch → 全部 `Applying:` 成功。

**结论**：subagent 的两处探测发现（clang 前端 RB 寄存器名缺口、QEMU/gem5 block-copy 保真分歧）均经独立复现确认真实，处置得当（如实报告+登记 issue，未越界修改后端/前端代码）；`get_tp.s`/`__set_thread_area.s` 里 `ret rd0,0` 与 `ret rd31,0` 两处相反选择的正确性均独立核对规范原文成立，不是"看起来一致就当对了"。**ML-011a 验收通过**——`pthread_arch.h`/TP 寄存器读写落地，编译成功文件数 778→937，`pthread_arch.h` 相关错误清零，musl 阶段B进度：syscall handler→crt0 auxv→arch/dadao 骨架→atomic_arch.h→**pthread_arch.h+TLS stub（本任务）**均完成。剩余 409 个失败全部落在已知/已追踪类别（含本任务新曝光的一处独立 UNREACHABLE 断言，已登记），无一归因于本任务新代码。
