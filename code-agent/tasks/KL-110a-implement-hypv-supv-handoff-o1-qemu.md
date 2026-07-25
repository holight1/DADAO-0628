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
