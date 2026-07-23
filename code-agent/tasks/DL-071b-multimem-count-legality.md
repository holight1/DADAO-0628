# DL-071b：multi-load/store count=0 指令级合法性

日期：2026-07-23

## 状态

待后续下发。

## 背景与范围

DL-071a 已完成所有 MC 编码字段的 signed/unsigned 范围检查。独立 review
指出：`immu6` 编码字段范围是 `[0,63]`，但 ISA 对 multi-load/store 的 count
另有限制 `[1,63]`；当前 assembler 和既有 `rrri.s` 仍接受 count=0。

后续任务应：

1. 只对 multi-load/store count operand 增加 `[1,63]` 指令级 matcher，不改变
   其它使用 `immu6` 的指令。
2. 修订既有正向测试并新增 count=0 负测试、1/63 边界正测试、64 负测试。
3. 由独立 reviewer 核对 spec、诊断、MC/E2E/differential 和 patch replay。

本文件只记录 finding，不在 DL-071a 中扩展实现范围。
