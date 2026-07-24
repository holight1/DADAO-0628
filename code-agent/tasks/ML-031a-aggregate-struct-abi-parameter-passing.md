# ML-031a：实现聚合类型（struct）参数传递 ABI——严格按 wiki，解锁 15 个 gcc-c-torture 变参传 struct 用例

**执行环境**: 本地 subagent

**状态**: 待处理

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
