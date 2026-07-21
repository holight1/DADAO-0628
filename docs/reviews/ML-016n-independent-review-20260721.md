# ML-016n 独立 reviewer 记录

日期：2026-07-21（Asia/Shanghai）  
结论：**Accepted-with-findings**

## 范围与材料

独立读取了 `/tmp/ml-016n-selectiondag-illegal-result-repro-20260721/` 的
`summary.tsv`、`variant-summary.tsv`、`commands.tsv`、各阶段 `.rc/.stderr/.argv`，
真实 `intscan.c` 的 O0/O3 source/IR/asm，O3 isel/llc 诊断，以及 legalized/selected
raw DAG。用户指定的
`/home/holight/DADAO-0628/code-agent/tasks/ML-016n-selectiondag-illegal-result-repro-20260721.md`
在当前 workspace 不存在；同名 worker report 实际位于
`docs/reviews/ML-016n-selectiondag-illegal-result-repro-20260721.md`，以下按该材料
和 tmp 产物复核。未修改实现、构建、测试或规范文件。

## 主复现核验

主矩阵的关键 rc 与 stderr 一致：

| case | frontend | clang | llc | 观察 |
|---|---:|---:|---:|---|
| `intscan O0` | 0 | 0 | 0 | 生成 asm |
| `intscan O3` | 0 | 1 | 134 | `Illegal result number!` |
| `integer/overflow/intrinsic O0/O3` | 0 | 0 | 0 | 无 stderr |
| `multi_result/result_number O0/O3` | IR-input | 0 | 0 | 无 stderr |
| `call_shapes O3` | IR-input | 0 | 134 | 另一条 `insertBranch` UNREACHABLE |

`intscan.O3` clang 和 llc 的 stderr 都明确指向
`SDNode::getValueType` 的 `ResNo < NumValues` assertion；stack dump 均落在
`DADAO DAG->DAG Pattern Instruction Selection`、`@__intscan`，具体栈为
`ScheduleDAGSDNodes::BuildSchedUnits`/`BuildSchedGraph`。原始复现 record 也保留了
真实 build 命令、`-O3` 最终 cc1 命令、rc=1、stderr 及预处理 reproducer。

`intscan.O3.ll` 是前端成功产生的优化后 IR，且包含 `llvm.ctpop.i32`、
`llvm.umul.with.overflow.i64`/`extractvalue`、compare/select、整数 shift 与多处
`___errno_location` pointer-return call；O0 IR 保留未优化的普通控制流/乘法形状。
直接对 O3 IR 做 llc 时，O0/O1/O2/O3 均为 rc=134，而对 O0 IR 的 llc O0 成功，
这进一步把边界定位在优化后 IR 的后端处理，而不是 frontend parser 或 clang driver。

## `t58:i64 -> t58:1` 证据

证据充分支持“该 selected DAG 含非法 result 引用”这一层结论：

- legalized DAG 的 `t7` 是 `ch,glue`，`CopyFromReg` 使用合法的 `t7:1`；
- 同一 block 的 selected DAG 将 call 重写为 `t53: ch,glue = CALL_IIII ...`，但
  `t58: i64 = ADDI_RRII ... <63>` 只有一个 i64 value，却出现
  `t9: i64,ch,glue = CopyFromReg t53, Register:i64 $rb31, t58:1`；
- selected DAG 的 `TokenFactor` 还引用 `t9:1`，而 assertion 紧随 instruction
  selection 结束、进入 scheduler 的 `BuildSchedUnits` 发生；
- raw DAG 之外的 clang/llc assertion、函数名、阶段和 rc 相互独立重现。

因此，`t58:1` 不是从最终 asm 反推的猜测，而是 selected DAG 文本中可直接核对的
越界 result number。证据足以支撑 SelectionDAG/selector 后端缺陷的 repro 与
regression 边界；不足以单独证明某一个 intrinsic lowering、某一条 ABI 规则或某个
TableGen pattern 是唯一根因。

## 对照与不泛化判断

`c_intrinsic_shapes.c`/`intrinsic_shapes` 覆盖 ctpop、ctlz、cttz、ctpop 后 shift/index
及与 overflow 组合；`c_overflow_shapes.c` 覆盖 value/flag/select/compare 的
`umul.with.overflow` 与 signed overflow；`c_integer_shapes.c` 覆盖整数运算、compare、
select、循环和 widen/narrow；`ir_multi_result.ll` 覆盖 `{i64,i1}` 的两个
extractvalue、双结果 select 和 intrinsic；`ir_result_number_shapes.ll` 覆盖无 call、
errno pointer call、`__shgetc`、umul 后的 shift/select。上述 O0/O3 clang/llc 的
`.rc` 均为 0，`.stderr` 为空，且 clang/llc asm 均已生成。因此不能把 ctpop、overflow、
compare/select、multi-result 或一般 result-number 形状单独宣称为根因。

`call_shapes` O3 llc 的失败是 Control Flow Optimizer 中
`TargetInstrInfo::insertBranch` 未实现，不是本 assertion；worker report 对此未合并，
判断正确。`result_number_shapes` 的成功也只是 negative control，不等于证明
SelectionDAG 全面正确。

本单例不应与 sign-extend-inreg、tail-call return、AsmPrinter unknown operand、RB31
MachineVerifier 或 libc/archive/runtime/QEMU/gem5 簇合并。`$rb31` 在 raw DAG 中只是
pointer-return call 的读取位置，不能据此改判为 ABI 根因；当前可安全归类为
“优化后 `__intscan` 组合 DAG 在 selector/scheduler 边界形成非法 result 引用”。

## Findings

1. **非阻塞：一个 variant 不是有效对照。** `run_variants.sh` 使用的
   `-mllvm -disable-simplifycfg` 在当前 clang 中报 `Unknown command line argument`，
   所以 `O3_nosimplifycfg rc=1` 不能计入“O3 仍因 illegal-result 失败”的证据。应在后续
   汇总中标为 invalid-command，不要仅按 rc=1 归入 crash matrix。

2. **结论边界需保持现状。** worker report 已基本做到不把单例泛化为 intrinsic/ABI
   根因；后续修复或 regression 说明应继续把 `t58:1` 写成 observed selected-DAG
   corruption，并把具体 selector/lowering/ABI 归因留给进一步 reduction 或实现级
   证据。

## 终审

作为诊断型 repro，主失败、阶段、raw DAG、预处理 reproducer、O0/O3 对照和负向 probe
证据链足够，且未把独立 CFG 失败或其他簇合并。由于 `O3_nosimplifycfg` 的记录未被
标记为无效命令，给出 **Accepted-with-findings**；该 finding 不阻塞 ML-016n 的当前
SelectionDAG illegal-result 诊断结论。
