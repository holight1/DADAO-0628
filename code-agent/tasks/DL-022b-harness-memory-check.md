# DL-022b: Harness expected_state.memory 验证

**执行环境**：本地 DS · DADAO-0628

---

## 背景

`tests/scripts/build_test_binary.py` 的 `emit_state_compare()` 仅比较寄存器（`rd`/`rb`），
不处理 `expected_state.memory`。当前行为：

```python
if not rd and not rb:
    emit_exit(out, 0)  # 静默 PASS —— memory 期望完全跳过
    return
```

10 条 store 语义向量（stb/stw/stt/sto/stmo/stmb/stmw/stmt，共 2 个文件）的
`expected_state.memory` 当前零验证，无论 QEMU 写了什么值都会静默通过。

---

## 目标

在 `emit_state_compare()` 中新增 memory 验证路径：

对 `expected_state.memory` 的每条条目：
1. 将目标地址加载进 `rb30`（temp）
2. 用宽度对应的 **unsigned** load 指令将内存内容读入 `rd30`
3. 将期望值加载进 `rd31`，XOR 比对后 ORR 入 `rd29`（mismatch 累加器）

---

## 修改规格

### 文件：`tests/scripts/build_test_binary.py`，函数 `emit_state_compare()`

#### 变更 1：提取 memory 列表

在函数开头，紧接 `rd`/`rb` 提取之后，新增：

```
memory = expected_state.get('memory', []) if expected_state else []
```

#### 变更 2：early-return 条件

```
旧：if not rd and not rb:
新：if not rd and not rb and not memory:
```

#### 变更 3：memory 比对循环（放在 rb 比对循环之后，guard patching 之前）

对 `memory` 列表中每条 entry（包含 `address`、`value`、`width`）：

```
load_reg(out, 'rb', 30, int(entry['address'], 16))   # rb30 ← address

width = entry.get('width', 8)
if   width == 1: write_rrii(out, 0x40, 30, 30, 0)   # ldbu rd30, rb30, 0
elif width == 2: write_rrii(out, 0x41, 30, 30, 0)   # ldwu rd30, rb30, 0
elif width == 4: write_rrii(out, 0x42, 30, 30, 0)   # ldtu rd30, rb30, 0
else:            write_rrii(out, 0x33, 30, 30, 0)   # ldo  rd30, rb30, 0

expected_val = int(entry['value'], 16)
load_reg(out, 'rd', 31, expected_val)               # rd31 ← expected
xor rd31, rd31, rd30                                # rd31 = actual XOR expected
or  rd29, rd29, rd31                                # rd29 |= rd31 (accumulate mismatch)
```

XOR 编码（与现有 rd 比对循环相同）：
- `xor rd31, rd31, rd30` → `0x10280000 | (31 << 12) | (31 << 6) | 30`
- `or  rd29, rd29, rd31` → `0x10240000 | (29 << 12) | (29 << 6) | 31`

**注意**：`n_before = len(out) // 4` 位于 guard patching 节开头，已在 memory 循环之后，
无需调整 `n_patch = 17`（patching 节自身大小不变）。

---

## 约束

1. memory 比对使用 **unsigned** load（ldbu/ldwu/ldtu），不用带符号版本；
   period_state.memory.value 写的是 raw 存储字节，比对时直接 zero-extend 即可
2. `rb30`、`rd30`、`rd31` 作为 temp：
   - `rb30`：当前 emit_state_compare 未使用（rb 比对循环用的是 rd30，不是 rb30）
   - `rd30`：rb 比对循环已用完，memory 循环可复用
   - 若向量的 `expected_state.rb` 含 `rb30`，或 `expected_state.rd` 含 `rd30`/`rd31`，
     会产生误判——当前所有 10 条 store 向量不含这些寄存器，不受影响
3. 每条 memory entry 独立循环，支持单条向量有多个 entry（stmo/stmb/stmw/stmt 向量均有 2 entry）
4. 不修改 `n_patch`、不修改 guard patching 节

---

## 验收步骤（DS 完成区填写）

```bash
# 1. 确认 memory 比对路径被激活（无 rd/rb 期望的纯 memory 向量）
python3 -c "
import yaml
for f in ['tests/vectors/isa/rd-load-store.yaml',
          'tests/vectors/isa/rb-ops.yaml']:
    for c in yaml.safe_load(open(f)):
        es = c.get('expected_state') or {}
        if 'memory' in es:
            print(c['mnemonic'], es)
"

# 2. 运行 10 条 store 语义向量（需要 QEMU 已构建）
python3 tests/scripts/run_qemu_test.py \
    --filter-class semantic \
    --filter-file tests/vectors/isa/rd-load-store.yaml \
    tests/vectors/isa/rb-ops.yaml

# 期望：stb/stw/stt/sto/stmo/stmb/stmw/stmt 全部 PASS

# 3. 语义验证有效性检验：手动改一条 expected_state.memory.value 为错误值
#    运行后 QEMU 应返回 exit 0x82 (ILLI) → 状态比对检测到 mismatch → FAIL ✓
#    改回正确值后再次运行应 PASS

# 4. 全量验证（所有语义向量）
python3 tests/scripts/run_qemu_test.py --filter-class semantic \
    tests/vectors/isa/rd-arith.yaml \
    tests/vectors/isa/rd-compare.yaml \
    tests/vectors/isa/rd-load-store.yaml \
    tests/vectors/isa/rb-ops.yaml \
    tests/vectors/isa/control-flow.yaml \
    tests/vectors/isa/misc.yaml

# 期望：全部 semantic 向量 PASS
```

---

## 参考指针

| 资源 | 用途 |
|------|------|
| `tests/scripts/build_test_binary.py` `emit_state_compare()` | 唯一修改目标 |
| `tests/vectors/isa/rd-load-store.yaml` | 7 条 store memory 向量（stb/stw/stt/sto/stmo/stmb/stmw/stmt） |
| `tests/vectors/isa/rb-ops.yaml` | 3 条 store memory 向量（sto-rb/stmo-rb 各 1，另有 RB load 1）|
| `tools/opcodes.yaml` | ldbu=0x40/ldwu=0x41/ldtu=0x42/ldo=0x33 op 确认 |
| `tests/scripts/run_qemu_test.py` | 执行框架（不修改） |
| `code-agent/tasks/DL-021a-harness-semantic.md` | emit_state_compare 设计文档 |
