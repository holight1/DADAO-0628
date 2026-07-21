# ML-016c worker report：fputs/stdout flush diagnostic

日期：2026-07-21

本轮在 `/tmp/ml-016c-fputs-stdout-flush-diagnostic-20260721/` 做临时 probe，未
修改主线或 ML-014a。

| probe | compile | link | objcopy | QEMU/Gem5 |
|---|---:|---:|---:|---|
| fputs no flush | 0 | 0 | 0 | 两端 rc=42，无 marker |
| fputs + fflush | 0 | 1 | N/A | `undefined symbol: fflush` |
| fwrite + fflush | 0 | 1 | N/A | `undefined symbol: fflush` |
| fputs return + fixed write | 0 | 0 | 0 | 两端 rc=42，输出 `BYPASS_FPUTS_RC_ERR` |
| fwrite no flush | 0 | 0 | 0 | 两端 rc=42，无 marker |

`fputs` 返回值通过固定 `write` 旁路报告为负；`fflush` 在 archive 中只有未
定义引用、没有定义。成功链接 probe 均无 timeout/fault。结论是 stdout 高层链路
仍未打通，fixed write 只能诊断旁路，ML-014a 仍未验收。
