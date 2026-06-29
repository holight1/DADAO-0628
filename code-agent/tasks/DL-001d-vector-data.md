# DL-001d — 测试向量数据与 validator

**状态**：待执行  
**执行环境**：本地 DS · DADAO-0628  
**类型**：测试数据 + 工具实现  
**优先级**：Phase 0.5A 交付物；DL-001c 完成后开始（opcodes.yaml 已就绪后）  
**前置任务**：DL-001c（`tools/opcodes.yaml` 需已存在）

---

## 目标

在任何实现（LLVM/QEMU）字节被写入之前，生成 M1 全量测试向量数据文件，
并实现 schema 级 validator 作为 `make check` 门控。

所有期望值（编码字节、寄存器状态、异常类型）必须从 `contracts/isa/spec.md`
手工推导，**不得**从 LLVM 输出或 QEMU 运行结果反推。

---

## 交付物

| 文件 | 内容 |
|------|------|
| `tests/vectors/schema.md` | vector YAML 字段规范（字段名、类型、约束、是否必填）|
| `tests/vectors/inventory.md` | 每条 M1 指令的覆盖矩阵（有哪些 YAML 文件、覆盖哪些类别）|
| `tests/vectors/isa/*.yaml` | **实际测试数据**，每个文件对应一个指令组 |
| `scripts/validate_vectors.py` | 校验 `tests/vectors/isa/*.yaml` 格式合规性 |
| `Makefile`（修改） | `check` target 新增 `validate_vectors.py` 调用 |

---

## schema.md 字段规范

每个 `tests/vectors/isa/*.yaml` 文件包含一个 YAML 列表，每个元素是一个 test case：

```yaml
- mnemonic: add           # 必填：指令助记符（对应 opcodes.yaml）
  format: orrr            # 必填：格式类型
  class: semantic         # 必填：向量类别（见下）
  encoding:               # 必填：完整 32-bit 指令字（hex 字符串）
    word: "0x10200000"
  input_state:            # 必填：执行前寄存器/内存状态（仅列出相关字段）
    rd:
      rd1: "0x0000000000000001"
      rd2: "0x0000000000000002"
  expected_state:         # 条件必填（见 status 字段说明）
    rd:
      rd1: "0x0000000000000003"   # 期望写入值，64-bit hex
  expected_fault: null    # null / ILLI / UNDI / MALIGN / IALIGN / RASOF / RASUF
  status: active          # active / deferred
  deferred_reason: null   # 仅 status=deferred 时必填（例如 "C-27"）
  wiki_cite: "SimRISC-01 §整数加法"   # 必填：语义来源
  notes: ""               # 可选
```

**class 合法值**（5 类）：

| class | 说明 |
|-------|------|
| encoding | 验证 word 与 opcodes.yaml mask/value 一致 |
| legality | 非法操作数/立即数 → 期望 ILLI；expected_state = null |
| semantic | 正常执行后寄存器/内存状态正确 |
| boundary | 边界值（signed-min/max/zero/overflow），是 semantic 的子集 |
| overlap | src=dst 同一寄存器；C-27 cases status=deferred |

**status=deferred 规则**：
- `expected_state` 字段必须为 `null`
- `deferred_reason` 必须填写（例如 `"C-27"`）
- C-27 的 overlap cases **必须出现在 inventory 中**，不得静默缺席

---

## 每条指令覆盖要求

对 M1 scope 内每条指令（见 Scope Matrix），至少需要以下 class 的 case：

| 指令类型 | encoding | legality | semantic | boundary | overlap |
|---------|----------|----------|----------|----------|---------|
| 所有指令 | ≥1 | ≥1（有约束的字段） | ≥1 正常情况 | ≥1（signed-min/max/zero）| 视情况 |
| 算术类（add/sub/mul/div） | ✓ | rd0 dest, 除法除零 | ✓ | signed-min/max/overflow | src=dst |
| 条件赋值（csn/csz/csp/cseq/csne） | ✓ | rdhb/rdhc=rd0 | ✓ | 条件真/假 | **deferred (C-27)** |
| 访存（load/store） | ✓ | rd0 src/dst, 对齐 | ✓ | 最大地址 | src base=dst |
| 多寄存器（ldmo/stmo） | ✓ | immu6=0, 超界 | ✓ | immu6=1/63 | — |
| RegRAS（call/ret） | ✓ | — | ≥2 层嵌套 | 深度63/64 | — |
| branch/jump | ✓ | — | taken/not-taken | — | rdha=rd0 合法 |
| RB 操作 | ✓ | rb0 dest | ✓ | 48-bit 边界 | — |

---

## tests/vectors/isa/ 文件组织

建议每个指令组一个文件（不强制，可按需拆分）：

```
tests/vectors/isa/
  rd-arith.yaml          # add/sub/mul/divs/divu/muls/mulu
  rd-logic.yaml          # and/orr/xor/xnor
  rd-shift-extend.yaml   # shlu/shrs/shru/exts/extz
  rd-compare.yaml        # cmps/cmpu
  rd-cond-assign.yaml    # csn/csz/csp/cseq/csne
  rd-load.yaml           # ldo-rd/ldb-rd/ldh-rd/ldw-rd/...
  rd-store.yaml          # sto-rd/stb-rd/...
  rd-multi.yaml          # ldmo-rd/stmo-rd
  rb-ops.yaml            # rb 算术/赋值/比较/立即数
  control-flow.yaml      # branch/jump/call/ret (含 RegRAS 深度测试)
  misc.yaml              # swym/unimp
```

---

## inventory.md 格式

```markdown
# Test Vector Inventory

| Instruction | File | encoding | legality | semantic | boundary | overlap | Notes |
|------------|------|----------|----------|----------|----------|---------|-------|
| add (orrr) | rd-arith.yaml | ✓ | ✓ rd0 | ✓ | ✓ min/max | ✓ | |
| csn (crrr) | rd-cond-assign.yaml | ✓ | ✓ rd0 | ✓ | ✓ | deferred C-27 | |
| swym | misc.yaml | ✓ | — | ✓ | — | — | no-op |
```

`deferred` 字段：填写 deferred reason（例如 `C-27`），不写 `—` 也不写 `✓`。

---

## validate_vectors.py 验证内容

对 `tests/vectors/isa/*.yaml` 中每条 case 验证：

1. **必填字段存在**：`mnemonic/format/class/encoding/input_state/wiki_cite`
2. **class 合法值**：∈ `{encoding, legality, semantic, boundary, overlap}`
3. **status 合法值**：∈ `{active, deferred}`
4. **deferred 一致性**：`status=deferred` → `expected_state=null` 且 `deferred_reason` 非空
5. **expected_fault 合法值**：`null` 或 `∈ {ILLI, UNDI, MALIGN, IALIGN, RASOF, RASUF}`
6. **encoding.word 格式**：合法 hex 字符串，值 ≤ 0xFFFFFFFF
7. **mnemonic 在 opcodes.yaml 中存在**（需读取 `tools/opcodes.yaml`）

退出码：有错误则 exit(1) 并列出具体文件+行号；无错误 exit(0)。

---

## 约束

1. 所有 `expected_state` 中的寄存器值必须从 `contracts/isa/spec.md` 手推，注释说明计算步骤
2. 不从 LLVM 汇编或 QEMU 运行结果填写期望值
3. `encoding.word` 必须与 `tools/opcodes.yaml` 中对应记录的 `(word & mask) == value` 一致（validator 检查）
4. C-27 overlap 向量**必须存在**，status=deferred，不得静默缺席（inventory 中也要有记录）
5. 完成后**不自行 commit**，等待 Claude review
6. 如发现 spec.md 有歧义无法手推期望值，在任务完成区记录，标 `[OPEN]`，不猜测

---

## 参考

- `contracts/isa/spec.md` — 全部语义来源（§3 数据、§4 地址/访存、§5 控制流、§6 系统）
- `tools/opcodes.yaml` — mnemonic/format/mask/value 数据源（DL-001c 产物）
- `docs/open-spec-issues.md` — C-27 等 OPEN 项（影响哪些 vector 必须 deferred）
- `code-agent/designs/0002-detailed-roadmap.md` §TDD Contract — 5 类向量说明和 Ordering Rule
