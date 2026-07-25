# KL-114a：LLVM MC 支持 `ldmo-ra`/`stmo-ra`/`cfx2rc`/`escape`

**执行环境**：本地 subagent，LLVM 源码改动（`.work/source/llvm`），产出
patch 落 `components/llvm/patches/`

## 背景

`ldmo-ra`/`stmo-ra`（RegRAS 整 bank RA 访问，KL-108a QEMU/KL-109a gem5
已实现并验证）和 `cfx2rc`/`escape`（hypv→supv 特权切换，KL-110a/112a QEMU、
KL-113a gem5 已实现并验证）这四条指令目前**只能靠手写指令字/裸字节编码
测试**（`tests/scripts/gen_kl110a_o1_probe.py` 等探针脚本直接拼二进制），
LLVM 汇编器/反汇编器完全不认识它们——不能从真实 `.s` 汇编源码或 C 源码
生成的 MC 层写出这几条指令。这是 K1 阶段唯一还没做的"工具链闭环"缺口，
补上之后才能让 K2/K3 的内核代码（真正需要写 `.s` 引导代码调用这些指令）
用正常编译流程产出，而不是继续靠手工拼指令字。

**现有可直接类比的 TableGen 先例**（架构师已核实，位置准确）：

- `ldmo-ra`/`stmo-ra` 是 RB-bank 版本 `ldmo-rb`/`stmo-rb` 的 RA-bank
  变体，编码格式完全同构（`rrri`）。`DADAOInstrInfo.td:402`
  `LDMO_RBRRRI`（`op=0x47`，`F_RRRI_RB` 格式类，输出 `GPRB`，
  `DADAOInstrFormats.td:249` 定义）和 `DADAOInstrInfo.td:415`
  `STMO_RB_RRRI`（`op=0x4F`）是直接的移植模板——`ldmo-ra`/`stmo-ra`
  的 opcode 是 `0x63`/`0x6F`（`SimRISC-00-指令系统设计.md` 第103-104行
  opcode 表 `0110-0xxx`/`0110-1xxx` 行 `xxxx-x111` 列）。`GPRA` 寄存器类
  已存在（`DADAORegisterInfo.td:66-70`，`isAllocatable=0`，和 `GPRF`
  同样的"不参与寄存器分配，只做显式寻址"模式），可以直接复用，不需要
  新建寄存器类。
- `escape` 是 `trap` 的同构指令（都是 `ciii` 格式：`ha`=立即数 cfxcode，
  `imms18`=有符号偏移）。`DADAOInstrInfo.td:451` `TRAP_CIII`
  （`op=0x76`，`F_RIII_RD` 格式类，`(ins cfxcode6:$rdha, imms18:$imm18)`）
  是直接的移植模板——`escape` 的 opcode 是 `0x77`
  （`SimRISC-00-指令系统设计.md` 第105行 `0111-0xxx` 行 `xxxx-x111` 列，
  `01110111=0x77`）。
- `cfx2rc` 是 `crrr` 格式，**当前没有任何现成的 TableGen 格式类**（架构师
  已 grep 确认 `F_CRRR`/`crrr` 在 `DADAOInstrFormats.td`/
  `DADAOInstrInfo.td` 零命中）——这是本任务唯一需要新建格式类的部分。
  `crrr` 的语法是 `cfx2rc cfx_<cfxname>, cghb, rchc, rdhd`
  （`SimRISC-04-系统类指令.md` 第80-91行）：`ha`=cfxcode（立即数）、
  `hb`=cg（立即数）、`hc`=rc（立即数）、`hd`=源寄存器（`GPRD`，可选，
  `hd=0` 时读常量0，同 QEMU/gem5 已实现的 `rd0` 惯例）。`cfx2rc` 的
  opcode 是 `0x73`（`SimRISC-00-指令系统设计.md` 第105行 `0111-0xxx` 行
  `xxxx-x011` 列，`01110011=0x73`）。

## 目标

在 `.work/source/llvm` 里让这四条指令能：

1. 从 `.s` 汇编源码正确汇编成 QEMU/gem5 已验证过的确切指令字编码（用
   `gen_kl108a`/`gen_kl110a_o1_probe.py`/`gen_kl112a_o2_probes.py`/
   KL-109a 相关探针里的裸字节作为 ground truth 逐位核对，不是自己重新
   编码后就相信）。
2. `llvm-mc`/`llvm-objdump -d` 能正确反汇编回可读的汇编文本（往返
   round-trip：汇编→反汇编→汇编，二进制不变）。
3. 具体分工：
   - `ldmo-ra`/`stmo-ra`：`DADAOInstrInfo.td` 仿 `LDMO_RBRRRI`/
     `STMO_RB_RRRI` 各加一条定义，操作数用 `GPRA` 代替 `GPRB`，`op`
     改成 `0x63`/`0x6F`。
   - `escape`：`DADAOInstrInfo.td` 仿 `TRAP_CIII` 加一条 `ESCAPE_CIII`
     定义，`op=0x77`。
   - `cfx2rc`：`DADAOInstrFormats.td` 新增 `F_CRRR` 格式类（三个立即数
     操作数 + 一个可选源寄存器，编码布局参照 QEMU
     `.work/source/qemu/target/dadao/insn.decode` 里 `cfx2rc` 的
     `@rrrr`/`@riii` 复用模板反推字段位置，或直接读 wiki
     `SimRISC-04-系统类指令.md` 的编码位置描述），`DADAOInstrInfo.td`
     用这个新格式类定义 `CFX2RC_CRRR`（`op=0x73`）。
4. 每条指令至少一个 `tests/lit/CodeGen/` 或专门的 MC-only lit 测试
   （`llvm-mc`直接跑，不需要过 Clang/C），验证编码字节与 QEMU/gem5 探针
   脚本里对应指令的手工编码逐位一致（不是只验证"能汇编成功"，要验证
   "编出来的字节和已验证的实现读的是同一个东西"）。

## 约束

- **不要实现 wiki `SimRISC-04-系统类指令.md` 第91-97行提到的
  `cfx_<cfxname>_regname` 符号化简写语法**（汇编器自动查 cg/rc 编号那个
  便利特性）——当前项目所有探针/QEMU/gem5 实现都是用裸数字操作数
  （`cfx2rc cfx_power, 8, 63, rd2` 这种三段式，不是
  `cfx2rc cfx_power_ctrl, rd2` 简写），本任务只做裸数字操作数形式的
  MC 支持，符号化简写是独立的、更大的后续特性，不在本任务范围。
- 不要改变任何已经验证过的指令编码——四条指令的确切编码在 QEMU/gem5
  实现里已经过差分/裸pin验证，MC 层必须精确匹配这个既有编码，不能自己
  另创一套"更合理"的编码方式。
- 不需要给这四条指令写 `SelectionDAG` lowering / CodeGen 支持（Clang
  C 源码目前不会生成这几条系统指令，只需要能从手写 `.s` 汇编）——只做
  `MCInstrInfo`/`AsmParser`/`MCCodeEmitter`/`InstPrinter`/反汇编这条
  链路，不碰 `DADAOISelLowering.cpp`。
- 完整 patch-series bare-pin replay（tree-hash 比对）是硬性验收项，
  照本项目其它 LLVM 任务的标准执行。
- 完成后写「完成区」+「审阅记录（subagent 自审）」；不需要嵌套
  subagent、不需要独立 reviewer（架构师会亲自复核）。

## 验收

- `llvm-mc -triple=dadao` 汇编这四条指令的测试用例，产出字节与
  QEMU/gem5 探针脚本里对应的裸编码逐位一致（列出具体核对的探针文件/
  函数名）。
- `llvm-objdump -d` 反汇编能正确还原可读汇编文本；round-trip（汇编→
  反汇编→再汇编）字节不变。
- 全量 LLVM MC/CodeGen 定向 lit 测试通过，无回归。
- LLVM patch-series 从 `manifests/components.lock.toml` 锁定 commit
  起裸 pin + 完整 series replay，tree hash 与开发树一致。
- 现有全量 E2E lit（`tests/lit/E2E/`）、`tools/run_differential.py`
  保持不变，无回归（这四条指令不进入现有差分向量集合，只验证 MC 层
  本身，不影响执行语义测试）。

## 参考指针

- `DADAOInstrInfo.td:402/415`（`LDMO_RBRRRI`/`STMO_RB_RRRI`，RA-bank
  版本的直接移植模板）、`DADAOInstrInfo.td:451`（`TRAP_CIII`，`escape`
  的直接移植模板）、`DADAORegisterInfo.td:66-70`（`GPRA` 寄存器类，
  已存在可直接复用）、`DADAOInstrFormats.td:235-260`附近
  （`F_RRRI`/`F_RRRI_RB` 格式类定义，供 `cfx2rc` 新格式类参照写法）
- `.work/source/qemu/target/dadao/insn.decode`（`ldmo-ra`/`stmo-ra`
  KL-108a 已加的解码模式；`cfx2rc`/`escape` KL-110a/112a 已加的解码
  模式——MC 层编码必须和这里的位域定义精确对应）
- `~/DADAO-gem5/src/arch/dadao/decoder.cc`（`RAMultiLoadInst`/
  `RAMultiStoreInst`、`CFX2RCInst`/`EscapeInst`——手工解码的字段提取
  顺序，交叉核对编码位置）
- `tests/scripts/gen_kl110a_o1_probe.py`、
  `tests/scripts/gen_kl112a_o2_probes.py`（`cfx2rc`/`escape` 的
  ground-truth 裸编码，用来核对 MC 层编出来的字节）
- KL-108a/KL-109a 任务文件完成区（`ldmo-ra`/`stmo-ra` 的确切编码/
  操作数顺序，QEMU+gem5 双重验证过）
- `~/DADAO-wiki/SimRISC-00-指令系统设计.md` 第85-106行 opcode 表；
  `~/DADAO-wiki/SimRISC-02-地址类指令.md` 第47-63行"存取RA寄存器"
  （`ldmo-ra`/`stmo-ra` 语法）；`~/DADAO-wiki/SimRISC-04-系统类指令.md`
  第72-103行寄存器传输指令（`cfx2rc`/`crrr` 语法与编码位置）

---

## 完成区（2026-07-25）

**状态**：已完成；实现、bare-pin patch-series replay、自审均通过。

### 与任务文件原始描述的两处偏差（ground-truth 核对后修正）

任务文件转述有两处与既有实现的 ground truth 不符，均在动手前用
`.work/source/qemu/target/dadao/insn.decode`/`tools/opcodes.yaml`/
`contracts/isa/spec.md` 交叉核对后发现并按 ground truth 执行，而不是
按任务文件原文字面实现：

1. **`ldmo-ra` opcode**：任务文件写 `0x63`，但 `insn.decode:158`
   （`ldmo_ra 01100111 ... @rrri`）、`tools/opcodes.yaml`
   （`ldmo-ra` 条目 `op: 0x67`）、`contracts/isa/spec.md §4.9`
   （"Encoding: §2.8 row 01100 col 111 (`0x67`)"）三处一致确认为
   `0x67`。`stmo-ra=0x6F` 任务文件原文正确。按 `0x67`/`0x6F` 实现。
2. **`ldmo-ra`/`stmo-ra` 的实际汇编助记符**：任务文件全文称呼这两条指令
   为"ldmo-ra"/"stmo-ra"，`contracts/isa/spec.md` Appendix A 的
   "Mnemonic" 列也写作 `ldmo-ra`/`stmo-ra`。但通过对比该同一张表里已经
   落地实现的邻近行——`0x43` 表列"ldo-rb"对应的却是已实现的
   `LDO_RBRRII`，真实 `AsmString` 是裸 `"ldo $rbha, ..."`（`rb_ops.s`
   实测 `# ASM: ldo rb1, rb2, 8`）；`0x47`/`0x4F` 表列"ldmo-rb"/
   "stmo-rb"对应的真实助记符同样是裸 `"ldmo"`/`"stmo"`（`rrri.s`/
   `rb_ops.s` 实测）——可以确认 spec.md 表格里的 `-rb`/`-ra` 后缀是
   文档层面消歧标签（区分同一张表里多行共享的助记符），不是独立的
   汇编器 token。另外做了实机验证：把 `LDMO_RARRRI` 的 `AsmString`
   临时改成字面 `"ldmo-ra $raha, ..."` 编译后跑
   `llvm-mc ... "ldmo-ra ra1, rb2, rd3, 5"` 会解析失败
   （`error: expected comma`）——LLVM 默认 `AsmLexer` 的标识符文法
   `[a-zA-Z_$.@?][a-zA-Z0-9_$.@#?]*` 不含 `-`，"ldmo-ra" 会被切成三个
   token（`ldmo`/`-`/`ra`），不加汇编器层面的特殊逐字符拼接逻辑无法
   作为单一 token 解析。因此最终实现为裸 `"ldmo"`/`"stmo"` 助记符，
   按目的操作数寄存器组重载（`GPRA`），与既有 `GPRD`(op=0x37)/
   `GPRB`(op=0x47) 两路重载完全同构，也是 wiki
   `SimRISC-02-地址类指令.md` 第52-53行原文字面语法
   （`ldmo raha, rbhb, rdhc, immu6`，没有 `-ra` 后缀）。

### LLVM 落地

- 普通 commit：`1146c671a1ae418fd84733fa98fd58a559a5112d`
  （`DADAO: add MC assembler/disassembler support for
  ldmo-ra/stmo-ra/cfx2rc/escape (KL-114a)`）。
- 改动严格限于：
  - `llvm/lib/Target/DADAO/DADAOInstrFormats.td`（新增 `F_RRRI_RA`、
    `F_CRRR` 两个格式类）
  - `llvm/lib/Target/DADAO/DADAOInstrInfo.td`（新增
    `LDMO_RARRRI`/`STMO_RA_RRRI`/`CFX2RC_CRRR`/`ESCAPE_CIII` 四条定义）
  - `llvm/lib/Target/DADAO/Disassembler/DADAODisassembler.cpp`（新增
    `DecodeGPRARegisterClass`——`GPRA` 此前无任何指令引用，没有对应
    反汇编回调，本任务首次需要它）
  - `llvm/test/MC/DADAO/immediate-range-{valid,invalid}.s`（新增四条
    指令的立即数边界用例）
  - 未改动 `DADAOISelLowering.cpp`/`DADAOISelDAGToDAG.cpp` 或任何
    SelectionDAG/CodeGen 代码路径。
- 统计：5 files changed，128 insertions。
- patch：`components/llvm/patches/0065-DADAO-add-MC-assembler-disassembler-support-for-ldmo.patch`
  （264 行），已追加 `components/llvm/patches/series`。
- commit 与 patch 的 stable patch-id 均为
  `b523a0a7f81ac86a7afe22c3e0b58076eda6433e`；LLVM worktree clean。

### 实现内容

- `F_RRRI_RA`：`F_RRRI_RB` 的 RA-bank 对应类，字段名 `raha`（而非
  `rbha`），编码布局与 `F_RRRI_RB`/`F_RRRI` 完全同构（`InstDADAO` 基类
  的 `ha/hb/hc/hd` 直接对应 `Inst{23-18,17-12,11-6,5-0}`，四个格式类
  只是字段命名不同）。
- `F_CRRR`：`cfxcode`/`cg`/`rc`/`rdhd` 四字段，同样直接复用
  `InstDADAO` 的 `ha/hb/hc/hd` 位布局，新建这个类纯粹是为了字段命名
  对应 wiki `crrr` 语义角色。
- `LDMO_RARRRI`（`op=0x67`）/`STMO_RA_RRRI`（`op=0x6F`）：`outs`/`ins`
  换成 `GPRA:$raha`（`GPRB:$rbhb, GPRD:$rdhc, immu6:$imm6` 不变），
  `AsmString` 裸 `"ldmo"`/`"stmo"`（见上文助记符决策）。
- `CFX2RC_CRRR`（`op=0x73`）：`(ins cfxcode6:$cfxcode, immu6:$cg,
  immu6:$rc, GPRD:$rdhd)`，`AsmString`
  `"cfx2rc $cfxcode, $cg, $rc, $rdhd"`；`cfxcode`/`cg`/`rc` 均为裸
  数字操作数（复用已有 `Immu6AsmOperand` 解析类，与 `trap` 的
  `cfxcode6` 操作数完全一致），未实现 wiki 提到的
  `cfx_<cfxname>_regname` 符号化简写（任务范围明确排除）。
- `ESCAPE_CIII`（`op=0x77`）：`TRAP_CIII` 的直接镜像，`(ins
  cfxcode6:$rdha, imms18:$imm18)`，`AsmString`
  `"escape $rdha, $imm18"`。
- `DecodeGPRARegisterClass`：与既有 `DecodeGPRBRegisterClass` 完全同构
  的手写 `RegNo -> DADAO::RA0+RegNo` 映射。

### 验证结果

1. 增量构建：`ninja -C .work/build/llvm llvm-mc llvm-objdump llc`：
   全部 PASS（`llc` 单独验证 CodeGen 路径仍可编译，尽管本任务未新增
   CodeGen 语义）。
2. 编码逐位核对（`.work/evidence/KL-114a-groundtruth-crosscheck.md`
   完整记录，方法论：独立按
   `scripts/check_legality_matrix.py` 的 `encode()` 公式
   `(op&0xFF)<<24|(ha&0x3F)<<18|(hb&0x3F)<<12|(hc&0x3F)<<6|(hd&0x3F)`
   手算期望字节，与 `llvm-mc` 实际编码输出比对，逐位一致）：
   - `ldmo ra1, rb2, rd3, 5` → `67 04 20 c5`
   - `stmo ra1, rb2, rd3, 5` → `6f 04 20 c5`
   - `cfx2rc 63, 8, 1, rd2` → `73 fc 80 42`（wiki 原文worked example
     `cfx2rc cfx_power, 8, 1, rd2` 的裸数字形式，`cfx_power`=63 取自
     `gen_kl110a_o1_probe.py` 的 `CFX_POWER = 63`）
   - `escape 63, 0` → `77 fc 00 00`（`gen_kl110a_o1_probe.py` HBI §3
     handoff probe 最后一条指令原样复用）
   - `escape 5, -4` → `77 17 ff fc`
   - `ldmo ra63, rb63, rd63, 63` → `67 ff ff ff`
   - `stmo ra0, rb1, rd2, 1` → `6f 00 10 81`
   - `cfx2rc 0, 0, 0, rd0` → `73 00 00 00`
   - 全部 8 项 `llvm-mc` 实际输出与独立手算 ground truth 逐字节一致；
   - 同一 probe 里额外验证既有 `ldmo rd10,rb11,rd12,31`(op=0x37)/
     `ldmo rb1,rb2,rd3,4`(op=0x47) 两行未受新增 RA-bank 重载影响。
   - opcode/format 来源交叉表见 evidence 文件，逐一对照
     `target/dadao/insn.decode` 与 `tools/opcodes.yaml`。
3. round-trip：`llvm-objdump -d` 将上述 8+2 条指令全部正确反汇编回
   原始助记符/操作数；`llvm-mc -filetype=asm` 原样重印相同汇编文本
   （`.work/evidence/KL-114a-objdump-roundtrip.txt`/
   `KL-114a-asm-roundtrip.txt`）。
4. 新增 lit 测试：
   - `tests/lit/MC/Dadao/ra_ops.s`、`tests/lit/MC/Dadao/cfx_ops.s`
     （本项目既有 `llvm-mc→objdump OBJ字节检查 + llvm-mc -filetype=asm
     ASM 回环` 惯例，仿照 `rb_ops.s`/`riii_ret.s` 写法）。
   - `llvm/test/MC/DADAO/immediate-range-{valid,invalid}.s` 追加四条
     指令的立即数边界用例（`cfx2rc`/`escape` 的 cfxcode/cg/rc/imm18，
     `ldmo`/`stmo` RA-bank 的 immu6 count）；invalid 侧的期望错误列号
     先用探针脚本实跑确认真实报错位置再写入 `CHECK`，不是手数字符
     猜测。
5. 全量回归（均在本次改动后的构建产物上跑）：
   - `llvm-lit llvm/test/MC/DADAO`：2/2 PASS。
   - `llvm-lit llvm/test/CodeGen/DADAO`：13/13 PASS（用重新构建的
     `llc`，确认新增 TableGen 定义未破坏 CodeGen 编译路径）。
   - `llvm-lit tests/lit/MC/Dadao`（项目自有 MC 套件）：16/16 PASS
     （14 条既有 + 2 条新增）。
   - `llvm-lit tests/lit/E2E`：81/81 PASS，无回归。
   - `python3 tools/run_differential.py`：`AGREE(3-way)=200`、
     `AGREE(4-way)=200`、`DIVERGE=0`，与 KL-109a 完成区基线完全一致
     （本任务未改动 QEMU/gem5/interp/Sail，未纳入新指令到差分向量集
     合，数字符合预期不变）。
   - `python3 scripts/manifest_check.py`：PASS。
   - `python3 scripts/check_issues.py`：PASS。
6. patch series 独立 bare-pin replay：
   - manifest LLVM pin `ca7933e47d3a3451d81e72ac174dcb5aa28b59d1`；
   - 从该 pin 在独立临时 clone（`--reference` 本地对象库加速，未用
     `--dissociate`，验证完成后已整体删除）上 plain `git am`
     依次应用 65/65 patch，全部成功（含既有 64 条 + 本任务新增
     `0065`）；
   - replay tree 与开发树（`.work/source/llvm` 当前 HEAD）均为
     `79fc86403e6ae54382a38d13132e71ef9a78cb2d`；
   - 临时 clone 已清理。
7. `git diff --check`（LLVM 子仓库改动 + 根仓库 `patches/series`）：
   PASS，无尾随空白问题。

### 未做的事（明确排除，非遗漏）

- `cfx_<cfxname>_regname` 符号化简写语法（wiki
  `SimRISC-04-系统类指令.md` L91-97）——任务约束明确排除，独立后续
  特性。
- `SelectionDAG`/CodeGen lowering——任务约束明确排除，`llc` 仅验证
  编译不受影响，未新增任何 lowering 代码。
- `cfx_<name>`/`cfxNN` 记号化（数字以外的 cfxcode 写法）——`trap`
  这条早已存在的同类指令（`TRAP_CIII`）本身也从未实现过任何符号化
  cfxcode 支持，本任务与既有实现保持一致（裸数字），未扩大范围单独
  给 `cfx2rc`/`escape` 加这个能力。

## 执行者自审：审阅记录（subagent 自审）

**判决**：自审通过，未发现阻塞 finding。

- **编码正确性**：四条指令的 opcode/格式/字段布局均逐一对照
  `target/dadao/insn.decode`（QEMU 权威解码定义）、`tools/opcodes.yaml`
  （项目权威编码目录）、`contracts/isa/spec.md`（KL-107a/110a/112a
  formalize 的权威语义 spec）三处独立源，三者互相一致且与
  `llvm-mc` 实际编码输出逐位吻合（见验证结果第2项）。未凭空发明或
  "看起来更合理"的编码。
- **opcode 纠错**：任务文件原文 `ldmo-ra` 写的 `0x63` 与三份权威源
  （`insn.decode`/`opcodes.yaml`/`spec.md`）均不一致，动手前已核实并
  按 `0x67` 实现，未盲信任务文件转述。
- **助记符决策**：没有直接照抄任务文件"ldmo-ra"字面表述，而是通过
  （a）交叉比对 spec.md 同一张表里已落地实现的相邻行的真实助记符、
  （b）实机验证字面 hyphenated mnemonic 在 LLVM 默认 AsmLexer 下无法
  解析，两条独立证据链得出裸 `"ldmo"`/`"stmo"` 重载才是正确实现，
  过程和依据已完整记录在"与任务文件原始描述的两处偏差"一节。
- **范围边界**：未实现 cfx 符号化简写（任务约束排除）；未碰
  `DADAOISelLowering.cpp`/`DADAOISelDAGToDAG.cpp`
  （`git show --stat` 确认改动文件列表不含它们）；未修改任何既有
  指令的编码或行为（`llvm/test/MC/DADAO`、`llvm/test/CodeGen/DADAO`、
  项目自有 `tests/lit/MC/Dadao`、`tests/lit/E2E` 四套既有回归测试
  全部 PASS，`tools/run_differential.py` 基线数字不变）。
- **patch-series 完整性**：bare-pin 从 manifest 锁定 commit 独立
  clone+replay，65/65 成功，replay tree 与开发树 hash 完全一致——这是
  硬性验收项，已达成。临时 clone 使用 `--reference` 加速但未
  `--dissociate`（验证完立即删除，不留存、不提交），未触碰
  `.work/source/llvm` 开发树本身的 git 历史。
- **未做的事**：本任务未在根仓库 `DADAO-0628` 做任何 `git commit`
  （任务文件、`tests/lit/MC/Dadao/*.s`、`.work/evidence/*`、
  `components/llvm/patches/*` 均为待架构师复核的未提交改动）；只在
  `.work/source/llvm` 子仓库做了一次普通 commit，与
  KL-108a/109a 先例的执行边界一致。
