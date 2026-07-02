# DL-035a: LLVM AsmParser — 添加 halt + 修正 smoke .s 助记符

**执行环境**: 本地 DS · DADAO-0628

**状态**: 待执行

---

## 背景

当前 `llvm-mc -triple=dadao -filetype=obj` 在汇编 `halt rd1` 时报：
```
error: Unrecognized instruction mnemonic
halt rd1
^
```

根因：`halt` 指令在 `DADAOInstrInfo.td` 中**完全缺失**（未定义）。

同时，smoke 测试文件使用了错误助记符：
- `jump_i 1` → LLVM 使用 `"jump $imm24"`（助记符 `jump`，非 `jump_i`）
- `call_i N` → LLVM 使用 `"call $imm24"`（助记符 `call`，非 `call_i`）

已确认在 MnemonicTable（`DADAOGenAsmMatcher.inc`）中：
- `addi` ✅、`add` ✅（4 寄存器格式 `"add $rdha, $rdhb, $rdhc, $rdhd"`）
- `jump` ✅、`call` ✅
- `halt` ❌（缺失）

---

## 目标

1. 在 `DADAOInstrInfo.td` 中添加 `halt` 指令定义
2. 更新 `tests/e2e/smoke_jump.s`（`jump_i` → `jump`）
3. 重新构建 LLVM（增量）
4. 验证完整 E2E 流程：`llvm-mc -filetype=obj` → ELF → raw binary → QEMU exit=42/0

---

## 接口说明书

### 1. 添加 halt 到 InstrInfo.td

**路径**：`.work/source/llvm/llvm/lib/Target/DADAO/DADAOInstrInfo.td`

`halt` ISA 规格（§3.1 spec.md）：
- opcode = 0x00，format = riii，ha = rd 源寄存器（exit code），imm18 = 0（ignored）
- ha=0 → ILLI（QEMU 已处理，LLVM 端无需特判）
- 编码：`[0x00:8][ha:6][0:18]` = `(0x00 << 24) | (ha << 18)`

建议定义（在 swym 附近添加）：
```tablegen
let op = 0x00 in
def HALT : F_RIII_RD<(outs), (ins GPRD:$rdha, imms18:$imm18),
                     "halt $rdha, $imm18", []>;
```

**注意**：
- opcode 0x00 已被 `swym`（F_OIII format，ha 固定=0）使用
- `halt` 是 F_RIII_RD（ha 可变），两者助记符不同，AsmMatcher 通过助记符区分，无冲突
- 若 TableGen 报编码冲突，可加 `let DecoderNamespace = "halt"` 或用 `DisableDecoder`

**或者**（如 imm18 不需要用户指定）：
```tablegen
let op = 0x00 in
def HALT : F_RIII_RD<(outs), (ins GPRD:$rdha), "halt $rdha", []> {
  let imm18 = 0;
}
```

DS 根据 TableGen 报错选择方案，确保最终 `halt rd1` 可汇编。

### 2. 更新 smoke .s 文件

**`tests/e2e/smoke_jump.s`**：将 `jump_i 1` 改为 `jump 1`

**`tests/e2e/smoke_arith.s` 和 `smoke_add.s`**：保持不变（`addi`/`add`/`halt` 助记符符合 LLVM 格式，待 halt 加入后直接可用）

### 3. 重建 LLVM

```bash
# 仅重建 llvm-mc（增量，约 2-5 分钟）
make -C .work/build/llvm llvm-mc -j$(nproc)
```

确认 `DADAOGenAsmMatcher.inc` 中出现 `halt` 字样：
```bash
grep "halt" .work/build/llvm/lib/Target/DADAO/DADAOGenAsmMatcher.inc
```

### 4. 验证完整 E2E 流程

```bash
LLVM_MC=.work/build/llvm/bin/llvm-mc
LLVM_OBJCOPY=.work/build/llvm/bin/llvm-objcopy
QEMU=.work/source/qemu/build/qemu-system-dadao
TRAMPOLINE=tests/scripts/trampoline.bin

# 场景 A: 算术
$LLVM_MC -triple=dadao -filetype=obj -o /tmp/a.o tests/e2e/smoke_arith.s
$LLVM_OBJCOPY -O binary --only-section=.text /tmp/a.o /tmp/a.bin
$QEMU -M dadao-m1 -bios $TRAMPOLINE -kernel /tmp/a.bin -display none -nographic 2>/dev/null
echo "smoke_arith exit=$?"   # 期望 42

# 场景 B: add
$LLVM_MC -triple=dadao -filetype=obj -o /tmp/b.o tests/e2e/smoke_add.s
$LLVM_OBJCOPY -O binary --only-section=.text /tmp/b.o /tmp/b.bin
$QEMU -M dadao-m1 -bios $TRAMPOLINE -kernel /tmp/b.bin -display none -nographic 2>/dev/null
echo "smoke_add exit=$?"   # 期望 42

# 场景 C: jump（用修正后的 smoke_jump.s）
$LLVM_MC -triple=dadao -filetype=obj -o /tmp/c.o tests/e2e/smoke_jump.s
$LLVM_OBJCOPY -O binary --only-section=.text /tmp/c.o /tmp/c.bin
$QEMU -M dadao-m1 -bios $TRAMPOLINE -kernel /tmp/c.bin -display none -nographic 2>/dev/null
echo "smoke_jump exit=$?"   # 期望 0
```

**交叉验证**：smoke_arith.bin 应与 `gen_e2e_binary.py smoke_arith` 输出字节完全一致：
```bash
python3 tests/scripts/gen_e2e_binary.py smoke_arith /tmp/ref_arith.bin
diff <(xxd /tmp/a.bin) <(xxd /tmp/ref_arith.bin)
# 应无差异
```

### 5. 更新 lit 测试（如 E2E 验证通过）

更新 `tests/lit/E2E/smoke_arith.test` 和 `smoke_add.test`：将 `%binbuilder` 路径改为用 `%llvm-mc` + `%llvm-objcopy`（可选，若 lit 配置允许）。

---

## 约束

- 只修改 `.work/source/llvm/llvm/lib/Target/DADAO/DADAOInstrInfo.td` 和 `tests/e2e/smoke_jump.s`
- 不改 smoke_arith.s / smoke_add.s（助记符已正确）
- 不添加 LLVM 指令 alias（保持 1:1 对应 ISA mnemonic）
- 不修改 QEMU 相关文件

---

## 验收

```bash
# 1. halt 在 AsmMatcher 中
grep "halt" .work/build/llvm/lib/Target/DADAO/DADAOGenAsmMatcher.inc | head -2

# 2. 三场景全部正确退出
python3 tests/scripts/run_e2e.py $QEMU $TRAMPOLINE /tmp/a.bin; [ $? -eq 42 ]
python3 tests/scripts/run_e2e.py $QEMU $TRAMPOLINE /tmp/b.bin; [ $? -eq 42 ]
python3 tests/scripts/run_e2e.py $QEMU $TRAMPOLINE /tmp/c.bin; [ $? -eq 0 ]

# 3. 字节一致性验证（smoke_arith）
diff <(xxd /tmp/a.bin) <(xxd /tmp/ref_arith.bin) && echo "MATCH"

# 4. 回归：全套 QEMU 测试不退步
for f in tests/vectors/isa/*.yaml; do
  python3 tests/scripts/run_qemu_test.py $f 2>&1 | grep -c "^FAIL\|^TIMEOUT" | grep -v "^0" && echo "FAIL: $f"
done
echo "回归: 0 failures"
```

---

## 参考指针

- 知识库 §2（ISA 编码规则，halt opcode=0x00 格式 riii）
- `DADAOInstrInfo.td`：`.work/source/llvm/llvm/lib/Target/DADAO/DADAOInstrInfo.td`
- `DADAOGenAsmMatcher.inc`（生成）：`.work/build/llvm/lib/Target/DADAO/DADAOGenAsmMatcher.inc`
- gen_e2e_binary.py（参考编码）：`tests/scripts/gen_e2e_binary.py`
- smoke 汇编源：`tests/e2e/smoke_arith.s`, `smoke_add.s`, `smoke_jump.s`

---

## 完成区

（DS 填写）
