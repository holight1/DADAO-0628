# ML-037a：实现 `__divsc3`（单精度复数除法），关闭最后一个软浮点符号缺口

**执行环境**: 本地 subagent

## 硬约束（务必遵守，违反视为任务失败）

- **禁止**对 `.work/source/musl` 做 `git rebase`/`git am` 重放整条历史/
  `git reset --hard`。只允许在当前 HEAD 基础上新增普通 `git commit`。
- **算法必须严格遵循 C99 Annex G 语义**（复数除法在操作数含 `NaN`/`Inf`/`0`
  时有专门定义的特判规则，不是普通复数除法公式的直接实现）——参照
  `.work/source/llvm/compiler-rt/lib/builtins/divsc3.c`（Smith's method
  参考实现，权威依据），逻辑结构可以照抄，但要用本文件已有的"纯位模式运算，
  不调用原生浮点 `+-*/`"这个方法论重写（避免自递归调用其它软浮点符号），
  参照 `src/internal/dadao/softfloat_shim.c` 里现有函数的写法风格。
- **需要先实现的基础设施**（本文件目前完全没有）：`logb`/`scalbn`（重新
  定标避免中间结果溢出）+ `isnan`/`isinf`（Annex G 特判分支判断）的单精度
  位模式版本。这些是本任务范围内的必要前置组件，不是"顺带超范围实现"。
- **完成后立即导出 patch**（不要延后），追加进对应 `series`。
- 完成后必须在任务文件里写「完成区」+ subagent 自审「审阅记录」（含逐条 finding
  + 判决）。

## 背景

`ML-028a`（92 文件软浮点符号缺口关闭任务）逐一排查后确认：gcc-c-torture
1708 个用例里，实际引用 `__divsc3`（单精度复数除法）的**只有 `complex-5.c`
一个文件**（`y = p(x, 1.0f / z)`，`z` 是 `float __complex__`，"实数 / 复数"
触发 C99 复数除法）；`complex-6.c`/`complex-7.c` 用到的是构造/相等比较，
不需要 `__divsc3`（已在 ML-028a 补齐比较家族后转 PASS）。`__divsc3` 因为
算法复杂度（Smith's method，涉及 `logb`/`scalbn` 重定标 + NaN/Inf/0 各种
组合的 Annex G 特判表，跟本文件其余全部符号"闭式位模式运算无特判表"不是
同一量级）被 ML-028a 登记为独立后续任务（`docs/issues.yaml`
`musl-softfloat-shim-missing-divsc3`），未在当时实现。

这是当前 gcc-c-torture FAIL_LINK 分类里**唯一**尚未落位的一个已知缺口
（`ML-035a` 重新分类扫描确认 FAIL_LINK 125 个文件里其余 124 个全部落位到
已知类别）。

## 目标

1. 在 `src/internal/dadao/softfloat_shim.c` 里新增：
   - `logbf`/`scalbnf`（或等价的内部 helper，命名不必与 libm 公开符号
     完全一致，除非发现直接复用能减少重复代码）的位模式实现。
   - `isnan`/`isinf` 对应的单精度位模式判断 helper（如果本文件或
     musl 其它地方已有可复用的位模式实现，优先复用，不要重复造轮子——
     先 grep 确认）。
   - `__divsc3`：按 `compiler-rt/lib/builtins/divsc3.c` 的 Smith's method
     逻辑结构重写，同样用纯位模式运算实现底层加减乘除（复用本文件已有的
     `__addsf3`/`__subsf3`/`__mulsf3`/`__divsf3`），不引入对原生浮点
     运算符的依赖，不产生自递归调用。
2. **验证方法沿用本文件既有约定**（`ML-022a`/`ML-025a`/`ML-028a` 的方法论）：
   - 反汇编确认新增函数没有意外的 `call` 自递归（除了对本文件内其它已验证
     softfloat 符号的正常调用）。
   - fuzz 测试对拍原生硬件复数除法运算（覆盖正常值 + Annex G 规定的
     NaN/Inf/0 各种边界组合，这些边界组合不能只随机 fuzz，需要显式构造
     覆盖，因为随机 fuzz 命中特定边界值的概率极低）。
3. 关闭 `complex-5.c` 的 FAIL_LINK。

## 验收

- `complex-5.c` 用 `python3 tests/scripts/gcc_torture_sweep.py --filter
  "complex-5"` 重跑，确认转 PASS。
- 反汇编确认新增函数无自递归 `call`（沿用 `ML-022a`/`ML-025a`/`ML-028a`
  的验证方式）。
- fuzz + 显式边界值测试：正常值范围 fuzz 若干万次零不一致 + C99 Annex G
  规定的 NaN/Inf/0 各种操作数组合全部显式覆盖，对拍原生硬件复数除法结果。
- 全量 `gcc-c-torture` 重扫（当前基线 `1464/104/125/15`），逐文件 diff
  确认只有 `complex-5.c` 变化，零回归。
- 全量 `llvm-lit tests/lit/E2E/`（当前基线 78/78）：零回归。
- `python3 tools/run_differential.py`：AGREE 数与当前基线一致、DIVERGE=0
  （本任务不改指令语义/LLVM，理论上不应变化）。
- `python3 scripts/manifest_check.py`/`check_issues.py` 通过；
  `musl-softfloat-shim-missing-divsc3` 状态更新为 closed 并迁移到
  `docs/issues-archive.yaml`。
- musl 侧改动用**普通** `git commit` 落地，`git format-patch` 导出对应
  patch，追加进 `series`；独立验证可在干净 pin-commit checkout 上 `git am`
  成功，且 replay tree 与开发树 tree hash 一致。

## 参考指针

- `docs/issues.yaml` `musl-softfloat-shim-missing-divsc3`（完整背景，
  complex-6.c/complex-7.c 不需要这个符号的验证过程）
- `.work/source/llvm/compiler-rt/lib/builtins/divsc3.c`（Smith's method
  权威参考实现，C99 Annex G 特判表照这个抄逻辑结构）
- `src/internal/dadao/softfloat_shim.c`（现有 36 个符号的写法风格，
  `ML-022a`/`ML-025a`/`ML-028a` 建立的方法论：位模式运算、反汇编验证无
  自递归、fuzz + 负控制）
- `.work/source/llvm-test-suite/SingleSource/Regression/C/gcc-c-torture/execute/
  complex-{5,6,7}.c`（原始复现源码）
- `feedback_volatile_needed_for_memory_verification_tests`（如果验证测试
  涉及写读回校验，记得用 volatile + 负控制）
