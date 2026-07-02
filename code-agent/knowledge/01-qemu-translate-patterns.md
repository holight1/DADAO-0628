# §1 QEMU translate.c 约定与 DADAO 分支偏移语义

**来源**：DL-028a/029a review（2026-07-02，commit 815d204）  
**交叉验证**：RISC-V / Alpha / TriCore target translate.c（QEMU 10.0.0）

---

## §1.1 pc_next 在 trans_* 运行时的值

`dadao_tr_translate_insn` 的执行顺序：

```c
decode_opc(env, ctx);        // trans_* 在此调用，pc_next = PC_branch
ctx->base.pc_next += 4;      // 事后才加
```

`translator_ldl_swap` 只读 opcode，**不更新** `pc_next`。  
→ 在任何 trans_* 函数内，`ctx->base.pc_next` = **当前指令地址**（不是 PC+4）。

**这是 QEMU 全 target 统一惯例**，RISC-V/Alpha/TriCore 完全相同，没有哪个 target 引入额外的 `pc_cur` 变量消歧义。

---

## §1.2 DADAO 分支目标公式

```c
// not-taken（fall-through）
target = ctx->base.pc_next + 4          // = PC_branch + 4

// taken，imm 单位为 word
target = ctx->base.pc_next + 4 + imm * 4   // = PC_branch + 4 + imm*4
```

偏移基点是 **PC+4**（分支指令的下一条地址），不是 PC 本身。

| imm | 目标 | 效果 |
|-----|------|------|
| 0 | PC_branch + 4 | 等效 NOP（两路径相同） |
| 1 | PC_branch + 8 | 跳过下一条 |
| -1 | PC_branch + 0 | 跳到自身（死循环） |

**与其他 ISA 对比**：RISC-V/Alpha 用 `pc_next + imm*N`（imm=0 = 跳到自身）；DADAO 多加了 `+4`，是 spec 层面的设计选择，不是 workaround。

---

## §1.3 jump_i / call_i 目标公式

```c
// jump_i (iiii format, imm24)
uint64_t target = (ctx->base.pc_next + 4) + (int64_t)a->imm24 * 4;

// call_i 目标同 jump_i
uint64_t target = (ctx->base.pc_next + 4) + (int64_t)a->imm24 * 4;

// call_i/call_r 返回地址
ra[63] = ctx->base.pc_next + 4;   // ← 注意：是 pc_next + 4，不是 pc_next
```

**已知 bug（已修复，commit 815d204）**：DS 在 DL-028a 实现时将 `ra[63]` 写为 `pc_next`（= call 指令自身），导致 ret 会跳回 call 形成死循环。架构师直修为 `pc_next + 4`。

---

## §1.4 branch-over-poison 测试 pattern

由 DL-029a（`build_branch_test_binary`）建立的测试 binary layout：

**taken pattern**（验证跳转确实发生）：
```
[setup registers]
[branch imm=+1]      ← taken 时跳过 unimp → exit=0 → PASS
[unimp/poison]       ← not taken 时 ILLI → FAIL
[emit_exit(0)]
```

**not_taken pattern**（验证条件不满足时不跳）：
```
[setup registers]
[branch imm=+1]      ← taken 时跳过 exit → unimp → ILLI → FAIL
[emit_exit(0)]
[unimp/poison]
```

imm=+1 时的偏移：target = PC_branch + 4 + 1×4 = PC_branch + 8，即 **跳过紧邻的一条指令**。

---

## §1.5 jump_r 的目标计算

`jump_r rb[ha], rd[hb], imm12`：

```
target = (rb[ha] & 0x0000FFFFFFFFFFFF) + rd[hb] + imm12
```

测试 binary 中：`rb[ha] = BINARY_BASE`，`rd[hb] = exit_offset_from_base`，imm12=0。  
`load_reg(rb, ...)` 固定 3 wydes = 12 bytes；`load_reg(rd, 4 wydes)` 固定 16 bytes。  
→ `exit_offset = 12 + 16 + 4(jump_r) + 4(unimp) = 36 bytes`（对 taken pattern 成立）。

---

## §1.6 ret 的返回地址约定

`ret rd_retval, imm`：从 ra[63] 取返回地址，跳到 ra[63] + imm*4。

- ra[63] 在 CPU 复位时 = 0；不经 call 直接执行 ret → 跳到 addr=0 → halt rd0 → ILLI
- call 正确压栈后 ra[63] = call_addr + 4（分支后第一条指令）
- ret 的 semantic 测试需要先执行 call 建立 ra[63]（DL-030a scope）
