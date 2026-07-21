# ML-016n：SelectionDAG illegal result number 最小复现

**日期**：2026-07-21

**状态**：Audit-accepted-with-findings（ML-016 新 30-task run：14/30）

## 背景

ML-016g 将 `intscan.o` 单独归为 SelectionDAG assertion `Illegal result number!`。
需要定位触发的 IR/DAG 节点、结果编号和优化级别，确认是否是单一 intrinsic/多结果
节点/target lowering 形状；不能把 assertion 当作 generic backend failure。

## 目标与 ownership

worker 只做 `/tmp` 诊断：

1. 对 `intscan.c` 保存 source/IR、clang/llc argv/rc/stderr、stack/节点诊断；定位
   assertion 前后的函数与 DAG operation/result number。
2. 生成最小 LLVM IR/C probes，覆盖相关整数转换、比较、select、multi-result 或
   intrinsic 形状，并按 O0/O3 保存成功/失败对照。
3. 给出 SelectionDAG/CodeGen regression 边界，明确哪些是候选 lowering bug，不修改
   LLVM/TableGen。

## 约束

- 只写本 task 完成区和 `docs/reviews/ML-016n-selectiondag-illegal-result-repro-20260721.md`；
  probe/日志/脚本均放 `/tmp/ml-016n-selectiondag-illegal-result-repro-20260721/`。
- 不修改 LLVM、musl、主 build/archive、QEMU/gem5、contracts、vectors、issues、wiki
  或 ML-014a。
- 不访问或引用 `~/toolchain`、`~/knowledge-graph`；不使用 `|| true`。
- 不把 frontend-only、单个 llc 成功或 asm 生成当作完整 libc/runtime 验收。

## 完成区

### worker 交付（2026-07-21）

状态：诊断完成，待不同 subagent 独立 review；不预置 Accepted。本轮只读复核了真实
`intscan.c`、O0/O3 frontend IR、clang/llc 后端、原始 assertion 和 SelectionDAG debug
输出，未修改 LLVM/TableGen、musl、主 build/archive、QEMU/gem5、contracts、vectors、
issues、wiki 或 ML-014a。仓库内只写本完成区和指定 review 文档；所有 probe、脚本、IR、
asm、argv、rc、stdout、stderr 均在 `/tmp/ml-016n-selectiondag-illegal-result-repro-20260721/`。

真实 source 与原始失败证据：

- source 副本：[intscan.c](/tmp/ml-016n-selectiondag-illegal-result-repro-20260721/probes/source/intscan.c)
  与 [intscan.h](/tmp/ml-016n-selectiondag-illegal-result-repro-20260721/probes/source/intscan.h)。
- 原始隔离命令的 [record](/tmp/ml-016n-selectiondag-illegal-result-repro-20260721/logs/clang/intscan.original.record)、
  [stderr](/tmp/ml-016n-selectiondag-illegal-result-repro-20260721/logs/clang/intscan.original.stderr)、
  [preprocessed source](/tmp/ml-016n-selectiondag-illegal-result-repro-20260721/probes/source/intscan.original-crash-preprocessed.c)
  和 [crash argv script](/tmp/ml-016n-selectiondag-illegal-result-repro-20260721/logs/clang/intscan.original-crash.sh)
  均保留。
- 当前可复核入口：[evidence-index.tsv](/tmp/ml-016n-selectiondag-illegal-result-repro-20260721/results/evidence-index.tsv)、
  [summary.tsv](/tmp/ml-016n-selectiondag-illegal-result-repro-20260721/results/summary.tsv)、
  [failure-signatures.tsv](/tmp/ml-016n-selectiondag-illegal-result-repro-20260721/results/failure-signatures.tsv)。

真实 `__intscan` 结果：frontend IR 在 O0/O3 均 `rc=0`；clang backend 为 O0 `rc=0`、
O3 `rc=1`，llc 为 O0 `rc=0`、O3 `rc=134`。O3 两条 stderr 都保留
`SDNode::getValueType` 的 assertion（`ResNo < NumValues && "Illegal result number!"`）；
stack dump 均指向 `DADAO DAG->DAG Pattern Instruction Selection` 的 `@__intscan`，
不是 frontend-only 失败。O1/O2/O3 真实 source 均失败，O0 成功；O3 加
`-mllvm -disable-llvm-optzns` 成功，说明触发边界在优化后 IR/DAG 形状，而不是 O3
文字标签本身。完整 level/flag 原始 argv 与 rc 在 [variant-summary.tsv](/tmp/ml-016n-selectiondag-illegal-result-repro-20260721/results/variant-summary.tsv)。

节点定位已闭合到一个具体非法引用：`intscan.O3` 的最后失败 block 是
`@__intscan:for.end346`。在 [raw selected DAG](/tmp/ml-016n-selectiondag-illegal-result-repro-20260721/probes/raw/intscan.O3.bb79.selected-dag.raw.txt)
中，选择后的节点含：

```text
t58: i64 = ADDI_RRII Register:i64 $rd0, TargetConstant:i64<63>
t9: i64,ch,glue = CopyFromReg t53, Register:i64 $rb31, t58:1
t53: ch,glue = CALL_IIII ... @___errno_location ...
```

`t58` 是单结果 i64 `ADDI_RRII`，却被当作 `t58:1` 作为 `CopyFromReg` glue/result
引用；这解释了随后 scheduler 在 `getValueType(ResNo)` 上触发 assertion。前置
[legalized DAG](/tmp/ml-016n-selectiondag-illegal-result-repro-20260721/probes/raw/intscan.O3.bb79.legalized-dag.raw.txt)
中的 call-result glue 仍是合法的 `t7:1`。当前最高价值候选是 DADAO SelectionDAG
instruction selection 在 pointer-return `___errno_location` call 与同一 DAG 的整数
shift/select 计算组合中错误传播 glue/result number；这是候选 lowering/selector bug，
未修改实现，也未把它升级成 ABI/RB31 verifier 根因。

O3 IR 还明确保留相关形状：[intscan.O3.ll](/tmp/ml-016n-selectiondag-illegal-result-repro-20260721/probes/ir/intscan.O3.ll)
含带 range 的 `llvm.ctpop.i32`、`llvm.umul.with.overflow.i64` 的 `{i64,i1}` 返回及
`extractvalue`，而 O0 IR 保留普通整数 mul/phi 形状；因此已覆盖整数转换、比较、
select、multi-result 和 intrinsic 的 source/IR 对照。独立 C/IR probe 的 O0/O3
frontend、clang、llc 结果均成功：`integer_shapes`、`overflow_shapes`、
`intrinsic_shapes`、`multi_result` 和专门的 `result_number_shapes` 均未单独复现
assertion。这表明单个 `umul.with.overflow`、`ctpop`、compare/select 或简单 pointer
call 不是充分触发器；当前最小稳定 reproducer 仍是优化后的真实 `__intscan` IR/source
加该调用/控制流上下文，不能声称已隔离为单一 intrinsic。

边界：本单例发生在 SelectionDAG scheduler/selector 之后的非法 result reference；
没有 `Cannot select sign_extend_inreg from i1`、没有 `LowerCall emitted a return value
for a tail call!`、没有 DADAO AsmPrinter unknown operand，也没有 MachineVerifier
undefined physical register 结论。`$rb31` 在 raw DAG 中只是该 pointer-return call 的
结果 bank，不把本 assertion 与 ML-016j RB31 verifier、ML-016l i1、ML-016k tail-call
或 ML-016m AsmPrinter 合并。`call_shapes` 的 llc O3 汇总中另有一个
`TargetInstrInfo::insertBranch` CFG optimizer abort；该不相关错误已排除，未作为本
SelectionDAG 证据。

本轮没有链接、archive、libc/runtime、QEMU/gem5 验收；frontend IR 或单个 O0 asm 成功
不代表完整 libc/runtime 可用。后续 CodeGen regression 应固定真实 `__intscan` O0
成功/O1-O3 失败矩阵，并检查 `for.end346` 的 selected DAG 不得出现单结果节点的
`ResultNo=1`；同时保留 `ctpop.i32`、`umul.with.overflow.i64`、compare/select 和
simple pointer-call 成功对照，避免误报为 intrinsic-only、i1、tail-call、AsmPrinter
或 RB31 verifier 修复。

独立 reviewer Huygens the 2nd 的结论为 **Accepted-with-findings**，见
`docs/reviews/ML-016n-independent-review-20260721.md`。review 确认 `t58:i64 → t58:1`
的 selected-DAG 证据充分；`O3_nosimplifycfg` 使用无效参数，不能作为有效失败对照，
已保留为证据卫生 finding。
