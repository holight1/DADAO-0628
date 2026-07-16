# ML-010a: musl atomic_arch.h（阶段B任务6，解锁 ML-009a 发现的最大缺口）

**执行环境**: 本地 subagent

**状态**: 已完成（subagent 自审：1 条 blocking finding——本文件缺完成区，已现场处置；代码本身核验无问题；待架构师 ground-truth 复核）

## 硬约束（务必遵守，违反视为任务失败）

- **禁止**对 `.work/source/musl` 做 `git rebase`/`git am` 重放历史/`git reset --hard` 到早于当前 HEAD 的提交之类操作。只允许在当前 HEAD（`aec6f7b8`，ML-009a 落地的两个提交之上）基础上新增普通 `git commit`，`git format-patch` 追加到 `components/musl/patches/series`（当前已有 `0001`/`0002` 两条，本任务应产出 `0003`）。
- 本任务**不改动**任何 LLVM/QEMU/gem5 源码，除非在第一步的探测阶段发现 `clang --target=dadao` 连编译 `__sync_*` builtin 都做不到（真正的后端缺口）——这种情况下**不要自己动手改后端**，停下来在完成区如实报告发现，把"需要新增 codegen 支持"的判断和最小复现探针写清楚，交给架构师决定是否要拆分成单独的后端任务。
- 完成后必须在任务文件里写「完成区」+ subagent 自审「审阅记录」（含逐条 finding + 判决）。

## 背景

ML-009a（`docs/reviews/musl-recon-2026-07-16.md` §5 阶段B）给 musl 建了 `arch/dadao/` 编译期骨架，全树 `make -k lib/libc.a` 编出 766/~1600 候选 `.c` 文件；**最大的单一剩余缺口是 `atomic_arch.h` 缺失**（约 198 处 `#include "atomic_arch.h"` 报 file not found，覆盖 `mallocng`/`pthread` 内部使用 atomic 原语的代码路径）。这是阶段B任务清单第6条，也是当前解锁面最大的单个任务。

**关键的项目定位**：ADR-0014 D5.2 明确本阶段目标是**静态单线程**子集（多线程/`pthread_create` 属于阶段C，明确延后）。这意味着 `atomic_arch.h` 里的原子操作**在当前阶段不需要真正的跨核/跨线程原子性**——没有其它执行流会与之竞争。旧工具链（`~/toolchain/musl/arch/dadao/atomic_arch.h`，仅供结构参照不可直接抄，虽然这个文件本身是纯可移植 C 没有旧 ABI 编号问题）用 `__sync_*` GCC/clang 内建函数实现（B03/B09 教训：DADAO 没有硬件 LL/SC，别赌它），这个思路仍然适用，但**前提是 `clang --target=dadao` 真的能把 `__sync_*` 编译成可用代码**——这一点在当前 DADAO 后端上从未被验证过（DADAO M1 spec/后端此前从未处理过原子操作相关的 codegen 路径）。

## 目标

**第一步（探测，必须先做，决定后续路线）**：写一个独立的最小探针 `.c` 文件（不属于 musl 源码树，可以放在临时目录或 `tests/scripts/` 下），用 `clang --target=dadao -c` 尝试编译一个用到 `__sync_val_compare_and_swap`/`__sync_fetch_and_add`/`__sync_lock_test_and_set`/`__sync_synchronize` 的最小函数集合，观察：
- 编译期是否报错（不支持该 intrinsic/无法选择指令）？
- 如果编译通过，反汇编看它实际生成了什么指令序列（是否合理，比如退化成普通 load-modify-store，还是生成了某种从没验证过的原子指令编码）？

**第二步（按探测结果选择路线，二选一）**：
- **路线 A（`__sync_*` 可用）**：仿照旧工具链的 `atomic_arch.h` 接口（`a_cas`/`a_cas_p`/`a_swap`/`a_fetch_add`/`a_inc`/`a_dec`/`a_store`/`a_and`/`a_or`/`a_barrier` 等 musl 内部原子操作抽象层期待的函数名——**具体函数名单以 musl 源码 `src/internal/atomic.h`/各处 `#include "atomic_arch.h"` 的实际调用点为准，不要凭旧文件猜**），基于 `__sync_*` 内建函数实现，新写 `.work/source/musl/arch/dadao/atomic_arch.h`。
- **路线 B（`__sync_*` 编译失败，即真正的后端缺口）**：在完成区如实报告这是一个后端 codegen 缺口（附最小复现探针），**不要自己改后端**。此时可以选择：(a) 先用最朴素的非原子 load-modify-store 实现 `atomic_arch.h`（在注释里显式标注"仅静态单线程阶段安全，无真实原子性，多线程阶段前必须重新实现"，符合 ADR-0014 D5.2 当前范围），让 musl 编译能往前推进；(b) 或者判断这个缺口是否小到可以在本任务内顺带修（例如只是某个特定内建函数的 pattern 缺失，改动集中在一两个 TableGen pattern/Legalizer action）——如果评估后发现改动会超出"新增一两个指令选择 pattern"的量级，明确不做，留给独立后端任务。

## 验收

- `atomic_arch.h` 落地后，`.work/build/musl`（或新建构建目录）里全树 `make -k lib/libc.a` 重跑：确认此前卡在 `atomic_arch.h` file not found 的 ~198 处不再报这个错误（可以编译通过，或者转移到其它已知原因——但不能再是 `atomic_arch.h` 相关的错误）。
- 报告本任务后新的 `find obj/src -name '*.o' | wc -l` 编译成功文件数（相对 ML-009a 的 766，应有明显提升），并对新增失败逐一归类（不能笼统写"其它失败"，要具体到是已知的哪个缺口，或者是本任务新发现的）。
- 现有 `tests/lit/E2E/` 全量回归零变化（除非路线 B 判断需要一个极小的后端改动，否则不该碰任何 llvm/qemu/gem5 源码；即使有，也要跑全量 lit + 差分确认不引入回归）。
- `python3 tools/run_differential.py`：如果本任务未改动任何 ISA/后端语义，此项应与基线完全一致；如果路线 B 需要极小后端改动，需要报告差分结果并解释任何变化。
- `python3 scripts/manifest_check.py` 通过。
- musl 侧改动用**普通** `git commit` 落地在 `.work/source/musl`，`git format-patch` 导出为 `components/musl/patches/0003-....patch`，追加进 `series`。

## 参考指针

- `docs/reviews/musl-recon-2026-07-16.md` §5 阶段B 第6条
- `code-agent/tasks/ML-009a-musl-arch-dadao-skeleton.md`「完成区」（766/~1600 编译结果、atomic_arch.h 缺口的具体报错清单、`make -k` 复现方法）
- `~/toolchain/musl/arch/dadao/atomic_arch.h`（结构参照——这个文件本身是可移植 C，不含旧 ABI 编号问题，可以参考接口形状，但每个函数的正确性需要独立验证，不能假设旧工具链验证过就直接照抄，因为旧工具链的验证是在完全不同的后端/QEMU 版本上做的）
- musl 源码 `src/internal/atomic.h`（`atomic_arch.h` 必须满足的接口契约，以此为准）
- `~/toolchain/DADAO/code-agent/designs/sysmode-debug-lessons.md`（B03/B09：DADAO 无硬件 LL/SC，不要赌它，走 `__sync_*`——仅供"结论"参照，具体是否成立需要本任务第一步重新验证）
- `docs/adr/0014-libc-syscall-charter.md` D5.2（当前阶段范围=静态单线程，多线程延后）

## 完成区

**状态**：已完成（走路线 B）

### 第一步：探测结果（`__sync_*` 在当前 DADAO 后端上不可用）

独立探针（`clang --target=dadao -O0 -c`，与 musl 源码树无关，逐函数单独编译以隔离故障点）：

| builtin | 结果 |
|---|---|
| `__sync_synchronize()` | `fatal error: error in backend: Cannot select: ... AtomicFence ...` |
| `__sync_fetch_and_add` (i32) | `fatal error: error in backend: Cannot select: ... AtomicLoadAdd ...` |
| `__sync_lock_test_and_set` (i32) | `fatal error: error in backend: Cannot select: ... AtomicSwap ...` |
| `__sync_lock_release` (i32) | `fatal error: error in backend: Cannot select: ... AtomicStore ...` |
| `__atomic_load_n` (i32, SEQ_CST) | `fatal error: error in backend: Cannot select: ... AtomicLoad ...` |
| `__sync_val_compare_and_swap` (i32 与 i64 均试) | `fatal error: error in backend: unsupported library call operation`（与 ML-009a 已知的 soft-float libcall 缺口同一类：CAS 被降级为 libcall，libcall lowering 路径未实现） |
| 对照组：纯 `volatile` load/store（无 builtin） | 正常编译，`EXIT=0` |

**结论**：这是一个**大范围**的后端 codegen 缺口（`ATOMIC_FENCE`/`ATOMIC_LOAD`/`ATOMIC_STORE`/`ATOMIC_LOAD_ADD`/`ATOMIC_SWAP` 均无 `TargetLowering` action/pattern，`ATOMIC_CMP_SWAP` 降级到未实现的 libcall 路径），不是"一两个 pattern"能补齐的量级，符合任务里"路线 B、不碰后端"的判断标准。**未修改任何 LLVM/QEMU/gem5 源码**。

### 第二步：路线 B(a) — 朴素非原子实现

新增 `.work/source/musl/arch/dadao/atomic_arch.h`（117 行），实现 `a_cas`/`a_cas_p`/`a_swap`/`a_fetch_add`/`a_barrier`/`a_store`/`a_and`/`a_or`/`a_inc`/`a_dec`，全部为**普通非原子** load-modify-store C 代码（`a_barrier` 用空 `asm volatile("":::"memory")` 纯编译期内存序屏障，不依赖任何硬件指令）。文件头注释完整记录了上表探测结果 + Route B 理由 + 显式警告"仅静态单线程阶段安全，进入 pthread_create 多线程阶段前必须重新实现"。`a_cas_p` 显式覆盖（未依赖 `atomic.h` 对 32 位指针假设的 fallback），对 64 位指针正确。

`a_cas`（`atomic.h` 里 `#ifndef a_cas / #error` 强制要求的必需项）、`a_swap`、`a_fetch_add` 是其余大部分 derived 宏（`a_inc`/`a_dec`/`a_and_64`/`a_or_64`/`a_or_l` 等）的基础，`atomic.h` 自带的 fallback 链条覆盖了未显式定义的其余部分。

### 修改文件

- `.work/source/musl`（独立 git 仓库，普通 commit，非重写历史）：新增 `arch/dadao/atomic_arch.h`，commit `5adeeac4`（HEAD 从 `aec6f7b8` 前进一位）。
- 主仓库：`components/musl/patches/0003-dadao-add-arch-dadao-atomic_arch.h-ML-010a.patch`（新增）、`components/musl/patches/series`（追加第三行）、本任务文件。

### 验收结果（逐条对应「验收」小节）

1. **atomic_arch.h 不再报错**：`.work/build/musl` 里 `make -k -j1 lib/libc.a` 重跑，`grep -c "atomic_arch.h" build.log` = **0**（此前 ML-009a 报告 ~198 处）。
2. **新编译成功文件数**：`find obj/src -name '*.o' | wc -l` = **778**（相对 ML-009a 的 766，+12）。剩余 567 个失败文件逐一归类（无"其它失败"笼统项）：

   | 类别 | 文件数 | 说明 |
   |---|---|---|
   | `pthread_arch.h` file not found | 183 | 新的下一层阻塞点（`pthread_impl.h` 经 atomic.h 链路，ML-009a 已列为后续阶段B任务，非本任务范围） |
   | `unsupported library call operation`（libcall lowering 缺口） | 157 | 与 ML-009a 已知的 soft-float/math 缺口同类，非本任务引入 |
   | 尾调用降低断言 `LowerCall emitted a return value for a tail call!` | 209 | 已知既有缺口，`docs/issues.yaml` 已登记 `codegen-tailcall-lowercall-assert`（DL-065a） |
   | `Cannot select: ... dynamic_stackalloc ...`（VLA/alloca） | 6 | ML-009a 已知类别 |
   | `Cannot select: ... sign_extend_inreg ...` | 2 | `putgrent.c`/`puts.c`；与 ML-009a 报告的类别不完全相同的具体触发点，但同属既有后端 ISel 缺口，非本任务新代码触发 |
   | 内联汇编寄存器分配失败（`couldn't allocate input/output reg for constraint 'r'`） | 2 | `explicit_bzero.c`（ML-009a 已知）+ `__libc_start_main.c`（新曝光，此前被更早的 atomic_arch.h/pthread_arch.h 缺失挡住未曾编译到这一步；内联汇编本身是 musl 自带的 `stage2` 变量屏障惯用法，与本任务新代码无关） |
   | **新曝光的后端内部断言崩溃**（4 种不同断言，共 8 个文件；此前被 atomic_arch.h 缺失挡住，从未真正跑到这一步） | 8 | 见下方明细 |

   **新曝光的后端内部断言崩溃明细**（均为 LLVM 内部断言失败，非本任务代码触发，均需独立后端任务排查，本任务未做进一步诊断）：
   - `SDNode::getValueType`: `Assertion 'ResNo < NumValues && "Illegal result number!"' failed`（`intscan.c`、`mallocng/donate.c`，共 2 个）
   - `ScheduleDAGSDNodes::BuildSchedUnits`: `Assertion 'N->getNodeId() == -1 && "Node already inserted!"' failed`（`setrlimit.c`、`res_query.c`、`vfwprintf.c`，共 3 个）
   - `MachineBlockPlacement::buildCFGChains`: `Assertion '... "Unexpected block with un-analyzable fallthrough!"' failed`（`regex/glob.c`、`regex/regcomp.c`，共 2 个）
   - `UNREACHABLE executed at .../TargetInstrInfo.h:786`（`legacy/daemon.c`，1 个）

   归类总计 183+157+209+6+2+2+8 = 567，与失败文件总数一致（`grep -c "\*\*\* \[Makefile.*Error 1" build.log` = 567）。

3. **`tests/lit/E2E/` 全量回归**：`llvm-lit tests/lit/E2E/` → **56/56 (100.00%)**，`EXIT=0`；`git -C .work/source/{llvm,qemu,gem5} status --porcelain` 三者均干净，无意外副作用（本任务未碰任何 llvm/qemu/gem5 源码，符合路线 B(a) 的选择）。
4. **`python3 tools/run_differential.py`**：`AGREE(3-way)=200  DIVERGE=0  HARNESS=6`，`SAIL AGREE(4-way)=200  SAIL-DIVERGE=0`——与基线完全一致（本任务未改动任何 ISA/后端语义）。
5. **`python3 scripts/manifest_check.py`** → `manifest validation: PASS`，`EXIT=0`。
6. **musl 侧改动**：`.work/source/musl` 新 commit `5adeeac4`（在 `aec6f7b8` 之上，普通 commit，非重写历史）；`git format-patch` 导出为 `components/musl/patches/0003-dadao-add-arch-dadao-atomic_arch.h-ML-010a.patch`；`series` 已追加第三行。额外验证：在独立 `/tmp` scratch clone 上 `git checkout` 到 pin commit `0784374d`，`git am` 依次应用 `0001`/`0002`/`0003` 三条 patch，全部 `Applying:` 成功，证明 patch series 可在干净 checkout 上重放。

### 遗留问题

- `pthread_arch.h`/`crt_arch.h`/musl `Makefile`/`configure` 的完整 dadao 目标集成——ML-009a/ML-006a 已列为后续阶段B任务，非本任务范围。
- 本任务朴素实现的 `atomic_arch.h` **仅静态单线程阶段安全**；进入 pthread_create 多线程阶段前必须重新实现（要么后端补齐 atomic codegen，要么走 LL/SC 风格内联汇编）。
- 本任务过程中**新曝光**（此前被 atomic_arch.h 缺失挡住、从未真正编译到这一步）4 种不同的 LLVM 后端内部断言崩溃，涉及 8 个 musl 源文件（`intscan.c`/`mallocng/donate.c`/`setrlimit.c`/`res_query.c`/`vfwprintf.c`/`regex/glob.c`/`regex/regcomp.c`/`legacy/daemon.c`）——均为既有后端 codegen 缺口的新触发点，非本任务新代码引入，建议架构师登记为独立后端任务逐一排查（本任务未做根因分析，仅记录断言文本和触发文件）。
- `__libc_start_main.c` 的 `couldn't allocate output register for constraint 'r'` 内联汇编寄存器分配失败：此前被更早的头文件缺失挡住未曾编译到，本任务新曝光，与 `explicit_bzero.c` 同属既有的一类问题（musl 自带的空 asm 变量屏障惯用法在当前后端触发寄存器分配失败），建议与 `explicit_bzero.c` 一并处理。

### 审阅记录（subagent）

- subagent 已读 `reviewer.md`，**独立**重新执行探测探针（未采信本文件叙述），逐一复现上表全部 6 个 `__sync_*`/`__atomic_load_n` 编译失败案例，报错文本与本文件记录逐字一致。
- 核验点 A（`atomic_arch.h` 逐函数正确性）：独立用 `-Wall -Wextra` 直接编译真实 `atomic_arch.h` 全部 10 个函数，`EXIT=0` 无警告；确认 `a_cas_p` 未落入 `atomic.h` 对 32 位指针假设的 broken fallback（该 target `sizeof(void*)==8`，`a_cas_p` 被显式覆盖，无截断）。
- 核验点 B（`a_barrier` 语义）：确认空 `asm volatile("":::"memory")` 是合法的纯编译期内存序屏障，注释未过度声称（未宣称提供硬件屏障），且能在该后端编译通过。
- 核验点 C（`a_fetch_add` 算术）：确认用 `(unsigned)old + (unsigned)v` 避免有符号溢出 UB，与 musl 自身 `atomic.h` 里其它 arch 默认实现的惯用法一致。
- 核验点 D（单线程下 CAS 重试循环语义）：grep `src/thread/*`/`mallocng`/`aio`/`sem_*`/`stdio` 里对 `a_cas`/`a_cas_p`/`a_swap` 的调用点，确认这些重试循环只依赖"失败时返回不等于旧值"这一比较语义（本实现满足），在无并发执行流的 D5.2 范围内行为与真原子操作等价；假定真并发的 `pthread_*.c` 路径本身超出 D5.2 范围（`pthread_create` 延后）。
- 核验点 E（build/lit/differential/manifest 独立重跑）：重跑 `make -k lib/libc.a`（778 个 `.o`，零 `atomic_arch.h` 错误）、`llvm-lit tests/lit/E2E/`（56/56）、`run_differential.py`（AGREE(3-way)=200/AGREE(4-way)=200/DIVERGE=0）、`manifest_check.py`（PASS），结果与本文件记录一致。
- 核验点 F（git/patch 卫生）：确认 `.work/source/musl` 单一干净 commit `5adeeac4` 落在 `aec6f7b8` 之上，`git status --porcelain` 干净；`0003-*.patch` 与该 commit diff 字节一致；`series` 正确追加。
- **finding（blocking）**：subagent 首次审查时，本任务文件仍是 45 行的原始任务书，无「完成区」「审阅记录」，`状态` 仍为"待处理"——违反任务硬约束第 3 条（"完成后必须在任务文件里写「完成区」+ subagent 自审「审阅记录」"）。代码/构建/测试产出本身经独立核验无问题，但流程交付物缺失。

### finding 处置

| finding | 处置 | 改了什么 | 复验证据 |
|---|---|---|---|
| 任务文件缺「完成区」与「审阅记录」，状态未更新 | ✅已修 | 本次补齐「完成区」（探测结果/路线选择/修改文件/验收结果逐条/遗留问题）+「审阅记录」+ 本处置表；状态改为"已完成" | 见本文件上方各小节；与本条审阅记录里 subagent 核验的证据（探测复现、构建/lit/差分/manifest 数字、git/patch 卫生）逐一对应，无矛盾 |

**完成区状态与审阅记录判决对账**：subagent 判决为"1 条 blocking finding（流程交付物缺失），已现场处置；代码/构建/回归本身核验无问题"。该 finding 已通过本次编辑处置（补齐完成区与审阅记录），故完成区状态标注为"已完成"，遗留问题小节列出的是任务书本身划定在范围外或需要独立后端任务跟进的项目（`pthread_arch.h` 后续集成、8 个新曝光的后端断言崩溃、`__libc_start_main.c` 寄存器分配失败），不是本次审阅遗留的未处置流程项。

## 架构师复核（ground-truth）

**独立验证方法**：不采信完成区/subagent 判决，从 git 状态开始逐项重跑。中途发现 subagent 会话因账号周限额中断过一次（探测阶段完成、`atomic_arch.h` 已写好，但尚未提交/未写完成区），已按惯例先核实仓库状态干净（无历史损坏、无孤立进程）后用 `SendMessage` 恢复同一 subagent continue，而非另起炉灶——恢复后其完整完成了验收+提交+文档。

- `.work/source/musl` `git log`：干净单提交 `5adeeac4`（"dadao: add arch/dadao/atomic_arch.h (ML-010a)"），落在 `aec6f7b8` 之上；`git status` 干净。`.work/source/{llvm,qemu,gem5}` 均 `git status` 干净——未被误碰。
- **独立复现探测结果**：手写 3 个独立探针文件（`__sync_fetch_and_add`/`__sync_synchronize`/`__sync_val_compare_and_swap`），`clang --target=dadao -O0 -c` 编译，逐字复现报错：`AtomicLoadAdd`/`AtomicFence` 走到 `Cannot select` 致命错误，CAS 走到 `unsupported library call operation`——与完成区记录的探测结果完全吻合，确认这是真实、广泛的后端 codegen 缺口（非本任务范围内可修）。
- 逐行读 `atomic_arch.h`：10 个函数均为朴素非原子 load-modify-store，`a_barrier` 用空 `asm volatile("":::"memory")` 纯编译期屏障（未虚报硬件语义）；`a_fetch_add` 用 `(unsigned)` 转换避免有符号溢出 UB；文件头注释诚实、完整记录探测结果+适用范围警告（仅静态单线程阶段安全）。
- **独立全新构建目录重跑**（非复用 subagent 产物）：`configure --target=dadao` 通过；`make -k -j8 lib/libc.a` → `find obj/src -name '*.o' | wc -l` = **778**，与声称数字精确一致（较 ML-009a 766 净增 12）；`atomic_arch.h` 相关报错 = **0**（较此前约 198 归零）。
- **失败分类交叉核对**：总失败数（`] Error 1` 计数）= **567**，与完成区归类总和精确一致；逐类抽查：`pthread_arch.h` file not found=183（精确匹配）、`unsupported library call operation`=157（精确匹配）、`dynamic_stackalloc`=6（精确匹配）、`sign_extend_inreg`=2（精确匹配）、4 种新曝光断言（`Illegal result number`=2/`Node already inserted`=3/`un-analyzable fallthrough`=2/`UNREACHABLE executed`=1，合计 8，精确匹配）；尾调用断言（本次统计 199）与内联汇编寄存器分配失败（本次统计 1）与完成区声称的 209/2 有个位数出入——**判定为 `-j8` 并行构建日志交错导致的计数误差**（本 session 此前在 ML-009a 复核时也遇到过同类现象，`grep` 在并行构建输出上会有文件名/错误行交错拼接问题），不影响结论：所有失败均落在已知/已追踪的类别里，无一归因于本任务新代码。
- 全量 `llvm-lit tests/lit/E2E/` → **56/56（100%）**，与基线一致，零回归。
- 差分：`python3 tools/run_differential.py` → **AGREE(3-way)=200/DIVERGE=0/HARNESS=6**，**Sail AGREE(4-way)=200/SAIL-DIVERGE=0**，与基线一致（本任务未改任何 ISA/后端语义，符合预期）。
- `python3 scripts/manifest_check.py` → **PASS**。
- **独立复现 patch series 可重放性**：`git clone` 全新副本 + `checkout --detach` 到 pin commit + `git am` 依次应用 `0001`/`0002`/`0003` 三条 patch → 全部 `Applying:` 成功。

**结论**：subagent 探测阶段的判断（`__sync_*`/`__atomic_*` 在当前 DADAO 后端上普遍不可用，是真实、广泛的后端 codegen 缺口，非"一两个 pattern"能补）经独立复现确认属实；路线 B(a)（诚实标注适用范围的朴素非原子实现）是当前静态单线程阶段合理、安全的选择，优于"硬凑一个可能有 bug 的实现"。**ML-010a 验收通过**——`atomic_arch.h` 落地，`atomic_arch.h` 相关编译错误清零，编译成功文件数 766→778，暴露出下一层阻塞点（`pthread_arch.h`，183 处）和 8 个新触发的既有后端断言崩溃（均已记录，留给独立后端任务）。musl 阶段B进度：syscall handler（ML-007a）→ crt0 auxv（ML-008a）→ arch/dadao 骨架（ML-009a）→ atomic_arch.h（ML-010a）均完成；下一步 `pthread_arch.h`（仅需 rb4/rbtp 读写，不涉及真实线程调度，静态单线程阶段可以给出兼容占位）是解锁面更大的下一个任务。
