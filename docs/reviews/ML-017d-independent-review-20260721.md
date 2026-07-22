# ML-017d 独立 review

日期：2026-07-21（Asia/Shanghai）  
Reviewer：ML-017d independent reviewer

## 审阅范围与结论

审阅了 [ML-017d task](../../code-agent/tasks/ML-017d-final-handoff-roadmap.md)、
本轮 [final handoff report](ML-017d-final-handoff-roadmap-20260721.md)、
[ML-016 tracker](../../code-agent/tasks/ML-016-30-task-run-20260721.md)，以及
ML-016a~z、ML-017a~c 的 canonical task/report 和独立 review。未修改生产代码、旧
task/report、tracker 或原 ML-014a 文件；未查阅或引用禁用目录。

**结论：Accepted-with-findings。**

handoff 的事实、证据范围、阻塞边界和 A→E roadmap 均可接受；没有发现把 targeted
gate 写成完整 libc 或 puts success 的错误。保留一个已披露的 tracker 状态 finding，
以及一个必须继续阻塞后续高层输出验收的 puts finding。

## Blocking findings

### B-1：puts-success 仍是 A 路线的 blocking 子目标

这不是 handoff 文案错误，而是 handoff 正确携带的未闭合验收边界。ML-017c 独立
review 记录：

- `puts_probe` 在 QEMU/Gem5 均 `rc=42`、无 timeout，但没有 puts marker；
- `puts_return_bypass` 两端为 `PUTS_RC_ERR`；
- `puts_errno_bypass` 两端为 `PUTS_ERR_ERRNO_NONZERO`；
- fixed `write` 的 `write-ok` 只能作为正控制，不能替代 puts/flush 成功。

因此 handoff 将 A（stdio/writev/stdout runtime）列为首要阻塞，并明确禁止用
`rc=42`、fixed write、partial archive link 或 errno 诊断宣称高层 stdout/flush 已
通过，这一处理正确。该 finding 继续阻塞 puts-success，不拒绝本次“限定范围的
handoff”。依据：[ML-017c independent review](ML-017c-independent-review-20260721.md)。

## Non-blocking findings

### NB-1：artifact 计数与 tracker 状态不是同一口径

计数本身正确：ML-016a~z 为 26 项，ML-017a~c 为 3 项，加 ML-017d 为 30 项；
29 个既有任务均有 task/report 与 review 输入，ML-017d 自身尚待本 review。因此
handoff 中的“文件级 worker 交付 30/30”和“已有独立 review 29/30”成立。

但 tracker 的原始最后一行仍是 `29–30 | Pending`，并没有写入 ML-017d 的 30/30
完成状态。handoff 已明确说明 30/30 是 artifact count、tracker 不改写，且没有把
ML-017d 写成已独立验收；所以这是已披露的状态同步 finding，而不是隐性越界。严格
表述应为：**artifact 计数 30/30；tracker 状态仍为 29–30 Pending**。本 review
不修改 tracker，符合任务约束。依据：[tracker](../../code-agent/tasks/ML-016-30-task-run-20260721.md)
与 [handoff 计数表](ML-017d-final-handoff-roadmap-20260721.md)。

### NB-2：be99→d3bd causal isolation 仍未执行，但禁止越界声明已正确保留

final HEAD `d3bd9c15434fd7a48c0b7bab87354778cd932a72` 的 fresh matrix 是
1347 个对象、`1166/181`；stdio 为 `114/116`，失败对象为 `vfprintf.o` 与
`vfscanf.o`，四簇为 `157/16/7/1`。相对 ML-016u 的 `40bc` aggregate baseline
是 `0 regression / 0 migration`，但提交图是 `40bc → be99 → d3bd`，没有在
`be99` 上以同一工具、source/configuration 和方法重做 1347-object matrix。

handoff 正确禁止把该 aggregate comparison、静态 frame probe 或 varargs `0/0`
写成 `be99→d3bd` frame-only causal isolation；ML-017b 的 scope correction 也与
此一致。C 路线的“可选”定位不会阻塞已明确的 A/B gate。依据：
[ML-017a review](ML-017a-independent-review-20260721.md)、
[ML-017b review](ML-017b-independent-review-20260721.md)。

## 逐项核对

| 检查项 | 独立核对结果 |
|---|---|
| LLVM final commit | 正确记录 final nested commit `d3bd9c...`、parent `be99...`；四项落地修复为 AsmPrinter external symbol、inline-asm constraint、i1 sign extension、frame rounding。ML-016z 已把 ML-016y 的 final-head provenance blocking finding 闭合。 |
| 1166/181、四簇、stdio 114/116 | 与 ML-017a/ML-017b 一致：1347→1166 success/181 failure；四簇 `unsupported library call=157`、undefined physical register=16、dynamic_stackalloc=7、illegal result number=1；stdio 114/116，剩余 `vfprintf.o`/`vfscanf.o`。 |
| llvm-lit 边界 | 正确：因缺少 `llvm-config` 返回 `rc=2`；窄的 `llc | FileCheck` 通过不等于目录级 lit 或 full LLVM suite 通过。 |
| varargs 与输入形态 | final-head 正常 varargs QEMU/Gem5 为 `0/0`，odd/padding=4 仅静态边界；QEMU 是 launcher+同次链接 BIN，Gem5 是 `dadao_se.py` 直接接同次链接 ELF，不使用 QEMU launcher/BIN。 |
| partial archive 与 targeted gate | 1166-member archive 的 `ar=0`、`ranlib=0`、link/disasm/objcopy 及 `write_fixed`、`_Exit`、return-valued syscall 目标化运行证据成立；archive 明确为 `partial_incomplete`，不是完整 libc archive。 |
| mallocng / ML-014a / kernel | 正确保持未接受、未重新解决；partial archive 中的 mallocng object 不构成 ML-014a completion。kernel 尚未进入，用户态证据不替代 kernel bring-up。 |
| roadmap A→E | 顺序与证据一致：A 先闭合 stdio/writev/stdout；B 处理 `vfprintf`/`vfscanf` 与 157 libcall；C 可选地补 be99 parent matrix；D 再做真实 mallocng e2e；E 最后另行定义 kernel bring-up。每项都有 fresh provenance、双后端/marker 或逐对象门槛，以及相应禁止越界声明。 |
| targeted gate 的声明边界 | 未发现把 `write-ok`、`rc=42`、`varargs 0/0`、partial archive link 或无 marker 的 puts probe 写成完整 libc、完整 stdout/puts、ML-014a 或 kernel success。 |

## 最终交接判断

可接受的终点是：四项 LLVM 修复有其限定范围证据；final d3bd matrix 为 `1166/181`、
stdio 为 `114/116`；final-head varargs 为双后端 `0/0`；1166-member partial archive
及 fixed-write、`_Exit`、return-valued syscall targeted gate 通过；但 high-level
puts 在两端无 marker 且 errno bypass 非零。故本报告接受 handoff 的记录和 roadmap，
同时保留 B-1 与 NB-1/NB-2；不把本轮升级为完整 libc、ML-014a、puts 或 kernel 验收。

本文件为本 reviewer 唯一新增文件。
