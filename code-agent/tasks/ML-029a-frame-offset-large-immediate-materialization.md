# ML-029a：修复栈帧偏移超出 imms12 范围时的静默环绕截断——通用正确性缺口，最高优先级

**执行环境**: 本地 subagent

**状态**: 已完成（独立 review Accepted）

## 硬约束（务必遵守，违反视为任务失败）

- **禁止**对 `.work/llvm` 做 `git rebase`/`git am` 重放整条历史/`git reset --hard`。
  只允许在当前 HEAD 基础上新增普通 `git commit`。
- **这是当前项目发现的最高优先级正确性问题**——不是 gcc-c-torture 的边缘情形，
  是任何栈帧使用超过约 2KB 的真实程序都可能静默触发的地址计算错误。请认真对待
  验收里"全量 gcc-c-torture 重扫"这一条，不要只验证 `pr56866.c` 一个用例就收尾。
- **本任务允许诊断优先，但根因已经由 `ML-027a` 完整定位到字节级**（见下方「背景」），
  本任务是**修复**任务，不是重新诊断——除非在实现过程中发现 `ML-027a` 的根因分析
  有遗漏/不准确之处，那种情况下如实报告，不要自己另起炉灶设计一套不同的修复思路。
- **完成后立即导出 patch**（不要延后）：`components/llvm/patches/0051-...patch`，
  追加进 `series`。
- 完成后必须在任务文件里写「完成区」+ subagent 自审「审阅记录」（含逐条 finding
  + 判决）。

## 背景（`ML-027a` 已诊断到字节级，本任务直接基于其结论修复）

`docs/issues.yaml` 的 `frame-offset-no-imms12-range-check-silent-wraparound`
条目（完整二分过程+字节级根因证据见该条目全文）：

`DADAOFrameLowering::emitPrologue`/`emitEpilogue`
（`llvm/lib/Target/DADAO/DADAOFrameLowering.cpp` 约43-45/60-62行）和
`DADAORegisterInfo::eliminateFrameIndex` 的全部6个 case
（`ADDI_RB_FI`/`LDO_FI`/`STO_FI`/`LDO_RB_FI`/`STO_RB_FI`，
`DADAORegisterInfo.cpp` 约91-168行）把 `StackSize`/`FrameOff`（`+GEPOff`）不做
范围检查直接 `.addImm(...)` 到 `ADDI_RBRRII`/`LDO_RRII`/`STO_RRII`——这三条指令
的立即数字段都是 `imms12`（12位有符号，`[-2048,2047]`，`contracts/isa/spec.md`
§2.2/§2.3）。`DADAOMCCodeEmitter::getImm12OpValue`
（`MCTargetDesc/DADAOMCCodeEmitter.cpp:112-125`）对立即数本身也没有 range assert，
直接 `static_cast<unsigned>(MO.getImm())`——超出范围时在**指令编码层**被静默按
12-bit 环回截断（`ML-027a` 已实测验证：真实 `StackSize=6192` 编码成 `+2000`，
不但截断、**符号还翻了**，栈指针调整方向完全反了）。

`eliminateFrameIndex` 的函数签名已经带了 `RegScavenger *RS` 参数
（`DADAORegisterInfo.h:35`），但函数体内完全没有使用它。

## 可复用的既有基础设施（架构师已确认存在，供设计修复方案参考）

- **GPRD（RD bank）大立即数物化已有先例**：`DADAOInstrInfo.cpp` 的
  `CONST_WYDE` pseudo 展开（约145-166行）用 `SETZW_RWII`（首个非零 wyde）+
  `ORW_RWII`（后续非零 wyde）逐 16 位物化任意 64 位常量到一个 RD 寄存器——
  这是本任务"大立即数物化"这半步要复用的既有模式（不是重新发明）。
- **跨 bank 加法已有指令**：`ADDRB_ORRR`（`DADAOInstrInfo.td:307`，
  `add $rbhb, $rbhc, $rdhd`，语义 `rbhb = rbhc(RB) + rdhd(RD)`）——把一个
  RD 寄存器里的值加到一个 RB 基址寄存器上、结果仍是 RB——这正是本任务需要的
  "把物化好的大偏移量加到帧基址寄存器 RB1 上，得到新的有效 RB 地址"这一步。
- `LDO_RRII`/`STO_RRII` 的基址操作数都是 `GPRB`（`imms12` 之外的基址寄存器
  永远是 RB bank，不论加载/存储的值本身是 RD 还是 RB 类型）——所以"物化偏移量
  到 RD 寄存器 + `ADDRB_ORRR` 得到新 RB 基址 + 用新基址+立即数0 做原指令"这一套
  组合手法对 `LDO_FI`/`STO_FI`/`LDO_RB_FI`/`STO_RB_FI`/`ADDI_RB_FI` 应该是统一
  适用的模式，不需要针对每个 case 发明不同的技巧。

## 目标

1. 在 `DADAOFrameLowering::emitPrologue`/`emitEpilogue` 和
   `DADAORegisterInfo::eliminateFrameIndex` 的全部6个 case，对将要写入 `imms12`
   字段的偏移量做 `isInt<12>` 检查；不满足时改用"大立即数物化+跨 bank 加法"的
   兜底路径（而不是直接编码，参照上面「可复用的既有基础设施」）。
2. **正确使用 `RegScavenger`**（`eliminateFrameIndex` 签名里已有的 `RS` 参数）
   在 PEI 阶段安全借用一个临时寄存器做物化中间结果，不能破坏当前活跃的寄存器——
   这是本任务里"需要仔细设计、不能照抄"的部分，具体怎么用 `RS->scavengeRegister`
   之类接口、借用哪个寄存器类，需要你自己读 LLVM 里其它 in-tree target（比如
   RISC-V/ARM 在 `eliminateFrameIndex` 里对大偏移量的处理方式）作为参照，理解清楚
   `RegScavenger` 的正确用法再动手，不要凭空猜测 API。
3. `emitPrologue`/`emitEpilogue` 阶段（不经过 `eliminateFrameIndex`，是直接
   `BuildMI` 构造 `ADDI_RBRRII`）的大立即数兜底，不需要 `RegScavenger`（此时函数
   刚开始/刚结束，没有 PEI 意义上的"任意时刻寄存器分配状态"问题，可以直接用一个
   预留的临时 RD 寄存器做物化中间值——确认此时可以安全使用哪个寄存器不会破坏
   调用约定/活跃参数）。
4. **验证不能只测 `pr56866.c`**：这个 bug 影响面是"任意大栈帧函数"，需要构造
   一批新的判别性测试（不同栈帧大小跨越 `2047`/`4095`/`-2048` 等边界值，覆盖
   `emitPrologue`/`emitEpilogue` 和 `eliminateFrameIndex` 全部6个 case 各自的
   大偏移场景），确认修复后每种情形都产出正确的地址计算（不是"编译链接跑通"就
   算数，要有真实的读写判别性校验，参照
   `feedback_volatile_needed_for_memory_verification_tests` 教训，用 volatile
   访问 + 负控制确认测试真的会抓错）。

## 验收

- 新增判别性测试�covering `emitPrologue`/`emitEpilogue`+6个`eliminateFrameIndex`
  case 各自的大偏移场景，双后端真实验证正确性（不只是不崩溃）。
- `pr56866.c` 本身：`tests/scripts/gcc_torture_sweep.py --filter pr56866` 重跑，
  确认从 `TIMEOUT` 变为 `PASS`（双后端）。
- **全量 gcc-c-torture 重扫**（`tests/scripts/gcc_torture_sweep.py`，全量约16秒，
  成本很低没有理由跳过）：报告新的 PASS/FAIL_COMPILE/FAIL_LINK/FAIL_RUN/TIMEOUT
  分布，和当前基线对比（`ML-026a` 原始 1328/113/217/49/1，`ML-028a` 补软浮点符号
  后应该已经有提升，以你落地前实际重跑记录的当前基线为准）——**这一步是为了验证
  ML-027a 指出的"侥幸PASS"风险**：修复大立即数物化后，任何此前"运气好没撞上关键
  数据"的用例应该继续PASS或变成真正的PASS，不应该有此前PASS的用例在本次修复后
  反而失败（如果有，说明本次修复本身引入了新问题，必须查清楚不能忽略）。
- 全量 `llvm-lit tests/lit/E2E/`：零回归（当前基线以落地前重新跑一次记录的
  当前值为准）。
- `python3 tools/run_differential.py`：AGREE 数与当前基线一致、DIVERGE=0（本任务
  是 CodeGen 正确性修复，不改指令语义本身，但必须实跑验证不假设）。
- `python3 scripts/manifest_check.py`/`check_issues.py` 通过；关闭
  `frame-offset-no-imms12-range-check-silent-wraparound` 条目（若真正解决，
  移入 `docs/issues-archive.yaml`）。
- LLVM 侧改动用**普通** `git commit` 落地，`git format-patch` 导出为
  `components/llvm/patches/0051-....patch`，追加进 `series`；独立验证可在干净
  pin-commit checkout 上 `git am` 成功。
- 如果诊断/实现过程中发现改动量/风险超出预期（比如 `RegScavenger` 的正确用法
  比预想复杂很多，或者发现还有其它指令也有同样的 `imms12` 静默截断问题）：
  允许如实报告扩大后的范围评估，不要为了"完成任务"匆忙上一个不完整/有风险的
  修复——参照 `ML-020a`/`ML-021a`/`ML-024a`/`ML-027a` 的一贯先例。

## 参考指针

- `docs/issues.yaml` `frame-offset-no-imms12-range-check-silent-wraparound`
  （`ML-027a` 完整二分过程+字节级根因证据，本任务的直接前置，务必完整重读）
- `llvm/lib/Target/DADAO/DADAOFrameLowering.cpp`（`emitPrologue`/`emitEpilogue`，
  约43-45/60-62行）
- `llvm/lib/Target/DADAO/DADAORegisterInfo.cpp`（`eliminateFrameIndex`，
  约91-168行，全部6个 case）、`DADAORegisterInfo.h:35`（`RS` 参数）
- `llvm/lib/Target/DADAO/DADAOInstrInfo.cpp` 约145-166行（`CONST_WYDE` pseudo
  展开，GPRD 大立即数物化的既有模式，本任务要复用的算法）
- `llvm/lib/Target/DADAO/DADAOInstrInfo.td:307`（`ADDRB_ORRR`，跨 bank 加法，
  RB+RD→RB，本任务需要的地址合成指令）、约359/373行（`LDO_RRII`/`STO_RRII`
  的基址操作数永远是 `GPRB`）
- `contracts/isa/spec.md` §2.2/§2.3（`imms12` 范围定义）
- `tests/scripts/gcc_torture_sweep.py`（全量重扫工具，`--filter` 可选单个用例）
- `feedback_volatile_needed_for_memory_verification_tests`（新测试涉及写读回
  校验要用 `volatile`）
- LLVM 其它 in-tree target（RISC-V/ARM）的 `eliminateFrameIndex` 对大偏移量的
  `RegScavenger` 用法，作为正确 API 使用范式参考

## 完成区

**状态**：已完成；独立 subagent review 已 Accepted。

### 根因确认与实现

- ML-027a 的字节级诊断正确：真正的 switch 共有 5 个 frame-index pseudo
  case（任务标题里的“6 个”是计数笔误），加上 prologue/epilogue 两条直接
  构造路径，均会把超范围值直接送入 signed imms12。
- LLVM 普通提交：
  - `245d4f42a5d8`（parent `3aa546d1d0cd`）：主体大 frame offset
    materialization；
  - `032fab81c9bf`（parent `245d4f42a5d8`）：独立集成检查发现
    small-frame + large-GEP/fixed-offset 在 RD 高压下缺少 emergency slot，
    以及显式 MIR 的 RB5 source/dest collision 后，新增的 spill-safe
    follow-up。
  两者均为普通 commit；未 amend、rebase、`git am` 或 reset 改写历史。
- `DADAOInstrInfo::materializeImm64` 复用既有 `SETZW` + `ORW` wyde 拼接法。
  `CONST_WYDE=0` 的既有行为保持不变。
- prologue/epilogue 对 `isInt<12>` 的小帧保留原单条 `ADDI_RBRRII`；
  大帧用 ABI-reserved、非 allocatable 且不承载参数/返回值的 RD2 物化有
  符号调整量，再用 `ADDRB_ORRR rb1,rb1,rd2` 调整 SP。
- PEI 的 5 个 pseudo 全部先检查最终 `FrameOff + GEPOff`。超范围时通过
  `RegScavenger::scavengeRegisterBackwards` 安全取得 allocatable RD 临时
  寄存器，物化完整偏移；通常以 reserved RB5 作为瞬时有效地址寄存器，
  再将原 load/store 改为相同 memory operand、立即数 0。若显式 MIR 的
  RB load/store value operand 本身是 RB5，则改用同为 reserved 的 RB6，
  避免地址物化提前覆盖 source/dest。`ADDI_RB_FI` 直接写原 destination
  RB。
- `processFunctionBeforeFrameFinalized` 不再只看
  `estimateStackSize > 2047`：它扫描五类实际 FI pseudo，并对尚未布局的
  local object 使用 `[0, estimated-frame-size] + GEPOff` 保守范围，对
  fixed object 使用其已知 offset + estimated frame + GEPOff。只要最终
  Total 可能超出 imms12，就预留 8-byte emergency scavenger slot。PEI
  将该 slot 放在最靠近 final SP 的位置，使其自身 spill/reload 保持小
  offset、不会递归物化；不可能走大 Total 的普通小帧仍不增加 slot。
- 顺带修正 DL-072a 后已过时的 varargs callee-save-area LLVM 测试：
  caller 负责统一保存区时，无 local 的 varargs callee 应保持 frame-free。

### 修改与导出

- LLVM：`DADAOFrameLowering.{cpp,h}`、`DADAORegisterInfo.{cpp,h}`、
  `DADAOInstrInfo.{cpp,h}`。
- LLVM 回归：`large-frame-offsets.{ll,mir}` 与
  `frame-lowering-stack-alignment.ll`。
- 运行回归：`tests/lit/E2E/frame_offset_large.test` 与
  `Inputs/frame_offset_large.c`。
- patch：
  `components/llvm/patches/0051-DADAO-materialize-large-frame-offsets.patch`
  与
  `0052-DADAO-make-frame-offset-scavenging-spill-safe.patch`，均已追加
  `series`。原计划单个 0051 扩为 0051+0052，是因为 0051 提交后的独立
  集成 finding 要求保留既有普通 commit、以新的普通 follow-up 修正，未
  改写 0051。
- issue：`frame-offset-no-imms12-range-check-silent-wraparound` 已从 open
  registry 移到 archive。

### 验收结果

1. LLVM 定向 IR/MIR：2/2 PASS；DADAO CodeGen 目录：5/5 PASS。
   MIR 明确锁定 `2047/-2048` 仍走直接立即数、`2048/-2049` 走物化，
   并覆盖 prologue/epilogue、`ADDI_RB_FI`、RD/RB load/store、正负大偏移。
   新增 small-frame + large-GEP 用例把 RD8..RD63 全部保持 live，实际观察
   到 emergency `STO_RRII`、偏移物化、原 RB store、`LDO_RRII` restore；
   large fixed offset + 显式 RB5 store/load 则锁定 RB6 地址 scratch。
2. 新增 volatile 大帧 E2E：QEMU+gem5 正例均 exit 42；故意改错期望值的
   negative-control build 在两后端均 exit 1。全量 E2E：73/73 PASS。
3. `pr56866.c`：QEMU 由 TIMEOUT 转 PASS；同一 ELF 在 gem5
   `SIM_END: trap-exit code=0`。
4. gcc-c-torture 1708 项：
   `PASS=1412 / FAIL_COMPILE=113 / FAIL_LINK=133 / FAIL_RUN=50 /
   TIMEOUT=0`。相对落地前真实基线
   `1409/113/133/52/1`：PASS +3、FAIL_RUN -2、TIMEOUT -1；无分类总数
   漂移，也没有旧 PASS 数下降。
5. differential：
   `AGREE(3-way)=200, DIVERGE=0`；
   `AGREE(4-way)=200, SAIL-DIVERGE=0`。
6. 裸 manifest pin `ca7933e47d3a...` 依次 plain `git am`：
   52/52 PASS；replay tree 与 LLVM commit `032fab81c9bf` tree 同为
   `09a9fe311ef08133a65a6435de26003768d6bb8c`。

### 已知边界

- 本任务关闭的是 frame adjustment/frame-index 的 imms12 缺口；不宣称
  所有非 frame 的 imms12 生产者都由本任务覆盖。
- RB5 是 ABI-reserved scratch，RD2 是 ABI-reserved prologue/epilogue
  scratch；实现不占用 incoming argument（RD/RB16+）或 return（RD/RB31）。

## 审阅记录（实现者自审）

| Finding | 处置 |
|---|---|
| 直接固定一个 allocatable RD 会破坏活跃值 | PEI 强制使用 RegScavenger；MIR verifier 与真实大帧执行通过 |
| store 源在指令后可能已 dead，不能凭 live-out 直接挑寄存器 | 使用 `scavengeRegisterBackwards(..., II, RestoreAfter=false)`，覆盖原指令位置，而不是只调用 `FindUnusedReg` |
| scavenger 自身 spill 可能递归触发大偏移 | 初版只按 frame estimate 预留不足；0052 改为扫描实际 pseudo 的最终 Total 保守范围，small-frame + large-GEP 的 RD8..RD63 全活 MIR 已强制并验证 emergency spill/restore |
| 固定 RB5 地址 scratch 可能覆盖 RB store source/load dest | 正常 RA 不会分配 reserved RB5；0052 仍使显式 RB5 operand 自动改用 reserved RB6，并由 fixed-offset MIR 锁定 |
| prologue/epilogue scratch 可能破坏参数或返回值 | 仅用 ABI-reserved RD2；参数从 RD16 开始，scalar return 在 RD31 |
| 小帧路径可能因新 slot/metadata 漂移 | 仅当扫描证明某个 FI pseudo 的最终 Total 可能越界才创建 slot；普通小帧汇编回归保持原单指令 |
| 只验证 pr56866 可能遗漏“侥幸 PASS”变化 | 重跑完整 1708 corpus、73 E2E 与四方差分 |
| LLVM 全目录首次发现 varargs 旧断言失败 | 确认为 DL-072a 后的 stale callee-save-area 测试，按 caller-save-area 事实修正后 5/5 |

**实现者自审判决：PASS，提交独立 subagent review。**

## 独立 subagent review（2026-07-24）

- 审查记录：
  `docs/reviews/ML-029a-independent-review-20260724.md`。
- 审查对象为最终 LLVM HEAD `032fab81c9bf`，覆盖主体提交
  `245d4f42a5d8`、spill-safe follow-up `032fab81c9bf`、0051/0052 patch、
  运行测试与 issue 关闭记录。
- 独立定向验证：新增 LLVM IR/MIR 2/2 PASS，DADAO CodeGen 5/5 PASS；
  E2E 73/73 PASS；gcc-c-torture 为
  `1412/113/133/50/0`，相对基线旧 PASS 零退化；三方/四方 differential
  均 200 AGREE、0 DIVERGE；manifest pin 上 plain `git am` 52/52，
  replay tree 与最终 LLVM tree 一致。
- reviewer 未发现 blocking、major 或 minor finding。其两条 informational
  仅说明测试覆盖的组合方式与临时审查沙箱配置，不影响实现或验收结论。
- 架构师收尾时保留了 ML-027a issue 的完整诊断历史，仅将状态、解决提交和
  ML-029a 最终证据补入 archive，避免关闭 issue 时丢失既有调查记录。

**独立 reviewer 判决：Accepted，无 blocking finding。**
