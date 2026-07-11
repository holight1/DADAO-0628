# DL-058b: CodeGen — 无符号比较 + 去 cmp commutative 误标

**执行环境**: 本地 DS · DADAO-0628（LLVM backend + E2E）

**状态**: 已完成

**前置**: DL-058a（条件控制流：有符号 icmp+br 双后端通；patch 0007）。遗留两项在此收：无符号比较未覆盖（当前 `Cannot select: br_cc setult`）+ `DADAOISD::CMP` 误标 `SDNPCommutative`（见 issues `codegen-cmp-commutative-mismark`）。

---

## 完成区

**状态**：已完成
**修改文件**：
- `.work/source/llvm/llvm/lib/Target/DADAO/DADAOISelLowering.h` — 新增 CMPU node
- `.work/source/llvm/llvm/lib/Target/DADAO/DADAOISelLowering.cpp` — LowerBR_CC 添加 SETULT/SETULE/SETUGT/SETUGE 分支（cmpu + 单寄存器分支）
- `.work/source/llvm/llvm/lib/Target/DADAO/DADAOInstrInfo.td` — 新增 DADAOCmpU SDNode + CMPU_ORRR pattern；去掉 `[SDNPCommutative]` 误标
- `tests/lit/E2E/usum_loop.test` + `tests/lit/E2E/Inputs/usum_loop.ll` — 新增无符号循环 E2E
- `components/llvm/patches/0008-dadao-unsigned-cmp.patch` — 新 LLVM patch
- `components/llvm/patches/series` — 追加 0008

**验收结果**：
```
# 4 个无符号谓词全部可用（不再 crash）
for p in ult ule ugt uge: all OK

# SDNPCommutative 已移除
$ grep SDNPCommutative DADAOInstrInfo.td → (no match)

# E2E lit 9/9 PASS（含 usum_loop.test）
usum_loop.test PASS (exit=55, QEMU+gem5)

# 有符号 9 例探针全绿
slt/sle/sgt/sge × const-RHS × non-const-fwd/rev + breq/brne/eq0: all OK

# 差分 AGREE(4-way)=198 / DIVERGE=0 无回归
```

**遗留问题**：无

## 目标

1. **无符号比较 ISel**：把 `icmp ult/ule/ugt/uge` + 条件 `br` 下降到 DADAO：
   - **比较**用 `cmpu`（§3.8 无符号），配单寄存器符号分支（§5.1 brz/brnz/brn/brnn/brp/brnp）或双寄存器 breq/brne（§5.2）——谓词映射从 spec 推。
   - 覆盖全 4 个无符号谓词 `ult/ule/ugt/uge`。当前对它们 llc crash（`Cannot select`），修完不再 crash。
2. **去掉 `DADAOISD::CMP` 的 `[SDNPCommutative]` 误标**（cmps/cmpu 非交换：sign(a−b)≠sign(b−a)）：
   - 改 `DADAOInstrInfo.td` 的 `DADAOCmp` SDNode 定义，去掉 `SDNPCommutative`。
   - 若去掉后某 ISel pattern 依赖交换匹配而失配，按需补显式 pattern（别为过测又加回误标）。
3. **真实无符号程序双后端跑通**（**被测=llc 产物，禁手搓**）：至少一个用无符号比较的程序，例如无符号循环 `usum(n){u64 s=0; for(u64 i=1;i<=n;i++)s+=i; return s}`（`icmp ule` 无符号）或含 `ult` 的边界判断 → 双后端退出码 = 正确值；入 lit E2E。

## 约束
- 编译器改动在 `.work/source/llvm/`（spike）；无符号谓词→分支映射从 spec §3.8/§5.1/§5.2 推、不从别的后端抄。
- LLVM 改动同步为 **新 patch** `components/llvm/patches/0008-*.patch`（不改写已提交的 0007；format-patch 入 series）。
- **不回归**：
  - lit E2E **8/8**（含 DL-058a 的 loop_sum/cond_abs）→ 加新用例后全绿；
  - **有符号有序比较不能因去 commutative 而退步**——DL-058a 架构师探针的 9 例（slt/sle/sgt/sge × 常量 RHS + 两非常量操作数正反定义序）必须仍全对（自己复跑一遍贴输出）；
  - 四方差分 AGREE(4-way)=198 / DIVERGE=0。
- 新增 E2E 入 `tests/lit/E2E/`（双后端 QEMU+gem5 断言退出码），参 `nested_call.test`/`loop_sum.test` 范式。

## 验收（架构师亲自复跑）
```bash
cd ~/DADAO-0628 && ninja -C .work/build/llvm llc llvm-mc
LLC=.work/build/llvm/bin/llc
# 无符号谓词都能选（不再 crash）
for p in ult ule ugt uge; do
  printf 'define i64 @f(i64 %%x){\n %%c=icmp '$p' i64 %%x,5\n br i1 %%c,label %%t,label %%e\nt: ret i64 11\ne: ret i64 22\n}\ndefine i64 @main(){%%r=call i64 @f(i64 3) ret i64 %%r}\n' > /tmp/u.ll
  $LLC -march=dadao /tmp/u.ll -o /tmp/u.s 2>&1 | grep -i "cannot select" && echo "$p CRASH" || echo "$p OK"
done
grep -n "SDNPCommutative" .work/source/llvm/llvm/lib/Target/DADAO/DADAOInstrInfo.td   # DADAOCmp 那行应无
llvm-lit -v tests/lit/E2E/ 2>&1 | tail            # 全 PASS（含无符号新用例）
python3 tools/run_differential.py 2>&1 | tail -3  # AGREE(4-way)=198 / DIVERGE=0
```

## 参考指针
- DL-058a 完成区 + `## 架构师复核`（有符号分支实现、9 例探针、SDNPCommutative 分析）；issues `codegen-cmp-commutative-mismark`
- `.work/source/llvm/llvm/lib/Target/DADAO/`：`DADAOISelLowering.cpp`（`LowerBR_CC` 有符号谓词处理，无符号并入）、`DADAOInstrInfo.td`（`DADAOCmp` SDNode 行 + branch pattern；cmpu 指令定义）
- spec `contracts/isa/spec.md §3.8`（cmps/cmpu 有/无符号语义）、`§5.1`（单寄存器条件分支）、`§5.2`（双寄存器）；`tools/opcodes.yaml`（cmpu 编码位段）
- E2E 范式：`tests/lit/E2E/loop_sum.test`（有符号循环，无符号照此改）、`tests/scripts/crt0.s`
- 后续 **DG-005b**：比较谓词补齐后可编译更完整的 gem5 大程序

—— 通用验收/自审纪律见 DS-common（§5 反偷换：被测=真 llc 产物）与 DS.md §自审流程（subagent 代码级 · 本任务强制）。CodeGen 产物禁手搓（DS.md §工作规则）。去 commutative 后**必须复跑 DL-058a 的 9 例有符号探针**证明无回归。

---

## 审阅记录（subagent）

**审阅日期**: 2026-07-11

### 重跑记录

**1. lit E2E（9/9 PASS，含 usum_loop）:**
```
$ .work/build/llvm/bin/llvm-lit tests/lit/E2E/ 2>&1

PASS: E2E :: cond_abs.test (1 of 9)
PASS: E2E :: smoke_arith.test (2 of 9)
PASS: E2E :: nested_call.test (3 of 9)
PASS: E2E :: loop_sum.test (4 of 9)
PASS: E2E :: rasof_overflow.test (5 of 9)
PASS: E2E :: rasuf_cold.test (6 of 9)
PASS: E2E :: usum_loop.test (7 of 9)
PASS: E2E :: smoke_jump.test (8 of 9)
PASS: E2E :: smoke_add.test (9 of 9)

Testing Time: 0.73s
Total Discovered Tests: 9
  Passed: 9 (100.00%)
```

**2. SDNPCommutative 全移除:**
```
$ grep -n "SDNPCommutative" .work/source/llvm/llvm/lib/Target/DADAO/DADAOInstrInfo.td
（无输出 — 已完全移除）
```

**3. 四方差分不回归:**
```
$ python3 tools/run_differential.py 2>&1 | grep -E "AGREE|DIVERGE|HARNESS"

--- HARNESS (single-instr model deliberately abstains) ---
=== AGREE(3-way)=198  AGREE(interp+QEMU, gem5-SKIP)=0  DIVERGE=0  HARNESS=6  QEMU-SKIP=0 ===
=== SAIL 4th column: AGREE(4-way)=198  Sail-SKIP(out-of-slice)=0  SAIL-DIVERGE=0 ===
```

**4. 无符号谓词不 crash + 生成 cmpu 指令:**
```
$ for p in ult ule ugt uge; do ... done
ult OK
ule OK
ugt OK
uge OK
```

**5. 无符号谓词 E2E 退出码正确（QEMU 裸跑）:**
```
PASS: ult exit=22 expected=22
PASS: ule exit=22 expected=22
PASS: ugt exit=11 expected=11
PASS: uge exit=11 expected=11
```

**6. 有符号比较回归探针（12 例，全部正确退出码）:**

| 探针 | QEMU 退出码 | 预期 | 结果 |
|------|-----------|------|------|
| slt const RHS (x=10, 5) | 22 | 22 | PASS |
| sle const RHS (x=10, 5) | 22 | 22 | PASS |
| sgt const RHS (x=10, 5) | 11 | 11 | PASS |
| sge const RHS (x=10, 5) | 11 | 11 | PASS |
| slt const LHS (5, x=10) | 11 | 11 | PASS |
| sle const LHS (5, x=10) | 11 | 11 | PASS |
| slt 2vr (7, 10) | 11 | 11 | PASS |
| sgt 2vr (7, 10) | 22 | 22 | PASS |
| sge 2vr (7, 10) | 22 | 22 | PASS |
| slt 2vr_REV (25, 22) | 22 | 22 | PASS |
| sgt 2vr_REV (25, 22) | 11 | 11 | PASS |
| sge 2vr_REV (25, 22) | 11 | 11 | PASS |

**7. usum_loop 生成的 cmpu+brnp（非常量操作数，直接验证 LowerBR_CC 映射）:**
```
$ llc -march=dadao tests/lit/E2E/Inputs/usum_loop.ll -o - | grep -E "cmpu|br[^n ]|brn[^z ]|brp|brnp|jump"
	cmpu rd18, rd17, rd16
	brnp rd18, .LBB0_1
	jump .LBB0_2
```
非常量操作数（`%i2`, `%n`）下，SETULE → CMPU + BRNP 映射直接生成，与源头中 LowerBR_CC 的定义一致。

### 约束核验

| 约束 | 状态 |
|------|------|
| 编译器改动在 `.work/source/llvm/` | ✅ 通过。patch 0008 仅改 DADAOISelLowering.{h,cpp} + DADAOInstrInfo.td |
| 无符号谓词→分支映射从 spec §3.8/§5.1/§5.2 推 | ✅ 通过。ult→BRN, ule→BRNP, ugt→BRP, uge→BRNN，基于 cmpu 返回 −1/0/1 |
| LLVM 改动同步为新 patch `0008-*.patch`，入 series | ✅ 通过。`components/llvm/patches/0008-dadao-unsigned-cmp.patch` 已生成，series 已追加 |
| lit E2E 加新用例后全绿 | ✅ 通过。9/9 PASS，usum_loop.test 双后端（QEMU+gem5）断言 exit=55 |
| 有符号有序比较不因去 commutative 退步 | ✅ 通过。12 例探针全部退出码正确 |
| 四方差分 AGREE(4-way)=198 / DIVERGE=0 | ✅ 通过。与 DL-058a 基准完全一致 |
| 新增 E2E 入 `tests/lit/E2E/`，双后端断言退出码 | ✅ 通过。usum_loop.test QEMU + gem5 均断言 exit 55 |
| E2E 被测 = 真 llc 产物（禁手搓） | ✅ 通过。usum_loop.test 使用 `%llc` 编译 Inputs/usum_loop.ll |
| Patch 不改写已提交的 0007 | ✅ 通过。0007 未变，0008 为增量 patch |

### 代码审查（逐文件）

**DADAOISelLowering.h:23** — `CMPU` 枚举项添加正确，位于 `CMP` 之后。

**DADAOISelLowering.cpp:251-266** — 四个无符号 case 映射正确：
- `SETULT → CMPU + BRN`（unsigned LHS<RHS ↔ cmpu(LHS,RHS)<0）
- `SETULE → CMPU + BRNP`（unsigned LHS≤RHS ↔ cmpu(LHS,RHS)≤0）
- `SETUGT → CMPU + BRP`（unsigned LHS>RHS ↔ cmpu(LHS,RHS)>0）
- `SETUGE → CMPU + BRNN`（unsigned LHS≥RHS ↔ cmpu(LHS,RHS)≥0）

所有 case 与签名比较 case 结构一致，语义正确。

**DADAOInstrInfo.td:71** — `[SDNPCommutative]` 已从 `DADAOCmp` 移除。`SDTIntBinOp` 本身不含 `SDNPCommutative`，正确。

**DADAOInstrInfo.td:72** — `DADAOCmpU` SDNode 新增，使用 `SDTIntBinOp`（不含 `SDNPCommutative`），与 `DADAOCmp` 定义一致。

**DADAOInstrInfo.td:269-271** — `DADAOCmpU → CMPU_ORRR` pattern 正确，与 `DADAOCmp → CMPS_ORRR` 对称。

### 观察说明

通用 DAG combiner 在常量 RHS 场景下会将 BR_CC 条件规范化（例：`icmp ult x, 5` → 等效于 `cmps x, 4` 配合交换后的分支目标及反转条件），导致生成的分支指令与 LowerBR_CC 中字面定义的映射不同（如出现 BRP 替代 BRN）。这是 LLVM 标准行为，不影响正确性 — 非常量操作数（如 usum_loop 的 `%i2`, `%n`）下映射直接对应，出口码全部正确。

### 判决

**Accepted** — 所有验收命令块在独立重跑下全部通过，约束无违反。SDNPCommutative 已完全移除且无不回归，无符号比较 4 谓词双后端跑通。

---

## 架构师复核（通过）

**复核日期**: 2026-07-11 · ground-truth 独立复跑（touch 强制重建 llc + 判别性无符号探针 + 有符号回归）

| 核验项 | 结果 |
|--------|------|
| llc touch 强制重建 | ✓ |
| SDNPCommutative 去除（dev 树 + patch 0008 均含移除）| ✓ |
| lit E2E | ✓ 9/9（usum_loop 用真 `icmp ule` → 55 双后端）|
| 四方差分不回归 | ✓ AGREE(4-way)=198 / DIVERGE=0 |
| **判别性无符号探针**（架构师加做，x=-1=0xFFFF..，符号位置位）| ✓ ult(-1,5)=22 / ugt=11 / ule=22 / uge=11 全对——**真无符号语义** |
| 交叉验证 | ✓ slt(-1,5)=11 与 ult 结果**相反**→铁证 cmpu 真被用（非误用 cmps）|
| 去 commutative 后有符号回归 | ✓ sgt/slt 两非常量正反序仍对 |
| patch 0008 增量（0007 未改写）+ 可复现 | ✓ |
| subagent 自审 | ✓ present |

**架构师补住的盲区**：DS 自审的无符号探针用 `x=3 vs 5` 小值——**ult(3,5) 与 slt(3,5) 答案相同，不能区分 cmpu/cmps**。架构师用 `x=-1`（符号边界）判别性输入证实 cmpu 真正确。又一次「subagent 代码级 + 架构师未测输入真值」互补生效。

**判决：通过。** 无符号比较补齐（4 谓词符号边界正确）+ SDNPCommutative landmine 清除。比较谓词全覆盖，**DG-005b 大程序就绪**。架构师提交。issue `codegen-cmp-commutative-mismark` closed。
