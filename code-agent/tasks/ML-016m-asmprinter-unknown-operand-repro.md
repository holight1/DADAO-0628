# ML-016m：DADAO AsmPrinter unknown operand 最小复现

**日期**：2026-07-21

**状态**：Audit-accepted-with-findings（ML-016 新 30-task run：13/30）

## 背景

ML-016g 将 `__unmapself.o` 单独归为 DADAO AsmPrinter `unknown operand type`，且该
对象 frontend rc=134。需要确认它是特定 `CRTJMP`/pseudo、inline asm operand、
branch/call 输出，还是 generic instruction emission 的问题；不能与 inline-asm
constraint 单例或 SelectionDAG assertion 合并。

## 目标与 ownership

worker 只做 `/tmp` 诊断：

1. 对 `__unmapself` 保存 source/IR、clang/llc argv/rc/stderr 和 backend 阶段；从
   raw diagnostic/machine dump 定位 unknown operand 的具体指令/operand 类型。
2. 生成最小 LLVM IR/asm/调用形状，覆盖普通 call/branch、inline asm、可能的 CRTJMP
   或 pseudo operand；至少保存一个成功的相邻形状和一个失败触发器。
3. 给出 AsmPrinter/MC 层 CodeGen regression 边界，不修改 LLVM/TableGen。

## 约束

- 只写本 task 完成区和 `docs/reviews/ML-016m-asmprinter-unknown-operand-repro-20260721.md`；
  probe/日志/脚本均放 `/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/`。
- 不修改 LLVM、musl、主 build/archive、QEMU/gem5、contracts、vectors、issues、wiki
  或 ML-014a。
- 不访问或引用 `~/toolchain`、`~/knowledge-graph`；不使用 `|| true`。
- 不把 frontend-only、单个 asm 生成或 link 成功当作完整 libc/runtime 验收。

## 完成区

worker 已完成 `__unmapself` source/IR/raw stderr 复核与 AsmPrinter 最小对照；全部 probes、原始 argv/rc/stdout/stderr、MIR 和成功形状 asm 位于
`/tmp/ml-016m-asmprinter-unknown-operand-repro-20260721/`。

- 原始 `__unmapself.c`、原始编译 record/stderr、frontend-only IR rc=0 与 fresh clang 证据均已保存。直接 clang backend driver rc=1（raw diagnostic 的 frontend abort code=134），失败函数为 `@__dadao_crtjmp_not_implemented`；首个 MachineInstr 为 `CALL_IIII &abort`，随后为 `lowerToMCInst: unknown operand type` 与 `DADAOAsmPrinter.cpp:82`，没有生成 asm。
- 最小失败触发器 `crtjmp-trap.ll` 的 `llc -mtriple=dadao -O0` 为 rc=134；`-stop-after=finalize-isel` 为 rc=0，MIR 保留 `CALL_IIII &abort`。完整运行的 raw stack 显示该已选指令经过寄存器分配后到达 AsmPrinter；失败发生在 `MO_ExternalSymbol` 到 `MCOperand` 的 lowering。
- 成功相邻形状：普通 external/internal call、direct branch、无操作数 inline asm、indirect-call pseudo、indirect-branch pseudo 均 llc rc=0 且保存 asm。带 `=r,r` 的 inline asm 另以 rc=1 报 `couldn't allocate output register for constraint 'r'`，保留为独立 inline-asm constraint 单例。
- 结论边界已写入 `docs/reviews/ML-016m-asmprinter-unknown-operand-repro-20260721.md`：这是 DADAO AsmPrinter `lowerToMCInst` 未覆盖 external-symbol operand 的单例；不是普通 call/branch、`CALL_PSEUDO_INDIRECT`/`JUMP_PSEUDO_INDIRECT`、inline-asm constraint 或 SelectionDAG assertion，也未修改 LLVM/TableGen、musl 或任何主构建/运行时面。

独立 reviewer Aquinas the 2nd 的结论为 **Accepted-with-findings**，见
`docs/reviews/ML-016m-independent-review-20260721.md`。review 确认 `CALL_IIII &abort`
与 `@abort` 对照的定位成立；两个无效 stage-control 命令及缺少字面量 enum dump 作为
非阻塞 evidence findings 保留，不升级为实现结论。
