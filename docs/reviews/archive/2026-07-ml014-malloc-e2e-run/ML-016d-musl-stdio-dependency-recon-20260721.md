# ML-016d 独立 review：musl stdio dependency recon（2026-07-21）

## 审计范围

独立核对 `code-agent/tasks/ML-016d-musl-stdio-dependency-recon.md` 的完成区、
`/tmp/ml-016d-musl-stdio-dependency-recon-20260721/` 下的 probe source、compile/link/
objcopy 原始输出、link map 及 QEMU/Gem5 原始 runtime 结果；并只读检查当前
`.work/source/musl` 与 `.work/build/musl/lib/libc.a` 的 archive/object、`llvm-nm`
和 `llvm-objdump` 结果。本 review 不修改实现、archive、主线或 ML-014a。

## 核对结果

### 1. 调用链与 syscall 入口

源码和已链接 ELF 的 map/反汇编一致支持以下 stdout 路径：

```text
fputs -> fwrite -> __fwritex -> __stdout_write -> __stdio_write -> SYS_writev(66)
```

这里 `__stdout_write` 是 stdout 初始的 `FILE.write`，会把该指针切换为
`__stdio_write` 后继续调用它；因此省略它的简写仍不能把 `fputs` 说成直接调用
`__stdio_write`。具体证据为：

- `src/stdio/fputs.c:4-7` 调用 `fwrite`，并在写入长度不等于字符串长度时返回
  `-1`；`src/stdio/fwrite.c:4-10,28-35` 经 `__fwritex` 调用 `f->write`。
- `src/stdio/stdout.c:6-18` 将 stdout fd 初始化为 `1`、初始 write pointer 设为
  `__stdout_write`；`src/stdio/__stdout_write.c:4-10` 设置为 `__stdio_write`。
- `src/stdio/__stdio_write.c:4-25` 直接使用 `syscall(SYS_writev, ...)`。其
  `llvm-objdump --triple=dadao -dr` 在两个 syscall site 均显示 `rd16 = 66`、
  参数进入 `rd17..rd19`、`trap 2, 0`，随后调用 hidden `__syscall_ret`。
- `arch/dadao/bits/syscall.h.in:77-79` 定义 `write=64`、`writev=66`；
  `src/internal/syscall.h:44-45` 将 `syscall(...)` 映射到
  `__syscall_ret(__syscall(...))`。公共 `writev.o` 则是另一条
  `writev -> __syscall_cp -> __syscall_ret` 路径，反汇编同样装入 syscall number
  `66`，不能与 stdio 内联路径混为同一个 object wrapper。

### 2. archive/object 状态

当前 `libc.a` 的 `llvm-nm -A`/member inventory 证实 `fputs.o`、`fwrite.o`
（含 `__fwritex`）、`__stdout_write.o`、`__stdio_write.o`、`stdout.o`、
`stdin.o`、`stderr.o`、`write.o`、`writev.o`、`__syscall_cp.o` 和
`syscall_ret.o` 存在并可被成功 probe 拉入。链接 map 进一步显示成功的
`fputs_rc` ELF 实际包含 `__stdout_FILE`、`__stdout_used`，以及 stdout 的
`.fd=1` 初始化 object；因此本轮没有证据把负值归因于 stdout fd object 缺失。

相反，以下 source 存在但 build object/archive member 不存在：

| API | source | 缺失 object / archive 定义 | link probe |
|---|---|---|---|
| `fflush` | `src/stdio/fflush.c:8-47` | `fflush.o` / 无 `T fflush` | `rc=1`，`undefined symbol: fflush` |
| `fileno` | `src/stdio/fileno.c:4-16` | `fileno.o` / 无 `T fileno` | `rc=1`，`undefined symbol: fileno` |
| `fdopen` | `src/stdio/__fdopen.c:9-61` | `__fdopen.o` / 无 `T __fdopen`、`T fdopen` | `rc=1`，`undefined symbol: fdopen` |

三个 probe 的 compile 均为 `0`，link 原始 rc 均为 `1`，objcopy 未运行。当前
`Makefile:22-31,165-168` 的 wildcard/object/archive 规则理论上覆盖这些 source；
这只把问题边界收敛到 build/archive object 选择或产物状态，不能从本轮证据判定
是 manifest 裁剪、stale archive 还是具体构建步骤遗漏。

### 3. runtime 与返回值

`fputs_rc` 和 `writev_rc` 的成功链接产物分别在 QEMU 与 Gem5 运行。原始结果为：

| probe | QEMU | Gem5 | 入口返回/marker |
|---|---|---|---|
| `fputs_rc` | `rc=42`, timeout=`NO` | `rc=42`, timeout=`NO` | `FPUTS_RC_NEG1` |
| `writev_rc` | `rc=42`, timeout=`NO` | `rc=42`, timeout=`NO` | `WRITEV_RC=-1` |
| `fwritex_link` | `rc=42`, timeout=`NO` | `rc=42`, timeout=`NO` | `FWX_RC_0` |
| `stdio_write_link` | `rc=42`, timeout=`NO` | `rc=42`, timeout=`NO` | `SW_RC_0` |

`FPUTS_RC_NEG1`、`WRITEV_RC=-1` 和其他 marker 都由 probe 在调用后通过固定
`write(1, ...)` 旁路报告；guest `rc=42` 是最终 trap-exit code，不是 stdio
返回值。QEMU stderr 均为空；Gem5 仅有既有启动 warning/info，无 fault、panic、
abort 或 timeout。因而可以确认 `fputs` 与独立 public `writev` 在两个后端都
返回 `-1`，同时不能把 fixed `write` 的可用性或成功退出当作 stdio 输出验收。

## Findings 与边界

证据支持且仅支持以下两个待定位边界：

1. **build/archive 边界**：`fflush`、`fileno`、`__fdopen` 的 source 存在，但
   当前 libc archive 缺少对应 object/定义，三个 link probe 失败。
2. **writev responder 边界**：stdio 内联 `SYS_writev=66` 路径与独立 `writev`
   probe 均得到 `-1`；本轮未定位该返回值在两个后端 responder 中对应的具体
   errno、参数契约或实现分支。

不把上述任一边界进一步归因于特定 manifest、syscall ABI、fd 初始化或 runtime
实现，也不在本 review 实施修复。后续若继续，应分别定位 archive/object 选择与
`SYS_writev=66` responder 语义，再复验高层 stdio；两者不应合并为一个推测性根因。

## 独立结论

**Audit-accepted-with-findings**

本轮 recon 的 source/archive/link/runtime 证据链完整，且两个未决边界已被清楚
分离；finding 保留为待定位事项，不构成修复或归因结论。
