# KL-110a：在 QEMU 里实现 hypv→supv 移交 O1（`cfx2rc`/`escape` 最小语义）

**执行环境**：本地 subagent，只改 `.work/source/qemu`

## 背景

`KL-101a`/`KL-102a`（2026-07-21，架构师已逐条核对 wiki 原文确认可信，见
`docs/reviews/kernel-hypv-supv-handoff-20260721.md`/
`docs/reviews/kernel-cfx-state-patch-surface-20260721.md`）确认：QEMU/gem5
目前都**没有真实的特权移交**，只有 host-side `cfx_smon` syscall 捷径。K1
需要先补上 HBI §3 规定的最小 hypv→supv 移交序列，这是内核能在 supv 模式
运行的前提（不是可选项——HBI §3 规定硬件复位永远先进 hypv，不补这段就没有
任何路径能让代码跑在 supv）。`KL-102b`（已 commit）已经把状态容器
（`inner_run_mode`/`inner_cfx_code`/`inner_cfx_mask`/`cfx_power_frame`）加进
QEMU 的 `CPUArchState`，reset 时初始化为 hypv/power/全1 mask——本任务是
KL-102a 建议顺序里的下一步（"先加状态容器→再做O1→再做O2→最后加验收向量"）。

**wiki 原文权威依据**（架构师已亲自核对，行号准确）：
- `DADAO-wiki/DADAO-23-HBI-超管系统二进制接口.md` 第29-64行：hypv→supv
  最小移交序列——12 条 `cfx2rc cfx_<name>_hypv_cg_reg_deleg, rd2`（`rd2=0`，
  清除 delegation；12 个 cfx：umon/jmon/smon/ptw/tlb/cache/hart/llc/pmem/
  timer/uart/power，**不含 hmon**）→写 `cfx_power_excp_prev_run_mode=2`
  （supv）→写 `cfx_power_excp_prev_cfx_mask=-1`（全1）→写
  `cfx_power_excp_cause_ip=target_addr`→`rb16=fdt_addr`（无则0）→
  `escape cfx_power, 0`。
- `DADAO-wiki/DADAO-12-SEE-主管系统运行环境.md` 第813-845行：`escape`
  的完整硬件语义——(0) 检查 escape cfx mask，被禁止则重定向 ILLI；
  (1) 恢复 `inner_cfx_mask ← cfx_<name>_excp_prev_cfx_mask`；(2) 恢复
  `inner_run_mode ← cfx_<name>_excp_prev_run_mode`；(3) `escape_num++`；
  (4) `inner_inst_pointer ← cfx_<name>_excp_cause_ip + (imms18<<2)`。
  **注意**：这段伪代码里 `escape` **从未写** `inner_cfx_code`——这是架构师
  已核实的真实 wiki 空白（`docs/reviews/kernel-hypv-supv-handoff-20260721.md`
  已记录），处置方式见下方目标第2条。
- `SimRISC-00-指令系统设计.md` 第105行：opcode 布局第 `0111-0xxx` 行，
  `cfx2rc` 在第4列 = `0111_0011` = `0x73`（格式 `crrr`）；`escape` 在第8列
  = `0111_0111` = `0x77`（格式 `ciii`）。

## 目标

1. **`contracts/isa/spec.md` 形式化**（参照 `KL-107a` 给 `ldmo-ra`/`stmo-ra`
   formalize 的写法和位置约定）：
   - §7 M1 Excluded：把 `cfx2rc`、`escape` 从"System cfx"排除行移出
     （`trap`、`cfx2rd`、`cfxld`、`cfxst` 保留排除——本任务不涉及）。
   - 新增正式指令定义（编码 `0x73`/`0x77`，格式分别是 `crrr`/`ciii`，
     具体字段布局参照 wiki `SimRISC-00`/`SimRISC-02`/`SimRISC-04` 里
     `crrr`/`ciii` 格式的通用字段定义——**不要凭空猜格式字段**，先读
     wiki 里这两种格式的通用定义章节）。
   - Appendix A：`0111-0xxx`/`0111-1xxx`（自行核对具体是哪个 row，
     `escape` 在 `0111-0xxx` 的第8列，`cfx2rc` 在同 row 第4列）新增对应
     行。
   - `inner_cfx_code` 未被 escape 恢复这一 wiki 空白：登记进
     `docs/wiki-deviations.md`（本任务范围内的 spec-decision，采用
     `KL-102a` 报告已经给出的处置建议——如实引用该报告的原话，不要自己
     重新发明结论）。
2. **QEMU 实现**（参照 `KL-102a` 报告 §2.1 给出的精确承载点建议，不要
   自己另设计一套）：
   - `insn.decode`：新增 `cfx2rc`（`0x73`）/`escape`（`0x77`）pattern。
   - `translate.c`：新增翻译函数。
   - `helper.c`：新增集中式 `cfx2rc`/`escape` 状态转移 helper——所有
     prev/cause 写入和恢复只从这一处完成（`KL-102a` 报告原话："在
     helper.c/.h 增加集中式 cfx2rc、escape、enter/fault helper；所有
     prev/cause 写入和恢复只从这一处完成"）。
   - `cpu.c`：`cfx2rc` 只需要支持清除 delegation（写 0）这一种用法——
     本任务**不要求**实现完整的 delegation 读写语义，只要能让 HBI §3
     那 12 条 `cfx2rc cfx_*_hypv_cg_reg_deleg, rd2`（`rd2=0`）产生正确的
     "清除该 cg 的 delegation 标记"效果即可（这个标记本身在本任务里可以
     先只是一个内部状态位，不需要接完整的权限检查逻辑——权限检查是 O2
     阶段的范围，`KL-102a` 报告已经把 O1/O2 明确分开）。
   - `escape cfx_power, 0`：恢复 `inner_cfx_mask`/`inner_run_mode`，
     `escape_num++`，跳到 `cause_ip + imms18*4`。**`inner_cfx_code` 按
     目标1的 spec-decision 处理**（不要凭直觉自己决定，按 spec.md 里
     写清楚的规则实现）。
   - **不要**触碰现有的 `EXCP_CFXTRAP`/host-side `cfx_smon` syscall 捷径
     （`ML-002a` 起的整条 syscall 实现）——那是独立、保留的 legacy 路径，
     `KL-102a` 报告明确要求"不删除也不重写现有 shortcut"。
3. **Oracle O1 验证**（`KL-102a` 报告 §3.1 已给出精确定义，直接照此实现
   测试，不要自己重新设计验收标准）：
   - 在 HBI reset vector 可取指区域放一段 handoff stub（12条delegation
     清除 + prev_mode=2 + prev_mask=全1 + cause_ip=supv_entry地址 +
     rb16=0 + `escape cfx_power,0`）和一个物理 `supv_entry`（写唯一
     marker 并停止）。
   - 双后端预期：可观测 trace 显示 `reset(hypv) → escape(power) →
     supv`，PC 落在 `supv_entry`，不是仅显示进程退出或 host syscall
     成功。**本任务只做 QEMU**，gem5 是后续独立任务。

## 约束

- **禁止**对 `.work/source/qemu` 做 `git rebase`/`git am` 重放整条历史/
  `git reset --hard`。只允许在当前 HEAD 基础上新增普通 `git commit`。
- **不要实现 O2**（越权/被 mask 的负例）——那是下一个独立任务，`KL-102a`
  报告已经明确把 O1/O2 分开设计。
- **不要实现 cfx_smon 真实 guest handler**（那是 KL-103a 范围，`KL-102a`
  报告已经明确排除）、**不要实现 MMU/完整 CFX/嵌套 trap**。
- 完成后立即导出 patch，追加进 `components/qemu/patches/series`。
- 完成后必须在任务文件里写「完成区」+ 自审「审阅记录」（含逐条 finding +
  判决）。

## 验收

- Oracle O1（成功移交）在 QEMU 上可观测通过：PC 落在 `supv_entry`，
  `inner_run_mode=supv`，marker 被正确写入。
- `python3 tools/run_differential.py`：AGREE 数与当前基线一致、DIVERGE=0
  （这条改动此前不在差分向量集合里，预期这个数字本身不变）。
- `python3 scripts/manifest_check.py`/`check_issues.py`：PASS。
- QEMU 侧改动用**普通** `git commit` 落地，`git format-patch` 导出对应
  patch，追加进 `series`；独立验证可在干净 pin-commit checkout 上 `git am`
  成功，且 replay tree 与开发树 tree hash 一致。
- 如果诊断后发现工作量远超预期（比如 `crrr`/`ciii` 格式字段定义比预想
  复杂、或者 delegation 状态位设计牵涉更大改动），如实停下报告，登记
  `docs/issues.yaml`，不要勉强拼一个高风险的大改动。

## 参考指针

- `docs/reviews/kernel-hypv-supv-handoff-20260721.md`（KL-101a，HBI §3/
  SEE §5 权威原文引用，架构师已核对准确）
- `docs/reviews/kernel-cfx-state-patch-surface-20260721.md`（KL-102a，
  精确的 QEMU 承载点设计 + O1/O2 范围划分，本任务的直接依据）
- `code-agent/tasks/KL-107a-formalize-ldmo-ra-stmo-ra-spec.md`（spec
  formalize 的格式模板）
- `code-agent/tasks/KL-108a-implement-ldmo-ra-stmo-ra-qemu.md`（QEMU
  实现+验证方法论模板）
- `~/DADAO-wiki/DADAO-23-HBI-超管系统二进制接口.md`（第29-64行，移交
  序列原文）
- `~/DADAO-wiki/DADAO-12-SEE-主管系统运行环境.md`（第678-706行异常进入、
  第813-845行 escape 硬件语义原文）
- `~/DADAO-wiki/SimRISC-00-指令系统设计.md`（opcode 布局表 + `crrr`/
  `ciii` 格式定义）
- `.work/source/qemu/target/dadao/`（现有 `cpu.h`/`cpu.c`/`insn.decode`/
  `translate.c`/`helper.c` 结构，`KL-102b` 已加的状态容器代码）

---

## 完成区（2026-07-25）

**状态**：已完成。O1（成功移交）在 QEMU 上可观测通过；spec 形式化 +
wiki-deviations 记录 + QEMU 实现 + 独立复现验证全部完成。

### wiki 原文复核（动手前，非重新调研）

亲自读了任务文件引用的三处 wiki 原文，确认行号和内容准确：

- `DADAO-23-HBI-超管系统二进制接口.md` 第29-66行：hypv→supv 移交序列，
  12 条 `cfx2rc cfx_*_hypv_cg_reg_deleg, rd2`（umon/jmon/smon/ptw/tlb/
  cache/hart/llc/pmem/timer/uart/power，不含 hmon）→
  `cfx_power_excp_prev_run_mode=2` → `cfx_power_excp_prev_cfx_mask=-1` →
  `cfx_power_excp_cause_ip=target_addr` → `rb16=fdt_addr` →
  `escape cfx_power,0`——与任务文件引用完全一致。
- `DADAO-12-SEE-主管系统运行环境.md` 第813-845行：escape 硬件语义 5 步
  （0 检查 escape mask、1 恢复 mask、2 恢复 mode、3 escape_num++、
  4 跳转 `cause_ip+imms18<<2`）——确认**从未写 `inner_cfx_code`**，且
  第678-811行"异常进入流程"对照显示只有进入时才写
  `inner_cfx_code<=temp_cfx_code`，退出没有对称操作。
- `SimRISC-00-指令系统设计.md` 第87-106行 opcode 表：`0111-0xxx` 行第4列
  `cfx2rd(0x72)`/第4列实为 `cfx2rc`——手工验算 `01110|011=0x73`
  （cfx2rc）、`01110|111=0x77`（escape），与任务文件一致。

补充读了任务文件未展开但明确要求先读的两处（`crrr`/`ciii` 通用字段定义、
`(cg,rc)` 编号来源），发现任务文件本身没有给出的关键信息，属于本次
实现必需的深挖，不是范围外调研：

- `SimRISC-04-系统类指令.md` §寄存器传输指令（第72-103行）：`crrr` 标准
  4 操作数写法 `cfx2rc cfx_<cfxname>, cghb, rchc, rdhd`，以及**简化写法**
  `cfx2rc cfx_<cfxname>_<regname>, rdhd` 由汇编器查表展开——HBI §3 stub
  用的正是简化写法，必须找到 `cfx_*_hypv_cg_reg_deleg`（cg=3,rc=12，
  `DADAO-13-HEE §1` 第24行）和 `cfx_power_excp_prev_run_mode`/
  `_prev_cfx_mask`/`_cause_ip`（cg=5,rc=0/1/3，`DADAO-12-SEE §3` 第
  357-360行）的真实 `(cg,rc)` 编号才能手工编码测试向量，否则无法验证。

### `contracts/isa/spec.md` 改动

- §2.8 M1-covered opcode map：新增 `01110/011 cfx2rc-crrr`、
  `01110/111 escape-ciii` 两行。
- §7 M1 Excluded："System cfx" 行从
  `trap, escape; cfx2rd, cfx2rc; cfxld, cfxst` 改为
  `trap; cfx2rd; cfxld, cfxst`（`cfx2rc`/`escape` 移出排除，`trap`/
  `cfx2rd`/`cfxld`/`cfxst` 保留排除，本任务不涉及）。
- 新增 `## §8 System / CFX Instructions (crrr / ciii)`（放在 §7 之后、
  Appendix A 之前，不重排 §1-§7 现有编号——`docs/adr/0014-*`、多份
  review 已经用"spec §7"指代 M1 Excluded，重排会造成这些引用失效）：
  - §8.1 `cfx2rc`/`cfx2rd` 完整语义（编码、`(cg,rc)` 寻址、named-register
    简化语法、CFXREG/reserved-cfxcode 的 wiki 全量语义）+ 明确标注 QEMU
    O1 子集范围。
  - §8.2 `trap`/`escape` 完整语义（编码 + SEE §5 exception-exit 流程
    步骤0-4逐条列出）+ wiki gap 说明（`inner_cfx_code` 未被 escape 恢复）。
  - §8.3 HBI §3 handoff 工作示例的 `(cg,rc)` 对照表（不重复抄写 HBI 原文，
    只给编号映射，指回 HBI §3 权威原文）。
- Appendix A 新增 A.1.12（Row 0111-0xxx）：`0x73 cfx2rc`/`0x77 escape`
  两条编码记录，并注明 `0x72`/`0x76` 同 row 但仍排除。

**关键设计取舍**：spec.md 按 wiki **完整架构语义**形式化（不是只写 QEMU
实现了的子集），QEMU 实现明确只做 O1 子集——这个不对称是刻意的，spec.md
里用醒目的方括号标注（"QEMU's current implementation only covers the
subset..."）说清楚，不会误导读者以为 QEMU 已经实现了完整 CFXREG/权限
检查。这个做法对齐 KL-107a→KL-108a 先 spec 后 QEMU 分步落地的项目惯例
（spec 领先、QEMU 滞后是被接受的正常过渡态，不是缺陷）。

### `docs/wiki-deviations.md` 新增第9条

`escape` 退出流程从未赋值 `inner_cfx_code` 这一 wiki 空白——独立复核
wiki 原文后发现这不只是"漏写一行"，而是 SEE §3 cg5 根本没有配套的
`excp_prev_cfx_code` 寄存器可供恢复（`inner_run_mode`/`inner_cfx_mask`
各自有 `prev_run_mode`/`prev_cfx_mask`，唯独 cfx_code 没有对应寄存器）。
决定：`escape` 不修改 `inner_cfx_code`（保持不变）。**状态标为 OPEN**
而非 SETTLED——因为这个读法只在 O1（单层、reset 后从未经历过 trap 进入）
场景下被验证过，多层 `trap→trap→escape` 调用链下是否仍然正确未经测试，
如实标注为待续开放问题。

### QEMU 实现（`.work/source/qemu`）

严格按 KL-102a 报告 §2.1 给出的承载点：

- `cpu.h`：新增 `cfx_hypv_cg_reg_deleg[64]` 状态数组
  （HEE §1 cg3/rc12），复用已有 `cfx_power_frame`（KL-102b）。
- `cpu.c`：reset 时初始化 deleg 数组为全1（HEE §1 init 值）；新增
  `CPU_LOG_INT` reset trace（仅 `-d int` 时输出，默认静默）。
- `insn.decode`：新增 `cfx2rc`（`0x73`，复用 `@rrrr` 模板——crrr 与 rrrr
  位布局完全相同）、`escape`（`0x77`，复用 `@riii` 模板，与 `trap` 同一
  手法）两条 pattern。
- `translate.c`：`trans_cfx2rc`/`trans_escape` 只做操作数提取和 helper
  调用，不在 TCG 里散落状态写入（按 KL-102a 报告"承载点"设计要求）；
  `escape` 用 `DISAS_JUMP`（非 `DISAS_NORETURN`——escape 不像 trap 那样
  退出 CPU loop，是正常控制流延续，模式与 `trans_jump_r`/`trans_ret`
  一致）。
- `helper.c`/`helper.h`：新增集中式 `helper_cfx2rc`/`helper_escape`——
  所有 prev/cause 写入和恢复只从这两个函数完成：
  - `cfx2rc`：只识别两种 `(cg,rc)` 组合——`(3,12)` 写 deleg 数组（bit3
    硬件强制置1）、`cfx_power` 的 `(5,0/1/3)` 写 power frame 三个字段；
    其它组合静默 no-op（不发明未实现的存储结构）。
  - `escape`：只对 `cfxcode==power` 从 power frame 恢复 mask/mode 并跳转
    `cause_ip+imms18*4`；`inner_cfx_code` 按 wiki-deviations #9 的决定
    不修改；escape mask 权限检查（SEE §5 步骤0）明确不实现（O2 范围）；
    新增 `CPU_LOG_INT` trace 记录 mode 转换，格式含 cfxcode/mode前后值/
    mask/pc。
- **未触碰** `EXCP_CFXTRAP`/host-side `cfx_smon` syscall 捷径——`cpu.c`
  里 `EXCP_CFXTRAP` 分支一行未改。

### Oracle O1 验证

新增 `tests/scripts/gen_kl110a_o1_probe.py`（仿 `gen_trampoline.py`/
`gen_rasof_asm.py` 惯例，未 commit，留工作区）：手工编码 HBI §3 完整
stub（12条 cfx2rc deleg + 3条 cfx2rc power frame + escape），放在 ROM
reset vector（`0x00100000`）；stub 结束到 `supv_entry`（`0x00100200`）
之间填充 `unimp`（毒化区，落地错误目标会触发 ILLI 而非静默通过）；
`supv_entry` 写 marker 到 RAM 后**读回比对**（不是只信任 store 没
fault），比对结果编码进退出码本身（42=真正匹配成功，0x99=读回不一致）。

**正例结果**（`.work/evidence/KL-110a-o1-handoff.bin/.trace.log`）：
```
QEMU exit code: 42
dadao: reset mode=hypv cfx_code=power(63) mask=all-1 pc=0x0000000000100000
dadao: escape cfx=63 mode 3->2 mask=0xffffffffffffffff pc=0x0000000000100200
```
PC 精确落在 `supv_entry`（`0x100200`）；`inner_run_mode` 3(hypv)→2(supv)；
marker 读回比对通过（否则会退出 0x99 而非 42）。

**负控制验证**（`.work/evidence/KL-110a-o1-negctrl.bin/.trace.log`，
故意把 `cause_ip` 改成毒化区里的地址 `0x100180`）：确认 exit=0x82（ILLI，
命中 `unimp`），trace 显示 escape 确实跳到了错误目标
`pc=0x0000000000100180`——证明毒化区机制真实生效，正例的 exit=42 不是
永真式通过，而是有区分度的断言。

### 验证结果

- Oracle O1：PASS（见上）。
- `python3 tools/run_differential.py`：`AGREE(4-way)=200`，`DIVERGE=0`
  ——与改动前基线完全一致（cfx2rc/escape 尚未进差分向量集合，预期数字
  不变）。
- `python3 scripts/manifest_check.py`：PASS。
- `python3 scripts/check_issues.py`：PASS（Open 24/Closed 43/Total 67，
  无变化——本任务未新增/关闭 issue）。
- `python3 scripts/validate_encoding.py tools/opcodes.yaml`：91 records
  OK（新增 `cfx2rc`/`escape` 2 条）。
- `python3 scripts/check_wiki_refs.py --profile isa`：`OVERALL: PASS`
  （`Check 2 missing ref: 0`——过程中修过一次自己的行内引用换行问题，
  见「审阅记录」finding 1）。
- `python3 scripts/check_qfc_coverage.py`：`0x73`/`0x77` 不再出现在
  "only in wiki" 缺口列表。
- `python3 scripts/check_wiki_drift.py`：PASS。
- `python3 scripts/check_legality_matrix.py`：`QEMU-BUG(check-1)=0`，
  `opcodes-漏(check-2)=0`（`cfx2rc`/`escape` 的 `legality: []` 未产生
  新测试单元，符合"不实现权限/legality 检查"的范围设计）。
- `lit tests/lit/E2E`：**81/81 PASS**（confirm 无回归）。
- QEMU 侧改动：普通 `git commit`（`72cba5f`，detached HEAD，与既有 pin
  工作流一致），`git format-patch` 导出
  `components/qemu/patches/0024-target-dadao-implement-cfx2rc-escape-O1-hypv-supv-ha.patch`
  并追加进 `series`；commit 与导出 patch 的 stable patch-id 均为
  `6eb9d01465a97b975820d6860269f06bd64028d9`；独立在 manifest pin
  （`385b0a7d9785c8f3ac7b116d7f31d61502b55183`）干净 checkout 上依次
  `git am` 全部 24 个 patch 成功，replay tree 与开发树 tree 均为
  `480dca4c7116ef09b057394bd788ae86750e4bee`，临时 worktree 已清理。

### 范围边界确认

- 未实现 O2（越权/被 mask 负例）——`escape` 的 mask 检查、`cfx2rc` 的
  CFXREG/reserved-cfxcode 路由均未实现，spec.md §8 开头方括号已醒目
  标注。
- 未碰 gem5、未实现真实 `cfx_smon` guest handler、未实现 MMU。
- 未触碰 `EXCP_CFXTRAP`/host-side syscall 捷径任何一行。
- 未 commit 到 DADAO-0628 根仓库——`contracts/isa/spec.md`、
  `docs/wiki-deviations.md`、`tools/opcodes.yaml`、
  `tests/scripts/gen_kl110a_o1_probe.py`、`.work/evidence/KL-110a-*`、
  本任务文件均留在工作区等架构师复核。

---

## 自审：审阅记录

**判决**：自审通过，无阻断 finding。

- **Finding 1（自查发现并修复，格式问题非语义问题）**：初版 §8 文字里
  多处"断言 + wiki 引用"跨行书写（长句手动换行导致 `[wiki ...]`
  引用括号落在断言所在行的下一行），`check_wiki_refs.py --profile isa`
  Check 2 报了 3 处硬错误（`spec.md:1037/1039/1041`）——与 KL-107a
  架构师复核记录的 finding 2（"Alignment 行引用写在下一行"）是同一类
  问题。已把 §8 全部改成"断言与其 wiki 引用同一行"（即使行较长），复跑
  `Check 2 missing ref: 0`，`OVERALL: PASS`。
- **wiki 引用逐项复核**：§8.1/§8.2/§8.3 里每一条 `[wiki §... Lxx–Lyy]`
  行号区间，本次实现前都亲自用 Read 工具打开对应 wiki 文件核对过内容
  （见完成区"wiki 原文复核"小节），不是照抄任务文件字面行号——任务文件
  给的行号（HBI 29-64、SEE 813-845、SimRISC-00 opcode 表）与我独立核对
  结果一致；额外为 SimRISC-04/HEE/SEE cg5 的 `(cg,rc)` 编号做了任务文件
  未展开的补充核实（这是实现 crrr 编码所必需，不是随意扩大范围）。
- **编码手工验算**：`01110||011=01110011=0x73`（cfx2rc）；
  `01110||111=01110111=0x77`（escape）——与 spec.md/opcodes.yaml/QEMU
  三处记录一致；Appendix A mask/value 用 `0xFF000000`/`op<<24` 规则，
  与既有非-MISC-Norm 条目格式一致。
- **QEMU 实现范围核对**：
  - `grep -n "EXCP_CFXTRAP" target/dadao/cpu.c` 确认该分支代码逐字未改
    （`git diff` 显示 `cpu.c` 只新增了 reset 循环里一行deleg数组初始化
    +一段独立的 trace 打印，`EXCP_CFXTRAP`/`case 63/64/66/93/94/214/
    215/222/226` 等 host syscall responder 代码零改动）。
  - `helper_cfx2rc`/`helper_escape` 是新增函数，未修改
    `helper_trap`/`helper_ras_push`/`helper_ras_pop`/
    `dadao_raise_exception` 任何一行。
  - `translate.c` 只在 `trans_trap` 后面新增两个函数，未修改
    `trans_trap` 本身或任何既有 `trans_*` 函数体。
- **正例/负例证据独立性核对**：负控制（`KL-110a-o1-negctrl.*`）不是
  凭空捏造的"应该失败"断言，而是真实跑出 `exit=0x82` 且 trace 显示
  `pc=0x100180`（负例故意设置的错误目标），证明毒化区机制和 escape 的
  `cause_ip` 计算路径都是真实生效，不是巧合通过。
- **"marker 读回比对"设计核对**：探针没有单纯依赖"store 没有 fault"作为
  marker 正确性证据，而是显式 `ldo` 读回、`xor` 比对、`csz` 把比对结果
  编码进退出码——`emit_state_compare` 里已有的项目内既有模式（`build_
  test_binary.py`），复用而非另造一套。
- **回归范围核对**：`lit tests/lit/E2E` 81/81、`run_differential.py`
  AGREE=200/DIVERGE=0（改动前后完全一致的数字，非巧合——cfx2rc/escape
  此前不在差分向量集合，改动理论上不该影响这个数字，实测确认符合预期）、
  `check_legality_matrix.py` QEMU-BUG=0——均为独立重跑，非沿用改动前的
  缓存结果。
- **未做事项确认**（对照约束逐条自查）：未对 `.work/source/qemu` 做
  `rebase`/`am` 重放历史/`reset --hard`（只有一次普通 `git commit`，
  patch 导出用的是独立临时目录 `/tmp/kl110a-patch`，验证复现用的是独立
  临时 worktree，均已清理）；未实现 O2；未碰 gem5；未碰 host cfx_smon
  handler；未碰 MMU；未 commit 到 DADAO-0628 根仓库。
