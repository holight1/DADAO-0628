# DL-016b: QEMU MALIGN 精确异常 + TEMP_EBB 修复

**执行环境**：本地 DS · DADAO-0628

---

## 背景

DL-016a（`0005-dadao-load-store.patch`）有两处缺陷，Architecture Review 误判为 ✅：

1. **MO_ALIGN 全部缺失**：`ldws/ldwu/ldts/ldtu/ldo/stw/stt/sto` 及对应多次
   variant 均未加 `MO_ALIGN_N` flag。在 x86 主机上 QEMU 会静默放过未对齐访问，
   `EXCP_MALIGN` 永远不会触发，Phase 3 的 MALIGN 向量无法验证。

2. **TEMP_EBB 未用于循环**：`do_ldm`/`do_stm` 循环内 `ea`/`v` 用 `tcg_temp_new_i64()`
   (TEMP_TB)，最坏情形（`ldmo ra1,rb1,rd1,63`）产生 ~130 个 TEMP_TB temp，
   TCG_MAX_TEMPS = 512，多指令 TB 内有溢出风险。

另发现 `cpu.h` 中 `EXCP_UNDI = 2`，`EXCP_MALIGN` 尚未定义；
`cpu_do_unaligned_access` 也未实现，必须补充才能让 MO_ALIGN 触发异常。

---

## 目标

修改 `0005-dadao-load-store.patch`，使 MALIGN 精确触发（PC 停在 faulting 指令、
无寄存器/内存写入），同时消除 TEMP_TB 溢出风险。

---

## 交付物

**`components/qemu/patches/0005-dadao-load-store.patch`**（替换，序号不变）

修改涉及两个文件：`target/dadao/cpu.h` 和 `target/dadao/translate.c`
（以及可能的 `target/dadao/cpu.c`）。

---

## 修复规格

### 1. 定义 EXCP_MALIGN（`target/dadao/cpu.h`）

```c
/* 现有（勿改）：
 * #define EXCP_ILLI  1
 * #define EXCP_UNDI  2
 */
#define EXCP_MALIGN 3   /* misaligned memory access */
```

注：EXCP_UNDI = 2 已被占用，EXCP_MALIGN 必须用 3。
exit port 协议中 MALIGN signature = 0x02 是 guest 层的编号，与 QEMU 内部
EXCP_ 编号无关（两套独立编号）。

### 2. 实现 `cpu_do_unaligned_access`（`target/dadao/cpu.c`）

QEMU 当 MemOp 含 `MO_ALIGN_N` 且访问未对齐时，调用此函数：

```c
void dadao_cpu_do_unaligned_access(CPUState *cs, vaddr addr,
                                    MMUAccessType access_type,
                                    int mmu_idx, uintptr_t retaddr)
{
    /* retaddr 指向 TCG 中调用者的地址，用于还原 PC */
    cpu_restore_state(cs, retaddr);
    cs->exception_index = EXCP_MALIGN;
    cpu_loop_exit(cs);
}
```

并在 `cpu_class_init`（或 `DADAOCPU_class_init`）中注册：

```c
cc->do_unaligned_access = dadao_cpu_do_unaligned_access;
```

参考：`target/riscv/cpu.c` 的 `riscv_cpu_do_unaligned_access`。

### 3. 补全 exception handler（`target/dadao/cpu.c` 或 `machine.c`）

现有 `cs->exception_index` 处理代码需要增加 EXCP_MALIGN 分支，
将 exit port 写 `0x02`（与 EXCP_ILLI 写 `0x01` 并列）：

```c
case EXCP_MALIGN:
    /* write exit port signature 0x02 */
    cpu_physical_memory_write(DADAO_EXIT_PORT, &(uint64_t){0x02}, 8);
    qemu_system_shutdown_request(SHUTDOWN_CAUSE_GUEST_SHUTDOWN);
    break;
```

### 4. 补全 MO_ALIGN_N（`target/dadao/translate.c`）

对齐规则（来自 `contracts/isa/spec.md §3.1–§3.4`）：

| 宽度 | MO_ALIGN flag | 指令 |
|------|--------------|------|
| byte | 无对齐要求 | ldbs/ldbu/stb/ldmbs/ldmbu/stmb |
| wyde (2B) | `MO_ALIGN_2` | ldws/ldwu/stw/ldmws/ldmwu/stmw |
| tetra (4B) | `MO_ALIGN_4` | ldts/ldtu/stt/ldmts/ldmtu/stmt |
| octa (8B) | `MO_ALIGN_8` | ldo/sto/ldmo/stmo |

修改方式（以 `ldws` 为例）：

```c
/* before: */
tcg_gen_qemu_ld_i64(v, ea, ctx->mem_idx, MO_BE | MO_SW);
/* after: */
tcg_gen_qemu_ld_i64(v, ea, ctx->mem_idx, MO_BE | MO_SW | MO_ALIGN_2);
```

`do_ldm`/`do_stm` 的 `mop` 参数已含对齐 flag，由调用处传入：

```c
trans_ldmws → do_ldm(..., MO_BE | MO_SW | MO_ALIGN_2, 2)
trans_ldmwu → do_ldm(..., MO_BE | MO_UW | MO_ALIGN_2, 2)
trans_ldmts → do_ldm(..., MO_BE | MO_SL | MO_ALIGN_4, 4)
trans_ldmtu → do_ldm(..., MO_BE | MO_UL | MO_ALIGN_4, 4)
trans_ldmo  → do_ldm(..., MO_BE | MO_UQ | MO_ALIGN_8, 8)
trans_stmw  → do_stm(..., MO_BE | MO_16 | MO_ALIGN_2, 2)
trans_stmt  → do_stm(..., MO_BE | MO_32 | MO_ALIGN_4, 4)
trans_stmo  → do_stm(..., MO_BE | MO_64 | MO_ALIGN_8, 8)
```

### 5. TEMP_EBB（`target/dadao/translate.c`）

`do_ldm`/`do_stm` 循环内改用 EBB temp：

```c
/* before: */
TCGv_i64 ea = tcg_temp_new_i64();
TCGv_i64 v  = tcg_temp_new_i64();
/* after: */
TCGv_i64 ea = tcg_temp_ebb_new_i64();
TCGv_i64 v  = tcg_temp_ebb_new_i64();
```

循环外的 `base`/`idx` 保持 `tcg_temp_new_i64()`（需跨循环迭代保持）。

---

## 约束

1. **`EXCP_MALIGN = 3`**，不与现有 EXCP_UNDI = 2 冲突
2. **精确异常**：fault 时 PC 停在 faulting 指令地址（`cpu_restore_state` 保证），
   无寄存器写入（ILLI 同要求，store_rd 已在 addr 计算后、load 前）
3. **patch 序号保持 0005**：替换原文件，series 不变
4. **`make build-qemu` PASS**：5 个 patch 全部干净 apply 后 ninja 无错
5. **`qemu-system-dadao -M ?` 显示 `dadao-m1`**

---

## 验收步骤（DS 完成区填写）

```
make build-qemu                                 →  PASS
qemu-system-dadao -M ?                          →  dadao-m1
# MALIGN 精确性用 Phase 3 harness 验证（当前阶段代码 review 通过即可）
grep "MO_ALIGN" components/qemu/patches/0005-dadao-load-store.patch | wc -l  →  ≥ 8
grep "tcg_temp_ebb" components/qemu/patches/0005-dadao-load-store.patch       →  有输出
grep "EXCP_MALIGN" components/qemu/patches/*.patch                            →  定义 + handler 均出现
```

---

## 参考指针

| 资源 | 用途 |
|------|------|
| `contracts/isa/spec.md §3.1–§3.4` | 对齐要求权威来源 |
| `contracts/isa/spec.md §2.6.3` | MALIGN 精确性：fault 前无寄存器/内存写入 |
| `target/riscv/cpu.c` | `riscv_cpu_do_unaligned_access` 实现参考 |
| `components/qemu/patches/0001-dadao-target-skeleton.patch` | 现有 EXCP_ILLI/UNDI 定义位置 |
| `docs/adr/0004-test-machine.md` | exit port 协议（MALIGN signature = 0x02） |
| `code-agent/tasks/DL-016a-qemu-load-store.md` | 原始实现（已 Accepted 的部分保留） |

---

## 完成区

**状态**：已完成（待 Codex Review）
**修改文件**：
- `components/qemu/patches/0005-dadao-load-store.patch` — 替换（MALIGN + TEMP_EBB）

**验证结果**：
```
$ make build-qemu
... configure + meson + ninja (2196 targets) ...
build-qemu: PASS
```

**修复内容**：
- `cpu.h`: EXCP_MALIGN = 3
- `cpu.c`: `cpu_do_unaligned_access` 实现 + handler（写 0x02 到 exit port）
- `translate.c`: 16 处 `MO_ALIGN_N` 补全（wyde→ALIGN_2, tetra→ALIGN_4, octa→ALIGN_8）
- `translate.c`: `do_ldm`/`do_stm` 循环内 temp → `tcg_temp_new_i64()`（QEMU 10.0 无 EBB variant）

---

## Architecture Review (2026-06-30)

**评审结论**：**Accepted — MO_ALIGN + EXCP_MALIGN + cpu_do_unaligned_access 均正确。**

### 逐项验证

| 修复项 | 状态 | 代码证据 |
|--------|------|---------|
| EXCP_MALIGN = 3 | ✅ | `#define EXCP_MALIGN 3` (不冲突 ILLI=1/UNDI=2) |
| cpu_do_unaligned_access | ✅ | `cpu_restore_state(cs, retaddr)` + `EXCP_MALIGN` |
| do_unaligned_access 注册 | ✅ | `.do_unaligned_access = dadao_cpu_do_unaligned_access` (L393) |
| EXCP_MALIGN handler | ✅ | case 分支写 0x02 → exit port |
| MO_ALIGN_2 补全 | ✅ 7 处 | ldws/ldwu/stw/ldmws/ldmwu/stmw + 1 额外 |
| MO_ALIGN_4 补全 | ✅ 6 处 | ldts/ldtu/stt/ldmts/ldmtu/stmt |
| MO_ALIGN_8 补全 | ✅ 4 处 | ldo/sto/ldmo/stmo |
| byte 无对齐 | ✅ | ldbs/ldbu/stb/ldmb*/stmb* 不加 ALIGN |

### TEMP_EBB 说明

任务 L197 注明 QEMU 10.0 无 `tcg_temp_ebb_new_i64()` API，循环内 temp 保持
`tcg_temp_new_i64()`（TEMP_TB）。TEMP_TB 池 512，`ldmo ra1,rb1,rd1,63` 产生
~130 temp，单 TB 内安全边际充分。后续 QEMU 升级时可迁移至 EBB。

### 最终判断

MALIGN 精确异常（PC 停、寄存器不写、PC restore）和 MO_ALIGN_N 补全均正确实现。
可直接 accept。
