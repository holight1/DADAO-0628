# ML-003k: 跳转表悬空条目修复（死块合并未同步更新 MachineJumpTableInfo）

**执行环境**: 本地 DS · DADAO-0628（LLVM SelectionDAG/MachineFunction pass 调试，跳转表生命周期）

**状态**: 待执行

**前置**：ML-003j（DS 定位 + 架构师 ground-truth 确认为真根因）——`vfprintf.c` 用真实 flags 编译报"Undefined temporary symbol"，根因不是 section/重定位问题，是**跳转表悬空条目**：`.LBB0_19`（`.LJTI0_0` 的一个条目）、`.LBB3_13`（`.LJTI3_0` 的一个条目）在整个汇编输出里只作为 `.quad` 引用出现过一次，**从无对应的基本块标签定义**——某个基本块被消除/合并，但跳转表条目没跟着更新。已提交的 `rela_page`/`rela_lo` 同 section 快速路径（commit `eac74b0ed86e`/patch 0030）本身正确，但不解决这个问题（问题在更早的 codegen 阶段，不在 MC 层）。

---

## 背景（架构师已定位到具体触发点，直接用）

`vfprintf.c` 第一个 switch（`libc/stdio/vfprintf.c` line 376）：
```c
switch (c) {
case '0':
    continue;
case '+':
case ' ':
    continue;
case '-':
    continue;
case '#':
    continue;
case '\'':
    continue;
}
```
**每个 case 的函数体完全相同**（都只是 `continue;`）。**怀疑触发条件**：LLVM 常见的"合并语义相同的基本块"优化（tail-merging/cross-jump-elimination，在 `BranchFolder` pass 里）会识别多个 case 对应的基本块内容完全一致，将它们合并成一个、重定向所有前驱到幸存的那个块，**消除其它块**。如果这发生在跳转表（`MachineJumpTableInfo`）已经构造好、记录了"这个 case 值 → 那个即将被消除的块"之后，且合并逻辑没有同步调用 `MachineJumpTableInfo::ReplaceMBBInJumpTables()`（把跳转表里指向被消除块的条目重定向到幸存块）或 `RemoveJTI()`，就会正好留下这种"跳转表条目引用一个从未真正生成的基本块"的悬空状态——**与观察到的现象完全吻合**。

## 做什么
1. **确认触发通道**：用 `-print-after-all`（`llc` 直接跑，不经 clang 驱动）或对比 `-mllvm -disable-branch-fold` 前后的 `.s` 输出/跳转表条目——如果关掉 `BranchFolder`（或其它疑似的 block-merging pass）后 `.LBB0_19`/`.LBB3_13` 变得有定义（或跳转表条目本身消失了），就证实是这条 pass 干的。
2. **确认根因具体是哪个 pass/哪个调用点**没有同步更新跳转表：
   - LLVM 通用基础设施 `MachineJumpTableInfo` 提供了 `ReplaceMBBInJumpTables(MBB *Old, MBB *New)`、`RemoveJTI(unsigned Idx)` 这类接口，**正常情况下**基本块合并/删除类 pass（`BranchFolder`、`UnreachableMachineBlockElim` 等）在消除/合并块时会调用这些接口同步维护跳转表——需要确认 DADAO 这条链路上到底是哪一步没触发、或者是不是 DADAO 自定义的 `BR_JT`/`JumpTable` custom lowering（ML-003a 添加的）导致跳转表用了一种通用 pass 认不出来的表示方式，从而这些 pass 压根不知道要去更新它。
   - 检查 `DADAOISelLowering.cpp` 里 `BR_JT`/`JumpTable` 相关 lowering，跳转表的构造方式是否标准（是否正确注册进 `MachineJumpTableInfo`，还是绕过了标准接口自己攒了一份"影子"数据结构，导致通用 pass 的同步机制够不着）。
3. **修复**：
   - 若是 pass 顺序/调用点缺失：确保 block 合并/消除发生时正确调用 `ReplaceMBBInJumpTables`/`RemoveJTI`（可能需要在 DADAOTargetMachine 的 pass 配置里调整，或者是 LLVM 通用 pass 本身有调用但 DADAO 的跳转表表示方式不兼容，需要让 DADAO 的表示方式符合标准接口预期）。
   - 若是 DADAO 自己的 custom lowering 问题：修正跳转表构造/更新逻辑，确保它和标准 `MachineJumpTableInfo` 生命周期一致。
4. **验证**：`vfprintf.c` 用真实 flags（含 `-ffunction-sections`）编译 **0 错误**；反汇编确认跳转表里不再有引用不存在标签的条目；完整 printf 测试（crt0+stdout接线+libc.a+pico_stubs+dadao.ld）在 QEMU 上**真跑出正确字符串输出 + exit=0**——这是 goal① 最终判据。
5. **回归**：E2E 27/27、四方 200/0；已提交的三处修复（offset 踩踏修复、section 路由标准化、rela 同 section 快速路径）不退步。

## 约束
- 不回归：`.work/llvm` commit `45d59391b3c3`（offset 踩踏修复）、`4f2967eac9ec`（section 路由标准化）、`eac74b0ed86e`（rela 快速路径）都不退步。
- **禁止绕过**（如给这类 switch 强制关掉跳转表优化、或手动补一个假的空 `.LBB` 标签哄骗汇编器过关）——要修的是"消除/合并块时忘记同步跳转表"这个真正的生命周期管理缺口。
- 修复后**必须真跑通完整 printf 测试**，不能停在"vfprintf.c 编译通过"。

## 验收（架构师亲跑）
```bash
cd ~/DADAO-0628 && ninja -C .work/build/llvm llc clang
cd .work/picolibc/build-dadao
# 真实 flags 编译 vfprintf.c，应 0 错误
cd ~/DADAO-0628
llvm-lit tests/lit/E2E/ 2>&1 | tail
python3 tools/run_differential.py 2>&1 | tail -3
# 完整 printf 测试双后端真跑
```
**判别强调**：`vfprintf.c` 真编译通过（非绕过）；跳转表条目全部指向真实存在的标签；完整 printf 测试真输出正确字符串 + exit=0；E2E/四方不回归。

## 参考指针
- ML-003j 完成区 + 架构师复核（`.LBB0_19`/`.LBB3_13` 悬空引用的复现方式、疑似触发源码位置）
- `llvm/lib/CodeGen/BranchFolding.cpp`（block 合并/tail-merge 逻辑，检查有没有调用跳转表同步接口）
- `llvm/include/llvm/CodeGen/MachineJumpTableInfo.h`（`ReplaceMBBInJumpTables`/`RemoveJTI` 标准接口）
- `DADAOISelLowering.cpp`（`BR_JT`/`JumpTable` custom lowering，ML-003a 添加）
- `libc/stdio/vfprintf.c` line 376（疑似触发源码：多个函数体完全相同的 case）
- 后续：解锁后回 ML-003b 收尾 goal①（picolibc 后端 enablement 里程碑，这是最后一块拼图）

—— 自审见 DS.md §自审流程（subagent 代码级 · 强制；审阅记录占位必填——**AC/零 finding 也写实质记录**）。**subagent 必须真编译 vfprintf.c + 真跑完整 printf 测试**，别用绕过手段冒充修复。

---

## 审阅记录（subagent）

> **[架构师预置占位 · DS 必填]** DS 返回前必须开 subagent 代码级 review，逐条 finding + 处置表 + 判决写入此区。**占位未替换成实质记录 = 未自审 = 直接打回（AC/零 finding 也写：判决行 + 逐条核验点附证据 + finding:无）。**
> 特别核：是否真定位了跳转表未同步更新的具体 pass/调用点（有实测证据，非猜测）？`vfprintf.c` 真编译通过？完整 printf 测试真跑出正确输出 + exit=0？E2E/四方不回归？无绕过/workaround？
