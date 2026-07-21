# ML-016c 独立 review：fputs/stdout flush diagnostic（2026-07-21）

## 审计范围

独立阅读 `code-agent/tasks/ML-016c-fputs-stdout-flush-diagnostic.md`、
`docs/reviews/ML-016c-fputs-stdout-flush-worker-report-20260721.md` 和
`docs/reviews/ML-016c-fputs-stdout-flush-diagnostic-20260721.md`，并以
`/tmp/ml-016c-fputs-stdout-flush-diagnostic-20260721/` 下的 source、命令记录、
返回码文件、linker stderr、`llvm-nm` 原始输出及 QEMU/Gem5 原始
stdout/stderr 为准复核。本 review 只写入本文件。

## 核对结果

| probe | compile | link | objcopy | QEMU | Gem5 |
|---|---:|---:|---:|---|---|
| `fputs_no_flush` | 0 | 0 | 0 | rc=42, timeout=NO | rc=42, timeout=NO |
| `fputs_fflush` | 0 | 1 | not-run | 无 ELF | 无 ELF |
| `fwrite_fflush` | 0 | 1 | not-run | 无 ELF | 无 ELF |
| `fputs_return_bypass_write` | 0 | 0 | 0 | rc=42, timeout=NO | rc=42, timeout=NO |
| `fwrite_no_flush` | 0 | 0 | 0 | rc=42, timeout=NO | rc=42, timeout=NO |

### F1 — 两个 fflush probe 在 link 阶段失败，原文一致

`build/fputs_fflush.link.rc` 和 `build/fwrite_fflush.link.rc` 均为 `1`。
对应 stderr 分别为：

```text
ld.lld: error: undefined symbol: fflush
>>> referenced by fputs_fflush.c
>>>               .../fputs_fflush.o:(main)
```

```text
ld.lld: error: undefined symbol: fflush
>>> referenced by fwrite_fflush.c
>>>               .../fwrite_fflush.o:(main)
```

原始 `libc.llvm-nm.raw` 中可见 `fputs`、`fwrite`、`write` 的定义；
`ext.o` 只有 `U fflush`，没有 `fflush` 定义。因此两种 `fflush` 行为没有
进入 runtime，不能判作 flush runtime 失败。

**判定：确认。**

### F2 — 所有成功 probe 的双后端退出与 timeout 结果一致

三个成功 link/objcopy 的 probe 均分别使用记录中的 BIN（QEMU）和 ELF
（Gem5）运行。六个后端原始结果全部为 `rc=42`、`timeout=NO`。QEMU stderr
为空；Gem5 stderr 只有既有启动 warning/info，stdout 含正常的
`SIM_START` / `SIM_END: trap-exit code=42`，没有 fault、panic、abort 或
超时迹象。

**判定：确认。**

### F3 — 两种 no-flush probe 均没有 stdio marker

`fputs_no_flush` 的 QEMU stdout 只有 monitor 文本，Gem5 stdout 只有仿真器
启动/结束文本；两端均没有 `FPUTS_NO_FLUSH`。`fwrite_no_flush` 同样两端
均没有 `FWRITE_NO_FLUSH`。因此成功退出只证明程序走到 trap-exit，不能证明
stdio 缓冲内容已经写到可观察 stdout。

**判定：确认。**

### F4 — fixed write 旁路确认 fputs 返回负值，但不属于高层输出验收

`fputs_return_bypass_write.c` 以 `fputs_rc < 0` 选择旁路字符串。QEMU 和
Gem5 原始 stdout 均出现 `BYPASS_FPUTS_RC_ERR`，所以在该固定产物和运行
路径下，`fputs` 返回值确实走了负值分支；该字符串由固定参数的底层
`write(1, ...)` 发出。

这只能证明诊断旁路可观察，以及 `fputs` 返回了负值；它不证明 fputs 的
stdio 内容已 flush，也不能把 fixed `write` 的成功当作 ML-014a 所要求的
high-level output acceptance。

**判定：确认。**

## 独立结论

**Audit-accepted-with-findings。**

本轮诊断证据完整支持两个未解决 finding：

1. 当前 libc archive 缺少可链接的 `fflush` 定义；
2. 可链接的 `fputs`/`fwrite` no-flush probe 在 QEMU/Gem5 均无 stdio
   marker，且 `fputs` 返回负值。

fixed `write` 旁路仅是诊断 fallback，不构成 ML-014a high-level output
acceptance。因此 ML-014a 仍为 **Not Accepted**；本 review 不实施修复。
