# DL-066a: 修 CALL_PSEUDO_INDIRECT 误用 rb0 做绝对调用 base

**执行环境**: 本地 subagent（LLVM CodeGen，涉及跨 bank 寄存器物化）

**状态**: 通过（架构师复核）

**前置**：DG-007a 根因定位（`code-agent/tasks/DG-007a-gem5-elf-load-crash-rootcause.md` 完成区）、issue `codegen-indirect-call-rb0-misuse`（`docs/issues.yaml`）。

## 背景（DG-007a 已确认，直接复用）

`.work/llvm/llvm/lib/Target/DADAO/DADAOInstrInfo.cpp` 的 `expandPostRAPseudo`：
```cpp
case DADAO::CALL_PSEUDO_INDIRECT: {
  BuildMI(MBB, MI, DL, get(DADAO::CALL_RRII))
      .addReg(DADAO::RB0)
      .addReg(MI.getOperand(0).getReg())
      .addImm(0);
  MI.eraseFromParent();
  return true;
}
```
`call rbha, rdhb, imms12`（rrii 格式，spec §5.4）的目标公式是 `rbha[47:0] + rdhb[47:0] + sext_12(imms12)<<2`。`rbha=rb0` 按 spec §1.3 通用语义（rb0 硬件维护=PC+4）恒表示"base=PC+4"，**不是**"base=0"。上面这段代码把待调用的绝对地址（存在某个 RD 寄存器里，即 `MI.getOperand(0)`）当成 `rdhb`（偏移量），同时把 `rbha` 填成 `RB0`——实际算出的目标地址是 `PC+4 + 绝对地址`，垃圾值。

**QEMU 端目前"能跑"是巧合**：已知 open issue `QEMU-rb0-not-maintained`（QEMU 从不维护 `env->rb[0]=PC+4`，恒读 0）让这个误用侥幸抵消（`0 + 绝对地址 + 0 = 绝对地址`，凑巧算对）。gem5 正确维护 rb0=PC+4，按 spec 语义真实执行，暴露了这个 miscompilation。**这是一个真实的、不限于 picolibc 的间接调用 CodeGen bug**，一旦 `QEMU-rb0-not-maintained` 被修（该 issue 本身是 open 的，可能被其它任务修复），会在 QEMU 上同时暴露。

## 做什么

1. 修改 `CALL_PSEUDO_INDIRECT` 的展开逻辑：**不使用 `rb0` 做 base**。改用已有的 RD→RB 跨 bank 物化机制（`rd2rb`，DL-051a 引入的 `copyPhysReg` 跨 bank 桥）把 `MI.getOperand(0)` 持有的绝对地址复制进一个 scratch RB 寄存器，再发出 `CALL_RRII <scratch_rb>, RD0, 0`（base=绝对地址，offset=`rd0`=0，imm=0）。
2. Scratch RB 寄存器的选择需要在 `expandPostRAPseudo`（后寄存器分配阶段）安全进行——参考现有 `rd2rb`/`rb2rd` copyPhysReg 桥的实现方式挑一个当前确定空闲、不会踩坏调用约定（callee-save/参数传递）的寄存器，或采用寄存器分配阶段就预留好的固定 scratch（视现有基础设施而定，不要引入新的寄存器分配 pass）。
3. 确认修复后**间接调用的返回地址（RAS push）仍然正确**——`call` 指令本身在 spec 里"Return address pushed: rb0"，这部分语义不受本次改动影响（改的只是"目标地址怎么算"，不是"返回地址怎么存"），但要在验证阶段实际确认嵌套间接调用场景不出问题。

## 约束

- 不改 spec、不改 gem5/QEMU 源码（这是纯 CodeGen 侧修复）。
- 不能用"避免走这条 pseudo 展开路径"之类的规避手段（比如强制走别的 lowering path 绕过这个 bug）——要修 `CALL_PSEUDO_INDIRECT` 本身。
- 不回归：E2E 29/29、四方 AGREE(3-way)=200/DIVERGE=0、Sail AGREE(4-way)=200（间接调用相关的既有 E2E 用例，如 `printf_hello.test` 的 stdout 回调路径，必须继续在 QEMU 上正确工作）。

## 验收（架构师亲跑）

```bash
cd ~/DADAO-0628 && ninja -C .work/build/llvm llc clang lld llvm-mc
llvm-lit tests/lit/E2E/ 2>&1 | tail                       # 全绿，含 printf_hello.test（QEMU 侧，间接调用路径）
python3 tools/run_differential.py 2>&1 | tail -3          # AGREE 不回归
# 真正判别性验证：反汇编确认新的 CALL_RRII 不再用 RB0 做 base，且用 rd2rb 物化了目标地址
# 若可行，构造一个 gem5 能跑的间接调用探针（不依赖 gem5-se-heap-not-covered-by-elf-segment，
# 即不涉及 malloc）验证 gem5 上间接调用目标地址正确（不再是 PC+4+绝对地址的垃圾值）
```

**判别强调**：反汇编真实确认不再用 `rb0` 做间接调用 base；gem5 上一个不涉及堆的函数指针调用探针（例如两个简单函数之间用函数指针互调）能正确跳转到目标函数；QEMU 侧既有行为不退步。

## 参考指针

- DG-007a 完成区（`code-agent/tasks/DG-007a-gem5-elf-load-crash-rootcause.md`）：gdb 确认故障 PC/寄存器值的完整证据链
- `docs/issues.yaml` 的 `codegen-indirect-call-rb0-misuse`、`QEMU-rb0-not-maintained` 两个条目
- `contracts/isa/spec.md` §5.4（call rrii 语义）、§1.3（rb0 通用语义）
- `.work/llvm/llvm/lib/Target/DADAO/DADAOInstrInfo.cpp`（`expandPostRAPseudo`，`CALL_PSEUDO_INDIRECT`/`RET_PSEUDO` 展开逻辑，`RET_PSEUDO` 展开在同一函数里可参考写法风格）
- DL-051a 完成区（`rd2rb`/`rb2rd` copyPhysReg 跨 bank 桥的原始实现，本任务要复用同一机制）
- `tests/scripts/stdout_min.c`（`FDEV_SETUP_STREAM` 的 `my_putc` 函数指针回调，是本 bug 的真实触发点）

—— 自审见 DS.md §自审流程同等标准（subagent 自己复核，逐条 finding + 判决），**必须反汇编确认修复后的实际指令序列，不能只看代码改动"看起来对"**。

---

## 架构师复核（2026-07-14，ground-truth）：通过

- `DADAOInstrInfo.cpp` diff 审阅：`CALL_PSEUDO_INDIRECT` 改为 `rd2rb rb5, <target>, 1` + `call rb5, rd0, 0`；`imm=1` 与既有 `copyPhysReg` 里同一 `RD2RB_ORRI` 用法一致（非新猜测的写法）。
- 独立核对 `rb5` 是否真正安全：`DADAORegisterInfo::getReservedRegs` 里 `Reserved.set(DADAO::RB5)` 确认——寄存器分配器从不会把活跃值分给 rb5，不存在冲突风险；与 `contracts/abi/spec.md` 的 "rb5–rb7 (reserved)" 一致。
- 独立重跑：`ninja` 全新构建 → `llvm-lit tests/lit/E2E/` 29/30（含新增 `indirect_call.test` PASS；1 个既有失败 `syscall_hello.test` 已用 `git stash` 独立确认修复前后一致，与本任务无关）→ 四方差分 AGREE(3-way)=200/DIVERGE=0、Sail AGREE(4-way)=200，全部不回归。
- `printf_hello.test`/`malloc_hello.test` 尚未真正吃到这个修复（libc.a 是旧编译器产物）的诚实披露予以确认，issue `picolibc-libc-rebuild-blocked` 属实、未被绕过掩盖。
- issues.yaml 的 `status: resolved`→`status: closed`（schema 只认 open/closed）、`blocks` 字段清空（改用 `picolibc-libc-rebuild-blocked` 承接剩余阻塞）。

**判定**：通过，提交。
