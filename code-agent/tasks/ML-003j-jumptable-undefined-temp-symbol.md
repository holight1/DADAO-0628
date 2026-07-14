# ML-003j: 跳转表标签"Undefined temporary symbol"（前向引用 + section-symbol 机制收尾）

**执行环境**: 本地 DS · DADAO-0628（LLVM MC 层，`rela_page`/`rela_lo` fixup + ELF section-symbol 机制）

**状态**: 待执行

**前置**：ML-003i（架构师亲自修一轮）——**两个真实 bug 已修复提交**：跳转表 section 路由改用 LLVM 标准 `shouldPutJumpTableInFunctionSection` 机制（`.work/llvm` commit `4f2967eac9ec`/patch 0029）；`applyFixup` 双重 Offset 内存踩踏修复（commit `45d59391b3c3`/patch 0028，这是 ML-003i 那个 SIGSEGV 的真根因）。**`vfprintf.c` 编译不再崩溃**，E2E 27/27、四方 200/0 无回归。本任务收尾最后一个、已收窄到很具体的问题。

---

## 背景 / 已收窄的现象（架构师排查到此，直接用）

`vfprintf.c` 用真实 flags（含 `-ffunction-sections`）编译，回到**干净、不崩溃**的错误：
```
error: Undefined temporary symbol
error: Undefined temporary symbol
2 errors generated.
```
来自 `llvm/lib/MC/ELFObjectWriter.cpp:530`：某个**临时/局部符号**被某处引用（通过一个 relocation），但从未真正"定义"（赋 section+offset）到能进符号表的程度。

**已排查的具体机制**（架构师看的 `ELFObjectWriter::recordRelocation`）：
```cpp
bool UseSectionSym = SymA && SymA->getBinding() == ELF::STB_LOCAL &&
                     !SymA->isUndefined() &&
                     !mc::isRelocRelocation(Fixup.getKind());
if (UseSectionSym && useSectionSymbol(Target, SymA, Addend, Type)) {
  Addend += Asm->getSymbolOffset(*SymA);
  SymA = static_cast<const MCSymbolELF *>(SecA->getBeginSymbol());
}
```
这是 LLVM 的标准机制："把对局部临时符号的重定位，转换成对该符号所在 section 符号 + 偏移量的重定位"——避免临时符号（如跳转表标签 `.LJTI0_0`）真的要进符号表。**触发条件是 `!SymA->isUndefined()`**（符号必须已"定义"）。

**怀疑点**：`.LJTI0_0`（跳转表索引标签）在 `.text.vfprintf` 里的**物理位置在函数尾部**（跳转表数据紧跟函数体后发射），但**引用它的 `rela rb8, .LJTI0_0` / `addi rb8, rb8, .LJTI0_0` 指令在函数体中部**——是一次**前向引用**（引用点在定义点之前）。`fixup_dadao_rela_page`/`fixup_dadao_rela_lo` 这两个 fixup kind 的 `applyFixup` 实现里，判断逻辑是：
```cpp
if (Kind == DADAO::fixup_dadao_rela_page) {
  if (!IsResolved) {           // ← 直接送重定位，没有"同 section 直接解析"分支
    Value = 0;
    maybeAddReloc(F, Fixup, Target, Value, IsResolved);
    return;
  }
  ...
}
```
对比 `call24`/`branch18`/`branch12`（都有"同 section 直接解析，不走重定位"的快速路径），`rela_page`/`rela_lo` **没有类似的同 section 短路**——`IsResolved` 是 MC 层在评估这个 fixup 时算出来的（是否已经能确定最终值），如果**前向引用**导致这个时间点 `.LJTI0_0` 还没有被视为"已定义"，`IsResolved` 就是 false，直接走重定位；而重定位记录阶段（`recordRelocation`）时，可能这时候 `.LJTI0_0` **依然**被判定为 undefined（同一颗前向引用问题在两处都可能发生），导致既没有走"同 section 直接编码"也没有走"section-symbol 替代"，最终变成"引用了一个从未被认定为已定义的临时符号"，触发 ELFObjectWriter 报错。

## 做什么
1. **验证前向引用假说**：用 gdb 在 `MCAssembler::layout()`/`evaluateFixup()`/`recordRelocation()` 断点，检查处理 `.LJTI0_0` 这个 fixup 时，`Sym->isUndefined()` 到底返回什么、`Sym->getFragment()` 是否已经指向正确的 fragment（即这时候 MC 是否已经知道 `.LJTI0_0` 最终会在哪）——确认是不是"前向引用+多趟 layout 的时机"问题。
2. **对照其它 target 怎么处理类似的"PC-relative 页对齐寻址引用同 section 前向标签"场景**（如 RISC-V 的 `%pcrel_hi`/`%pcrel_lo` 对 label 的处理，通常有专门的"AUIPC pair"机制处理这类前向引用，可能有值得参照的模式）。
3. **可能的修法方向**（供参考，非唯一，DS 按实际定位定）：
   - 给 `fixup_dadao_rela_page`（可能也包括 `rela_lo`）也加一条"同 section 直接解析"的快速路径（像 `call24`/`branch18` 那样），只在真正跨 section/未定义时才走重定位——但要想清楚 `rela_page` 语义是"页对齐的 PC 相对偏移"，直接解析在**同 section 但物理布局尚未最终确定**时是否可靠（可能需要在 MC 完成足够的 layout 后才能算，而不是第一遍就尝试直接编码）。
   - 或者：确认 `useSectionSymbol` 机制本该覆盖这个场景，追为什么 `isUndefined()` 在这一步仍返回 true——可能是 DADAO 这两个 fixup kind 没有被正确标记为"可与 section symbol 一起用"（检查 `needsRelocateWithSymbol` 的返回值和调用时机）。
4. **验证**：`vfprintf.c` 真实 flags 编译 0 错误；完整 printf 测试（crt0+stdout接线+libc.a+pico_stubs+dadao.ld）在 QEMU 上**真跑出正确字符串输出 + exit=0**——这是 goal① 最终判据。
5. **回归**：E2E 27/27、四方 200/0；架构师已修的两处（section 路由、offset 踩踏）不退步。

## 约束
- 不回归：已提交的两个修复（patch 0028/0029）不退步；直接调用/普通函数调用的 fixup 路径（call24 等）不受影响。
- **禁止绕过**（`-fno-jump-tables`、"强制走重定位"之类）——DS 前两轮已经试过都被打回，这次要真正定位并修好这个前向引用/section-symbol 收尾问题。
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
**判别强调**：`vfprintf.c` 真编译通过；完整 printf 测试真输出正确字符串 + exit=0；E2E/四方不回归。

## 参考指针
- ML-003i 完成区 + 架构师复核（两个已修 bug 的完整记录、这次问题的精确收窄过程）
- `.work/llvm` commit `45d59391b3c3`（offset 踩踏修复）、`4f2967eac9ec`（section 路由标准化）
- `llvm/lib/MC/ELFObjectWriter.cpp`（`recordRelocation`/`useSectionSymbol`，line ~1245-1370）
- `DADAOAsmBackend.cpp`（`fixup_dadao_rela_page`/`rela_lo` 的 `applyFixup`，对比 `call24`/`branch18` 已有的"同 section 直接解析"分支）；`DADAOELFObjectWriter.cpp`（`needsRelocateWithSymbol`）
- 后续：解锁后回 ML-003b 收尾 goal①（picolibc 后端 enablement 里程碑基本完整，这是最后一块）

—— 自审见 DS.md §自审流程（subagent 代码级 · 强制；审阅记录占位必填——**AC/零 finding 也写实质记录**）。**subagent 必须真编译 vfprintf.c + 真跑完整 printf 测试**，别用绕过手段冒充修复。

---

## 审阅记录（subagent）

> **[架构师预置占位 · DS 必填]** DS 返回前必须开 subagent 代码级 review，逐条 finding + 处置表 + 判决写入此区。**占位未替换成实质记录 = 未自审 = 直接打回（AC/零 finding 也写：判决行 + 逐条核验点附证据 + finding:无）。**
> 特别核：是否真定位了前向引用/`isUndefined()`判断的具体机制（有 gdb 或等效证据）？`vfprintf.c` 真编译通过？完整 printf 测试真跑出正确输出 + exit=0？E2E/四方不回归？无绕过/workaround？
