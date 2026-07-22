# ML-016q：修复 inline asm `r` register constraint mapping

**日期**：2026-07-21

**状态**：Audit-accepted-with-findings（ML-016 新 30-task run：17/30）

## 背景

ML-016o 已将 `explicit_bzero.o` 和最小 probes 的失败定位到 DADAO target 没有为
通用 inline-asm `r` 约束提供 register-class mapping；失败发生在 SelectionDAG
constraint allocation，早于 AsmPrinter。需要实现最小 target hook，并保持内存/无操作数
asm、AsmPrinter external-symbol 修复和其他簇不受影响。

## 目标与 ownership

worker 只负责 DADAO inline-asm constraint 的最小实现修复与回归：

1. 阅读当前 `DADAOISelLowering` 类、LLVM `getRegForInlineAsmConstraint` API 和
   DADAO GPRB/GPRD register classes；设计 `r`（及必要的 `f`/宽度限定）最小映射，
   不修改 calling convention、TableGen 或其他 target。
2. 只修改 `.work/source/llvm/llvm/lib/Target/DADAO/DADAOISelLowering.cpp`，除非
   编译 API 明确要求同一 ownership 的声明文件，若需额外文件必须说明。
3. 实际重编 LLVM/llc，运行 ML-016o 的 explicit_bzero、pointer/i64/u8-u64 `r` 输入/
   输出/inout、memory/clobber/无操作数成功对照，并保存修复前后 rc/stderr/asm/MIR。

## 约束

- 只写本 task 完成区、指定实现文件（必要时同一 hook 声明文件）和
  `docs/reviews/ML-016q-fix-inline-asm-register-constraint-20260721.md`；临时证据放
  `/tmp/ml-016q-fix-inline-asm-register-constraint-20260721/`。
- 不修改 AsmPrinter、musl、主 libc archive、contracts、vectors、issues、wiki、ML-014a
  或 QEMU/gem5；不访问或引用 `~/toolchain`、`~/knowledge-graph`。
- 不使用 `|| true`；必须确认使用新编译器产物。不要扩大修改到 RB31、tail-call、f64
  libcall、dynamic_stackalloc 或其他 backend 问题。
- worker 不是独自在仓库工作，不得回滚已有改动；完成后列出所有修改文件。

## 完成区

worker 已完成最小 inline-asm `r` register-class mapping，并用新重编的 DADAO
`llc` 完成 ML-016o 对照。实现文件只在
`.work/source/llvm/llvm/lib/Target/DADAO/DADAOISelLowering.cpp` 增加
`getRegForInlineAsmConstraint`：对非向量、整数标量且宽度不超过 64 bit 的 `r`
返回 `DADAO::GPRDRegClass`，其余约束交给 LLVM generic fallback。由于 hook API
只接收 `MVT`、没有原始 pointer provenance，pointer 值通过现有 GPRB↔GPRD
cross-bank copy 进入/离开 asm；没有新增 `f` 映射（GPRF 当前不可分配），没有改
calling convention、TableGen 或 AsmPrinter。

该 override 需要类声明，因此按 task 允许范围同时修改了同一 ownership 的
`DADAOISelLowering.h`；没有其他声明文件改动。`ninja -C .work/build/llvm llc`
和 `ninja -C .work/build/llvm clang` 均实际完成且 rc=0。

后修复结果与修复前证据：

- 修复前 ML-016o 的 `explicit_bzero`、pointer/i64 `r` input、i64 output/
  output+input/inout、u8/u16/u32/u64 的 input/output/inout 均为 O0/O3 backend
  rc=1；memory、clobber、无操作数均为 rc=0。原始证据仍在
  `/tmp/ml-016o-inline-asm-constraint-repro-20260721/`。
- 修复后新的 `llc` 对 ML-016o 已核对的 fresh `explicit_bzero.O0.ll`/
  `explicit_bzero.O3.ll` 均 rc=0，均生成 asm 和 finalize-isel MIR；pointer/i64
  `r` input、i64 output/output+input/inout、全部 u8/u16/u32/u64 三类形状在 O0/O3
  均 backend rc=0、MIR rc=0；memory/clobber/无操作数仍保持 O0/O3 rc=0。
- 修复后原始 argv、rc、stderr、asm、MIR 和 build/tool 记录位于
  `/tmp/ml-016q-fix-inline-asm-register-constraint-20260721/`。新 clang 直接从
  `explicit_bzero.c` 重新生成 IR 的尝试另有 host `/usr/include/string.h`
  缺失 `bits/libc-header-start.h` 阻塞，rc=1 和 raw stderr 已保留；没有用该失败
  结果或旧 asm 冒充修复后结果。

本 task 实际修改文件：

- `.work/source/llvm/llvm/lib/Target/DADAO/DADAOISelLowering.cpp`
- `.work/source/llvm/llvm/lib/Target/DADAO/DADAOISelLowering.h`（API 声明所需）
- `code-agent/tasks/ML-016q-fix-inline-asm-register-constraint.md`
- `docs/reviews/ML-016q-fix-inline-asm-register-constraint-20260721.md`

独立 reviewer Dewey the 2nd 的结论为 **Accepted-with-findings**，见
`docs/reviews/ML-016q-independent-review-20260721.md`。review 确认 hook 和新产物的
50/50 标准矩阵有效，但指出 explicit_bzero 本轮未能由新 clang 生成 IR（host header
缺失），只完成了新 llc 对既有 IR 的回归；同时没有 ABI/其他簇全量回归证据。因此本
任务只接受为局部 CodeGen 修复，下一任务补齐 explicit_bzero 新 clang→llc 链路。
