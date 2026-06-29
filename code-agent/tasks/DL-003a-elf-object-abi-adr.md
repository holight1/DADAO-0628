# DL-003a: ELF Object ABI ADR（Object ABI 架构决策记录）

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
| `~/toolchain/llvm-unicore/llvm/include/llvm/BinaryFormat/ELF.h` L324 | 遗留 `EM_DADAO = 0x0DA0`（只读参考） |

---

## 验收门

- [ ] `docs/adr/0003-object-abi.md` 存在且 Status = Candidate
- [ ] D1–D5 全部覆盖，无空白或"待定"
- [ ] 每条重定位有完整的：名称、编号、字段宽度/位置、S/A/P 公式、溢出策略
- [ ] `docs/open-spec-issues.md` 中 "ELF/object ABI" 条目标注"已关闭（ADR-0003）"
- [ ] 无行号引用（只用章节号 §N）
- [ ] Architecture Review 通过后标注 Status: Accepted
