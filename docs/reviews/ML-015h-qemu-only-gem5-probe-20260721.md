# ML-015h QEMU-only fixture Gem5 probe

日期：2026-07-21

## Probe result

对 `arrayresolution`、`bitops`、`minint` 分别按现有 `.test` 的 llvm-mc →
clang → llvm-objcopy 链路生成临时 ELF/bin，三步均 `rc=0`。

| fixture | expected | QEMU rc | Gem5 rc | Gem5 end marker |
|---|---:|---:|---:|---|
| arrayresolution | 0 | 0 | 0 | `SIM_END: halt code=0` |
| bitops | 249 | 249 | 249 | `SIM_END: halt code=249` |
| minint | 1 | 1 | 1 | `SIM_END: halt code=1` |

Gem5 使用 `timeout 10s` 包装，三个用例均未超时；stderr 只有现有 DRAM/stats
warning。没有使用 `|| true`。

## Decision

三个 fixture 的缺口目前看是遗漏 Gem5 RUN 行，而不是已复现的 ABI/loader
阻塞；它们具备下一任务补双后端断言的证据。但本报告不等同于已修改 `.test`
或已完成完整 E2E 回归，ML-015g 的 23/23 口径仍保持为仓库切片结果。

本任务只做 probe，没有修改实现、测试语义、issues/wiki 或 ML-014a。
