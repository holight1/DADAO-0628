# ML-036a：修复 `-O0` 下负极性单比特 AND 测试掩码指令被静默丢弃的 miscompile

**执行环境**: 本地 subagent

## 硬约束（务必遵守，违反视为任务失败）

- **禁止**对 `.work/llvm` 做 `git rebase`/`git am` 重放整条历史/`git reset
  --hard`。只允许在当前 HEAD 基础上新增普通 `git commit`。
- **这是本项目当前最高优先级的正确性缺陷**（`docs/issues.yaml`
  `dadao-o0-negative-polarity-bitand-mask-dropped`，架构师已独立复现确认），
  不是普通的 gcc-c-torture 文件计数任务——本任务的验收标准比"让哪几个 torture
  文件变绿"更高：必须**先说清楚根因**（具体是哪个 DAGCombine/isel 阶段/pattern
  丢掉了 `and` 指令），再修复，且修复后必须证明没有引入相反方向的新错误（比如
  修复负极性场景时不小心把已经正确的正极性场景弄错）。
- **完成后立即导出 patch**（不要延后），追加进对应 `series`。
- 完成后必须在任务文件里写「完成区」+ subagent 自审「审阅记录」（含逐条 finding
  + 判决）。

## 背景

`ML-035a`（`docs/reviews/ML-035a-gcc-torture-gap-rescan-2026-07-24.md` §3.4）
发现并被架构师独立复现确认：**仅在 `-O0`**，把单比特 AND 测试写成**负极性**
（真值分支是 `if.else`，即 `if ((x & 1) == 0)` 或 `if (!(x & 1))`）时，
生成的汇编里**完全没有** `and rd,rd,1` 这条掩码指令，直接对**未掩码的原始字节**
做条件分支。

架构师独立复现的最小案例（`/tmp` 临时文件，未提交仓库，重新构造即可复现）：

```c
__attribute__((noinline)) int testMask1(int l) {
  if ((l & 1) == 0) { return 1; } else { return 0; }
}
int main() { return testMask1(2); }
```

`clang --target=dadao -O0 -S` 生成的 `testMask1` 汇编：把参数存到栈槽，计算
`栈槽基址+3`（大端序 4 字节值的最低有效字节偏移），`ldbu` 加载这一个字节，
直接 `brnz`/`brz` 判断这个字节是否非零——等价于判断"整个字节是否非零"而不是
"第 0 位是否为 1"。对 `l=2`（`00000010b`，第 0 位为 0 但字节非零）这种输入，
产生与预期相反的分支结果。

架构师端到端复现确认：上述最小案例 `-O0` 编译链接跑 QEMU 得到 exit=0（错误，
`testMask1(2)` 应返回 1，`main` 应 exit 1）；同一份源码 `-O2` 编译得到正确的
exit=1。语义等价的**正极性**写法（`if (l & 1)` / `if ((l&1) != 0)`）在 `-O0`
下编译正确（真的生成 `and rd,rd,1` 再 `brz`/`brnz`）。

`ML-035a` 额外发现 `960608-1.c`（位域读取，`flags->c != 0` 子条件）疑似同一
根因家族的另一触发形状，但未能孤立出独立于位域/指针解引用/相邻短路子表达式
的最小触发条件。

这对应 gcc-c-torture 里的 `931102-1.c`/`931102-2.c`（确诊）+ `960608-1.c`
（强嫌疑，见下方目标 3），但**本任务的价值不在于让这 2-3 个文件变绿**——这是
一个"不崩溃、只产生错误运行时结果"的静默 miscompile，`if (!(x&1))`（奇偶/
标志位清除判断）、`while ((x&mask)==0)`（找最低置位比特循环）、单比特位域
读取都是极常见的真实 C 写法，风险面远大于当前语料库命中的文件数。

## 目标

1. **根因诊断**（优先于修复）：用 `-print-after-all`/`-debug-only=isel`/
   MIR dump 找到具体是哪个阶段（`SelectionDAGBuilder` 初始翻译、某个
   `DAGCombiner` 通用 combine、还是 DADAO 后端自己的 isel pattern）把
   "`AND(x, 1)` 然后与 0 比较、真值分支取 `else`"这个模式变成了"直接加载/测试
   原始字节是否非零"。需要能清楚解释：
   - 为什么**只在 `-O0`** 复现（`-O0` 通常意味着更少的 DAGCombine，理论上应该
     更"字面"、更不容易丢指令，需要搞清楚这个反直觉之处的真实机制）。
   - 为什么**只在负极性**（真值分支是 else）复现，正极性（真值分支是 then）
     没事——这个不对称性本身就是重要线索。
   - 是否与"大端序窄值在 slot 内右对齐"这个 DADAO 特有的内存表示规则
     （`contracts/isa/spec.md`/wiki 里关于大端序的说明）有交互——从架构师的
     复现汇编看，丢失掩码后走的是"加载大端 4 字节槽位的最低有效字节"这个
     地址计算路径，这可能是理解根因的关键切入点。
2. **修复**：在诊断清楚具体机制后，修正对应的 lowering/combine/pattern，
   确保负极性场景下 `and rd,rd,1` 掩码指令不会被错误地替换成"直接测试原始
   字节"这种不等价的路径。
3. **`960608-1.c` 二分**：用 MIR 级别调试进一步孤立出这个文件失败的最小触发
   条件，确认是否确实是同一根因家族；如果修复后 `960608-1.c` 恰好也变绿，
   记录下来作为佐证（但不能仅凭"变绿了"就断言是同一 bug，需要在 MIR/汇编层面
   证实修复前后这个文件的相关代码路径确实经过了同一条被修复的逻辑）。
4. **回归验证**：修复对 DADAO 后端 isel/combine 是较有杠杆的改动（可能影响
   不止单比特 AND 这一种模式），必须验证：
   - 正极性场景（`if (l & 1)`）在修复后仍然正确（不能因为改了负极性路径而
     弄坏正极性路径）。
   - 更宽的位掩码（`& 2`、`& 4`、`& 0xff` 等，不只是 `& 1`）、不同的比较目标
     （`== 0` vs `!= 0` vs `== 1` vs 布尔取反 `!`）在正负极性下都要覆盖，
     确认不是"只修好了 bit 0 这一个特例"。
   - 更宽的整数类型（`long`/`char`/`short`，不只是 `int`）覆盖。

## 验收

- 独立、判别性的 CodeGen lit 测试（`llvm/test/CodeGen/DADAO/`）覆盖上面
  目标 4 列出的各种组合（正负极性 × 多种掩码值 × 多种比较 × 多种宽度），
  用 FileCheck 直接断言生成的汇编/MIR 里确实存在正确的掩码指令，不只是跑
  `-O0`+`-O2` 的行为一致性。
- 独立、判别性的项目 E2E 测试（`tests/lit/E2E/`），用 `volatile` 输入 +
  正负控制（参照 `feedback_volatile_needed_for_memory_verification_tests`），
  在 QEMU+gem5 双后端跑通，覆盖至少一个"低位为 0 但整字节非零"的判别性输入
  （类似 `l=2` 这种）。
- 原始 3 个 torture 文件（`931102-1.c`/`931102-2.c`/`960608-1.c`）用
  `python3 tests/scripts/gcc_torture_sweep.py --filter
  "931102-1|931102-2|960608-1"` 重跑，如实报告有几个变绿（不强行要求全部
  3 个，`960608-1.c` 如果诊断后确认是不同根因，如实说明）。
- 全量 `gcc-c-torture` 重扫（`python3 tests/scripts/gcc_torture_sweep.py`，
  当前基线 `1461/104/125/18`），逐文件 diff 确认零回归（这是对通用
  isel/combine 逻辑的改动，必须完整验证不会让任何其它文件从 PASS 退化）。
- 全量 `llvm-lit tests/lit/E2E/`（当前基线 77/77）：零回归。
- `python3 tools/run_differential.py`：AGREE 数与当前基线一致、DIVERGE=0。
- `python3 scripts/manifest_check.py`/`check_issues.py` 通过；本 issue
  （`dadao-o0-negative-polarity-bitand-mask-dropped`）状态更新为 closed
  并迁移到 `docs/issues-archive.yaml`（如果 `960608-1.c` 未能完全确认是
  同一根因，可以在关闭说明里如实注明这一点，不必因此阻塞整个 issue 的关闭）。
- LLVM 侧改动用**普通** `git commit` 落地，`git format-patch` 导出对应
  patch，追加进 `series`；独立验证可在干净 pin-commit checkout 上 `git am`
  成功，且 replay tree 与开发树 tree hash 一致。

## 参考指针

- `docs/reviews/ML-035a-gcc-torture-gap-rescan-2026-07-24.md` §3.4（本任务
  对应的发现原文，含架构师复现细节）
- `docs/issues.yaml` `dadao-o0-negative-polarity-bitand-mask-dropped`
  （完整诊断线索记录）
- `.work/source/llvm-test-suite/SingleSource/Regression/C/gcc-c-torture/execute/
  {931102-1,931102-2,960608-1}.c`（原始复现源码）
- `.work/llvm/llvm/lib/Target/DADAO/DADAOISelLowering.cpp`（`SETCC`/`BR_CC`/
  `AND` 相关 lowering，最可能需要改的地方）
- `.work/llvm/llvm/lib/Target/DADAO/DADAOISelDAGToDAG.cpp`（isel pattern
  选择，`ML-021a`/`ML-030a` 都在这类文件里找到过根因，参照其诊断方法论——
  MIR/DAG dump 逐节点核对，不要凭直觉猜）
- `contracts/isa/spec.md`（大端序数据表示规则，如果诊断确认与"窄值 slot 内
  右对齐"这条规则交互，这里是权威依据）
- `feedback_volatile_needed_for_memory_verification_tests`（新测试涉及
  写读回校验要用 volatile + 负控制）
- `feedback_dadao_add_semantics_and_grep_trap`（DADAO 后端历史上出现过的
  类似"寄存器/bank 语义想当然"的踩坑记录，诊断时可参考避免同类误判）

## 完成区（2026-07-24）

### 根因

`DADAOTargetLowering` 构造函数从未调用 `setBooleanContents()`，落到
`TargetLowering` 默认值 `UndefinedBooleanContent`。这个默认值对本后端是
错的：`lowerSETCC` 每个 `case` 分支（`cmps`/`cmpu` + `shru`-63/`sub`/`orr`
链）都在整个 64 位寄存器宽度上物化一个真正的 0-or-1 值，且实际的分支指令
（`BRNZ`/`BRZ`，`BRCOND`/`BR_CC` 选中的目标）测试的是**整个寄存器**是否
非零——它们自己不做 bit-0 掩码。本后端真正的不变量是
`ZeroOrOneBooleanContent`。

在错误的默认值下，`TargetLowering::promoteTargetBoolean`（被
`DAGTypeLegalizer::PromoteIntOp_BRCOND` 调用）把一个较窄的 i1 布尔值为
`BRCOND` 消费而加宽时用的是 `ANY_EXTEND` 而非 `ZERO_EXTEND`。在 `-O0`
（clang 给函数打 `optnone`，无论 `llc` 自身的 `-O` 标志是什么，都强制整个
`SelectionDAG` 流水线为 `CodeGenOptLevel::None`——直接验证：对同一份带
`optnone` 的 `.ll`，`llc -O0` 和 `llc -O2` 产生逐字节相同、同样错误的汇编），
`DAGCombiner.cpp` 的 `visitXOR` 里一条通用 combine
（`fold not (setcc x, y, cc) -> setcc x y !cc`）先把负极性写法
（`if ((x&1)==0)`/`if (!(x&1))`，真值分支落在 `else` 臂）里的
`xor(seteq(and,0),true)` 折成 `setne(and,0)`；随后另一条通用 combine
在这个特定 DAG 形状下把整条 `and`+`setcc` 链进一步折叠成裸的
`truncate(loadedByte, i1)`（等价，因为 truncate 到 i1 恰好取最低位）；
为 `BRCOND` 重新加宽这个 i1 时因为 `ANY_EXTEND` 被调用，
`ANY_EXTEND(TRUNCATE(X))` 直接代数化简成不带掩码的 anyext 装载——因为
`ANY_EXTEND` 允许"垃圾"高位——于是 `BRNZ` 变成测试"整个装载字节是否非零"
而不是"bit 0 是否为 1"。正极性写法（`if (l&1)`）没有走到这条 combine
（`and`+`setcc` 显式保留到指令选择），所以从未受影响。

声明 `ZeroOrOneBooleanContent` 让同一处加宽改走 `ZERO_EXTEND`，此时
`ZERO_EXTEND(TRUNCATE(X))` 无法免费抵消——必须物化一次真正的掩码——
从而恢复被丢弃的 `and rd,rd,<mask>`。

### 修复

`llvm/lib/Target/DADAO/DADAOISelLowering.cpp` 构造函数中加一行
`setBooleanContents(ZeroOrOneBooleanContent);`（含 25 行注释说明上述机制）。

### 960608-1.c 二分结论

**确认为同一根因**（非"巧合变绿"）：直接比对修复前后的 `.s`，函数内
`||` 链的**第一个**子条件（`flags->c != 0`，位域读取，编译成
`shru`+`and`+`brnz`）修复前恰好缺失 `shru` 之后的 `and rd16,rd16,1`，
修复后在完全相同位置恢复；同一 `||` 链里的其它子条件修复前就已经带
`and`（走了不同的 DAG 路径），修复前后逐字节不变。

### 通用性验证（ground truth，非手算期望值）

用 4 宽度（int/long/char/short）× 4 掩码（1/2/4/0xff）× 4 比较
（eq0/ne0/eq1/not）× 2 极性 = 128 个函数、每函数 9 个输入 = 1152 个
向量的矩阵，同一份源码分别在**宿主机原生编译执行**（ground truth）和
DADAO QEMU 流水线下跑，两边逐行 diff：
- 修复前：45/1152 向量分叉，精确对应 9/128 个函数形状，**全部 mask=1**、
  全部语义等价于"masked-result-is-zero"，覆盖 int/char/short 但不覆盖
  long（与诊断的 combine 触发条件一致）。
- 修复后：**0/1152 分叉**。

### 交付物

- `llvm/lib/Target/DADAO/DADAOISelLowering.cpp`：+25 行（1 行是fix，24行注释）
- `llvm/test/CodeGen/DADAO/negative-polarity-bitand-mask.ll`（新增，13
  个函数，覆盖正负极性×掩码 1/2/4/0xff×eq0/ne0/eq1/not×i8/i16/i32/i64）——
  独立验证：对修复前编译器跑该 lit 测试 FAIL，修复后 PASS
- `tests/lit/E2E/Inputs/negative_polarity_bitand_mask.c` +
  `tests/lit/E2E/negative_polarity_bitand_mask.test`（新增，volatile 输入
  + 不短路累加的正负控制，QEMU+gem5 双后端×O0+O2）——独立验证：修复前
  O0 阶段即 FAIL，修复后 PASS
- LLVM commit `42a9070dce2a`（`.work/llvm`，普通 commit，HEAD 前进）
- patch `components/llvm/patches/0061-DADAO-declare-ZeroOrOneBooleanContent-to-stop-O0-mas.patch`，已追加进 `series`
- `docs/issues.yaml` 的 `dadao-o0-negative-polarity-bitand-mask-dropped`
  条目已移除，完整迁移到 `docs/issues-archive.yaml` 并置
  `status: closed`、`resolved_by: "ML-036a; ..."`，附完整根因/修复/验证记录

### 验收结果

| 项 | 修复前基线 | 修复后 |
|---|---|---|
| gcc-c-torture 1708 全量 | 1461/104/125/18 | **1464/104/125/15**（逐文件 diff：仅 931102-1.c/931102-2.c/960608-1.c 从 FAIL_RUN→PASS，其余 1705 个文件零变化） |
| llvm-lit `tests/lit/E2E/` | 77/77 | **78/78**（77 基线 + 1 个新增测试，零回归） |
| llvm-lit `CodeGen/DADAO/` | 9/9 | **10/10**（9 基线 + 1 个新增测试，零回归） |
| `tools/run_differential.py` | AGREE(4-way)=200/DIVERGE=0 | **不变**（spec 向量层harness，不经过 codegen，确认未受影响） |
| `scripts/manifest_check.py` | PASS | **PASS** |
| `scripts/check_issues.py` | PASS（open 23/closed 40） | **PASS**（open 22/closed 41） |
| patch 裸 pin 重放 | — | `git worktree` 到 pin commit `ca7933e47d3a` + `git am` 全部 61 个 patch 成功，replay tree hash `f52e7a386ff53103fe829323f705787317e4de3d` 与开发树 `HEAD^{tree}` 完全一致 |

## 审阅记录（自审，2026-07-24）

- Finding 1：矩阵测试脚本第一版（`gen.py`）用"return 累加 fails 计数"
  作为退出码——发现 `fails` 可能 ≥256 导致 exit code mod 256 环绕回 0，
  险些把"256/512 向量分叉"误判为"0 fails"。判决：**真实缺陷（自己的测试
  方法论），已发现并改正**——弃用累加退出码，改用 printf 输出 + 宿主机
  ground truth 逐行 diff（`gen3.py`/`matrix3.c`），此后所有分叉计数结论
  均基于这条更严谨的路径。
- Finding 2：第二版按 width 拆分的测试文件（`gen2.py`）显示 int/long/char/
  short 各自 64-66 fails，与 combined 矩阵的 6 fails 严重不一致——排查后
  发现是**测试生成脚本自己的 python "expected" 手算逻辑有 bug**（正极性
  分支的期望值推导对 `not`/`eq1` 比较符号弄反了），不是 DADAO 编译器的
  问题。判决：**已发现并绕过**——放弃手算 expected，全部改成宿主机原生
  执行取 ground truth。
- Finding 3：diff/grep 命令在 bash 工具里出现过一次诡异的假阴性
  （`diff` 打印 `[ok] Files are identical` 而两文件 md5 明显不同）。用
  `/usr/bin/diff`/`/usr/bin/cmp` 直接调用复现出真实差异，怀疑是执行环境
  里某层命令封装/缓存的瞬时问题，非本任务逻辑错误。判决：**已用绝对路径
  规避，不影响最终结论**（所有关键 diff 结论都用 `/usr/bin/diff` 或
  python 直接读文件比对复核过）。
- Finding 4：`ninja`（不带具体 target）在构建 `libclang-cpp.so` 链接阶段
  被 OOM kill（`ld terminated with signal 9`）。判决：**环境资源限制，非
  本任务改动引入**——`ninja clang llc` 精确构建所需目标每次都干净成功，
  不需要构建 `bugpoint` 等无关工具；未追查/未修复这个无关的资源问题。
- Finding 5：`960608-1.c` 的确认方式——任务书要求"如果没能孤立出确定
  结论，如实报告不要强行下结论"。本次**没有依赖"变绿了"这一间接证据**，
  而是直接对比了修复前后的 `.s`，在 `||` 链第一个子条件里逐指令确认了
  同一 `shru`+缺失`and`+`brnz`-测试未掩码值 的特征，因此这里是**确定
  结论**（同一根因），不是"强嫌疑"。
- Finding 6：mask=0xff 的情况下 CodeGen lit 测试**不要求**出现显式
  `and` 指令，理由是 `ldbu`（无符号字节装载）本身已经等价于 `& 0xff`
  掩码。判决：这是正确的、经查验的行为（`ldbu` 零扩展，不会引入本类
  bug），故该测试用例断言的是 `ldbu` 存在而非 `and`——已在测试文件注释
  中说明，不是宽松放过。
- 结论：所有 finding 均已在本次任务内自行发现、自行修正或明确判定为
  环境噪声，不影响修复本身与验收结果的正确性；未发现需要转交/升级的
  阻断性问题。
