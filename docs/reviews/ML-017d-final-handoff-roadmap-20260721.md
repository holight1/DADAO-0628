# ML-017d 最终 handoff 与后续 roadmap

日期：2026-07-21（Asia/Shanghai）  
范围：ML-016a~z、ML-017a~c 的 canonical task/report 与独立 review；本轮第 30
任务 ML-017d。  
结论：**本轮 worker 交付已完成，独立 review 为 Accepted-with-findings；当前
不得把 targeted gate 或 object matrix 扩大解释为完整 libc、ML-014a 或 kernel
验收。**

## 1. 完成计数与阶段状态

### 计数口径

| 口径 | 计数 | 状态 |
|---|---:|---|
| 文件级 worker 交付 | **30/30** | ML-016a~z、ML-017a~c 加本 ML-017d 均已有 task/report 交付 |
| 独立 review | **30/30** | ML-016a~z、ML-017a~c 与 ML-017d 均已有独立 review；ML-017d 为 Accepted-with-findings |
| tracker | 已由主 agent 集成 | review 时曾为 `29–30 Pending`；最终已补入 ML-017c/ML-017d 两行并记录独立 review 状态 |

“30/30”是本 handoff 的 worker artifact 计数，不是把待 review 的 ML-017d 标成已
独立验收；最终 task 文件明确保持“Worker completed；待独立 review”。

### 各阶段状态

| 阶段 | 任务 | 当前状态 |
|---|---|---|
| 诊断、依赖与构建审计 | ML-016a~g（7） | 1 项 diagnosis、6 项 audit；均为 `accepted-with-findings`，锁定 mallocng/output 边界和 1347→1163/184 初始失败簇 |
| backend 最小复现 | ML-016h~o（8） | `accepted-with-findings`；f64/libcall、dynamic stack、RB31/tail、i1、AsmPrinter、SelectionDAG、inline-asm 分簇，未把候选根因写成全局根因 |
| backend 修复与链路回归 | ML-016p~r（3） | AsmPrinter 修复为 `Accepted`；inline-asm 修复为 audit-accepted-with-findings；fresh chain 为 `Accepted` |
| 修复后 object matrix 与 i1 | ML-016s~u（3） | audit-accepted-with-findings；从 1165/182 到 1166/181，puts 由 i1 修复迁移成功；仍未生成完整 archive |
| targeted runtime、frame 与 provenance | ML-016v~z（5） | partial puts gate、MALIGN audit、frame repro、frame fix、final-head varargs provenance 均有交付；ML-016y 初始 provenance finding 由 ML-016z 闭合 |
| final d3bd matrix、scope、targeted gate | ML-017a~c（3） | 均为 audit-accepted-with-findings；ML-017b 已收窄 causal wording；ML-017c targeted gate 可接受，但 puts-success 是 blocking finding |
| 最终 handoff | ML-017d（1） | Audit-accepted-with-findings；puts-success 仍为后续 A 路线 blocking 子目标 |

## 2. 事实（Facts）

### 2.1 LLVM 已落地的四项修复

| 已落地项 | 事实与范围 |
|---|---|
| AsmPrinter external symbol | ML-016p 在 `DADAOAsmPrinter` 增加 `MO_ExternalSymbol → MCSymbolRefExpr` 映射；普通 call/branch/pseudo 与无操作数 inline asm 回归通过。 |
| inline asm register constraint | ML-016q 增加 `getRegForInlineAsmConstraint`；`r` 及整数宽度 ≤64 映射到 GPRD；ML-016r 用 include-free fresh clang→IR→llc→MIR/asm 链复核通过。 |
| i1 sign extension | ML-016t 将 `SIGN_EXTEND_INREG/i1` 走 `Expand`；i1 IR/C matrix 与隔离 puts probe 通过；后续 ML-016u 的 puts object 成功。 |
| frame rounding | ML-016y 在 prologue、epilogue、frame-index reference 共用 `alignTo(raw, 8)` 的有效 frame size，并处理 varargs save-area 的对齐；最终 nested commit 为 `d3bd9c15434fd7a48c0b7bab87354778cd932a72`，parent 为 `be99e5505abe341100c62d70cd955b2df7e4711e`。 |

frame fix 的最终 varargs provenance 由 ML-016z 在 final HEAD 上重跑闭合；这不是把
ML-016y 的中间提交证据冒充 final-head 证据。

### 2.2 final object matrix 与 LLVM test 边界

- ML-017a 在 final `d3bd9c...` 上 fresh 编译 **1347 个对象：1166 success / 181
  failure**；stdio 116 个对象中 **114 success / 2 failure**，失败为
  `vfprintf.o` 与 `vfscanf.o`。
- 当前四个失败簇为：`unsupported library call operation=157`、
  `machine verifier undefined physical register=16`、
  `dynamic_stackalloc=7`、`SelectionDAG illegal result number=1`。
- 相对 ML-016u 的记录型 `40bc` aggregate baseline，逐对象为 0 regression / 0
  migration；相对 ML-016f 的历史 1163/184，三个旧对象
  (`puts.o`、`explicit_bzero.o`、`__unmapself.o`) 已分别在此前 i1、inline-asm、
  AsmPrinter 修复链中成功。
- `llvm-lit` 目录级运行因构建树缺少 `llvm-config` 返回 rc=2；直接
  `llc | FileCheck` 的窄范围证据通过，但不能宣称 full LLVM suite，也不能把
  `1166/181` 宣称为完整 LLVM 或完整 musl 通过。

### 2.3 final-head varargs、partial archive 与目标化运行

| 证据 | QEMU | Gem5 | 事实口径 |
|---|---:|---:|---|
| final-head varargs probe | **0** | **0** | final `d3bd9c...` 的 compile/link/objcopy/disasm 与正常 `va_start/va_arg` runtime 均闭合；odd/padding=4 只作静态边界 |
| 1166-member partial archive | ar=0；ranlib=0 | — | fresh success object 1166/1166，occurrence-aware member hash 闭合；archive 明确 `partial_incomplete` |
| `write_fixed` | rc=42，`write-ok` | rc=42，`write-ok` | fixed write 正控制通过 |
| `main_exit` / `_Exit` | rc=42 | rc=42 | `_Exit` 目标化路径正常结束 |
| `return_syscall` | rc=42 | rc=42 | return-valued syscall 目标化路径正常结束 |
| `puts_probe` | rc=42，无 puts marker | rc=42，无 puts marker | 退出码不是 puts 成功码 |
| `puts_return_bypass` | `PUTS_RC_ERR` | `PUTS_RC_ERR` | puts 返回负值的诊断 marker |
| `puts_errno_bypass` | `PUTS_ERR_ERRNO_NONZERO` | `PUTS_ERR_ERRNO_NONZERO` | errno 非零失败诊断 marker |

上述主 probe 的 compile/link/undefined/objcopy/object-disasm/ELF-disasm 均为 rc=0；
`puts_probe` 的 map 解析到本轮 archive 的 `puts.o` 及其 stdio/output 链，故不是
undefined symbol 或“没有链接到 puts”的结果。

运行输入形态必须保持区分：**QEMU 使用 launcher 加载同次链接的 BIN；Gem5 使用同次
链接的 ELF 作为 `dadao_se.py` 的直接参数**，Gem5 不使用 QEMU 的 launcher/BIN。

### 2.4 mallocng、ML-014a 与 kernel

- ML-016a 只确认双块 malloc/free/write/read/exit 的窄诊断行为，并明确当前高层
  输出缺失；ML-017c 没有重新做 mallocng 行为 probe。
- 因此 **mallocng/ML-014a 本轮没有重新解决，也没有接受**；partial archive 中
  存在 mallocng 相关 object 不构成 ML-014a completion claim。
- **kernel 尚未进入**。当前用户态 object、partial archive、varargs 或 QEMU/Gem5
  targeted 结果都不能替代 kernel bring-up evidence。
- 原有未跟踪的 `code-agent/tasks/ML-014a-musl-e2e-malloc-printf.md` 必须保留原样，
  本轮没有编辑、关闭或重解释它。

## 3. 推断（Inference）

| 推断 | 支持它的事实 | 不能进一步推出 |
|---|---|---|
| AsmPrinter、inline-asm、i1 三个旧单例已被各自修复链覆盖 | 对应最小 probe、fresh chain 与 ML-017a 三对象迁移 | 不能推出其余 181 个 failure 或 full LLVM suite 已解决 |
| frame rounding 消除了 ML-016v 目标路径的早期 MALIGN | final d3bd 的 `_Exit`/return/fixed-write 目标化双后端均 rc=42；ML-016y/z varargs 正常 probe 为 0/0 | 不能把该结果写成所有 runtime 或 stdout 已修复 |
| puts 失败已进入已链接 libc stdio/output API 路径 | puts map 拉入 stdio 链；两后端无 marker；return bypass 为负值，errno bypass 非零；fixed write 可输出 | 不能确定具体 errno、首次失败的 writev/fd/console 条件或完整 flush 语义 |
| d3bd final matrix 相对 ML-016u aggregate 没有观察到 regression/migration | 1166 个旧成功与 181 个旧失败逐对象保持原结果 | 不能称为 `be99→d3bd` frame-only causal isolation |

## 4. 边界（Boundaries）

### 已明确禁止的扩大解释

- `1166/181` 是 final-head musl object compile matrix，不是完整 libc archive、完整
  link、完整 runtime 或 full LLVM suite 的通过数。
- 1166-member archive 是隔离的 partial/incomplete archive；ar/ranlib/link 成功不
  等于完整 libc 可链接，更不等于高层 stdio 已通过。
- `write-ok`、`rc=42`、`SIM_END: trap-exit` 和 `varargs 0/0` 不能替代 puts marker；
  ML-017c review 的 puts-success finding 在后续 gate 前保持阻塞。
- `ML-016u(40bc)→d3bd` 的 aggregate 0 regression/0 migration 不能写成
  `be99→d3bd` frame-only causal isolation；后者本轮未做。ML-016x/y/z 的窄 probe
  也不能替代同工具、同 source/configuration 的 be99 1347 matrix。
- 当前结果不能宣称 mallocng/ML-014a 已接受、kernel 已就绪，不能修改或关闭原
  ML-014a 未跟踪 task。

### ML-017c review 的判定

ML-017c 独立 review 为 **Accepted-with-findings**：它允许把 1166-member archive、
link、fixed-write、`_Exit`、return-valued syscall 记录为**限定范围的 targeted gate**；
但 **puts-success 是阻塞子目标**。该 finding 不被 `rc=42` 或 fixed-write 结果覆盖。
review 中的 disassembler hash 清单缺口和 diagnostic bypass raw argv 缺口是非阻塞的
证据卫生 finding，本 handoff 不把它们改写成成功或失败的 runtime 结论。

## 5. 后续 roadmap（按阻塞顺序）

| 顺序 | 路线 | 验收门槛 | 禁止越界声明 |
|---|---|---|---|
| **A** | **stdio / writev / stdout runtime** | 在 final-head、可复核 fresh object/archive 输入上，分别验证 `puts`、`fputs`/`fwrite` 与必要的 `fflush`/stdout 路径；QEMU 与 Gem5 均无 timeout、API 返回成功、输出 marker 实际出现；保存 writev/底层 fd/errno 的逐阶段 rc 与 provenance，保留 fixed-write 正控制。 | 不得用 fixed `write`、无 marker 的 rc=42、partial archive link 成功或 errno 非零诊断宣称高层 stdout/flush 已通过；不得顺手宣称 ML-014a 或完整 libc 已完成。 |
| **B** | **vfprintf / vfscanf / libcall** | 先使 `vfprintf.o`、`vfscanf.o` 从当前 failure matrix 转为 fresh success，并用整数格式的 printf/scanf 目标化 link+QEMU/Gem5 运行；随后对 157 项 `unsupported library call operation` 按簇重跑，逐项保留成功/失败迁移和未覆盖簇。 | 不得把 final-head varargs `0/0` 当作 vfprintf/vfscanf 或所有 libcall 已通过；不得把两个 stdio object 的成功写成完整 157 簇或 full LLVM suite 通过。 |
| **C（可选）** | **be99 parent matrix** | 若需要 frame-only 因果结论，必须在 `be99e5505abe341100c62d70cd955b2df7e4711e` 上用同一工具身份、同一 musl source/configuration、同一方法完成完整 1347 matrix，并与 d3bd 逐对象比较 regression、migration、clusters、artifact freshness。 | 在该实验完成前，严禁把 `ML-016u(40bc)→d3bd` aggregate 结果、静态 frame probe 或 varargs 0/0 称为 `be99→d3bd` causal isolation；C 为可选实验，不得阻塞事实已明确的 A/B gate 口径。 |
| **D** | **mallocng e2e** | 在 A/B 所需输出基础稳定后，重新执行 ML-014a 规定的真实 mallocng 路径：至少两种不同大小分配、写入/读回/free，证实实际 mmap/bump/page-align 语义，并在 QEMU/Gem5 均获得判别性成功退出与高层输出 marker；保存 fresh source/object/archive/launcher provenance。 | 不得把 ML-016a 的窄 malloc 诊断、partial archive 中的 malloc object、无 marker 的 puts 或静态地址观察写成 ML-014a 接受；不得编辑原 ML-014a task 代替验收。 |
| **E** | **kernel bring-up** | 仅在用户态 ABI/libc、输出和 mallocng gate 达到明确门槛后，另行定义 kernel artifact/entry、异常/CFX/RegRAS 与 QEMU/Gem5 最小启动及 handoff evidence；每个阶段有独立 rc、trace 和双后端边界。 | 不得用 LLVM object matrix、partial archive、varargs 0/0、puts targeted gate 或已有用户态退出码宣称 kernel 已进入、已启动或已完成 handoff。 |

## 6. 交接结论

本轮交接的可靠终点是：四项 LLVM backend 修复已有各自限定范围的落地/回归证据；
final d3bd object matrix 为 1166/181、stdio 为 114/116；final-head varargs 双后端
为 0/0；1166-member partial archive 及 fixed-write、`_Exit`、return-valued syscall
目标化门禁通过。但 high-level puts 在两后端都没有 marker，且 errno bypass 为非零
失败，因此 A（stdio/writev/stdout runtime）仍是下一步首要阻塞；ML-014a/mallocng
未重新解决或接受，kernel 尚未进入。

本报告只新增该文件；旧 task/report、tracker、生产代码、launcher/spec、
`docs/issues.yaml`、wiki 和原 ML-014a 未跟踪文件均保持不动。

本报告对应 ML-017d 独立 review：[ML-017d-independent-review-20260721.md](ML-017d-independent-review-20260721.md)。
review 保留 puts-success 尚未通过这一边界。review 时的 tracker 同步 finding 已由主
agent 在最终交接提交中补入 ML-017c/ML-017d 两行；当前 tracker 与 30/30 artifact/review
口径一致。
