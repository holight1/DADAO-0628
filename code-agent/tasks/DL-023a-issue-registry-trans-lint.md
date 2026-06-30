# DL-023a: O-2 Issue Registry + O-3 QEMU Trans Lint

**执行环境**：本地 DS · DADAO-0628

---

## 背景

`docs/open-spec-issues.md` 当前是 Markdown 表格，无法被 CI 机械读取：
- 无法自动检测"哪些 open 问题阻断 M1 gate"
- 需要人工查看，容易漏看

`components/qemu/patches/` 中 QEMU trans 函数存在性无任何工具验证：
- 87 条 M1 opcode 中，某条 trans_xxx 若实现缺失，QEMU 会走 ILLI stub，测试静默失败
- 目前只能靠人工逐个检查

---

## 目标

**O-2**：新建 `docs/issues.yaml`（机器可读 issue registry）+ `scripts/check_issues.py`（CI gate）
**O-3**：新建 `scripts/check_qemu_trans.py`（trans 函数存在性 lint）+ Makefile `lint` 目标

---

## O-2: Issue Registry

### 格式规范

`docs/issues.yaml` 顶层为列表，每条 issue：

```yaml
- id: C-27
  title: "csn/csz/csp/cseq/csne src=dst overlap snapshot rule"
  status: open          # open | closed
  scope: [M1]          # M1 | post-M1 | system | SBI | kernel
  blocks: [overlap-vectors, M1-gate]  # M1-gate 表示直接阻断 M1 里程碑
  resolved_by: null     # null 或 "commit SHA / ADR ref / wiki PR"

- id: C-SBZ-fault
  title: "SBZ field write fault semantics"
  status: open
  scope: [M1]
  blocks: [legality-vectors]
  resolved_by: null

- id: ADR-0003
  title: "ELF/object ABI"
  status: closed
  scope: [M1]
  blocks: []
  resolved_by: "ADR-0003 (2026-06-29)"
```

字段约束：
- `status`：必须是 `open` 或 `closed`
- `scope`：列表，至少含一项
- `blocks`：列表，可空
- `resolved_by`：closed 时必须填，open 时为 null

### 迁移内容

从 `docs/open-spec-issues.md` 迁移当前所有条目（open 和 closed）到 `docs/issues.yaml`。

当前 open 条目（至少含）：
- C-27（条件赋值重叠，blocks M1-gate）
- C-18b（rb0 复位值，scope post-M1）
- SBZ fault（blocks legality-vectors）
- TLB fault return（scope system）
- PTW SBI ABI（scope SBI）
- VA2PA result（scope SBI）
- Varargs（scope post-M1）
- Cross-cfx escape（scope system）
- Multiple returns（scope post-M1）
- Hardware reset（scope system）

从 `docs/wiki-questions.md` 中 OPEN 项中补充遗漏的 C-xx。

### `scripts/check_issues.py` 规范

```python
#!/usr/bin/env python3
"""CI gate: fail if any M1-blocking issue is still open."""
```

逻辑：
1. 读取 `docs/issues.yaml`
2. 对每条 issue：若 `status == 'open'` 且 `'M1-gate' in blocks`：报错
3. 若有任何报错：print 到 stderr，`sys.exit(1)`
4. 若 `docs/issues.yaml` 不存在：`sys.exit(1)` fail-closed
5. 成功时输出：`check_issues: N open, M closed (K blocking M1-gate: 0)`

### Makefile 集成

在 `check` target 中追加 `check-issues`：

```makefile
check-issues:
	@$(PYTHON) scripts/check_issues.py

check: manifest-check validate-encoding validate-vectors check-wiki-drift check-issues
	...
```

---

## O-3: QEMU Trans Existence Lint

### `scripts/check_qemu_trans.py` 规范

```python
#!/usr/bin/env python3
"""Lint: check that every M1 opcode has a trans_<mnemonic> in QEMU patches."""
```

逻辑：
1. 读取 `tools/opcodes.yaml`，收集所有 M1 mnemonic（排除 `rd2ra`/`ra2rd`）
2. 对每个 mnemonic：grep `components/qemu/patches/*.patch` 是否含 `trans_<mnemonic>`
   - 注意：mnemonic 中的 `-` 在 C 函数名中为 `_`（如 `ldmbs` → `trans_ldmbs`）
   - 多个 opcode 共享同一 mnemonic（如 `addi` 既是 RD 也是 RB）：只需找到一个匹配
3. 收集所有未找到 `trans_xxx` 的 mnemonic，输出警告
4. 打印汇总：`check_qemu_trans: N/M mnemonics have trans impl`
5. **不以非零 exit 阻断 CI**（仅 lint 警告，不是 gate）；DS 可加 `--strict` flag 使其 exit 1

输出格式：
```
MISSING trans_unimp (op=0x10 ha=0x3F)
MISSING trans_swym  (op=0x10 ha=0x00)
...
check_qemu_trans: 75/87 mnemonics have trans impl (12 missing)
```

### Makefile 集成

新增 `lint` target（不在 check 中，单独运行）：

```makefile
.PHONY: lint check-qemu-trans

check-qemu-trans:
	@$(PYTHON) scripts/check_qemu_trans.py || true

lint: check-qemu-trans
	@echo "lint: complete"
```

`|| true` 使 lint 不阻断 make（因为 check_qemu_trans.py 总是 exit 0）。

---

## 约束

1. `docs/open-spec-issues.md` 保留不删（保持人类可读视图），`docs/issues.yaml` 作为新增机械源
2. `check_issues.py` 只检查 `M1-gate in blocks`，不检查其他 blocks 项（避免误报）
3. `check_qemu_trans.py` 是 lint 不是 gate，exit 始终为 0（除非加 `--strict`）
4. mnemonic 标准化：将 `-` 转为 `_`，全小写，搜索 `trans_<normalized>`
5. 去重 mnemonic：`add` 既出现在 RD 组也出现在 RB 组，但只需一个 `trans_add` 即可

---

## 验收步骤（DS 完成区填写）

```bash
# O-2 验收

# 1. docs/issues.yaml 存在且格式正确
python3 -c "import yaml; d=yaml.safe_load(open('docs/issues.yaml')); print(len(d), 'issues')"
# 期望：输出 ≥ 10

# 2. check_issues.py 当前报 C-27 blocking（无阻断时期望 exit 0）
python3 scripts/check_issues.py; echo "exit: $?"
# 注：若 C-27 status=open + M1-gate in blocks → exit 1 + 报错（符合预期）

# 3. make check 通过（C-27 blocking 是预期状态，check_issues 应当报 FAIL 并输出原因）
#    如果用户希望 make check 目前仍然 PASS，DS 可将 C-27 的 blocks 改为 [overlap-vectors]
#    而不是 [M1-gate]，直到 C-27 真正解决。由 DS 判断哪个更准确。

# O-3 验收

# 4. check_qemu_trans.py 输出 trans 覆盖统计
python3 scripts/check_qemu_trans.py
# 期望：输出类似 "check_qemu_trans: 75/87 mnemonics have trans impl"
#        MISSING 列表合理（应含 swym/unimp 等 MISC-Norm 特殊指令）

# 5. make lint 运行无错
make lint

# 6. make check PASS（check_issues 如有 M1-gate open 则报告，不影响其他检查）
make check
```

---

## 参考指针

| 资源 | 用途 |
|------|------|
| `docs/open-spec-issues.md` | 迁移源（C-xx open issue 清单）|
| `docs/wiki-questions.md` | 补充 OPEN 条目 |
| `tools/opcodes.yaml` | M1 mnemonic 列表（O-3 来源）|
| `components/qemu/patches/*.patch` | trans 函数存在性 grep 目标 |
| `Makefile` | check / lint target（修改目标）|
| `consistency-coverage-analysis.md §四 O-2/O-3` | 背景与实现复杂度定性 |
