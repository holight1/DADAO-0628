# DADAO-0628 KL-105a：RegRAS 保存/恢复最小交付

**日期**：2026-07-21　　**范围**：M1 → K1 决策输入

## 结论

AEE 要求进程切换时保存、恢复完整 `ra0-ra63`；但 M1 的 RegRAS 只有
`call`/`ret` 自动进出栈，当前没有把 RA bank 读写到内存或 RD bank 的通路。
因此“只靠现有 M1 软件完成保存”不可行。K1 推荐方案 **A：重新纳入整 bank
RA 访问指令**，优先评估恢复 `ldmo-ra`/`stmo-ra`。这是架构决策建议，
不是现行 ISA 行为；必须先冻结指令语义、内存布局、精确异常和汇编/双模拟器
行为，再进入实现。方案 C 也只能作为另立的 SEE/spec decision，不能假定现有
trap 已经自动保存 RegRAS。

**依据**：AEE 要求及其 wiki pin 的原文由
`docs/reviews/kernel-bringup-recon-2026-07-18.md §4.1` 转引（这是外部 AEE
环境契约，不是 ISA §1.5/§7 单独推出的 OS 责任）；
`contracts/isa/spec.md §1.5、§7` 只作为 RA 模型及 M1 排除项依据，
`docs/reviews/kernel-bringup-recon-2026-07-18.md §7/KL-105a`（K1 先做机制立项）。

## 三方案比较

| 方案 | 判断 | 代价与边界 | 依据 |
|---|---|---|---|
| **A．重新纳入整 bank 指令** | **推荐的 K1 决策方向**。由内核显式把 64 个 RA 槽保存/恢复到约定 frame；若 AEE 责任要求保持不变，它最接近 OS 可控的责任划分，且不改变普通 `call`/`ret` 路径。 | 现行契约没有这些指令行为；需要先补回/新增编码、槽顺序（含 `ra0`）、原子性、对齐/越界和 fault 行为，并同步 assembler、QEMU、gem5。 | `contracts/isa/spec.md §1.5、§2.7、§7`；`docs/reviews/kernel-bringup-recon-2026-07-18.md §4.1、§4.2(1)、§7/KL-105a`。 |
| **B．软件逐槽** | **当前明确不可行**。逐槽必须有 `ra2rd`/`rd2ra` 或等价读写指令；这两条与 RA 内存访问均被 M1 排除，软件无法观察或写回 RA bank。即使未来恢复，64 槽循环也会放大顺序、引用计数和中途 fault 风险。 | 不应把“已有 `ldo`/`sto`”误当作 RA 访问；它们不能访问 RegRAS。 | `contracts/isa/spec.md §1.5、§3.14、§7`；`docs/reviews/kernel-bringup-recon-2026-07-18.md §4/B04、B07、B11`；`contracts/abi/spec.md §1.4`。 |
| **C．硬件 / trap frame** | 备选架构方向，不是现行行为。由硬件在切换或 trap entry/exit 时自动把完整 RA bank 纳入 context/trap frame，软件不逐槽操作。 | 需另行定义 trap frame 格式、嵌套/跨 CFX escape、保存时机、异常可重入性及 reset 语义；会扩大 SEE、CPU 状态和双后端改动面。若 trap 并非每次进程切换触发，还需另设切换接口。 | `docs/reviews/kernel-bringup-recon-2026-07-18.md §1.1、§3.3、§4.1`；`docs/open-spec-issues.md` 的 **Cross-cfx escape**、**Hardware reset**；`contracts/isa/spec.md §2.7`。 |

## K1 决策与三个 bare-metal oracle

K1 先选 **A** 作为决策方向，交付“可被测试机观察的整 bank save/restore
contract”，不直接把 C 混入 trap 语义。若架构师要求 trap 对所有 RA 状态透明
保护，再以 C 另立 SEE/spec decision；B 在当前 M1 直接判定为不可行。
下面三个是 **contract 冻结后的验收草案，不是当前 M1 可执行的 oracle**；在
指令、初始化/读取通路、内存布局和异常语义落定前，不能声称已有可运行测试：

1. **全槽 round-trip（待 contract 后实现）**：用 64 个互异的 `(refcount, pc[47:0])` 向量建立 RA
   bank，执行 save→改写/清空→restore，再 dump 64 槽；期望 `ra0-ra63` 每一位
   与原向量相等，尤其不得丢 `bits[63:48]` 引用计数。依据：
   `contracts/isa/spec.md §1.5、§5.6`；`docs/reviews/kernel-bringup-recon-2026-07-18.md §4.1`。
2. **切换隔离（待 contract 后实现）**：准备互不相同的 A/B 两个 RA frame；保存 A、装入 B 并完成一组
   嵌套 `call`/`ret`，再恢复 A。期望 B 的返回地址序列不泄漏到 A，恢复 A 后
   `ret` 回到 A 的预设 PC，且 64 槽逐值一致。依据：
   `contracts/abi/spec.md §1.4、§4.4、§5.2–§5.3`；`contracts/isa/spec.md §5.4–§5.6`。
3. **边界与精确性（待 contract 后实现）**：分别覆盖全零 bank、`refcount>1` 的递归槽、最后有效槽，
   并触发 `RASOF/RASUF` 及 save/restore 的非法对齐或越界输入。期望正常路径
   保留空槽和引用计数；异常精确、fault 指令不产生部分 bank/内存更新。依据：
   `contracts/isa/spec.md §1.5、§2.7、§7`；`docs/reviews/kernel-bringup-recon-2026-07-18.md §4/B11、B13`。
