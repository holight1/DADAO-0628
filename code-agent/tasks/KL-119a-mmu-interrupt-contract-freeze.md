# KL-119a：冻结 MMU/TLB + 完整中断分派的契约空白（候选A-E）

**执行环境**：远端 Codex（本仓库），只写契约/偏离记录，不写 QEMU/gem5
实现代码

## 背景

`KL-118a`（纯调研，已 commit）把 K1 收尾项（MMU/TLB SBI式操作 +
完整中断分派）拆成了 21 个建议增量任务（`docs/reviews/
kernel-mmu-interrupt-recon-20260726.md` §5），并识别出 5 个必须先
冻结、否则后续实现任务无法正确验收的契约空白（候选A-E，报告 §2.3）。
本任务是这 21 个任务序列里的第一个（KL-119a），只做契约冻结，不写
任何实现代码——后续所有 QEMU/gem5 任务都依赖本任务的决定。

架构师已独立复核过 `KL-118a` 报告，确认候选A-E 的 wiki 引用和分析
准确，其中**候选E（嵌套 cfx 返回时 `inner_cfx_code` 不恢复）是最
关键、最需要谨慎决定的一个**——它不是"QEMU/gem5 实现细节"，而是
影响 ISA 异常退出模型本身的架构决定，会被后续所有涉及嵌套 trap
（`cfx_tlb→cfx_ptw→cfx_tlb` 委托、以及未来任何 A→B→A 调用链）的
任务依赖。

## 目标

逐条对 `docs/reviews/kernel-mmu-interrupt-recon-20260726.md` §2.3
列出的候选A-E 做出决定，产出：

1. **候选A（通用 `pending` 寄存器落点）**：决定是"所有 cfx 通用
   pending"还是"只有产生异步原因的 cfx 才有专有 pending"，冻结
   具体 cg/rc 编号；决定同一 cfx 内多个 cause 同时 pending 时的
   优先级规则（最低位优先，还是别的）。
2. **候选B（timer 最小 profile）**：报告已给出建议 profile
   （counter0 相对递减、0→pending bit10、one-shot 自动停、
   software write-0 ack），本任务确认或调整这个 profile，并明确
   `GET_TIME` 与"读 counter0"的关系、periodic reload 的来源。
3. **候选C（TLB 容量/替换策略）**：确认报告的判断——K1 只承诺架构
   可见的 hit/miss/invalidate/fault 语义，不做性能声明；固定一个
   QEMU/gem5 共用的测试 profile（比如每个逻辑集合的容量、替换策略），
   写清楚这是"测试用固定选择"不是"架构规定"。
4. **候选D（外部中断/UART 协议）**：决定 K1 是否要冻结一个最小
   UART0 协议（IRQ 拉高/撤销、source clear、pending ack 顺序），
   还是明确降级为"合成外部 IRQ source"（不声称 UART/PLIC 已实现）。
   这个决定会影响后续 KL-137a/138a 任务的范围（报告已把这两个任务
   写成条件任务，根据本任务的决定走不同分支）。
5. **候选E（嵌套 cfx 返回语义）——这条需要你先给出至少两个可行方案，
   明确标注每个方案的代价，不要replace架构师/用户直接拍板**：
   - 现状：SEE `escape` 用当前 `inner_cfx_code` 选择 frame，只恢复
     mode/mask/PC，从不恢复 `inner_cfx_code`（`docs/wiki-deviations.md`
     #9）；SBI 的 `cfx_tlb→cfx_ptw→cfx_tlb` 委托要求嵌套 escape 后
     `inner_cfx_code` 能"回到"上一层，两者字面矛盾。
   - 至少给出以下方向的可行性分析（不预设哪个更好）：
     (a) 引入 `prev_cfx_code` 存储（每层 trap 保存进入前的
     `inner_cfx_code`，`escape` 恢复时读回——类比 `excp_prev_run_mode`/
     `excp_prev_cfx_mask` 已有的做法，需要决定存在哪个 cg/rc，是否
     需要支持多层嵌套栈还是只支持"恢复上一层"这一层）；
     (b) 限制 K1 范围只支持单层嵌套（`cfx_tlb→cfx_ptw` 委托后，ptw
     escape 时不做"self-escape"语义，而是显式跳回 tlb 的向量/状态，
     绕开"cfx_tlb 再次 escape"这一步——需要判断这是否会改变 SBI 已
     写好的示例代码逻辑，如果会，说明这是偏离 SBI 示例还是SBI示例
     本身需要改写）；
     (c) 其它你认为可行的方案。
   - **不要在本任务里直接拍板选哪个方案**——如果几个方案都可行，
     在完成区列出来，供架构师/用户决定；如果只有一个方案真正可行
     （其它都有你能证明的硬缺陷），可以在完成区给出你的判断和依据，
     但仍要明确标注"建议"而非"已冻结"，等待确认。

## 约束

- 只写 `contracts/isa/spec.md`（如果需要正式补充语义）和
  `docs/wiki-deviations.md`（记录候选A-E 的最终决定/建议）——不写
  QEMU/gem5/LLVM 代码，本任务不是实现任务。
- 候选A-D 如果决定清楚、有依据，可以直接在 `docs/wiki-deviations.md`
  按既有格式记录为"我们的决定"（不是"建议"）；候选E 除非你能证明
  只有一个方案可行，否则记录为"建议方案+待决定"，不要擅自拍板。
- 不要重新做 `KL-118a` 已经做过的 wiki 调研——直接复用报告的引用，
  只在需要进一步验证细节时才重新读 wiki 原文。
- 完成后写「完成区」+ 自审记录；如果你自己内部开了 reviewer
  subagent 复核（`KL-118a` 用了这个方法，效果不错），继续沿用，
  记录审阅过程。

## 验收

- `docs/wiki-deviations.md` 新增候选A-D 对应的条目（决定+理由+
  影响范围），候选E 的条目按上面"不要擅自拍板"的要求处理。
- 如果涉及 `contracts/isa/spec.md` 补充（比如 K1 范围内 timer/
  pending 的具体行为约定），按既有 `[wiki §...]`/`[spec-decision:...]`
  格式写，跑一遍 `scripts/check_wiki_refs.py --profile isa` 确认 PASS。
- 任务文件「完成区」清楚列出候选A-D 的最终决定，候选E 的方案对比
  和你的建议（如果有）。

## 参考指针

- `docs/reviews/kernel-mmu-interrupt-recon-20260726.md`（KL-118a，
  §2.3 候选A-E 的完整分析、§1.3 候选E 问题的详细追溯）
- `docs/wiki-deviations.md` 第9条（`inner_cfx_code` 不被 escape 恢复
  的既有记录，候选E 直接建立在这条之上）
- `~/DADAO-wiki/DADAO-22-SBI-主管系统二进制接口.md` 第345-372行
  （`cfx_tlb_ptw_delegate` 嵌套委托示例，候选E 问题的具体触发场景）
- `~/DADAO-wiki/DADAO-12-SEE-主管系统运行环境.md`（cg4/cg5 表、
  异常进入/退出流程完整伪代码）

---

## 完成区（2026-07-26）

### 候选A-D 已冻结决定

1. **A / pending**：所有非 reserved cfx 新增 common cause-pending
   `(cg,rc)=(4,7)`，64-bit reset-zero RW/W0C；只允许该 cfx 原因表中的
   maskable cause bits。timer/UART/power 的既有专有 pending 是独立
   device-source latch，不与 common pending alias；source→cause 两级
   映射。优先级固定为最低 cfxcode、再最低 cause bit。电平源 ack 顺序为
   source deassert/service → drain 映射到该 cause 的全部 private pending
   → common pending W0C；任一 private bit 尚在时 common cause 必须保持/
   重新置位。source assert/expire 本身不受 mask 影响。
2. **B / timer**：K1 只承诺 counter0 decrement profile。
   `SET_TIMER(timeout)` 是相对延迟；写 current counter 和内部 reload latch；
   1→0 到期，0 在下一指令边界可触发；one-shot 自动清 enable，periodic
   从 last-written reload。counter0 source 使用 private pending/mask bit0，
   映射 common TIMER cause bit10。`GET_TIME` 返回 monotonic
   `cfx_hart_cycle_lo`，不返回 countdown。counters1-7/increment 明确
   non-claim，留给条件收口任务。
   timer tick 与 `cfx_hart_cycle_lo` 使用同一 K1 virtual-cycle timebase：
   每退休一条架构指令推进一次，低64位按 `2^64` 回绕；这是功能 oracle，
   不作性能声明。
3. **C / TLB profile**：双后端固定 all 64 sets present、每 set 16-entry、
   unified fully-associative、deterministic true-LRU，
   `tlb_exist=UINT64_MAX`。只作为稳定功能/替换 oracle，不形成 ISA 性能或
   硬件组织声明。
4. **D / external IRQ**：选择 test-machine-only 合成 level source
   `K1_EXT0`，映射 cfx_uart private source bit0 → common UART0 cause bit32。
   不实现、不声明 UART/PLIC，刺激机制不是 guest ABI；按 A 的两级 ack 顺序
   验证 re-latch。

上述决定已写入 `contracts/isa/spec.md §8.5.1-§8.5.4`，并分别记录为
`docs/wiki-deviations.md` #12-#15。

### 候选E 方案比较（未冻结）

- **E1（建议）**：新增 per-cfx `excp_prev_cfx_code`，建议 cg5/rc5。
  trap 保存 caller cfx，escape 与 mode/mask/PC 一并恢复。不同 cfx 的
  A→B→C 链沿用现有 per-cfx frame，无硬件栈；同 cfx 重入继续按 wiki
  要求由软件把 cg5 保存到 cg6。代价最小，SBI TLB→PTW→TLB 示例无需改写；
  但一次 escape 跳过多个 cfx 的 shortcut 仍需另行冻结，K1 不依赖它。
- **E2（可行但代价高）**：硬件异常上下文栈，push/pop 完整 frame。能覆盖
  同 cfx 多层嵌套，但必须新增栈深、溢出异常、cross-cfx shortcut 丢层规则、
  cg5 顶层可见性以及双后端迁移/复制语义。
- **E3（不建议，当前不闭合）**：单层软件 trampoline/SBI 改写。当前没有
  可写 `inner_cfx_code`，返回 trampoline 后仍是 ptw 身份；再次 trap tlb
  会覆盖 frame，最终 caller code 仍无法恢复。除非再新增 escape-return-code
  或可写 inner-code 机制，否则只能是测试捷径。

本任务**没有拍板 E**：`docs/wiki-deviations.md` #9 继续保持 OPEN，
`contracts/isa/spec.md §8.5.5` 明确阻止后续任务在确认前声称 nested CFX
return 已闭环。建议架构师/用户后续选择 E1。

### 自审记录

- 修改范围仅为 `contracts/isa/spec.md`、`docs/wiki-deviations.md` 和本任务
  完成区；未修改 QEMU、gem5、LLVM、kernel、wiki 或测试实现。
- 自审时发现并修正了“专有 pending 与 common pending alias”的错误初稿：
  8 个 timer source 只能汇聚到一个 TIMER cause，因此最终契约明确采用
  private source latch + common cause latch 两级模型。
- A-D 均有正式决定、理由、影响范围和状态；E 保留两个真正可行方案及一个
  被证明不闭合的受限方向，只给建议未改写既有 #9 决定。
- 独立首审指出 timer tick/timebase、多 private source 聚合及 cross-cfx
  shortcut 三处未闭合；均已补入契约。多层 shortcut 现明确为 K1 non-claim，
  且 #9 已记录 SEE 第664-676行自然语言与第813-845行退出伪码的冲突。
- `python3 scripts/check_wiki_refs.py --profile isa`：**OVERALL PASS**；
  169 references 中 166 RESOLVED、0 DANGLING、3 个既有 UNPARSEABLE warning，
  normative assertion missing ref=0。
- 保留无关未跟踪文件 `gcc-torture-results.json`，不纳入本任务。

### 独立 review 记录

- 唯一 reviewer 首轮结论为 NOT PASS，指出 timer tick/timebase、多 private
  source 汇聚同一 cause、cross-cfx shortcut 三项未闭合；意见均有 wiki/
  契约证据，已全部接受并修订。
- 同一 reviewer delta review 结论为 **PASS**：确认 virtual-cycle 与
  modulo `2^64`、drain-all source/cause pending、shortcut K1 non-claim
  均已闭合；独立复跑 checker 得到 `169/166/0/3/0, OVERALL PASS`，
  `git diff --check` 通过。reviewer 全程只读，未修改文件。
