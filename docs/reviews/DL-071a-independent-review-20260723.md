# DL-071a 独立审查：DADAO MC 立即数范围校验

日期：2026-07-23  
角色：Independent reviewer  
判决：**Accepted**

## 1. 判决与 findings

DL-071a 可以接受。没有 blocking finding。

实现把当前 DADAO TableGen 中全部可由 MC 汇编器显式输入的立即数字段绑定到
有符号/无符号范围 matcher；常量越界在汇编期以精确 operand 位置和明确上下界
报错，不能绝对求值的符号表达式仍进入既有 fixup 路径。独立 clean build、测试、
裸 pin 重放和 tree identity 均通过。

### Blocking findings

无。

### Nonblocking findings

1. **原生 LLVM lit 目录门禁仍不可运行。** 当前项目 LLVM build tree 缺少
   `bin/llvm-config`，所以
   `.work/build/llvm/bin/llvm-lit -sv .work/llvm/llvm/test/MC/DADAO`
   在测试发现/执行前退出 `2`。本审查独立执行了新增测试的 RUN 命令、项目
   DADAO MC 14 项，并在裸 pin 重放后的隔离 build 中重新构建
   `llvm-mc`/`FileCheck` 后再次执行新增正负测试；这些证据不能扩大表述成
   “完整 LLVM MC suite”或“完整 LLVM suite”通过。

2. **`immu6=0` 的指令级 legality 仍有一个既有缺口。** 0049 正确检查
   `immu6` 编码字段的无符号六位范围 `[0, 63]`。但 ISA contract 对
   multi-load/store 另有更窄的有效计数范围 `[1, 63]`；当前 MC 仍接受
   `ldmbs ..., 0` 和 `stmb ..., 0`，项目既有
   `tests/lit/MC/Dadao/rrri.s` 也仍把零当作合法汇编输入。这不是 0049
   引入的回归，也不影响本任务要求的编码字段 signed/unsigned 范围修复，
   但后续应以独立 operand-legality 任务处理，不能据 DL-071a 声称所有
   指令级合法性约束都已由 assembler 拒绝。

3. **`tp_probe` 的“语义等价”应限定为测试意图等价。**
   `setzw rd16, 0, 0x5A5A` 精确产生 `0x0000000000005A5A`，满足该测试
   “用一个不同于 value1/value2 的值污染 rb16”的判别目的。旧的
   `addi rd16, rd0, 0x5A5A` 本身违反 `imms12` 范围；旧汇编器静默截断后
   的真实机器值并不是 `0x5A5A`。因此新写法保持的是探针角色和预期源码语义，
   不是与旧错误编码逐 bit 相同。任务和 worker report 当前使用“按测试本意”
   的表述是准确的。

## 2. 独立审查范围

完整读取并交叉核对：

- `code-agent/tasks/DL-071a-mc-immediate-range-validation.md`
- LLVM commit
  `72cb112b4c1eb4f00cb8e8facc78e5185edb1244`
- `components/llvm/patches/0049-dadao-mc-immediate-range-validation.patch`
- root `tests/lit/E2E/tp_probe.test` diff
- `docs/reviews/DL-071a-worker-report-20260723.md`
- DADAO 指令 operand 定义、全部编码 format、MC emitter、ISA/ELF contract
  和生成的 `DADAOGenAsmMatcher.inc`

未把 worker 的结论作为证据；下述测试和重放均由 reviewer 独立执行。

## 3. 立即数类型与覆盖审计

### 3.1 编码字段

`DADAOInstrFormats.td` 当前存在的显式立即数字段为：

| 编码 format | 字段 | MC operand / matcher | 合法常量范围 | 结论 |
|---|---|---|---:|---|
| `rrii` | 12 bit | `imms12` / signed 12 | -2048..2047 | 正确 |
| `rrii` | 12 bit | `immu12` / unsigned 12 | 0..4095 | 正确 |
| `riii`、`oiii` | 18 bit | `imms18` / signed 18 | -131072..131071 | 正确 |
| `rwii` | 16 bit | `immu16` / unsigned 16 | 0..65535 | 正确 |
| `orri`、`rrri` | 6 bit | `immu6` / unsigned 6 | 0..63 | 正确 |
| `iiii` | 24 bit | `imms24` / signed 24 | -8388608..8388607 | 正确 |
| `rwii` | 2 bit | `wydepos` / unsigned 2 | 0..3 | 正确 |
| `ciii` | 6 bit | `cfxcode6`，复用 unsigned 6 | 0..63 | 正确 |

ISA contract 还列出 `immu18`，但当前 LLVM DADAO TableGen 没有
`immu18` operand，也没有可由 AsmParser 输入并编码该类型的指令；因此本提交
不存在漏挂一个现有 MC operand 的问题。CodeGen-only pseudo 使用的
`i64imm` 不对应可编码的 AsmParser 字段，也不属于本次范围。

### 3.2 branch/call 与复用 matcher

独立追踪所有使用点：

- `breq`/`brne` 的 `brtarget12` 复用 `Imms12AsmOperand`；
- `brn`/`brnn`/`brz`/`brnz`/`brp`/`brnp` 的 `brtarget18`
  复用 `Imms18AsmOperand`；
- direct `jump` 的 `brtarget24` 和 direct `call` 的 `imms24`
  均复用 `Imms24AsmOperand`；
- register `jump`/`call` 的末 operand 是 `imms12`；
- `rela`、`ret`、`swym`、`unimp` 和 `trap` 的第二 operand 使用
  `imms18`。

未发现 branch/call 或其它已定义指令绕过 matcher。生成 matcher 中只存在七类
范围 diagnostic，恰好对应七种不同的范围；复用 operand 不重复制造可能漂移的
范围实现。

### 3.3 常量表达式与符号表达式

`isImmInRange<Bits, Signed>()` 只对 `evaluateAsAbsolute` 成功的表达式做
`isIntN`/`isUIntN` 判断：

- 普通常量及 `(2047 + 1)` 会被计算后检查；
- 未解析 symbol 不会在 matcher 阶段被误判成越界；
- `rela`、`addi-rb`、12/18/24-bit branch/jump/call 的外部 symbol
  独立汇编成功。

Reviewer 另建外部 `ext` 输入，六条上述符号指令生成 object 后，
`.rela.text` 中存在六条 relocation，offset 分别为
`0x0/0x4/0x8/0xC/0x10/0x14`。因此证据不只是 parser 接受文本，确实走到了
object relocation 路径。

## 4. Diagnostic 与测试判别力

新增 invalid test 同时检查：

- `llvm-mc` 非零退出；
- 精确源行与 operand 列；
- 对应类型的精确闭区间文本；
- ML-024a 原始 `addi ..., 4096`；
- 可求值越界表达式；
- 普通、branch、direct/indirect jump/call 和 trap/wyde 代表形式。

新增 valid test 覆盖七种范围的合法端点、branch/call 复用字段、绝对表达式，
以及 local symbol/fixup。它只要求成功汇编，不以截断后的反汇编结果代替
汇编期拒绝，判别方向正确。

Reviewer 另以 stdin 独立运行扩展矩阵：

```text
CUSTOM_MATRIX ok=20 bad=24 symbol_object=PASS expr_reject_rc=1
```

该矩阵为每种 signed/unsigned 类型和 wyde position 检查合法端点及上下越界，
并补齐：

- `trap` 的 cfxcode6 和 imms18 两个字段；
- `breq`/`brne` 的 12-bit 两侧越界；
- `brz`/`brnz` 的 18-bit 两侧越界；
- direct `jump`/`call` 的 24-bit 两侧越界；
- register `jump`/`call` 的 12-bit 两侧越界。

24 个非法样本全部在 operand 所在行产生预期范围文本并非零退出；未发现静默
截断或错误 diagnostic 类型。

## 5. `tp_probe` 审查

两处改动均为：

```asm
setzw rd16, 0, 0x5A5A
rd2rb rb16, rd16, 1
```

按 ISA wyde 语义，`setzw` 将 position 0 写成 `0x5A5A` 并把其它 wyde 清零，
所以 rb16 得到一个合法 48-bit sentinel。它与：

- value1 `0x0000BABE12345678`
- value2 `0x0000112233445566`

均不同，仍能排除“set_tp 无效且 get_tp 错读旧 rb16”的复合假阳性。两处替换
对称，未改变 call/ret、TP 写读或成功/失败路径。独立完整 E2E 中该探针和其余
65 项均通过。

## 6. 独立测试结果

| 检查 | Reviewer 结果 |
|---|---|
| 新增 valid RUN | PASS |
| 新增 invalid RUN | `llvm-mc rc=1`，`FileCheck rc=0` |
| 隔离 clean build 后再次运行新增正负测试 | PASS |
| 项目 `tests/lit/MC/Dadao` | 14/14 PASS |
| 完整 `tests/lit/E2E` | 66/66 PASS |
| differential | `AGREE(3-way)=200`，gem5-SKIP=2，`DIVERGE=0` |
| Sail | `AGREE(4-way)=200`，Sail-SKIP=2，`SAIL-DIVERGE=0` |
| `make manifest-check` | PASS |
| `make check-issues` | PASS，Open 23 / Closed 34 / Total 57 |
| 原生 LLVM MC lit 目录 | 未运行；缺 `bin/llvm-config`，配置阶段 rc=2 |

原生 LLVM lit 的失败发生在 suite 配置阶段，不代表用例失败；同样也不能被写成
suite PASS。

## 7. Patch、重放与 clean build

独立结果：

```text
APPLIED=49
REPLAY_TREE=214c454ff1fcf163d95e0d72f5c7743b69374dcf
CURRENT_TREE=214c454ff1fcf163d95e0d72f5c7743b69374dcf
COMMIT_PATCH_ID=41721c9276c69392ac3f2720aea034b4c9b61620
FILE_PATCH_ID=41721c9276c69392ac3f2720aea034b4c9b61620
PATCH_SHA256=a2611309ddfc9804246a85593c04e5815de8a233b0964d5728785a244538bc74
REPLAY_STATUS=<clean>
```

重放从 manifest LLVM pin
`ca7933e47d3a3451d81e72ac174dcb5aa28b59d1` 开始，以 plain
`git am` 顺序应用 `series` 的 49 个 patch。最终 tree 与
`72cb112b4c1eb4f00cb8e8facc78e5185edb1244` 完全一致。

Reviewer 随后直接以该重放 source 新建隔离 CMake/Ninja build：

```text
llvm-mc + FileCheck clean build: PASS
valid test: rc=0
invalid test: llvm-mc rc=1, FileCheck rc=0
```

这同时排除了当前 `.work/build/llvm` 中旧生成文件或增量构建偶然通过的可能。

## 8. 修改边界

本 reviewer 未修改 task、LLVM commit、patch、series、测试、issues、wiki、
roadmap 或任何组件仓库，也未提交。审查在开始和结束前均确认
`.work/llvm` clean。

本审查仅新增本文件。
