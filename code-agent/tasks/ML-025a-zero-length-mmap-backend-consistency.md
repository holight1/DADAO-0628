# ML-025a：QEMU/gem5 零长度 mmap 一致性

日期：2026-07-23

## 状态

已完成，独立判决 **Accepted-with-findings**；当前双后端语义一致，新增回归
测试固化，无需 component 代码修复。

## 背景

ML-024a 诊断发现：`libc.page_size==0` 时，QEMU 的 cfx_smon mmap responder
对 `length==0` 返回 `-EINVAL`，而 gem5 返回一个非空但未映射的地址，导致同一
错误在两后端分别表现为 malloc 返回 NULL 与后续 MALIGN。AT_PAGESZ 根因修复后
正常 malloc 不再触发该差异，但 responder 的错误输入语义仍不一致。

## Ownership 与约束

- 允许修改 QEMU/gem5 各自 mmap responder 的最小实现、对应 component patch
  与 series、新增主仓测试、本任务完成区及 worker report。
- 不修改 LLVM、musl、ISA/ABI contract、kernel、wiki。
- 两个 component 都必须在当前 HEAD 上新增普通 commit；禁止 rebase、reset、
  amend 或历史重写。
- 先用同一个 raw syscall 最小探针独立复现，不得用 malloc 间接现象代替。
- 优先保持 Linux/asm-generic `mmap(length=0) -> -EINVAL` 语义；若现有项目契约
  有相反规定，必须停止实现并报告冲突。

## 目标

1. 新增判别性 E2E：直接执行 syscall 222，length=0，检查返回值为 `-EINVAL`；
   同时保留正常非零 mmap 成功的控制项。
2. 修正 gem5，使 QEMU/gem5 返回值与副作用一致；确认零长度请求不推进 arena
   cursor、不建立 VMA。
3. 避免只比较退出码；测试需检查 raw return 和后续正常 mmap 地址。
4. 重建 QEMU/gem5，运行新增测试、全量 E2E、differential、manifest/issues。
5. 导出两侧普通 patch，并从各自裸 pin 全量重放 series。

## 验收

双后端同一探针均通过；正常 mmap/malloc E2E 不回归；独立 reviewer 检查两侧
错误码、arena/VMA 副作用与 patch replay。

## Worker 完成区

### 结论

任务背景中的“当前 gem5 对 `length==0` 返回非空未映射地址”在当前 pin、当前
源码和当前重建产物上均**无法复现**。当前实现已经一致：

- QEMU HEAD `cf5c06bbcf7ac0e176b7f5e52fca48868c3d03a9` 在
  `target/dadao/cpu.c` 的 SYS_mmap 分支中，先检查 `length == 0`，返回 raw
  `-EINVAL`，再计算 aligned length 和读取/推进 static arena cursor。
- gem5 HEAD `ca12f8261eb6c096d48b50ff206293f32a7d1daa` 在
  `src/arch/dadao/decoder.cc` 中执行相同的早退。`git blame` 证明该检查并非
  本任务期间的并发改动，而是早已包含在提交
  `6dd0d7c9f162fa4e414e8824f6129ff5c78a35ed`（ML-014c 对应的 VMA backing
  提交）中；早退发生在 `mapRegion()` 和 `mmapArenaCursor()` 之前。

因此本 worker 没有创建空提交、注释提交或重复修复，也没有导出虚假的下一号
QEMU/gem5 patch。两个 component 源仓 HEAD 保持不变且工作树干净。任务中
“两个 component 都必须新增普通 commit/导出两侧 patch”的要求依赖错误前提，
需要独立 reviewer/架构师据实裁定，不能靠无语义改动满足。

### 契约与 Linux/asm-generic 核对

- 项目 `docs/adr/0014-libc-syscall-charter.md` D2 规定 syscall 编号采用 Linux
  asm-generic，并要求 syscall 层双后端一致；未发现任何允许零长度 mmap 成功
  或产生副作用的相反契约。
- 本机 Linux UAPI `include/uapi/asm-generic/unistd.h` 对应安装头
  `/usr/include/asm-generic/unistd.h` 定义 `__NR3264_mmap 222`，并令
  `__NR_mmap` 指向该编号。
- Linux 主线 `mm/mmap.c` 的 `do_mmap()` 在任何 page align、查找 unmapped
  area 或创建 VMA 之前执行 `if (!len) return -EINVAL;`。Linux man-pages
  `mmap(2)` 同样记录 Linux 2.6.12 起 `length==0` 返回 `EINVAL`。

结论是 `SYS_mmap=222, length=0 -> raw -22` 且无 cursor/VMA 副作用符合项目
软件 ABI 方向和 Linux 语义，不存在契约冲突。

### 新增判别性 E2E

新增 `tests/lit/E2E/mmap_zero_length_consistency.test`，完全绕过 libc/malloc，
直接发出 raw syscall 222。它不只比较进程退出码，而是在 guest 内逐项验证：

1. 第一次零长度调用 raw return 必须精确等于 `-22`；
2. 随后的 length=1 正控制必须精确返回 arena base `0x100000000`；
3. 对该映射执行 64-bit store/load 回读，证明是真实 backing；
4. 在两个正常 mmap 之间再次调用零长度 mmap，仍须返回 `-22`；
5. 第二个正常 mmap 必须精确返回 `0x100001000`。

两次成功地址的精确值证明两个失败请求均未推进 cursor；首个正常 mapping 能在
arena base 建立、第二个能紧接上一页建立，也会捕获零长度请求建立冲突 VMA 的
错误实现。每个失败点使用独立退出码 1～5。

手工编译同一探针并分别运行：

```text
QEMU: mmap-zero-ok, rc=42
gem5: mmap-zero-ok, SIM_END: trap-exit code=42, rc=42
```

### 构建与门禁

- `ninja -C .work/source/qemu/build qemu-system-dadao`：exit 0。
- `scons build/DADAO/gem5.opt -j6`：exit 0，target up to date。
- `llvm-lit -sv tests/lit/E2E/mmap_zero_length_consistency.test`：1/1 PASS。
- `llvm-lit -sv tests/lit/E2E/`：66/66 PASS（原 65 + 本任务新增 1）。
- `python3 tools/run_differential.py`：
  `AGREE(3-way)=200`、gem5-SKIP=2、`DIVERGE=0`；
  `AGREE(4-way)=200`、Sail-SKIP=2、`SAIL-DIVERGE=0`。
- `python3 scripts/manifest_check.py`：PASS。
- `python3 scripts/check_issues.py`：PASS（Open=23/Closed=34/Total=57）。

### Patch series 重放

- gem5：从 manifest pin
  `c8222cc67a399bfc01e8658dd14b30d5bfd634f9` 依次 `git am` 当前 15 条
  series，15/15 成功；重放后 tree 与 live HEAD `ca12f826...` 一致。
- QEMU：从 manifest pin
  `385b0a7d9785c8f3ac7b116d7f31d61502b55183` 重放，0001～0007（series
  中前 7 个文件）成功，`0008-dadao-fix-helper-exit.patch` 失败，因为它要
  修改的 `helper_exit()` 尚不存在。
- 根因已精确隔离：QEMU live 历史在 control-flow commit 与 branch-call
  commit 之间包含
  `e7639ea9a84ecfd42b28d387fb5ca5383999605e`
 （`DL-026a divs/divu TCG label fix + machine/CPU hardening`），该提交创建
  `helper_exit()`，但 component series 漏掉了对应 patch。
- 负向诊断：在另一临时裸 pin clone 中，在现有 0006 后注入由上述真实 commit
  直接 `git format-patch` 生成的 patch，再继续现有 series，全部后续 patch
  均成功，最终 tree 与 QEMU live HEAD `cf5c06bb...` 一致。这证明阻塞是单一
  漏 patch，而非 ML-025a 改动或其它隐藏冲突。

本任务未获授权扩展为 QEMU 历史 patch 链修复，且不能把该历史提交冒充为本任务
新增的 mmap 修复，故只记录 finding，建议另拆 reproducibility 任务处理。

### Ownership 与工作树

- 未修改 LLVM、musl、spec/contract、kernel、wiki、issues。
- QEMU 与 gem5 源仓均未修改、未新增 commit、未重写历史，最终工作树干净。
- 主仓仅新增本测试、更新本任务完成区并新增 worker report；未自行 commit。
- 验证期间主仓出现并发的
  `components/llvm/patches/0005-dadao-asmparser.patch` 修改，属于
  IN-006a worker，不是本任务产生；本 worker 未触碰。

详细命令、输出和临时重放目录见
`docs/reviews/ML-025a-worker-report-20260723.md`。

## 独立 review

- 报告：`docs/reviews/ML-025a-independent-review-20260723.md`
- 判决：Accepted-with-findings，无 blocking finding。
- 独立确认 QEMU/gem5 均在 cursor/VMA 副作用前返回 `-EINVAL`，新增探针、
  E2E 66/66、differential、manifest/issues 与 gem5 15/15 replay 均通过。
- non-blocking finding：QEMU series 漏失真实历史提交 `e7639ea...`；已下发
  IN-007a 修复，不把该历史缺口冒充为 ML-025a 的 mmap 代码改动。
