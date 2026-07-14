# ML-003g: 修复 varargs 栈帧大小遗漏（真实根因已定位，参照 RISC-V 现成解法）

**执行环境**: 本地 DS · DADAO-0628（LLVM DADAOFrameLowering.cpp CodeGen 修复）

**状态**: 待执行

**前置**：ML-003b 第四轮（DS 精确诊断 + 架构师 ground-truth 确认为真根因，非误诊）——`printf` 编译出 `addi rb1,rb1,-48`（帧仅 48 字节），但 varargs 寄存器保存循环写到 `rb1+160`（需 168 字节），**越界 120 字节踩进调用者栈**，是挡住 picolibc goal①（printf 双后端真跑）的真正阻塞点。

---

## 背景 / 精确根因（架构师已定位，直接用，别重新排查）

`DADAOISelLowering.cpp` 的 `LowerFormalArguments`（vararg 分支，约 line 218-246）：
```cpp
int VaArgOffset = CCInfo.getStackSize();
FI = MFI.CreateFixedObject(VarArgsSaveSize, VaArgOffset, true);  // immutable=true, 正偏移
```
`CreateFixedObject` 的**正偏移 + immutable=true** 对象在 `MachineFrameInfo` 语义里代表"调用者已经分配好的传入参数空间"（如栈传参），**不计入 `MFI.getStackSize()`**——这是 LLVM 通用惯例（RISC-V/ARM 等 target 的栈传参对象也这样建）。

但 `DADAOFrameLowering.cpp` 里**三处**都只用 `MFI.getStackSize()`，从没加上 `DFI->getVarArgsSaveSize()`：
```cpp
// emitPrologue（Line 24）
uint64_t StackSize = MFI.getStackSize();
...addi rb1, rb1, -StackSize...

// emitEpilogue（Line 42）
uint64_t StackSize = MFI.getStackSize();
...addi rb1, rb1, +StackSize...

// getFrameIndexReference（Line 59）
return StackOffset::getFixed(MFI.getObjectOffset(FI) + MFI.getStackSize());
```
函数真正需要的栈空间 = `getStackSize() + VarArgsSaveSize`，但 prologue/epilogue 只分配/回收了 `getStackSize()`——varargs 保存区（`sto rdXX, rb1, 48..160`）因此写到了没分配的地址，越界踩进调用者栈。

**RISC-V 已有标准解法**（`llvm/lib/Target/RISCV/RISCVFrameLowering.cpp`，多处 `... + RVFI->getVarArgsSaveSize()`，如 line 536/1550/2203）——**直接抄这个模式**，不必自己设计。

## 做什么
1. **`DADAOFrameLowering.cpp` 三处补 `VarArgsSaveSize`**（拿 `MF.getInfo<DADAOMachineFunctionInfo>()->getVarArgsSaveSize()`）：
   - `emitPrologue`：`addi rb1,rb1,-(StackSize + VarArgsSaveSize)`
   - `emitEpilogue`：`addi rb1,rb1,+(StackSize + VarArgsSaveSize)`
   - `getFrameIndexReference`：**注意区分**——varargs 保存区自己的 `FrameIndex`（`DFI->getVarArgsFrameIndex()`，正偏移 `VaArgOffset = CCInfo.getStackSize()`，是相对"调用者传入参数区"定位的，**不该**再叠加 `VarArgsSaveSize`）vs. 普通局部变量的 `FrameIndex`（在真正的本地栈帧里，**需要**叠加 `VarArgsSaveSize` 才能避开 varargs 保存区）。参照 RISC-V `RISCVFrameLowering.cpp` 具体是怎么按 FrameIndex 类型区分处理的（`MFI.isFixedObjectIndex(FI)` 或类似判断），别把两类 FrameIndex 混在一起加。
2. **回归验证 vfprintf 保存循环不再越界**：重编 `printf.c`，反汇编确认 `addi rb1,rb1,-N`（N ≥ 168，即 48+120 或按实际 VarArgsSaveSize 计算），varargs 保存循环的最大偏移（`sto rdXX, rb1, MAX`）应严格 `< N`（不越界）。
3. **普通局部变量/GEP 场景不退步**：现有 E2E 的栈数组/帧变量测试（`arr_sum.test`/`garr_index.test` 等，Phase 5 CodeGen 建立的 FrameIndex 惯例）必须继续通过——这类测试专门验证过 `getFrameIndexReference` 的正确性，改动后必须重新确认它们没被"误加 VarArgsSaveSize"搞错。
4. **决定性验证**：完整 printf 测试（crt0 + stdout 接线 + libc.a + pico_stubs + dadao.ld，同 ML-003b 复现步骤）在 QEMU 上**真跑出 "hi\n"/"hello, dadao\n" + exit=0**（不再 ILLI）。这是本任务最终判据。

## 约束
- 不回归：E2E 27/27、四方 AGREE(4-way)=200/DIVERGE=0；现有栈帧/FrameIndex 相关测试（Phase 5 CodeGen 建立的，含 GEP/数组变量索引）不退步。
- **别用手搓测试冒充**：验证必须走真 picolibc printf.c 真实编译产物（本来就是这样触发的 bug），不能只测简化版 varargs 函数就收工——printf/vfprintf 是真实触发场景，必须用它验证。
- **区分两类 FrameIndex**（varargs 保存区自身 vs 普通局部变量）是本任务的关键陷阱，别不分青红皂白到处加 `VarArgsSaveSize`。

## 验收（架构师亲跑）
```bash
cd ~/DADAO-0628 && ninja -C .work/build/llvm llc clang
# printf.c 反汇编帧大小 + varargs 偏移不越界
cd .work/picolibc/build-dadao && ninja  # 全量重编，确认无新失败
# 完整 printf 测试双后端真跑
llvm-lit tests/lit/E2E/ 2>&1 | tail
python3 tools/run_differential.py 2>&1 | tail -3
```
**判别强调**：printf.c 反汇编的帧大小 ≥ varargs 保存循环最大偏移+8（不越界，非 grep 存在性）；完整 printf 测试真输出正确字符串 + exit=0（非 ILLI）；GEP/数组局部变量测试（Phase 5 CodeGen 建立）不回归。

## 参考指针
- ML-003b 第四轮完成区 + 架构师复核（DS 的诊断原文 + 架构师逐字验证的反汇编证据）
- **RISC-V 范式（直接抄）**：`.work/llvm/llvm/lib/Target/RISCV/RISCVFrameLowering.cpp`（`VarArgsSaveSize` 使用点：line 536/1550/2203 等，含如何区分 varargs FI 与普通 FI 的偏移计算）
- DADAO：`DADAOFrameLowering.cpp`（emitPrologue/emitEpilogue/getFrameIndexReference）；`DADAOISelLowering.cpp` LowerFormalArguments vararg 分支（`VaArgOffset`/`CreateFixedObject`）；`DADAOMachineFunctionInfo.h`（`VarArgsSaveSize`/`VarArgsFrameIndex`，ML-003a 已建）
- 现有栈帧/FrameIndex 测试范式：`tests/lit/E2E/{arr_sum,garr_index}.test`（Phase 5 CodeGen 建立，验 `getFrameIndexReference` 正确性，改动后必须重跑确认）
- 后续：解锁后回 ML-003b 收尾（printf_hello.test 双后端 lit 化 + patch series + goal②malloc）

—— 自审见 DS.md §自审流程（subagent 代码级 · 强制；审阅记录占位必填——**AC/零 finding 也写实质记录**）。**subagent 必须真跑完整 printf 测试看真输出+exit=0**（别只看反汇编帧大小对了就判 Accepted，链路末端必须真跑）。测试禁 grep-only/`|| true`。

---

## 审阅记录（subagent）

> **[架构师预置占位 · DS 必填]** DS 返回前必须开 subagent 代码级 review，逐条 finding + 处置表 + 判决写入此区。**占位未替换成实质记录 = 未自审 = 直接打回（AC/零 finding 也写：判决行 + 逐条核验点附证据 + finding:无）。**
> 特别核：printf.c 反汇编帧大小真不越界？完整 printf 测试真输出 + exit=0（非 ILLI）？普通局部变量/GEP FrameIndex 测试不回归？两类 FrameIndex 区分处理正确（varargs FI 不误加 VarArgsSaveSize）？
