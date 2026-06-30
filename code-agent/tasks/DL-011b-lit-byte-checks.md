# DL-011b: Lit 字节级 CHECK 模式（OBJ 前缀）

**执行环境**：本地 DS · DADAO-0628

---

## 背景

14 个 lit 文件中 13 个有 `llvm-objdump -d` RUN 行（`triple-smoke.s` 除外）。
所有 CHECK 行当前只匹配助记符文本，不验证字节编码：

```
# CHECK: addi rd8, rd0, 1    ← mnemonic only, 同时被 objdump 和 asm-round-trip 消费
```

这意味着 `llvm-objdump -d` 输出了错误的字节（或空字节）也会通过。
DL-011a 补充了 `DADAODisassembler.cpp`，但其字节→助记符的映射是否正确，目前 lit 无法检测。

---

## 目标

对全部 13 个含 objdump RUN 行的 lit 文件：

1. **拆分 CHECK 前缀**：现有 `# CHECK:` 拆为 `# OBJ:`（objdump 输出）和 `# ASM:`（asm round-trip 输出）
2. **添加字节级 OBJ 模式**：每条指令用 `# OBJ: <hex bytes>{{.*}}<mnemonic>` 验证实际字节
3. **字节手工计算**：依据 spec §2.2 公式 + `tools/opcodes.yaml`，不从 llvm-mc 输出复制

---

## 字节计算规则

### spec §2.2 编码公式

```
word[31:0] = (op << 24) | (ha << 18) | (hb << 12) | (hc << 6) | hd
```

字段到寄存器/立即数的映射（格式相关，查 spec §2.3）：

| 格式 | ha | hb | hc | hd |
|------|----|----|----|----|
| rrii | dest-reg | src-reg | imm[11:6] | imm[5:0] |
| rrrr | dest-hi | dest-lo | src1 | src2 |
| orrr | minor-op | dest | src1 | src2 |
| riii | dest | imm[17:12] | imm[11:6] | imm[5:0] |
| rrri | dest | base | src | count |
| rwii | dest | wyde-pos | imm[11:6] | imm[5:0] |
| orri | minor-op | dest | src | imm[5:0] |

### 字节顺序

DADAO 为大端序（big-endian）。`word = 0x19200001` 在内存中存储为字节序列：`19 20 00 01`。

`llvm-objdump -d` 按内存顺序显示字节（MSB 在左）。

DS 必须在 `components/llvm/patches/0002-dadao-target-skeleton.patch` 中确认 DataLayout 声明：
- 若含 `E`（big-endian），则 MSB 在左，公式直接适用
- 若含 `e`（little-endian），则字节序相反（不应出现，DADAO 为大端）

### 带符号立即数编码

imm12（rrii）为 sign-extended 12-bit：
- 正数：直接取低 12 位，分配到 hc/hd
- 负数：取补码后取低 12 位，例如 -3 → 0xFFD → hc=0x3F, hd=0x3D

### 示例计算

**`addi rd8, rd0, 1`**（rrii，op=0x19，ha=dest=8，hb=src=0，imm12=1）：
```
word = (0x19 << 24) | (8 << 18) | (0 << 12) | 1
     = 0x19000000 | 0x00200000 | 0 | 1
     = 0x19200001
bytes: 19 20 00 01
```

**`cmps rd1, rd2, -3`**（rrii，op=0x1A，ha=1，hb=2，imm12=-3=0xFFD）：
```
hc = (0xFFD >> 6) & 0x3F = 0x3F
hd = 0xFFD & 0x3F        = 0x3D
word = (0x1A << 24) | (1 << 18) | (2 << 12) | (0x3F << 6) | 0x3D
     = 0x1A040000 + 0x00002000 + 0xFD + 0x3D
→ 手工核算：0x1A042FBD
bytes: 1A 04 2F BD
```

DS 必须对每条指令独立推导字节，不得从工具输出复制（复制工具输出无法检测工具 bug）。

---

## 13 个目标文件

| 文件 | 当前 CHECK 条数 | 主要指令格式 |
|------|----------------|-------------|
| `rrii_alu.s` | 3 | rrii RD（addi/cmps/cmpu） |
| `rrrr.s` | 6 | rrrr（add/sub/muls/mulu/divs/divu） |
| `rrri.s` | 11 | rrri（ldm*/stm*） |
| `riii_branch.s` | ? | riii 分支 |
| `riii_ret.s` | ? | ret |
| `rrii_branch.s` | ? | rrii 分支（breq/brne） |
| `rrii_load.s` | ? | rrii load |
| `rrii_store.s` | ? | rrii store |
| `iiii_jump.s` | ? | iiii jump/call |
| `orrr.s` | ? | orrr |
| `orri.s` | ? | orri |
| `rb_ops.s` | ? | rb ops |
| `rwii.s` | ? | rwii |

---

## 改造后格式（以 `rrii_alu.s` 为例）

**改前**：
```s
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=obj %s -o %t
# RUN: llvm-objdump -d --triple=dadao-unknown-elf %t | FileCheck %s
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=asm %s | FileCheck %s

# CHECK: addi rd8, rd0, 1
# CHECK: cmps rd1, rd2, -3
# CHECK: cmpu rd3, rd4, 10
```

**改后**：
```s
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=obj %s -o %t
# RUN: llvm-objdump -d --triple=dadao-unknown-elf %t | FileCheck %s --check-prefix=OBJ
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=asm %s | FileCheck %s --check-prefix=ASM

# OBJ: 19 20 00 01{{.*}}addi rd8, rd0, 1
# OBJ: 1A 04 2F BD{{.*}}cmps rd1, rd2, -3
# OBJ: 1B 04 28 0A{{.*}}cmpu rd3, rd4, 10

# ASM: addi rd8, rd0, 1
# ASM: cmps rd1, rd2, -3
# ASM: cmpu rd3, rd4, 10
```

**规则**：
- `{{.*}}` 吸收字节与助记符之间的空白（objdump 可能有多个空格）
- OBJ 行验证字节 + 助记符两者都对；ASM 行只验证助记符（asm 输出无字节）
- 字节全大写，每字节 2 位 hex，空格分隔
- 每条汇编指令对应一个 OBJ 和一个 ASM 检查行
- `triple-smoke.s`：不改（无 objdump RUN 行）

---

## 约束

1. **手推字节**：所有字节从 spec §2.2 公式 + `tools/opcodes.yaml` op/ha 推导，禁止从 `llvm-mc` 输出复制
2. **不改汇编内容**：`.s` 文件中的实际指令行（非注释行）不修改
3. **保留 triple-smoke.s 不变**
4. `make check` 不运行 lit（lit 需要构建 LLVM）；DS 用 `lit tests/lit/` 本地验收（需已 build-llvm）
5. 若 build-llvm 未完成，DS 只交付修改后的 .s 文件，在完成区注明"lit 未运行，需用户 build-llvm 后验收"

---

## 验收步骤（DS 完成区填写）

```bash
# 前提：LLVM 已 build（make build-mc 或等价）

# 验证所有 13 个 lit 文件都含 --check-prefix=OBJ
grep -l "check-prefix=OBJ" tests/lit/MC/Dadao/*.s | wc -l
# 期望：13

# 验证 triple-smoke.s 未改
diff tests/lit/MC/Dadao/triple-smoke.s <(echo '// RUN: llvm-mc --triple=dadao-unknown-elf %s')
# 期望：无差异（或查文件内容与原一致）

# 运行 lit（需 build）
lit tests/lit/MC/Dadao/
# 期望：全部 PASS，无 FAIL/XFAIL

# 若 lit 失败，检查 OBJ 字节与实际 objdump 输出
llvm-mc --triple=dadao-unknown-elf -filetype=obj tests/lit/MC/Dadao/rrii_alu.s -o /tmp/rrii.o
llvm-objdump -d --triple=dadao-unknown-elf /tmp/rrii.o
# 比对输出字节与 OBJ 模式
```

---

## 参考指针

| 资源 | 用途 |
|------|------|
| `contracts/isa/spec.md §2.2` | 编码公式 `word[31:0]` |
| `contracts/isa/spec.md §2.3` | 各格式字段分配 |
| `tools/opcodes.yaml` | 每条指令的 op/ha 值 |
| `components/llvm/patches/0002-dadao-target-skeleton.patch` | DataLayout 大端确认 |
| `tests/lit/MC/Dadao/rrii_alu.s` | 格式参考（最简 3 指令文件） |
| DL-011a 任务文件 | 0006-dadao-disassembler.patch 实现背景 |
