# KL-001a: kernel bring-up 调研（K0，仿 ML-006a musl-recon 模式）

**执行环境**: 本地 subagent（纯调研，不写代码）

**状态**: 待处理

## 硬约束

- **纯调研任务，不写任何代码/不改任何仓库文件**（除产出的调研报告本身）。不碰 `.work/<component>`。
- 完成后必须在任务文件里写「完成区」+ subagent 自审「审阅记录」（调研类任务的自审重点是"结论有没有证据支撑"，不是代码 review）。

## 背景

DADAO-0628 的终极目标是 QEMU + kernel + 用户态应用全链路跑通（`docs/adr/0015-kernel-bringup-charter.md`）。用户已决策：目标内核 Linux 5.4（非强制）、暂不引入固件/SBI monitor 层。已归档的 `~/toolchain/DADAO` 三轮 kernel 尝试（V1/V2-V4/V5）均未真正跑通用户态执行，代码/patch 因 ISA 版本不兼容（当前 pin 是 `9f378f4426e131903d60a208766086ae74a53c89`，比旧项目任何一版都新）不可直接复用，只继承 `~/toolchain/DADAO/code-agent/designs/sysmode-debug-lessons.md`（~20条踩坑 B01-B22+L1-L3）等结论。

DADAO-0628 目前只有 SEE `cfx_smon` syscall trap 机制（ADR-0014），没有完整的异常/中断模型、MMU/TLB 操作、特权级切换。本任务是 kernel bring-up 的第一步：把"现在有什么、缺什么、要做多少"摸清楚，产出一份路线图报告，供架构师拆分后续 K1-K4 任务——模式完全参照 `docs/reviews/musl-recon-2026-07-16.md`（ML-006a）当时对 musl 移植做的调研，那份报告显著降低了后续任务的风险判断误差，本任务照此标准执行。

## 目标（产出一份调研报告，路径建议 `docs/reviews/kernel-bringup-recon-2026-07-18.md`）

1. **当前 wiki pin（`9f378f4426e131903d60a208766086ae74a53c89`）的 SEE §5 完整定义**：`~/DADAO-wiki/DADAO-12-SEE-*.md`（或对应文件名）里除了 `cfx_smon`（已实现）之外，还定义了哪些异常/中断类别（timer、page fault、非法指令、其它）？每种的进入/返回机制（CP0/CP1 寄存器、cause 编码）是什么？DADAO-0628 现有 QEMU/gem5 实现（`components/qemu/patches/`、`components/gem5/patches/`）目前覆盖到哪一步，缺口具体是什么（逐项列出，不要笼统写"缺中断模型"）。
2. **MMU/TLB 的 SBI 式操作定义**：当前 wiki pin 里 `SBI_TLB_INVALIDATE`（旧项目 V5 提到的草案）或等效机制是否已经在当前 pin 里正式定义？PTBR/PTHI/PAHI（旧项目 V1-V4 用的直接 CP0/CP1 寄存器写方式）在当前 wiki 里对应哪些寄存器/机制？页表格式（页大小、级数）当前 wiki 是否已经明确规定，还是仍是 `[OPEN]`？
3. **特权级/模式切换**：当前 wiki pin 是否已定义 User/Supervisor 模式切换机制？和 `cfx_smon` trap 现有实现的关系是什么（trap 本身是否已经隐含某种模式切换，还是纯粹的"陷入 responder 函数"没有真正的特权级概念）？
4. **旧项目 20 条踩坑的适用性重新核实**：逐条读 `sysmode-debug-lessons.md`（B01-B22+L1-L3），对每一条标注"这条在当前 spec/DADAO-0628 现状下是否仍然适用"（有些可能是旧 ISA 版本特有的、当前 spec 已经不存在这个坑；有些是通用工程教训，仍然适用）——产出一份"新 kernel 任务必读清单"，只保留仍然适用的，并标注每条对应当前 spec 的哪个章节/哪个后续 K 阶段任务。
5. **Linux 5.4 树本身的可用性**：`~/toolchain/DADAO/__source/linux-0504` 是否是一份干净的 vanilla 5.4.0 源码（可以作为 DADAO-0628 新 `arch/dadao` 移植的基线），还是已经被大量 DADAO 专有改动污染、不方便剥离？如果污染严重，是否需要重新从上游拉一份干净 5.4.0 而不是复用这个目录？
6. **裸机内核态回归的可行范围**（K2 阶段前置调研）：根据当前 DADAO-0628 的差分验证框架（`tools/run_differential.py`、`tests/vectors/isa/*.yaml`）和 E2E lit 框架，判断"上下文切换"/"trap 分派"/"MMU 开关"这几类裸机测试大概需要什么样的测试向量/手写汇编结构，是否有现成的可扩展框架，还是需要新建一套（不需要写代码，只需要给出判断和理由）。
7. **产出建议的 K1 任务拆分清单**（供架构师后续派发，类似 ML-006a §7 的"下一步任务清单"格式）——按风险/工作量给出合理的任务颗粒度建议（不需要精确，量级判断即可）。

## 验收

- 调研报告写入 `docs/reviews/kernel-bringup-recon-2026-07-18.md`，结构清晰、每条结论都要有具体依据（wiki 章节号、旧项目文件路径、当前仓库文件路径），不要空泛断言。
- 报告末尾给出建议的 K1 任务清单。
- 完成区总结报告核心发现（不超过一屏，太长的细节留在报告正文里）。

## 参考指针

- `docs/adr/0015-kernel-bringup-charter.md`（本任务是其 K0 阶段的具体执行）
- `docs/adr/0014-libc-syscall-charter.md` D4（现有 SEE trap 机制的范围/局限）
- `~/toolchain/DADAO/code-agent/designs/`：`sysmode-debug-lessons.md`、`dadao-mmu-enable-design.md`、`dadao-sysmode-design-reference.md`、`dadao-v5-impl-spec.md`（SBI 草案章节）、`dadao-userspace-plan.md`（仅供查阅结论，不可直接抄代码/patch）
- `~/DADAO-wiki/`（当前 pin `9f378f4426e131903d60a208766086ae74a53c89` 对应的 wiki 内容——需要确认这是不是本地可直接读取的路径，如果不是要说明如何核对当前 pin 内容，比如通过 `git -C ~/DADAO-wiki log`/`show <pin>` 之类）
- `docs/reviews/musl-recon-2026-07-16.md`（ML-006a，本任务的报告格式/深度范例）
- `manifests/components.lock.toml`（`linux` 组件当前 `enabled=false`，本任务不需要改，但报告可以给出"建议 pin 到哪个版本"的意见）

## 完成区

**状态**：已完成
**产出**：`docs/reviews/kernel-bringup-recon-2026-07-18.md`（全部 7 个目标逐一调研，含 wiki pin 章节号/旧项目文件路径/当前仓库文件路径三方依据）

**核心发现（详见报告正文）**：

1. **SEE §5 在当前 pin（9f378f4）已是完整规范，不是草案**——cfx 路由、cg0-cg7 寄存器规范、每个 cfx 的异常原因表、10 步异常进入伪代码+escape 退出伪代码全部齐备。但 DADAO-0628 现有实现（`0013-dadao-trap-syscall.patch`）是**纯 host 侧语义捷径**（QEMU C 代码直接模拟 write/exit/brk），`escape`/`cfx2rd`/`cfx2rc`/`cfxld`/`cfxst`/`inner_run_mode`/cg5 现场寄存器**全部未实现**（grep 双后端 patch 零匹配）。K1 是"从捷径升级为真实现"，不是"从零开始"。
2. **MMU/TLB SBI 操作已从旧项目草案变为正式定义**（SBI §4/§5 完整 cfx_ptw/cfx_tlb 功能表+初始化+分发伪代码）。访问范式与旧项目（RISC-V 风格 CSR 直接读写 `cp0_write`）完全不同——当前走 `trap`/`escape`/cfx 寄存器组，机制层面不可复用旧代码。页表格式已明确（非 OPEN），但 `docs/open-spec-issues.md` 有 4 条真实未决细节（TLB fault return 重试/跳过不一致、PTW SBI ABI 分类、VA2PA 符号编码、cross-cfx escape 嵌套策略）会阻塞 K1 实现，需先决。
3. **特权级切换现状=完全空白**（QEMU CPU state 无 `inner_run_mode` 字段）。**重要发现**：HBI §3 规定硬件复位后永远先进入 **hypv 模式**（非 supv），需要一段~15-20 指令的 hypv→supv 移交桩代码（`cfx2rc` delegation + `escape`）才能进入 S-mode——这与 ADR-0015 D2"暂不引入固件层"存在理解张力，**建议澄清 D2 为"不做复杂固件，但仍需最小移交桩代码"**，否则会漏做这一步。
4. **旧项目 25 条踩坑（B01-B22+L1-L3）逐条核实**：6 条因新 ISA 机制结构性消除（B02/B04/B07/B18/B19/L2，如 ra2rd/rd2ra 在新 RegRAS 栈模型下不存在），精简为 10 条必读清单（含 4 条通用工程纪律、3 条需在新 spec 下重新验证、3 条明确对应 K1/K3 前置动作）。**新发现一条不在原清单里、比旧坑更根本的问题**：当前 M1 完全没有指令可以整体保存/恢复 RegRAS（`ldmo-ra`/`stmo-ra` 被 M1 excluded），而 wiki AEE 明文规定"进程切换必须保存恢复全部 ra0-ra63"——这是 K1 的最高优先级未决项。
5. **`~/toolchain/DADAO/__source/linux-0504` 基本是干净 vanilla 5.4.0**：只 7 个提交 ahead of v5.4，`arch/dadao` 是外部符号链接（真实移植代码不在树内），其余 6 个提交是 2 行 uapi 枚举 + 4 处编译优化等级覆盖，**可直接复用作移植基线**，无需重新拉取上游。
6. **裸机内核态回归框架部分可扩展，非现成够用**：trap 分派可扩展现有 yaml 向量字段（小-中工作量）；上下文切换需新建断点+dump 断言机制（可基于 gem5 halt-regdump 起点扩展，中工作量）；MMU 开关需新建测试页表构造小工具（中工作量）。三类应分别排子任务，不合并。
7. **建议 K1 任务清单**（10 个任务，KL-101a～KL-110a，见报告 §7）：优先级顺序为 hypv→supv 移交（KL-101a）→ cg 寄存器+escape 地基（KL-102a/103a，可与 RegRAS 机制调研 KL-105a 并行）→ syscall 捷径收口（KL-104a）→ MMU/TLB（KL-106a，需先决 4 条 open-issues）→ K2 测试框架扩展（KL-107a/108a/109a）→ pgtable 工作量校准（KL-110a，K3 立项前）。不建议把整个 SEE §5 作为单任务下发，按 cfx 逐个拆分。

## 审阅记录（subagent · 判决 = 通过）

- 本任务为纯调研（无代码改动），按 DS.md 自审流程精神，由执行者（本 subagent 自身）逐条核验以下证据链完整性：
  - 目标1：QEMU/gem5 patch series 逐项 grep（`escape`/`cfx2rc`/`inner_run_mode` 零匹配）✓，`contracts/isa/spec.md` §7 M1 Excluded 第957行原文引用 ✓
  - 目标2：SBI.md §4/§5 完整读取（非摘要），旧项目 `dadao-mmu-enable-design.md` CSR 风格代码原文对比 ✓，`docs/open-spec-issues.md` 4条 open issue 原文核对 ✓
  - 目标3：HBI.md §3 全文读取，发现 hypv 复位默认值与 ADR-0015 D2 表述的潜在张力（非报告臆测，基于 spec 原文"运行模式初始化为 hypv"）✓
  - 目标4：`sysmode-debug-lessons.md` 全文（432行）逐条读取，25条（非"约20条"字面数）逐条判定并给出当前仓库对应依据（非泛泛写"仍适用/不适用"）✓；RegRAS 新发现基于 AEE wiki 原文"须保存和恢复全部ra0-ra63"+`contracts/isa/spec.md`第958行`ldmo-ra/stmo-ra`排除项交叉验证 ✓
  - 目标5：`git log --stat`/`git show`逐提交核实（非只看commit message），确认 `arch/dadao` 为符号链接（`git ls-tree`验证blob类型120000）✓
  - 目标6：`run_differential.py`/`tests/vectors/isa/`/`tests/lit/E2E/`/`tests/e2e/`实际文件结构核对（非假设）✓
  - 目标7：K1清单交叉引用报告正文各章节结论，未凭空新增未经调研支撑的任务 ✓
- 未测/边界推敲：wiki pin 的 git 分支指针滞后于目标commit这一情况已在报告§0专门说明核实方法，避免读者误以为"读不到pin内容"；报告中"⚠️"类判定项明确标注"本次调研未核实/超出K0边界"，未过度断言
- finding：无（判决=通过）

## 架构师复核（ground-truth）

**独立验证方法**：调研类任务不涉及代码改动，复核重点是"结论有没有证据支撑、有没有过度断言"，抽查了本报告最关键/最反直觉的三条结论，直接读取原始来源核实：

- **SEE §5 现有实现是"host 侧捷径非真实现"**：独立 `grep -rc "escape\|cfx2rc\|inner_run_mode" components/qemu/patches/*.patch components/gem5/patches/*.patch` → 零匹配，逐字确认。
- **HBI §3"硬件复位后运行模式初始化为 hypv"**：独立 `git -C ~/DADAO-wiki show 9f378f4...:DADAO-13-HEE-超管系统运行环境.md` 读取原文，确认"hypv switch run mode"寄存器默认值"3 (hypv)"；独立读 `DADAO-12-SEE-主管系统运行环境.md` 确认"cfx_power_hypv_excp_vector 为硬件复位后的启动地址"——两处交叉印证"硬件永远从 hypv 态启动"这个结论成立，不是过度推断。这条发现（与 ADR-0015 D2 的理解张力）价值很高，值得单独向用户说明。
- **RegRAS 整栈保存/恢复缺少 ISA 层支持（本报告标注为"新发现"）**：独立读 `DADAO-11-AEE-应用程序运行环境.md` 原文确认"进程切换时，操作系统须保存和恢复全部 ra0-ra63 寄存器"；独立核对 `contracts/isa/spec.md` 第 958 行确认 `ldmo-ra`/`stmo-ra`（RA↔内存）确实在 M1 Excluded 表里，且 `rd2ra`/`ra2rd`（RA↔RD）同样排除——两处交叉验证，确认"当前 M1 连保存 RA bank 的指令通路都没有"这个结论真实、非夸大。这是本次调研最重要的发现，直接决定 K1 第一优先级任务（KL-105a）。
- **linux-0504 树"基本干净 vanilla 5.4"**：独立 `git log --oneline v5.4..HEAD` + `git ls-tree HEAD arch/dadao` 核实，确认 7(6)个提交、`arch/dadao` 确系 symlink（mode 120000），与报告描述一致。
- 报告整体质量评估：结构、证据链完整度、判定标准的一致性（✅/⚠️/❌ 三档）均达到或超过 ML-006a 的深度标准；K1 任务清单（KL-101a~110a）的依赖关系图和"不建议整体打包成单任务"的判断（引用 `feedback_ds_gem5_semantic_unreliable.md` 既有教训）合理。

**结论**：**KL-001a 验收通过**——报告质量高，关键结论均有原始来源交叉验证支撑，不是空泛断言。两个最有价值的发现（HBI hypv-reset 与 ADR-0015 D2 的理解张力、RegRAS 保存指令缺口）都直接影响后续任务规划优先级，建议向用户重点汇报这两点，再决定 K1 任务下发顺序（报告本身建议 KL-105a 作为"先调研不先实现"的高优先级项，因为"用什么机制保存RegRAS"这件事本身还没有答案）。
