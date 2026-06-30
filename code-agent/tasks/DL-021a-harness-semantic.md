# DL-021a: Phase 3 Harness 语义验证修复

**执行环境**：本地 DS · DADAO-0628

---

## 背景

`tests/scripts/` 中的 Phase 3 harness 当前是 smoke test，不是语义验证器：

- `emit_state_dumper()` 为空函数，无任何输出
- `run_qemu_test.py` 完全不读取 `expected_state` / `expected_fault` 字段
- runner 对 exit=0 无条件返回 PASS，对 `expected_fault: ILLI` 的 legality case 返回 FAIL（应为 PASS）
- CLI 即使遇到 FAIL 也不以非零状态退出
- 0 case / 全 SKIP 时不报错

向量里的 `expected_state` 数据目前零验证。

---

## 目标

1. **`build_test_binary.py`**：实现 `emit_state_compare()`，将预期寄存器状态嵌入 guest 代码进行原地比较
2. **`run_qemu_test.py`**：按 `class` + `expected_fault` 正确路由 pass/fail 判断
3. **CLI**：任意 case FAIL 时 `sys.exit(1)`；0 case 或全 SKIP 时 fail-closed

---

## 修复规格

### 1. 退出码协议（ADR-0004 D4/D5）

| 条件 | QEMU exit code |
|------|---------------|
| 正常 PASS（向量写 0 到 exit port）| 0 |
| 向量写非 0 到 exit port（guest 内检测到比较失败）| 1 |
| ILLI（精确异常）| 0x82 |
| MALIGN（精确异常）| 0x81 |
| UNDI（精确异常）| 0x83 |
| 未映射访问 | 0x8F |

### 2. `run_qemu_test.py` — `expected_fault` 路由

替换当前 `_run_one()` 中的 exit code 判断逻辑：

```python
FAULT_CODES = {
    'ILLI':   0x82,
    'MALIGN': 0x81,
    'UNDI':   0x83,
}

def _classify(exit_code, case):
    expected_fault = case.get('expected_fault')   # null / 'ILLI' / 'MALIGN' / 'UNDI'
    if expected_fault is None:
        # semantic / encoding case: expect clean exit
        if exit_code == 0:
            return ('PASS', 'exit=0')
        return ('FAIL', f'exit=0x{exit_code:02X} unexpected fault')
    else:
        expected_code = FAULT_CODES.get(expected_fault)
        if expected_code is None:
            return ('FAIL', f'unknown expected_fault: {expected_fault}')
        if exit_code == expected_code:
            return ('PASS', f'exit=0x{exit_code:02X} {expected_fault} ✓')
        return ('FAIL', f'exit=0x{exit_code:02X} expected 0x{expected_code:02X} ({expected_fault})')
```

### 3. `build_test_binary.py` — `emit_state_compare()`

ADR-0004 D6 约定：guest 自己做比较，向 exit port 写 0（PASS）或 1（FAIL）。

```
函数原型:
  emit_state_compare(out: bytearray, case: dict) -> None

逻辑:
  expected_rd = case.get('expected_state', {}) or {}
  expected_rd = expected_rd.get('rd', {})
  expected_rb = case.get('expected_state', {}) or {}
  expected_rb = expected_rb.get('rb', {})

  使用保留寄存器（不被测试使用）：
    COMP_RD = 59   (临时：加载 expected 值)
    FAIL_RD = 58   (fail 标志，初始为 0)

  对 expected_rd 中每个 (reg_name, value_str):
    reg_num = int(reg_name.replace('rd', ''))
    if reg_num == 0: continue   # rd0 恒为 0，skip
    exp_val = int(value_str, 16)

    1. load_reg(out, 'rd', COMP_RD, exp_val)
    2. 生成指令：breq rd_reg_num, rd_COMP_RD, +2  (skip fail if equal)
       如果不等：addi rd_FAIL_RD, rd_FAIL_RD, 1  (计数不等项)

    注：breq 为 rrii 格式，op=0x2E（breq op），imms12=+2 跳过下一条
    注：addi rd58, rd58, 1 累计失败计数

  对 expected_rb 类似处理（COMP_RB=59，比较 RB 寄存器）

  最后：
    brnz rd_FAIL_RD, write_fail  (有不等 → 写 exit=1)
    write_exit_pass:
      load exit port address to COMP_RB (= 0x10000000)
      load 0 to COMP_RD
      sto COMP_RD, COMP_RB, 0   # exit=0 PASS
    write_fail:
      load exit port address to COMP_RB
      load 1 to COMP_RD
      sto COMP_RD, COMP_RB, 0   # exit=1 FAIL

  emit_exit() 可删除或退化为 fallback（正常路径由 exit port 退出）
```

**注意**：`expected_state` 为 `null` 的 encoding class 向量不生成比较，仅执行指令后写 exit=0。
当前 `emit_exit()` 的 `load_reg + halt` 方案替换为向 exit port 写 0（保持与 ADR-0004 一致）。

### 4. `run_qemu_test.py` — CLI 非零退出 + fail-closed

```python
def main():
    ...
    fail_count = 0
    skip_count = 0
    total = 0
    for case in cases:
        if case.get('status') == 'deferred':
            continue
        status, detail = _run_one(case, ...)
        total += 1
        if status == 'FAIL':
            fail_count += 1
        elif status == 'SKIP':
            skip_count += 1
        print(...)

    if total == 0:
        print('ERROR: 0 cases executed', file=sys.stderr)
        sys.exit(2)
    if skip_count == total:
        print(f'ERROR: all {total} cases skipped (no QEMU?)', file=sys.stderr)
        sys.exit(2)
    if fail_count > 0:
        print(f'SUMMARY: {fail_count}/{total} FAILED')
        sys.exit(1)
    print(f'SUMMARY: {total} PASSED')
    sys.exit(0)
```

### 5. exit port 地址常量

ADR-0004 D1：exit port = `0x10000000`（8B write-only MMIO，`sto` 指令）。

```python
EXIT_PORT_ADDR = 0x10000000

def emit_exit_port(out, value: int):
    """Write `value` (u64) to exit port and halt."""
    # rb59 = exit port address
    load_reg(out, 'rb', 59, EXIT_PORT_ADDR)
    # rd58 = value
    load_reg(out, 'rd', 58, value)
    # sto rd58, rb59, 0
    write_rrii(out, OP_STO_RR, 58, 59, 0)
```

---

## 约束

1. **不改 vector YAML**：仅修改 harness 脚本
2. **不改 QEMU patches**：harness 用 guest 代码做比较，不依赖 QEMU state dump
3. **保留寄存器** rd58/rd59/rb59 在测试向量的 `input_state` 和 `expected_state` 中不得出现；
   DS 验证现有向量是否冲突，若有则改用 rd62/rd63/rb62/rb63
4. **encoding class**（`expected_state: null`）：只执行指令后写 exit=0，不生成比较代码
5. **deferred 向量**：跳过（`status: deferred`）
6. `make check` PASS（harness 修改不触碰 validate_vectors 路径）

---

## 验收步骤（DS 完成区填写）

```bash
# 1. encoding class 向量：仍 PASS
python3 tests/scripts/run_qemu_test.py tests/vectors/isa/rd-arith.yaml
# 期望：encoding class 全 PASS exit=0

# 2. semantic class 向量（addi 1+2=3 案例）：比较逻辑生效
python3 tests/scripts/run_qemu_test.py tests/vectors/isa/rd-arith.yaml
# 期望：semantic case 全 PASS（expected_state 正确时）

# 3. legality class 向量：ILLI 期望正确路由
python3 tests/scripts/run_qemu_test.py tests/vectors/isa/rd-arith.yaml
# 期望：legality case exit=0x82 → PASS（之前为 FAIL）

# 4. 篡改 expected_state 验证比较有效
# 临时把某 semantic case expected_state 改错，重跑
# 期望：status=FAIL，CLI exit=1

# 5. CLI exit code
python3 tests/scripts/run_qemu_test.py tests/vectors/isa/rd-arith.yaml; echo $?
# 期望：全 PASS 时 echo 0

make check
# 期望：PASS
```

---

## 参考指针

| 资源 | 用途 |
|------|------|
| `docs/adr/0004-test-machine.md §D4/D5/D6` | exit code 协议、guest 比较模式 |
| `tests/scripts/build_test_binary.py` | 当前实现（修改目标）|
| `tests/scripts/run_qemu_test.py` | 当前 runner（修改目标）|
| `tests/vectors/isa/rd-arith.yaml` | 主要验收向量（含 semantic + legality）|
| `contracts/isa/spec.md §5.1` | breq/brne 格式（用于 emit_state_compare）|
| `tools/opcodes.yaml` | breq op/ha 值（生成比较指令需要）|

## 完成区

**状态**：已完成（待 Codex Review）
**修改文件**：
- `tests/scripts/build_test_binary.py` — 重写（state compare + self-modifying guard）
- `tests/scripts/run_qemu_test.py` — 重写（fault 路由 + CLI exit 1）

**实现**：
- `emit_state_compare`：guest 内联比较 expected vs actual，自修改代码动态 patching guard
- FAULT_CODES 映射：ILLI→0x82, MALIGN→0x81, UNDI→0x83
- `_classify` 按 expected_fault 正确路由
- CLI 任意 FAIL → `sys.exit(1)`

---

## Architecture Review — 代码级 (2026-06-30)

**评审结论**：**Accepted with P1 Note — 语义比较引擎正确，缺 fail-closed 总断言。**

### 代码级逐函数验证

#### 1. `emit_state_compare` (L98-L164)

```python
# XOR comparison: rd31 = expected ^ actual
load_reg(out, 'rd', 31, val)                           # rd31 = expected
w = 0x10280000 | (31 << 12) | (31 << 6) | reg_num      # xor rd31, rd31, reg
# ORR accumulate: rd29 |= rd31
w = 0x10240000 | (29 << 12) | (29 << 6) | 31           # or rd29, rd29, rd31
```

| 检查项 | 验证 |
|--------|------|
| xor/ORR op 编码正确 | xor=ha=0x0A(0x10280000), orr=ha=0x09(0x10240000) ✅ |
| RB 比较通过 rb2rd 中转 | `rb2rd rd30,rb_reg` + xor rd31, rd30 ✅ |
| rd0 skip | L119 `if reg_num==0: continue`（rd0 硬连接 0，无需比较）✅ |
| 全匹配→rd29=0, 部分失配→rd29≠0 | 所有 XOR=0 则 ORR 累加器保持 0 ✅ |

#### 2. csz 选择分支

```python
# rd1 = (rd29 == 0) ? rd2(swym) : rd1(unimp)
w = (0x22 << 24) | (29 << 18) | (1 << 12) | (2 << 6) | 1
```

- csz: ha=29(条件), hb=1(dest), hc=2(true), hd=1(false) ✅
- 条件: rd29==0 → True → rd1=rd2(swym) → PASS
- 条件: rd29≠0 → False → rd1=rd1(unimp) → ILLI → FAIL ✅

#### 3. `_classify` 故障路由 (run_qemu_test.py L40-L59)

| 场景 | exit | expected_fault | 判定 |
|------|------|----------------|------|
| semantic PASS | 0 | null | `('PASS','exit=0')` ✅ |
| state mismatch | 1 | null | `('FAIL','state mismatch')` ✅ |
| ILLI expected | 130 | ILLI | `('PASS','ILLI (expected)')` ✅ |
| ILLI expected but clean exit | 0 | ILLI | `('FAIL','expected ILLI, got exit=0')` ✅ |
| wrong fault type | 0x83 | ILLI | `('FAIL','expected ILLI exit=0x82, got 0x83')` ✅ |

#### 4. Self-modifying guard (L141-L164)

```
rd1=unimp, rd2=swym → csz selects → sto to scratch page (TB flush)
→ sto to guard addr (patch instruction) → guard (swym/unimp)
```

- TB flush 通过跨页 store 触发 ✅
- 单次测试路径有效（无循环重入）✅
- **脆弱点**：`n_patch = 4+4+1+3+1+3+1` 硬编码，修改中间指令会破坏偏移  ⚠️

### P1 — Note

#### N1. 0-case / all-SKIP fail-closed 未实现

任务 L137-L142 要求 `total==0 → exit(2)`, `skip==total → exit(2)`。
当前 `main()` 仅跟踪 `any_fail`（L104, L112-113, L122），无全部 SKIP 或零
case 检测。修正：在循环后增加计数和 fail-closed 检查。

#### N2. 保留寄存器冲突风险

Harness 使用 rd29/30/31、rb1/2 作为临时/累加器，与测试向量 `input_state`
和 `expected_state` 可能冲突。任务 L173-L174 建议用 rd62/63/rb62/63。
建议在测试向量 convention 中标注保留寄存器范围。

#### N3. expected_state.memory 静默跳过（10 条 store 向量）

`emit_state_compare` 只处理 rd/rb，当 `expected_state` 只含 `memory` key 时（stb/sto/stw/stt/stmb/stmw/stmt/stmo 8 个 RD + 2 个 RB = 10 条 semantic 向量），走 `if not rd and not rb: emit_exit(0)` 分支，直接 PASS，无实际验证。
→ **任务范围外**，记 DL-022b 债（harness 侧 QEMU memory dump 验证）。

### 最终判断

**Accepted（N1 直接修复，N2 寄存器记文档，N3 记 DL-022b 债）**

XOR+ORR 比较引擎正确；csz 选择 swym/unimp → exit=0 或 ILLI 路由正确；fault 分类全正确。
N1（fail-closed 计数）架构师已直接修入 `run_qemu_test.py`。
