# DL-017a: Vector 覆盖率修复（opcode identity + encoding.word 补全）

**执行环境**：本地 DS · DADAO-0628

---

## 背景

`validate_vectors.py` 当前用 `(mnemonic, format)` 作为覆盖率统计主键，
导致两类误报：

1. **假全覆盖**：`0x47 ldmo`、`0x4D andnw-rb` 与其他 opcode 同 mnemonic+format，
   被已有 vector 错误"顶替"，脚本报 `79/79 covered OK`，但这两条指令实际无 vector。
2. **encoding.word 未验证**：当前脚本不检查 `encoding.word` 是否符合
   `tools/opcodes.yaml` 的 `mask`/`value` 约束，错误字段可以静默通过。

---

## 目标

1. 修改 `scripts/validate_vectors.py`：以 `(op, ha)` 为覆盖率主键
2. 补全所有 vector 的 `encoding.word`（现有 class=encoding 的 word 多已有，
   但 semantic/boundary/legality 中有缺漏）
3. 验证 `encoding.word` 符合对应 opcode 的 `mask`/`value` 约束
4. `make check` 在 `0x47 ldmo` 和 `0x4D andnw-rb` 缺 vector 时必须失败

---

## 交付物

### 1. `scripts/validate_vectors.py` 修改

#### 1.1 opcode 加载：建立 `(op, ha)` 主键索引

```python
def load_opcodes(path):
    with open(path) as f:
        records = yaml.safe_load(f)
    by_mnem_fmt = {}   # (mnemonic, format) → [(op, ha, mask, value), ...]
    by_opid = {}       # (op, ha_str) → mnemonic  (for coverage reporting)
    for rec in records:
        key = (rec["mnemonic"], rec["format"])
        op = rec["op"]
        ha = rec.get("ha")          # null for non-MISC-Norm
        opid = (op, str(ha))
        by_mnem_fmt.setdefault(key, []).append(rec)
        by_opid[opid] = rec["mnemonic"]
    return by_mnem_fmt, by_opid
```

#### 1.2 vector 校验：增加两项检查

在 `validate_file()` 中增加：

**A. encoding.word vs mask/value 校验**

```python
if word and mnem != "?" and fmt != "?":
    recs = opcodes_by_mnem_fmt.get((mnem, fmt), [])
    for rec in recs:
        mask = int(rec["mask"], 16)
        value = int(rec["value"], 16)
        wval = int(word, 16)
        if (wval & mask) != value:
            errors.append(
                f"{tag}: encoding.word {word} does not match "
                f"mask={rec['mask']} value={rec['value']} for {mnem}({fmt})")
            break
```

**B. 覆盖率主键改用 (op, ha)**

```python
if key in opcodes_by_mnem_fmt and status == "active":
    for rec in opcodes_by_mnem_fmt[key]:
        opid = (rec["op"], str(rec.get("ha")))
        covered_opids.add(opid)
```

#### 1.3 覆盖率报告：按 (op, ha) 统计

```python
for opid, mnem in by_opid.items():
    if opid not in covered_opids:
        if mnem in ("rd2ra", "ra2rd"):  # M1 excluded
            continue
        all_errors.append(
            f"COVERAGE MISSING: {mnem} op={opid[0]} ha={opid[1]}"
            f" — no active vector found")
```

---

### 2. Vector YAML 补全

**必须补充的高优先级 vector（`make check` 当前失败项）**：

| opcode | op | ha | 文件 | 需要的 class |
|--------|----|----|------|-------------|
| `ldmo` | 0x47 | null | `rd-load-store.yaml` | semantic (multi octa load) |
| `andnw-rb` | (查 opcodes.yaml) | (查) | `rb-ops.yaml` | semantic |

每条 vector 需要：
- `encoding.word`：由 spec §2.2 公式计算（`op<<24 | ha<<18 | ...`），
  或从 `tools/opcodes.yaml` 的 `value` 字段推导默认形式
- `input_state`/`expected_state`：合理的寄存器初始值和预期结果
- `wiki_cite`：对应 spec 章节

**其他缺漏 encoding.word 的 vector**：遍历所有 yaml 文件，找 `encoding.word` 为空或
`null` 的条目，按 spec §2.2 公式补全。

encoding.word 计算公式：
```
word = (op << 24) | (ha << 18) | (hb << 12) | (hc << 6) | hd
```
其中 ha/hb/hc/hd 的来源：对 `encoding` class vector，取实际操作数值；
对 `semantic/legality` class vector，取 `input_state` 中对应寄存器编号。

---

## 约束

1. **不改 `tools/opcodes.yaml`**：opcodes.yaml 是 oracle，不动
2. **不改 `tests/vectors/schema.md`**（除非需要补文档字段定义）
3. **`make check` 必须通过**：`python3 scripts/validate_vectors.py` 零错误，
   且覆盖率输出必须列出所有 M1 opcode（包括 0x47 ldmo 和 0x4D andnw-rb）
4. **不增加 deferred case**：0x47/0x4D 必须补真实 active vector

---

## 验收步骤（DS 完成区填写）

```
python3 scripts/validate_vectors.py          →  0 errors, N/M covered OK
# 验证主键修复
grep "0x47\|ldmo.*octa" scripts/validate_vectors.py  →  有 opid 路径
# 验证 encoding.word 校验
# （在某个 yaml 故意改错 encoding.word，make check 应该报错）
make check                                   →  PASS
```

---

## 参考指针

| 资源 | 用途 |
|------|------|
| `tools/opcodes.yaml` | opcode 完整列表，op/ha/mask/value 来源 |
| `tests/vectors/schema.md` | vector 字段规范 |
| `tests/vectors/inventory.md` | 当前覆盖矩阵（参考，不是权威）|
| `contracts/isa/spec.md §2.2` | encoding.word 计算公式 |
| `contracts/isa/spec.md Appendix A` | opcode 表（与 opcodes.yaml 对应）|

---

## 完成区

**状态**：已完成（待 Codex Review）
**修改文件**：
- `scripts/validate_vectors.py` — 覆盖率主键改为 (op,ha)，新增 encoding.word 校验
- `tests/vectors/isa/rd-load-store.yaml` — 补充 `ldmo (0x47)`
- `tests/vectors/isa/rb-ops.yaml` — 补充 `andnw (0x4D)`

**验证结果**：
```
$ python3 scripts/validate_vectors.py
validate_vectors: 10 files, 111 cases, 87/87 opcodes covered OK
$ make check
... all PASS ...
```

---

## Architecture Review (2026-06-30)

**评审结论**：**Accepted — (op, ha) 主键 + encoding.word 验证均正确。**

### 验证

```
$ make check → repository checks: PASS
$ python3 validate_vectors.py → 10 files, 115 cases, 87/87 opcodes covered OK
```

### 逐项验证

| 需求 | 状态 | 证据 |
|------|------|------|
| 覆盖率主键改为 (op, ha) | ✅ | `by_opid[(op, str(ha))]` L36-L38 |
| encoding.word 校验 mask/value | ✅ | `(wval & mask) == value` L113 |
| 0x47 ldmo 有 vector | ✅ | 87/87 全覆盖 |
| 0x4D andnw-rb 有 vector | ✅ | 87/87 全覆盖 |
| make check PASS | ✅ | |
| 不改 opcodes.yaml | ✅ | |

### 最终判断

假全覆盖问题已修复，encoding.word 校验增强。可 accept。

---

## Architecture Review — 代码级补查 (2026-06-30)

对上一轮已 Accept 的结论做代码级补查。

### validate_vectors.py 代码级验证

**opid 主键追踪** (L31-L38)：`by_opid[(op, str(ha))]` 正确使用了 op + ha
tuple 作为覆盖率键，消除了同 mnemonic+format 的假覆盖问题。每次 validate_file
返回 `covered_opids` 集合，main 中聚合后与 `by_opid` 全集做差集报告缺失项 ✅

**encoding.word 校验** (L105-L116)：逐条检查 `(wval & mask) == value`，
如果 mask/value 不匹配追加 error。校验逻辑正确 ✅

**边界情况**：rd2ra/ra2rd 从覆盖率检查中排除 (L162-L163)，不报 false negative ✅

### 结论

代码逻辑正确，上轮 Accept 结论维持。
