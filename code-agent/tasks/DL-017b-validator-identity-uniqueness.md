# DL-017b: validate_vectors.py 身份唯一性修复

**执行环境**：本地 DS · DADAO-0628

---

## 背景

`scripts/validate_vectors.py` 存在已知缺陷：在 `validate_file()` 的覆盖率标记逻辑（L136-L139）中，
当发现某个向量的 `(mnemonic, format)` 存在于 opcodes.yaml 时，
将该 `(mnemonic, format)` 组内**所有** `(op, ha)` identity 全部标为 covered：

```python
elif status == "active":
    for rec in opcodes_by_mnem_fmt[key]:   # 遍历整组
        opid = (rec["op"], str(rec.get("ha")))
        covered_opids.add(opid)            # 全组标为 covered ← BUG
```

**影响举例**：`ldo rrii` 在 opcodes.yaml 中有两条记录：
- op=0x33, ha=None（RD load）
- op=0x43, ha=None（RB load）

当有一条 `ldo rrii` RD 向量时，两条 opid 都被标为 covered，即使 RB 向量不存在。
当前 200 cases 数据恰好都有向量，所以 87/87 是真实的——但若去掉某条 RB 向量，validator 也不会发现。

---

## 目标

修复 `validate_file()`：只将**实际匹配 encoding.word 的那条 opcode 记录**标为 covered，
不允许同组的兄弟 opid 互相顶替。

---

## 修复规格

### 覆盖率标记逻辑重构

当前代码在两个地方各自独立处理：
1. mask/value 校验（L106-L119）：找到匹配的 `rec`，验证 word 合法性
2. 覆盖率标记（L136-L139）：将整组 opid 全部标为 covered

修复后，将两者合并为一次遍历，只标记匹配的 `rec`：

```
新逻辑（替换 L106-L139）：

if word and mnem != "?" and fmt != "?":
    recs = opcodes_by_mnem_fmt.get((mnem, fmt), [])
    if recs:
        wval = int(word, 16)
        matched_rec = None
        for rec in recs:
            mask_val = int(rec["mask"], 16) if isinstance(rec["mask"], str) else rec["mask"]
            value_val = int(rec["value"], 16) if isinstance(rec["value"], str) else rec["value"]
            if (wval & mask_val) == value_val:
                matched_rec = rec
                break
        if matched_rec is None:
            rec = recs[0]
            errors.append(
                f"{tag}: encoding.word {word} does not match "
                f"mask={rec['mask']} value={rec['value']}")
        elif status == "active":
            opid = (matched_rec["op"], str(matched_rec.get("ha")))
            covered_opids.add(opid)   # 只标记匹配的那条

elif mnem != "?" and fmt != "?" and status == "active":
    # word 为空时的 mnemonic+format 存在性检查保持原样（不做覆盖率标记）
    key = (mnem, fmt)
    if key not in opcodes_by_mnem_fmt:
        errors.append(f"{tag}: unknown mnemonic+format: {mnem}({fmt})")
```

**注意**：原有的 L130-L135（mnemonic+format 存在性检查，无 word 时）逻辑不变。
修复后 L136-L139 的整组 covered 标记删除，覆盖率现在仅由 mask/value 匹配驱动。

### 同步 mnemonic+format 存在性检查

原代码 L130-L139：
```python
if mnem != "?" and fmt != "?":
    key = (mnem, fmt)
    if key not in opcodes_by_mnem_fmt:
        errors.append(...)
    elif status == "active":
        for rec in opcodes_by_mnem_fmt[key]:   # ← 删除这段
            opid = (rec["op"], str(rec.get("ha")))
            covered_opids.add(opid)
```

修复后，这段整组标记完全删除，覆盖率标记移入上方的 mask/value 检查分支。

---

## 验收步骤（DS 完成区填写）

```bash
# 1. make check PASS（覆盖率不变，87/87）
make check
# 期望：validate_vectors: 10 files, 200 cases, 87/87 opcodes covered OK

# 2. 验证修复有效：手动移除一条 RB 向量后，validator 应该报告 COVERAGE MISSING
#    例如：暂时注释掉 rb-ops.yaml 中的 `ldo rrii class: encoding` 向量
#    然后运行
python3 scripts/validate_vectors.py
# 期望：显示 ldo (op=0x43 ha=None) COVERAGE MISSING

# 3. 恢复向量
# 期望：make check 再次 PASS

# 4. 对照新旧代码：确认 covered_opids 的填写只发生在 mask/value 匹配分支
grep -n "covered_opids.add" scripts/validate_vectors.py
# 期望：只有 1 处（匹配分支内），不再有整组遍历
```

---

## 参考指针

| 资源 | 用途 |
|------|------|
| `scripts/validate_vectors.py` L106-L139 | 修改目标（当前实现） |
| `tools/opcodes.yaml` | (mnemonic,format) 分组与 mask/value 来源 |
| `tests/vectors/isa/rb-ops.yaml` | 有 ldo rrii RD 和 RB 两种 opid 的 YAML，适合验证修复 |
| `consistency-coverage-analysis.md §三.4` | 已知 validator 缺陷描述 |
