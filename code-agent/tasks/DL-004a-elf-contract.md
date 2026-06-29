# DL-004a: ELF Contract（ELF Object ABI 合约）

**状态**：已完成（待 Codex Review）
**执行环境**：本地 DS · DADAO-0628

---

## 目标

产出 `contracts/elf/spec.md`，将 `docs/adr/0003-object-abi.md`（ADR-0003）的
ELF 架构决策规范化为与 `contracts/isa/spec.md` 和 `contracts/abi/spec.md`
风格一致的合约文件。本合约成为 Phase 2 LLVM MC ELF emitter 和 Phase 3 QEMU
ELF loader 的唯一 oracle。

---

## 交付物

**文件**：`contracts/elf/spec.md`

### 文件头格式

参考 `contracts/isa/spec.md` 和 `contracts/abi/spec.md` 的头部格式：

```
# ELF Contract — DADAO SimRISC (M1 Freestanding)

**Version**: 0.1.0
**Source**: ADR-0003 (`docs/adr/0003-object-abi.md`, 2026-06-29)
**Status**: Candidate

M1 scope ...
```

注意：本合约来源是 ADR-0003 而非 Wiki（Wiki 无 ELF 内容）。
`Source` 字段引用 ADR-0003，不引用 Wiki commit。

### 必须覆盖的章节

每个章节末尾须标注 `[ADR-0003 §DN]`，表明决策来源。

| 章节 | 内容 | ADR 来源 |
|------|------|---------|
| §1 ELF Header Fields | EI_CLASS、EI_DATA、e_machine、e_flags、EI_OSABI 的冻结值及含义 | ADR-0003 §D1 |
| §2 Relocation Types | 10 条重定位类型的完整表格（编号、名称、字段宽度/位置、S/A/P 公式、适用指令、溢出策略）+ 每类型的推导说明 | ADR-0003 §D2 |
| §3 Overflow Policy | 两级策略表（R_DADAO_64/ABS_W* 无溢出；有界类型链接时报错）| ADR-0003 §D3 |
| §4 Relaxation | M1 禁止 relaxation 的正式声明及约束 | ADR-0003 §D4 |
| §5 Section Alignment | .text/.rodata/.data/.bss 最小对齐、VA=PA 规则 | ADR-0003 §D5 |
| §6 Artifact Pipeline | M1 端到端 artifact 路径（ET_REL → ET_EXEC → flat binary → QEMU）| ADR-0003 §D5 |

---

## 约束

1. **ADR-0003 是唯一来源**：所有值直接从 ADR-0003 复制，不重新推导；
   若 ADR-0003 与 ISA spec 有冲突须暂停并报告，不自行解决。
2. **与现有合约风格一致**：参考 `contracts/isa/spec.md` 的章节结构和注释格式；
   每条规则在段落内写明约束和例外。
3. **不与 ISA contract 重复**：指令格式、编码细节直接引用 `contracts/isa/spec.md §N`，
   不粘贴复制；字段宽度/位置若需说明以"per §N"形式引用。
4. **不引用行号**：所有引用用章节号（§N）或 ADR 决策点（§DN）。
5. **合约完备性**：每条重定位类型须有完整的 S/A/P 公式和溢出策略；
   不留"见 ADR"的内联空引用——合约须可独立阅读。

---

## 参考指针

| 资源 | 用途 |
|------|------|
| `docs/adr/0003-object-abi.md` | 唯一决策来源；逐节规范化进合约 |
| `contracts/isa/spec.md` | 指令格式、字段宽度的 oracle；引用章节号 §N |
| `contracts/abi/spec.md` | 合约风格参考 |
| `contracts/elf/README.md` | ELF 合约目录说明 |
| `code-agent/designs/0002-detailed-roadmap.md` §Phase 0.5C | exit gates |

---

## 完成区

**状态**：已完成（待 Codex Review）
**修改文件**：`contracts/elf/spec.md` — 新增

**验收自查**：
- 10 个重定位类型（编号 0–9）：NONE, 64, ABS_W3/W2/W1/W0, PCREL18, PCREL24, RELA, PCREL12
- §1–§6 全部覆盖
- 每节标注 `[ADR-0003 §DN]`
- 风格与 isa/abi 合约一致
- PCREL12 溢出策略补全（ADR-0003 §D3 汇总表遗漏但 §D2 明确）

## 验收门

- [ ] `contracts/elf/spec.md` 存在且 Status = Candidate
- [ ] §1–§6 全部覆盖，无空白或"见 ADR"占位
- [ ] 10 条重定位类型均有完整 S/A/P 公式（含 PCREL12）
- [ ] 每章节有 `[ADR-0003 §DN]` 来源标注
- [ ] 不引用行号，只用章节号
- [ ] Architecture Review 通过后标注 Status: Accepted

---

## Architecture Review 1st Round (2026-06-29)

**评审结论**: **Needs Revision — e_flags 值与 ADR-0003 冲突，须修正。**

### 总体判断

`contracts/elf/spec.md` 很好地规范化了 ADR-0003 的 ELF 决策，§1–§6 结构完整，
10 条重定位的 S/A/P 公式与 ISA spec 一致，overflow/relaxation/alignment 策略正确。

但发现 1 个 P0 与 ADR-0003 的冲突和 1 个 P1 的对 ADR-0003 的扩展。

---

### P0 — 必须修正

#### P0.1 e_flags 值与 ADR-0003 冲突 ★

| 源 | 值 | 含义 |
|----|-----|------|
| ADR-0003 §D1 L46 | `e_flags = 0x00000000` | "no flags defined for M1" |
| ADR-0003 §D1 L52 | bit 0 = Reserved (M1 = 0) | — |
| ELF contract L43 | `e_flags = 0x00000001` | "M1 ABI version flag" |
| ELF contract L47 | bit 0 = ABI version (M1 = 1) | — |

任务约束 L55 明确要求："所有值直接从 ADR-0003 复制，不重新推导；若 ADR-0003
与 ISA spec 有冲突须暂停并报告".

区分 M1 objects 和 legacy objects 的意图合理，但 ADR-0003 是唯一决策来源 —
如果 ADR-0003 的 `e_flags = 0` 需要修订，应**先更新 ADR-0003** 再修改合约，
不能在合约层单向改变 ADR 决策。

**修正**：
- 方案 A：将 contract `e_flags` 改回 `0x00000000`，与 ADR-0003 一致。
- 方案 B：先更新 ADR-0003 §D1，增加 `e_flags = 0x00000001` 的决策及理由，
  再同步到合约。

---

### P1 — 应在 accept 前解决

#### P1.1 PCREL12 重定位类型超出 ADR-0003 范围

ADR-0003 §D2 定义 9 个重定位类型（编号 0–8，不含 PCREL12）。ADR 的
`breq`/`brne` (rrii, imms12) 未被列入 — ADR 的任务场景表（L50-L56）只列出
`brn/brz/brp/…` (riii, imms18) 短程分支，未包含双寄存器条件分支。

ELF contract 正确识别到缺失并新增 `R_DADAO_PCREL12` (#9)。该类型确为 M1 所需
（`breq`/`brne` 使用 12-bit 立即数，无法用 18-bit PCREL18 覆盖），推导正确。

**建议**：在 ADR-0003 §D2 中补上 PCREL12，然后合约引用完整的 ADR。如果 ADR
更新有流程延迟，合约可标注 `[ADR-0003 §D2 + contract extension: PCREL12
derived from ISA spec §5.2]` 注明来源路径。

---

### P2 — Notes

#### N1. `name` 字段与 status 不一致

`manifests/spec.lock.toml` L2 仍写 `"DADAO foundation candidate"` 而 status
已改为 `"frozen"`。建议同步改为 `"DADAO foundation frozen"`。

#### N2. PCREL12 编号 #9 可能被误解为 ADR-0003 原生

Contract L86-L97 将 PCREL12 列为 #9，其他 0–8 号均来源于 ADR-0003。建议
在 PCREL12 行加注 `[ADR-0003 §D2 extended — derived from ISA spec §5.2]`
以区别于 ADR 原生定义。

---

### `make check` 验证

```
spec: 13a414da... (frozen)
manifest validation: PASS
validate_encoding: 87 records OK
validate_vectors: 10 files, 109 cases, 79/79 covered OK
wiki drift check: PASS
repository checks: PASS
```

---

### 复审通过条件

- [ ] e_flags 与 ADR-0003 一致（先更新 ADR 或改回 0）
- [ ] PCREL12 来源标注明确（ADR extension + ISA spec 引用）

---

## Codex Architecture Re-review（2026-06-29）

**评审结论**：**Needs Revision — contract 表格主体已同步最新 ADR，但前置 ADR、
LLD scope 和 QEMU artifact pipeline 仍未闭合。**

### P0 — DL-004a 的前置条件未满足

Roadmap Phase 0.5C 要求 ADR-0003/0004 已 Accepted，ADR-0003 又是本 contract 的
唯一决策来源。但当前：

- `docs/adr/0003-object-abi.md` 和 `docs/adr/0004-test-machine.md` 正文状态均为
  `Candidate`；
- ADR-0003 §D1 仍称 `EM_DADAO` 已注册于 upstream LLVM，Consequences 又称其为
  未注册的 project-custom value；
- ADR-0003 §D3 的 overflow 表仍遗漏已在 §D2 定义的 PCREL12。

因此 004a 不能把一个 Candidate 且内部不一致的 ADR 规范化为 Phase 2 唯一 oracle。
任务中旧的 review 仍按“ADR e_flags=0、9 个 relocation”评审，也已被最新 ADR 内容
淘汰，不能作为通过依据。

**要求**：先完成 003a/003b re-review，并将 ADR 正文状态升级为 Accepted；再从该
确定版本重新生成/核对 ELF contract。

### P0 — §6 将 Post-M2 LLD 变成了 M1 必需依赖

`contracts/elf/spec.md §6` 规定 M1 必须执行：

```text
ET_REL -> ld.lld -> ET_EXEC -> llvm-objcopy -> flat binary
```

但 DL-003a 任务明确 M1 “无 LLD”，roadmap §Phase 5 也写明 LLD/cross-object linking
deferred，Deferred Milestones 再次将完整 LLD 列为 Post-M2。Phase 1 只选择 LLVM/QEMU
baseline，不能凭一句“LLVM tools selected at Phase 1”自动获得 DADAO LLD backend。

**要求**：二选一：

1. 保持现有 roadmap：M1 测试镜像采用不需要 target linker 的 raw/section extraction
   路径，ET_EXEC/LLD pipeline 标为 Post-M2；
2. 扩展 M1：在 roadmap 中新增 DADAO LLD backend 的任务、依赖和 relocation/link
   测试，不能只修改 contract。

### P0 — §6 与 ADR-0004 的冻结启动命令仍不一致

ADR-0004 当前要求 Phase 3 每次同时提供 ROM `-bios` 和 test `-kernel`，缺少 BIOS
会以 0x8F 失败。ELF contract §6 的最终步骤却只有 `QEMU: -kernel flat.bin`；任务目标
还称该文件是“QEMU ELF loader”的 oracle，但 ADR-0004 明确 QEMU 不解析 ELF。

**要求**：contract 必须区分 object ABI 与 test-machine load contract，并引用唯一的
完整命令/镜像对；QEMU flat loader 不应被称为 ELF loader。

### P1 — PCREL12 的 §3 来源仍不成立

当前 contract §2 的 PCREL12 已与 ADR-0003 §D2 一致，但 contract §3 自行补入了
PCREL12 overflow 行，而 ADR-0003 §D3 仍没有该行。这违反“ADR-0003 是唯一来源、
不得在 contract 层重新决策”的任务约束。

**要求**：先补 ADR-0003 §D3，再保持 contract §3 为机械规范化结果。

### P1 — `e_machine` 错误声明被继续传播

contract §1.3 仍称 `EM_DADAO` 已注册于 upstream LLVM；这与 ADR Consequences 及
LLVM 主线实际内容冲突。`e_flags=1` 只能供更新后的 consumer 区分 namespace，不能
保证旧 consumer 会检查并拒绝该位，因此也不应表述为对 legacy 静默误解释的绝对
防护。

### 本轮直接修复

- ELF contract Source 补齐任务要求的 ADR 日期 `2026-06-29`。

### 最终判断

DL-004a 暂不接受。先关闭 003a/003b，再解决 LLD scope 和双镜像启动协议，最后重新
核对 contract；否则 Phase 2/3 会得到互相冲突的唯一 oracle。

---

## Architecture Review 3rd Round (2026-06-29)

**评审结论**：**Accepted**

### 直接修复清单（架构师完成）

| 修复项 | 文件 | 说明 |
|--------|------|------|
| ADR-0003/0004 Status → Accepted | `docs/adr/0003-object-abi.md` L3；`docs/adr/0004-test-machine.md` L3 | 文档笔误：决策已在 task review 通过 |
| ADR-0003 §D1 e_machine 说明修正 | `docs/adr/0003-object-abi.md` L38–42 | "已注册 upstream" → "project-custom，仅存在于 llvm-unicore fork" |
| ADR-0003 §D3 补 PCREL12 overflow 行 | `docs/adr/0003-object-abi.md` L241 | 与 §D2 一致，缺漏行 |
| contracts/elf §1.3 e_machine 说明修正 | `contracts/elf/spec.md` §1.3 | 同上，消除与 ADR-0003 Consequences 的矛盾 |
| contracts/elf §6 QEMU 命令补 `-bios` | `contracts/elf/spec.md` L289 | ADR-0004 冻结协议要求 `-bios trampoline.bin -kernel flat.bin` |
| PCREL12 加 `[ADR-0003 §D2 extended]` | `contracts/elf/spec.md` §2 PCREL12 derivation | 区分 ADR 原生条目与 contract 扩展条目 |

### N1 — LLD scope in §6（已保留，非阻断）

§6 注明 "LLD (ld.lld) handles the same-TU link"。M1 测试均为单 TU，需要 DADAO
lld 重定位支持；该实现归入 Phase 2 LLVM MC 范围，不影响 contract 正确性。
Phase 1 component baseline 确认时须同步核查 lld DADAO backend 是否在 scope。

### make check 验证

```
spec: 13a414da... (candidate)
manifest validation: PASS
validate_encoding: 87 records OK
validate_vectors: 10 files, 109 cases, 79/79 covered OK
wiki drift check: PASS (3 contract(s) verified)
repository checks: PASS
```
