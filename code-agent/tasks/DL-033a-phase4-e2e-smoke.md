# DL-033a: Phase 4 MC↔QEMU 端到端冒烟测试

**执行环境**: 本地 DS · DADAO-0628

**状态**: 待执行（DL-032a 完成后可并行）

---

## 背景

Phase 2（LLVM MC）和 Phase 3（QEMU scalar core）均已完成。本任务是 **Phase 4 的首个里程碑**：验证 llvm-mc 汇编的 DADAO 二进制能在 qemu-system-dadao 上正确执行。

当前工具链：
- `llvm-mc`：`.work/build/llvm/bin/llvm-mc`
- `qemu-system-dadao`：`.work/source/qemu/build/qemu-system-dadao`
- trampoline：`tests/scripts/trampoline.bin`（ROM @ 0x100000，跳转到 0x80000000）

---

## 目标

1. **编写 3 条 DADAO 汇编冒烟测试**（覆盖算术、load/store、控制流各一）
2. **用 llvm-mc 汇编** → 生成 raw binary
3. **QEMU 运行** → 验证正确退出
4. **写入 lit 测试** 固化为 Phase 4 门控

---

## 接口说明书

### 1. 测试场景

#### 场景 A：算术（addi + halt）

```asm
# tests/e2e/smoke_arith.s
# addi rd1, rd0, 42  → rd1 = 42
# halt rd1           → exit 42
.text
addi rd1, rd0, 42
halt rd1
```

期望：QEMU exit code = 42

#### 场景 B：RD 算术 + 比较（add + halt）

```asm
# tests/e2e/smoke_add.s
# rd1 = 10, rd2 = 32; add rd0,rd3,rd1,rd2; rd3 = 42
addi rd1, rd0, 10
addi rd2, rd0, 32
add  rd0, rd3, rd1, rd2
halt rd3             # exit 42
```

期望：exit code = 42

#### 场景 C：无条件跳转

```asm
# tests/e2e/smoke_jump.s
# jump_i 到 ok 跳过错误路径
jump_i  1           # +1 = 跳过 halt rd1（exit 1）
halt    rd1         # 不应到达
addi    rd1, rd0, 0
halt    rd1         # exit 0
```

期望：exit code = 0

**注意**：offset 单位为 word（4 bytes）。`jump_i 1` = 跳到 PC+4+4 = PC+8（跳过 `halt rd1`）。

### 2. llvm-mc 汇编命令

```bash
LLVM_MC=.work/build/llvm/bin/llvm-mc

$LLVM_MC -triple=dadao -filetype=obj -o smoke_arith.o tests/e2e/smoke_arith.s
# 或 raw binary（如果支持）：
$LLVM_MC -triple=dadao -filetype=asm --show-encoding tests/e2e/smoke_arith.s
```

DS 需要确认 llvm-mc 对 DADAO triple 能正常解析汇编。若需要显式 `--arch=dadao` 或其他参数，以实际报错调整。

从 ELF 提取 `.text` 段（若 llvm-mc 仅输出 ELF）：
```bash
llvm-objcopy -O binary --only-section=.text smoke_arith.o smoke_arith.bin
```

### 3. QEMU 运行命令

```bash
QEMU=.work/source/qemu/build/qemu-system-dadao
TRAMPOLINE=tests/scripts/trampoline.bin

$QEMU -M dadao-m1 -bios $TRAMPOLINE -kernel smoke_arith.bin \
      -display none -nographic 2>/dev/null
echo "exit: $?"
```

期望：`exit: 42`（场景 A）

### 4. lit 测试固化

在 `tests/lit/E2E/` 下为每个场景写 lit 文件：

```
// RUN: %llvm-mc -triple=dadao -filetype=obj -o %t.o %s
// RUN: llvm-objcopy -O binary --only-section=.text %t.o %t.bin
// RUN: %qemu -M dadao-m1 -bios %trampoline -kernel %t.bin \
// RUN:       -display none -nographic 2>/dev/null; [ $? -eq 42 ]
```

DS 需在 `tests/lit/E2E/lit.cfg` 中配置 `%qemu` 和 `%trampoline` 替换变量。

### 5. 调试指引

若 llvm-mc 报 "unknown target"：
- 确认 LLVM build 含 DADAO target：`llvm-mc --version | grep dadao`（或 `--print-supported-cpus`）

若 QEMU exit code 为 0x82（ILLI）而非预期值：
- 说明指令编码与 insn.decode 不匹配
- 用 `llvm-objdump -d` 反汇编检查 opcode 字节

若 QEMU 无输出/hang：
- 可能是 trampoline 没跳到 0x80000000，或 kernel binary 格式不对
- 尝试 `-d in_asm` 看 TCG trace

---

## 约束

- 优先用 **最小测试**（能 PASS 就算里程碑），不要求覆盖所有指令
- `tests/e2e/` 为新目录，lit 测试放 `tests/lit/E2E/`
- 不修改 `tests/vectors/isa/*.yaml`（QEMU unit test 维持独立）
- 知识库引用：§1（translate 约定）、§5（harness 协议）、§6（内存映射）

---

## 验收

```bash
# 手动验证
.work/source/qemu/build/qemu-system-dadao \
  -M dadao-m1 -bios tests/scripts/trampoline.bin \
  -kernel tests/e2e/smoke_arith.bin \
  -display none -nographic 2>/dev/null
echo $?   # 应输出 42

# lit 验证
llvm-lit tests/lit/E2E/   # 所有场景 PASS
```

**里程碑标志**：任意一个场景 llvm-mc 汇编 + QEMU 正确退出 = Phase 4 解锁。

---

## 参考指针

- 知识库 §5.1（binary 布局）、§6（机器内存映射，BINARY_BASE=0x80000000）
- ADR-0004（Test Machine 规范）：`docs/adr/0004-test-machine.md`
- 现有 lit 配置：`tests/lit/MC/Dadao/lit.cfg`（可参考 %llvm-mc 配置方式）
- insn.decode：`.work/source/qemu/target/dadao/insn.decode`（验证编码）
- QEMU 运行脚本参考：`tests/scripts/run_qemu_test.py`（`_run_qemu` 函数）

---

## 完成区

（DS 填写）
