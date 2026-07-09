# DG-004b: DADAO-gem5 G2 batch-2 — 内存 load/store + block-copy

**执行环境**: 本地 DS · 跨 DADAO-0628 + DADAO-gem5（**subagent 执行** —— owns gem5 arch）

**状态**: 待执行

**前置**: DG-004a（ALU 批量，三方 AGREE=77/DIVERGE=0）

**依据**: ADR-0010 §里程碑-G2；DG-002a 的 StaticInst 模板 + DG-003a/004a 的 harness

---

## 工作目录（重要）
- gem5 指令实现落 **`~/DADAO-gem5`** 分支 `dadao-arch-skeleton`。
- harness 内存支持改 **`~/DADAO-0628/tests/scripts/run_gem5_test.py`**。
- 完成区写回 **`~/DADAO-0628` 本任务文件**。gem5 commit 到 DADAO-gem5；DADAO-0628 侧架构师 review 后提交。

---

## 背景
DG-004a 后三方差分覆盖 77/198，剩 121 gem5-SKIP 主要是**内存类指令**（load/store/block-copy）+ 异常/rb 入参。
本任务补**内存 load/store + block-copy**（无异常路径），让内存类向量从 SKIP 转 AGREE。**异常模型
（ILLI/MALIGN/UNDI、store-from-rd0、ldo 非对齐、除零）留 DG-004c——本任务不碰**，涉 fault 的内存向量保持 SKIP。

---

## 目标
1. **gem5 内存 load/store**（从 spec §3.1/§3.2 派生，**big-endian** §2.1）：
   - load：ldbs/ldbu、ldws/ldwu、ldts/ldtu、ldo（byte/wyde/tetra/octa，有/无符号；EA = rbhb + immu；结果入 rdha）
   - store：stb/stw/stt/sto（rdha → mem[rbhb+immu]，宽度截断）
   - block-copy：ldmbs/ldmbu/ldmws/ldmwu/ldmts/ldmtu/ldmo、stmb/stmw/stmt/stmo（immu6 个连续寄存器 ↔ 连续内存）
   - 用 gem5 的内存访问接口（StaticInst 内存操作数 + MemRead/MemWrite OpClass + `initiateAcc`/`completeAcc` 或原子 `readMem`/`writeMem`，参 riscv load/store 的**接口形状**）。
2. **harness 内存支持**（run_gem5_test.py）：向量 `input_state` 含初始 memory → 装入 gem5 SE 地址空间；`expected_state` 含 memory → 终态读出比对。rb 入参装载（EA 基址寄存器）也在此解锁。
3. **big-endian 内存**：多字节 load/store 按 spec §2.1 大端序（与取指 betoh 一致）。

**不做**：异常/fault（store rdha=rd0→ILLI、ldo EA 非 8B 对齐→MALIGN、legality）——保持 SKIP，DG-004c 补。

---

## 接口说明书
- 内存指令 StaticInst 照 DG-002a/004a 模板 + gem5 内存访问范式；EA 计算 = rbhb(48-bit 有效) + 立即数；语义标 spec §。
- harness 内存装入/读出：SE 模式下把 input_state.memory 写进进程地址空间；终态经 dump（扩展现有 DADAO_REGDUMP 机制，或另加 memory dump hook）读回比对 expected_state.memory。
- block-copy 的寄存器区间 + 内存区间连续性、immu6 范围按 spec §3.2/opcodes.yaml legality（合法性检查本身留 DG-004c，但地址/宽度计算要对）。
- 语义**只从 spec § + opcodes.yaml**，**禁抄 QEMU translate.c**；riscv 只借内存访问接口形状。

---

## 约束
- 独立性：禁抄 translate.c；dadao_interp 别抄成一份。
- **不回归**：DG-004a 的 77 AGREE 不退步；3 smoke 42/42/0；gem5.opt build；DIVERGE 保持 0。
- 涉 fault 的内存向量（expected_fault）保持 SKIP（DG-004c）。
- 不改 opcodes/spec/向量/dadao_interp；run_differential 判定逻辑不动（harness 内存支持可加，说明理由）。

---

## 过程要求（reviewer 见 reviewer.md）
1. 完成区**贴真实终端输出**：rd-load-store.yaml + block-copy 相关向量 PASS/SKIP（内存类转 PASS、FAIL=0）、run_differential 三方 AGREE(3-way) 增长且 DIVERGE=0、gem5.opt build、3 smoke 不回归。不许估算。
2. 交付前自跑通。
3. reviewer 独立重跑 run_gem5_test（内存向量 PASS）+ run_differential（DIVERGE=0）+ 抽查 2-3 条 load/store 语义从 spec 派生（含 big-endian）+ gem5.opt build & smoke 不回归；判决带自己输出，写 `## Codex Review`。

---

## 验收（架构师亲自复跑）
```bash
cd ~/DADAO-0628
python3 tests/scripts/run_gem5_test.py tests/vectors/isa/rd-load-store.yaml 2>&1 | tail -1   # 内存 load/store PASS，FAIL=0
python3 tools/run_differential.py 2>&1 | tail -3     # AGREE(3-way) 较 77 增长，DIVERGE=0
(cd ~/DADAO-gem5 && scons build/DADAO/gem5.opt -j6 2>&1 | tail -1)
# 3 smoke 42/42/0
git -C ~/DADAO-gem5 log --oneline -1
```

---

## 参考指针
- `~/DADAO-gem5/docs/gem5-arch-notes.md` + `src/arch/dadao/decoder.cc`（指令模板）
- `~/DADAO-0628/contracts/isa/spec.md`（§2.1 big-endian、§3.1 load、§3.2 store/block-copy、§1.3 RB 48-bit EA）
- `~/DADAO-0628/tools/opcodes.yaml`（ld*/st*/ldm*/stm* op/格式/字段/legality）
- `~/DADAO-0628/tests/vectors/isa/rd-load-store.yaml`（内存向量：input/expected memory）
- gem5 `src/arch/riscv/`（load/store StaticInst + MemRead/MemWrite **接口形状**，非语义）
- `~/DADAO-0628/tools/dadao_interp.py`（load/store 语义已实现，可对照——别抄成一份）
- **不参考** QEMU translate.c
- 后续 **DG-004c**：异常模型（ILLI/MALIGN/UNDI）+ 除零 + legality → 剩余 SKIP 转 AGREE → 203 三方全 AGREE

---

## 完成区

**状态**: 完成（DG-004c 前置的异常/fault 向量保持 SKIP）

### 交付
gem5 提交 `2c716add01`（叠在 `e0f346bf78` 上，分支 `dadao-arch-skeleton`，未 push）：
- `src/arch/dadao/decoder.cc` — 新增内存指令 + cmp-rb 修正 + 终态内存 dump
- `tests/dadao/dadao_se.py` — 切 AtomicSimpleCPU（同步 readMem/writeMem）
- `tests/dadao/gen_min_elf.py` — build_elf 支持可选 RW 数据段

DADAO-0628 侧（**未 commit**，待架构师 review）：
- `tests/scripts/run_gem5_test.py` — 解锁 memory/rb 入参 + DADAO_MEMDUMP 比对

### 新增指令（语义仅由 spec § + opcodes.yaml 派生，未抄 QEMU translate.c）
- RD 单 load：ldbs/ldbu/ldws/ldwu/ldts/ldtu/ldo（op 0x30-0x33, 0x40-0x42），spec §3.1
- RD 单 store：stb/stw/stt/sto（op 0x38-0x3B），spec §3.2
- RD 多 load：ldm{bs,bu,ws,wu,ts,tu,o}（op 0x34-0x37, 0x44-0x46），spec §3.3
- RD 多 store：stm{b,w,t,o}（op 0x3C-0x3F），spec §3.4
- RB load/store：ldo-rb/sto-rb（0x43/0x4B §4.1）、ldmo-rb/stmo-rb（0x47/0x4F §4.2）
- RB wyde 立即数：setzw-rb/orw-rb/andnw-rb（0x4E/0x4C/0x4D §4.6）—— harness rb 入参装载所需
- cmp-rb（0x10 minor 0x2D §4.5）：修正原实现（原比较 RD，应比较 RB 48-bit）

关键点：EA = (rbhb[47:0] + off) mod 2^48（§1.3）；多寄存器 EA_i = rbhb+rdhc+i×N（§3.3）；
所有多字节访问显式按大端组装/拆解（§2.1），与取指 betoh 一致，host 端序无关。

### harness 内存支持（run_gem5_test.py）
- 固定内存窗口 [0x87FEF000, +0x3000) 作为 RW 数据段映入每个测试 ELF：load 输入/store 目标
  有有效页；input_state.memory 直接大端初始化写入窗口。
- 终态 gem5 在 halt 时 tryReadBlob 该窗口发 `DADAO_MEMDUMP`；harness 解析后大端读回比对
  expected_state.memory（tryReadBlob → smoke ELF 未映射窗口不会 abort，只是不发 MEMDUMP）。
- run_differential 判定逻辑未动。

### 真实终端输出

```
$ python3 tests/scripts/run_gem5_test.py tests/vectors/isa/rd-load-store.yaml | tail -1
=== gem5: PASS=38 SKIP=11 FAIL=0 (total 49) ===
```
（11 SKIP 全为 expected_fault 向量：ILLI rdha=rd0 / immu6=0 / 最小操作数、MALIGN 非对齐 —— DG-004c）

```
$ python3 tests/scripts/run_gem5_test.py tests/vectors/isa/rb-ops.yaml | tail -1
=== gem5: PASS=20 SKIP=8 FAIL=0 (total 28) ===
```

```
$ python3 tools/run_differential.py | tail -2
=== AGREE(3-way)=131  AGREE(interp+QEMU, gem5-SKIP)=67  DIVERGE=0  HARNESS=6  QEMU-SKIP=0 ===
    gem5 covers 131 of the 198 interp+QEMU-agreed cases ...
```
AGREE(3-way) 77 → 131（+54），**DIVERGE=0**。

```
$ scons build/DADAO/gem5.opt -j6   # exit 0
$ for t in arith add jump; do ./build/DADAO/gem5.opt tests/dadao/dadao_se.py tests/dadao/smoke_$t.elf; done
smoke_arith → SIM_END: halt code=42
smoke_add   → SIM_END: halt code=42
smoke_jump  → SIM_END: halt code=0
```
3 smoke 42/42/0 不回归。

---

## Codex Review

**判决: APPROVE**（DG-004b 范围内；异常/fault 正确留 DG-004c）

独立重跑（reviewer 亲自执行，非引用完成区）：

1. **run_gem5_test 内存向量 PASS / FAIL=0**
   - `rd-load-store.yaml`: PASS=38 SKIP=11 **FAIL=0**。所有 semantic/boundary 内存
     load/store/multi 转 PASS；11 SKIP 逐条核对均为 expected_fault（ILLI/MALIGN），
     符合"fault 留 DG-004c"约束，无 semantic 向量被误 SKIP。
   - `rb-ops.yaml`: PASS=20 SKIP=8 **FAIL=0**（含 ldo-rb/sto-rb/ldmo-rb/stmo-rb/cmp-rb）。

2. **run_differential DIVERGE=0** — AGREE(3-way)=131（较基线 77 增长 54），**DIVERGE=0**，
   HARNESS=6（控制流单指令模型故意弃权，与本任务无关）。发现并修复了一处被本任务解锁
   暴露的既有 bug：cmp-rb（0x2D）原实现比较 RD 寄存器，spec §4.5 应比较 RB 48-bit —— 修正后
   该向量三方 AGREE。

3. **抽查 2-3 条语义确从 spec 派生 + big-endian**
   - `ldbs rd1,rb2,+8`（0x30042008）：EA=rb2[47:0]+8；读 1 字节 0x80 符号扩展→
     0xFFFFFFFFFFFFFF80。execute 用 `memReadBE` 逐字节大端组装再 `sextN`。✓ §3.1/§2.1
   - `sto rd1,rb2,+0`（0x3B042000）：mem_be[EA..EA+7]=rd1[63:0]，`memWriteBE` 按
     `b[i]=(val>>8*(7-i))&0xFF` 大端拆解。dump 读回 0xDEADBEEFCAFEBABE。✓ §3.2/§2.1
   - `ldmws rd1,rb2,rd0,2`（0x35042002）：EA_i=rb2+rd0+i×2；0x7F00→0x7F00、
     0x8000 符号扩展→0xFFFFFFFFFFFF8000。✓ §3.3
   均只依赖 spec §/opcodes.yaml；未见 translate.c 借用。

4. **gem5.opt build & smoke 不回归** — `scons build/DADAO/gem5.opt` exit 0；
   smoke_{arith,add,jump} = 42/42/0，与 G1 基线一致。AtomicSimpleCPU 切换 + 内存 dump
   （tryReadBlob 守卫）对无内存工作负载无副作用。

遗留/移交 DG-004c：ILLI（rdha/rbha=rd0/rb0、immu6=0、first+immu6>64）、MALIGN（非对齐
load/store）、UNDI —— 对应 expected_fault 向量当前 gem5-SKIP。
