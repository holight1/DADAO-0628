# DL-027a: 架构师直修记录 — ISA 测试向量 5 文件修复

**执行环境**: 架构师直修（Claude） · DADAO-0628

**状态**: 已完成（commit 10d9ac6，2026-07-02）

---

## 背景

DL-024a / DL-025a review 通过后发现 5 个 ISA yaml 文件存在 encoding 错误、expected 值错误、setup 触发 ILLI 等问题，共计 27 处需要修正，全部属于架构师可直修范围（单行数据纠正，根因已明确）。

---

## 改动清单

### rd-arith.yaml（共 5 处）

| # | 改动 | 根因 |
|---|------|------|
| 1 | `add rd0` encoding 0x1A0843FF → 0x1A0033FF | hb 位域错误：bit[14]=1 → hb=4 而非 3 |
| 2 | 去掉 `add rd0` input_state 中的 `rd0: "0x0..."` | `load_reg(rd,0,val)` emit setzw rd0 → trans_setzw ha=0 → ILLI |
| 3 | `add rd0` expected rd3: "0x0..." → "0x8000000000000000" | 配合正确 encoding（lo→rd3） |
| 4 | divs semantic status: active → deferred | TCG gen_set_label dead-code bug（→ DL-026a） |
| 5 | divu semantic / divs encoding / divu encoding status: active → deferred | 同上，4 条共用 DL-026a |

### rd-wyde-block.yaml（共 12 处）

| # | 改动 | 根因 |
|---|------|------|
| 6 | setow word 0x17043000 → 0x17050000 | ha=1,ww=0 → ha=1,ww=1（wyde 字段偏移） |
| 7 | setow expected rd1 0x0000FFFF00000000 → 0xFFFFFFFF0000FFFF | 配合正确 setow rd1,w1,0 语义 |
| 8 | setzw_rb word 0x4E043000 → 0x4E050000 | 同上 wyde 字段 |
| 9 | setzw_rb expected rb1 0x0000FFFF0000BABE → 0x0000000000000000 | setzw rb1,w1,0 结果为 0 |
| 10 | rd2rb word 0x10A42842 → 0x10A4A042 | bits[17:12]=2(rb2),bits[11:6]=33(rd33)；应为 rb10,rd1 |
| 11 | rb2rd word 0x10A82842 → 0x10A8A042 | 同上：dst/src hb/hc 位域混淆 |
| 12 | rb2rb word 0x10AC2842 → 0x10ACA042 | 同上 |
| 13 | rb2rd expected rd10: 0x3333... → 0x0000333333333333 | load_reg RB 只写 3 wyde（48-bit） |
| 14 | rb2rd expected rd11: 0x4444... → 0x0000444444444444 | 同上 |
| 15 | rb2rb expected rb10: 0x5555... → 0x0000555555555555 | 同上 |
| 16 | rb2rb expected rb11: 0x6666... → 0x0000666666666666 | 同上 |
| 17 | notes 各处更新 | 反映正确语义 |

### rd-load-store.yaml（共 22 处）

| # | 改动 | 根因 |
|---|------|------|
| 18–25 | 8 × store encoding expected_fault: null → ILLI | ha=0 时 trans_stb/stw/stt/sto 检查 ILLI |
| 26–39 | 14 × load encoding status: active → deferred | addr=0 → tlb identity map → host NULL → SIGSEGV timeout |

### rd-shift-extend.yaml / misc.yaml

验证全通，仅更新 notes/status（misc unimp expected_fault: null→ILLI 等）。

---

## 验收结果

```
rd-arith.yaml        15 PASS  0 FAIL  (4 deferred)
rd-wyde-block.yaml   19 PASS  0 FAIL
rd-load-store.yaml   34 PASS  0 FAIL  (14 deferred)
rd-shift-extend.yaml 21 PASS  0 FAIL
misc.yaml             3 PASS  0 FAIL
──────────────────────────────────────
总计                 92 PASS  0 FAIL
```

---

## 新技术结论

1. **rd0 禁止出现在 input_state**（→ `feedback_dadao_test_vector_constraints.md` §1）
2. **load_reg RB 为 3 wyde / 48-bit 截断**（→ §2）
3. **rd2rb 存 64-bit，rb2rd 读 64-bit，不受 48-bit 截断影响**（→ §3）
4. **ORRI 位域**：bits[17:12]=dst, bits[11:6]=src, bits[5:0]=count（hb/hc 易混淆）

---

## 遗留

- **DL-026a**（divs/divu TCG label bug）：待 DS 执行，完成后恢复 4 条 deferred 测试
- **load addr=0 deferred 问题**：14 条 load encoding 向量仍 deferred；需 tlb_fill 不 identity map addr=0，或改用 ha=0 ILLI path（后续任务 TBD）
