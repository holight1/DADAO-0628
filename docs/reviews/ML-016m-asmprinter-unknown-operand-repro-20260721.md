# ML-016m AsmPrinter unknown operand 最小复现 review

日期：2026-07-21（Asia/Shanghai）  
状态：worker complete；仅诊断，未修改 LLVM/TableGen、musl、主 build/archive、QEMU/gem5 或测试。

## 结论

`__unmapself.o` 的单例已缩到 `llvm.trap`/CRTJMP 占位路径：backend 在
`@__dadao_crtjmp_not_implemented` 中形成 `CALL_IIII &abort`，DADAO
AsmPrinter 的 `lowerToMCInst` 遇到未覆盖的 external-symbol MachineOperand，命中
`lowerToMCInst: unknown operand type` 和 `DADAOAsmPrinter.cpp:82`。

这不是普通 direct call、普通 branch、inline asm constraint、SelectionDAG assertion，
也不是 `CALL_PSEUDO_INDIRECT` 或 `JUMP_PSEUDO_INDIRECT` 的 pseudo 展开问题。失败点在
AsmPrinter 构造 `MCInst` 之前，尚未进入 MC encoder/parser；本 task 没有提出或实施修复。

## `__unmapself` 原始证据

原始 source、record、stderr 和 frontend-only IR 已原样复制到 task 临时目录：

- source：[__unmapself.c.original](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/probes/source/__unmapself.c.original)
- 原始编译 record：[__unmapself.o.record](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/logs/original/__unmapself.o.record)
- 原始 backend stderr：[__unmapself.o.stderr](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/logs/original/__unmapself.o.stderr)
- 原始 frontend IR：[__unmapself.original.ll](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/probes/ir/__unmapself.original.ll)
- fresh frontend IR：[__unmapself.fresh.ll](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/probes/ir/__unmapself.fresh.ll)

原始 stderr 的关键顺序为：

```text
CALL_IIII &abort, <regmask ...>, <regmask ...>, implicit-def dead $rd31
lowerToMCInst: unknown operand type
UNREACHABLE executed at .../DADAOAsmPrinter.cpp:82!
...
Running pass 'DADAO Assembly Printer' on function '@__dadao_crtjmp_not_implemented'
```

fresh source backend 的 driver rc=1；stderr 内的 clang frontend command failed exit code
为 134，目标 `.o` 与 `.s` 均不存在。frontend-only `-S -emit-llvm` 为 rc=0，IR 明确保留：

```llvm
call void @__dadao_crtjmp_not_implemented(ptr noundef @do_unmap, ptr noundef %5)
...
define internal void @__dadao_crtjmp_not_implemented(ptr noundef %pc, ptr noundef %sp)
...
call void @llvm.trap()
unreachable
```

因此 frontend 生成 IR 成功，但这不被解释为 backend、archive 或 libc/runtime 验收。

## 最小矩阵

所有 llc 命令均保存逐命令 argv、rc、原始 stdout/stderr；成功项保存 asm，machine
对照另保存 `-stop-after=finalize-isel` 的 MIR。证据根目录为
[/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/)。

| 形状 | llc rc | finalize-isel MIR | 关键结果 |
|---|---:|---:|---|
| `crtjmp-trap.ll` | 134 | 0 | `CALL_IIII &abort`，AsmPrinter unknown operand；失败触发器 |
| ordinary external call `@abort` | 0 | 0 | `CALL_IIII @abort`，asm 为 `call abort` |
| ordinary internal call | 0 | 0 | `CALL_IIII @callee_internal`，asm 成功 |
| direct branch | 0 | 0 | `JUMP_IIII %bb.1`，asm 为 `jump .LBB0_1` |
| 无操作数 inline asm | 0 | 0 | `INLINEASM`，asm 原样输出 `trap 2, 0` |
| indirect-call pseudo | 0 | 0 | `CALL_PSEUDO_INDIRECT` 展开为 `rd2rb` + `CALL_RRII` |
| indirect-branch pseudo | 0 | 0 | `JUMP_PSEUDO_INDIRECT` 展开为 `rd2rb` + `JUMP_RRII` |
| inline asm `=r,r` operand | 1 | — | `couldn't allocate output register for constraint 'r'`，独立簇 |

probe IR：[probes/ir](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/probes/ir)；
MIR：[probes/mir](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/probes/mir)；
成功 asm：[probes/asm](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/probes/asm)；
llc raw logs：[logs/llc](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/logs/llc)。

失败触发器的 machine dump 中，`crtjmp-trap.ll` 的 helper 函数只有：

```text
CALL_IIII &abort, CustomRegMask(...), implicit-def dead $rd31
```

而成功的 ordinary external call 是：

```text
CALL_IIII @abort, CustomRegMask(...), implicit-def dead $rd31
```

这里 `&abort` 与 `@abort` 是决定性差别：前者是 external-symbol operand，后者是
global-address operand。对应完整 dump 为
[crtjmp-trap-finalize-isel.mir](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/probes/mir/crtjmp-trap-finalize-isel.mir)
和
[call-external-finalize-isel.mir](/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/probes/mir/call-external-finalize-isel.mir)。

## AsmPrinter 层边界

只读检查当前实现的 `DADAOAsmPrinter::lowerToMCInst`：

- [`DADAOAsmPrinter.cpp:72-82`](/home/holight/DADAO-0628/.work/llvm/llvm/lib/Target/DADAO/DADAOAsmPrinter.cpp:72) 遍历 MachineOperand；显式处理 register mask、MBB、register、immediate、global address、jump-table 和 constant-pool，但没有 `MO_ExternalSymbol` case，default 在第 82 行 `llvm_unreachable`。
- [`DADAOISelDAGToDAG.cpp:119-142`](/home/holight/DADAO-0628/.work/llvm/llvm/lib/Target/DADAO/DADAOISelDAGToDAG.cpp:119) 将 direct callee 形成 `CALL_IIII`，indirect callee 形成 `CALL_PSEUDO_INDIRECT`；本矩阵证明 indirect pseudo 能正常到达 asm。
- [`DADAOInstrInfo.cpp:175-208`](/home/holight/DADAO-0628/.work/llvm/llvm/lib/Target/DADAO/DADAOInstrInfo.cpp:175) 将 call/branch indirect pseudo 展开成跨 bank bridge 加真实 `CALL_RRII`/`JUMP_RRII`；它们不是本次 `&abort` 失败点。

所以当前 regression 边界应落在：**一个已选择、已分配、待打印的 `CALL_IIII`，其
callee 使用 `MO_ExternalSymbol`**。需要后续修复时，应先决定该 operand 应如何形成
合法 MC symbol expression，再增加 AsmPrinter/MC CodeGen regression；本 task 不修改
实现文件，也不把它扩大成普通 call 或全部 pseudo 的问题。

## 与其他 ML-016 单例的分离

- `inline-asm-operand.ll` 的 rc=1 是 constraint allocation failure，发生在 AsmPrinter
  之前；无操作数 inline asm rc=0，故不能与 `__unmapself` 的 external-symbol lowering
  合并。
- 本 task 没有 `Cannot select`、`SelectionDAG` illegal-result、MachineVerifier undefined
  register 或普通 call/branch failure 诊断；不能与这些簇共享修复名义。
- CRTJMP 在当前 source 中通过 `llvm.trap` 占位实现暴露该问题；触发的机器指令是
  `CALL_IIII &abort`，不是一个可单独归并的 CRTJMP target pseudo。

## 验收边界与保护范围

本交付只证明 frontend IR、backend crash stage、最小 MachineOperand 形状和相邻成功
形状；不证明修复后的 ABI、链接、`libc.a`、runtime、QEMU/gem5 或完整 musl 验收。
没有修改 LLVM/TableGen、musl、主 build/archive、QEMU/gem5、contracts、vectors、issues、
wiki 或 ML-014a；仓库内只写入本 task 完成区与本 review 文档。
