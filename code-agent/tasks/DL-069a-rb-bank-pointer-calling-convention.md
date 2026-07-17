# DL-069a: 实现 RB bank 指针调用约定（修复 contracts/abi/spec.md §2.1 与后端实现的分歧）

**执行环境**: 本地 subagent

**状态**: 待处理

## 硬约束（务必遵守，违反视为任务失败）

- **禁止**对 `.work/<component>`（llvm/qemu/gem5/llvm-test-suite/musl）做任何 `git rebase`/`git am` 重放整条历史/`git reset --hard` 到早于当前 HEAD 的提交之类操作。只允许在当前 working tree 基础上新增普通 `git commit`，`git format-patch` 追加到对应 `components/<name>/patches/series`（`.work/llvm` 当前已有 37 条 patch，本任务在其基础上追加）。
- 本任务**只改 LLVM**（`DADAOCallingConv.td`/`DADAOISelLowering.cpp` 及必要的相关文件）。**不要**在本任务里顺手改 musl/picolibc 侧文件——那些受影响的下游文件（见"已知受影响清单"）由后续任务 ML-013a 处理，本任务只需要**如实报告**哪些下游文件会因为这个改动而需要更新（不必自己去改）。
- 完成后必须在任务文件里写「完成区」+ subagent 自审「审阅记录」（含逐条 finding + 判决）。
- **如果实现过程中发现改动范围/风险比预期大得多**（比如需要大改 ISel 才能让指针类型在 CC 分析阶段可区分、或者会导致大量既有测试的汇编输出结构性改变而不仅仅是寄存器编号变化），如实在完成区报告清楚，不要为了"看起来完成"而用不稳妥的 hack 强行让测试通过。

## 背景

`contracts/abi/spec.md §2.1` 规定：整数/标量参数走 RD bank（rd16-31），指针/地址参数走 RB bank（rb16-31），两个 bank 各自独立计数、没有共享槽位编号；§3.1 同理规定指针返回值走 `rb31`（区别于标量返回的 `rd31`）。但 `llvm/lib/Target/DADAO/DADAOCallingConv.td` 的 `CC_DADAO`/`RetCC_DADAO`（引入时注释为"GPRD only (Phase 5 spike)"）从建立起就只有一条规则，把所有 i64 可表示的值（含指针）无条件分配到 RD bank，从未使用 RB bank。这个分歧长期未被发现——`scripts/check_codegen_abi.py`（DL-040a）早在约两周前就已经把这条分歧打印成 `[INFO]`（非阻断），但因为当时 CC_DADAO 还是"spike"，这条发现没有被升级追踪，直到 ML-012a（musl 首个真实 E2E 里程碑）第一次让手写汇编（遵循文档 RB bank 约定）调用真实编译产物（遵循后端 RD bank 实现）才撞成运行时 bug。已登记 `docs/issues.yaml` 的 `dadao-callingconv-pointer-args-use-rd-bank-not-rb-bank`。

**用户已决策（2026-07-18）**：走路线 (a)——实现真正的 RB bank 指针调用约定，让后端实现追上文档 ABI，而不是反过来修订文档。

## 目标

1. **区分指针类型与整数类型**：在 LLVM CodeGen 的调用约定分析阶段（`CCState::AnalyzeFormalArguments`/`AnalyzeCallOperands`/`AnalyzeReturn`/`AnalyzeCallResult`）让指针类型的参数/返回值与普通整数类型的参数/返回值可被区分对待。DADAO 是 64 位目标，指针和 `i64` 整数在 SelectionDAG 里默认会被规约成同一个 MVT（`i64`），需要找到 LLVM 现有支持的机制来保留"这是指针"这条信息直到 CC 分析阶段（例如但不限于：使用独立的 `MVT::iPTR` 值类型贯穿到 CC 分析、或参考其它需要"指针与整数分离"的成熟目标的做法）——具体机制由 subagent 判断，不预设实现路径。
2. **`DADAOCallingConv.td`**：`CC_DADAO` 增加指针类型的规则，分配到 RB bank 寄存器列表（`RB16..RB31`），且必须与整数类型规则**各自独立计数**（不能共享同一个参数序号槽位——例如 `f(int a, char *b, int c)` 里 `a`/`c` 走 `rd16`/`rd17`，`b` 独立走 `rb16`，不是 `rd16`/`rb17`/`rd18` 混排）。`RetCC_DADAO` 同理增加指针返回值走 `RB31`。
3. **`DADAOISelLowering.cpp`**：`LowerFormalArguments`/`LowerCall`/`LowerReturn`/`LowerCallResult` 里为指针类型的参数/返回值走 RB bank 寄存器类（`GPRB`）的 `CopyFromReg`/`CopyToReg`，不能直接照搬整数路径。
4. **回归验证不能有任何缺口**：
   - `python3 scripts/check_codegen_abi.py`：pointer params/pointer return 两条从 `INFO` 变成 `MATCH`。
   - `python3 tools/run_differential.py`：AGREE(3-way)/AGREE(4-way) 必须与当前基线（200/200，DIVERGE=0）完全一致——本任务是调用约定/寄存器分配层面的改动，不改变任何单条指令的语义，理论上不应该也不可能影响这个基线；如果发现有影响，说明改动方式有问题，需要停下来重新评估。
   - 全量 `llvm-lit tests/lit/E2E/`：重新构建 LLVM 后完整跑一遍，**列出所有变化**（新失败/新通过），不能笼统写"回归"。**明确预期**：一部分现有测试的汇编输出/寄存器分配会因为这个 ABI 改动而变化（这是预期中的、正确的变化，不是回归）——需要甄别"输出变了但语义仍然正确"（例如某个 `.test` 用 `CHECK:` 断言了具体寄存器号，这类需要更新 `CHECK` 行以反映新的正确寄存器分配）与"真的跑挂了"（这才是需要排查的真回归）。
   - **已知会受影响、需要同步更新的下游手写文件**（本任务不必修改这些文件本身，但必须在完成区里逐一列出每个文件具体哪里需要改、为什么，交给 ML-013a 处理）：
     - `tests/scripts/pico_stubs.s`：`_write(int fd, char *buf, int len)` 的 `buf` 参数（当前假设从 `rd17` 读取，ABI 改变后应改为从 `rb16` 读取——因为 RB bank 独立计数从 16 开始，`buf` 是"第一个 RB 参数"）；`_sbrk` 的返回值（当前 `ret rd0,0` + `addi rd31,...`，ABI 改变后指针返回值应改用 `rb31`）。
     - `.work/source/musl/arch/dadao/crt_arch.h`（ML-012a 落地，`call _start_c` 前用 `rb2rd rd16, rb1, 1` 把指针参数塞进 rd16——ABI 改变后应该直接 `rb2rb rb16, rb1, 1`，不再需要 bank 转换）。
     - `.work/source/musl/src/thread/dadao/__set_thread_area.s`（ML-011a 落地、ML-012a 修正为从 `rd16` 读指针参数——ABI 改变后应改回从 `rb16` 读，ML-011a 最初的写法反而是对的，只是当时后端还没实现）。
     - `tests/lit/E2E/tp_probe.test`（`set_tp_sub`/`get_tp_sub` 镜像上面这个文件，需要同步）。
     - 用 `grep` 在 `tests/`（不含 `.work/`）里搜索还有没有其它手写汇编/lit 测试涉及"编译产物↔手写代码之间传递指针参数或指针返回值"的边界，逐一列出。
   - `python3 scripts/manifest_check.py` 通过。
5. **关闭/更新 issue**：`docs/issues.yaml` 的 `dadao-callingconv-pointer-args-use-rd-bank-not-rb-bank` 标记 `resolved_by`；如果本任务过程中发现新的、独立的缺口（例如 CC 分析阶段区分指针类型这件事本身暴露了另一个此前未知的问题），照实新增 issue，不要归并进已有条目。

## 参考指针

- `docs/issues.yaml` `dadao-callingconv-pointer-args-use-rd-bank-not-rb-bank`（本任务要解决的问题的完整背景）
- `contracts/abi/spec.md §2.1`（参数传递规则权威定义）、`§3.1`（返回值规则）
- `llvm/lib/Target/DADAO/DADAOCallingConv.td`、`DADAOISelLowering.cpp`（`AnalyzeCallOperands`/`AnalyzeFormalArguments`/`LowerCall`/`LowerFormalArguments`/`LowerReturn`/`LowerCallResult` 的现有实现）
- `scripts/check_codegen_abi.py`（本任务验收的关键工具，目前把这条分歧打印成 INFO，需要在本任务后变成 MATCH）
- `code-agent/tasks/ML-012a-musl-crt-configure-e2e1.md`「架构师复核（ground-truth）」区（分歧被发现的完整过程、反汇编探针方法，可参照其"探测方法"复用于本任务的验证）
- `~/knowledge-graph/compiler-backend/04-isel-calling-convention.md`"调用约定的 CCAssignFn 模式"+"跨 bank 数据移动（多 bank 架构）"两节（多 bank ABI 设计的既有经验/陷阱清单）
- 已知受影响的下游手写文件清单见上"目标4"（不在本任务改，只需查清楚+报告）

## 完成区

**状态**：已完成

**修改文件**：

- `.work/source/llvm/llvm/lib/Target/DADAO/DADAOCallingConv.td`（`.work/llvm` 内 git commit `4d932e49ac64`）——`CC_DADAO` 新增 `CCIfPtr<CCAssignToReg<[RB16..RB31]>>` + `CCIfPtr<CCAssignToStack<8,8>>`，置于原有 `CCIfType<[i64],...]>` 规则之前；`RetCC_DADAO` 新增 `CCIfPtr<CCAssignToReg<[RB31]>>`，同理置于整数规则之前。
- `.work/source/llvm/llvm/lib/Target/DADAO/DADAOISelLowering.cpp`（同一 commit）——`LowerFormalArguments` 里虚拟寄存器类的判定从"按 `Function` 参数下标反查 `isPointerTy()`"改为"按 `VA.getLocReg()` 落在哪个 bank 反查"（`DADAO::GPRBRegClass.contains(VA.getLocReg())`），更健壮；顺带移除因此变为无用的 `const Function &F` 局部变量与 `#include "llvm/IR/Function.h"`。`LowerCall`/`LowerReturn`/`LowerCallResult` **未改动**——它们只对显式物理寄存器做 `CopyToReg`/`CopyFromReg`，在 SelectionDAG 层是 bank-agnostic 的，且 `DADAORegisterInfo::copyPhysReg` 早已支持跨 bank 物理寄存器拷贝（`RD2RB_ORRI`/`RB2RD_ORRI`），足以覆盖 live-in 拷贝插入等场景。
- `components/llvm/patches/0038-rb-bank-pointer-calling-convention.patch`（新增，`git format-patch` 从上述 commit 导出）+ `components/llvm/patches/series`（追加第 38 行）。
- `scripts/check_codegen_abi.py`——`parse_calling_conv()`/`check_calling_conv()` 改为分别解析 `CCIfPtr<CCAssignToReg<[...]>>`（指针）与 `CCIfType<[i64], CCAssignToReg<[...]>>`（整数）两条规则族（原实现把同一个 `CallingConv<[...]>` 里所有 `CCAssignToReg` 块的寄存器混在一个列表里返回，在只有一条规则族时够用，但两条规则族同时存在时无法区分"指针达标"与"整数达标"）；新增 pointer params/pointer return 的 MATCH/MISMATCH 判定（原来只有一条 INFO advisory、从未有过 MATCH 分支）。这个脚本严格说不属于"LLVM"，但它是本任务验收标准 1 明确要求"从 INFO 变成 MATCH"的工具本身，原实现里没有任何代码路径能产出 MATCH，不改这个脚本就无法达成验收标准 1，判断为任务范围内的必要改动（不是 musl/picolibc 下游文件）。
- `docs/issues.yaml`——`dadao-callingconv-pointer-args-use-rd-bank-not-rb-bank`：`status: open→closed`，`resolved_by: DL-069a`，追加收尾说明。

**未修改（按硬约束，仅报告见下）**：`tests/scripts/pico_stubs.s`、`.work/source/musl/arch/dadao/crt_arch.h`、`.work/source/musl/src/thread/dadao/__set_thread_area.s`、`tests/lit/E2E/tp_probe.test`。

**验收结果**（均为本人真实重跑，非估算）：

1. `python3 scripts/check_codegen_abi.py`：
   ```
   [MATCH      ] CallingConv  integer params rd16..rd31 [abi §2.1]
   [MATCH      ] CallingConv  integer return rd31 [abi §3.1]
   [MATCH      ] CallingConv  pointer params rb16..rb31 [abi §2.1]
   [MATCH      ] CallingConv  pointer return rb31 [abi §3.1]
   ...
   MATCH=23  OPEN-COMMIT=3  INFO=2  MISMATCH=0
   RESULT: PASS (no MISMATCH; OPEN-COMMIT/INFO are advisory)
   ```
   pointer params/pointer return 均从 INFO 变为 MATCH，达成验收标准 1。

2. `python3 tools/run_differential.py`：
   ```
   === AGREE(3-way)=200  AGREE(interp+QEMU, gem5-SKIP)=0  DIVERGE=0  HARNESS=6  QEMU-SKIP=0 ===
   === SAIL 4th column: AGREE(4-way)=200  Sail-SKIP(out-of-slice)=0  SAIL-DIVERGE=0 ===
   ```
   与改动前基线（3-way=200/4-way=200/DIVERGE=0）逐位一致，符合预期（纯调用约定改动不触及指令语义）。

3. 全量 `llvm-lit tests/lit/E2E`（重新构建 LLVM 后完整跑一遍，58 个测试，含 llvm-test-suite 子集）：
   ```
   Total Discovered Tests: 58
     Passed: 56 (96.55%)
     Failed:  2 (3.45%)
   Failed Tests (2):
     E2E :: malloc_hello.test
     E2E :: printf_hello.test
   ```
   **两个新失败**，均已定位根因、均是预期中的正确变化（详见"已知受影响下游文件"节，不是真回归）：
   - 两者都是唯二链接 `tests/scripts/pico_stubs.s` 的 lit 测试（`grep -l pico_stubs tests/lit/E2E/*.test` 只命中这两个）。
   - 反汇编确认：picolibc 编译产物（如 `memset(void *s,...)`、`my_putc`）现在正确地把指针参数放进 `rb16`（如 `stdout_min.c` 的 `_write(1, &ch, 1)` 调用点：`rd16=1`(fd,整数参数1)、`rb16=&ch`(指针参数1，独立计数)、`rd17=1`(len,整数参数2)）。而 `pico_stubs.s` 的手写 `_write` 桩仍按旧约定连续读 `rd16/rd17/rd18`（fd/buf/len 全挤在 RD bank），于是把 `len`(=1) 误读成 `buf` 地址、`rb16` 里的真实 `buf` 从未被读取——这正是任务背景描述的 ABI 分歧本身,是 ML-013a 待修的下游文件问题,不是本次改动引入的新 bug。
   - 其余 56 个测试（含全部 `llvm-test-suite/*` 子测试、`tp_probe.test`、`musl_crt0_auxv.test`、`musl_e2e_exit.test` 等所有涉及指针的既有测试）全部 PASS，零意外回归。`tests/lit/MC/Dadao` 14/14 PASS（MC 层编码测试，`rd16`等纯粹是任意寄存器操作数，与调用约定无关，未受影响）。
   - 无任何测试的 `CHECK:` 行断言了具体寄存器号（`grep "CHECK.*rd1[6-9]\|CHECK.*rb1[6-9]" tests/lit/E2E/*.test` 零命中），因此没有需要因寄存器分配变化而更新 `CHECK` 行的既有测试。

4. **已知受影响、需要 ML-013a 更新的下游手写文件**（逐一核实，未在本任务修改）：
   - `tests/scripts/pico_stubs.s`：`_write(int fd, char *buf, int len)` 需要把 `buf` 参数改为从 `rb16` 读取（当前从 `rd17` 读，第二条 `addi rd18, rd17, 0` / `addi rd18, rd17, 0` 一线相关三行都要重排：`fd`=整数参数1=`rd16`不变，`buf`=指针参数1=`rb16`（新增读取源），`len`=整数参数2=`rd17`不再是 `rd18`）；`_sbrk` 的返回值（`addi rd31, rd18, 0` 那一行——若 `_sbrk` 签名视为返回 `void*`，应改用 `rb31` 而非 `rd31`；需要 ML-013a 确认 `_sbrk` 在 picolibc 里的返回类型声明后再定具体改法）。
   - `.work/source/musl/arch/dadao/crt_arch.h`：`call _start_c` 前的 `rb2rd rd16, rb1, 1` 应改为 `rb2rb rb16, rb1, 1`（不再需要跨 bank 转换，直接同 bank 拷贝或干脆直接把 `rb1`（栈指针本身即地址）通过 `addi rb16, rb1, 0` 传入）。
   - `.work/source/musl/src/thread/dadao/__set_thread_area.s`：`rd2rb rb4, rd16, 1` 应改为 `rd2rb rb4, rb16, 1`？不对——目标寄存器 `rb4` 本身就是 RB bank，只是**源**操作数要从 `rb16` 读（不再是 `rd16`），指令本身从"跨 bank 拷贝"(`rd2rb`) 变为"同 bank 拷贝"(`rb2rb rb4, rb16, 1`)。ML-011a 最初的写法（从 `rb16` 读、用 `rb2rb`）反而是对的，只是当时后端还没实现 RB bank，ML-012a 才被迫改成从 `rd16` 读；本次改动后应该改回 ML-011a 最初的版本。
   - `tests/lit/E2E/tp_probe.test`：`set_tp_sub`/`get_tp_sub` 镜像上面这个文件的调用约定，需要同步把 `addi rd16, rd1, 0` / `call set_tp_sub` 改为把指针值放进 `rb16`（`get_tp_sub` 本身无参数，用 `rb2rd`从 `rb4` 读出到 `rd31` 不受影响）。
   - `tests/lit/E2E/musl_e2e_exit.test`：文件本身没有硬编码 `rd16`/`rb16` 的手写汇编（它只是 RUN 行 + 大段注释链接到 `.work/build/musl/lib/{crt1.o,libc.a}` 预构建产物），本任务改动不需要改这个文件的 RUN 行本身，但文件顶部注释里"1. DADAOCallingConv.td...实际上是走 RD bank...crt_arch.h 的 call _start_c 和 __set_thread_area.s 被更正为从 rd16 读"这段历史记录性文字，在 ML-013a 把 crt_arch.h/__set_thread_area.s 改回 RB bank、musl 重新构建 crt1.o/libc.a 后会变得过时——ML-013a 应同步更新这段注释（文档性质，非功能性）。
   - `grep -rl "rd1[6-9]"` 在 `tests/`（不含 `.work/`）里额外命中的文件逐一核实：`tests/lit/MC/Dadao/{rrrr.s,rrri.s,orrr.s}` 是纯 MC 编码往返测试，`rd16..rd20` 只是任意选取的寄存器操作数，与函数调用约定无关，**不在受影响范围**；`tests/lit/E2E/syscall_hello.test`、`tests/lit/E2E/mmap_probe.test` 用的是 DADAO 的 **trap/syscall ABI**（`rd16`=系统调用号、`rd17..`=参数），这是与函数调用约定完全独立的另一套约定（trap ABI 从未在 spec 里规定指针参数走 RB bank），**不在本任务范围/不受影响**；`tests/lit/E2E/Output/*.s` 是 lit 测试运行时生成的临时产物，不是源文件；`tests/scripts/crt0_auxv.s`（`musl_crt0_auxv.test` 用）已确认使用的是 `rb2rb rb16, rb1, 1` 等新约定写法（ML-008a 落地时已前瞻性地按 RB bank 写，未受本次改动影响，该测试本次全程 PASS）。

5. `python3 scripts/manifest_check.py`：`manifest validation: PASS`。

6. `docs/issues.yaml` `dadao-callingconv-pointer-args-use-rd-bank-not-rb-bank`：`status: closed`，`resolved_by: DL-069a`（`python3 scripts/check_issues.py` 确认 `ISSUE REGISTRY: PASS`）。未发现需要独立开新 issue 的问题（CC 分析阶段用 `ArgFlags.isPointer()` 区分指针与整数是 LLVM 现成机制，未暴露新的、独立的缺口；varargs 保存区仍是 RD-only 是既有缺口，已有独立 issue 覆盖，本任务未扩大也未修复它）。

**遗留问题**：

- `tests/scripts/pico_stubs.s`/`.work/source/musl/{crt_arch.h,__set_thread_area.s}`/`tests/lit/E2E/tp_probe.test`（+ musl_e2e_exit.test 的历史注释）需要 ML-013a 按上面第 4 点逐条更新；更新后 musl 需要重新构建 `crt1.o`/`libc.a`，`malloc_hello.test`/`printf_hello.test` 才能恢复 PASS。
- 非阻断的次要观察（subagent review 提出，判断为可选优化、非缺陷）：溢出场景下把一个指针类型的溢出参数存到栈时（`VA.isMemLoc()`），当前只有 `Pat<(store GPRD:$rdha, GPRB:$rbhb), (STO_RRII ...)>` 一条 store pattern，选择器会先插入一条 `rb2rd` 转换再 `sto`，多花一条指令；`DADAOInstrInfo.td` 里已经存在 `STO_RBRRII`（`op=0x4B`）但没有配套的 `Pat<(store GPRB:$rbha, GPRB:$rbhb), (STO_RBRRII ...)>`，补上可以省掉这条转换指令。已用 20+ 参数混合 int/pointer 的探针验证这只是一条多余指令、不影响正确性（详见下方审阅记录第6条），不阻塞本任务，留给后续任务按需优化。
- 本任务运行 `make check` 时发现 `check-wiki-drift` 报 `contracts/abi/spec.md`/`contracts/isa/spec.md` 引用的 wiki commit（`13a414da158d…`）与 `manifests/spec.lock.toml` 锁定的 commit（`9f378f4426e1…`）不一致——**与本任务无关的既有 drift**（本任务未改动 `contracts/`，`scripts/manifest_check.py` 单独跑是 PASS 的，任务验收标准里也没有要求 `make check` 整体通过），如实记录供架构师评估，不在本任务范围内处理。

## 审阅记录（subagent）

**判决 = 通过（Accepted）**

subagent 独立读取任务文件 + 本次 diff（`cd .work/source/llvm && git show HEAD`）+ `scripts/check_codegen_abi.py`/`docs/issues.yaml` 改动，未采信任何转述数字，全部自己重新执行命令核验：

1. **约束核对**：`.work/source/llvm` `git log --oneline` 确认新 commit 线性叠在既有历史（`d324a5db0956` ML-004d）之上，无 rebase/reset 痕迹；`git show --stat HEAD` 只改 `DADAOCallingConv.td`+`DADAOISelLowering.cpp` 两个文件，符合"只改 LLVM"；`components/llvm/patches/` 下 0001..0038 连续 38 个文件，`series` 尾部为新增一行，未见重排。**判定：符合约束。**
2. **CC_DADAO/RetCC_DADAO 规则与顺序**：确认 `CCIfPtr` 规则在 `CCIfType<[i64]>` 之前，顺序敏感性推理正确（CCState 命中第一条即止），`ArgFlags.isPointer()` 由 `SelectionDAGBuilder` 从原始 IR 类型统一设置，M1 范围（无 byval/sret/variadic 指针）内可靠。**判定：正确。**
3. **`LowerFormalArguments` 寄存器类判定**：`GPRBRegClass.contains(VA.getLocReg())` 比旧的按 Function 参数下标反查更健壮；检查了 varargs 保存区仍硬编码 RD-only 寄存器列表，判定这是**既有缺口**（已有独立 `Varargs` issue 覆盖），与本次改动不冲突、未被本任务放大。**判定：pre-existing 缺口，非本任务引入的风险。**
4. **`const Function &F` 移除**：核实文件内无其它遗漏引用；发现 `#include "llvm/IR/Function.h"` 变为可能未使用（非阻断次要观察）。**处置：✅已修**——已移除该 include，重新构建（`ninja llc clang`，15/15 全部成功）+ 复跑 `check_codegen_abi.py`（MATCH=23/MISMATCH=0）+ `run_differential.py`（AGREE 3-way/4-way=200/DIVERGE=0）+ `llvm-lit tests/lit/E2E`（56 PASS/2 FAIL，与移除前一致）确认无影响，并 `git commit --amend` 折入同一 commit、重新 `git format-patch` 覆盖 `0038-rb-bank-pointer-calling-convention.patch`。
5. **`check_codegen_abi.py` 正则健壮性**：读完整脚本确认 `PTR_RULE`/`INT_RULE` 两条正则互不干扰（`CCAssignToStack` 行不含 `CCAssignToReg` 不会被误吃）。**判定：本次改动范围内可靠。**
6. **独立复跑**（subagent 亲自执行）：`check_codegen_abi.py`→`MATCH=23/MISMATCH=0`；`run_differential.py`→`AGREE(3-way)=200/AGREE(4-way)=200/DIVERGE=0`；`llvm-lit tests/lit/E2E`→`56 PASS/2 FAIL`（`malloc_hello.test`/`printf_hello.test`，读 `pico_stubs.s` 源码确认根因）；`tests/lit/MC/Dadao`→14/14 PASS；`manifest_check.py`/`check_issues.py`→均 PASS；额外用独立探针（`int a,char *b,int c,char *d,long e` 混合参数 + 指针返回函数）编译反汇编，确认 `a=rd16,c=rd17,e=rd18` / `b=rb16,d=rb17`（两个 bank 各自独立连续计数，无交叠）、指针返回值落 `rb31`，与 spec §2.1/§3.1 完全吻合；额外 grep 确认 `tests/scripts/crt0_auxv.s` 已按新约定书写、`musl`/`pico_stubs.s` 源文件未被本任务误改。

| finding | 处置 | 改了什么 | 复验证据 |
|---|---|---|---|
| varargs 保存区仍 RD-only（既有缺口） | ⏸不改（不在本任务范围） | 无改动 | 已有独立 `Varargs` issue 覆盖，本任务未扩大也未修复，判断为正确的范围界定 |
| `#include "llvm/IR/Function.h"` 可能未使用 | ✅已修 | `DADAOISelLowering.cpp` 移除该 include，`git commit --amend` 折入同一 commit，重新导出 `0038-rb-bank-pointer-calling-convention.patch` | 重新 `ninja llc clang` 15/15 成功；`check_codegen_abi.py` MATCH=23/MISMATCH=0；`run_differential.py` AGREE 3-way/4-way=200/DIVERGE=0；`llvm-lit tests/lit/E2E` 56 PASS/2 FAIL（与修改前一致） |
| 溢出指针参数存栈多一条 `rb2rd` 转换指令（可选优化） | ⏸延后（非缺陷，留后续任务） | 无改动 | 20+ 参数混合探针验证仅多一条指令，语义正确 |

**AC 结论**：所有 finding 均已处置（1 项已修+复验，2 项判定为范围外/非缺陷并附证据），无遗留未处置项，完成区状态"已完成"与本判决一致。

## 架构师复核（ground-truth）

**独立验证方法**：不采信完成区/subagent 判决，从 git 状态开始逐项重跑，本任务是本 session 里风险最高的一次改动（第一次真正动 LLVM CodeGen 核心逻辑），复核力度按最高标准执行。

- `git status`（主仓库 + `.work/source/{llvm,qemu,gem5,musl,llvm-test-suite}`）：仅预期文件改动，`.work/llvm` 干净单提交 `4d932e49ac64` 落在 `d324a5db0956`（ML-004d）之上，其余组件全干净，无孤立进程。
- 逐行读 `DADAOCallingConv.td`/`DADAOISelLowering.cpp` diff：`CCIfPtr` 规则放在 `CCIfType<[i64]>` 之前（顺序敏感性验证正确）；`LowerFormalArguments` 改用 `GPRBRegClass.contains(VA.getLocReg())` 判定 bank，比原来按 Function 参数下标反查更健壮；`LowerCall`/`LowerReturn`/`LowerCallResult` 确认未改动且不需要改动（只做显式物理寄存器 `CopyToReg`/`CopyFromReg`，bank-agnostic）。
- **独立重新编译**：`ninja -C .work/build/llvm clang llc lld llvm-objcopy` 干净构建成功（无 error）。
- **独立复现 `check_codegen_abi.py`**：`MATCH=23 MISMATCH=0`，`pointer params rb16..rb31`/`pointer return rb31` 均 MATCH（此前是 INFO）。
- **独立复现差分**：`AGREE(3-way)=200/AGREE(4-way)=200/DIVERGE=0`，与改动前基线逐位一致。
- **独立重跑全量 E2E**：`llvm-lit tests/lit/E2E/` → **56 PASS / 2 FAIL**（`malloc_hello.test`/`printf_hello.test`），与声称完全一致；`tests/lit/MC/Dadao` → 14/14 PASS。
- **独立复现新失败的根因**：单独跑 `malloc_hello.test` 的 QEMU 步骤，确认程序真的崩溃（QEMU 掉进 monitor 提示符，非单纯退出码不对）——与"pico_stubs.s 的 `_write` 桩仍按旧约定连续读 rd16/rd17/rd18，把 `len` 误当 `buf` 地址使用"这个根因描述吻合（用错误地址做内存访问会导致真实 fault）。
- **独立设计并跑了一个针对 §2.3"共享溢出区"规则的专项探针**（比 subagent 自己的"20+参数混合探针"更贴近 spec 原文举的例子）：`f(16个int, 16个pointer, 溢出int r, 溢出pointer s, 溢出int t)`，反汇编调用点确认 `r→sp+0`/`s→sp+8`/`t→sp+16`——与 `contracts/abi/spec.md §2.3` 给出的"Cross-bank overflow example"逐字节吻合，证明两个独立 bank 共享同一个 `CCState` 栈偏移计数器这个非显然的正确性声明经得起最刁钻的边界测试，不是巧合。同时独立确认了 subagent 自陈的"次要观察"（溢出指针参数在被调方要多一条 `rb2rd` 转换才能 `sto` 到栈上，因为 `STO_RBRRII` 缺配套 pattern）在反汇编里确实存在，判断为真实、无害的次要低效，不影响正确性。
- `python3 scripts/manifest_check.py` / `check_issues.py`：均 PASS（Open 21/Closed 30/Total 51，`dadao-callingconv-pointer-args-use-rd-bank-not-rb-bank` 确认 `status: closed`/`resolved_by: DL-069a`）。
- **独立验证本任务新增 patch（0038）的可重放性**：`git clone` 独立副本 + `checkout --detach` 到其直接前置 commit `d324a5db0956` + `git am 0038-....patch` → 干净应用成功。
- **额外发现（与 DL-069a 无关，独立记录）**：尝试验证 LLVM **全部 38 条 patch** 从裸 pin commit（`ca7933e47d3a3451d81e72ac174dcb5aa28b59d1`）开始完整重放时，在**第 5 条**（`0005-dadao-asmparser.patch`，远早于本 session 任何工作、与 DL-069a 无关）报 `error: corrupt patch at line 447`，用 `scripts/apply_series.py` 同款 `git am` 调用复现，非我操作有误。这是一个此前从未被验证过的"完整从零重放"路径（此前每个任务都只验证过"新增的最后一条 patch 能否接到当前已有状态之上"，从未有人真正验证过全部 38 条从裸 pin 开始重放），可能是老早的 patch 文件本身格式问题（大 diff 里可能有一行以"From "开头触发 mbox 解析歧义）。**不影响 DL-069a 验收**（其自身 patch 独立可重放），但建议架构师后续另开一个基础设施任务核实/修复，避免"这条 patch series 理论上不可从零复现"这个隐患像 `fetch.py` 那次一样被搁置太久。

**结论**：这是本 session 风险最高的一次 LLVM CodeGen 改动，独立复核（含一个针对 spec §2.3 共享溢出区规则的专项边界探针，比原始验收测试更刁钻）确认实现正确、差分基线不受影响、唯二新失败精确对应预期中的下游文件待更新（非真回归）。**DL-069a 验收通过**——RB bank 指针调用约定已在 LLVM 后端真正实现，`contracts/abi/spec.md §2.1/§3.1` 与后端行为首次一致。下一步：ML-013a 更新 4 个已识别的下游手写文件（`pico_stubs.s`/musl `crt_arch.h`/`__set_thread_area.s`/`tp_probe.test`），恢复 `malloc_hello.test`/`printf_hello.test`。
