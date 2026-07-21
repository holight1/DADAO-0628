# ML-016r 独立 review

日期：2026-07-21（Asia/Shanghai）  
结论：**Accepted**

## 审查范围

独立阅读了 `code-agent/tasks/ML-016r-fresh-inline-asm-chain-verification.md`、
`docs/reviews/ML-016r-fresh-inline-asm-chain-verification-20260721.md`，并抽查
`/tmp/ml-016r-fresh-inline-asm-chain-verification-20260721/` 的 source、rationale、
metadata、逐命令日志和 IR/asm/MIR 产物。审查未越出上述指定范围，未修改 LLVM、
musl、build/archive、测试或规范。

## Source 与等价性

- `probes/source/explicit_bzero.c.original` 与
  `.work/source/musl/src/string/explicit_bzero.c`、ML-016o 的
  `probes/source/explicit_bzero.c.original` 均 `cmp` rc=0；SHA-256 均为
  `fbd2b46b1b8ca5ad1f47476741eb552beb8b12b9dff9ce2a773f747e1ea07189`。
- `explicit_bzero.include-free.c` 保留 `_BSD_SOURCE`、函数签名、`d = memset(d, 0, n)`
  的顺序、空字符串 asm、`__asm__ __volatile__`、`"r"(d)` input 和 `"memory"`
  clobber。它只移除会触发 host-header 问题的 `#include <string.h>`，并以
  `typedef __SIZE_TYPE__ size_t` 和 `extern void *memset(void *, int, size_t)`
  提供该语句所需声明。
- `source-rationale.md` 与既有报告的逐项对照覆盖了上述 feature macro、签名、
  memory operation、asm template/qualifier、constraint、clobber 及顺序理由。
  因此该文件可作为 inline-asm hook 的 include-free CodeGen reproduction，但不
  等同于原始 source 的成功编译；报告对此边界表述正确。

## Fresh chain 与矩阵

- `fresh-matrix.tsv` 有 22 个 case、O0/O3 共 44 行；frontend、backend 和
  `-stop-after=finalize-isel` MIR 各有 44 个 `.rc`，全部为 `0`。对应 44 个 IR、
  44 个 asm、44 个 MIR 文件均存在且非空。
- 抽查 explicit_bzero O0/O3：IR 均保留
  `asm sideeffect "", "r,~{memory}"(ptr ...)`；MIR 均有
  `INLINEASM` 与 `reguse:GPRD`；asm 均有 `#APP`/`#NO_APP`。
- 抽查 pointer/i64 input、output、tied inout、memory `m`/`=m`/`+m`、无操作数和
  `trap 2, 0`，以及 u8/u16/u32/u64 的 input/output/inout：IR 约束、MIR 的
  `reguse:GPRD`/`regdef:GPRD`/tied operand/`mem:m` 和 asm 输出均相互对应。
- 每条成功命令均有逐参数 argv、rc、stdout、stderr；frontend/backend/MIR 各
  44 组日志齐全且成功 stderr 为空。width case 的 `-DPROBE_WIDTH=8/16/32/64`
  也与 source/矩阵条目对应。

## 工具元数据

记录的 clang/llc 路径、版本和 hash 均可复核：clang 为 22.1.8、LLVM commit
`10690fc4d40dd7d30757b344c2e259cd9c89a5c4`，hash
`9c5450b37bc3447879f247e435d611f545f49b240cba6a9ee8051176e31bdd71`；llc 为
LLVM 22.1.8、registered target `dadao`，hash
`ed5bd8155a45b7b1b5933cb7505ef08abc5bb243dc945bbca13464ce4c15f8e3`。当前二进制
重新计算的 SHA-256 与 `tool-hashes.tsv` 一致，`tool-versions.txt` 与当前版本输出
一致。

## Original source host-header 阻塞与报告边界

`logs/metadata/original-host-header.tsv` 的 O0/O3 frontend 和 direct clang backend
四次尝试均为 `rc=1`。四份 raw stderr 均保留同一阻塞：

`/usr/include/string.h:26:10: fatal error: 'bits/libc-header-start.h' file not found`

四个 stdout 为空，原始 IR/asm 输出不存在。既有报告明确把成功归于
`explicit_bzero.include-free.c` 的 fresh 等价复现，并明确写出这不是原始
`explicit_bzero.c` 的新 clang 全链路成功；没有将 include-free 成功冒充为原始
source 成功。

## Findings

无阻断性或准确性 finding。证据、数量、rc、工具元数据和 host-header 失败边界均
与既有报告及任务要求一致。
