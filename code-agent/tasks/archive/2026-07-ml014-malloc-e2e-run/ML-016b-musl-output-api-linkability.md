# ML-016b：musl 输出 API 可链接性与双后端可用性审计

**日期**：2026-07-21

**状态**：Audit-accepted-with-findings（ML-016 新 30-task run：2/30）

## 背景

ML-016a 的 mallocng 双块 probe 在两后端均 `rc=42`，但使用的是固定参数
`write`；尝试 `puts` 时当前 `libc.a` 链接失败：`undefined symbol: puts`。
ML-014a 要求使用 `puts/fputs` 或仅整数参数的 `printf` 做高层输出验证，因此
需要先精确知道当前构建产物支持哪些 API。

## 目标与 ownership

worker 只做只读 archive inventory 和 `/tmp` 临时 probe：

1. 用 `nm/llvm-nm` 统计当前 `.work/build/musl/lib/libc.a` 中
   `write/puts/fputs/printf` 及相关符号的定义/未定义状态。
2. 为 `puts("...")`、`fputs("...", stdout)`、`printf("value=%d", 42)`、
   固定参数 `write` 分别生成最小临时 ELF，记录 compile/link/objcopy rc。
3. 对能链接的 probe 使用同一 ELF 分别跑 QEMU/Gem5，记录真实 rc、输出和
   timeout；不能链接的 API 保留原始 linker error。
4. 给出 ML-014a 最小可接受输出路径，不修改主线 libc、musl、测试或 ML-014a。

## 约束

- 只允许写本 task 完成区和
  `docs/reviews/ML-016b-musl-output-api-linkability-20260721.md`；临时文件放
  `/tmp`。
- 不修改 LLVM/QEMU/gem5/musl、contracts、vectors、issues、wiki 或 ML-014a。
- 不访问或引用 `~/toolchain`、`~/knowledge-graph`；不使用 `|| true`，不忽略
  任一后端退出码。

## 完成区

（由 worker 填写；完成后由不同 subagent 独立 review）

### 完成与 review

worker 结果记录在 `docs/reviews/ML-016b-output-api-worker-report-20260721.md`；
独立 review 记录在 `docs/reviews/ML-016b-musl-output-api-linkability-20260721.md`，
结论 **Audit-accepted-with-findings**。

- `puts`：link `rc=1`，`undefined symbol: puts`。
- `printf("value=%d", 42)`：link `rc=1`，`undefined symbol: vfprintf`。
- `fputs(stdout)`：link 成功、QEMU/Gem5 均 `rc=42`，但没有观察到 marker。
- 固定 `write`：双后端实际输出 `write-ok`；仅为诊断 fallback，不能替代
  ML-014a 要求的高层输出验收。

ML-014a 仍为 Not Accepted；没有修改主线组件或 ML-014a。

## 完成区（2026-07-21）

**状态**：Completed / 只读 linkability probe；ML-014a 仍未验收。

本轮只在 `/tmp/ml-016b-musl-output-api-linkability-20260721/` 生成临时
C/object/ELF/BIN/log，没有修改 LLVM、QEMU、Gem5、musl、contracts、vectors、
issues、wiki 或 ML-014a。构建输入是当前 `.work/build/llvm/bin/clang`、
`ld.lld`、`llvm-objcopy`、`.work/build/musl/lib/crt1.o`、
`.work/build/musl/lib/libc.a` 和 `tests/scripts/dadao.ld`。

### 1. archive 符号审计

`nm .work/build/musl/lib/libc.a` 与
`.work/build/llvm/bin/llvm-nm -A .work/build/musl/lib/libc.a` 均返回 **rc=0**。
llvm-nm 的相关定义/未定义记录为：

| 符号 | archive 状态 |
|---|---|
| `write` | `T` 定义在 `write.o`；`eventfd.o` 另有 `U write` 引用 |
| `puts` | 没有该精确符号记录（无定义、无 archive 内未定义记录） |
| `fputs` | `T` 定义在 `fputs.o`；`err.o` 另有 `U fputs` 引用 |
| `printf` | `T` 定义在 `printf.o` |
| `vfprintf` | 多个 `U` 引用，未见 `T` 定义；`printf.o` 的实现依赖它 |
| `stdout` | `R` 定义在 `stdout.o` |
| `__stdio_write` / `__overflow` / `__fwritex` / `__towrite` / lock helpers | archive 中存在相应 `T` 定义及若干 `U` 引用 |

### 2. exact-call 构建尝试

四个临时源分别是 `puts("puts-ok")`、`fputs("fputs-ok", stdout)`、
`printf("value=%d", 42)` 和固定参数 `write`。四次 clang 编译均为
**rc=0**。

```text
puts         compile=0  link=1  objcopy=not-run
fputs_stdout compile=0  link=0  objcopy=0
printf_int   compile=0  link=1  objcopy=not-run
write_fixed  compile=0  link=0  objcopy=0
```

失败 linker 原文：

```text
ld.lld: error: undefined symbol: puts
>>> referenced by puts.c
>>>               /tmp/ml-016b-musl-output-api-linkability-20260721/exact/puts.o:(main)
```

```text
ld.lld: error: undefined symbol: vfprintf
>>> referenced by printf.c
>>>               printf.o:(printf) in archive .work/build/musl/lib/libc.a
```

### 3. 可链接 ELF 的双后端运行

每个后端使用同一次链接产生的 ELF；QEMU 按当前 M1 入口运行该 ELF 的唯一
`llvm-objcopy -O binary` flat twin，Gem5 直接运行同一个 ELF。
两次运行的 timeout 均为 **NO**，后端 rc 均为 **42**。

| probe | QEMU rc/timeout/stdout | Gem5 rc/timeout/stdout |
|---|---|---|
| `fputs_stdout` | `42` / `NO` / `QEMU 10.0.0 monitor - type 'help' for more information` + `(qemu)`；没有 `fputs-ok` | `42` / `NO` / 原始 stdout 含 `SIM_START`、`SIM_END: trap-exit code=42`；没有 `fputs-ok` |
| `write_fixed` | `42` / `NO` / monitor 两行后为 `write-ok`（无换行） | `42` / `NO` / `SIM_START`、`SIM_END: trap-exit code=42`、`write-ok` |

QEMU 两次 stderr 均为空；Gem5 两次 stderr 均只有既有 dot-file、DRAM 容量、
legacy stat 和 stack-page warning/info，无 fault、panic、abort 或 timeout。
最终 ELF SHA-256 为：`fputs_stdout.elf`
`6adbdf1e992e8cf02e7cee0dd8a9d5452d3bf54c72cc7337a10a235755f2dcce`，
`write_fixed.elf`
`58bf2e317594ef4c6bee9e04b6caaae67ab63d972001c2211c3edc66048689d9`。

### 4. 结论

当前 libc archive 中只有固定参数 `write` 有实际双后端输出证据：它有 archive
定义、能完成 clang/link/objcopy，并在当前 QEMU/Gem5 均实际输出 `write-ok`
且 rc=42。它只能作为诊断 fallback，不能替代 ML-014a 要求的
`puts`/`fputs`/整数-only `printf` 高层输出验收。`fputs(stdout)` 虽能链接并双
后端 rc=42，但本 probe 两端均没有观察到 `fputs-ok`，只能判为“可链接、未
证明 stdout 输出”。`puts` 无法链接，`printf("value=%d", 42)` 因缺少
`vfprintf` 无法链接；ML-014a 的高层输出验收仍未通过。
