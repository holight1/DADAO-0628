# ML-016c：fputs/stdout flush diagnostic review（2026-07-21）

## 审计范围

复核 `code-agent/tasks/ML-016c-fputs-stdout-flush-diagnostic.md` 完成区及
`/tmp/ml-016c-fputs-stdout-flush-diagnostic-20260721/` 中的 source、compile/link/objcopy 原始日志、失败 linker stderr、三份成功 ELF/BIN 和 QEMU/Gem5 原始 stdout/stderr。未修改主线组件、测试或 ML-014a。

## Findings

### F1 — 构建矩阵和失败 link 原文可复核

五个 probe 的 compile 均为 `rc=0`。三个成功链接 probe 的 link/objcopy 均为 `0`；两个 flush probe 的 link 均为 `rc=1`，objcopy 未执行。两份原始 stderr 都明确为 `undefined symbol: fflush`，引用分别来自 `fputs_fflush.o:(main)` 和 `fwrite_fflush.o:(main)`。archive `llvm-nm` 原始输出支持 `fputs`、`fwrite`、`write` 有定义，而 `fflush` 没有定义。

**判定：确认。**

### F2 — 同一产物双后端运行和退出状态可复核

成功链接的每个 probe 都由其对应 ELF 生成唯一 flat BIN；QEMU 运行该 BIN，Gem5 运行该 ELF。三份 probe 在两端均为 `rc=42`、timeout=`NO`。QEMU stderr 均为 0 bytes；Gem5 stderr 均为 443 bytes 的既有 warning/info，未见 fault、panic、abort 或 timeout。

**判定：确认。**

### F3 — fputs 返回值和 stdout marker 的阶段边界成立

`fputs_no_flush` 两端均没有 `FPUTS_NO_FLUSH` marker；`fwrite_no_flush` 两端均没有 `FWRITE_NO_FLUSH` marker。`fputs_return_bypass_write` 两端均输出 `BYPASS_FPUTS_RC_ERR`，该 marker 由固定参数 `write` 发出，说明 fputs 返回值走了负值分支；同时证明低层旁路 write 可观察。该旁路不等价于 stdio flush，也不构成高层输出验收。

**判定：确认。**

## 独立结论

**Audit-accepted-with-findings / Diagnosis-only。**

本轮锁定了两个不同阶段的问题：`fflush` 版本当前不能 link，属于 libc archive 可链接性缺口；在可链接的 `fputs`/`fwrite` 版本中，两后端虽正常返回 `42`，却没有 stdio marker，而 `fputs` 旁路报告返回错误。底层 `write` 的成功只可作为诊断 fallback，不能替代 ML-014a 要求的高层输出路径。因此 ML-014a 仍为 **Not Accepted**，本 review 不实施修复。
