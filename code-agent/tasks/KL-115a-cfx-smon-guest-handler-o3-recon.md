# KL-115a：调研 O3（真实 `trap cfx_smon`→guest handler→`escape` 往返）的最小可实现切片

**执行环境**：本地 subagent，纯调研，不修改 QEMU/gem5/LLVM/kernel/
contracts/wiki

## 背景

K1 的 hypv→supv 特权切换（O1 成功路径 + O2 两个负例）已经在 QEMU/gem5
双后端完整实现并独立验证（`KL-110a`/`KL-112a`/`KL-113a`），LLVM MC 也已
补齐（`KL-114a`）。K1 剩下两块：本任务对应的 O3（移交后真实受控操作），
以及 MMU/TLB+完整中断分派。

`KL-101a` 当年（`docs/reviews/kernel-hypv-supv-handoff-20260721.md`
§3.4/§4）给出的 O3 定义："在 O1 的 `supv_entry` 中先按冻结后的
mask/delegation 规则使 `cfx_smon` 可达，再执行 `trap cfx_smon,0`，由
guest-side smon handler 做一个无副作用最小动作（例如读取固定 ABI 参数、
写回 `rd31=0`、`escape cfx_smon,1` 返回），随后写 marker。禁止直接调用
QEMU/gem5 的 host syscall API。"——目的是证明"移交到 supv 之后，`trap`
指令走的是真实的 SEE §5 异常进入流程 + guest 侧 handler + `escape` 异常
退出流程"这个完整闭环，而不是继续依赖现有 QEMU `cpu.c:130-223`/gem5
`TrapInst::execute()` 里那条**已确认必须保留、但只是兼容捷径**的
host/SE syscall 直通路径（`KL-102a` 报告 §5.1"隔离原则"）。

架构师在准备下发实现任务前，重读了 wiki 完整的"异常进入流程"（SEE §5
第678-745行，10 个步骤 + 完整伪代码），发现这比 O1/O2 已实现的范围复杂
得多：步骤2"不可屏蔽异常判断"（`excp_cause_nonmaskable`）、步骤3
"inner_cfx_mask 屏蔽判断"、步骤4"global_cfx_mask 屏蔽判断"、步骤5
"异常原因掩码判断"（`excp_cause_mask`，含 pending 寄存器语义）、步骤6
"陷入计数更新"（`trap_num`/`excp_sync_num`/`excp_async_num`）——这些
机制目前在 QEMU/gem5 都**完全没有任何存储或检查代码**（`KL-110a`/
`KL-112a`/`KL-113a` 只实现了步骤1的"reserved→ILLI"和"指令类型 cfx mask
禁止→ILLI"这两条路由分支，以及步骤7-10 里 `cfx_power` 专属的
`escape` 退出侧镜像）。**如果 O3 要求逐字按 wiki 10 个步骤实现通用的
异常进入机制，这个任务的规模会远超"guest handler 例子"这个描述**。

## 目标

1. **精确定义 O3 所需的最小步骤子集**：对照 wiki 10 步伪代码，逐步判断
   哪些步骤是"`trap cfx_smon` 这一个具体场景（从 supv 模式、无嵌套、
   guest handler 只做一次无副作用往返）能不能跳过、必须做"：
   - 步骤2（nonmaskable）：`cfx_smon` 的 `excp_cause_nonmaskable` 对
     `CFXTRAP`（trap 指令产生的 cause）默认值是什么？wiki 是否已经说明
     `CFXTRAP` 必然不可屏蔽（对照 SEE §5 步骤5 的备注"其余同步异常均为
     不可屏蔽"——`CFXTRAP` 是不是包含在"其余同步异常"里，如果是，步骤
     2-5 对这个场景可能整体可以走"不可屏蔽直接进步骤6"这条捷径，需要
     核实原文是否支持这个读法）。
   - 步骤3/4（inner_cfx_mask/global_cfx_mask）：从 hypv 模式执行 O1
     handoff 时，`cfx_power` 的 `inner_cfx_mask`/相关 global mask 复位
     值是什么（已知 O1 的 `inner_cfx_mask` 复位是全1，HBI §3 stub 也
     没有清它——这会不会导致"从 hypv 发起的、以及 supv 侧任何目标 cfx
     的异常"在到达 `cfx_smon` 之前就先被 `inner_cfx_mask`/`global_cfx_
     mask` 挡住"？需要判断 O1 stub 之后 supv 侧再执行 `trap cfx_smon`
     时这两个 mask 的实际取值，以及是否需要在 O3 探针里显式清除它们
     才能让 trap 真正打到 `cfx_smon`）。
   - 步骤6（陷入计数）：`trap_num` 等计数寄存器如果本次不实现存储，
     对 O3 验收（"确认走了真实路径，不是走了 host 捷径"）有没有影响——
     如果没有，可以明确排除在本次范围外（类比 `escape_num`
     在 O1/O2 里就是这么处理的）。
   - 步骤7-10：这四步是 O3 的核心（保存 prev_run_mode/prev_cfx_mask、
     模式切换、保存 cause_ip/cause_id/cause_info、跳转异常向量）——
     确认这四步和 `escape` 已实现的退出侧（`cfx_power` 专属 cg5 frame）
     是否同构，`cfx_smon` 是否需要一份**自己的** cg5 frame（目前只有
     `cfx_power` 有）。
2. **`cfx_smon` 从 supv 可达的具体前置条件**：O3 描述"先按冻结后的
   mask/delegation 规则使 `cfx_smon` 可达"——结合 `KL-110a`/`KL-112a`
   已经实现/未实现的检查（`trap_cfx_mask`跨cfx检查、`cg_reg_deleg`），
   梳理 O1 的 HBI §3 stub 执行完之后，从 supv 侧执行
   `trap cfx_smon,0` 需要跨过哪些检查点（是否需要额外的 `cfx2rc` 写入
   才能让这条路径不被 O2 已实现的检查挡住，还是天然可达）。
3. **guest handler 的最小 ABI 约定**：现有 host/SE 捷径读 `rd16`
   （sysno）+`rd17-19`（参数），O3 描述"读取固定 ABI 参数、写回
   `rd31=0`"——判断是否可以直接复用这个既有寄存器约定（不需要调用任何
   host syscall，只是把同样的调用惯例套在真实 guest handler 代码上），
   还是需要一套独立约定。
4. **产出一个精确、当前 M1 状态下真正可构造的 O3 设计**：给出具体的
   探针指令序列（HBI §3 stub → supv 侧准备工作 → `trap cfx_smon,0` →
   guest handler 代码 → `escape cfx_smon,1` → marker），标注每一步
   依赖哪些"已实现"vs"本任务需要新实现"的机制，供后续实现任务
   （建议 `KL-116a`）直接使用。如果发现范围比预期大很多（比如必须先
   补 `cfx_smon` 自己的 cg5 frame 存储），如实说明，不要为了凑一个
   "看起来可行"的方案而简化掉必要步骤。

## 约束

- 只做调研，不修改任何文件。
- wiki 引用必须自己读原文核实（`~/DADAO-wiki/DADAO-12-SEE-主管系统
  运行环境.md` 第678-811行完整异常进入/退出流程是本任务的核心依据），
  不要只转述本任务文件或历史 review 报告的转述。
- 参照既有 review 报告的证据标签格式（`[正式契约]`/`[已有实现]`/
  `[推断]`）和写法（`docs/reviews/kernel-hypv-supv-handoff-20260721.md`/
  `kernel-cfx-state-patch-surface-20260721.md`/
  `kernel-hypv-supv-o2-permission-recon-20260725.md`）。
- 完成后写「完成区」+ subagent 自审「审阅记录」，不需要嵌套 subagent、
  不需要独立 reviewer。
- 如果某个机制 wiki 确实没写清楚（不是"复杂"是"沉默"），按
  `docs/wiki-deviations.md` 现有格式给出建议条目草稿（不直接写入文件），
  不要自己编一个没有依据的解读。

## 验收

- 产出 `docs/reviews/kernel-cfx-smon-o3-recon-20260725.md`。
- 报告结尾给出清晰的 O3 探针设计（精确到指令序列/寄存器/预期状态），
  明确列出"复用现有实现的部分"vs"本任务发现必须新做的部分"，以及一个
  诚实的范围/工作量估计（是否应该拆成 QEMU/gem5 两个独立实现任务，还是
  范围小到可以合并）。
- 任务文件「完成区」总结关键结论。

## 参考指针

- `docs/reviews/kernel-hypv-supv-handoff-20260721.md`（KL-101a，O3
  最初定义，§3.4/§4）
- `docs/reviews/kernel-cfx-state-patch-surface-20260721.md`（KL-102a，
  §5.1 legacy 隔离原则）
- `code-agent/tasks/KL-110a-*.md`/`KL-112a-*.md`/`KL-113a-*.md` 完成区
  （O1/O2 已实现的确切机制、`cfx_power` cg5 frame 的确切实现方式，
  作为 `cfx_smon` 需要什么的参照物）
- `~/DADAO-wiki/DADAO-12-SEE-主管系统运行环境.md` 第678-811行（完整
  异常进入+退出流程，本任务核心）；第265-330行（cg0-2 各模式寄存器表，
  含 `trap_cfx_mask`/`excp_cause_mask`/`switch_run_mode`/
  `switch_cfx_mask`/`excp_vector` 等）
- `.work/source/qemu/target/dadao/cpu.c:130-223`（现有 host-side
  `cfx_smon` syscall 捷径，O3 明确不能依赖它，但要保留不动）

## 完成区（2026-07-25）

**状态**：调研完成，产出 `docs/reviews/kernel-cfx-smon-o3-recon-20260725.md`，
未修改任何文件。

**关键结论**：

1. Wiki 步骤2-5 对 `trap cfx_smon` 场景可合法整体跳过——`CFXTRAP` 对
   `cfx_smon`/`cfx_umon` 共用异常表硬件固化为不可屏蔽（wiki
   `DADAO-12-SEE §5` L402/419/693/763-765），任务背景关于 O1 遗留
   `inner_cfx_mask`=全1 的担忧经核实**不成立**（只影响可屏蔽异常，
   `CFXTRAP` 不是）。步骤6（陷入计数）可排除，类比 `escape_num`
   处理先例。
2. 步骤7-10 是真正核心缺口——**不是"`cfx_smon` 部分缺失"，是整个
   `trap` 指令的异常进入流程从未被实现过**（`cfx_power` 现有的
   prev/cause 三字段是 O1 用软件 `cfx2rc` 写入模拟出来的假现场，从未
   经历过真正的硬件 trap 进入；`cause_id`/`cause_info` 连 `cfx_power`
   都没有存储）。
3. O2 已实现的两项检查（escape mask 设计1、CFXREG 设计3）都不会拦截
   O3 探针；`trap_cfx_mask` 这项 wiki 提到但从未被实现/评估过的检查
   同样不会拦截（机制本身不存在）。真正的可达性障碍不是权限检查。
4. **新发现（任务背景未预判）**：`trap` 指令的 `cfxcode==2` 分支当前
   被 host/SE syscall 捷径无条件独占（QEMU `cpu.c:157`；gem5当前
   checkout `~/DADAO-gem5/src/arch/dadao/decoder.cc:708`，与 patch
   series 一致），O3 要做"真实进入流程"必须先解决这个共存问题，报告
   §4.4 列出三个选项（新增开关/换未占用 cfxcode/func 取值分岔），
   **建议架构师先拍板再下发实现任务**。
5. guest handler ABI 约定（`rd16-19`/`rd31`）可直接复用，无冲突。
6. 未发现需要登记 `docs/wiki-deviations.md` 的新沉默/矛盾（逐项排查
   理由见报告 §5）。
7. 工作量估计：不小于 O1+O2 合计，建议拆 QEMU/gem5 两个独立实现任务；
   §4.4 的设计分叉点需要架构师决策后才适合下发给实现 DS/subagent。

**产出文件**：`docs/reviews/kernel-cfx-smon-o3-recon-20260725.md`（完整
证据链、wiki 逐行核对、探针设计、自审记录）。

---

## 自审：审阅记录（subagent 自审）

见报告文件末尾「自审：审阅记录」章节——判决通过，无阻断 finding；
记录了 wiki/源码引用的逐项复核方式，以及 gem5 侧证据从"patch文本+
KL-113a转述"升级为"直接读取 `~/DADAO-gem5` 当前 checkout 一手核实"
的过程。
