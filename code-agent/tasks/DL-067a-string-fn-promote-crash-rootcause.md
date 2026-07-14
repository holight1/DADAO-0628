# DL-067a: 根因定位 — DADAO backend 编译基础 string 函数崩溃（PromoteIntegerOperand）

**执行环境**: 本地 subagent（LLVM SelectionDAG 类型合法化排查）

**状态**: 通过（架构师复核）

**前置**：issue `codegen-string-fn-promote-crash`（`docs/issues.yaml`），架构师已独立复现。

## 现象（架构师已复现，直接复用）

```bash
cd ~/DADAO-0628
.work/build/llvm/bin/clang --target=dadao -nostdlib -nostdinc -ffreestanding -O0 -c \
  -I.work/picolibc/libc/include -I.work/picolibc/libc/stdio -I.work/picolibc/libc/locale \
  -I.work/picolibc -I.work/picolibc/build-dadao -I.work/build/llvm/lib/clang/22/include \
  -D_LIBC -DNEWLIB_NANO_MALLOC .work/picolibc/libc/string/strlen.c -o /tmp/strlen_test.o
```
崩溃：
```
PromoteIntegerOperand Op #1: t27: ch = <<Unknown Target Node #524>> t0, t22, BasicBlock:ch<while.end>
fatal error: error in backend: Do not know how to promote this operator's operand!
```
崩在 `DADAO DAG->DAG Pattern Instruction Selection` pass 处理 `@strlen` 时（实际是更早的 SelectionDAG 类型合法化阶段报错，不是真正的指令选择本身——报错文本里的 "Op #1" 是某个 DADAO 自定义/目标特定 SDNode 的第 2 个操作数需要类型提升，但类型合法化框架里没有为这个节点注册对应的 `PromoteIntegerOperand` case）。

## 已知背景（ML-005a 发现，直接复用）

- 用不容错的 `ninja libc.a`（去掉 `-k 0`）全新重建，实际有 **228 个编译单元失败**，不止最初记录的 2 个（jmp_buf/atold_engine，已由 ML-005a 处理）。多数失败是 libm/complex（M1 排除浮点，预期内），但 `strlen`/`memset`/`memchr`/`strcat`/`strchr`/`strstr` 等**与浮点完全无关**的基础 string 函数也在崩溃列表里。
- 现有的 E2E 测试套件（`loop_sum.test`/`usum_loop.test`/`cond_abs.test` 等）都用**手写的简单 C**（简单整数比较+分支），从未撞上这个问题——说明触发条件与 picolibc 源码里某种特定的 IR 形状/惯用法有关（比如窄位宽 i8 字符比较、指针自增循环、或者某个特定的 SelectionDAG 合法化路径顺序），不是泛泛的"分支/比较不工作"。

## 做什么

1. 用 `-print-after-all`/`-debug-only=legalize-types` 之类的 `llc`/`clang -mllvm` 选项，缩小到具体触发这次崩溃的 IR 节点——确认 "Unknown Target Node #524" 具体是 DADAO 自定义 SDNode 里的哪一个（`DADAOISD::` 命名空间下的哪个 opcode），以及为什么在 `while.end` 基本块相关的这条链（chain）类型节点上，操作数 #1 需要 promote。
2. 找到极简复现（比 `strlen.c` 更小的独立 `.c`/`.ll` 用例，比如一个只含 `while (*p) p++;` 风格循环的最小函数），加速迭代（参考 ML-003k 用极简复现替代整个 picolibc 编译的方法）。
3. 确认这是不是"某个自定义 SDNode 缺少 `ReplaceNodeResults`/`PromoteIntegerOperand` case"这一类通用的类型合法化钩子缺失（类似标准 LLVM target 在扩展自定义节点时常见的疏漏），还是别的更深层问题。
4. 产出**根因结论**（哪个节点、哪个钩子缺失、为什么现有测试没撞上）——本任务只定位，不在本任务里做修复（修复是后续任务）。

## 约束

- 只读诊断为主；若需要临时调试打印（在 `DADAOISelLowering.cpp` 或 LLVM 通用类型合法化代码里加 `dbgs()`），验证完说明是否已清理，交给修复任务一并处理。
- 不要为了让 `strlen.c` 编过而添加规避手段（比如给这个特定文件加特殊 flag 跳过合法化检查）——要定位真正缺失的合法化钩子。

## 验收（架构师亲跑）

- 根因结论清晰：具体是哪个 `DADAOISD::` 节点、缺少哪个类型合法化钩子（`PromoteIntegerOperand`/`ReplaceNodeResults`/其它），有 `-debug-only`/trace 证据支持，不是猜测。
- 有一个比 `strlen.c` 更小的独立复现用例（`.c` 或 `.ll`），可用于后续修复任务快速验证。
- 说明为什么现有 E2E 测试从未撞上这个问题（触发条件是什么）。

## 参考指针

- ML-005a 完成区（`code-agent/tasks/ML-005a-picolibc-libc-rebuild-unblock.md`）：228 个失败编译单元的背景、architect 独立复现的完整错误信息
- `docs/issues.yaml` 的 `codegen-string-fn-promote-crash` 条目
- `.work/llvm/llvm/lib/Target/DADAO/DADAOISelLowering.cpp`（自定义 SDNode 的 `LowerOperation`/`ReplaceNodeResults` 覆盖，比对哪些自定义节点注册了类型合法化钩子、哪些没有）
- `.work/picolibc/libc/string/strlen.c`（触发源码，`local.h` 相关 include 路径见 ML-005a 完成区的手动编译命令）
- ML-003k 完成区（`llc -print-after-all` 逐 pass 追踪方法论，遇到类似"极简复现比全量编译快"的场景可直接复用方法）
- feedback `feedback_ds_gem5_semantic_unreliable.md`（本任务虽非 gem5，但"细腻 CodeGen 语义活派 subagent 而非 DS"的精神一致）

—— 自审见 DS.md §自审流程同等标准（subagent 自己复核，逐条 finding + 判决）。

---

## 架构师复核（2026-07-14，ground-truth）：通过

独立核对 `DADAOISelLowering.cpp`：
- 行 32：`setOperationAction(ISD::BR_CC, MVT::Other, Custom)` + 行 58：`setTargetDAGCombine(ISD::BR_CC)` —— 同一 opcode 同时注册进两条完全独立的合法化路径。
- 行 280-281（`LowerOperation`）与行 538-539（`PerformDAGCombine`）**双双**调用 `LowerBR_CC`——真实重复，逐字确认。
- grep 全文件 `PromoteIntegerOperand`/`ReplaceNodeResults`：零匹配，确认全部 `DADAOISD::` 节点无类型合法化钩子。

根因证据链（`-debug-only=dagcombine` trace）逻辑自洽、最小复现（6 行 C，无需 picolibc 依赖）具体可执行。**判定**：根因定位扎实，转入修复任务 DL-067b。
