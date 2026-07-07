# DL-042a: M2a Python 工作黄金模型 + 差分 QEMU（ADR-0009 M2a，第一阶段）

**执行环境**: 本地 DS · DADAO-0628

**状态**: 待执行

**依据**: ADR-0009 §M2a（Accepted）

---

## 背景

验证链的 QEMU 执行侧现状：oracle 是**枚举式**手写 YAML 向量（203 条）。ADR-0009 M2a 要建一个**可执行的独立黄金模型**——从 spec/opcodes.yaml **直接派生**的 Python 解释器，与 QEMU 差分。价值：① 把 oracle 从枚举升级为**生成式**（任意/生成程序可判）；② 给 Phase 5 生成的代码当 oracle（编译→QEMU 跑→比对解释器）。

**独立性是命根子**：解释器语义**只从 `contracts/isa/spec.md` + `tools/opcodes.yaml`（+ wiki）派生，绝不从 QEMU 源码抄**。decode 从 opcodes.yaml 驱动。只有独立，`解释器 vs QEMU` 差分才非循环、才能抓 QEMU 实现 bug + spec 翻译错误。

本任务是 M2a **第一阶段**：框架 + 核心指令切片 + 差分。全 87 指令覆盖留后续。

---

## 目标（Type-A，可机械验）

1. Python 解释器复现**核心切片**（rd-arith、rd/rb load/store、control-flow）所有 active 向量的 `expected_state`。
2. 差分 harness 确认 **解释器 == QEMU** 于同一批向量。
3. 两处不一致都如实报（可能是解释器 bug、QEMU bug、或向量/spec 问题——架构师三查）。

---

## 接口说明书

### 1. 解释器 `tools/dadao_interp.py`

- **状态**：RD/RB/RF/RA bank（RF 可最小/M1 排除）、内存、PC。RB 48-bit 有效地址规则、RD 64-bit。
- **decode**：从 `tools/opcodes.yaml` 驱动（mask/value + 字段布局），不硬编码。
- **语义**：从 `contracts/isa/spec.md` 实现本阶段指令类——arith（add/sub/addi/mul/div…）、load/store（RD/RB，含多寄存器 ldm/stm）、control-flow（branch/call/ret，RegRAS）。
- **fault**：ILLI/UNDI/MALIGN/IALIGN/RASOF/RASUF——按 spec legality 触发（复用已梳理的 wiki 出处）。
- **接口**：`run(program_bytes 或 单指令 word, input_state) -> (output_state, fault)`。

### 2. 向量验证 `tools/validate_interp.py`

- 对本阶段覆盖的 yaml 向量，跑解释器，断言 `解释器输出 == 向量 expected_state`（fault 同理）。
- 报告：覆盖数 / PASS / MISMATCH（列出 file:line + 期望 vs 解释器）。

### 3. 差分 harness `tools/run_differential.py`

- 对同一向量/程序，跑**解释器**与 **QEMU**（复用现有 `run_qemu_test.py` 的 QEMU 执行 + 状态 dump 路径），逐寄存器/内存比对架构状态。
- 报告：AGREE / DIVERGE（列出分歧项 + 两侧值）。
- 首轮：对本阶段向量跑差分，确认三方一致（spec 手写向量 / 解释器 / QEMU）。

### 独立性与集成

- **不读 QEMU 源码**实现语义；decode 用 opcodes.yaml；语义引 spec.md §。
- 新增独立 `make check-golden`（跑 validate_interp + run_differential 本阶段切片），**暂不并入 make check**（覆盖未全）。

---

## 约束

- **解释器独立于 QEMU**（不抄 translate.c 逻辑）；语义源标 spec.md §。
- 本阶段只做 arith/load-store/control-flow 切片；wyde/logic/shift/compare/cond-assign/misc 留后续（报告覆盖）。
- 不改 QEMU/LLVM/spec/向量（发现向量/spec 疑点→报告回架构师，不擅改）。
- 不并入 make check（覆盖未全）。

---

## 过程要求（reviewer 见 reviewer.md）

1. 完成区**粘贴真实终端输出**：validate_interp（覆盖+PASS/MISMATCH）、run_differential（AGREE/DIVERGE）。不许重写/估算。
2. 交付前自跑通。
3. reviewer 独立重跑 validate_interp + run_differential，抽查解释器某指令语义确从 spec.md 派生（非抄 QEMU），判决带自己输出，写 `## Codex Review`。

---

## 验收（架构师亲自复跑）

```bash
cd ~/DADAO-0628
python3 tools/validate_interp.py 2>&1 | tail -15    # 本阶段向量 PASS，列覆盖
python3 tools/run_differential.py 2>&1 | tail -15   # 解释器 vs QEMU AGREE
make check-golden 2>&1 | tail -5
grep -c "check-golden" <(sed -n '/^check:/p' Makefile)   # 0：未并入 check
make check 2>&1 | tail -3                            # 不受影响、全绿
```

---

## 参考指针

- ADR-0009 §M2a、§独立性保证、§射程总表
- `contracts/isa/spec.md`（语义源，逐指令 §）；`tools/opcodes.yaml`（decode 驱动 + 编码契约）
- `tests/vectors/isa/*.yaml`（验证/差分语料，203 active）
- `tests/scripts/run_qemu_test.py`（QEMU 执行 + 状态 dump，差分复用）
- feedback（memory）：RB 48-bit 截断、load_reg 3 wyde、rd2rb 64-bit 不对称、SMC heisenbug——解释器实现这些边界须对齐
- **不参考** QEMU `target/dadao/translate.c` 实现（独立性要求）

---

## 完成区

**状态**：部分完成（核心切片全部交付并跑通；暴露 2 条真实 QEMU-vs-spec 分歧 + 6 条 harness 伪影，如实上报，未擅改）

**修改文件**：
- `tools/dadao_interp.py`（新增）：独立黄金模型。RD/RB/RF/RA bank + 48-bit 内存 + PC + fault（ILLI/UNDI/MALIGN/IALIGN/RASOF/RASUF）。decode 由 `opcodes.yaml` 的 mask/value + 字段布局驱动；语义逐条从 `spec.md §` 实现（52 处 § 引用）。**未读 QEMU 源码**（唯一出现 "translate.c" 的地方是声明"不读它"的 docstring）。
- `tools/validate_interp.py`（新增）：对核心切片 3 个向量文件跑解释器，断言 `解释器 == 向量 expected_state`（含 fault），报 PASS/MISMATCH/SKIP。
- `tools/run_differential.py`（新增）：同批向量在解释器与 QEMU（复用 `tests/scripts/run_qemu_test.py`）上跑、三方（解释器/QEMU/手写向量）比对，报 AGREE/DIVERGE。
- `Makefile`：新增独立 `check-golden`（跑 validate_interp + run_differential），**未并入 make check**。

**覆盖清单**（本阶段核心切片）：
- arith：addi, add, sub, muls, mulu, divs, divu（`rd-arith.yaml` 19/19 PASS）
- load/store：ldbs/ldbu/ldws/ldwu/ldts/ldtu/ldo、stb/stw/stt/sto、ldm*/stm*（RD 多寄存器）、ldmo-rb（`rd-load-store.yaml` 46 PASS / 2 MISMATCH）
- control-flow：brn/brnn/brz/brnz/brp/brnp、breq/brne、jump(i/r)、call(i/r)、ret + RegRAS push/pop（`control-flow.yaml` 31 PASS / 6 SKIP-harness）
- 解码器另可识别 wyde/logic/shift/compare/cond-assign/RB-arith 等，但语义**留后续**（`Unsupported`，不执行）。misc/rb-ops/rd-* 其它文件本阶段不纳入 validate。

**验收结果（真实终端输出，未改写）**：

```
$ python3 tools/validate_interp.py    (exit=1)
=== validate_interp: DL-042a core slice ===
  rd-arith.yaml          PASS= 19 MISMATCH=  0 SKIP-unsupported=  0 SKIP-harness=  0
  rd-load-store.yaml     PASS= 46 MISMATCH=  2 SKIP-unsupported=  0 SKIP-harness=  0
  control-flow.yaml      PASS= 31 MISMATCH=  0 SKIP-unsupported=  0 SKIP-harness=  6
--- MISMATCH (interpreter vs vector — findings) ---
   rd-load-store.yaml case[2] ldo: unexpected fault MALIGN | ldo rd1,rb2,+255; load octa = 0x1234567890ABCDEF
   rd-load-store.yaml case[6] ldo: unexpected fault MALIGN | ldo rd1,rb2,+4095; max offset (0xFFF)
=== TOTAL PASS=96 MISMATCH=2 SKIP-unsupported=0 SKIP-harness=6 ===

$ python3 tools/run_differential.py   (exit=1)
=== run_differential: interpreter vs QEMU (DL-042a core slice) ===
    qemu = /home/holight/DADAO-0628/.work/source/qemu/build/qemu-system-dadao
--- DIVERGE (interp vs QEMU — findings, architect triages) ---
   rd-load-store.yaml case[2] ldo: interp=MISMATCH(unexpected fault MALIGN); qemu=PASS(exit=0) | ldo rd1,rb2,+255; ...
   rd-load-store.yaml case[6] ldo: interp=MISMATCH(unexpected fault MALIGN); qemu=PASS(exit=0) | ldo rd1,rb2,+4095; ...
=== AGREE=96 DIVERGE=2 HARNESS=6 QEMU-SKIP=0 ===

$ make check   (exit=0)  →  ISSUE REGISTRY: PASS / repository checks: PASS
$ grep -c "check-golden" <(sed -n '/^check:/p' Makefile)  →  0（未并入 check）
```

**遗留问题 / 上报架构师（三查，未擅改向量或解释器）**：

1. **【真分歧 · DIVERGE×2】`ldo` 非对齐但 QEMU 不抛 MALIGN。** 向量 `ldo rd1,rb2,+255`（EA=0x87FF00FF）与 `ldo rd1,rb2,+4095`（word 0x33042FFF，imms12 为**有符号** → -1，EA=0x87FEFFFF）两条 EA 均非 8 对齐。spec §3.1 明列 `ldo | 8 | MALIGN`，故解释器抛 MALIGN；QEMU 实测 exit=0（正常返回值）。→ 三种可能：(a) QEMU 缺 ldo 对齐检查（QEMU bug）；(b) 向量用了非对齐的 max-offset（向量 bug）；(c) spec §3.1 过严。**M2a 的价值产出，请架构师定夺，未擅改。** 另注：+4095 向量的 notes 写 "+4095" 但 imms12 有符号上限 +2047，0xFFF=-1，notes 与字段语义不一致（次生疑点）。

2. **【harness 伪影 · SKIP×6】control-flow 的 encoding/legality 向量 expected_fault=ILLI 是 harness 多指令结果，非单指令 ISA 语义。** jump/call `rrii`（rb0,rd0,0）单指令语义 = 跳到 PC+4（spec §5.3 rbha=rb0 相对跳），无 fault；ret 冷 RAS 单指令语义 = **RASUF**（spec §5.6），非 ILLI。向量的 ILLI 来自"跳到地址 0 → 执行 halt rd0 → QEMU 退出 ILLI"这一 harness 布局。单指令黄金模型刻意不复现，标 SKIP-harness。**另暗含**：QEMU 冷 RAS ret 未抛 spec §5.6 的 RASUF（而是落到 halt→ILLI），可能是 QEMU RASUF 未实现——建议 M3 legality 矩阵专门覆盖 RASOF/RASUF。

3. **【opcodes.yaml 空缺】store 类 legality 未含 `rdha != rd0`。** `opcodes.yaml` 中 stb/stw/stt/sto/stm* 的 `legality: []`，但 spec §2.6.1/§3.2 明确"store from rd0 → ILLI"，向量 encoding 也期望 ILLI。解释器按 **spec** 实现该约束（非从 opcodes.yaml），故 PASS。建议后续把该约束补进 opcodes.yaml 以保持编码契约完备。

4. `check-golden` 因上述真分歧当前 exit≠0（诚实暴露，未 whitelist 凑绿）。它是独立目标、**未并入 make check**，不阻塞仓库结构检查（make check 仍全绿）。

---

## Codex Review

**复审者**：Claude（架构师自审，按 reviewer.md 六项独立重跑）

### 重跑记录（我自己的真实输出 + 退出码）

```
$ python3 tools/validate_interp.py ; echo rc=$?
=== TOTAL PASS=96 MISMATCH=2 SKIP-unsupported=0 SKIP-harness=6 ===   rc=1
    （2 MISMATCH 均为 rd-load-store case[2]/[6] ldo → MALIGN）

$ python3 tools/run_differential.py ; echo rc=$?
    qemu = .work/source/qemu/build/qemu-system-dadao
=== AGREE=96 DIVERGE=2 HARNESS=6 QEMU-SKIP=0 ===                     rc=1
    （2 DIVERGE：interp=MALIGN vs qemu=PASS(exit=0)，即 ldo 非对齐两条）

$ make check-golden ; echo rc=$?
=== TOTAL PASS=96 MISMATCH=2 ... ===
=== AGREE=96 DIVERGE=2 HARNESS=6 QEMU-SKIP=0 ===                     rc=2（两工具都真跑，非零暴露分歧）

$ grep -c "check-golden" <(sed -n '/^check:/p' Makefile)  →  0        （未并入 check）

$ make check 2>&1 | tail -3 ; (真实 rc=0)
Total:  14
ISSUE REGISTRY: PASS
repository checks: PASS
```

### 约束核验（逐条）

- **独立性（命根子）**：✅ `grep translate.c/helper.c/target/dadao/tcg` 于 dadao_interp.py 仅命中 docstring 中"DELIBERATELY does NOT read"一句；无 QEMU 源码搬运痕迹。解释器 52 处 `spec §` 引用。抽查 3 条语义确从 spec 推：
  - `add/sub`（§3.5）：源 sext 到 128 位、rdha=高半/rdhb=低半——与 QEMU TCG 写法无关，直接照 spec §3.5 "result[127:64]→rdha, result[63:0]→rdhb"。
  - `divs`（§3.7）：截断向零 + 余数符号随被除数 + div0/INT64_MIN÷-1→ILLI——照 spec §3.7 逐条，非 QEMU helper。
  - RegRAS `push/pop`（§5.6）：cnt==0 首压 / 递归折叠 / 满则下移+RASOF；pop cnt>1 递减、cnt==1 上移+清 ra1、cnt==0 RASUF——严格照 spec §5.6 方向（与已知 feedback「RAS push/pop 方向」一致）。
- **decode 由 opcodes.yaml 驱动**：✅ `decode()` 遍历 opcodes.yaml 的 (mask,value) 匹配 + 字段 bit 区间抽取，无硬编码 opcode 表。
- **只做核心切片**：✅ arith/load-store/control-flow；其余 `Unsupported` 不执行、报覆盖。
- **不改 QEMU/LLVM/spec/向量**：✅ `git`/文件层面仅新增 3 个 tools + Makefile 加独立 target；spec.md、tests/vectors/、opcodes.yaml 未改（发现的 3 类疑点均上报未擅改，符合"别为凑 PASS 迎合 QEMU / 别擅改向量"）。
- **不并入 make check**：✅ grep=0；make check 独立跑 rc=0 全绿、不受影响。
- **完成区贴真实输出**：✅ 与我重跑一致（PASS=96/MISMATCH=2/SKIP-harness=6；AGREE=96/DIVERGE=2）。

### 判决

**Accepted（作为 worker 达标证据）**。核心切片解释器独立于 QEMU、decode 由 opcodes.yaml 驱动、语义 spec 溯源，validate/differential 均真跑并**如实**暴露分歧而非凑绿。

**但架构师需终审 3 项上报（非实现缺陷，是链上真问题）**：
1. `ldo` 非对齐 MALIGN：QEMU 缺对齐检查 vs 向量非对齐 vs spec 过严——三查定夺（我倾向 QEMU 侧缺 §3.1 对齐强制 + 向量 max-offset 恰好非对齐，二者叠加）。
2. control-flow ILLI 向量是 harness 伪影；且 QEMU 冷 RAS ret 未抛 §5.6 RASUF → 建议 M3 覆盖。
3. opcodes.yaml store 类 legality 缺 `rdha != rd0`，与 spec §2.6.1 不一致，建议补齐。

`check-golden` 当前 exit≠0 是**诚实暴露真分歧**（符合 ADR-0009 M2a "分歧即价值"、reviewer.md "不许凑绿"），非任务失败；它独立于 make check、不阻塞仓库检查。
