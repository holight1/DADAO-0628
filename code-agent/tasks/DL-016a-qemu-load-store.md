# DL-016a: QEMU RD Load/Store 语义（Phase 3）

**执行环境**：本地 DS · DADAO-0628

---

## 目标

1. **前置修复**：修复 `0002-dadao-hw-meson-subdir.patch`（当前 corrupt，无法 `git am` 应用）
2. **实现**：RD 单次和多次 load/store 共 22 条 trans 函数的 TCG 语义

完成后 `qemu-system-dadao -M dadao-m1 ...` 能正常启动（机器注册），
load/store 指令正确读写大端内存，MALIGN 精确触发。

---

## 前置条件（必须先完成，再实现 load/store）

### 修复 `0002-dadao-hw-meson-subdir.patch`

当前 patch 的 hunk header `@@ -1,3 +1,4 @@` 与 diff body 实际行数不符，
导致 `git am` 报 "corrupt patch at line 12"。

**修复步骤**（在 `.work/qemu/` 中执行）：

```bash
cd .work/qemu
# 确保当前处于干净基线（仅 apply 了 0001）
git log --oneline  # 应只有 1 条 dadao 提交

# 手动编辑 hw/meson.build，在 subdir('cxl') 后插入 subdir('dadao')
# 按字母顺序，找到 subdir('cxl') 所在行，在其后插入

# 生成新 patch
git add hw/meson.build
git diff --cached > /tmp/new-0002.patch
# 或用 git format-patch HEAD~ 方式生成

# 验证
git apply --check /tmp/new-0002.patch   # 必须无错
git reset HEAD hw/meson.build
```

将新生成的 patch 替换 `components/qemu/patches/0002-dadao-hw-meson-subdir.patch`，
格式必须能被 `git am` 干净应用。

**验证整个 patch 序列**：

```bash
# 从干净 QEMU baseline 依次 apply 全部 patch
cd .work/qemu
git am ../../../components/qemu/patches/0001-dadao-target-skeleton.patch
git am ../../../components/qemu/patches/0002-dadao-hw-meson-subdir.patch  # 必须成功
git am ../../../components/qemu/patches/0003-dadao-decodetree.patch
git am ../../../components/qemu/patches/0004-dadao-rd-arith.patch

# 重新 build
make build-qemu

# 验证机器注册
qemu-system-dadao -M ?  # 必须显示 dadao-m1
```

**只有上述全部通过后，才继续实现 load/store 内容。**

---

## 交付物

### Patch（`components/qemu/patches/0005-dadao-load-store.patch`）

文件：`target/dadao/translate.c`（替换 ILLI stub 为真实 TCG）

---

## 指令实现规格

### 内存访问辅助函数约定

```c
/* EA 计算：48-bit 截断 */
static inline uint64_t gen_ea_rb(uint64_t rb_val, int64_t offset)
{
    return (rb_val + offset) & 0x0000FFFFFFFFFFFF;
}
```

TCG 层直接使用 `tcg_gen_qemu_ld/st` 系列接口，以 `MemOp` 指定宽度、符号和字节序：
- 大端 load/store 通过 `MO_BE` flag
- EA = `rbhb[47:0] + sext12(imms12)`，高 16 位截断（`& 0xFFFFFFFFFFFF`）

---

### §3.1 RD 单次 Load（7 条，格式 `rrii`，`contracts/isa/spec.md §3.1`）

```
ldbs  rdha, rbhb, imms12   ; 1 byte, sign-extend to 64
ldbu  rdha, rbhb, imms12   ; 1 byte, zero-extend to 64
ldws  rdha, rbhb, imms12   ; 2 bytes, sign-extend to 64
ldwu  rdha, rbhb, imms12   ; 2 bytes, zero-extend to 64
ldts  rdha, rbhb, imms12   ; 4 bytes, sign-extend to 64
ldtu  rdha, rbhb, imms12   ; 4 bytes, zero-extend to 64
ldo   rdha, rbhb, imms12   ; 8 bytes, no extension
```

**TCG 实现**（以 `ldbs` 为例）：

```c
static bool trans_ldbs(DisasContext *ctx, arg_ldbs *a)
{
    if (a->ha == 0) { gen_exception_illegal(ctx); return true; }  // ILLI: rdha=rd0
    TCGv_i64 addr = tcg_temp_new_i64();
    TCGv_i64 dst  = tcg_temp_new_i64();
    tcg_gen_ld_i64(addr, tcg_env, offsetof(CPUDADAOState, rb[a->hb]));
    tcg_gen_andi_i64(addr, addr, 0x0000FFFFFFFFFFFF);   // 48-bit EA
    tcg_gen_addi_i64(addr, addr, a->imms12);
    tcg_gen_qemu_ld_i64(dst, addr, ctx->mem_idx, MO_SB | MO_BE);  // signed byte, big-endian
    tcg_gen_st_i64(dst, tcg_env, offsetof(CPUDADAOState, rd[a->ha]));
    return true;
}
```

**MemOp 对照表**：

| 指令 | MemOp flags |
|------|------------|
| ldbs | `MO_SB` （1 字节，符号扩展）|
| ldbu | `MO_UB` （1 字节，零扩展）|
| ldws | `MO_BESW`（2 字节大端，符号扩展）|
| ldwu | `MO_BEUW`（2 字节大端，零扩展）|
| ldts | `MO_BESL`（4 字节大端，符号扩展）|
| ldtu | `MO_BEUL`（4 字节大端，零扩展）|
| ldo  | `MO_BEQ` （8 字节大端，无扩展）|

**MALIGN 处理**：QEMU `tcg_gen_qemu_ld_i64` 使用 `MO_ALIGN` flag（或默认对齐检查），
对齐不满足时自动产生 SIGBUS 或 guest memory fault。DADAO 的 MALIGN 精确语义需要
映射到 QEMU 的 `MO_ALIGN_N` flag，确保对齐错误触发 EXCP_MALIGN 而非 SIGSEGV。

具体：
- ldbs/ldbu：无对齐要求，不加 `MO_ALIGN`
- ldws/ldwu：`MO_ALIGN_2`（2 字节对齐，否则 MALIGN）
- ldts/ldtu：`MO_ALIGN_4`
- ldo：`MO_ALIGN_8`

在 `cpu.h` 定义 `EXCP_MALIGN = 2`，在 helper 中处理对齐异常。

**ILLI 检查**：`rdha == 0` → ILLI（per `contracts/isa/spec.md §3.1`）

---

### §3.2 RD 单次 Store（4 条，格式 `rrii`，`contracts/isa/spec.md §3.2`）

```
stb   rdha, rbhb, imms12   ; store bits[7:0]
stw   rdha, rbhb, imms12   ; store bits[15:0]
stt   rdha, rbhb, imms12   ; store bits[31:0]
sto   rdha, rbhb, imms12   ; store bits[63:0]
```

**TCG 实现**：EA 计算同上；`tcg_gen_qemu_st_i64` + 对应 MemOp：

| 指令 | MemOp |
|------|-------|
| stb | `MO_UB`（忽略大端对字节无影响）|
| stw | `MO_BEUW` |
| stt | `MO_BEUL` |
| sto | `MO_BEQ` |

对齐规则同 load（stb 无要求，stw 2-byte，stt 4-byte，sto 8-byte）。

**ILLI 检查**：`rdha == 0` → ILLI（per `contracts/isa/spec.md §3.2`）

---

### §3.3 RD 多次 Load（7 条，格式 `rrri`，`contracts/isa/spec.md §3.3`）

```
ldmbs  rdha, rbhb, rdhc, immu6
ldmbu  rdha, rbhb, rdhc, immu6
ldmws  rdha, rbhb, rdhc, immu6
ldmwu  rdha, rbhb, rdhc, immu6
ldmts  rdha, rbhb, rdhc, immu6
ldmtu  rdha, rbhb, rdhc, immu6
ldmo   rdha, rbhb, rdhc, immu6
```

`EA_i = (rbhb[47:0] + rdhc[47:0] + i × N) mod 2^48`，i = 0 … immu6-1，N = 元素字节数。
目标寄存器：`rd(ha)` … `rd(ha + immu6 - 1)`。

**ILLI 检查**（任一 → ILLI）：
1. `rdha == 0`
2. `immu6 == 0`
3. `rdha + immu6 > 64`（超出 bank 边界）

**TCG 实现**：C 层循环（不生成循环 TCG，展开为 immu6 次 load-store）：

```c
// 先 snapshot rdhc（源地址寄存器）
TCGv_i64 base = tcg_temp_new_i64();
tcg_gen_ld_i64(base, tcg_env, offsetof(CPUDADAOState, rb[a->hb]));
TCGv_i64 idx  = tcg_temp_new_i64();
tcg_gen_ld_i64(idx, tcg_env, offsetof(CPUDADAOState, rd[a->hc]));
// base[47:0] + idx[47:0]，48-bit 截断
for (int i = 0; i < a->hd; i++) {
    TCGv_i64 ea = tcg_temp_new_i64();
    tcg_gen_addi_i64(ea, base_plus_idx, i * N);   // N = element bytes
    tcg_gen_andi_i64(ea, ea, 0x0000FFFFFFFFFFFF);
    TCGv_i64 val = tcg_temp_new_i64();
    tcg_gen_qemu_ld_i64(val, ea, ctx->mem_idx, memop_with_align);
    tcg_gen_st_i64(val, tcg_env, offsetof(CPUDADAOState, rd[a->ha + i]));
    tcg_temp_free_i64(ea);
    tcg_temp_free_i64(val);
}
```

**注意**：rdhc 在循环前 snapshot（不随 rd 写入变化）。

---

### §3.4 RD 多次 Store（4 条，格式 `rrri`，`contracts/isa/spec.md §3.4`）

```
stmb   rdha, rbhb, rdhc, immu6
stmw   rdha, rbhb, rdhc, immu6
stmt   rdha, rbhb, rdhc, immu6
stmo   rdha, rbhb, rdhc, immu6
```

语义对称：`memory_be[ea_i] = rd(ha+i)[N×8-1:0]`。

ILLI 检查同 multi-load。展开循环 store。

---

## 约束

1. **前置修复必须先验证** `git am` + `qemu-system-dadao -M ?` 显示 `dadao-m1` 再继续
2. **大端内存访问**：全部 MemOp 使用 `MO_BE*` 变体，不得使用小端 flag
3. **48-bit EA**：地址计算后必须 `& 0x0000FFFFFFFFFFFF` 截断高 16 位
4. **MALIGN 精确**：对齐错误触发 EXCP_MALIGN，PC 保持在 faulting 指令，无寄存器写入
5. **multi-load/store rdhc snapshot**：在循环前读取 rdhc，循环内不重新 load
6. **bank 边界检查**：`rdha + immu6 > 64` 静态可在 trans 函数中直接检查
7. **make build-qemu PASS**：patch 01+02（新）+03+04+05 全部干净 apply 后 ninja 编译无错
8. **不实现 RB load/store**：ldo-rb/sto-rb/ldmo-rb/stmo-rb 属于 DL-017a

---

## 验收步骤（DS 完成区填写）

```
# 前置修复验证
git am components/qemu/patches/0002-dadao-hw-meson-subdir.patch  →  PASS
make build-qemu                                                   →  PASS
qemu-system-dadao -M ?                                           →  显示 dadao-m1

# load/store 编译验证
ninja qemu-system-dadao   →  PASS（translate.c 编译无错）

# 基本功能验证（有 trampoline + test binary 的情况下）
# 小程序：addi rd8, rd0, 42 → sto rd8, rb1, 0 → 读回 → exit
```

---

## 参考指针

| 资源 | 用途 |
|------|------|
| `contracts/isa/spec.md §3.1–§3.4` | 每条 load/store 语义和合法性规则权威来源 |
| `contracts/isa/spec.md §2.6.1, §2.6.3` | ILLI 合法性：rd0 目标、immu6=0、bank 越界 |
| `target/riscv/insn_trans/trans_rvi.c.inc` | QEMU TCG load/store 风格参考（MO_* flags）|
| `components/qemu/patches/0003-dadao-decodetree.patch` | arg_ldbs 等结构体字段名 |
| `components/qemu/patches/0004-dadao-rd-arith.patch` | gen_load_rd / gen_store_rd 辅助函数 |

---

## 完成区

<!-- DS 在此填写 -->
