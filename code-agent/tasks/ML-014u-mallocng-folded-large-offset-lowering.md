# ML-014u：隔离 mallocng 末端访问的大偏移折叠 lowering

**执行环境**：本地 subagent worker；承接 ML-014s/t

**状态**：Accepted（2026-07-18）

## 目标

解释为什么真实 `malloc_rw_after` 的 `p[131051]` 最终形成
`stb/ldbu ..., -21`，而 ML-014t 将同一数学偏移先物化为完整 RD 加法后双后端
通过。任务只建立 source → LLVM IR → SelectionDAG/MIR（能取得多少记录多少）→
ELF 的差异链，确定是否是 DADAO load/store 地址折叠的立即数合法性判断或其他
具体 lowering 环节；不直接修改实现。

## Locked inputs 与 Ownership

- 使用当前主线、ML-014m 真实 mallocng-linked source/ELF 与 ML-014t probe。
- worker 只可新增本任务 `.work/ML-014u-mallocng-folded-large-offset-lowering/`
  诊断产物，并完成本 task MD 的完成区；不得修改 LLVM/QEMU/gem5/musl、patch
  series、tests、docs/issues、contracts、manifests 或用户原始 ML-014a。
- 外部架构资料不在 worker scope；只使用本仓库和合同锁定产物。
- 其他 agent 可能同时工作；不得回滚、覆盖或整理他人的改动。

## 执行阶梯

1. 精确固定 `malloc_rw_after.c`、ML-014t source、编译器、参数和链接产物身份。
2. 生成可审计的 IR、汇编/反汇编；如当前工具支持，保留关键 SelectionDAG/MIR
   或 `llc -stop-*` 产物。不可用时记录真实错误，不以猜测补齐。
3. 新增最小 source 变体，仅改变“偏移直接用于 load/store”与“先保存 q 再访问”
   的形态，确认触发条件；变体只放本任务 `.work`，不替代真实 mallocng 证据。
4. 定位最窄可疑实现函数/模式和立即数范围，给出下一实现任务的文件、测试与
   非目标边界。
5. 记录命令、退出码、证据层级、未验证项和 worker 自审，等待独立 reviewer。

## 验收

- 真实路径和最小变体都具有 source/IR/ELF 证据；明确 `131051 -> -21` 在哪一层
  首次出现，或严格说明尚缺哪一层。
- 结论足以决定是否开启一个有最小回归测试的 LLVM 专项修复任务。
- 无实现、patch series、测试主线、issues 或 ML-014a 变更；不得宣称 mallocng、
  ML-014f 或 ML-014a 完成。

## 完成区

### Finding：DADAO DAG selector 将越界 GEP 常量折叠进 signed-12 load/store；等待独立复核

本任务只收口既有诊断证据，不修改实现。直接访问形态在 LLVM IR 和进入
instruction selection 的 DAG 中仍保留完整 `131051`；DADAO
`DADAODAGToDAGISel::Select` 随后把它选成 `STB_RRII/LDBU_RRII` 的立即数操作数，
但该操作数的指令定义是 signed 12-bit。AsmPrinter 仍打印 `131051`，MC 编码后
只留下低 12 位 `0xfeb`，ELF/对象反汇编才首次显示为 `-21`。因此：

- **非法地址折叠首次可直接观察于 selected DAG/finalize-isel MIR**；
- **`131051 -> -21` 的数值截断首次可直接观察于 MC 编码后的对象/ELF
  反汇编**，不在 C、LLVM IR、pre-isel DAG、finalize-isel MIR 或文本汇编层；
- 根因边界是 LLVM DADAO load/store address selection 缺少 signed-12 合法性
  判断，不是 mallocng、linker 或 QEMU/gem5 的一般 EA/backing。

#### 1. Locked identity 与命令退出码

诊断命令固定在
`.work/ML-014u-mallocng-folded-large-offset-lowering/run_diagnostics.sh`，使用：

```text
clang/llc flags: --target=dadao -std=c99 -nostdinc -ffreestanding -O0
llc layers: -stop-after=finalize-isel, -debug-only=isel, -filetype=asm
link: ld.lld -T tests/scripts/dadao.ld --start-group crt1.o object libc.a --end-group
```

`toolchain.txt` 记录 clang/LLVM `22.1.8`、assertions build，编译器 version string
含 upstream `4d932e49ac641b7886389a72cb50d0a45eadedfa`；被读取的 LLVM source tree
为 detached clean HEAD `92dd91c67c08f6b680d11c7b713f87c496cd5d94`。两项身份分开记录，
不把 version string 与 source-tree HEAD 冒充为同一 hash。

`inputs.sha256` 与 `cmp` 直接确认：

- 真实 source SHA-256：
  `da16d2c82a2fa4d2aed8d00732f5e89c6e8f67b5706f7c01102bf2c4a2a0d1cc`；
- 真实 locked/rebuilt object 均为
  `257eab02d1dd91477746e5f392029c41b1bda4b2e403aef667c09abed98672f5`；
- ML-014t source SHA-256：
  `42f21b60fb0b4ca2c964171ac66a120239f249134aada9dd93eb2154e272ac5e`；
- ML-014t locked/rebuilt object 均为
  `31952a76da73402a9cc9af964abd820f1315fad36a73353b0d0ec6ae7fa8f57f`。

`run.log` 保存的真实退出码为：

| 命令组 | 退出码 |
|---|---:|
| 真实 source 的 IR/MIR/isel log/asm/object 生成 | `compile_real=0` |
| rebuilt object 与 locked real object 比较 | `cmp_real_locked_object=0` |
| ML-014t 的 IR/MIR/isel log/asm/object 生成 | `compile_ml014t=0` |
| rebuilt object 与 locked ML-014t object 比较 | `cmp_ml014t_locked_object=0` |
| `minimal_direct` 编译、链接、反汇编 | `compile_link_minimal_direct=0` |
| `minimal_saved_q` 编译、链接、反汇编 | `compile_link_minimal_saved_q=0` |
| 两条越界 load/store 的 `llvm-mc` encoding/object/disassembly | `llvm_mc_large_imm=0` |
| driver 全部诊断完成 | `all_diagnostics=0` |

driver 使用 `set -euo pipefail`；因此到达末尾也证明脚本内的 clang、llc、ld.lld、
llvm-objdump、sha256sum、version/git 查询均未非零退出。限制是 `run.log` 只保存
上述命令组退出码，没有为每个组内子命令单独保存 sidecar exit code；本完成区不
伪造更细粒度的退出码。

#### 2. source → IR → selected DAG/MIR → asm → ELF 直接证据

证据摘录集中在 `layer_focus.txt`，以下均可回到同目录原始 `.ll`、
`.isel.stderr`、`.finalize-isel.mir`、`.s` 和反汇编逐项核对。

| 路径 | IR / selected DAG | finalize-isel MIR / asm | 编码后反汇编 |
|---|---|---|---|
| 真实 `malloc_rw_after` | 两个末端 GEP 均为 `i64 131051`；pre-isel 是 `add ... Constant<131051>`，selected DAG 变为 `STB_RRII/LDBU_RRII ... TargetConstant<131051>` | `STB_RRII ... 131051`、`LDBU_RRII ... 131051`；AsmPrinter 仍打印 `131051` | locked ELF `0x80000160 stb ... -21`、`0x80000190 ldbu ... -21` |
| `minimal_direct` | store/load 直接使用两个 GEP `131051`，并同样选成 RRII `131051` | MIR 与 asm 同样保留 RRII `131051` | ELF `0x8000012c stb ... -21`、`0x80000138 ldbu ... -21` |
| `minimal_saved_q` | 只在形成并保存 `q` 时做 GEP `131051`；后续 store/load 的 GEP 为 0 | `%2 = CONST_WYDE 131051`、`%3 = ADD_PSEUDO base, %2`；asm 为 `setzw 65515; orw 1,1; add`，store/load 偏移均为 0 | ELF 保留完整加法，随后 `stb/ldbu ..., 0`，没有该路径的 `-21` |
| locked ML-014t probe | `q=p+131051` 先保存，实际 byte store/load 使用 `q` | `CONST_WYDE 131051 + ADD_PSEUDO`；asm 为完整 `0x1ffeb` 加法，内存偏移 0 | locked ELF `0x8000018c..0x80000194` 构造/相加完整 `131051`，`0x800001c8/0x800001d4` 用偏移 0 |

这组只改变地址值是否在 load/store 前单独保存的最小对照复现了真实差异，排除
mallocng 是触发该 codegen 形态所必需的条件。它没有运行 allocator，也不把
最小 ELF 的成功链接写成运行成功。

额外的直接 MC round-trip 输入：

```text
stb  rd16, rb8, 131051 -> [0x38,0x40,0x8f,0xeb] -> stb  rd16, rb8, -21
ldbu rd16, rb8, 131051 -> [0x40,0x40,0x8f,0xeb] -> ldbu rd16, rb8, -21
```

其退出码为 0，stderr 为空。这直接证明当前 MC 路径没有拒绝越界 signed-12
立即数，并把低 12 位写入编码；它不是用 simulator 行为反推的结论。

#### 3. 后端实现证据与证据层级

| 层级 | 内容 | 可支持的结论 |
|---|---|---|
| **L1：直接产物/命令结果** | locked 与 rebuilt object 相同；真实/最小 IR、isel log、MIR、asm、ELF；直接 MC encoding/disassembly；`run.log` 退出码 | 直接访问在 isel 被折叠为 RRII `131051`，编码后为 `-21`；saved-q/ML-014t 走完整加法 |
| **L1：直接源码检查** | `backend_evidence.txt`：`DADAODAGToDAGISel::Select` 取任意 `ADD + Constant` 为 `GEPOff`，非 FI/PCREL 路径无范围检查就创建 RRII；TableGen 将相关 load/store operand 定义为 `imms12`；generated emitter 对该 operand 执行 `op & 0xfff` | selector 允许越界值进入 signed-12 指令，emitter 只保留 12 位 |
| **L2：由 L1 唯一确定的算术解释** | `131051 = 0x1ffeb`，`0x1ffeb & 0xfff = 0xfeb`，12-bit sign extension 为 `-21` | 解释 encoding/disassembly 的数值关系；不是额外运行观测 |
| **未验证/不得宣称** | 未修改 LLVM，未运行新实验、QEMU/gem5、mallocng E2E、优化级别矩阵或全量测试 | 不宣称修复已实现，不宣称 allocator、ML-014f 或 ML-014a 完成 |

源码中的关键不对称是：通用 constant selection 已对 `[-2048, 2047]` 使用
`ADDI_RRII`、越界值使用 `CONST_WYDE`，PC-relative 分支也显式检查同一范围；
但本次命中的 non-FrameIndex、non-PCREL load/store 分支把 `GEPOff` 无条件传给
`STB_RRII/LDBU_RRII`。这与四条产物链一致，足以收口到具体 selector 分支。

#### 4. 最窄 LLVM 修复边界

下一实现任务的最窄语义边界是：

- 文件：`llvm/lib/Target/DADAO/DADAOISelDAGToDAG.cpp`；
- 函数：`DADAODAGToDAGISel::Select`；
- 分支：non-FrameIndex、non-`DADAOISD::PCREL_HI` 的 load/store address fold；
- 行为：仅当常量满足 signed-12（`[-2048, 2047]`）时拆出 `GEPOff` 并选择
  `*_RRII`；越界时保留完整 `ISD::ADD` 地址，让已有 large-constant
  `CONST_WYDE` + `ADD_PSEUDO` 路径物化地址，再以立即数 0 访问。该规则应覆盖
  load/store 的 i8/i16/i32/i64 opcode 选择，而不是只特判本例 `STB/LDBU`。
- 最小回归测试：在 `llvm/test/CodeGen/DADAO/` 增加直接 GEP load/store checks，
  至少覆盖 `131051` 以及边界 `-2048/2047`、越界 `-2049/2048`；检查越界值
  形成完整地址加法且最终内存立即数为 0，边界内值仍可折叠。测试不需要 musl、
  malloc、linker 或 simulator。

当前 `llvm-mc` 接受 `imms12` 越界常量且 emitter 静默 mask 是另一项有直接证据
的 LLVM MC 防线缺口。它值得单独增加 `llvm/test/MC/DADAO/` negative diagnostic
并定位 operand predicate/matcher，但**不是修复 compiler-generated folded GEP
语义所必需的最窄边界**；不能用只修 MC parser 代替上述 selector 修复。

明确非目标：不改 DADAO ISA 的 signed-12 定义，不改通用常量物化、register
allocation、AsmPrinter、linker、musl mallocng、QEMU/gem5，也不扩展到 `-O X`、
pointer ABI、puts/free/varargs、全量 E2E、ML-014f 或 ML-014a。

#### 5. 未验证项与 worker 自审

- 本任务没有实现修复，因此尚无修复后 MIR/asm/ELF，也没有修复后 CodeGen/MC
  test 退出码；这些属于下一实现任务，不能由当前诊断产物代替。
- 没有新增或重跑实验；本次只读取 task contract 与既有 `run.log`、
  `backend_evidence.txt`、`layer_focus.txt`、原始 IR/MIR/asm/反汇编及 backend
  source，并更新本任务记录。
- 没有修改 LLVM/QEMU/gem5/musl、patch series、tests、docs/issues、contracts、
  manifests、其他 task 或用户原始 ML-014a；不宣称 mallocng、ML-014f、
  ML-014a 完成。
- 自审结论：现有直接证据足以开启上述最窄 LLVM CodeGen 修复任务；本任务为
  **Completed awaiting independent review**，必须由不同 reviewer 复核后才可
  接受。

## 审阅记录

- **Accepted（2026-07-18，独立 review）**：只读核对既有产物与 selector 源码；IR
  保留 `131051`，finalize-isel 为 `STB_RRII/LDBU_RRII ... 131051`，编码后
  `0xfeb` 反汇编为 `-21`，且 non-FI/non-PCREL load/store fold 确实缺少
  signed-12 范围检查。结论与完成区一致。
