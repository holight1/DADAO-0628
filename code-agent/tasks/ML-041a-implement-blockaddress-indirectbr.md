# ML-041a：实现 `BlockAddress`（computed goto / `&&label`）支持

**执行环境**: 本地 subagent

## 硬约束（务必遵守，违反视为任务失败）

- **禁止**对 `.work/llvm` 做 `git rebase`/`git am` 重放整条历史/`git reset
  --hard`。只允许在当前 HEAD 基础上新增普通 `git commit`。
- **先诊断根因，再修复**——独立用 `-print-after-all`/IR dump 确认具体
  崩溃触发点（`Cannot select: t.: i64 = BlockAddress<@fn, %label> 0`），
  弄清楚 `DADAOISelLowering.cpp`/`DADAOISelDAGToDAG.cpp` 当前对
  `ISD::BlockAddress`/`ISD::BRIND`（间接跳转）分别处理到什么程度。
- **优先复用已有基础设施**——DADAO 后端已经实现了 `GlobalAddress` 的
  `rela`+`addi` lowering（`ML-013a`/`ML-030a` 等）和 jump table 的间接
  跳转选择（历史 patch 里的 `ML-003h`/`ML-004d` 等，用 `BRIND` 或等价
  机制做 `switch` 语句的跳转表分发）。`BlockAddress` 本质上是"取一个
  基本块的地址当成一个编译期常量"，`indirectbr`（`goto *ptr`）本质上是
  "对一个运行时寄存器值做无条件跳转"——这两块很可能已经有可以直接复用的
  相邻实现（跳转表分发就是一种间接跳转），不要凭空新写一整套机制，先确认
  能复用多少。
- **完成后立即导出 patch**（不要延后），追加进对应 `series`。
- 完成后必须在任务文件里写「完成区」+ subagent 自审「审阅记录」（含逐条 finding
  + 判决）。

## 背景

`ML-035a`（`docs/reviews/ML-035a-gcc-torture-gap-rescan-2026-07-24.md`
§1.2(d)）确认 3 个文件因 `BlockAddress` 未实现而编译期崩溃：

```
fatal error: error in backend: Cannot select: t.: i64 = BlockAddress<@fn, %label> 0
```

文件：`990208-1.c`, `comp-goto-1.c`, `pr70460.c`——全部用到 GCC 的
"computed goto" / "labels as values" 扩展（`&&label` 取标签地址，
`goto *ptr` 跳到运行时计算出的地址）。这是 P3 优先级，本次重新确认这 3 个
文件目前仍是 `FAIL_COMPILE`。

## 目标

1. **诊断**：确认当前 `DADAOISelLowering.cpp` 对 `ISD::BlockAddress` 的
   `setOperationAction`（大概率完全未声明，默认走 `Expand` 但 `Expand`
   对 `BlockAddress` 这种"编译期已知地址常量"类型通常没有意义的展开路径，
   需要确认具体行为）；确认 `ISD::BRIND`（间接跳转）当前的选择状态——
   本项目已有 switch 跳转表分发，很可能已经支持某种形式的间接跳转，
   需要确认是否可以直接复用同一套指令选择。
2. **实现**：
   - `BlockAddress` 需要能被当成一个编译期常量地址处理（类似
     `GlobalAddress`，走 `rela`+`addi` 或等价的重定位表达式），值放入
     RB bank（地址）寄存器。
   - `indirectbr`（对应 `goto *ptr` 的 IR 形式）需要能选择出一条无条件
     跳转到寄存器值的指令，复用已有的跳转表分发间接跳转机制（如果确认
     可复用）。
   - 汇编器/链接器层面确认 `BlockAddress` 产生的重定位类型能被正确处理
     （标签地址在同一函数/同一 object 内，理论上不需要跨 section 重定位，
     但需要验证 `MCCodeEmitter`/lld 对这类 fixup 的处理路径）。
3. **验证**：独立、判别性的 CodeGen lit 测试 + 项目 E2E 测试（真实
   computed goto 跳转序列，`volatile` 输入 + 正负控制，QEMU+gem5 双后端
   跑通端到端正确性）。

## 验收

- 3 个目标文件用 `python3 tests/scripts/gcc_torture_sweep.py --filter
  "990208-1|comp-goto-1|pr70460"` 重跑，如实报告有几个变绿（不强行要求
  全部 3 个——如果某个文件还牵涉本任务未覆盖的其它问题，如实报告）。
- 独立、判别性的 CodeGen lit 测试（`llvm/test/CodeGen/DADAO/`）+ 项目
  E2E 测试（`tests/lit/E2E/`，volatile + 正负控制，双后端）。
- 全量 `gcc-c-torture` 重扫（当前基线 `1479/90/124/15`），逐文件 diff
  确认零回归。
- 全量 `llvm-lit tests/lit/E2E/`（当前基线 80/80）：零回归。
- `python3 tools/run_differential.py`：AGREE 数与当前基线一致、DIVERGE=0。
- `python3 scripts/manifest_check.py`/`check_issues.py` 通过。
- LLVM 侧改动用**普通** `git commit` 落地，`git format-patch` 导出对应
  patch，追加进 `series`；独立验证可在干净 pin-commit checkout 上 `git am`
  成功，且 replay tree 与开发树 tree hash 一致。
- 如果诊断后发现工作量远超预期（比如发现跳转表机制其实不可复用，需要
  从零设计一套新的间接跳转/重定位机制），如实停下报告，登记
  `docs/issues.yaml`，不要勉强拼一个高风险的大改动。

## 参考指针

- `docs/reviews/ML-035a-gcc-torture-gap-rescan-2026-07-24.md` §1.2(d)
  （断言崩溃原文）
- `.work/source/llvm-test-suite/SingleSource/Regression/C/gcc-c-torture/execute/
  {990208-1,comp-goto-1,pr70460}.c`（原始复现源码）
- `.work/llvm/llvm/lib/Target/DADAO/DADAOISelLowering.cpp`（`GlobalAddress`
  lowering 现有实现，`BlockAddress` 大概率可以类比处理）
- `.work/llvm/llvm/lib/Target/DADAO/DADAOISelDAGToDAG.cpp`（jump table /
  间接跳转现有指令选择，确认能否复用于 `BRIND`）
- `components/llvm/patches/`（历史 patch 名称含 `jump-table`/`jmp`/
  `BRIND` 关键词的条目，可以 `grep` series 文件找到具体是哪几个 patch
  实现了现有的跳转表分发机制）
- `code-agent/tasks/ML-030a-relocation-range-large-constant-offset.md`
  完成区（`GlobalAddress` 重定位相关的既有诊断方法论，`BlockAddress`
  如果走类似的重定位路径可以参考）
- `feedback_volatile_needed_for_memory_verification_tests`（新测试涉及
  写读回校验要用 volatile + 负控制）
