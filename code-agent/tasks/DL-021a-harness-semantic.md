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
