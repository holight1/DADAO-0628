# ML-016g backend failure cluster

日期：2026-07-21（Asia/Shanghai）

## 阶段性结论

已完成 184 个失败对象的只读聚类；本报告不预置 Accepted。原始对象 rc 全部保留为 rc=1，原始 stderr 和 record 路径未被压缩或替换。

复核入口：

- 聚类脚本：/tmp/ml016g_cluster.py
- 全量逐对象结果：[/tmp/ml-016g-backend-failure-cluster-20260721/all-failures.tsv](/tmp/ml-016g-backend-failure-cluster-20260721/all-failures.tsv)
- 机器输入：[/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/results/object-results.tsv](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/results/object-results.tsv)
- 失败输入：[/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/results/object-results.failed.tsv](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/results/object-results.failed.tsv)

## 统计与簇

全量对象为 1347：成功 1163、失败 184。稳定签名为 7；frontend rc 为 70:181、134:2、未报告:1；最终优化级别为 -O0:165、-O3:19。

| 稳定签名 | 数量 | 阶段 | 失败 family |
|---|---:|---|---|
| unsupported library call operation | 157 | DAG instruction selection | math 127, complex 22, internal 1, legacy 1, stdio 2, stdlib 2, prng 1, time 1 |
| machine verifier: undefined physical register | 16 | register allocation | string 15, malloc 1 |
| Cannot select: dynamic_stackalloc | 7 | DAG instruction selection | process 4, locale 1, network 1, unistd 1 |
| Cannot select: sign_extend_inreg from i1 | 1 | DAG instruction selection | stdio 1 |
| DADAO AsmPrinter: unknown operand type | 1 | DADAO AsmPrinter | thread 1 |
| SelectionDAG assertion: illegal result number | 1 | SelectionDAG assertion | internal 1 |
| inline asm: input register constraint allocation | 1 | inline-asm constraint allocation | string 1 |

逐簇完整对象清单（每行带 source、function、rc、stderr_saved、record_file）：

- [簇 01，157](/tmp/ml-016g-backend-failure-cluster-20260721/cluster-objects-01-unsupported-library-call-operation.tsv)
- [簇 02，16](/tmp/ml-016g-backend-failure-cluster-20260721/cluster-objects-02-machine-verifier-undefined-physical-register.tsv)
- [簇 03，7](/tmp/ml-016g-backend-failure-cluster-20260721/cluster-objects-03-cannot-select-dynamic-stackalloc.tsv)
- [簇 04，1](/tmp/ml-016g-backend-failure-cluster-20260721/cluster-objects-04-cannot-select-sign-extend-inreg-from-i1.tsv)
- [簇 05，1](/tmp/ml-016g-backend-failure-cluster-20260721/cluster-objects-05-dadao-asmprinter-unknown-operand-type.tsv)
- [簇 06，1](/tmp/ml-016g-backend-failure-cluster-20260721/cluster-objects-06-selectiondag-assertion-illegal-result-number.tsv)
- [簇 07，1](/tmp/ml-016g-backend-failure-cluster-20260721/cluster-objects-07-inline-asm-input-register-constraint-allocation.tsv)

全量 family 统计在 [family-total-clusters.tsv](/tmp/ml-016g-backend-failure-cluster-20260721/family-total-clusters.tsv)。失败最多的是 math 127/232、complex 22/68、string 16/74；这说明最大簇集中但不能代表全部 184。

## 代表性原始 stderr

- 最大簇：__cexp.o.stderr (/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/logs/compiler/compile_obj_src_complex___cexp.o_pid_567721.stderr)，首行是 fatal error: error in backend: unsupported library call operation，frontend rc=70。
- verifier：posix_memalign.o.stderr (/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/logs/compiler/compile_obj_src_malloc_posix_memalign.o_pid_571831.stderr)，raw machine code 报 undefined physical register $rb31，frontend rc=70。
- dynamic stack：dcngettext.o.stderr (/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/logs/compiler/compile_obj_src_locale_dcngettext.o_pid_571442.stderr)，报 Cannot select: dynamic_stackalloc，frontend rc=70。
- i1 select：puts.o.stderr (/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/logs/compiler/compile_obj_src_stdio_puts.o_pid_580046.stderr)，报 sign_extend_inreg i1，frontend rc=70。
- AsmPrinter：__unmapself.o.stderr (/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/logs/compiler/compile_obj_src_thread___unmapself.o_pid_582167.stderr)，报 lowerToMCInst: unknown operand type，frontend rc=134。
- SelectionDAG assertion：intscan.o.stderr (/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/logs/compiler/compile_obj_src_internal_intscan.o_pid_569898.stderr)，报 Illegal result number，frontend rc=134。
- inline asm：explicit_bzero.o.stderr (/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/logs/compiler/compile_obj_src_string_explicit_bzero.o_pid_580935.stderr)，报 constraint 'r' allocation failure；对象 rc=1，未生成 frontend summary。

## 只读 source/IR/backend 对照

隔离 config 和 argv 见 [config.mak](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/build/config.mak) 及对象 record，例如 [acos record](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/logs/compiler/compile_obj_src_math_acos.o_pid_572345.record)。10 个代表对象使用原始 argv 做 frontend-only -S -emit-llvm，全部 rc=0，证据在 [/tmp/ml-016g-backend-failure-cluster-20260721/ir-probes/](/tmp/ml-016g-backend-failure-cluster-20260721/ir-probes/)；所以这些失败发生在 frontend 可生成 IR 之后。

最大簇的 acos/exp/__cexp IR 含 f64 运算、llvm.fmuladd.f64 和 sqrt/exp/sin/cos 调用；当前只读 DADAOISelLowering.cpp:26 显式注册 i64 GPRD，未见 f32/f64 register class/action。此处是共同 capability/lowering 候选，但 raw stderr 没有具体 DAG node，不能声称 157 个对象只有一个精确根因。

dynamic_stackalloc 的 getcwd/dcngettext IR 均有 llvm.stacksave 与动态 alloca；source 也分别含 VLA。该簇应作为独立 stack/frame lowering 任务。

verifier 的 memmem/posix_memalign raw machine code 均在调用结果路径使用 undefined RB31。DADAOCallingConv.td 当前将 pointer return 分配至 RB31，而 DADAOInstrInfo.td 的 CALL_* Defs 为 RD31；这是 16 个失败的高价值候选，仍须用最小 pointer-return call 实验确认 call defs、liveness 和 indirect/direct call 是否同一问题。

其余四簇不能合并：puts 的 DAG 是 i1 sign extension；intscan IR 含 ctpop 和 umul.with.overflow 多结果值；explicit_bzero 保留 pointer inline-asm constraint；__unmapself 走 CRTJMP/特定 DADAO AsmPrinter operand。

## Accepted 前边界与后续修改面

独立 reviewer 至少应重跑 python3 /tmp/ml016g_cluster.py，核对 184/184 覆盖、7 簇计数、原始 stderr/record 引用和保护范围。下一轮修复应拆为：

1. 浮点/libcall：先以最小 f64/库调用 DAG reproducer 定位具体 operation，再修改 DADAO lowering/instruction selection 相关文件和对应 CodeGen tests。
2. dynamic stackalloc：最小 VLA/alloca reproducer，修改 frame/lowering 相关文件和 CodeGen test。
3. RB31：最小 pointer-return direct/indirect call，修改 calling convention/call instruction defs/liveness 相关文件和 CodeGen test。
4. 四个单例：分别处理 i1 sign extension、SelectionDAG assertion、CRTJMP AsmPrinter operand、inline-asm constraint；不得用一个 family 修复名义覆盖它们。

本轮未修改任何 LLVM/musl/实现文件；实际仓库修改仅为 ML-016g task 完成区与本 review 文档。修复后需重跑隔离 clean object matrix；本报告不把单对象成功、frontend-only IR rc=0 或 best-effort archive 等同于完整 libc.a/runtime acceptance。
