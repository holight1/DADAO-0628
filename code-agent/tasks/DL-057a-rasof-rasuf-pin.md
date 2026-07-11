# DL-057a: RASOF/RASUF 退出码四方对齐 + 向量 + 嵌套 E2E 收口

**执行环境**: 本地 DS · DADAO-0628（QEMU target/dadao + Sail + 向量 + lit E2E）

**状态**: 待执行

**前置**: DL-056c（QEMU 补 RegRAS 栈，嵌套 call 双后端 42）；ADR-0004 §D5 已 pin `RASOF=0x84 / RASUF=0x85`

---

## 背景

RASOF/RASUF 退出码此前从未 pin（ADR-0004 当年只定了 ILLI/MALIGN/UNDI），四方各拍：
QEMU `0x87/0x86`、Sail `0x82`(归 ILLI 类)、gem5 `0x84/0x85`、runner FAULT_CODES 曾缺。
架构师已 pin 为 **`RASOF=0x84 / RASUF=0x85`**（ADR-0004 §D5，退出码数字是测试机约定、故障类型来自 spec §5.6），
并已改好 3 个 runner 的 `FAULT_CODES` + gem5 faults.hh 本就 0x84/0x85。**剩 QEMU、Sail 未对齐，且全仓无 RASOF/RASUF 向量、嵌套 E2E 未入 lit。**

## 目标

1. **QEMU 对齐**：`helper.c` 里 `helper_ras_push` 的 RASOF `0x87→0x84`、`helper_ras_pop` 的 RASUF `0x86→0x85`；重生成 `components/qemu/patches/0012-qemu-ras-stack.patch`（format-patch，覆盖原文件、series 不变）。
2. **Sail 对齐**：`sail/dadao_types.sail` 的 `fault_to_code`（或等价映射）`F_RASOF => 0x84`、`F_RASUF => 0x85`，删掉“surfaces as ILLI-class”注释（不再归 ILLI）。
3. **interp 无需改**（只抛命名 `Fault('RASOF'/'RASUF')`，退出码由 runner FAULT_CODES 映射）——**验证**其 RAS 路径确无硬编码 0x82 即可。
4. **加 RASOF/RASUF 单指令故障向量**（可向量化：靠 input_state 摆好 RAS 状态 + 一条 call/ret 触发故障）：
   - **RASUF**：冷 RAS（`ra1..ra63` 低 48 位全 0）+ 一条 `ret` → RASUF(0x85)。
   - **RASOF**：满 RAS（`ra1[63:48]≠0`，即最深槽已占）+ 一条 `call` → RASOF(0x84)。
   - 放 `tests/vectors/isa/`（新文件或并入 control-flow.yaml，按现有 yaml schema）；expected 用故障名（RASOF/RASUF），**不写死码号**（码号由 runner 映射）。
   - 四方跑 **AGREE**（interp/QEMU/gem5/Sail 都判 RASOF/RASUF；若某后端 HARNESS abstain 需注明理由，不算 AGREE 但不阻塞）。
5. **嵌套 call E2E 入 lit**：把 DL-056c 已跑通的 `crt0→main→callee`（2 层，exit=42）真 llc 产物固化成一条 lit E2E 用例（QEMU+gem5 双后端），进现有 E2E smoke 套件——**被测对象是 llc 产物，禁手搓**（DS.md §工作规则）。

## 约束
- QEMU 只改 `target/dadao`，语义不动（DL-056c 的栈算法已对），**只改两个码号**；patch 重生成后 apply 干净。
- Sail 只改码号映射，不动 RAS 状态机语义。
- **不回归**：现有 204 差分向量（198 AGREE + 6 HARNESS）、smoke E2E（QEMU+gem5）、DL-056c 嵌套 42 全绿。
- 向量遵守 `feedback_dadao_test_vector_constraints`（rd0 禁入 input_state、RB 48-bit 截断等）；RAS 状态设定确认 harness 支持写 ra 寄存器。

## 验收（架构师亲自复跑）
```bash
cd ~/DADAO-0628
# 1. QEMU 重建 + 码号
(cd .work/source/qemu/build && ninja qemu-system-dadao 2>&1 | tail -1)
grep -n "0x84\|0x85" .work/source/qemu/target/dadao/helper.c   # RASOF=0x84 RASUF=0x85，无 0x86/0x87
# 2. Sail 码号
grep -n "F_RASOF\|F_RASUF" sail/dadao_types.sail                # => 0x84 / 0x85
# 3. 四方差分（含新 RASOF/RASUF 向量）
python3 tests/scripts/run_differential.py 2>&1 | tail -5        # 新向量 AGREE，总数不回归
# 4. RASOF/RASUF 单后端确认退出码
#   （QEMU/gem5 各跑 RASUF 冷 ret 向量 → exit=0x85=133；RASOF 满栈 call → exit=0x84=132）
# 5. 嵌套 E2E lit
llvm-lit -v tests/e2e/ 2>&1 | tail -5                           # 含 nested-call，QEMU+gem5 双绿
```

## 参考指针
- ADR-0004 §D5（RASOF=0x84/RASUF=0x85 定义）；issues.yaml `rasof-rasuf-exit-code-unpinned`、`RASUF-cold-ret`、`qemu-no-ras-stack`
- QEMU：`.work/source/qemu/target/dadao/helper.c`（`helper_ras_push`/`helper_ras_pop` 内 `dadao_raise_exception(env, 0x87/0x86, 0)`）；patch 生成参 0009~0012、`components/qemu/patches/series`
- Sail：`sail/dadao_types.sail`（`enum fault_kind` + `fault_to_code` 映射，L37-38）
- interp：`tools/dadao_interp.py` L416/434（`Fault('RASOF'/'RASUF')`）、`_ras_push`/`_ras_pop`（RAS 状态机，spec §5.6 正确算法）
- 向量 schema：`tests/vectors/isa/control-flow.yaml`（现有 call/ret 向量，看 input_state 如何设寄存器）；runner FAULT_CODES 已含 RASOF/RASUF
- 嵌套 E2E 复现命令：DL-056c 完成区（`printf ...m.ll → llc → llvm-mc → +crt0 → flat binary`）；现有 lit E2E smoke 位置 `tests/e2e/`（若无则参 smoke 套件组织方式新建）
- spec §5.6（RegRAS overflow=RASOF/underflow=RASUF，精确故障，RA 不改）

—— 通用验收/自审纪律见 DS-common（§5 反偷换：被测=真 llc 产物 + 真跑的四方，别改测例/码号绕过）与 DS.md §自审流程（subagent 代码级）。
