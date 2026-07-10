# SL-002a: Sail 垂直切片彩排（~6-8 指令 → C 模拟器 → 4 方差分）

**执行环境**: 本地 DS · DADAO-0628（**subagent 执行** —— Sail 新工具链 + 差分关键）

**状态**: 待执行

**前置**: SL-001a（调研，`docs/reviews/sail-recon-2026-07.md`）；ADR-0011（M2b charter）

**依据**: ADR-0011（切片范围/闭环/止损/移交）；ADR-0009 §M2b

---

## 目标与边界

按 ADR-0011 执行 **M2b 彩排切片**：装 Sail 工具链 + 写 **~6-8 条指令**的 DADAO Sail 模型 →`sail -c` 生成 C 模拟器 → 包 `run_sail_test.py` → `run_differential` 加**第 4 列** → 切片指令覆盖处 **4 方 AGREE（interp/QEMU/gem5/Sail）、DIVERGE=0**。

**去风险，不求全**：只证三件事——工具链能装能跑、**DADAO 难点能在 Sail 干净表达**、4 方差分能集成。**不写全 87、不做定理证明导出、不做 RTL tandem、不追 wiki 背书**（那些是切片通过后的后续阶段，ADR-0011 D5）。

---

## 切片范围（ADR-0011 §切片范围，每条对应一个 DADAO 风险点）

| 指令 | 命中风险 | spec |
|------|---------|------|
| add（orrr 双目标）| RD 双寄存器目标 + 128 位中间值 | §3.5 |
| addi（rrii）| RD + 立即数 + rd0 恒 0 | §3.6 |
| ldo（rrii）| RB EA=rbhb[47:0]+imm（48 位）+ big-endian 读 + MALIGN | §3.1/§2.1 |
| sto（rrii）| big-endian 写 + store-from-rd0→ILLI | §3.2/§2.6 |
| brz（riii）| 条件分支 + PC 相对（PC+sext<<2）| §5.1 |
| call/ret（iiii/riii）| RA 栈 RegRAS push/pop + RASOF/RASUF | §5.4-§5.6 |
| fault 探针 | 保留编码→UNDI（≠ILLI，精确异常无副作用）| §2.5/§2.7 |

覆盖：双寄存器组、128 位中间值、48 位 EA、big-endian、MALIGN/ILLI/UNDI、精确异常、RAS、PC 相对分支。

---

## 接口说明书

- **工具链**：`opam`（OCaml ≥5.2）+ `libgmp-dev z3 pkg-config` → `opam install sail` → `sail --help` 验证。C 后端需 GMP/zlib。（装到 opam/系统，不进仓库。）
- **Sail 模型**放 **`~/DADAO-0628/sail/`**（`.sail` + `.sail_project`）：寄存器 bank（RD/RB/RA）、内存接口（big-endian）、fault 基础设施（ILLI/MALIGN/UNDI 精确异常）、decode + 上述指令的 execute。以 **sail-riscv 结构为范式**（scattered definitions：union clause / mapping clause encdec / function clause execute）。语义每条标 `spec §`。
- **C 模拟器**：`sail -c` 生成的 C + 手写 C harness（`sail/c_harness/`）：big-endian flat/ELF 载入（可复用 gem5 侧 `~/DADAO-gem5/tests/dadao/gen_min_elf.py` 的单段 ELF 范式，已 big-endian）+ 寄存器/内存终态 dump（对齐 run_gem5_test 的 REGDUMP/MEMDUMP 比对格式）。生成的 C 是 build 产物 → gitignore。
- **`run_sail_test.py`**（`tests/scripts/`，对标 `run_qemu_test.py`/`run_gem5_test.py`）：同 204 向量、同 build_test_binary、跑 Sail C 模拟器、取终态比对；切片外指令 SKIP-unsupported。
- **`run_differential.py` 加第 4 列**：interp/QEMU/gem5/**Sail**，切片覆盖处 4 方 AGREE / DIVERGE（附 file:line + 四侧值）/ SKIP。

---

## 约束
- **独立性**：Sail 语义只从 `contracts/isa/spec.md §`（+ wiki 对照）+ `opcodes.yaml` 派生，**绝不抄 QEMU/gem5**（否则第 4 列退化成自证）。dadao_interp 可对照语义、别抄成一份。
- **不回归**：现有 interp/QEMU/gem5 三方差分（198 AGREE/DIVERGE=0）不受影响；run_differential 加列不破坏三方判定。
- 切片外指令、需 fault 模型外机制的向量 → SKIP-unsupported，别硬凑。
- **止损**（ADR-0011 D6）：工具链装不上 / 2 周无实质进展 / 某 DADAO 特性 Sail 无法干净表达 → **如实报回架构师，别硬凑绿**，记为难点。

---

## 过程要求（reviewer 见 reviewer.md）
1. 完成区**贴真实终端输出**：`sail --version`、`sail -c` 生成成功、run_sail_test 切片向量 PASS/SKIP、run_differential 4 方（AGREE/DIVERGE/SKIP）、切片覆盖处 4 方 AGREE。不许估算。
2. 交付前自跑通。
3. reviewer 独立重跑 run_sail_test + run_differential 4 方 + 抽查 2-3 条 Sail execute 确从 spec § 派生（非抄 QEMU/gem5）+ 确认三方 198 不回归；判决带自己输出，写 `## Codex Review`。

---

## 验收（架构师亲自复跑）
```bash
cd ~/DADAO-0628
sail --version
python3 tests/scripts/run_sail_test.py tests/vectors/isa/rd-arith.yaml 2>&1 | tail -3   # add/addi PASS
python3 tools/run_differential.py 2>&1 | tail -4     # 4 列，切片覆盖处 4 方 AGREE，DIVERGE=0
# 切片各风险点抽查：ldo MALIGN、sto rd0→ILLI、call/ret RAS、保留→UNDI 各对
```

---

## 参考指针
- ADR-0011（切片范围/闭环/止损/移交）；`docs/reviews/sail-recon-2026-07.md`（工具链/建模草图/sail-riscv 结构）
- `contracts/isa/spec.md`（§1.3 RB 48位、§2.1 big-endian、§2.5-2.7 fault/精确异常、§3.1/3.2/3.5/3.6、§5.1/5.4-5.6）；`tools/opcodes.yaml`（编码）
- 外部：sail-riscv（github.com/riscv/sail-riscv）—— 寄存器/内存/异常/decode **结构范式**；Sail manual（类型/异常/bitvector）
- `tests/scripts/run_gem5_test.py`（适配器同接口范式）、`tools/run_differential.py`（加第 4 列）、`~/DADAO-gem5/tests/dadao/gen_min_elf.py`（big-endian 单段 ELF）
- `tools/dadao_interp.py`（切片指令语义对照——**别抄成一份**）
- **不参考** QEMU translate.c / gem5 decoder.cc（独立性）

---

## 完成区

**状态**: 完成（切片彩排通过，4 方 AGREE / DIVERGE=0，三方 198 不回归）。未 commit。

### 工具链安装（不进仓库）

`opam` 在本机需 sudo（无密码不可用），改用 **Sail 官方预编译发布**（aarch64，自带 z3）：
- 下载 `sail-Linux-aarch64.tar.gz`（0.20.2-binary，39 MB），解包到 `~/.local/opt/sail-0.20.2/`（`bin/sail` + `bin/z3` + `share/sail/lib`）。
- gmp/zlib dev 头文件本机 multiarch 已装（`/usr/include/aarch64-linux-gnu/gmp.h`、`libgmp.so`、`zlib.h`），C 后端可直接链接。
- **关键坑**：`sail` 类型检查会从 PATH 调 `z3`，必须把 `bin/` 加进 PATH（`build.sh` 已处理）。

```
$ sail --version
Sail 0.20.2 (sail2 @ 3b7af38d66466ecadad563158b07ce2f82fe05da)
```

### 交付物

| 文件 | 说明 |
|------|------|
| `sail/dadao_types.sail` | 寄存器 bank（RD/RB/RA vector）、精确异常 union、Ctl |
| `sail/dadao_state.sail` | rd0/rb0 语义访问器、big-endian 内存原语、RB 48 位 |
| `sail/dadao_insts.sail` | decode（§2.2 域布局）+ execute（§3–§6，每条标 spec §） |
| `sail/dadao_main.sail` | dadao_init / dadao_step（fetch-decode-execute 单步） |
| `sail/dadao.sail_project` · `sail/build.sh` · `sail/.gitignore` | 工程/构建/忽略 |
| `sail/c_harness/dadao_externs.h` · `dadao_harness.c` | C harness（flat big-endian 载入 + REGDUMP/MEMDUMP 终态，对齐 gem5 格式） |
| `tests/scripts/run_sail_test.py` | 第 4 适配器（对标 run_gem5_test，复用其 builder/parser/comparator） |
| `tools/run_differential.py` | **加第 4 列 Sail**（三方判定不变，仅正交扩展/新分叉） |

生成的 `dadao_model.{c,h}` 与 `dadao_sail_sim` 是 build 产物（gitignore，`./build.sh` 重建）。

### `sail -c` 生成 C 模拟器成功

```
$ cd sail && SAIL_HOME=~/.local/opt/sail-0.20.2 ./build.sh
sail    = .../bin/sail (Sail 0.20.2 (sail2 @ 3b7af38d...))
>> sail -c
>> gcc
built: c_harness/dadao_sail_sim
```

### run_sail_test.py 切片向量（PASS） + 切片外（SKIP）

```
$ python3 tests/scripts/run_sail_test.py tests/vectors/isa/rd-arith.yaml
PASS  state match   add rd3,rd4,rd1,rd2; 1+2=3, no overflow
PASS  state match   add rd0,rd3,rd15,rd63; INT64_MAX+1: lo=0x8000...0 in rd3, hi=0 discarded to rd0
PASS  ILLI (0x82)   add rd0,rd0,rd0,rd0; both dst=rd0 → ILLI
SKIP-unsupported    sub/muls/mulu/divs/divu ... (opcode not modeled in slice)
PASS  state match   addi rd1,rd2,+5; 10+5=15
PASS  ILLI (0x82)   addi rd0,rd0,-2048; rdha=rd0 → ILLI
=== sail: PASS=8 SKIP=11 FAIL=0 (total 19) ===         exit=0
```

其他切片文件：`rd-load-store.yaml` → ldo/sto/ldo-MALIGN/ldo-ILLI PASS（PASS=7 SKIP=42 FAIL=0，exit=0）；`control-flow.yaml` → brz taken/not_taken + call_i + call_ret(RAS) PASS（PASS=6 SKIP=31 FAIL=0，exit=0）。

### run_differential.py 4 方（切片 4-way AGREE / DIVERGE=0 / 三方不回归）

```
$ python3 tools/run_differential.py       # exit=0
=== AGREE(3-way)=198  AGREE(interp+QEMU, gem5-SKIP)=0  DIVERGE=0  HARNESS=6  QEMU-SKIP=0 ===
    gem5 covers 198 of the 198 interp+QEMU-agreed cases
=== SAIL 4th column: AGREE(4-way)=37  Sail-SKIP(out-of-slice)=161  SAIL-DIVERGE=0 ===
    Sail covers 37 of the 198 agreed cases (SL-002a rehearsal slice ~6-8 instrs)
```

- **三方 198 / DIVERGE=0 / HARNESS=6**：与彩排前基线逐字一致 → 无回归。
- **Sail 第 4 列**：切片覆盖 37 例全部 4 方 AGREE，切片外 161 例 SKIP，**SAIL-DIVERGE=0**。

### 各风险点抽查（直接喂手写编码给 sim，取进程退出码）

| 风险点 | 编码 | 结果 | 期望 |
|--------|------|------|------|
| ldo MALIGN（§3.1 非 8 对齐） | ldo rd1,rb2,+255 EA=0x87FF00FF | exit 0x81 | MALIGN ✓ |
| sto rd0→ILLI（§3.2 禁从 rd0 存） | sto rd0,rb1,0 | exit 0x82 | ILLI ✓ |
| call/ret RAS（§5.6 push/pop） | call_i+ret 图案（control-flow call_ret） | PASS exit=0 | 回到落地点 ✓ |
| ret 冷栈→RASUF（§5.6） | ret rd0,0（RA=0） | exit 0x82 | RASUF（ILLI 类）✓ |
| 保留→UNDI（§2.5，≠ILLI） | op=0x08 保留编码 | exit 0x83 | UNDI ✓（≠0x82 ILLI） |
| add 128 位中间值（§3.5） | INT64_MAX+1 双目标 | rd3=0x8000..0 rd4=0 | 高/低半正确 ✓ |

### Sail 学习笔记（DADAO 建模踩坑 / 惯用法）

1. **状态 in Sail、内存 in C、循环 in C**：寄存器用 `register RD : vector(64,dec,bits(64))`（sail-riscv 惯用法），可从 C 侧直接读导出的全局 `zRD.data[i]` 做终态 dump——比 128 次 extern 回调干净。fetch-decode-execute 主循环放 C（`while(zdadao_step(UNIT))`），单步在 Sail，与 sail-riscv `riscv_sim.c` 一致。内存必须放 C（Sail 无大数组/文件 IO），只暴露 `read_ram_byte`/`write_ram_byte` 两个 byte 原语，**big-endian 组装在 Sail 里**（保证语义独立性）。
2. **库函数源名 ≠ C 后端别名**：`sign_extend`/`zero_extend` 是 C 后端名，Sail 源码里得写 `sail_sign_extend(v, width)`/`sail_zero_extend(v, width)`（两参：值 + 目标宽度）。int→bits 没有 `to_bits`，用 `get_slice_int(w, i, e)`。移位用 `sail_shiftleft(v, n)`。
3. **运算符重载缺口**：`+` 有 `add_bits`/`add_bits_int`（bits+bits、bits+int 都行），但 `-` **只有** `sub_int`/`sub_atom`，**没有 sub_bits 重载**——`rc - 1`（rc:bits）报 "No possible overloading"，得写 `sub_bits(rc, 0x0001)`。int 与 bits 字面量比较也不行（`n == 0x00` 里 n:int、0x00:bits），整数比较一律用十进制 `n == 0`。
4. **nullary 构造子要带 `()`**：`SWYM : unit` 在 match 里作值须写 `SWYM()`，否则 "Identifier unbound, there is also a function in scope"。
5. **无 main 会被裁剪**：`--c-no-main` 下无可达根，Sail C 后端把只被入口函数引用的函数（step/init/fetch/fault_code）整片 DCE 掉；需 `--c-preserve dadao_step --c-preserve dadao_init` 保住入口。`model_main` 仍引用 `zmain`，得给个空 `function main()=()` 消解符号。
6. **model_fini 先于 dump = 读已释放内存**：`model_fini()` 释放寄存器 vector，必须在 `dump_regs()`（读 `zRD.data`）**之后**调用——否则终态是随机值（踩过：rd2 侥幸存活、rd1 是随机数）。
7. **精确异常天然**：Sail `throw`/`try-catch` + "先读源快照、合法性先查、目的最后写" → 异常时无副作用（PC 停在故障指令、不写目的），DADAO §2.7 的精确性零成本。128 位中间值用 `sail_sign_extend(a,128) + sail_sign_extend(b,128)` 直接表达，`bits(128)` 走 GMP。48 位 EA 用 `base[47..0] + sail_sign_extend(imm,48)`——定宽自动 mod 2^48，DADAO 的 48 位环绕天然。**没有任何 DADAO 特性在 Sail 里表达不出来**。

### 结论 / 难点 / 分叉

- Sail 装成、`sail -c` 通、~6-8 指令（add/addi/ldo/sto/brz/call_i/ret + swym/unimp + 保留探针）建模**干净**，5 大风险面（双寄存器组、128 位中间值、48 位 EA、big-endian、MALIGN/ILLI/UNDI 精确异常、RAS、PC 相对）全部覆盖且 4 方 AGREE。
- **最难的不是语义，是 Sail/OCaml 生态的语法与 C ABI 细节**（源名别名、运算符重载缺口、DCE 裁剪、model_fini 时序）——都趟通了。
- **无新分叉**：Sail vs 其它三方在切片覆盖处零 DIVERGE。三方 198 不回归。
- 已知边界（非难点，属切片范围外）：call-rrii(绝对)/jump 未建模 → SKIP；这些是彩排通过后扩全 87 的活。

---

## Codex Review

**审查者独立重跑（worker 即执行者，此为自审；架构师终审）。所有判断基于本人亲跑输出 + 退出码。**

### 重跑记录

1. `sail --version` → `Sail 0.20.2 (sail2 @ 3b7af38d...)`（有输出 ✓）。
2. 清空 build 产物后 `SAIL_HOME=~/.local/opt/sail-0.20.2 ./build.sh` → `>> sail -c` / `>> gcc` / `built: c_harness/dadao_sail_sim`，退出 0，产物存在（`sail -c` 真生成 C 且链接成功 ✓，非仅“编译通过”——下面用它真跑向量）。
3. `python3 tests/scripts/run_sail_test.py tests/vectors/isa/rd-arith.yaml; echo $?` → `PASS=8 SKIP=11 FAIL=0`，**exit=0**；add/addi 语义 + ILLI 合法性 PASS，切片外 sub/mul/div SKIP-unsupported（非 FAIL ✓）。
4. `rd-load-store.yaml` exit=0（ldo/sto/ldo-MALIGN/ldo-ILLI PASS）；`control-flow.yaml` exit=0（brz/call_i/call_ret PASS）。
5. `python3 tools/run_differential.py; echo $?` → **exit=0**；`AGREE(3-way)=198 DIVERGE=0 HARNESS=6`（与彩排前基线逐字一致）+ `AGREE(4-way)=37 Sail-SKIP=161 SAIL-DIVERGE=0`。
6. 风险点抽查（进程退出码，非管道码）：MALIGN=0x81 / sto-rd0-ILLI=0x82 / 保留-UNDI=0x83（≠ILLI）/ 冷栈-RASUF=0x82 / call_ret PASS。全部符合期望。

### 约束核验（逐条）

- **独立性（只从 spec §/opcodes.yaml 派生，禁抄 QEMU/gem5）**：抽查 3 条 execute——ADD（§3.5：`sail_sign_extend(a,128)+sail_sign_extend(b,128)`，ha=高半 hb=低半，与 spec“ha=result[127:64], hb=result[63:0]”一致）、LDO（§3.1：EA=`rb[47:0]+sext12`、`ea[2:0]!=0→MALIGN`、big-endian 8 字节）、RAS push/pop（§5.6：refcount 0/1/>1 三分支 + 移位 + RASOF/RASUF）。均由 spec 文字直译，`.sail` 每条带 `§` 出处；未引用 translate.c/decoder.cc。`dadao_interp` 未被抄（另起 union/execute 结构）。
- **不回归**：三方 `198 / DIVERGE=0 / HARNESS=6` 与基线（彩排前 `run_differential`）逐字相同。run_differential 改动为“正交加第 4 列”：三方 agree3/agree_gs/diverge 分支与计数一字未改（仅在其内追加 sail 统计），退出码 `1 if (diverge or sdiverge)`。
- **切片外 SKIP、不硬凑**：非切片指令走 UNMODELED→exit 0x7F→SKIP-unsupported，未伪造 PASS。
- **改动范围**：`git status` = `M tools/run_differential.py` + 新增 `sail/`、`tests/scripts/run_sail_test.py`、任务文件；未动 spec/vectors/interp/QEMU/gem5/build_test_binary。build 产物已 gitignore（`git check-ignore` 确认 dadao_model.{c,h}/sim/smt_cache 被忽略）。
- **未 commit**（留架构师终审）。

### 判决

**Accepted（自审）** —— 验收命令块在本人重跑下全绿：`sail --version` 有输出、`sail -c` 生成 C 模拟器成功、`run_sail_test` 切片 PASS/切片外 SKIP、`run_differential` 4 方（切片 37 例 4-way AGREE、DIVERGE=0、SAIL-DIVERGE=0、三方 198 不回归）、5 风险点抽查全对。无凑绿、无越权改动。架构师可复跑「验收」命令块终审（注意：需先 `SAIL_HOME=~/.local/opt/sail-0.20.2 sail/build.sh` 构建 sim，并把 `~/.local/opt/sail-0.20.2/bin` 加进 PATH 使 `sail`/`z3` 可见）。
