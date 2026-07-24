# ML-031a 最终独立复审（2026-07-24）

**任务**：`code-agent/tasks/ML-031a-aggregate-struct-abi-parameter-passing.md`

**第一轮报告**：`docs/reviews/ML-031a-independent-review-20260724.md`

**最终审查对象**：

- LLVM HEAD `86656a44524167b605274b616906f8d432563f6e`；
- 第一轮整改提交 `36abcbd6369d`、`86656a445241`；
- root patch 0055-0059、`components/llvm/patches/series`；
- ML-031a 两项 E2E、ABI contract、issues/archive、wiki questions 与任务完成记录。

**审查隔离**：本轮由最终 reviewer 亲自完成，没有启动、派生或调用任何 subagent/
Codex 进程，也没有参考 `~/toolchain` 或 `~/knowledge-graph`。除本报告外未修改任何
仓库文件。

## 最终判决

**Accepted**

第一轮 B1-B4 四项 blocking finding 均已在最终 LLVM HEAD 上得到实现修复、永久回归
覆盖和独立运行证据支持。本轮未发现新的 blocking 或 major correctness finding。

## Findings

### Blocking

无。

### Major

无。

### Minor N1：永久 mem* 回归采用代表性矩阵，没有枚举完整笛卡尔积

`mem-intrinsic-libcall-no-tail.ll` 永久覆盖了：

- memcpy：16B、17B、256KiB，tail 与 non-tail；
- memmove：17B，tail 与 non-tail；
- memset：17B，tail 与 non-tail。

它没有把 memmove/memset 的 16B、256KiB，以及每一种尺寸的 tail/non-tail 全部写成
独立函数。由于 `86656a445241` 的修复位于统一 `LowerCall` 入口，这不是已知语义
缺陷；本轮另用临时 C probe 独立编译完整矩阵：

- memcpy/memmove/memset；
- 16B、17B、256KiB；
- tail、non-tail；

共 18 种组合全部在最终 assertions-enabled clang 上成功编译，无 assertion；16B
内联，17B/256KiB 生成普通 libcall，non-tail 路径之后仍保留 `observe` call。
建议后续把该完整矩阵固化进 LLVM 测试，但不阻断本次接受。

### Informational I1：0055/0056 的字节差异仅来自 format-patch 编号元数据

0058/0059 与各自提交的 fresh single-commit `git format-patch --stdout` 字节完全
一致。0055/0056 与 fresh single-commit 导出不逐字相同，是因为现有 patch Subject
保留了 `[PATCH 55/56]`、`[PATCH 56/56]` 系列编号；其 diff 的 stable patch-id 与
提交完全一致。0057 也与 fresh 导出字节一致，且最终 59/59 replay tree 完全匹配，
因此不是 provenance finding。

## 第一轮 blocking finding 逐项复验

### B1：padded/nested HPA 的 AST offset 与物理 RB bank

**结论：已修复。**

静态审查确认 `36abcbd6369d`：

- recursive flatten 使用 `ASTRecordLayout::getFieldOffset` 累加真实 byte offset；
- `coerceAndExpandHPA` 在 packed coercion type 中显式表示 padding；
- unpadded expansion type 只暴露 pointer leaves，使每个 leaf 继续命中
  `CCIfPtr`；
- 没有把数组字段重新擅自纳入 HPA flatten。

独立 IR/汇编证据：

- `PaddedHPA` caller 从 offset 0、16 分别取出两个 pointer；
- IR 调用签名为两个独立 `ptr` 参数；
- caller 分别写入 `rb16`、`rb17`；
- callee 从 `rb16`、`rb17` 重建到本地 offset 0、16。

`agg_args_named.test` 的 O0/O2 正例及负控制在 QEMU、gem5 均通过。额外同类探针用
9 个 `H2 { void *a, *b; }` 参数产生 18 个 pointer leaves，真实跨过 RB16-RB31
并触发 stack overflow；O2 下 QEMU/gem5 均 exit 42，说明 HPA 展开后的物理 RB bank
和溢出路径一致。

### B2：非 HFA、`>32B` 聚合变参的 inline slots

**结论：已修复。**

静态审查确认 `computeInfo` 按 `FI.getNumRequiredArgs()` 区分 named/unnamed；
`classifyAggregateVarArg` 对非 HFA aggregate 返回
`[ceil(sizeof(T)/8) x i64]` direct coercion，不复用 named `>32B` indirect。
`EmitVAArg` 同样使用 unnamed 分类。

独立 IR 证据显示 40B `Big40` 被传为 `[5 x i64]`，后接独立的尾随 `i32 999`，
而不是一个 temporary pointer slot。callee 的 `va_arg` 对 Big40 将游标推进 40
字节，再对尾随标量推进 8 字节。

`agg_vararg_multislot.test` 的 12B、16B、40B+tail 在 O0/O2 QEMU、gem5 均通过，
两后端负控制也得到预期失败码 9。

### B3：内部 pointer call 后恢复 sret RB16/live-out

**结论：已修复。**

静态审查确认 `86656a445241`：

- `LowerFormalArguments` 把 hidden sret pointer 保存到 GPRB virtual register；
- call regmask 使它在内部 call 周围正常 spill/reload；
- `LowerReturn` 在每个 sret return 前 copy 回物理 RB16；
- RB16 被加入 variadic `RET_GLUE` 的 live-out operands。

最终 `make_big` O2 汇编在 `call sink` 后明确出现：

```asm
ldo rb8, rb1, 0
ldo rb16, rb1, 8
...
ret rd0, 0
```

`aggregate-sret-preserve.ll` 通过，具名 E2E 的 internal pointer call、两次独立
sret 调用在 QEMU/gem5 均通过。

### B4：mem* 阈值、tail/non-tail 与大对象

**结论：已修复。**

`86656a445241` 在 `DADAOTargetLowering::LowerCall` 入口统一设置
`CLI.IsTailCall=false`，与当前目标没有 sibling-call lowering 的事实一致，不会
再把有限 `MaxStoresPerMem*` 阈值引出的 libcall 送入未实现的 tail-call 路径。

独立验证：

- LLVM 永久回归 `mem-intrinsic-libcall-no-tail.ll` PASS；
- 临时 18-case 完整矩阵全部编译成功，无 assertion；
- 17B/256KiB 的 memcpy/memmove/memset 均生成普通 call；
- `pr28982b.c` 在目标 torture filter 中 PASS；
- 全量 torture 未出现状态退化。

## 定向、全量与同类遗漏验证

| 验证 | 独立结果 |
|---|---|
| Clang aggregate ABI + DADAO CodeGen | 9/9 PASS |
| ML-031a 两项 E2E | 2/2 PASS |
| 全量 E2E | 76/76 PASS |
| 目标 torture（含 `pr28982b`） | 22 PASS / 1 FAIL_RUN |
| 唯一目标失败 | `pr38151.c`, exit 127，既有已登记 issue |
| 全量 gcc-c-torture | 1429 PASS / 113 FAIL_COMPILE / 131 FAIL_LINK / 35 FAIL_RUN |
| 与 root `gcc-torture-results.json` | 1708 项 status mismatch = 0 |
| differential | AGREE(3-way)=200，DIVERGE=0，gem5-SKIP=2 |
| Sail | AGREE(4-way)=200，SAIL-DIVERGE=0，Sail-SKIP=2 |
| HPA RB-bank overflow probe | O2 QEMU=42，gem5=42 |
| RD aggregate overflow probe | O2 QEMU=42，gem5=42 |
| mem* 18-case compile matrix | 全部成功，无 assertion |

额外 RD overflow probe 用 5 个 32B aggregate 参数产生 20 个 RD blocks，跨过
RD16-RD31 后进入 stack；O2 QEMU/gem5 均 exit 42。未发现 HPA/RD split 在 bank
耗尽边界的同类遗漏。

## Contract / issues / gates

独立检查结果：

- `scripts/manifest_check.py`：PASS；
- `scripts/check_issues.py`：PASS，Open=22 / Closed=39 / Total=61；
- `scripts/check_wiki_refs.py --profile abi`：PASS；
- `scripts/check_wiki_drift.py`：PASS；
- `scripts/check_codegen_abi.py`：MISMATCH=0；
- `scripts/check_lit_bytes.py`：69 patterns OK。

`contracts/abi/spec.md` 对 HPA、普通 aggregate、非 HFA aggregate vararg、sret 的
已实现声明与最终代码和上述证据一致；HFA 仍明确排除并由 open issue 跟踪。
`codegen-tailcall-lowercall-assert` 的原始历史完整迁入 archive，关闭依据与 0059
一致；`pr38151` 的复杂变参缺陷保持 open，没有被 ML-031a 结果掩盖。

## Patch / commit provenance

- `36abcbd6369d` 的 parent 是 `53e5e16e829a`；
- `86656a445241` 的 parent 是 `36abcbd6369d`；
- 两者均为当前线性历史上的普通 commit；
- 0058 SHA256：
  `84c3ad2f94aee140bfca4b8c2884bd276d265bbed4b9acbc2b8ec406aa9f96d5`；
- 0059 SHA256：
  `789653ef0ffc8304f0419460dc65dc588fd063aeb4a39cc66ce0ecf60f2bb875`；
- 0058/0059 分别与对应 commit 的 fresh format-patch 字节完全一致；
- 0055-0059 stable patch-id 均与其 `From` commit 一致；
- 最终 clang revision：
  `86656a44524167b605274b616906f8d432563f6e`；
- 从 manifest pin `ca7933e47d3a3451d81e72ac174dcb5aa28b59d1` 在独立临时 clone
  中按 series 执行 plain `git am`：**59/59** 成功；
- replay tree 与开发 LLVM HEAD tree 均为
  `5eb4aa6953eb634052fecad3fd0e187aa103e204`；
- replay 与开发 LLVM 工作树均干净。

## 最终意见

ML-031a 的四项首轮 blocker 已关闭，整改代码、物理 ABI 行为、双后端运行、全量
回归、contract/issues 记录和 patch provenance 相互一致。除 Minor N1 的永久测试
矩阵可继续扩充外，本任务满足当前验收要求，可以按 **Accepted** 收口。
