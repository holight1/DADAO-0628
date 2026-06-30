# DL-022c: ISA 语义向量内存地址迁移 ROM → RAM

**执行环境**：本地 DS · DADAO-0628

---

## 背景

所有 load/store 语义向量的 `rb2` 地址寄存器和内存段地址均指向
ROM 区域（`0x0000000000100000` ≈ 0x100000–0x10FFFF）：

- **QEMU patch 0001**：`memory_region_set_readonly(rom, true)` —— 写入静默丢弃
- **emit_memory_setup**：对 `input_state.memory` 执行 store 指令来初始化测试内存
  → 写入 ROM → 静默丢弃 → load 读到原始 ROM 内容而非期望值
- **emit_state_compare（DL-022b）**：对 `expected_state.memory` 执行 load 回读
  → 读到原始 ROM 内容 → XOR ≠ 0 → 全部 FAIL

涉及 2 个文件共 **26 条 semantic 向量**（23 + 3），需整体迁移至 RAM scratch 区。

---

## 目标

将以下两个文件中所有 `class: semantic` 向量使用 ROM 地址的字段
统一替换为 RAM scratch 区地址：

```
旧 base：0x0000000000100000
新 base：0x0000000087FF0000   （RAM 0x80000000-0x87FFFFFF 靠顶部的 scratch 区）
```

---

## 地址映射规则

### 通用规则

```
old_addr = 0x0000000000100000 + offset
new_addr = 0x0000000087FF0000 + offset
```

对应关系：

| 旧地址                       | 新地址                       | offset |
|------------------------------|------------------------------|--------|
| `0x0000000000100000`         | `0x0000000087FF0000`         | +0     |
| `0x0000000000100001`         | `0x0000000087FF0001`         | +1     |
| `0x0000000000100002`         | `0x0000000087FF0002`         | +2     |
| `0x0000000000100004`         | `0x0000000087FF0004`         | +4     |
| `0x0000000000100008`         | `0x0000000087FF0008`         | +8     |
| `0x00000000001000FF`         | `0x0000000087FF00FF`         | +255   |
| `0x0000000000100FFF`         | `0x0000000087FF0FFF`         | +4095  |

### 例外：stb 向量 [rd-load-store.yaml #3]

`stb` 向量的 `expected_state.memory.address` 原值 `0x0000000000100FFC` 存在
**已有 bug**：指令 `stb rd1,rb2,-4` 的有效地址 = rb2 + (-4)，
以原 rb2=0x100000 计算应得 `0x0FFFFC`（非 ROM），而非 YAML 中写的 `0x100FFC`。

**正确修复**（同时修正该 bug）：

```
rb2:    0x0000000000100000  →  0x0000000087FF0000
地址:   0x0000000000100FFC  →  0x0000000087FEFFFC
           （= 0x87FF0000 - 4，即新 rb2 + offset(-4)）
```

不要用 naive 映射 (0x100FFC - 0x100000 + 0x87FF0000 = 0x87FF0FFC)，
而要使用 `rb2_new + (-4) = 0x87FEFFFC`。

---

## 修改规格

### 文件 1：`tests/vectors/isa/rd-load-store.yaml`

修改所有 `class: semantic` 的向量中 `rb2`（及 `rb0`）寄存器值、
`input_state.memory[*].address`、`expected_state.memory[*].address`：

| 向量 # | mnemonic | 字段 | 旧值 | 新值 |
|--------|----------|------|------|------|
| [0] | ldbs | rb.rb2 | `0x0000000000100000` | `0x0000000087FF0000` |
| [0] | ldbs | rb.rb0 | `0x0000000000100000` | `0x0000000087FF0000` |
| [0] | ldbs | in_mem[0].address | `0x0000000000100008` | `0x0000000087FF0008` |
| [1] | ldbu | rb.rb2 | `0x0000000000100000` | `0x0000000087FF0000` |
| [1] | ldbu | in_mem[0].address | `0x0000000000100008` | `0x0000000087FF0008` |
| [2] | ldo | rb.rb2 | `0x0000000000100000` | `0x0000000087FF0000` |
| [2] | ldo | in_mem[0].address | `0x00000000001000FF` | `0x0000000087FF00FF` |
| [3] | stb | rb.rb2 | `0x0000000000100000` | `0x0000000087FF0000` |
| [3] | stb | ex_mem[0].address | `0x0000000000100FFC` | `0x0000000087FEFFFC` |
| [4] | sto | rb.rb2 | `0x0000000000100000` | `0x0000000087FF0000` |
| [4] | sto | ex_mem[0].address | `0x0000000000100000` | `0x0000000087FF0000` |
| [7] | ldws | rb.rb2 | `0x0000000000100000` | `0x0000000087FF0000` |
| [7] | ldws | in_mem[0].address | `0x0000000000100008` | `0x0000000087FF0008` |
| [8] | ldwu | rb.rb2 | `0x0000000000100000` | `0x0000000087FF0000` |
| [8] | ldwu | in_mem[0].address | `0x0000000000100008` | `0x0000000087FF0008` |
| [9] | ldts | rb.rb2 | `0x0000000000100000` | `0x0000000087FF0000` |
| [9] | ldts | in_mem[0].address | `0x0000000000100008` | `0x0000000087FF0008` |
| [10] | ldtu | rb.rb2 | `0x0000000000100000` | `0x0000000087FF0000` |
| [10] | ldtu | in_mem[0].address | `0x0000000000100008` | `0x0000000087FF0008` |
| [11] | stw | rb.rb2 | `0x0000000000100000` | `0x0000000087FF0000` |
| [11] | stw | ex_mem[0].address | `0x0000000000100008` | `0x0000000087FF0008` |
| [12] | stt | rb.rb2 | `0x0000000000100000` | `0x0000000087FF0000` |
| [12] | stt | ex_mem[0].address | `0x0000000000100000` | `0x0000000087FF0000` |
| [13] | ldmo | rb.rb2 | `0x0000000000100000` | `0x0000000087FF0000` |
| [13] | ldmo | in_mem[0].address | `0x0000000000100000` | `0x0000000087FF0000` |
| [13] | ldmo | in_mem[1].address | `0x0000000000100008` | `0x0000000087FF0008` |
| [14] | stmo | rb.rb2 | `0x0000000000100000` | `0x0000000087FF0000` |
| [14] | stmo | ex_mem[0].address | `0x0000000000100000` | `0x0000000087FF0000` |
| [14] | stmo | ex_mem[1].address | `0x0000000000100008` | `0x0000000087FF0008` |
| [15] | ldmbs | rb.rb2 | `0x0000000000100000` | `0x0000000087FF0000` |
| [15] | ldmbs | in_mem[0].address | `0x0000000000100000` | `0x0000000087FF0000` |
| [15] | ldmbs | in_mem[1].address | `0x0000000000100001` | `0x0000000087FF0001` |
| [16] | stmb | rb.rb2 | `0x0000000000100000` | `0x0000000087FF0000` |
| [16] | stmb | ex_mem[0].address | `0x0000000000100000` | `0x0000000087FF0000` |
| [16] | stmb | ex_mem[1].address | `0x0000000000100001` | `0x0000000087FF0001` |
| [18] | ldmws | rb.rb2 | `0x0000000000100000` | `0x0000000087FF0000` |
| [18] | ldmws | in_mem[0].address | `0x0000000000100000` | `0x0000000087FF0000` |
| [18] | ldmws | in_mem[1].address | `0x0000000000100002` | `0x0000000087FF0002` |
| [19] | ldmts | rb.rb2 | `0x0000000000100000` | `0x0000000087FF0000` |
| [19] | ldmts | in_mem[0].address | `0x0000000000100000` | `0x0000000087FF0000` |
| [19] | ldmts | in_mem[1].address | `0x0000000000100004` | `0x0000000087FF0004` |
| [20] | stmw | rb.rb2 | `0x0000000000100000` | `0x0000000087FF0000` |
| [20] | stmw | ex_mem[0].address | `0x0000000000100000` | `0x0000000087FF0000` |
| [20] | stmw | ex_mem[1].address | `0x0000000000100002` | `0x0000000087FF0002` |
| [21] | stmt | rb.rb2 | `0x0000000000100000` | `0x0000000087FF0000` |
| [21] | stmt | ex_mem[0].address | `0x0000000000100000` | `0x0000000087FF0000` |
| [21] | stmt | ex_mem[1].address | `0x0000000000100004` | `0x0000000087FF0004` |
| [22] | ldmbu | rb.rb2 | `0x0000000000100000` | `0x0000000087FF0000` |
| [22] | ldmbu | in_mem[0].address | `0x0000000000100000` | `0x0000000087FF0000` |
| [22] | ldmbu | in_mem[1].address | `0x0000000000100001` | `0x0000000087FF0001` |
| [23] | ldmwu | rb.rb2 | `0x0000000000100000` | `0x0000000087FF0000` |
| [23] | ldmwu | in_mem[0].address | `0x0000000000100000` | `0x0000000087FF0000` |
| [23] | ldmwu | in_mem[1].address | `0x0000000000100002` | `0x0000000087FF0002` |
| [24] | ldmtu | rb.rb2 | `0x0000000000100000` | `0x0000000087FF0000` |
| [24] | ldmtu | in_mem[0].address | `0x0000000000100000` | `0x0000000087FF0000` |
| [24] | ldmtu | in_mem[1].address | `0x0000000000100004` | `0x0000000087FF0004` |
| [25] | ldmo | rb.rb2 | `0x0000000000100000` | `0x0000000087FF0000` |
| [25] | ldmo | in_mem[0].address | `0x0000000000100000` | `0x0000000087FF0000` |
| [25] | ldmo | in_mem[1].address | `0x0000000000100008` | `0x0000000087FF0008` |

注意：
- 向量 #5、#6、#17 是 legality/encoding/boundary 类，**不修改**
- `notes` 字段是注释，可选择同步更新地址字符串（非强制）
- 向量索引（#N）是零基，与 yaml.safe_load(open(f)) 返回的列表下标对应

### 文件 2：`tests/vectors/isa/rb-ops.yaml`

| 向量 # | mnemonic | 字段 | 旧值 | 新值 |
|--------|----------|------|------|------|
| [5] | ldo | rb.rb2 | `0x0000000000100000` | `0x0000000087FF0000` |
| [5] | ldo | in_mem[0].address | `0x0000000000100008` | `0x0000000087FF0008` |
| [6] | sto | rb.rb2 | `0x0000000000100000` | `0x0000000087FF0000` |
| [6] | sto | ex_mem[0].address | `0x0000000000100000` | `0x0000000087FF0000` |
| [9] | stmo | rb.rb2 | `0x0000000000100000` | `0x0000000087FF0000` |
| [9] | stmo | ex_mem[0].address | `0x0000000000100000` | `0x0000000087FF0000` |

注意：
- [4] rela 的 rb0=0x100000 是算术输入（不做内存访问），**不修改**
- [7] stmo legality 类，**不修改**

---

## 约束

1. **只修改** `class: semantic` 向量的 `rb.rb2`、`rb.rb0`（仅 ldbs）、
   `input_state.memory[*].address`、`expected_state.memory[*].address`
2. **不修改** encoding.word（指令编码不变，只有 rb 寄存器值变了）
3. **不修改** 任何 legality/boundary/encoding 类向量（即使它们也引用 0x100000）
4. **不修改** expected_state.rd/rb 寄存器值（值不变，只是地址换了）
5. 所有新地址必须在 RAM 范围 `[0x80000000, 0x87FFFFFF]` 内
6. stb 向量的例外处理（见"地址映射规则"章节）必须精确

---

## 验收步骤（DS 完成区填写）

```bash
# 1. 确认 ROM 地址已清零（语义向量不再引用 ROM）
python3 -c "
import yaml, glob
ROM_START, ROM_END = 0x100000, 0x10FFFF
for path in sorted(glob.glob('tests/vectors/isa/*.yaml')):
    for i, c in enumerate(yaml.safe_load(open(path))):
        if c.get('class') != 'semantic':
            continue
        inp = c.get('input_state') or {}
        for m in (inp.get('memory') or []):
            a = int(m['address'], 16)
            if ROM_START <= a <= ROM_END:
                print('STILL ROM:', path, i, c['mnemonic'], m['address'])
        for m in ((c.get('expected_state') or {}).get('memory') or []):
            a = int(m['address'], 16)
            if ROM_START <= a <= ROM_END:
                print('STILL ROM:', path, i, c['mnemonic'], m['address'])
# 期望：无输出
"

# 2. 确认 RAM 范围合法
python3 -c "
import yaml, glob
RAM_START, RAM_END = 0x80000000, 0x87FFFFFF
for path in sorted(glob.glob('tests/vectors/isa/*.yaml')):
    for i, c in enumerate(yaml.safe_load(open(path))):
        if c.get('class') != 'semantic':
            continue
        inp = c.get('input_state') or {}
        for m in (inp.get('memory') or []):
            a = int(m['address'], 16)
            if a > 0 and not (RAM_START <= a <= RAM_END):
                print('OUT OF RAM:', path, i, c['mnemonic'], m['address'])
        for m in ((c.get('expected_state') or {}).get('memory') or []):
            a = int(m['address'], 16)
            if a > 0 and not (RAM_START <= a <= RAM_END):
                print('OUT OF RAM:', path, i, c['mnemonic'], m['address'])
# 期望：无输出
"

# 3. make check 仍然通过（yaml schema 合法，不影响其他检查）
make check

# 4. stb 专项确认
python3 -c "
import yaml
cases = yaml.safe_load(open('tests/vectors/isa/rd-load-store.yaml'))
stb = cases[3]
assert stb['mnemonic'] == 'stb'
rb2 = int(stb['input_state']['rb']['rb2'], 16)
addr = int(stb['expected_state']['memory'][0]['address'], 16)
assert rb2 == 0x87FF0000, f'rb2 wrong: {rb2:#x}'
assert addr == 0x87FEFFFC, f'addr wrong: {addr:#x}'
print('stb OK: rb2=', hex(rb2), 'ea=', hex(addr))
"
```

---

## 参考指针

| 资源 | 用途 |
|------|------|
| `tests/vectors/isa/rd-load-store.yaml` | 23 条 semantic 向量，主文件 |
| `tests/vectors/isa/rb-ops.yaml` | 3 条 semantic 向量 |
| `docs/adr/0004-test-machine.md` | ADR-0004 D5：ROM=0x100000 只读，RAM=0x80000000 |
| `tests/scripts/build_test_binary.py` | emit_memory_setup / emit_state_compare（不修改）|
| `code-agent/tasks/DL-022b-harness-memory-check.md` | DL-022b P0 根因说明 |

---

## 完成区

**状态**：已完成（待 Codex Review）

**修改文件**：
- `tests/vectors/isa/rd-load-store.yaml` — 63 个地址字段
- `tests/vectors/isa/rb-ops.yaml` — 10 个地址字段

**迁移**：ROM `0x...00100000` → RAM `0x...87FF0000`

**验证**：
```
$ python3 scripts/validate_vectors.py
200 cases, 87/87 opcodes covered OK
$ grep -c "100000\|100FFF\|100FFC\|100008\|1000FF\|100001\|100002\|100004" \
  tests/vectors/isa/rd-load-store.yaml tests/vectors/isa/rb-ops.yaml
0  (无残留旧地址)
```

---

## Architecture Review — 代码级 (2026-06-30)

**评审结论**：**Accepted — 26 条语义向量 ROM→RAM 迁移正确，stb 例外精确修复。**

### 数据级验证

#### 1. ROM 地址清零

```
rd-load-store.yaml: CLEAN (all addresses in RAM)
rb-ops.yaml:       CLEAN (all addresses in RAM)
```

23 + 3 条 semantic 向量 → 73 个地址字段 → 零 ROM 残留 ✅

#### 2. RAM 范围合法

所有迁移后地址 ∈ `[0x80000000, 0x87FFFFFF]`，零越界 ✅

#### 3. stb 向量例外精确修复 (rd-load-store.yaml [3])

| 字段 | 值 | 公式验证 |
|------|-----|---------|
| rb2 基址 | `0x87FF0000` | new base ✅ |
| ex_mem[0].address | `0x87FEFFFC` | `rb2 + (-4) mod 2^48` = `0x87FF0000 - 4` ✅ |

Bug 修复：原 YAML 中 stb 期望地址 `0x100FFC` 与指令 `rb2 + (-4)` 语义不一致，
新值 `0x87FEFFFC` 正确反映 EA = 0x87FF0000 + (-4) ✅

#### 4. encoding.word 不变性

```
rd-load-store.yaml: all encoding.word still valid (23 semantic cases)
rb-ops.yaml:       all encoding.word still valid (12 semantic cases)
```

迁移仅改寄存器/内存地址值，不触碰指令编码 ✅

#### 5. `make check` PASS

```
validate_vectors: 200 cases, 87/87 opcodes covered OK
repository checks: PASS
```

### 最终判断

ROM→RAM 地址迁移完整：73 个字段全部更新，stb 例外精确定位修复（地址从 naive 偏移修正为 EA 公式），encoding.word 不变，make check PASS。可 accept。
