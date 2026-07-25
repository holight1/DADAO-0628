# 一致性与覆盖率分析

**版本**：0.2.0（2026-06-30，接受 §八 Review 意见后修订）  
**范围**：DADAO-0628 仓库，M1 Scope，wiki commit `13a414da`

---

## 一、全链路结构

```
DADAO-wiki (commit 13a414da)
    │  [wiki→spec]
    ▼
contracts/isa/spec.md          ← ISA 契约（人工翻译+引用）
    │  [spec→opcodes]
    ▼
tools/opcodes.yaml             ← 机器可读 opcode 表（oracle）
    │  [opcodes→vectors]          │  [opcodes→llvm]       [opcodes→qemu]
    ▼                             ▼                         ▼
tests/vectors/isa/*.yaml   LLVM patches (0001-0006)   QEMU patches (0001-0006)
    │  [vectors→execution]        │  [llvm→lit]
    ▼                             ▼
Phase 3 harness (QEMU)    tests/lit/MC/Dadao/*.s
```

另有一层当前分析未覆盖：**治理文档一致性**（ADR ↔ roadmap ↔ task ↔ 代码常量）。

---

## 二、现有机械检查清单

### `make check`（结构检查，不构建/运行）

| 脚本 | 覆盖层 | 检查内容 |
|------|--------|---------|
| `manifest_check.py` | 基础设施 | spec.lock.toml 格式、组件 hash |
| `check_wiki_drift.py` | wiki→spec | spec.md 含正确 wiki commit SHA（仅溯源） |
| `validate_encoding.py` | opcodes.yaml 内部 | mask/value 算术、字段不重叠、decode 无冲突、role/bank 合法性 |
| `validate_vectors.py` | opcodes→vectors | (op,ha) 87/87 覆盖、encoding.word mask/value 一致 |

**`make check` 不构建 QEMU/LLVM，不运行 Phase 3 harness，不跑 lit 测试。**  
"make check PASS"只能说明仓库结构检查通过，不代表实现正确性。

**现状（commit `9ade7fb`）**：make check PASS，200 cases，87/87 opcodes 覆盖。

### `make build-qemu` / `make build-mc`（独立构建）

### Phase 3 harness（独立运行，非 make check）

`tests/scripts/run_qemu_test.py` 目前是 **smoke test**，不是语义验证器：
- `emit_state_dumper()` 为空函数，无状态 dump 实现
- runner 不读取 `expected_state` / `expected_fault` 字段
- 测试后无条件认为 exit=0 为 PASS，不对 `expected_fault: ILLI` case 验证异常
- CLI 不以非零状态退出（CI 即使看到 FAIL 文本也可返回 0）

当前 harness 能力：raw binary 构建 + QEMU 进程启动是否 exit=0（进程存活测试）。

---

## 三、各层缺口分析

### 3.1 wiki → spec.md

**已覆盖**：`check_wiki_drift.py` 验证 spec.md 内 wiki commit SHA 与 spec.lock.toml 一致（仅溯源）。

**未覆盖**：

| 缺口 | 说明 | 风险 |
|------|------|------|
| **引用有效性** | spec.md 有 57 处 wiki 引用，格式多样（行号/节标题/范围/多文件/内嵌引文）；当前不验证引用对象是否存在 | 引用指向移动内容，架构师误判为"wiki 支持" |
| **未引用规范性断言** | spec.md 中 ILLI/UNDI/MALIGN/IALIGN 相关句子约 30 处，部分无 `[wiki §...]` 标注 | 架构师添加的规则若与 wiki 不符，无法发现 |
| **C-xx open 项** | `docs/wiki-questions.md` 当前 3 项未确认（C-27/SBZ fault/复位初值）；未纳入 make check | 依赖未确认语义的向量可能静默通过 |

### 3.2 wiki → opcodes.yaml（经 SimRISC-00 QFC 表）

**未覆盖**：

| 缺口 | 说明 |
|------|------|
| **QFC 表 vs opcodes.yaml** | SimRISC-00 §QFC 表是权威 opcode 布局，markdown 格式可解析；与 opcodes.yaml 未做双向比对 |

### 3.3 spec.md → opcodes.yaml

**未覆盖**：

| 缺口 | 说明 |
|------|------|
| **ILLI 条件一致性** | spec.md §2.5–§2.6 的 ILLI 触发条件未在 opcodes.yaml 中结构化，两者无交叉验证 |

### 3.4 opcodes.yaml → vectors

**已覆盖**：(op,ha) 87/87 + encoding.word mask/value。

**已知 validator 缺陷（待修 DL-017b）**：`validate_vectors.py` 在发现某 `(mnemonic, format)` 的向量时，将该组内*所有* `(op,ha)` identity 标为 covered——即 `ldo-rrii`（RD）和 `ldo-rb-rrii`（RB）的向量可互相顶替。87/87 当前数据恰好完整，但 validator 本身无法保证。

**未覆盖**：

| 缺口 | 说明 |
|------|------|
| **legality 向量密度** | spec §2.5 约 15 类 ILLI 条件；legality 向量共约 20 条，多数 opcode 的 ILLI 条件无向量 |
| **boundary 向量密度** | rd-logic/rd-wyde-block/rd-shift-extend/rd-cond-assign 的 boundary 向量为 0 |
| **C-27 overlap** | rd-cond-assign src=dst 重叠向量全部 deferred |

### 3.5 opcodes.yaml / vectors → QEMU patches

**当前实际能力**（harness smoke test）：raw encoding 向量打包为 flat binary，验证 QEMU 进程能 exit=0 启动并执行指令。

**不具备**：`expected_state` 寄存器值断言、`expected_fault` 异常断言、CI 失败返回非零。

**未覆盖**：

| 缺口 | 说明 |
|------|------|
| **harness 语义验证** | state dump 未实现；expected_state/expected_fault 未读取；向量里的期望值当前零验证 |
| **trans 函数存在性** | 87 条 M1 opcode 是否都有对应 QEMU trans 实现，无脚本验证 |

### 3.6 opcodes.yaml / vectors → LLVM patches

**已覆盖**：14 个 lit 文件覆盖全部指令格式，`-filetype=asm` round-trip + `llvm-objdump -d` 字节级验证（DL-011a 完成后）。

**未覆盖**：

| 缺口 | 说明 |
|------|------|
| **lit 期望字节 vs spec 公式** | `llvm-objdump -d` CHECK 字节手推；DL-010b 曾写错，靠 DS 纠正 |
| **lit DISASM 更新在 patch 外** | DL-011a lit 文件改动未纳入 0006 patch（P1.1 债，待 DL-011b）|

### 3.7 治理文档一致性（当前未覆盖）

已知内部矛盾（无机械检查）：

| 文件 | 矛盾 |
|------|------|
| `0003-testing-roadmap.md` | exit code 写 0x01/0x02/0x03，与 ADR-0004 的 0x82/0x81/0x83 冲突 |
| `0003-testing-roadmap.md` | 脚本名写 `build_qemu_binary.py`，实际文件为 `build_test_binary.py` |
| `0003-testing-roadmap.md` | 声称"逐字段 state dump"，harness 代码中为空函数 |
| `0003-testing-roadmap.md` | boundary/overlap "QEMU 收敛后补"与 ADR-0007 D4"不得推迟"矛盾 |

---

## 四、优化建议

全部机械检查，不依赖 LLM 判断：

### 紧急（阻断语义验证闭环）

#### O-0：Phase 3 harness 语义验证修复

完成 `emit_state_dumper()`（写 rd/rb/pc 寄存器组到固定地址），`run_qemu_test.py` 读取
dump 后与 `expected_state` 比对，`expected_fault` 与 QEMU exit code 比对；
CLI 在任一 case 失败时返回非零；0 case / SKIP 时拒绝（fail-closed）。  
**状态**：待下发 DL-021a。

### P0 — 纳入 `make check`

#### O-1：wiki 引用有效性检查

先定义 canonical citation grammar（`<file>#<heading-anchor>:<line-range>:<fingerprint>`），
对 `git show <locked-sha>:<path>` 验证内容（不读工作树）；
将现有 57 处非标准引用迁移到新格式后再入 CI。  
实现复杂度：**中**（citation grammar 定义 + 迁移 + 验证脚本）。

#### O-2：open issue 阻断

建立机器可读 issue registry（YAML，字段：`id/status/scope/blocks/resolved_by`）；
CI 阻断 `status=open && blocks⊇M1`，未知状态 fail-closed。  
比 markdown 删除线计数更可靠。  
实现复杂度：**低**。

#### O-3：QEMU trans 函数存在性（lint 级）

遍历 opcodes.yaml M1 opcode，grep QEMU patches 是否含 `trans_<mnemonic>`；
仅作为 lint 警告，不作为 P0 gate（存在性不等于语义正确，最终以 harness 为准）。  
实现复杂度：**低**。

### P1 — 纳入 `make lint`

#### O-4：QFC 表 vs opcodes.yaml 交叉验证

解析 `~/DADAO-wiki/SimRISC-00-指令系统设计.md` QFC 表格，与 opcodes.yaml 双向比对。  
实现复杂度：**中**（markdown 表格解析 + mnemonic 规范化）。

#### O-5：lit 期望字节验证

使用 `llvm-mc --show-encoding` 或 `llvm-readobj --hex-dump=.text` 获取对象字节，
与 opcodes.yaml 公式计算结果比对；不重新实现汇编器语法解析（避免第二套易漂移实现）。  
前提：DL-011a 交付 `llvm-objdump -d` CHECK 行后可实施。  
实现复杂度：**中**。

### P2 — 文档/流程层

#### O-6：未引用规范性断言扫描（one-shot）

grep spec.md ILLI/UNDI/MALIGN/IALIGN 行，过滤掉有 `[wiki §...]` 的行，输出清单供人工确认。  
不进 CI（有误报），适合 spec 版本更新时一次性运行。

#### O-7：ILLI 条件结构化（M2 计划）

opcodes.yaml 增加 `illi_conditions` 字段，`validate_vectors.py` 检查每条 ILLI 条件至少有
1 条 legality 向量。  
实现复杂度：**高**（87 条手填 + 脚本修改）。M1 阶段先靠 legality 向量人工补。

---

## 五、优先级汇总

| 编号 | 名称 | 复杂度 | 纳入目标 | 当前状态 |
|------|------|--------|---------|---------|
| O-0 | Phase 3 harness 语义验证 | 中 | `make test-qemu` | 待 DL-021a |
| O-1 | wiki 引用有效性 | 中 | `make check` | 待 citation 规范化 |
| O-2 | open issue 结构化 registry | 低 | `make check` | 未实现 |
| O-3 | QEMU trans 存在性 lint | 低 | `make lint` | 未实现 |
| O-4 | QFC 表 vs opcodes.yaml | 中 | `make lint` | 未实现 |
| O-5 | lit 期望字节验证 | 中 | `make lint` | 待 DL-011a |
| O-6 | 未引用规范性断言扫描 | 低 | 手动工具 | 未实现 |
| O-7 | illi_conditions 结构化 | 高 | `make check` | M2 计划 |

---

## 六、当前机械覆盖评级

| 层 | make check 覆盖 | 实际能力上限 | 主要缺口 |
|----|----------------|------------|---------|
| wiki → spec | ★★☆☆☆ | ★★☆☆☆ | 只验 SHA；引用内容不验 |
| wiki → opcodes | ★☆☆☆☆ | ★☆☆☆☆ | QFC 表未比对 |
| spec → opcodes | ★☆☆☆☆ | ★☆☆☆☆ | ILLI 条件未结构化 |
| opcodes → vectors | ★★★★☆ | ★★★☆☆ | 覆盖率统计有 identity 匹配 bug |
| vectors → QEMU | ★☆☆☆☆ | ★☆☆☆☆ | harness 仅 smoke；state/fault 零验证 |
| vectors → LLVM | ★★☆☆☆ | ★★★☆☆ | asm round-trip ✓；字节级验证待 DL-011a |

**总体**：opcodes.yaml 数据层结构完整性较好；执行层（QEMU harness）当前仅具备进程级 smoke，
语义断言闭环尚未建立。M1 最高优先：O-0（harness 修复）。

---

## 七、近期行动

1. **DL-021a**：harness 语义验证（state dump + expected 比对 + CLI exit code）
2. **DL-011b**：将 lit DISASM 更新纳入 LLVM 0006 或新 0007 patch
3. **O-2 + O-3**：打包一个任务（结构化 issue registry + trans 存在性 lint）
4. **O-4 + O-5**：DL-022a（QFC 比对 + lit 字节验证，DL-011a 完成后）
5. **O-7**：M2 阶段

---

*参考：`docs/wiki-questions.md`（C-xx 清单），`docs/adr/0007-testing-methodology.md`（TDD 规范），`docs/adr/0004-test-machine.md`（exit port 协议）*
