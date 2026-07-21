# ML-016p：AsmPrinter external-symbol 修复 review

日期：2026-07-21（Asia/Shanghai）  
状态：worker complete；独立 review 待执行

## 结论

ML-016m 定位的 DADAO AsmPrinter `MO_ExternalSymbol` lowering 缺口已用最小实现修复。
重编后的真实 `llc` 产物可处理 `CALL_IIII &abort`，`crtjmp-trap` 从 AsmPrinter abort
恢复为 rc=0，并生成 `call abort`。ordinary call/branch、indirect pseudo 和无操作数
inline asm 的成功边界保持不变；带寄存器约束的 inline asm 仍保留其独立失败。

## 实现与 MC API 依据

修改仅位于
`.work/source/llvm/llvm/lib/Target/DADAO/DADAOAsmPrinter.cpp` 的
`DADAOAsmPrinter::lowerToMCInst`：

```cpp
case MachineOperand::MO_ExternalSymbol:
  MCOp = MCOperand::createExpr(MCSymbolRefExpr::create(
      GetExternalSymbolSymbol(MO.getSymbolName()), OutContext));
  break;
```

`MachineOperand::getSymbolName()` 是 `MO_ExternalSymbol` 的专用 accessor；
`AsmPrinter::GetExternalSymbolSymbol()` 按当前 target `DataLayout` 处理外部符号名称，
然后以 `MCSymbolRefExpr` 形成 MC expression。`MachineOperand` API 对此类型的
`getOffset()` 恒返回 0，所以没有引入与 global-address addend 无关的额外表达式逻辑。
现有 `MO_GlobalAddress` offset 修复保持原样。

精确 source diff 位于
`/tmp/ml-016p-fix-asmprinter-external-symbol-20260721/diff/DADAOAsmPrinter.cpp.patch`；
`git diff --check` rc=0。

## 真实构建

执行的命令为：

```text
ninja -C /home/holight/DADAO-0628/.work/build/llvm bin/llc
```

构建 rc=0，Ninja 实际完成：

```text
[1/3] Building CXX object lib/Target/DADAO/CMakeFiles/LLVMDADAOCodeGen.dir/DADAOAsmPrinter.cpp.o
[2/3] Linking CXX static library lib/libLLVMDADAOCodeGen.a
[3/3] Linking CXX executable bin/llc
```

构建命令、原始 stdout/stderr/rc 位于
`/tmp/ml-016p-fix-asmprinter-external-symbol-20260721/build/`；修复后 `llc --version`
确认是 assertions-enabled LLVM 22.1.8，且注册 `dadao` target。

## ML-016m 修复前/后对照

修复前使用重编前仍在 build 中的旧 `llc`，修复后使用上述 Ninja 新链接的 `bin/llc`。
两侧命令均为 `llc -mtriple=dadao -O0 -filetype=asm ...`；所有原始 argv、rc、stdout、
stderr、asm 和 `-stop-after=finalize-isel` MIR 均保存于临时证据目录的 `pre/`、`post/`。

| 形状 | 修复前 rc / asm | 修复后 rc / asm | 结果边界 |
|---|---:|---:|---|
| `crtjmp-trap.ll` | 134 / absent | 0 / present | `CALL_IIII &abort` 可打印为 `call abort` |
| ordinary external call | 0 / present | 0 / present | `CALL_IIII @abort` 保持成功 |
| ordinary internal call | 0 / present | 0 / present | global-address call 保持成功 |
| direct branch | 0 / present | 0 / present | `JUMP_IIII` 保持成功 |
| indirect-call pseudo | 0 / present | 0 / present | `CALL_PSEUDO_INDIRECT` 正常展开 |
| indirect-branch pseudo | 0 / present | 0 / present | `JUMP_PSEUDO_INDIRECT` 正常展开 |
| 无操作数 inline asm | 0 / present | 0 / present | inline asm 原样输出保持成功 |
| inline asm `=r,r` operand | 1 / absent | 1 / absent | 独立 constraint allocation failure |

修复前 `crtjmp-trap` 的 stderr 保留 `lowerToMCInst: unknown operand type` 和
`DADAOAsmPrinter.cpp:82`；修复后该 case stderr 为空。两侧 finalize-isel 对照全部
rc=0，说明选择阶段的 `CALL_IIII &abort` 没有变化，变化仅发生在 MachineInstr 到
MCInst 的 lowering。修复后 MIR 和 asm 证据位于：

- `post/probes/mir/crtjmp-trap-finalize-isel.mir`：保留 `CALL_IIII &abort`；
- `post/probes/asm/crtjmp-trap.s`：helper 输出 `call abort`；
- `post/probes/asm/call-external.s`、`call-indirect-pseudo.s`、
  `branch-indirect-pseudo.s`、`inline-asm.s`：成功相邻形状。

完整 rc 汇总位于
`/tmp/ml-016p-fix-asmprinter-external-symbol-20260721/rc-summary.txt`。

## 范围与未宣称事项

本交付只覆盖 AsmPrinter 的 external-symbol 到 MCOperand 映射和 CodeGen 级回归；没有
扩大到 inline-asm constraint、RB31、tail-call、f64/libcall、SelectionDAG、TableGen、
musl、archive、链接、QEMU/gem5 或完整 libc/runtime 验收。仓库内只修改任务指定的
完成区、该实现文件和本 review 文档；其他 worker 改动保持不动。
