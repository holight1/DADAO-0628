# DL-041a: CodeGen spike 收口 — 在验证过的地基上取 MIR

**执行环境**: 本地 DS · DADAO-0628

**状态**: 待执行

**前置**: CodeGen 验证链 C1+C2+C3 闭环（DL-040a/b/c）；spike WIP（DL-036a~038a）

---

## 背景

CodeGen 验证链已闭环，spike 的 CodeGen 输入现在有 oracle 背书：
- **CallingConv**：C3 机械确认与 ABI 一致（rd16-31 参数 / rd31 返回）✓
- **Reserved/allocatable**：C3 MATCH ✓
- **DataLayout**：C3 报 **1 处 MISMATCH — 后端 `S128`(16B) vs ABI §4.2 `S64`(8B)**（架构师原 DataLayout 串写错，S128 比契约严）

DL-038a 状态：llc 可构建（删了无效 `RET_FLAG`），`LowerFormalArguments`/`LowerReturn` 已实现，但 `llc -stop-after=finalize-isel`（`i64 add`）**段错误（exit 139）于 "Expand IR instructions" pass，无 MIR**。此前疑为"验证链断链导致难诊断"——现在地基已验证，可正经 debug。

---

## 目标（收口 spike）

1. 修 **S128→S64**（后端 DataLayout），确认 `check_codegen_abi` 的 MISMATCH 清零。
2. **GDB 定位** `expand-ir-insts` 段错误根因（target-wiring bug）。
3. 让 `llc -march=dadao -stop-after=finalize-isel`（`i64 add`）**产出 MIR，含 `%N:GPRD`**。
4. 据 MIR 回填 ADR-0008 **终判 SPIKE PASS/BLOCKED**（基于实证，非"编译通过"）。

---

## 接口说明书

### 1. S128 → S64

`.work/source/llvm/llvm/lib/TargetParser/TargetDataLayout.cpp` 的 `case Triple::dadao`：`...-S128` → `...-S64`（ABI §4.2 只要 8 字节栈对齐）。重建 llc 后：
```bash
python3 scripts/check_codegen_abi.py 2>&1 | grep -E "DataLayout|MISMATCH|RESULT"
```
DataLayout 应转 MATCH、MISMATCH=0、脚本 exit 0。

### 2. GDB 定位 expand-ir-insts 崩溃

```bash
cat > /tmp/spike_add.ll << 'EOF'
target triple = "dadao"
target datalayout = "E-m:e-i64:64-n64-S64"
define i64 @add_func(i64 %a, i64 %b) { %s = add i64 %a, %b  ret i64 %s }
EOF
gdb -batch -ex run -ex bt --args .work/build/llvm/bin/llc -march=dadao \
    -stop-after=finalize-isel /tmp/spike_add.ll -o /tmp/spike_add.mir
```
从 backtrace 定位崩溃的 C++ 帧（很可能是某个未初始化/未实现的 TargetLowering 钩子、Subtarget 字段、或缺 `setOperationAction` 的默认路径）。**贴真实 backtrace。**

### 3. 最小修复到出 MIR

只做让 `finalize-isel` 产出 MIR 所必需的最小改动（补缺失的 lowering 钩子/操作合法化/Subtarget 初始化）。**不扩展功能**（不做 GPRB 地址 bank、load/store、完整 asm 发射、callee-save——留后续）。

### 4. 取 MIR 并判定

```bash
.work/build/llvm/bin/llc -march=dadao -stop-after=finalize-isel /tmp/spike_add.ll -o /tmp/spike_add.mir
cat /tmp/spike_add.mir
grep -q "GPRD" /tmp/spike_add.mir && echo "GPRD 存活 → 双 bank 数据侧可行"
```
- MIR 含 `%N:GPRD` → **SPIKE PASS**（回答 DL-036a 核心问题：双 bank 在 SelectionDAG 存活）
- 若仍崩/丢 bank 分类 → **SPIKE BLOCKED**，附具体现象

### 5. 回填 ADR-0008

结论从 INCONCLUSIVE 改为 **SPIKE PASS** 或 **SPIKE BLOCKED**，附 MIR 关键片段 / 崩溃根因。若 PASS，确认 Phase 5 正式实现序列（GPRB bank、load/store、CallingConv 完整、AsmPrinter MCInst 降低）。

---

## 约束

- 只做到 MIR 的最小修复；不扩展功能。
- **不回归**：`make check` 全绿；`check_codegen_abi` 修 S128 后 MISMATCH=0；`make build-mc` + E2E lit（DL-035a）仍过；QEMU 向量 203 不退步。
- 结论必须基于 MIR 实证，**不得以"编译通过"代替"DAG 可行"**。
- spike 代码仍 throwaway；Codex review 后架构师决定是否纳入 LLVM patch series。

---

## 过程要求（reviewer 见 reviewer.md）

1. 完成区**粘贴真实终端输出**：`check_codegen_abi`（S128 修后）、GDB backtrace、`llc -stop-after=finalize-isel` 的 stdout/stderr + `cat spike_add.mir`（或崩溃）。不许重写/估算。
2. 交付前自跑通；树留可构建。
3. reviewer 独立重跑 llc + check_codegen_abi + make check，判决带自己输出，写 `## Codex Review`。

---

## 验收（架构师亲自复跑）

```bash
cd ~/DADAO-0628/.work/build/llvm && ninja llc 2>&1 | tail -3
cd ~/DADAO-0628
python3 scripts/check_codegen_abi.py; echo "codegen-abi exit=$?（S128 修后应 0）"
.work/build/llvm/bin/llc -march=dadao -stop-after=finalize-isel /tmp/spike_add.ll -o /tmp/spike_add.mir
grep -q "GPRD" /tmp/spike_add.mir && echo "SPIKE PASS" || echo "查 MIR/崩溃"
grep -c "SPIKE PASS\|SPIKE BLOCKED" docs/adr/0008-codegen-feasibility.md
make check 2>&1 | tail -3
```

---

## 参考指针

- ADR-0008（待终判回填）；DL-036a/037a/037b/038a（spike 历史 + WIP 文件）
- `scripts/check_codegen_abi.py`（C3，S128 finding 来源）；`tools/abi.yaml`（S64 契约）
- 后端：`TargetParser/TargetDataLayout.cpp`（S128→S64）、`DADAOISelLowering.cpp/.h`、`DADAOSubtarget.*`、`DADAOTargetMachine.cpp`
- 参考 ISA：Lanai（LowerFormalArguments/LowerReturn/PassConfig 最小结构）

---

## 完成区

**状态**：SPIKE PASS —— `finalize-isel` 产出含 `%N:gprd` 的 MIR，双 bank 数据侧在 SelectionDAG 存活。

**修改文件**（均在 `.work/source/llvm/`，spike throwaway）：
- `llvm/lib/TargetParser/TargetDataLayout.cpp` — `case Triple::dadao` DataLayout `-S128` → `-S64`
- `llvm/lib/Target/DADAO/DADAOTargetMachine.h` — +`#include DADAOSubtarget.h`；+`DADAOSubtarget Subtarget` 成员；+`getSubtargetImpl(const Function&)` override
- `llvm/lib/Target/DADAO/DADAOTargetMachine.cpp` — ctor 初始化列表 +`Subtarget(TT, Cpu, FeatureString, *this)`
- `llvm/lib/Target/DADAO/DADAOSubtarget.h` — +`#include SelectionDAGTargetInfo.h`；+`SelectionDAGTargetInfo TSInfo` 成员；+`getSelectionDAGInfo()` override
- `llvm/lib/Target/DADAO/DADAOSubtarget.cpp` — +`#define GET_SUBTARGETINFO_CTOR`；ctor body 构造 `TLInfo`
- `llvm/lib/Target/DADAO/DADAOISelLowering.cpp` — ctor 末尾 +`computeRegisterProperties(STI.getRegisterInfo())`
- `llvm/lib/Target/DADAO/MCTargetDesc/DADAOMCTargetDesc.cpp` — +`GET_INSTRINFO_MC_DESC` / +`GET_SUBTARGETINFO_MC_DESC` include；`createDADAOMCInstrInfo` +`InitDADAOMCInstrInfo(X)`
- `llvm/lib/Target/DADAO/DADAOInstrInfo.td` — +`DADAOPseudo` 基类 + `ADD_PSEUDO`（`(set GPRD, (add GPRD, GPRD))`）+ `RET_PSEUDO`（`(DADAORetGlue)`），均 `isPseudo=1, isCodeGenOnly=1`（不 expand、不 emit，纯 spike 脚手架）
- `llvm/lib/Target/DADAO/DADAOISelDAGToDAG.cpp` — 删除 `SelectCodeCommon(Node, nullptr, 0)` 空表 stub，改 `SelectCode(Node)`（`#include DADAOGenDAGISel.inc` 引入真实 MatcherTable）；+`#include MCTargetDesc/DADAOMCTargetDesc.h`（取指令枚举）

### 崩溃根因链（GDB 实证，逐层剥）

`finalize-isel` 的 SIGSEGV 不是单点，是 5 层未接线缺陷叠加。每修一层暴露下一层：

**层 1 — expand-ir-insts 空指针（原 exit 139 现象）**
```
Program received signal SIGSEGV
#0  ExpandIRInstsLegacyPass::runOnFunction (F=...) at ExpandIRInsts.cpp:1151
        1151    auto *TLI = Subtarget->getTargetLowering();
#1  llvm::FPPassManager::runOnFunction ... LegacyPassManager.cpp:1398
```
根因：`DADAOTargetMachine` **未 override `getSubtargetImpl(const Function&)` 且无 Subtarget 成员** → `TM->getSubtargetImpl(F)`（1150 行）返回基类默认 `nullptr` → 1151 行解引用崩溃。DL-038a 完成区把此归为 "expand-ir-insts 对 DataLayout 有隐式依赖 / 需更深 LLVM 基础设施调试" —— **错**，就是 TargetMachine 缺 Subtarget 接线。附带：`DADAOSubtarget` 从不构造 `TLInfo`（有 setter 无调用）。
→ 修：TM 加 Subtarget 成员 + override；Subtarget ctor 构造 TLInfo。牵出层 1.5 连锁 link error：`DADAOInstrNameIndices/Data`（`GET_INSTRINFO_MC_DESC` 从未编译）、`DADAOGenSubtargetInfo` vtable/ctor（`GET_SUBTARGETINFO_CTOR` 缺）、sched 表（`GET_SUBTARGETINFO_MC_DESC` 缺）—— 因 Subtarget 此前从未被实例化，这些表的缺失是潜伏的。

**层 2 — LowerArguments 越界 assert**
```
llc: SmallVector.h:297: ... [T = llvm::ISD::InputArg]: Assertion `idx < size()' failed.
#8  llvm::SelectionDAGISel::LowerArguments (F=...) at SelectionDAGBuilder.cpp:11953
#10 SelectionDAGISel::SelectAllBasicBlocks ... #11 runOnMachineFunction
```
根因：`DADAOTargetLowering` ctor **从不调用 `computeRegisterProperties()`** → `addRegisterClass(i64, GPRD)` 已注册但 类型→寄存器数 表未计算 → i64 被按默认拆分，generic LowerArguments 构建的 `Ins` 计数与 CC 分配不符 → `Ins[i]` 越界。
→ 修：ctor 末尾加 `computeRegisterProperties(STI.getRegisterInfo())`。

**层 3 — LowerReturn 的 verifyNode 空指针**
```
Program received signal SIGSEGV
#0  llvm::SelectionDAG::verifyNode (N=...) at SelectionDAG.cpp:1154
        1153    if (N->isTargetOpcode())
        1154      getSelectionDAGInfo().verifyTargetNode(*this, N);
#4  DADAOTargetLowering::LowerReturn ... #5 SelectionDAGBuilder::visitRet
```
根因：`DADAOISD::RET_GLUE` 是 target opcode → `verifyNode` 调 `getSelectionDAGInfo().verifyTargetNode()`；`DADAOSubtarget` **未提供 SelectionDAGInfo** → 基类默认返回 `nullptr` → 解引用崩溃。
→ 修：Subtarget 加 `SelectionDAGTargetInfo TSInfo` 成员 + override `getSelectionDAGInfo()`（基类 `verifyTargetNode` 为 no-op，满足最小需求）。

**层 4 — ISel matcher table 空指针**
```
Program received signal SIGSEGV
#0  SelectionDAGISel::SelectCodeCommon (NodeToMatch=..., MatcherTable=0x0, ...) at SelectionDAGISel.cpp:3432
#1  DoInstructionSelection ... #2 CodeGenAndEmitDAG
```
根因：`DADAODAGToDAGISel::Select` 是 stub，显式 `SelectCodeCommon(Node, nullptr, 0)` —— **传了 null MatcherTable**，tablegen 生成的真实 `SelectCode` 从未接入。
→ 修：`#include DADAOGenDAGISel.inc` 引入 `SelectCode`，`Select` 改调 `SelectCode(Node)`。

**层 5 — 无选择 pattern（不再是崩溃，是 "Cannot select"）**
`ADD_RRRR` 是双输出（DL-040 scope），`RET_GLUE` 无 pattern → add/ret 无法选择。
→ 修：加两个 CodeGen-only pseudo（`ADD_PSEUDO`/`RET_PSEUDO`）带 pattern，仅为让 ISel 完成产出 MIR；真实双输出 ADD_RRRR 选择与 return/AsmPrinter 降低留 DL-040+。

### 验收原始输出

**check_codegen_abi（S128→S64 修后）**
```
$ python3 scripts/check_codegen_abi.py 2>&1 | grep -E "DataLayout|MISMATCH|RESULT"
[MATCH      ] DataLayout   stack alignment S64 = 8B [abi §4.2 (SP must be 8-byte aligned before call)]
[INFO       ] DataLayout   backend string  = E-m:e-i64:64-n64-S64
[INFO       ] DataLayout   contract string = E-m:e-i64:64-n64-S64 [abi §2.2 + §4.2, isa §2.1]
MATCH=21  OPEN-COMMIT=3  INFO=3  MISMATCH=0
RESULT: PASS (no MISMATCH; OPEN-COMMIT/INFO are advisory)
$ python3 scripts/check_codegen_abi.py >/dev/null 2>&1; echo $?
0
```

**llc -stop-after=finalize-isel（最终，exit 0）+ cat spike_add.mir（关键片段）**
```
$ .work/build/llvm/bin/llc -march=dadao -stop-after=finalize-isel /tmp/spike_add.ll -o /tmp/spike_add.mir; echo exit=$?
exit=0

registers:
  - { id: 0, class: gprd, ... }
  - { id: 1, class: gprd, ... }
  - { id: 2, class: gprd, ... }
liveins:
  - { reg: '$rd16', virtual-reg: '%0' }
  - { reg: '$rd17', virtual-reg: '%1' }
body: |
  bb.0 (%ir-block.0):
    liveins: $rd16, $rd17
    %1:gprd = COPY $rd17
    %0:gprd = COPY $rd16
    %2:gprd = ADD_PSEUDO %0, %1
    $rd31 = COPY %2
    RET_PSEUDO implicit $rd31
```

**判定（含大小写发现）**
```
$ grep -q "GPRD" /tmp/spike_add.mir; echo $?   # 任务验收字面命令（大写）
1                                               # ← 假阴性：MIR 用小写 gprd
$ grep -qi "gprd" /tmp/spike_add.mir; echo $?
0
$ grep -nE "%[0-9]+:gprd" /tmp/spike_add.mir
73:    %1:gprd = COPY $rd17
74:    %0:gprd = COPY $rd16
75:    %2:gprd = ADD_PSEUDO %0, %1
```
> **发现**：MIR 的寄存器 class 打印为小写 `gprd`（LLVM 惯例：class 名小写化），任务验收里的 `grep -q "GPRD"`（大写）会假阴性。实质上 `%0/%1/%2` 三个 vreg 全是 GPRD class，`$rd16/$rd17`（参数）、`$rd31`（返回）与 ABI §2.1/§3.1 一致 —— 双 bank 数据侧完整存活。建议后续验收命令用 `grep -qi gprd` 或 `grep -q ':gprd'`。

**回归（全绿，无退步）**
```
make check                → OVERALL: PASS (exit 0)
check_codegen_abi         → MISMATCH=0 (exit 0)
MC lit  tests/lit/MC/Dadao → Passed: 14 (100%)
E2E lit tests/lit/E2E      → Passed: 3 (100%)
QEMU vectors (10 yaml)     → PASS=203 FAIL=0
ninja llc                  → no work to do（树可构建）
```

### ADR-0008 终判
已回填 `docs/adr/0008-codegen-feasibility.md`：INCONCLUSIVE → **SPIKE PASS**，附 MIR 片段 + 5 层根因链。

---

## Codex Review

**审查者独立重跑（非采信完成区），以下均为本人终端真实输出/退出码。**

### 重跑记录（验收命令块）

```
$ cd .work/build/llvm && ninja llc 2>&1 | tail -2 ; echo exit=$?
ninja: no work to do.
ninja-llc-exit=0                                  # 树可构建

$ python3 scripts/check_codegen_abi.py 2>&1 | grep -E "MISMATCH|RESULT"
MATCH=21  OPEN-COMMIT=3  INFO=3  MISMATCH=0
RESULT: PASS (no MISMATCH; OPEN-COMMIT/INFO are advisory)
$ python3 scripts/check_codegen_abi.py >/dev/null 2>&1 ; echo $?
0                                                 # S128→S64 后 MISMATCH 清零

$ .work/build/llvm/bin/llc -march=dadao -stop-after=finalize-isel /tmp/spike_add.ll -o /tmp/spike_add.mir ; echo exit=$?
exit=0                                            # 无崩溃，产出 MIR

$ grep -q "GPRD" /tmp/spike_add.mir ; echo $?     # 任务字面命令（大写）
1                                                 # ← 假阴性
$ grep -qi "gprd" /tmp/spike_add.mir ; echo $?
0
$ grep -nE "%[0-9]+:gprd" /tmp/spike_add.mir
73:    %1:gprd = COPY $rd17
74:    %0:gprd = COPY $rd16
75:    %2:gprd = ADD_PSEUDO %0, %1

$ grep -c "SPIKE PASS\|SPIKE BLOCKED" docs/adr/0008-codegen-feasibility.md
2                                                 # ADR 已回填终判

$ make check 2>&1 | tail ; echo exit=$?
... OVERALL: PASS ...
make-check-exit=0

$ .work/build/llvm/bin/llvm-lit tests/lit/MC/Dadao/    → Passed: 14 (100.00%)
$ .work/build/llvm/bin/llvm-lit tests/lit/E2E/         → Passed: 3 (100.00%)
$ for f in tests/vectors/isa/*.yaml; ... QEMU          → PASS=203 FAIL=0
```

### 目标产物核验（非"编译通过"）

- **MIR 真产出**且 `id 0/1/2` register class 均为 `gprd`；`liveins $rd16/$rd17`（参数 ABI §2.1）、`$rd31`（返回 ABI §3.1）。GPRD class 经 CopyFromReg→ADD→CopyToReg 全链存活 —— 双 bank 数据侧可行性有 MIR 实证，**非**编译通过推断。核验通过。
- **崩溃根因链**：本人复跑各中间态 GDB backtrace 与完成区所述 5 层一致（getSubtargetImpl 空指针 / computeRegisterProperties 缺失 / getSelectionDAGInfo 空指针 / MatcherTable=0x0 / 无 pattern）。均为标准 target 未接线，无一与双 bank 相关。采信。

### 约束核验（逐条）

| 约束 | 结论 |
|------|------|
| 只做到 MIR 的最小修复，不扩展功能（不做 GPRB 地址 bank / load/store / 完整 asm 发射 / callee-save） | ✅ 未触及上述；add/ret 用 CodeGen-only pseudo（`isPseudo=1,isCodeGenOnly=1`，不 expand/emit），真实 ADD_RRRR 双输出 / return 序列 / AsmPrinter 留 DL-040+ |
| 不回归：make check 全绿 | ✅ exit 0 |
| check_codegen_abi 修 S128 后 MISMATCH=0 | ✅ exit 0 |
| make build-mc + E2E lit（DL-035a）仍过 | ✅ llvm-mc/objdump 重建成功；MC lit 14/14、E2E lit 3/3 |
| QEMU 向量 203 不退步 | ✅ 203 PASS / 0 FAIL |
| 结论基于 MIR 实证，非"编译通过" | ✅ 见上，MIR 含 gprd class |
| 未改契约/spec/测试凑绿 | ✅ 改动仅 `.work/source/llvm/`（9 文件 spike throwaway）+ 本任务 md + ADR-0008；contracts/tools/scripts/tests 均未由本任务改动（mtime 核对为会前旧时间） |

### 阻断/风险提示（供架构师定夺，非放行障碍）

1. **验收命令大小写 bug（任务 spec 层面）**：MIR 的 register class 按 LLVM 惯例小写打印为 `gprd`，任务里 `grep -q "GPRD"`（大写）恒返回 exit 1，字面执行会打印"查 MIR/崩溃"造成假阴性。实质产物正确（`%N:gprd` 三处）。建议架构师将验收命令改为 `grep -qi gprd` 或 `grep -q ':gprd'`。这是**任务命令拼写缺陷**，非 worker 规避或凑绿——worker 已在完成区如实披露而非改名强凑大写。
2. spike pseudo（ADD_PSEUDO/RET_PSEUDO）为 throwaway 脚手架，Phase 5 须以真实 ADD_RRRR 双输出选择 + 真实 return/AsmPrinter 替换（ADR-0008 已列 DL-042~046 拟序列）。

### 判决

**Accepted** —— 验收命令块在本人独立重跑下全部达成实质目标：`finalize-isel` 无崩溃产出含 `%N:gprd` 的 MIR（双 bank 数据侧存活得 MIR 实证），5 层根因 GDB 实证、修复最小且守住"不扩展功能"边界，六项回归（make check / check_codegen_abi / MC lit / E2E lit / QEMU 203 / 树可构建）全绿，改动范围合规无凑绿。唯一非绿点为任务验收命令自身的大小写拼写缺陷（`GPRD` vs `gprd`），已如实标注供架构师订正，不构成 worker 交付失败。ADR-0008 终判 SPIKE PASS 有 MIR 证据支撑，可接受。
