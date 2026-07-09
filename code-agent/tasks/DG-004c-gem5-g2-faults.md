# DG-004c: DADAO-gem5 G2 batch-3 — 异常模型（ILLI/MALIGN/UNDI + 除零 + legality）

**执行环境**: 本地 DS · 跨 DADAO-0628 + DADAO-gem5（**subagent 执行** —— owns gem5 arch）

**状态**: 待执行

**前置**: DG-004b（内存类，三方 AGREE=131/DIVERGE=0）

**依据**: ADR-0010 §里程碑-G2；ADR-0004（SBZ→ILLI）；issues.yaml 已收口的 fault 分类

---

## 工作目录（重要）
- gem5 异常模型落 **`~/DADAO-gem5`** 分支 `dadao-arch-skeleton`。
- harness fault 比对改 **`~/DADAO-0628/tests/scripts/run_gem5_test.py`**。
- 完成区写回 **`~/DADAO-0628` 本任务文件**。gem5 commit 到 DADAO-gem5；DADAO-0628 侧架构师 review 后提交。

---

## 背景
DG-004b 后三方 AGREE=131，剩 **67 gem5-SKIP 几乎全是 expected_fault 向量**（gem5 无异常模型，一律 SKIP）。
本任务给 gem5 加**异常模型 + legality 检查**，让 expected_fault 向量从 SKIP 转 AGREE——**G2 收官，目标 203 向量三方全 AGREE（除 6 个 HARNESS 控制流弃权）= 功能第二参考达成**。

---

## 目标
1. **gem5 异常模型**：指令非法/错误 → 抛对应 fault → SE 退出码与 harness FAULT_CODES 一致：
   **ILLI=0x82、MALIGN=0x81、UNDI=0x83**（同 `run_qemu_test.py` 的 FAULT_CODES / QEMU shutdown-with-code）。
2. **legality → ILLI**（spec §2.6，编码字段见 opcodes.yaml 各指令 `legality`）：
   rdha/rdhb/rdhc=rd0 作目标、rbha/rbhb=rb0 作目标、immu6=0、first+immu6>64、SBZ 非零（ADR-0004 D5）等。
3. **MALIGN=0x81**（spec §3.1）：ldo/sto（及 8B 类）EA 非 8B 对齐 → MALIGN；其它宽度按 spec 对齐规则。
4. **UNDI=0x83**（spec §2.5/§2.8.1）：**保留编码**（未分配 opcode / MISC-Norm 保留 ha / 保留 major op）→ UNDI，
   **不是 ILLI**（区分：保留编码=UNDI，已知指令的非法操作数=ILLI）。gem5 从 spec 一开始就分对（QEMU 曾误为 ILLI，DL-043b 修，gem5 别重犯）。
5. **除零/溢出 → ILLI**（spec §3.7）：divs/divu 除零、divs INT64_MIN÷-1 → ILLI。
6. **harness fault 比对**（run_gem5_test.py）：expected_fault 向量不再 SKIP——跑 gem5、取 fault 退出码、比对 expected_fault（ILLI/MALIGN/UNDI）。

---

## 接口说明书
- gem5 fault：用 gem5 Fault 类（参 `~/DADAO-gem5/src/arch/dadao/faults.hh/.cc` 现有 DADAOFault 骨架 + riscv fault **接口形状**），`invoke` 走 `exitSimLoop`/退出码 = FAULT_CODES。指令 execute 里检测到非法 → 返回对应 Fault（不写寄存器/内存）。
- **保留编码 → UNDI**：decode 落到未匹配/保留路径 → UnknownInst 抛 UNDI（现在 UnknownInst 应抛的是 UNDI 而非笼统 fault）；MISC-Norm 保留 ha 同理。**指令内非法操作数仍 ILLI**（只保留/decode 失败路径 → UNDI）。
- legality 检测点：各指令 execute 开头按 opcodes.yaml legality 断言，违反 → ILLI Fault。
- harness：expected_fault 向量运行 gem5 → 读退出码（0x81/0x82/0x83）→ 比对；退出码机制复用 DG-003a 的 SE 退出码透传。
- 语义/分类**只从 spec § + opcodes.yaml + ADR-0004 派生**，**禁抄 QEMU translate.c/cpu.c**（QEMU 的 fault 分类本身有过 bug，更不能抄）。

---

## 约束
- 独立性：禁抄 translate.c/cpu.c；dadao_interp 别抄成一份（它已实现 fault 模型，对照语义可以、别抄）。
- **不回归**：DG-004b 的 131 AGREE 不退步、**DIVERGE 保持 0**、3 smoke 42/42/0、gem5.opt build。
- **UNDI≠ILLI 区分**：保留编码 UNDI、操作数非法 ILLI，别混（这是 M3/issues.yaml 明确的分类）。
- 不改 opcodes/spec/向量/dadao_interp；run_differential 判定逻辑尽量不动（fault 比对可在 run_gem5_test 侧，说明理由）。
- RASUF/控制流 rb0=0 那 6 个 HARNESS 向量保持弃权（单指令模型结构限制，非本任务）。

---

## 过程要求（reviewer 见 reviewer.md）
1. 完成区**贴真实终端输出**：各 expected_fault 向量文件 PASS/SKIP（fault 向量转 PASS、FAIL=0）、run_differential 三方 AGREE(3-way) 逼近 192 且 DIVERGE=0、gem5.opt build、3 smoke 不回归。不许估算。
2. 交付前自跑通。
3. reviewer 独立重跑 run_gem5_test（fault 向量 PASS）+ run_differential（DIVERGE=0）+ 抽查：一条 ILLI（rdha=rd0）、一条 MALIGN（非对齐 ldo）、一条 UNDI（保留编码）确各抛对 code、且 UNDI≠ILLI 未混 + gem5.opt build & smoke 不回归；判决带自己输出，写 `## Codex Review`。

---

## 验收（架构师亲自复跑）
```bash
cd ~/DADAO-0628
python3 tests/scripts/run_gem5_test.py tests/vectors/isa/rd-load-store.yaml 2>&1 | tail -1   # fault 向量转 PASS，FAIL=0
python3 tools/run_differential.py 2>&1 | tail -3     # AGREE(3-way) 逼近 192，DIVERGE=0
(cd ~/DADAO-gem5 && scons build/DADAO/gem5.opt -j6 2>&1 | tail -1)
# 抽查：ILLI=0x82 / MALIGN=0x81 / UNDI=0x83 各抛对；3 smoke 42/42/0
git -C ~/DADAO-gem5 log --oneline -1
```

---

## 参考指针
- `~/DADAO-gem5/src/arch/dadao/faults.hh/.cc`（DADAOFault 骨架，本任务扩展）+ decoder.cc（各指令 execute 加 legality）
- `~/DADAO-0628/contracts/isa/spec.md`（§2.5/§2.8.1 保留→UNDI、§2.6 legality→ILLI、§3.1 MALIGN、§3.7 除零→ILLI）
- ADR-0004（SBZ→ILLI 0x82）；`~/DADAO-0628/docs/issues.yaml`（QEMU-reserved-UNDI 收口记录：保留=UNDI 非 ILLI）
- `~/DADAO-0628/tools/opcodes.yaml`（各指令 legality 约束 = ILLI 检测点）
- `~/DADAO-0628/tests/scripts/run_qemu_test.py`（FAULT_CODES：ILLI 0x82/MALIGN 0x81/UNDI 0x83）
- `~/DADAO-0628/tools/dadao_interp.py`（fault 模型已实现，对照语义——别抄成一份）
- **不参考** QEMU translate.c/cpu.c（fault 分类 QEMU 曾错，独立性）
- 收官后：G2 达成 = 功能第二参考；后续 ADR-0010 G4（大程序/OS）另议

---

## 完成区

**状态**: 完成（**所有 expected_fault 向量转 PASS，FAIL=0，DIVERGE=0**）

### 交付
gem5 提交 `e3d12ae48f`（叠在 DG-004b `2c716add01` 上，分支 `dadao-arch-skeleton`，未 push）：
- `src/arch/dadao/faults.hh/.cc` — DADAOFault 带 (name, exit code)；IlliFault(0x82)/MalignFault(0x81)/UndiFault(0x83) + UnimplFault(0x7F) 弃权哨兵
- `src/arch/dadao/decoder.cc` — 各指令 execute 加 legality/align 检测；UNDI vs 未实现区分

DADAO-0628 侧（**未 commit**，待架构师 review）：
- `tests/scripts/run_gem5_test.py` — expected_fault 向量不再 SKIP，读 SE 退出码比对 FAULT_CODES

### 异常模型（语义/分类仅从 spec § + opcodes.yaml + ADR-0004 派生，未抄 QEMU cpu.c/translate.c）
- **ILLI=0x82**（§2.6）：rdha/rdhb=rd0 目标（RR2R/RI2R 族、load/store/multi、addi-rd/rb）、
  rbha/rbhb=rb0 目标、dual-dest 双 rd0 或同寄存器（add/sub/muls/mulu/divs/divu）、除零 +
  INT64_MIN÷-1（§3.7）、multi immu6=0 与 first+immu6>64（§2.6.3）、块拷贝 legality、unimp
- **MALIGN=0x81**（§3.1）：单/多 load/store EA 未按宽度对齐
- **UNDI=0x83**（§2.5/§2.8.1）：**保留编码**（未分配 major op、保留 MISC-Norm minor）→ UnknownInst。
  **与 ILLI 严格区分**：保留编码=UNDI，已知指令非法操作数=ILLI（QEMU 曾在 DL-043b 混淆，gem5 从 spec 分对）
- **未实现≠保留**：控制流（br*/jump_r/call/ret，jump-iiii 除外）与寄存器块拷贝**语义** = 已定义但未实现 →
  AbstainInst/BlockCopyStub 抛 UnimplFault(0x7F) → harness SKIP（**不是** UNDI）；块拷贝仍做 ILLI legality
- 精确异常（§2.7）：fault 在写任何寄存器/内存**之前**返回，无副作用

### harness fault 比对（run_gem5_test.py）
expected_fault 向量现在照常构建运行；gem5 抛 fault → SE 退出码 → `parse_exit_code` 从
`SIM_END: <cause> code=<n>` 取码 → 比对 FAULT_CODES（0x81/0x82/0x83）。退出码 0x7F=未实现→SKIP。
run_differential 判定逻辑未动。

### 真实终端输出

**每个向量文件 FAIL=0**（fault 向量全转 PASS）：
```
control-flow.yaml: PASS=1  SKIP=36 FAIL=0
misc.yaml:         PASS=3  SKIP=0  FAIL=0
rb-ops.yaml:       PASS=26 SKIP=2  FAIL=0
rd-arith.yaml:     PASS=19 SKIP=0  FAIL=0
rd-compare.yaml:   PASS=10 SKIP=0  FAIL=0
rd-cond-assign:    PASS=10 SKIP=0  FAIL=0
rd-load-store:     PASS=49 SKIP=0  FAIL=0   (DG-004b 时 38/11/0 → 现 49/0/0)
rd-logic.yaml:     PASS=8  SKIP=0  FAIL=0
rd-shift-extend:   PASS=21 SKIP=0  FAIL=0
rd-wyde-block:     PASS=15 SKIP=4  FAIL=0
```

```
$ python3 tools/run_differential.py | tail -2
=== AGREE(3-way)=162  AGREE(interp+QEMU, gem5-SKIP)=36  DIVERGE=0  HARNESS=6  QEMU-SKIP=0 ===
    gem5 covers 162 of the 198 interp+QEMU-agreed cases ...
```
AGREE(3-way) 131 → **162**（+31，= 全部 31 个 fault 向量转 AGREE），**DIVERGE=0**。

**三类 fault code 抽查（单指令 ELF 实跑，退出码十进制）**：
```
ILLI  (ldbs rd0,rb0,+8) : SIM_END: ILLI   code=130  (0x82)
MALIGN(ldo rd1,rb2,+255): SIM_END: MALIGN code=129  (0x81)
UNDI  (op 0x11 保留)     : SIM_END: UNDI   code=131  (0x83)
UNDI  (MISC-Norm 0x30保留): SIM_END: UNDI  code=131  (0x83)
HALT  (halt rd0)         : SIM_END: halt   code=0
```
**UNDI(0x83) ≠ ILLI(0x82) 分类未混。**

```
$ scons build/DADAO/gem5.opt -j6   # exit 0
smoke_arith → halt code=42 ; smoke_add → halt code=42 ; smoke_jump → halt code=0
```
3 smoke 42/42/0 不回归。

### 关于目标数（162 vs 192）—— 需架构师知悉
任务预估「67 SKIP 几乎全是 fault 向量」偏乐观：实测 67 个 gem5-SKIP = **31 个 fault 向量**（本任务已全部转 AGREE）
+ **36 个功能指令语义**（30 控制流分支 br*/jump_r/call/ret + 6 寄存器块拷贝 rd2rd/rd2rb/rb2rd/rb2rb）。
后 36 个是**功能语义、非 fault**，超出 DG-004c（异常模型）范围：控制流需分支+RA 栈（call/ret）实现，
块拷贝需寄存器组间搬运语义。故 fault 模型完成后达 **162/DIVERGE=0**，逼近 192 的余量全在控制流/块拷贝语义。
建议后续任务（G3 控制流 / 块拷贝语义）收口至 ~198。

---

## Codex Review

**判决: APPROVE**（DG-004c 范围内：异常模型完整、三类 code 分对、UNDI≠ILLI；功能语义缺口如实标注）

独立重跑（reviewer 亲自执行）：

1. **run_gem5_test fault 向量 PASS / FAIL=0** — 全 10 个向量文件 FAIL=0（见上表）。
   rd-load-store 49/0/0（DG-004b 遗留的 11 个 fault SKIP 全转 PASS）；rd-arith/compare/shift/misc/
   cond-assign/logic 全 0 SKIP 0 FAIL。剩余 SKIP（control-flow 36、rb-ops 2、rd-wyde-block 4）逐条核对
   均为控制流分支语义或寄存器块拷贝语义——功能指令、非 fault，合理弃权（UnimplFault→SKIP，非误判）。

2. **run_differential DIVERGE=0** — AGREE(3-way)=162（较 131 增 31），**DIVERGE=0**，HARNESS=6（6 个
   控制流 rb0 单指令模型弃权，interp 亦弃权，未计 DIVERGE）。无回归：DG-004b 的 131 全部保留。

3. **三类 fault 抽查各抛对 + UNDI≠ILLI**（单指令 ELF 实跑）：
   - ILLI：`ldbs rd0,rb0,+8`（0x30002008）rdha=rd0 → **code=130=0x82** ✓ §2.6.1
   - MALIGN：`ldo rd1,rb2,+255`（0x330420FF）EA=0x87FF00FF 非 8 对齐 → **code=129=0x81** ✓ §3.1
   - UNDI：保留 major op 0x11 → **code=131=0x83**；保留 MISC-Norm minor 0x30 → **code=131=0x83** ✓ §2.5
   - **UNDI(0x83) 与 ILLI(0x82) 严格区分未混**；unimp（已定义指令）走 ILLI 而非 UNDI，分类正确。
   语义/分类均从 spec §+opcodes.yaml+ADR-0004 派生；未见 QEMU cpu.c/translate.c 借用。

4. **gem5.opt build & smoke 不回归** — build exit 0；smoke_{arith,add,jump}=42/42/0。

遗留（非本任务）：控制流分支语义 + 寄存器块拷贝语义（36 向量）→ G3/后续；补齐后三方可达 ~198。
