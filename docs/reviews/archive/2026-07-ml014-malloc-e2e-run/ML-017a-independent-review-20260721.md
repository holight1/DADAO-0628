# ML-017a 独立 Review

日期：2026-07-21（Asia/Shanghai）  
范围：审阅 ML-017a task、既有 review，以及
`/tmp/ml-017a-post-frame-musl-matrix-20260721/` 的逐对象结果、hash、record 和阶段日志。
未修改 LLVM、musl、QEMU、Gem5、spec、launcher 或 tracker；未查阅或引用
`~/toolchain`、`~/knowledge-graph`。

## 结论

**Accepted-with-findings**。

本轮 fresh 1347-object ledger 及其有限范围内的静态结论成立；既有报告没有把
ML-016f→post 的三个历史迁移冒充成 ML-016u→post 迁移，archive/link/runtime 边界也
写得正确。

但有一个 **blocking finding（针对“frame-only 无回归”归因）**：记录中的 ML-016u
baseline 工具身份是 LLVM revision `40bc313742b00848d341e77e1a38441211971729`
（clang/llc hash 为
`d1c6e0026741e45f7ae98f13d4057a6838f9ef049d6b9d110152a2f90ce94bdc` /
`ac7a71404061254b68f7d43cd343f4b121952af77b0ef7cb2428a15231ad2f9c`），而本轮是
final HEAD `d3bd9c15434fd7a48c0b7bab87354778cd932a72`（clang/llc hash 为
`64a8067ec4de0794ad137919565ec7d632631719d2d6f9ef8a3357068ad743e6` /
`3feb59bfc2bf46efd86510b56387c6e98f9e0c4496042b4574e28b61ec7ff6be`）。独立检查
nested LLVM 图得到
`40bc -> be99 -> d3bd`；`be99` 是 d3bd 的父提交。故“相对记录中的 ML-016u
结果 0 回归/0 迁移”是可复算的跨 revision 事实，但不是仅隔离 d3bd frame commit
的 parent-vs-child 实验。应补充 be99 parent baseline，或明确把主张限定为
“相对记录中的 ML-016u aggregate baseline 无迁移”。

除此之外没有额外 non-blocking finding。

## 独立核对结果

### Identity、freshness 与计数

- 当前 nested LLVM detached clean HEAD 为 `d3bd9c15434fd7a48c0b7bab87354778cd932a72`，
  parent 为 `be99e5505abe341100c62d70cd955b2df7e4711e`；musl source clean commit 为
  `4741d4d1105849adf551a7998503866ed4f8b961`。
- 当前 clang、llc、frame source、frame regression、musl configure 及 selected source
  hashes 与 [`provenance/`](</tmp/ml-017a-post-frame-musl-matrix-20260721/logs/provenance/>)
  一致；before/after tool hash 也一致。逐对象 source hash 重算无 mismatch。
- [`evidence-sha256.txt`](</tmp/ml-017a-post-frame-musl-matrix-20260721/results/evidence-sha256.txt>)
  共 4,554 条，独立 `sha256sum -c` 结果为 `OK=4554, FAILED=0, NOT FOUND=0`。
- [`targets.all1347.txt`](</tmp/ml-017a-post-frame-musl-matrix-20260721/results/targets.all1347.txt>)
  为 1,347 行且唯一；fresh result 为 1,347 行且 output 唯一 1,347。
- 逐对象重算得到 `rc=0: 1166`、`rc=1: 181`，故 `1166+181=1347`。成功对象实际
  artifact hash、fresh 标志、失败对象无残留 artifact 均通过独立检查。

### Baseline provenance 与迁移

ML-016u 的记录确实是同一 musl source commit/configure/source hash，且有 1,347 个
逐对象结果。把 ML-016u 的 `rc`、canonical signature 与 fresh 结果逐对象对齐，得到：

```text
source-hash mismatches       0
row mismatches               0
success -> failure            0
failure -> success            0
```

因此 **ML-016u→post 的 0 回归/0 迁移本身正确**。同时，
[`compare-ml016f-to-post.summary.tsv`](</tmp/ml-017a-post-frame-musl-matrix-20260721/results/compare-ml016f-to-post.summary.tsv>)
正确给出 ML-016f→post 的 `1163 unchanged success + 3 fixed + 181 unchanged failure`；
三个对象为：

- `obj/src/stdio/puts.o`
- `obj/src/string/explicit_bzero.o`
- `obj/src/thread/__unmapself.o`

这三项在 ML-016u baseline 已经是 success，所以没有被计入 ML-016u→post transition。
该项没有发现“把三项混淆成 ML-016u baseline transition”的错误。

需要保留的 blocking finding 是实验归因，而不是对象账本错误：ML-016u 证据中的工具
版本/哈希见其 `logs/metadata/tool-versions.before.txt` 和
`tool-hashes.before.tsv`，记录的是 40bc/d1c6/ac7a；当前 final 证据见
[`nested-head-status.txt`](</tmp/ml-017a-post-frame-musl-matrix-20260721/logs/provenance/nested-head-status.txt>)
和 `key-source-and-tool-sha256.txt`。在没有 be99 baseline 的情况下，不能把零迁移
表述为 d3bd frame rounding commit 的完全因果隔离。

### 181 failures、stdio 与 prologue

[`fresh-failure-clusters.tsv`](</tmp/ml-017a-post-frame-musl-matrix-20260721/results/fresh-failure-clusters.tsv>)
逐对象复算为四簇，合计 181：

| canonical signature | count |
|---|---:|
| unsupported library call operation | 157 |
| machine verifier: undefined physical register | 16 |
| Cannot select: dynamic_stackalloc | 7 |
| SelectionDAG assertion: illegal result number | 1 |

每个失败对象都有 stderr 和 record；stderr fingerprint 与结果表一致。`intscan.o` 的
原始 stderr 使用的是 `Illegal result number!` assertion 文本，属于结果表中的同一
canonical signature，非额外第五簇。

stdio 逐对象表独立重算为 **114 success / 2 failure / 116 total**；唯一失败为
`vfprintf.o` 与 `vfscanf.o`，均为 unsupported library call operation。114 个 fresh
stdio artifact 的 static objdump 均 `rc=0`，frame adjustment 非对齐数为 0，窄于 8
的 emitted adjustment 为 0。

边界对象的保存 disassembly 直接显示：`_Exit.o` 为 `-8`，其 `__syscall1` 为
`-40`；`exit.o` 为 `-8/-16`；`puts.o` 为 `-40`；`fputs.o` 为 `-24`；
`__stdio_exit.o` 为 `-8/-8`。这些证据支持静态 emitted prologue/frame-alignment
结论，不支持 link 或 runtime 结论。

### `make rc=2` 的含义

阶段日志记录的命令是 `make -k -j6`，target count 为 1,347，阶段 `rc=2`。逐对象
结果同时记录 1,166 个成功编译和 181 个对象级失败，`make.stderr` 中是逐对象 backend
diagnostic 以及对应的 `make: *** ... Error 1`。因此将 `rc=2` 解释为存在失败对象的
aggregate make status 是准确的；它不等价于 configure 失败或整个工具链不可用。
失败的 clang invocation 本身可以出现 backend assertion/fatal error，但其余 1,166
个对象成功，不能将阶段 rc 简化为整体工具链崩溃。

## Gate 边界

本轮没有生成或验证完整 archive，没有完整 libc link、runtime、QEMU 或 Gem5 验收。
`1166/181` 只证明 fresh object compile matrix 的结果，不证明完整 libc 可归档、可
链接或可运行。既有报告提出的下一步 targeted archive/link/QEMU gate 可以保留，但
必须继续限定为 fresh 成功对象和显式 probe；完整 gate 仍被 181 个 failures 阻塞。

## 判定与修复要求

接受当前 fresh ledger、failure/stdio/prologue 证据和边界结论；在将本轮作为
“frame rounding commit 的 frame-only regression acceptance”使用前，补充 be99 parent
baseline 的 tool/source provenance，或修正文案，明确当前结论只针对记录中的
ML-016u aggregate baseline。 
