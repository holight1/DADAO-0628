# KL-105a 独立 review（2026-07-21）

## 结论

**Needs-fix**

## 三条证据核验

1. **AEE 要求：有依据，但归因需收紧。** 原报告第 7、13–15 行把要求归于 AEE；调研报告第 160–166 行给出了 AEE 原文依据。因此“进程切换保存/恢复全部 `ra0-ra63`”有证据。不过 `contracts/isa/spec.md` §1.5/§7（第 63–78、947–959 行）只规定 RA 模型和 M1 排除项，并不单独证明“由 OS 负责”；原报告应明确该责任要求来自调研报告所引的 AEE pin，而不是 ISA §1.5/§7 本身。

2. **M1 excluded：指令判断准确。** 原报告第 21–22 行所称 `ldmo-ra`/`stmo-ra`、`rd2ra`/`ra2rd` 均与 ISA §7 第 947–959 行一致；ISA 第 208–213 行也将其列入多寄存器/RA 相关指令集合。`ldo`/`sto` 不能替代 RA bank 访问的判断没有发现反证。需要修正的是：方案 A 所需新指令的编码、槽顺序、原子性、对齐、越界和 fault 语义目前并非现行契约，不能写成已有行为。

3. **三方案与 bare-metal oracle：方案方向可作推断，但三个 oracle 当前不可执行。** 原报告第 17–29 行将 A/B/C 作为决策方案，整体没有把 C 说成现行契约，但第 21、23、27 行列出的硬件/指令语义仍应统一标注为“待 spec decision”。第 31–42 行的三个 oracle 都预设了 save/restore 指令、任意 RA bank 初始化、64 槽 dump 以及 save/restore 的非法对齐/越界异常；而当前 M1 明确排除这些 RA 访问指令（ISA 第 947–959 行），且 ISA 第 237–239 行的精确异常规则未定义未来 save/restore 的具体内存/fault 行为。因此目前既没有可执行的指令/编码与初始化路径，也没有可核验的异常预期。遗漏项是：先定义并实现最小 save/restore contract，再给出具体裸机汇编/装载布局、dump 通路和异常断言；在此之前三项只能算验收草案，不能称为可执行 oracle。

## 发现的问题

- `/home/holight/DADAO-0628/docs/reviews/kernel-regras-save-restore-20260721.md:13-15,21,23,27-42`：需区分现行 ISA 契约、AEE 外部依据和待决方案推断；三个 oracle 缺少当前 M1 可执行前提。
- `/home/holight/DADAO-0628/contracts/isa/spec.md:63-78,208-213,237-239,947-959`：支持 RA 模型及 M1 excluded，但没有提供未来 save/restore 的具体语义与可执行测试接口。
- `/home/holight/DADAO-0628/docs/reviews/kernel-bringup-recon-2026-07-18.md:160-166,229-234`：支持 AEE 要求及 KL-105a 的调研立项性质；不能替代尚未完成的 ISA/spec decision。

## Review 命令

```bash
nl -ba /home/holight/DADAO-0628/docs/reviews/kernel-regras-save-restore-20260721.md
rg -n -i 'AEE|RegRAS|ra0|ra63|ldmo-ra|stmo-ra|rd2ra|ra2rd|M1 Excluded|RASOF|RASUF' /home/holight/DADAO-0628/contracts/isa/spec.md
sed -n '160,166p;229,234p' /home/holight/DADAO-0628/docs/reviews/kernel-bringup-recon-2026-07-18.md
```

## 独立复核补充

本次仅只读核对 `kernel-regras-save-restore-20260721.md`、
`contracts/isa/spec.md` 与 `kernel-bringup-recon-2026-07-18.md`；结论保持
**Needs-fix**。

- ISA §1.5（spec:67–80）确立 `ra0`–`ra63`、RegRAS 槽位、引用计数和
  process-entry 全零，但没有给出可用于 context switch 的 RA bank 读写接口。
- ISA §7（spec:947–960）明确将 `ldmo-ra`/`stmo-ra` 与 `rd2ra`/`ra2rd`
  排除在 M1 外；§2.6.3 对这些名称的范围规则不构成启用它们的依据。
- ISA §2.7（spec:225–240）只为现行 ISA 异常规定精确性；报告所提
  save/restore 的对齐、越界、原子性和 fault 行为仍需新的 spec decision，
  因而三个 bare-metal oracle 目前是验收草案，不是现行可执行 contract。
- bring-up recon §4.1（160–166）和 KL-105a 任务表（233）都把“先确定
  RegRAS 保存/恢复机制”定位为调研/立项前置项，而非已完成实现。

复核命令：

```bash
nl -ba /home/holight/DADAO-0628/docs/reviews/kernel-regras-save-restore-20260721.md
nl -ba /home/holight/DADAO-0628/contracts/isa/spec.md | sed -n '63,80p;210,240p;947,960p'
nl -ba /home/holight/DADAO-0628/docs/reviews/kernel-bringup-recon-2026-07-18.md | sed -n '160,170p;229,234p'
```
