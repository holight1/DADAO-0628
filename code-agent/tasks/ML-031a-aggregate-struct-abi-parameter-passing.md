# ML-031a：实现聚合类型（struct）参数传递 ABI——严格按 wiki，解锁 15 个 gcc-c-torture 变参传 struct 用例

**执行环境**: 本地 subagent

**状态**: 已完成（最终独立复审 Accepted）

## 硬约束（务必遵守，违反视为任务失败）

- **禁止**对 `.work/llvm` 做 `git rebase`/`git am` 重放整条历史/`git reset --hard`。
  只允许在当前 HEAD 基础上新增普通 `git commit`。
- **本任务的 ABI 设计严格按 wiki 原文实现，不是开放讨论题**——`~/DADAO-wiki/
  DADAO-21-ABI-应用程序二进制接口.md` §聚合类型参数/§聚合类型返回值/§可变参数
  "大于8字节的聚合变参"三处已经给出完整、精确的规则（下方「wiki 原文」逐字引用），
  照此实现，不要自己设计替代方案。发现 wiki 原文有歧义/内部矛盾之处，参照
  `DL-072a` 的先例——如实记录到 `docs/wiki-questions.md`，保留你认为最合理的
  实现选择并说明理由，不要因为一处歧义就放弃整个任务。
- **HFA（同质浮点聚合，走 RF bank）明确排除在本任务范围外**——DADAO 后端当前
  完全没有注册任何浮点寄存器类、没有 RF bank 的 CodeGen 基础设施（`ML-020a`/
  `ML-025a` 已确认："DADAOISelLowering.cpp 里对 f32/f64 没有任何 setOperationAction/
  寄存器类注册"）。实现 HFA 需要先有完整的浮点 CodeGen 支持，这是一个独立、
  体量对等于"给 DADAO 添加浮点支持"的大工程，不在本任务范围内。**遇到 HFA 场景
  时**：如实报告，登记为独立 issue，不要为了"看起来完整"而勉强拼凑一个不基于
  真实 RF 寄存器的实现。HPA（同质指针聚合，走 RB bank）**在本任务范围内**——RB
  bank 是现有、完整支持的寄存器组，没有类似 HFA 的基础设施缺口。
- **完成后立即导出 patch**（不要延后），追加进对应 `series`。
- 完成后必须在任务文件里写「完成区」+ subagent 自审「审阅记录」（含逐条 finding
  + 判决）。

## wiki 原文（权威依据，逐字引用自 `~/DADAO-wiki/DADAO-21-ABI-应用程序二进制接口.md`
第178-307/362-377行，务必自己完整重读原文，不要只信本任务的引用摘录）

> #### 聚合类型参数：Aggregate parameter
>
> 聚合类型按以下规则传递，最多消耗 4 个寄存器槽位（32 字节）。
>
> **HFA/HPA 递归判定流程**
> 1. **展开（flatten）**：递归展开聚合类型的所有嵌套 struct 成员，得到叶子字段
>    列表。union 直接判定为不满足条件。
> 2. **同质检查**：HFA 要求所有叶子字段为同一浮点类型（float 或 double）；HPA
>    要求所有叶子字段为指针类型（指针指向的具体类型可以不同）。
> 3. **计数检查**：叶子字段总数 ≤ 4。
>
> **同质浮点聚合（HFA）**：满足条件时通过 RF bank 传递，每个叶子字段占1个RF槽位。
> （**本任务不实现**，见硬约束）
>
> **同质指针聚合（HPA）**：满足条件时通过 RB bank 传递，每个叶子字段占1个RB槽位。
> 例：`struct { void *p, *q; }` → RB16,RB17；`struct { int *a,*b,*c,*d; }` →
> RB16-19。以下不是HPA：`struct { void *p; int i; }`（混合类型）。
>
> **不满足 HFA/HPA 条件**：
> - ≤ 32 字节：拆分为 1-4 个 8 字节块，放入 RD bank，**高位块先入高寄存器**
> - > 32 字节：通过指针引用（caller 在栈上分配临时空间，callee 通过 RB bank
>   中的指针访问）
>
> #### 栈溢出规则
>
> 当某 bank 的可用寄存器槽位用完时，该 bank 的后续参数使用栈传递。栈参数按
> **声明顺序从左到右**依次排列，8 字节对齐。三 bank 共享同一个栈增长方向，
> 各组溢出参数连续紧凑存放。
>
> #### 聚合类型返回值：Aggregate return
>
> 长度大于 64 位的聚合类型，采用 **hidden sret 模式**：caller 在栈上预分配
> 返回值空间，地址作为隐藏的第一个参数通过 **RB16** 传入 callee；callee
> 将返回值写入该地址，返回时 RB16 仍保存该地址供 caller 读取。
> `struct Big make_big(int a)` 展开为 `void make_big(struct Big* sret_ptr,
> int a)`（`sret_ptr`→RB16，`a`→RD16）。
> 长度 ≤ 64 位的聚合类型，使用标量返回值规则（通过 RD31 返回）。
>
> #### 可变参数"大于8字节的聚合变参"（§可变参数一节）
>
> 聚合体 > 8 字节（如 16 字节 struct）按自然对齐（最大 8 字节）拆分为多个
> 8 字节单元，按字节序依次占用连续 slot。例如 16 字节 struct 占两个连续
> slot，32 字节 struct 占四个连续 slot。callee 通过 `va_arg` 宏按原始类型
> 大小逐 slot 读取并重组。

## 背景

`ML-026a`（`docs/reviews/ML-026a-gcc-c-torture-sweep-2026-07-24.md`）gcc-c-torture
扫描 + `ML-029a` 修复帧偏移 bug 后重新扫描，发现一个 15 个文件的失败簇——全部
用 `va_arg(ap, struct XXX)` 传递结构体作为变参（`stdarg-3.c`/`strct-stdarg-1.c`/
`strct-varg-1.c`/`va-arg-22.c`/`pr38151.c`/`920625-1.c`/`920908-1.c`/
`931004-{2,4,6,8,10,12,14}.c`/`pr44575.c`）。这些文件**编译不报错**，是运行时
产出错误结果触发 `abort()`——说明当前编译器对"聚合类型参数传递"这个 `contracts/
abi/spec.md` §2.4 明确标注"Excluded from M1"的能力，既没有实现也没有在编译期
拒绝，静默产出错误代码。

架构师已确认这批文件的聚合类型均**不是 HFA**（都混有 int/char/pointer，不是
纯浮点叶子字段），大概率都落在"≤32字节 RD bank 拆分"这条路径，但**本任务应该
按 wiki 完整实现 HPA + RD-split + 指针间接 + 聚合返回值这几条规则**（用户
2026-07-24 明确要求"现在就实现聚合类 ABI 传参"，是要一个通用、完整的能力，
不是只刚好够这 15 个文件用的最小拼凑）。

## 目标

1. **非变参聚合类型实参传递**（`DADAOISelLowering.cpp` 的 `LowerCall`/
   `LowerFormalArguments`，可能还需要 `CC_DADAO`/`RetCC_DADAO`
   自定义分类逻辑，或 Clang 侧的 `ABIArgInfo` 分类——参照 `DL-072a` 给 DADAO
   新增的 `clang/lib/CodeGen/Targets/DADAO.cpp` 自定义 `TargetCodeGenInfo`，
   本任务大概率需要在同一个文件里补充聚合类型的 `classifyArgumentType`/
   `classifyReturnType` 逻辑）：
   - 实现 HFA/HPA 递归判定算法（flatten + 同质检查 + 计数检查）。
   - HPA：走 RB bank，每叶子字段1个RB槽位。
   - HFA：**探测到即报告为 issue，不实现**（硬约束已明确）。
   - 不满足 HFA/HPA：≤32字节按1-4个8字节块拆分进RD bank（注意"高位块先入
     高寄存器"这个字节序细节，需要你自己验证清楚具体是什么意思——DADAO是
     大端序，可能意味着聚合体内存布局里地址较低的字节块对应较高编号的
     寄存器，或者相反，用真实探针核实，不要凭直觉猜）；>32字节走caller栈
     分配+RB指针间接引用。
   - 栈溢出：任一 bank 槽位用完后走栈，按声明顺序8字节对齐紧凑排列。
2. **聚合类型返回值**：≤64位走标量规则（RD31）；>64位走hidden sret（RB16
   传入caller预分配的返回空间地址，callee写入后RB16仍保留该地址）。
3. **变参聚合类型**：扩展 `DL-072a` 已经实现的"caller 统一保存区"机制
   （`DADAOISelLowering.cpp::LowerCall` 里 `IsVarArg` 分支新增的保存区填充
   逻辑）——>8字节的聚合变参按自然对齐拆成多个连续8字节slot，不是单个slot。
   这应该是对现有保存区填充循环的自然扩展（原来假设每个实参恰好1个slot，
   现在需要按实参的实际大小占用1个或多个slot），不需要推倒重来。
4. **验证禁止只测 15 个 torture 用例本身**：需要构造独立的判别性测试（覆盖
   HPA、RD-split的≤32B不同大小、>32B间接引用、聚合返回值≤64位和>64位、
   变参聚合体跨slot边界），用 `volatile` + 负控制确保测试有判别力（参照
   `feedback_volatile_needed_for_memory_verification_tests`）。

## 验收

- 15 个原始 torture 文件：`tests/scripts/gcc_torture_sweep.py --filter
  "stdarg-3|strct-stdarg-1|strct-varg-1|va-arg-22|pr38151|920625-1|920908-1|931004-|pr44575"`
  重跑，报告实际转 PASS 的数量（**不强行要求全部15个变PASS**——如果诊断中
  发现某个文件还牵涉本任务未覆盖的其它问题，如实报告，不要夸大）。
- 新增判别性测试覆盖 HPA/RD-split各种大小/>32B间接引用/聚合返回值两种模式/
  变参聚合跨slot——双后端验证。
- 全量 `llvm-lit tests/lit/E2E/`：零回归（落地前重新跑一次记录当前值为准）。
- **全量 gcc-c-torture 重扫**：报告新分布，和当前基线（`1412/113/133/50/0`，
  `ML-030a` 若已落地则以其后的基线为准）对比，确认零回归。
- `python3 tools/run_differential.py`：AGREE 数与当前基线一致、DIVERGE=0。
- `python3 scripts/manifest_check.py`/`check_issues.py` 通过。
- LLVM 侧改动用**普通** `git commit` 落地，`git format-patch` 导出对应 patch，
  追加进 `series`；独立验证可在干净 pin-commit checkout 上 `git am` 成功。
- `contracts/abi/spec.md` 更新：§2.4 从"Excluded from M1"改为标注实际实现
  范围（HPA/RD-split/indirect/sret/变参聚合已实现；HFA 明确排除，注明原因）。
- 如果发现 HFA 场景在这批文件之外的地方也会被触发（比如某个既有 E2E 测试
  意外用到）：如实报告，不要因为"目前没测试触发"就假装 HFA 完全不需要关心。

## 参考指针

- `~/DADAO-wiki/DADAO-21-ABI-应用程序二进制接口.md` 第178-307/362-377行
  （本任务的权威依据）
- `contracts/abi/spec.md` §2.4（当前"Excluded from M1"措辞，本任务要更新的
  位置）、§2.1-2.3（现有标量RD/RB传参规则，聚合传参是在此基础上的扩展）
- `code-agent/tasks/DL-072a-varargs-caller-populated-save-area.md` 完成区
  （变参保存区机制的现有实现，本任务要扩展支持多slot聚合体；wiki歧义处置
  的方法论参照）
- `clang/lib/CodeGen/Targets/DADAO.cpp`（`DL-072a` 新增的自定义
  `TargetCodeGenInfo`/`EmitVAArg`，本任务大概率要在这里补充聚合类型分类
  逻辑）
- `llvm/lib/Target/DADAO/DADAOISelLowering.cpp`（`LowerCall`/
  `LowerFormalArguments`/`CC_DADAO`/`RetCC_DADAO`）
- `docs/reviews/ML-026a-gcc-c-torture-sweep-2026-07-24.md`（15个文件清单
  出处）
- `feedback_volatile_needed_for_memory_verification_tests`（新测试涉及
  写读回校验要用volatile）
- `docs/wiki-questions.md`（若发现wiki歧义，参照DL-072a §5条目的格式追加）

## 完成区

**状态**：已完成；第一轮四项 blocker 已整改，最终独立复审 Accepted

**修改文件**：

- `.work/source/llvm`（普通 git commit，5 个）：
  - `clang/lib/CodeGen/Targets/DADAO.cpp`：新增 `DADAOABIInfo::classifyArgumentType`/
    `classifyReturnType`（HPA/HFA/RD-split/indirect/sret 全套分类逻辑 + `flattenHomogeneous`
    递归展开helper）+ 修复 `EmitVAArg` 的 `IsIndirect`（此前硬编码 `false`）/
    `ForceRightAdjust`（此前硬编码 `true`，聚合体现在按 `!isAggregateTypeForABI(Ty)` 判定）。
  - `clang/test/CodeGen/DADAO/aggregate-abi.c`（新增，IR级FileCheck定向测试）。
  - `llvm/lib/Target/DADAO/DADAOISelLowering.cpp`：`MaxStoresPerMemset/Memcpy/Memmove`
    从 `UINT_MAX` 改为 `16`（回归测试中发现的必要修复，见下方"回归诊断"）。
  - 架构师接手复核后修正 HFA/HPA flatten 的两个 spec 偏差：`float` 与
    `double` 现在按不同 leaf type 判定，混合类型不会误报为 HFA；数组字段不再
    被擅自展开为 HFA/HPA leaf（wiki 仅授权递归展开 nested struct）。新增
    mixed-float、pointer-array 与真实 HFA warning/fallback 的 IR/诊断回归。
  - 第一轮独立 review 后新增 `36abcbd6369d`：HPA 改用带真实 AST field offset
    的 `CoerceAndExpand`，不再把 padding 当 pointer leaf；非 HFA 聚合变参使用
    独立分类，`>32B` 仍按 `ceil(size/8)` 个连续 inline data slot 传递。
  - 第一轮独立 review 后新增 `86656a445241`：在
    `DADAOMachineFunctionInfo` 保存 hidden sret 地址并在每个 return 前显式恢复
    RB16；`DADAOTargetLowering::LowerCall` 对目标全局保守关闭尚未实现的 tail-call
    lowering，有限 `MaxStoresPerMem*` 阈值产生的 libcall 统一走普通 call。
  - 已导出 `components/llvm/patches/0055-DADAO-implement-aggregate-struct-parameter-return-va.patch`
    + `0056-DADAO-bound-MaxStoresPerMem-instead-of-unconditional.patch`
    + `0057-DADAO-enforce-exact-aggregate-homogeneity-rules.patch`
    + `0058-DADAO-preserve-aggregate-ABI-layout-and-vararg-slots.patch`
    + `0059-DADAO-preserve-sret-and-disable-unsupported-tail-cal.patch`，追加进
    `components/llvm/patches/series`。
- `tests/lit/E2E/Inputs/agg_args_named.c` + `tests/lit/E2E/agg_args_named.test`（新增，
  HPA（含 nested/over-aligned、内部 padding）/RD-split各尺寸/32B边界/>32B
  间接引用别名检测/两种返回值模式（sret callee 含内部 pointer call）；输入来自
  volatile storage，NEGATIVE_CONTROL 在全部主路径执行后于最终 sret 检查触发）。
- `tests/lit/E2E/Inputs/agg_vararg_multislot.c` + `tests/lit/E2E/agg_vararg_multislot.test`
  （新增，变参聚合体跨多个8字节slot，覆盖12B/16B及40B `>32B`+尾随标量；
  输入来自 volatile storage，并有独立的双后端 NEGATIVE_CONTROL；O2 不再使用
  `-fno-optimize-sibling-calls` 测试侧绕行）。
- `contracts/abi/spec.md`：§2.4（聚合参数）、§3.3（sret）、§6（Open Issues 表 Varargs/HFA/
  Complex aggregate ABI 三行）从"Excluded from M1"改为标注实际实现范围。
- `docs/wiki-questions.md`：新增 #6（RD-split 高位块/高寄存器顺序歧义）、#7（聚合体变参
  slot 内左右对齐方向未定义）。
- `docs/issues.yaml`：新增 2 个 open issue：`dadao-hfa-argument-not-implemented`、
  `dadao-complex-vararg-padded-struct-field-corruption`；整改 B4 后将既有
  `codegen-tailcall-lowercall-assert` 完整历史迁移至 `docs/issues-archive.yaml`
  并标记由 `86656a445241`/0059 关闭。

**验收结果**：

1. **15 个原始 torture 文件重跑**（`--filter
   "stdarg-3|strct-stdarg-1|strct-varg-1|va-arg-22|pr38151|920625-1|920908-1|931004-|pr44575"`，
   实际匹配 22 个文件——`931004-` 前缀匹配 7 个变体，`pr38151` 等各匹配 1 个）：
   **21/22 PASS**。**14/15** 个原始目标文件转 PASS；`pr38151.c` 仍 `FAIL_RUN`——
   已诊断为与聚合ABI无关的独立既有缺陷（`_Complex int` 字段 + 变参memcpy重建交互，
   见下方"回归诊断"和 `docs/issues.yaml` 新增条目），不在本任务范围内修复。
   **额外发现并顺带修复 1 个不在原15个清单内的文件**：`20040703-1.c`
   （`FAIL_RUN`→`PASS`，本任务的通用HPA/RD-split实现覆盖到的额外用例）。

2. **判别性测试**：`tests/lit/E2E/agg_args_named.test`（HPA 3指针字段、
   nested/over-aligned padded HPA、RD-split
   5种尺寸含5B、8B、16B、20B、32B边界/>32B间接引用+独立副本别名检测/聚合返回值
   ≤64位与>64位两种模式含双次sret调用不互相覆盖，NEGATIVE_CONTROL 变体验证
   全路径后的 sret 负控制）+ `tests/lit/E2E/agg_vararg_multislot.test`
   （12B/16B/40B 三种变参聚合体跨 slot，各带尾随标量验证 slot 计数正确）+
   `clang/test/CodeGen/DADAO/aggregate-abi.c`（IR级签名断言）。双后端（QEMU+gem5）、
   O0/O2 全部 PASS。架构师接手后补齐 volatile 来源，并把具名测试的负控制移到
   所有主路径之后；变参测试也新增自己的负控制。最终两个正例与两个负控制均在
   QEMU+gem5 通过。

3. **全量 `llvm-lit tests/lit/E2E/`**：**76/76 PASS**（改动前 74/74，含本任务
   新增2个）。

4. **全量 gcc-c-torture 重扫**（`python3 tests/scripts/gcc_torture_sweep.py`）：
   - 改动前基线（stash 掉 `.work/source/llvm` 改动、重建 clang 后实测）：
     `PASS=1414 FAIL_COMPILE=113 FAIL_LINK=131 FAIL_RUN=50`（与
     `ML-030a` 完成区声称基线一致）。
   - 改动后：`PASS=1429 FAIL_COMPILE=113 FAIL_LINK=131 FAIL_RUN=35`。
   - 逐文件精确 diff（1708 个文件全部比对 status）：**恰好 15 个文件状态变化，
     全部是 `FAIL_RUN → PASS`，零回归**（无任何原 PASS/其它状态的文件退化）：
     `20040703-1.c, 920625-1.c, 920908-1.c, 931004-{2,4,6,8,10,12,14}.c,
     pr44575.c, stdarg-3.c, strct-stdarg-1.c, strct-varg-1.c, va-arg-22.c`。

5. **回归诊断（`pr28982b.c`，中途发现的真实回归，已修复）**：初次全量重扫发现
   `pr28982b.c` 从 `PASS` 退化为 `FAIL_COMPILE`（编译器崩溃）。根因定位：该文件
   `struct big { int i[0x10000]; }`（256KB）按值传参，命中本任务新增的 `>32B
   indirect(ByVal=false)` 路径——与此前"所有聚合体一律 `ByVal=true`"不同，
   `ByVal=false` 会让 Clang 在 IR 层真正 emit 一次 `llvm.memcpy`（此前 `ByVal=true`
   从不在 IR 层生成 memcpy，且 DADAO 后端完全没有 byval CC lowering 代码，等效于
   静默传递一个未拷贝的别名指针——这也解释了为什么当年这个测试"能过"）。该
   `llvm.memcpy` 命中 `DADAOISelLowering.cpp` 里 `MaxStoresPerMemcpy = UINT_MAX`
   （源自 `ML-003a-d`，注释写"since brcond-based expansion was previously
   unselectable"——即当年 call 选择本身有 bug 的临时规避，不是刻意"永不 emit
   mem* libcall"的freestanding设计决策），导致 SelectionDAG 尝试为 256KB
   拷贝展开 32768+ 个 store 节点直接崩溃。用一个独立、脱离聚合体ABI的最小复现
   （`__builtin_memcpy(dst, src, 262144)`，无struct参与）确认这是预先存在、与本
   任务无关的通用缺陷，只是此前从未被真正触发过（memcpy只在 IR 层真正生成时
   才会经过这条 lowering 路径）。修复：`MaxStoresPerMemset/Memcpy/Memmove` 改为
   `16`（对齐 `LanaiISelLowering.cpp` 现有精度，call 选择基础设施在
   ML-003a-d 之后已大幅成熟，验证超阈值拷贝改走真实 `memcpy` 调用后
   `pr28982b.c` 编译链接运行全部通过，且不影响任何 nostdlib E2E 测试
   ——它们都不构造接近这个量级的聚合体/memcpy）。修复后重跑确认：`pr28982b.c`
   回到 `PASS`，全量重扫仍是"恰好15个文件变化、零回归"（见上）。

6. **`pr38151.c` 独立诊断（未在本任务范围内修复，如实记录不夸大）**：
   通过4个最小化探针隔离：①具名参数传同一 layout（`_Complex int` +
   `__attribute__((aligned))` 空成员导致16字节尺寸/16字节对齐）——PASS；
   ②同尺寸16字节变参但把 `_Complex int` 换成等价的 `struct{int re,im;}`——PASS；
   ③更小（12字节，无trailing padding）的 `_Complex int` 变参——PASS；④原始
   `S2848` layout 变参——FAIL（仅虚部 `__imag__` 读回错误，`.a`/`__real__` 均正确）。
   四个探针共同锁定：缺陷特定于"变参聚合体 memcpy 重建路径" + "`_Complex`
   实部/虚部lvalue访问应用在该重建临时对象上"这一组合，且要求trailing padding
   同时存在；与本任务的字节块ABI分类/传输机制本身无关（探针①②③都真实
   走了本任务的新RD-split/变参slot代码路径且正确）。`pr38151.c` 在 `ML-026a`
   原始扫描里已经是 `FAIL_RUN`（"尚未深挖"9个文件之一）——本任务未引入此
   缺陷，只是诊断清楚了它，未修复（与聚合类型ABI传参正交）。已登记
   `docs/issues.yaml` `dadao-complex-vararg-padded-struct-field-corruption`。

7. **HFA 场景既有出现排查**：`grep` `tests/lit/E2E/Inputs/*.c` 与 musl
   `src/*/*.c` 未发现任何既有 struct-with-float-field 按值传递的用例（唯二
   命中 `double`/`float` 关键词的文件是注释提到软浮点符号，非实际HFA用法）；
   全量 E2E 76/76 零回归也间接印证没有既有测试路径因 HFA fallback 行为
   （本任务保持与此前完全一致，未改动）而改变结果。gcc-c-torture 里唯一
   真实 HFA 用例是 `920625-1.c` 的 `point`（`struct{double x,y;}`）变参子测试
   `va1`——该子测试意外PASS，但已在 `docs/issues.yaml` 的
   `dadao-hfa-argument-not-implemented` 条目里如实注明：这是 DADAO 后端从未
   实现 byval CC lowering 导致的"传裸别名指针、恰好因为源数据是长寿命全局数组
   而蒙对"的偶然结果，不是真正符合 spec 的 HFA 实现，不能理解为"HFA 已经可用"。

8. **`python3 tools/run_differential.py`**：`AGREE(3-way)=200 DIVERGE=0`，
   `AGREE(4-way)=200 SAIL-DIVERGE=0` —— 与改动前完全一致（本任务不改指令语义）。

9. **`python3 scripts/manifest_check.py`**：PASS。**`python3 scripts/check_issues.py`**：
   PASS（Open=23 Closed=38 Total=61）。**`python3 scripts/check_wiki_refs.py
   --profile abi`**：PASS（0 DANGLING/0 UNPARSEABLE/0 缺引用）。
   **`python3 scripts/check_wiki_drift.py`**：PASS。**`python3
   scripts/check_lit_bytes.py`**：69 patterns OK。

10. **patch 导出与独立验证**：0055-0059 均已追加进 `series`；在干净
    pin-commit（`ca7933e47d3a...`）checkout 上依次 plain `git am` 全部
    **59/59**，成功、无冲突，最终 tree 与开发树（`86656a445241`）同为
    `5eb4aa6953eb634052fecad3fd0e187aa103e204`。

11. **`.work/source/llvm` 侧改动均为普通 `git commit`**（未做
    `git rebase`/`git am` 重放历史/`git reset --hard`）：
    - `9079603c93f3`："DADAO: implement aggregate (struct) parameter/return-value ABI"
    - `ac7c52aa6cd4`："DADAO: bound MaxStoresPerMem* instead of unconditional UINT_MAX"
    - `53e5e16e829a`："DADAO: enforce exact aggregate homogeneity rules"
    - `36abcbd6369d`："DADAO: preserve aggregate ABI layout and vararg slots"
    - `86656a445241`："DADAO: preserve sret and disable unsupported tail calls"

12. **架构师接手及四项整改后的最终重跑**：原目标 filter 仍为
    `21 PASS / 1 FAIL_RUN`（`pr38151.c`）；加 `pr28982b` 后为
    `22 PASS / 1 FAIL_RUN`。全量 1708 项仍为
    `PASS=1429 / FAIL_COMPILE=113 / FAIL_LINK=131 / FAIL_RUN=35`，与接手时
    `gcc-torture-results.json` 逐文件 status mismatch 为 0；E2E 76/76；
    三方/四方 differential 均 200 AGREE、0 DIVERGE；manifest、issue、ABI、
    wiki refs/drift 与 lit-bytes 门禁全部 PASS。

13. **第一轮独立 review 四项 blocking finding 整改**：
    - **B1 padded/nested HPA**：`36abcbd6369d` 扩展 recursive flatten，同步记录
      每个 pointer leaf 的真实 AST byte offset；按 offset 构造含显式 byte-padding
      的 packed `CoerceToType` 与无 padding 的 pointer 参数序列。IR 现在把
      `PaddedHPA` 展开为两个独立 pointer 参数，callee 重组时第二个字段明确定位
      offset 16；新增 over-aligned nested HPA 双后端运行检查，原 review 的
      exit 17 已消失。
    - **B2 `>32B` vararg**：`computeInfo` 按 `FI.getNumRequiredArgs()` 区分 named/
      unnamed；非 HFA 聚合变参始终 direct-coerce 为
      `[ceil(sizeof(T)/8) x i64]`，不复用 named `>32B` indirect。40B `Big40`
      实际产生 5 个连续 slot，后接 `999` 标量，O0/O2 QEMU+gem5 均 PASS；HFA
      仍走明确 warning + indirect fallback，未虚假声称 RF ABI 已实现。
    - **B3 sret RB16**：`86656a445241` 在 `LowerFormalArguments` 将 hidden sret
      pointer 保存到 GPRB virtual register，内部 call 的 regmask 使其正常
      spill/reload；`LowerReturn` 显式 copy 回 RB16 并加入 RET live-out。
      `aggregate-sret-preserve.ll` 锁定 `call sink` 后 `ldo rb16,...` 再 `ret`。
    - **B4 mem* tail call**：同一提交在 `LowerCall` 入口统一
      `CLI.IsTailCall=false`，只关闭 DADAO 尚未实现的优化，不伪造 tail-call
      支持。`mem-intrinsic-libcall-no-tail.ll` 覆盖 memcpy/memmove/memset 的
      16/17B 边界、tail/non-tail 及 256KiB 路径；17B/大路径生成普通 call，
      不再 assertion，`pr28982b.c` 保持 PASS。

14. **整改后最终证据**（最终构建产物 revision =
    `86656a44524167b605274b616906f8d432563f6e`）：
    - Clang aggregate ABI + DADAO CodeGen：**9/9 PASS**；
    - 全量 E2E：**76/76 PASS**，其中 padded HPA、40B vararg+tail、
      internal-call sret 均在 QEMU+gem5 覆盖；
    - 目标 torture（原 filter + `pr28982b`）：**22 PASS / 1 FAIL_RUN**，
      唯一失败仍为已登记的既有 `pr38151.c`；
    - 全量 torture：`1429/113/131/35`，与整改前 JSON 1708 项逐文件
      status mismatch = **0**；
    - differential：3-way/4-way 均 `AGREE=200`、`DIVERGE=0`；
      manifest/issues/wiki refs/wiki drift/CodeGen ABI/lit-bytes 全部 PASS；
      issue registry 更新后 `Open=22 / Closed=39 / Total=61`。

15. **patch provenance**：0058/0059 的 SHA256 分别与对应 commit 的 fresh
    `git format-patch --stdout` 精确一致：
    `84c3ad2f94aee140bfca4b8c2884bd276d265bbed4b9acbc2b8ec406aa9f96d5`、
    `789653ef0ffc8304f0419460dc65dc588fd063aeb4a39cc66ce0ecf60f2bb875`。
    从 manifest pin `ca7933e47d3a...` 在独立临时 clone 中按 series 顺序
    plain `git am` **59/59** 成功；replay tree 与 LLVM HEAD tree 均为
    `5eb4aa6953eb634052fecad3fd0e187aa103e204`。

**遗留问题**：

- `dadao-hfa-argument-not-implemented`（open）：HFA（同质浮点聚合，RF bank）
  未实现，需要先给 DADAO 加完整浮点寄存器类/CodeGen基础设施，是独立的大工程。
- `dadao-complex-vararg-padded-struct-field-corruption`（open）：`_Complex int`
  字段 + 变参聚合体memcpy重建路径 + 非天然尺寸trailing padding 三者组合时
  虚部读回错误（`pr38151.c`），与本任务的聚合ABI机制正交，未修复。
- `docs/wiki-questions.md` #6/#7：两处wiki文字未覆盖到的边界情况（RD-split
  高低寄存器顺序、聚合变参slot内左右对齐方向），已采用最合理的读法并记录理由，
  等待 wiki 团队确认。

## 审阅记录（subagent）

### 第一轮独立 review（2026-07-24）

- 报告：`docs/reviews/ML-031a-independent-review-20260724.md`
- 判决：**Needs changes**
- blocking findings：
  1. `[N x ptr]` coercion 会让带内部 padding 的递归 HPA 丢失非连续字段；
  2. `>32B` 聚合变参错误复用 named indirect 分类，只保存一个 pointer slot；
  3. sret callee 内部发生 pointer call 后，返回前没有把原 sret 地址恢复到 RB16；
  4. 0056 让 17B 以上尾位置 mem* 进入尚未实现完整的 tail-call lowering，
     在 `-O2` 触发 assertion。
- 第一轮 review 同时确认：0057 的 exact-homogeneity 修复正确；E2E 76/76、
  torture 1429/113/131/35、differential 200/0 和 57/57 replay 数字可信，但
  这些既有测试没有覆盖上述四个边界，不能抵消 findings。
- 当前处置：四项均作为 ML-031a 完成前的阻断项整改，不降级为后续 issue，也不以
  现有绿色数字提前关闭任务。整改后的最终独立复审由主 agent 另行显式管理；
  本 agent 不再自行派生 reviewer。

### 最终独立复审（2026-07-24）

- 报告：`docs/reviews/ML-031a-independent-rereview-20260724.md`
- 判决：**Accepted**
- 第一轮 B1-B4 均由最终 reviewer 独立确认关闭：
  - padded/nested HPA 的 AST offset、RB16/RB17 物理映射与 bank overflow；
  - 40B 非 HFA 聚合变参的 5 个 inline slot、尾随标量位置与双后端执行；
  - internal pointer call 后 sret 地址恢复到 RB16/live-out；
  - mem* 16/17B、tail/non-tail、256KiB 路径与 `pr28982b.c`。
- 独立结果：Clang/CodeGen 9/9、E2E 76/76、torture
  `1429/113/131/35` 且逐文件零变化、三方/四方 differential 200/0、
  plain `git am` 59/59、replay tree 与 LLVM HEAD 一致。
- 无 blocking/major finding。唯一 Minor N1 是永久
  `mem-intrinsic-libcall-no-tail.ll` 采用代表性矩阵；reviewer 已用临时 18-case
  完整矩阵确认全部编译成功，建议以后按需固化，不阻断本任务。

**最终独立 reviewer 判决：Accepted。**
