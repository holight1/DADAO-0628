# ML-025a：QEMU/gem5 零长度 mmap 一致性

日期：2026-07-23

## 状态

待处理。

## 背景

ML-024a 诊断发现：`libc.page_size==0` 时，QEMU 的 cfx_smon mmap responder
对 `length==0` 返回 `-EINVAL`，而 gem5 返回一个非空但未映射的地址，导致同一
错误在两后端分别表现为 malloc 返回 NULL 与后续 MALIGN。AT_PAGESZ 根因修复后
正常 malloc 不再触发该差异，但 responder 的错误输入语义仍不一致。

## Ownership 与约束

- 允许修改 QEMU/gem5 各自 mmap responder 的最小实现、对应 component patch
  与 series、新增主仓测试、本任务完成区及 worker report。
- 不修改 LLVM、musl、ISA/ABI contract、kernel、wiki。
- 两个 component 都必须在当前 HEAD 上新增普通 commit；禁止 rebase、reset、
  amend 或历史重写。
- 先用同一个 raw syscall 最小探针独立复现，不得用 malloc 间接现象代替。
- 优先保持 Linux/asm-generic `mmap(length=0) -> -EINVAL` 语义；若现有项目契约
  有相反规定，必须停止实现并报告冲突。

## 目标

1. 新增判别性 E2E：直接执行 syscall 222，length=0，检查返回值为 `-EINVAL`；
   同时保留正常非零 mmap 成功的控制项。
2. 修正 gem5，使 QEMU/gem5 返回值与副作用一致；确认零长度请求不推进 arena
   cursor、不建立 VMA。
3. 避免只比较退出码；测试需检查 raw return 和后续正常 mmap 地址。
4. 重建 QEMU/gem5，运行新增测试、全量 E2E、differential、manifest/issues。
5. 导出两侧普通 patch，并从各自裸 pin 全量重放 series。

## 验收

双后端同一探针均通过；正常 mmap/malloc E2E 不回归；独立 reviewer 检查两侧
错误码、arena/VMA 副作用与 patch replay。
