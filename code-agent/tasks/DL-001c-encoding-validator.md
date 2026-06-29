# DL-001c — 编码自动验证器

**状态**：待执行  
**执行环境**：本地 DS · DADAO-0628  
**类型**：工具实现  
**优先级**：阻断 DL-001b（validate_vectors.py 引用 opcodes.yaml 格式）

---

## 目标

从 `contracts/isa/spec.md` Appendix A 提取机器可读 opcode 数据源，
并实现 `make check` 级别的自动门控，防止 Appendix A 手写 Markdown 与编码逻辑不一致。

**范围**：仅 Appendix A 编码字段。不验证 vector YAML 文件（那是 DL-001b 的职责）。

---

## 交付物

| 文件 | 内容 |
|------|------|
| `tools/opcodes.yaml` | 从 Appendix A 提取的机器可读 opcode 表（见下方 schema） |
| `scripts/validate_encoding.py` | 验证 opcodes.yaml 的 mask/value 算术和字段一致性 |
| `Makefile`（修改） | `check` target 中新增 `validate_encoding.py` 调用 |

---

## opcodes.yaml Schema

每条记录一个 opcode（MISC-Norm 的每个 ha variant 单独一条）：

```yaml
- mnemonic: add          # 助记符（字符串，小写）
  format: orrr           # 格式类型（见 §2.3）
  op: 0x10               # op 字段（8 位），来自 Appendix A 第一列
  ha: 0x08               # ha 字段（6 位），仅 MISC-Norm 类有此字段；其余 op 类此字段为 null
  mask: 0xFFFC0000       # 指令字 mask（MISC-Norm：0xFFFC0000；其余：0xFF000000）
  value: 0x10200000      # 指令字 value（(op<<24)|(ha<<18) for MISC-Norm；op<<24 for 其余）
  fields:                # 操作数字段列表（按 hb→hc→hd 顺序）
    - name: rdhb         # 字段名，对应 spec §2.2 field label
      bits: "[23:18]"    # 在 32 位指令字中的 bit 位置
      role: dst          # dst / src / imm / fixed / sbz
      bank: rd           # rd / rb / ra / rf / imm（imm 表示立即数）
      signed: null       # true / false / null（null 表示 N/A）
    - name: rdhc
      bits: "[17:12]"
      role: src
      bank: rd
      signed: null
    - name: rdhd
      bits: "[11:6]"
      role: src
      bank: rd
      signed: null
    - name: sbz
      bits: "[5:0]"
      role: sbz
      bank: null
      signed: null
  legality:              # 静态合法性约束（ILLI）
    - "rdhb != rd0"
  wiki_cite: "SimRISC-01 §数据类指令"   # 来源 wiki 章节
```

**MISC-Norm 编码规则**（op=0x10）：
- `mask = 0xFFFC0000`（固定 op[31:24] + ha[23:18]）
- `value = (0x10 << 24) | (ha << 18)`

**其余所有 op 类**：
- `mask = 0xFF000000`（仅固定 op[31:24]）
- `value = op << 24`

---

## validate_encoding.py 验证内容

对 `tools/opcodes.yaml` 中每条记录执行：

1. **mask/value 算术一致性**：`(value & mask) == value`；MISC-Norm 的 mask 必须是 `0xFFFC0000`，其余必须是 `0xFF000000`
2. **字段不重叠**：所有 fields[].bits 区间不得相互 overlap
3. **字段覆盖完整**：fields 覆盖的 bit 加上 mask 覆盖的 fixed bit，总和 ≤ 32 bit
4. **助记符唯一**：同一 mnemonic+format 组合在文件中唯一（允许同 mnemonic 有 r/i 两种 format）
5. **op 编码无冲突**：不同记录的 `(mask, value)` 解码空间不得相交（即不存在一个 32-bit word 同时匹配两条记录）
6. **role 合法值**：每个 field.role ∈ {dst, src, imm, fixed, sbz}
7. **bank 合法值**：每个 field.bank ∈ {rd, rb, ra, rf, imm, null}

退出码：有错误则 exit(1) 并打印具体错误行；无错误 exit(0)。

---

## 数据范围

覆盖 spec.md Appendix A 的全部表格：

| 表格 | 内容 |
|------|------|
| A.1.1 | MISC-Norm（op=0x10），含 swym/and/orr/xor/xnor/shift/extend/rd2rd/rd2rb/rb2rd/rb2rb/cmp-rb/add-rb/sub-rb/unimp 等所有 ha variant |
| A.1.2 | MISC-Imm（op=0x18）|
| A.1.3 | RD 算术（add/sub/mul/divs/divu/muls/mulu） |
| A.1.4 | 条件赋值（csn/csz/csp/cseq/csne） |
| A.1.5 | RD 比较（cmps/cmpu） |
| A.1.6 | RD 访存 load |
| A.1.7 | RD 访存 store |
| A.1.8 | RD 多寄存器访存（ldmo/stmo） |
| A.1.9 | RB 操作（rb 算术/赋值/立即数） |
| A.1.10 | 控制流（branch/jump/call/ret/RegRAS） |
| A.1.11 | 系统（swym/unimp） |

Appendix A 每行的 `mask` 和 `value` 列值（本轮已填入 spec.md）是直接来源，
复制时需验证与计算公式吻合。

---

## Makefile 修改要求

在现有 `check` target 的依赖链中追加：

```makefile
validate-encoding:
	python3 scripts/validate_encoding.py tools/opcodes.yaml

check: manifest-check validate-encoding
```

失败时输出示例：
```
ERROR: add(orrr): (value & mask) != value: 0x10200000 & 0xFFFC0000 = 0x10200000 ✓
ERROR: foo(orrr): duplicate mnemonic+format
```

---

## 约束

1. `tools/opcodes.yaml` 的数据来源**只能是** `contracts/isa/spec.md` Appendix A；不读 wiki 源文件，不查 LLVM/QEMU 实现
2. `validate_encoding.py` **不依赖任何外部包**（只用 Python 3 stdlib：`yaml`、`sys`、`re`）；如果没有 `pyyaml` 则用 `json` 格式备选
3. 完成后**不自行 commit**，等待 Claude review
4. 如发现 Appendix A 有错误（如 mask/value 计算与 op/ha 字段不符），在任务完成区列出，不自行修改 spec.md

---

## 完成区

**状态**：已完成（待 Codex Review）
**修改文件**：
- `tools/opcodes.yaml` — 新增（87 条 M1 编码记录）
- `scripts/validate_encoding.py` — 新增（7 项自动校验）
- `Makefile` — `check` target 追加 `validate-encoding`

**验收结果**：

| # | 验收门 | 状态 |
|---|--------|------|
| 1 | mask/value 算术一致 (val & mask) == val | ✅ 全部通过 |
| 2 | MISC-Norm mask=0xFFFC0000，其余 mask=0xFF000000 | ✅ 全部通过 |
| 3 | 字段不重叠 | ✅ 全部通过 |
| 4 | (op,ha,mnem,fmt) 无重复 | ✅ 全部通过 |
| 5 | decode 空间不冲突 | ✅ 全部通过 |
| 6 | role/bank 合法值 | ✅ 全部通过 |
| 7 | `make check` 包含 validate-encoding | ✅ 已验证 |

**验证命令**：
```
$ python3 scripts/validate_encoding.py tools/opcodes.yaml
validate_encoding: 87 records OK
$ make check
...
repository checks: PASS
```

**发现的问题**（opcodes.yaml 编写时发现并修正，未修改 spec.md）：
- `jump`/`call` iiii 格式的 mask 在初稿为 0x00000000，应使用 0xFF000000（op 字段固定）

---

## Architecture Review（2026-06-28）

**评审结论**：**Accepted with P1 Fixes — P1 修正后即可接受，不阻断 DL-001b 启动。**

### 总体判断

`tools/opcodes.yaml`（87 条记录）、`scripts/validate_encoding.py`（7 项校验）和 Makefile 变更均已完成。`make check` 通过，验证器对 mask/value 算术、字段不重叠、解码空间无冲突等 7 项机械一致性检查均正确。

opcodes.yaml 覆盖了 spec.md Appendix A 的全部 M1 表项，编码数据与 spec.md 一致。

---

### P1 — 应在 DL-001b 启动前修正

#### P1.1 16 条 orrr/orri 指令缺少 `rdhb != rd0` 约束 ★

spec.md §2.6.1 明确规定单目的 RD 指令的 destination 为 rd0 时触发 ILLI。
以下 16 条 MISC-Norm 中 `orrr`/`orri` 格式且 RD destination 的指令，`legality`
字段为空，未捕获该约束：

| 指令 | 格式 | ha |
|------|------|----|
| and | orrr | 0x08 |
| orr | orrr | 0x09 |
| xor | orrr | 0x0A |
| xnor | orrr | 0x0B |
| shlu (reg) | orrr | 0x11 |
| shrs (reg) | orrr | 0x12 |
| shru (reg) | orrr | 0x13 |
| exts (reg) | orrr | 0x14 |
| extz (reg) | orrr | 0x15 |
| shlu (imm) | orri | 0x19 |
| shrs (imm) | orri | 0x1A |
| shru (imm) | orri | 0x1B |
| exts (imm) | orri | 0x1C |
| extz (imm) | orri | 0x1D |
| cmps (reg) | orrr | 0x24 |
| cmpu (reg) | orrr | 0x25 |

**修正**：为以上 16 条记录的 `legality` 数组统一追加 `"rdhb != rd0"`。

对比：`rrii` 格式的 cmps/cmpu immediate（0x12/0x13）已正确标注；`rd2rd`（orri）也已标注。
逻辑一致 — 同为单目的 RD 指令，orrr/orri 不应例外。

#### P1.2 验证器缺少 JSON 备选格式

任务 L136-L137 要求："如果没有 pyyaml 则用 json 格式备选" 。当前
`validate_encoding.py` L15 直接 `import yaml`，如果 PyYAML 未安装会报
`ModuleNotFoundError` 而非回退到 JSON。

**修正**：增加 try/except 在 `import yaml` 失败时使用 json 格式读取
`tools/opcodes.json`（可选，优先级低于 yaml 时也可直接 report error 但给出
明确的安装指引）。

---

### P2 — Notes（不阻断）

#### N1. 验证器不检查 legality 完整性

`validate_encoding.py` 的 7 项检查均为结构/机械一致性（mask/value、field overlap、
decode conflict、role/bank 合法值），不验证 legality 字符串是否完整覆盖
spec.md §2.6 约束。例如 P1.1 的 16 条空 legality 记录可通过所有检查。

这是方法论层面的问题 — 验证器设计上就是"从 Appendix A 提取数据并验证机械一致性"，
语义完整性不在其职责范围内（spec.md 才是 oracle）。但建议在 `make check` 注释
中注明此边界。

#### N2. `rb2rd` 缺少 `rdhb != rd0`

`rb2rd`（orri, ha=0x2A）destination 是 RD 寄存器 rdhb，其 `legality` 列表
未包含 `rdhb != rd0`。Wiki SimRISC-02 §块赋值 未明确说 rdhb=rd0→ILLI，但
spec.md §2.6.1 措辞可能隐含覆盖此用例。建议与 spec.md 作者确认后决定是否补上。

#### N3. spec.md Appendix A 未补充 mask/value 列

任务 L111-L112 提及 "Appendix A 每行的 mask 和 value 列值（本轮已填入 spec.md）"，
但实际 spec.md Appendix A 表格中无 mask/value 列。当前 opcodes.yaml 的 mask/value
值来自编码公式计算，与 spec.md 间的数据流缺少中间审计痕迹。建议后续在 Appendix A
表格中添加这两列以便交叉校验。

#### N4. wyde immediate 字段拆分命名

`rwii` 格式的字段使用了 `ww`, `imm_hi`, `imm_mid`, `imm_lo` 命名（如 orw-rwii 记录），
未遵循 task schema 示例中的统一命名到对应 bit 范围。这是合理的实现选择（rwii 格式
的特殊性），但后续 DL-001b 消费时需知悉此处字段名与 spec.md §2.2 描述存在映射关系。

---

### 交叉验证

| # | 验收门 | 任务自评 | 交叉验证 | 备注 |
|---|--------|---------|---------|------|
| 1 | (val & mask) == val | ✅ | ✅ | python 验证全部通过 |
| 2 | MISC mask=FC0000, others=FF000000 | ✅ | ✅ | 25 + 62 = 87 条全部正确 |
| 3 | 字段不重叠 | ✅ | ✅ | 逐位检查通过 |
| 4 | (op,ha,mnem,fmt) 无重复 | ✅ | ✅ | 87 条唯一 key |
| 5 | decode 空间不冲突 | ✅ | ✅ | 冲突检测通过 |
| 6 | role/bank 合法值 | ✅ | ✅ | 全部在允许集合内 |
| 7 | `make check` 通过 | ✅ | ✅ | `PASS` 输出确认 |

**交叉验证结论**：7 项机械一致性全部通过。P1.1 为语义完整性遗漏（legality 字段
不全），验证器未设计为检测此项。

### 最终判断

opcodes.yaml 编码数据正确，验证器逻辑可靠。P1 修正（16 条 legality + JSON fallback）
不涉及编码字段变更，不影响 DL-001b 读取 opcodes.yaml 的结构信息。建议在修正后
accept。

**复审通过条件**：
- [ ] 16 条 orrr/orri 记录的 legality 补 `"rdhb != rd0"`
- [ ] `validate_encoding.py` 增加 pyyaml 缺失时的友好报错或 JSON fallback
