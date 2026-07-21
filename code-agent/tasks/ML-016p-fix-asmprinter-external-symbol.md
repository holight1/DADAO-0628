# ML-016p：修复 AsmPrinter external-symbol operand

**日期**：2026-07-21

**状态**：Accepted（ML-016 新 30-task run：16/30）

## 背景

ML-016m 已将 `__unmapself.o` 的 crash 定位为 DADAO AsmPrinter 在
`lowerToMCInst` 中未处理 `MO_ExternalSymbol`。这是当前 184 个失败中证据最明确、
边界最小的实现修复候选。

## 目标与 ownership

worker 只负责 DADAO AsmPrinter 的最小实现修复与回归：

1. 阅读当前 `DADAOAsmPrinter.cpp` 的 operand lowering、MC symbol API 和现有
   ordinary external/global call 处理，设计最小 `MO_ExternalSymbol` 到 MCOperand
   的映射；不要改 calling convention、TableGen、SelectionDAG 或其他 target。
2. 只修改 `.work/source/llvm/llvm/lib/Target/DADAO/DADAOAsmPrinter.cpp`（如确有
   必要的同文件测试辅助才说明；默认不动其他实现文件），记录 patch diff。
3. 在隔离或当前既有构建流程中重编相关 LLVM target，运行 ML-016m 的
   `crtjmp-trap.ll` 失败 probe 及 ordinary call/branch/indirect-pseudo/inline-asm
   成功对照；保存原始 build/test rc、stderr、asm/MIR。若全量重编不可行，说明确切
   阻塞层级，不把旧产物结果当修复后结果。

## 约束

- 只写本 task 完成区、指定实现文件和
  `docs/reviews/ML-016p-fix-asmprinter-external-symbol-20260721.md`；临时证据放
  `/tmp/ml-016p-fix-asmprinter-external-symbol-20260721/`。
- 不修改 musl、主 libc archive、contracts、vectors、issues、wiki、ML-014a 或
  QEMU/gem5；不访问或引用 `~/toolchain`、`~/knowledge-graph`。
- 不使用 `|| true`；保留修复前/后的原始退出码和 stderr。不要扩大修改到 inline asm
  constraint、RB31、tail-call 或 f64/libcall 问题。
- worker 不是独自在仓库工作，不得回滚已有改动；完成后明确列出所有修改文件。

## 完成区

worker 已完成最小 `MO_ExternalSymbol` lowering、可用 LLVM 重编和 ML-016m 对照验证；实现 ownership 仅为
`.work/source/llvm/llvm/lib/Target/DADAO/DADAOAsmPrinter.cpp`。独立 review 待后续 subagent 执行。

- 实现：在 `DADAOAsmPrinter::lowerToMCInst` 增加 `MachineOperand::MO_ExternalSymbol` case，使用
  `GetExternalSymbolSymbol(MO.getSymbolName())` 创建 `MCSymbolRefExpr`，再包装为 `MCOperand::createExpr`。
  `MO_ExternalSymbol` 的 offset API 规定恒为 0；没有改动 global-address offset、selector、pseudo、ABI 或其他 target 文件。
- 构建：既有 CMake/Ninja DADAO-only build 的
  `ninja -C /home/holight/DADAO-0628/.work/build/llvm bin/llc` rc=0；实际重编
  `DADAOAsmPrinter.cpp`、`libLLVMDADAOCodeGen.a` 和 `bin/llc`。原始命令、stdout、stderr、rc 位于
  `/tmp/ml-016p-fix-asmprinter-external-symbol-20260721/build/`。
- 修复前/后 llc rc：`crtjmp-trap` `134 -> 0`（无 asm -> 生成 asm，修复后 helper 输出 `call abort`）；
  ordinary external/internal call、direct branch、indirect-call pseudo、indirect-branch pseudo 和无操作数
  inline asm 均 `0 -> 0`；带 `=r,r` constraint 的 inline asm 保持 `1 -> 1`，仍是独立的寄存器分配问题。
  两侧 `-stop-after=finalize-isel` 对照均 rc=0；完整 argv、原始 stdout/stderr、asm 和 MIR 均位于同一临时目录的
  `pre/` 与 `post/` 下。
- 质量检查：`git diff --check` rc=0；精确 source diff 保存于
  `/tmp/ml-016p-fix-asmprinter-external-symbol-20260721/diff/DADAOAsmPrinter.cpp.patch`。
- 本次仓库写入文件：本 task 完成区、`.work/source/llvm/llvm/lib/Target/DADAO/DADAOAsmPrinter.cpp`、
  `docs/reviews/ML-016p-fix-asmprinter-external-symbol-20260721.md`。未回滚或修改其他 worker 的已有改动。

独立 reviewer Rawls the 2nd 的结论为 **Accepted**，见
`docs/reviews/ML-016p-independent-review-20260721.md`。review 确认实际重编了
AsmPrinter、DADAO CodeGen archive 和 `llc`，修复前后 probe 使用正确产物；该修复只
处理 `MO_ExternalSymbol`，没有掩盖 inline-asm constraint 失败。
