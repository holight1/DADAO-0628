# ML-016i 独立 reviewer 意见

日期：2026-07-21  
审查对象：[任务说明](/home/holight/DADAO-0628/code-agent/tasks/ML-016i-dynamic-stackalloc-minimal-repro.md)、[worker review](/home/holight/DADAO-0628/docs/reviews/ML-016i-dynamic-stackalloc-minimal-repro-20260721.md) 及 `/tmp/ml-016i-dynamic-stackalloc-minimal-repro-20260721/` 原始产物。

## 结论

**Accepted-with-findings**

最小复现、固定 alloca 对照、stackrestore 探针以及 7 个 representative 的矩阵均有可复核的 argv、rc、stdout/stderr 和 IR/asm 产物；核心边界成立。但 `dcngettext-O3` representative 的失败节点不是 `dynamic_stackalloc` 或 `stackrestore`，需要在归因上单列，不能把 14/14 backend 失败整体当作同一个 selector 根因的证据。

## 独立抽查结果

### 最小形状与固定对照

- [`probes/ir/dynamic_void.ll`](/tmp/ml-016i-dynamic-stackalloc-minimal-repro-20260721/probes/ir/dynamic_void.ll) 只有 `alloca i8, i64 %n` 后 `ret void`，不含 `llvm.stacksave`/`llvm.stackrestore`，但 O0/O3 的 [`llc` 日志](/tmp/ml-016i-dynamic-stackalloc-minimal-repro-20260721/logs/llc) 都是 `rc=134`；argv 均为目标 `llc -mtriple=dadao -O{0,3}`，stderr 首诊断为 `Cannot select ... dynamic_stackalloc`。
- [`fixed_alloca.ll`](/tmp/ml-016i-dynamic-stackalloc-minimal-repro-20260721/probes/ir/fixed_alloca.ll) 的 llc、直接 clang 和 frontend IR 在 O0/O3 均为 `rc=0`。生成的 [`fixed_alloca` asm](/tmp/ml-016i-dynamic-stackalloc-minimal-repro-20260721/probes/asm/llc/fixed_alloca-O0.s) 可见 `rb1 -= 32`、访问和 `rb1 += 32`；这证明静态 alloca 边界，不证明动态 frame ABI。
- [`fixed_stacksave_restore.ll`](/tmp/ml-016i-dynamic-stackalloc-minimal-repro-20260721/probes/ir/fixed_stacksave_restore.ll) 没有动态 alloca，但 O0/O3 llc 均 `rc=134`，stderr 首节点为 `stackrestore`。因此 `stackrestore` 是独立失败面，而不是必须由 dynamic alloca 引起。
- [`stacksave_restore.ll`](/tmp/ml-016i-dynamic-stackalloc-minimal-repro-20260721/probes/ir/stacksave_restore.ll) 的 combined probe O0/O3 也均 `rc=134`，但首个 selector 诊断是 `stackrestore`。C VLA 则在 O0 首先报告 `stackrestore`、O3 首先报告 `dynamic_stackalloc`。这只能说明 selector/优化后的暴露顺序不同，不能把两个节点合并或据此排序根因。

### 矩阵与 argv/rc/stderr

按 [`run-matrix.sh`](/tmp/ml-016i-dynamic-stackalloc-minimal-repro-20260721/run-matrix.sh) 产生的日志重新计数：

| 阶段 | 数量 | rc=0 | 非零 rc | 独立核验 |
|---|---:|---:|---:|---|
| 9 个 C probe frontend IR，O0/O3 | 18 | 14 | 4 | 4 项是两个 C stack builtin 的 frontend unknown-builtin，不计为 backend 证据 |
| 9 个 C probe 直接 clang asm，O0/O3 | 18 | 2 | 16 | 仅 fixed alloca 成功 |
| 10 个显式 IR llc，O0/O3 | 20 | 2 | 18 | fixed alloca 成功；动态 alloca/restore 失败 |
| 7 个 representative frontend IR，O0/O3 | 14 | 14 | 0 | 14 个 argv 均指向预期 musl source，stderr 为空 |
| 7 个 representative 直接 clang backend，O0/O3 | 14 | 0 | 14 | 均为 backend 失败，rc=1 |
| 7 个 representative IR llc，O0/O3 | 14 | 0 | 14 | 均为非零，rc=134 |

7 个 representative 的 14/14 frontend 成功、14/14 clang backend 失败、14/14 llc 失败均可由 [`logs/representatives`](/tmp/ml-016i-dynamic-stackalloc-minimal-repro-20260721/logs/representatives) 与 [`logs/llc`](/tmp/ml-016i-dynamic-stackalloc-minimal-repro-20260721/logs/llc) 的逐项 `.argv`、`.rc`、`.stderr` 对上；没有把 frontend-only 成功当作 backend 成功。

## Finding：dcngettext-O3 的失败归因需收窄

[`dcngettext-O3-llc.stderr`](/tmp/ml-016i-dynamic-stackalloc-minimal-repro-20260721/logs/llc/dcngettext-O3-llc.stderr) 与对应的 [`dcngettext-O3-compile.stderr`](/tmp/ml-016i-dynamic-stackalloc-minimal-repro-20260721/logs/representatives/dcngettext-O3-compile.stderr) 的关键结果是：

- llc `rc=134`、clang backend `rc=1`；
- 失败函数是 `@bindtextdomain`，阶段是 `Greedy Register Allocator`；
- 两个 verifier 报告均为 `Using an undefined physical register`，具体是 `$rb31`；
- 末尾诊断是 `Found 2 machine code errors`，stderr 中没有 `dynamic_stackalloc` 或 `stackrestore` 的 selector 诊断。

同一 O3 IR 的 `@dcngettext` 确实含动态 alloca、stacksave 和 stackrestore，但该失败日志没有证明这些节点是本次 `dcngettext-O3` 失败的首因；失败发生在另一个函数/后续寄存器分配阶段。故矩阵的 `0/14` 计数有效，但该单元只能标作“representative backend 仍失败，具体为 frame/register verifier 失败”，不能作为 `dynamic_stackalloc` 或 `stackrestore` 的直接复现。worker review 中“共同 stderr 仍保存完整 DAG”的表述应限于实际包含该 DAG 的单元。

其余 representative 的 O0/O3 backend/llc stderr 首诊断均与动态 frame 形状相符：`dcngettext-O0`、`res_msend`、`execl`、`execle`、`execlp`、`execvp`、`getcwd` 的对应失败日志均能看到 `dynamic_stackalloc`；这支持最小 probe 的范围结论，但不消除上述 O3 例外。

## frame/ABI 结论边界

worker review 对未证实内容的处理是合格的：没有从静态 asm 推断动态 frame 的增长方向、单位、对齐、frame index 重物化、SP/FP 约定、callee-saved/epilogue 关系，也没有把 stacksave/stackrestore 的表示或 chain 语义写成已证实根因。`dynamic_void` 只证明 dynamic alloca selection 的必要触发形状；独立 fixed-allocation restore probe 只证明 restore selection 也缺失。两者都不足以构成 ABI 修复结论。

后续修复验收应继续分别覆盖 dynamic alloca/frame lowering 与 stacksave/stackrestore selection，并保留 static success、`dynamic_void`、VLA O0/O3、动态对齐、escape/call 及 7 个 representative；本次材料本身不应升级为 libc/runtime 或 ABI 验收。

## 审查范围外修改核对

本次只读取任务说明、既有 review 和 `/tmp` 证据，并只创建本文件；未修改 LLVM、musl、build/archive、测试或规范。
