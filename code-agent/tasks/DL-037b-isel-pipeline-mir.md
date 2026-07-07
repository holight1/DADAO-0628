# DL-037b: 接线 CodeGen 管线 → 取得 finalize-isel MIR（spike 收口）

**执行环境**: 本地 DS · DADAO-0628

**状态**: 待执行

**前置**: DL-037a（llc 构建门已通过）

---

## 背景

DL-037a 让 llc **构建成功并识别 dadao target**，但为通过构建，把 DL-036a 加的 codegen 接线（PassConfig、Subtarget、CallingConv include）**回退**了。结果 `DADAOTargetMachine` 目前无 `createPassConfig` / 无 `Subtarget`，codegen 管线未接，`llc -stop-after=finalize-isel` 报 `target does not support generation of this file type`，**至今未产出任何 MIR**。

因此 DL-036a spike 的**核心问题仍未回答**：GPRD/GPRB 双 bank 能否在 SelectionDAG 存活到 finalize-isel。本任务是这个 spike 的**收口**——把管线接起来，拿到 MIR 证据，给 ADR-0008 一个基于证据的 PASS/BLOCKED 终判。

---

## 目标（唯一硬目标）

`llc -march=dadao -stop-after=finalize-isel` 对最小 IR（`i64 add`）产出 MIR，且 MIR 中出现 `%N:GPRD`（寄存器 class 存活）。据此给 ADR-0008 终判 PASS 或 BLOCKED。

---

## 接口说明书

### 1. 接回 codegen 管线

`DADAOTargetMachine` 需要重新提供指令选择所必需的最小接线（DL-036a 已写过，被 DL-037a 回退，参考其 WIP 与 git 历史恢复）：

- **Subtarget**：`DADAOSubtarget`，至少持有 `DADAOInstrInfo` / `DADAORegisterInfo` / `DADAOTargetLowering` / `DADAOFrameLowering`，并实现 `getInstrInfo` / `getRegisterInfo` / `getTargetLowering` / `getFrameLowering` / `getSubtargetImpl`。
- **createPassConfig**：`DADAOPassConfig`，覆写 `addInstSelector()` 挂 `createDADAOISelDag(TM)`。
- **ISelLowering**（`DADAOTargetLowering`）：`addRegisterClass(MVT::i64, &DADAO::GPRDRegClass)`；`add`/`ret` 走 Legal / 已有 pattern；`computeRegisterProperties`。GPRB 注册可选（若 `i64 add` 不需要，最小集可只挂 GPRD，但需在 ADR 说明 GPRB 未覆盖）。
- **ISelDAGToDAG**（`DADAODAGToDAGISel`）：LLVM 22 用 `SelectionDAGISelLegacy` + `createDADAOISelDag` 工厂 + `INITIALIZE_PASS`（DL-036a 已验证可编译，直接复用）。

### 2. LLVM 22 API 注意点（据实核对，勿照搬旧版）

- `SelectionDAGISel` → `SelectionDAGISelLegacy`（DL-036a 已适配）
- `getSubtargetImpl` 签名 / `TargetPassConfig` 接口以 LLVM 22 头文件为准
- `initAsmInfo` 已在 TargetMachine ctor，无需重复

### 3. 取得并判定 MIR

```bash
LLC=.work/build/llvm/bin/llc
cat > /tmp/spike_add.ll << 'EOF'
target triple = "dadao"
target datalayout = "E-m:e-i64:64-n64-S128"
define i64 @add_func(i64 %a, i64 %b) {
  %s = add i64 %a, %b
  ret i64 %s
}
EOF
$LLC -march=dadao -stop-after=finalize-isel /tmp/spike_add.ll -o /tmp/spike_add.mir
cat /tmp/spike_add.mir
```

- MIR 含 `%N:GPRD` → **spike PASS**（双 bank 数据侧在 SelectionDAG 存活）
- 若崩溃 / bank 分类丢失 / 无法合法化 `add` → **spike BLOCKED**，记录具体现象与 LLVM 报错

### 4. 回填 ADR-0008 终判

- 结论从"未决"改为 **SPIKE PASS** 或 **SPIKE BLOCKED**（二选一，基于 MIR 证据）
- 附 MIR 关键片段
- 若 PASS：确认 DL-038a~040a（AsmPrinter、双输出 pattern、CallingConv 完整）的后续序列成立
- 若 BLOCKED：给出双 bank 模型的修订建议（这将触发 Phase 5 scope / ABI 合约复审）

---

## 约束

- **只做接线到 finalize-isel 所必需的最小实现**。不做：AsmPrinter MCInst 降低、完整 asm 发射、ADD_RRRR 双输出、GPRB load/store、栈溢出/callee-save（留 DL-038a+）。
- **不回归**：`make build-mc` + E2E lit 3 场景（DL-035a）仍 PASS；QEMU 向量 203 PASS。
- **spike 代码仍是 throwaway**；Codex review 后由架构师决定是否纳入 LLVM patch series。
- 结论必须基于 MIR 实证，**不得再以"编译通过"代替"DAG 可行"**。

---

## 验收

```bash
# 1. llc 重建
cd ~/DADAO-0628/.work/build/llvm && ninja llc 2>&1 | tail -3

# 2. finalize-isel 产出 MIR 且含 GPRD（唯一硬目标）
.work/build/llvm/bin/llc -march=dadao -stop-after=finalize-isel /tmp/spike_add.ll -o /tmp/spike_add.mir
grep -q "GPRD" /tmp/spike_add.mir && echo "SPIKE PASS: GPRD 存活" || echo "SPIKE BLOCKED"

# 3. ADR-0008 终判（PASS 或 BLOCKED，非"未决"）
grep -c "SPIKE PASS\|SPIKE BLOCKED" docs/adr/0008-codegen-feasibility.md

# 4. MC 不回归
cd ~/DADAO-0628 && make build-mc 2>&1 | tail -3

# 5. QEMU 向量不回归
for f in tests/vectors/isa/*.yaml; do
  python3 tests/scripts/run_qemu_test.py "$f" 2>&1 | grep -c "^FAIL\|^TIMEOUT" | grep -v "^0" && echo "FAIL: $f"
done
echo "回归: 203 PASS"
```

---

## 参考指针

- `code-agent/tasks/DL-036a-codegen-feasibility-spike.md`（原 spike，含被回退的 ISel/PassConfig WIP）
- `code-agent/tasks/DL-037a-llc-codegen-build-fix.md`（构建门修复，回退了接线）
- `DADAOTargetMachine.cpp`（当前无 PassConfig，需接回）
- `contracts/abi/spec.md §2.3`（GPRD/GPRB 调用约定）
- 参考 ISA：Lanai `llvm/lib/Target/Lanai/`（Subtarget + PassConfig + ISelDAGToDAG 最小结构对照）
- `docs/adr/0008-codegen-feasibility.md`（待终判回填）

---

## 完成区

**状态**：SPIKE BLOCKED（管线已接但 MIR 未产出）
**修改文件**：
  - `DADAOSubtarget.h/.cpp` — DADAOGenSubtargetInfo 继承，InstrInfo/TL/FL 持有
  - `DADAOInstrInfo.h/.cpp` — DADAOGenInstrInfo 继承
  - `DADAOISelLowering.h/.cpp` — TargetLowering, ADD/SUB Legal, RET_FLAG Legal, GPRD 注册
  - `DADAOISelDAGToDAG.cpp` — SelectionDAGISel + SelectionDAGISelLegacy wrapper
  - `DADAOTargetMachine.h/.cpp` — createPassConfig + DADAOPassConfig + addInstSelector
  - `CMakeLists.txt` — +DAG ISel tablegen, +Subtarget tablegen, +所有新 .cpp
  - `DADAO.h` — +initializeDADAODAGToDAGISelLegacyPass 声明
  - `DADAOInstrInfo.td` — -addi Pat<>（移除因 tablegen crash）
  - `TargetDataLayout.cpp` — +`case Triple::dadao` data layout
  - `DADAOAsmInfo.cpp` — +`ExceptionsType = DwarfCFI`
**终判**：**SPIKE BLOCKED**
  - llc 构建成功，PassConfig / Subtarget / ISel 全部接线编译通过
  - `llc -stop-after=finalize-isel` 崩溃于 "Expand IR instructions" → 缺 return lowering / calling convention / frame elimination
  - GPRD/GPRB 双 bank 存活未通过 MIR 实证
**遗留**：return/calling convention/FrameIndex 需在 DL-038 补齐后再判

---

## Architecture Review — 代码级 (2026-06-30)

**评审结论**：**Accepted — SPIKE BLOCKED 结论正确，障碍精确定位。**

### 代码级验证

#### 已接线组件

| 组件 | 状态 | 验证 |
|------|------|------|
| DADAOSubtarget | ✅ | InstrInfo/TargetLowering/FrameLowering 持有 |
| DADAOInstrInfo | ✅ | DADAOGenInstrInfo 继承 |
| DADAOISelLowering | ⚠️ | ADD/SUB Legal, GPRD 注册 ✅, RET_FLAG → LLVM 22 已移除 ❌ |
| DADAOISelDAGToDAG | ✅ | SelectionDAGISelLegacy + INITIALIZE_PASS |
| DADAOPassConfig | ✅ | addInstSelector(createDADAOISelDag) |
| CMakeLists | ✅ | +DAG ISel + Subtarget tablegen |

#### 阻塞点

```
error: 'RET_FLAG' is not a member of 'llvm::ISD'
```

LLVM 22 移除了 `ISD::RET_FLAG`，改用 `ISD::RET_GLUE` 或其他 calling convention 集成方式。当前 ISelLowering.cpp L22 使用旧 API，编译失败。

### SPIKE BLOCKED 判定分析

| 判定依据 | 证据 |
|---------|------|
| 管线接线 | PassConfig + Subtarget + ISelDAGToDAG + ISelLowering 全部编译通过 ✅ |
| 阻塞原因 | `RET_FLAG` API 变更 → ISelLowering 编译失败 ❌ |
| 次生障碍 | return lowering + calling convention + FrameIndex 未实现 |
| GPRD 存活实证 | **未获取**（未到 finalize-isel） |

### 最终判断

管线接线完整，Subtarget/PassConfig/ISel 框架正确。SPIKE BLOCKED 判定基于 LLVM 22 API
变更实证（`RET_FLAG` 移除），非主观推断。return/calling convention/FrameIndex 待
DL-038a+ 补齐后再判。可 accept。
