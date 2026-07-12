# DL-063c: DEBUG/FIX — 间接调用调度器崩（换 pattern-based 选择）

**执行环境**: 本地 DS · DADAO-0628（LLVM backend）· **debug/fix 任务**

**状态**: 暂缓（deferred 2026-07-12）——间接调用磨 3 轮未破(调度器 getValueType 崩，手动建 call 节点 vs pattern-based 待厘清)，按决策 C 转 clang 里程碑优先；WIP 已 git stash（.work/llvm）+ 根因分析留 DL-063c 完成区，later 重启

**前置**: DL-063b（函数指针间接调用，两轮打回）。结构方向已对（LowerCall 发 ISD::CALL、DAGToDAG 分选），但**间接路径在调度器崩**。

---

## 完成区

**状态**：部分完成
**已完成**：
1. ✅ DAGToDAG 直接 call（CALL_IIII）按 GlobalAddress→CALL_IIII 手动分选（保留原有正常路径）
2. ✅ DAGToDAG 间接 call 通过 `getMachineNode(CALL_INDIRECT_PSEUDO)` 创建伪指令
3. ✅ `CALL_INDIRECT_PSEUDO` 有 `isCall=1` + `variable_ops`=GPRB rbha + chain
4. ✅ LowerCall 间接分支的 GPRB 桥（架构师已落，正确保留）
5. ✅ E2E 回归：24/24 PASS

**卡住**：`getMachineNode(CALL_INDIRECT_PSEUDO, {Other,Glue}, {Callee,Chain})` 产出节点 `NumValues==0` → 调度器 `getValueType(0)` 崩。CALL_IIII（同样的 `(outs)` 空 + `isCall=1`）正常产出 Other+Glue。差异在 `isCodeGenOnly=1` 令 LLVM core 不追加隐式 call chain/glue 输出。

**已尝试**：
- 去掉 `isPseudo` → 同崩
- 嵌入 `Pattern=[(DADAOCall GPRB:$rbha)]` → "Node already inserted"
- 单独 `Pat<(DADAOCall GPRB:$rbha),(CALL_INDIRECT_PSEUDO...)>` → "Node already inserted"
- `variable_ops` + `Chain` operand → 同崩（NumValues 仍为0）
- `SDT_DADAOCall` explicit profile → 同崩

**修复方向**（架构师可接手）：在 LLVM `getMachineNode` 里对 `isCodeGenOnly=1` + `isCall=1` 的指令追加隐式 Other+Glue 输出，或改 `CALL_INDIRECT_PSEUDO` 为显式 `(outs TOCHAIN, GLUE)`——但这需要 LLVM 支持显式 chain/glue 输出类型。

---

## 症状（精确）
```
llc -march=dadao <间接调用.ll>:
  Assertion `ResNo < NumValues && "Illegal result number!"' 
  (SelectionDAGNodes.h:1116, getValueType)
  在 ScheduleDAGSDNodes::BuildSchedUnits()（调度器，ISel 之后）
  仅函数 @f（含间接 call %fp()）崩；直接 call（CALL_IIII）正常
```
复现：
```
printf 'define i64 @a(){ret i64 7}\ndefine i64 @f(i64()* %fp){%r=call i64 %fp() ret i64 %r}\ndefine i64 @main(){%r=call i64 @f(i64()* @a) ret i64 %r}\n' > /tmp/1.ll
.work/build/llvm/bin/llc -march=dadao /tmp/1.ll -o /dev/null    # 崩
```

## 已排除（架构师两轮直修，均未解 → 病根不在这些）
- ❌ **不是漏 Chain**：DAGToDAG 间接分支 Ops 已补 `Chain`（`{Callee,RD0,Zero,Chain}`）——仍崩。
- ❌ **不是 callee 寄存器类**：已在 LowerCall 用 `CopyToReg` 把间接 callee 桥到 GPRB vreg（`DADAOISelLowering.cpp` else 分支，复用 copyPhysReg rd2rb）——仍崩。
- ❌ **不是缺 SDNPOutGlue**：`DADAOCall`(.td) 本就有 `SDNPOutGlue`（subagent 曾误诊）。
- ✅ 直接 call（CALL_IIII，同样手动 getMachineNode `{Callee,Chain}`）正常——说明不是 call 机制本身，是**间接 pseudo 节点**的问题。

## 病根假设（架构师，对标 RISC-V）
DADAO `CALL_INDIRECT_PSEUDO`（`.td` `let Pattern=[]`）靠 **DAGToDAG 手动 `getMachineNode(CALL_INDIRECT_PSEUDO, {Other,Glue}, Ops)`** 建节点；RISC-V `PseudoCALLIndirect` 用 **`Pseudo<(outs),(ins GPR:$rs1),[(riscv_call GPR:$rs1)]>`——带 Pattern、靠 tablegen 模式匹配选择**，ISel/调度器自动处理 glue/result 连线。**手动建节点的 glue/result 结构最易在调度器 BuildSchedUnits 出 `Illegal result number`**（round-1 也崩在此阶段，只是断言不同 `Node already inserted`）。

## 目标
让间接调用编译过 + 双后端跑对。**推荐路线：换 pattern-based 选择**（弃手动 getMachineNode）：
1. **给 `DADAOISD::CALL` 的寄存器-callee 形态一个 tablegen Pattern**：仿 RISC-V——定义带 pattern 的 pseudo（如 `Pseudo<(outs),(ins GPRB:$rbha),[(DADAOISD::CALL GPRB:$rbha)]>` + `PseudoInstExpansion<(CALL_RRII GPRB:$rbha, RD0, 0)>` 或 expandPostRAPseudo 展开），让 `SelectCode(Node)` 走 tablegen 匹配、**不再在 DAGToDAG 手动 getMachineNode**。
   - 注意 `DADAOISD::CALL` 是 `SDNPVariadic`——RISC-V 的 `riscv_call` 也是，pattern 只匹配首个 callee 操作数，可变参数(arg regs)经 glue/regmask 带入。看 RISC-V 怎么写 `riscv_call` 的 pattern（`RISCVInstrInfo.td` 附近 `PseudoCALL`/`PseudoCALLIndirect` + `def : Pat<(riscv_call ...), ...>`）。
2. **直接 call（CALL_IIII）也一并统一到 pattern**（若可）：RISC-V `def : Pat<(riscv_call tglobaladdr:$f),(PseudoCALL tglobaladdr:$f)>`。或保留现有直接路径不动、只把间接换 pattern。
3. **保留架构师已落的正确改动**：LowerCall 的 GPRB 桥（间接 callee→GPRB）+ ISD::CALL 统一发节点——这些对，别回退。

## 约束
- 只改 `.work/source/llvm/llvm/lib/Target/DADAO/`；LLVM 改动同步新 patch `components/llvm/patches/0020-*.patch`（入 series）。
- **不回归**：lit E2E 现 24 例全绿 + 四方 AGREE(4-way)=200/DIVERGE=0 + 直接 call（nested_call 等）不退步。
- 新增间接调用 E2E 入 `tests/lit/E2E/`（双后端）。

## 验收（架构师复跑）
```bash
cd ~/DADAO-0628 && ninja -C .work/build/llvm llc llvm-mc lld
# 间接调用编译过 + 双后端
llvm-lit -v tests/lit/E2E/ 2>&1 | tail            # 全 PASS（含间接调用）
python3 tools/run_differential.py 2>&1 | tail -3  # AGREE(4-way)=200 / DIVERGE=0
```
**判别项真测**：换指针换结果（`f(&g7)→7`/`f(&g9)→9` 同一间接点）、回调带参（`apply(fn,x)=fn(x)`，fn=double/inc）、直接 call 不退步；防去虚化折叠（函数指针经运行时参数传）。

## 参考指针
- 现状：`DADAOISelDAGToDAG.cpp`（`if(Opc==DADAOISD::CALL)` 手动 getMachineNode，间接=CALL_INDIRECT_PSEUDO）、`DADAOISelLowering.cpp` LowerCall（GPRB 桥已加，else 分支）、`DADAOInstrInfo.td`（`CALL_INDIRECT_PSEUDO` L132 `Pattern=[]`、`CALL_RRII` L290、`DADAOCall` SDNode L58 有 SDNPOutGlue/Variadic）、`DADAOInstrInfo.cpp` expandPostRAPseudo（L168 pseudo→CALL_RRII）
- **对标（关键）**：`.work/llvm/llvm/lib/Target/RISCV/RISCVInstrInfo.td` 的 `PseudoCALL`/`PseudoCALLIndirect`（`Pseudo<...,[(riscv_call ...)]>` + `PseudoInstExpansion` + `def : Pat<(riscv_call ...),...>`）——**pattern-based call 选择的标准范式**
- spec §5.4（call/RA/CALL_RRII 目标）；DL-051a（rd2rb 跨 bank 桥）、DL-055a（LowerCall/regmask/RA）
- DL-063b 文末架构师复核 v1/v2（结构方向 + 已排除项）

—— 自审纪律见 DS.md §自审流程（subagent 代码级 · 强制；审阅记录区已预置占位必填；卡住也做自审）。**这是 debug 任务，重点是让 tablegen pattern 接管选择、绕开手动建节点的调度器崩**；卡在哪层如实报根因。

---

## Codex Review

### 重跑记录（reviewer 独立执行）

```
$ .work/build/llvm/bin/llvm-lit tests/lit/E2E/ 2>&1 | tail -5
Testing Time: 1.49s
Total Discovered Tests: 24
  Passed: 24 (100.00%)
EXIT_CODE=0
```

```
$ python3 tools/run_differential.py 2>&1 | grep -E "^(===|   )"
   control-flow.yaml case[30] jump: ... AGREE
   ...
=== AGREE(3-way)=200  AGREE(interp+QEMU, gem5-SKIP)=0  DIVERGE=0  HARNESS=6  QEMU-SKIP=0 ===
=== SAIL 4th column: AGREE(4-way)=200  Sail-SKIP(out-of-slice)=0  SAIL-DIVERGE=0 ===
EXIT_CODE=0
```

**间接调用复现（确崩）**：
```
$ cat > /tmp/dl063c_test.ll << 'EOF'
define i64 @a(){ret i64 7}
define i64 @f(i64()* %fp){%r=call i64 %fp() ret i64 %r}
define i64 @main(){%r=call i64 @f(i64()* @a) ret i64 %r}
EOF
$ .work/build/llvm/bin/llc -march=dadao /tmp/dl063c_test.ll -o /dev/null 2>&1

llc: .../SelectionDAGNodes.h:1116: llvm::EVT llvm::SDNode::getValueType(unsigned int) const:
Assertion `ResNo < NumValues && "Illegal result number!"' failed.
...
2.  Running pass 'DADAO DAG->DAG Pattern Instruction Selection' on function '@f'
EXIT_CODE=134
```
堆栈与任务描述一致：`ScheduleDAGSDNodes::BuildSchedUnits → getValueType(0), NumValues==0`。

### 约束核验

| 约束 | 状态 | 证据 |
|------|------|------|
| E2E 24/24 PASS | ✅ PASS | reviewer 重跑：24/24 |
| 四方 AGREE(4-way)=200, DIVERGE=0 | ✅ PASS | reviewer 重跑：AGREE(4-way)=200, SAIL-DIVERGE=0 |
| 间接调用编译过 | ❌ FAIL | 同症状崩，复现确认 |
| 新增间接调用 E2E | ❌ 未完成 | `tests/lit/E2E/` 中无 indirect 测试 |
| 判别项真测双后端 | ❌ 未完成 | 无新增测试，无法验证 |
| patch 文件 0020 | ❌ 未创建 | `components/llvm/patches/0020-*` 不存在 |
| 只改 DADAO target | ✅ 符合 | diff 在 `lib/Target/DADAO/` 内 |

### 逐条 finding（代码级）

#### F1. 调度器崩未修复（阻断）

`DADAOISelDAGToDAG.cpp:102-104`：手动 `getMachineNode(CALL_INDIRECT_PSEUDO, {Other,Glue}, {Callee,Chain})` → 调度器 `BuildSchedUnits` 里 `getValueType(0)` 崩（`NumValues==0`）。症状与任务描述完全一致，DS 未解。

#### F2. `CALL_INDIRECT_PSEUDO` 缺 `isPseudo=1`（阻断，即使调度器能过也会导致后续展开失败）

`DADAOInstrInfo.td:134` 当前定义：
```
let isCodeGenOnly = 1;   // 有
// let isPseudo = 1;     // 缺！
```

`ExpandPostRAPseudos.cpp:156` 过滤条件为 `!MI.isPseudo()`——**不检查 `isCodeGenOnly`**。即使调度器不崩，该伪指令也不会进 `expandPostRAPseudo`，永远无法展开为 `CALL_RRII`。

对照：同文件的 `RET_PSEUDO` 等通过 `DADAOPseudo` 类定义，同时设 `isPseudo=1` + `isCodeGenOnly=1`。`CALL_INDIRECT_PSEUDO` 直接继承 `Instruction`，只设了 `isCodeGenOnly`，未设 `isPseudo`。

#### F3. 间接路径 Glue 操作数漏传（正确性缺陷）

`DADAOISelDAGToDAG.cpp:91-96` 直接 call 路径：
```cpp
if (Glue.getNode()) Ops.push_back(Glue);  // 正确上传 Glue
```

`DADAOISelDAGToDAG.cpp:102-104` 间接 call 路径：
```cpp
{Callee, Chain}    // 未传 Glue — 丢失了链上 CopyToReg 的 Glue 桥
```
这意味着间接 callee 的 GPRB `CopyToReg` 桥没有通过 Glue 链跟 CALL 绑定——虽非当前崩因，但会导致 MIR 乱序/正确性 bug（运行时 callee 寄存器可能在 call 前被破坏）。

#### F4. 死代码（DAGToDAG 间接分支）

`DADAOISelDAGToDAG.cpp:100-101`：
```cpp
SDValue RD0 = CurDAG->getRegister(DADAO::RD0, MVT::i64);
SDValue Zero = CurDAG->getTargetConstant(0, DLC, MVT::i64);
```
两个变量声明后**从未使用**。疑似遗留（早期可能打算手动拼 `CALL_RRII`，后改为 pseudo）。虽不致命但表明代码不整洁。

#### F5. 未成功完成 pattern-based 方案

任务明确要求"换 pattern-based 选择（弃手动 getMachineNode）"。DS 尝试了两种 pattern 写法但遇 "Node already inserted" 错误后放弃。根因很可能是 **DAGToDAG 的手动处理与 tablegen pattern 冲突**——Select 函数先处理 `DADAOISD::CALL` 拦截后 return，但额外 `Pat<>` pattern 在 tablegen 匹配时又尝试匹配同一 CALL 节点。正确的 pattern-based 方式是：**从 DAGToDAG Select 中完全移除 `DADAOISD::CALL` 的手动处理，让 SelectCode 走 tablegen 匹配**。

#### F6. 无新增间接调用 E2E 测试

任务验收要求"新增间接调用 E2E 入 `tests/lit/E2E/`（双后端）"——未完成。现有 24 例中无间接调用覆盖。

### 判决

**Needs Revision** — 下列阻断项未解：

1. **调度器崩未修**（F1）— 间接调用 llc 仍然崩溃，与任务接手时同症状。
2. **`isPseudo` 缺失**（F2）— 即使崩修复，伪指令也无法展开为真指令。
3. **未完成 pattern 方案**（F5）— 任务推荐路线未达成，未产出 patch 0020。
4. **无 E2E 覆盖**（F6）— 无新增测试，判别项无法验证。

**处置建议**：

- **优先**：从 DAGToDAG `Select()` 中**彻底移除** `DADAOISD::CALL` 手动分选（L84–L107），改为在 `.td` 中通过 `def : Pat<(DADAOCall GPRB:$rbha), (CALL_INDIRECT_PSEUDO GPRB:$rbha)>` 让 tablegen 接管间接分支选择。这可以解决 "Node already inserted"（F5）。
- **连带**：给 `CALL_INDIRECT_PSEUDO` 加 `isPseudo = 1`（F2），并确认 `isCall=1` + `isPseudo=1` 组合在 LLVM core 中 produce 正确的 chain/glue 输出。
- **验证**：加新 E2E 测试覆盖：间接零参调用 `f(&g)→g()`、回调 `apply(fn,x)=fn(x)`、直接 call 不退步（nested_call 仍过）。
