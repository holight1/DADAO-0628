# ML-022a: 极简软浮点 shim（7 符号）——真正 link+跑通整数格式 printf（roadmap B 收尾）

**执行环境**: 本地 subagent

**状态**: 已完成

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

## 完成区

**状态**：已完成

**修改文件**：
- `.work/source/musl/src/internal/dadao/softfloat_shim.c`（新增，普通 `git commit`
  落地在 `.work/source/musl` 仓库，commit `fe3f43b6`）——实现 10 个符号（见下方
  "与任务原文的出入"）：`__adddf3`/`__subdf3`/`__muldf3`/`__nedf2`/`__eqdf2`/
  `__unorddf2`/`__fixdfdi`/`__fixunsdfdi`/`__floatsidf`/`__floatunsidf`
- `components/musl/patches/0010-dadao-add-IEEE-754-binary64-soft-float-shim-for-vfpr.patch`（新增，`git format-patch` 导出）
- `components/musl/patches/series`（追加一行）
- `tests/lit/E2E/musl_printf_int.test`（新增）
- `tests/lit/E2E/Inputs/musl_printf_int.c`（新增）
- `docs/issues.yaml`（新增 1 条 open issue：
  `musl-vfscanf-missing-single-precision-and-divide-softfloat-symbols`）

**与任务原文的三处出入（均已如实修正，非隐瞒）**：

1. **7 个符号 → 10 个符号**：独立重跑架构师原始 repro（`clang --target=dadao -O2`
   编译 `printf("value=%d\n", 42); return 42;`，`ld.lld --static` 链接
   `crt1.o` + 该 `.o` + 当前 `.work/build/musl/lib/libc.a`）发现**10** 个未定义
   符号，不是 7 个：原 7 个（`__adddf3`/`__subdf3`/`__nedf2`/`__fixdfdi`/
   `__fixunsdfdi`/`__floatsidf`/`__floatunsidf`）之外还有 `__eqdf2`/`__muldf3`/
   `__unorddf2`。`llvm-nm -u obj/src/stdio/vfprintf.o` 证实这 10 个符号都是
   `vfprintf.c`/`printf_core` 直接引用的（整个翻译单元同时含 %f/%g/%e 与
   %d/%u 路径，不管运行时用哪个格式符都要 type-legalize 全部）。按任务本身的
   应急条款（"如果这 7 个不够…可以在本任务范围内继续补，只要总数仍然是个位数/
   十几个以内的小集合"）在本任务内直接补齐了全部 10 个，未回头找架构师，也未
   缩水到只做 7 个再谎报"完成"。
2. **落地目录 `arch/dadao/` → `src/internal/dadao/`**：任务文件原文断言
   "`arch/dadao/` 由 `ARCH_GLOBS`/`ARCH_SRCS` 自动 glob 进构建"——**这个断言是
   错的**。实测：把文件放在 `arch/dadao/` 后 `make build-musl` 的 fresh 对象数
   完全不变（1336，未新增），因为 `Makefile:21-23` 的
   `ARCH_GLOBS = $(addsuffix /$(ARCH)/*.[csS],$(SRC_DIRS))` 里
   `SRC_DIRS = src/* crt ldso $(MALLOC_DIR)...`——只 glob `src/*/dadao/`、
   `crt/dadao/`、`ldso/dadao/`、mallocng 的 `dadao/` 子目录，`arch/dadao/`
   本身只放头文件（`syscall_arch.h` 等），从来不会被自动编译。改放
   `src/internal/dadao/`（`src/internal` 本身是 `src/*` 的一员，且已有
   `src/internal/i386/` 的先例）后，`make build-musl` 的成功对象数从 1336
   变成 1337（+1，即本文件），确认真正被编译进 `libc.a`。
3. **patch 编号 `0011` → `0010`**：任务文件写"导出为 `0011-...patch`"，但
   `components/musl/patches/` 实际只到 `0009`（`ls` 核实，没有已存在的
   `0010`），按顺序应该是 `0010`。已用 `0010` 落地，未凭空跳号。

**验收结果（真实输出，非估算）**：

1. **架构师给出的整数格式 printf 最小复现**（`clang --target=dadao -O2` 编译
   → `ld.lld --static -T tests/scripts/dadao.ld` 链接真实
   `.work/build/musl/lib/{crt1.o,libc.a}`）：
   - 链接**成功**（此前报 10 个 undefined symbol，加入 shim 后 0 个）。
   - QEMU：`exit=42`，stdout 含 `value=42`。
   - gem5：`SIM_END: trap-exit code=42`，stdout 含 `value=42`。
2. **`tests/lit/E2E/musl_printf_int.test`**（新增）：双后端 PASS，
   `FileCheck --check-prefix=MARKER` 真实匹配 QEMU/gem5 各自 stdout 里的
   `value=42`（不是只判 exit code）。
3. **全量 `lit -v tests/lit/E2E/`**：**62/62 PASS（100.00%）**——基线 61（任务
   文件写的"当前基线 61/61"，落地前重新确认过一次）+ 本任务新增 1 个
   （`musl_printf_int.test`），零回归。
4. **`python3 tools/run_differential.py`**：
   `AGREE(3-way)=200 gem5-SKIP=2 DIVERGE=0` / `AGREE(4-way)=200
   Sail-SKIP=2 SAIL-DIVERGE=0`——与既有基线完全一致（本任务不改任何指令
   语义，只加 musl 侧 C 库符号，预期零变化，实测确认零变化）。
5. **`python3 scripts/manifest_check.py`**：`manifest validation: PASS`。
   **`python3 scripts/check_issues.py`**：`Open: 23 / Closed: 34 / Total: 57
   / ISSUE REGISTRY: PASS`（Open 从 22 变 23，正是本任务新增的那条 vfscanf
   issue）。
6. **musl 全量 fresh 重建**（`rm -rf .work/build/musl/obj lib/libc.a
   lib/crt1.o` 后 `make build-musl`）：成功对象数 **1337**（较 ML-021a 基线
   1336 恰好 +1，即本文件），失败对象数仍是**同一批 10 个**
   （`legacy/daemon.o` `locale/dcngettext.o` `network/res_msend.o`
   `process/{execle,execl,execlp,execvp}.o` `regex/{glob,regcomp}.o`
   `unistd/getcwd.o`——逐个核对文件名与 ML-021a 记录的清单完全一致），
   **零新增失败、零回归**。
7. **`__nedf2` 自我递归陷阱**：按任务要求专门核查——`__nedf2`/`__eqdf2` 均只用
   整数位模式比较（`cmp_nonequal` 共享实现，`aRep != bRep` 是 `uint64_t`
   比较不是 `double` 比较），**全文件 10 个函数没有任何一处对 `double` 操作数
   使用原生 `+ - == != <` 运算符**。独立编译单文件后 `llvm-objdump -dr`
   反汇编全文核查（非仅 `nm -u`）：整个 1068 行反汇编里只有唯一 1 处
   `call` 指令（`__subdf3` 调 `__adddf3`），没有任何函数调用自身——排除了
   自递归风险（subagent 复核，见下方审阅记录）。
8. **vfscanf 侧**：按任务要求独立验证、未假设 printf 通了 scanf 也通。
   `scanf("%d", &x)` 编译后链接同一份 `libc.a`，报 **6 个新的**未定义符号：
   `__divdf3` `__extendsfdf2` `__floatsisf` `__gedf2` `__mulsf3`
   `__truncdfsf2`——根因是 `vfscanf.o` 本身不直接引用任何符号，而是引用
   `__floatscan`（`src/internal/floatscan.c`），后者需要的符号集合比
   `vfprintf.o` 大得多、且引入了本任务完全未涉及的**单精度 f32 精度族**
   （`__extendsfdf2`/`__floatsisf`/`__mulsf3`/`__truncdfsf2`）和**除法算法**
   （`__divdf3`，本任务的 add/sub/mul/fix/float 都没有除法）。已登记为新
   open issue（`docs/issues.yaml`
   `musl-vfscanf-missing-single-precision-and-divide-softfloat-symbols`），
   **未在本任务内顺手实现**——按 DS-common 任务分级原则，引入全新精度族+
   新算法属于"需要先想清楚再动手"的独立任务范围，不是"同精度族再补几个"的
   延伸，建议后续任务跟进。
9. **patch 导出 + 独立验证**：`git format-patch -1 HEAD` 导出
   `0010-...patch`，追加进 `series`。独立验证：全新 `git clone`、
   `checkout` 到 pin commit `9e51f0ed`（补丁前一个 commit）、`git am`
   干净应用（`am exit=0`），`diff -r` 结果文件与工作树逐字节一致。

**遗留问题**：
- `musl-vfscanf-missing-single-precision-and-divide-softfloat-symbols`
  （新登记 open issue）——scanf 整数格式路径仍未真正 link 通，需要独立任务
  实现单精度 f32 软浮点家族 + `__divdf3`/`__gedf2`。
- 10 个失败对象（`daemon.o`/`dcngettext.o`/`res_msend.o`/
  `exec{le,l,lp,vp}.o`/`glob.o`/`regcomp.o`/`getcwd.o`）——ML-021a 已登记的
  既有缺口，本任务未触碰，逐一核对确认与本任务改动无关。

## 审阅记录（subagent）

### 判决：Accepted（零 finding 需要修改）

subagent（general-purpose agent）已读 `reviewer.md`，独立执行以下核验（非仅采信
完成区转述，逐条真实命令重跑）：

1. **自递归陷阱**：逐行读 10 个函数体，确认全部只操作 `rep_t`
   （uint64_t）——无任何对 `double` 操作数的原生 `+ - == != <`。独立编译后
   `llvm-objdump -dr --triple=dadao` 反汇编全文核查：整个反汇编（1068 行）
   只有唯一 1 处 `call` 指令（`__subdf3` 调 `__adddf3`），无任何函数调用
   自身 ✓。
2. **尾调用规避**：核对 `arch/dadao/arch.mak:31` 确有
   `CFLAGS_AUTO += -fno-optimize-sibling-calls`，且经 `CFLAGS_AUTO` 全局
   生效（非按文件）。独立用真实编译器分别加/不加该 flag 编译本文件：
   **不加**——真实复现声称的崩溃（`SelectionDAGBuilder` 里
   `LowerCall emitted a return value for a tail call!` 断言，选择
   `__subdf3` 时触发）；**加**——编译干净（exit 0）。声称的机制真实成立，
   非编造 ✓。
3. **落地目录**：核对 `Makefile:23`
   `ARCH_GLOBS = $(addsuffix /$(ARCH)/*.[csS],$(SRC_DIRS))` 且
   `SRC_DIRS` 含 `src/*`（含 `src/internal`），确认 `src/internal/dadao/`
   真被自动 glob；核对 `arch/dadao/` 只有头文件+`arch.mak`，无 `.c`，
   确认放那里不会被自动编译 ✓。
4/5. **数值正确性/边界**：独立写了一套原生 fuzz 对拍工具（改名避免与
   libgcc 符号冲突，同一份算法在 x86-64 原生编译，对拍真实硬件 double
   运算），跑约 20 万随机 64-bit 位模式 + 精选边界集（±0.0、次正规数含
   最小 denormal `5e-324`、`DBL_MAX`、2^52/2^53 边界、±inf、NaN、
   `fixdfdi`/`fixunsdfdi` 的 2^63/2^64 溢出边界、`float{s,uns}idf` 的
   `INT32_MIN`/`INT32_MAX`/`UINT32_MAX`）跑 add/sub/mul/eq/ne/unord/fix/
   float 全部 8 类操作——**0 处不一致**（`TOTAL FAILS: 0`）。`__floatsidf`
   的 `INT32_MIN` 无符号取负技巧也在其中验证正确 ✓。
6. **`__int128` 隐藏依赖**：独立编译后 `llvm-nm -u` 确认 0 个未定义符号，
   `wideMultiply` 未引入 `__multi3` 类依赖 ✓。
7. **build/nm 检查的局限性**：意识到 `nm -u` 本身查不出"已解析的自调用"，
   补充读反汇编全文（见第1条），非仅信 nm 输出 ✓。
8. **测试文件**：核对 `lit.cfg` 里 `%qemu`/`%gem5`/`%ld.lld` 等替换全部指向
   真实二进制（非桩）；独立单独跑
   `lit -v tests/lit/E2E/musl_printf_int.test` **PASS**；确认
   `FileCheck` 断言的是 QEMU/gem5 各自真实 stdout 里的 `value=42`
   内容，非仅判 exit code ✓。
9. **issues.yaml 新条目**：`check_issues.py` PASS；独立编译链接
   `scanf("%d", &x)` 复现，ld.lld 报出的未定义符号（`__truncdfsf2`/
   `__divdf3`/`__floatsisf`/`__mulsf3`/`__extendsfdf2`/`__gedf2`）与
   yaml 条目描述的 6 个symbol 逐一对应，未夸大 ✓。
10. **patch/series**：`git diff HEAD~1 HEAD` 与导出的 `0010-...patch`
    内容逐字节一致（仅 `git format-patch` 版本页脚不同，属预期）；
    `series` 文件最后一行正确追加 ✓。

**finding**：无（判决=通过，零 finding 需要处置，故无处置表）。
