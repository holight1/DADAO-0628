# ML-016a：mallocng 真实运行时失败复现与阶段分类

**日期**：2026-07-21

**状态**：Diagnosis-accepted-with-findings（ML-016 新 30-task run：1/30）

## 背景

基础 mmap arena/backing 和独立 backing probe 已经解决，但 ML-014a 要求的
musl mallocng 大块分配双后端闭环仍未完成。历史记录显示不同阶段出现过
QEMU `130/挂起`、Gem5 `0`，以及后续访问 `0x90001000` 时 QEMU `13/14`、
Gem5 `134`。本任务先建立当前可复核的失败分类，避免把不同阶段混成一个问题。

## 目标与 ownership

worker 只负责诊断、临时 probe 和本 task/report，不修改主线实现：

1. 阅读 ML-014a/ML-014f/ML-014m 历史证据，确认当前可复用的阈值和失败语义。
2. 在 `/tmp` 或 worker 临时目录重建最小 musl mallocng probe；禁止把临时
   测试、候选 musl patch、`0007` patch 或 series 改动带回主仓库。
3. 对同一 ELF 分别运行 QEMU 和 Gem5，记录原始 rc、stdout/stderr、halt marker、
   失败地址/阶段；至少区分启动、mmap 返回、首写、读回、free、输出、exit。
4. 给出当前最小可复现命令和下一步最小诊断切片；若无法复现，明确环境/证据
   缺口，不凭历史数字宣称已解决。

## 约束

- 不修改 LLVM/QEMU/gem5/musl 源码、contracts、vectors、`docs/issues.yaml`、wiki。
- 不修改用户原有 `code-agent/tasks/ML-014a-musl-e2e-malloc-printf.md`。
- 不访问或引用 `~/toolchain`、`~/knowledge-graph`。
- 不用 `|| true`，不忽略任一后端退出码，不把单 backend 通过当作验收。

## 完成区

（由 worker 填写；完成后由不同 subagent 独立 review）

### Finding：当前锁定产物未复现历史 mallocng 运行失败；发现第二次 mmap 返回地址跨后端分歧，`puts` 版本无法链接

本任务只新增 `/tmp/ml-016a-mallocng-runtime-failure-repro/` 临时 probe/ELF/日志，未修改主仓库、`.work` source、ML-014a 或任何组件。未访问、未引用 `~/toolchain`、`~/knowledge-graph`。

#### 1. 构建尝试与真实退出码

- 单块阶段 probe：使用当前 `.work/build/llvm/bin/clang`、`ld.lld`、musl `crt1.o`/`libc.a`、`tests/scripts/dadao.ld`；compile/link/objcopy 均 `0`。
- exact 双块 source 的阶段化版本：`malloc(131052)` + `malloc(262144)`、page sentinel、读回、逆序 `free`，固定参数 `write` marker；最终 compile/link/objcopy 均 `0`。
- 尝试加入 `puts("MALLOCNG_OK")` 的同一双块版本：compile 成功，`ld.lld` **rc=1**，真实诊断为 `undefined symbol: puts`（被 `staged_dual_puts.o:(main)` 引用）。该版本没有 ELF，未运行后端；不能把高层 `puts` 输出问题伪装成 runtime 结果。
- 为取得实际返回地址，最终运行 ELF 为 `/tmp/ml-016a-mallocng-runtime-failure-repro/staged_dual_puts.elf`，对应 QEMU flat BIN 为同一次链接生成的 `staged_dual_puts.bin`。最终产物 SHA-256：ELF `28484ac6ec0190a647181888a228d951c1543049be473b7112d54f19c5ee80e8`，BIN `c45429b20026f241de069949717e0ccb74f5c25cebca0f1fddf433ae4da7f578`。

#### 2. 同一 ELF 的双后端真实结果

最终命令均为 `timeout 60s`；QEMU 使用该 ELF 对应的 flat BIN，Gem5 使用同一次链接的 ELF：

```text
QEMU: timeout 60s .work/source/qemu/build/qemu-system-dadao -M dadao-m1 -nographic -bios tests/scripts/trampoline.bin -kernel /tmp/ml-016a-mallocng-runtime-failure-repro/staged_dual_puts.bin
qemu_rc=42

Gem5: timeout 60s /home/holight/DADAO-gem5/build/DADAO/gem5.opt --outdir=/tmp/ml-016a-mallocng-runtime-failure-repro/final.m5out --debug-flags=Exec --debug-file=gem5.exec.trace /home/holight/DADAO-gem5/tests/dadao/dadao_se.py /tmp/ml-016a-mallocng-runtime-failure-repro/staged_dual_puts.elf
gem5_rc=42
```

QEMU raw stdout 为：

```text
QEMU 10.0.0 monitor - type 'help' for more information
(qemu) MAIN
A_RETURN p=0x0000000100000010
B_RETURN p=0x0000000100021030
RANGE_OK
FIRST_WRITE
READBACK
FREE_B
FREE_A
OUTPUT_OK
```

QEMU raw stderr 为空（0 bytes）。Gem5 guest stdout 的阶段部分为：

```text
SIM_START
SIM_END: trap-exit code=42
MAIN
A_RETURN p=0x0000000100000010
B_RETURN p=0x0000000100020030
RANGE_OK
FIRST_WRITE
READBACK
FREE_B
FREE_A
OUTPUT_OK
```

Gem5 raw stderr 只有既有启动 warning/info：无 dot file、DRAM capacity mismatch、legacy stat warning、stack 增长信息（443 bytes）；没有 page-table fault、panic、fatal、abort 或 timeout。完整 raw 文件、`gem5.exec.trace`、stdout/stderr 均保留在上述 `/tmp` 目录。

#### 3. 阶段与地址判定

| 阶段 | QEMU | Gem5 | 判定 |
|---|---|---|---|
| startup → `main` | `MAIN` | `MAIN` | 两端进入 `main`；ELF `main=0x80000110` |
| first mmap return | `A_RETURN p=0x100000010` | 同值 | 第一块返回地址一致；`131052 >= MMAP_THRESHOLD=131052` |
| second mmap return | `B_RETURN p=0x1000021030` | `B_RETURN p=0x1000200030` | 返回地址跨端不同；均通过非空、对齐、区间不重叠检查 |
| first write | `FIRST_WRITE` | `FIRST_WRITE` | 两块首/中/尾及 page-stride 写入完成 |
| readback | `READBACK` | `READBACK` | 两块 sentinel/page-stride 读回完成 |
| free | `FREE_B`, `FREE_A` | `FREE_B`, `FREE_A` | 逆序 free 和 marker 完成 |
| output | `OUTPUT_OK` | `OUTPUT_OK` | 固定参数 `write` 输出完成；不是 `puts` 结果 |
| exit | rc `42` | rc `42`，`SIM_END: trap-exit code=42` | 阶段化 probe 成功退出 |

第二块相对第一块的地址间隔为 QEMU `0x21020`、Gem5 `0x200020`，差异为 `0x1df000`。这是真实当前 ELF 的跨后端 allocator/mmap 返回布局差异；本次证据没有继续追到两端 `SYS_mmap` 参数/arena cursor 的寄存器级对应关系，不能据此唯一判定是 responder backing、对齐/游标策略还是 mallocng 元数据布局。

#### 4. 结论、证据缺口与下一步

- 当前锁定构建下，最小单块 probe 和阶段化双块 probe 均已越过 startup、两次 mmap 返回、首写、读回、逆序 free、固定 write 输出和 guest exit；本轮没有复现 ML-014a/ML-014f 历史的 QEMU `130` / Gem5 `0` 或 Gem5 `134`。
- 不能据此标记 ML-014a 完成：最终 probe 没有覆盖 exact `puts`/`fputs`，因为当前 libc archive 对 `puts` 未定义；也没有生成原 ML-014a 的主仓库测试文件。
- 当前最小可复现诊断边界是“同一 ELF 双块 mallocng 运行成功但第二块 payload 地址跨后端不同”；下一步应只增加 mmap syscall 参数/返回值和 arena cursor 的双端 trace，并单独确认可用的 musl 输出成员（`puts`/`fputs` 或已有固定 `write` 替代），不修改实现、不把地址偶然一致性当作 allocator 总体合同。

**自审判定：Completed / Diagnosis-only；ML-014a 仍 Not Accepted，未提出修复。**

### 独立 review

`docs/reviews/ML-016a-independent-review-20260721.md`，结论
**Diagnosis-accepted-with-findings**；reviewer 独立核对同一 ELF 的 QEMU/Gem5
`rc=42`、完整阶段 marker、第二次返回地址差异以及 `puts` 链接 `rc=1`，确认
本任务没有把固定 `write` probe 当作 ML-014a 验收。
