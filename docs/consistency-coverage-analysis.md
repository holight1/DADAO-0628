# 一致性与覆盖率分析

**版本**：0.1.0（2026-06-30）  
**范围**：DADAO-0628 仓库，M1 Scope，wiki commit `13a414da`

---

## 一、全链路结构

```
DADAO-wiki (commit 13a414da)
    │  [wiki→spec]
    ▼
contracts/isa/spec.md          ← ISA 契约（人工翻译）
    │  [spec→opcodes]
    ▼
tools/opcodes.yaml             ← 机器可读 opcode 表（oracle）
    │  [opcodes→vectors]          │  [opcodes→llvm]       [opcodes→qemu]
    ▼                             ▼                         ▼
tests/vectors/isa/*.yaml   LLVM patches (0001-0005)   QEMU patches (0001-0006)
    │  [vectors→execution]        │  [llvm→lit]
    ▼                             ▼
Phase 3 harness (QEMU)    tests/lit/MC/Dadao/*.s
```

---

## 二、现有机械检查清单（`make check`）

| 脚本 | 覆盖层 | 检查内容 |
|------|--------|---------|
| `manifest_check.py` | 基础设施 | spec.lock.toml 格式、组件 hash |
| `check_wiki_drift.py` | wiki→spec | spec.md 含正确 wiki commit SHA（溯源） |
| `validate_encoding.py` | opcodes.yaml 内部 | mask/value 算术、字段不重叠、decode 无冲突、role/bank 合法性 |
| `validate_vectors.py` | opcodes→vectors | (op,ha) 87/87 覆盖、encoding.word 与 mask/value 一致 |
| Phase 3 harness | vectors→QEMU | semantic 向量 → QEMU 执行 → exit code 断言 |

**现状（2026-06-30）**：`make check` PASS，200 cases，87/87 opcodes 覆盖。

---

## 三、各层缺口分析

### 3.1 wiki → spec.md

**已覆盖**：`check_wiki_drift.py` 验证 spec.md 内 wiki commit SHA 与 spec.lock.toml 一致。

**未覆盖**：

| 缺口 | 说明 | 风险 |
|------|------|------|
| **引用行号有效性** | spec.md 有 42 处 `[wiki §SimRISC-01 L37]` 等行号引用；wiki 更新后行号可能偏移，但当前不检查行是否存在 | 引用指向已移动的内容，架构师误判为"wiki 支持" |
| **节标题引用有效性** | 部分引用为 `[wiki §SimRISC-02 §地址类指令]`；wiki 重命名节时引用失效 | 同上 |
| **未引用规范性断言** | spec.md 中 ILLI/UNDI/MALIGN/IALIGN 相关句子约 30 处，部分无 `[wiki §...]` 标注（如 §2.6 内的多处 ILLI 规则）| 架构师自行添加的规则若与 wiki 不符，无法发现 |
| **C-xx open 项** | `docs/wiki-questions.md` 当前 3 项未确认（C-27 snapshot、SBZ fault 类型、复位初值）；未纳入 make check | 依赖未确认语义的测试向量可能静默通过 |

### 3.2 wiki → opcodes.yaml（间接，经 SimRISC-00 QFC 表）

**未覆盖**：

| 缺口 | 说明 |
|------|------|
| **QFC 表 vs opcodes.yaml** | SimRISC-00 §SimRISC QFC 是权威 opcode 布局表（markdown 格式，机器可解析）；opcodes.yaml 是从中衍生的结构化数据；两者未做交叉校验 |

QFC 表列出了全部 `(op_group, col)` → `mnemonic-format` 映射。opcodes.yaml 给出 `op/ha/mask/value`。
理论上可机械比对：QFC 表每个非空单元格 → opcodes.yaml 中必须存在对应 `(op, ha, mnemonic, format)` 记录；
opcodes.yaml 中每条 M1 记录 → QFC 表中必须有对应单元格。

### 3.3 spec.md → opcodes.yaml

**未覆盖**：

| 缺口 | 说明 |
|------|------|
| **ILLI 条件一致性** | spec.md §2.5–§2.6 列出了各 opcode 的 ILLI 触发条件（rd0 dest、immu6=0、超界等）；opcodes.yaml 中 `fields[].role` 记录了操作数类型，但未编码 ILLI 条件；两者无交叉验证 |

### 3.4 opcodes.yaml → vectors

**已覆盖**：(op,ha) 覆盖 + encoding.word mask/value。

**未覆盖**：

| 缺口 | 说明 |
|------|------|
| **legality 向量密度** | spec.md §2.5 列出的 ILLI 条件约 15 类；当前 legality 向量共约 20 条，平均每 opcode < 0.25 条；多数 opcode 的 ILLI 条件无 legality 向量 |
| **boundary 向量密度** | rd-logic/rd-wyde-block/rd-shift-extend/rd-cond-assign 的 boundary 向量为 0 |
| **C-27 overlap** | rd-cond-assign 的 src=dst 重叠 overlap 向量全部 deferred |

### 3.5 opcodes.yaml / vectors → QEMU patches

**已覆盖**：Phase 3 harness 执行 semantic 向量，exit code 断言。

**未覆盖**：

| 缺口 | 说明 |
|------|------|
| **trans 函数存在性** | opcodes.yaml 87 条 M1 opcode；QEMU patches 中是否每条都有对应 `trans_<mnemonic>` 尚无脚本验证——某 opcode 未实现时只有 ILLI（UNDI）出现，若无 legality 向量则静默漏过 |

### 3.6 opcodes.yaml / vectors → LLVM patches

**未覆盖**：

| 缺口 | 说明 |
|------|------|
| **lit 期望字节 vs spec 公式** | lit 测试 CHECK-OBJ 行字节手推，无脚本验证；DL-010b 中架构师曾写错（`19 40 00 01` → 实际应为 `19 20 00 01`），靠 DS 纠正 |
| **llvm-objdump -d 验证** | 14 个 lit 仅测 `-filetype=asm` round-trip，未做字节级 disassembly 验证（N1 债，待 DL-011a）|

---

## 四、优化建议

按优先级排列，全部机械检查，不依赖 LLM 判断：

### P0 — 纳入 `make check`（高价值，低复杂度）

#### O-1：wiki 引用有效性检查（扩展 `check_wiki_drift.py`）

解析 spec.md 所有 `[wiki §<文件> L<N>]` 格式引用，在本地 `~/DADAO-wiki/` 中验证：
- 行号引用：该文件存在且行数 ≥ N
- 节标题引用：该文件存在且包含对应 `## <节名>` 标题

实现复杂度：**低**（正则 + wc -l + grep）。  
价值：wiki 更新后引用漂移立即报错，不依赖人工核查。

#### O-2：C-xx open 项阻断（新脚本 `check_open_questions.py`）

解析 `docs/wiki-questions.md`，统计未 struck-through 的 `### N.` 条目数；
若 > 0 则 `make check` 警告（或对 M1 release tag 阻断）。

实现复杂度：**极低**（5 行 grep）。  
价值：让 open 语义问题在 CI 可见，不会被遗忘。

#### O-3：QEMU trans 函数覆盖（新脚本 `check_qemu_coverage.py`）

遍历 `tools/opcodes.yaml` 中所有 M1 active opcode；对每条 mnemonic，grep 所有
`components/qemu/patches/*.patch` 中是否含 `trans_<mnemonic>`（下划线规范化）。
缺失即报错。

实现复杂度：**低**（YAML load + grep）。  
价值：防止 opcode 在 vectors 有覆盖但 QEMU 未实现的静默漏洞。

### P1 — 纳入 `make lint`（中价值，中复杂度）

#### O-4：QFC 表 vs opcodes.yaml 交叉验证（新脚本 `check_qfc_opcodes.py`）

解析 `~/DADAO-wiki/SimRISC-00-指令系统设计.md` 的 QFC markdown 表格，
提取每个非空单元格的 `mnemonic-format`，与 opcodes.yaml 做双向比对：
- QFC 表有但 opcodes.yaml 无 → 报错
- opcodes.yaml 有但 QFC 表无（且非 MISC-Norm 子表扩展）→ 报错

实现复杂度：**中**（markdown 表格解析 + mnemonic 规范化）。  
价值：直接校验 wiki 权威 opcode 布局与代码 oracle 的一致性。

#### O-5：lit 期望字节验证（新脚本 `verify_lit_bytes.py`）

解析 `tests/lit/MC/Dadao/*.s` 中的汇编行和对应 `# CHECK-OBJ: <bytes>` 行；
从操作数值 + opcodes.yaml 公式（`op<<24 | ha<<18 | hb<<12 | hc<<6 | hd`）计算期望字节；
与 CHECK 行比对，不一致则报错。

实现复杂度：**中**（汇编语法解析 + opcodes.yaml 字段映射）。  
价值：防御 DL-010b 同类错误（手推期望字节写错）。  
前提：DL-011a（disassembler）完成后 lit 才有 CHECK-OBJ 行。

### P2 — 文档/流程层（不进 make check）

#### O-6：未引用规范性断言扫描（one-shot 审计工具）

grep spec.md 中含 `ILLI`/`UNDI`/`MALIGN`/`IALIGN` 的行，过滤掉有 `[wiki §...]` 的行，
输出"未引用规范性断言"清单，人工确认是否需要补 wiki 引用。

不建议进 CI（有一定误报率），适合 spec 版本更新时一次性运行。

#### O-7：ILLI 条件结构化（opcodes.yaml 字段扩展）

在 opcodes.yaml 每条 opcode 记录中增加 `illi_conditions` 字段（字符串列表），
与 spec.md §2.5–§2.6 的 ILLI 规则对应。然后：
- `validate_encoding.py` 可验证 `illi_conditions` 字段格式
- `validate_vectors.py` 可检查每条 `illi_conditions` 至少有 1 条 legality 向量覆盖

实现复杂度：**高**（需手工填写 87 条 illi_conditions，并修改 validate 脚本）。  
价值：关闭 legality 向量密度缺口，使 ILLI 覆盖率可机械统计。  
建议：M2 阶段再做，M1 先靠 legality 向量人工补充。

---

## 五、优先级汇总

| 编号 | 名称 | 复杂度 | 纳入目标 | 当前状态 |
|------|------|--------|---------|---------|
| O-1 | wiki 引用行号/节标题有效性 | 低 | `make check` | 未实现 |
| O-2 | C-xx open 项阻断 | 极低 | `make check` | 未实现 |
| O-3 | QEMU trans 函数覆盖 | 低 | `make check` | 未实现 |
| O-4 | QFC 表 vs opcodes.yaml | 中 | `make lint` | 未实现 |
| O-5 | lit 期望字节验证 | 中 | `make lint` | 未实现（待 DL-011a）|
| O-6 | 未引用规范性断言扫描 | 低 | 手动工具 | 未实现 |
| O-7 | illi_conditions 结构化 | 高 | `make check` | M2 计划 |

---

## 六、当前 `make check` 完整性评级

| 层 | 机械覆盖程度 | 主要缺口 |
|----|------------|---------|
| wiki → spec | ★★☆☆☆ | 只验证 SHA，不验证引用内容 |
| wiki → opcodes | ★☆☆☆☆ | QFC 表未做比对 |
| spec → opcodes | ★☆☆☆☆ | ILLI 条件未结构化 |
| opcodes → vectors | ★★★★☆ | (op,ha) + encoding.word 覆盖；legality/boundary 密度偏低 |
| vectors → QEMU | ★★★☆☆ | Phase 3 harness 执行正确；trans 存在性未验 |
| vectors → LLVM | ★★☆☆☆ | lit 有 asm round-trip；无字节级验证（待 DL-011a）|

**总体**：核心数据层（opcodes.yaml）和执行层（Phase 3 harness）覆盖较好；
wiki→spec→opcodes 上游层和 LLVM 字节层是主要机械检查盲区。

---

## 七、近期行动建议

按不阻断当前 DL-011a/DL-020a 进度的前提：

1. **现在**：O-2（C-xx 计数，5 行脚本）+ O-3（QEMU trans 覆盖，20 行脚本）可在 1 个任务内完成
2. **DL-011a 完成后**：实现 O-5（verify_lit_bytes.py），利用新增的 CHECK-OBJ 行
3. **M1 milestone 前**：O-1（wiki 引用验证）+ O-4（QFC 比对）打包一个 DL-022a
4. **M2 计划**：O-7（illi_conditions 结构化）

---

*参考：`docs/wiki-questions.md`（C-xx open 项），`docs/adr/0007-testing-methodology.md`（TDD 规范）*
