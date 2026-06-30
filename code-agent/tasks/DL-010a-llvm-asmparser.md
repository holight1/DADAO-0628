# DL-010a: LLVM AsmParser + MC Code Emitter（Phase 2 汇编器）

**执行环境**：本地 DS · DADAO-0628

---

## 目标

在 DL-009a 指令格式 TableGen 基础上，实现 DADAO 汇编器的完整 MC 层：
1. **AsmParser**：将文本汇编解析为 `MCInst`（助记符 + 操作数）
2. **MC Code Emitter**：将 `MCInst` 编码为大端字节序列
3. **AsmPrinter（MCInstPrinter）**：将 `MCInst` 还原为文本（为 DL-011a 反汇编做基础）

完成后，`llvm-mc --triple=dadao-unknown-elf -filetype=obj -o out.o test.s` 能生成
正确 ELF object，`make build-mc` 仍然 PASS。

---

## 背景

- 编码格式：大端，op[7:0]=bits[31:24]，ha/hb/hc/hd 各 6 bits（`contracts/isa/spec.md §2`）
- 指令 def 已在 DL-009a 中定义（`DADAOInstrInfo.td`），本任务在此基础上实现 parser/emitter
- 汇编语法：`助记符 目标寄存器, 源操作数...`，逗号分隔，寄存器名 `rd0`…`rd63` / `rb0`…`rb63`
- 寄存器名大小写不敏感

---

## 交付物

### 1. Patch（`components/llvm/patches/0005-dadao-asmparser.patch`）

所有文件位于 `llvm/lib/Target/DADAO/`。

#### 1.1 `AsmParser/DADAOAsmParser.cpp`

继承 `MCTargetAsmParser`，实现：

**寄存器解析**：
- `rd0`–`rd63`：映射到 `DADAO::RD0`–`DADAO::RD63`（TableGen 生成的枚举）
- `rb0`–`rb63`：映射到 `DADAO::RB0`–`DADAO::RB63`
- 未识别的寄存器名 → 报 ParseError

**立即数解析**：按操作数类型检查范围：

| 操作数 | 范围 | 越界处理 |
|--------|------|---------|
| imms12 | -2048 … 2047 | 报错拒绝 |
| immu12 | 0 … 4095 | 报错拒绝 |
| imms18 | -131072 … 131071 | 报错拒绝 |
| immu16 | 0 … 65535 | 报错拒绝 |
| immu6  | 0 … 63 | 报错拒绝 |
| imms24 | -8388608 … 8388607 | 报错拒绝 |
| wyde-pos | 0 … 3 | 报错拒绝 |

**指令解析**（`ParseInstruction`）：
- 读助记符 → 查 `MatchInstructionImpl`（TableGen 生成）
- 按格式类型读操作数序列
- 报清晰错误：`"invalid register"`, `"immediate out of range"`, `"expected ','"`

**关键约束**：
- 操作数合法性（rd0 目标限制等）**不在 AsmParser 层检查**；汇编器只做语法/范围检查，语义合法性由执行层处理
- immu12 用于 `cmpu`；imms12 用于其余 rrii 格式的立即数

**MISC-Norm 同名助记符**：多个助记符共用同一名称（如 `cmps` 有 rrii 和 orrr 两种形式），
通过操作数数量和类型区分（`MatchInstructionImpl` 的 AsmVariant 机制处理）。

#### 1.2 `MCTargetDesc/DADAOMCCodeEmitter.cpp`

继承 `MCCodeEmitter`，实现 `encodeInstruction()`：

```cpp
void DADAOMCCodeEmitter::encodeInstruction(
    const MCInst &MI, SmallVectorImpl<char> &CB,
    SmallVectorImpl<MCFixup> &Fixups,
    const MCSubtargetInfo &STI) const
{
    uint32_t Bits = getBinaryCodeForInstr(MI, Fixups, STI); // TableGen 生成
    // 大端输出：先写 bits[31:24]，最后写 bits[7:0]
    support::endian::write<uint32_t>(CB, Bits, llvm::endianness::big);
}
```

**大端字节序**：4 字节，MSB 先输出（`llvm::endianness::big`）。
验证点：`addi rd8, rd0, 1` 编码 = `0x19_40_00_01`（op=0x19, ha=rd8=8, hb=rd0=0, hc:hd=imms12(1)=0x001）。

**Branch/Jump 相对偏移**：
- `brn/brnn/brz/brnz/brp/brnp` 的 imms18 = `(target_pc - (current_pc + 4)) / 4`（PC-relative，4 字节对齐）
- `breq/brne` 的 imms12 同理
- `call-iiii/jump-iiii` 的 imms24 同理
- 超出范围 → `MCFixup` 记录，链接期报错

注意：`rela` 指令的 imms18 = `(target_pc - rb0_at_linktime) / 4`，
实际为重定位，本任务作为 PCRel 处理占位，DL-012a 完善。

#### 1.3 `MCTargetDesc/DADAOMCInstPrinter.cpp`

继承 `MCInstPrinter`，实现 `printInstruction()` 和 `printOperand()`：

- 寄存器打印：`DADAO::RD8` → `"rd8"`（小写）；`DADAO::RB1` → `"rb1"`
- 立即数打印：有符号十进制（`-1`/`1` 等）
- 格式：`"助记符\t操作数1, 操作数2, ..."`

#### 1.4 `AsmParser/CMakeLists.txt` + 顶层 `CMakeLists.txt` 更新

- 添加 `AsmParser` 子目录，注册 `add_llvm_component_library`
- 在顶层 `CMakeLists.txt` 加 `add_subdirectory(AsmParser)`
- `MCTargetDesc/CMakeLists.txt` 加 `DADAOMCCodeEmitter.cpp` 和 `DADAOMCInstPrinter.cpp`

#### 1.5 AsmParser 注册（`TargetInfo/DADAOTargetInfo.cpp` 或 `MCTargetDesc.cpp`）

```cpp
extern "C" LLVM_EXTERNAL_VISIBILITY void LLVMInitializeDADAOAsmParser() {
  RegisterMCAsmParser<DADAOAsmParser> X(getTheDADAOTarget());
}
```

---

### 2. lit 测试（`tests/lit/MC/Dadao/`）

覆盖 **全部 M1 指令格式**的编码验证，每条指令至少一个正面用例 + 边界用例。
测试格式：

```asm
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=obj %s | llvm-objdump -d - | FileCheck %s
# 或：
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=obj %s -o %t
# RUN: llvm-objdump -d %t | FileCheck %s
```

**必须覆盖的 lit 测试文件**（DS 可合并或拆分，但覆盖不得减少）：

| 文件 | 覆盖内容 |
|------|---------|
| `encoding-rd-arith.s` | addi, add, sub, muls, mulu, divs, divu — 验证字节序列 |
| `encoding-rd-logic.s` | and, orr, xor, xnor, MISC-Norm subtable |
| `encoding-rd-shift.s` | shlu/shrs/shru/exts/extz reg+imm 两形式 |
| `encoding-rd-cmp.s` | cmps/cmpu imm+reg, csn/csz/csp/cseq/csne |
| `encoding-rd-wyde.s` | orw/andnw/setzw/setow，验证 rwii 位域分解 |
| `encoding-mem.s` | ldbs/ldbu/ldws/ldwu/ldts/ldtu/ldo, stb/stw/stt/sto |
| `encoding-mem-multi.s` | ldmbs…ldmo, stmb…stmo (rrri 格式) |
| `encoding-rb.s` | addi-rb, rela, orw-rb/andnw-rb/setzw-rb, sto-rb, rd2rb, rb2rd, rb2rb, add-rb, sub-rb, cmp-rb |
| `encoding-ctrl.s` | brn/brnn/brz/brnz/brp/brnp, breq/brne (相对偏移) |
| `encoding-jump-call.s` | jump-iiii/rrii, call-iiii/rrii, ret |
| `encoding-misc.s` | swym, unimp, rd2rd |
| `encoding-negative.s` | 立即数越界报错（CHECK：error 关键词）; 寄存器名错误 |

**期望字节值**必须从 `contracts/isa/spec.md §2.8 + §3-§6` 手推，**不得从 LLVM 输出自举**。
关键用例期望值（DS 用于自我核查）：

| 指令示例 | 预期编码（大端十六进制） |
|----------|----------------------|
| `addi rd8, rd0, 1` | `19 40 00 01` (op=0x19, ha=8, hb=0, imms12=1→hc:hd=00_01) |
| `addi rd8, rd0, -1` | `19 40 3F FF` (imms12=-1→hc:hd=0x3F_3F, 即 hc=63,hd=63) |
| `add rd9, rd10, rd11, rd12` | `1A 4A 2B 0C` (op=0x1A, ha=9, hb=10, hc=11, hd=12) |
| `brz rd8, .+8` | `2A 20 00 01` (op=0x2A, ha=8, imms18=+8→(+8-4)/4=1→hb:hc:hd=0x00_00_01) |
| `swym` | `10 00 00 00` (op=0x10, ha=0x00 minor, hb=hc=hd=0) |
| `ldo rd8, rb1, 0` | `<按 §2.8 行 01000_011=0x43> 20 04 00 00`（DS 核查具体 op 值） |

**注意**：`addi rd8, rd0, -1` 中 imms12=-1 = 0xFFF = 12'b111111_111111，
hc = bits[11:6] = 0b111111 = 63 = 0x3F；hd = bits[5:0] = 0b111111 = 63 = 0x3F。

---

### 3. `components/llvm/patches/series` 更新

追加 `0005-dadao-asmparser.patch`。

---

## 约束

1. **`make build-mc` 必须 PASS**；`llvm-lit tests/lit/MC/Dadao/` 全部通过
2. **不实现 Disassembler**（DL-011a）；MCInstPrinter 仅为 llvm-objdump -d 提供最小文本输出
3. **不实现 ELF relocation 逻辑**（DL-012a）；Branch 超出范围用 MCFixup 占位
4. **编码独立推导**：lit 测试期望字节必须来自 spec 手算，不得从 LLVM 输出复制
5. **大端输出**：`support::endian::write<uint32_t>(..., big)` — 不得用 little-endian
6. **immu12 vs imms12 区分**：`cmpu` 使用 immu12（无符号），其余 rrii 格式使用 imms12
7. **MISC-Norm 重名助记符**：cmps/cmpu 两种 format 靠操作数签名区分，AsmParser 必须能区分
8. **patch 05 紧接 04**：apply 顺序 01→02→03→04→05

---

## 验收步骤（DS 完成区填写）

```
make build-mc                          →  cmake + ninja PASS
llvm-mc --triple=dadao-unknown-elf \
  --filetype=obj -o /dev/null encoding-rd-arith.s  →  无错误
llvm-lit tests/lit/MC/Dadao/           →  0 failures
# 至少验证以下关键字节：
echo "addi rd8, rd0, 1" | \
  llvm-mc --triple=dadao-unknown-elf -filetype=obj - | \
  xxd | head -1                        →  首 4 字节 = 19 40 00 01
```

---

## 参考指针

| 资源 | 用途 |
|------|------|
| `contracts/isa/spec.md §2.2–§2.4` | 字段位置、立即数格式 |
| `contracts/isa/spec.md §2.8 + §2.8.1` | 全部 op/ha 值（lit 测试期望字节来源）|
| `contracts/isa/spec.md §3–§6` | 助记符、操作数顺序 |
| `llvm/lib/Target/Lanai/AsmParser/LanaiAsmParser.cpp` | 最简 AsmParser 风格参考 |
| `llvm/lib/Target/RISCV/MCTargetDesc/RISCVMCCodeEmitter.cpp` | 大端 emitter 风格参考 |
| `code-agent/tasks/DL-009a-llvm-instrinfo.md` | 指令 def、格式类、Operand 类型名 |
| `components/llvm/patches/0004-dadao-instrinfo.patch` | 现有 TableGen 内容（寄存器枚举名、Operand 类型）|

---

## 完成区

<!-- DS 在此填写 -->
