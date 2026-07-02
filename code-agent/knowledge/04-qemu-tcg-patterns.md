# §4 QEMU TCG 编码模式

**来源**：DL-015a, DL-016a, DL-026a, DL-024a, DL-025a review（2026-07-02）  
**交叉验证**：参见 §1 QEMU translate 约定

---

## §4.1 TCG Label 顺序规则（关键：不可将 gen_set_label 放在 return 之后）

**divs 正确模式**：
```c
TCGLabel *l_div0 = gen_new_label();
TCGLabel *l_ok = gen_new_label();

tcg_gen_brcond_i64(TCG_COND_EQ, divisor, zero, l_div0);  // div0 → exception
tcg_gen_div_i64(quot, dividend, divisor);                 // normal path
tcg_gen_rem_i64(rem, dividend, divisor);
store_rd(ctx, ha, rem);
store_rd(ctx, hb, quot);
tcg_gen_br(l_ok);                                         // skip exception

gen_set_label(l_div0);                                    // ← 必须在 return 前
gen_helper_raise_exception(tcg_env, tcg_constant_i32(EXCP_ILLI));
gen_set_label(l_ok);
return true;
```

**错误模式（会导致 SIGABRT 或死循环）**：
```c
gen_set_label(l_div0);   // ← 在 return true 之后 → 不可达 → TCG 报错
return true;
```

## §4.2 ILLI 检查纪律

**在生成任何 TCG 写操作之前检查 ILLI**：
```c
if (a->ha == 0) { gen_exception_illegal(ctx); return true; }
// 仅在通过 ILLI 检查后才生成 TCG 代码
```

**源快照**：在写入任何目标之前读取所有源操作数：
```c
TCGv_i64 s1 = load_rd(ctx, a->hc);
TCGv_i64 s2 = load_rd(ctx, a->hd);
// ... 现在可以安全地 store 了
store_rd(ctx, a->ha, result_hi);
store_rd(ctx, a->hb, result_lo);
```

## §4.3 128-bit add/sub 模式

```c
TCGv_i64 s1 = load_rd(ctx, a->hc);
TCGv_i64 s2 = load_rd(ctx, a->hd);
TCGv_i64 s1h = tcg_temp_new_i64();
TCGv_i64 s2h = tcg_temp_new_i64();
tcg_gen_sari_i64(s1h, s1, 63);   // 符号扩展提取高位
tcg_gen_sari_i64(s2h, s2, 63);
TCGv_i64 lo = tcg_temp_new_i64();
TCGv_i64 hi = tcg_temp_new_i64();
tcg_gen_add2_i64(lo, hi, s1, s1h, s2, s2h);
store_rd(ctx, a->hb, lo);        // 低位
store_rd(ctx, a->ha, hi);        // 高位
```

## §4.4 48-bit EA 计算

```c
tcg_gen_ld_i64(base, tcg_env, offsetof(CPUDADAOState, rb[a->hb]));
tcg_gen_andi_i64(base, base, 0x0000FFFFFFFFFFFFULL);  // mask 高 16 位
tcg_gen_addi_i64(base, base, a->imms12);              // + offset
tcg_gen_andi_i64(base, base, 0x0000FFFFFFFFFFFFULL);  // 重新 mask
```

**RB 算术高 16 位保留**：
```c
TCGv_i64 old = tcg_temp_new_i64();
tcg_gen_ld_i64(old, ..., rb[a->ha]);
tcg_gen_andi_i64(old, old, 0xFFFF000000000000ULL);     // 提取高 16 位
// 对 v 进行低 48 位算术运算
tcg_gen_andi_i64(v, v, 0x0000FFFFFFFFFFFFULL);
tcg_gen_or_i64(v, v, old);                             // 合并回高 16 位
tcg_gen_st_i64(v, ..., rb[a->ha]);
```

## §4.5 内存访问 MemOp 参考

| 指令 | MemOp |
|------|-------|
| ldbs | `MO_SB` |
| ldbu | `MO_UB` |
| ldws | `MO_BESW \| MO_ALIGN_2` |
| ldwu | `MO_BEUW \| MO_ALIGN_2` |
| ldts | `MO_BESL \| MO_ALIGN_4` |
| ldtu | `MO_BEUL \| MO_ALIGN_4` |
| ldo | `MO_BEQ \| MO_ALIGN_8` |
| stb | `MO_UB` |
| stw | `MO_BEUW \| MO_ALIGN_2` |
| stt | `MO_BEUL \| MO_ALIGN_4` |
| sto | `MO_BEQ \| MO_ALIGN_8` |

字节 load/store 无对齐要求（不加 MO_ALIGN）。

## §4.6 条件分支模式

```c
TCGv_i64 cond = load_rd(ctx, a->ha);
TCGLabel *taken = gen_new_label();
tcg_gen_brcondi_i64(TCG_COND_EQ, cond, 0, taken);     // 条件 → taken

// not-taken fallthrough
tcg_gen_st_i64(tcg_constant_i64(ctx->base.pc_next + 4), ..., pc);
TCGLabel *done = gen_new_label();
tcg_gen_br(done);

gen_set_label(taken);
// 注意：pc_next 是当前指令地址（见 §1.1），+4 后才是下一条指令基址
tcg_gen_st_i64(tcg_constant_i64(ctx->base.pc_next + 4 + imm * 4), ..., pc);
gen_set_label(done);
ctx->base.is_jmp = DISAS_JUMP;
```

**Branch TCGCond 对照表**：

| 指令 | 条件 | TCGCond |
|------|------|---------|
| brz | rd == 0 | `TCG_COND_EQ` |
| brnz | rd ≠ 0 | `TCG_COND_NE` |
| brn | rd < 0 | `TCG_COND_LT` |
| brnn | rd ≥ 0 | `TCG_COND_GE` |
| brp | rd > 0 | `TCG_COND_GT` |
| brnp | rd ≤ 0 | `TCG_COND_LE` |
| breq | rd_a == rd_b | `TCG_COND_EQ`（reg vs reg） |
| brne | rd_a ≠ rd_b | `TCG_COND_NE`（reg vs reg） |

## §4.7 多寄存器 load/store

```c
// ILLI 检查
if (ha == 0) gen_exception_illegal;
if (hd == 0) gen_exception_illegal;
if (ha + hd > 64) gen_exception_illegal;

// 循环前 snapshot rb[hb] + rd[hc]
TCGv_i64 base = ..., idx = ...;
tcg_gen_ld_i64(base, ..., rb[hb]);
tcg_gen_ld_i64(idx, ..., rd[hc]);

// C 级循环展开（i = 0 时跳过 addi）
for (int i = 0; i < hd; i++) {
    TCGv_i64 ea = tcg_temp_new_i64();
    tcg_gen_mov_i64(ea, base);
    if (i) {
        tcg_gen_addi_i64(ea, ea, i * elem_size);
        tcg_gen_andi_i64(ea, ea, 0x0000FFFFFFFFFFFFULL);
    }
    tcg_gen_qemu_ld_i64(v, ea, ctx->mem_idx, memop_with_align);
    tcg_gen_st_i64(v, ..., rd/ha + i);
}
```
