# ADR-0015: kernel bring-up charter — Linux 5.4、暂不引入固件层、分阶段 K0-K4

**状态**：Accepted（2026-07-18）
**日期**：2026-07-18
**关联**：ADR-0014（libc/syscall charter，SEE trap 机制+musl 移植现状）、ADR-0012 D5（gcc-c-torture 终极目标）、ADR-0004（测试机 exit MMIO）、ADR-0009（四方验证链）

---

## 背景

DADAO-0628 的终极目标是 QEMU + kernel + 用户态应用全链路跑通。当前状态：M1 工具链+CodeGen+clang+picolibc 全部完成；musl 移植 Phase A/B 接近完成（syscall handler、crt0 auxv、arch/dadao 骨架、atomic_arch.h、pthread_arch.h+TP、crt_arch.h，首个 `int main(){return 42;}` 静态链接 E2E 里程碑已达成；DL-069a 正在修复 musl 集成中发现的指针调用约定 ABI 分歧）。kernel bring-up 此前一直是"Deferred Milestone"，未开始。

**已归档的预研项目 `~/toolchain/DADAO` 三轮尝试均未真正跑通**（详见调研，2026-07-18）：
- **V1**（照 RISC-V 猜测的非官方 ISA）：走得最远——kernel_init 运行、initrd 加载、打印出 `Run /init as init process`，但 `switch_mm` 从未真正激活新页表，执行 init 第一条指令即 ILLI fault；且这套 ISA 假设后来被官方 spec 全盘推翻。
- **V2/V4**（照官方 spec 重写）：架构更正确，bare-metal TDD 15/15→29/29 通过，boot 推进到 `do_initcalls`，但没到 V1 那个节点就卡在 RA 硬件栈自动溢出（该走 RASOF/RASUF 异常没走）+ 中断掩码极性 bug。
- **V5**（spec 又一次大改）：归档时仍在 Phase 0.5/1（QEMU 异常入口+编码），kernel 部分未开始。

**没有可直接复用的"能跑"kernel 镜像**——`__source/linux-0504` 的 `arch/dadao` patch 针对的 ISA 版本比当前 pin（`9f378f4426e131903d60a208766086ae74a53c89`）早至少5个不兼容修订，代码层面不可复用。**结论继承模式与 musl 相同**：只继承教训（~20条踩坑归类：ISA语义与文档不符、编译器后端缺口由kernel代码暴露、上下文切换寄存器保存完整性最痛、链接顺序/弱符号/调试代码删除等kernel特有坑、设计假设晚期暴露如装载地址/IO映射），不抄代码/patch。

## 决策

### D1：目标内核版本 = Linux 5.4（沿用旧项目选型，非硬性要求）

旧项目已验证 5.4 树本身（vanilla，非 DADAO patch 部分）可用作移植基线。用户明确此项非强制——若后续因构建工具链/驱动依赖等原因需要换版本，可以调整，不是路线图的阻断项。

### D2：暂不引入固件/SBI monitor 层，继续裸加载（用户 2026-07-18 决策）

ADR-0014 D4 曾把"guest 侧真 SEE monitor firmware（OpenSBI 式）"列为未来项。本次决策：**这次 kernel bring-up 暂不做**，继续沿用现有模式（QEMU/gem5 直接 `-kernel`/ELF 裸加载，无引导固件层，无 FDT/DTB）。旧项目 V1-V4 全程也是这个模式，没有因此被卡住——固件层不是达成"kernel 启动到用户态"这个里程碑的必需前置。若未来需要更贴近真实硬件的启动链，作为独立后续项再议。

**D2 补充澄清（KL-001a 调研，2026-07-18）**：`~/DADAO-wiki` HBI §3 规定硬件复位后运行模式**永远初始化为 hypv**（不是 supv），PC 跳到 `cfx_power_hypv_excp_vector`——"裸加载直接进 S-mode"在当前 spec 下没有对应硬件行为。**D2 的"暂不引入固件层"应理解为"不做 OpenSBI 式的复杂固件（设备树解析、多核唤醒协商等），但仍需要 HBI §3 规定的那段最小 hypv→supv 移交桩代码（约15-20条指令，纯 `cfx2rc` delegation + 一次 `escape`，wiki 给出了可参照的示例代码）"**，不是"硬件可以配置为直接从 supv 开始执行"。这段桩代码工作量很小，已列入 K1 任务清单第一项（KL-101a），必须先做，否则后续所有"从 S-mode 视角设计"的任务都建立在错误假设上。

### D3：分阶段路线图 K0-K4

| 阶段 | 内容 | 方法论参照 |
|------|------|-----------|
| **K0（调研，先行）** | 核对当前 wiki pin（9f378f4）的 SEE §5/中断模型/MMU-SBI 完整定义 vs DADAO-0628 现有实现（目前只有 `cfx_smon` syscall trap）缺口清单；确认 D1 内核版本；把旧项目 ~20 条踩坑提炼成"新 kernel 任务必读"清单；产出路线图报告（模式同 `docs/reviews/musl-recon-2026-07-16.md`） | ML-006a musl 调研 |
| **K1（SEE/SBI 基础设施）** | 补完整异常/中断模型（timer 中断、page fault、真正中断分派，不只 syscall trap）+ MMU/TLB SBI 式操作（PTBR/PTHI/PAHI）+ 特权级切换（User/S-mode），双后端（QEMU+gem5）实现，拆成若干增量任务 | musl Phase A/B 的增量任务节奏 |
| **K2（裸机内核态回归先行）** | 旧项目 V2/V4 比 V1 走得更正确的关键就是"先上 bare-metal TDD 再碰真 Linux"——上下文切换/trap 分派/MMU 开关等先用双后端+差分验证钉死，避免 V1"直接尝试跑 Linux"的教训 | V2/V4 方法论；ADR-0009 四方验证链 |
| **K3（真内核移植）** | `arch/dadao` 从零写（只继承教训，不抄代码/patch），Linux 5.4 树，目标先到 `do_initcalls`/`kernel_init` | 旧项目 20 条踩坑清单逐条规避 |
| **K4（收官里程碑）** | `Run /init` 真正执行一个 **musl 链接的用户程序**——直接对接 DADAO-0628 已完成的 musl 用户态工作，是"QEMU+kernel+用户态应用"字面达成的节点 | 衔接 ADR-0014 musl 工作 |

**gcc-c-torture 全量通过（ADR-0012 D5）与本路线图的关系**：大部分 torture 用例是单进程纯计算，预计可以在 K3/K4 之前独立继续推进（不需要真内核）；kernel 主要解锁需要 fork/exec/signal 的那批用例，不阻塞 D5 目标的主体进度。

### D4：ADR-0014 syscall ABI 寄存器编号与旧项目的关系（存档说明，非冲突）

旧项目的 syscall ABI（`nr=rd15`，`args=rd16..21`，`return=rd31`）与 ADR-0014 D2（`nr=rd16`，`args=rd17..22`，`return=rd31`）方向一致（同走 RD bank、返回值都在 rd31）但寄存器编号整体错开一位——ADR-0014 制定时 wiki 本就未定义这套 ABI，是本项目独立选定，不存在"应该兼容旧项目却不兼容"的问题，此处仅作历史记录，避免未来误以为两者可以直接对接。

## 后果

**正面**：有明确的分阶段目标和方法论参照（尤其 K2 的"先裸机测试再碰真内核"直接来自旧项目的失败教训，是本次相比旧项目的关键改进）；不引入固件层降低了当前阶段的复杂度；D1/D2 均标注非硬性，路线图有调整空间。

**负面/风险**：kernel bring-up 是目前为止最大的单体任务量级，旧项目三次尝试均未跑通，"这次会不同"完全依赖于 K0-K2 打的底子是否扎实（更完整的 SEE/中断模型+先行的裸机回归）——不能假设这次会顺利，需要按 K0→K1→K2→K3→K4 严格递进、每一步双后端+差分验证，不能跳步。

## 参考指针

- `~/toolchain/DADAO/code-agent/designs/`：`dadao-sysmode-v1-retrospective.md`（V1 详细回顾+被推翻的假设表）、`sysmode-debug-lessons.md`（~20 条踩坑 B01-B22+L1-L3）、`dadao-kernel-v2-plan.md`、`dadao-v5-migration-plan.md`、`dadao-v5-master-review.md`、`dadao-mmu-enable-design.md`、`dadao-userspace-plan.md`（仅供查阅结论，不可直接抄代码/patch）
- `docs/adr/0014-libc-syscall-charter.md` D4（SEE trap→CFXTRAP 现状+"未来真固件"的原始记录）、D2（当前 syscall ABI）
- `docs/adr/0012-test-tiering-strategy.md` D5（gcc-c-torture 终极目标，与本路线图的关系见 D3）
- `manifests/components.lock.toml`（`linux` 组件目前 `enabled=false`，K0 调研后决定何时启用+ pin 到哪个版本）
