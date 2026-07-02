# §2 ISA 编码与操作数合法规则

**来源**：DL-001b/c/d, DL-015a, DL-016a, DL-018a review（2026-07-02）  
**交叉验证**：contracts/isa/spec.md §2, 工具 tools/opcodes.yaml

---

## §2.1 指令字段布局

```
31      24 23   18 17   12 11    6 5      0
+---------+-------+-------+-------+-------+
|  op[8]  | ha[6] | hb[6] | hc[6] | hd[6] |
+---------+-------+-------+-------+-------+
```

全大端序：bits[31:24] (op) 位于最低内存地址。

## §2.2 13 种格式及寄存器/立即数分配

| 格式 | ha | hb | hc | hd |
|------|----|----|----|----|
| iiii | imm[23:18] | imm[17:12] | imm[11:6] | imm[5:0] |
| oiii | minor-op(6b) | imm[17:12] | imm[11:6] | imm[5:0] |
| orii | minor-op(6b) | reg | imm[11:6] | imm[5:0] |
| orri | minor-op(6b) | reg(dest) | reg(src1) | imm6 |
| orrr | minor-op(6b) | reg(dest) | reg(src1) | reg(src2) |
| rrrr | reg(dest_hi) | reg(dest_lo) | reg(src1) | reg(src2) |
| rrri | reg(dest_start) | reg(base) | reg(offset) | immu6(count) |
| rrii | reg(dest) | reg(src/base) | imm[11:6] | imm[5:0] |
| riii | reg | imm[17:12] | imm[11:6] | imm[5:0] |
| rwii | reg | ww(2b):imm[15:12](4b) | imm[11:6] | imm[5:0] |

注：orrr 和 orri 格式中 ha = minor-op（固定值），hb = 目标寄存器。

## §2.3 立即数拼接规则

多域立即数按 hb → hc → hd 高位到低位拼接：
- 12 位立即数（rrii/orii）：hc（高 6 位）+ hd（低 6 位）
- 18 位立即数（riii/ciii/oiii）：hb（高 6 位）+ hc（中 6 位）+ hd（低 6 位）
- rwii 格式：immu16 高 4 位在 hb[3:0]、中 6 位在 hc、低 6 位在 hd；wyde-position 在 hb[5:4]

## §2.4 操作数合法性规则（ILLI 触发器）

### §2.4.1 RD 目标规则

| 条件 | 指令 | 行为 |
|------|------|------|
| rdha == rd0（单目标） | addi, cmps/cmpu(rrii), ld*, 移位, 扩展, wyde imm | **ILLI** |
| rdhb == rd0（orrr/orri 目标） | and/orr/xor/xnor, 移位, 扩展, cmps/cmpu(orrr) | **ILLI** |
| rdha == rd0 且 rdhb == rd0（双目标） | add/sub/mul/div | **ILLI** |
| rdha == rdhb 且两者均 ≠ rd0 | add/sub/mul/div | **ILLI** |
| rdha == rd0（合法，丢弃高/低半） | add/sub/mul/div（仅一个为 rd0） | **合法** |
| brz rd0 | 条件分支 | **合法**（始终跳转，rd0=0） |
| brnz rd0 | 条件分支 | **合法**（永不跳转） |
| 存储类 ha == rd0 | stb/stw/stt/sto | **合法**（从 rd0 读取零值） |

### §2.4.2 RB 目标规则

| 条件 | 指令 | 行为 |
|------|------|------|
| rbha == rb0（写入目标） | addi-rb, add-rb, sub-rb, rd2rb, rb2rb, rela, orw-rb, andnw-rb, setzw-rb | **ILLI** |

### §2.4.3 多寄存器规则

| 条件 | 行为 |
|------|------|
| immu6 == 0 | **ILLI** |
| rdha/rbha + immu6 > 64（目标溢出） | **ILLI** |

## §2.5 RB 高 16 位行为表

| 操作类别 | 指令 | bits[63:48] behavior |
|---------|------|---------------------|
| 存取类-内存↔RB | ldo/ldmo/sto/stmo | **全覆盖**：写入全部 64 位 |
| 赋值类-寄存器 | rd2rb/rb2rb/ra2rd/rd2ra | **全覆盖** |
| 赋值类-立即数 | setzw-rb/orw-rb/andnw-rb | **全覆盖**：w3（bits[63:48]）合法 |
| 算术运算-加减 | add-rb/sub-rb/addi-rb/rela | **仅低 48 位**：高 16 位**保持不变** |
| 算术运算-比较 | cmp-rb | **仅比较低 48 位**：高 16 位忽略 |
| 控制流-跳转 | br*/jump | **仅低 48 位**：溢出丢弃 |
| 控制流-函数 | call/ret | **低 48 位**：高 16 位用作引用计数（RA） |

## §2.6 保留编码行为

- 保留 opcode（opcode map 中的空槽位）→ **UNDI**
- MISC-Norm 子表中未列出的 ha 值 → **UNDI**
- SBZ 字段非零 → **ILLI**（ADR-0004 决策映射）

## §2.7 除法语义

| 条件 | 行为 |
|------|------|
| 除数为零 | **ILLI**（精确；rdha/rdhb 无写入） |
| 截断方向 | 向零截断（C99） |
| 余数符号 | 等于被除数符号 |
| INT64_MIN ÷ -1 | **ILLI**（唯一溢出情况） |
| 操作数重叠 | 先读取所有源操作数，再写目标（源快照） |
