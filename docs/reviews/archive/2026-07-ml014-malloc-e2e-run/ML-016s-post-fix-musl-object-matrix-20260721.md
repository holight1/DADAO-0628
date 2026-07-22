# ML-016s post-fix musl object matrix review

日期：2026-07-21（Asia/Shanghai）  
范围：只验证修复后新 clang 的 musl object 编译矩阵；不打包 archive，不做主 archive
替换，不做 link、runtime、QEMU 或 gem5 验收。

## 结论

在全新隔离 source/build 中完成了旧 184 failures 优先批次和完整 1347-object matrix。
新鲜结果为 **1165 成功、182 失败**，相对 ML-016f 的 1163/184 减少两个失败；
没有成功对象回归，也没有出现新的 failure cluster。

这不是完整 libc archive 或 runtime acceptance。剩余 182 个失败仍覆盖五个旧簇，
所以当前应继续 backend 修复；只有在 object matrix 完整后，才进入受控 archive，再做
完整 link/runtime 复验。已成功的单对象可以做目标化 link 复验，但不能代表完整 libc。

## 隔离边界与工具

所有新 source、build、object、log、summary 和脚本位于
[`/tmp/ml-016s-post-fix-musl-object-matrix-20260721/`](/tmp/ml-016s-post-fix-musl-object-matrix-20260721/)。
source commit 为 `4741d4d1105849adf551a7998503866ed4f8b961`，source status clean；
configure 使用 `--target=dadao --disable-shared`，新 config 位于
[`build/config.mak`](/tmp/ml-016s-post-fix-musl-object-matrix-20260721/build/config.mak)。

固定工具：

| tool | path | version | SHA-256 |
|---|---|---|---|
| clang | `/home/holight/DADAO-0628/.work/build/llvm/bin/clang` | clang 22.1.8，version commit `10690fc4d40dd7d30757b344c2e259cd9c89a5c4` | `9c5450b37bc3447879f247e435d611f545f49b240cba6a9ee8051176e31bdd71` |
| llc | `/home/holight/DADAO-0628/.work/build/llvm/bin/llc` | LLVM 22.1.8，registered target `dadao` | `ed5bd8155a45b7b1b5933cb7505ef08abc5bb243dc945bbca13464ce4c15f8e3` |

版本、二进制 mtime/hash 和前后稳定性证据在
[`logs/metadata/tool-versions.before-matrix.txt`](/tmp/ml-016s-post-fix-musl-object-matrix-20260721/logs/metadata/tool-versions.before-matrix.txt)、
[`tool-hashes.before-matrix.tsv`](/tmp/ml-016s-post-fix-musl-object-matrix-20260721/logs/metadata/tool-hashes.before-matrix.tsv)、
[`tool-hashes.after-matrix.tsv`](/tmp/ml-016s-post-fix-musl-object-matrix-20260721/logs/metadata/tool-hashes.after-matrix.tsv)。
hash stability 为 `rc=0`。configure 原始 `rc=0`；configure 前后 object inventory
均为 0，见 `logs/configure.rc` 和 `logs/initial-object-inventory.*`。

## 执行与逐对象证据

旧失败对象先以 184 个显式 object target 执行：
[`logs/priority184/make.rc`](/tmp/ml-016s-post-fix-musl-object-matrix-20260721/logs/priority184/make.rc)
为 `rc=2`。该批次有 184 条新 compiler record，2 条 `rc=0`、182 条 `rc=1`。
其余 1163 个对象随后执行：
[`logs/rest1163/make.rc`](/tmp/ml-016s-post-fix-musl-object-matrix-20260721/logs/rest1163/make.rc)
为 `rc=0`，1163 条全部成功。

最终索引 [`results/object-results.tsv`](/tmp/ml-016s-post-fix-musl-object-matrix-20260721/results/object-results.tsv)
共有 1347 条对象记录、1347 个唯一 output、0 个重复 output。每一行含 phase、对象
路径、原始 rc、stderr 路径、record/argv 路径、argv SHA-256、artifact 存在性、artifact
大小、mtime、SHA-256、freshness 和 signature；原始逐参数 argv/rc/stderr 保存在
[`logs/compiler/`](/tmp/ml-016s-post-fix-musl-object-matrix-20260721/logs/compiler)。
矩阵完整性汇总在
[`results/matrix-integrity.txt`](/tmp/ml-016s-post-fix-musl-object-matrix-20260721/results/matrix-integrity.txt)：
初始 object 数为 0，最终 artifact 数为 1165，成功行缺 artifact 数为 0，成功行非
fresh 数为 0，隔离 `libc.a` 存在标志为 0。

因此没有旧 `.o` 被当作修复后结果：build 从无 object 开始，所有成功记录都对应本轮
新产物，失败对象没有产物 hash/mtime 可冒充成功。

## 旧 7 簇 transition

| ML-016f cluster | old failures | fixed | still same cluster | new/changed |
|---|---:|---:|---:|---:|
| unsupported library call operation | 157 | 0 | 157 | 0 |
| machine verifier: undefined physical register | 16 | 0 | 16 | 0 |
| Cannot select: dynamic_stackalloc | 7 | 0 | 7 | 0 |
| Cannot select: sign_extend_inreg from i1 | 1 | 0 | 1 | 0 |
| DADAO AsmPrinter: unknown operand type | 1 | 1 | 0 | 0 |
| SelectionDAG assertion: illegal result number | 1 | 0 | 1 | 0 |
| inline asm: input register constraint allocation | 1 | 1 | 0 | 0 |
| **total** | **184** | **2** | **182** | **0** |

两个成功转移为 `__unmapself.o`（AsmPrinter 单例）和 `explicit_bzero.o`（inline-asm
`r` constraint 单例）。完整逐对象映射见
[`results/old-7-cluster-comparison.tsv`](/tmp/ml-016s-post-fix-musl-object-matrix-20260721/results/old-7-cluster-comparison.tsv)，
汇总见 [`old-7-cluster-summary.tsv`](/tmp/ml-016s-post-fix-musl-object-matrix-20260721/results/old-7-cluster-summary.tsv)。
修复后 failure signature 总表见
[`results/fresh-cluster-summary.tsv`](/tmp/ml-016s-post-fix-musl-object-matrix-20260721/results/fresh-cluster-summary.tsv)。

## Special objects

| object | rc | result | new artifact SHA-256 |
|---|---:|---|---|
| `obj/src/thread/__unmapself.o` | 0 | success | `b7782f168bea04ca4bfa68f8756b82fcbb2415263ad76b4a13223bddcace37ed` |
| `obj/src/string/explicit_bzero.o` | 0 | success | `38b9aba2d1cbbe1e89fa2366ff2ab58f13b156b638ede3c2e6b025805bb55ba3` |
| `obj/src/stdio/__fdopen.o` | 0 | success | `74b7735d4cb5fb25ea4a9532f5a2a7e9204f0aa9f0c57196e19afa2f2303eec0` |
| `obj/src/stdio/fflush.o` | 0 | success | `ac4247a682b3049ae0e4f82e664a11e44e52aedb8b9ba1d87cd41fe75bb56494` |
| `obj/src/stdio/fileno.o` | 0 | success | `b679aa4fc1908dcd7a6d89252373cb5eeb5b0231b933381a91761e00104e53eb` |
| `obj/src/stdio/puts.o` | 1 | `Cannot select: sign_extend_inreg from i1` | absent |
| `obj/src/stdio/vfprintf.o` | 1 | `unsupported library call operation` | absent |
| `obj/src/stdio/vfscanf.o` | 1 | `unsupported library call operation` | absent |

stdio 总体为 116 个对象、113 成功、3 失败。全量 stdio 记录见
[`results/stdio-object-results.tsv`](/tmp/ml-016s-post-fix-musl-object-matrix-20260721/results/stdio-object-results.tsv)，
并含在 [`results/special-objects.tsv`](/tmp/ml-016s-post-fix-musl-object-matrix-20260721/results/special-objects.tsv)。
这些是编译结果，不是 archive symbol、link 或 runtime 结果。

## Archive / link / runtime gate

- **Archive：不可进入。** 本轮明确没有打包 isolated archive，更没有替换主 archive；
  且 182 个 backend failures 使完整 object 集合仍不可用。
- **Link：仅可进入目标化复验。** 已成功的单对象（包括 `__unmapself`、
  `explicit_bzero` 和三个 stdio 关键对象）可作为后续受控 link probe 输入；本轮未执行
  link，不能宣称完整 libc linkability。
- **Runtime：不可进入完整验收。** 没有完整 archive/full link，也没有 runtime、QEMU
  或 gem5 执行；需先处理剩余 backend 簇，完成受控 archive 和完整 link 后再验 runtime。

本轮最终建议是继续 backend 修复，优先处理剩余五簇；之后重新做全矩阵，再受控重建
archive，最后进入完整 link/runtime 复验。
