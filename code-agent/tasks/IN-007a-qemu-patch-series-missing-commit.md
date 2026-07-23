# IN-007a：补齐 QEMU patch series 缺失历史提交

日期：2026-07-23

## 状态

待处理。

## 背景

ML-025a worker 与独立 reviewer 均确认：QEMU live 历史从 manifest pin 到
`cf5c06b...` 有 21 个线性提交，component series 只有 20 条。缺失的是
`e7639ea9a84ecfd42b28d387fb5ca5383999605e`
（DL-026a divs/divu TCG label fix + machine/CPU hardening）。它在真实历史中
位于现有 0006 与 0007 之间，并创建后续 0008 所需的 `helper_exit()`。

## Ownership 与约束

- 只允许新增由 `e7639ea...` 原样导出的 QEMU patch、调整 QEMU series 中的
  文件名编号/顺序以插入正确历史位置、本任务完成区及 worker report。
- 不修改 `.work/source/qemu` 源码或历史、其它 component、测试、issues、
  roadmap、wiki。
- 不得把缺失提交合并进相邻 patch，不得改其源码 payload，不得改变后续 patch
  最终表达的 tree。

## 目标

1. 从真实提交导出 patch，在现有 0006 与原 0007 之间插入。
2. 必要时机械重编号原 0007～0020，并同步 series；内容不得变化。
3. 从 QEMU manifest pin plain `git am` 全 series，必须 21/21。
4. 最终重放 tree 与 live QEMU HEAD `cf5c06b...` 一致。
5. 运行 QEMU build、E2E、differential、manifest/issues。

## 验收

独立 reviewer 必须核对缺失 patch 的 patch-id/tree、插入位置、后续 patch
payload 未变化、21/21 replay 与最终 tree identity。
