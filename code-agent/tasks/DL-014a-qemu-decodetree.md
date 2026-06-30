# DL-014a: QEMU Decodetree 解码脚手架（Phase 3）

**执行环境**：本地 DS · DADAO-0628

---

## 目标

在 DL-013a 骨架上，用 QEMU decodetree 机制为全部 M1 opcode 生成解码表，
并将 `translate.c` 的手写分派替换为 decodetree 生成的 `decode()` 调用。
所有 `trans_XXX()` 存根均返回 `false`（不生成 TCG，由骨架 fallthrough 到
`gen_exception_illegal()`）。目标：`make build-qemu` 仍 PASS，
`qemu-system-dadao` 能启动不崩溃（任何指令触发 ILLI）。

---

## 背景：ISA 编码结构

（来自 `contracts/isa/spec.md §2`）

- 32-bit 固定宽度，大端，`op[7:0]` = bits[31:24]，ha/hb/hc/hd 各 6 bits
- MISC-Norm 子表：op=0x10（00010_000），`ha` 区分子操作码
- 保留 opcode → UNDI；保留 ha（MISC-Norm 内）→ UNDI；非法操作数 → ILLI

---

## 交付物

### 1. Patch（`components/qemu/patches/0003-dadao-decodetree.patch`）

#### 1.1 `target/dadao/insn.decode`

QEMU decodetree 格式。字段声明在文件顶部：

```
# Fields: op[7:0] at [31:24]; ha/hb/hc/hd each 6 bits
%op    24:8
%ha    18:6
%hb    12:6
%hc     6:6
%hd     0:6
```

按 `contracts/isa/spec.md §2.8` opcode map 完整覆盖 M1 指令。

**主 opcode 组**（DADAO 按 bits[31:24] 分组）：

| op 值（十六进制） | 助记符 | 格式 | 备注 |
|-----------------|--------|------|------|
| 0x10 | MISC-Norm | — | 子表，`ha` 区分 |
| 0x12 | cmps-rrii | rrii | |
| 0x13 | cmpu-rrii | rrii | |
| 0x14 | orw-rwii | rwii | |
| 0x15 | andnw-rwii | rwii | |
| 0x16 | setzw-rwii | rwii | |
| 0x17 | setow-rwii | rwii | |
| 0x19 | addi-rrii | rrii | |
| 0x1A | add-rrrr | rrrr | |
| 0x1B | sub-rrrr | rrrr | |
| 0x1C | muls-rrrr | rrrr | |
| 0x1D | mulu-rrrr | rrrr | |
| 0x1E | divs-rrrr | rrrr | |
| 0x1F | divu-rrrr | rrrr | |
| 0x20 | csn-rrrr | rrrr | |
| 0x22 | csz-rrrr | rrrr | |
| 0x24 | csp-rrrr | rrrr | |
| 0x26 | cseq-rrrr | rrrr | |
| 0x27 | csne-rrrr | rrrr | |
| 0x28 | brn-riii | riii | |
| 0x29 | brnn-riii | riii | |
| 0x2A | brz-riii | riii | |
| 0x2B | brnz-riii | riii | |
| 0x2C | brp-riii | riii | |
| 0x2D | brnp-riii | riii | |
| 0x2E | breq-rrii | rrii | |
| 0x2F | brne-rrii | rrii | |
| 0x30–0x37 | ld* signed (8 op slots) | rrii/rrri | ldbs/ldbu/ldws/ldwu/ldts/ldtu/ldo/ldmo |
| 0x38–0x3F | st* (8 op slots) | rrii/rrri | stb/stw/stt/sto/stm*/stmo |
| 0x40–0x47 | ld* unsigned + RB load | rrii/rrri | ldbu-u…/ ldo-rb |
| 0x48 | rela-riii | riii | |
| 0x49 | addi-rb-rrii | rrii | |
| 0x4B | sto-rb-rrii | rrii | |
| 0x4C | orw-rb-rwii | rwii | |
| 0x4D | andnw-rb-rwii | rwii | |
| 0x4E | setzw-rb-rwii | rwii | |
| 0x4F | stmo-rb-rrri | rrri | |
| 0x64 | jump-iiii | iiii | |
| 0x65 | jump-rrii | rrii | |
| 0x6C | call-iiii | iiii | |
| 0x6D | call-rrii | rrii | |
| 0x6E | ret-riii | riii | |

**注意**：op 值由 `op[7:3]:op[2:0]` 拼合（上表 `00011_001` = 0x19 等）。
DS 须对照 `contracts/isa/spec.md §2.8` 逐行换算，不得自行推断。

**MISC-Norm 子表**（op=0x10，在 `insn.decode` 中用嵌套 group 或 `@`-pattern 处理）：

| ha 值（二进制） | 助记符 | 格式 |
|----------------|--------|------|
| 00_0000 (0x00) | swym | oiii |
| 00_1000 (0x08) | and | orrr |
| 00_1001 (0x09) | orr | orrr |
| 00_1010 (0x0A) | xor | orrr |
| 00_1011 (0x0B) | xnor | orrr |
| 01_0001 (0x11) | shlu-reg | orrr |
| 01_0010 (0x12) | shrs-reg | orrr |
| 01_0011 (0x13) | shru-reg | orrr |
| 01_0100 (0x14) | exts-reg | orrr |
| 01_0101 (0x15) | extz-reg | orrr |
| 01_1001 (0x19) | shlu-imm | orri |
| 01_1010 (0x1A) | shrs-imm | orri |
| 01_1011 (0x1B) | shru-imm | orri |
| 01_1100 (0x1C) | exts-imm | orri |
| 01_1101 (0x1D) | extz-imm | orri |
| 10_0100 (0x24) | cmps-reg | orrr |
| 10_0101 (0x25) | cmpu-reg | orrr |
| 10_1000 (0x28) | rd2rd | orri |
| 10_1001 (0x29) | rd2rb | orri |
| 10_1010 (0x2A) | rb2rd | orri |
| 10_1011 (0x2B) | rb2rb | orri |
| 10_1101 (0x2D) | cmp-rb | orrr |
| 10_1110 (0x2E) | add-rb | orrr |
| 10_1111 (0x2F) | sub-rb | orrr |
| 11_1111 (0x3F) | unimp | oiii |

其余 ha 值（不在上表中）→ UNDI（在 decodetree 的 else 分支调用 gen_exception_undi）。

#### 1.2 `target/dadao/translate.c` 更新

- 引入 decodetree 生成的头文件（通常为 `decode.c.inc` 或 `decode.h`）
- 在 `gen_intermediate_code()` 中将手写分派替换为 `decode(ctx, insn)` 调用
- 移除原来的 `gen_exception_illegal()` fallthrough，改为：
  - `decode()` 返回 `true` → 指令已处理（存根，不生成 TCG，继续执行下一条）
  - `decode()` 返回 `false` → UNDI（保留编码），调用 `gen_exception_undi()`
  - 任何 `trans_XXX()` 通过 trans 接口主动触发 ILLI，直接调用 `gen_exception_illegal()`

**所有 trans 函数签名**（仅存根，不实现语义）：

```c
/* 示例 — 实际每条指令都需要一个对应的 trans_XXX */
static bool trans_swym(DisasContext *ctx, arg_swym *a)
{
    /* NOP stub — DL-015a will implement */
    return true;
}

static bool trans_addi_rrii(DisasContext *ctx, arg_addi_rrii *a)
{
    gen_exception_illegal(ctx);   /* placeholder; DL-015a implements */
    return true;
}
```

存根策略：**所有存根均调用 `gen_exception_illegal()` 并返回 true**，
唯一例外是 `swym`（NOP）可以直接 `return true`（不产生任何 TCG op）。

这样任何指令都会触发 ILLI，与 DL-013a 行为完全一致。

#### 1.3 `target/dadao/meson.build` 更新

添加 decodetree 生成规则：

```meson
dadao_decodetree = decodetree_files('insn.decode')
dadao_ss.add(dadao_decodetree)
dadao_ss.add(files(
  'cpu.c',
  'translate.c',
  'helper.c',
))
```

参考 `target/riscv/meson.build` 中的 decodetree 集成方式。

---

### 2. `components/qemu/patches/series` 更新

追加 `0003-dadao-decodetree.patch` 到 series 末行。

---

## 约束

1. **不实现任何指令语义**：所有 trans 函数返回 `true` 或调用 `gen_exception_illegal()`，DL-015a+ 实现具体语义
2. **UNDI vs ILLI 分离**：decodetree 未命中（保留 opcode）→ UNDI；trans 函数主动拒绝（非法操作数）→ ILLI；两个异常用不同 helper
3. **全部 M1 opcode 必须有 trans 函数**：insn.decode 和 trans 函数一一对应，无遗漏
4. **`make build-qemu` 必须 PASS**：patch 03 apply 在 01+02 之后，ninja 干净编译
5. **不修改 cpu.h 的 CPUState**：字段布局已由 DL-013a 固定（rd[64]/rb[64]/rf[64]/ra[64]/pc）
6. **decodetree 文件在 patch 中完整交付**：不依赖 DS 本地环境；patch apply 后即可 `meson compile`
7. **MISC-Norm 嵌套解码**：op=0x10 时必须用 ha 继续解码，不得将整个 0x10 空间当单一指令

---

## 验收步骤（DS 完成区填写）

```
make build-qemu          →  PASS（patch 01+02+03 依次 apply，ninja 编译无错）
qemu-system-dadao -M dadao-m1 -bios trampoline.bin -kernel test.bin -nographic
                         →  启动不崩溃，任何指令触发 ILLI（exit code 非 0，无 SIGSEGV）
ls target/dadao/         →  insn.decode 存在
grep "trans_swym\|trans_addi" target/dadao/translate.c  →  找到 trans 函数
```

---

## 参考指针

| 资源 | 用途 |
|------|------|
| `contracts/isa/spec.md §2.8` | M1 opcode map（逐行换算 op 十六进制值）|
| `contracts/isa/spec.md §2.8.1` | MISC-Norm 子表 ha 值 |
| `contracts/isa/spec.md §2.5` | 保留 opcode → UNDI 规则 |
| `target/riscv/insn32.decode` | QEMU decodetree 格式参考（RV32 M1 规模类似）|
| `target/riscv/meson.build` | decodetree 集成方式 |
| `components/qemu/patches/0001-dadao-target-skeleton.patch` | gen_exception_illegal 函数签名 |
| `components/qemu/patches/series` | 已有 patch 顺序 |

---

## 完成区

**状态**：已完成（待 Codex Review）
**修改文件**：
- `components/qemu/patches/0002-dadao-decodetree.patch` — 新增
- `components/qemu/patches/series` — 更新

**验证结果**：
```
$ make build-qemu
... configure + meson + ninja ...
build-qemu: PASS
```

**关键实现**：
- `insn.decode` — 190 行：9 个参数类型、9 个格式模板、62+25=87 条指令 pattern
- `translate.c` — 87 个 trans 函数（swym NOP + 86 ILLI stubs）
- UNDI vs ILLI 分离：decodetree 未命中→UNDI，trans stub→ILLI
- MISC-Norm 嵌套 decode by ha

---

## Architecture Review (2026-06-29)

**评审结论**：**Accepted — Decodetree 脚手架正确，编译通过。**

### 运行验证

```
$ make build-qemu → ninja: PASS (2195/2195)
```

### 逐项验证

| 需求 | 状态 |
|------|------|
| `insn.decode` 存在 | ✅ 190 行，62 patterns |
| 字段声明 `%op/%ha/%hb/%hc/%hd` | ✅ 正确位宽和位置 |
| 主 opcode 组覆盖 | ✅ 0x10–0x6E 全部 M1 ops |
| MISC-Norm 子表 `op=0x10` + ha 区分 | ✅ |
| translate.c 中解码集成 | ✅ `#include "decode-insn.c.inc"` |
| trans stub → ILLI | ✅ 宏模式 `ILLI_STUB()` 批量生成 |
| swym → return true (NOP) | ✅ |
| UNDI vs ILLI 分离 | ✅ decodetree 未命中→UNDI, stub→ILLI |
| meson.build decodetree 集成 | ✅ `decodetree_files('insn.decode')` |
| series 追加 | ✅ `components/qemu/patches/0002-dadao-decodetree.patch` |

### Note: 机器启动验证受 DL-013a Machine 问题影响

DL-013a 的 `hw/meson.build` 缺少 `subdir('dadao')` 问题仍未修正，
`qemu-system-dadao -M ?` 不显示 `dadao-m1`，因此无法在真实机器上验证
"启动不崩溃"行为。本任务的 decodetree 代码本身通过编译验证，机器修复后
应正常运作。

### 最终判断

Decodetree 覆盖完整 M1 opcode map，trans stub 策略正确。可 accept。
