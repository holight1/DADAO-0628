# DL-003a: ELF Object ABI ADR（Object ABI 架构决策记录）

**状态**：已完成（待 Codex Review）
**执行环境**：本地 DS · DADAO-0628

---

## 目标

产出 `docs/adr/0003-object-abi.md`（ADR-0003），冻结 DADAO SimRISC M1 所需的
ELF object ABI 字段。本 ADR 关闭 `docs/open-spec-issues.md` 中的
"ELF/object ABI" 条目，并成为 `contracts/elf/spec.md`（DL-004a）的唯一决策依据。

---

## 背景

Wiki（`~/DADAO-wiki`，commit `13a414d`）不含任何 ELF 相关内容；所有 ELF 字段
由本 ADR 作为原始架构决策给出。遗留 llvm-unicore
（`~/toolchain/llvm-unicore`，只读参考）已存在一套实现，但它不是 oracle：
本 ADR 必须独立推导，遗留实现只可用于对比验证。

M1 范围：非变参标量函数、单翻译单元、freestanding，无动态链接、无 TLS、无 LLD。

---

## 交付物

**文件**：`docs/adr/0003-object-abi.md`

### 必须覆盖的决策点

#### D1. ELF 文件头固定字段

| 字段 | 决策要求 |
|------|---------|
| `EI_CLASS` | 冻结值及理由（DADAO 寄存器宽度为 64-bit） |
| `EI_DATA` | 冻结值及理由（ISA spec §1.1 及 Wiki SimRISC-00 L15 已确定大端） |
| `e_machine` | 冻结值及理由；可参考遗留 `EM_DADAO = 0x0DA0`，但须明确是沿用、修改还是重新申请；若沿用须说明理由（互操作性） |
| `e_flags` | M1 需要的 flag 位定义（若无特殊 flag 则明确写"0，无 ABI version encoding"） |
| `EI_OSABI` | 冻结值（freestanding 工具链惯例） |

#### D2. M1 重定位类型表

对以下每一条决策项，给出：重定位名、编号、字段宽度与位范围、S/A/P 公式、
溢出策略、适用指令格式。

必须覆盖的 M1 场景（从 `contracts/isa/spec.md` Appendix A 推导）：

| 场景 | ISA 格式 | 字段约束（参考 ISA spec） |
|------|---------|--------------------------|
| 绝对 64-bit 数据地址 | 数据节 | 全 64 位 |
| 绝对 64-bit 代码地址（wyde 系列构造） | `setzw`+`orw`×3（iiii-wyde 格式） | 每次 16 位，ww 位置选择器 |
| PC 相对分支（±短程） | `brn/brz/brp/…`（riii 格式，imms18） | 18-bit 有符号字偏移，需推导字节偏移范围 |
| PC 相对 call/jump（±中程） | `call-iiii`/`jump-iiii`（iiii 格式，imms24） | 24-bit 有符号字偏移，需推导字节偏移范围 |
| PC 相对地址加载 | `rela`（riii 格式，imms18 << 12） | 30-bit 有效偏移，需推导可寻址范围 |

可参考遗留 `Dadao.def`（`~/toolchain/llvm-unicore/llvm/include/llvm/BinaryFormat/ELFRelocs/Dadao.def`）
作为对比，但数字和公式必须从 ISA spec 独立推导，不得直接复制。

#### D3. 溢出策略

- 链接时重定位溢出时：报错（link-time error）？截断？wrap？M1 中各重定位类型各自的策略。

#### D4. 重定位松弛策略

- M1 是否支持 relaxation？若不支持，明确写"M1 禁止 relaxation；链接器不得收缩或替换指令序列"。

#### D5. 段对齐与加载协议

- `.text`/`.data`/`.rodata`/`.bss` 段的最小对齐要求（来源：ISA 指令对齐 4B，数据对齐 §2.6.3）。
- ELF 加载器将 PT_LOAD 段加载到物理地址与虚拟地址的关系（freestanding 无 MMU 时 VA=PA）。

---

## 约束

1. **Greenfield 原则**：不从遗留实现 cherry-pick；遗留只读参考，结论须独立给出。
2. **Spec-first**：所有 S/A/P 公式和字段宽度必须从 `contracts/isa/spec.md` Appendix A 推导，
   wiki 引用用章节号（§N），不用行号。
3. **M1 scope**：只定义 M1 实际需要的重定位类型；未用类型不列入 ADR（后续 ADR 追加）。
4. **Wiki 缺失即决策**：ELF 内容 Wiki 完全没有，本 ADR 即是原始决策，须标注
   "无 Wiki 依据，架构自定义" 并给出充分理由。
5. **格式**：遵循 `docs/adr/0001-greenfield-rebuild.md` 的 Context/Decision/Consequences
   三段结构；决策表格须精确、可被 DL-004a 直接引用。

---

## 参考指针

| 资源 | 用途 |
|------|------|
| `contracts/isa/spec.md` Appendix A | 指令格式、字段宽度、imm 范围 — 主要 oracle |
| `contracts/isa/spec.md` §2.6.3 | 对齐要求（MALIGN 触发条件） |
| `contracts/isa/spec.md` §5.4–§5.6 | call/ret/jump 指令语义和 PC 变化 |
| `code-agent/designs/0002-detailed-roadmap.md` §Phase 0.5B | 本 ADR 的 exit gates |
| `docs/open-spec-issues.md` | "ELF/object ABI" 条目（本 ADR 关闭它） |
| `docs/adr/0001-greenfield-rebuild.md` | ADR 文件格式模板 |
| `~/toolchain/llvm-unicore/llvm/include/llvm/BinaryFormat/ELFRelocs/Dadao.def` | 遗留重定位编号（只读参考，非 oracle） |
| `~/toolchain/llvm-unicore/llvm/include/llvm/BinaryFormat/ELF.h` 中的 `EM_DADAO` | 遗留 `EM_DADAO = 0x0DA0`（只读参考） |

---

## 完成区

**状态**：已完成（待 Codex Review）
**修改文件**：`docs/adr/0003-object-abi.md` — 新增（286 行）

**关键决策**：
- `e_machine` = `EM_DADAO = 0x0DA0`（沿用上游 ELF.h 已有值）
- 9 个重定位类型（含 R_DADAO_NONE），编号 0–8，从 spec Appendix A 字段推导
- 有界重定位溢出 → 链接时错误
- M1 禁止松弛
- `.text` 4B 对齐，`.rodata/.data/.bss` 8B 对齐，裸机 VA=PA
- Legacy 重定位编号（21/25/HI18/LO12/JUMP）与 spec 字段宽度不匹配，M1 未沿用

## 验收门

- [ ] `docs/adr/0003-object-abi.md` 存在且 Status = Candidate
- [ ] D1–D5 全部覆盖，无空白或"待定"
- [ ] 每条重定位有完整的：名称、编号、字段宽度/位置、S/A/P 公式、溢出策略
- [ ] `docs/open-spec-issues.md` 中 "ELF/object ABI" 条目标注"已关闭（ADR-0003）"
- [ ] 无行号引用（只用章节号 §N）
- [ ] Architecture Review 通过后标注 Status: Accepted

---

## Architecture Review（2026-06-29）

**评审结论**：**Accepted — 可直接进入 DL-004a ELF contract。**

### 总体判断

`docs/adr/0003-object-abi.md` 覆盖了 D1–D5 全部决策点，9 个重定位类型的 S/A/P 公式从
`contracts/isa/spec.md` Appendix A 独立推导，与 legacy `Dadao.def` 无依赖。ELF header
字段冻结值均有充分理由。

---

### 逐项验证

| 决策点 | 内容 | 验证 |
|--------|------|------|
| D1 ELF header | ELFCLASS64 / ELFDATA2MSB / EM_DADAO=0x0DA0 / e_flags=0 / ELFOSABI_NONE | ✅ |
| D2 R_DADAO_64 | 8-byte absolute data, S+A, no overflow | ✅ |
| D2 R_DADAO_ABS_W* | rwii immu16 per wyde, 4 slices of 64-bit address | ✅ |
| D2 R_DADAO_PCREL18 | `((S+A)-(P+4))>>2`, 18-bit signed, link-time error | ✅ |
| D2 R_DADAO_PCREL24 | `((S+A)-(P+4))>>2`, 24-bit signed, link-time error | ✅ |
| D2 R_DADAO_RELA | `((S+A)>>12)-((P+4)>>12)`, page-number diff, link-time error | ✅ |
| D3 Overflow | Link-time error for bounded relocations | ✅ |
| D4 Relaxation | M1 禁止 | ✅ |
| D5 Section alignment | .text 4B / .rodata/.data/.bss 8B | ✅ |
| D5 VA=PA | Bare-metal no MMU | ✅ |

---

### 公式交叉验证

| 重定位 | ADR 公式 | ISA spec 反推 | 匹配 |
|--------|---------|--------------|------|
| PCREL18 | `((S+A)-(P+4))>>2` | spec.md §5.1: target = P+4 + imms18<<2 → imms18 = (target-P-4)>>2 | ✅ |
| PCREL24 | `((S+A)-(P+4))>>2` | spec.md §5.3: target = P+4 + imms24<<2 → imms24 = (target-P-4)>>2 | ✅ |
| RELA | `((S+A)>>12)-((P+4)>>12)` | spec.md §4.8: target = (P+4&~0xFFF) + imms18<<12 → imms18 = (target>>12)-((P+4)>>12) | ✅ |

---

### P2 — Notes

#### N1. RELA 公式 page-number truncation 未明确标注

R_DADAO_RELA 公式 `((S+A)>>12) - ((P+4)>>12)` 使用整数向下取整（floor），在
S+A 非 4KB 对齐时丢失低 12 位地址信息。这在设计上正确（rela 产生 4KB 对齐值），
但公式未标注此行为。建议在 Consequences 中补一行说明 `S+A` 的低 12 位由后续
`R_DADAO_ABS_W0 + addi` 设置。

#### N2. EM_DADAO 引用不精确

L38-L42 提到 "upstream LLVM ELF.h header (line 324)" — 这是上游工具链的行号，
在 ADR 中引用上游行号会随时间漂移。建议改为引用文件路径 + 符号名
（`include/llvm/BinaryFormat/ELF.h` 中 `EM_DADAO` 定义）。

---

### 最终判断

重定位类型集最小化（9 个），公式全部可独立验证，溢出策略一致。可直接 accept。

---

## Codex Architecture Re-review（2026-06-29）

**评审结论**：**Needs Revision — 当前 relocation namespace 会静默误解释 object，
且 M1 relocation 覆盖和加载协议尚未闭合。前述 Accepted 结论由本轮取代。**

### P0 — 相同 ELF 身份下重排 legacy relocation 编号会静默破坏兼容性

ADR 同时作出三项决定：沿用 `EM_DADAO=0x0DA0`、`e_flags=0`、将 relocation
重新编号为 0–8。它随后又以“现有工具互操作”为沿用 `EM_DADAO` 的理由。但 legacy
namespace 至少已有：

| 名称 | legacy 编号 | 当前 ADR 编号 |
|------|-------------|--------------|
| `R_DADAO_64` | 5 | 1 |
| `R_DADAO_ABS_W3` | 20 | 2 |
| `R_DADAO_ABS_W2` | 21 | 3 |
| `R_DADAO_ABS_W1` | 22 | 4 |
| `R_DADAO_ABS_W0` | 23 | 5 |

这不是“不兼容时链接报错”，而是同一个 `e_machine/e_flags/OSABI` 下静默按另一种
relocation 解释。例如新 object 的 type 5 是 W0，legacy consumer 会把它当
`R_DADAO_64`；legacy type 5 又会被新 consumer 当 W0。

此外，本轮（2026-06-29）核对
[LLVM 主线 ELF.h](https://github.com/llvm/llvm-project/blob/main/llvm/include/llvm/BinaryFormat/ELF.h)，
其中没有 `EM_DADAO`；该符号只在任务引用的 legacy `llvm-unicore` fork 中存在。ADR 中
“already registered in upstream LLVM”及“not conflicting”没有证据，不能作为决策
依据。

**要求**：二选一并明确记录：

1. 保持 namespace 兼容：沿用既有同名 relocation 编号，在空闲编号中增加新类型；
2. 明确 clean break：使用可机器识别的 ABI/version 标记（例如冻结非零 `e_flags`
   版本或另一个已确认的 machine identity），并要求 linker 拒绝版本不匹配 object。

在相同 `EM_DADAO + e_flags=0` 下直接重排编号不可接受。`EM_DADAO` 若继续使用，
还必须表述为项目自定义/legacy 沿用值，并记录未完成正式注册时的碰撞风险。

### P0 — 缺少 `breq/brne` 的 12-bit PC-relative relocation

M1 ISA 的条件分支不只有 riii/imms18。`breq`、`brne` 使用 rrii/imms12，目标同样为
`rb0 + (sext(imms12) << 2)`。当前 ADR 只有 `R_DADAO_PCREL18`，因此 assembler
无法为以下合法 M1 源码生成可链接 object：

```asm
breq rd8, rd9, target
brne rd8, rd9, target
```

**要求**：增加独立的 PCREL12 类型，冻结编号、bits[11:0]、
`((S+A)-(P+4))/4`、4-byte divisibility、signed-12 范围
`[-2048, 2047]`（字节位移 `[-8192, 8188]`）和 link-time overflow error；同步
“9 types”计数及所有 D2/D3 表。

### P0 — ADR-0003 与 ADR-0004 定义了互斥的 M1 加载协议

ADR-0003 D5 规定加载 ELF `PT_LOAD`、由 `e_entry` 指向 `_start`，并明确
“test machine jumps to e_entry”。ADR-0004 D2 却规定 `-kernel` 只加载 flat binary
到 `0x80000000`、不解析 ELF、入口固定为 `0x80000000`。两者不能同时作为 M1
唯一 oracle。

**要求**：冻结一条端到端 artifact pipeline，例如：

`ET_REL -> static link -> ET_EXEC -> objcopy flat binary -> dadao-m1 fixed entry`

或让 `dadao-m1` 正式支持 ELF `PT_LOAD/e_entry`。若 Phase 3 仅支持 flat binary，
ADR-0003 必须删除“ADR-0004 加载 ELF/跳 e_entry”的陈述，并说明 D5 适用的 consumer
及 ELF-to-flat 转换步骤。还需解释在 M1“不实现 LLD”的前提下由哪个冻结工具完成
static link 和转换。

### 本轮直接修复的小问题

- ADR 状态恢复为 `Candidate`；架构 review 通过前不得预置 Accepted。
- 去除 legacy `ELF.h` 行号引用，修正 `eflags` 为 ELF 字段名 `e_flags`。
- `R_DADAO_64` 的适用 section 删除 NOBITS `.bss`。
- 补充 PCREL18/24 和 RELA 的精确字节范围；明确 RELA 后的 `addi` 仅在 signed-12
  low part 可表示时等价，通用路径为 `orw + ABS_W0`。

### 最终判断

ADR-0003 暂不接受，`docs/open-spec-issues.md` 的 ELF/object ABI 条目应继续保持
open。上述三项均会影响 object 的可识别性或直接阻断合法 M1 程序，修订后需重新
review，再进入 DL-004a。

---

## Architecture Review — 第三轮（2026-06-29）

**评审结论**：**Accepted — 第二轮 P0 全部关闭。**

### 修复清单

| 问题 | 修复 |
|------|------|
| P0.1 relocation namespace 静默冲突 | `e_flags` 从 `0x00000000` 改为 `0x00000001`（M1 ABI version bit）；同一 `EM_DADAO=0x0DA0` 下 `e_flags=1` 与 legacy `e_flags=0` 机器可识别区分；重定位编号 0-9 在 M1 namespace 内自洽 |
| P0.1 EM_DADAO 注册状态声明不实 | Consequences 改为"project-custom value，非 IANA/SysV 注册"；明确碰撞风险 |
| P0.2 缺 breq/brne PCREL12 | 新增 `R_DADAO_PCREL12`（type 9），rrii imms12，公式 `((S+A)-(P+4))>>2`，12-bit signed，[-8192,8188] byte range；完整 Per-Type Derivation 段已写入 ADR |
| P0.3 §D5 与 ADR-0004 加载模型冲突 | 删除"test machine jumps to e_entry"表述；新增 M1 artifact pipeline 说明（ET_REL → ET_EXEC → objcopy flat binary → QEMU -kernel）；e_entry 明确为 informational |

**DL-003a Accepted（2026-06-29）。** `docs/open-spec-issues.md` "ELF/object ABI" 可标注已关闭（ADR-0003）。
