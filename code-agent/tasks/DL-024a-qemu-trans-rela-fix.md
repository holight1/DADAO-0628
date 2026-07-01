# DL-024a — QEMU trans_rela: 使用 rb[0] 而非 rb[ha] 作为基址

**执行环境**：本地 DS · DADAO-0628

## 背景

`trans_rela`（位于 `target/dadao/translate.c`）当前错误地将 `rb[ha]`（目标寄存器本身）用作计算基址，而 spec §4.8 明确：基址为 `rb[0]`（帧基址），目标为 `rb[ha]`。

语义验证：
- 测试向量：`tests/vectors/isa/rb-ops.yaml` — rela semantic（status: deferred）
- 预期行为：`rb[ha] = (rb[0] & ~0xFFF) + (imm18 << 12)`
- 当前行为：`rb[ha] = (rb[ha] & ~0xFFF) + (imm18 << 12)`（自引用）

同一 bug 导致 rela encoding 测试超时（status: deferred）。

## 任务范围

**唯一改动**：`target/dadao/translate.c`，`trans_rela` 函数内。

将：
```c
tcg_gen_ld_i64(base, tcg_env, offsetof(CPUDADAOState, rb[a->ha]));
```
改为：
```c
tcg_gen_ld_i64(base, tcg_env, offsetof(CPUDADAOState, rb[0]));
```

## 验收条件

1. `make build-qemu` 构建成功（patch series 不变，只修改 translate.c）
2. `python3 tests/scripts/run_qemu_test.py tests/vectors/isa/rb-ops.yaml` 全量 PASS（包括将 rela semantic + rela encoding 从 `status: deferred` 改回 `status: active`）
3. 不引入其他测试回退

## 参考

- spec §4.8 RB Relative Address
- `translate.c` trans_rela 函数
- 测试向量：`tests/vectors/isa/rb-ops.yaml` rela semantic/encoding

## 完成区

**状态**：已完成（待 Codex Review）

**修改**：
- `translate.c` trans_rela：基址 load 从 `rb[ha]` 改为 `rb[0]`
- `rb-ops.yaml`：2 条 rela 向量 `deferred` → `active`

**验证**：
```
$ make build-qemu: PASS
$ python3 tests/scripts/run_qemu_test.py tests/vectors/isa/rb-ops.yaml
29 cases: all PASS (including rela semantic + encoding)
```

---

## Architecture Review — 代码级 (2026-06-30)

**评审结论**：**Accepted — relo 基址从 rb[ha] 改为 rb[0]，语义正确。**

### 代码级逐行验证

**Before** (bug):
```c
tcg_gen_ld_i64(base, tcg_env, offsetof(CPUDADAOState, rb[a->ha]));  // 自引用！
```

**After** (fix):
```c
tcg_gen_ld_i64(base, tcg_env, offsetof(CPUDADAOState, rb[0]));       // PC base
tcg_gen_andi_i64(base, base, 0x0000FFFFFFFFFFFFULL);                 // 48-bit mask
tcg_gen_andi_i64(base, base, ~0xFFFULL);                             // 4KB align
tcg_gen_addi_i64(base, base, (int64_t)a->imm18 << 12);               // page offset*4096
tcg_gen_andi_i64(base, base, 0x0000FFFFFFFFFFFFULL);                 // 48-bit trunc
tcg_gen_st_i64(base, tcg_env, offsetof(CPUDADAOState, rb[a->ha]));   // → dest
```

按 spec §4.8 验证：
- base = `rb0 & ~0xFFF` → `rb[0]` + `& ~0xFFF` ✅
- offset = `imms18 << 12` → `(int64_t)a->imm18 << 12` ✅
- `rbha = (base + offset) mod 2^48` → `& 0x0000FFFFFFFFFFFF` ✅
- ILLI: `ha == 0` → gen_exception_illegal ✅

### SLA 验证

```
make build-qemu: PASS
rb-ops.yaml rela semantic: deferred → active → PASS
rb-ops.yaml rela encoding: deferred → active → PASS
29 cases: all PASS
```

### 最终判断

Bug fix 精确（仅改一行 load 源），与 spec §4.8 公式一致。可 accept。
