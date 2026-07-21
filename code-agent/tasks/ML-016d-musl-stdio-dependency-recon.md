# ML-016d：musl stdio 依赖与 syscall 失败来源 recon

**日期**：2026-07-21

**状态**：Audit-accepted-with-findings（ML-016 新 30-task run：4/30）

## 背景

ML-016c 已确认：`fputs` 返回负值；`fflush` 在当前 `libc.a` 中没有定义；
固定 `write` 可用。需要确认 fputs 负值来自哪个 libc stdio object、底层 syscall
（例如 writev）、stdout fd/FILE 初始化还是 DADAO port 的构建裁剪。

## 目标与 ownership

worker 只做 source/archive/relink 诊断，不修改实现：

1. 阅读当前 musl `src/stdio`、`src/internal`、DADAO arch/syscall glue 和
   arch.mak；用 `nm/llvm-nm` 追踪 `fputs → __fwritex → __stdio_write` 及其
   syscall/object 依赖，确认 `fflush`/`writev`/fd 初始化符号状态。
2. 在 `/tmp` 构建最小 probe（可调用固定 write 报告返回值），分别验证能否
   直接链接/调用候选底层入口；保留原始 link/runtime rc，不修改 libc archive。
3. 给出最小、可审查的后续修复边界：build manifest 缺 object、stdio 配置、
   syscall ABI 或 runtime fd 初始化；不凭猜测选择修复。

## 约束

- 只写本 task 完成区和
  `docs/reviews/ML-016d-musl-stdio-dependency-recon-20260721.md`；临时产物放
  `/tmp`。
- 不修改 LLVM/QEMU/gem5/musl、contracts、vectors、issues、wiki 或 ML-014a。
- 不访问或引用 `~/toolchain`、`~/knowledge-graph`；不使用 `|| true`，不忽略
  任一后端退出码。

## 完成区

（由 worker 填写；完成后由不同 subagent 独立 review）

### 完成（2026-07-21）

**状态**：Completed / source、archive、relink 与双后端诊断；未修改实现。

本轮只在 `/tmp/ml-016d-musl-stdio-dependency-recon-20260721/` 生成临时源、
object、ELF、flat BIN、map、原始 link/runtime 输出。使用当前
`.work/build/musl/lib/crt1.o`、`.work/build/musl/lib/libc.a`、DADAO clang/lld、
`tests/scripts/dadao.ld`，没有重建或写入 libc archive/source。

#### 结论

- `fputs` 的源码链是 `fputs -> fwrite -> __fwritex -> f->write`；stdout 的
  初始 `f->write` 是 `__stdout_write`，随后设置为 `__stdio_write`。
- `__stdio_write.o` 直接内联 `syscall(SYS_writev, ...)`，目标 syscall 号为
  `66`，并在 `trap 2, 0` 后调用 hidden `__syscall_ret`；它不调用 archive
  中的 `writev.o`。`writev.o` 是另一路公共 wrapper，经 hidden
  `__syscall_cp -> __syscall_ret`。
- `stdout.c`/`stdin.c`/`stderr.c` 在 archive 中存在，FILE fd 分别为
  `1/0/2`，且 `stdout` 的 `__stdout_FILE`/`__stdout_used` 已被实际 ELF
  拉入；没有证据表明本轮负值来自 fd 初始化缺失。
- 当前 archive 缺少 `fflush.o`、`fileno.o`、`__fdopen.o`，对应定义也缺失；
  三个 link probe 的原始 linker rc 都是 `1`。源码 Makefile 使用
  `src/*/*.c` wildcard，且 `src/stdio/fflush.c` 等文件确实存在，因此可审查
  的边界是当前 build/archive object 选择或产物陈旧，不是猜测某个 syscall ABI
  修复。
- `fputs` 负值在两后端复现为 fixed-write marker `FPUTS_RC_NEG1`；直接
  `writev` 复现为 `WRITEV_RC=-1`。这把失败边界收敛到 stdio 使用的 writev
  syscall 路径；固定 `write` 旁路仍可用，但不能替代 stdio 验收。

#### 构建与运行矩阵

| probe | compile | link | objcopy | QEMU rc/timeout | Gem5 rc/timeout | fixed-write return marker |
|---|---:|---:|---:|---|---|---|
| `fputs_rc` | 0 | 0 | 0 | 42 / NO | 42 / NO | `FPUTS_RC_NEG1` |
| `writev_rc` | 0 | 0 | 0 | 42 / NO | 42 / NO | `WRITEV_RC=-1` |
| `fwritex_link` | 0 | 0 | 0 | 42 / NO | 42 / NO | `FWX_RC_0` |
| `stdio_write_link` | 0 | 0 | 0 | 42 / NO | 42 / NO | `SW_RC_0` |
| `fflush_link` | 0 | 1 | not-run | not-run | not-run | linker: undefined `fflush` |
| `fileno_link` | 0 | 1 | not-run | not-run | not-run | linker: undefined `fileno` |
| `fdopen_link` | 0 | 1 | not-run | not-run | not-run | linker: undefined `fdopen` |

QEMU stderr 为 0 bytes；Gem5 stderr 为既有启动 warning/info（443 bytes），无
fault/panic/abort/timeout。成功 probe 的 QEMU/Gem5 guest exit rc 均为 `42`；
表中的 marker 是由固定参数 `write` 报告的被调用入口返回分类，二者已区分。

#### 后续修复边界

下一步应先在不改变 syscall ABI 的前提下复核 musl build manifest、对象选择和
archive 生成输入，补齐 `fflush/fileno/__fdopen` 的可链接性后再做 flush 复验；
同时单独核对 writev syscall responder 对 syscall 号 `66` 的返回语义。不要把
固定 `write` 成功、stdout fd 已初始化或 hidden 入口可 link 推断为 stdio 高层
输出已经修复。本任务不实施上述修复。

完整证据、源码行号、nm/objdump 输出摘要和 probe SHA-256 见：
`docs/reviews/ML-016d-musl-stdio-dependency-recon-20260721.md`。

worker 原始结果另存于 `docs/reviews/ML-016d-musl-stdio-dependency-recon-worker-report-20260721.md`；
独立 review 结论为 **Audit-accepted-with-findings**。当前只保留两个待定位边界：
archive/build object 选择，以及 QEMU/Gem5 对 `SYS_writev=66` 的返回语义。
