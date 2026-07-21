# ML-016i：dynamic_stackalloc 最小复现

**日期**：2026-07-21

**状态**：Audit-accepted-with-findings（ML-016 新 30-task run：9/30）

## 背景

ML-016g 将 7 个 musl object 单独聚为 `Cannot select: dynamic_stackalloc`。需要区分
VLA、`alloca`、`llvm.stacksave/stackrestore`、对齐/动态大小和优化级别，确认最小
触发形状以及是否与 ABI/frame lowering 有关；不把该簇并入 f64/libcall 问题。

## 目标与 ownership

worker 只做 `/tmp` 诊断：

1. 生成覆盖固定 alloca、动态 alloca、VLA、动态对齐、stacksave/restore、返回值/指针
   逃逸和纯栈访问的最小 C/LLVM IR probes，按 O0/O3 保存 compile/llc rc、stderr、
   argv、IR/asm。
2. 最小化触发 `dynamic_stackalloc` 的 IR/source 形状，并记录至少一个成功对照；
   对 7 个原始失败对象做 representative source/IR 对照，避免只凭一个 probe 下结论。
3. 给出后续 backend 修复和 CodeGen 回归边界，但不修改 LLVM 或测试。

## 约束

- 只写本 task 完成区和 `docs/reviews/ML-016i-dynamic-stackalloc-minimal-repro-20260721.md`；
  probe/日志/脚本均放 `/tmp/ml-016i-dynamic-stackalloc-minimal-repro-20260721/`。
- 不修改 LLVM、musl、主 build/archive、QEMU/gem5、contracts、vectors、issues、wiki
  或 ML-014a。
- 不访问或引用 `~/toolchain`、`~/knowledge-graph`；不使用 `|| true`。
- frontend-only 成功、单个 llc 成功或 link 成功都不等于完整 libc/runtime 验收。

## 完成区

worker 已完成 dynamic_stackalloc 最小复现与 O0/O3 矩阵；全部 probes、脚本、原始 argv/rc/stdout/stderr、IR/asm 位于
`/tmp/ml-016i-dynamic-stackalloc-minimal-repro-20260721/`。

- 9 个 C 形状覆盖 fixed alloca、dynamic alloca、VLA、动态对齐、纯栈访问、返回/调用逃逸；另以显式 LLVM IR 覆盖 `stacksave/stackrestore`，并加入 `dynamic_void` 最小形状。
- C frontend IR：18 次 O0/O3，14 次 rc=0；两个 C `__builtin_stack_save/restore` 文件被 frontend 判为 unknown builtin，未作为 backend 证据。
- C 直接 clang asm：18 次，fixed alloca O0/O3 两次 rc=0；其余动态形状 rc=1。
- 显式 IR llc：20 次，fixed alloca O0/O3 两次 rc=0；`alloca i8, i64 %n` 即使随后 `ret void` 也在 O0/O3 触发 `Cannot select: dynamic_stackalloc`；独立 fixed-allocation + `stackrestore` IR 触发 `Cannot select: stackrestore`。
- 7 个 ML-016f representative（`dcngettext`、`res_msend`、`execl`、`execle`、`execlp`、`execvp`、`getcwd`）均完成 O0/O3 source/frontend IR/backend/llc 对照：frontend IR 14/14 成功，直接 clang 0/14 成功，llc 0/14 成功；ML-016f 原始 record/stderr 只读证据已复制到 task `/tmp` 目录。
- 最小失败形状、成功边界、动态 frame lowering 与 `stacksave/stackrestore` 的未闭合 ABI/frame 假设、以及后续 CodeGen 回归边界已记录在
  `docs/reviews/ML-016i-dynamic-stackalloc-minimal-repro-20260721.md`。

frontend-only、单个 llc 成功或 link 成功均未被解释为完整 libc/runtime 验收；未修改 LLVM、musl、主 build/archive、QEMU/gem5、contracts、vectors、issues、wiki 或 ML-014a。

独立 reviewer Fermat the 2nd 的结论为 **Accepted-with-findings**，见
`docs/reviews/ML-016i-independent-review-20260721.md`。review 确认动态 alloca 与
stackrestore 是两个独立 selector 失败面，并指出 `dcngettext-O3` 的失败实际是
Greedy Register Allocator 的未定义 `RB31`，不能归因于 dynamic_stackalloc。
