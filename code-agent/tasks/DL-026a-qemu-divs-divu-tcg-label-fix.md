# DL-026a: 修复 trans_divs / trans_divu TCG label 顺序 bug

**执行环境**: 本地 DS · DADAO-0628

**状态**: 待执行

---

## 背景

`translate.c` 中 `trans_divs` 和 `trans_divu` 存在 TCG label 顺序错误：`gen_set_label(l1)` 被放在 `return true` 之后（dead code），导致：

- TCG SIGABRT（label 未使用）
- 或 brcond 跳转到未定义位置 → 无限循环 → 5 秒 timeout

相关测试在 `tests/vectors/isa/rd-arith.yaml` 中已标记 `status: deferred`，等本任务完成后恢复。

---

## 目标

修复 `translate.c` 中 `trans_divs` / `trans_divu` 的 TCG label 排列顺序，使 divide-by-zero 检查正确分支。

---

## 接口说明书

### 约束

1. **不改变 ISA 语义**：divisor==0 → ILLI；除法结果写入 ha（余数）/ hb（商）。
2. **ha==0 或 hb==0 检查仍需保留**（已有逻辑）。
3. **只改 `translate.c`**，不改其他文件。

### 正确的 TCG 控制流结构

```
check ha==0 → ILLI
check hb==0 → ILLI
check divisor (hd)==0 → brcond_i64 eq → label_div0
    正常除法路径:
        tcg_gen_div_i64 / tcg_gen_rem_i64
        store_rd ha, remainder
        store_rd hb, quotient
        (落穿到 label_ok)
label_div0:
    gen_exception_illegal
label_ok:              ← brcond 跳过异常后的目标
return true
```

注意：`gen_set_label(label_ok)` 必须在 `gen_exception_illegal` 之后、`return true` 之前；`gen_set_label(label_div0)` 紧跟 `brcond`（不在 return 后）。

### 参考指针

- 当前错误位置：`translate.c` 中 `trans_divs` / `trans_divu`，`gen_set_label(l1)` 出现在 `return true` 后面。
- 参考正确模式：`trans_csn`、`trans_csz`（已有 TCG 条件分支的正确写法）。
- 知识库：`code-agent/knowledge/` §4（translate 约束）

---

## 验收

```bash
python3 tests/scripts/run_qemu_test.py tests/vectors/isa/rd-arith.yaml
```

修复后需将 `rd-arith.yaml` 中 divs/divu 的 4 个测试改回 `status: active`，运行全通（包含：
- divs semantic: 17÷4=4 rem 1
- divu semantic: 17÷4=4 rem 1  
- divs encoding: 0x1E042000
- divu encoding: 0x1F042000）

---

## 完成区

（DS 填写）
