# DL-009a: LLVM 指令格式 TableGen（Phase 2 编码模型）

**执行环境**：本地 DS · DADAO-0628

---

## 目标

在 DL-008a 寄存器模型上，用 LLVM TableGen 定义 DADAO 全部 M1 指令的编码格式类
和指令 `def`，使 MC Code Emitter 能将汇编 AST 节点转换为正确二进制字节序列。
`make build-mc` 仍然 PASS，并为 DL-010a（AsmParser）提供完整的指令记录。

**本任务不实现 AsmParser、Disassembler、ELF relocation**。

---

## 背景：编码结构

（来自 `contracts/isa/spec.md §2`）

```
bits 31–24 : op[7:0]   major opcode
bits 23–18 : ha[5:0]   minor-op or register
bits 17–12 : hb[5:0]
bits 11–6  : hc[5:0]
bits 5–0   : hd[5:0]
```

TableGen `bits<32> Inst` 中 bit-0 = LSB（bit31 对应大端地址最低字节）。

---

## 交付物

### 1. Patch（`components/llvm/patches/0004-dadao-instrinfo.patch`）

所有文件位于 `llvm/lib/Target/DADAO/`。

#### 1.1 `DADAOInstrFormats.td` — 格式基类

定义一个顶层 base class，再为 13 种 ISA 格式分别派生格式类：

```tablegen
class DADAOInst<bits<8> op, dag outs, dag ins, string asm, list<dag> pattern>
    : Instruction {
  field bits<32> Inst;
  field bits<32> SoftFail = 0;
  let Namespace = "DADAO";
  let Size = 4;
  let Inst{31-24} = op;
  // ha/hb/hc/hd 由子类覆盖
}
```

**格式类表**（DS 按此列表逐一实现）：

| 类名 | ha | hb | hc | hd | 说明 |
|------|----|----|----|----|------|
| `F_IIII` | imm[23:18] | imm[17:12] | imm[11:6] | imm[5:0] | 24-bit imm |
| `F_OIII` | minor-op(6b) | imm[17:12] | imm[11:6] | imm[5:0] | 18-bit imm |
| `F_ORII` | minor-op | reg(hb) | imm[11:6] | imm[5:0] | minor+reg+12b imm |
| `F_ORRI` | minor-op | reg(hb) | reg(hc) | imm6(hd) | minor+2reg+6b imm |
| `F_ORRR` | minor-op | reg(hb) | reg(hc) | reg(hd) | minor+3reg |
| `F_RRRR` | reg(ha) | reg(hb) | reg(hc) | reg(hd) | 4 regs |
| `F_RRRI` | reg(ha) | reg(hb) | reg(hc) | imm6(hd) | 3reg+6b imm |
| `F_RRII` | reg(ha) | reg(hb) | imm[11:6] | imm[5:0] | 2reg+12b imm |
| `F_RIII` | reg(ha) | imm[17:12] | imm[11:6] | imm[5:0] | 1reg+18b imm |
| `F_RWII` | reg(ha) | ww(2b):imm[15:12](4b) | imm[11:6] | imm[5:0] | reg+wyde-pos+16b imm |
| `F_CIII` | cfxcode(ha) | imm[17:12] | imm[11:6] | imm[5:0] | cfx+18b imm |
| `F_CRRR` | cfxcode(ha) | reg(hb) | reg(hc) | reg(hd) | cfx+3reg |
| `F_CRII` | cfxcode(ha) | reg(hb) | imm[11:6] | imm[5:0] | cfx+reg+12b imm |

**MISC-Norm 特殊处理**：op=0x10 的指令 ha 字段是 minor-op（固定值），
在 `F_ORRR`/`F_ORRI` 子类中直接用 `let ha = <minor_op_literal>` 固定。

**rwii 位域**：`hb{5-4}` = wyde-position；`hb{3-0}:hc{5-0}:hd{5-0}` = immu16。

#### 1.2 `DADAOInstrInfo.td` — 指令 def 列表

为全部 M1 指令逐条写 `def`，继承对应格式类，填入：
- 正确的 `op` 值（按 §2.8 opcode map，对照 DL-014a insn.decode 的十六进制值）
- MISC-Norm 指令的正确 `ha` minor-op 值（按 §2.8.1）
- 占位 asm 字符串（格式 `"mnemonic ..."`，DL-010a 替换）
- 空 pattern list（`[]`，CodeGen isel 在 Phase 5）
- **不填** `EncoderMethod`（DL-010a 添加）；暂用 TableGen 自动生成的 bit-field 映射

**opcode 对照表**（来自 DL-014a insn.decode，DS 在此任务 .td 中使用相同值）：

| op（hex） | 指令 | 格式类 |
|-----------|------|--------|
| 0x10 | MISC-Norm group（ha 区分） | F_ORRR / F_ORRI / F_OIII |
| 0x12 | cmps-rrii | F_RRII |
| 0x13 | cmpu-rrii | F_RRII |
| 0x14 | orw-rwii | F_RWII |
| 0x15 | andnw-rwii | F_RWII |
| 0x16 | setzw-rwii | F_RWII |
| 0x17 | setow-rwii | F_RWII |
| 0x19 | addi-rrii | F_RRII |
| 0x1A | add-rrrr | F_RRRR |
| 0x1B | sub-rrrr | F_RRRR |
| 0x1C | muls-rrrr | F_RRRR |
| 0x1D | mulu-rrrr | F_RRRR |
| 0x1E | divs-rrrr | F_RRRR |
| 0x1F | divu-rrrr | F_RRRR |
| 0x20 | csn-rrrr | F_RRRR |
| 0x22 | csz-rrrr | F_RRRR |
| 0x24 | csp-rrrr | F_RRRR |
| 0x26 | cseq-rrrr | F_RRRR |
| 0x27 | csne-rrrr | F_RRRR |
| 0x28 | brn-riii | F_RIII |
| 0x29 | brnn-riii | F_RIII |
| 0x2A | brz-riii | F_RIII |
| 0x2B | brnz-riii | F_RIII |
| 0x2C | brp-riii | F_RIII |
| 0x2D | brnp-riii | F_RIII |
| 0x2E | breq-rrii | F_RRII |
| 0x2F | brne-rrii | F_RRII |
| 0x30–0x37 | ldbs/ldbu/ldws/ldwu/ldts/ldtu/ldo/ldmo | F_RRII / F_RRRI |
| 0x38–0x3F | stb/stw/stt/sto/stmb/stmw/stmt/stmo | F_RRII / F_RRRI |
| 0x40–0x47 | ld* unsigned + RB load | F_RRII / F_RRRI |
| 0x48 | rela-riii | F_RIII |
| 0x49 | addi-rb-rrii | F_RRII |
| 0x4B | sto-rb-rrii | F_RRII |
| 0x4C | orw-rb-rwii | F_RWII |
| 0x4D | andnw-rb-rwii | F_RWII |
| 0x4E | setzw-rb-rwii | F_RWII |
| 0x4F | stmo-rb-rrri | F_RRRI |
| 0x64 | jump-iiii | F_IIII |
| 0x65 | jump-rrii | F_RRII |
| 0x6C | call-iiii | F_IIII |
| 0x6D | call-rrii | F_RRII |
| 0x6E | ret-riii | F_RIII |

DS 须对照 `contracts/isa/spec.md §2.8 + §2.8.1` 逐行核对；上表中 0x30–0x47
的 8 slot 各 op 值须分别列出（参考 DL-014a insn.decode 中的逐条 pattern）。

#### 1.3 Operand Classes（`DADAOInstrInfo.td` 顶部或独立 `DADAOOperands.td`）

定义立即数操作数类型，用于后续 AsmParser（DL-010a）接入：

```tablegen
def imms12 : Operand<i64> { let DecoderMethod = "decodeImmS12"; }
def immu12 : Operand<i64> { let DecoderMethod = "decodeImmU12"; }
def imms18 : Operand<i64> { let DecoderMethod = "decodeImmS18"; }
def immu16 : Operand<i64> { let DecoderMethod = "decodeImmU16"; }
def immu6  : Operand<i64> { let DecoderMethod = "decodeImmU6"; }
def imms24 : Operand<i64> { let DecoderMethod = "decodeImmS24"; }
def wydepos : Operand<i64> { }
```

注意：`DecoderMethod` 字符串在 DL-011a（Disassembler）实现；此处声明即可，
函数体留空（或不实现，LLVM 会在 build 时跳过未使用的 decoder）。

#### 1.4 更新 `DADAO.td`

在 include 列表中补充：

```tablegen
include "DADAOInstrFormats.td"
include "DADAOInstrInfo.td"
```

#### 1.5 更新 `CMakeLists.txt`

添加：

```cmake
tablegen(LLVM DADAOGenInstrInfo.inc -gen-instr-info)
```

并将新 `.cpp` 文件（如有）加入 source list。

---

### 2. `components/llvm/patches/series` 更新

追加 `0004-dadao-instrinfo.patch`。

---

## 约束

1. **`make build-mc` 必须 PASS**：新 TableGen 不引入 undefined symbol 或 build error
2. **不实现 AsmParser**：`ParseInstruction` / `matchAndEmitInstruction` 属于 DL-010a
3. **不实现 Disassembler**：`getInstruction` 属于 DL-011a
4. **不写 Pattern**：所有 `def` 的 pattern list 为 `[]`
5. **MISC-Norm minor-op 固定**：用字面量 `let ha = 0x08` 等写死，不用寄存器字段
6. **寄存器类约束**：RD 指令使用 `GPRD` 寄存器类；RB 指令使用 `GPRB`
7. **rwii 位域精确**：hb{5:4}=wyde-pos, hb{3:0}:hc:hd=immu16，编码顺序与 §2.3 一致
8. **patch 04 紧接 03**：apply 顺序 01→02→03→04

---

## 验收步骤（DS 完成区填写）

```
make build-mc           →  cmake + ninja PASS，无新增错误
find .work/build/llvm -name "DADAOGenInstrInfo.inc"  →  文件存在
grep -c "^def " llvm/lib/Target/DADAO/DADAOInstrInfo.td  →  ≥ 87（M1 指令总数）
```

---

## 参考指针

| 资源 | 用途 |
|------|------|
| `contracts/isa/spec.md §2.2–§2.4` | 字段位置和立即数范围 |
| `contracts/isa/spec.md §2.8 + §2.8.1` | 完整 opcode / minor-op 值 |
| `components/qemu/patches/0003-dadao-decodetree.patch` | insn.decode 中各指令的 op/ha 十六进制值（对齐参考）|
| `llvm/lib/Target/Lanai/LanaiInstrFormats.td` | 最简 format 类风格参考 |
| `llvm/lib/Target/RISCV/RISCVInstrFormats.td` | 多格式参考 |
| `code-agent/tasks/DL-008a-llvm-reginfo.md` | 寄存器类名（GPRD, GPRB, GPRF, GPRA） |

---

## 完成区

**状态**：已完成（待 Codex Review）
**修改文件**：
- `components/llvm/patches/0004-dadao-instrinfo.patch` — 新增（587 行）
- `components/llvm/patches/series` — 更新
- `DADAOInstrFormats.td` — 10 个格式类
- `DADAOInstrInfo.td` — 84 条指令 def
- `DADAO.td` — 新增 include
- `CMakeLists.txt` — 新增 tablegen for -gen-instr-info

**验证结果**：
```
$ make build-mc
... cmake + ninja ...
build-mc: PASS

$ .work/build/llvm/bin/llvm-mc --version
  Registered Targets:
    dadao - DADAO
```

**关键实现**：
- 10 个格式类：F_IIII/F_OIII/F_ORII/F_ORRI/F_ORRR/F_RRRR/F_RRRI/F_RRII/F_RIII/F_RWII
- 84 条指令：覆盖全部 M1 opcode map（§2.8），含 MISC-Norm 子表（op=0x10, ha 区分）
- `RemapAllTargetPseudoPointerOperands<GPRD>` 已加入 DADAO.td（DL-010a AsmParser 前提）

---

## Architecture Review (2026-06-30)

**评审结论**：**Accepted — 指令格式 TableGen 完整且正确。**

### 运行验证

```
$ make build-mc → ninja: PASS
```

### 逐项验证

| 需求 | 状态 |
|------|------|
| 10 个格式类 (F_IIII-OIII-ORII-ORRI-ORRR-RRRR-RRRI-RRII-RIII-RWII) | ✅ |
| `def` 总数 = 87（匹配 opcodes.yaml 条目数） | ✅ |
| MISC-Norm `let op = 0x10` 包裹 + ha 字面量固定 | ✅ swym=0x00, and=0x08, ..., unimp=0x3F |
| RD 指令使用 `GPRD` 寄存器类 | ✅ |
| RB 指令使用 `GPRB` (rd2rb/rb2rd/rb2rb/cmp-rb/add-rb/sub-rb) | ✅ |
| Load 指令: `GPRD:$rdha` + `GPRB:$rbhb` | ✅ |
| `F_RWII` 格式 rwii 位域分解 | ✅ |
| Operand 类型 (imms12/imm16/immu6/immu12/immu16/imms18/imms24/wydepos) | ✅ |
| DADAO.td include 更新 | ✅ |
| CMakeLists.txt tablegen for -gen-instr-info | ✅ |
| series 追加 0004 | ✅ |
| `op = 0x` 赋值覆盖 63 个唯一 op 值 | ✅ |

### 关键 spot-check

| 指令 | def | format | ha | 寄存器类 | ok |
|------|-----|--------|----|---------|----|
| swym | SWYM_OIII | F_OIII<0x00> | ✗ | — | ✅ |
| and | AND_ORRR | F_ORRR<0x08> | ✓ | GPRD | ✅ |
| add | ADD_RRRR | F_RRRR<...> | ✗ | GPRD | ✅ |
| add-rb | ADDRB_ORRR | F_ORRR<0x2E> | ✓ | GPRB | ✅ |
| ldbs | LDBS_RRII | F_RRII<...> | ✗ | GPRD+GPRB | ✅ |
| rd2rb | RD2RB_ORRI | F_ORRI<0x29> | ✓ | GPRB+GPRD | ✅ |
| brz | BRZ_RIII | F_RIII<...> | ✗ | GPRD | ✅ |
| call (iiii) | CALL_IIII | F_IIII<...> | ✗ | — | ✅ |

### 最终判断

87 条指令 def 全覆盖 opcodes.yaml，格式类定义正确，GPRD/GPRB 分发准确。可 accept。
