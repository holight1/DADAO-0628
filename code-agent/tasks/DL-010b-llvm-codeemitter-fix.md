# DL-010b: LLVM MCCodeEmitter 修复 + 全量 lit 测试

**执行环境**：本地 DS · DADAO-0628

---

## 背景

DL-010a 交付的 `DADAOMCCodeEmitter::encodeInstruction()` 是一个完全的 stub：

```cpp
// FIXME: Implement once instruction encoding is properly defined
support::endian::write<uint32_t>(CB, 0, llvm::endianness::big);
```

它对所有指令写出 `0x00000000`，从未调用 `getBinaryCodeForInstr()`。
`-filetype=asm` 路径不经过 CodeEmitter 所以看起来正常；
`-filetype=obj` 路径调用 `encodeInstruction()` 时可能因 ELF section 尺寸
或 fixup 处理崩溃（SEGFAULT）。

`AsmParser`、`getMachineOpValue`、`MCInstPrinter` 实现已正确，本任务只修 Emitter。

---

## 目标

1. 修复 `encodeInstruction()` 使其调用 TableGen 生成的 `getBinaryCodeForInstr()`
2. 验证 `addi rd8, rd0, 1` 输出字节 `19 40 00 01`
3. 交付 **全部 12 个 lit 测试文件**，`llvm-lit tests/lit/MC/Dadao/` 0 failures

---

## 交付物

### 1. 修改 `0005-dadao-asmparser.patch`（替换原文件，序号不变）

#### 1.1 `DADAOMCCodeEmitter.cpp` 修复

```cpp
#define GET_INSTRINFO_ENUM
#include "DADAOGenInstrInfo.inc"
#define ENABLE_INSTR_PREDICATE_VERIFIER
#include "DADAOGenMCCodeEmitter.inc"
```

`encodeInstruction()` 实现：

```cpp
void DADAOMCCodeEmitter::encodeInstruction(const MCInst &MI,
                                           SmallVectorImpl<char> &CB,
                                           SmallVectorImpl<MCFixup> &Fixups,
                                           const MCSubtargetInfo &STI) const {
  uint32_t Bits = getBinaryCodeForInstr(MI, Fixups, STI);
  support::endian::write<uint32_t>(CB, Bits, llvm::endianness::big);
}
```

`getMachineOpValue()` 保持 DL-010a 实现不变（注册值 + 立即数）。

**注意**：`getBinaryCodeForInstr` 由 TableGen 生成（`DADAOGenMCCodeEmitter.inc`），
需要 `#include` 该文件并在 `DADAOMCCodeEmitter` 类中声明为友元或在同一命名空间。
参照 `llvm/lib/Target/Lanai/MCTargetDesc/LanaiMCCodeEmitter.cpp` 的 include 方式。

#### 1.2 Branch 和 Jump 的 MCFixup 占位

对于 `imms18`（`brn/breq` 等）、`imms24`（`jump/call-iiii`）等 PC-relative 操作数，
`getMachineOpValue` 遇到 `MCExpr` 时创建 MCFixup 并返回 0：

```cpp
if (MO.isExpr()) {
  Fixups.push_back(MCFixup::create(0, MO.getExpr(),
                                   MCFixupKind(DADAO::fixup_dadao_pcrel18)));
  return 0;
}
```

Fixup kind 在 `DADAOFixupKinds.h` 中声明（可先用 `FK_PCRel_4` 占位，DL-012a 完善）。

---

### 2. lit 测试文件（12 个，`tests/lit/MC/Dadao/`）

**通用 RUN 模板**（每个文件都需要两条 RUN 行）：

```asm
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=obj %s -o %t
# RUN: llvm-objdump -d %t | FileCheck %s
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=asm %s | FileCheck %s --check-prefix=ASM
```

**期望字节必须手推（不得从 llvm-mc 输出复制）**。公式来源：
`contracts/isa/spec.md §2.2`（指令字段布局）+ `§2.8`（opcode 表）。

编码公式：`word[31:24]=op, [23:18]=ha, [17:12]=hb, [11:6]=hc, [5:0]=hd`

关键期望值（供 DS 自我核查）：

| 指令 | 手推编码（大端） |
|------|----------------|
| `addi rd8, rd0, 1` | `19 40 00 01`（op=0x19, ha=8, hb=0, hc=0, hd=1） |
| `addi rd8, rd0, -1` | `19 40 3F FF`（imms12=-1→hc=63,hd=63） |
| `add rd9, rd10, rd11, rd12` | `1A 4A 2B 0C`（op=0x1A, ha=9, hb=10, hc=11, hd=12） |
| `swym` | `10 00 00 00`（op=0x10, ha=0, hb=hc=hd=0） |
| `brz rd8, .+8` | `2A 20 00 01`（op=0x2A, ha=8, imms18=(8-4)/4=1→hb:hc:hd=0x00_00_01） |

#### 文件清单

| 文件 | 覆盖内容 |
|------|---------|
| `encoding-rd-arith.s` | addi, add, sub, muls, mulu, divs, divu |
| `encoding-rd-logic.s` | and, orr, xor, xnor；MISC-Norm（op=0x10, ha=subtable） |
| `encoding-rd-shift.s` | shlu/shrs/shru（reg+imm 两形式）；exts/extz |
| `encoding-rd-cmp.s` | cmps/cmpu（imm+reg）；csn/csz/csp/cseq/csne |
| `encoding-rd-wyde.s` | orw/andnw/setzw/setow（rwii 格式，wydepos 字段） |
| `encoding-mem.s` | ldbs/ldbu/ldws/ldwu/ldts/ldtu/ldo；stb/stw/stt/sto |
| `encoding-mem-multi.s` | ldmbs…ldmo；stmb…stmo（rrri 格式） |
| `encoding-rb.s` | addi-rb, rela, orw-rb/andnw-rb/setzw-rb, sto-rb, rd2rb, rb2rd, rb2rb, add-rb, sub-rb, cmp-rb |
| `encoding-ctrl.s` | brn/brnn/brz/brnz/brp/brnp, breq/brne（相对偏移） |
| `encoding-jump-call.s` | jump-iiii/rrii, call-iiii/rrii, ret |
| `encoding-misc.s` | swym, unimp, rd2rd |
| `encoding-negative.s` | 立即数越界报错；寄存器名非法（CHECK: error） |

每个文件需覆盖：
- 至少 1 个"正常值"用例（字节完整匹配）
- 至少 1 个"边界值"用例（如 imms12 = -2048、2047）
- `-filetype=obj` 和 `-filetype=asm` 两条路径

---

## 约束

1. **`encodeInstruction` 必须调用 `getBinaryCodeForInstr`**，不得保留 stub
2. **期望字节手推**：lit 测试 CHECK 行字节来自 spec §2.2/§2.8 公式，不得从 llvm-mc 输出复制
3. **两条 RUN 行**：每个 lit 文件必须同时测 `-filetype=obj` 和 `-filetype=asm`
4. **patch 序号保持 0005**：替换原文件，series 不变
5. **`make build-mc` PASS**：patch 01→02→03→04→05 全部干净 apply 后 ninja 无错
6. **`llvm-lit tests/lit/MC/Dadao/` 0 failures**

---

## 验收步骤（DS 完成区填写）

```
make build-mc                             →  PASS
echo "addi rd8, rd0, 1" |
  llvm-mc --triple=dadao-unknown-elf \
  -filetype=obj - | xxd | head -1         →  首 4 字节 = 19 40 00 01
echo "addi rd8, rd0, -1" | ... | xxd      →  首 4 字节 = 19 40 3f ff
llvm-lit tests/lit/MC/Dadao/              →  0 failures
```

---

## 参考指针

| 资源 | 用途 |
|------|------|
| `components/llvm/patches/0005-dadao-asmparser.patch` | DL-010a 产出（替换此文件） |
| `contracts/isa/spec.md §2.2–§2.4` | 字段位置和立即数编码公式 |
| `contracts/isa/spec.md §2.8 + §2.8.1` | 全部 op/ha 值（lit 期望字节来源） |
| `llvm/lib/Target/Lanai/MCTargetDesc/LanaiMCCodeEmitter.cpp` | `getBinaryCodeForInstr` include 方式 |
| `code-agent/tasks/DL-009a-llvm-instrinfo.md` | 格式类、Operand 类型名 |
| `code-agent/designs/0003-testing-roadmap.md §阶段一` | lit 测试两条 RUN 行要求 |

---

## 完成区

<!-- DS 在此填写 -->
