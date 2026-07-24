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
