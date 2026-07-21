# ML-016b：musl output API linkability 独立 review（2026-07-21）

## 审计范围

本 review 独立阅读 `code-agent/tasks/ML-016b-musl-output-api-linkability.md`
的完成区，并逐项检查 `/tmp/ml-016b-musl-output-api-linkability-20260721/`
中的原始 `nm`/`llvm-nm`、compile/link/objcopy stderr/stdout、link map、ELF
符号和 QEMU/Gem5 输出。未修改 task、主线组件或 ML-014a；未访问或引用
`~/toolchain`、`~/knowledge-graph`。

目录中同时存在根目录产物和 `exact/` 产物。两组日志的错误、退出码和输出结论
一致；以下以对应的 probe 名称归纳，不把重复产物当成额外通过项。

## Findings

### F1 — archive 符号状态与报告一致

`nm`/`llvm-nm` 原始输出和空 stderr 支持其 rc=0。`llvm-nm.raw` 中可见：

- `write.o: T write`；`fputs.o: T fputs`；`printf.o: T printf`；`stdout.o:
  R stdout`；
- 没有精确的 `puts` 定义或未定义记录；
- `printf.o: U vfprintf`，未见 `T vfprintf`；
- `__stdio_write`、`__overflow`、`__fwritex`、`__towrite` 等 helper 有定义，
  但不能补上 `puts` 或 `vfprintf`。

**判定：确认。**

### F2 — exact-call link 结果与原始 linker error 一致

四个源文件的 clang compile 均为 rc=0。构建结果如下：

| probe | link | objcopy | 原始结果 |
|---|---:|---:|---|
| `puts("puts-ok")` | 1 | 未执行 | `ld.lld: error: undefined symbol: puts`，引用来自 `puts.o:(main)` |
| `fputs("fputs-ok", stdout)` | 0 | 0 | 生成 ELF/BIN |
| `printf("value=%d", 42)` | 1 | 未执行 | `ld.lld: error: undefined symbol: vfprintf`，来自 archive `printf.o` |
| fixed `write(1, ..., 8)` | 0 | 0 | 生成 ELF/BIN |

原文分别保存在 `puts.link.stderr` 和 `printf_int.link.stderr`；成功 probe 的
link/objcopy stderr 均为空。成功 ELF 由 ELF header/map 及符号表交叉确认：
两个 ELF 均为静态 ELF64、入口 `0x80000000`；`fputs_stdout.elf` 有 `main`、
`fputs`、`stdout`，`write_fixed.elf` 有 `main`、`write`。

**判定：确认。**

### F3 — fputs 仅证明可链接和返回，不证明 marker 输出

`fputs_stdout.elf` 内确实包含 `fputs-ok` 字符串，且两个后端均在 timeout 前以
guest rc=42 结束，但原始 stdout 没有该 marker：

- QEMU：`fputs_stdout.qemu.stdout` 只有 monitor 行和 `(qemu)` 空提示；
- Gem5：`fputs_stdout.gem5.stdout` 有 `SIM_START`、`SIM_END: trap-exit
  code=42`，没有 `fputs-ok`。

QEMU stderr 为空；Gem5 stderr 只有既有 warning/info（dot file、DRAM 容量、legacy
stat、stack-page），没有 fault、panic、abort 或 timeout。因此应记录为
“linkable/runtime-returnable, marker not observed”，不能记录为高层输出通过。

**判定：确认。**

### F4 — fixed write 双后端实际输出成立，但只能作为诊断 fallback

`write_fixed.elf` 在 QEMU 和 Gem5 均于 timeout 前 guest rc=42 结束，且两端原始
stdout 都含 `write-ok`：

- QEMU：`(qemu) write-ok`；
- Gem5：`SIM_START`、`SIM_END: trap-exit code=42`、`write-ok`。

该 probe 使用的是固定参数的底层 `write`，不是 `puts`、`fputs` 或整数-only
`printf`。所以这项正证据只说明 syscall/低层写路径可以工作；它**只能是诊断
fallback，不能算作 ML-014a 要求的 high-level output acceptance**。

**判定：确认。**

## 独立结论

**Audit-accepted-with-findings**。

ML-016b 的只读 linkability/双后端 probe 证据链可接受，但 findings 保留：
`puts` 因缺失符号无法链接，整数-only `printf` 因缺失 `vfprintf` 无法链接，
`fputs(stdout)` 虽可链接并返回 rc=42，却没有任一后端的 marker 输出。当前只有
fixed `write` 有双后端实际输出，且明确不得用它替代 ML-014a 的高层输出验收；据此
ML-014a high-level output acceptance 仍为 **Not accepted**。本 review 不实施修复。
