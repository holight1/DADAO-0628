# DL-022a: O-4 QFC 覆盖校验 + O-5 Lit 字节 Oracle + DL-011c Lit Spacer

**执行环境**：本地 DS · DADAO-0628

---

## 背景

`consistency-coverage-analysis.md §四 O-4/O-5` 识别了两条未覆盖的 lint 缺口：

- **O-4**：wiki SimRISC-00 QFC 表是 opcode 布局的权威来源，但从未与 `tools/opcodes.yaml` 做双向比对；若 DS 在 opcodes.yaml 中漏填或错填了某个 op/ha，当前 `make check` 无法发现
- **O-5**：`tests/lit/MC/Dadao/*.s` 中 `# OBJ:` 行手写了期望字节，但这些字节是否与 `tools/opcodes.yaml` 的 mask/value 公式一致，从未有独立验证（DL-011b 验收靠 Python 手算，没有常态化工具）
- **DL-011c**：lit OBJ 模式 `# OBJ: XX XX XX XX mnemonic` 在 bytes 和 mnemonic 之间只有单空格；实际 `llvm-objdump` 输出两空格+tab（`  \t`），FileCheck 恰好能子串匹配，但含义不明确；加 `{{.*}}` 显式说明中间内容任意

三者合并为一个任务，均属 lint/校验层，不改变核心数据。

---

## 目标

| 子目标 | 产物 | 挂入 |
|--------|------|------|
| O-4 | `scripts/check_qfc_coverage.py` | `make lint` |
| O-5 | `scripts/check_lit_bytes.py` | `make lint` |
| DL-011c | 13 lit 文件的 `# OBJ:` 行修改 | — |

---

## O-4: QFC 表 vs opcodes.yaml 双向比对

### 输入

- `~/DADAO-wiki/SimRISC-00-指令系统设计.md`（wiki 文件，绝对路径，可 hardcode 或从 `manifests/spec.lock.toml` `local_reference` 字段读取）
- `tools/opcodes.yaml`

### QFC 表结构（L85-L152）

wiki 文件有四个 markdown 表：

**① 主表**（L89-L106，16 行 × 8 列）

行头格式：`| RRRR-Rxxx |`  
列头格式：`| xxxx-xCCC |`

解码规则：
- bits[7:3] = int("RRRR-R".replace("-", ""), 2)（忽略末尾 "xxx"）
- bits[2:0] = int("CCC", 2)（忽略前缀 "xxxx-x"）
- op = (bits[7:3] << 3) | bits[2:0]

单元格内容：
- 空格 → reserved（UNDI）
- `MISC-Norm` / `MISC-RF` / `MISC-AMO` → 主表 op，详情见子表
- `{name}-{format}` 或 `{name}-{bank}-{format}` → 一条具体指令

**② MISC-Norm 子表**（L113-L121，8 行 × 8 列）

行头格式：`| RRR-xxx |`，列头：`| xxx-CCC |`
- ha[5:3] = int("RRR", 2)
- ha[2:0] = int("CCC", 2)
- ha = (ha[5:3] << 3) | ha[2:0]
- op = 0x10（固定）

**③ MISC-RF 子表**（L127-L136）：同结构，op = 0x50

**④ MISC-AMO 子表**（L142-L150）：同结构，op = 0x70

### 比对逻辑

1. 解析 QFC → 提取所有非空、非 MISC-header 单元格的 `(op, ha_or_None)` 集合 `qfc_opids`
2. 读 opcodes.yaml → 提取所有记录的 `(op, str(ha))` 集合 `yaml_opids`
3. 报告：
   - `qfc_opids - yaml_opids`：QFC 有但 opcodes.yaml 缺失
   - `yaml_opids - qfc_opids`：opcodes.yaml 有但 QFC 不含（需排除 rd2ra/ra2rd，它们在 QFC 内有单元格但已排除 M1 scope）
4. 数量汇总：`QFC_COUNT non-empty cells / yaml_COUNT records`
5. exit 0（lint 警告，不阻断 CI）

### Makefile 集成

```makefile
check-qfc:
    @$(PYTHON) scripts/check_qfc_coverage.py

lint: check-issues check-trans check-qfc check-lit-bytes
```

---

## O-5: Lit 字节 Oracle 独立校验

### 输入

- `tests/lit/MC/Dadao/*.s`（13 个有 OBJ 行的文件，排除 `triple-smoke.s`）
- `tools/opcodes.yaml`

### OBJ 行解析规则

从每个 .s 文件提取 `# OBJ:` 开头的行，格式：

```
# OBJ: AA BB CC DD{{.*}}mnemonic ...
# OBJ: AA BB CC DD mnemonic ...    ← 修改前格式（兼容两种）
```

- 字节字段：前 4 个空格分隔的两位十六进制（`[0-9a-f]{2}`）
- word = int("AABBCCDD", 16)
- 其余部分忽略（mnemonic 验证为 best-effort，因命名约定可能不同）

### 校验逻辑

对每个 word：

1. 遍历 opcodes.yaml 所有记录，找满足 `(word & mask) == value` 的记录
2. 若无匹配：输出 `WARN: {file}:{line}: word 0x{word:08X} matches no opcodes.yaml entry`
3. 若有匹配（可能多条，正常）：校验通过
4. 汇总：`check_lit_bytes: N OBJ patterns checked, K warnings`
5. 若有 WARN：exit 1；若全通过：exit 0

**注意**：word 无匹配是真正的错误（说明人工写了错误字节），应阻断 lint。

### Makefile 集成

```makefile
check-lit-bytes:
    @$(PYTHON) scripts/check_lit_bytes.py

lint: check-issues check-trans check-qfc check-lit-bytes
```

---

## DL-011c: Lit OBJ Spacer

修改 13 个 lit 文件中所有 `# OBJ:` 行，在 bytes（第 4 个十六进制字节）和 mnemonic 之间加 `{{.*}}`：

**修改前**：
```
# OBJ: 19 20 00 01 addi rd8, rd0, 1
```

**修改后**：
```
# OBJ: 19 20 00 01{{.*}}addi rd8, rd0, 1
```

规则：
- 匹配模式：`^# OBJ: ([0-9a-f]{2} ){4}(\S)`
- 在第 4 字节末尾空格处插入 `{{.*}}`：`XX XX XX XX{{.*}}mnemonic`
- `triple-smoke.s` 无 OBJ 行，跳过
- 修改后运行 `llvm-lit tests/lit/MC/Dadao/` 验证 14/14 PASS

---

## 约束

1. `check_qfc_coverage.py`：不修改任何 yaml 文件，只读+比对+报告
2. `check_lit_bytes.py`：不运行 LLVM 工具（纯 Python + yaml），oracle 独立于实现
3. DL-011c：仅改 `# OBJ:` 行，不改 `# ASM:` 行和 RUN 行
4. wiki 路径优先从 `manifests/spec.lock.toml` `local_reference` 字段读取；若该字段不存在则 hardcode `/home/holight/DADAO-wiki`
5. `make lint` 现有依赖（`check-issues check-trans`）保留；追加 `check-qfc check-lit-bytes`

---

## 验收步骤（DS 完成区填写）

```bash
# O-4 验收
python3 scripts/check_qfc_coverage.py
# 期望：无 MISSING 行（或仅 rd2ra/ra2rd 相关差异），数量一致

# O-5 验收
python3 scripts/check_lit_bytes.py
# 期望：N OBJ patterns checked, 0 warnings；exit 0

# DL-011c 验收
grep "OBJ:.*{{.*}}" tests/lit/MC/Dadao/*.s | wc -l
# 期望：所有 OBJ 行都已加 spacer（行数与修改前 OBJ 行总数一致）

.work/build/llvm/bin/llvm-lit tests/lit/MC/Dadao/ -v
# 期望：14/14 PASS

# Makefile 验收
make lint
# 期望：全部子检查通过，exit 0
```

---

## 参考指针

| 资源 | 用途 |
|------|------|
| `~/DADAO-wiki/SimRISC-00-指令系统设计.md` L85-L152 | QFC 表（4 个 markdown 表，主表+3子表）|
| `tools/opcodes.yaml` | oracle opid 集合 + mask/value |
| `tests/lit/MC/Dadao/*.s` | 13 个 lit 文件（OBJ 行来源）|
| `Makefile` lint target | 追加 check-qfc + check-lit-bytes |
| `consistency-coverage-analysis.md §四 O-4/O-5` | 背景与缺口描述 |
| `scripts/validate_vectors.py` `load_opcodes()` | opcodes.yaml 加载参考实现 |
