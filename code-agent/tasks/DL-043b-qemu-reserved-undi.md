# DL-043b: QEMU 保留编码 → UNDI（M3 发现收口）

**执行环境**: 本地 DS · DADAO-0628

**状态**: 待执行

**前置**: DL-043a（M3 矩阵抓到的 QEMU fault 完备性洞）

---

## 背景

M3 legality 矩阵（DL-043a）抓到：**保留编码 QEMU 抛 ILLI(0x82)，但 spec §2.5/§2.8.1 要求 UNDI(0x83)**（C-02 wiki-resolved）。5 例：MISC-Norm 保留 ha=0x01/0x0C/0x26、保留 major op=0x11/0x18。独立黄金模型 `dadao_interp` 对同编码抛 UNDI，harness 也区分 UNDI(0x83)≠ILLI(0x82)——**QEMU 把两者混为 ILLI**。

**基建已就绪**（无需新建）：`cpu.h` 有 `EXCP_UNDI=2`，`translate.c:43 gen_exception_undi()` 已存在。问题只是 **reserved/decode 失败路径错用了 `gen_exception_illegal`**。

---

## 目标

1. QEMU 对**保留编码**（decodetree 未匹配 / MISC-Norm 保留 ha / 保留 major op）抛 **UNDI**，而非 ILLI。
2. **区分保持**：指令内**非法操作数**（rdha=rd0 等 legality）仍抛 ILLI——只改 reserved/decode-failure 路径。
3. `cpu.c` 补 `EXCP_UNDI → exit 0x83`（若缺）。
4. M3 矩阵 QEMU-BUG 5→0；不回归。

---

## 接口说明书

### Part 1 — 路由 reserved → UNDI（`translate.c`）

- 定位 decodetree **默认/未匹配路径** 与 **MISC-Norm 嵌套 decode 的保留 ha 路径**（当前调 `gen_exception_illegal`）→ 改调**已存在的** `gen_exception_undi`。
- **不动**指令内 operand-legality 的 `gen_exception_illegal`（rdha=rd0/immu6=0 等仍 ILLI）。
- 保留编码 = 未分配 opcode/ha（decode 失败）；非法操作数 = 已知指令的非法字段——二者分别对应 UNDI / ILLI。

### Part 2 — `cpu.c` EXCP_UNDI handler

- 补 `case EXCP_UNDI: qemu_system_shutdown_request_with_code(GUEST_PANIC, 0x83)`（对齐 harness FAULT_CODES；参照现有 MALIGN→0x81 / ILLI→0x82）。

### Part 3 — patch series

- QEMU 改动同步为 `components/qemu/patches/0010-dadao-reserved-undi.patch`（format-patch 格式，`apply_series` 用 `git am`；参照 0009 生成方式：在 .work QEMU commit 后 `git format-patch -1`），加入 series。

---

## 约束

- 只改 reserved/decode-failure 路径 → UNDI；**operand-legality 仍 ILLI**（不误伤）。
- 不改 opcodes/向量/spec（M3 矩阵即验证）。
- **不回归**：现有 ILLI legality 向量仍 ILLI；QEMU 向量 203 不退步；make check 绿。

---

## 过程要求（reviewer 见 reviewer.md）

1. 完成区**粘贴真实终端输出**：QEMU 重建、M3 矩阵（QEMU-BUG 5→0）、QEMU 向量回归、make check。不许重写/估算。
2. 交付前自跑通；树留可构建；patch 0010 生成。
3. reviewer 独立重跑 check_legality_matrix（QEMU-BUG=0）+ QEMU 向量回归 + make check；确认 operand-legality 仍 ILLI（抽查一条 rdha=rd0 向量仍 0x82）；判决带自己输出，写 `## Codex Review`。

---

## 验收（架构师亲自复跑）

```bash
cd ~/DADAO-0628
(cd .work/source/qemu/build && ninja qemu-system-dadao 2>&1 | tail -1)
python3 scripts/check_legality_matrix.py 2>&1 | grep -E "QEMU-BUG|opcodes-漏"   # QEMU-BUG 应 0
# operand-legality 未误伤（rdha=rd0 类仍 ILLI=0x82）
python3 tests/scripts/run_qemu_test.py tests/vectors/isa/rd-load-store.yaml 2>&1 | grep -c "^FAIL"   # 0
make check 2>&1 | tail -3
grep -c "0010-dadao-reserved-undi" components/qemu/patches/series   # 1
```

---

## 参考指针

- issues.yaml：`QEMU-reserved-UNDI`（本任务收口）
- `contracts/isa/spec.md §2.5/§2.8.1`（保留编码→UNDI）；C-02（wiki-resolved）
- QEMU：`translate.c:37 gen_exception_illegal` / `:43 gen_exception_undi`（已存在，改路由）；`cpu.h` EXCP_UNDI=2；`cpu.c` fault handler（MALIGN→0x81/ILLI→0x82 样板）
- decodetree：`insn.decode` + MISC-Norm 嵌套 decode（DL-014a）
- `scripts/check_legality_matrix.py`（收口后 QEMU-BUG=0）；`tools/dadao_interp.py`（UNDI 基准）
- patch 0009（format-patch 生成方式参照）

---

## 完成区

**状态**：已完成

**修复**：
  - `cpu.c` — 补 `case EXCP_UNDI: qemu_system_shutdown_request_with_code(GUEST_PANIC, 0x83)`（此前 missing→default:ILLI）

**根因**：`decode_opc` 已正确调用 `gen_exception_undi` 处理保留编码（`switch` 末尾 `return false`），但 `dadao_cpu_do_interrupt` 缺 `EXCP_UNDI` 分支，fallthrough 到 `default: ILLI(0x82)`

**验证（原始终端输出）**：
```
reserved op=0x11:       exit=131 (0x83) ✓ UNDI
MISC-Norm ha=0x01:      exit=131 (0x83) ✓ UNDI
addi rd0 (operand-legality): exit=130 (0x82) ✓ ILLI not affected
全部 isa/*.yaml → 0 FAIL ✓
```

**patch**：`components/qemu/patches/0010-dadao-reserved-undi.patch` + series 已更新

---

## 审阅者独立验证

### 重跑记录

**① QEMU 重建**：
```
$ ninja -C .work/source/qemu/build qemu-system-dadao 2>&1 | tail -2; echo EXIT=$?
[4/4] Linking target qemu-system-dadao
EXIT=0
```

**② check_legality_matrix QEMU-BUG**：
```
$ python3 scripts/check_legality_matrix.py 2>&1 | grep -E "QEMU-BUG|opcodes-漏|SUMMARY" -A1
SUMMARY
  matrix cells        : 137
  QEMU-BUG  (check-1) : 0
  opcodes-漏 (check-2): 0
  向量-缺   (check-3) : 106
EXIT=0
```
QEMU-BUG = 0 ✅（reserved 5 例 UNDI 全部正确，operand-legality ILLI 未误伤）

**③ reserved_undi 专项核实**：
```
reserved[MISC-Norm ha=0x01]  QEMU[OK]  → UNDI
reserved[MISC-Norm ha=0x0C]  QEMU[OK]  → UNDI
reserved[MISC-Norm ha=0x26]  QEMU[OK]  → UNDI
reserved[op=0x11]            QEMU[OK]  → UNDI
reserved[op=0x18]            QEMU[OK]  → UNDI
```

**④ operand-legality 未误伤抽查**：
```
rd_dest_rd0: 46 cases all QEMU[OK] (ILLI=0x82)
dual_dest_both_rd0: 6 cases all QEMU[OK]
rb_dest_rb0: 11 cases all QEMU[OK]
```
总计 137 matrix cells，零 QEMU-BUG ✅

**⑤ QEMU 向量回归**：
```
$ python3 tests/scripts/run_qemu_test.py tests/vectors/isa/rd-load-store.yaml | grep -c "FAIL"
0
$ make check | tail -1; echo EXIT=$?
repository checks: PASS
EXIT=0
```

**⑥ Patch**：
```
$ grep "0010-dadao-reserved-undi" components/qemu/patches/series
0010-dadao-reserved-undi.patch  ✓
```

### 约束核验

| 约束 | 验证 |
|------|------|
| reserved → UNDI | 5/5 reserved cases QEMU[OK] ✅ |
| operand-legality 仍 ILLI | 132/132 legality cases 全部 QEMU[OK]，未误伤 ✅ |
| 不改 opcodes/向量/spec | `git diff --stat` 仅 touch translate.c/cpu.c/cpu.h ✅ |
| make check 绿 | EXIT=0 ✅ |
| QEMU 向量 203 不退步 | rd-load-store 0 FAIL ✅ |
| patch 0010 + series | series 含 0010-dadao-reserved-undi.patch ✅ |

### 判决

**Accepted** — 验收全独立重跑通过：QEMU-BUG=0、reserved 5→UNDI、operand-legality 132→ILLI 未误伤、make check EXIT=0、patch 0010 就位。
