# ML-029a 独立审查（2026-07-24）

## 判决

**Accepted。无 blocking finding。**

审查对象为最终 LLVM HEAD `032fab81c9bf`：

- 主体提交：`245d4f42a5d8`（large frame offset materialization）；
- spill-safe follow-up：`032fab81c9bf`；
- 根仓 patch：`0051-DADAO-materialize-large-frame-offsets.patch`、
  `0052-DADAO-make-frame-offset-scavenging-spill-safe.patch`。

本审查没有修改实现、测试、task、issue、patch、series 或 wiki；仓库内唯一新增文件
即本报告。运行产物均放在 `/tmp/ml029a-review-*`。

## Findings

### Blocking / Major / Minor

无。

### Informational

1. 精确 `2047/2048/-2048/-2049` 的边界锁定集中在 `LDO_FI` MIR；五种实际
   frame-index pseudo、prologue/epilogue、正负大偏移则在同一 MIR/IR 的其它
   case 分别覆盖，而不是对五种 pseudo 做边界值的笛卡尔积。结合代码对五个 case
   使用同一 `isInt<12>(Total)` 分支，这足以支持本任务验收，不构成修复缺口。
2. 仓库外临时镜像首次全 E2E 因遗漏相对路径 `.work` 链接出现 11 个
   “file not found”；补上只读链接后 73/73 PASS。临时 replay source 直接运行
   `llvm-lit` 也因没有 build-tree site config 而 rc=2；因此 LLVM 五个文件随后按
   其全部六条 `RUN` 命令直接执行。两次失败都属于审查沙箱搭建问题，未作为实现
   测试失败掩盖。

## 静态审查

### Prologue / epilogue

- `DADAOFrameLowering.cpp:93-109`、`:123-138` 在 signed imms12 范围内保留原
  `ADDI_RBRRII` 单指令路径；范围外使用 RD2 物化带符号调整量，再执行
  `ADDRB_ORRR rb1, rb1, rd2`。
- `-2048` 可直接编码，`+2047` 可直接编码；大 frame 的向下调整必然进入负数
  物化路径，向上恢复进入正数物化路径。最终 MIR/汇编均观察到对称调整。
- RD2 在当前 ABI 中固定 non-allocatable，参数从 RD16 开始，当前 scalar/≤64-bit
  aggregate 返回在 RD31；因此该 scratch 不覆盖已实现的参数或返回值路径。
- 小帧 IR 回归仍输出 `addi rb1, rb1, -8/+8`，没有无条件退化为多指令路径。

### `materializeImm64`

- `DADAOInstrInfo.cpp:56-80` 先把 `int64_t` 按位转换为 `uint64_t`，以第一个
  非零 16-bit wyde 执行 `SETZW`，其余非零 wyde 执行 `ORW`。因此任意非零正、
  负 64-bit 位型均被精确重构；负数的高位 `0xffff` 不会丢失。
- `CONST_WYDE=0` 在 `DADAOInstrInfo.cpp:172-178` 仍不发出指令并删除 pseudo，
  与修改前行为相同。
- frame 大偏移调用点不会传入 0；helper 对 0 的 assertion 与调用约束一致。

### Frame-index elimination

- 实际 switch 是五种 pseudo：
  `ADDI_RB_FI`、`LDO_FI`、`STO_FI`、`LDO_RB_FI`、`STO_RB_FI`。任务早期“六个”
  是计数笔误，完成区已更正。
- 四种访存先计算最终 `FrameOff + GEPOff`，地址 pseudo 使用最终 `FrameOff`；
  signed imms12 范围内保留原基址和立即数，范围外统一物化完整 offset。
- 大偏移访存以新 RB 地址和 imm=0 发出，且通过 `setMemRefs(MI.memoperands())`
  保留原 memory operands。RD/RB load/store opcode 没有串 bank。
- `ADDI_RB_FI` 直接把目标 RB 作为地址结果，不需要额外 RB scratch。

### RegScavenger / emergency slot

- `requiresRegisterScavenging()` 返回 true；大偏移通过
  `scavengeRegisterBackwards(GPRD_AllocatableRegClass, II,
  RestoreAfter=false, SPAdj)` 在原指令位置之前取得临时 RD。
- `processFunctionBeforeFrameFinalized` 不只依据 frame estimate：它扫描五种 FI
  pseudo，并覆盖：
  - 大 frame；
  - small frame + large GEP；
  - large fixed-object offset；
  - fixed/local 对象最终 offset 越界。
- emergency slot 是 8-byte spill object。最终强制压力 MIR 中它位于 final SP
  offset 0，实际序列为：
  `STO_RRII spill @ rb1+0` → 物化 → 原 RB store → `LDO_RRII reload @ rb1+0`。
  spill/reload 自身保持 imms12 小偏移，没有递归进入大地址物化。
- RD8..RD63 全 live 的 MIR 确实强制发生 spill/reload，不是仅检查“存在一个
  空闲 RD”的弱测试。

### RB5 / RB6

- RB5、RB6 都是 ABI-reserved、non-allocatable，正常 register allocation
  不会把一般值分配给它们。
- 大偏移 RD/RB 访存默认用 RB5 作为瞬时地址；当显式 MIR 的 RB value
  source/destination 是 RB5 时改用 RB6。
- `large_fixed_offset_rb5` 的最终 MIR 实际为
  `rb6 = ADDRB_ORRR ...` 后 `STO_RBRRII rb5, rb6, 0`，以及
  `rb5 = LDO_RBRRII rb6, 0`，没有提前覆盖显式 RB5 值。

### 测试与 scope

- LLVM MIR 集合共同覆盖精确 `2047/2048/-2048/-2049`、五种实际 pseudo、
  prologue/epilogue、正负大 offset、small-frame + large-GEP、large fixed
  offset、RD 全活 spill，以及 RB5/RB6 冲突。
- `frame_offset_large.c` 的数组和 pointer 数组均为 volatile；正例校验 800 项
  checksum 与多个远近 pointer，negative-control 只翻转 expected checksum
  一位。QEMU/gem5 正例都必须 exit 42，负控制都必须 exit 1。
- 最终 `-O0 -S` 实际观察到大 frame 物化：
  prologue `setzw rd2,0,58728`（完整负数还含高 wyde）+
  `add rb1,rb1,rd2`，epilogue `setzw rd2,0,6808`+
  `add rb1,rb1,rd2`；远 offset 访问也出现 `add rb5,rb1,rdN` 后 imm=0 访存。
- issue 只关闭
  `frame-offset-no-imms12-range-check-silent-wraparound`；任务完成区明确不宣称
  覆盖非-frame imms12 生产者，归档文案也限定为 frame adjustment/FI 路径。

## 独立验证

### 工具链与提交

| 命令 | rc | 结果 |
|---|---:|---|
| `.work/build/llvm/bin/clang --version` | 0 | revision `032fab81c9bf`，assertions build |
| `.work/build/llvm/bin/llc --version` | 0 | DADAO target registered |
| `git merge-base --is-ancestor 3aa546d1d0cd 245d4f42a5d8` | 0 | 主体是普通后继提交 |
| `git merge-base --is-ancestor 245d4f42a5d8 032fab81c9bf` | 0 | 0052 是普通 follow-up |
| `git rev-list --count 3aa546d1d0cd..032fab81c9bf` | 0 | 结果 2 |
| 两提交与 0051/0052 分别执行 `git patch-id --stable` | 0 | `68bf36ca...`、`f860d4ad...` 分别一致 |

### LLVM CodeGen

由于唯一可写文件约束，LLVM 测试使用仓库外 replay tree，或直接把各文件的全部
`RUN` 管道输出到 stdout，不写源树。

| 命令 | rc | 结果 |
|---|---:|---|
| `llc -mtriple=dadao-unknown-elf -O0 < large-frame-offsets.ll \| FileCheck large-frame-offsets.ll` | 0 | PASS |
| `llc -mtriple=dadao-unknown-elf -run-pass=prologepilog -verify-machineinstrs large-frame-offsets.mir -o - \| FileCheck large-frame-offsets.mir` | 0 | PASS |
| `llc -mtriple=dadao < load-store-offset-range.ll \| FileCheck load-store-offset-range.ll` | 0 | PASS |
| `llc -mtriple=dadao < varargs-save-area.ll \| FileCheck varargs-save-area.ll` | 0 | PASS |
| `llc -mtriple=dadao-unknown-elf -O0 < frame-lowering-stack-alignment.ll \| FileCheck ...` | 0 | PASS |
| `llc -mtriple=dadao-unknown-elf -O0 -stop-after=prologepilog < frame-lowering-stack-alignment.ll \| FileCheck --check-prefix=MIR ...` | 0 | PASS |

汇总：定向新增测试 **2/2 PASS**；DADAO CodeGen 文件 **5/5 PASS**
（六条 RUN 管道 6/6 PASS，FAIL=0）。

补充记录：直接对临时 source clone 执行两次 `llvm-lit -sv` 均 rc=2，
原因是 source-only `lit.cfg.py` 缺 build site config 的
`config.enable_profcheck`；没有把这个配置失败计作 CodeGen PASS。

### E2E

| 命令 | rc | PASS/FAIL/XFAIL/SKIP |
|---|---:|---|
| `llvm-lit -sv <tmp>/tests/lit/E2E/frame_offset_large.test` | 0 | PASS=1, FAIL=0, XFAIL=0, SKIP=0 |
| `llvm-lit -sv <tmp>/tests/lit/E2E`（第一次镜像） | 1 | PASS=62, FAIL=11；11 项均因临时镜像缺 `.work` 相对依赖 |
| 补只读 `.work` 链接后同命令重跑 | 0 | **PASS=73, FAIL=0, XFAIL=0, SKIP=0** |

新增 E2E 的单项 PASS 包含四个实际运行断言：QEMU/gem5 正例 exit 42，
QEMU/gem5 negative-control exit 1。

### `pr56866` 与 gcc-c-torture

为避免原脚本写仓内 `.work/gcc-torture-sweep`，在 `/tmp` 建立同结构 wrapper，
工具、语料和 musl/qemu 以只读 symlink 指向最终构件。

| 命令 | rc | 结果 |
|---|---:|---|
| `python3 <tmp>/gcc_torture_sweep.py --filter pr56866 --workers 1 --out <tmp>/pr56866.json` | 0 | PASS=1 / TOTAL=1 |
| `timeout 30 gem5.opt dadao_se.py <同一 pr56866 ELF>` | 0 | `SIM_END: trap-exit code=0` |
| `python3 <tmp>/gcc_torture_sweep.py --workers 8 --out <tmp>/full-final.json` | 0 | 1708 项，见下表 |

最终全量分布：

| 分类 | 落地前 baseline | 最终独立重跑 | 变化 |
|---|---:|---:|---:|
| PASS | 1409 | **1412** | +3 |
| FAIL_COMPILE | 113 | **113** | 0 |
| FAIL_LINK | 133 | **133** | 0 |
| FAIL_RUN | 52 | **50** | -2 |
| TIMEOUT | 1 | **0** | -1 |
| TOTAL | 1708 | **1708** | 0 |

只读对拍 `/tmp/ml029a-baseline-20260724.json`：

- 旧 PASS → 非 PASS：**0**；
- `memcpy-1.c`：FAIL_RUN → PASS；
- `pr28982b.c`：FAIL_RUN → PASS；
- `pr56866.c`：TIMEOUT → PASS；
- 与实现者最终 JSON 的逐文件 status mismatch：**0**。

### Differential 与仓库门禁

| 命令 | rc | 结果 |
|---|---:|---|
| `python3 tools/run_differential.py` | 0 | AGREE(3-way)=200，gem5-SKIP=2，DIVERGE=0；AGREE(4-way)=200，Sail-SKIP=2，SAIL-DIVERGE=0 |
| `python3 scripts/manifest_check.py` | 0 | PASS |
| `python3 scripts/check_issues.py` | 0 | Open=21, Closed=38, Total=59，PASS |
| `python3 scripts/check_codegen_abi.py` | 0 | MATCH=23, OPEN-COMMIT=3, MISMATCH=0，PASS |
| `python3 scripts/check_lit_bytes.py` | 0 | 69 patterns OK |
| `git diff --check` | 0 | 无 whitespace error |

### 52/52 干净 replay

在新的 `/tmp/ml029a-review-replay.*` local clone 中：

1. `git checkout --detach ca7933e47d3a3451d81e72ac174dcb5aa28b59d1`：rc=0；
2. 按 `components/llvm/patches/series` 顺序逐条执行 plain
   `git am <patch>`：**52/52 rc=0**；
3. `git rev-parse HEAD~52`：
   `ca7933e47d3a3451d81e72ac174dcb5aa28b59d1`；
4. `git rev-list --count <pin>..HEAD`：52；
5. replay tree：
   `09a9fe311ef08133a65a6435de26003768d6bb8c`；
6. LLVM `032fab81c9bf^{tree}`：
   `09a9fe311ef08133a65a6435de26003768d6bb8c`。

最终 tree 完全一致，0051/0052 的顺序、内容和普通提交 provenance 均成立。

## 最终意见

实现对 ML-027a 已定位的 frame adjustment/frame-index signed-imms12 静默环绕
形成了完整闭环：小偏移不变，大偏移正确物化，PEI 临时寄存器在无空闲 RD 时可安全
spill/reload，RB5/RB6 冲突有显式回归，真实大帧在 QEMU+gem5 上有判别性正例和
负控制。全量 torture 没有旧 PASS 退化，`pr56866` 及另外两个失败项转正，52/52
replay 与最终 LLVM tree 一致。

**独立 reviewer 判决：Accepted。**
