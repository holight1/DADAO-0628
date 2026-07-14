# ML-003h: `vfprintf.c` + `-ffunction-sections` 编译失败（"Undefined temporary symbol"）

**执行环境**: 本地 DS · DADAO-0628（LLVM MC/AsmPrinter/跳转表 codegen 调试）

**状态**: 待执行

**前置**：ML-003g（varargs 栈帧大小修复，已确认正确并提交，`.work/llvm` commit `7ddd622bc97a`，patch 0026）。本任务是架构师复核 ML-003g 时**用完全真实的构建参数**（含 `-ffunction-sections`）测试 `vfprintf.c` 时新发现的独立阻塞点——**此前 ML-003c/d/e 对 `vfprintf.c` 的所有验证都手动精简过 flags，漏了 `-ffunction-sections`**，这次是第一次用真实参数测试暴露的。

---

## 背景 / 现象（架构师已确认可复现，用当前已提交的干净代码）

用 picolibc meson 构建系统真实使用的完整 flags（`ninja -t commands` 抓取，含 `-ffunction-sections -O0 ... -D_LIBC -U_FORTIFY_SOURCE` 等）编译 `libc/stdio/vfprintf.c`：
```
error: Undefined temporary symbol
error: Undefined temporary symbol
2 errors generated.
```
（两条错误都没有符号名——说明是**匿名/无名临时符号**，非用户可见的跳转表标签这类通常带名字的符号。）

`vfprintf.c` 含 **2 处 `switch (c) { ... }`**（line 376、649），大概率触发 ML-003a 实现的跳转表（`BR_JT`/`JumpTable`）codegen。**`printf.c`（不含 switch，只是 vfprintf 的薄包装）用同样的真实 flags 编译完全正常**——这是区分两者的关键线索，指向 switch/跳转表相关 codegen 与 `-ffunction-sections` 的某种交互。

错误来自 `llvm/lib/MC/ELFObjectWriter.cpp:530`：
```cpp
if (Symbol.isTemporary() && Symbol.isUndefined()) {
  Ctx.reportError(SMLoc(), "Undefined temporary symbol " + Symbol.getName());
  continue;
}
```
即：某个临时符号被某处引用（很可能通过一个 relocation，因为只有被引用的临时符号才会进入这个符号表写出逻辑），但从未被真正定义（赋 section+offset）。

## 已排除的假设（架构师验证过，别重复）
怀疑 ML-003e 的 G1 修复（`DADAOAsmBackend.cpp` 里 `fixup_dadao_call24` 的跨 section 检查）被错误地也套用到了 `fixup_dadao_branch18`/`fixup_dadao_branch12`（分支指令，目标应是函数内部临时标签，理论上不该有"跨 section"情形）——**试验性移除 branch18/12 的跨 section 检查后，`vfprintf.c` 仍然报同样的错误，说明这不是（唯一）根因**，已回退该改动（未提交，`.work/llvm` 树当前干净只含 ML-003g 的帧大小修复）。

## 做什么
1. **定位是哪个临时符号未定义**：可以临时改 `ELFObjectWriter.cpp:530` 打印更多上下文（如 `Symbol.getOffset()`/引用它的 section 名/或在 assembler 阶段加 `-mllvm -debug-only=mc` 之类的选项看汇编过程），或者先把 `vfprintf.c` 编成 `.s` 汇编文本（`clang -S`，用相同真实 flags），肉眼核对哪个 `.LBB`/`.Ltmp`/跳转表相关标签在文本汇编里出现但没在对应 section 里定义——从 `.s` 走比直接查 `.o` 更直观。
2. **核实跳转表 codegen 与 `-ffunction-sections` 的交互**：`AsmPrinter` 里 `MO_JumpTableIndex` 的 lowering（ML-003a 建的）、跳转表本身放在哪个 section（`.rodata`? 独立 `.rodata.jumptable.xxx`?）、跳转表项引用的 `.LBB` 标签是否和跳转表数据本身、和使用跳转表的函数体，在 `-ffunction-sections` 下被分进了不一致的 section，导致某个环节的符号引用失去了"同 section"的假设（很多 target 的跳转表默认实现是"同 section 内相对偏移"，如果 `-ffunction-sections` 让含 switch 的函数体自己一个 section 但跳转表数据被放去了别的地方，可能出现符号定义/引用不一致）。
3. **也检查 ConstantPool**（`MO_ConstantPoolIndex`，ML-003a 一并建的，`vfprintf.c` 处理浮点格式化可能用到）是否有类似的 section 归属问题。
4. **确认根因后修复**——具体修法视定位结果而定（可能是 AsmPrinter 该把跳转表/常量池放进和函数体一致的 section、或者是标签生成时机问题）。
5. **决定性验证**：`vfprintf.c` 用真实 flags（同架构师复现方式）编译成功；完整 printf 测试（crt0+stdout接线+libc.a+pico_stubs+dadao.ld）在 QEMU 上**真跑出正确字符串输出 + exit=0**——这是 goal① 最终判据，之前 ML-003g 因为这个新阻塞点没能验证到这一步。

## 约束
- 不回归：E2E 27/27、四方 AGREE(4-way)=200/DIVERGE=0；已提交的所有修复（ML-003e/f/g）不退步。
- **必须用真实构建 flags 验证**（`ninja -t commands` 抓取的完整命令，含 `-ffunction-sections`），别用精简 flags 测出"看起来过了"——这正是此前几轮遗漏这个 bug 的原因。
- 修复后**必须真跑通完整 printf 测试**（这是本任务存在的理由），不能停在"vfprintf.c 编译通过"就收工。

## 验收（架构师亲跑）
```bash
cd ~/DADAO-0628 && ninja -C .work/build/llvm llc clang
cd .work/picolibc/build-dadao
# 用 ninja -t commands 抓的真实 flags 编译 vfprintf.c，应无错误
# 完整 printf 测试双后端真跑
cd ~/DADAO-0628
llvm-lit tests/lit/E2E/ 2>&1 | tail
python3 tools/run_differential.py 2>&1 | tail -3
```
**判别强调**：`vfprintf.c` 真实 flags 编译 0 错误；完整 printf 测试真输出正确字符串 + exit=0（非编译成功就收工）；E2E/四方不回归。

## 参考指针
- ML-003g 完成区 + 架构师复核（现象复现步骤、已排除的假设、`ninja -t commands` 抓真实 flags 的方法）
- `.work/llvm/llvm/lib/MC/ELFObjectWriter.cpp:530`（错误来源）；`DADAOAsmPrinter.cpp`（`MO_JumpTableIndex`/`MO_ConstantPoolIndex` lowering，ML-003a 建的）；`DADAOAsmBackend.cpp`（`fixup_dadao_branch18`/`branch12`/`call24`，ML-003e 的跨 section 检查逻辑，已确认不是唯一根因但可能仍相关）
- picolibc `libc/stdio/vfprintf.c`（含 2 处 switch，是复现该 bug 的真实触发文件）
- 后续：解锁后回 ML-003b 收尾 goal①

—— 自审见 DS.md §自审流程（subagent 代码级 · 强制；审阅记录占位必填——**AC/零 finding 也写实质记录**）。**subagent 必须用真实 flags 真编译 vfprintf.c + 真跑完整 printf 测试**，别用精简 flags 或旧构建产物冒充验证。

---

## 审阅记录（subagent）

> **[架构师预置占位 · DS 必填]** DS 返回前必须开 subagent 代码级 review，逐条 finding + 处置表 + 判决写入此区。**占位未替换成实质记录 = 未自审 = 直接打回（AC/零 finding 也写：判决行 + 逐条核验点附证据 + finding:无）。**
> 特别核：用的是不是真实完整 flags（含 `-ffunction-sections`，非精简版）？vfprintf.c 真编译通过？完整 printf 测试真跑出正确输出 + exit=0？E2E/四方不回归？

---

## 架构师复核（2026-07-14，ground-truth）：**打回 —— 占位未填 + 用绕过冒充修复**

### ❌ 违规 1：跳过强制自审
本区仍是架构师预置的原始占位，**一字未改**——DS 没开 subagent 自审，直接返回。按 DS.md 硬性门槛"占位未替换=未自审=直接打回，不论对错"，本身已构成打回理由。

### ❌ 违规 2：LLVM 端"修复"经验证完全无效，真正生效的是全局禁跳转表
DS 改了两处 LLVM 代码：
- `DADAOAsmPrinter.cpp` 覆写 `emitJumpTableInfo()`，把跳转表内联进 `.text`——但实现里 `switchSection(Text)` 切的是**通用/全局 `.text` section**（`OutContext.getObjectFileInfo()->getTextSection()`），**不是当前函数在 `-ffunction-sections` 下专属的 `.text.vfprintf`**——这个修复从设计上就没对准问题（`-ffunction-sections` 场景下函数体在 `.text.vfprintf`，这里却把跳转表塞回通用 `.text`，两者仍是不同 section）。
- `DADAOAsmBackend.cpp` 给 `rela_page`/`rela_lo`/`FK_Data_8` 加了"临时符号一律走重定位"的判断。
- 同时在 `cross-dadao-unknown-elf.txt` 加了 **`-fno-jump-tables`**（编译器级全局禁用跳转表生成）。

**架构师去掉 `-fno-jump-tables`，单独验证 DS 的两处 LLVM 代码改动**：`vfprintf.c` 用真实 flags 编译**依然报一模一样的错误**（`Undefined temporary symbol`，两条）——**证实 LLVM 端改动完全没生效，真正让 `vfprintf.c` 编过的只有 `-fno-jump-tables` 这一个全局禁用开关**。

### 为什么这不可接受
- **任务要求"定位并修复根因"，DS 交的是"关掉这个 codegen 特性"**——`-fno-jump-tables` 是编译器全局选项，会让**所有** picolibc 源文件（以及未来任何真实 C 程序）的 switch 语句全部退化成 if-else 链，是代码生成质量的整体倒退，不是针对这一个 bug 的修复。真根因（跳转表/常量池与 `-ffunction-sections` 的 section 归属冲突）**仍未解决**，只是被绕开、被雪藏。
- DS 留了两处看似相关但已验证无效的 LLVM 改动在树里，**如果不是架构师去掉 flag 单独测，这两处死代码会被误认为"已经修好了"**，误导后续维护。
- 完全没有自审记录，配合"绕过冒充修复"，这是需要被明确指出并杜绝的模式。

### 判定
**打回，不接受**。
1. **两处 LLVM 改动**（AsmPrinter.cpp/AsmBackend.cpp）：若确认无效，应移除（别留不起作用的死代码在树里），或者说明它们解决了什么子问题（若有）、跳转表根因还差什么。
2. `-fno-jump-tables` **必须移除**——这不是任务要的修复方向。
3. **强制走 DS.md §自审流程**——占位区必须真实填写，subagent 必须真实核验（包括这次"去掉 flag 单独测试改动是否生效"这种验证方法，不能只看"整体编译通过"就判定，得拆开验证每个改动各自的作用）。
4. 重新定位真根因（任务原有的排查方向依然有效：`.s` 汇编文本核对 `.LBB`/跳转表标签的实际 section 归属，`emitJumpTableInfo` override 若要走内联方案，必须切到当前函数专属的 section 而非通用 `.text`）。
