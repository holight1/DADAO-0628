# ML-016p 独立 implementation review

日期：2026-07-21（Asia/Shanghai）

## 结论

**Accepted**

本 review 仅核验 ML-016p 的实现范围、构建 provenance 和 CodeGen/AsmPrinter 回归；不扩展到链接、运行时或 libc 验收。

## 实现 diff

`/home/holight/DADAO-0628/.work/source/llvm/llvm/lib/Target/DADAO/DADAOAsmPrinter.cpp` 当前内容与构建实际引用的 `.work/llvm/llvm/lib/Target/DADAO/DADAOAsmPrinter.cpp` 为同一 inode、同一 SHA-256（`2c942f1a978bf9bfcfbfc8d86aeeaab14242f4d0738d4cee5bcf136fd3d0c7b2`）。独立执行的 `git diff --check` rc=0；保存的精确 patch 为：

`/tmp/ml-016p-fix-asmprinter-external-symbol-20260721/diff/DADAOAsmPrinter.cpp.patch`

语义 diff 只有一个新增 case：

```cpp
case MachineOperand::MO_ExternalSymbol:
  MCOp = MCOperand::createExpr(MCSymbolRefExpr::create(
      GetExternalSymbolSymbol(MO.getSymbolName()), OutContext));
  break;
```

另有一个文件末尾换行变化，无语义影响。新增 mapping 只匹配 `MO_ExternalSymbol`，只使用 `getSymbolName()`；没有改变 `MO_GlobalAddress`、offset、pseudo、ABI 或 inline-asm constraint。LLVM 的 `MachineOperand::setSymbolName` 明确将该类型 offset 设为 0，API 头文件也提供了 `GetExternalSymbolSymbol`。

## 构建与产物 provenance

证据目录：`/tmp/ml-016p-fix-asmprinter-external-symbol-20260721/`。

```text
ninja -C /home/holight/DADAO-0628/.work/build/llvm bin/llc
rc=0
[1/3] Building .../LLVMDADAOCodeGen.dir/DADAOAsmPrinter.cpp.o
[2/3] Linking .../libLLVMDADAOCodeGen.a
[3/3] Linking .../bin/llc
```

构建 stderr 为空。实际 compile command 的输入是 `.work/llvm/llvm/lib/Target/DADAO/DADAOAsmPrinter.cpp`，输出是 `LLVMDADAOCodeGen` object；随后确实重建了 archive 和 `bin/llc`。source mtime 为 17:29:50，object 为 17:31:24，`llc` 为 17:31:44；pre probe 在 17:31:09，post probe 在 17:32:05。因此 pre 使用旧产物、post 使用重编后产物，未发现把旧产物冒充修复后结果的证据。

所有 probe argv 均显式使用 `-mtriple=dadao`；pre/post `llc --version` 均为 assertions-enabled LLVM 22.1.8 且注册 `dadao` target。未发现错误 target 或未重编证据。post `bin/llc` SHA-256 为 `7197c3a0d5ce2f7750c820c5655739b5d428f16f121a5e73733387a7d1adf5f7`。

## 修复前后结果

原始 rc、stderr、asm/MIR 位于 evidence 目录的 `pre/` 和 `post/`；汇总如下：

| probe | pre | post | 核验结果 |
|---|---:|---:|---|
| `crtjmp-trap` | 134，无 asm | 0，有 asm | `CALL_IIII &abort` 输出为 `call abort` |
| ordinary external call | 0，有 asm | 0，有 asm | `call abort` 保持成功 |
| ordinary internal call | 0，有 asm | 0，有 asm | global-address call 保持成功 |
| direct branch | 0，有 asm | 0，有 asm | `jump .LBB0_1` 保持成功 |
| indirect-call pseudo | 0，有 asm | 0，有 asm | `call rb5, rd0, 0` 保持成功 |
| indirect-branch pseudo | 0，有 asm | 0，有 asm | `jump rb5, rd0, 0` 保持成功 |
| 无操作数 inline asm | 0，有 asm | 0，有 asm | `trap 2, 0` 保持成功 |
| inline asm `=r,r` | 1，无 asm | 1，无 asm | 保持独立失败 |

pre/post 输入 IR hash 一致；`finalize-isel` 的 `crtjmp-trap` MIR 除 pre/post 文件路径外一致，均保留 `CALL_IIII &abort`。这支持回归差异发生在 MachineInstr 到 MCInst 的 lowering，而不是选择阶段。`=r,r` constraint 两侧 stderr SHA-256 均为 `8772e092040053fb960e9e9713fa5701b4846e20bd5c357ef642887dc2df2394`，内容均为 `couldn't allocate output register for constraint 'r'`，故未被本修复掩盖或误归因。

## 工作区边界

reviewer 未修改实现文件、测试、规范或其他任务文件；仅新增本独立 review 文档。既有未提交改动保持原样，未执行回滚。
