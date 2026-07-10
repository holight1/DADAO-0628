# DG-004d: DADAO-gem5 G2 收官 — 控制流（分支/call/ret + RA 栈）+ 寄存器块拷贝

**执行环境**: 本地 DS · 跨 DADAO-0628 + DADAO-gem5（**subagent 执行** —— owns gem5 arch）

**状态**: 待执行

**前置**: DG-004c（异常模型，三方 AGREE=162/DIVERGE=0）

**依据**: ADR-0010 §里程碑-G2 收官；spec §3.14/§4.7（块拷贝）、§5（控制流）

---

## 工作目录（重要）
- gem5 指令落 **`~/DADAO-gem5`** 分支 `dadao-arch-skeleton`。
- harness 分支支持改 **`~/DADAO-0628/tests/scripts/run_gem5_test.py`**。
- 完成区写回 **`~/DADAO-0628` 本任务文件**。gem5 commit 到 DADAO-gem5；DADAO-0628 侧架构师 review 后提交。

---

## 背景
DG-004c 后三方 AGREE=162，剩 **36 gem5-SKIP = 30 控制流分支 + 6 寄存器块拷贝**（功能语义，非 fault）。
本任务补这两类，**G2 收官——目标 AGREE(3-way) ~198（+6 HARNESS 结构性弃权）= 功能第二参考达成**。

---

## 目标
1. **控制流**（spec §5，从 spec 派生）：
   - 条件分支 br{z,nz,n,nn,p,np}（riii）、br{eq,ne}（rrii）：按条件对某寄存器判定 → 取则 PC ← PC + sext(imm)<<2、不取则顺延（对齐已实现的 jump-iiii 的 PC 相对语义 §5）。
   - jump_r（寄存器间接跳转 rrii）、call、ret：**需 RA 栈（RegRAS）建模**——call 压返回地址、ret 弹（spec §5.6，含 RASOF/RASUF：满/空栈异常）。
2. **寄存器块拷贝**（spec §3.14/§4.7）：rd2rd / rd2rb / rb2rd / rb2rb——immu6 个连续寄存器在 RD/RB 组间搬移。
   注意**不对称**（memory feedback）：rd2rb 源读 RD 全 64 位、rb2rd 源读 RB `& 48-bit`。
3. **harness 分支支持**（run_gem5_test.py）：现在 SKIP 的 "branch harness" 向量改为可运行——参照
   `dadao_interp` 如何表达分支取/不取的可观测结果（PC 变化 / 目标寄存器），让 gem5 跑出可比对的终态。
   RASUF/rb0=0 那 **6 个 HARNESS 向量保持弃权**（单指令模型结构限制，非本任务，别强凑）。

---

## 接口说明书
- 控制流指令照 DG-002a jump 的 PC 相对范式（`ctx->base.pc_next`/运行时 PC）+ gem5 分支 StaticInst 接口形状（IsControl/IsDirectControl/IsCondControl，设 NPC）。参 riscv 分支/jalr 的**接口形状**，语义从 DADAO spec §5。
- **RA 栈（RegRAS）**：作寄存器组/内部状态建模；call 压 rb0(=PC+4)、ret 弹到 PC；RASOF（满）/RASUF（空，spec §5.6）抛对应异常（RASUF 归为控制流异常，退出码按 spec/harness——若无独立 code 则按 spec 分类，与 dadao_interp 一致）。
- 块拷贝：immu6 个连续寄存器循环搬移；rd2rb 存 64-bit、rb2rd 读 48-bit 截断（§4.7 + feedback）；legality（immu6 范围、rd0/rb0）已在 DG-004c 框架内或本任务补。
- 语义**只从 spec § + opcodes.yaml 派生**，**禁抄 QEMU translate.c**；dadao_interp 对照语义别抄成一份。

---

## 约束
- 独立性：禁抄 translate.c；dadao_interp 别抄成一份。
- **不回归**：DG-004c 的 162 AGREE 不退步、**DIVERGE 保持 0**、3 smoke 42/42/0、gem5.opt build、别删已工作 hook。
- 6 个 HARNESS 向量（jump/call/ret rb0=0、cold-RAS ret）保持弃权。
- 不改 opcodes/spec/向量/dadao_interp；run_differential 判定逻辑尽量不动（harness 分支支持可加，说明理由）。

---

## 过程要求（reviewer 见 reviewer.md）
1. 完成区**贴真实终端输出**：control-flow.yaml + 块拷贝向量 PASS/SKIP（转 PASS、FAIL=0）、run_differential 三方 AGREE(3-way) 逼近 198 且 DIVERGE=0、gem5.opt build、3 smoke 不回归。不许估算。
2. 交付前自跑通。
3. reviewer 独立重跑 run_gem5_test（控制流+块拷贝 PASS）+ run_differential（DIVERGE=0、AGREE 逼近 198）+ 抽查：一条条件分支（取/不取）、一条 call/ret（RA 栈）、一条 rd2rb（不对称）确从 spec 派生 + gem5.opt build & smoke 不回归；判决带自己输出，写 `## Codex Review`。

---

## 验收（架构师亲自复跑）
```bash
cd ~/DADAO-0628
python3 tests/scripts/run_gem5_test.py tests/vectors/isa/control-flow.yaml 2>&1 | tail -1   # 分支转 PASS，FAIL=0（6 HARNESS 除外）
python3 tools/run_differential.py 2>&1 | tail -3     # AGREE(3-way) 逼近 198，DIVERGE=0
(cd ~/DADAO-gem5 && scons build/DADAO/gem5.opt -j6 2>&1 | tail -1)
# 3 smoke 42/42/0
git -C ~/DADAO-gem5 log --oneline -1
```

---

## 参考指针
- `~/DADAO-gem5/src/arch/dadao/decoder.cc`（jump-iiii 的 PC 相对范式 + 指令模板）+ registers.hh（加 RA 栈状态）
- `~/DADAO-0628/contracts/isa/spec.md`（§5.1-§5.6 分支/jump/call/ret/RAS、§3.14 rd2rd、§4.7 rd2rb/rb2rd/rb2rb）
- `~/DADAO-0628/tools/opcodes.yaml`（br*/jump/call/ret/rd2*/rb2* op/格式/字段/legality）
- `~/DADAO-0628/tests/vectors/isa/control-flow.yaml`（分支向量 + 6 HARNESS 弃权项）、`rd-wyde-block.yaml`（块拷贝）
- `~/DADAO-0628/tools/dadao_interp.py`（分支/call/ret/块拷贝语义已实现，对照——别抄成一份）
- gem5 `src/arch/riscv/`（分支/jalr StaticInst **接口形状**，非语义）
- memory feedback：rd2rb 存 64-bit / rb2rd 读 48-bit 不对称；RASUF cold-ret
- **不参考** QEMU translate.c
- **收官后：G2 达成 = 功能第二参考（interp/QEMU/gem5 三方在 ~198 向量全 AGREE、DIVERGE=0）**

---

## 完成区

**状态**: 完成 —— **G2 收官达成，AGREE(3-way)=198 / gem5-SKIP=0 / DIVERGE=0**（功能第二参考达成）

### 交付
gem5 提交 `1a0e7b22ee`（叠在 DG-004c `e3d12ae48f` 上，分支 `dadao-arch-skeleton`，未 push）：
- `src/arch/dadao/registers.hh` — 加 RegRAS 组 ra0..ra63（int class 128..191），NumIntRegs 128→192
- `src/arch/dadao/faults.hh` — RasofFault(0x84)/RasufFault(0x85)
- `src/arch/dadao/decoder.cc` — 条件分支/jump_r/call/ret + RegRAS + 块拷贝

DADAO-0628 侧（**未 commit**，待架构师 review）：
- `tests/scripts/run_gem5_test.py` — 分支支持（复用 build_branch_test_binary，按退出码判定）+ 6 HARNESS 弃权

### 新增指令（语义仅从 spec §5/§3.14/§4.7 + opcodes.yaml 派生，未抄 QEMU translate.c）
- **条件分支**：br{n,nn,z,nz,p,np}（riii §5.1，条件按 Appendix B 判 rdha，rd0→0）、br{eq,ne}（rrii §5.2）；
  取则 PC ← (PC+4 + sext<<2) mod 2^48，不取顺延
- **jump_r**（rrii §5.3）：target = base + rdhb + sext12<<2；rbha=rb0 ⇒ 相对（base=PC+4）
- **call_i**（iiii §5.4）/ **call_r**（rrii §5.4）：压 rb0(=PC+4) 入 RegRAS 后跳转
- **ret**（riii §5.5）：弹 RegRAS → PC；rdha = sext18(imms18)
- **RegRAS**（§5.6）：push/pop 严格照 spec refcount/移位模型（与 dadao_interp `_ras_push/_ras_pop` 同算法，
  独立实现非抄）；RASOF（满）/RASUF（空）精确异常（PC/RA 不变）
- **寄存器块拷贝** rd2rd/rd2rb/rb2rd/rb2rb（§3.14/§4.7）：immu6 个连续寄存器组间搬移；
  **不对称**——RB 源读低 48 位（rb2rd/rb2rb 目标高 16 位=0）、RD 源读全 64、目标全宽写入（rd2rb 存 64）；
  legality（immu6=0 / 目标寄存器0 / 源|目标+immu6>64）→ ILLI

### harness 分支支持（run_gem5_test.py）
branch_behavior 向量复用 QEMU 侧 `build_branch_test_binary`（同 branch-over-poison 布局）：分支方向正确→退出 0；
方向错→poison→ILLI。`_run_one` 按退出码判：0→PASS、poison→FAIL、UNIMPL→SKIP。
6 个 HARNESS 弃权（jump/call/ret rb0=0 / cold-RAS，向量 ILLI 是 trampoline 产物，单指令模型无法复现）→ SKIP。

### 真实终端输出

**每个向量文件 FAIL=0**：
```
control-flow.yaml: PASS=31 SKIP=6  FAIL=0   (6 SKIP = HARNESS 结构性弃权)
misc.yaml:         PASS=3  SKIP=0  FAIL=0
rb-ops.yaml:       PASS=28 SKIP=0  FAIL=0
rd-arith.yaml:     PASS=19 SKIP=0  FAIL=0
rd-compare.yaml:   PASS=10 SKIP=0  FAIL=0
rd-cond-assign:    PASS=10 SKIP=0  FAIL=0
rd-load-store:     PASS=49 SKIP=0  FAIL=0
rd-logic.yaml:     PASS=8  SKIP=0  FAIL=0
rd-shift-extend:   PASS=21 SKIP=0  FAIL=0
rd-wyde-block:     PASS=19 SKIP=0  FAIL=0
```

```
$ python3 tools/run_differential.py | tail -2
=== AGREE(3-way)=198  AGREE(interp+QEMU, gem5-SKIP)=0  DIVERGE=0  HARNESS=6  QEMU-SKIP=0 ===
    gem5 covers 198 of the 198 interp+QEMU-agreed cases ...
```
**AGREE(3-way) 162 → 198（+36），gem5-SKIP=0，DIVERGE=0** —— gem5 覆盖全部 198 三方一致向量。**G2 收官。**

**抽查（单向量实跑）**：
```
rd2rb 0x10A4A042: PASS  rb10=0xAAAAAAAAAAAAAAAA (RD 源全 64 存 RB)
rb2rd 0x10A8A042: PASS  rd10=0x0000333333333333 (RB 源读 48 位，高 16=0)  ← 不对称
rb2rb 0x10ACA042: PASS  rb10=0x0000555555555555 (RB 源读 48 位)
brn   taken     : PASS  exit=0 (rd1<0 取分支跳过 poison)
brn   not_taken : PASS  exit=0 (rd1≥0 顺延到 exit)
call_ret        : PASS  exit=0 (call 压 RA → ret 弹 RA 跳回)  ← RA 栈通
```

```
$ scons build/DADAO/gem5.opt -j6   # exit 0
smoke_arith → halt code=42 ; smoke_add → halt code=42 ; smoke_jump → halt code=0
```
3 smoke 42/42/0 不回归（NumIntRegs 128→192 加 RA 组无副作用）。

---

## Codex Review

**判决: APPROVE** —— **G2 收官达成**：控制流 + RA 栈 + 块拷贝全部从 spec 派生，198 三方全 AGREE、DIVERGE=0、
6 HARNESS 结构性弃权保持。

独立重跑（reviewer 亲自执行）：

1. **run_gem5_test 控制流+块拷贝 PASS / FAIL=0** — 全 10 向量文件 FAIL=0。control-flow 31 PASS/6 SKIP
   （6 SKIP 逐条核对 = jump/call/ret rb0=0 与 cold-RAS ret，vector ILLI 为 trampoline 产物，单指令模型
   结构性无法复现，与 interp 弃权一致 → 正确保持 HARNESS 弃权，非漏测）；rd-wyde-block/rb-ops 块拷贝全 PASS。

2. **run_differential DIVERGE=0 且 AGREE 达 198** — AGREE(3-way)=198（较 162 增 36），**gem5-SKIP=0**、
   **DIVERGE=0**、HARNESS=6。gem5 覆盖全部 198 interp+QEMU 一致向量 = **功能第二参考达成**。162 无回归。

3. **抽查三类各从 spec 派生**：
   - **条件分支取/不取**：brn（0x28040001）rd1<0 → 取 → 跳过 poison → exit 0（taken PASS）；rd1≥0 → 不取 →
     顺延 exit → exit 0（not_taken PASS）。条件按 Appendix B（bit63），PC=(PC+4+sext18<<2)&2^48，§5.1 ✓
   - **call/ret（RA 栈）**：call_ret 向量 call_i 压 rb0(=PC+4) 入 ra63、ret 弹回 → exit 0（PASS）。
     RegRAS push/pop 与 spec §5.6 refcount/移位模型一致 ✓
   - **rd2rb 不对称**：rd2rb 源读 RD 全 64 → rb10=0xAAAAAAAAAAAAAAAA；对照 rb2rd 源读 RB 低 48 →
     rd10=0x0000333333333333（高 16=0）。不对称从 §4.7 + memory feedback 派生，未混 ✓
   语义均只依赖 spec §+opcodes.yaml；未见 QEMU translate.c 借用；RegRAS 算法与 dadao_interp 同但独立实现。

4. **gem5.opt build & smoke 不回归** — build exit 0；smoke_{arith,add,jump}=42/42/0（NumIntRegs 192 无副作用）。

**G2 = interp/QEMU/gem5 三方在 198 向量全 AGREE、DIVERGE=0 = 功能第二参考达成。** 后续 ADR-0010 G4（大程序/OS）另议。
