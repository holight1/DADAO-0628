# ML-016o inline asm register constraint 最小复现 review

日期：2026-07-21（Asia/Shanghai）  
范围：只读诊断；未修改 LLVM/TableGen、musl、主 build/archive、QEMU/gem5 或运行时验收面。

## 结论

失败不是 frontend 解析或 IR 生成失败，而是 DADAO backend 在 SelectionDAG inline-asm constraint allocation 阶段没有为通用 `"r"` 约束分配寄存器。`r` input、`=r` output、`=r,r` 和 `+r` 均独立失败；无操作数 asm、内存约束和 clobber 形状均能通过 O0/O3。整数宽度没有改变这个边界。

只读 target 证据显示 DADAO lowering 注册了 i64 `GPRD`，但 DADAO 没有 `getRegForInlineAsmConstraint` 的 `"r"` 映射。LLVM generic fallback 仅处理显式 `{register}` 约束，因此 `"r"` 没有可用 register class，最终在 SelectionDAGBuilder 报 allocation failure。本 task 没有提出或实施修复。

## explicit_bzero source / IR / raw diagnostics

原始 source：[explicit_bzero.c.original](/tmp/ml-016o-inline-asm-constraint-repro-20260721/probes/source/explicit_bzero.c.original)；fresh source：[explicit_bzero.c](/tmp/ml-016o-inline-asm-constraint-repro-20260721/probes/source/explicit_bzero.c)。两者与仓库中的 musl source 用 `cmp` 核对一致。

原始对象记录与诊断：[original.record](/tmp/ml-016o-inline-asm-constraint-repro-20260721/logs/metadata/explicit_bzero.original.record)、[original.stderr](/tmp/ml-016o-inline-asm-constraint-repro-20260721/logs/metadata/explicit_bzero.original.stderr)。原始 stderr 是：`couldn't allocate input reg for constraint 'r'`，位置为 `__asm__ __volatile__ ("" : : "r"(d) : "memory")`。

历史 frontend IR：[explicit_bzero.original.ll](/tmp/ml-016o-inline-asm-constraint-repro-20260721/probes/ir/explicit_bzero.original.ll)；fresh IR：[explicit_bzero.O0.ll](/tmp/ml-016o-inline-asm-constraint-repro-20260721/probes/ir/explicit_bzero.O0.ll)、[explicit_bzero.O3.ll](/tmp/ml-016o-inline-asm-constraint-repro-20260721/probes/ir/explicit_bzero.O3.ll)。O0/O3 frontend 均 rc=0；O0 保留 alloca/load，O3 折叠为 tail call，但二者都保留 `"r,~{memory}"(ptr ...)`。

| 阶段 | O0 | O3 | 原始证据 |
|---|---:|---:|---|
| `clang -S -emit-llvm` | 0 | 0 | [frontend logs](/tmp/ml-016o-inline-asm-constraint-repro-20260721/logs/frontend) |
| `llc -mtriple=dadao` | 1 | 1 | [backend rc/stderr](/tmp/ml-016o-inline-asm-constraint-repro-20260721/logs/backend) |
| clang direct backend `-S` | 1 | 1 | [direct argv/rc/stderr](/tmp/ml-016o-inline-asm-constraint-repro-20260721/logs/frontend) |

backend raw stderr：[O0](/tmp/ml-016o-inline-asm-constraint-repro-20260721/logs/backend/explicit_bzero.O0.stderr)、[O3](/tmp/ml-016o-inline-asm-constraint-repro-20260721/logs/backend/explicit_bzero.O3.stderr)。direct clang 的 warning、error、argv 和 rc 也原样保存；因 rc=1，没有 explicit_bzero asm 输出。

## O0/O3 constraint matrix

每个 probe 都先生成 frontend IR，再单独调用 `llc`；成功项保留 asm，失败项保留原始 stderr。完整机器索引见 [matrix-current.tsv](/tmp/ml-016o-inline-asm-constraint-repro-20260721/logs/metadata/matrix-current.tsv)，所有命令的逐参数 argv、rc、stdout、stderr 分别在 [frontend logs](/tmp/ml-016o-inline-asm-constraint-repro-20260721/logs/frontend)、[backend logs](/tmp/ml-016o-inline-asm-constraint-repro-20260721/logs/backend)、[MIR logs](/tmp/ml-016o-inline-asm-constraint-repro-20260721/logs/mir) 和 [debug logs](/tmp/ml-016o-inline-asm-constraint-repro-20260721/logs/debug)。

| 形状 | IR constraint | O0 | O3 | 结果 |
|---|---|---:|---:|---|
| 无操作数空 asm / `trap 2, 0` | empty | 0 | 0 | 通过；asm 保留 `#APP/#NO_APP`，trap 形状保留文本 |
| pointer input | `r` | 1 | 1 | `couldn't allocate input reg` |
| i64 scalar input | `r` | 1 | 1 | `couldn't allocate input reg` |
| i64 output | `=r` | 1 | 1 | `couldn't allocate output register` |
| output + input | `=r,r` | 1 | 1 | output allocation failure |
| tied in/out | `+r`（IR 为 `=r,0`） | 1 | 1 | output allocation failure |
| memory input/output/inout | `m`、`=m`、`+m` | 0 | 0 | MIR 为 `mem:m`，asm 生成成功 |
| clobber | `memory`、`cc`、`memory+cc` | 0 | 0 | 无寄存器 operand，asm 生成成功 |
| integer width input/output/inout | u8/u16/u32/u64 + `r` | 1 | 1 | 无宽度特异性，均在 constraint 阶段失败 |

原始 probe source 位于 [probes/source](/tmp/ml-016o-inline-asm-constraint-repro-20260721/probes/source)，IR 位于 [probes/ir](/tmp/ml-016o-inline-asm-constraint-repro-20260721/probes/ir)，成功 asm 位于 [probes/asm](/tmp/ml-016o-inline-asm-constraint-repro-20260721/probes/asm)。可复跑 runner：[run-probes.sh](/tmp/ml-016o-inline-asm-constraint-repro-20260721/run-probes.sh)。

## register-class / CodeGen regression boundary

只读 source 对照：

- `DADAOISelLowering.cpp:26` 通过 `addRegisterClass(MVT::i64, &DADAO::GPRDRegClass)` 注册 i64 GPRD。
- `DADAORegisterInfo.td` 声明 GPRD/GPRB 都只含 i64；calling-convention debug dump 显示 pointer input 的 live-in 是 `$rb16` / `gprb`，i64 scalar input 是 `$rd16` / `gprd`。
- DADAO 的 `DADAODAGToDAGISel` 实现了 `SelectInlineAsmMemoryOperand`，但返回 false，未实现通用 register constraint mapping。
- generic `TargetLowering::getRegForInlineAsmConstraint` 只对 `{...}` 显式寄存器名返回 register class；`"r"` 返回空 class。`SelectionDAGBuilder` 随后在 `couldn't allocate input/output ... constraint 'r'` 分支报错。

这解释了两个关键对照：pointer 与 scalar 的入口 register class 不同，但都在 `r` mapping 处失败；memory constraint 不请求 register class，因此能继续到 `INLINEASM ... mem:m` 和 AsmPrinter。失败 probe 的 `-stop-after=finalize-isel` 也保持同一 rc=1，说明没有进入可供 register allocator/AsmPrinter 处理的 inline-asm MachineInstr。

## 与无操作数 inline asm、AsmPrinter 单例的边界

无操作数 asm 的 `INLINEASM` 没有 input/output register operand，O0/O3 均能到达 AsmPrinter 并生成 asm；它只能证明无寄存器约束路径，不证明 `"r"` 路径或 libc/runtime。

ML-016m 的单例是另一条路径：已选择的 `CALL_IIII &abort` 携带 external-symbol MachineOperand，在 DADAO AsmPrinter `lowerToMCInst` 阶段报 `unknown operand type`。本 task 的 `r` 失败发生更早，在 SelectionDAG inline-asm constraint allocation；`=r,r` 不是 AsmPrinter failure，也不是 ML-016m 的 external-symbol operand。两者边界与相邻成功形状见 [ML-016m review](../reviews/ML-016m-asmprinter-unknown-operand-repro-20260721.md)。

## 验收边界

本交付只确认 frontend source/IR、raw diagnostics、inline-asm constraint/register-class CodeGen 边界及 O0/O3 对照；不把 frontend-only、单个 asm 输出或 backend 单对象成功解释为 archive、libc、runtime、QEMU/gem5 验收。仓库内仅更新本 task 完成区和本 review 文档。
