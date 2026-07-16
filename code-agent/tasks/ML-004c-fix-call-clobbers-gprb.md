# ML-004c: 修复 CALL 指令未声明 GPRB caller-saved RegMask

**执行环境**: 本地 subagent（LLVM CodeGen 修复，寄存器分配正确性）

**状态**: 通过（架构师复核，★ llvm-test-suite 目录 20/20 全通过）

**前置**：issue `codegen-call-clobbers-gprb-not-declared`（`docs/issues.yaml`），根因已由 ML-004b 精确定位并附最小复现，架构师已独立验证。这是当前 llvm-test-suite 10 个失败用例里 8 个的共同根因，杠杆最大。

## ⚠️ 硬性约束（与 DL-068b/ML-004b 相同，必读）

**禁止对 `.work/llvm`（或任何 `.work/<component>`）做 `git rebase`/`git am` 重放整条历史/`git reset` 之类改写既有 git 历史的操作**。只允许在当前 HEAD 基础上做普通的、追加式的新提交 + `git format-patch` 生成新 patch 加入 series（参照 DL-065a/DL-066a/DL-067b/DL-068b 的模式）。若排查中怀疑 patch series 有问题，如实报告，不要自己动手"验证"或"重建"。

## 背景（issue 里已有完整根因，直接复用）

`DADAOInstrInfo.td` 里寄存器分配阶段唯二可见的 CALL 类指令——`CALL_IIII`（直接调用）和 `CALL_PSEUDO_INDIRECT`（间接调用伪指令）——都只声明 `Defs=[RD31]`，`DADAOISelLowering::LowerCall` 从未调用 `getCallPreservedMask()` 或把结果附加成 RegMask 操作数。`DADAORegisterInfo::getCallPreservedMask` 本身实现是对的（rb8 及以上正确不在 preserved 集合里），但没有接到 CALL 指令上——寄存器分配器因此不知道 GPRB（地址寄存器）bank 除 rb0-7（reserved）外全部是 caller-saved，导致"调用前算好一个 GPRB 地址值→发生调用→调用后继续用这个地址值"的模式下，陈旧值被静默复用（未被调用方实际改写导致的值错，或落在错误对齐边界导致 MALIGN）。

最小复现（issue 里已给出，架构师已独立验证 host=36/QEMU=21）：
```c
static unsigned garr[4]={10,20,30,40}, scratch_slot;
static unsigned touch(unsigned x){return x+1;}
int main(void){
  unsigned acc=5; acc=acc*3;
  unsigned v=garr[1];
  unsigned r=touch(v);
  scratch_slot=acc+r;
  return scratch_slot;
}
```

## 做什么

1. 在 `DADAOISelLowering::LowerCall` 里，给 `DADAOISD::CALL` 的 SDNode（或对应的 MachineInstr 构造路径）附加 `DAG.getRegisterMask(TRI->getCallPreservedMask(MF, CallConv))` 操作数——标准 LLVM 模式（参照其它 target 的 `LowerCall` 实现，比如 RISC-V）。
2. 确认这条 RegMask 正确传递到 `CALL_IIII`（直接调用）和 `CALL_PSEUDO_INDIRECT`（间接调用）两条指令的 MachineInstr（参照 DL-065a/DL-066a 修 CALL 相关 SDNode→MachineSDNode 操作数传递链路的方法——这是同一大类"CALL 指令操作数在 DAGToDAG Select 阶段丢失/未正确传递"问题的第三次修复，前两次的排查方法直接复用）。
3. **验证**：
   - 最小复现 `garr`/`touch` 用例双后端跑出正确值（36）。
   - 补充判别性探针：至少覆盖"调用前后都用同一个 GPRB 值"（数组/全局变量地址）、"嵌套调用"、"调用参数本身就是 GPRB 类型（指针）"几种组合，确认修复没有引入新问题（比如误伤了参数传递本身用到的 GPRB 寄存器）。
   - `tests/lit/E2E/llvm-test-suite/` 目录下此前因这个 bug 失败的用例（`crc8.le`/`crc16.be`/`popcount-clz-ctz`/`divtest`/`long_shifts`/`loopbug`/`loopbug2`/`int_overflow`，源码/参考见 ML-004b 完成区）重新尝试，如实报告修复后能过几个（可能还有其它独立问题混在个别用例里，不强求全部通过）。
   - **全量差分向量 + 全 E2E 回归**（这是本任务约束明确要求的，因为改动涉及所有 CALL 相关的寄存器分配决策，影响面广）。

## 约束

- 不要为了让某几个具体测试过而打局部补丁——要修 `LowerCall` 本身让 RegMask 正确附加，这是通用、影响全部调用点的修复。
- 修复后**必须做全量四方差分 + 全 E2E**（不能只跑受影响的几个用例），因为这类底层寄存器分配语义改动理论上可能影响所有涉及函数调用的既有测试（哪怕它们此前没暴露这个 bug，也要确认没有引入回归）。
- 不回归：E2E 全绿（含 `syscall_hello.test` 已知无关失败）、四方 AGREE(3-way)=200/DIVERGE=0、Sail AGREE(4-way)=200，以及 `indirect_call.test`/`align_strfn.test` 等此前修复的回归测试。

## 验收（架构师亲跑）

```bash
cd ~/DADAO-0628 && ninja -C .work/build/llvm llc clang
llvm-lit tests/lit/E2E/ 2>&1 | tail
python3 tools/run_differential.py 2>&1 | tail -3
llvm-lit -v tests/lit/E2E/llvm-test-suite/ 2>&1 | tail -30
```

**判别强调**：最小复现真正返回正确值（非仅"不崩溃"）；全量差分/E2E 无回归（这次改动影响面广，格外要看这个）；如实报告 llvm-test-suite 目录下修复后的通过数变化。

## 参考指针

- `docs/issues.yaml` 的 `codegen-call-clobbers-gprb-not-declared` 条目（完整根因、两个独立最小复现 `rbreuse.c`/`snapshot_bug2.c`、`DADAORegisterInfo::getCalleeSavedRegs`/`getReservedRegs`/`getCallPreservedMask` 的现状核实）
- ML-004b 完成区（`code-agent/tasks/ML-004b-llvm-test-suite-triage-expand.md`，8 个受影响用例列表）
- DL-065a/DL-066a 完成区（同一大类"CALL 指令 SDNode 操作数传递"问题的两次前例，排查/修复方法论直接复用）
- `.work/llvm/llvm/lib/Target/DADAO/DADAOISelLowering.cpp`（`LowerCall`）、`DADAOISelDAGToDAG.cpp`（`Select` 里 CALL 相关分支）、`DADAORegisterInfo.cpp`（`getCallPreservedMask`/`getCalleeSavedRegs`/`getReservedRegs`）

—— 自审见 DS.md §自审流程同等标准（subagent 自己复核，逐条 finding + 判决）。**必须做全量差分+E2E 回归**（不是抽样跑受影响的几个测试）；**严格遵守不碰 patch/git 历史的约束**。

---

## 架构师复核（2026-07-16，ground-truth）：通过

### 硬性约束遵守情况
- `.work/llvm` git log 确认干净的 additive 提交（`ab11cbd8e94e`，在 `778e62ed55f0` DL-068b 之上），无 rebase/am/reset 痕迹。

### 独立验证
- 全新 `ninja` 重建；`rbreuse.c` 最小复现独立跑：host=36/QEMU=36/gem5=36（此前 QEMU=21/gem5=SIGABRT）。
- `llvm-lit -v tests/lit/E2E/llvm-test-suite/`：**20/20 全部真 PASS**（含此前受阻的全部 8 个）。
- 全 E2E 50/51（同一已知无关的 `syscall_hello.test` 失败，51=43+8 新增，与报告吻合）、四方 AGREE(3-way)=200/Sail AGREE(4-way)=200，不回归。
- `issues.yaml`/`manifest_check.py` 均 PASS。

### 意外发现的第二个真实 bug（本任务修复过程中的连带修正，非范围膨胀）
`DADAOInstrInfo::storeRegToStackSlot`/`loadRegFromStackSlot` 此前把 GPRB（地址 bank）和 GPRD 寄存器都路由到同一套 RD-bank 的 `STO_FI`/`LDO_FI` pseudo——本次 RegMask 修复让寄存器分配器**史上第一次**真的去溢出一个跨调用存活的 GPRB 值时，才暴露这个潜伏的编码错误（GPRB 寄存器序号被当成 RD 寄存器序号错误编码）。新增 `LDO_RB_FI`/`STO_RB_FI`（对应 spec §4.1 RB-bank load/store），正确路由。这是必要的连带修复，不是范围膨胀——没有它 RegMask 修复本身反而会引入新的溢出正确性问题。

**判定**：通过，提交。★ **ML-004 系列（llvm-test-suite 首轮）完整收官：20/20 全通过，10 个失败全部归零**。
