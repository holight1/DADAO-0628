# DL-020a: encoding class 向量补全（Phase 3 harness 输入）

**执行环境**：本地 DS · DADAO-0628

---

## 背景

`tests/vectors/isa/` 共 10 个 YAML 文件，115 cases。
当前 `class: encoding` 向量极少（仅 `misc.yaml` 2 条），其他 9 个文件全部为 0。

`encoding` class 的语义：验证该 32-bit instruction word 能被 QEMU 解码并无异常执行
（exit=0，无 ILLI/MALIGN/UNDI）；不检查执行后寄存器状态（`expected_state: null`）。

Phase 3 harness（`tests/scripts/run_qemu_test.py`）读取所有 `class: encoding` 向量，
打包成 flat binary 喂给 QEMU，以 exit code 断言无 fault。
目前主体指令集没有 encoding 向量可跑，harness 几乎空转。

---

## 目标

为每个 `(op, ha)` opcode 至少补充 **1 条 `class: encoding` 向量**，
使所有 M1 指令（rd2ra/ra2rd 除外）都有至少 1 条 encoding 向量在对应 YAML 文件中。

---

## 约束与规则

### 1. encoding vector 格式

```yaml
- mnemonic: <mnemonic>
  format: <format>
  class: encoding
  encoding:
    word: "<0x????????>"
  input_state: {}
  expected_state: null
  expected_fault: null
  status: active
  wiki_cite: "spec.md §<章节>"
  notes: "<可选说明>"
```

`input_state: {}` — 空 map，不预置寄存器（QEMU 初始状态全 0）  
`expected_state: null` — 不检查执行后状态  
`expected_fault: null` — 无异常期望

### 2. encoding.word 计算规则

公式（来源：`contracts/isa/spec.md §2.2`）：
```
word = (op << 24) | (ha << 18) | (hb << 12) | (hc << 6) | hd
```
- `op`、`ha` 从 `tools/opcodes.yaml` 的对应 opcode 记录读取
- 操作数字段（hb/hc/hd）填入最小合法值：
  - **目标寄存器**（dest rd/rb）：若 rd0/rb0 为目标会触发 ILLI（见规则 3），用 1；否则用 0
  - **源寄存器**：用 0（rd0/rb0 作为源合法）
  - **立即数**：用 0
  - **wyde-pos**（rwii 格式）：用 0（W0）
  - **count 字段**（rrri 格式，load/store multi）：用 1（count=0 语义未定义）

### 3. 哪些 opcode 的目标 rd0/rb0 触发 ILLI

按照 spec §2.5，以下目标操作数为 0 时触发 ILLI，encoding vector 必须用 ha=1 或 hb=1：

| 规则 | 受影响指令 |
|------|----------|
| rd0 as DEST → ILLI | addi, add, sub, muls, mulu, divs, divu (rrrr/rrii)；shlu/shrs/shru/exts/extz；cmps/cmpu (rrii)；csn/csz/csp/cseq/csne |
| rb0 as DEST → ILLI | addi-rb, add-rb, sub-rb, rd2rb, rb2rb, rela, orw-rb, andnw-rb, setzw-rb |
| rd0 as DEST 合法 | brz/brnz/brn/brnn/brp/brnp/breq/brne（分支，目标是 PC）；jump/call/ret；store 类（stb/stw/stt/sto/stm*）；rd2rd；cmp-rb |

### 4. 向量写入位置

| 文件 | 写入 opcode |
|------|-----------|
| `rd-arith.yaml` | addi, add, sub, muls, mulu, divs, divu |
| `rd-compare.yaml` | cmps, cmpu, cmp（orrr 格式） |
| `rd-cond-assign.yaml` | csn, csz, csp, cseq, csne |
| `rd-logic.yaml` | and, orr, xor, xnor |
| `rd-shift-extend.yaml` | shlu, shrs, shru, exts, extz（rrii + orrr 各 1 条） |
| `rd-wyde-block.yaml` | orw, andnw, setzw, setow（rwii 格式） |
| `rd-load-store.yaml` | ldbs, ldbu, ldws, ldwu, ldts, ldtu, ldo；stb, stw, stt, sto；ldmbs, ldmbu, ldmws, ldmwu, ldmts, ldmtu, ldmo；stmb, stmw, stmt, stmo |
| `rb-ops.yaml` | rela, addi-rb, orw-rb, andnw-rb, setzw-rb, sto-rb, rd2rb, rb2rd, rb2rb, add-rb, sub-rb, cmp-rb |
| `control-flow.yaml` | brz, brnz, brn, brnn, brp, brnp, breq, brne；jump（iiii）, jump（rrii）, call（iiii）, call（rrii）, ret |

`misc.yaml`（已有 2 条 encoding vector）：检查是否覆盖所有 MISC-Norm opcode，若有缺漏补全。

### 5. 特殊处理

- **store 类**（stb/stw/stt/sto/stm*）：encoding vector 写出到地址 0，QEMU flat-map 覆盖整个地址空间，写 0x000000 合法；`expected_fault: null`
- **ldmo/stmo multi**：count 字段填 1（仅搬一次），避免越界；地址用 0
- **jump/call iiii**：target imm 用 0（跳回地址附近，flat-map 下不会 fault）
- **ret**：ra[63] 初始为 0，PC=0 在 flat-map 内合法；`input_state: {}` 即可
- **rd2rb/rb2rd**：ha/hb 用有效但不触发 ILLI 的值；rd2rb hb=1（rb1 as dest）

---

## 交付物

修改以下文件（追加 encoding class 向量，不删改现有向量）：
- `tests/vectors/isa/rd-arith.yaml`
- `tests/vectors/isa/rd-compare.yaml`
- `tests/vectors/isa/rd-cond-assign.yaml`
- `tests/vectors/isa/rd-logic.yaml`
- `tests/vectors/isa/rd-shift-extend.yaml`
- `tests/vectors/isa/rd-wyde-block.yaml`
- `tests/vectors/isa/rd-load-store.yaml`
- `tests/vectors/isa/rb-ops.yaml`
- `tests/vectors/isa/control-flow.yaml`

---

## 验收步骤（DS 完成区填写）

```bash
python3 scripts/validate_vectors.py
# 期望：0 errors，87/87 covered OK，cases 数量 ≥ 160（新增 ≥ 45 条）

# 验证 encoding class 向量数量
grep -l "class: encoding" tests/vectors/isa/*.yaml | wc -l
# 期望：≥ 9 个文件有 encoding 向量

grep -c "class: encoding" tests/vectors/isa/*.yaml
# 期望：每个文件 ≥ 1（misc.yaml ≥ 2）

# Phase 3 harness 冒烟（需已 build-qemu）
python3 tests/scripts/run_qemu_test.py tests/vectors/isa/rd-arith.yaml
# 期望：encoding 类 case 全 PASS（exit=0）

make check
# 期望：PASS
```

---

## 参考指针

| 资源 | 用途 |
|------|------|
| `tools/opcodes.yaml` | op/ha/mask/value（encoding.word 主键来源） |
| `contracts/isa/spec.md §2.2` | encoding.word 计算公式 |
| `contracts/isa/spec.md §2.5` | ILLI 条件（rd0/rb0 dest 规则） |
| `tests/vectors/schema.md` | encoding class 字段规范 |
| `tests/vectors/isa/misc.yaml` | encoding class 向量格式参考 |
| `tests/scripts/run_qemu_test.py` | Phase 3 harness（encoding class 消费者） |

## 完成区

**状态**：已完成（待 Codex Review）
**修改文件**：9 个 `tests/vectors/isa/*.yaml` — 新增 85 条 encoding class 向量

**验证**：
```
$ python3 scripts/validate_vectors.py
... 87/87 opcodes covered OK
$ make check
... all PASS ...
```

---

## Architecture Review — 代码级 (2026-06-30)

**评审结论**:**Needs Revision — 12 条 rrri encoding 向量 immu6=0 违反 spec。**

### 数据验证

87 条 encoding class 向量，200 cases 总量，`make check` + mask/value 校验全 PASS。
但逐字检查发现实质性数据错误。

### P0 — 必须修正

#### P0.1 全部 rrri encoding 向量 immu6=0 ★

| 文件 | 指令 | word | 错误 |
|------|------|------|------|
| rd-load-store.yaml | ldmbs, ldmbu, ldmws, ldmwu, ldmts, ldmtu, ldmo | `0x34..37` 各 1 条 | `immu6=0` |
| rd-load-store.yaml | stmb, stmw, stmt, stmo | `0x3C..3F` 各 1 条 | `immu6=0` |
| rb-ops.yaml | ldmo (op=0x47) | `0x47040000` | `immu6=0` |
| rb-ops.yaml | stmo (op=0x4F) | `0x4F000000` | `immu6=0` |

spec.md §2.6.3 明确规定 `immu6 = 0 → ILLI`。任务 spec L62 明确要求
"count 字段用 1"。但全部 12 条 rrri encoding 向量将 immu6 填为 0。

**影响**：这些 encoding 向量在 QEMU harness 下将触发 ILLI（exit ≠0），
无法通过 encoding class 验证。

**修正**：将所有 rrri encoding 向量的 `hd`（immu6）字段从 0 改为 1。
即 word += 1（或 word |= 1），使 immu6 = 1。

### 其他验证（通过）

| 检查项 | 状态 |
|--------|------|
| mask/value 匹配（87/87） | ✅ 全部通过 |
| rd0 dest ILLI 避免（addi/add/ldbs 等） | ✅ ha=1 |
| dual-dest ILLI 避免（add/sub/mul/div） | ✅ ha=1, hb=2 |
| rrrr csn/csz/csp: dest=hb=1 | ✅ |
| branch rd0 合法（brz ha=0） | ✅ |
| store 源 rd0 合法（stb/stw ha=0） | ✅ |
| and/orr/xnor orrr dest=hb=1 | ✅ |

### 复审通过条件

- [ ] 12 条 rrri encoding 向量的 immu6 从 0 改为 1
- [ ] `make check` PASS（105 cases → 不变）
