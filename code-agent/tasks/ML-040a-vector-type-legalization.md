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
