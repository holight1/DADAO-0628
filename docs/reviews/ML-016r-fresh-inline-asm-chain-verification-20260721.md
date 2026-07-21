# ML-016r fresh clang→llc inline-asm chain verification

日期：2026-07-21（Asia/Shanghai）  
范围：只验证 DADAO inline-asm hook 的 fresh CodeGen chain；不验证 ABI、libc
archive、runtime、QEMU 或 gem5。

## 结论

ML-016q 修复后的当前新 clang 和 llc 完成了 include-free 等价 source 的
O0/O3 fresh IR→backend asm→finalize-isel MIR 链路。explicit_bzero 等价 source
两档优化均 frontend/backend/MIR rc=0，并实际生成 asm 和 MIR。

这不是原始 `explicit_bzero.c` 的新 clang 全链路成功：原始 source 的 O0/O3
fresh clang IR 以及 direct clang backend 均因 host `<string.h>` 依赖失败，rc=1；
原始 stderr 已保留，结论单独列出。

## 工作区与工具

所有本轮 source、IR、asm、MIR、脚本和日志均在
[`/tmp/ml-016r-fresh-inline-asm-chain-verification-20260721/`](/tmp/ml-016r-fresh-inline-asm-chain-verification-20260721/)。

工具记录：

- clang：`/home/holight/DADAO-0628/.work/build/llvm/bin/clang`，clang 22.1.8，
  commit `10690fc4d40dd7d30757b344c2e259cd9c89a5c4`，SHA-256
  `9c5450b37bc3447879f247e435d611f545f49b240cba6a9ee8051176e31bdd71`。
- llc：`/home/holight/DADAO-0628/.work/build/llvm/bin/llc`，LLVM 22.1.8，
  registered target `dadao`，SHA-256
  `ed5bd8155a45b7b1b5933cb7505ef08abc5bb243dc945bbca13464ce4c15f8e3`。

完整版本输出见 [`tool-versions.txt`](/tmp/ml-016r-fresh-inline-asm-chain-verification-20260721/logs/metadata/tool-versions.txt)，哈希见 [`tool-hashes.tsv`](/tmp/ml-016r-fresh-inline-asm-chain-verification-20260721/logs/metadata/tool-hashes.tsv)。每条命令的逐参数 argv、rc、stdout、stderr 按 phase 保存在 `logs/frontend`、`logs/backend`、`logs/mir` 和 `logs/original`。

## 等价 source

原始 source [`explicit_bzero.c.original`](/tmp/ml-016r-fresh-inline-asm-chain-verification-20260721/probes/source/explicit_bzero.c.original) 与仓库 source 以及 ML-016o 原始副本 `cmp` rc=0，保留了原始缩进和语句。

include-free source [`explicit_bzero.include-free.c`](/tmp/ml-016r-fresh-inline-asm-chain-verification-20260721/probes/source/explicit_bzero.include-free.c) 只移除 host header 阻塞，并显式提供原语句所需的两个声明：`typedef __SIZE_TYPE__ size_t` 和 `extern void *memset(void *, int, size_t)`。以下项目逐项保留：

| 项目 | 原始 / 等价 source |
|---|---|
| feature macro | `_BSD_SOURCE` |
| function | `void explicit_bzero(void *d, size_t n)` |
| memory operation | `d = memset(d, 0, n);` |
| asm template | empty string `""` |
| asm qualifier | `__asm__ __volatile__` |
| input constraint | `"r"(d)` |
| clobber | `"memory"` |

理由和原始 source 说明保存在 [`source-rationale.md`](/tmp/ml-016r-fresh-inline-asm-chain-verification-20260721/source-rationale.md)。该 source 是 inline-asm hook 的等价 CodeGen reproduction，不被当作原始文件编译成功。

## Fresh explicit_bzero chain

| source / opt | clang IR | llc asm | llc finalize-isel MIR | 关键证据 |
|---|---:|---:|---:|---|
| include-free / O0 | 0 | 0 | 0 | [`IR`](/tmp/ml-016r-fresh-inline-asm-chain-verification-20260721/probes/ir/explicit_bzero.O0.ll), [`asm`](/tmp/ml-016r-fresh-inline-asm-chain-verification-20260721/probes/asm/explicit_bzero.O0.s), [`MIR`](/tmp/ml-016r-fresh-inline-asm-chain-verification-20260721/probes/mir/explicit_bzero.O0.mir) |
| include-free / O3 | 0 | 0 | 0 | [`IR`](/tmp/ml-016r-fresh-inline-asm-chain-verification-20260721/probes/ir/explicit_bzero.O3.ll), [`asm`](/tmp/ml-016r-fresh-inline-asm-chain-verification-20260721/probes/asm/explicit_bzero.O3.s), [`MIR`](/tmp/ml-016r-fresh-inline-asm-chain-verification-20260721/probes/mir/explicit_bzero.O3.mir) |

两档 fresh IR 均保留 inline asm constraint `"r,~{memory}"(ptr ...)`；O0 MIR 中为
`INLINEASM ... reguse:GPRD`，backend asm 中实际有 `#APP` / `#NO_APP`。每条命令的原始记录在对应的 `logs/frontend/explicit_bzero.O*.{argv,rc,stdout,stderr}`、`logs/backend/...` 和 `logs/mir/...`。

## r / memory / no-operand fresh matrix

完整索引为 [`fresh-matrix.tsv`](/tmp/ml-016r-fresh-inline-asm-chain-verification-20260721/logs/metadata/fresh-matrix.tsv)。共 22 个 case、O0/O3 共 44 条完整链路，全部 frontend/backend/MIR rc=0，并生成 asm/MIR：

- pointer `r` input；i64 scalar `r` input、`=r` output、`+r` inout；
- u8/u16/u32/u64 的 `r` input、output、inout；
- memory `m`、`=m`、`+m` input/output/inout；
- no-operand empty asm 以及 `trap 2, 0`。

代表性 fresh IR 保留 clang lowering 的 `r`、`=r`、`=r,0` 和 memory 约束；对应 MIR 分别显示 `reguse:GPRD`、`regdef:GPRD`、tied `reguse` 和 `mem:m`。无操作数 MIR 没有 register operand。

## 原始 source 的明确阻塞

原始 source 的 O0/O3 fresh clang IR 与 direct clang backend 记录见
[`original-host-header.tsv`](/tmp/ml-016r-fresh-inline-asm-chain-verification-20260721/logs/metadata/original-host-header.tsv)。四条命令均 rc=1，raw stderr 位于 `logs/original`，典型内容为：

```text
In file included from .../explicit_bzero.c.original:2:
/usr/include/string.h:26:10: fatal error: 'bits/libc-header-start.h' file not found
```

因此本报告只把 include-free source 的成功归因于 ML-016q hook 在等价 inline-asm 形状上的 fresh 验证；不宣称原始 `explicit_bzero.c` 已完成新 clang→llc 全链路。

## 范围与未修改面

本轮只在指定 `/tmp` 目录写入验证证据，并更新 ML-016r task 完成区和本 review
文档；未修改 LLVM、musl、主 build/archive、测试、规范、QEMU、gem5、contracts、
vectors、issues、wiki 或 ML-014a，也未回滚其他 worker 的改动。
