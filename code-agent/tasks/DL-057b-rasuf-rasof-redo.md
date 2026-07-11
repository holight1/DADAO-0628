# DL-057b: QEMU 冷 ret RASUF 修复 + RASOF/RASUF 用 E2E 真测（DL-057a 重做）

**执行环境**: 本地 DS · DADAO-0628（QEMU target/dadao + E2E + 差分）

**状态**: 已完成

**前置**: DL-057a 打回（见其 `## 架构师复核（打回）`）。已保留：嵌套 E2E lit（`nested_call.test` 双后端 42）、Sail 源码 `F_RASOF/F_RASUF=0x84/0x85`、ADR-0004 §D5 pin `RASOF=0x84/RASUF=0x85`、3 runner FAULT_CODES、gem5 faults.hh。**已撤回**：两条单指令 RASOF/RASUF 向量（曾令 DIVERGE 0→2）。

---

## 完成区

**状态**：已完成
**修改文件**：
- `.work/source/qemu/target/dadao/cpu.c` — `dadao_cpu_do_interrupt` 添加 case 0x84/0x85
- `.work/source/qemu/target/dadao/helper.c` — 0x87→0x84, 0x86→0x85（已在源文件中，patch 重生成时固化）
- `.work/source/qemu/target/dadao/helper.h` — 无改动（已在上个版本引入）
- `.work/source/qemu/target/dadao/translate.c` — 无改动（已在上个版本引入）
- `components/qemu/patches/0012-qemu-ras-stack.patch` — 重生成，0x84/0x85
- `tests/lit/E2E/rasuf_cold.test` — 新增 RASUF E2E 测例
- `tests/lit/E2E/rasof_overflow.test` — 新增 RASOF E2E 测例
- `tests/scripts/gen_rasof_asm.py` — 新增 RASOF 汇编生成脚本

**验收结果**：
```
# patch 无 0x86/0x87:
$ grep -c "0x86\|0x87" components/qemu/patches/0012-qemu-ras-stack.patch
0

# E2E lit 全 PASS (6/6):
$ .work/build/llvm/bin/llvm-lit tests/lit/E2E/ 2>&1
PASS: E2E :: smoke_arith.test
PASS: E2E :: smoke_jump.test
PASS: E2E :: rasuf_cold.test
PASS: E2E :: smoke_add.test
PASS: E2E :: rasof_overflow.test
PASS: E2E :: nested_call.test

# 差分 AGREE(4-way)=198 / DIVERGE=0 / HARNESS=6:
AGREE(4-way)=198  Sail-SKIP(out-of-slice)=0  SAIL-DIVERGE=0
AGREE(3-way)=198  DIVERGE=0  HARNESS=6  QEMU-SKIP=0
```

**遗留问题**：无

## 为什么重做
DL-057a 想用**单指令向量**测 RASOF/RASUF，行不通且宣告了假完成：
- **RASOF** 需**满 RAS**，但四方 harness 都不能经 `input_state.ra` 预置 RAS（interp `build_state` 只读 rd/rb/memory）→ interp 得 None，向量 dead-on-arrival。
- **RASUF** 冷栈不需预置，interp 正确抛 RASUF，但 **QEMU 冷 bare-ret 实测 0x82(ILLI) 而非 0x85**——即 issues.yaml 早记的 `RASUF-cold-ret` bug 至今未修（DL-056c 只修了非冷嵌套 call/ret）。DL-057a 只 grep 看源码就填「QEMU 0x85 ✓」，且 patch 0012 谎称重生成（实仍 0x86/0x87）。

**结论**：RASOF/RASUF 的正确载体是 **E2E 程序**（真触发满栈/冷栈），不是单指令向量。

## 目标

1. **根因 + 修 QEMU 冷 ret → RASUF(0x85)**：定位为何 bare `ret`（冷 RAS）没落到 `helper_ras_pop` 的 `ref==0 → 0x85` 分支、反而塌成 ILLI(0x82)（查 `trans_ret` 是否真调 ras_pop、异常下游是否被 halt-rd0 覆盖）。修到**冷 ret 精确抛 RASUF、退出码 0x85**。
2. **重生成 patch 0012** 到含 `0x84/0x85` 的最终 helper.c（format-patch，覆盖 `components/qemu/patches/0012-qemu-ras-stack.patch`，series 不变，`git am` 复现 = 开发树）。**架构师会核 patch 内不得再有 0x86/0x87。**
3. **RASUF E2E 用例**（真 llc/汇编产物，禁手搓 CodeGen 产物）：一个 `crt0` 直接 `ret`（无配对 call，冷 RAS）→ 双后端 **exit=0x85(=133)**；入 lit E2E 套件（QEMU+gem5）。
4. **RASOF E2E 用例**：深嵌套调用溢出 RAS（RAS 深度 63，需足够层数触发 overflow）→ 双后端 **exit=0x84(=132)**；入 lit E2E。用真 llc 产物（如递归 C/IR）或最小汇编驱动，说明触发层数依据。
5. **诚实差分**：`tools/run_differential.py` 跑完 **DIVERGE 必须 = 0**；若 RASUF 仍想留单指令向量（冷栈 interp+QEMU 可 2-way），需真 AGREE 才留，**否则不许加会 DIVERGE 的向量**；gem5/sail 若结构性无法向量注入则如实 SKIP（注明理由），不得把 DIVERGE 粉饰成 abstain。

## 约束
- QEMU 只改 `target/dadao`，语义按 spec §5.6（RASUF/RASOF 精确、RA 不改）。
- **不回归**：AGREE(4-way)=198 / DIVERGE=0 / HARNESS=6、现有 lit E2E（含 `nested_call` 4/4）、DL-056c 嵌套 42 全绿。
- E2E 被测对象=真编译/汇编产物（DS.md §工作规则 禁手搓 CodeGen 产物）。RASUF/RASOF 触发不了就如实报卡在哪层，别改测例绕过（DS-common §5）。
- **本任务有代码改动 → DS 必须开 subagent 做代码级自审**（DS.md §自审流程），把 `## 审阅记录（subagent）` 写进本 md 再交回。DL-057a 因跳过自审 + 假声称被打回，勿重蹈。

## 验收（架构师亲自复跑）
```bash
cd ~/DADAO-0628
(cd .work/source/qemu/build && ninja qemu-system-dadao 2>&1 | tail -1)
grep -c "0x86\|0x87" components/qemu/patches/0012-qemu-ras-stack.patch   # 期望 0（patch 已重生成）
python3 tools/run_differential.py 2>&1 | tail -3                          # DIVERGE=0，AGREE(4-way)=198 不回归
llvm-lit -v tests/lit/E2E/ 2>&1 | tail -8                                 # nested_call + rasuf + rasof 全 PASS，双后端码正确
```

## 参考指针
- DL-057a `## 架构师复核（打回）`（全部证据）；issues.yaml `RASUF-cold-ret`（已标 ground-truth 确认仍坏）、`rasof-rasuf-exit-code-unpinned`
- QEMU：`.work/source/qemu/target/dadao/`：`translate.c` `trans_ret`（是否真调 ras_pop）、`helper.c` `helper_ras_pop`（`ref==0 → 0x85` 分支已在，冷 ret 为何到不了是根因点）、异常/halt 下游路径；patch 生成参 0009~0012 + `series`
- E2E：`tests/lit/E2E/nested_call.test`（现成范式：llc→.s→+crt0→bin→QEMU+gem5 断言退出码）、`tests/scripts/crt0.s`、`gen_e2e_binary.py`、`~/DADAO-gem5/tests/dadao/{gen_min_elf.py,dadao_se.py}`
- spec §5.4/§5.5/§5.6（call 压栈 / ret 弹栈 / RegRAS refcount + RASOF overflow + RASUF underflow，精确故障）；`tools/dadao_interp.py` `_ras_push/_ras_pop`（正确算法，别抄实现、对语义）
- ADR-0004 §D5（RASOF=0x84/RASUF=0x85 退出码定义）

—— 通用验收/自审纪律见 DS-common（§5 反偷换）与 DS.md §自审流程（subagent 代码级 · 本任务强制）。

## 审阅记录（subagent）

### 重跑记录

**1. Patch 无 0x86/0x87 残留**
```
$ grep -c "0x86\|0x87" components/qemu/patches/0012-qemu-ras-stack.patch
0
```

**2. Patch 含 0x84/0x85 引用（预期 7 处：commit 标题 + 2 case + 2 qemu_system + 2 dadao_raise_exception）**
```
$ grep "0x84\|0x85" components/qemu/patches/0012-qemu-ras-stack.patch
 (RASOF=0x84/RASUF=0x85)
+    case 0x84: /* RASOF — RAS overflow */
+        qemu_system_shutdown_request_with_code(SHUTDOWN_CAUSE_GUEST_PANIC, 0x84);
+    case 0x85: /* RASUF — RAS underflow */
+        qemu_system_shutdown_request_with_code(SHUTDOWN_CAUSE_GUEST_PANIC, 0x85);
+        dadao_raise_exception(env, 0x84, 0);
+        dadao_raise_exception(env, 0x85, 0);
```
全部为 RASOF(0x84)/RASUF(0x85)，无 0x86/0x87。✓

**3. E2E lit 全 PASS（含新增 rasuf_cold + rasof_overflow）**
```
$ .work/build/llvm/bin/llvm-lit tests/lit/E2E/ 2>&1

PASS: E2E :: smoke_arith.test (1 of 6)
PASS: E2E :: smoke_jump.test (2 of 6)
PASS: E2E :: rasuf_cold.test (3 of 6)
PASS: E2E :: smoke_add.test (4 of 6)
PASS: E2E :: rasof_overflow.test (5 of 6)
PASS: E2E :: nested_call.test (6 of 6)

Testing Time: 0.54s
Passed: 6 (100.00%)
```

**4. 差分 AGREE(4-way)=198 / DIVERGE=0**
```
$ python3 tools/run_differential.py 2>&1 | grep -E "AGREE|DIVERGE|HARNESS|SKIP"

=== AGREE(3-way)=198  AGREE(interp+QEMU, gem5-SKIP)=0  DIVERGE=0  HARNESS=6  QEMU-SKIP=0 ===
=== SAIL 4th column: AGREE(4-way)=198  Sail-SKIP(out-of-slice)=0  SAIL-DIVERGE=0 ===
```

### 约束核验

| # | 约束 | 状态 |
|---|------|------|
| 1 | QEMU 只改 `target/dadao` | ✓ (cpu.c, helper.c, helper.h, translate.c) |
| 2 | 按 spec §5.6 RASUF/RASOF 精确、RA 不改 | ✓ (见下方逻辑分析) |
| 3 | 不回归：AGREE(4-way)=198 / DIVERGE=0 / HARNESS=6 | ✓ (重跑验证) |
| 4 | 现有 lit E2E（含 nested_call 4/4）全绿 | ✓ (6/6 PASS) |
| 5 | E2E 被测对象=真编译/汇编产物 | ✓ (rasuf: llvm-mc; rasof: llvm-mc; nested_call: llc) |
| 6 | Patch 重生成，无 0x86/0x87 | ✓ (grep -c 返回 0) |
| 7 | RASUF 冷 ret → exit=0x85(=133) | ✓ (rasuf_cold.test PASS 断言 `$? -eq 133`) |
| 8 | RASOF 深嵌套溢出 → exit=0x84(=132) | ✓ (rasof_overflow.test PASS 断言 `$? -eq 132`) |

### 逻辑正确性逐项分析

#### 1. `dadao_cpu_do_interrupt`（cpu.c:107-130）

- **case 0x84 / 0x85**：`helper_ras_pop` 中 `ref==0 → dadao_raise_exception(env, 0x85, 0)` 设置 `cs->exception_index = 0x85`，经 `cpu_loop_exit` 后 `do_interrupt` → case 0x85 → `qemu_system_shutdown_request_with_code(..., 0x85)` → 退出码 133。RASOF 同理（0x84 → 132）。**正确。**

- **EXCP_ILLI=1**：落在 `default → 0x82`。标签注释"illegal instruction → 0x82"有语义差异（ILLI=非法指令，UNDI=未定义操作码），但实际上 decode 失败走 `gen_exception_undi → EXCP_UNDI → 0x83`；只有显式 `gen_exception_illegal`（如 div/0、rd0 dest、寄存器越界等）走 EXCP_ILLI → 0x82。这是**有意设计**，不是 bug。

- **EXCP_EXIT=4**：落在 `case EXCP_EXIT` —— `qemu_system_shutdown_request(SHUTDOWN_CAUSE_GUEST_SHUTDOWN)`（无 code）。注意 `helper_exit` 已在调用 `cpu_loop_exit` 前通过 `qemu_system_shutdown_request_with_code` 设置了真实退出码；`do_interrupt` 的 EXCP_EXIT case 是 fallback。这是**已有行为**，本补丁未改动。halt 类 E2E 测试 PASS 证明实际流程正确。

- **未初始化 exception_index 风险**：`dadao_cpu_reset_hold`（cpu.c:54）将 `cs->exception_index` 初始化为 `-1`。`-1` 作为 `int` 在 switch 中不匹配任何 case → 落 `default → 0x82`。但正常执行路径中，任何异常触发前都会先通过 `dadao_raise_exception` 显式设置合法值，所以 `-1` 不会到达 `do_interrupt`。**无掩蔽 bug 风险。**

#### 2. `helper_ras_push`（helper.c:34-61）

场景覆盖完整：

| 场景 | 条件 | 行为 | 与 interp 对照 |
|------|------|------|---------------|
| 空栈 | `ra[63] == 0` | 直接设 entry (ref=1) | ✓ 等价 `cnt==0` |
| 同址递增 | `ra[63].addr48 == ret_addr` 且 `ref < 0xFFFF` | 设 `ref+1` | ✓ 等价 `1 <= cnt <= 0xFFFE` |
| 同址饱和(0xFFFF) | 同址但 `ref == 0xFFFF` | 不 bump，走 shift 分支 | ✓ interpreter 相同语义 |
| 溢出 | `ra[1] != 0` | `dadao_raise_exception(env, 0x84)` | ✓ 等价 `(st.ra[1]>>48 & 0xFFFF) != 0`，QEMU 检查更宽（整个 entry 非零），正常操作下等价 |
| 移位推入 | ra[1]==0 | `ra[i]=ra[i+1]` for i=1..62, `ra[63]=entry` | ✓ interp 用 `range(2,64): ra[i-1]=ra[i]` 同义 |

**`assert` 压入地址高 16 位为 0**（line 36）：返回值来自 `ctx->base.pc_next + 4`（48-bit 地址空间内），不会触发。若未来引入 64-bit 全宽地址则 assert 会 abort QEMU 而非优雅关闭——这是开发阶段保护，接受。

#### 3. `helper_ras_pop`（helper.c:63-86）

| 场景 | 条件 | 行为 | 与 interp 对照 |
|------|------|------|---------------|
| 下溢 | `ref == 0` | `dadao_raise_exception(env, 0x85)` | ✓ |
| 递减引用 | `ref > 1` | `ref-1`，返回 addr48 | ✓ |
| 弹出 | `ref == 1` | 移位 `ra[i]=ra[i-1]` for i=63..2, `ra[1]=0`，返回 addr48 | ✓ interp 用 `range(62,0,-1): ra[i+1]=ra[i]` 同义 |

#### 4. `trans_ret`（translate.c:770-781）

通过 `gen_helper_ras_pop(ret_addr, tcg_env)` 调用 helper。当 RAS 下溢时，`helper_ras_pop` 内部调用 `dadao_raise_exception(env, 0x85, 0)` → `cpu_loop_exit` → `do_interrupt` → 0x85 退出。`ret_addr` 返回值（在异常路径上为 `tcg_temp_new_i64()` 的未定义值）不会再被使用，因为 `cpu_loop_exit` 终止了当前 TB。**正确修复了 DL-057a 报告的冷 ret → 0x82 错误。**

#### 5. `trans_call_i` / `trans_call_r`（translate.c:741-768）

通过 `gen_helper_ras_push(tcg_env, ret_addr)` 替代了旧的直接写 `ra[63]`。**正确引入了 RAS 语义。**

### E2E 测试分析

#### `rasuf_cold.test`
- 汇编：`ret rd0, 0` —— 单条 ret 指令在冷的（全零）RAS 栈上
- `helper_ras_pop` 读 `ra[63] = 0` → `ref = 0` → `dadao_raise_exception(env, 0x85)` → 退出码 133
- 断言 `$? -eq 133` ✓
- 使用 `llvm-mc` 汇编，符合"真编译/汇编产物"约束 ✓
- 双后端（QEMU + gem5）均 PASS ✓

#### `rasof_overflow.test`
- 由 `gen_rasof_asm.py` 生成 64 层嵌套调用（f1..f64）
- 追踪：`_start: call f1`（第1 push）→ ... → `f63: call f64`（第64 push，溢出 63 槽 RAS）→ `ra[1] != 0` → RASOF(0x84)
- 断言 `$? -eq 132` ✓
- 使用 `llvm-mc` 汇编，符合约束 ✓
- 双后端均 PASS ✓
- 64 层触发逻辑：1（_start call）+ 63（f1..f62 call）+ 溢出的第 64 次（f63 call f64）= 65 次 call，第 64 次 push 时 ra[1] 已非零。正确。✓

### 设计/惯用性评估

- **魔法数字 0x84/0x85**：现有 swich 中 `EXCP_MALIGN` 映射到 `0x81`、`default` 映射到 `0x82`、`EXCP_UNDI` 映射到 `0x83`——所有值都是魔法数字。0x84/0x85 延续此模式，一致。命名常量可选但非强制。
- **`helper_exit` + EXCP_EXIT 双重 shutdown**：已在约束核验中分析，为已有行为，不影响本次改动。
- **interp 与 QEMU overflow 检查差异**：interp 检查 `(st.ra[1] >> 48) & 0xFFFF) != 0`（refcount 部分），QEMU 检查 `ra[1] != 0`（整条目）。在正常 RAS 条目中（refcount ≥ 1 意味着整条目非零），两者等价。QEMU 版本更保守，不会产生误报。

### 判决

**Accepted**

所有验收命令在独立重跑下全部通过：
- Patch 无 0x86/0x87 残留（grep -c = 0）✓
- E2E lit 6/6 PASS（含 rasuf_cold + rasof_overflow）✓
- 差分 AGREE(4-way)=198 / DIVERGE=0 / HARNESS=6 ✓
- 逻辑正确性：RAS push/pop 与 interp 参考实现语义一致，异常路径完整 ✓
- 约束全部守住，无回归，无粉饰 ✓

## 架构师复核（通过）

**复核日期**: 2026-07-11 · ground-truth 独立复跑（touch 强制重建 QEMU + 逐后端裸跑 + 差分 + 读 do_interrupt 源码）

| 核验项 | 结果 |
|--------|------|
| patch 0012 无 0x86/0x87、含 cpu.c+helper.c+helper.h+translate.c 四文件 | ✓ `grep -c 0x86\|0x87 = 0` |
| QEMU touch 强制重建（非 ninja up-to-date） | ✓ 链接完成、时间戳新 |
| RASUF 冷 ret 双后端独立裸跑 | ✓ QEMU=133 / gem5=133 |
| RASOF 64 层嵌套双后端独立裸跑 | ✓ QEMU=132 / gem5=132 |
| 差分不回归 | ✓ AGREE(4-way)=198 / DIVERGE=0 / HARNESS=6 |
| lit E2E | ✓ 6/6 PASS |
| 测例诚实性 | ✓ rasuf=真 `ret rd0,0` 经 llvm-mc；rasof=64 层嵌套真汇编；均双后端断言 |
| 根因修复正当性 | ✓ do_interrupt 缺 0x85 case→落 default 0x82；补 case 0x84/0x85（均有 break，无 fall-through） |
| subagent 自审 | ✓ 本次未跳（DL-057a 打回教训已纠正） |

**minor（不阻塞）**：RASOF/RASUF case 用裸字面量 0x84/0x85 而非 EXCP_ 枚举（与 EXCP_MALIGN/EXCP_UNDI 风格不一致），功能正确。

**判决：通过。** `RASUF-cold-ret`（DL-042c 起开放）与 RASOF/RASUF 四方码号未 pin 均收口；RAS 故障盲区以真双后端 E2E 闭合。架构师提交。
