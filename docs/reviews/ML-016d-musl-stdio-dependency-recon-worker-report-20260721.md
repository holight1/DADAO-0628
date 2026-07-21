# ML-016d worker report：musl stdio dependency recon

日期：2026-07-21

本轮只读检查当前 musl source/archive，并在
`/tmp/ml-016d-musl-stdio-dependency-recon-20260721/` 做临时 probe，未修改主线。

## 结论

- 调用链：`fputs → fwrite → __fwritex → __stdio_write → SYS_writev(66)`。
- `fputs` 返回 `-1`；直接 `writev` probe 也返回 `-1`。
- stdout FILE objects 存在，fd 为 1/0/2；没有证据表明本轮首先是 fd 初始化
  缺失。
- 当前 archive 缺少 `fflush.o`、`fileno.o`、`__fdopen.o`；对应 link 均
  `rc=1`，但源码和 wildcard Makefile 中这些文件存在，需后续复核构建产物选择。
- 成功诊断 probe 的 QEMU/Gem5 均 `rc=42`、无 timeout；固定 write 只作为
  旁路报告，不代表高层输出验收。

## 后续边界

先复核 musl build/archive object 选择，再单独核对 QEMU/Gem5 `SYS_writev=66`
responder 的 errno/return contract；本任务没有实施修复。
