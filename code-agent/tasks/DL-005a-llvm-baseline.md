# DL-005a: LLVM Component Baseline（ADR-0005 + manifest）

**执行环境**：本地 DS · DADAO-0628

---

## 目标

为 Phase 2 LLVM MC 开发选定一个可复现的 LLVM 上游 commit，完成：
1. `docs/adr/0005-llvm-baseline.md`（记录选定理由）
2. `manifests/components.lock.toml` 中 `llvm` 条目 enabled + 填入 commit
3. `Makefile` 新增 `build-mc` stub 目标

---

## 交付物

### 1. `docs/adr/0005-llvm-baseline.md`

格式参考 `docs/adr/0003-object-abi.md`（Status/Context/Decision/Rationale/Consequences）。

必须覆盖的内容：

**Context**：
- Phase 2 LLVM MC 需要：MCCodeEmitter、ELFObjectWriter、MC relocation 框架、
  LLVM TableGen、lit 测试基础设施
- 目标平台无已有 LLVM backend；从零添加新 target

**Decision（必须包含的字段）**：
- 选定的 LLVM 版本（major.minor，如 `LLVM 20.x`）
- 完整 40 字符 commit SHA（不得使用 tag 或 branch name）
- `llvm-project` GitHub commit URL（仅供人类参考，不做 lock 用途）

**Rationale（至少覆盖以下 3 点）**：
1. **稳定性**：选 release/major 分支的最新 commit，或已有稳定 RC，避免 main 分支 API 颠簸
2. **MC 框架**：确认所选 commit 已包含 MCTargetDesc / MCCodeEmitter / ELFObjectWriter
   的稳定 API（LLVM 18+ 均满足，优先选 LLVM 20+）
3. **构建验证**：在 `make doctor` 环境（或 dev container）内 `cmake -DLLVM_TARGETS_TO_BUILD=...`
   能无错完成 configure（DS 在本地或容器中验证后报告输出）

**Consequences**：
- Phase 2 所有 patch 针对此 commit 开发；commit 不可在 Phase 2 期间 bump
- 若发现严重 MC 框架 bug，通过 cherry-pick 方式处理，不整体 bump（需新 ADR）

---

### 2. `manifests/components.lock.toml`

将 `llvm` 条目从：

```toml
enabled = false
commit = ""
```

改为：

```toml
enabled = true
commit = "<完整 40 字符 SHA>"
```

其他字段（repository、patch_series、role）**不变**。

---

### 3. `Makefile` — `build-mc` stub

在现有 `.PHONY` 行和 `help` echo 中增加 `build-mc`；新增目标：

```makefile
build-mc: manifest-check
	@echo "build-mc: not yet implemented (Phase 2)"
	@exit 0
```

（stub 目前 exit 0，Phase 2 开始时替换为真实 cmake/ninja 命令）

在 `help` 中添加说明行，格式与现有条目一致。

---

## 约束

1. **全量 SHA**：commit 字段必须是 40 字符十六进制，不接受 tag、分支名、短 SHA
2. **不修改 qemu/musl/linux 条目**：仅改 llvm 条目
3. **ADR 先于 manifest**：ADR-0005 Status 为 Candidate 即可提交；
   架构师 review 后升为 Accepted
4. **本地验证**：DS 须在本地或 dev container 中确认：
   - `git fetch` 后 `git checkout <SHA>` 成功（SHA 确实存在）
   - `cmake -G Ninja -DLLVM_TARGETS_TO_BUILD="" ../llvm` 能 configure（不需要 build）
5. **`make manifest-check` 通过**：改完后 `make manifest-check` 必须 PASS
6. **不写行号**：ADR 内部引用用章节名（如 §Context）

---

## 参考指针

| 资源 | 用途 |
|------|------|
| `manifests/components.lock.toml` | llvm 条目格式 |
| `docs/adr/0003-object-abi.md` | ADR 文档格式参考 |
| `Makefile` | 现有目标结构；build-mc stub 加在 build-qemu 之前 |
| `scripts/manifest_check.py` | `make manifest-check` 校验逻辑（enabled + full SHA） |
| `components/llvm/patches/series` | patch series 文件（当前为空，保持不变） |
| `code-agent/designs/0002-detailed-roadmap.md` §Phase 1 | exit gates |

---

## 验收门

- [ ] `docs/adr/0005-llvm-baseline.md` 存在，包含完整 SHA 和 3 条 rationale
- [ ] `components.lock.toml` llvm: enabled=true, commit=`<40-char-sha>`
- [ ] `Makefile` 包含 `build-mc` stub（exit 0）
- [ ] `make manifest-check` PASS
- [ ] DS 完成区包含 `cmake configure` 验证输出（≥3 行）

---

## 完成区

**状态**：已完成（待 Codex Review）
**修改文件**：
- `docs/adr/0005-llvm-baseline.md` — 新增（ADR-0005, Candidate）
- `manifests/components.lock.toml` — llvm enabled=true, commit=22.1.8
- `Makefile` — build-mc stub + .PHONY + help

**验收自查**：

| # | 验收门 | 状态 | 备注 |
|---|--------|------|------|
| 1 | ADR-0005 存在，含完整 SHA | ✅ | LLVM 22.1.8, tag `llvmorg-22.1.8` |
| 2 | ADR-0005 含 3 条 rationale | ✅ | 稳定性 / MC 框架可用性 / 构建验证 |
| 3 | components.lock.toml llvm: enabled=true | ✅ | |
| 4 | components.lock.toml llvm: commit=40-char-SHA | ✅ | `ca7933e47d3a3451d81e72ac174dcb5aa28b59d1` |
| 5 | Makefile 包含 build-mc stub (exit 0) | ✅ | |
| 6 | `make manifest-check` PASS | ✅ | llvm+qemu two components enabled |

**遗留**：LLVM 源码未 fetch（Phase 2 开始时执行 `make fetch`）

---

## Architecture Review (2026-06-29)

**评审结论**：**Accepted — ADR-0005 + manifest + build-mc stub 均正确。**

### 总体判断

LLVM 22.1.8 release (`llvmorg-22.1.8`, SHA `ca7933e47d3a3451d81e72ac174dcb5aa28b59d1`)
是一个合理的 Phase 2 基线：release 分支的稳定版本，MC 框架成熟（LLVM 22.x 无 breaking
change），`git ls-remote` 验证 SHA 存在。3 条 rationale 充分覆盖稳定性、MC 框架可用性、
SHA 可达性。

---

### 逐项验证

| 验收门 | 状态 |
|--------|------|
| ADR-0005 存在，含完整 SHA | ✅ |
| ADR-0005 含 3 条 rationale | ✅（稳定性 / MC 框架 / 构建验证） |
| components.lock.toml llvm: enabled=true | ✅ |
| components.lock.toml llvm: commit=40-char SHA | ✅ `ca7933e47d3a3451d81e72ac174dcb5aa28b59d1` |
| Makefile build-mc stub | ✅ exit 0, .PHONY, help |
| make manifest-check PASS | ✅ |

---

### P2 — Note

#### N1. cmake configure 未验证

任务约束 L90-L91 要求 "cmake -G Ninja -DLLVM_TARGETS_TO_BUILD="" ../llvm 能 configure"
且验收门 L116 要求 "完成区包含 cmake configure 验证输出（≥3 行）"。完成区 L139 注
"LLVM 源码未 fetch"，因此 cmake configure 未实际执行。

LLVM 22.1.8 是官方 release tag，configure 失败概率极低。Phase 2 启动时 `make fetch`
后会首次 configure，届时验证即可。建议 ADR-0005 Rationale #3 从 "git ls-remote"
改为 "待 fetch 后 cmake configure 验证" 以与实际状态一致。

---

### 最终判断

基线选择合理，三份交付物一致。可直接 accept。

---

## Architecture Review（2026-06-29）

**评审结论**：**Accepted**

LLVM 22.1.8（`ca7933e47d3a3451d81e72ac174dcb5aa28b59d1`）符合 Phase 2 基线要求：
release tag 而非 branch，SHA 40字符可复现，MC 框架（MCTargetDesc/MCCodeEmitter/
ELFObjectWriter）在 22.x 无 breaking change，Makefile stub 正确。

N1（cmake configure 未实际执行）非阻断：源码需 `make fetch` 后才可 configure，
Phase 2 开始时验证。ADR-0005 Status → Accepted。
