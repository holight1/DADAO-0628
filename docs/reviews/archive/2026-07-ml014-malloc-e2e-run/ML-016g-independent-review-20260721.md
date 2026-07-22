# ML-016g backend failure cluster：独立 review

日期：2026-07-21（Asia/Shanghai）

## 结论

**Accepted-with-findings**

聚类的对象会计、簇覆盖、原始证据引用和阶段/family/优化级别统计均通过独立核验。报告没有把错误签名直接冒充 184 个失败对象的已证实根因；但 157 簇的具体 lowering 根因、16 簇的 RB31 机制，以及其余单例的修复方式仍是待验证 finding，不能作为本 review 的实现结论。

## 独立核验结果

我重跑了 `/tmp/ml016g_cluster.py`，并对 `/tmp/ml-016g-backend-failure-cluster-20260721/` 的全量 TSV 做了独立集合和原始文件检查。

| 项目 | 核验结果 |
|---|---:|
| 全量 object rows | 1347 |
| 成功（rc=0） | 1163 |
| 失败（rc=1） | 184 |
| 1163 + 184 | 1347 |
| 稳定错误签名 | 7 |
| 簇对象总数 | 184 |
| 簇之间交集 | 0 |
| 簇联合与失败集合相等 | 是 |

簇计数为：

| 稳定签名 | 数量 | 阶段 | 失败 family 分布 |
|---|---:|---|---|
| unsupported library call operation | 157 | DAG instruction selection | math 127、complex 22、stdio 2、stdlib 2、internal 1、legacy 1、prng 1、time 1 |
| machine verifier: undefined physical register | 16 | register allocation | string 15、malloc 1 |
| Cannot select: dynamic_stackalloc | 7 | DAG instruction selection | process 4、locale 1、network 1、unistd 1 |
| Cannot select: sign_extend_inreg from i1 | 1 | DAG instruction selection | stdio 1 |
| DADAO AsmPrinter: unknown operand type | 1 | DADAO AsmPrinter | thread 1 |
| SelectionDAG assertion: illegal result number | 1 | SelectionDAG assertion | internal 1 |
| inline asm: input register constraint allocation | 1 | inline-asm constraint allocation | string 1 |

总阶段计数为 DAG instruction selection 165、register allocation 16、DADAO AsmPrinter 1、SelectionDAG assertion 1、inline-asm constraint allocation 1；最终优化级别为 `-O0:165`、`-O3:19`；frontend rc 为 `70:181`、`134:2`、未报告 1。

## 原始 stderr、argv、rc 完整性

对 `all-failures.tsv` 的 184 行逐行检查结果如下：

- 184/184 的 `stderr_saved` 和 `record_file` 都存在且 stderr 非空。
- 184/184 的 record `rc=1`，record output 与聚类 output 一致，且均有 `argv` 和 `real_command`。
- 184/184 的 `real_command` 含 `--target=dadao`；argv 均含 `-nostdinc`、`-ffreestanding`。
- 184/184 的 stderr 各自只出现一个本簇对应的原始错误标记，没有发现一个 stderr 同时包含多个候选签名而被聚类优先级掩盖的情况。
- 7 个逐簇对象清单的集合互不相交，联合覆盖全部 184 个失败对象；没有只存在于汇总而缺少原始对象引用的条目。

代表性原始诊断与 record 相互吻合：

- `__cexp.o`：`fatal error: error in backend: unsupported library call operation`，record 为 `rc=1`、`-O0`。
- `posix_memalign.o`：machine verifier 明确报 `COPY $rb31` 使用 undefined physical register，record 为 `rc=1`、`-O3`。
- `dcngettext.o`：DAG 中明确为 `dynamic_stackalloc`，record 为 `rc=1`、`-O0`。
- `puts.o`：明确为 `sign_extend_inreg ... ValueType:ch:i1`。
- `__unmapself.o`：明确为 `lowerToMCInst: unknown operand type`，frontend rc 134。
- `intscan.o`：明确为 `SelectionDAGNodes.h` 的 `Illegal result number!` assertion，frontend rc 134。
- `explicit_bzero.o`：明确为 inline asm constraint `r` allocation failure；原始 stderr 没有 frontend summary，聚类标为未报告。

## 根因推断边界

已有报告的谨慎边界是正确的，没有发现把错误签名直接当作根因的过度推断：

1. 157 个对象共享的是 `unsupported library call operation` 这个 backend 诊断，不是一个具体 DAG operation 的证明。3 个浮点/数学 IR probe 确实显示 f64、`llvm.fmuladd.f64` 及数学库调用；目标 lowering 也显式只为 i64 注册 GPRD。但这只能确立“浮点/libcall capability/lowering 候选”，不能证明 157 个对象只有同一个缺失 capability，也不能证明修复其中一个 operation 会覆盖全簇。
2. 7 个 dynamic-stackalloc 对象的代表性 IR/source 具有动态 alloca 与 `llvm.stacksave`，足以支持独立的 frame/lowering 调查；它不是对 157 簇或全部失败的解释。
3. 16 个 verifier 对象中抽查的 `memmem`、`posix_memalign` raw machine code 都出现 `$rb31` 未定义。`DADAOCallingConv.td` 的 pointer return 为 `RB31`，而 `DADAOInstrInfo.td` 的 CALL defs 为 `RD31`，这是高价值候选机制；但现有证据仍不能替代 direct/indirect pointer-return 最小 reproducer 和 liveness/call-def 实验。
4. `puts`、`intscan`、`__unmapself`、`explicit_bzero` 的 raw stderr、IR 形态和阶段彼此不同，按四个单独边界处理是适当的，不应合并成一个泛化根因。

10 个 frontend-only `-S -emit-llvm` probe 均为 rc=0。这证明抽查样本可以生成 IR，并不证明对应对象能完成 backend codegen，更不等于完整 `libc.a` 或 runtime acceptance。

## Findings / 后续验收条件

- **F1（根因仍未闭合）**：157 簇的下一步必须从最小 f64/libcall DAG reproducer 开始，记录具体 operation 及失败→成功 rc；不能以签名名称或 frontend-only IR 成功作为修复验收。
- **F2（RB31 仍为候选）**：16 簇必须分别覆盖 direct/indirect pointer-return、CALL defs、liveness 和 `RB31` 的定义路径，并用最小实验确认机制后再修改 calling convention/instruction definitions。
- **F3（簇间不可合并）**：dynamic stackalloc 与四个单例应保持独立 reproducer/修复边界；修复后需重跑隔离 clean object matrix，而不是只验证代表对象。

本独立 review 只写入本文件；未修改 LLVM、musl、build/archive、测试或规范文件。
