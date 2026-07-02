# §5 Harness 二进制协议

**来源**：DL-019a, DL-021a, DL-022b, DL-029a, DL-030a review（2026-07-02）  
**交叉验证**：tests/scripts/build_test_binary.py, run_qemu_test.py

---

## §5.1 二进制布局

测试二进制通过 raw encoding.word 直接构建，不依赖 LLVM 汇编器：

```
[section 1] loader   ← setzw/orw 加载 input_state 寄存器值
[section 2] memory   ← setzw + sto 写入 input_state.memory（如存在）
[section 3] test     ← struct.pack('>I', encoding_word) 指令字
[section 4] compare  ← XOR/ORR 比较 + CSZ guard + self-modifying patch
[section 5] exit     ← halt rd62（写 exit port → QEMU shutdown）
```

## §5.2 退出码协议（ADR-0004）

| 条件 | QEMU exit code |
|------|---------------|
| PASS（guest 写 0 到 exit port） | 0 |
| FAIL（guest 写 1 到 exit port） | 1 |
| ILLI（精确异常） | 0x82 |
| MALIGN | 0x81 |
| UNDI | 0x83 |
| IALIGN | 0x84 |
| RASOF | 0x85 |
| RASUF | 0x86 |
| 未映射访问 | 0x8F |

run_qemu_test.py 的 `_classify()` 按 `expected_fault` 路由：
- expected_fault 为 null：exit=0 → PASS，其他 → FAIL
- expected_fault 非 null：exit 匹配预期码 → PASS，不匹配 → FAIL

## §5.3 语义比较引擎（emit_state_compare）

**算法**：XOR 预期值与实际值 → ORR 累加入 rd29 → CSZ 选择 guard

```
1. rd29 初始化为 0（失配累加器）
2. 对每个 expected_state.rd 条目：
   a. load_reg rd31 = 预期值
   b. xor rd31, rd31, actual_reg    # rd31 = 预期 ^ 实际（匹配时为 0）
   c. or  rd29, rd29, rd31          # rd29 |= 失配位
3. 对每个 expected_state.rb 条目：
   a. rb2rd rd30, actual_rb         # 复制 RB 到 RD
   b. 同 RD 比较逻辑
4. 对每个 expected_state.memory 条目：
   a. load_reg rb30 = 地址
   b. ldbu/ldwu/ldtu/ldo rd30, rb30, 0  # 无符号 load
   c. 同 RD 比较逻辑
5. CSZ guard：
   a. rd1 = unimp (FAIL), rd2 = swym (PASS)
   b. csz rd1, rd29, rd2, rd1  # rd29==0 → rd1=swym, 否则 rd1=unimp
   c. sto 到 scratch page（强制 TB exit + guard patching）
```

**保留寄存器**：rd29（累加器）、rd30（临时）、rd31（临时）、rb30（临时）。
测试向量不应在 input_state / expected_state 中使用这些寄存器。

## §5.4 分支语义测试（Poison Pattern）

**taken pattern**：
```
[setup] → [branch +1] → [unimp poison] → [exit(0)]
```
- 跳转发生 → 跳过 unimp → exit=0 → PASS
- 跳转失败 → 执行 unimp → ILLI → FAIL

**not_taken pattern**：
```
[setup] → [branch +1] → [exit(0)] → [unimp poison]
```
- 未跳转 → 顺序执行 → exit=0 → PASS
- 误跳转 → 跳过 exit → 执行 unimp → ILLI → FAIL

**YAML 标记**：`branch_behavior: taken` 或 `branch_behavior: not_taken`

**jump_r iiir setup**：
```python
load_reg(buf, 'rb', ha, BINARY_BASE)    # base = 0x80000000
offset = pos_after_rb + 16 + 4 + 4      # 跳过 load_reg + jump_r + unimp
load_reg(buf, 'rd', hb, offset)         # target = base + offset
```

## §5.5 halt 指令（op=0x00）

合成 halt 指令（op=0x00, riii 格式，ha=rd_src）：
- trans_halt 读取 rd[ha]，调用 gen_helper_exit 写入 exit port
- `build_test_binary.py` 使用 `emit_exit(code)` → load rd62 = code → halt rd62
- ha == 0（rd0 作为源）→ ILLI

## §5.6 call/ret 组合测试（call_ret pattern）

`branch_behavior: call_ret` 触发 `emit_call_ret_pattern()`，用于验证 call 压栈 + ret 弹栈的完整往返：

```
pos 0-3:   call_i +5          ra[63] = pos0+4 = 4（ret_landing）
                               target  = pos0+4 + 5*4 = 24（subr）
pos 4-23:  emit_exit(0)       ← ret_landing：ret 弹回到这里 → PASS
pos 24-27: ret rd_retval, 0   → ra[63] = 4 → 跳回 ret_landing
pos 28-47: emit_exit(0xAB)    ← poison：不应到达
```

**PC 算术**（依赖 §1.3 公式）：
- call_i imm=+5：`ra[63] = pc_next+4 = 4`；`target = pc_next+4 + 20 = 24` ✓
- ret imm=0：`PC = ra[63] + 0 = 4` → 落在 emit_exit(0) ✓

`emit_exit(0)` = load_reg rd62 0（4 wydes=16B）+ halt（4B）= 20B，占 pos4-23 ✓

此 pattern 隐式验证了 ra[63] 压栈/弹栈的正确性，无需 expected_state.ra 字段支持。
