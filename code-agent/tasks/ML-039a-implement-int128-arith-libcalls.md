# ML-039a：补齐 `__int128` 算术 libcall 缺口（`__fixsfti`/`__udivti3` 起步）

**执行环境**: 本地 subagent

## 硬约束（务必遵守，违反视为任务失败）

- **禁止**对 `.work/source/musl` 做 `git rebase`/`git am` 重放整条历史/
  `git reset --hard`。只允许在当前 HEAD 基础上新增普通 `git commit`。
- **先摸清真实范围，再动手**——`docs/issues.yaml`
  `musl-softfloat-shim-missing-int128-arith-libcalls` 里明确写了"未审计
  compiler-rt 定义的 128 位算术 libcall 全集 vs. gcc-c-torture 语料库
  实际用到几个"，本任务第一步是**在全量 gcc-c-torture 重扫的 FAIL_LINK
  分类里 grep 所有含 `ti`/`ti2`/`ti3`/`ti4` 后缀（compiler-rt 128 位宽
  libcall 命名惯例）的 undefined symbol**，摸清真实需要实现的符号集合，
  不要只做 `__fixsfti`/`__udivti3` 这两个已确认的就收工，也不要没摸清楚
  范围就开始实现。
- **方法论沿用 `softfloat_shim.c` 已有约定**（`ML-022a`/`ML-025a`/`ML-028a`/
  `ML-037a`）：纯位模式运算实现（`__udivti3` 是无符号 128 位整数除法，
  不涉及浮点，但同样不能调用原生 128 位 `/` 运算符——需要确认 DADAO
  后端本身是否已经支持 `i128` 的原生 `udiv`/`urem` legalization，如果
  后端自己就能生成正确代码只是缺运行时符号，这个符号的实现可以直接用
  C 语言的移位减法长除法算法，不需要位模式技巧；如果后端对 `i128` 除法
  的 legalization 本身有问题，如实诊断报告，不要在错误的假设上硬写代码）、
  反汇编确认无自递归、fuzz + 显式边界值 + 负控制。
- **完成后立即导出 patch**（不要延后），追加进对应 `series`。
- 完成后必须在任务文件里写「完成区」+ subagent 自审「审阅记录」（含逐条 finding
  + 判决）。

## 背景

`ML-038a` 修复 `__int128` 返回值 CallingConv 崩溃后，`pr49218.c`/`pr84748.c`
两个文件从编译期崩溃变成链接期缺符号：`__fixsfti`（`float`→`__int128`
转换）、`__udivti3`（无符号 128 位除法）。这暴露出 `softfloat_shim.c`
从未实现任何 `__int128` 相关的 compiler-rt libcall——此前这类符号缺口一直
被更前置的编译期崩溃掩盖，从未真正被链接阶段触达过。

架构师已独立复现两个具体链接错误：

```
ld.lld: error: undefined symbol: __fixsfti
>>> referenced by pr49218.c:(main)
ld.lld: error: undefined symbol: __udivti3
>>> referenced by pr84748.c:(foo)
```

## 目标

1. **摸清范围**：全量 `gcc-c-torture` 重扫（当前基线 `1471/96/126/15`），
   在 126 个 `FAIL_LINK` 文件里逐一识别 undefined symbol，筛出所有
   `ti`/`ti2`/`ti3`/`ti4` 后缀的 128 位宽 libcall（`compiler-rt` 命名
   惯例参考 `.work/source/llvm/compiler-rt/lib/builtins/` 目录下
   `*ti3.c`/`*ti2.c` 等文件名），统计每个符号被几个文件引用。
2. **逐个实现**：按 `compiler-rt` 对应源文件的算法逻辑重写成
   `softfloat_shim.c` 风格（纯位模式/整数运算，不引入自递归，参照上面
   硬约束的方法论）。不要求本任务必须覆盖 `compiler-rt` 定义的全部
   128 位 libcall——只需要覆盖本次 gcc-c-torture 重扫实际暴露出的需求，
   多余的可以不做，但要在完成区写清楚"实现了哪些、还有哪些
   compiler-rt 有但本语料库未触达、未实现"。
3. **验证**：反汇编确认无自递归；fuzz + 显式边界值（0、全 1、符号相关的
   边界如 `INT128_MIN`、除以 1、除以自身等）+ 负控制，对拍原生 128 位
   算术（宿主机 GCC/Clang 通常原生支持 `__int128`，可以直接用宿主机
   编译对拍，不需要额外软件模拟）。

## 验收

- `docs/issues.yaml` `musl-softfloat-shim-missing-int128-arith-libcalls`
  提到的 `pr49218.c`/`pr84748.c` 用 `python3 tests/scripts/
  gcc_torture_sweep.py --filter "pr49218|pr84748"` 重跑，确认转 PASS
  （如果范围摸查后发现还有其它文件依赖同类符号，一并覆盖并如实报告）。
- 反汇编确认新增函数无自递归 `call`。
- fuzz + 显式边界值测试，对拍宿主机原生 128 位算术结果，含负控制。
- 全量 `gcc-c-torture` 重扫（当前基线 `1471/96/126/15`），逐文件 diff
  确认零回归。
- 全量 `llvm-lit tests/lit/E2E/`（当前基线 79/79）：零回归。
- `python3 tools/run_differential.py`：AGREE 数与当前基线一致、DIVERGE=0。
- `python3 scripts/manifest_check.py`/`check_issues.py` 通过；
  `musl-softfloat-shim-missing-int128-arith-libcalls` 状态更新为 closed
  并迁移到 `docs/issues-archive.yaml`（如果摸查后确认还有 compiler-rt
  定义但本语料库未触达的符号未实现，可以在关闭说明里如实注明"仅覆盖本次
  暴露的需求"，不必因此阻塞关闭）。
- musl 侧改动用**普通** `git commit` 落地，`git format-patch` 导出对应
  patch，追加进 `series`；独立验证可在干净 pin-commit checkout 上 `git am`
  成功，且 replay tree 与开发树 tree hash 一致。

## 参考指针

- `docs/issues.yaml` `musl-softfloat-shim-missing-int128-arith-libcalls`
  （完整背景，架构师已独立复现的两个具体链接错误）
- `.work/source/llvm/compiler-rt/lib/builtins/`（`fixsfti.c`/`udivti3.c`
  等权威参考实现，命名惯例可以据此枚举其它可能需要的符号）
- `src/internal/dadao/softfloat_shim.c`（现有符号写法风格，`ML-022a`/
  `ML-025a`/`ML-028a`/`ML-037a` 建立的方法论）
- `.work/source/llvm-test-suite/SingleSource/Regression/C/gcc-c-torture/execute/
  {pr49218,pr84748}.c`（原始复现源码）
- `code-agent/tasks/ML-037a-implement-divsc3-softfloat-shim.md` 完成区
  （最近一次同类符号缺口任务的方法论范本，包括 fuzz oracle 选择的踩坑
  记录——原生宿主机运算符可能启用 FMA 等编译器优化导致假阳性不一致，
  `__int128` 整数运算没有这个问题但如果后续任务涉及 128 位浮点转换要
  留意类似陷阱）
- `feedback_volatile_needed_for_memory_verification_tests`（如果验证测试
  涉及写读回校验，记得用 volatile + 负控制）
