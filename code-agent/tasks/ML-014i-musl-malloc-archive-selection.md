# ML-014i：修复 musl mallocng 的 build/archive selection

**执行环境**：本地 subagent worker；承接 ML-014h 诊断

**状态**：实现候选已验证但 Blocked（2026-07-18）

## 背景

ML-014h 已证明真实 C `mmap(NULL, 4096/135168, ...)` 在 QEMU/gem5 均能
通过 pointer return；当前 `malloc(131052)` 却为 QEMU=11、gem5=13，首尾写读
为 QEMU=11、gem5=134。独立复核确认当前 `libc.a` 的归档/链接选择实际落到
`lite_malloc.o`，而配置声明 `MALLOC_DIR = mallocng`。本任务只修正这一层，先
打通真实 musl mallocng 的基本分配与访问链路。

## Ownership

- 允许修改：临时 `.work/ML-014i-musl-malloc-archive/` 探针和报告；必要的
  `components/musl/patches/0007-*`（或下一个连续编号）及 `series`；本任务 MD；
  必要时恢复一个最小的 `tests/lit/E2E` 回归输入。
- 可使用当前 `.work/source/musl` 的既有候选 commit `8ecf6f6e` 进行验证，但
  不得 reset/rebase 或重写该工作树历史；若需要提交新的 musl 普通 commit，必须
  从当前 HEAD 导出可顺序应用 patch。
- 不允许修改 LLVM、QEMU、gem5、contracts、manifests、`docs/issues.yaml`、
  `ML-014a` 原文；不得修改 `-O0`/`optnone` workaround，也不得借此任务处理
  `-O2`/寄存器分配器问题或 `puts` 归档覆盖。
- 不得把测试改成 raw syscall；必须调用当前 musl 的真实 `malloc`，并对返回块
  做首尾写入/读回。不得使用 `|| true` 或忽略 backend 退出码。

## 执行阶梯

1. 复核 `MALLOC_DIR`、`SRC_DIRS`、归档 member order、`llvm-nm`/链接 map，
   明确为何 `lite_malloc.o` 抢先满足 malloc/内部 malloc 符号。
2. 选择最小 musl build/archive 修复，使配置为 mallocng 时不会把 lite allocator
   作为实际 public/internal malloc provider；保持替换 malloc 的既有语义，不删除
   源码功能。先用临时 C probe 验证 `malloc(131052)`、首尾写读、真实 `free`。
3. 生成 patch 并在干净 musl pin checkout 顺序应用；用该 patch 重建 libc，
   QEMU/gem5 均要求 pointer stage=42、write/read/free stage=42。
4. 回归 ML-014e `mmap_backing_probe`；若基本链路通过，再运行既有单测/全量门禁，
   但不要把未重新运行的 ML-014f/ML-014a 或 `puts` E2E 标成完成。

## 验收

- 报告包含 archive member order、符号解析前后对比和最小修复理由；
- patch series 可在干净 musl checkout 应用且 checkout 干净；
- 真实 musl `malloc(131052)` 首尾写读并 `free`：QEMU=42、gem5=42；
- ML-014e probe 仍为双 backend=42；manifest/issues 检查通过；
- 不修改 LLVM/QEMU/gem5、`-O0`/`optnone` workaround、contracts、manifests、
  issues、ML-014a；
- 完成区有 subagent 自审，随后由独立 reviewer 复核；未达到双 backend=42 时
  必须保持 Blocked，不得宣称 ML-014f/ML-014a 完成。

## 完成区

**状态**：Blocked（2026-07-18；归档选择修复生效，但 mallocng 启动链仍失败）

**根因证据**：

- `.work/build/musl/config.mak` 声明 `MALLOC_DIR = mallocng`，但当前
  `Makefile` 的 `SRC_DIRS = src/* src/malloc/$(MALLOC_DIR) ...` 使通配的
  `src/*` 同时纳入 `src/malloc/lite_malloc.c` 和选中的 mallocng 源码。
- 当前 `libc.a` member order（保留于
  `.work/ML-014i-musl-malloc-archive/before.map` 同步的原始检查）为：第
  660 个 `lite_malloc.o`，第 664 个 mallocng `malloc.o`。
- `llvm-nm`：`lite_malloc.o` 导出 weak `malloc` 与 weak
  `__libc_malloc_impl`，而 mallocng `malloc.o` 导出 strong
  `__libc_malloc_impl`。
- 原始 `ld.lld --why-extract` 显示 `malloc_pointer.o -> libc.a(lite_malloc.o)
  -> malloc`；link map 将 `malloc`、`default_malloc`、`__simple_malloc` 和
  `__libc_malloc_impl` 都解析到 `lite_malloc.o`，mallocng `malloc.o` 未被
  该 malloc-only link 提取。因此这是 musl build/archive selection 根因，
  不是 QEMU/gem5 pointer-return bridge 证据。
- 证据原文与命令产物保留在
  `.work/ML-014i-musl-malloc-archive/report.md`、`before.why`、
  `before.map`、`before.elf`。

**修改文件**：

- `.work/ML-014i-musl-malloc-archive/report.md` 及同目录诊断产物。
- `.work/source/musl` 普通候选 commit `4741d4d1`：在
  `src/malloc/mallocng/malloc.c` 增加强 public `malloc` wrapper，使静态链接
  解析 public `malloc` 时提取 mallocng archive member；尚未导出到主仓库
  `components/musl/patches/series`。
- `.work/ML-014i-musl-malloc-archive/after.map` 与 `after_rw.map` 保留修复后
  link map；可见 mallocng `malloc.o` 的 `__libc_malloc_impl` 与 `malloc`。

**验收结果**：

- 诊断证据：已完成，member order、`ld.lld --why-extract`、修复前后 link map
  均已保留。
- 修复后 archive selection：生效；mallocng `malloc.o` 被提取并导出 strong
  `malloc`/`__libc_malloc_impl`，lite 仅保留 `__libc_malloc`/fallback 相关符号。
- 修复后真实 musl ELF：QEMU=129、gem5=129（两者均为 `MALIGN`），失败发生在
  `main` 前启动/TLS 链路；pointer/write-read/free 尚未达到可验收阶段。
- 因此修复后真实 mallocng 基本链路仍未通过，不满足 QEMU=42、gem5=42，不能
  Accepted；ML-014e/ML-014f/ML-014a 未宣称完成。
- ML-014e、ML-014f、ML-014a、`puts` 及其它排除范围：未宣称完成。

**遗留问题**：

- `4741d4d1` 只证明归档选择层已修正，不能越过启动链 `MALIGN=129`；ML-014j
  单独定位该共同失败后，才能决定是否导出 0007 patch。
- 需要在干净 musl checkout 应用候选 patch、重建 libc，并用真实
  `malloc(131052)` 首尾写读及 `free` 验证 QEMU=42、gem5=42。

## 审阅记录（subagent）

> 本任务仅处理 mallocng 的 build/archive selection；`-O2` workaround、
> `puts` 覆盖和主 ML-014a 仍保持独立状态。

### Subagent 自审（2026-07-18）

- 已先记录 `MALLOC_DIR`、`SRC_DIRS`、archive member order、`llvm-nm` 符号
  以及 `ld.lld --why-extract`/link map 证据，随后按用户指示停止，没有把
  诊断阶段误写成修复完成。
- 未修改 `.work/source/musl`、未 reset/rebase 他人历史，未创建 patch 或
  `series` 变更；受限 ownership 外的 LLVM/QEMU/gem5、contracts、manifests、
  issues 与 ML-014a 均未触及。
- QEMU/gem5 当前真实 malloc 基线仍分别为 11/13（pointer）和 11/134
  （write/read）；没有伪造 exit=42，也没有忽略 backend 退出码。
- **自审判决：Blocked；诊断完成但未实现，不能 Accepted。**

### 实现候选自审（2026-07-18）

- 复核 `4741d4d1` 只新增 mallocng public wrapper，未修改 LLVM/QEMU/gem5、
  `-O0`/`optnone`、主 patch series 或用户文件；复核 after link map 确认
  mallocng member 已实际提取。
- 真实运行未通过：QEMU=129、gem5=129，故没有生成主仓库 0007/series，也没有
  把归档选择修复写成 ML-014f/ML-014a 完成。
- **自审判决：Blocked；归档选择修复有效，但基本运行链路仍阻塞。**
