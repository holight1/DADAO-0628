# ML-003i: 跳转表 section 修复后暴露的 MC 汇编器崩溃（根因分析任务）

**执行环境**: 本地 DS · DADAO-0628（LLVM MC 层调试，需 gdb 定位崩溃）

**状态**: 待执行

**前置**：ML-003h（打回 + 架构师亲自修一轮）——架构师定位并修好了跳转表 section 归属 bug（`emitJumpTableInfo` 不该切去通用 `.text`，已修复提交 `.work/llvm` commit `851ad359b2e1`/patch 0027），但修复后**暴露了一个更深的 MC 汇编器崩溃**，本任务是纯粹的根因调试。

---

## 背景（架构师已排查清楚，直接用）

### 已修好的部分（别重新排查）
DS 上一轮（ML-003h）诊断"vfprintf.c + -ffunction-sections 编译失败"时，尝试了两处 LLVM 改动：
1. `DADAOAsmPrinter.cpp` 覆写 `emitJumpTableInfo()`，想把跳转表内联进函数自己的 section——但实现里 `switchSection(Text)` 切的是 `OutContext.getObjectFileInfo()->getTextSection()`（**通用/默认 `.text`**），`-ffunction-sections` 下这和函数体所在的 `.text.vfprintf`是**不同 section**，问题没解决。
2. `DADAOAsmBackend.cpp` 给 `rela_page`/`rela_lo`/`FK_Data_8` 加了"临时符号一律走重定位"逻辑，靠这个绕开了"跨 section"报错——但连带加了全局 `-fno-jump-tables` 才让 `vfprintf.c` 编译通过（因为核心问题没修，只是禁用了触发场景）。

**架构师的修复**（已提交，commit `851ad359b2e1`）：`emitJumpTableInfo()` 改成**完全不切换 section**——函数体结束后 `OutStreamer` 天然还停留在函数自己的 section（`-ffunction-sections` 下是 `.text.<fname>`，否则是通用 `.text`），直接原地发射跳转表即可，不需要主动切换。**已验证**：反汇编确认 `.LJTI0_0` 等跳转表标签现在正确落在 `.text.vfprintf`（和函数体同一 section）。E2E 27/27、四方 200/0 无回归。

`.work/picolibc/scripts/cross-dadao-unknown-elf.txt` 的 `-fno-jump-tables` 已移除（不该用这个 workaround）。DS 的 `DADAOAsmBackend.cpp` 临时符号强制重定位改动**未提交**（已回退到 ML-003e 的原始状态，即无这段逻辑）。

### 剩余真问题（本任务的调试目标）
section 修好后，`vfprintf.c` 用真实 flags（含 `-ffunction-sections`）编译**仍然失败**，但**换成了不同的失败模式**：
```
clang: error: clang frontend command failed with exit code 139 (use -v to see invocation)
```
**SIGSEGV，无断言信息**（`Build config: +assertions` 但没打印任何 `Assertion ... failed`，是真的段错误，不是优雅的 assert 拦截）。崩溃栈：
```
llvm::MCAssembler::layout()
llvm::MCAssembler::Finish()
llvm::AsmPrinter::doFinalization(llvm::Module&)
...
```
**复现条件**：section 已经修对（`.LJTI0_0` 和引用它的分支指令同在 `.text.vfprintf`）之后，`DADAOAsmBackend.cpp` 里 `fixup_dadao_rela_page`/`fixup_dadao_rela_lo` 的**直接解析路径**（非"强制走重定位"分支，即 `IsResolved==true` 且不是"未定义/跨 section"的正常情形）在处理 `.LJTI0_0` 这个**同 section 局部跳转表标签**时崩溃。**DS 上一轮加的"临时符号一律强制走重定位"改动，实际上是绕开了这个直接解析路径的崩溃**（代价是产生了另一个"Undefined temporary symbol"错误）——两条路都不对，直接解析路径本身有 bug。

## 做什么（纯根因调试，非猜测性尝试修复）
1. **重建这个精确崩溃场景**：
   ```bash
   cd ~/DADAO-0628 && ninja -C .work/build/llvm llc clang   # 用当前已提交代码(含架构师的section修复)
   cd .work/picolibc/build-dadao
   <用 ninja -t commands 抓的真实 flags> -c ../libc/stdio/vfprintf.c -o /tmp/x.o
   # 应该 SIGSEGV，退出码 139
   ```
2. **用 gdb 拿到真实崩溃点**（这次必须做，之前几轮都是读代码猜测，这次要真调试）：
   ```bash
   gdb --args .work/build/llvm/bin/clang -target dadao ... -c ../libc/stdio/vfprintf.c -o /tmp/x.o
   (gdb) run
   (gdb) bt full
   ```
   找到 `MCAssembler::layout()` 具体崩在哪一行、访问的是什么指针/哪个 symbol/fragment，为什么是 NULL 或非法。
3. **对照 `fixup_dadao_rela_page`/`fixup_dadao_rela_lo` 的直接解析代码**（`DADAOAsmBackend.cpp`，`IsResolved` 分支，不强制走重定位那条路）：这条路径此前只被"跨 section 场景强制走 reloc"绕开过，从没真正被"同 section 局部跳转表标签"这种输入测过——找出它假设了什么、遇到 `.LJTI0_0` 这类无普通符号表条目的局部标签时哪里出错（可能是访问了一个从未初始化的 fragment/offset 字段，或者对 `Target.getAddSym()` 返回值做了不安全的假设）。
4. **修复根因**（不是"强制走重定位绕开崩溃"，是让直接解析路径正确处理同 section 局部标签）。
5. **验证**：`vfprintf.c` 用真实 flags 编译成功（0 错误 0 崩溃）；完整 printf 测试双后端真跑出正确输出 + exit=0；E2E/四方不回归。

## 约束
- **禁止用"强制走重定位"绕开这个崩溃**——DS 上一轮已经试过这条路，被打回，别重复。
- **禁止 `-fno-jump-tables` 之类的全局 workaround**。
- 必须用 gdb（或等效工具）拿到真实崩溃现场（指针值/栈帧），不能只靠读代码猜测——这是"根因分析调试任务"，不是"随便试改改看"。
- 不回归：E2E 27/27、四方 200/0；架构师已修的 section 归属（commit 851ad359b2e1）不退步。

## 验收（架构师亲跑）
```bash
cd ~/DADAO-0628 && ninja -C .work/build/llvm llc clang
cd .work/picolibc/build-dadao
# 真实 flags 编译 vfprintf.c，应 0 错误 0 崩溃
cd ~/DADAO-0628
llvm-lit tests/lit/E2E/ 2>&1 | tail
python3 tools/run_differential.py 2>&1 | tail -3
# 完整 printf 测试双后端真跑
```
**判别强调**：真 gdb 定位过崩溃点（完成区要贴 `bt`/关键帧信息，非"读代码觉得是这里"）；`vfprintf.c` 真编译通过（非绕开）；完整 printf 测试真输出+exit=0。

## 参考指针
- 架构师这轮的修复与排查记录：`.work/llvm` commit `851ad359b2e1`（AsmPrinter section 修复，含详细 commit message 记录已排除的路径）
- `DADAOAsmBackend.cpp`：`fixup_dadao_rela_page`/`fixup_dadao_rela_lo` 的直接解析分支（`applyFixup`，`IsResolved==true` 走到底那段代码，非 `maybeAddReloc` 分支）
- MC 崩溃栈：`llvm/lib/MC/MCAssembler.cpp`（`layout()`/`Finish()`）
- ML-003h 任务文件（DS 上一轮的两处尝试，均已验证无效/是绕过，勿重复）

—— 自审见 DS.md §自审流程（subagent 代码级 · 强制；审阅记录占位必填——**AC/零 finding 也写实质记录**）。**本任务的判据是"真用 gdb 找到崩溃点 + 真正修复 + 真跑通"**，读代码猜测不算数，绕过/workaround 不算数。

---

## 审阅记录（subagent）

> **[架构师预置占位 · DS 必填]** DS 返回前必须开 subagent 代码级 review，逐条 finding + 处置表 + 判决写入此区。**占位未替换成实质记录 = 未自审 = 直接打回（AC/零 finding 也写：判决行 + 逐条核验点附证据 + finding:无）。**
> 特别核：是否真用 gdb 定位了崩溃点（有 bt 证据）？修法是否是"直接解析路径真正修好"而非"强制走重定位/禁用跳转表"这类绕过？vfprintf.c 真编译通过 0 崩溃？完整 printf 测试真跑出正确输出+exit=0？E2E/四方不回归？
