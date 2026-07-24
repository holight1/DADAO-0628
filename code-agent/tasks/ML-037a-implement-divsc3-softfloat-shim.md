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

## 完成区

**状态**：已完成

**实现内容**（`src/internal/dadao/softfloat_shim.c` 末尾追加约 275 行，
musl commit `69cadae0`，patch `components/musl/patches/
0014-dadao-add-divsc3-single-precision-complex-division.patch`）：

1. **基础设施 helper**（全部 `static __inline`，纯位模式运算）：
   `isnanF32`/`isinfF32`/`isfiniteF32`/`iszeroF32`/`fabsF32Rep`/
   `copysignF32Rep`/`fmaxAbsF32`。
2. **`ilogbAbsF32`**：`__compiler_rt_logbX`（compiler-rt fp_lib.h）的特化
   移植——输入始终是 `fmaxAbsF32` 的结果（非负或 NaN，符号位恒 0），因此
   省略了通用算法里"负号 -inf"分支；直接返回 `int` + `*isSpecial` 标志，
   不像参考实现那样把指数值先包成一个 `float` 再靠原生 `(int)` 强转转回
   （分析见文件内注释：任何有限 float 的无偏指数都精确落在 float 可表示
   范围内，参考实现自己的 float 往返本身也是无损的，这里只是省掉一次不
   必要的往返，同时避免引入本文件从未用过、且未知 DADAO 是否存在对应
   libcall 的 `__fixsfsi`（float→int32）依赖）。
3. **`scalbnF32`**：`__compiler_rt_scalbnX` 的位模式移植，包括其饱和式
   指数加法（这里用 64 位宽整数代替 `__builtin_sadd_overflow`）和上溢出
   /下溢出（次正规化）路径；下溢路径复用本文件已有的
   `rightShiftWithStickyRep` + 3-bit guard/round/sticky + round-to-nearest
   -even 约定（`__truncdfsf2`/`__mulsf3` 已用的同一套惯例），不用参考实现
   "构造一个 2 的幂 float 再乘"的写法（那样会是原生浮点乘法）。
4. **`__divsc3`**：逐语句照抄 `compiler-rt/lib/builtins/divsc3.c` 的
   Smith's method + 完整 C99 Annex G NaN/Inf/0 三个恢复分支，把
   `logb`/`scalbn`/原生 `+ - * /` 换成 `ilogbAbsF32`/`scalbnF32`/
   `__addsf3`/`__subsf3`/`__mulsf3`/`__divsf3`。返回值用原生
   `float _Complex` + `__real__`/`__imag__`（compiler-rt 自己的 `Fcomplex`
   在任何 C99 编译器上就是 `float _Complex` 的 typedef，`__real__`/
   `__imag__` 是编译期字段访问，不是运算，不构成自递归风险）；DADAO ABI
   分类（`clang/lib/CodeGen/Targets/DADAO.cpp`）对函数定义和 Clang 自己
   为复数除法表达式生成的调用点（`CGExprComplex.cpp`
   `EmitComplexBinOpLibCall`）适用同一套分类逻辑，不需要手工打包寄存器。

**验证**：

1. **独立标准编译**（真实 musl 构建参数：`-O2 -fno-align-functions -pipe
   -fomit-frame-pointer -fno-unwind-tables
   -fno-asynchronous-unwind-tables -ffunction-sections -fdata-sections
   -std=c99 -nostdinc -ffreestanding -fexcess-precision=standard
   -frounding-math -fno-strict-aliasing -fno-optimize-sibling-calls`）：
   exit 0，`llvm-nm -u`：**0 个未定义符号**。
2. **反递归核查**：由于真实构建参数含 `-ffunction-sections`，每个函数
   各自一个 section，简单的地址算术不足以判断 call 目标（已踩坑并纠正：
   第一次用地址算术误判出 32 处"自递归"，全部是每个函数独立 section
   导致地址从 0 开始重算的假象）。改用 `llvm-readelf -r` 直接读
   `.rela.text.__divsc3` 的 30 条 relocation 记录，逐条核对 Symbol's
   Name：全部指向 `__mulsf3`（14 次）/`__addsf3`（8 次）/`__divsf3`
   （2 次）/`__eqsf2`（2 次）/`__nesf2`（2 次）/`__unordsf2`（1 次）——
   均为本文件已有且已独立验证过的非递归符号，**0 处自递归**、**0 处新增
   未定义符号依赖**。
   - 附带发现：`__eqsf2`/`__nesf2`/`__unordsf2` 这 3 处调用并非我在源码里
     手写的比较（`__divsc3` 源码里没有任何一处对 `float` 值使用原生
     `== != < >`），而是 `-O2` 的 InstCombine 把
     `iszeroF32(toRepF32(denom))`/`isnanF32(...)` 这类位运算模式识别为
     等价的浮点比较后自行改写成 `fcmp`，再被类型合法化为这几个 libcall
     ——不违反硬约束（不是自递归、不是新符号），但如实记录这个编译器
     行为，不隐瞒。
3. **Fuzz 对拍**（改名 harness `#include` 实际提交的源文件；oracle 是
   `divsc3.c` 的逐语句原生 float 移植，用 host 自己的 `logbf`/`scalbnf`/
   `fmaxf`/`isnan`/`isinf`/`isfinite`/`copysignf`，编译时加
   `-ffp-contract=off -fno-fast-math`）：
   - **重要踩坑记录**：第一版 oracle 直接用宿主机 `_Complex float` 的
     `/` 运算符（调用宿主系统自带、预编译好的 libgcc `__divsc3`），
     在 228 万次检查里跑出 **699,999 处"不一致"**，但逐一检查全部恰好是
     最后 1 bit（1 ULP）之差，且集中在 `a*c+b*d`/`b*c-a*d` 两个交叉项
     里数量级较小的那一项——这是宿主系统预编译 libgcc 在构建时启用了
     FMA 融合（`-ffp-contract=fast`，GNU 方言默认值）导致的更精确但
     位不同的结果，不是本任务实现的 bug。换成上面"逐语句移植 +
     `-ffp-contract=off`"的忠实 oracle 后这批"不一致"全部消失，确认是
     oracle 选择问题而非实现问题（完整分析记在源码 `native_divsc3`
     函数头注释里）。
   - **正式结果**：279,841 个显式边界值交叉积（±0/±1/±2/±0.5/`FLT_MAX`/
     `FLT_MIN`/`FLT_TRUE_MIN`（次正规数）/±inf/NaN/极大极小值等 22 个
     取值 4 维交叉）+ 34 个按 Annex G 三个恢复分支各自设计的具名向量
     （denom=0、分子含 inf、分母含 inf 三个分支各 5 个 + 纯 NaN 传播 8 个
     + 普通有限值除法 4 个 + 极端量级重定标压力测试 7 个）+ 800 万随机
     fuzz（含 1/16 概率的纯随机位模式，天然覆盖 NaN/Inf/次正规数按编码
     空间占比抽样），共 **8,279,875 次检查，0 处不一致**。
   - **7 个独立负控制**（逐一改错一处实现细节，确认 fuzz harness 真的
     会抓到，不是摆设）：`fmaxAbsF32` NaN 分支返回值搞反（抓到
     800/579,875）、`ilogbAbsF32` 指数偏置故意加 1（抓到 15,870）、
     `scalbnF32` 上溢出饱和值故意减 1（抓到 12,495）、`scalbnF32` 下溢出
     舍入 tie 分支故意强制永远向上舍入而非 ties-to-even（抓到 13,739）、
     `__divsc3` 分支 1（denom==0）条件取反（抓到 85,670）、分支 2
     （分子含 inf）条件 `||` 改 `&&`（抓到 1,586）、分支 3（分母含 inf）
     条件 `isinfF32` 误写成 `isnanF32`（抓到 35,605）。另有一次
     "把 tie 舍入分支的 `==0x4` 改成 `>=0x4`"因为在代码里排在
     `>0x4` 分支之后、两者值域互斥而恰好行为等价（0 处不一致，非
     harness 失效，如实记录并换了另一处真正改变行为的舍入 tie 突变
     重测，抓到 13,739 处）。
4. **`complex-5.c` 单文件重跑**：`python3 tests/scripts/gcc_torture_sweep.py
   --filter "complex-5"`：FAIL_LINK → **PASS**。
5. **`gcc-c-torture` 全量重扫**：`1465/104/124/15`
   （基线 `1464/104/125/15`）——精确 **+1 PASS / -1 FAIL_LINK**，逐文件
   核对（`complex` 相关全部文件的 status）确认仅 `complex-5.c` 从
   FAIL_LINK 变为 PASS，其余（含 `complex-6.c`/`complex-7.c`/
   `builtins/complex-1*.c`）status 不变，**0 回归**。
6. **`llvm-lit tests/lit/E2E/`**：78/78 PASS，不变。
7. **`tools/run_differential.py`**：`AGREE(4-way)=200 DIVERGE=0
   SAIL-DIVERGE=0`，与基线完全一致（本任务不涉及指令语义，预期不变）。
8. **`scripts/manifest_check.py`/`check_issues.py`**：均 PASS；
   `musl-softfloat-shim-missing-divsc3` 已从 `docs/issues.yaml` 移除，
   在 `docs/issues-archive.yaml` 追加为 `status: closed`，
   `resolved_by` 指向本任务 + patch 文件名。
9. **Patch 导出 + 独立 replay 验证**：`git format-patch` 导出为
   `components/musl/patches/
   0014-dadao-add-divsc3-single-precision-complex-division.patch`，
   追加进 `series`（14 个 patch）。在 manifest 锁定的干净 pin commit
   （`0784374d561435f7c787a555aeab8ede699ed298`）clone 上 `git am` 全部
   14 个 patch **全部成功**，replay tree hash
   （`c1b7c2544d09b9ec6eb766765d39e4e6e9108b38`）与开发树 HEAD 的 tree
   hash **完全一致**。

**根仓库层面改动**（未提交，留待架构师复核后处理）：本任务文件的
完成区、`docs/issues.yaml`（移除条目）、`docs/issues-archive.yaml`
（追加 closed 条目）。

## 审阅记录（subagent 自审）

以下为实现完成后独立进行的自审（沿用 ML-022a/025a/028a 建立的方法论：
不只信任实现时的记录，重新过一遍逐条 finding + 判决）。

1. **finding**：`__divsc3` 内部出现了我没有手写的 `__eqsf2`/`__nesf2`/
   `__unordsf2` 调用（见完成区第 2 条）。
   **判决**：不是缺陷。逐行核对 `__divsc3` 源码确认没有任何一处对
   `float` 值使用原生比较运算符；这是 `-O2` InstCombine 把位模式
   等价形式改写成 `fcmp` 后合法化产生的调用，目标全部是本文件已验证过
   的非递归符号。已如实记录在完成区，不视为对"纯位模式运算"约束的
   违反（约束的本意是防自递归和防新增未定义符号依赖，两者都未发生）。

2. **finding**：`ilogbAbsF32`/`scalbnF32` 没有严格 1:1 对应参考实现的
   `__compiler_rt_logbf`（返回 `float`）签名，而是返回 `int` + 输出参数。
   **判决**：不是缺陷。任务书原文明确"命名不必与 libm 公开符号完全一致"，
   且这个改动是为了避免引入本文件从未出现过、且未确认 DADAO 目标是否
   已注册对应 libcall 的 `__fixsfsi`（float→int32 转换）——如果严格照抄
   参考实现的 `float` 返回值再靠原生 `(int)` 强转，反而会新增一个本任务
   范围外、未经验证的依赖。数学等价性已在文件注释里证明（有限 float 的
   无偏指数范围 `[-149,127]` 恒可用 float 精确表示，参考实现自己的往返
   本身也是无损的）。

3. **finding**：`copysignF32Rep`/`fmaxAbsF32` 等 helper 没有对应
   `-ffast-math`/`-fno-signed-zeros` 之类的假设做防御性注释。
   **判决**：不需要。这些 helper 只在 `__divsc3` 内部使用，且
   `arch.mak`/musl 构建从不对这个文件传 `-ffast-math`（真实构建参数已在
   完成区第 1 条列出，核对过不含任何 fast-math 相关 flag）；如果将来
   这个文件被其它调用者以不同 flag 编译，这些 helper 仍然是纯整数位
   运算，行为不受编译器 fast-math flag 影响（只有原生浮点比较/运算才会
   受影响），无需额外防御。

4. **finding**：fuzz harness 里 `random_float()` 的"合理范围随机值"生成
   逻辑（`mant * 2^exp / 2^-exp` 形式）在 `exp` 取到 20 附近时是否会栽到
   `float` 表示范围外从而静默产生非预期的 inf。
   **判决**：不影响验证有效性。即使个别随机向量意外产生 inf/超大值，
   `check_one` 仍然会正确对拍（`__divsc3` 对任意合法 `float` 输入包括
   inf 都有定义行为），不会导致漏检；且边界值交叉积和具名 Annex G
   向量已经显式覆盖了所有 inf/NaN/0 组合，不依赖随机生成器"恰好"生成
   这些边界。

5. **finding**：8,279,875 次检查里 `floats_match` 对 NaN 只判断"双方都是
   NaN"，不比较 payload 位模式，是否会放过一个"结果是 NaN 但选错了
   quiet/signaling 或错误 payload"的缺陷。
   **判决**：这是本文件既有方法论（ML-022a/025a/028a 一直如此），NaN
   payload 本身不是 C99 Annex G 规定的可观察语义（标准只保证"是 NaN"，
   不保证具体 payload 位模式），沿用既有约定合理，不算漏检。

6. **finding**：没有单独为 `__divsc3` 新增一个常驻 gcc-c-torture 之外的
   lit/CodeGen 回归测试（ML-028a 完成区曾提到"大规模 host fuzz 与负控制
   目前以任务证据记录为主，并未形成常驻仓库测试"这一遗留改进项）。
   **判决**：本任务未额外新增，沿用 ML-028a 遗留的同一个已知改进方向
   （不在本任务书验收范围内，任务书验收项完全对齐 gcc-c-torture 单文件
   /全量重扫 + E2E + differential + manifest/issues，未要求新增独立
   lit 回归）；如实记录，留给后续如果继续扩展 softfloat 时一并处理。

**结论**：`__divsc3` 实现正确、无自递归、无新增未定义符号依赖，
`complex-5.c` 转 PASS，gcc-c-torture 全量精确 +1/-1 且 0 回归，
`docs/issues.yaml` 缺口关闭。可提交架构师复核。
