# DL-004b: Spec Freeze（规格冻结动作）

**状态**：已完成（待 Codex Review）
**执行环境**：本地 DS · DADAO-0628

---

## 目标

执行 Phase 0.5C 规格冻结动作：
1. 将 `manifests/spec.lock.toml` 的状态从 `candidate` 改为 `frozen`
2. 新建 `docs/impact-matrix.md`，记录 wiki/合约章节与下游 Phase 1+ 实现的依赖映射
3. 新建 `scripts/check_wiki_drift.py`，验证所有合约文件中引用的 Wiki SHA 与
   `spec.lock.toml` 记录的 commit 一致；并在 `Makefile` 的 `check` 目标中调用它

---

## 交付物

### 1. `manifests/spec.lock.toml`

唯一改动：将

```toml
status = "candidate"
```

改为

```toml
status = "frozen"
```

其他字段（commit、foundation_included 等）不变。

---

### 2. `docs/impact-matrix.md`

格式：三列 Markdown 表格，列名为 `规格来源 | 依赖此节的合约/文件 | Phase 1+ 实现目标`。

至少覆盖以下行（DS 可在此基础上追加，不得删减）：

| 规格来源 | 依赖此节的合约/文件 | Phase 1+ 实现目标 |
|---------|-------------------|-----------------|
| ISA §4（RB bank rules）| `contracts/isa/spec.md §4` | LLVM MC register allocation |
| ISA §5（instruction encoding）| `contracts/isa/spec.md §5–§9` | LLVM MC code emission |
| ABI §3（register roles）| `contracts/abi/spec.md §3` | LLVM calling convention |
| ABI §5（stack frame）| `contracts/abi/spec.md §5` | LLVM prologue/epilogue |
| ELF §1（ELF header fields）| `contracts/elf/spec.md §1` | LLVM MC ELF emitter |
| ELF §2（relocation types）| `contracts/elf/spec.md §2` | LLVM MC relocations |
| ADR-0004 D1（test machine map）| `docs/adr/0004-test-machine.md §D1` | QEMU machine model |
| ADR-0004 D6（ROM trampoline）| `docs/adr/0004-test-machine.md §D6` | ROM bios.bin image |

文件头需注明冻结日期和 spec.lock.toml commit 引用。

---

### 3. `scripts/check_wiki_drift.py`

**功能**：扫描所有 `contracts/*/spec.md` 文件，提取 `Source` 行中的 Wiki commit SHA，
与 `manifests/spec.lock.toml` 中的 `commit` 字段比对；若有不一致则以错误退出。

**行为规则**：
- 只检查包含 `**Source**: Wiki commit` 的合约文件（ELF 合约引用 ADR 而非 Wiki，跳过）
- SHA 提取 pattern：`**Source**: Wiki commit \`<40-char-sha>\``
- 若某合约文件的 SHA ≠ `spec.lock.toml commit`，输出 `ERROR: <file>: SHA <x> != locked <y>` 并返回非零
- 若所有合约一致（或无 Wiki-sourced 合约），输出 `wiki drift check: PASS` 并返回 0
- 脚本风格参考 `scripts/manifest_check.py`（同一 Python 版本，pathlib + tomllib）

---

### 4. `Makefile`（追加一条依赖）

在 `check` 目标下追加 `check-wiki-drift`：

```makefile
check: manifest-check validate-encoding validate-vectors check-wiki-drift
	@$(PYTHON) -m compileall -q scripts
	@echo "repository checks: PASS"

check-wiki-drift:
	@$(PYTHON) scripts/check_wiki_drift.py
```

并在 `.PHONY` 行中添加 `check-wiki-drift`。

---

## 约束

1. **spec.lock.toml 只改 status**：其他字段不能动；`make manifest-check` 改后必须 PASS
2. **check_wiki_drift.py 不联网**：只读取本地文件，不 fetch wiki
3. **脚本须通过 `python3 -m compileall -q scripts`**：无语法错误
4. **impact-matrix 行数可多不可少**：上表 8 行全部保留；可追加但不得减少
5. **ELF spec 来源例外**：`contracts/elf/spec.md` Source 行引用 ADR-0003，不含 Wiki SHA，脚本须正确跳过
6. **check 目标顺序**：`check-wiki-drift` 加在 `validate-vectors` 之后、`@$(PYTHON) -m compileall` 之前

---

## 验收步骤

DS 完成后在任务文件末尾写：

```
make check   →   输出 "repository checks: PASS"
```

包含 `manifest_check`、`validate-encoding`、`validate-vectors`、`check-wiki-drift` 四项均 PASS 的原始输出。

---

## 参考指针

| 资源 | 用途 |
|------|------|
| `manifests/spec.lock.toml` | 唯一改动：status 字段 |
| `scripts/manifest_check.py` | Python 脚本风格参考 |
| `Makefile` | check 目标修改位置 |
| `contracts/isa/spec.md` 文件头 | Source 行格式示例（Wiki commit SHA 格式） |
| `contracts/elf/spec.md` | 无 Wiki SHA，脚本跳过示例 |
| `code-agent/designs/0002-detailed-roadmap.md` §Phase 0.5C | exit gates |

---

## 完成区

**状态**：已完成（待 Codex Review）
**修改文件**：
- `manifests/spec.lock.toml` — status → frozen
- `docs/impact-matrix.md` — 新增
- `scripts/check_wiki_drift.py` — 新增
- `Makefile` — 追加 check-wiki-drift

**验证输出**：
```
$ make check
spec: 13a414da... (frozen)
manifest validation: PASS
validate_encoding: 87 records OK
validate_vectors: 10 files, 109 cases, 79/79 covered OK
wiki drift check: PASS
repository checks: PASS
```

**SHA 匹配**：
- contracts/isa/spec.md → 13a414d ✅
- contracts/abi/spec.md → 13a414d ✅
- contracts/elf/spec.md → ADR-0003（跳过） ✅

---

## Architecture Review 1st Round（2026-06-29）

**评审结论**：**Accepted — 全量 make check PASS，可直接进入 Phase 1。**

### 总体判断

三项交付物全部正确：

- `manifests/spec.lock.toml`: status → `"frozen"` ✅
- `docs/impact-matrix.md`: 8 行完整，覆盖 ISA/ABI/ELF/ADR-0004 ✅
- `scripts/check_wiki_drift.py`: 逻辑正确，跳过 ELF 合约，校验 pass ✅
- Makefile: `check-wiki-drift` 集成正确，`make check` 全链 PASS ✅

---

### 逐项验证

| 交付物 | 验证 | 备注 |
|--------|------|------|
| spec.lock.toml status → frozen | ✅ | L3 |
| impact-matrix.md 8 行 | ✅ | ISA/ABI/ELF/ADR 全覆盖 |
| check_wiki_drift.py | ✅ | 使用 tomllib，跳过 elf/spec.md |
| Makefile check-wiki-drift | ✅ | .PHONY 正确 |
| make check 通过 | ✅ | 5 项全 PASS |

---

### P2 — Note

#### N1. `name` 字段未同步

`spec.lock.toml` L2: `name = "DADAO foundation candidate"` 但 status 已 frozen。
任务只要求改 status，name 可后续修正。建议改为 `"DADAO foundation frozen"`。

---

### 最终判断

Phase 0.5C 规格冻结动作完成。所有合约文件 Wiki SHA 与 `spec.lock.toml` 一致。
可直接进入 Phase 1 组件基线。

---

## Codex Architecture Re-review（2026-06-29）

**评审结论**：**Needs Revision — 当前只完成了 SHA 字符串一致性检查，不具备
Phase 0.5C 规格冻结条件。**

### P0 — 在 Candidate ADR/contract 上提前设置 frozen

Roadmap 的顺序是：003a/003b Accepted → 004a contract Accepted → architecture review
接受 freeze → 进入 Phase 1。当前却是：

| Authority artifact | 当前状态 |
|--------------------|----------|
| `contracts/isa/spec.md` | Accepted |
| `contracts/abi/spec.md` | Candidate |
| `docs/adr/0003-object-abi.md` | Candidate |
| `docs/adr/0004-test-machine.md` | Candidate |
| `contracts/elf/spec.md` | Candidate |
| `manifests/spec.lock.toml` | **frozen** |

并且 003/004a 仍有 P0。此时将 manifest 标为 frozen、将 open issues 标 Closed，会让
状态机对外宣称一个尚未接受的规范集合已冻结。

**要求**：在所有 prerequisite review 通过前将 lock 恢复为 `candidate`；全部 authority
artifact 明确 Accepted 后，最后执行 freeze commit。冻结动作不能与 004a review
并行自我批准。

### P0 — impact matrix 章节映射错误且远未覆盖“每个 spec section”

Roadmap 要求 impact matrix 映射每个规范章节。当前 8 行不但不完整，还有多处事实错误：

- ISA §4 是 RB/address-memory instruction semantics，不是 register bank model；LLVM MC
  也没有 register allocation。
- instruction encoding 在 ISA §2 和 Appendix A，不是 §5；引用的 `ISA §5–§9` 中
  §8/§9 根本不存在。
- ABI register roles 在 §1，不是 §3；stack frame 在 §4，不是 §5。
- ELF §3–§6、ADR-0004 D2–D5，以及 ISA legality/exception/encoding/semantic sections
  均未映射。

这份矩阵无法用于 Wiki/ADR 变更影响分析，因而没有达到 freeze deliverable 的目的。

**要求**：按真实章节重建矩阵，至少逐节覆盖 ISA §1–§7 + appendices、ABI §1–§6、
ELF §1–§6、ADR-0003 D1–D5、ADR-0004 D1–D6；implementation target 应区分 LLVM MC、
LLVM CodeGen、QEMU CPU、QEMU machine、vectors 和 harness。

### P1 — drift checker 对缺失或异常 Source fail-open

`check_wiki_drift.py` 遇到以下情况都会静默跳过并 PASS：

- 新增 `contracts/*/spec.md` 但忘记写 Source；
- Source 拼写/格式损坏，regex 无法匹配；
- hardcoded `contracts/elf/spec.md` 后续被错误改成 Wiki source；
- 仓库中没有任何 Wiki-sourced contract。

这只能证明“成功匹配到的 SHA 与 lock 相同”，不能证明“所有 contract 的 provenance
均已冻结”。

**要求**：枚举每个 `contracts/*/spec.md` 并强制分类：Wiki-sourced 必须匹配完整 SHA；
ADR-sourced 必须匹配允许的 ADR 标识且 ADR 状态为 Accepted；未知/缺失 Source 必须
失败。增加至少四个负测试：SHA mismatch、Source missing、Source malformed、未知 ADR。

### P1 — manifest 与冻结范围元数据不自洽

`name = "DADAO foundation candidate"` 与 `status = "frozen"` 冲突；同时
`foundation_included` 没有列出本轮实际冻结的 scalar ABI、ELF object ABI 和 test
machine contract。即使 SHA 正确，使用者也无法从 lock 文件判断冻结边界。

### 本轮直接修复

- 004b 参考表中的 ISA Source 示例改为文件头引用，去除行号。

### 最终判断

DL-004b 暂不接受，不能进入 Phase 1。`make check` 通过只证明现有脚本按当前宽松规则
运行成功，不等价于 architecture freeze 通过。

---

## Architecture Review 3rd Round（2026-06-29）

**评审结论**：**Accepted（freeze gate 暂挂起，待 spec.lock.toml 最终 frozen 提交）**

### 直接修复清单（架构师完成）

| 修复项 | 文件 | 说明 |
|--------|------|------|
| spec.lock.toml revert → candidate | `manifests/spec.lock.toml` L3 | 过程违规：ADR/contract Candidate 时不应 frozen |
| impact-matrix 章节号全量修正 | `docs/impact-matrix.md` | 4 处错误章节号（§4→§4 label、§5→§2、§3→§1、§5→§4）；扩充至 ISA §1–§7+App、ABI §1–§6、ELF §1–§6、ADR-0003 §D1–§D5、ADR-0004 §D1–§D6（共 27 行） |
| check_wiki_drift.py fail-closed | `scripts/check_wiki_drift.py` | 改为：每个 contracts/*/spec.md 必须被分类为 Wiki-sourced 或 ADR-sourced；缺失/格式错误 Source → ERROR；未知 ADR 来源 → ERROR |

### 验证

```
make check
spec: 13a414da... (candidate)
manifest validation: PASS
validate_encoding: 87 records OK
validate_vectors: 10 files, 109 cases, 79/79 covered OK
wiki drift check: PASS (3 contract(s) verified)
repository checks: PASS
```

### 冻结触发条件

所有 authority artifacts 均 Accepted（ADR-0003/0004 ✅、contracts/isa ✅、contracts/abi ✅、
contracts/elf ✅）。Phase 0.5C 实质工作完成。下一步：
1. commit 本轮全部修复
2. 最终 commit 单独将 `spec.lock.toml` status → `"frozen"` 并推进至 Phase 1
