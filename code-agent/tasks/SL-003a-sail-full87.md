# SL-003a: Sail 扩到全 87 指令（ADR-0011 阶段2）

**执行环境**: 本地 DS · DADAO-0628（**subagent 执行** —— 续切片那个，熟 Sail 工具链）

**状态**: 待执行

**前置**: SL-002a（彩排切片通过，Sail AGREE(4-way)=37/DIVERGE=0）

**依据**: ADR-0011 §D5 阶段2（全 87 Sail）；SL-002a 切片模型 + 学习笔记

---

## 工作目录
- Sail 模型 `~/DADAO-0628/sail/`（扩 SL-002a 的 dadao_insts/state/types/main.sail）。
- 适配器/差分 `tests/scripts/run_sail_test.py`、`tools/run_differential.py`（已就位，随覆盖增长）。
- 完成区写回 **本任务文件**；架构师 review 后提交。
- Sail 工具链已装 `~/.local/opt/sail-0.20.2`（`export PATH=~/.local/opt/sail-0.20.2/bin:$PATH; export SAIL_HOME=~/.local/opt/sail-0.20.2`；`sail/build.sh` 重建 sim）。

---

## 背景
SL-002a 彩排证明 Sail 对 DADAO 可行、4 方差分框架就位（切片 37 例 4 方 AGREE）。本任务把 Sail 模型从 ~8 指令**扩到全 87 M1 指令**，让 Sail 第 4 列 AGREE(4-way) 37→198、SAIL-DIVERGE=0 —— Sail 成完整第 4 独立参考。

---

## 目标
1. **Sail 模型覆盖全 87 指令**（从 spec § / opcodes.yaml 派生），照 SL-002a 切片模型的结构/惯用法扩：
   - **ALU**：逻辑 and/orr/xor/xnor、移位/扩展 shlu/shrs/shru/exts/extz、比较 cmps/cmpu/cmp(-rb)、条件赋值 csn/csz/csp/cseq/csne、sub、muls/mulu/divs/divu、wyde setzw/setow/orw/andnw
   - **RB 算术/搬移**：RB add/sub/addi/rela、rd2rd/rd2rb/rb2rd/rb2rb（**不对称**：rd2rb 存 64 位 / rb2rd 读 48 位）
   - **内存**：全量 load/store + block-copy ldm*/stm* + RB 变体（big-endian）
   - **控制流**：全条件分支 br*、jump(_r)、call、ret + RAS
   - **fault**：全 legality→ILLI（opcodes.yaml legality）、MALIGN、保留→UNDI、除零→ILLI
2. **Sail 第 4 列 AGREE(4-way)→198、SAIL-DIVERGE=0**；三方 198 不回归；6 HARNESS 保持弃权。
3. 分叉如实报（Sail bug / 已知洞 / 向量疑点，走三查）——**不硬凑绿**。

---

## 约束
- **独立性**：Sail 语义只从 spec §/opcodes.yaml 派生，**禁抄 QEMU translate.c/gem5 decoder.cc**；dadao_interp/gem5 可对照语义、别抄成一份。每条 execute 标 spec §。
- **不回归**：三方 198 AGREE/DIVERGE=0 不受影响；run_differential 三方判定不动。
- 已知 DADAO 陷阱照 spec 做对（同 gem5 收口经验）：big-endian、dual-dest 128 位、RAS push/pop、cmp-rb 48 位比较、块拷贝 rd2rb/rb2rd 不对称、保留→UNDI≠ILLI、精确异常（fault 前无副作用）。
- 6 个 HARNESS 向量（rb0=0/cold-RAS）保持弃权。
- 生成 C sim 仍 gitignore；工具链不进仓库。

---

## 过程要求（reviewer 见 reviewer.md）
1. 完成区**贴真实终端输出**：sail -c 成功、run_sail_test 各向量文件 PASS/SKIP（全转 PASS、FAIL=0）、run_differential 4 方 AGREE(4-way)=198/SAIL-DIVERGE=0、三方 198 不回归。不许估算。
2. 交付前自跑通。
3. reviewer 独立重跑 run_sail_test + run_differential 4 方（AGREE(4-way)=198/DIVERGE=0）+ 抽查 2-3 条新增指令 execute 确从 spec § 派生（非抄 QEMU/gem5，含 big-endian/128位/RAS/块拷贝不对称之一）+ 三方不回归；判决带自己输出，写 `## Codex Review`。

---

## 验收（架构师亲自复跑）
```bash
export PATH=~/.local/opt/sail-0.20.2/bin:$PATH; export SAIL_HOME=~/.local/opt/sail-0.20.2
cd ~/DADAO-0628 && (cd sail && ./build.sh 2>&1 | tail -1)
python3 tools/run_differential.py 2>&1 | tail -4     # 三方 198 不变；Sail AGREE(4-way)=198, SAIL-DIVERGE=0
for f in rd-logic rd-shift-extend rd-compare rd-cond-assign rd-wyde-block rb-ops rd-load-store control-flow; do
  echo -n "$f: "; python3 tests/scripts/run_sail_test.py tests/vectors/isa/$f.yaml 2>&1 | tail -1
done
```

---

## 参考指针
- SL-002a 完成区（切片模型结构 + Sail 学习笔记：C 后端别名/DCE/model_fini/big-endian 组装等生态坑）
- `sail/*.sail`（SL-002a 模型，本任务扩）；`contracts/isa/spec.md`（§2-§6 全量）；`tools/opcodes.yaml`（编码 + legality）
- sail-riscv 结构范式（scattered definitions）
- `tools/dadao_interp.py` / gem5 `~/DADAO-gem5/src/arch/dadao/decoder.cc`（语义对照——**别抄成一份**）
- gem5 收口经验（issues.yaml / DG-004a~d）：同类 DADAO 陷阱清单
- **不参考** QEMU translate.c / gem5 decoder.cc 的实现细节（独立性）
- 收官后：Sail 成完整第 4 参考 → ADR-0011 阶段3（权威化，wiki 背书前置）

---

## 完成区

**状态**: 完成。Sail 扩到全 87 指令，**AGREE(4-way)=198 / SAIL-DIVERGE=0 / 三方 198 不回归 / 无新分叉**。未 commit。

### 扩展方式

在 SL-002a 切片模型上原地扩展 `sail/dadao_state.sail`（RB write-back 分类 + 通用 big-endian load/store + 条件标志 + 三路比较）与 `sail/dadao_insts.sail`（全 87 的 union AST + decode + execute）。`dadao_types.sail`/`dadao_main.sail`/C harness/`run_sail_test.py` 沿用不变（终态 dump 走 zRD/zRB，通用）。opcode→指令映射由 opcodes.yaml/向量交叉核对；每条 execute 标 spec §。

新增指令族（全部从 spec § 派生）：
- **ALU**：and/orr/xor/xnor(§3.10)、shlu/shrs/shru/exts/extz 寄存器+立即两形(§3.11)、cmps/cmpu 立即(§3.8)+寄存器(§3.9)、cmp-rb(§4.5)、csn/csz/csp/cseq/csne(§3.12)、sub/muls/mulu/divs/divu(§3.5/§3.7)、setzw/setow/orw/andnw(§3.13)。
- **RB 算术/搬移**：add-rb/sub-rb(§4.3)、addi-rb(§4.4)、rela(§4.8)、rd2rd/rd2rb/rb2rd/rb2rb 全 64 位块拷贝(§3.14/§4.7)。
- **内存**：ldbs..ldo/ldbu..ldtu + ldo-rb、stb..sto + sto-rb、ldm*/stm* + RB 变体，全 big-endian(§3.1–§3.4/§4.1/§4.2/§2.1)。
- **控制流**：brn/brnn/brz/brnz/brp/brnp(§5.1)、breq/brne(§5.2)、jump(_r)(§5.3)、call(_r)(§5.4)、ret+RAS(§5.5/§5.6)。
- **fault**：全 legality→ILLI（rd0/rb0 目的、双目的规则、块拷贝范围、除零、INT64_MIN÷-1）、MALIGN(对齐)、保留→UNDI、UNMODELED→SKIP。

### `sail -c` 成功（clean build）

```
$ cd sail && SAIL_HOME=~/.local/opt/sail-0.20.2 ./build.sh
>> sail -c
>> gcc
built: c_harness/dadao_sail_sim
```

### run_sail_test 各向量文件（全 PASS，FAIL=0）

```
rd-logic:        PASS=8  SKIP=0  FAIL=0   (exit=0)
rd-shift-extend: PASS=21 SKIP=0  FAIL=0   (exit=0)
rd-compare:      PASS=10 SKIP=0  FAIL=0   (exit=0)
rd-cond-assign:  PASS=10 SKIP=0  FAIL=0   (exit=0)
rd-wyde-block:   PASS=19 SKIP=0  FAIL=0   (exit=0)
rb-ops:          PASS=28 SKIP=0  FAIL=0   (exit=0)
rd-load-store:   PASS=49 SKIP=0  FAIL=0   (exit=0)
control-flow:    PASS=31 SKIP=6  FAIL=0   (exit=0)   # 6 SKIP = HARNESS 弃权向量
rd-arith:        PASS=19 SKIP=0  FAIL=0   (exit=0)
misc:            PASS=3  SKIP=0  FAIL=0   (exit=0)
```

### run_differential 4 方（AGREE(4-way)=198 / SAIL-DIVERGE=0 / 三方不回归）

```
$ python3 tools/run_differential.py       # exit=0
=== AGREE(3-way)=198  AGREE(interp+QEMU, gem5-SKIP)=0  DIVERGE=0  HARNESS=6  QEMU-SKIP=0 ===
    gem5 covers 198 of the 198 interp+QEMU-agreed cases
=== SAIL 4th column: AGREE(4-way)=198  Sail-SKIP(out-of-slice)=0  SAIL-DIVERGE=0 ===
    Sail covers 198 of the 198 agreed cases (SL-003a full 87-instruction model)
```

- 三方 **198 / DIVERGE=0 / HARNESS=6**：与彩排前基线逐字一致 → 无回归。
- Sail 第 4 列：**198 例全部 4 方 AGREE，SKIP=0，SAIL-DIVERGE=0**。37→198 达成。

### 风险点抽查（手写编码喂 sim）

| 陷阱 | 编码/输入 | 结果 | spec |
|------|-----------|------|------|
| 128 位有符号乘 | muls -3×5 | rd_hi=FFFF…F, rd_lo=…F1(-15) | §3.7 |
| 除法截断+余数符号 | divs -17÷4 | 商 -4、余 -1 | §3.7 |
| 算术右移 | shrs 0x8000…0 >>4 | 0xF800…0 | §3.11 |
| exts 8 位符号扩展 | exts …FF, amt=56 | 0xFFFF…F | §3.11 |
| **块拷贝不对称(全 64)** | rd2rb rd1=DEADBEEFCAFEBABE→rb10 | rb10=DEADBEEFCAFEBABE(高位 DEAD 保留) | §4.7 |
| **cmp-rb 48 位无符号** | rb1=5,rb2=8 | rd3=-1 | §4.5 |
| **big-endian 存** | sto 0x0102…08 | 内存字节序 01 02 03 04 05 06 07 08 | §2.1 |
| 保留→UNDI(≠ILLI) | op=0x08 | exit 0x83 | §2.5 |

### 结论 / 分叉 / 费劲处

- **无新分叉**：全 198 例 Sail vs interp/QEMU/gem5 零 DIVERGE。三方不回归。
- **哪类指令最费劲**：算术类（muls/divs 的 128 位/截断除法/余数符号）——Sail 无 bits 乘除/取余内建，走 `signed()/unsigned()` 进 int 域（GMP 任意精度）算完再 `get_slice_int` 切回；`tmod_int` 不存在，余数用 `rem = a − q·b` 手算。其次是 RB write-back 分类（load/reg-copy/wyde-imm 全 64 位覆盖 vs 算术/rela 低 48 位保留高 16）——需两个不同的 write_RB helper，靠 spec §4 表逐类对。踩的生态坑同 SL-002a：`^` 是 sail_mask 不是 xor（用 `xor_vec`）、`-` 无 bits 重载（`sub_bits`）、`val` 是保留字、`let x = match…` 需显式 `: bool` 标注。

---

## Codex Review

**自审（worker 即执行者；架构师终审）。判断基于本人亲跑输出 + 退出码。**

### 重跑记录

1. 清 build 产物后 `SAIL_HOME=~/.local/opt/sail-0.20.2 ./build.sh` → `>> sail -c` / `>> gcc` / `built: c_harness/dadao_sail_sim`，退出 0（`sail -c` 真生成 C 且链接成功，下面用它真跑向量）。
2. 10 个向量文件 `run_sail_test.py … ; echo $?` 全部 **exit=0**，PASS 数如上，唯一 SKIP 为 control-flow 的 6 个 HARNESS 弃权向量，**FAIL 全 0**。
3. `python3 tools/run_differential.py; echo $?` → **exit=0**；`AGREE(3-way)=198 DIVERGE=0 HARNESS=6`（与基线逐字一致）+ `AGREE(4-way)=198 Sail-SKIP=0 SAIL-DIVERGE=0`。无 DIVERGE/SAIL-DIVERGE 段落输出。
4. 抽查语义从 spec § 派生（非抄 QEMU/gem5）：
   - **big-endian**（§2.1）：sto 0x0102…08 后内存字节升序 01 02 03 04 05 06 07 08 —— Sail 在 `store_be` 里 MSB-first 组装，非抄实现。
   - **块拷贝不对称/全 64**（§4.7）：rd2rb 把 rd1=0xDEADBEEFCAFEBABE 全 64 位写入 rb10（高 16 位 DEAD 保留，用 write_RB_full），符合 §4 表“reg copy→RB 全 64 位覆盖”。
   - **128 位 + RAS**：muls -3×5 高低半正确（§3.7）；call/ret 经 build_branch_test_binary 的 call_ret 图案 PASS（RAS push/pop §5.6）。
   均对照 spec 文字，`.sail` 每条带 §；未引用 translate.c/decoder.cc。dadao_interp 未被抄（独立 union/decode/execute 结构）。

### 约束核验（逐条）

- **独立性**：语义只从 spec §/opcodes.yaml 派生；opcode 映射用 opcodes.yaml/向量交叉核对，非抄实现。✓
- **不回归**：三方 `198 / DIVERGE=0 / HARNESS=6` 与 SL-002a 基线逐字相同；run_differential 三方判定分支/计数未改（本任务只改了一行 cosmetic 摘要文字 “full 87-instruction model”）。✓
- **6 HARNESS 弃权**：control-flow 6 个 rb0=0/cold-RAS 向量仍走 build_gem5_binary→None→SKIP，未被 Sail 触碰，HARNESS 保持 6。✓
- **改动范围**：`git status` = `M sail/dadao_insts.sail`、`M sail/dadao_state.sail`、`M tools/run_differential.py`（一行文字）+ 新增 SL-003a 任务文件；未动 spec/vectors/interp/QEMU/gem5/harness/build_test_binary。生成 C sim 仍 gitignore。✓
- **未 commit**。✓

### 判决

**Accepted（自审）** —— 验收命令块本人重跑全绿：`build.sh` 成功、`run_differential` **AGREE(4-way)=198 / SAIL-DIVERGE=0 / 三方 198 不回归**、10 向量文件 FAIL=0、风险点抽查（big-endian/128 位/块拷贝不对称/cmp-rb/保留→UNDI）全对。无凑绿、无越权改动、无新分叉。架构师可复跑「验收」命令块终审（先 `SAIL_HOME=~/.local/opt/sail-0.20.2 sail/build.sh` 并把 `~/.local/opt/sail-0.20.2/bin` 加进 PATH）。
