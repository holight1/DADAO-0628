# ML-016m AsmPrinter unknown operand 独立 review

日期：2026-07-21（Asia/Shanghai）  
审查范围：任务说明、worker review，以及 `/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/` 中的原始日志、IR、MIR 和 asm。  
结论：**Accepted-with-findings**

## 独立结论

worker 的核心定位成立：`__unmapself` 经过 `CRTJMP` 当前占位 helper
`@__dadao_crtjmp_not_implemented`，其中 `llvm.trap` 选择出首个
`CALL_IIII &abort`；完整 backend 运行在 DADAO Assembly Printer 中进入
`lowerToMCInst: unknown operand type`，并在
`DADAOAsmPrinter.cpp:82` 的 `llvm_unreachable` 终止。

这不是把普通 call、branch、inline asm 或 indirect-call/branch pseudo 泛化成失败，
也没有证据把本次 crash 归因于 ABI。失败发生在已选择的 MachineInstr 到 MCInst 的
打印转换阶段；没有进入生成 asm、目标文件、链接或运行时验收。

## `__unmapself` 原始链路

- 原始编译 record [__unmapself.o.record](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/logs/original/__unmapself.o.record) 的真实 clang 命令 rc=1；[__unmapself.o.stderr](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/logs/original/__unmapself.o.stderr) 首行即为 `CALL_IIII &abort`，随后是 `lowerToMCInst: unknown operand type`、`DADAOAsmPrinter.cpp:82`，stack dump 的函数为 `@__dadao_crtjmp_not_implemented`。
- 独立 fresh clang 的 [argv](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/logs/clang/unmapself-clang-object.argv) 与 [rc](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/logs/clang/unmapself-clang-object.rc) 为 rc=1；其 [stderr](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/logs/clang/unmapself-clang-object.stderr) 说明 frontend command 内部以 134 abort。`object=absent`，且 `-S` 的 [asm=absent](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/logs/clang/unmapself-clang-asm.output-status)，没有被误报为成功。
- frontend-only [IR argv](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/logs/clang/unmapself-clang-ir.argv) rc=0、stderr 为空、IR present。IR 保留 `CRTJMP` 调用、helper 定义和 `call void @llvm.trap(); unreachable`。原始 source 与 probe source 比对一致；original/fresh IR 的差异仅为 `ModuleID/source_filename` 路径。

## 最小失败触发器与 operand 证据

[crtjmp-trap.ll](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/probes/ir/crtjmp-trap.ll) 的有效完整运行 [argv](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/logs/llc/crtjmp-trap.argv) 为 rc=134，stdout 为空；[stderr](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/logs/llc/crtjmp-trap.stderr) 顺序为：

```text
CALL_IIII &abort, ... implicit-def dead $rd31
lowerToMCInst: unknown operand type
UNREACHABLE executed at .../DADAOAsmPrinter.cpp:82!
```

有效的 [finalize-isel argv](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/logs/llc/crtjmp-trap-finalize-isel.argv) rc=0，stderr 为空；[MIR](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/probes/mir/crtjmp-trap-finalize-isel.mir) 在 helper body 中保留：

```text
CALL_IIII &abort, CustomRegMask(...), implicit-def dead $rd31
```

成功的 ordinary external call 的 [MIR](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/probes/mir/call-external-finalize-isel.mir) 则是：

```text
CALL_IIII @abort, CustomRegMask(...), implicit-def dead $rd31
```

这里 `&abort` 是 MIR 对 external-symbol operand 的标准打印形态，`@abort` 是
global-address 形态；两者在相同 `CALL_IIII` opcode 上形成了最小差异。当前
[DADAOAsmPrinter.cpp:72-82](/home/holight/DADAO-0628/.work/llvm/llvm/lib/Target/DADAO/DADAOAsmPrinter.cpp:72)
只处理 register mask、MBB、register、immediate、global address、jump-table 和
constant-pool，default 直接 unreachable，没有 `MO_ExternalSymbol` case。结合
`DADAOISelLowering.cpp` 对 TargetExternalSymbol 的保留和 DAG selector 生成
`CALL_IIII`，把根因写成 external-symbol 到 MCOperand 的 AsmPrinter lowering 缺口是
有根据的。

## 成功对照复核

以下 rc、stderr、argv 和 asm 均来自对应的原始文件；成功项的 stderr/stdout 为空，且
asm 文件实际存在。

| 形状 | rc / stderr | argv 与 asm 结果 | MIR/边界 |
|---|---|---|---|
| ordinary external call | rc=0 / empty | [argv](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/logs/llc/call-external.argv)；[asm](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/probes/asm/call-external.s) 为 `call abort` | [MIR](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/probes/mir/call-external-finalize-isel.mir) 为 `CALL_IIII @abort` |
| ordinary internal call | rc=0 / empty | [argv](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/logs/llc/call-internal.argv)；[asm](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/probes/asm/call-internal.s) 为 `call callee_internal` | [MIR](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/probes/mir/call-internal-finalize-isel.mir) 为 `CALL_IIII @callee_internal` |
| direct branch | rc=0 / empty | [argv](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/logs/llc/branch-direct.argv)；[asm](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/probes/asm/branch-direct.s) 为 `jump .LBB0_1` | [MIR](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/probes/mir/branch-direct-finalize-isel.mir) 为 `JUMP_IIII %bb.1` |
| 无操作数 inline asm | rc=0 / empty | [argv](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/logs/llc/inline-asm.argv)；[asm](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/probes/asm/inline-asm.s) 原样输出 `trap 2, 0` | [MIR](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/probes/mir/inline-asm-finalize-isel.mir) 为 `INLINEASM` |
| indirect-call pseudo | rc=0 / empty | [argv](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/logs/llc/call-indirect-pseudo.argv)；[asm](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/probes/asm/call-indirect-pseudo.s) 为 `rd2rb` 后 `call rb5, rd0, 0` | finalize MIR 保留 `CALL_PSEUDO_INDIRECT`，可正常展开 |
| indirect-branch pseudo | rc=0 / empty | [argv](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/logs/llc/branch-indirect-pseudo.argv)；[asm](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/probes/asm/branch-indirect-pseudo.s) 为 `rd2rb` 后 `jump rb5, rd0, 0` | finalize MIR 保留 `JUMP_PSEUDO_INDIRECT`，可正常展开 |
| 带 `=r,r` 的 inline asm | rc=1 / `couldn't allocate output register for constraint 'r'` | [argv](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/logs/llc/inline-asm-operand.argv)；asm absent | 独立的 constraint allocation failure，不是本次 AsmPrinter crash |

因此没有把普通 call、普通 branch、inline asm 或 pseudo 的成功/失败对照误写成
通用 call/pseudo 问题。indirect pseudo 的实现也确实在成功 asm 中展开为
`rd2rb` + 真实 `CALL_RRII`/`JUMP_RRII`，不是 `&abort` 触发点。

## Findings

1. **非阻塞：两个 stage-control 命令无效。**
   [crtjmp-trap-stop-before.stderr](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/logs/llc/crtjmp-trap-stop-before.stderr)
   报告 `"asm-printer" pass is not registered`，rc=1；
   [crtjmp-trap-print-after-isel.stderr](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/logs/llc/crtjmp-trap-print-after-isel.stderr)
   报告 llc 不支持 `-mllvm`，rc=1。这两项不能作为阶段定位证据。worker 的有效阶段证据
   是完整运行的 AsmPrinter stack dump 和 rc=0 的 `-stop-after=finalize-isel` MIR，故不影响
   核心结论。

2. **非阻塞：`MO_ExternalSymbol` 没有以 enum 名称出现在 raw `/tmp` dump 中。**
   现有证据是 MIR 的 `&abort` 形态、对照的 `@abort` 形态，以及 target lowering 和
   AsmPrinter switch 的源码对应关系；这足以支持本 review 的判断，但后续正式 regression
   若需要更强的诊断可增加直接打印 `MachineOperand::MO_ExternalSymbol` 类型的 debug
   证据。当前不应把这一点表述成已通过独立 enum 转储直接观测到。

## 验收边界

本证据只证明 frontend IR 成功、backend crash stage、`CALL_IIII` operand 差异和相邻
CodeGen 形状；不证明修复后的 ABI、链接、归档、运行时或完整 libc 验收。worker 没有以
这些未执行的层级替代本 task 的 CodeGen 结论，也没有提出需要修改实现的 patch。

**最终状态：Accepted-with-findings。** Findings 均为证据表述/控制命令卫生问题，未推翻
“DADAO AsmPrinter 未处理 external-symbol operand，而非通用 call/pseudo 或 ABI 根因”的
独立审查结论。
