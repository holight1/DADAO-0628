# DL-030a: call/ret 语义测试 + RA stack 验证

**执行环境**: 本地 DS · DADAO-0628

**状态**: 待执行（DL-029a 已完成为前置）

---

## 背景

DL-029a 完成了条件分支和 jump 的语义测试（18条，全 PASS）。call/ret 因涉及 RA stack 压栈/弹栈，需要专用 binary layout：

- `call_i / call_r`：执行时把 `PC+4`（下一条指令地址）压入 `ra[63]`，然后跳转
- `ret`：从 `ra[63]` 读返回地址，跳回

当前已知约定（§1.3, §1.6）：
- `ra[63] ← pc_next + 4`（call 指令地址 + 4）
- ret 跳到 `ra[63] + imm*4`，通常 imm=0

**已知 bug 状态**：call_i/call_r 的 `ra[63]` 写入已在 commit 815d204 修复（`pc_next + 4`）。

---

## 目标

1. **新增 call/ret 语义测试向量**（TDD：先写测试向量，再跑验证）
2. **激活这些测试**（build_branch_test_binary 已有 taken/not_taken 框架，此任务可能需要新的 `call_ret` pattern）
3. **全套测试回归不破坏**（130 PASS 基线维持）

---

## 接口说明书

### 1. call 语义测试 — 验证跳转目标 + RA 压栈

**call_i 测试 pattern**：

```
binary layout:
[call_i +1]        ← 调用 +1 word = call_addr + 8 = subroutine
[emit_exit(0xAB)]  ← poison: 若 call 不跳，执行这里 → 读到错误 exit code
[subroutine:]
  verify ra[63] == call_addr + 4   ← 检查返回地址是否正确
  emit_exit(0)                      ← 正常退出
```

不过"verify ra[63]"需要 QEMU 能读 ra[63] 并比较。更简单的 TDD 方式：

**简化 pattern**：只验证 call 确实跳转到目标（taken），RA 值正确性留 DL-031a（需 expected_state 支持 ra 字段）。

使用已有 `branch_behavior: taken` pattern，把 call 当作无条件跳转测试：

```yaml
- mnemonic: call
  format: iiii
  class: semantic
  encoding:
    word: "0x6C000001"   # call_i imm=+1 → target = PC+4+4 = PC+8
  branch_behavior: taken
  input_state: {}
  expected_state: {}
  expected_fault: null
  status: active
  wiki_cite: "spec.md §5.3"
  notes: "call_i imm=+1; 无条件跳到 PC+8，跳过 unimp → exit=0"
```

同样为 `call_r rb1, rd1, 0` 写一条（需 rb1/rd1 指向 exit 地址）。

### 2. ret 语义测试 — 验证弹栈并跳回

**ret 需要先有 call 建立 ra[63]**。独立 binary layout：

```
binary layout:
[call_i +2]           ← 调用 subr（跳过 ret_landing）
[ret_landing:]
  emit_exit(0)        ← ret 正确弹回时落这里 → PASS
[subr:]
  ret rd0, 0          ← 弹出 ra[63]（= &ret_landing），跳回
```

计算：
- call_i 在 offset 0，call_i imm=+2 → target = 0 + 4 + 2*4 = 12 = subr 地址
- ra[63] ← 0 + 4 = 4 = ret_landing 地址（emit_exit 起始）
- ret rd0,0 → 跳到 ra[63] + 0 = 4 = ret_landing → emit_exit(0) → PASS

这个 layout 不能直接复用 branch_behavior taken/not_taken，需要在 build_test_binary.py 新增 `call_ret_pattern` 分支。

### 3. build_test_binary.py 改动

在 `build_branch_test_binary()` 中新增两条分支：

```python
elif mnemonic == 'call' and fmt == 'iiii' and behavior == 'taken':
    # call_i taken pattern (类似 jump_i taken)
    pass  # 不需要寄存器 setup，word 中的 imm 已经指向 exit

elif mnemonic in ('ret',):
    # call_i + ret pattern:
    # [call_i +2] [emit_exit(0)] [ret rd0,0]
    # ret 弹回到 emit_exit(0)
    emit_call_ret_pattern(buf, case)
```

新增 `emit_call_ret_pattern(buf, case)` 函数，构建上述三段 layout。

### 4. 测试向量规范（TDD 先写）

最小覆盖集（4条）：

```yaml
# 1. call_i taken（验证跳转发生）
- mnemonic: call
  format: iiii
  class: semantic
  branch_behavior: taken
  encoding:
    word: "0x6C000001"   # call_i imm=+1
  input_state: {}
  expected_state: {}
  expected_fault: null
  status: active
  wiki_cite: "spec.md §5.3"
  notes: "call_i imm=+1; target=PC+8; skip unimp → exit=0"

# 2. call_r taken（验证 rb/rd 目标计算）
- mnemonic: call
  format: rrii
  class: semantic
  branch_behavior: taken
  encoding:
    word: "0x6D041001"   # call_r rb1, rd1, 0（DS 计算正确 encoding）
  input_state:
    rb:
      rb1: "0x0000000080000000"  # BINARY_BASE（DS 确认是否需调整）
    rd:
      rd1: ???                   # exit offset（DS 计算）
  expected_state: {}
  expected_fault: null
  status: deferred              # DS 确认 exit offset 后激活
  wiki_cite: "spec.md §5.3"
  notes: "call_r rb1,rd1,0; 无条件跳转 → exit=0"

# 3. ret 弹回（call_i+ret 组合 pattern）
- mnemonic: ret
  format: riii
  class: semantic
  branch_behavior: call_ret
  encoding:
    word: "0x6E040000"   # ret rd1, 0（rd1 = 返回值占位，不影响地址）
  input_state: {}
  expected_state: {}
  expected_fault: null
  status: active
  wiki_cite: "spec.md §5.4"
  notes: "call_i+ret 组合 pattern；ra[63] 由 call 压栈，ret 弹回"

# 4. call_i not_taken（验证不存在"不跳"这个场景——call 是无条件的，无此测试）
# → 不需要 not_taken 变体（call 无条件执行）
```

### 5. 约束

- 不修改现有 build_test_binary 主路径（参考 §1 约束）
- `branch_behavior: call_ret` 新增为 emit_call_ret_pattern 的触发标志
- 验收时保持 130 PASS 基线；新增 2-4 条 active → PASS
- DS 必须从 spec.md §5.3-§5.4 手推 call_r encoding bits，不能从 QEMU 行为反推

---

## 验收

```bash
python3 tests/scripts/run_qemu_test.py tests/vectors/isa/control-flow.yaml
python3 tests/scripts/run_qemu_test.py tests/vectors/isa/rd-arith.yaml  # regression
```

预期：≥132 PASS（+2 新增 call_i taken + ret call_ret pattern），0 FAIL。

---

## 参考指针

- 知识库 §1（`code-agent/knowledge/01-qemu-translate-patterns.md`）
  - §1.3：call 返回地址公式
  - §1.4：branch-over-poison pattern
  - §1.5：jump_r offset 计算（call_r 类比）
  - §1.6：ret RA 约定
- 现有 harness：`tests/scripts/build_test_binary.py`（build_branch_test_binary，L207-L247）
- 测试向量：`tests/vectors/isa/control-flow.yaml`（DL-028a/029a 已激活的测试）
- translate.c：`trans_call_i`（L726-L733）、`trans_call_r`（L736-L753）、`trans_ret`（DS 确认行号）
- insn.decode：call_i=0x6C（iiii），call_r=0x6D（rrii），ret=0x6E（riii）

---

## 完成区

（DS 填写）
