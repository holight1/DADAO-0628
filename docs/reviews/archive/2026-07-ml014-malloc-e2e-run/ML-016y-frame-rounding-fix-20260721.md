# ML-016y review：DADAO frame lowering ABI 栈对齐修复

日期：2026-07-21

结论：**Accepted with one infrastructure limitation**。生产修复和独立 CodeGen
regression 已提交到 nested LLVM；静态探针与 QEMU/Gem5 最小矩阵闭合。目录级
`llvm-lit` 因构建树缺少 `llvm-config` 返回 rc=2，已保留准确日志。

## 事实

### 源码与提交

事实：修复前 `emitPrologue`/`emitEpilogue` 使用 `MFI.getStackSize()+VarArgsSaveSize`
原值；raw `stackSize=4` 因而产生 `addi rb1,rb1,-4`。修复后
`getDADAOFrameSize` 在同一处计算 `alignTo(raw,8)`，三条使用路径共享 rounded value。

事实：最终代码位于
[`DADAOFrameLowering.cpp`](/home/holight/DADAO-0628/.work/source/llvm/llvm/lib/Target/DADAO/DADAOFrameLowering.cpp:20)，
regression 位于
[`frame-lowering-stack-alignment.ll`](/home/holight/DADAO-0628/.work/source/llvm/llvm/test/CodeGen/DADAO/frame-lowering-stack-alignment.ll:1)。

事实：nested LLVM 是 detached HEAD，但工作树 clean；最终 commit 为
`d3bd9c15434fd7a48c0b7bab87354778cd932a72`，parent 为
`be99e5505abe341100c62d70cd955b2df7e4711e`。此前报告中的
`3ae8bff76d2e` 是同一任务的中间 commit，随后为纳入 varargs align-down 修订而
安全 amend，最终 hash 以 `d3bd9c...` 为准。

事实：nested commit 只改 2 个文件：frame lowering 源文件和同一 DADAO target 下的
最小 CodeGen regression。主仓库保留原有无关未跟踪文件
`code-agent/tasks/ML-014a-musl-e2e-malloc-printf.md`，没有回退或提交它。

### 设计与布局

事实：普通 i32 alloca 的 MIR raw `stackSize` 为 4，但最终机器指令为：

```text
addi rb1, rb1, -8
addi rb8, rb1, 4
stt  ..., rb8, 0
addi rb1, rb1, 8
```

事实：i64 alloca 保持 `-8/+8`，direct trap 的 MIR `stackSize: 0` 且没有 frame
adjustment。

事实：include-free variadic C probe 的 `varargs_one_local` MIR raw local frame 为
4，fixed varargs save object 为 120 bytes；最终 assembly 为 `-128/+128`，64-bit
save stores 从 `rb1+0` 到 `rb1+112`，普通 `count` local 通过 `addi rb8,rb1,124`
访问。save area 与 local slot 不重叠且 store base 对齐。

事实：一个较大的 variadic probe 也成功生成 `-152/+152`，其保存区和普通 locals
均落在同一 rounded frame 内。最终 include-free varargs runtime 加入 crt0 后，compile、
link、objcopy 均 rc=0，QEMU/Gem5 均以 rc=0 结束。

### 构建与测试证据

| 命令/阶段 | rc | 证据 |
|---|---:|---|
| `ninja -C .work/build/llvm llc` | 0 | `logs/build-llc.rc` |
| `ninja -C .work/build/llvm clang llc`（含最终 HEAD 重编） | 0 | `logs/build-clang-llc-on-final-head.rc` |
| assembly `llc | FileCheck` | 0 | `logs/final-assembly-check.rc` |
| MIR `llc -stop-after=prologepilog | FileCheck` | 0 | `logs/final-mir-check.rc` |
| `git diff --check` | 0 | `logs/final-diff-check.rc` |
| directory `llvm-lit -v .../CodeGen/DADAO` | 2 | `logs/lit-dadao-final.rc` |

`llvm-lit` 的事实性错误是：无法运行
`.work/build/llvm/bin/llvm-config --assertion-mode --build-mode`；不是 regression
FileCheck 失败。

### ML-016x 探针静态与双后端结果

新工具链静态编译/汇编/链接/objcopy/disasm 的正常路径均 rc=0。权威 runtime 结果：

| probe | QEMU rc | Gem5 rc | 观察 |
|---|---:|---:|---|
| `direct_syscall1` | 42 | 42 | direct syscall/trap 对照；helper `-40` |
| `wrapper_noreturn` | 42 | 42 | 外层 frame 已由 `-4` 变 `-8` |
| `exit_shape` | 42 | 42 | `_Exit` 结构孪生不再触发 MALIGN |
| `trap_direct` | 42 | 42 | direct trap 对照 |
| `trap_stack_minus4` | 129 | 129 | 保留的故意未对齐负对照 |
| `trap_stack_minus8` | 42 | 42 | 对齐负对照 |
| `varargs_runtime` | 0 | 0 | rounded varargs frame/save area 真实执行 |

QEMU/Gem5/launcher/tool hash、完整 argv、raw stdout/stderr 和 rc 位于
`/tmp/ml-016y-frame-rounding-fix-20260721/`；launcher hash 为
`44042fabb2741724828443d7ae13bd42e3931e88d8be7f2f7dc48be3d851f5e0`。

## 推断

推断：ML-016x 中的 `wrapper_noreturn`/`exit_shape` `129` 首要来自 callee 外层
4-byte frame 破坏 SP mod-8，而非 trap/launcher；修复后同一 probe 两端 rc=42，且
故意 `trap_stack_minus4` 仍为 129、`trap_stack_minus8` 仍为42，支持该归因。

推断：varargs save area 必须作为有效 frame 的独立布局区处理，不能只把
`VarArgsSaveSize` 加到 prologue。此次 C probe 的中间 `rb1+4` 试验两端 rc=129，说明
save-area base 也必须 8-byte aligned；最终使用 rounded frame 的 lower aligned base，
并把 residual padding 留在 save area 与 local frame 之间。

这些是由 MIR/assembly 与双后端结果共同支持的归因，不是将 simulator rc 单独反推为
LLVM 事实。

## 失败、阻塞与边界

1. 目录级 `llvm-lit`：rc=2，阻塞原因是 build tree 未生成 `llvm-config`；直接
   `llc | FileCheck` rc=0，已作为权威 target regression 证据。
2. 初次 varargs runtime 的 `padding=4` 实验：QEMU/Gem5 rc=129，已保留；修订为
   `alignDown(padding,8)` 后 final runtime rc=0。
3. 一次错误 varargs 子 shell 路径命令 rc=1，以及一次把 trap 自带 `_start` 与 crt0
   重链的 duplicate-symbol rc=1，均保留在 logs 中并明确不是权威结果。
4. 本轮未修改或验证完整 musl、完整 LLVM suite、完整 E2E/differential、QEMU/Gem5
   源码；这些不应被本报告的最小矩阵结果替代。

## 变更边界与最终交接

canonical task：[`ML-016y-frame-rounding-fix.md`](../../code-agent/tasks/ML-016y-frame-rounding-fix.md)

nested final commit：`d3bd9c15434fd7a48c0b7bab87354778cd932a72`

证据目录：[`/tmp/ml-016y-frame-rounding-fix-20260721/`](/tmp/ml-016y-frame-rounding-fix-20260721/)

主 agent 可 cherry-pick/集成该 nested commit；本主仓库工作树未提交 nested LLVM 生产
源，也未触碰 30-task tracker。
