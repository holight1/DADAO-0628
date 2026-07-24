# ML-038a：修复 `__int128` 返回值/调用结果的 CallingConv 分配崩溃

**执行环境**: 本地 subagent

## 硬约束（务必遵守，违反视为任务失败）

- **禁止**对 `.work/llvm` 做 `git rebase`/`git am` 重放整条历史/`git reset
  --hard`。只允许在当前 HEAD 基础上新增普通 `git commit`。
- **先诊断根因，再修复**——不要凭 `ML-035a` 报告里的错误信息猜测直接改代码，
  自己用 `-print-after-all`/IR dump 独立确认崩溃的确切触发点。
- **本任务范围只覆盖 `__int128`，不覆盖向量类型**（`ML-035a` 报告指出向量
  和 `__int128` 共享同一个 CC 分配崩溃点，但向量类型还有一个额外的、独立的
  `SetCC` 断言崩溃前置问题，本任务不处理——如果诊断中发现修复 `__int128`
  这条路径顺带也让某个向量文件真的编译通过，如实记录，但不要因此扩大任务
  范围去处理向量类型专属的问题）。
- **完成后立即导出 patch**（不要延后），追加进对应 `series`。
- 完成后必须在任务文件里写「完成区」+ subagent 自审「审阅记录」（含逐条 finding
  + 判决）。

## 背景

`ML-035a`（`docs/reviews/ML-035a-gcc-torture-gap-rescan-2026-07-24.md` §1.2
(b)(c)）确认：`__int128` 触发的 6 个 gcc-c-torture 文件（`pr54471.c`,
`pr85582-2.c`, `pr85582-3.c`, `pr49218.c`, `pr84748.c`, `pr84169.c`）全部
在编译期崩溃于同一类"128 位宽返回值 CallingConv 分配失败"问题，具体是两个
不同的崩溃点：

```
# (b) 7 个文件里的 3 个 __int128 文件：
<fatal error>: unable to allocate function return #1
```

```
# (c) 4 个文件里的 3 个 __int128 文件：
llvm/lib/CodeGen/CallingConvLower.cpp:174: UNREACHABLE executed
（llvm::CCState::AnalyzeCallResult 内）
```

这是 `ML-026a`（PASS=1328 基线）时就已经存在、`ML-027a`~`ML-034a` 均未触碰的
FAIL_COMPILE 真实候选缺陷，`ML-035a` 重新确认逐文件完全一致（零进展也零新
发现，代表这条路径需要专门任务才能推进）。

DADAO 是 64 位宽寄存器架构（RD bank），`__int128` 需要跨两个 64 位寄存器
（高/低半区）传递返回值——目前后端的 `CC_DADAO`/`RetCC_DADAO`（或等价的
CallingConv 分配逻辑）显然没有为 128 位宽标量值实现"拆成两个寄存器"这条路径，
遇到时直接崩溃而非静默错误（这点和聚合体的情况不同——`ML-031a` 已经实现了
聚合体的多寄存器拆分，但 `__int128` 是标量类型，走的是不同的分类代码路径，
可能完全没有复用 `ML-031a` 那套逻辑）。

## 目标

1. **根因诊断**：确认这 6 个文件具体在哪个 `TargetLowering`/`CallingConv`
   相关函数崩溃（`LowerReturn`/`LowerCallResult`/`RetCC_DADAO`/`CC_DADAO`
   或 `TargetLowering::LowerCallTo` 的返回值处理路径），弄清楚当前代码对
   128 位宽标量返回值到底是完全没处理，还是有处理但逻辑有 bug。
2. **修复**：让 `__int128` 函数返回值（以及如果诊断发现调用点传参也有同类
   缺口，视情况一并处理，但**不要主动扩大范围**去处理向量类型）能正确拆分
   到两个 64 位寄存器（RD bank，参照 wiki/`contracts/abi/spec.md` 里
   "标量参数拆分"相关规则，如果 `__int128` 没有被 wiki 明确覆盖，按现有
   `long`/`long long` 的既定寄存器分配惯例做最合理的扩展，并在完成区里说明
   依据）。
3. **判别性验证**：不能只靠这 6 个 torture 文件通过，需要独立构造 CodeGen
   lit 测试覆盖：`__int128` 作为返回值（含边界值：全 0、全 1、只有高位/
   低位非零、符号扩展相关的负数）、`__int128` 作为函数调用的返回值被
   调用方消费（对应 `AnalyzeCallResult` 那条崩溃路径）。

## 验收

- 独立、判别性的 CodeGen lit 测试（`llvm/test/CodeGen/DADAO/`），FileCheck
  断言生成的寄存器分配/返回序列正确（高低 64 位分别对应正确的输入值）。
- 独立、判别性的项目 E2E 测试（`tests/lit/E2E/`），用 `volatile` 输入 +
  正负控制，覆盖至少一个真实的 `__int128` 返回值+调用点消费的端到端场景，
  QEMU+gem5 双后端跑通。
- 6 个目标 torture 文件用 `python3 tests/scripts/gcc_torture_sweep.py
  --filter "pr54471|pr85582-2|pr85582-3|pr49218|pr84748|pr84169"` 重跑，
  如实报告有几个变绿（不强行要求全部 6 个——如果诊断中发现某个文件还牵涉
  本任务未覆盖的其它问题，如实报告）。
- 全量 `gcc-c-torture` 重扫（当前基线 `1465/104/124/15`），逐文件 diff
  确认零回归。
- 全量 `llvm-lit tests/lit/E2E/`（当前基线 78/78）：零回归。
- `python3 tools/run_differential.py`：AGREE 数与当前基线一致、DIVERGE=0。
- `python3 scripts/manifest_check.py`/`check_issues.py` 通过。
- LLVM 侧改动用**普通** `git commit` 落地，`git format-patch` 导出对应
  patch，追加进 `series`；独立验证可在干净 pin-commit checkout 上 `git am`
  成功，且 replay tree 与开发树 tree hash 一致。
- 如果诊断后发现这个修复的合理工作量远超预期（比如发现需要先做一个更大的
  "任意宽标量类型跨寄存器传递"通用框架），如实停下报告，不要为了"看起来
  完整"而勉强拼一个只覆盖这 6 个文件的特例补丁。

## 参考指针

- `docs/reviews/ML-035a-gcc-torture-gap-rescan-2026-07-24.md` §1.2(b)(c)
  （本任务对应的发现原文，含精确的崩溃点和文件分组）
- `.work/source/llvm-test-suite/SingleSource/Regression/C/gcc-c-torture/execute/
  {pr54471,pr85582-2,pr85582-3,pr49218,pr84748,pr84169}.c`（原始复现源码）
- `.work/llvm/llvm/lib/Target/DADAO/DADAOISelLowering.cpp`（`LowerReturn`/
  `LowerCallResult`/`CC_DADAO`/`RetCC_DADAO` 相关逻辑）
- `.work/llvm/llvm/lib/CodeGen/CallingConvLower.cpp:174`（`AnalyzeCallResult`
  UNREACHABLE 崩溃点，读这里的上下文理解触发条件）
- `code-agent/tasks/ML-031a-aggregate-struct-abi-parameter-passing.md`
  完成区（聚合体的多寄存器拆分实现，`__int128` 如果需要类似的"跨寄存器"
  处理可以参考其设计，但 `__int128` 是标量不是聚合体，具体机制大概率不同，
  需要自己诊断确认，不要想当然直接照抄）
- `contracts/abi/spec.md`（标量参数寄存器分配规则，如果 wiki/spec 对
  128 位标量类型没有明确覆盖，如实记录这个空白并按现有规则做最合理扩展）
