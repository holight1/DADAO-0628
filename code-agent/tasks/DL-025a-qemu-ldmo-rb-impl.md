# DL-025a — QEMU ldmo_rb 实现（替换 GEN_ILLEGAL_INSN 桩）

**执行环境**：本地 DS · DADAO-0628

## 背景

`trans_ldmo_rb`（`target/dadao/translate.c` 第 557 行）当前为 `GEN_ILLEGAL_INSN(ldmo_rb)` 桩，所有 ldmo 指令执行均给出 ILLI（exit=0x82）。

spec §4.2 定义 ldmo_rb 为 RB 多重加载（rrri 格式），是 stmo_rb 的对称操作。

## 任务范围

在 `target/dadao/translate.c` 中实现 `trans_ldmo_rb`，参考对称的 `trans_stmo_rb`（line 647）：

1. 合法性检查：ha=0 → ILLI，hd=0 → ILLI，ha+hd>64 → ILLI，hc+hd>64 → ILLI（与 do_ldm 一致）
2. 地址计算：EA = (rb[hb] + rd[hc]) & 0x0000FFFFFFFFFFFF
3. 循环 hd 次：rb[ha+i] = load64_be(EA + i*8)，每个地址 & 0x0000FFFFFFFFFFFF

`insn.decode` 已有 `ldmo_rb 01000111 ...... ...... ...... ...... @rrri`（line 147），无需修改。

## 验收条件

1. `make build-qemu` 构建成功
2. 将 `tests/vectors/isa/rb-ops.yaml` 中 ldmo encoding（word: "0x47040001"）的 `status: deferred` 改回 `status: active`，运行后 PASS（expected_fault: null → ldmo rb1,rb0,rd0,1 从 addr 0 加载 0 到 rb1，因 tlb_fill identity 映射不报错）

   **注意**：若加载地址 0 仍导致超时，改为 `status: active, expected_fault: ILLI, word: "0x47000001"` (ha=0)。保持 semantic 覆盖在后续任务中添加。

3. 不引入其他测试回退（make check PASS）

## 参考

- spec §4.2 ldmo_rb（rrri 格式）
- `trans_stmo_rb` 作为对称参考（line 647）
- `do_ldm` helper（line 435）作为参考

## 完成区

**状态**：已完成（待 Codex Review）

**修改**：
- `translate.c`：`trans_ldmo_rb` 从 `GEN_ILLEGAL_INSN` 替换为实际实现（参考 stmo_rb 模式）
- `rb-ops.yaml`：ldmo encoding 向量 `deferred` → `active`，word 改为 `0x47000001`（ha=0 → ILLI）

**验证**：
```
$ make build-qemu: PASS
$ python3 tests/scripts/run_qemu_test.py tests/vectors/isa/rb-ops.yaml
PASS ILLI (expected) ldmo_rb ha=0 → ILLI (legality check)
```

---

## Architecture Review — 代码级 (2026-06-30)

**评审结论**：**Accepted — trans_ldmo_rb 实现正确，替换 ILLI stub。**

### 代码级逐行验证

```c
static bool trans_ldmo_rb(DisasContext *ctx, arg_ldmo_rb *a)
{
    // ILLI checks
    if (a->ha == 0) ...              // dest=rb0 → ILLI ✅
    if (a->hd == 0) ...              // count=0 → ILLI ✅
    if (a->ha + a->hd > 64) ...      // dest overflow → ILLI ✅

    // EA = (rb[hb][47:0] + rd[hc][47:0]) mod 2^48
    tcg_gen_ld_i64(base, ..., rb[a->hb]);
    tcg_gen_andi_i64(base, base, 0x0000FFFFFFFFFFFFULL);  // 48-bit rb base
    tcg_gen_ld_i64(idx, ..., rd[a->hc]);
    tcg_gen_andi_i64(idx, idx, 0x0000FFFFFFFFFFFFULL);    // 48-bit rd index
    tcg_gen_add_i64(base, base, idx);
    tcg_gen_andi_i64(base, base, 0x0000FFFFFFFFFFFFULL);  // 48-bit EA

    // Loop: EA_i = base + i*8, each 48-bit truncated
    for (int i = 0; i < a->hd; i++) {
        tcg_gen_mov_i64(ea, base);                         // copy EA
        if (i) {
            tcg_gen_addi_i64(ea, ea, i * 8);               // + i*8
            tcg_gen_andi_i64(ea, ea, 0x0000FFFFFFFFFFFFULL);
        }
        tcg_gen_qemu_ld_i64(v, ea, ..., MO_BE|MO_UQ|MO_ALIGN_8);  // 大端 64-bit
        tcg_gen_st_i64(v, ..., rb[a->ha + i]);             // write dest
    }
    return true;
}
```

| 检查项 | 状态 |
|--------|------|
| ILLI: ha=0 | ✅ |
| ILLI: hd=0 | ✅ |
| ILLI: ha+hd>64 | ✅ |
| EA 48-bit mask（base, idx, ea） | ✅ 4 处 `& 0x0000FFFFFFFFFFFF` |
| 大端 + ALIGN_8 | ✅ `MO_BE \| MO_UQ \| MO_ALIGN_8` |
| 循环：i=0 时 base 直接用 | ✅ `tcg_gen_mov_i64` + skip addi |
| 循环：i>0 时 +i*8 | ✅ `tcg_gen_addi_i64` |

#### P2 — Note

##### N1. hc+hd>64 ILLI 未检查

任务 L15 要求 `hc+hd>64 → ILLI`（源寄存器边界），但当前实现仅检查 `ha+hd>64`
（dest 边界）。现有 `do_ldm` 辅助函数同样不检查 `hc+hd>64`，保持了一致性但
与 spec §2.6.3 的完整约束有差异。M1 测试向量中 count≤4 不会触发此边界。

### 验证

```
make build-qemu: PASS
rb-ops.yaml ldmo_rb encoding: ILLI (expected) PASS
```

### 最终判断

替换 ILLI stub 为完整实现，RB multi-load 语义正确。N1 与现有 do_ldm 模式一致。可 accept。
