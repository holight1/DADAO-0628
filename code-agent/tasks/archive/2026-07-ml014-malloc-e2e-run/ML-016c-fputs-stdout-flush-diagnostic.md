# ML-016c：fputs/stdout flush 链路诊断

**日期**：2026-07-21

**状态**：Audit-accepted-with-findings（ML-016 新 30-task run：3/30）

## 背景

ML-016b 确认 `fputs("fputs-ok", stdout)` 可以链接，QEMU/Gem5 均 rc=42，
但两端都没有观察到 marker；`puts`/整数 `printf` 当前不可链接。需要区分
“fputs 本身未执行/返回错误”“stdout 未初始化”“缓冲未 flush”“trap-exit
绕过 libc flush”等阶段。

## 目标与 ownership

worker 只在 `/tmp` 做临时 probe，不修改主线：

1. 构建并运行 `fputs` 无 flush、`fputs + fflush(stdout)`、必要时
   `fwrite/fflush` 或返回值通过固定 `write` 旁路报告的最小 probe。
2. 每个 probe 用同一 ELF 分别跑 QEMU/Gem5，记录 link rc、后端 rc、stdout、
   marker、flush/return status，区分 fputs 调用、flush、exit 阶段。
3. 明确下一步是测试入口修正、libc 构建缺口还是 runtime/exit 语义问题；不把
   临时 `write` 旁路结果当作 ML-014a 完成。

## 约束

- 只写本 task 完成区和
  `docs/reviews/ML-016c-fputs-stdout-flush-diagnostic-20260721.md`；临时产物放
  `/tmp`。
- 不修改 LLVM/QEMU/gem5/musl、contracts、vectors、issues、wiki 或 ML-014a。
- 不访问或引用 `~/toolchain`、`~/knowledge-graph`；不使用 `|| true`，不忽略
  任一后端退出码。

## 完成区

（由 worker 填写；完成后由不同 subagent 独立 review）

### 完成（2026-07-21）

**状态：Completed / Diagnosis-only；ML-014a 仍为 Not Accepted。**

本轮只在 `/tmp/ml-016c-fputs-stdout-flush-diagnostic-20260721/` 生成 C、object、ELF、flat BIN、构建日志和双后端原始 stdout/stderr；未修改 LLVM、QEMU、Gem5、musl、contracts、vectors、issues、wiki 或 ML-014a。构建输入为当前 `.work/build/llvm/bin/clang`、`ld.lld`、`llvm-objcopy`、`.work/build/musl/lib/crt1.o`、`.work/build/musl/lib/libc.a` 和 `tests/scripts/dadao.ld`。

#### 1. 构建结果

| probe | 内容 | compile rc | link rc | objcopy rc | 后端运行 |
|---|---|---:|---:|---:|---|
| `fputs_no_flush` | `fputs("FPUTS_NO_FLUSH\\n", stdout)` 后直接返回 | 0 | 0 | 0 | QEMU/Gem5 |
| `fputs_fflush` | `fputs` 后 `fflush(stdout)`，旁路报告两次返回值 | 0 | 1 | 未执行 | 无 ELF |
| `fwrite_fflush` | `fwrite` 后 `fflush(stdout)`，旁路报告两次返回值 | 0 | 1 | 未执行 | 无 ELF |
| `fputs_return_bypass_write` | `fputs` 返回值经固定参数 `write` 旁路报告 | 0 | 0 | 0 | QEMU/Gem5 |
| `fwrite_no_flush` | `fwrite("FWRITE_NO_FLUSH\\n", 1, 16, stdout)` 后直接返回 | 0 | 0 | 0 | QEMU/Gem5 |

两次失败 link 的原文分别为：

```text
ld.lld: error: undefined symbol: fflush
>>> referenced by fputs_fflush.c
>>>               /tmp/ml-016c-fputs-stdout-flush-diagnostic-20260721/build/fputs_fflush.o:(main)
```

```text
ld.lld: error: undefined symbol: fflush
>>> referenced by fwrite_fflush.c
>>>               /tmp/ml-016c-fputs-stdout-flush-diagnostic-20260721/build/fwrite_fflush.o:(main)
```

archive 的 `llvm-nm` 原始输出也显示 `fputs`、`fwrite`、`write` 有定义，而 `fflush` 只有 `ext.o: U fflush` 引用、没有定义；该审计命令 rc=0，原始文件保留在临时目录。

#### 2. 成功 ELF 的同产物双后端结果

QEMU 使用同一次 `llvm-objcopy -O binary` 生成的 flat BIN，Gem5 使用同一次链接生成的 ELF；每次均用 `timeout 600s`，均未超时。

| probe | ELF SHA-256 | QEMU rc/timeout/stdout marker/stderr | Gem5 rc/timeout/stdout marker/stderr |
|---|---|---|---|
| `fputs_no_flush` | `df78796735f69a61c1a9b3200edf10abd4e78f96a9cd37c1b980d04afa463b79` | `42` / `NO` / 无 `FPUTS_NO_FLUSH`，仅 monitor 两行 / 0 bytes | `42` / `NO` / 无 `FPUTS_NO_FLUSH`，有 `SIM_START`、`SIM_END: trap-exit code=42` / 443 bytes既有 warning/info |
| `fputs_return_bypass_write` | `b2efb647b0a35bcc9773a37a8c97401513828876066db432936e812dbe16db0c` | `42` / `NO` / `BYPASS_FPUTS_RC_ERR` / 0 bytes | `42` / `NO` / `BYPASS_FPUTS_RC_ERR`，有 `SIM_START`、`SIM_END: trap-exit code=42` / 443 bytes既有 warning/info |
| `fwrite_no_flush` | `bb2661d4c8c883100dccab4e377f426f77c8ec00f4219af9b7a01e46a0fa8910` | `42` / `NO` / 无 `FWRITE_NO_FLUSH`，仅 monitor 两行 / 0 bytes | `42` / `NO` / 无 `FWRITE_NO_FLUSH`，有 `SIM_START`、`SIM_END: trap-exit code=42` / 443 bytes既有 warning/info |

Gem5 stderr 仅为 dot-file、DRAM 容量、legacy stat 和 stack-page warning/info，没有 fault、panic、abort 或 timeout。QEMU stderr 均为空。

#### 3. 阶段判定与结论

- `fputs_no_flush`：两端进入 `main` 并正常 trap-exit，但没有观察到 stdio marker；不能证明 stdout flush 成功。
- `fputs_return_bypass_write`：两端都能执行固定 `write` 旁路并观察到 `BYPASS_FPUTS_RC_ERR`，因此当前 `fputs` 返回值为负；旁路 write 路径可用，但不能替代高层输出验收。
- `fwrite_no_flush`：两端正常退出但没有 stdio marker；与 `fputs` 一致，未证明缓冲内容落到 stdout。
- `fputs + fflush` 与 `fwrite + fflush`：当前 libc archive 缺少 `fflush` 定义，均止于 link，不能归类为 runtime/flush 失败。

当前最小诊断结论是：本构建的底层 `write` 可用，`fputs` 已执行到返回错误，stdout 高层链路没有可观察 marker；`fflush` 缺口在 link 阶段已锁定。下一步应补齐/确认 libc 的 `fflush` 可链接性及 stdout 初始化/文件描述符语义；本任务不实施修复，也不把旁路 write 结果当作 ML-014a 完成。

独立复核记录见 `docs/reviews/ML-016c-fputs-stdout-flush-diagnostic-20260721.md`。

worker 原始结果另存于 `docs/reviews/ML-016c-fputs-stdout-flush-worker-report-20260721.md`。
独立 review 结论为 **Audit-accepted-with-findings / Diagnosis-only**：
`fputs` 返回负值，`fflush` 缺失定义，fixed `write` 仅为诊断旁路；ML-014a
仍为 Not Accepted。
