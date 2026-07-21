# ML-016o：inline asm register constraint 最小复现

**日期**：2026-07-21

**状态**：Audit-accepted-with-findings（ML-016 新 30-task run：15/30）

## 背景

ML-016g 将 `explicit_bzero.o` 单独归为 `inline asm: input register constraint allocation`。
ML-016m 的无操作数 inline asm 成功，但带 `=r,r` 的 probe 另有 constraint allocation
失败；需要隔离 input/output 约束、寄存器类、值类型、clobber 和优化级别。

## 目标与 ownership

worker 只做 `/tmp` 诊断：

1. 对 `explicit_bzero.c` 保存 source/IR、clang/llc argv/rc/stderr 和 inline asm 约束；
   定位失败是 input 还是 output，涉及哪一类值/寄存器。
2. 生成最小 inline asm C/LLVM IR probes，覆盖无操作数、input-only、output-only、
   `=r,r`、内存约束、clobber、整数宽度和 O0/O3；保留成功/失败原始证据。
3. 给出 inline asm constraint/target register-class 的 CodeGen regression 边界，
   不修改 LLVM/TableGen。

## 约束

- 只写本 task 完成区和 `docs/reviews/ML-016o-inline-asm-constraint-repro-20260721.md`；
  probe/日志/脚本均放 `/tmp/ml-016o-inline-asm-constraint-repro-20260721/`。
- 不修改 LLVM、musl、主 build/archive、QEMU/gem5、contracts、vectors、issues、wiki
  或 ML-014a。
- 不访问或引用 `~/toolchain`、`~/knowledge-graph`；不使用 `|| true`。
- 不把 frontend-only、单个 asm 成功或 link 成功当作完整 libc/runtime 验收。

## 完成区

（由 worker 填写；完成后由不同 subagent 独立 review）

worker 已完成 inline asm constraint source/IR/raw diagnostics 复核与 O0/O3 最小矩阵；所有 probes、脚本、原始 argv/rc/stdout/stderr、IR、成功 asm、finalize-isel MIR 和 `-debug-only=isel` 输出均位于 `/tmp/ml-016o-inline-asm-constraint-repro-20260721/`。

- `explicit_bzero.c` 原始 source、compile record、原始 stderr、历史 frontend-only IR 已复制并用 `cmp` 核对；fresh frontend `-S -emit-llvm` 在 O0/O3 均 rc=0，IR 保留 `"r,~{memory}"(ptr ...)`；fresh `llc -mtriple=dadao` O0/O3 均 rc=1，raw diagnostic 均为 `couldn't allocate input reg for constraint 'r'`。直接 clang backend O0/O3 也均 rc=1，保留 warning、source line、error 和无 asm 结果。
- 最小对照表明：无操作数 inline asm（含空 asm 与 `trap 2, 0`）、`m`/`=m`/`+m` 内存约束、`memory`/`cc`/组合 clobber 在 O0/O3 均 rc=0；独立 `r` input、`=r` output、`=r,r`、`+r` 在 O0/O3 均 rc=1。指针 input 与 i64 scalar input 均分别复现 input-reg failure；u8/u16/u32/u64 的 input/output/inout `r` 矩阵未显示宽度特异性，均在 constraint allocation 阶段失败。
- finalize-isel/debug 证据显示 input-pointer 入口为 `gprb`、i64 scalar 入口为 `gprd`，但两者的 `r` 均未获得可用寄存器类；内存形状在 MIR 中保留 `mem:m` 并完成 asm。只读 target 检查显示 DADAO lowering 注册 i64 `GPRD`，但没有 `getRegForInlineAsmConstraint` 的 `r` 映射；因此回归边界是 target inline-asm register-constraint mapping，尚未进入 register allocation/AsmPrinter。
- 已明确与 ML-016m AsmPrinter 单例的边界：本 task 的 `r` 失败发生在 SelectionDAG inline-asm constraint allocation；无操作数 asm 能到达并通过 AsmPrinter；ML-016m 则是已选择的 `CALL_IIII &abort` external-symbol operand 在 AsmPrinter lowering 失败。两者不合并，本次未修改 LLVM/TableGen、musl、主 build/archive、QEMU/gem5 或其他受保护面。

review 结论与原始证据索引见 `docs/reviews/ML-016o-inline-asm-constraint-repro-20260721.md`。

独立 reviewer Nietzsche the 2nd 的结论为 **Accepted-with-findings**，见
`docs/reviews/ML-016o-independent-review-20260721.md`。review 确认失败发生在
SelectionDAG inline-asm `r` constraint mapping、早于 AsmPrinter；非阻塞 finding 是
dated task 文件缺失，以及既有 `matrix-current.tsv` 索引表述不精确。
