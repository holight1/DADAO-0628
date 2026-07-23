# ML-022a: 极简软浮点 shim（7 符号）——真正 link+跑通整数格式 printf（roadmap B 收尾）

**执行环境**: 本地 subagent

**状态**: 待处理

## 硬约束（务必遵守，违反视为任务失败）

- **禁止**对 `.work/llvm`、`.work/source/musl` 做 `git rebase`/`git am` 重放整条历史/
  `git reset --hard` 到早于当前 HEAD 的操作。只允许在当前 HEAD 基础上新增普通 `git commit`。
- 本任务**只写 musl 侧的软浮点符号实现**（新文件放 `arch/dadao/` 下，`ARCH_GLOBS` 会
  自动 glob 进构建，不需要改 Makefile），**不改 LLVM**、**不接入 compiler-rt 组件**
  ——这是 ML-020a 当时评估过的选项 A（缺口小则手写 shim），现在缺口已经精确确认
  只有 7 个符号，走这条路线是本任务明确授权的范围。
- **完成后立即导出 patch**（不要延后）：`components/musl/patches/0011-...patch`，
  追加进 `series`。
- 完成后必须在任务文件里写「完成区」+ subagent 自审「审阅记录」（含逐条 finding + 判决）。

## 背景

roadmap B（`docs/reviews/ML-017d-final-handoff-roadmap-20260721.md` §5）的验收门槛
是"link+跑通整数格式的 printf/scanf"，不是"编译过"。`ML-021a` 修复了 `CALLSEQ_START/
END` glue 链缺陷后，`vfprintf.o` 终于能用 musl 真实构建标志编译通过，但**链接期**
还没验证过。架构师已直接尝试链接一个最小整数格式 printf 程序：

```c
#include <stdio.h>
int main(void) { printf("value=%d\n", 42); return 42; }
```

用 `clang --target=dadao -O2` 编译通过，`ld.lld --static` 链接 `crt1.o` + 该 `.o` +
`.work/build/musl/lib/libc.a` 时报错，**精确列出 7 个未定义符号**（架构师已核实
这是完整清单，非估算）：

```
__adddf3  __subdf3  __nedf2  __fixdfdi  __fixunsdfdi  __floatsidf  __floatunsidf
```

这正是 ML-020a 任务文件里预先设计好的「选项 A」触发条件（"缺的符号集合很小...手写
一个极简的 DADAO 侧软浮点 shim"）——现在缺口已经精确确认到只有这 7 个符号，可以
直接执行选项 A，不需要再判断走 A 还是 B。

## 目标

1. 在 `.work/source/musl/arch/dadao/` 下新增一个 C 源文件（文件名自定，例如
   `softfloat_shim.c`），实现上述 **7 个符号**，全部是 IEEE-754 binary64（`double`）
   语义的标准 GNU libgcc/compiler-rt 风格实现：
   - `__adddf3`/`__subdf3`：double 加减法
   - `__nedf2`：double 不等比较（返回非 0 表示不等且非 unordered，语义参照下面的
     参考实现）
   - `__fixdfdi`：double → int64_t（截断取整）
   - `__fixunsdfdi`：double → uint64_t（截断取整）
   - `__floatsidf`：int32_t → double
   - `__floatunsidf`：uint32_t → double
   - 只需要覆盖 musl `vfprintf.c`/`vfscanf.c` 实际会调用到的这 7 个符号，**不要**
     顺手实现乘除/更多比较函数等这次没被链接期报出来的符号——这是精确匹配的最小
     shim，不是要做一个完整 libgcc 替代品。
2. **可以参照**（不是照抄整个文件，是借算法思路）`.work/source/llvm/compiler-rt/
   lib/builtins/{adddf3,subdf3,fixdfdi,fixunsdfdi,floatsidf,floatunsidf,
   comparedf2}.c` 的算法（这些文件依赖 compiler-rt 自己的 `int_lib.h`/`fp_lib.h`
   宏基础设施，本任务的实现不需要引入这套基础设施——用直接的位操作/`union`
   技巧写独立、自包含的实现，不要尝试把 compiler-rt 的头文件体系整个搬进 musl）。
   `__nedf2` 的语义可以用最简单的方式实现（两个 double 按 IEEE-754 规则直接比较
   `a != b`，用 C 内建的 `!=` 运算符在纯 C 里写，不需要手动拆位比较，因为这个符号
   只是给编译器在软浮点合法化路径里发出的调用用，函数体内部可以用编译器已经支持
   的整数运算实现，不涉及递归依赖同名 libcall——**需要你自己验证这一点不会导致
   编译器又对这个符号本身的实现发出软浮点 libcall 调用造成循环依赖**，如果发现
   会循环，改用手动位操作实现）。
3. 用架构师给出的整数格式 printf 最小复现验证 link 成功、**双后端实际运行**、
   输出内容正确（`value=42`）、退出码正确（42）。
4. 新增 `tests/lit/E2E/musl_printf_int.test` + `Inputs/*.c`（真实 `printf` 整数格式，
   避开已知的 `varargs-pointer-args-lost-rb-bank-save-area` 指针变参缺口——只用
   `%d`/`%u` 之类整数格式说明符），双后端 exit=42 + FileCheck 真实断言输出内容
   `value=42`。

## 验收

- 架构师给出的整数格式 printf 最小复现：编译+链接+双后端运行，输出
  `value=42\n`，exit=42。
- 新增 `tests/lit/E2E/musl_printf_int.test`：双后端 PASS，FileCheck 真实匹配输出。
- 全量 `llvm-lit tests/lit/E2E/`：零回归（当前基线 61/61，落地前重新跑一次记录
  当前值为准）。
- `python3 tools/run_differential.py`：AGREE 数与当前基线一致、DIVERGE=0（本任务
  不改指令语义）。
- `python3 scripts/manifest_check.py`/`check_issues.py` 通过。
- musl 侧改动用**普通** `git commit` 落地，`git format-patch` 导出为
  `components/musl/patches/0011-....patch`，追加进 `series`；独立验证可在干净
  pin-commit checkout 上 `git am` 成功。
- 报告链接后是否还有其它未定义符号（比如 `vfscanf.c` 走到的路径是否需要额外符号，
  不要假设跟 `vfprintf` 完全一样）——如实报告，不要只验证 `printf` 就假设 `scanf`
  也一定通。
- 如果验证中发现这 7 个符号不够（链接时冒出新的未定义符号），如实报告新缺口清单，
  可以在本任务范围内继续补（只要总数仍然是"个位数/十几个以内"的小集合），不要在
  没有和架构师沟通的情况下就判定"缺口太大回退到选项B"——先如实报告实际链接结果。

## 参考指针

- `code-agent/tasks/ML-020a-f64-softfloat-libcall-vfprintf.md` 完成区（roadmap B
  第一阶段，选项 A/B 决策框架的出处）
- `code-agent/tasks/ML-021a-direct-call-glue-chain-multicall-block.md` 完成区
  （vfprintf.o 编译通过的前置修复）
- `docs/reviews/ML-017d-final-handoff-roadmap-20260721.md` §5 路线 B（roadmap B
  完整验收门槛原文）
- `.work/source/llvm/compiler-rt/lib/builtins/{adddf3,subdf3,fixdfdi,fixunsdfdi,
  floatsidf,floatunsidf,comparedf2}.c`（算法参考，不是要移植的对象）
- `.work/source/musl/arch/dadao/`（新文件的落地目录；`Makefile` 里
  `ARCH_GLOBS`/`ARCH_SRCS` 自动 glob 进构建，不需要额外接线）
- `docs/issues.yaml` `varargs-pointer-args-lost-rb-bank-save-area`（新测试必须避开
  的已知缺口）
- `.work/build/musl/lib/{crt1.o,libc.a}`（`make build-musl` 重新生成）
