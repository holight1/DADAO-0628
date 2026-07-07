# ADR-0008: CodeGen Feasibility Spike 结论（终判 — DL-041a 收口）

**日期**：2026-07-03（2026-07-06 架构师实机核对修正；2026-07-07 DL-041a 终判）
**当前状态**：**SPIKE PASS** —— `llc -stop-after=finalize-isel`（`i64 add`）产出含 `%N:gprd` 的 MIR，GPRD 数据 bank 在 SelectionDAG→MIR 全程存活。双 bank 数据侧可行性以 MIR 实证确认。

## 背景

DL-037b 接入 CodeGen 管线，使 `llc -march=dadao -stop-after=finalize-isel` 运行到 ISel。此前（DL-037b/038a）崩溃于 "Expand IR instructions"，未能产出 MIR，双 bank 存活问题无 MIR 实证。DL-041a 在验证过的地基（C1+C2+C3 闭环、DataLayout 校正到 S64）上用 GDB 逐层剥出根因，取得 MIR。

## MIR 实证（SPIKE PASS 的依据）

`i64 add`（`define i64 @add_func(i64 %a, i64 %b) { %s = add i64 %a, %b  ret i64 %s }`）→ `finalize-isel` MIR：

```
registers:
  - { id: 0, class: gprd }
  - { id: 1, class: gprd }
  - { id: 2, class: gprd }
liveins:
  - { reg: '$rd16', virtual-reg: '%0' }   ; 参数 a（ABI §2.1 rd16..）
  - { reg: '$rd17', virtual-reg: '%1' }   ; 参数 b
body: |
  bb.0:
    liveins: $rd16, $rd17
    %1:gprd = COPY $rd17
    %0:gprd = COPY $rd16
    %2:gprd = ADD_PSEUDO %0, %1
    $rd31   = COPY %2                      ; 返回值（ABI §3.1 rd31）
    RET_PSEUDO implicit $rd31
```

- 三个 vreg 全部 `class: gprd`；参数 `$rd16/$rd17`、返回 `$rd31` 与 ABI 一致。
- GPRD register class 从 LowerFormalArguments（CopyFromReg）经 add 到 LowerReturn（CopyToReg）全链路存活，未在 DAG 类型合法化/选择中丢失或错分类。
- **回答 DL-036a 核心问题：双 bank 数据侧在 SelectionDAG 存活 = 是。**

> 大小写注记：MIR 的 register class 打印为小写 `gprd`（LLVM 惯例）。DL-041a 验收里的字面 `grep -q "GPRD"`（大写）会假阴性，实质通过。后续验收用 `grep -qi gprd`。

## 崩溃根因链（GDB 逐层实证，非"编译通过"推断）

`finalize-isel` 的 SIGSEGV 是 5 层 target 未接线缺陷叠加，每修一层暴露下一层：

| 层 | 现象（GDB 帧） | 根因 | 最小修复 |
|----|---------------|------|---------|
| 1 | `ExpandIRInsts.cpp:1151 auto *TLI = Subtarget->getTargetLowering()` 空指针 | `DADAOTargetMachine` 未 override `getSubtargetImpl(const Function&)` 且无 Subtarget 成员 → 返回基类 `nullptr`；且 Subtarget 从不构造 TLInfo | TM 加 `DADAOSubtarget` 成员 + override；Subtarget ctor 构造 TLInfo。连带补 `GET_INSTRINFO_MC_DESC`/`GET_SUBTARGETINFO_CTOR`/`GET_SUBTARGETINFO_MC_DESC`（因 Subtarget 首次被实例化才暴露的潜伏 link error） |
| 2 | `SelectionDAGBuilder.cpp:11953 LowerArguments` → `Assertion idx < size()`（InputArg） | `DADAOTargetLowering` ctor 未调 `computeRegisterProperties()` → i64 类型→寄存器映射表未算，`Ins` 计数与 CC 分配不符 | ctor 末尾 +`computeRegisterProperties(STI.getRegisterInfo())` |
| 3 | `SelectionDAG.cpp:1154 verifyNode` → `getSelectionDAGInfo().verifyTargetNode()` 空指针 | `DADAOSubtarget` 未提供 SelectionDAGInfo，基类返回 `nullptr`（RET_GLUE 是 target opcode 触发校验） | Subtarget 加 `SelectionDAGTargetInfo TSInfo` + override `getSelectionDAGInfo()` |
| 4 | `SelectionDAGISel.cpp:3432 SelectCodeCommon(MatcherTable=0x0)` 空指针 | `Select()` 是 stub，显式传 `nullptr` MatcherTable，真实 tablegen `SelectCode` 未接入 | `#include DADAOGenDAGISel.inc`，`Select` 改调 `SelectCode(Node)` |
| 5 | "Cannot select"（非崩溃）：ADD_RRRR 双输出、RET_GLUE 无 pattern | add/ret 无可选 pattern | 加 CodeGen-only pseudo `ADD_PSEUDO`/`RET_PSEUDO`（`isPseudo=1,isCodeGenOnly=1`，不 expand/emit，纯 spike 脚手架） |

**关键**：所有 5 层均为标准 target 骨架未接线，**无一与双 bank 设计相关**——不能据崩溃判双 bank 不可行；修齐后 GPRD 顺利存活。DL-038a 完成区将层 1 误判为 "expand-ir-insts 对 DataLayout 有隐式依赖 / 需更深 LLVM 基础设施调试"，实际是 TargetMachine 缺 Subtarget override 的空指针，GDB 一帧即定位。

## 修复清单（DL-041a，均在 `.work/source/llvm/`，spike throwaway）

| 修复 | 文件 |
|------|------|
| DataLayout `-S128` → `-S64`（ABI §4.2 8B 栈对齐，C3 MISMATCH 清零） | TargetParser/TargetDataLayout.cpp |
| +Subtarget 成员 + `getSubtargetImpl(const Function&)` override | Target/DADAO/DADAOTargetMachine.h/.cpp |
| +`SelectionDAGTargetInfo TSInfo` + `getSelectionDAGInfo()` override | Target/DADAO/DADAOSubtarget.h |
| +`GET_SUBTARGETINFO_CTOR`；ctor 构造 TLInfo | Target/DADAO/DADAOSubtarget.cpp |
| +`computeRegisterProperties()` | Target/DADAO/DADAOISelLowering.cpp |
| +`GET_INSTRINFO_MC_DESC`/`GET_SUBTARGETINFO_MC_DESC`；`InitDADAOMCInstrInfo` | Target/DADAO/MCTargetDesc/DADAOMCTargetDesc.cpp |
| +`ADD_PSEUDO`/`RET_PSEUDO`（spike 脚手架 pseudo） | Target/DADAO/DADAOInstrInfo.td |
| 接入真实 `SelectCode`（删 null-table stub） | Target/DADAO/DADAOISelDAGToDAG.cpp |

## 不回归验证（DL-041a）

- `make check` → OVERALL PASS（exit 0）
- `check_codegen_abi`（S128 修后）→ MISMATCH=0（exit 0）
- MC lit `tests/lit/MC/Dadao` → 14/14；E2E lit `tests/lit/E2E` → 3/3
- QEMU 向量（10 yaml）→ **203 PASS / 0 FAIL**
- `ninja llc` → no work to do（树可构建）

## Phase 5 正式实现序列（更新）

DL-041a 确认双 bank 数据侧可行后，Phase 5 正式序列（spike pseudo 全部替换为真实实现）：

- DL-042（拟）：**GPRB 地址 bank** 接入 SelectionDAG（rd2rb/rb2rd 桥接、LDO/STO 地址计算），验证地址侧双 bank 存活。
- DL-043（拟）：**load/store** patterns（GPRB base + imm12，FrameIndex 消解）。
- DL-044（拟）：**ADD_RRRR 双输出**真实选择（替换 ADD_PSEUDO；处理 rdha=和/rdhb=进位双 def），+ SUB/逻辑/移位。
- DL-045（拟）：完整 **CallingConv**（LowerCall、栈参数、callee-save prologue/epilogue）。
- DL-046（拟）：**AsmPrinter → MCInst 降低**（替换 RET_PSEUDO 为真实 ret 序列；EmitInstruction），端到端 `.s` 发射。

（编号待架构师定稿；spike 代码 review 后决定是否纳入 LLVM patch series。）
