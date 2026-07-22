# ML-016q 独立 implementation review

日期：2026-07-21（Asia/Shanghai）

结论：**Accepted-with-findings**

## 核验范围

我独立读取了任务说明、已有 review、`.work/source/llvm` 子仓库中的实际 diff，以及
`/tmp/ml-016q-fix-inline-asm-register-constraint-20260721/` 的 build、frontend、backend、MIR、asm 和 metadata 记录。
LLVM 子仓库的实际改动仅为：

- `llvm/lib/Target/DADAO/DADAOISelLowering.cpp`：新增 hook 实现；
- `llvm/lib/Target/DADAO/DADAOISelLowering.h`：新增 override 声明。

`git diff --check` 通过，未见实现文件以外的 LLVM/TableGen/测试改动。`.work/llvm`
是指向 `.work/source/llvm` 的符号链接，因此 build 命令使用的源码与被审查 diff
一致。

## 实现判断

`DADAOTargetLowering::getRegForInlineAsmConstraint` 仅在 `Constraint == "r"`、
整数 `MVT` 且宽度不超过 64 bit 时返回 `DADAO::GPRDRegClass`；所有其它 constraint
仍调用 LLVM generic fallback。`=r`、`+r` 等约束在上层解析后由同一 hook 处理，后修复
MIR 中分别出现 `regdef:GPRD`、tied `reguse`，所以 hook 没有扩大到 memory、clobber
或无 operand asm。

GPRD 作为 generic scalar `r` 的选择是合理的：DADAO 当前将 i64 legal register
class 设为 GPRD，RD0--RD7 保留而 RD8--RD63 可分配；后修复结果实际使用 RD16 等
GPRD 寄存器。指针输入在进入 asm 前出现 `rb2rd` bridge，说明现有 cross-bank copy
路径可用。由于该 API 只有 `MVT`、没有 pointer provenance，不能在 hook 内可靠地区分
GPRB 与 GPRD；因此这是一项可接受的 generic `r` 约定，但 pointer 的 ABI/语义保持性
仍由 cross-bank 指令和后续 ABI 测试负责。没有添加 `f` 映射是合理的，因为当前 GPRF
标为不可分配。

## 构建与产物 provenance

保存的 build 命令 `ninja ... clang` 与 `ninja ... llc` 均返回 0，但 stdout 是
`ninja: no work to do.`，所以 build 日志自身不能证明这两个命令在记录时发生了重编。
不过源码 mtime 为 17:44:18，DADAO lowering object 为 17:44:29，`llc` 为 17:44:53，
`clang` 为 17:46:19；`.ninja_log` 也记录了 lowering object 及两个 binary 的构建
条目。因此结合 object/binary mtime，可以确认本轮修改之后确实产生过新的 CodeGen
object、llc 和 clang；只是这条证明主要来自 build tree 的时间戳/ninja log，而非保存
的 build stdout。

## probe、MIR 和 50/50 矩阵

`post-matrix.tsv` 共 54 行，其中标准矩阵是 50 行（25 个非 explicit_bzero probe，
各跑 O0/O3），另有 explicit_bzero 的 2 个 fresh-frontend 失败行和 2 个
`from-ml016o` 行。标准 50/50 行全部满足 frontend/backend/MIR rc=0，且 asm、MIR
均存在。标准 probe 的 frontend argv 指向当前 build 的 clang；生成 IR 的
`!llvm.ident` 是 clang 22.1.8 commit `10690fc4...`，随后 backend/MIR argv 指向
当前 build 的 llc。该部分可以认定为由新 clang/llc 产物生成。

代表性结果与预期一致：

- pointer input 的 MIR 为 `INLINEASM ... reguse:GPRD`，前置有 `rb2rd`；
- scalar output 为 `regdef:GPRD`；output+input 有独立 def/use；inout 为 tied use；
- u8/u16/u32/u64 的 input/output/inout 在 O0/O3 全部通过；
- `memory_input/output/inout` 的 MIR 保留 `mem:m`，不出现寄存器 constraint operand；
- `clobber_cc`、`clobber_memory`、`clobber_memory_cc` 全部通过，MIR 没有伪造的
  GPR operand；
- no-operand asm 没有寄存器 operand，`no_operand_trap` 的 `trap 2, 0` 仍保留。

修复前 ML-016o 记录显示对应 `r` 输入/输出/inout 在 O0/O3 为 rc=1，而 memory、
clobber、无 operand 为 rc=0；这与当前差分结果相符，支持故障簇定位和修复方向。

## explicit_bzero 的限制

这是本次验收的主要 finding。新 clang 从 `explicit_bzero.c` 生成 IR 的 O0/O3 命令及
带 include path 的 retry 都是 rc=1，stderr 为 host `/usr/include/string.h` 缺少
`bits/libc-header-start.h`。因此本轮目录中的
`probes/ir/explicit_bzero.O0.ll`、`explicit_bzero.O3.ll` 不存在，metadata 中对应
backend/MIR 行也是“输入文件不存在”的 rc=1，而不是 hook 失败。

成功的 `explicit_bzero.from-ml016o.O0/O3` asm/MIR 确实由本轮新 llc 生成，且显示
`rb2rd` 后的 `reguse:GPRD`；但其 argv 输入是
`/tmp/ml-016o-inline-asm-constraint-repro-20260721/probes/ir/explicit_bzero.*.ll`。
这些旧 IR 的 mtime 为 17:16，`!llvm.ident` 是旧 clang commit `1697be42...`，不是
本轮新 clang 生成的 IR。因此可以接受“新 llc 对既有 IR 的 explicit_bzero 回归”，
不能宣称 explicit_bzero 完成了新 clang→llc 的全链路重编验证。

## ABI 与其它簇证据

当前证据只覆盖 SelectionDAG inline-asm constraint、窄宽度 scalar、memory/clobber
和无 operand 对照。没有 ABI 专项 probe（调用参数/返回、callee-saved、跨 call 的
GPRB/GPRD 值保持），也没有其它 backend failure cluster 的回归矩阵、archive/runtime
或执行环境证据。因此没有发现 ABI/其它簇回归，但也不能把“未观察到回归”表述为已被
本轮证明；这属于范围 finding，而不是当前 hook 已造成回归的证据。

## Findings

1. **中等：explicit_bzero 缺少本轮新 clang 生成的 IR。** host header 阻塞已被如实
   保存，且新 llc 对旧 IR 的结果有效；若要关闭该 finding，需要用可用的 host include
   环境或自包含等价 source 重新生成 explicit_bzero O0/O3 IR，再由当前 clang/llc
   完整跑通。
2. **较低：缺少 ABI/其它簇回归证据。** 目前只能批准 inline-asm hook 的局部
   implementation 和 50/50 CodeGen 矩阵，不能扩展为 ABI 或全 backend 验收。
3. **较低：build 日志的直接表述不足。** 两个保存的 ninja 日志是 no-op；实际重编由
   lowering object、llc、clang 的时间戳和 `.ninja_log` 间接确认。后续若需更强审计链，
   应保存触发重编时的完整 compile/link command 和 rc。

综合判断：实现范围正确，GPRD mapping 有直接 MIR 支持，标准 50/50 新产物矩阵及
memory/clobber/no-operand 对照通过；上述 provenance 和覆盖范围限制不构成拒绝实现，
故结论为 **Accepted-with-findings**。
