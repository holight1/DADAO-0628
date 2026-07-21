# ML-016s 独立 Review

日期：2026-07-21（Asia/Shanghai）  
结论：**Accepted-with-findings**

## 审查范围

独立核对了 `/tmp/ml-016s-post-fix-musl-object-matrix-20260721/` 的 targets、逐对象
results、compiler records、artifact inventory、cluster 汇总及 metadata；未访问或引用
`~/toolchain`、`~/knowledge-graph`，未修改 LLVM/musl/build/archive、测试或规范。

用户指定的任务说明路径
`code-agent/tasks/ML-016s-post-fix-musl-object-matrix-20260721.md` 不存在；实际读取的是
同目录的 `ML-016s-post-fix-musl-object-matrix.md`。其 scope 与已有 dated review 一致，
但该路径问题记录为 finding。

## 独立核对结果

- `targets.all1347.txt` 为 1347 个唯一对象；priority 为 184、rest 为 1163，二者无交集且并集完整。逐对象结果为 1347 个唯一 output：`rc=0` 为 1165，`rc=1` 为 182，故 `1165+182=1347`。priority 阶段为 2/182，rest 阶段为 1163/0。
- 逐一重新计算了 1165 个成功 artifact 的 SHA-256、size、mtime：全部与 `results/object-results.tsv` 一致；成功行与实际 `.o` 集合双向相等，失败行无 artifact。configure 前后 object inventory 均为 0，实际 fresh `.o` 为 1165，未发现旧 `.o` 混入。
- 实际工具 hash 与记录一致，且 before/after 无变化：
  - clang：`9c5450b37bc3447879f247e435d611f545f49b240cba6a9ee8051176e31bdd71`
  - llc：`ed5bd8155a45b7b1b5933cb7505ef08abc5bb243dc945bbca13464ce4c15f8e3`
- 旧 7-cluster 逐对象 transition 与汇总一致：
  `unsupported library call operation` 157→157，machine verifier 16→16，dynamic_stackalloc 7→7，sign_extend_inreg 1→1，SelectionDAG illegal result 1→1；AsmPrinter 1→0、inline-asm constraint 1→0。旧 184 中正好 2 个成功：`__unmapself.o` 与 `explicit_bzero.o`；182 个仍失败。全量对比为 1163 个原成功 unchanged、182 个原失败 unchanged、2 个 fixed、0 regressions。
- fresh failure 仅包含上述五个旧簇，计数为 157/16/7/1/1；`new-clusters.tsv` 与 `fresh-new-unclassified.tsv` 均为空，无新簇。
- special objects 核对通过：
  `__unmapself.o` hash `b7782f168bea04ca4bfa68f8756b82fcbb2415263ad76b4a13223bddcace37ed`；
  `explicit_bzero.o` hash `38b9aba2d1cbbe1e89fa2366ff2ab58f13b156b638ede3c2e6b025805bb55ba3`；
  stdio 的 `__fdopen.o`、`fflush.o`、`fileno.o` 均成功，`puts.o` 仍为 sign_extend 簇，`vfprintf.o`/`vfscanf.o` 仍为 unsupported-library-call 簇。stdio 总计 116，成功 113、失败 3。

## Archive / link / runtime 边界

临时 build 实际 `.a/libc.a` 数量为 0；没有 archive 打包或主 archive 替换。没有执行完整 link、runtime、QEMU 或 gem5 验收。已有 review 对此没有错误宣称：明确将 archive、完整 libc linkability 和 runtime 留在后续 gate；单对象成功不能代表完整 libc。

## Findings

1. **任务说明路径不一致（低严重度）**：dated 文件不存在，只能读取无日期后缀的实际任务文件。建议补齐调用方引用或统一文件名。
2. **两条汇编对象的逐对象元数据不完整（低严重度）**：`obj/src/thread/dadao/__set_thread_area.o` 与 `obj/src/thread/dadao/get_tp.o` 的 TSV `input_source`/`source_sha256` 为缺失或错位，record 的 `input_source` 也为空；但 record 的真实 argv 明确指向对应 `.s` 文件，两个 artifact 的 rc、实际 hash、mtime 和 fresh 校验均通过。因此不影响本次 1347-object 编译结论，但应修正 collector 的汇编源路径记录。

除上述审计 findings 外，1347 object 结果、hash、旧簇 transition、新鲜 failure clusters、special objects、stdio 113/116 及 archive/link/runtime 边界均得到独立支持。  

**最终结论：Accepted-with-findings。**
