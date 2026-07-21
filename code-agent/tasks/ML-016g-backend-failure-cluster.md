# ML-016g：LLVM DADAO backend 编译失败聚类

**日期**：2026-07-21

**状态**：Audit-accepted-with-findings（ML-016 新 30-task run：7/30）

## 背景

ML-016f 的隔离 musl clean build 中，1163 个 object 成功、184 个 object 因 LLVM
DADAO backend 失败；这阻止生成完整 libc.a。需要先从原始逐对象日志中聚类失败，
判断是少数共同 unsupported operation、特定 source family、编译参数/配置，还是
多个不相关问题，再决定修复任务。

## 目标与 ownership

worker 只做诊断，不改实现：

1. 读取 `/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/` 的逐对象结果、argv、
   stderr 和 source 路径，按稳定错误签名、目录/family、编译阶段聚类；给出总数、
   去重签名数、每簇对象清单和代表性原始 stderr。
2. 对最大/最关键簇做最小只读 source/IR/compile-command 对照，确认是否能映射到
   已有 backend capability、错误 lowering 或单个源代码模式；不得凭单个错误推出
   全部 184 个根因。
3. 给出下一步最小任务边界（例如 capability 修复、单一 builtin/lowering、配置
   拆分或逐簇处理），并明确哪些结论仍需实验。

## 约束

- 只写本 task 完成区和 `docs/reviews/ML-016g-backend-failure-cluster-20260721.md`；
  其他脚本/汇总放 `/tmp`。
- 不修改 LLVM、musl、主 build/archive、QEMU/gem5、contracts、vectors、issues、
  wiki 或 ML-014a。
- 不访问或引用 `~/toolchain`、`~/knowledge-graph`。
- 不使用 `|| true`；原始退出码和 stderr 必须保留，不能只报告聚类后的摘要。

## 完成区

### worker 交付（2026-07-21）

状态：诊断完成，待独立 review；不预置 Accepted。

本轮只读分析 /tmp/ml-016f-isolated-musl-clean-rebuild-20260721/；未修改 LLVM、musl、主 build/archive、QEMU/gem5、contracts、vectors、issues、wiki 或 ML-014a。仓库内只写本完成区和指定 review 文档；聚类脚本在 /tmp/ml016g_cluster.py，IR 对照脚本在 /tmp/ml016g_readonly_ir_probe.py。

统计：全量对象 1347，成功 1163，失败 184；失败对象 rc 全部为 1。稳定签名 7：unsupported library call operation 157；machine verifier undefined physical register 16；Cannot select dynamic_stackalloc 7；Cannot select sign_extend_inreg from i1 1；DADAO AsmPrinter unknown operand type 1；SelectionDAG assertion illegal result number 1；inline asm input register constraint allocation 1。阶段计数为 DAG instruction selection 165、register allocation 16、DADAO AsmPrinter 1、SelectionDAG assertion 1、inline-asm constraint allocation 1。frontend rc 为 70:181、134:2、未报告:1；最终优化级别为 -O0:165、-O3:19。

原始逐对象表：[object-results.tsv](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/results/object-results.tsv)、[object-results.failed.tsv](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/results/object-results.failed.tsv)；含每一行 output、rc、stderr_saved、record_file 的全量聚类结果：[all-failures.tsv](/tmp/ml-016g-backend-failure-cluster-20260721/all-failures.tsv)。逐簇对象清单：

- [unsupported library call operation（157）](/tmp/ml-016g-backend-failure-cluster-20260721/cluster-objects-01-unsupported-library-call-operation.tsv)
- [machine verifier undefined physical register（16）](/tmp/ml-016g-backend-failure-cluster-20260721/cluster-objects-02-machine-verifier-undefined-physical-register.tsv)
- [dynamic_stackalloc（7）](/tmp/ml-016g-backend-failure-cluster-20260721/cluster-objects-03-cannot-select-dynamic-stackalloc.tsv)
- [sign_extend_inreg i1（1）](/tmp/ml-016g-backend-failure-cluster-20260721/cluster-objects-04-cannot-select-sign-extend-inreg-from-i1.tsv)
- [AsmPrinter unknown operand（1）](/tmp/ml-016g-backend-failure-cluster-20260721/cluster-objects-05-dadao-asmprinter-unknown-operand-type.tsv)
- [SelectionDAG assertion（1）](/tmp/ml-016g-backend-failure-cluster-20260721/cluster-objects-06-selectiondag-assertion-illegal-result-number.tsv)
- [inline asm constraint（1）](/tmp/ml-016g-backend-failure-cluster-20260721/cluster-objects-07-inline-asm-input-register-constraint-allocation.tsv)

代表性原始 stderr：__cexp.o.stderr (/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/logs/compiler/compile_obj_src_complex___cexp.o_pid_567721.stderr)、posix_memalign.o.stderr (/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/logs/compiler/compile_obj_src_malloc_posix_memalign.o_pid_571831.stderr)、dcngettext.o.stderr (/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/logs/compiler/compile_obj_src_locale_dcngettext.o_pid_571442.stderr)、puts.o.stderr (/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/logs/compiler/compile_obj_src_stdio_puts.o_pid_580046.stderr)、__unmapself.o.stderr (/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/logs/compiler/compile_obj_src_thread___unmapself.o_pid_582167.stderr)、intscan.o.stderr (/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/logs/compiler/compile_obj_src_internal_intscan.o_pid_569898.stderr)、explicit_bzero.o.stderr (/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/logs/compiler/compile_obj_src_string_explicit_bzero.o_pid_580935.stderr)。这些文件保留原始诊断及 rc 对应的 record。

只读对照：隔离 config.mak 与各 .record 均为 --target=dadao、-nostdinc -ffreestanding，失败跨 -O0/-O3；10 个代表对象 frontend-only -S -emit-llvm probe 均 rc=0，命令/rc/IR 在 /tmp/ml-016g-backend-failure-cluster-20260721/ir-probes/。

初步边界：157 簇的 acos/exp/__cexp IR 含 f64、llvm.fmuladd.f64 及浮点库调用，当前 DADAO lowering 只显式注册 i64 GPRD；但 stderr 未给出单一 DAG operation，不能把 157 个对象声称为一个精确根因。7 个 dynamic_stackalloc 对象的 source/IR 含 VLA、llvm.stacksave/动态 alloca。16 个 verifier 对象的 raw machine code 出现 undefined RB31；当前 calling convention pointer return 为 RB31、CALL Defs 为 RD31，这是候选，仍需最小 call-return 实验。puts、intscan、AsmPrinter CRTJMP、inline asm constraint 各为独立一对象边界，不合并。

Accepted 前下一步：独立 reviewer 重跑 python3 /tmp/ml016g_cluster.py 核对 184/184、7 簇、raw 引用及受保护范围；随后分别建立浮点/libcall DAG、dynamic stackalloc、RB31 pointer-return/call-clobber、i1 sign_extend、SelectionDAG assertion、AsmPrinter operand、inline-asm constraint 的最小 reproducer 和失败→成功 rc 对照。修复任务完成后必须重跑隔离 clean object matrix，不把单对象或 frontend-only IR 成功当作完整 libc.a/runtime acceptance。

本轮实际修改文件：本 task 完成区、docs/reviews/ML-016g-backend-failure-cluster-20260721.md；脚本、TSV、IR、stderr/rc 汇总均在 /tmp，无实现文件修改。

独立 reviewer Galileo the 2nd 的结论为 **Accepted-with-findings**，见
`docs/reviews/ML-016g-independent-review-20260721.md`。review 确认 7 个簇互斥且
覆盖全部 184 个失败，同时保留各簇根因尚未闭合的边界。
