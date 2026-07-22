# ML-016r：fresh clang→llc inline-asm chain verification

**日期**：2026-07-21

**状态**：Accepted（ML-016 新 30-task run：18/30）

## 背景

ML-016q 的 hook 修复已通过新 llc 的 50/50 标准矩阵，但独立 review 指出
`explicit_bzero.c` 受 host `<string.h>` header 缺失阻塞，本轮使用的是旧 clang 生成
的 IR 再由新 llc 验证。需要用 include-free、与 explicit_bzero inline-asm 约束等价的
fresh source，完整验证新 clang→新 llc→MIR/asm，明确等价复现而非冒充原文件全链路。

## 目标与 ownership

worker 只做 `/tmp` 验证，不改实现：

1. 只读提取 ML-016o 的 explicit_bzero inline-asm 语句和参数/约束，构造 include-free
   self-contained source；保存原始 source、与原语句的逐项对照及选择等价复现的理由。
2. 使用当前已重编 DADAO clang 和 llc，分别 O0/O3 生成 fresh IR、backend asm、
   finalize-isel MIR；保存 clang/llc rc、argv、stderr、工具 hash/version。若直接
   fresh original source 仍失败，记录阻塞，不用等价复现覆盖原文件结论。
3. 运行 pointer/i64/u8-u64 `r` input/output/inout 和 memory/no-operand 对照的部分
   fresh chain，报告修复后所有 rc；明确这一任务只验证 inline-asm hook，不验 ABI、
   libc archive、runtime 或 QEMU/gem5。

## 约束

- 只写本 task 完成区和 `docs/reviews/ML-016r-fresh-inline-asm-chain-verification-20260721.md`；
  全部 source/IR/asm/MIR/log 放 `/tmp/ml-016r-fresh-inline-asm-chain-verification-20260721/`。
- 不修改 LLVM、musl、主 build/archive、contracts、vectors、issues、wiki、ML-014a
  或 QEMU/gem5；不访问或引用 `~/toolchain`、`~/knowledge-graph`。
- 不使用 `|| true`；不要把 include-free 等价 source 的成功表述为原
  `explicit_bzero.c` 新 clang 成功。

## 完成区

worker 已完成 fresh clang→llc inline-asm chain verification；全部源文件、fresh
IR、backend asm、finalize-isel MIR、逐命令 argv/rc/stdout/stderr、工具版本和
SHA-256 均保存在 `/tmp/ml-016r-fresh-inline-asm-chain-verification-20260721/`。

- 原始 `explicit_bzero.c` 已逐字保存为
  `probes/source/explicit_bzero.c.original`，并与仓库 source 及 ML-016o 原始
  副本 `cmp` rc=0。include-free 等价 source 为
  `probes/source/explicit_bzero.include-free.c`；只补充 target-defined
  `size_t` typedef 和 `memset` extern declaration，保留函数、赋值、空
  volatile asm、`"r"(d)` input constraint、`"memory"` clobber 的语义和顺序。
  选择理由见 `source-rationale.md`。
- include-free source 的 explicit_bzero O0/O3 均为 fresh clang IR rc=0、new
  llc asm rc=0、finalize-isel MIR rc=0；IR 保留
  `"r,~{memory}"(ptr ...)`，MIR 为 `INLINEASM` 的 `reguse:GPRD`，asm 实际
  生成 `#APP/#NO_APP`。
- fresh 对照共 22 个 case、O0/O3 共 44 条完整 IR→asm/MIR chain，全部
  frontend/backend/finalize-isel rc=0：pointer/i64 `r` input、i64
  output/inout、u8/u16/u32/u64 的 input/output/inout，以及 memory
  input/output/inout、无操作数和 `trap 2, 0` 对照。
- 原始带 `<string.h>` source 的新 clang fresh IR 和 direct backend 尝试在
  O0/O3 均 rc=1；raw stderr 均保留
  `/usr/include/string.h:26:10: fatal error: 'bits/libc-header-start.h' file not found`。
  include-free 成功结果没有被表述为原始文件全链路成功。
- 使用的工具为 `/home/holight/DADAO-0628/.work/build/llvm/bin/clang` 和
  `llc`；版本/哈希在 `logs/metadata/tool-versions.txt`、
  `tool-hashes.tsv`，完整矩阵见 `logs/metadata/fresh-matrix.tsv`，原始
  header 阻塞见 `logs/metadata/original-host-header.tsv`。

独立 review 文档：
`docs/reviews/ML-016r-fresh-inline-asm-chain-verification-20260721.md`。

独立 reviewer Bernoulli the 2nd 的结论为 **Accepted**，见
`docs/reviews/ML-016r-independent-review-20260721.md`。review 确认 44 条 fresh
等价链路全部通过，并确认原始 `explicit_bzero.c` 的 host-header 阻塞仍单独保留。
