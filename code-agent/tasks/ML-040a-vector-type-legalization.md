# ML-040a：诊断并修复向量类型 `SetCC` 断言崩溃（9 个 gcc-c-torture 文件）

**执行环境**: 本地 subagent

## 硬约束（务必遵守，违反视为任务失败）

- **禁止**对 `.work/llvm` 做 `git rebase`/`git am` 重放整条历史/`git reset
  --hard`。只允许在当前 HEAD 基础上新增普通 `git commit`。
- **这是一个不确定工作量的任务，允许诊断后发现范围过大就停下报告**——
  DADAO 是标量寄存器架构（RD/RB/RF bank），从未实现过任何向量
  legalization（`setOperationAction` 对 `MVT::v*` 系列类型从未被调用过）。
  这类文件用的是 GCC/Clang 的 `vector_size`/`__attribute__((vector_size))`
  扩展（不是真实 SIMD 硬件指令，语义上是"逐元素标量运算的语法糖"），LLVM
  对没有寄存器类的向量类型默认走 `Expand`/`Scalarize` legalization 路径——
  这条路径理论上不需要 DADAO 有任何向量硬件支持，只需要后端正确声明
  "这些向量类型都是非法类型，请用标量化/展开处理"。**如果诊断后发现实际
  需要的工作量远超"补几个 `setOperationAction` 声明"这个量级**（比如发现
  当前崩溃点意味着需要新写大段自定义 lowering 代码），如实停下报告，
  登记到 `docs/issues.yaml`，不要勉强拼一个高风险的大改动。
- **完成后立即导出 patch**（不要延后），追加进对应 `series`。
- 完成后必须在任务文件里写「完成区」+ subagent 自审「审阅记录」（含逐条 finding
  + 判决）。

## 背景

`ML-035a`（`docs/reviews/ML-035a-gcc-torture-gap-rescan-2026-07-24.md`
§1.2(a)(b)(c)）确认 11 个文件因向量类型崩溃编译，两个不同崩溃点：

```
# 6 个文件：
clang: TargetLoweringBase.cpp:1905: getSetCCResultType(...): Assertion `...' failed
文件：pr23135.c, pr53645.c, pr53645-2.c, scal-to-vec1.c, simd-1.c, simd-2.c
```

```
# 原本 5 个文件止步于同一个 CC 分配崩溃点（"unable to allocate function
# return #1" / CallingConvLower.cpp:174 UNREACHABLE），ML-038a 修复
# __int128 返回值 CC 分配时作为副作用顺带让其中 2 个（20050316-1.c/
# 20050316-3.c）转 PASS，剩余 3 个仍待处理：
文件：pr60960.c, simd-6.c, pr70903.c
```

架构师已重新确认当前状态（`gcc-torture-results.json`）：这 9 个文件
（`pr23135.c`, `pr53645.c`, `pr53645-2.c`, `scal-to-vec1.c`, `simd-1.c`,
`simd-2.c`, `pr60960.c`, `simd-6.c`, `pr70903.c`）目前均为 `FAIL_COMPILE`。

`getSetCCResultType` 断言崩溃通常意味着 `TargetLowering` 从未告诉 LLVM
"向量类型的 `SETCC` 结果应该用什么类型表示"——这是 target-independent
type legalization 框架里一个需要显式声明的钩子（`setOperationAction`/
`getSetCCResultType` override，不是自动推导的）。

## 目标

1. **诊断**：用 `-print-after-all`/IR dump 确认这 9 个文件各自触发的具体
   向量类型（`vector_size(N)` 的具体宽度/元素类型组合），确认崩溃的精确
   触发点和当前 `DADAOISelLowering.cpp` 里向量类型相关声明的现状（大概率
   是完全没有任何 `MVT::v*` 相关的 `setOperationAction`/`addRegisterClass`
   调用——先确认这个假设是否成立）。
2. **实现**：为这些文件实际用到的向量类型宽度组合声明合法的
   legalization 路径——参照其它没有真实向量硬件的简单标量架构后端
   （如 Lanai、早期 RISC-V 未启用 V 扩展时的配置）如何处理向量类型：
   通常是让向量类型走 `Expand`（拆成标量操作序列）而不需要注册向量
   寄存器类。**不要为 DADAO 添加任何虚假的"向量寄存器"概念**——这个架构
   没有向量硬件，legalization 的目标是让编译器把向量操作正确地拆解/
   降级为一系列标量 RD/RB 操作，不是伪装出向量执行单元。
3. **验证**：不能只让这 9 个文件编译通过就算完——需要独立、判别性的
   CodeGen lit 测试（FileCheck 断言展开后的标量指令序列语义正确）+
   项目 E2E 测试（真实向量运算，`volatile` 输入 + 正负控制，QEMU+gem5
   双后端跑通端到端正确性，不只是"编译不崩溃"）。

## 验收

- 9 个目标文件用 `python3 tests/scripts/gcc_torture_sweep.py --filter
  "pr23135|pr53645|scal-to-vec1|simd-1|simd-2|pr60960|simd-6|pr70903"`
  重跑，如实报告有几个变绿（不强行要求全部 9 个——如果某个文件还牵涉
  本任务未覆盖的其它问题，如实报告）。
- 独立、判别性的 CodeGen lit 测试（`llvm/test/CodeGen/DADAO/`）+ 项目
  E2E 测试（`tests/lit/E2E/`，volatile + 正负控制，双后端）。
- 全量 `gcc-c-torture` 重扫（当前基线 `1473/96/124/15`），逐文件 diff
  确认零回归。
- 全量 `llvm-lit tests/lit/E2E/`（当前基线 79/79）：零回归。
- `python3 tools/run_differential.py`：AGREE 数与当前基线一致、DIVERGE=0。
- `python3 scripts/manifest_check.py`/`check_issues.py` 通过。
- LLVM 侧改动用**普通** `git commit` 落地，`git format-patch` 导出对应
  patch，追加进 `series`；独立验证可在干净 pin-commit checkout 上 `git am`
  成功，且 replay tree 与开发树 tree hash 一致。
- **如果诊断后判断范围远超预期**：在完成区如实写清楚诊断结论（具体卡在
  哪、为什么工作量超出预期），登记为 `docs/issues.yaml` 里的 open issue，
  不强行交付一个不完整/有风险的修复。这种情况下不需要满足上面其它验收项。

## 参考指针

- `docs/reviews/ML-035a-gcc-torture-gap-rescan-2026-07-24.md` §1.2(a)
  （断言崩溃原文，含精确文件分组）
- `.work/source/llvm-test-suite/SingleSource/Regression/C/gcc-c-torture/execute/
  {pr23135,pr53645,pr53645-2,scal-to-vec1,simd-1,simd-2,pr60960,simd-6,
  pr70903}.c`（原始复现源码）
- `.work/llvm/llvm/lib/Target/DADAO/DADAOISelLowering.cpp`（当前完全没有
  向量类型相关声明，需要新增的地方）
- `llvm/lib/Target/Lanai/LanaiISelLowering.cpp`（本项目多次参照的、
  同样没有真实向量硬件的简单标量架构后端，可以看它是否处理了向量类型、
  怎么处理的，或者确认它也没处理——如果连 Lanai 都没有向量类型支持，
  说明这条路径可能需要更通用的参照，比如 `TargetLoweringBase` 默认值
  本身是否已经能覆盖大部分情况，只是 DADAO 需要显式 opt-in）
- `code-agent/tasks/ML-038a-fix-int128-calling-convention.md` 完成区
  （最近一次涉及 `CallingConvLower.cpp` 崩溃点的诊断方法论参照）
- `feedback_volatile_needed_for_memory_verification_tests`（新测试涉及
  写读回校验要用 volatile + 负控制）

## 完成区（2026-07-25）

**诊断结论：9 个文件里 6 个是"补一个声明"量级、3 个是不同的、超出本任务范围的
CC-allocation 问题；已按任务书允许的"部分交付+登记剩余"方式收尾。**

### 1. 诊断

用当前 `.work/build/llvm/bin/clang`（rebuild 前）逐文件重现，确认任务书假设：

- 6 个文件（`pr23135.c`/`pr53645.c`/`pr53645-2.c`/`scal-to-vec1.c`/`simd-1.c`/
  `simd-2.c`）精确命中
  `TargetLoweringBase.cpp:1905: getSetCCResultType(...): Assertion
  '!VT.isVector() ...' failed`。`DADAOISelLowering.cpp` 逐行核查确认
  `addRegisterClass` 只调用过一次（`MVT::i64`），从未出现任何 `MVT::v*`
  相关声明——任务书假设成立。
- 用 `llc` 对最小 `.ll` 探针（`<2/4/8 x i{32,16}>` 的 `add`/`sdiv`/`udiv` 配合
  纯指针 load/store，不跨函数调用边界）反查崩溃调用栈：崩溃来自
  `DAGCombiner::visitSDIV`（`DAGCombiner.cpp:5124`）对非 2 的幂常量除法做
  shift/compare/subtract 展开时，在算子仍是向量类型的阶段（分裂/标量化尚未
  发生）就查询 `getSetCCResultType`——这是 target-independent 阶段的行为，
  不需要 DADAO 自己实现任何向量除法逻辑。逐文件确认这 6 个文件全部含
  `/` 或 `%` 运算，无一在函数边界按值传递/返回向量（`pr53645*`/`simd-1/2`
  只通过指针访问向量或把单个标量元素传给函数；`scal-to-vec1.c` 除
  `main` 外没有其它函数）。
- 另外 3 个文件（`pr60960.c`/`simd-6.c`/`pr70903.c`）**不是** `getSetCCResultType`
  断言崩溃——`pr60960.c`/`simd-6.c` 命中
  `fatal error: error in backend: unable to allocate function return #2`，
  `pr70903.c` 命中 `UNREACHABLE executed at .../CallingConvLower.cpp:174!`。
  三个文件共同点：都有 `__attribute__((noinline, noclone))` 函数**按值**
  传递/返回向量（`pr60960.c` 的 `v4qi`=4×i8=32bit、`simd-6.c` 的
  `v8qi`=8×i8=64bit、`pr70903.c` 的 `V8`/`V32`/`V64`=vector_size(32)=256bit，
  混合 8/32/64 位元素类型互相 reinterpret）。根因：无寄存器类的向量在
  target-independent legalization 下被**标量化成 N 个独立的逐元素 SDValue**
  （如 v4qi → 4 个独立 i8，不是打包成 1 个 i32），CC 分析把每个元素当一个
  独立 Outs/Ins 条目；`DADAOCallingConv.td` 的 `CC_DADAO`/`RetCC_DADAO`
  只有 `CCIfPtr`/`CCIfType<[i64]>` 两条规则，i8 类型的条目两条都不命中，
  `CCState::AnalyzeReturn`/`AnalyzeCallResult` 无处可放而 fatal。这与
  ML-038a 的 `__int128` CC 修复是**不同机制**：`__int128` 固定拆成 2 个
  同宽 i64（`DataLayout::isBigEndian()` 决定顺序），而小向量按元素个数展开
  成 N 个条目，且 wiki/`contracts/abi/spec.md` 从未提及向量类型，没有任何
  既定 ABI 约定可以照抄——修好它需要一次新的 ABI 设计决策（多少个寄存器、
  什么顺序、多宽之后转 indirect/sret），性质上等价于 DL-072a 那次 varargs
  指针 bank ABI 决策所花的工作量，**不是"补几个 `setOperationAction` 声明"
  这个量级**，命中任务书的止损条件。已停止对这 3 个文件的进一步尝试，
  登记为 `docs/issues.yaml` 的新 open issue
  `dadao-vector-by-value-call-boundary-cc-unimplemented`（含完整根因、
  与 ML-038a 的区分、后续任务切分建议）。

### 2. 实现

`.work/llvm/llvm/lib/Target/DADAO/DADAOISelLowering.{h,cpp}` 新增
`DADAOTargetLowering::getSetCCResultType` override：向量类型返回
`VT.changeVectorElementTypeToInteger()`，非向量分支不变（转发基类）——
与 Sparc/CSKY（同样没有向量寄存器堆）采用的写法一致。未添加任何寄存器类/
"向量硬件"概念；target-independent 的 split/scalarize 路径本来就不需要
DADAO 端 opt-in，这是唯一缺失的钩子。

### 3. 验证结果

- **9 个目标文件重跑**（`gcc_torture_sweep.py --filter
  "pr23135|pr53645|scal-to-vec1|simd-1|simd-2|pr60960|simd-6|pr70903"`）：
  **6/9 PASS**（`pr23135.c`/`pr53645.c`/`pr53645-2.c`/`scal-to-vec1.c`/
  `simd-1.c`/`simd-2.c`，真实 compile+link+QEMU run，退出码符合
  gcc-c-torture 自身 PASS 约定），**3/9 仍 FAIL_COMPILE**
  （`pr60960.c`/`simd-6.c`/`pr70903.c`，已登记 issue，不在本任务范围内）。
- **CodeGen lit 测试**：新增
  `llvm/test/CodeGen/DADAO/vector-type-legalization.ll`，覆盖 4 个真实命中
  过的向量形状/算子（`<2 x i32> add`、`<4 x i32> sdiv`、`<8 x i16> udiv`、
  `<4 x float> fdiv`），全部只用指针 load/store（不跨调用边界，避开未修复
  的 CC 缺口），FileCheck 断言真实标量指令序列（`add`/`divs`/`divu`/
  `call __divsf3`，且 `CHECK-NOT: v0` 排除向量寄存器痕迹）。`llvm-lit`
  跑 `CodeGen/DADAO/`：**12/12 PASS**（11 个既有 + 1 个新增，零回归）。
- **E2E lit 测试**：新增 `tests/lit/E2E/vector_type_legalization.test` +
  `Inputs/vector_type_legalization.c`（`nostdlib`+`crt0.s`，仿
  `negative_polarity_bitand_mask.test` 惯例）。三种向量形状/数值直接取自
  已验证真 PASS 的原始文件（`pr23135.c`/`simd-1.c`/`simd-2.c`），逐元素
  硬编码期望值覆盖 add/sub/mul/div/rem/and/or/xor/neg/not；`x0`/`y0`
  用 volatile 防止编译期常量折叠，`NEGATIVE_CONTROL` 篡改 `x0` 验证检查
  确实会失败（非重言式）。`-O0`/`-O2` × 正常/`NEGATIVE_CONTROL` ×
  QEMU/gem5 共 8 条 RUN 行全部符合预期退出码（42/1）。（浮点向量除法的
  scalarize-through-softfloat 路径改在 CodeGen lit 测试里覆盖，因为
  `nostdlib` 环境没有链接 musl 的软浮点符号，见测试文件内注释。）
  `llvm-lit tests/lit/E2E/`：**80/80 PASS**（79 个既有基线 + 1 个新增，
  零回归）。
- **gcc-c-torture 全量重扫**：`PASS 1473→1479`（+6）、
  `FAIL_COMPILE 96→90`（-6）、`FAIL_LINK 124`（不变）、`FAIL_RUN 15`
  （不变）。逐文件 diff（对照仓库根 `gcc-torture-results.json` 基线）
  确认**恰好 6 处变化，全部是目标文件 FAIL_COMPILE→PASS，零意外回归、
  零意外新增 PASS**。
- **`python3 tools/run_differential.py`**：`AGREE(4-way)=200 DIVERGE=0`，
  与基线一致。
- **`python3 scripts/manifest_check.py`**：PASS。
- **`python3 scripts/check_issues.py`**：PASS（Open 21→22，新增本任务
  登记的 1 条 issue）。
- **Patch 导出**：`.work/llvm` 内以普通 `git commit`（非 rebase/am 重放）
  落地（commit `f7cc59f158fc`，基于 `be30d543202b` HEAD，working tree
  在改动前用 `git status`/`git log` 确认干净）；`git format-patch` 导出为
  `components/llvm/patches/0063-DADAO-declare-getSetCCResultType-for-vector-types-ML.patch`，
  追加进 `series`。独立验证：在 pin commit
  `ca7933e47d3a3451d81e72ac174dcb5aa28b59d1` 的干净 `git worktree` 上依次
  `git am` 全部 63 个 patch 成功，replay tree 与开发树 `git rev-parse
  HEAD^{tree}` **逐字节一致**（`7b838df9a5b1148374b74a21872b890eb71709bd`）。
- **根仓库范围**：未对 DADAO-0628 根仓库做任何 `git add`/`git commit`——
  `docs/issues.yaml`、`components/llvm/patches/series`+新 patch 文件、
  `tests/lit/E2E/vector_type_legalization.test`+`Inputs/*.c` 均以未提交
  工作区改动形式留给架构师复核（`git status` 可见）。

### 4. 改动文件清单

- `.work/llvm/llvm/lib/Target/DADAO/DADAOISelLowering.h`（新增
  `getSetCCResultType` 声明+详细注释）
- `.work/llvm/llvm/lib/Target/DADAO/DADAOISelLowering.cpp`（实现）
- `.work/llvm/llvm/test/CodeGen/DADAO/vector-type-legalization.ll`（新增）
- `components/llvm/patches/0063-DADAO-declare-getSetCCResultType-for-vector-types-ML.patch`（新增，未提交）
- `components/llvm/patches/series`（追加一行，未提交）
- `tests/lit/E2E/vector_type_legalization.test`（新增，未提交）
- `tests/lit/E2E/Inputs/vector_type_legalization.c`（新增，未提交）
- `docs/issues.yaml`（追加 1 条新 open issue，未提交）

## 审阅记录（自审，无嵌套 subagent）

1. **finding**：任务背景/参考指针假设"DADAO 从未声明任何向量类型
   legalization"——逐行读 `DADAOISelLowering.cpp` 确认
   `addRegisterClass` 仅调用一次（`MVT::i64`），且全文件 grep
   `MVT::v`/`Vector` 零命中。
   **判决**：假设成立，接受。
2. **finding**：任务背景把 9 个文件全部归为"同一类"崩溃，但实测（rebuild
   前逐文件跑 clang）发现 3 个文件（`pr60960.c`/`simd-6.c`/`pr70903.c`）
   命中的是完全不同的 fatal error（CC allocation），不是
   `getSetCCResultType` 断言。
   **判决**：真实分歧，未按背景文字盲目假定"修一个钩子应该 9/9 全绿"；
   诊断后果断止损，没有为了凑满 9/9 去动
   `DADAOCallingConv.td`/`CallingConvLower.cpp` 做未经设计的临时拼凑（那
   会是真正高风险的"大改动"）。任务书本身允许这种"部分诊断说明不同问题"
   的报告方式，采纳。
3. **finding**：写 CodeGen lit 测试时，最初直接把 `<2 x i32>` 等向量类型
   用作函数参数/返回值类型（IR 级），结果会命中前面刚诊断出的、仍未修复
   的 CC allocation 崩溃，与本次要验证的 fix 无关。
   **判决**：改为纯指针 load/store 形状（匹配 6 个真实修复文件的实际
   访问模式），避免把测试写成"顺带依赖了另一个未修复的缺陷"，这样
   FileCheck 才是对本次改动的干净、判别性验证。
4. **finding**：第一次编译探针 `.ll` 时用 `llc` 直接崩在旧断言——一度以为
   fix 没生效，排查后发现是只 `ninja clang` 没有 `ninja llc`，`llc` 二进制
   没有重新链接 `libLLVMDADAOCodeGen.a`（该静态库确实已重新构建）。
   **判决**：真实的构建产物陈旧陷阱（不是与
   `feedback_stale_build_artifacts_after_toolchain_rebuild` 完全相同的
   "下游库增量构建"场景，但同一类"半个工具链重建、另一半没重建"问题）；
   补 `ninja llc` 后复现修复生效,记录在此避免下次误判。
5. **finding**：E2E 测试最初包含 `<4 x float>` 浮点向量除法（`fdiv`），
   `nostdlib`+`crt0.s` 环境下 link 失败（`__addsf3`/`__divsf3` 等符号未
   定义——这些符号只在链 musl 时可用）。
   **判决**：不为了凑单个测试文件里塞入所有形状而引入 musl 依赖（会让
   测试从"验证 codegen 修复"意外变成"同时依赖 musl 软浮点链接"，扩大
   测试的失败面/维护面）；把浮点向量情形移到本来就不需要链接、只跑
   `llc` 的 CodeGen lit 测试里（`fdiv_v4sf` 用例），E2E 测试保持纯整数、
   自包含。两个测试合起来仍完整覆盖 4 种向量形状。
6. **finding**：E2E 测试的期望值全部是硬编码常量，逐一核对是否与真实
   torture 源文件里已验证正确的 `verify()`/手工推导结果一致（而不是凭空
   编的数）——`v2si`/`v4si`/`v8hi` 三组直接复用 `pr23135.c`/`simd-1.c`/
   `simd-2.c` 自带的、已通过 QEMU+gem5 真实运行确认正确的期望值。
   **判决**：交叉验证一致，采纳；这比自己重新推导算术结果风险更低（避免
   我自己算错却被测试当作"正确答案"埋进回归测试的风险）。
7. **finding**：`gcc-torture-results.json`（仓库根）是一个此前就存在、
   未被 git 追踪的工作产物（`git log` 对该文件零记录），本次任务只用它
   做 diff 基线比对，未覆盖写入，也未 `git add`。
   **判决**：不属于本任务改动范围，保持原样，不主动纳入版本控制（超出
   任务授权范围的额外决定）。
8. **finding**：`.work/llvm` 内验证 patch series 用了 `git worktree
   add`/`git am`/`git worktree remove`，而不是在开发中的 `.work/llvm`
   本体上做任何 rebase/am 重放。
   **判决**：符合硬约束（"禁止对 `.work/llvm` 做 git rebase/git am 重放
   整条历史/git reset --hard；只允许在当前 HEAD 基础上新增普通 git
   commit"）——验证发生在一个独立、验证完立即删除的 detached worktree
   里，开发树本体全程只做了一次普通 `git commit`。
