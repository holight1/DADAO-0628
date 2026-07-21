# ML-016n SelectionDAG illegal result number 最小复现 review

日期：2026-07-21（Asia/Shanghai）  
范围：worker 在 `/tmp/ml-016n-selectiondag-illegal-result-repro-20260721/` 生成的只读
诊断产物；本 review 不修改 LLVM/TableGen、musl、主 build/archive、QEMU/gem5 或其他
受保护范围。

## 结论

真实 musl `intscan.c` 的后端失败已稳定复现并定位到 SelectionDAG 的非法 result 引用：
frontend O0/O3 都成功；真实 source 的 clang 后端 O0 `rc=0`、O3 `rc=1`，llc O0
`rc=0`、O3 `rc=134`。O3 原始 stderr 是：

```text
llvm::SDNode::getValueType(unsigned int) const: Assertion
`ResNo < NumValues && "Illegal result number!"' failed.
```

stack dump 将函数标为 `@__intscan`，阶段为 `DADAO DAG->DAG Pattern Instruction
Selection`。O1/O2/O3 均失败，O0 成功；O3 配合 `-mllvm -disable-llvm-optzns` 成功。
因此当前边界是优化后 IR 进入 DADAO SelectionDAG 时的形状/selector 问题，不是
frontend-only 或单纯优化级别名称问题。本任务状态应为“诊断完成，待独立 review”，
不预置 Accepted。

## 原始证据与复核入口

- [evidence-index.tsv](/tmp/ml-016n-selectiondag-illegal-result-repro-20260721/results/evidence-index.tsv)：
  source、record、stderr、preprocessed source、argv script 和 raw DAG 入口。
- [summary.tsv](/tmp/ml-016n-selectiondag-illegal-result-repro-20260721/results/summary.tsv)：
  所有主矩阵的阶段 rc。
- [variant-summary.tsv](/tmp/ml-016n-selectiondag-illegal-result-repro-20260721/results/variant-summary.tsv)：
  O0/O1/O2/O3、优化开关和 O3 IR 的 llc 变体原始 rc/argv 对照。
- [intscan.original.record](/tmp/ml-016n-selectiondag-illegal-result-repro-20260721/logs/clang/intscan.original.record)、
  [intscan.original.stderr](/tmp/ml-016n-selectiondag-illegal-result-repro-20260721/logs/clang/intscan.original.stderr)、
  [intscan.O3 clang stderr](/tmp/ml-016n-selectiondag-illegal-result-repro-20260721/logs/clang/intscan.O3.stderr)、
  [intscan.O3 llc stderr](/tmp/ml-016n-selectiondag-illegal-result-repro-20260721/logs/llc/intscan.O3.stderr)。
- source、O0/O3 IR、成功 asm、每条命令的 `.argv`、`.rc`、`.stdout`、`.stderr` 均保留；
  runner 以 `if command; then rc=0; else rc=$?; fi` 记录失败，没有使用 `|| true`。

## 节点诊断

O3 debug-only=isel 输出的最后完整 block 是 `@__intscan:for.end346`（bb.79）。
[原始 selected DAG](/tmp/ml-016n-selectiondag-illegal-result-repro-20260721/probes/raw/intscan.O3.bb79.selected-dag.raw.txt)
包含：

```text
t58: i64 = ADDI_RRII Register:i64 $rd0, TargetConstant:i64<63>
t9: i64,ch,glue = CopyFromReg t53, Register:i64 $rb31, t58:1
t53: ch,glue = CALL_IIII ... @___errno_location ...
```

`t58` 的类型/结果数是单一 i64 结果，`t58:1` 却被作为 `CopyFromReg` 的 glue/result
引用；该引用越界，正好对应 `ResNo=1` assertion。相比之下，进入 isel 的
[legalized DAG](/tmp/ml-016n-selectiondag-illegal-result-repro-20260721/probes/raw/intscan.O3.bb79.legalized-dag.raw.txt)
使用合法的 `t7:1` callseq/glue。选择后再进入 scheduler 时触发断言，所以不能只用
最终 asm 或 frontend IR 成功替代此证据。

O3 IR 的相关源形状也已核对：[intscan.O3.ll](/tmp/ml-016n-selectiondag-illegal-result-repro-20260721/probes/ir/intscan.O3.ll)
含：

- `llvm.ctpop.i32`（带 `range(i32 1,33)`）及其后续整数索引/shift 计算；
- `llvm.umul.with.overflow.i64` 的 `{i64,i1}` 多结果与 `extractvalue`；
- 大量整数 compare/select/phi 和 `___errno_location` pointer-return call。

O0 IR 则保留普通 mul/phi，未形成相同的优化后 intrinsic/multi-result 形状。候选
机制是 DADAO selector/lowering 在 pointer-return call 和同一 SelectionDAG 的整数
shift/select 组合中错误重写或传播 glue/result number；这已由 raw DAG 支持，但尚未
证明为可脱离 `__intscan` 控制流的单一 intrinsic 根因。

## Probe 对照与边界

主 probe 覆盖整数运算/转换、compare/select、`umul.with.overflow`/其他多结果、
`ctpop`/`ctlz`/`cttz` intrinsic，以及直接 IR 的 `{i64,i1}` extractvalue 形状；
每项保留 O0/O3 frontend、clang、llc 的原始输出。独立 `integer_shapes`、
`overflow_shapes`、`intrinsic_shapes`、`multi_result` 和 `result_number_shapes`
均为 O0/O3 `rc=0`。所以这些节点单独不是充分触发器；稳定失败边界仍是优化后真实
`__intscan` 的组合 DAG。`call_shapes` 的 llc O3 另报 `TargetInstrInfo::insertBranch`
在 CFG optimizer 中未实现，属于独立 target CFG 问题，不能算作本 assertion 的复现。

本单例明确不合并以下问题：

- `sign_extend_inreg from i1`：本轮没有该诊断；
- tail-call return assertion：本轮使用 no-sibling call 约束且没有该诊断；
- DADAO AsmPrinter unknown operand：本轮没有进入 AsmPrinter；
- ML-016j RB31 verifier：raw DAG 中的 `$rb31` 只是 pointer-return call 读取位置，
  本轮失败发生在 SelectionDAG scheduler 之前/期间，不等同 MachineVerifier failure；
- 本轮没有链接、archive、libc/runtime 或 QEMU/gem5 acceptance。

## Regression 边界

后续 CodeGen regression 应保留真实 `__intscan` 的 O0 成功与 O1/O2/O3 失败对照，或
在完成进一步 reduction 后固定等价 IR；测试应检查 selected DAG/scheduler 不产生
单结果 i64 节点的 `ResultNo=1`，并保留 `ctpop.i32`、`umul.with.overflow.i64`、
compare/select 和简单 pointer-call 的成功 negative controls。修复前不能把单个
intrinsic、单个 O0 asm 或 frontend IR `rc=0` 宣称为完整后端、libc/archive 或 runtime
验收。

本轮实际修改仅为 ML-016n 完成区和本 review 文档；未修改实现文件。
