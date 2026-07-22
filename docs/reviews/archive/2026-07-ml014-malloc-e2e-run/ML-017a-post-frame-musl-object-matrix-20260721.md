# ML-017a post-frame-fix musl object matrix review

日期：2026-07-21（Asia/Shanghai）  
结论范围：只验证 final nested LLVM clang 对 fresh musl objects 的编译与静态 prologue；
没有 archive、完整 link/runtime、QEMU 或 Gem5 验收。

## 结论

frame rounding 修复在 musl object 层没有引入回归。使用 final HEAD
`d3bd9c15434fd7a48c0b7bab87354778cd932a72` 和 fresh isolated build，1347 objects
得到 **1166 success / 181 failure**。这与 ML-016u 的 **1166/181 逐对象完全一致**：
没有旧成功回归、没有旧失败迁移、没有新 cluster。

与 ML-016f 的 **1163/184** 相比，恰有三个旧失败成功：`puts.o`、`explicit_bzero.o`、
`__unmapself.o`。这三个 transition 不是 frame fix 本轮新产生的迁移，而是 ML-016p/q/t
修复链路此前已经在 ML-016u 中闭合；因此不能把 frame fix 记作又修复了这三个 backend
簇。

下一步可以进入受控 targeted archive/QEMU gate，但不能进入完整 libc archive、完整 link
或 runtime gate。

## Provenance 与隔离

nested LLVM `.work/source/llvm` 为 detached、clean HEAD：
`d3bd9c15434fd7a48c0b7bab87354778cd932a72`；nested musl source copy 为 clean
`4741d4d1105849adf551a7998503866ed4f8b961`。工具为：

| tool | version / VCS | SHA-256 |
|---|---|---|
| clang | 22.1.8，VCS `d3bd9c15434fd7a48c0b7bab87354778cd932a72` | `64a8067ec4de0794ad137919565ec7d632631719d2d6f9ef8a3357068ad743e6` |
| llc | LLVM 22.1.8，registered target `dadao` | `3feb59bfc2bf46efd86510b56387c6e98f9e0c4496042b4574e28b61ec7ff6be` |

关键 source hash：frame lowering `a3ed13fcc5f03765e6980936454b2761f72efd7b55b44b9261f025d6c9882e6b`，
frame regression `6e871fa22863278808e77c2acbc33142555d4dbeb54fe6c884cbc39d55eb4e80`，
musl `configure` `f911a9997e9ba565b9b8a25efa8bbd24dc7196b346a7122c6f06141fc19c5a37`。
全部 provenance 在 [`/tmp/ml-017a-post-frame-musl-matrix-20260721/logs/provenance/`](/tmp/ml-017a-post-frame-musl-matrix-20260721/logs/provenance/)。

隔离目录为 [`/tmp/ml-017a-post-frame-musl-matrix-20260721/`](/tmp/ml-017a-post-frame-musl-matrix-20260721/)，
没有使用旧 object 或 archive 替代新结果；build 从 0 个 `.o` 开始，未生成
`build/lib/libc.a`。

## Command / result evidence

实际阶段为：

```text
configure: CC=.../tools/record-clang AR=.../llvm-ar RANLIB=.../llvm-ranlib
           source/configure --target=dadao --disable-shared --prefix=.../install
           rc=0
matrix:    make -k -j6 <results/targets.all1347.txt>
           rc=2 (object backend failures)
static:    llvm-objdump --triple=dadao -d <fresh-object>
           rc=0 for every checked fresh object
```

阶段 stdout/stderr/rc：`logs/configure.{stdout,stderr,rc}` 和
`logs/matrix1347/{make.stdout,make.stderr,make.rc}`。逐对象 argv、stderr、stderr
fingerprint、rc、artifact mtime/hash 在：

- [`results/object-results.tsv`](/tmp/ml-017a-post-frame-musl-matrix-20260721/results/object-results.tsv)
- [`results/object-results.post-frame.enriched.tsv`](/tmp/ml-017a-post-frame-musl-matrix-20260721/results/object-results.post-frame.enriched.tsv)
- [`logs/compiler/`](/tmp/ml-017a-post-frame-musl-matrix-20260721/logs/compiler/)

完整性事实：1347 records、1347 unique outputs、1166 fresh `.o`、成功缺产物=0、成功
非 fresh=0、失败残留产物=0、重复 output=0、未分类 failure=0、isolated archive=0。
全量输出 hash 见 [`results/evidence-sha256.txt`](/tmp/ml-017a-post-frame-musl-matrix-20260721/results/evidence-sha256.txt)。

## Cluster comparison

### ML-016u → post-frame

逐项结果为 success unchanged=1166、failure unchanged same cluster=181；没有
`success→failure` 或 `failure→success`。post-frame clusters 为：

| signature | count | stage classification |
|---|---:|---|
| unsupported library call operation | 157 | DAG instruction selection |
| machine verifier: undefined physical register | 16 | register allocation / machine verifier |
| Cannot select: dynamic_stackalloc | 7 | DAG instruction selection |
| SelectionDAG assertion: illegal result number | 1 | SelectionDAG assertion |

每一行的 stderr fingerprint 是 stderr 文件的 SHA-256；簇与 stage 汇总见
[`failure-cluster-stage-summary.tsv`](/tmp/ml-017a-post-frame-musl-matrix-20260721/results/failure-cluster-stage-summary.tsv)。

### ML-016f → post-frame

| old cluster | old failures | fixed to success | same cluster | post total |
|---|---:|---:|---:|---:|
| unsupported library call operation | 157 | 0 | 157 | 157 |
| machine verifier: undefined physical register | 16 | 0 | 16 | 16 |
| dynamic_stackalloc | 7 | 0 | 7 | 7 |
| sign_extend_inreg from i1 | 1 | 1 | 0 | 0 |
| AsmPrinter unknown operand type | 1 | 1 | 0 | 0 |
| illegal result number | 1 | 0 | 1 | 1 |
| inline asm register constraint | 1 | 1 | 0 | 0 |

精确 per-object transition 在 [`compare-ml016f-to-post.with-header.tsv`](/tmp/ml-017a-post-frame-musl-matrix-20260721/results/compare-ml016f-to-post.with-header.tsv)，
摘要在 [`compare-ml016f-to-post.summary.tsv`](/tmp/ml-017a-post-frame-musl-matrix-20260721/results/compare-ml016f-to-post.summary.tsv)。

## Static prologue checks

stdio 116 项的编译结果为 114 success、2 failure；失败是 `vfprintf.o` 和 `vfscanf.o`
的 unsupported library call operation。114 个 fresh stdio object 的最终 objdump 均
`rc=0`，所有 frame adjustments 8-byte aligned，`<8` emitted adjustment=0，非对齐
adjustment=0。逐对象记录见 [`stdio-static-prologue.tsv`](/tmp/ml-017a-post-frame-musl-matrix-20260721/results/stdio-static-prologue.tsv)。

ML-016x `_Exit`/puts 边界对象的静态记录：

| object | emitted frame adjustments | static rc | aligned |
|---|---|---:|---|
| `obj/src/exit/_Exit.o` | `-8`, `-40` (`__syscall1`) | 0 | yes |
| `obj/src/exit/exit.o` | `-8`, `-16` | 0 | yes |
| `obj/src/stdio/puts.o` | `-40` | 0 | yes |
| `obj/src/stdio/fputs.o` | `-24` | 0 | yes |
| `obj/src/stdio/__stdio_exit.o` | `-8`, `-8` | 0 | yes |

这验证 emitted prologue 的 alignment 形状；不等价于 archive symbol resolution 或
runtime 行为。`_Exit` 的 raw narrow `int` local 现在对应 emitted `-8`，是静态
frame-rounding 观察，不是完整 `_Exit` gate。

## Facts, inferences, and failure boundaries

事实：post-frame 结果与 ML-016u 逐对象相同；失败簇没有新成员；stdio 和边界对象的
emitted frame adjustment 没有非 8-byte-aligned 值。

推断：在当前受控 object matrix 范围内，frame rounding fix 没有引入 musl-level
compile regression。由于 ML-016u 已包含 p/q/t 修复，post-frame 与 ML-016u 的零迁移是
判断无回归的主要依据；不能把 ML-016f→post 的三个历史迁移归因于 frame fix。

边界：

1. `i1` 失败不再出现，但 puts 的修复归属 ML-016t；本轮只观察到 unchanged。
2. 没有 tail-call assertion 新簇；ML-016k 的 explicit-tail repro 没有在本轮重跑，
   因而不声明所有 tail-call ABI 通过。
3. 157 个 unsupported library call 和 7 个 dynamic_stackalloc 仍是 backend blockers；
   frame rounding 不会替代 libcall/dynamic-stack 修复。
4. 本轮没有重新执行 final-head varargs link/runtime；不能从 1347 object matrix 宣称
   varargs runtime 或完整 libc runtime 通过。
5. 没有生成 archive、完整 link、QEMU/Gem5 或 launcher 结果；任何下一步 gate 都必须
   使用 fresh object hash 并显式限定 members。

## Gate recommendation

**允许：** 以本轮 1166 个 fresh 成功 object 为输入的 targeted archive/link probe，
以及选定 `_Exit`/puts 边界的 targeted QEMU gate。  
**不允许：** 完整 1347-member archive、完整 libc link、完整 runtime acceptance。

下一步应保存 targeted archive 的 member/object hash 对照，并在 QEMU gate 中单独记录
argv/stdout/stderr/rc/hash；若目标是完整 libc，必须先解决 181 failures 后重跑全矩阵。
