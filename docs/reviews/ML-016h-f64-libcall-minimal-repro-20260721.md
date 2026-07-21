# ML-016h f64/libcall minimal repro

日期：2026-07-21（Asia/Shanghai）

## 结论

已完成只读最小 probe；本报告不预置 Accepted。17 个 LLVM IR probe 分别运行 O0/O3，
每个优化级别都独立运行 clang codegen 和 llc，并保留 argv、rc、stderr、输入 IR 和
成功时的 asm。完整入口是
[/tmp/ml-016h-f64-libcall-minimal-repro-20260721/results/summary.tsv](/tmp/ml-016h-f64-libcall-minimal-repro-20260721/results/summary.tsv)，
输入 IR 在
[/tmp/ml-016h-f64-libcall-minimal-repro-20260721/inputs/](/tmp/ml-016h-f64-libcall-minimal-repro-20260721/inputs/)。

最小且稳定的 `unsupported library call operation` 触发器不是“任意 f64 值”：
f64 identity、f64 constant、整数 add、指针 identity 均在 O0/O3 的 clang/llc 成功；
单个 `fadd`、`fsub`、`fmul`、`fdiv`、f64↔i64、f64↔f32、
`llvm.fmuladd.f64` 则在两个优化级别均失败。clang rc 为 1，llc rc 为 -6（abort）；
stderr 均在 DADAO DAG instruction selection 中进入
`TargetLowering::makeLibCall`，并报告 `unsupported library call operation`。

这确认了“缺少一组 soft-float/generated-libcall lowering”是高可信候选根因，但仍未
证明 157 个 object 共享一个精确 RTLIB operation，也未证明一次修复会覆盖整个簇。

## Probe matrix

| probe | O0 clang/llc | O3 clang/llc | 解释 |
|---|---:|---:|---|
| `f64_identity`, `f64_const` | 0/0 | 0/0 | f64 ABI/常量对照成功 |
| `f64_add`, `f64_sub`, `f64_mul`, `f64_div` | 1/-6 | 1/-6 | 单一 f64 算术指令即触发 generic libcall 错误 |
| `f64_to_i64`, `i64_to_f64` | 1/-6 | 1/-6 | 两向整数转换触发同一错误 |
| `f64_to_f32`, `f32_to_f64` | 1/-6 | 1/-6 | fptrunc/fpext 也未被当前 backend 处理 |
| `fmuladd` | 1/-6 | 1/-6 | 单一 `llvm.fmuladd.f64` intrinsic 触发 |
| `i64_add`, `ptr_identity` | 0/0 | 0/0 | 纯整数/指针对照成功 |
| `libm_sin` | 0/0 | 1/0 | O3 clang 为独立 f64 返回 call assertion；llc 成功 |
| `libm_sin_volatile_store` | 0/0 | 0/0 | call 后 volatile store/load 阻断 tail-call 后成功 |
| `explicit_adddf3_call` | 0/0 | 1/0 | 显式外部 helper call 的 O0 成功；O3 clang 为同一 call-lowering assertion |

每个 probe 的单独文件名为 `<probe>.<O0|O3>.<clang|llc>.*`，例如：

- [f64_add O0 IR](/tmp/ml-016h-f64-libcall-minimal-repro-20260721/inputs/f64_add.ll)
- [f64_add O0 clang stderr](/tmp/ml-016h-f64-libcall-minimal-repro-20260721/results/f64_add.O0.clang.stderr)
- [f64_add O0 llc stderr](/tmp/ml-016h-f64-libcall-minimal-repro-20260721/results/f64_add.O0.llc.stderr)
- [成功对照 asm](/tmp/ml-016h-f64-libcall-minimal-repro-20260721/results/f64_identity.O0.clang.s)
- [矩阵运行脚本](/tmp/ml-016h-f64-libcall-minimal-repro-20260721/run_matrix.py)

`libm_sin` 的 O3 clang 失败信息是
`LowerCallTo` assertion：`LowerCall emitted a return value for a tail call!`。
加入 `-fno-optimize-sibling-calls` 的变体仍为 rc=1；而显式 volatile store/load 的
变体 O3 clang/llc 均为 0。因此“DADAO O3 f64-return call/tail-call lowering 边界”是
另一个候选问题，不应与 generic `makeLibCall` 错误合并；这个结果也不是 157 簇的
精确根因证明。

## source family 对照

对 157 簇每个 family 至少抽取一个 source representative，在本任务目录中生成
O0/O3 frontend IR，并再次用 llc O0/O3 处理；IR 生成均为 rc=0，代表对象的 llc 均为
-6。完整计数和 operation 统计在
[/tmp/ml-016h-f64-libcall-minimal-repro-20260721/results/family-reps-summary.tsv](/tmp/ml-016h-f64-libcall-minimal-repro-20260721/results/family-reps-summary.tsv)，
抽样 IR/argv/stderr/asm 在
[/tmp/ml-016h-f64-libcall-minimal-repro-20260721/family-reps/](/tmp/ml-016h-f64-libcall-minimal-repro-20260721/family-reps/)。

| family | 簇对象数 | representative 证据 | 当前边界 |
|---|---:|---|---|
| `src/math` | 127 | `acos` 有 fadd/fmul/fdiv、`llvm.fmuladd.f64` 和 f64 calls | 可由浮点/libcall 候选解释，未逐对象闭合 |
| `src/complex` | 22 | `__cexp` 有 fmul/fadd 和 f64 calls | 同上；复杂函数可能叠加多个 operation |
| `src/internal` | 1 | `floatscan` 有 fadd/fmul/fdiv、fptosi/sitofp/uitofp、fmuladd | 候选覆盖很强，但未证明唯一触发点 |
| `src/stdio` | 2 | `vfprintf` 有算术/转换；`vfscanf` 有 fptrunc 和 f64 call | f64/f32 conversion 候选；仍需对象级 DAG 定位 |
| `src/stdlib` | 2 | `strtod` representative 有 fptrunc 和 f64 calls | fptrunc 已有最小失败 probe；wrapper/call 组合仍未闭合 |
| `src/legacy` | 1 | `getloadavg` 有 uitofp + fmul | 可由转换/算术候选解释，未唯一化 |
| `src/prng` | 1 | `drand48` 有 fsub 和 f64-return call | fsub 已最小复现；call/global 组合仍未闭合 |
| `src/time` | 1 | `difftime` 有 sitofp | 可由整数→f64 conversion 候选解释，未逐对象闭合 |

所以，8 个 source family 都有与本轮最小触发器相交的 IR 证据；这是“候选根因可
覆盖的 family”清单，不是 157/157 的根因证明。仍未解释的部分是每个 object 的
确切 DAG node/RTLIB helper、多个 operation 的先后组合，以及为什么相同 generic
stderr 在不同 source 中出现。特别是 `explicit_adddf3_call` O0 成功，不能把
“显式调用 helper 成功”当成“backend 能够为 IR fadd 生成该 helper”。

## 候选根因与未解释边界

高可信候选：

1. DADAO `TargetLowering` 对 f64/f32 soft-float arithmetic 和 conversions 的
   generated libcall/type legalization 不完整；最小单指令在 O0/O3 都能重现，stderr
   还直接落在 `makeLibCall`。
2. `llvm.fmuladd.f64` 的 lowering 缺口与普通 f64 arithmetic 共享候选路径，但尚不
   能确定它使用的具体 helper 或是否需要独立实现。
3. O3 f64-return external call 的 tail-call/call-result lowering 有独立 assertion
   边界；volatile store/load 能通过只是定位线索，不是修复验证。

仍未解释：

- 157 个对象是否分别由 add/sub/mul/div/conversion/fmuladd/fptrunc 中的哪一个触发；
  当前 raw stderr 没有给出具体 DAG node 或 RTLIB 名称。
- `src/math`/`src/complex` 的全部 149 个对象、以及其它 8 个 family 的每一个 object
  是否都走同一 lowering 路径；本轮是 representative，不是逐对象最小化。
- `strtod`/`vfscanf` 的 fptrunc、`drand48` 的 fsub、以及复杂函数中的外部 calls 是否
  还叠加了独立的 call/ABI 或其它 SelectionDAG 缺口。
- 本轮没有做 link、libc/runtime、QEMU/gem5 或完整 archive 验收；frontend IR 成功、
  单个 backend 成功或外部 call 成功均不等于 libc/runtime 已可用。

## 后续最小修改/测试边界

若进入 backend 修复，应先按 operation 拆成独立 CodeGen tests：fadd/fsub/fmul/fdiv、
f64↔i64、f64↔f32、`llvm.fmuladd.f64`，每项 O0/O3 都要求 llc 生成 asm；另加
non-tail f64-return external call 和 tail-call regression。修复后应重新运行隔离的
157-object matrix，再判断 family 是否真正收敛；本任务没有修改 LLVM、musl、主
build/archive、QEMU/gem5、contracts、vectors、issues、wiki 或 ML-014a。
