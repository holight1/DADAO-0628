# §3 测试向量约定

**来源**：DL-001d, DL-020a, DL-027a, DL-028a review（2026-07-02）  
**交叉验证**：tests/vectors/schema.md, scripts/validate_vectors.py

---

## §3.1 五种向量类别

| class | expected_state | expected_fault | 目的 |
|-------|---------------|----------------|------|
| encoding | null | null | 验证 32-bit 指令字无异常执行 |
| legality | null | ILLI/UNDI/MALIGN | 非法操作数 → 预期异常 |
| semantic | required | null | 正常操作，验证寄存器/内存状态 |
| boundary | required | null/ILLI | 边界值（signed-min/max/zero/overflow） |
| overlap | required/null | null/ILLI | src=dst 寄存器重叠 |

## §3.2 YAML Schema 字段

```yaml
- mnemonic: add           # 必填：匹配 tools/opcodes.yaml
  format: orrr            # 必填：格式类型
  class: semantic         # 必填：encoding/legality/semantic/boundary/overlap
  encoding:               # 必填
    word: "0x1A042000"
  input_state: {}         # 必填：执行前寄存器/内存状态
  expected_state: null    # 条件必填：status=deferred 时为 null
  expected_fault: null    # null/ILLI/UNDI/MALIGN/IALIGN/RASOF/RASUF
  status: active          # active/deferred
  deferred_reason: null   # status=deferred 时必填
  wiki_cite: "spec.md §3.5"  # 必填
  notes: ""               # 可选
  branch_behavior: taken  # 仅控制流语义测试：taken/not_taken
```

## §3.3 encoding.word 计算

```
word = (op << 24) | (ha << 18) | (hb << 12) | (hc << 6) | hd
```

**encoding class 向量最小合法值**：
- 目标寄存器（dest rd/rb）：若 rd0/rb0 触发 ILLI → 用 1；否则用 0
- 源寄存器：用 0（rd0/rb0 作为源合法）
- 立即数：用 0
- immu6（rrri 格式多寄存器 count）：**必须用 1**（0 触发 ILLI）

## §3.4 RD/RB 变体处理

7 对 (mnemonic, format) 在 opcodes.yaml 中共享同一键但 op 值不同：

| 键 | RD op | RB op |
|----|-------|-------|
| (orw, rwii) | 0x14 | 0x4C |
| (andnw, rwii) | 0x15 | 0x4D |
| (setzw, rwii) | 0x16 | 0x4E |
| (ldo, rrii) | 0x33 | 0x43 |
| (sto, rrii) | 0x3B | 0x4B |
| (ldmo, rrri) | 0x37 | 0x47 |
| (stmo, rrri) | 0x3F | 0x4F |

每条必须有独立的 encoding.word 匹配对应 mask/value。

## §3.5 数据完整性准则

- encoding.word 从 spec §2.2 公式手推，不从 LLVM 输出复制
- expected_state 寄存器值从 spec 逐条推导，不从 QEMU 结果反推
- RB 高 16 位保留规则需单独验证（如 addi-rb 边界测试必须保留高 16 位）
- deferred case 必须出现在清单中，不得静默缺席

## §3.6 文件组织

```
tests/vectors/isa/
  rd-arith.yaml         # add/sub/mul/divs/divu/muls/mulu/addi
  rd-logic.yaml         # and/orr/xor/xnor
  rd-shift-extend.yaml  # shlu/shrs/shru/exts/extz
  rd-compare.yaml       # cmps/cmpu
  rd-cond-assign.yaml   # csn/csz/csp/cseq/csne
  rd-load-store.yaml    # ld*/st* 单次及多次
  rd-wyde-block.yaml    # orw/andnw/setzw/setow + block copy
  rb-ops.yaml           # RB 算术/比较/load/store/立即数
  control-flow.yaml     # branch/jump/call/ret
  misc.yaml             # swym/unimp
```
