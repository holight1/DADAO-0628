# ML-016o inline asm constraint 独立 review

日期：2026-07-21（Asia/Shanghai）  
审查方式：独立抽查 worker task、既有 review，以及 `/tmp/ml-016o-inline-asm-constraint-repro-20260721/` 的原始四阶段记录。未修改 LLVM/TableGen、musl、build/archive、测试或规范。

## 最终结论

**Accepted-with-findings**

核心结论成立：本复现把失败限定在 DADAO backend 对通用 `r` inline-asm 约束的寄存器类映射/分配入口，而不是 frontend、所有 inline asm、ABI 总体或 ML-016m 的 AsmPrinter 单例。

## 独立证据核对

### 1. task 输入与 explicit_bzero

用户指定的 dated task 路径
`/home/holight/DADAO-0628/code-agent/tasks/ML-016o-inline-asm-constraint-repro-20260721.md`
当前不存在；实际读取了同目录同名但不带日期的
[ML-016o-inline-asm-constraint-repro.md](/home/holight/DADAO-0628/code-agent/tasks/ML-016o-inline-asm-constraint-repro.md)，以及既有 [worker review](/home/holight/DADAO-0628/docs/reviews/ML-016o-inline-asm-constraint-repro-20260721.md)。

`explicit_bzero` 的原始 compile record、argv 和 stderr 相互吻合：原始 stderr 为
`couldn't allocate input reg for constraint 'r'`；fresh O0/O3 frontend 均 rc=0，保留
`"r,~{memory}"(ptr ...)`；随后独立 `llc -mtriple=dadao` 的 O0/O3 均 rc=1，stderr
仍为同一 input-reg allocation error。直接 clang backend 的 O0/O3 也均 rc=1，并保留
warning、error、argv 和空 asm 输出。证据见：

- [original record](/tmp/ml-016o-inline-asm-constraint-repro-20260721/logs/metadata/explicit_bzero.original.record)
- [original stderr](/tmp/ml-016o-inline-asm-constraint-repro-20260721/logs/metadata/explicit_bzero.original.stderr)
- [O0 frontend argv/rc/stderr](/tmp/ml-016o-inline-asm-constraint-repro-20260721/logs/frontend/explicit_bzero.O0.argv)
- [O3 backend argv/rc/stderr](/tmp/ml-016o-inline-asm-constraint-repro-20260721/logs/backend/explicit_bzero.O3.argv)
- [fresh O0/O3 IR](/tmp/ml-016o-inline-asm-constraint-repro-20260721/probes/ir/explicit_bzero.O0.ll)

原始 source 与 fresh source 仅有缩进差异，snapshot check 为 `cmp=all-match`；这足以支持
该复现仍针对同一 source 形状。

### 2. 四阶段与约束矩阵

`matrix.tsv` 的四阶段记录与逐命令 raw 文件一致：frontend probe 生成成功，direct
clang 的两个 explicit_bzero backend 命令 rc=1；backend 对照中无操作数、内存和 clobber
成功，而 `r` 形状失败；MIR 对成功形状 rc=0、失败形状 rc=1；debug 记录的 8 个选定
失败样本 rc=1，诊断和 SelectionDAG trace 写在 stderr 中。

独立抽查结果如下：

| 形状 | O0/O3 backend | 原始边界 |
|---|---:|---|
| pointer input `r` | 1 / 1 | `couldn't allocate input reg` |
| i64 scalar input `r` | 1 / 1 | `couldn't allocate input reg` |
| output `=r` | 1 / 1 | `couldn't allocate output register` |
| output + input `=r,r` | 1 / 1 | output allocation failure |
| tied in/out `+r`（IR 为 `=r,0`） | 1 / 1 | output allocation failure |
| 无操作数空 asm、`trap 2, 0` | 0 / 0 | asm 文件存在并保留文本 |
| `m`、`=m`、`+m` | 0 / 0 | finalize-isel MIR 有 `INLINEASM ... mem:m` |
| `memory`、`cc`、组合 clobber | 0 / 0 | asm 文件存在，stderr 为空 |
| u8/u16/u32/u64 的 input/output/inout `r` | 全部 1 / 1 | 与宽度无关的同类 allocation error |

关键 raw 文件包括 [matrix.tsv](/tmp/ml-016o-inline-asm-constraint-repro-20260721/logs/metadata/matrix.tsv)、
[backend logs](/tmp/ml-016o-inline-asm-constraint-repro-20260721/logs/backend)、
[MIR logs](/tmp/ml-016o-inline-asm-constraint-repro-20260721/logs/mir) 和
[debug logs](/tmp/ml-016o-inline-asm-constraint-repro-20260721/logs/debug)。

### 3. 失败阶段、register class 与 ABI 边界

失败的 `-stop-after=finalize-isel` 命令仍 rc=1，且对应 `.mir` 文件不存在；debug trace
在 allocation error 后只显示普通 DAG 节点被选择，最终 machine dump 没有 `INLINEASM`。
相反，成功的无操作数/内存形状在 [MIR](/tmp/ml-016o-inline-asm-constraint-repro-20260721/probes/mir)
中保留 `INLINEASM`，并实际生成 asm。这支持“失败发生在 SelectionDAG inline-asm
constraint allocation，尚未进入可打印的 inline-asm MachineInstr”的结论。

只读 target source 也与该边界一致：

- [DADAOISelLowering.cpp:26](/home/holight/DADAO-0628/.work/source/llvm/llvm/lib/Target/DADAO/DADAOISelLowering.cpp:26) 注册 i64 `GPRD`。
- [DADAORegisterInfo.td:42](/home/holight/DADAO-0628/.work/source/llvm/llvm/lib/Target/DADAO/DADAORegisterInfo.td:42) 与 :51 声明 GPRD/GPRB，二者 value type 都是 i64。
- [DADAOISelDAGToDAG.cpp:21](/home/holight/DADAO-0628/.work/source/llvm/llvm/lib/Target/DADAO/DADAOISelDAGToDAG.cpp:21) 只有 `SelectInlineAsmMemoryOperand`，实现返回 false；没有 DADAO 自己的 `getRegForInlineAsmConstraint`。
- generic [TargetLowering.cpp:5872](/home/holight/DADAO-0628/.work/source/llvm/llvm/lib/CodeGen/SelectionDAG/TargetLowering.cpp:5872) 对非 `{register}` 约束返回空 register/class pair；SelectionDAGBuilder 随后在 [input/output allocation error 分支](/home/holight/DADAO-0628/.work/source/llvm/llvm/lib/CodeGen/SelectionDAG/SelectionDAGBuilder.cpp:10311) 报错。

debug/MIR 对照还显示 pointer input 的入口为 `$rb16/gprb`、i64 scalar input 的入口为
`$rd16/gprd`，两者都在相同的 `r` mapping/assignment 边界失败。因此没有把该现象
过度泛化为所有 inline asm，也没有证据把它写成 ABI 根因。更严格地说，当前证据只定位
到 inline-asm `r` mapping 缺口；它不构成完整 ABI 正确性的证明或否定。

### 4. 与 ML-016m AsmPrinter 单例分离

分离成立。ML-016o 的失败在 finalize-isel 之前，raw stderr 是
`couldn't allocate ... constraint 'r'`，没有待打印的 inline-asm MachineInstr。
ML-016m 的 raw stderr 则已经打印出 `CALL_IIII &abort`，随后在
`DADAOAsmPrinter.cpp:82` 报 `lowerToMCInst: unknown operand type`；其
finalize-isel MIR 为 rc=0，并保留 `CALL_IIII &abort`。ML-016m 的 ordinary external
call 使用 `CALL_IIII @abort` 并成功，说明其单例是已选择 MachineInstr 的
external-symbol operand lowering，而不是本 task 的 `r` constraint allocation。

证据见 [ML-016m raw stderr](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/logs/llc/crtjmp-trap.stderr)、
[ML-016m failing MIR](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/probes/mir/crtjmp-trap-finalize-isel.mir)
和 [ML-016m ordinary-call MIR](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/probes/mir/call-external-finalize-isel.mir)。

## Findings

1. **非阻塞：审查输入的 dated task 文件缺失。** 当前只能用不带日期的同名 task
   作为 fallback；若 dated 文件原本应包含不同内容，应补齐或确认两者等价。该问题不改变
   本次 raw 证据结论。

2. **非阻塞：worker review 的索引表述不精确。** `matrix-current.tsv` 明确排除了
   width probes；完整 width 记录在 [matrix.tsv](/tmp/ml-016o-inline-asm-constraint-repro-20260721/logs/metadata/matrix.tsv)
   和对应 backend logs 中。既有 review 将 `matrix-current.tsv` 称为“完整机器索引”应
   改为 current/non-width index，或同时链接 `matrix.tsv`。这只是证据导航问题，未推翻
   width 矩阵本身。

## 验收边界

本 review 只接受 frontend IR、四阶段 CodeGen/raw diagnostics、constraint/register-class
边界和 ML-016m 分离；不把单对象 asm、frontend-only、link、archive、runtime、QEMU/gem5
或 ABI 完整验收从本证据中推导出来。

**最终状态：Accepted-with-findings。**
