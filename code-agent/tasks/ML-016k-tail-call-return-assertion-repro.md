# ML-016k：tail-call return assertion 最小复现

**日期**：2026-07-21

**状态**：Audit-accepted-with-findings（ML-016 新 30-task run：11/30）

## 背景

ML-016h 和 ML-016j 都发现默认 O3 某些 f64、pointer-return、integer-return call 会
触发 `LowerCall emitted a return value for a tail call!`；禁用 sibling-call 后对应
最小矩阵可通过。该问题与 RB31 verifier 及 f64 generated-libcall 不能混为一谈。

## 目标与 ownership

worker 只做 `/tmp` 诊断：

1. 用最小 C/LLVM IR 覆盖 direct/indirect call、void/integer/pointer/f64 return、
   tail-call 标记、`-fno-optimize-sibling-calls`、volatile/use-after-call 和 O0/O3，
   记录 clang/llc rc、stderr、argv、IR/asm。
2. 确认 assertion 的最小触发条件，以及哪些形状能在保留优化的情况下成功；对
   `ML-016h`/`ML-016j` 代表 probe 做只读交叉核验，避免将它归入 RB31 或 libcall。
3. 给出后续 DAG call-lowering 修复与 CodeGen regression 边界，不修改 LLVM。

## 约束

- 只写本 task 完成区和 `docs/reviews/ML-016k-tail-call-return-assertion-repro-20260721.md`；
  probe/日志/脚本均放 `/tmp/ml-016k-tail-call-return-assertion-repro-20260721/`。
- 不修改 LLVM、musl、主 build/archive、QEMU/gem5、contracts、vectors、issues、wiki
  或 ML-014a。
- 不访问或引用 `~/toolchain`、`~/knowledge-graph`；不使用 `|| true`。
- 不把 frontend-only、单个 llc 成功或 asm 生成当作完整 libc/runtime 验收。

## 完成区

（由 worker 填写；完成后由不同 subagent 独立 review）

### worker 交付（2026-07-21）

状态：诊断完成，待独立 review；未修改 LLVM/TableGen 或任何实现、测试、规范、构建、
运行时、QEMU/gem5、contracts、vectors、issues、wiki 或其他 task。

完整原始证据只生成于
[`/tmp/ml-016k-tail-call-return-assertion-repro-20260721/`](/tmp/ml-016k-tail-call-return-assertion-repro-20260721/)，
包括 probes、每条命令的 `argv`/`rc`/`stdout`/原始 `stderr`、frontend IR 和成功生成的
clang/llc asm。主 C 矩阵为 24 个 probe（void/integer/pointer/f64 × direct/indirect ×
plain/volatile/use-after-call），覆盖 O0/O3 与 sibling enabled/disabled；另有 8 个
direct/indirect、四种返回类型的显式 `tail call` IR probe，覆盖 O0/O3。

主 C 矩阵的 288 条 stage 记录为 frontend 96/96 `rc=0`、clang 90/96 `rc=0` + 6 条
`rc=1`、llc 90/96 `rc=0` + 6 条 `rc=134`。6 条失败严格是 O3、sibling enabled、
direct/indirect 的 integer/pointer/f64 plain return；void plain、所有 volatile 与
use-after-call、全部 O0，以及全部 `-fno-optimize-sibling-calls` 组合均通过。逐项汇总：
[`results/summary.tsv`](/tmp/ml-016k-tail-call-return-assertion-repro-20260721/results/summary.tsv)。

显式 IR 子矩阵确认了最小边界：direct/indirect void 的 O0/O3 clang/llc 均通过；
direct/indirect integer/pointer/f64 的每个 O0/O3 clang 均为 `rc=1`、llc 均为 `rc=134`，
原始 stderr 首诊断均为 `LowerCall emitted a return value for a tail call!`。逐项
汇总为 [`results/explicit-cases-summary.tsv`](/tmp/ml-016k-tail-call-return-assertion-repro-20260721/results/explicit-cases-summary.tsv)，
显式 IR 源在 [`probes/ir/`](/tmp/ml-016k-tail-call-return-assertion-repro-20260721/probes/ir/)。

这建立了清晰分界：本 task 复现的是 SelectionDAG call lowering 在 tail-call 路径仍返回
`InVals` 的 assertion；它不要求 pointer return，也不要求 f64 generated-libcall。C 的
O3 IR 可见 plain return 被标为 `tail call`，而 disabled 版本为普通 `call`；例如
[`direct_int_plain` IR](/tmp/ml-016k-tail-call-return-assertion-repro-20260721/probes/ir/c/direct_int_plain.O3.enabled.ll)
与 [`no-sibling IR`](/tmp/ml-016k-tail-call-return-assertion-repro-20260721/probes/ir/c/direct_int_plain.O3.disabled.ll)。
volatile/use-after-call 的成功证据和 f64 外部 call asm 也已保存；它们没有出现
`unsupported library call operation`、RB31/RD31 或 MachineVerifier 诊断。

只读交叉核验保留两条不可合并的既有边界：ML-016j 的 O3 representative raw machine
dump 确实出现 CALL 的 `implicit-def dead $rd31` 后读取 `$rb31`，例如
[`posix_memalign stderr`](/tmp/ml-016j-rb31-pointer-return-repro-20260721/logs/representatives/clang.posix_memalign.O3.stderr)，
但本 task 的 no-sibling 最小 pointer-return probes 全部通过，故 RB31 仍是另一类
verifier 候选；ML-016h 的 f64 算术 probe 则在
[`f64_add llc stderr`](/tmp/ml-016h-f64-libcall-minimal-repro-20260721/results/f64_add.O0.llc.stderr)
报告 `unsupported library call operation`，本 task 只调用外部 `ext_f64`，其失败形状
始终是 tail-call assertion，不能归入 generated-libcall。

未执行 link、libc/archive、runtime、QEMU/gem5 验收；本交付仅闭合 CodeGen 最小复现和
后续 regression 边界，不宣称完整运行时通过。后续修复应分别保留：non-void direct/indirect
tail-call lowering（integer/pointer/f64）为 assertion regression，void tail-call 为
成功对照，volatile/use-after-call 与 `-fno-optimize-sibling-calls` 为保留优化/绕过对照；
RB31 verifier 与 f64 generated-libcall 另设独立 regression，不与本 assertion 合并。

独立 reviewer Franklin the 2nd 的结论为 **Accepted-with-findings**，见
`docs/reviews/ML-016k-independent-review-20260721.md`。review 要求将 explicit IR
结论限定为当前 target/build 和所测签名，不泛化为所有 tail-call ABI 形状。
