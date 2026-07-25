# KL-107a：把 `ldmo-ra`/`stmo-ra` 正式纳入 contracts/isa/spec.md（K1 RegRAS spec decision 落地）

**执行环境**：本地 subagent，**仅改 `contracts/isa/spec.md`，不改 QEMU/gem5/LLVM/wiki**

## 前置决策（架构师提议，需用户/架构师在下发前确认）

`KL-106a`（`docs/reviews/kernel-regras-ldmo-stmo-semantics-20260725.md`，架构师
已逐条核对 wiki 原文引用，结论可信）确认：`ldmo-ra`/`stmo-ra` 的编码
（`0x67`/`0x6F`，格式 `rrri`）、槽位数（1-63/条指令）、槽位顺序、对齐
（8字节 MALIGN）、越界（`immu6=0` 或 `raha+immu6>64` 触发 ILLI）、重叠处理
（按序号递增逐对先读后写）在 wiki `SimRISC-02-地址类指令.md §存取RA寄存器`
（第47-63行）**都有完整定义**，唯独**引用计数字段（`bits[63:48]`）在整 bank
搬移时如何处理**，wiki 从未提及（§大端序 `bits[63:48]` 高位行为分类表第9-21行
明确没有 RA↔内存这一行，且这不是遗漏——`ra2rd`/`rd2ra` 单槽搬移已定义为
"全64位覆盖"，但 RA↔内存的整bank搬移wiki始终没有对应条款，从wiki创建至今
21次相关commit均未补上）。

**本任务采用的立场**：`bits[63:48]` 引用计数在 `ldmo-ra`/`stmo-ra` 搬移时
**全64位原样拷贝**（不做清零/校验/特殊处理），与已有 `ra2rd`/`rd2ra`（单槽）
的"全64位覆盖"规则保持一致。**这是本任务提议的立场，不是 wiki 明文规定**——
`docs/wiki-deviations.md` 第8条已经如实记录了这个决策的性质（类比证据支持，
但非显式条款）。**如果你（用户/架构师）在下发这个任务前对这个立场有异议，
请先改这个任务文件，不要直接下发。**

## 背景

`ldmo-ra`/`stmo-ra` 从项目最早的 spec 定稿（2026-06-29，`8c6c0cc`）起就被排除
在 M1 之外（`contracts/isa/spec.md` §7 "RA memory access" 一行）。K1 内核
bring-up（`KL-105a`）需要这两条指令做进程切换时的完整 RegRAS bank
保存/恢复——`KL-105a` 判断软件逐槽方案（方案B）不可行，推荐重新纳入这两条
整 bank 指令（方案A）。`KL-106a` 已经把这个方案的技术可行性摸清楚。

本任务是这个决定的第一步：**只把 spec 正式写清楚**，不碰任何实现（QEMU/gem5/
LLVM 汇编器支持是后续独立任务，等 spec 落定后再做）。

## 目标

1. **`contracts/isa/spec.md` §7 M1 Excluded**：删除或改写"RA memory access"
   这一行——`ldmo-ra`/`stmo-ra` 不再属于 M1 排除范围。保留
   "RA register move"（`rd2ra`/`ra2rd`）那一行不变（这两条指令本任务不涉及，
   继续排除）。
2. **新增正式指令定义章节**（建议放在 §4（RB 相关指令）之后或 §1.5（RA 模型）
   附近，具体位置自行判断哪里最连贯，参照 §4.2 `ldmo-rb`/`stmo-rb` 的formalize
   写法）：
   ```
   ldmo-ra  raha, rbhb, rdhc, immu6  ; multi load to RA
   stmo-ra  raha, rbhb, rdhc, immu6  ; multi store from RA
   ```
   内容需覆盖：
   - Encoding：§2.8 row 0110-0xxx col 111（`0x67`）/ 0110-1xxx col 111
     （`0x6F`）。Format `rrri`。
   - EA 公式（类比 §4.2 `ldmo-rb`/`stmo-rb` 的写法：
     `(rbhb[47:0] + rdhc[47:0] + i × 8) mod 2^48`）。
   - **引用计数处理**：显式写明"全64位原样拷贝，`bits[63:48]` 不做特殊处理"，
     并标注这是 spec-decision（不是 wiki 原文条款），引用 `KL-106a`/
     `docs/wiki-deviations.md` 第8条作为决策依据，仿照 §7 现有
     "RA register move"那行的写法（`Excluded (M1 scope decision,
     2026-06-29; ...)`）用类似的方括号标注格式记录"这是何时、依据什么做的
     决定"。
   - Alignment：8字节/元素，MALIGN。
   - Legality：`immu6 ∈ [1,63]`；`raha + immu6 ≤ 64`；违反触发 ILLI。
   - 重叠处理：按序号递增逐对先读后写（wiki §存取RA寄存器 原文已有）。
3. **Appendix A**：在 A.1.10（Row 0110-0xxx）新增 `0x67` 行（`ldmo-ra`），
   A.1.11（Row 0110-1xxx）新增 `0x6F` 行（`stmo-ra`），字段列参照同表
   `ldmo-rb`（`0x4F`附近，在其它 row，自行按 `rrri` 格式确认对应字段）的
   写法（`ha`/`hb`/`hc`/`hd` 分别对应 `raha`/`rbhb`/`rdhc`/`immu6`，
   `mask`/`value` 按 `0xFF000000`/`op<<24` 规则填）。
4. **`docs/wiki-deviations.md` 第8条状态更新**：如果本任务的 spec-decision
   被采纳（正常情况下应该会，因为这是 KL-107a 存在的目的），把该条目的
   "状态"从 `OPEN` 改成 `SETTLED`，"我们的决定"部分从"尚未决定"改写成
   实际采用的"全64位原样拷贝"，并指向本任务作为决策落地记录。

## 约束

- **只改 `contracts/isa/spec.md` 和 `docs/wiki-deviations.md`**——不碰 wiki
  本身（wiki 是只读权威来源，我们的决定不能反过来"写回" wiki）、不碰
  QEMU/gem5/LLVM 源码、不碰 `docs/issues.yaml`。
- 不需要给这两条指令写 QEMU/gem5/LLVM 层面的任何实现——那是后续任务
  （建议命名 KL-108a 起，本任务不需要预先创建）。
- 引用计数处理的表述必须清楚区分"这是 wiki 原文"还是"这是本任务的
  spec-decision"，不能含糊其辞让读者误以为 wiki 本来就这样写。
- 完成后必须在任务文件里写「完成区」+ subagent 自审「审阅记录」，不需要
  嵌套 subagent，不需要独立 reviewer（架构师会亲自核对每一处新增内容的
  编码计算是否正确、格式是否与 §4.2 等既有章节一致）。
- 不要 commit——留在工作区等架构师复核。

## 验收

- `python3 scripts/manifest_check.py` 通过（确认 spec.md 改动没有破坏 spec
  锁定校验，如果这个工具会检查 spec 内容哈希，需要相应更新，自行判断）。
- 新增的 Appendix A 编码行手工验算：`0110-0xxx` 行第 8 列（`xxxx-x111`）
  = `01100111` = `0x67`；`0110-1xxx` 行第 8 列 = `01101111` = `0x6F`——
  与本任务背景部分给出的编码一致，需要在完成区展示这个验算过程。
- 新增内容风格（标题层级、代码块、Encoding/Alignment/Legality 小节顺序、
  wiki 引用格式 `[wiki §xxx Lyyy]`）与 §4.2 `ldmo-rb`/`stmo-rb` 逐项对齐，
  不引入新的格式惯例。
- `docs/wiki-deviations.md` 第8条按上面目标4更新。

## 参考指针

- `docs/reviews/kernel-regras-ldmo-stmo-semantics-20260725.md`（KL-106a
  完整调研，本任务的直接依据）
- `docs/reviews/kernel-regras-save-restore-20260721.md`（KL-105a，方案A的
  原始推荐）
- `docs/wiki-deviations.md` 第8条（本任务要更新状态的地方）
- `contracts/isa/spec.md` §4.2（`ldmo-rb`/`stmo-rb` 的 formalize 写法，本
  任务的直接格式模板）、§7（M1 Excluded 表，本任务要改的地方）、
  Appendix A.1.9/A.1.10/A.1.11（现有 opcode 编码表格式）
- `~/DADAO-wiki/SimRISC-02-地址类指令.md` 第9-21、47-63行（RA 访问权威定义，
  架构师已核对准确）
- `~/DADAO-wiki/SimRISC-00-指令系统设计.md` 第89、103-104行（opcode 布局表，
  架构师已核对 `0x67`/`0x6F` 编码准确）

---

## 完成区

**状态**：完成（2026-07-25），未 commit。

**实际改动**：

- `contracts/isa/spec.md`
  - §2.8 M1-covered opcode map 新增 `ldmo-ra`（row `01100`, col `111`）
    和 `stmo-ra`（row `01101`, col `111`）。
  - §4 新增 §4.9 `RA Multi Load/Store (rrri)`，正式定义 syntax、字段映射、
    EA、8 字节逐元素对齐/MALIGN、`immu6` 与 RA bank 边界合法性/ILLI，
    以及按 `i` 递增逐对先读后写。
  - §4.9 明确每个 RA 槽位按完整 64 位原样搬移，`bits[63:48]` 不清零、
    不校验、不特殊处理；该句明确标为 `KL-107a, 2026-07-25`
    spec-decision，并说明 wiki 未定义此字段行为。
  - §7 删除 `RA memory access` 排除行，保留 `RA register move`
    （`rd2ra`/`ra2rd`）排除行不变。
  - Appendix A.1.10/A.1.11 分别新增 `0x67 ldmo-ra` 和 `0x6F stmo-ra`
    的 `rrri` 编码记录。
- `docs/wiki-deviations.md`
  - 只对既有未提交的第 8 条做 KL-107a 增量：写入用户确认的完整 64 位
    原样搬移决定，明确它不是 wiki 原文，把状态 `OPEN` 改为 `SETTLED`，
    并指向 `contracts/isa/spec.md §4.9`。
- 本任务文件
  - 填写本完成区和下方 subagent 自审记录。

**验证结果**：

- `python3 scripts/manifest_check.py`：PASS
  - `spec: 9f378f4426e131903d60a208766086ae74a53c89 (frozen)`
  - `enabled components: llvm, qemu, gem5, llvm-test-suite, embench, musl`
  - `references: 6`
  - `manifest validation: PASS`
- `git diff --check`：PASS（无输出）。
- 手工编码验算：
  - `0110-0xxx` row 的第 8 列：`01100 || 111 = 01100111 = 0x67`
  - `0110-1xxx` row 的第 8 列：`01101 || 111 = 01101111 = 0x6F`

## Subagent 自审：审阅记录

- 范围：本次只修改
  `contracts/isa/spec.md`、`docs/wiki-deviations.md` 和本任务文件；
  未修改 KL-106a、review、manifest、issues、wiki、QEMU、gem5、LLVM 或其它
  文件，且未 commit。
- 既有改动保护：保留工作树中的 KL-106a、wiki-deviations 第 8 条原始补录、
  review 和无关未跟踪文件；对 wiki-deviations 仅追加第 8 条的 KL-107a
  决策落地增量。
- 内容逐项核对：
  - §2.8、§4.9、§7 和 Appendix A 的 opcode、格式与字段一致；
  - `0x67`/`0x6F` 的 `mask=0xFF000000`、`value=op<<24` 正确；
  - EA、8 字节 MALIGN、范围 ILLI、递增逐对先读后写均已写明；
  - 64 位原样搬移被明确标为 2026-07-25 项目 spec-decision，未冒充 wiki
    原文；
  - §7 的 RA memory exclusion 已移除，RA register move exclusion 原文保留。
- 协作：按任务要求未启动 nested subagent，也未调用独立 reviewer。
- 结论：自审通过，等待架构师复核。

## 架构师复核（2026-07-25）

**结论：Accepted，无阻塞 finding。**

- 本节由 parent Codex 在实现 subagent 返回并关闭后实际执行，不沿用
  subagent 预填结论。独立对照 manifest pin
  `9f378f4426e131903d60a208766086ae74a53c89` 的 wiki：
  - `SimRISC-00-指令系统设计.md` 第 89、103–104 行确认
    `01100 || 111 = 01100111 = 0x67`、`01101 || 111 = 01101111 = 0x6F`；
  - `SimRISC-02-地址类指令.md` 第 47–63 行确认 `rrri` 字段角色、8 字节
    MALIGN、`immu6=0`/RA bank 越界 ILLI，以及按序号递增逐对先读后写。
- `contracts/isa/spec.md §4.9` 对 `bits[63:48]` 的完整 64 位原样搬移规则
  明确标注为 `KL-107a, 2026-07-25` 项目 spec-decision，并明确 wiki 对该
  字段行为沉默，没有把项目决定冒充 wiki 原文。
- §2.8、§4.9、§7、Appendix A.1.10/A.1.11 彼此一致；RA memory exclusion
  已移除，RA register move exclusion 保持不变。
- 范围复核：相对任务下发前基线，本任务只触及获准的
  `contracts/isa/spec.md`、`docs/wiki-deviations.md` 第 8 条和本任务文件；
  KL-106a、review、manifest、issues、wiki、QEMU、gem5、LLVM 及无关结果文件
  均未被本任务改动；所有组件仓库保持 clean。
- 架构师独立复跑：
  - `python3 scripts/manifest_check.py`：PASS；
  - `python3 scripts/check_issues.py`：PASS（Open 24 / Closed 43 /
    Total 67）；
  - `git diff --check`：PASS；
  - 本未跟踪任务文件单独 whitespace 检查：PASS；
  - 手工编码验算结果仍为 `0x67`/`0x6F`。
