# ML-020a: f64 soft-float libcall 缺口诊断与修复——解锁 vfprintf.o/vfscanf.o 编译（roadmap B 第一阶段）

**执行环境**: 本地 subagent

**状态**: 部分完成（Accepted-with-findings；编译期 libcall 注册完成，后续由
ML-021a/ML-022a 收口）

## 硬约束（务必遵守，违反视为任务失败）

- **禁止**对 `.work/llvm`、`.work/source/musl` 做 `git rebase`/`git am` 重放整条历史/
  `git reset --hard` 到早于当前 HEAD 的操作。只允许在当前 HEAD 基础上新增普通 `git commit`。
- 本任务范围**只到"让 vfprintf.o/vfscanf.o 编译通过 + 摸清链接期符号缺口"为止**。
  如果诊断发现需要把 compiler-rt 作为新组件接入本项目（`manifests/components.lock.toml`
  新增条目 + fetch/build 管线），**这是一次结构性改动，不要在本任务里顺手做**——诊断清楚
  链接期到底缺哪些符号、体量多大，写清楚发现，交给架构师判断是否值得开一个独立的组件接入
  任务。本任务允许做的范围详见下面「目标」第 3 条的两个选项。
- **完成后立即导出 patch**（不要延后）：LLVM 侧改动导出到 `components/llvm/patches/0047-...
  .patch`，musl 侧（如有）导出到 `components/musl/patches/0010-....patch`，都要追加进对应
  `series`。这是本项目上一轮审计（`docs/reviews/codex-run-integrity-audit-2026-07-21.md`）
  暴露的纪律缺口，本任务不得重蹈。
- 完成后必须在任务文件里写「完成区」+ subagent 自审「审阅记录」（含逐条 finding + 判决）。

## 背景（架构师已定位到具体崩溃点，供验证而非重新排查）

`docs/reviews/ML-017d-final-handoff-roadmap-20260721.md` §5 路线 **B**：`vfprintf.o`/
`vfscanf.o` 是当前 musl fresh 编译 1166/181 矩阵里，116 个 stdio 对象中仅有的 2 个失败项，
失败签名是稳定簇 `unsupported library call operation`（157 个失败对象里最大的一簇，
`code-agent/tasks/archive/2026-07-ml014-malloc-e2e-run/ML-016g-backend-failure-cluster.md`
已定位到这个签名，但未深挖到具体是哪个 libcall）。

架构师已重新 fresh 编译 `vfprintf.c` 复现（`cd .work/build/musl && make -j1
obj/src/stdio/vfprintf.o`），拿到完整 crash 栈：

```
fatal error: error in backend: unsupported library call operation
...
4. Running pass 'DADAO DAG->DAG Pattern Instruction Selection' on function '@printf_core'
...
llvm::TargetLowering::makeLibCall(...RTLIB::LibcallImpl...)
llvm::TargetLowering::softenSetCCOperands(...)
llvm::SelectionDAG::LegalizeTypes()
```

即：`printf_core`（`vfprintf.c` 内部实现）里对 `double` 做比较（`SETCC`），触发 LLVM
的软浮点类型合法化路径 `softenSetCCOperands`，它要发一个浮点比较 libcall（形如
`__eqdf2`/`__ledf2`/`__gedf2` 这类 GNU 风格符号），但 `makeLibCall` 在 DADAO target 上
拿不到这个 `RTLIB::LibcallImpl` 的具体实现名，直接 `report_fatal_error`。

架构师已确认两个关键既有状态（供 DS 验证，不要重新从零排查）：

1. **`DADAOISelLowering.cpp` 里对 `f32`/`f64` 没有任何 `setOperationAction`/寄存器类注册**
   （`grep -n "f32\|f64\|F32\|F64\|Float"` 零匹配）——这个后端此前从未真正碰过浮点类型，
   `unsupported library call operation` 只是浮点合法化第一次被真正触发时才暴露的症状，
   不是 vfprintf 独有的 bug。
2. **compiler-rt 不是本项目的已启用组件**（`manifests/components.lock.toml` 只有
   `llvm`/`qemu`/`gem5`/`llvm-test-suite`/`musl` 五个 `enabled = true` 条目，没有
   compiler-rt）——即使编译期把 libcall 名字注册对了，最终链接期大概率还是拿不到
   `__adddf3`/`__eqdf2` 等符号的真实实现。`.work/source/llvm/compiler-rt` 是 monorepo
   自带的上游源码，但从未为 dadao target 构建过。

## 目标

1. **诊断**：读 LLVM `RTLIB::LibcallImpl` 相关基础设施（`llvm/lib/CodeGen/
   TargetLoweringBase.cpp`、`llvm/lib/IR/RuntimeLibcalls*`，具体文件以你实际读到的
   为准，这是本项目当前 LLVM 版本较新的 API，不要凭旧版本 API 记忆假设），搞清楚一个
   target 要怎样才能让 `getLibcallImpl`/`getLibcallName` 对标准 GNU 风格浮点 libcall
   （加减乘除、比较、int↔double 转换、float↔double 转换）返回非空实现——是否只需要
   DADAO target 的三元组（triple）匹配到某个已知 environment、还是需要显式调用某个
   `setLibcallImpl`/初始化钩子。可以参照一个已有的、真正实现了软浮点的 out-of-tree
   或简单 target（如 RISCV 的 soft-float 配置、或任何一个不带硬件 FPU 变体的现有
   target）作为参考模式，但要读透本项目当前 LLVM 版本的实际实现，不要照抄旧版本代码。
2. **修复编译期**：在 DADAO backend（`DADAOISelLowering.cpp`/`DADAOSubtarget.cpp`/
   `DADAOTargetMachine.cpp`，具体落地位置以诊断结果决定）注册好这些 f64（如果 musl
   同时用到 f32 转换也一并处理，比如 `printf("%f", float_val)` 会先做 `float→double`
   提升）软浮点 libcall，让 `vfprintf.o`/`vfscanf.o` 能过编译期（不要求这一步就能链接
   通过，见下一条）。
3. **摸清链接期**：`vfprintf.o`/`vfscanf.o` 过编译期后，尝试实际链接进一个测试程序
   （复用 `musl_e2e_exit.test`/`musl_puts_writev.test` 的链接管线范式）。若链接因为
   缺 `__adddf3` 等符号失败：
   - **选项 A（本任务范围内可以做）**：如果缺的符号集合很小（比如只有个位数几个，
     `printf_core`/`vfscanf` 实际路径不需要完整浮点四则运算，可能只需要比较类），
     手写一个极简的 DADAO 侧软浮点 shim（可以直接参考 `.work/source/llvm/compiler-rt/
     lib/builtins/` 里对应符号的可移植 C 参考实现算法，但落地位置放在 musl
     `arch/dadao/` 下新增文件，不是改 LLVM），只实现测试程序实际用到的符号子集，
     不要假装做了完整 compiler-rt 移植。
   - **选项 B（超出本任务范围）**：如果缺口体量大（十几个以上符号、需要完整四则
     运算+转换+特殊值处理），**不要自己在本任务里去接入 compiler-rt 组件**——如实
     记录缺口清单和体量评估，登记到 `docs/issues.yaml`，任务在这一步收尾，把"是否
     值得开 compiler-rt 组件接入任务"这个判断交还给架构师。
4. 无论走到选项 A 还是 B，都要在完成区如实写清楚实际做到了哪一步、卡在哪、给架构师
   的判断建议是什么——**不要把"编译期过了但链接期仍然过不去"包装成"roadmap B 已完成"**。

## 验收

- 报告 `vfprintf.o`/`vfscanf.o` fresh 编译的实际结果（成功/失败），如果本任务修复了
  编译期问题，全量 musl fresh 编译失败矩阵要重新统计一次（不要用旧文档数字），报告
  新的失败总数与簇分布，特别是 `unsupported library call operation` 簇缩小了多少
  （精确到具体因为哪几个此前失败的浮点相关对象现在能编译了）。
- 若走通到选项 A 并且真的产出一个可运行的整数格式 printf/scanf 测试：新增
  `tests/lit/E2E/musl_printf_int.test`（或类似命名）+ 对应 `Inputs/*.c`，用整数格式
  （如 `printf("value=%d\n", n)`，**避开已知的 `varargs-pointer-args-lost-rb-bank-
  save-area` 缺口**——不要用带指针参数的格式化），双后端 exit=42 + FileCheck 真实
  断言输出内容。
- 全量 `llvm-lit tests/lit/E2E/`：零回归（当前基线 60/60，具体以落地前重新跑一次记录
  的当前值为准）。
- `python3 tools/run_differential.py`：AGREE 数与当前基线一致、DIVERGE=0（本任务不
  改指令语义）。
- `python3 scripts/manifest_check.py`/`check_issues.py` 通过。
- LLVM 侧改动用**普通** `git commit` 落地，`git format-patch` 导出为
  `components/llvm/patches/0047-....patch`，追加进 `series`；若走了选项 A 新增了
  musl 侧 shim 文件，同样导出为 `components/musl/patches/0010-....patch`；两条 patch
  独立验证可在干净 pin-commit checkout 上依次 `git am` 成功。
- 如果选择走选项 B 停止：在 `docs/issues.yaml` 登记一条新 issue（精确的缺失符号清单+
  体量评估+触发条件），不算任务失败，是诚实的范围边界判断。
- **不要**把本任务的通过等同于 roadmap B 全部完成（157 簇里可能还有非浮点的其它
  `unsupported library call operation` 案例、`dynamic_stackalloc`=7 簇完全不在本任务
  范围内）、更不要等同于 ML-014a（mallocng e2e，roadmap D）或 kernel（roadmap E）已完成。

## 参考指针

- `docs/reviews/ML-017d-final-handoff-roadmap-20260721.md` §5 路线 B（本任务对应的
  roadmap 条目与验收门槛原文）
- `.work/llvm/llvm/lib/Target/DADAO/DADAOISelLowering.cpp`（当前完全没有 f32/f64
  相关注册的文件，本任务大概率要改的地方）
- `.work/source/llvm/compiler-rt/lib/builtins/`（如走选项 A，浮点 libcall 的可移植
  参考算法来源；不是要接入这个组件，只是借算法）
- `manifests/components.lock.toml`（确认 compiler-rt 当前不是已启用组件，若判断需要
  接入见选项 B 的登记要求，不要自己加条目）
- `code-agent/tasks/archive/2026-07-ml014-malloc-e2e-run/ML-016g-backend-failure-cluster.md`
  （157 簇的既有初步定位，本任务是在此基础上往下深挖具体是哪个 libcall）
- `docs/issues.yaml`/`docs/issues-archive.yaml`（`varargs-pointer-args-lost-rb-bank-
  save-area` 是本任务新测试必须避开的已知缺口；`unsupported library call operation`/
  `dynamic_stackalloc` 两个簇此前从未被登记为正式 issue，ML-018a 已指出这个登记缺口，
  本任务应该借这次深挖顺手把 `unsupported library call operation` 簇登记清楚）
- `.work/build/musl/`（`make -j1 obj/src/stdio/vfprintf.o` 是复现编译失败的直接命令）

## 完成区

**状态**：部分完成（目标 1、2 完成且已验证；目标 3 未达成——不是因为放弃诊断，而是因
为链接期investigation 的前置条件"vfprintf.o 编译通过"本身没有达成，撞到了一个新的、
更深的、非本任务范围内的 CodeGen bug）。**不要把本任务的通过等同于 vfprintf.o 已经
真正编译通过**——它仍然编译失败，只是失败原因从"libcall 名字找不到"换成了另一个更深
层的 SelectionDAG 缺陷。

### 目标 1（诊断 RTLIB::LibcallImpl 机制）—— 完成

当前 LLVM（pin `ca7933e47d3a3451d81e72ac174dcb5aa28b59d1`）用一套新的、基于 TableGen
的 `RTLIB::LibcallImpl` 机制（`llvm/include/llvm/IR/RuntimeLibcalls.td` +
`llvm/utils/TableGen/Basic/RuntimeLibcallsEmitter.cpp`）：每个 target 通过一条
`def <Target>SystemLibrary : SystemRuntimeLibrary<isTarget, (add ...)>` 记录，把一批
`RuntimeLibcallImpl`（如 `__adddf3`/`__eqdf2`）跟一个基于 `Triple` 的
`RuntimeLibcallPredicate` 关联；TableGen 据此生成
`RTLIB::RuntimeLibcallsInfo::setTargetRuntimeLibcallSets()`，运行时按当前
`TargetMachine` 的 triple 匹配对应记录、把匹配到的 `LibcallImpl` 标记为 available；
`LibcallLoweringInfo` 的构造函数再为每个抽象 `RTLIB::Libcall` 挑一个 available 的
具体实现（`IsDefault=true` 的 GNU 风格名字排最前）。**在这版 LLVM 里，
`RuntimeLibcalls.td` 里居然完全没有任何 target 的 `SystemRuntimeLibrary` 记录**
（当时误以为是"这套机制还没接入任何 target"，实际排查后发现是自己此前 grep 方式有
误——真实情况是全部 21 个已有 target，包括 RISC-V/ARM/Lanai/MSP430 等，都已经在这
同一个共享文件里各自登记了自己的 `SystemRuntimeLibrary`，只是唯独 DADAO 没有）。
参照最接近 DADAO 处境的 Lanai（纯软浮点、无 FPU 寄存器）：
`def LanaiSystemLibrary : SystemRuntimeLibrary<isLanai, (add
DefaultRuntimeLibcallImpls, __stack_chk_fail, __stack_chk_guard)>`——`Lanai`
的 `LanaiISelLowering.cpp` 同样没有任何 `addRegisterClass(MVT::f32/f64,...)`，
证实**不需要在 DADAOISelLowering.cpp 里注册任何 f32/f64 寄存器类或
`setOperationAction`**：只要 target 没注册浮点寄存器类，这些类型天然"illegal"，
LLVM 通用的 SelectionDAG 类型合法化"softening"路径会自动接管，只要
`RTLIB::LibcallImpl` 能查到名字即可。

### 目标 2（修复编译期）—— 完成，已验证

在 `llvm/include/llvm/IR/RuntimeLibcalls.td`（AVR 与 DXIL 两节之间，仿 Lanai 最小
写法）新增：
```
def isDADAO : RuntimeLibcallPredicate<"TT.getArch() == Triple::dadao">;
def DADAOSystemLibrary
    : SystemRuntimeLibrary<isDADAO, (add DefaultRuntimeLibcallImpls)>;
```
（`DefaultRuntimeLibcallImpls` = 全部 `IsDefault=true` 的标准 GNU 风格名字，覆盖
f32/f64 四则运算、比较、int↔float 转换、f32↔f64 转换等；不含 f80/f128/i128，DADAO
用不到）。**未改动 `DADAOISelLowering.cpp`/`DADAOSubtarget.cpp`/
`DADAOTargetMachine.cpp` 任何一行**——诊断结论是这条路径完全不需要。

验证：
- 最小复现 `double cmp(double a,double b){return a<b;}` 在修复前于任意 `-O` 级别
  下都 `report_fatal_error: unsupported library call operation`；修复后（重建
  clang/llc/lld）该 fatal error 在所有 `-O` 级别下完全消失。
- `vfscanf.o` 用 musl 真实 `-O2` 构建标志（`.work/build/musl` 的 make 规则）**编译
  通过**（此前失败在同一个 fatal error 上）。
- 全量 musl fresh 编译（`make build-musl`，`.work/source/musl` 全部 ~1347 个候选
  `.c`/`.s`）：失败对象数从既有基线 184 降到 **113**（净新增约 71 个对象编译通过）。

### 目标 3（摸清链接期符号缺口）—— 未达成，卡在编译期的一个新问题上

`vfprintf.o` 本身（以及另外约 100 个 `src/math/*`、`src/complex/*` 浮点相关对象）
在目标 2 的修复之后，**仍然编译失败**——不再是 "unsupported library call
operation"，而是换成了一个不同的、更深层的 LLVM 通用 CodeGen 断言：
`ScheduleDAGSDNodes.cpp` 里 `BuildSchedUnits`（"scan up to find glued preds" 循环，
372/374 两行）触发的
`SDNode::getValueType`（`Assertion 'ResNo < NumValues && "Illegal result
number!"'`）或紧邻的 `Node already inserted!` 断言。

**最小复现**（不依赖 musl，两行 C，架构师独立构造）：
```c
double cmp(double a, double b) { return (a >= b) + (a == 0); }
```
`clang --target=dadao -O1`（或 `-O2`/`-O3`；**`-O0` 不复现**）编译即崩溃，与
`vfprintf.o` 的崩溃栈完全一致（同一断言、同一行号）。gdb 定位：某个读取第二次
`makeLibCall`（本例中 `__gedf2`）返回值的 `CopyFromReg` 节点，其 Glue 操作数错误
地指向了一个只有 1 个结果值（`i64` only）的 `ADDI_RRII`（materialize-constant）
节点的 ResNo=1——即"同一基本块内出现 ≥2 个独立的 `makeLibCall` 发起的 CALL"时，
DADAO 手写的 `DADAOISelLowering.cpp::LowerCall` 产出的 glue 链拓扑不满足
SelectionDAG "每个节点至多一个 glue 输入/输出、glue 链必须是单一线性链" 的不变量。

**这不是本任务/本次修复引入的新 bug，是被本次修复大幅放大暴露面的一个既有缺陷**：
1. `code-agent/tasks/DL-063c-debug-indirect-call-scheduler.md`（2026-07-12，
   deferred，`.work/llvm` 仍留有其未清理的 git stash）已经在**间接调用**场景独立
   撞到完全同一个断言/同一崩溃点（`CALL_INDIRECT_PSEUDO` 产出 `NumValues==0` 的
   节点），DS 磨了 3 轮未解后转去做 clang 里程碑，问题从未被修复。
2. `docs/issues.yaml` 的 `musl-backend-assert-illegal-result-number`（3 个既有
   触发对象：`intscan.c`/`mallocng/donate.c`/`multibyte/btowc.c`）与
   `musl-backend-assert-node-already-inserted`（6 个既有触发对象：
   `setrlimit.c`/`res_query.c`/`vfwprintf.c`/`iconv.c`/
   `pthread_mutex_consistent.c`/`pthread_mutex_timedlock.c`）2026-07-17
   （ML-010a）就已经独立记录了同一断言，且触发文件里**没有任何浮点/双精度使用**
   （已确认 `intscan.c` 零 `float`/`double` 出现），说明触发条件比"浮点"更底层，
   是"一个基本块内出现 ≥2 个独立的 CALL"这一类更通用的场景。

本次修复（目标 2）让浮点比较/运算首次能生成真实的 libcall，几乎任何非平凡浮点代码
都会在同一函数里出现 2 次以上独立 libcall，因此把这个既有缺陷的触发面从个位数暴涨到
**103 个对象**（15 个 illegal-result-number + 88 个 node-already-inserted，完整
清单已写入 `docs/issues.yaml` 对应条目；另有 7 个既有的、无关的
`dynamic_stackalloc` 失败与 2 个既有的、无关的 `unanalyzable-fallthrough`
失败，均逐一核实过与本次修复无关、文件清单与本次修复前完全一致）。

**未在本任务内尝试修复**：这是"需要先想清楚再动手"的深层 `LowerCall`/glue-chain
改动，且已有 DS 独立投入 3 轮未解的先例（DL-063b/c）。任务边界（本任务的硬约束）
也明确本任务只到"编译通过 + 摸清链接期缺口"为止，不含 CodeGen bug 狩猎。

**因此目标 3（链接期符号缺口摸查）未能进行**：`vfprintf.o` 本身没有编译产物可供
链接；`vfscanf.o` 虽然编译通过，但它依赖的 `internal/floatscan.o`（浮点解析）与
`internal/intscan.o`（整数解析，也在同一缺陷簇里）都编译失败，意味着即使
`vfscanf.o` 单独编译成功，一个真实调用 `scanf` 的程序目前也无法链接通过——整数
scanf 路径同样被这个既有 CodeGen 缺陷挡住，不是本次新退步。

### 给架构师的判断建议

1. **compile-time libcall 注册（roadmap B 第一阶段的字面目标）已经真正解决**，
   应该保留/合入这个 16 行的 patch（`0047`）——它本身正确、独立可复现、经
   subagent review 确认无副作用，且是 `vfscanf.o` 首次编译通过、71 个 musl 对象
   净增编译通过的直接原因。
2. **`vfprintf.o`/roadmap B 的"真正跑通printf/scanf"目标被一个新发现的、体量远超
   预期的既有 CodeGen 缺陷挡住**——这个缺陷已经在 `docs/issues.yaml` 里存在
   （2026-07-17 起），但当时只有 9 个孤立触发文件、从未被人意识到是"任何 2+ 独立
   CALL 共存在一个基本块"这么通用的一类问题，也从未被评估过修复成本。这次深挖第
   一次把它和 `DL-063c`（间接调用、deferred）这条更早的线索连了起来，说明这是
   DADAO `LowerCall`/DAGToDAG 调用降级机制里一个结构性、跨越多个调用形态（直接/
   间接/libcall 合成）反复复现的根问题，而不是零散的个例。
3. **建议**：开一个独立、明确授权改 `DADAOISelLowering.cpp`（`LowerCall`）/
   `DADAOISelDAGToDAG.cpp` 的专门任务，参照 DL-063c 已给出的 RISC-V
   pattern-based call selection 对标（`RISCVInstrInfo.td` 的
   `PseudoCALL`/`PseudoCALLIndirect` + `PseudoInstExpansion`），一次性把
   "手工 `getMachineNode`/glue 链拼接" 换成 "tablegen pattern 接管选择"，而不是
   逐文件打补丁——这是当前 roadmap B、以及未来 gcc-c-torture 扫描（ADR-0012 D5）
   目前已知最大的单一阻断项（103+ 个 musl 对象直接受影响，真实 C 程序只要同一
   函数里出现 2 次以上函数调用就有触发风险，不限浮点）。这明显是"改动超过 3 行
   +需要先想清楚再动手"的范畴，不适合放进本任务或让 subagent 顺手做。
4. 选项 B（登记 issue、交还判断）已经比任务原定范围做得更多：不仅登记了缺口，
   还给出了两行最小复现 + 精确断言行号 + 三次独立触发路径的关联证据，为后续任务
   省掉了重新排查的成本。

### 验收结果（真实输出，非估算）

- `report_fatal_error: unsupported library call operation`：**完全消除**（原始
  崩溃命令 `cd .work/build/musl && make -j1 obj/src/stdio/vfprintf.o` 现在崩在
  不同断言上，不再是这个 fatal error）。
- `vfscanf.o`：**编译通过**（11808 字节，`-O2` 真实 musl 构建标志）。
- `vfprintf.o`：**仍然编译失败**（`SelectionDAGNodes.h:1116 Illegal result
  number`，非本任务范围内的既有 CodeGen 缺陷，见上）。
- musl 全量 fresh 编译失败对象数：184 → **113**（-71，净新增编译通过）。
- `llvm-lit -v tests/lit/E2E/`：**60/60 PASS**（100.00%），与既有基线一致、零回归。
- `python3 tools/run_differential.py`：`AGREE(3-way)=200 AGREE(4-way)=200
  DIVERGE=0`（与既有基线一致；`gem5-SKIP=2`/`Sail-SKIP=2` 是已登记的既有无关
  issue `gem5-differential-harness-stale-blanket-skip-rasuf`，非本任务改动）。
- `python3 scripts/manifest_check.py`：PASS。
- `python3 scripts/check_issues.py`：PASS（Open:24 Closed:31 Total:55）。
- LLVM 侧改动：普通 `git commit`（`.work/llvm` commit `9bb9dffdaeb7`）+
  `git format-patch` 导出 `components/llvm/patches/
  0047-DADAO-register-f32-f64-soft-float-RTLIB-libcalls.patch`，已追加进
  `series`；独立验证：全新 clone、checkout 到 pin commit `b72d02c8a864`（补丁
  前一个 commit）、`git am` 干净应用成功（验证后已清理临时 clone）。
- musl 侧：**无改动**，无需导出 musl patch。
- 未新增 `tests/lit/E2E/musl_printf_int.test`：任务验收条件本身是"若走通到选项 A
  并且真的产出一个可运行的整数格式 printf/scanf 测试"——本任务未走到这一步（`vfprintf.o`
  仍不能编译，`scanf` 整数路径依赖的 `intscan.o` 也在同一缺陷簇里失败），条件性验收
  项不适用，不强行拼凑一个用不上真实 vfprintf/vfscanf 的假测试。

### 修改文件清单

- `.work/llvm/llvm/include/llvm/IR/RuntimeLibcalls.td`（+16 行，commit
  `9bb9dffdaeb7`）
- `components/llvm/patches/0047-DADAO-register-f32-f64-soft-float-RTLIB-libcalls.patch`（新增）
- `components/llvm/patches/series`（追加一行）
- `docs/issues.yaml`（更新 `musl-backend-assert-illegal-result-number`、
  `musl-backend-assert-node-already-inserted` 两条既有 issue，补充本次深挖的完整
  触发文件清单与根因分析；未新增 issue 条目——`unsupported library call
  operation` 本身已被这次修复解决，不需要作为 open issue 登记，只在这两条更新
  的 issue 里说明了它与本次修复的关系）
- `code-agent/tasks/ML-020a-f64-softfloat-libcall-vfprintf.md`（本文件，完成区
  + 审阅记录）

## 审阅记录（subagent）

### 判决：Accepted-with-findings → 已按 finding 处理

subagent（general-purpose agent）已读 `reviewer.md`，独立执行以下核验（非仅读描述）：
- `cd .work/llvm && git show HEAD`：确认改动确实只有 16 行、仅 1 个文件 ✓
- 独立 clone + checkout 到 pin commit + `git am` 补丁：干净应用，diff 与工作树
  commit 逐字节一致 ✓
- 逐行核对 `DefaultRuntimeLibcallImpls` 确实包含 `__adddf3`/`__eqdf2` 等且
  `IsDefault=true`（读 `RuntimeLibcalls.td` 889-1413 行 + `AllDefaultRuntimeLibcallImpls`
  定义）✓
- 核对 Lanai 对照确实成立（`LanaiISelLowering.cpp` 无 f32/f64 寄存器类注册）✓
- 读 `RuntimeLibcallsEmitter.cpp::emitSystemRuntimeLibrarySetCalls`，确认每条
  `SystemRuntimeLibrary` 记录生成的代码都包在自己的 `TriplePred` if 判断里，
  不会影响其它 target ✓
- 独立重新编译验证 `vfscanf.o`（编译通过）/`vfprintf.o`（撞
  `SelectionDAGNodes.h:1116`）/`floatscan.o`（撞 `ScheduleDAGSDNodes.cpp:374`），
  行号与 issues.yaml 更新条目完全吻合，未发现夸大 ✓
- 独立重跑 `llvm-lit tests/lit/E2E/`（60/60 PASS）、`run_differential.py`
  （AGREE(3-way)=200 AGREE(4-way)=200 DIVERGE=0）、`manifest_check.py`/
  `check_issues.py`（均 PASS）✓
- 判断范围决策合理：目标 3 的前置条件（vfprintf.o 编译通过）本身未达成，无更小
  的安全修复可在本任务内完成 ✓
- 未独立复跑全量 1347 对象 musl 矩阵（184→113），因时间预算未做，抽查结果与之
  一致但非逐一复核（已如实标注为 subagent 报告里的一个未覆盖点，不影响判决）

**finding 处理**：

| finding | 处置 | 改了什么 | 复验证据 |
|---|---|---|---|
| 任务文件缺少 `## 完成区`/`## 审阅记录（subagent）`，违反任务硬约束 | ✅已修 | 本次编辑新增了这两个区块（本文件） | 本文件现含两区块，非占位 |
| `vfprintf.o` 本身仍未编译通过，任务标题的字面目标未达成，需明确标注避免误读为"已解决" | ✅已修 | 完成区状态标"部分完成"并在多处显式说明"不要把本任务的通过等同于 vfprintf.o 已经真正编译通过" | 见完成区第一段与"验收结果"小节 |

无 ❌不修/⏸延后项——两条 finding 均已在本次编辑中处理。完成区状态与本判决一致
（部分完成，非"已完成"，遗留项已在"未在本任务内尝试修复"与"给架构师的判断建议"中
列出，非"遗留:无"）。
