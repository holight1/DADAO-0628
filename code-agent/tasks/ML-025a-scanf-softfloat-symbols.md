# ML-025a: 补齐 scanf 缺失的 6 个软浮点符号——真正 link+跑通整数格式 scanf

**执行环境**: 本地 subagent

**状态**: 待处理

## 硬约束（务必遵守，违反视为任务失败）

- **禁止**对 `.work/llvm`、`.work/source/musl` 做 `git rebase`/`git am` 重放整条历史/
  `git reset --hard` 到早于当前 HEAD 的操作。只允许在当前 HEAD 基础上新增普通 `git commit`。
- 本任务**只写 musl 侧的软浮点符号实现**，不改 LLVM、不接入 compiler-rt 组件——延续
  `ML-022a` 已经走通的路线（当时是 10 个双精度符号，这次是 6 个，含单精度族 + 除法，
  规模仍在"小缺口手写 shim"范围内）。
- **完成后立即导出 patch**（不要延后）：`components/musl/patches/0012-...patch`，
  追加进 `series`。
- 完成后必须在任务文件里写「完成区」+ subagent 自审「审阅记录」（含逐条 finding + 判决）。

## 背景

`docs/issues.yaml` 的 `musl-vfscanf-missing-single-precision-and-divide-softfloat-symbols`
条目（`ML-022a` 登记）：`scanf("%d", &x)` 编译通过后链接报 6 个未定义符号：
`__divdf3`、`__extendsfdf2`、`__floatsisf`、`__gedf2`、`__mulsf3`、`__truncdfsf2`——
根因是 `vfscanf.o` 依赖 `src/internal/floatscan.c`（浮点数值解析辅助），它需要的符号
集合比 `vfprintf.o` 更大，引入了 `ML-022a` 完全没覆盖的**单精度 f32 家族**
（`__extendsfdf2`/`__floatsisf`/`__mulsf3`/`__truncdfsf2`）和**除法算法**
（`__divdf3`），外加一个双精度比较符号（`__gedf2`，`ML-022a` 已实现了
`__eqdf2`/`__nedf2`/`__unorddf2` 但没实现 `__gedf2`/`__ledf2`/`__ltdf2`/`__gtdf2`
这几个"有序关系"比较）。

`ML-022a` 已经在 `.work/source/musl/src/internal/dadao/softfloat_shim.c` 建立了完整的
方法论范式：自包含实现（不引入 compiler-rt 的 `int_lib.h`/`fp_lib.h`）、只用位模式
整数运算（避免对 `float`/`double` 用原生 `+-*/==!=<` 导致自递归 libcall）、
fuzz 测试对拍原生硬件运算、`-fno-optimize-sibling-calls` 处理尾调用陷阱。本任务
**沿用同一个文件**（追加函数，不新建文件），同一套方法论。

## 目标

1. 在 `.work/source/musl/src/internal/dadao/softfloat_shim.c` 追加 6 个符号的实现：
   - `__extendsfdf2`：`float`（32位）→ `double`（64位）精确提升（无精度损失，
     必须做的只是指数偏移调整 + 尾数左移 + 处理特殊值）。
   - `__truncdfsf2`：`double` → `float`（有精度损失，需要正确舍入——参照
     `ML-022a` 已实现的 round-to-nearest-even 逻辑）。
   - `__floatsisf`：`int32_t` → `float`（可以参照已有的 `__floatsidf` 改写成
     32 位尾数版本）。
   - `__mulsf3`：`float` × `float`（32位乘法，可以参照已有的 `__muldf3` 改写成
     32位版本，不需要 128位宽乘法，`unsigned long long`/`unsigned __int128`
     视精度需要选择）。
   - `__gedf2`：`double` 有序关系比较（GNU/libgcc 约定：返回 ≥0 表示 `a>=b`，
     负数表示 `a<b` 或 unordered——**注意这个返回值约定和 `ML-022a` 已实现的
     `__eqdf2`/`__nedf2`"返回0表示相等"的约定不同**，落地前先确认清楚
     `TargetLowering::softenSetCCOperands` 对 `__gedf2` 的返回值语义预期
     （参照 `.work/source/llvm/compiler-rt/lib/builtins/comparedf2.c` 里
     `__gedf2`/`__ledf2`/`__ltdf2`/`__gtdf2` 的返回值约定作为算法参考，不要
     直接照抄整个文件的基础设施）。
   - `__divdf3`：`double` ÷ `double`（可以用 Newton-Raphson 迭代或直接长除法，
     参照 `.work/source/llvm/compiler-rt/lib/builtins/divdf3.c` 的算法思路，
     同样只用位模式整数运算，不引入 compiler-rt 头文件依赖）。
2. **必须验证自递归陷阱**（`ML-022a` 强调过的同一个坑）：这 6 个函数的实现体内部
   绝不能对 `float`/`double` 操作数使用原生 `+ - * / == != < >` 运算符——用反汇编
   全文核查（不是只看 `nm -u`），确认没有任何函数间接/直接调用自身。
3. 用 `scanf("%d", &x)` 最小复现验证 link 成功、双后端实际运行、结果正确。
4. 新增 `tests/lit/E2E/musl_scanf_int.test`（管线范式参照 `musl_printf_int.test`，
   注意 scanf 需要输入源——检查现有 lit.cfg 里 QEMU/gem5 的 stdin 注入机制是否已有
   先例可以复用，如果没有需要判断怎么给被测程序提供输入，不要凭空假设）。

## 验收

- `scanf("%d", &x)` 最小复现：编译+链接+双后端运行，结果正确、exit 码符合预期。
- `tests/lit/E2E/musl_scanf_int.test`：双后端 PASS，真实断言 scanf 解析结果正确
  （不只是"没崩溃"）。
- 全量 `llvm-lit tests/lit/E2E/`：零回归（当前基线 65/65，落地前重新跑一次记录
  当前值为准）。
- `python3 tools/run_differential.py`：AGREE 数与当前基线一致、DIVERGE=0。
- `python3 scripts/manifest_check.py`/`check_issues.py` 通过。
- musl 侧改动用**普通** `git commit` 落地，`git format-patch` 导出为
  `components/musl/patches/0012-....patch`，追加进 `series`；独立验证可在干净
  pin-commit checkout 上 `git am` 成功。
- 关闭 `docs/issues.yaml` 的 `musl-vfscanf-missing-single-precision-and-divide-
  softfloat-symbols` 条目（若真正解决，移入 `docs/issues-archive.yaml`）。
- 若验证中发现链接期还冒出这 6 个之外的新符号缺口：如实报告，若数量仍小可以
  在本任务范围内继续补（参照 `ML-022a` 从7个发现到实际10个的先例），若数量大
  则如实报告缺口清单交还架构师判断，不要强行绕过。
- 不要把本任务的通过等同于 vfscanf 所有格式说明符（`%f`/`%e`/`%g` 等浮点格式）
  都已验证——本任务只要求整数格式 `%d`/`%u` 类的 scanf 真正 link+跑通，浮点格式
  scanf 的运行时正确性不在本任务范围（`__gedf2` 等符号是编译期需要，不代表浮点
  scanf 的运行时语义已被验证）。

## 参考指针

- `docs/issues.yaml` `musl-vfscanf-missing-single-precision-and-divide-softfloat-symbols`
  （本任务对应的缺口清单原文）
- `.work/source/musl/src/internal/dadao/softfloat_shim.c`（ML-022a 已实现的 10 个
  双精度符号，本任务追加函数到同一文件，同一方法论——尤其注意文件头部关于
  自递归陷阱、尾调用陷阱的注释）
- `code-agent/tasks/ML-022a-softfloat-shim-vfprintf-link.md` 完成区（完整的
  方法论范式：fuzz 测试、负控制、反汇编核查自递归、`-fno-optimize-sibling-calls`）
- `.work/source/llvm/compiler-rt/lib/builtins/{extendsfdf2,truncdfsf2,floatsisf,
  mulsf3,divdf3,comparedf2}.c`（算法参考，不是要移植的对象）
- `tests/lit/E2E/musl_printf_int.test`（最新管线范式参照）
- `.work/build/musl/lib/{crt1.o,libc.a}`（`make build-musl` 重新生成）
- `tests/scripts/dadao.ld`（链接脚本，必须用它）
- `feedback_volatile_needed_for_memory_verification_tests`（若新测试涉及写读回
  校验也要用 `volatile`，参照 `~/knowledge-graph/compiler-backend/07-isa-baremetal-
  test-harness.md` 里对应的模式节点）
