# ML-003c: 真修函数指针间接调用（CALL callee 类型分流，RISC-V pattern 范式）

**执行环境**: 本地 DS · DADAO-0628（LLVM DAGToDAG/InstrInfo.td 后端实现）

**状态**: DS 判 blocked（诚实自审，非造假）→ 架构师亲修一轮（用户授权）→ **部分修复，真工作但有窄范围剩余 bug** → 剩余交 ML-003d

---

## 架构师亲修记录（2026-07-13，用户授权"架构师亲自试一轮"）

### 复核 DS 这轮：诚实但归因有出入
DS 这轮 subagent 判"needs-fix/blocked"——**诚实自审**（非造假），但归因（"pattern-based 触发 BuildSchedUnits，需 PseudoCALL+expandPostRAPseudo"）与我独立核实的略有差异：我查实 RISC-V 的 `PseudoCALL` 确实是 **Pseudo**（非直接 pattern→真实指令），且 **DADAO 自己已有验证过的同款机制**（DL-054a `expandPostRAPseudo`，`RET_PSEUDO`/`ADD_PSEUDO` 已用）——比抽象抄 RISC-V 更直接可行。

### 修法与结果
1. 加 `CALL_PSEUDO_INDIRECT`（`DADAOPseudo<(outs),(ins GPRD:$reg),[(DADAOcall GPRD:$reg)]>`）+ `expandPostRAPseudo` case（同 `RET_PSEUDO` 模板，`BuildMI(CALL_RRII).addReg(RB0).addReg(reg).addImm(0)`）。
2. **关键发现（缩小 DS 的问题范围）**：直接尝试把 `CALL_PSEUDO_DIRECT`（`tglobaladdr`/`texternalsym` pattern）也走 Pseudo 化——**仍然崩在同一 `BuildSchedUnits` 断言**（证实问题不在"是否 Pseudo"，而在"把 `tglobaladdr`/`texternalsym` 直接绑定为 chain+glue `DADAOcall` 节点的 Pat<> 操作数"本身）。
3. **混合方案**：直接调用（callee=`TargetGlobalAddress`/`TargetExternalSymbol`）**保留原手动 `getMachineNode` 构造**（这部分从没坏过，原 bug 只是"无条件应用于所有 callee"范围错了）；间接调用（callee=纯寄存器）**改走 pattern-based `CALL_PSEUDO_INDIRECT`**（验证工作）。DAGToDAG 只保留一个类型判断分支，删除了原来"无条件 CALL_IIII"的错误逻辑。

### ✅ 验证工作（disassembly 实证）
```
void (*g)(void); void f(void){ g(); }     →  call rb0, rd31, 0   (CALL_RRII, 不崩)
int callee(int); int main(){ callee(5); } →  call callee          (CALL_IIII, 不退步)
```
E2E 27/27、四方 AGREE(4-way)=200/DIVERGE=0，无回归。

### ⚠ 新发现：窄范围剩余 bug（间接调用 + 返回值 + 特定形状，不是简单的"有无返回值"）
决定性测试 `vfprintf.c`（picolibc 真实文件，本任务的最终目标）**仍崩**——同一 `BuildSchedUnits` 断言，但触发条件更窄：不是所有"间接调用+非void返回"都崩，是特定组合。`llc -debug-only=isel` 抓到线索：崩溃前 `CopyFromReg` 的 glue 操作数是可疑的 `TargetConstant:i64<0>`（应为真 glue 值）——指向**返回值 `CopyFromReg` 与间接调用 pattern 生成的 glue chain 在某些形状下不一致**。

**复现矩阵**（架构师验证，供 ML-003d 直接用）：
| 用例 | 特征 | 结果 |
|------|------|------|
| `void(*g)(int); void f(){g(5);}` | 全局callee, void返回, 常量参数 | ✅不崩 |
| `int(*g)(void); int f(){return g();}` | 全局callee, int返回, 无参数 | ❌崩 |
| `int f(int(*g)(int)){return g(5);}` | 局部callee, int返回, 常量参数 | ✅不崩 |
| `int f(int(*g)(int),int x){return g(x);}` | 局部callee, int返回, **变量**参数 | ❌崩 |
| `int f(int(*g)(void)){return g();}` | 局部callee, int返回, 无参数 | ✅不崩 |
| `struct S{int(*put)(char,void*);void*ctx;}; int f(struct S*s,char c){return s->put(c,s->ctx);}` | 结构体成员callee, int返回, 2参数 | ✅不崩 |
| **`int(*g)(int); int f(){return g(5);}`（picolibc callback 最贴近形状）** | 全局callee, int返回, 常量参数 | ❌崩 |

对照：**直接调用**（同返回值/参数组合，`int callee(void); int f(){return callee();}` 等）**全部不崩**——确认 bug 严格限于新增的间接调用 pattern 路径，非既有回归。

### 未提交
本次改动（DADAOISelDAGToDAG.cpp 类型判断分支 + DADAOInstrInfo.td/.cpp 的 CALL_PSEUDO_INDIRECT）留在 `.work/llvm` 工作树，**与 ML-003a/b 累积的后端改动一起**，等 goal① 最终收口再一并提交（原计划不变）。

**前置**：ML-003a/b（picolibc printf 卡在间接调用——tinystdio 的 `FILE` 用函数指针分派 `put`/`get`，**间接调用是 goal① 的硬前提，非边角**）。历史：DL-063b/c（2026-07-12，同一问题磨 3 轮，决策 C 曾 defer）。本次架构师 ground-truth 复核 ML-003b 定位到**精确根因**（比之前"scheduler crash"清楚），用户 2026-07-13 决定**真修**（不再绕）。

---

## 背景 / 精确根因（架构师已定位，直接用，别重新排查）

`DADAOISelDAGToDAG.cpp` 里 `Opc == DADAOISD::CALL` 的手动 Select 分支**无条件**构造 `CALL_IIII`（直接调用/imm24 编码）：
```cpp
if (Opc == DADAOISD::CALL) {
  ...
  MachineSDNode *Call = CurDAG->getMachineNode(
      DADAO::CALL_IIII, DLC, MVT::Other, MVT::Glue, {Callee, Chain, Glue});
  ...
}
```
**从不判断 `Callee` 是 `GlobalAddress`（该走 CALL_IIII，symbol relocation）还是寄存器值（间接调用，该走 `CALL_RRII`）**。`DADAOISelLowering.cpp` 的 `getDADAOCallOp()` 同样是死分支——两个 if 分支都 `return DADAOISD::CALL`，从未真正区分。间接调用时 `Callee` 是寄存器值（函数指针 load 结果），被硬塞进 CALL_IIII 的 imm24 操作数位置 → MC 编码器 `getImm24OpValue` 断言 `MO.isExpr()` 失败（或更早在 `DoInstructionSelection` 里 `getOperand` 断言，视具体 IR 而定）。

**这不是新 bug**，是 DL-063b/c 已定位过的同一根因（"Select() 拦截了所有 CALL 走向，从不进 SelectCode"），DS 这轮（ML-003b）又试了 5 种手动 `getMachineNode` 方案（均撤销），没有触及真正修法。

## 正确做法：纯 pattern-based，参照 RISC-V（已验证的成熟范式）

**RISC-V 完全不在 DAGToDAG 手动拦截 CALL**——全靠 TableGen pattern 按操作数类型自动分流（`llvm/lib/Target/RISCV/RISCVInstrInfo.td`）：
```tablegen
def : Pat<(riscv_call tglobaladdr:$func), (PseudoCALL tglobaladdr:$func)>;
def : Pat<(riscv_call texternalsym:$func), (PseudoCALL texternalsym:$func)>;
def PseudoCALLIndirect : Pseudo<(outs), (ins GPRJALR:$rs1), [(riscv_call GPRJALR:$rs1)]>, ...;
```
TableGen 生成的 `SelectCode` 匹配器**自动**按 `$func` 的 SDNode 类型（`GlobalAddressSDNode` / `ExternalSymbolSDNode` / 普通寄存器值）选中对应 pattern——**不需要任何手动 `Select()` 拦截或 `getMachineNode` 构造**。

## 做什么
1. **删除/收窄手动拦截**：`DADAOISelDAGToDAG.cpp` 的 `if (Opc == DADAOISD::CALL) { ... }` 手动分支**去掉**，改为让 `SelectCode(Node)`（tablegen 生成的匹配器）处理——同 BRIND 已有模式清理时一并去掉**重复的 `if (Opc == DADAOISD::BRIND)` 死代码块**（当前有两处一样的判断，第二处不可达，顺手清）。
2. **加 TableGen pattern**（`DADAOInstrInfo.td`，仿 RISC-V 上面 3 条）：
   - `(dadao_call tglobaladdr:$func)` → `CALL_IIII $func`（直接，symbol relocation，同现有 call24 fixup）
   - `(dadao_call texternalsym:$func)` → `CALL_IIII $func`（外部符号同 direct 路径，跨对象已有 `R_DADAO_CALL24` 重定位，见 DL-064b）
   - `(dadao_call GPRx:$reg)` → `CALL_RRII $rb0, $reg, 0`（间接，寄存器持函数指针值）——**GPRx 是 GPRB 还是 GPRD 待你核实**：`CALL_RRII` 现声明 `(ins GPRB:$rbha, GPRD:$rdhb, imms12:$imm12)`，但函数指针是**指针类型**，按 Phase 5 CodeGen 既有 ABI 约定（DL-050a/051a）指针应活在 **GPRB**——核对 `rdhb` 该不该是 `GPRB`（并按需改 `.td` 里 `CALL_RRII`/`JUMP_RRII` 的操作数类型），或者用已有 `RD2RB_ORRI`/`RB2RD_ORRI` 桥转换后再喂给 pattern。以现有 `lowerBRIND`→`JUMP_RRII`（`{RB0, Target, 0}`）的手动构造为参考，但**改造成 pattern 形式**而非手动 `getMachineNode`。
3. **`DADAOISD::CALL` 的 `SDTypeProfile`**：目前似未见显式定义（`getDADAOCallOp` 死分支，未检查 profile 文件）——核实 `SDT_DADAOCall` 定义是否需要补上（对齐 RISC-V `SDT_RISCVCall`），保证 pattern 匹配时类型系统一致。
4. **`getDADAOCallOp` 清理**（`DADAOISelLowering.cpp`）：若判断逻辑最终不需要（因为分流移到 tablegen pattern），可以简化/删除死分支；若仍需要区分不同 `DADAOISD` 节点类型（如 tail-call 未来），保留但去掉死分支。
5. **回归验证**：
   - 最小间接调用：`void (*g)(void); void f(void){ g(); }` → `clang -target dadao -O0 -c` **不崩**，反汇编含 `call $rbha, $rdhb, 0`（CALL_RRII）。
   - 直接调用不退步：现有 E2E（`nested_call.test` 等）双后端仍对。
   - **picolibc goal① 解锁验证**：`vfprintf.c`（真实触发间接调用的文件）能编译（`-O0`，同 ML-003b 复核用的 meson 真实 flags）。
6. **E2E + 四方**：不回归。

## 约束
- **纯 pattern-based**，不手动 `getMachineNode` 拼 CALL_RRII/CALL_IIII 操作数（DL-063b/c 教训：手动构造在 scheduler/编码层反复出问题；RISC-V 证明 pattern-only 是对的路）。
- 不回归：E2E 27/27 + 四方 AGREE(4-way)=200/DIVERGE=0；直接调用（现有 nested_call 等）不退步。
- **真实文件验证，非玩具**：用 `vfprintf.c`（ML-003b 已知崩溃样本，真实触发间接调用）复测，不能只测最小 C 片段就收工。
- 若 `CALL_RRII`/`JUMP_RRII` 的 `rdhb` 操作数类型需要从 `GPRD` 改 `GPRB`，**核对不影响现有 `JUMP_RRII` 用例**（`brind`/switch 跳转表 ML-003a 已用，DL-058a 系列间接跳转），改动前确认现有寄存器类兼容或需要单独调整。

## 验收（架构师亲跑）
```bash
cd ~/DADAO-0628 && ninja -C .work/build/llvm llc clang
# 最小间接调用不崩 + 反汇编含 CALL_RRII
echo 'void (*g)(void); void f(void){ g(); }' > /tmp/ind.c
.work/build/llvm/bin/clang -target dadao -O0 -S /tmp/ind.c -o - | grep -E "call"
# vfprintf.c 真实文件编译(picolibc 源, 用 ML-003b 记录的 meson 真实 flags)
# E2E + 四方
llvm-lit tests/lit/E2E/ 2>&1 | tail
python3 tools/run_differential.py 2>&1 | tail -3
```
**判别强调**：反汇编真出现 `CALL_RRII`（非全 CALL_IIII 硬编）；vfprintf.c 真编过（非 crash）；直接调用（nested_call 等）双后端不退步。

## 参考指针
- ML-003b 完成区 + 审阅记录（DS 5 次失败尝试记录、崩溃现象——**别重复踩同样的手动 getMachineNode 坑**）
- **RISC-V 范式（直接抄，已验证）**：`.work/llvm/llvm/lib/Target/RISCV/RISCVInstrInfo.td` 行 1825-1843（`riscv_call` pattern 三条）、`RISCVISelLowering.cpp` 的 `RISCVISD::CALL` 构造（LowerCall 只发 chain-based CALL 节点，不在 DAGToDAG 手动分流）
- DADAO 现有：`DADAOISelDAGToDAG.cpp`（当前手动 CALL/BRIND 拦截，含重复 BRIND 死代码）；`DADAOInstrInfo.td`（`CALL_IIII`/`CALL_RRII`/`JUMP_RRII` 定义、`RD2RB_ORRI`/`RB2RD_ORRI` 桥，DL-050a/051a 指针 ABI 惯例）；`DADAOISelLowering.cpp`（`getDADAOCallOp` 死分支、`lowerBRIND`）
- roadmap 间接调用 defer 记录（`docs/development-roadmap.md`）、DL-063b/c memory 数据点（同问题第 1-2 轮）
- 后续：解锁后回 ML-003b（picolibc goal① printf 双后端）

—— 自审见 DS.md §自审流程（subagent 代码级 · 强制；审阅记录占位必填——**AC/零 finding 也写实质记录**）。**subagent 必须真跑最小间接调用 + vfprintf.c 真实文件**看不崩、反汇编含 CALL_RRII，别只读代码判 Accepted（DL-063b/ML-003b 教训：这类问题必须真跑验证，"看起来对"不可靠）。

---

## 审阅记录（subagent）

### 审阅记录（subagent · 判决 = needs-fix）

**改动文件**：DADAOInstrInfo.td, DADAOISelDAGToDAG.cpp, DADAOISelLowering.cpp

**核验点**：
- ✅ getDADAOCallOp 死分支删除 — 正确，两个分支均 return CALL，直接 inline
- ✅ ExternalSymbol → TargetExternalSymbol 转换 — 正确，libcall 路径预备
- ✅ SDT_DADAOCall 类型 profile — `(0, 1, [SDTCisVT<0, i64>])` 正确
- ✅ DADAOcall SDNode + SDNPHasChain/SDNPOptInGlue/SDNPOutGlue — 定义完整
- ✅ E2E 27/27 PASS（manual handler 保持）

**子查找发现 finding**：

| # | finding | 处置 | 说明 |
|---|---------|------|------|
| F1 [MEDIUM] | SDNPOutGlue 缺失 → pattern 无法正确连接 glue output → scheduler crash 根因之一 | ✅已修 | DADAOInstrInfo.td 加 SDNPOutGlue |
| F2 [HIGH] | Pattern-based ISel 创建 MachineSDNode 后 scheduler `BuildSchedUnits` 对 non-Machine SDNode operand（tglobaladdr）触发 `getValueType(ResNo)` assertion | ⏸ blocked | 需 Pseudo+Pseudo expander 或 deeper ISel fix。RISC-V 的 PseudoCALLIndirect 方案已验证但 Pseudo 的 operand 跟踪仍有调度冲突。manual handler（CALL_IIII for all）保底 ✅ |
| F3 [LOW] | getOperand(2) 边界检查缺失（0-arg 函数时 crash） | ✅已修 | DAGToDAG 加 `NumOps > 2` guard |

**判决**：needs-fix（F2 pattern-based 间接调用 blocked，已有 manual handler 保底）

**可在下一轮独立任务的改进**：
1. 使用 PseudoCALL + PseudoCALLIndirect（经 expandPostRAPseudo → CALL_IIII/CALL_RRII），完全仿 RISC-V 二阶段 lowered pattern
2. Pseudo 的 operand 使用 `MO_GlobalAddress`/`MO_Register`（非 SDNode 引用）避免调度冲突
3. 间接调用 + 非 void 返回函数的 glue + CopyFromReg 完整测试
