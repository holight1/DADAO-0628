# ML-016j：RB31 pointer-return / CALL defs 最小复现

**日期**：2026-07-21

**状态**：Audit-accepted-with-findings（ML-016 新 30-task run：10/30）

## 背景

ML-016g/ML-016i 发现 16 个对象在 register allocation/verifier 阶段出现 undefined
physical register `$rb31`。只读审计显示 pointer return 为 `RB31`、CALL defs 为
`RD31` 是候选不一致，但尚未证明它是实际触发机制。本任务只建立 direct/indirect
pointer-return、integer-return、caller use、nested call 的最小矩阵。

## 目标与 ownership

worker 只做 `/tmp` 诊断：

1. 生成 C/LLVM IR probes 覆盖 pointer-return direct call、indirect call、pointer
   argument/return、integer-return 对照、返回值立即使用/保存跨 call、nested call；
   按 O0/O3 保存 clang/llc rc、stderr、argv、IR/asm。
2. 对 `posix_memalign`、`memmem` 等失败代表做 source/IR/backend 对照，确认是否
   同一 verifier 形状；分别检查 generated machine code 中 RB31 定义/使用与 CALL
   defs，但不修改 TableGen 或 calling convention。
3. 给出下一步最小实现/CodeGen regression 边界，明确哪些只是候选，禁止把 verifier
   现象直接等同于 `RB31` 定义错误。

## 约束

- 只写本 task 完成区和 `docs/reviews/ML-016j-rb31-pointer-return-repro-20260721.md`；
  probe/日志/脚本均放 `/tmp/ml-016j-rb31-pointer-return-repro-20260721/`。
- 不修改 LLVM、musl、主 build/archive、QEMU/gem5、contracts、vectors、issues、wiki
  或 ML-014a。
- 不访问或引用 `~/toolchain`、`~/knowledge-graph`；不使用 `|| true`。
- 不把单个 verifier 成功、frontend IR 成功或 asm 生成当作完整 libc/runtime 验收。

## 完成区

### worker 交付（2026-07-21）

状态：诊断完成，待独立 review；RB31 仍为候选机制，不是本任务已证实的根因。

本轮仅在 [`/tmp/ml-016j-rb31-pointer-return-repro-20260721/`](/tmp/ml-016j-rb31-pointer-return-repro-20260721/) 生成 probes、脚本和原始日志；未修改 LLVM/TableGen、musl、主 build/archive、QEMU/gem5、contracts、vectors、issues、wiki 或 ML-014a，也未访问或引用 `~/toolchain`、`~/knowledge-graph`。

- 最小 C probe 覆盖 direct/indirect/nested pointer-return、pointer argument/return、pointer 返回值立即使用、pointer 返回值保存跨 call、对应 direct/indirect/nested integer-return，以及 pointer/integer identity 对照；每个 probe 都生成 O0/O3 frontend IR，并分别执行 clang 直接后端和 llc。
- 以失败 representative 使用的 `-fno-optimize-sibling-calls` 运行主矩阵：frontend 30/30、clang 30/30、llc 30/30 均 `rc=0`。因此最小 direct/indirect/nested pointer-return 和 integer-return 本身没有复现 undefined `$rb31` verifier。
- 另保留默认 O3 sibling-tail-call 变体：frontend 30/30 成功，clang 21/30 成功、9/30 `rc=1`，llc 21/30 成功、9/30 `rc=134`。失败项包括 direct/indirect/nested pointer-return，也包括 direct/indirect/nested integer-return；stderr 的共同首诊断是 `LowerCallTo` 的 `LowerCall emitted a return value for a tail call` assertion。这是独立的 tail-call lowering 候选，不能解释为 RB31 专属现象。
- 只读复制真实 musl `posix_memalign.c`、`memmem.c` 做 source/IR/backend 对照：O0 两个 representative 的 frontend/clang/llc 均成功；O3 frontend IR 均 `rc=0`，clang 均 `rc=1`，llc 均 `rc=134`。两条 O3 backend stderr 都保留 Greedy Register Allocator 的 `Using an undefined physical register` / `$rb31` 诊断和完整 machine-code dump。
- `posix_memalign` O3 raw machine code 有 2 条 `CALL_IIII`，均为 `implicit-def dead $rd31`，随后分别出现 `%9:gprd = COPY $rb31` 与 `%11:gprd = COPY killed $rb31`，2 个 verifier error。`memmem` O3 有 5 条 CALL、5 条 `implicit-def dead $rd31`，并在多条 call-result 路径 COPY `$rb31`，共 5 个 verifier error。该形状与“pointer return 为 RB31、CALL defs 为 RD31”的候选不一致相符，但最小 call-return probe 未复现它，尚不足以证明共同因果。
- 没有把 frontend IR 成功、单个 llc 成功、asm 生成或 machine-code dump 当作 libc/runtime 验收；没有执行 link、主 archive、QEMU/gem5 或完整 musl 验收。

完整结论、矩阵统计、候选边界、下一步 CodeGen regression 边界和证据索引见 [`docs/reviews/ML-016j-rb31-pointer-return-repro-20260721.md`](/home/holight/DADAO-0628/docs/reviews/ML-016j-rb31-pointer-return-repro-20260721.md)。

独立 reviewer McClintock the 2nd 的结论为 **Accepted-with-findings**，见
`docs/reviews/ML-016j-independent-review-20260721.md`。review 确认 no-tail 最小
矩阵与真实 representative 的 verifier 形状不同，并要求保留 O3 无 `.s` 可扫描、
CALL-def 文本不等于 calling-convention 因果的边界。
