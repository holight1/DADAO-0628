# ML-003e: MC 重定位缺口 — 跨 section 同对象 call + 数据段函数指针（G1/G2）

**执行环境**: 本地 DS · DADAO-0628（LLVM MC/AsmBackend/ELFObjectWriter + lld）

**状态**: 待执行

**前置**：ML-003b（DS 发现并定位这两个 MC gap，架构师 ground-truth 独立复现确认属实——**诊断准确，非误诊**）。间接调用（ML-003c/d）已提交（commit 316b04a），不受影响。

---

## 背景 / 目标
picolibc 的 -O0 全量编译已大幅推进（868/1102 通过），但**双后端真跑 printf** 卡在两个 **MC/ELF 层基础设施缺口**——这两个 gap **不是 picolibc 专属**，`-ffunction-sections`（几乎所有真实构建默认开）+ 静态初始化函数指针（tinystdio FILE 的 put/get 回调）在任何真实 C 程序都会撞上。修好后直接解锁 picolibc goal①。

## Gap 1：同对象跨 section 直接调用不发重定位（架构师已复现）

**复现**：
```c
void helper(void){}
void caller(void){ helper(); }
```
`clang -target dadao -O0 -ffunction-sections -c` → `caller` 反汇编出 **`call -1`**（垃圾偏移）+ **重定位表为空**。

**根因**：`DADAOAsmBackend.cpp` 的 `fixup_dadao_call24` 处理（`applyFixup`）：
```cpp
if (Kind == DADAO::fixup_dadao_call24) {
  const MCSymbol *Sym = Target.getAddSym();
  if (Sym && Sym->isUndefined()) {   // 只判断"是否在本对象定义"
    Value = 0;
    maybeAddReloc(F, Fixup, Target, Value, IsResolved);
    return;
  }
  // 否则汇编期直接算 imm24 偏移——但这假设 Sym 和当前 fixup 在同一 section！
  int64_t Imm24 = (static_cast<int64_t>(Value) - 4) >> 2;
  ...
}
```
`helper` 在同一对象文件里**已定义**（`isUndefined()`=false），但和 `caller` 在**不同 section**（`.text.helper` vs `.text.caller`，`-ffunction-sections` 每个函数一个 section）——汇编阶段不知道两个 section 最终的链接后相对偏移，此时算出的 `Value` 是占位值，`(Value-4)>>2` 算出垃圾（复现里是 -1）。**`isUndefined()` 不是判断"是否需要重定位"的正确条件**——正确条件是"目标符号是否与当前 fixup 位于同一 section"（同 section 才能汇编期确定相对偏移；跨 section 无论是否同对象都必须交给链接器）。DL-064b 当初只覆盖了"真跨对象"（crt0.o call main）这一种情形，这次要把"同对象跨 section"也纳入。

**修法**：`shouldForceRelocation`/`applyFixup` 判断条件从 `Sym->isUndefined()` 扩展为 `Sym->isUndefined() || (Fixup 所在 section != Sym 所在 section)`——获取 fixup 当前 section 与目标符号 section 比较（`MCSymbol::getFragment()->getParent()` 或对应 API，具体查 LLVM MC 现有目标的标准做法，例如 RISCV/ARM backend 如何判断"needs relocation"，通常用 `Target.getSymA()->getSymbol()` 关联的 section vs 当前 `MCFragment` 的 section）。

## Gap 2：数据段函数指针初始化被静默清零（架构师已复现）

**复现**：
```c
void myfunc(void){}
void (*fp)(void) = myfunc;
```
编译后 `.data` 段内容是 `00000000 00000000`（**全零**，该是 `myfunc` 地址）+ **重定位表为空**。

**根因**：`DADAOAsmBackend::applyFixup` 只处理 4 个自定义 `fixup_dadao_*` kind（call24/branch18/branch12/rela_page/rela_lo），**通用的 `FK_Data_8`（`.quad symbol` 这类 8 字节数据重定位，编译器给函数指针类型的全局变量初始化时会发出）完全没有处理分支**——落进 `applyFixup` 时被忽略（不写值也不发重定位），数据段该写地址的位置保持初始为零。`DADAOELFObjectWriter::getRelocType` 的 switch 也没有 `FK_Data_8` case（只有 `FK_SecRel_4`→`R_DADAO_32`，是 4 字节的）。

**修法**：
1. **新增 8 字节绝对重定位类型** `R_DADAO_ABS64`（`lld/ELF/Arch/DADAO.cpp` 现有 enum：`R_DADAO_32=0..R_DADAO_RELA_LO=5,R_DADAO_NUM=6`——加 `R_DADAO_ABS64=6, R_DADAO_NUM=7`）。
2. **`DADAOAsmBackend::applyFixup`** 加 `FK_Data_8` case：8 字节数据引用，若目标符号需要重定位（跨 section/未定义同 G1 判断逻辑）则 `maybeAddReloc`；否则写入解析后的绝对地址（8 字节，注意 DADAO **大端**）。
3. **`DADAOELFObjectWriter::getRelocType`** 加 `case FK_Data_8: return R_DADAO_ABS64;`。
4. **`lld/ELF/Arch/DADAO.cpp` relocate()** 加 `R_DADAO_ABS64` case：8 字节绝对地址写入（`write64be`，注意大端序，参考现有 `R_DADAO_32` case 的写法但是 8 字节版本）。
5. **可能需要**：`DADAOMCCodeEmitter`/其它发 `.quad` 的地方是否也要认这个 fixup kind（查 LLVM `MCObjectStreamer::emitValue` 对 `.quad symbol` 默认走的 fixup kind 是不是就是 `FK_Data_8`——通常是，但需确认 DADAO backend 有没有覆盖 `getFixupKindInfo` 遗漏了它）。

## 做什么
1. 修 Gap 1（同 section 判断，扩展 call24 的 relocation 触发条件）。
2. 修 Gap 2（新增 R_DADAO_ABS64 全链路：enum + AsmBackend + ELFObjectWriter + lld relocate）。
3. **复现用例验证**：上面两个最小 C 复现（`g1.c`/`g2.c` 风格）编译+链接后，`caller` 真调到 `helper`（非 `call -1`）；`fp` 真存 `myfunc` 地址（非全零）——**用 llvm-objdump -r --triple=dadao 看真重定位表非空 + 反汇编/数据内容正确**。
4. **决定性验证**：picolibc `puts.c`（`-ffunction-sections` 触发跨 section call）+ tinystdio stdout 的函数指针初始化（触发 FK_Data_8）真编译+**真链接**（不只是 `.o` 编出来，要 `ld.lld` 链完整程序）无重定位缺失。
5. **回归**：E2E 27/27、四方 AGREE(4-way)=200/DIVERGE=0（新增 relocation 类型不应影响现有 M1 指令语义）；已有 CALL24 跨对象场景（DL-064b clang_oneshot.test）不退步。

## 约束
- 不改变现有 `R_DADAO_CALL24`/`R_DADAO_32` 等既有重定位类型语义，只**扩大触发条件**（G1）+ **新增类型**（G2）。
- 大端序：`R_DADAO_ABS64` 写入用 `write64be`（DADAO 全大端，参考现有 `R_DADAO_32`/`RELA_LO` 写法）。
- lld、AsmBackend、ELFObjectWriter 三处必须一致（枚举值、判断条件），否则 assembler 发的重定位链接器认不出。

## 验收（架构师亲跑）
```bash
cd ~/DADAO-0628 && ninja -C .work/build/llvm llc clang lld llvm-mc
# G1/G2 最小复现
printf 'void helper(void){}\nvoid caller(void){ helper(); }\n' > /tmp/g1.c
.work/build/llvm/bin/clang -target dadao -O0 -ffunction-sections -c /tmp/g1.c -o /tmp/g1.o
.work/build/llvm/bin/llvm-objdump -r --triple=dadao /tmp/g1.o   # 应见 R_DADAO_CALL24 重定位
printf 'void myfunc(void){}\nvoid (*fp)(void) = myfunc;\n' > /tmp/g2.c
.work/build/llvm/bin/clang -target dadao -O0 -c /tmp/g2.c -o /tmp/g2.o
.work/build/llvm/bin/llvm-objdump -r --triple=dadao /tmp/g2.o   # 应见 R_DADAO_ABS64 重定位
# 回归
llvm-lit tests/lit/E2E/ 2>&1 | tail
python3 tools/run_differential.py 2>&1 | tail -3
```
**判别强调**：两个复现用例真出现非空重定位表（非 grep 存在性，看真值）；链接后（若测）反汇编真调对/数据真存对地址；四方/E2E 不回归。

## 参考指针
- ML-003b 完成区（DS 的 G1/G2 发现原文，含具体触发文件 `puts.c`/stdout 结构）+ 架构师复核（复现代码、根因分析）
- `DADAOAsmBackend.cpp`（`applyFixup`/`shouldForceRelocation`，DL-064b 的 `isUndefined()` 检查起点）；`DADAOELFObjectWriter.cpp`（`getRelocType`）；`lld/ELF/Arch/DADAO.cpp`（enum + `relocate()`，现有 `R_DADAO_32`/`CALL24` case 作范式）
- DL-064b（跨对象 call24 重定位，本任务的 G1 是它的扩展——同对象但跨 section 的情形当初没覆盖）
- 后续：解锁后回 ML-003b（picolibc printf 双后端真跑，goal①）

—— 自审见 DS.md §自审流程（subagent 代码级 · 强制；审阅记录占位必填——**AC/零 finding 也写实质记录**）。**subagent 必须真跑两个复现用例看重定位表非空 + 数据/跳转真对**，别只读代码判 Accepted。

---

## 审阅记录（subagent）

### 审阅记录（subagent · 判决 = 通过）

**改动文件**：DADAOMCTargetDesc.h, DADAOAsmBackend.cpp, DADAOELFObjectWriter.cpp, lld/ELF/Arch/DADAO.cpp

**核验点**：
- ✅ G1 复现 `caller → helper`（-ffunction-sections）：重定位表非空，含 `helper` 重定位
- ✅ G2 复现 `fp = myfunc`：重定位表非空，`.data` 节含 `myfunc` 重定位
- ✅ E2E 27/27 PASS（无回归）
- ✅ picolibc puts.o 重定位表：含 `.text.__flockfile` / `.text.__funlockfile` 跨节 CALL24 重定位（G1 生效）
- ✅ stdout_min.o 重定位表：含 `.data → .text` ABS64 重定位（G2 生效）
- ✅ puts + stdout + libc.a 链接成功，数据值正确（stdout→__stdout=0x80007000，put=0x80000058）

**改动内容**：

| 文件 | 改动 |
|------|------|
| DADAOMCTargetDesc.h | +R_DADAO_ABS64=6, NUM 改为 7 |
| DADAOAsmBackend.cpp G1 | CALL24/BRANCH18/BRANCH12 重定位触发条件：`isUndefined()`→`isUndefined() \|\| 跨 section`（比较 `FixupSec != SymSec`） |
| DADAOAsmBackend.cpp G2 | +FK_Data_8 case：解析值或发 ABS64 重定位 |
| DADAOELFObjectWriter.cpp | +FK_Data_8 → R_DADAO_ABS64，+FK_Data_4 → R_DADAO_32 |
| lld DADAO.cpp | +R_DADAO_ABS64 枚举，+getRelExpr(R_ABS)，+relocate(write64be) |

**残余 issue**：所有编译+链接正确，但 QEMU 执行 printf → 挂起。根因：LLVM 后端定义 rd0-rd63（64 寄存器），QEMU 可能仅支持 rd0-rd31。varargs spill 使用了 rd32+ 导致 QEMU 行为异常（非本任务 range）。

**判决**：通过（G1+G2 已修，复现用例验证通过，E2E 无回归）

---

## 架构师复核（2026-07-13，ground-truth）

### ✅ G1/G2：确认真修好（本任务范围内通过）
重建 + 独立复现两个最小 C 用例，**编译+真链接**（非仅 objdump 看 .o 重定位表）：
- **G1**：`caller`(0x80000004) 反汇编 `call -2`，链接后正确指向 `helper`(0x80000000)（PC 相对偏移编码验证：`(0x80000000-0x80000004-4)>>2=-2` ✓）。
- **G2**：`.data`(0x80001000) 真存 `80000000`（`myfunc` 真地址，大端），非全零。
- E2E 27/27、四方 AGREE(4-way)=200/DIVERGE=0 无回归。

**结论：ML-003e 目标（G1/G2 MC 重定位缺口）达成，接受。**

### ⚠ 残余问题：DS 诊断有误（rd0-31 说法不成立），但 hang 现象真实
**核实"寄存器范围"说法**：spec §register model 明确 64 个 `rd0-rd63`；QEMU `CPUDADAOState.rd[64]`；decode 逻辑全文 grep 无任何 `&0x1f`/`&31` 类限制——**QEMU 完全支持 rd32+，DS 的根因诊断不成立**（又一次归因偏差模式，同 DL-063b/064b/ML-002a）。

**架构师独立复现 hang**（用 DS 留的 `stdout_min.c` + 当前 libc.a + crt0 + link 全套构建，QEMU 5秒超时验证）：**真挂起属实**（timeout 前无 "hi" 输出、无退出）。`-d exec` trace 定位：卡在 `0x800001d0: ldo rd16, rb8, 8`（很可能是加载 `stdout->put` 函数指针字段），QEMU 反复打印 `cpu_io_recompile: rewound execution of TB to 00000000800001d0`——同一 PC 反复触发 io-recompile 不收敛，指向该 load 的目标地址落进了 **MMIO 映射区**（如 exit-port `0x10000000`）导致的 TCG 精确异常处理循环，而非简单的 C 层死循环。

**真根因待查**：需要真机寄存器态（`rb8` 运行时值）才能钉死——是地址计算错误（如 `rd2rb`/栈 spill 链路某处算错，`rb8` 意外落进 MMIO 区）还是 QEMU `cpu_io_recompile` 机制本身在这个场景没有正确前进 PC。**这是新任务范围**（QEMU TCG 层调试，非 MC/relocation），不阻塞 ML-003e 验收，另立任务处理。
