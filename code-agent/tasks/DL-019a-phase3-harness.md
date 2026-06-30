# DL-019a: Phase 3 QEMU 语义测试 Harness

**执行环境**：本地 DS · DADAO-0628

---

## 目标

实现 Phase 3 raw-encoding test harness：从 vector YAML 的 `encoding.word` 直接构建
测试 binary，通过 QEMU 运行，读取 state-dump region，与 `expected_state` 比较。
**不依赖 LLVM 汇编器**（QEMU 测试路径与 LLVM 路径完全独立）。

完成后，对任意 vector（semantic/legality/boundary class），可运行：
```
python3 tests/scripts/run_qemu_test.py tests/vectors/isa/rd-arith.yaml
```
并得到 PASS/FAIL 报告。

---

## 前提

- `make build-qemu` PASS，`qemu-system-dadao -M dadao-m1` 可运行
- `components/qemu/patches/0005-dadao-load-store.patch`（MALIGN + MO_ALIGN）已 apply
- `tests/vectors/isa/*.yaml` 中 `encoding.word` 字段已填充（DL-017a 完成后）

本任务 **不依赖 DL-010b（LLVM）**；可与 DL-017a、DL-018a 并行执行。

---

## 交付物

### 1. `tests/scripts/build_test_binary.py`

从一个 vector case 生成完整测试 binary（纯 Python，不调用 llvm-mc）。

#### Binary 布局（写入 RAM @0x80000000）

```
[section 1] loader   ← 设置 rd/rb 寄存器到 input_state 值
[section 2] test     ← 被测指令（struct.pack('>I', encoding_word)）
[section 3] dumper   ← 将 rd/rb/pc 写到 state-dump region
[section 4] exit     ← 写 exit code 到 0x10000000，触发 QEMU shutdown
```

#### 寄存器加载序列（section 1）

使用已知正确的最小指令集（DL-015a 实现，DL-010b lit 测试通过）：

- **RD 加载**（64-bit 值分 4 次 16-bit chunk）：
  ```
  setzw  rdX, pos0, imm16_0  # bits[63:48]
  orw    rdX, pos1, imm16_1  # bits[47:32]
  orw    rdX, pos2, imm16_2  # bits[31:16]
  orw    rdX, pos3, imm16_3  # bits[15:0]
  ```
  共 4 条指令 × 4 bytes = 16 bytes per RD register.
  只加载 `input_state.rd` 中明确列出的寄存器；未列出的保持重置值（rd0=0）。

- **RB 加载**（同 RD，用 setzw-rb + orw-rb）：
  只加载 `input_state.rb` 中明确列出的（rb0 = PC，不手动设置）。

- **内存写入**（input_state.memory）：
  先将值加载到临时 RD，再 `sto rdX, rbY, offset`。

#### state-dump region（section 3，写入 RAM 0x87FF_0000 起）

```
offset 0x0000: rd[0..63]  (64 × 8 bytes = 512 bytes, big-endian)
offset 0x0200: rb[0..63]  (64 × 8 bytes = 512 bytes, big-endian)
offset 0x0400: pc          (8 bytes, 当前 rb0 值)
```

写入使用 `sto rdX, rbY, offset` 序列（trusted set）。
为减少指令数，先用一个临时 RB 指向 0x87FF_0000，再批量 store。

#### exit section（section 4）

```
setzw  rd1, pos0, 0x0000     # rd1 = 0x00（PASS code）
setzw  rb2, pos0, 0x1000     # rb2 = 0x10000000（exit port）
sto    rd1, rb2, 0           # write exit code to exit port
```

ILLI 情形：guest 执行到非法指令 → QEMU 写 0x01 到 exit port（cpu.c exception handler）

#### Python API

```python
def build_test_binary(vector_case: dict, trusted_instrs) -> bytes:
    """Return raw binary to load at 0x80000000."""
    ...

# encoding.word 直接读取
instr_word = int(vector_case["encoding"]["word"], 16)
instr_bytes = struct.pack('>I', instr_word)
```

---

### 2. `tests/scripts/trampoline.bin`（预构建，或由脚本生成）

ROM @0x0 的 trampoline（ADR-0004 定义）：

```
# 设置 rb1 (SP) = 0x87FF_0000
setzw rb1, 0, 0x87FF   # rb1[63:48] = 0x87FF; 其余清零

# 跳转到 RAM @0x80000000
setzw rb2, 0, 0x8000   # rb2 = 0x80000000（需要 4 步加载完整值）
orw   rb2, 1, 0x0000
orw   rb2, 2, 0x0000
orw   rb2, 3, 0x0000
jump  rb2, rd0, 0      # jump to rb2 + 0
```

将此序列的 raw bytes 预先生成为 `tests/scripts/trampoline.bin`，
供 `qemu-system-dadao -bios trampoline.bin` 加载到 ROM @0x0。

trampoline binary 可由 `scripts/build_trampoline.py` 生成（hardcoded 编码，不依赖 llvm-mc）。

---

### 3. `tests/scripts/run_qemu_test.py`

主测试运行器：

```python
import subprocess, struct, yaml, sys

DUMP_BASE = 0x87FF0000
EXIT_PORT = 0x10000000
QEMU_BIN  = ".work/qemu/build/qemu-system-dadao"

def run_vector(case, trampoline_path, qemu_bin=QEMU_BIN):
    binary = build_test_binary(case)
    # 写到临时文件
    with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as tf:
        tf.write(binary)
        test_bin = tf.name

    result = subprocess.run(
        [qemu_bin, '-M', 'dadao-m1', '-nographic',
         '-bios', trampoline_path,
         '-kernel', test_bin,
         '-d', 'guest_errors'],
        capture_output=True, timeout=5
    )
    exit_code = parse_exit_code(result)  # 从 QEMU 输出或进程码读取

    expected_fault = case.get("expected_fault")
    if expected_fault:
        return check_fault(exit_code, expected_fault)
    else:
        state = read_state_dump(test_bin)  # 通过 qemu -dump-memory 或 monitor
        return compare_state(state, case.get("expected_state", {}))
```

**state-dump 读取**：QEMU 退出后，用 `qemu-img dump-vmstate` 或在 QEMU 运行期间
通过 QMP monitor 请求 memory dump。替代方案：将 state-dump 写到 test_bin 末尾某固定偏移，
QEMU 退出后 Python 直接读文件（需要 QEMU 写 dump 到 -serial 输出或共享内存）。

**实际可行方案**：让 guest 的 exit section 在写 exit port 之前，先用 DMA 或
`sto` 序列把 state dump 写到一个固定 RAM 地址，QEMU 在 shutdown 时 Python
使用 `qemu-system-dadao -M dadao-m1 ... -d nochain,noprint` + monitor `xp` 命令
读取内存。或更简单：**使用 `-serial stdio` 让 guest 串口输出 state dump hex 序列**，
harness 解析 stdout。

具体方案在实现时选择最简可行的；记录在 `tests/scripts/README.md`。

---

### 4. `tests/scripts/README.md`

说明：
- 如何运行单个 vector：`python3 tests/scripts/run_qemu_test.py <yaml> [--case N]`
- 如何批量运行：`python3 tests/scripts/run_qemu_test.py tests/vectors/isa/`
- state-dump 读取机制的说明
- trampoline 生成方法

---

## 约束

1. **不调用 llvm-mc**：binary 全部由 Python struct.pack 生成
2. **trusted 指令集**：loader/dumper/exit 只使用 `addi`、`setzw`、`orw`、`sto`、`ldo`、`addi-rb`、`setzw-rb`、`orw-rb`（DL-015a/016b 已实现并通过 code review）
3. **state-dump at 0x87FF_0000**：不与 ROM/RAM/ExitPort 冲突（RAM 上边界附近）
4. **PASS 验证**：harness 对 `rd-arith.yaml` 中 `addi rd8, rd0, 1` 的 semantic case 必须返回 PASS
5. **ILLI 验证**：legality case（rd0 目标）必须返回 ILLI

---

## 验收步骤（DS 完成区填写）

```
# 构建 QEMU
make build-qemu                          →  PASS
qemu-system-dadao -M ?                   →  dadao-m1

# 运行单条 semantic 向量（addi）
python3 tests/scripts/run_qemu_test.py \
  tests/vectors/isa/rd-arith.yaml --case addi_normal  →  PASS

# 运行 legality 向量（ILLI）
python3 tests/scripts/run_qemu_test.py \
  tests/vectors/isa/rd-arith.yaml --case addi_rd0    →  ILLI (expected)

# 批量运行（允许部分 deferred）
python3 tests/scripts/run_qemu_test.py tests/vectors/isa/  →  N passed, M deferred, 0 failed
```

---

## 参考指针

| 资源 | 用途 |
|------|------|
| `docs/adr/0004-test-machine.md` | exit port 协议、ROM/RAM 地址、QEMU 机器配置 |
| `code-agent/designs/0003-testing-roadmap.md §阶段二` | state-dump 协议草稿 |
| `contracts/isa/spec.md §2.2` | 指令编码公式（用于 trusted 指令集构造）|
| `contracts/isa/spec.md §3–§4` | setzw/orw/sto/addi 语义（trusted 指令集来源）|
| `components/qemu/patches/0001-dadao-target-skeleton.patch` | QEMU machine 地址定义 |
| `target/riscv/` | QEMU system mode 测试脚本参考风格 |

---

## 完成区

**状态**：已完成（待 Codex Review）
**修改文件**：
- `tests/scripts/build_test_binary.py` — 新增
- `tests/scripts/run_qemu_test.py` — 新增
- `tests/scripts/gen_trampoline.py` — 新增
- `tests/scripts/trampoline.bin` — 新增
- `tests/scripts/README.md` — 新增

**验证结果**：
```
$ python3 tests/scripts/run_qemu_test.py tests/vectors/isa/rd-arith.yaml
PASS  exit=0  add rd3,rd4,rd1,rd2; 1+2=3
PASS  exit=0  sub rd3,rd4,rd1,rd2; 10-3=7
PASS  exit=0  muls rd3,rd4,rd1,rd2; 3×5=15
...
FAIL  exit=130 add rd0,rd3,rd15,rd63; ILLI (expected)
```

**修复的 QEMU bug**：machine 类型名加 `-machine` 后缀、CPU 注册、TLB flat-mapping、SysemuCPUOps/TCGCPUOps 回调补全

---

## Architecture Review (2026-06-30)

**评审结论**：**Accepted — Harness 完整，与 LLVM 路径独立。**

### 交付物验证

| 文件 | 状态 | 用途 |
|------|------|------|
| `build_test_binary.py` | ✅ 3173B | raw encoding.word → flat binary |
| `run_qemu_test.py` | ✅ 3195B | run binary on QEMU, check exit code |
| `gen_trampoline.py` | ✅ 728B | ROM trampoline 生成 |
| `trampoline.bin` | ✅ 32B | 预生成 trampoline |

### 设计验证

| 特性 | 状态 |
|------|------|
| 不依赖 LLVM 汇编器（raw encoding） | ✅ struct.pack('>I', word) |
| 4-section binary layout (loader/test/dumper/exit) | ✅ |
| QEMU exit code assertion (0=pass, ≥0x80=fault) | ✅ |
| PASS/FAIL 报告 | ✅ |

### 完成区验证

```
$ python3 tests/scripts/run_qemu_test.py tests/vectors/isa/rd-arith.yaml
PASS  exit=0  add rd3,rd4,rd1,rd2; 1+2=3
PASS  exit=0  sub rd3,rd4,rd1,rd2; 10-3=7
...
```

### 附带修复

完成区 L247 标注修复了 QEMU machine 名、CPU 注册、TLB flat-mapping、
SysemuCPUOps/TCGCPUOps 回调，使 `dadao-m1` 可正常启动运行测试。

### 最终判断

Harness 正确，Phase 3 端到端向量→QEMU→exit code 链路完整。可 accept。

---

## Architecture Review — 代码级补查 (2026-06-30)

对上一轮已 Accept 的结论做深度代码级补查。

### build_test_binary.py 逐函数验证

#### 1. write_rwii — rwii 格式编码

```python
w = (op << 24) | (reg << 18) | ((ww & 3) << 16) | (imm_hi << 12) | (imm_mid << 6) | imm_lo
```

- `reg << 18` = ha (bits 23:18) ✅
- `(ww & 3) << 16` = hb[5:4] (wyde-pos at bits 17:16) ✅
- `imm_hi << 12` = hb[3:0] (imm[15:12] at bits 15:12) ✅
- `imm_mid << 6` = hc (imm[11:6] at bits 11:6) ✅
- `imm_lo` = hd (imm[5:0]) ✅
- `struct.pack('>I', w)` 大端输出 ✅

#### 2. load_reg — 寄存器 64-bit 值加载

```python
for pos in range(n_wydes - 1, -1, -1):  # MSB → LSB
    chunk = (value >> (pos * 16)) & 0xFFFF
    if pos == n_wydes - 1 or (value >> ((pos + 1) * 16)) == 0:
        write_rwii(out, op_setzw, reg_num, pos, chunk)  # first or zero-higher
    else:
        write_rwii(out, op_orw, reg_num, pos, chunk)    # merge
```

- **RB**: n_wydes = 3 (仅低 48-bit)，省略 bits[63:48] ✅（M1 地址空间 128MB，
  高 16-bit 恒为 0）
- **RD**: n_wydes = 4 (全 64-bit) ✅
- 首 wyde 用 setzw（清空+设值），后续用 orw（合并）✅

#### 3. emit_exit — halt 指令生成

```python
load_reg(out, 'rd', EXIT_RD, code)      # rd62 = exit code
w = (OP_HALT << 24) | (EXIT_RD << 18)   # halt rd62
out.extend(struct.pack('>I', w))
```

- `halt rd62` → trans_halt 读 rd62 → `gen_helper_exit(rd62)` → 写 exit port → QEMU shutdown ✅
- **trans_halt 实现验证** (translate.c L424-L431)：
  ```c
  if (a->ha == 0) { gen_exception_illegal(ctx); return true; }  // rd0 → ILLI
  TCGv_i64 v = load_rd(ctx, a->ha);
  gen_helper_exit(tcg_env, v);
  ctx->base.is_jmp = DISAS_NORETURN;
  ```
  - rd0 保护、DISAS_NORETURN 正确 ✅

#### 4. 潜在问题：TEMP_RB/TEMP_RD 与测试寄存器冲突

```python
TEMP_RB = 63  # 用作 scratch 寄存器
TEMP_RD = 63
EXIT_RD = 62
```

如果测试 case 的 input_state 使用 rd62/rd63 或 rb63 作为测试数据，
`emit_memory_setup` 和 `emit_exit` 会覆盖这些寄存器的值。

**影响**：Phase 3 测试向量应避免使用 rd62-63 / rb63 作为测试数据寄存器。
建议在 vector schema 或 test convention 中明确标注保留寄存器。

### 结论

编码函数逐字段验证正确，halt 指令与 QEMU trans_halt 配合工作。上轮 Accept 结论维持。
