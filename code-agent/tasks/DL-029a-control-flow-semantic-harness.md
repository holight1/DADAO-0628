# DL-029a: 分支语义测试 harness 扩展 + 测试向量激活

**执行环境**: 本地 DS · DADAO-0628

**状态**: 待执行（需 DL-028a 先完成）

---

## 背景

DL-028a 已将所有 semantic 分支/跳转测试标记为 `status: deferred`，并写入了 TDD 桩。本任务实现 harness 支持并激活这些测试。

当前 `build_test_binary.py` 的 `emit_state_compare` 假设测试指令后顺序执行。对于分支/跳转指令：
- **分支 taken**：PC 跳到目标地址，跳过后续比较代码
- **分支 not taken**：PC 顺序前进，正常执行比较代码

两种场景都需要专用 binary layout。

---

## 目标

1. **扩展 `build_test_binary.py`**：支持 branch/jump/call/ret 语义测试的 binary layout
2. **激活 control-flow.yaml semantic 测试**：所有 branch/jump/call/ret 语义向量 PASS

---

## 接口说明书

### 1. 设计原则

**branch-taken 测试 pattern**（验证跳转实际发生）：

```
[setup registers]
[branch instruction]  ← target = PC + 2 words（跳过 poison）
[unimp]               ← poison：NOT taken 路径进入 ILLI → 测试失败
[emit_exit(0)]        ← taken 路径正常退出
```

如果跳转实际执行（taken），poison 被跳过，exit=0 → PASS。
如果跳转未发生（bug），poison 触发 ILLI，exit=0x82 → FAIL。

**branch-not-taken 测试 pattern**（验证条件不满足时不跳）：

```
[setup registers]
[branch instruction, imm=+1]  ← 若 taken，跳到 unimp → ILLI → FAIL
[emit_exit(0)]                ← not taken 路径正常退出
[unimp]                       ← poison：taken 路径进入 ILLI
```

### 2. build_test_binary.py 改动

在 `build_test_binary.py` 中新增函数 `build_branch_test_binary(case)`，专门处理 `class: semantic` 的 branch/jump/call/ret 测试。

通过 yaml 中的新字段 `branch_behavior` 区分两种 pattern：

```yaml
branch_behavior: taken     # 测试此条件下分支 taken
branch_behavior: not_taken # 测试此条件下分支 not taken
```

在 `build_test_binary(case)` 中，检测到 `branch_behavior` 字段时调用 `build_branch_test_binary(case)`。

**taken pattern 的 binary 构建**：
1. `emit_register_loader(buf, case)`  
2. 写测试指令：encoding word 中的 offset 字段需要修改为 `+2 words`（跳过 poison）  
   — 需要从 yaml 中提取 mnemonic/format 来计算正确的 offset 编码位置
3. 写 `unimp`（0x10FC0000）
4. `emit_exit(buf, 0)`

**not-taken pattern 的 binary 构建**：
1. `emit_register_loader(buf, case)`
2. 写测试指令：offset = `+2 words`（若误 taken，跳到 unimp）
3. `emit_exit(buf, 0)`
4. 写 `unimp`（poison for taken path）

**offset 字段计算**：DS 需从 insn.decode 和 translate.c 确认 offset 的语义（PC-relative in words, 从 branch 指令本身还是下一条）。

### 3. yaml 测试向量规范（TDD 先写测试）

**先写测试向量，再实现 harness**。

为每个分支指令写 2 条测试（taken + not-taken），格式如下：

```yaml
- mnemonic: brz
  format: riii
  class: semantic
  encoding:
    word: "0x2A04XXXX"     # brz rd1, offset=+2（DS 计算正确 offset bits）
  branch_behavior: taken
  input_state:
    rd:
      rd1: "0x0000000000000000"   # 条件：zero → taken
  expected_state: {}
  expected_fault: null
  status: deferred                 # 待 harness 实现后激活
  wiki_cite: "spec.md §5.1"
  notes: "brz rd1,imm=+2; rd1=0 → taken，跳过 unimp → exit=0"

- mnemonic: brz
  format: riii
  class: semantic
  encoding:
    word: "0x2A040002"     # brz rd1, offset=+2（若 taken 则到 unimp → FAIL）
  branch_behavior: not_taken
  input_state:
    rd:
      rd1: "0x0000000000000001"   # 条件：non-zero → not taken
  expected_state: {}
  expected_fault: null
  status: deferred
  wiki_cite: "spec.md §5.1"
  notes: "brz rd1,imm=+2; rd1≠0 → not taken，顺序执行 → exit=0"
```

**覆盖范围**（DS 需为以下每条指令各写 taken + not-taken，共 ~20 条）：

| 指令 | taken 条件 | not-taken 条件 |
|------|-----------|----------------|
| brn rd1 | rd1 < 0 | rd1 ≥ 0 |
| brnn rd1 | rd1 ≥ 0 | rd1 < 0 |
| brz rd1 | rd1 == 0 | rd1 ≠ 0 |
| brnz rd1 | rd1 ≠ 0 | rd1 == 0 |
| brp rd1 | rd1 > 0 | rd1 ≤ 0 |
| brnp rd1 | rd1 ≤ 0 | rd1 > 0 |
| breq rd1,rd2 | rd1 == rd2 | rd1 ≠ rd2 |
| brne rd1,rd2 | rd1 ≠ rd2 | rd1 == rd2 |
| jump_i imm | 无条件 taken | — |
| jump_r rb1+rd1 | 无条件 taken，目标 = 合法地址 | — |

call/ret 语义测试较复杂（涉及 RA push/pop），可单独写 DL-030a 处理。

### 4. 约束

- `build_test_binary.py` 只加函数，不改现有 `build_test_binary()`/`emit_state_compare()` 逻辑
- `run_qemu_test.py` 不改动（识别 `branch_behavior` 字段由 build_test_binary 内部处理）
- offset 值必须从 spec.md §5 手推，不能从 QEMU 行为反推

---

## 验收

```bash
python3 tests/scripts/run_qemu_test.py tests/vectors/isa/control-flow.yaml
```

预期：DL-028a 的 encoding 测试继续 PASS + 本任务激活的 semantic 测试 PASS。

激活目标：≥16 条 semantic 测试全 PASS（brn/brnn/brz/brnz/brp/brnp/breq/brne 各 2 条 + jump_i/jump_r 各 1 条）。

---

## 参考指针

- 待激活的 deferred 测试：`tests/vectors/isa/control-flow.yaml`（DL-028a 写入）
- 现有 binary builder：`tests/scripts/build_test_binary.py`
- 分支指令 trans：`.work/source/qemu/target/dadao/translate.c`（trans_brn/brz/breq 等）
- 分支偏移语义：`contracts/isa/spec.md §5.1–§5.4`
- 知识库 §4（translate 约束）

---

## 完成区

（DS 填写）
