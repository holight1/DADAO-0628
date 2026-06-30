# DL-018a: QEMU 控制流 + RB 指令（TDD：向量先行）

**执行环境**：本地 DS · DADAO-0628

---

## 原则（TDD）

**必须先写 vector，再写实现。** 本任务要求：
1. 在 `tests/vectors/isa/control-flow.yaml` 和 `tests/vectors/isa/rb-ops.yaml`
   补充 semantic / legality / boundary vector（**先于 trans 函数实现提交**）
2. 再实现 QEMU trans 函数，通过 Phase 3 harness 验证（DL-019a 就绪后可运行）
3. 同时交付 LLVM lit 编码测试（控制流 / RB 各一个 lit 文件）

---

## 指令范围

### §5 控制流（`contracts/isa/spec.md §5`）

| 助记符 | 格式 | 含义 |
|--------|------|------|
| `brn`   | riii | branch if negative (rd[63]=1) |
| `brnn`  | riii | branch if non-negative |
| `brz`   | riii | branch if zero |
| `brnz`  | riii | branch if nonzero |
| `brp`   | riii | branch if positive (rd>0) |
| `brnp`  | riii | branch if non-positive (rd≤0) |
| `breq`  | rrii | branch if rd_ha == rd_hb |
| `brne`  | rrii | branch if rd_ha != rd_hb |
| `jump`  | iiii | PC = PC + imms24*4（无条件跳转，PC-relative）|
| `jump`  | rrii | PC = rb_ha + imms12*4（绝对，RB-relative）|
| `call`  | iiii | RegRAS.push(PC+4); PC = PC + imms24*4 |
| `call`  | rrii | RegRAS.push(PC+4); PC = rb_ha + imms12*4 |
| `ret`   | riii | PC = RegRAS.pop() |
| `rela`  | riii | rd_ha = PC + imms18*4（PC-relative address load）|

**PC-relative offset 计算**：target = PC_current + imm * 4
（PC_current = 当前指令地址 = ctx->base.pc_next - 4）

**RegRAS**：ra[2]..ra[63] 向上增长栈；`call` push = 从 ra[2] 开始，`ret` pop
（确切语义见 `contracts/isa/spec.md §5.3`，不自行猜测）

### §4 RB 指令（`contracts/isa/spec.md §4`）

| 助记符 | 格式 | 含义 |
|--------|------|------|
| `addi-rb` | orii | rb_ha += sext12(imms12) |
| `add-rb`  | orrr | rb_ha = rb_hb + rb_hc |
| `sub-rb`  | orrr | rb_ha = rb_hb - rb_hc |
| `cmp-rb`  | orrr | flags（实际实现见 spec §4.4）|
| `orw-rb`  | orri | rb_ha[pos*16+15:pos*16] = immu16 |
| `andnw-rb`| orri | rb_ha[pos*16+15:pos*16] = ~immu16（按 spec）|
| `setzw-rb`| orri | rb_ha = 0; rb_ha[pos*16+15:pos*16] = immu16 |
| `setow-rb`| orri | rb_ha = ~0; rb_ha[pos*16+15:pos*16] = immu16 |
| `rd2rb`   | orrr | rb_ha = rd_hb |
| `rb2rd`   | orrr | rd_ha = rb_hb |
| `rb2rb`   | orrr | rb_ha = rb_hb |
| `sto-rb`  | rrii | memory[rb_hb + imms12] = rb_ha（8 bytes BE）|
| `ldo-rb`  | rrii | rb_ha = memory[rb_hb + imms12]（8 bytes BE）|

**ILLI 规则**（来自 `contracts/isa/spec.md §4, §5`）：
- `rb_ha == rb0`（PC）作为目标 → ILLI（branch/call/ret 除外，它们明确写 rb0）
- `imms12`/`imms18`/`imms24` 范围越界 → AsmParser 层报错，不在 QEMU 检查

---

## 一、TDD 向量（先写，再实现）

### 1.1 `tests/vectors/isa/control-flow.yaml` 补充

**当前已有**：brz/brn/brnn/brnz/brp/brnp 的基本 semantic case（检查 `encoding.word` 字段是否正确，若无则补全）。

**需要补充**：

| 指令 | 需补 class | 要求 |
|------|-----------|------|
| brz (taken) | boundary | rd=0x0 → 跳转，验证 PC |
| brz (not taken) | boundary | rd=0x1 → 不跳转，PC=PC+4 |
| brn (taken) | semantic | rd=0x8000_0000_0000_0000 |
| brz (rd0 src) | legality | rd0 作为条件寄存器：是否 ILLI？（查 spec §5.1）|
| breq (taken) | semantic | rd_ha == rd_hb → branch |
| breq (not taken) | semantic | rd_ha != rd_hb |
| jump-iiii | semantic | PC = PC + imms24*4 |
| call-iiii | semantic | RegRAS.push + jump；验证 ra[2] = PC+4 |
| ret | semantic | RegRAS.pop；验证 PC = pushed value |
| rela | semantic | rd_ha = PC + imms18*4 |

每条 vector 必须：
- `encoding.word`：按 §2.2 计算
- `input_state`：列出所有相关寄存器初始值
- `expected_state`：list 明确最终 PC（rb0）和任何被写的寄存器
- `expected_fault`: null 或 ILLI

### 1.2 `tests/vectors/isa/rb-ops.yaml` 补充

**当前已有**：部分 addi-rb / add-rb 等基本 semantic case。

**需要补充**：

| 指令 | 需补 class | 要求 |
|------|-----------|------|
| addi-rb | boundary | imms12 = -2048, 2047 |
| setzw-rb | semantic | pos=0,1,2,3 各一个 case |
| andnw-rb | semantic | 按 spec 语义（注意是 AND + ~imm 还是 AND NOT）|
| rd2rb / rb2rd / rb2rb | semantic | 来回转换 |
| sto-rb / ldo-rb | semantic | 内存写读 roundtrip |
| rb0 目标 ILLI | legality | addi-rb rb0, 0 → ILLI |

---

## 二、QEMU trans 函数（向量提交后再写）

### 2.1 branch 通用模式（`target/dadao/translate.c`）

```c
static bool trans_brz(DisasContext *ctx, arg_brz *a)
{
    int64_t pc_cur = ctx->base.pc_next - 4;
    int64_t target = pc_cur + (int64_t)a->imm18 * 4;

    TCGv_i64 cond = load_rd(ctx, a->ha);
    TCGLabel *taken = gen_new_label();
    tcg_gen_brcondi_i64(TCG_COND_EQ, cond, 0, taken);
    /* not taken: fall through (PC += 4, already handled by TB) */
    gen_set_label(taken);
    /* set PC = target */
    store_pc(ctx, target);
    ctx->base.is_jmp = DISAS_JUMP;
    return true;
}
```

每条 branch 指令只有条件不同（`TCG_COND_*`）：

| 指令 | 条件 | TCGCond |
|------|------|---------|
| brz  | rd == 0 | `TCG_COND_EQ` |
| brnz | rd != 0 | `TCG_COND_NE` |
| brn  | rd < 0 (signed) | `TCG_COND_LT` |
| brnn | rd >= 0 | `TCG_COND_GE` |
| brp  | rd > 0 | `TCG_COND_GT` |
| brnp | rd <= 0 | `TCG_COND_LE` |

`store_pc(ctx, target)` 辅助：写入 `CPUDADAOState.rb[0]`。

### 2.2 jump / call / ret

参考 `target/riscv/insn_trans/trans_rvi.c.inc` 中的 `trans_jalr`/`trans_jal`。

`call`：在 jump 基础上增加 `RegRAS_push(PC+4)`：
```c
// RegRAS push = 移位 ra[2..63]（按 spec §5.3 方向）
// 然后 ra[2] = PC + 4
```

`ret`：
```c
// PC = ra[2]；RegRAS pop = 移位（spec §5.3 反方向）
```

RegRAS 的精确移位方向从 `contracts/isa/spec.md §5.3` 读取，不自行猜测。

### 2.3 RB 指令

直接类比 DL-015a 的 RD arith：
- `addi-rb`：读 rb_ha，加 sext(imms12)，写 rb_ha
- `rd2rb/rb2rd/rb2rb`：用 `load_rd`/`store_rd`/`load_rb`/`store_rb` 组合
- wyde 操作（orw-rb 等）：与 DL-015a 的 orw/andnw/setzw/setow 完全相同，只是 bank 是 rb
- `sto-rb/ldo-rb`：与 DL-016b 的 sto/ldo 完全相同，只是 rb_ha 作为源/目标

rb0 目标 ILLI 检查：
```c
if (a->ha == 0) { gen_exception_illegal(ctx); return true; }
```

---

## 三、LLVM lit 测试

补充/更新以下 lit 文件（`tests/lit/MC/Dadao/`）：

- `riii_branch.s`（当前已存在）：验证 brz/brn/brnn/brnz/brp/brnp encoding
- `riii_ret.s`（当前已存在）：验证 ret encoding
- `iiii_jump.s`（当前已存在）：验证 jump/call encoding
- 新增 `rb_ops.s`：验证 addi-rb, rd2rb, rb2rd, rb2rb, setzw-rb, sto-rb

每个 lit 文件的 RUN 行使用 `-filetype=asm` 验证（byte-level 等 DL-011a 反汇编器）。

---

## 交付物

1. `tests/vectors/isa/control-flow.yaml` — 补充向量（commit A：先于 trans 实现）
2. `tests/vectors/isa/rb-ops.yaml` — 补充向量（commit A）
3. `components/qemu/patches/0006-dadao-ctrl-flow.patch` — control flow + RB trans（commit B）
4. `tests/lit/MC/Dadao/rb_ops.s` — RB encoding lit 测试（commit B）
5. `components/qemu/patches/series` — 追加 0006

---

## 约束

1. **向量 commit 在 trans 实现 commit 之前**：git log 必须能看到两个独立 commit
2. **encoding.word 必须手推**：不从 QEMU/LLVM 输出复制
3. **branch PC 计算**：target = PC_current + imm * 4（PC_current = 当前指令地址）
4. **RegRAS 方向必须从 spec §5.3 读取**，不自行猜测
5. **rb0 目标 ILLI**：addi-rb/rd2rb/rb2rb/sto-rb/ldo-rb 检查 ha==0
6. **`make build-qemu` PASS**：6 个 patch 全部干净 apply 后 ninja 无错

---

## 验收步骤（DS 完成区填写）

```
# 向量检查
python3 scripts/validate_vectors.py           →  0 errors
git log --oneline -3                          →  向量 commit 早于 trans commit

# QEMU 编译
make build-qemu                               →  PASS

# lit 测试
llvm-lit tests/lit/MC/Dadao/                  →  0 failures（包含 rb_ops.s）

# Phase 3 harness 验证（DL-019a 就绪后）
python3 tests/scripts/run_qemu_test.py \
  tests/vectors/isa/control-flow.yaml         →  N passed, 0 failed
```

---

## 参考指针

| 资源 | 用途 |
|------|------|
| `contracts/isa/spec.md §4` | RB 指令语义 |
| `contracts/isa/spec.md §5` | 控制流语义、RegRAS 协议 |
| `contracts/isa/spec.md §2.6` | ILLI 触发规则（rb0 目标等）|
| `target/riscv/insn_trans/trans_rvi.c.inc` | jal/jalr 参考模式 |
| `components/qemu/patches/0004-dadao-rd-arith.patch` | wyde 操作风格参考 |
| `components/qemu/patches/0005-dadao-load-store.patch` | sto/ldo 风格参考 |
| `tests/vectors/isa/control-flow.yaml` | 已有 branch 向量（基线）|
| `tests/vectors/isa/rb-ops.yaml` | 已有 RB 向量（基线）|

---

## 完成区

<!-- DS 在此填写 -->
