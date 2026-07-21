# ML-016h：f64/libcall unsupported-operation 最小复现

**日期**：2026-07-21

**状态**：Audit-accepted-with-findings（ML-016 新 30-task run：8/30）

## 背景

ML-016g 发现 157 个 object 共享 `unsupported library call operation`，但该签名
不能证明它们只有一个具体 lowering 根因。需要用最小 C/LLVM IR 输入分别隔离 f64
算术、转换、`llvm.fmuladd`、数学库调用和整数/指针对照，确认真正触发失败的最小
操作及优化级别。

## 目标与 ownership

worker 只做 `/tmp` 诊断：

1. 使用当前 DADAO clang/llc/lld 配置生成一组最小 C 或 LLVM IR probes，至少覆盖
   `double` add/mul/div、f64↔整数转换、`llvm.fmuladd.*`、一个 libm 调用、纯整数
   对照；按 `-O0`、`-O3` 分别记录 compile/llc rc、stderr、argv 和 IR/asm。
2. 对触发同一错误的 probe，进一步缩小到一个 LLVM operation 或 builtin；对不触发
   的 probe 也保存成功证据，避免只报告失败样例。
3. 明确 157 簇中哪些 source family 可由该最小触发器解释，哪些仍需单独调查；给出
   后续最小 backend 修复/测试边界，但不修改 LLVM 或测试。

## 约束

- 只写本 task 完成区和 `docs/reviews/ML-016h-f64-libcall-minimal-repro-20260721.md`；
  全部 probe/日志/脚本放 `/tmp/ml-016h-f64-libcall-minimal-repro-20260721/`。
- 不修改 LLVM、musl、主 build/archive、QEMU/gem5、contracts、vectors、issues、
  wiki 或 ML-014a。
- 不访问或引用 `~/toolchain`、`~/knowledge-graph`；不使用 `|| true`。
- 不把 frontend-only IR 成功、单个 backend 成功或 link 成功当作完整 libc/runtime
  验收。

## 完成区

### worker 交付（2026-07-21）

状态：诊断完成，待独立 review；不预置 Accepted。

本轮严格只在 `/tmp/ml-016h-f64-libcall-minimal-repro-20260721/` 生成 probes、
脚本和日志；未访问或引用受保护的外部工具链/知识图目录，未修改 LLVM、musl、主
build/archive、QEMU/gem5、contracts、vectors、issues、wiki 或 ML-014a。

共 17 个 LLVM IR probes，逐个运行 O0/O3 的 clang codegen 与 llc：34 行矩阵中，
13 行 clang/llc 双成功，18 行两者均失败，3 行是 clang O3 独有的 f64-return call
assertion（llc 成功）。逐项 argv、compile/llc rc、stderr、输入 IR、成功 asm 和汇总
见 [/tmp/ml-016h-f64-libcall-minimal-repro-20260721/results/summary.tsv](/tmp/ml-016h-f64-libcall-minimal-repro-20260721/results/summary.tsv)。

最小 generic 失败边界为单个 `fadd`/`fsub`/`fmul`/`fdiv`、f64↔i64、f64↔f32 或
`llvm.fmuladd.f64`；O0/O3 均进入 DADAO DAG instruction selection 的
`TargetLowering::makeLibCall` 并报告 `unsupported library call operation`。f64
identity/constant、纯整数 add、指针 identity 作为成功对照均为 O0/O3 0/0。外部
`sin`/显式 `__adddf3` 的 O0 call 成功，普通 O3 f64-return call 触发独立 assertion；
volatile store/load 阻断 tail-call 后 O3 成功。因此 soft-float generated-libcall
缺口是高可信候选，但仍未解释 157 个 object 各自的精确 RTLIB/DAG operation；O3
call/tail-call assertion 是另一个候选，不能并入该簇。

157 簇的 8 个 source family（math 127、complex 22、internal 1、stdio 2、stdlib
2、legacy 1、prng 1、time 1）均有 representative IR 与本轮 operation 相交：
`strtod`/`vfscanf` 的 fptrunc、`drand48` 的 fsub 也已分别补 probe。但这些是
family 级候选覆盖，不是 157/157 的逐对象根因证明；多 operation 组合、具体 helper
名称和 source-specific call/ABI 交互仍需单独调查。frontend IR 成功、单 backend
成功或外部 call 成功均未被当作 libc/runtime 验收。

详细结果、候选根因、未解释边界及后续 CodeGen test 边界见
[`docs/reviews/ML-016h-f64-libcall-minimal-repro-20260721.md`](/home/holight/DADAO-0628/docs/reviews/ML-016h-f64-libcall-minimal-repro-20260721.md)。

本轮实际修改文件仅为本 task 完成区和上述 review 文档；其余 probe/日志/脚本均在
指定 `/tmp` 目录。

独立 reviewer Boyle the 2nd 的结论为 **Accepted-with-findings**，见
`docs/reviews/ML-016h-independent-review-20260721.md`。review 确认 34 行矩阵与
对照统计一致，并要求保留“tail-call 是现象候选、非已证实因果”和“family coverage
不等于 157 个对象逐一闭合”的边界。
