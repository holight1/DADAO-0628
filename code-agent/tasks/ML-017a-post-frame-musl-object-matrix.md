# ML-017a：post-frame-fix musl object matrix 回归

日期：2026-07-21（Asia/Shanghai）  
范围：nested LLVM final HEAD `d3bd9c15434fd7a48c0b7bab87354778cd932a72` 上的
fresh musl object 编译矩阵；不生成 archive，不做完整 link/runtime、QEMU 或 Gem5
验收。

## 状态

**Completed；measurement evidence ready，待独立 review。**

本任务只新增本文件和对应 review；未修改 ML-016/30-task tracker、生产源、QEMU/Gem5、
ABI/spec、launcher、docs/issues.yaml 或 wiki。主仓库原有未跟踪的
`code-agent/tasks/ML-014a-musl-e2e-malloc-printf.md` 保留不动；没有 nested LLVM commit。

## 目标与验收

- [x] 记录 nested LLVM HEAD/status、clang/llc VCS/version、工具与关键 source hashes。
- [x] 在 `/tmp/ml-017a-post-frame-musl-matrix-20260721/` 从空 build 开始，复用
  ML-016u/s 的受控 1347-object 方法。
- [x] 每个对象保留 fresh argv record、stage、rc、stderr、stderr SHA-256、产物 hash/mtime；
  阶段 stdout/stderr/rc 也保留在 `logs/matrix1347/`。
- [x] 精确对比 ML-016u `1166/181` 与 ML-016f `1163/184`，列出对象迁移和 clusters。
- [x] 检查 stdio 116 objects 与 ML-016x `_Exit`/puts 相关对象的静态 prologue 对齐。
- [x] 明确 archive/link/runtime/QEMU/Gem5 的边界和下一步 gate。

## 工具与 source identity

| 项目 | 事实 |
|---|---|
| nested LLVM | detached clean HEAD `d3bd9c15434fd7a48c0b7bab87354778cd932a72`，parent `be99e5505abe341100c62d70cd955b2df7e4711e` |
| clang | `/home/holight/DADAO-0628/.work/build/llvm/bin/clang`，22.1.8，VCS revision `d3bd9c15434fd7a48c0b7bab87354778cd932a72`，SHA-256 `64a8067ec4de0794ad137919565ec7d632631719d2d6f9ef8a3357068ad743e6` |
| llc | `/home/holight/DADAO-0628/.work/build/llvm/bin/llc`，LLVM 22.1.8，registered target `dadao`，SHA-256 `3feb59bfc2bf46efd86510b56387c6e98f9e0c4496042b4574e28b61ec7ff6be` |
| isolated musl | commit `4741d4d1105849adf551a7998503866ed4f8b961`，source copy clean |
| configure | `SHA-256 f911a9997e9ba565b9b8a25efa8bbd24dc7196b346a7122c6f06141fc19c5a37` |
| frame source | `SHA-256 a3ed13fcc5f03765e6980936454b2761f72efd7b55b44b9261f025d6c9882e6b` |
| frame regression | `SHA-256 6e871fa22863278808e77c2acbc33142555d4dbeb54fe6c884cbc39d55eb4e80` |

完整 provenance 在 [`/tmp/ml-017a-post-frame-musl-matrix-20260721/logs/provenance/`](/tmp/ml-017a-post-frame-musl-matrix-20260721/logs/provenance/)，
工具 before/after hash 相同。

## 运行结果

- configure 原始 `rc=0`；configure 前后 object inventory 均为 0。
- 1347/1347 个唯一 object 均有 fresh matrix record；matrix `make -k -j6` 原始
  `rc=2`，原因是对象编译失败。
- **1166 success / 181 failure**；成功对象缺 artifact=0，成功对象非 fresh=0，失败
  残留 artifact=0，重复 output=0，未分类 failure=0，isolated `libc.a`=0。
- 每个对象的结果、stage、stderr fingerprint、argv record 和 artifact hash 见
  [`object-results.post-frame.enriched.tsv`](/tmp/ml-017a-post-frame-musl-matrix-20260721/results/object-results.post-frame.enriched.tsv)。
- 原始索引为 [`object-results.tsv`](/tmp/ml-017a-post-frame-musl-matrix-20260721/results/object-results.tsv)，
  全量证据 hash 为 [`evidence-sha256.txt`](/tmp/ml-017a-post-frame-musl-matrix-20260721/results/evidence-sha256.txt)。

## 逐项 baseline 对比

相对 ML-016u 的 1166/181：

- 1166 个旧成功全部保持成功；181 个旧失败全部保持失败。
- 0 个 success→failure，0 个 failure→success，0 个 failure cluster 移动。
- 当前四个失败簇与 ML-016u 完全相同：unsupported library call operation=157、
  machine verifier undefined physical register=16、dynamic_stackalloc=7、
  SelectionDAG illegal result number=1。

相对 ML-016f 的 1163/184：

| ML-016f cluster | old | post success | post same cluster |
|---|---:|---:|---:|
| unsupported library call operation | 157 | 0 | 157 |
| machine verifier: undefined physical register | 16 | 0 | 16 |
| Cannot select: dynamic_stackalloc | 7 | 0 | 7 |
| Cannot select: sign_extend_inreg from i1 | 1 | 1 | 0 |
| DADAO AsmPrinter: unknown operand type | 1 | 1 | 0 |
| SelectionDAG assertion: illegal result number | 1 | 0 | 1 |
| inline asm: input register constraint allocation | 1 | 1 | 0 |
| **total** | **184** | **3** | **181** |

三个且仅三个历史 failure→success 对象为：

| object | ML-016f cluster | post result | fresh artifact SHA-256 |
|---|---|---|---|
| `obj/src/stdio/puts.o` | sign_extend_inreg from i1 | success | `f9129ef260649ef288f71991107342ff37b488683b3b0067feffc6c18b4aa41d` |
| `obj/src/string/explicit_bzero.o` | inline asm `r` constraint allocation | success | `8de63f49297b579bcadb6833678e433d279b9890eb33332da882e7c87bdce911` |
| `obj/src/thread/__unmapself.o` | DADAO AsmPrinter unknown operand type | success | `85e2c30d2e66637bd1474b226c264748e7dd9216c37514fed963bd9958fee0d6` |

因此 frame rounding fix 没有引入 musl object-level regression，也没有新 cluster；
但相对 ML-016u 的本轮 transition 是 **0**。puts/i1、explicit_bzero/inline-asm 和
__unmapself/AsmPrinter 的改善分别属于此前 ML-016t、ML-016q、ML-016p 修复链路。

## stdio 与静态 frame

stdio 116 objects 中 114 个编译成功，`vfprintf.o` 与 `vfscanf.o` 仍以
`unsupported library call operation` 失败。对 114 个 fresh `.o` 使用最终
`llvm-objdump --triple=dadao -d`，全部静态命令 `rc=0`：

- 所有观察到的 prologue frame adjustments 都是 8-byte aligned；非对齐 adjustment=0。
- 发出的 `<8` frame adjustment=0；也就是说没有把 raw narrow frame 以未取整值发出。
- 逐对象静态 stdout/stderr/rc/hash 在 [`logs/static-prologue/`](/tmp/ml-017a-post-frame-musl-matrix-20260721/logs/static-prologue/)，
  汇总在 [`static-prologue-summary.txt`](/tmp/ml-017a-post-frame-musl-matrix-20260721/results/static-prologue-summary.txt)。

ML-016x 相关对象的 fresh static prologue 也全部对齐：`_Exit.o` 为 `-8`、其
`__syscall1` 为 `-40`；`exit.o` 为 `-8/-16`；`puts.o` 为 `-40`；`fputs.o` 为
`-24`；`__stdio_exit.o` 为 `-8/-8`。详细 disassembly stdout/argv/rc/hash 见
[`ml016x-boundary-static-prologue.tsv`](/tmp/ml-017a-post-frame-musl-matrix-20260721/results/ml016x-boundary-static-prologue.tsv)。

这里的 `_Exit` 结论是静态 object/prologue 结论：它显示 4-byte `int` 触发的 raw
narrow-frame 形状现在发出 `-8`，不宣称 `_Exit` 已完成 link/runtime 验收。

## 边界

- **i1**：本轮没有 i1 failure cluster；puts 相对 ML-016f 已成功、相对 ML-016u
  unchanged。不能把它归因于 frame fix。
- **tail**：本矩阵没有 `LowerCall emitted a return value for a tail call!` 新簇；
  ML-016k 的显式 tail-call minimal repro 不是本轮复跑对象，不能由此宣称所有 tail-call
  形状通过。
- **libcall**：157 个 `unsupported library call operation` 仍在，主要覆盖 math/complex
  等对象；frame fix 没有消除 generated/unsupported libcall 边界。
- **dynamic stack**：7 个 dynamic_stackalloc failure 原样保留；没有动态 stack object
  的完整验证。
- **varargs**：本轮做的是 musl object compile matrix，没有额外 link/runtime varargs
  probe。ML-016z 的 final-head varargs 静态/运行证据不被本报告重新宣称；本报告只记录
  当前 musl matrix 没有因 frame fix 新增 varargs failure。
- **archive/link/runtime**：未打包或替换任何 archive，未做完整 link、runtime、QEMU
  或 Gem5；`1166/181` 不能代表完整 libc 可链接或可运行。

## 下一步 gate

结果支持进入下一步 **受控 targeted archive/QEMU gate**：只允许使用本轮 fresh、成功且
有 artifact hash 的对象，明确列出 archive members 和 link probe，随后对 `_Exit`/puts
等边界做目标化 QEMU 检查。当前仍不支持完整 1347-object archive、完整 libc link 或
runtime acceptance；进入完整 gate 前仍需处理 181 个 backend failures 并重跑矩阵。

详尽 review：[ML-017a post-frame musl object matrix review](../../docs/reviews/ML-017a-post-frame-musl-object-matrix-20260721.md)。
