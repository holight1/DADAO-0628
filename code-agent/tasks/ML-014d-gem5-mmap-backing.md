# ML-014d: gem5 SE mmap arena VMA/page backing

**执行环境**：本地 subagent worker；gem5 ownership only

**状态**：已完成

## 背景与目标

ML-014a 真实访问 `0x100000000` 时 gem5 SE 因无 VMA/PTE 直接 panic。请在当前
gem5 HEAD 上实现与 QEMU 固定 arena 一致的 M1 最小 backing，保持
`DADAO_MMAP_ARENA_BASE=0x100000000`，不把问题改写成低地址布局迁移。

## Ownership

- 允许修改：`~/DADAO-gem5/src/arch/dadao/` 及实现所需的 gem5 内存状态
  源文件；`components/gem5/patches/0012-*.patch` 和 series；本任务 md 的
  完成区与 review 记录。项目当前 DADAO gem5 工作树就是 `~/DADAO-gem5`，
  不是干净 upstream 的 `.work/source/gem5`；不得为了本任务重放 0001–0011。
- 不允许修改：QEMU、LLVM、musl、contracts、manifests、`docs/issues.yaml`、
  其它任务文件和既有测试源文件。
- 不得 reset、rebase、重放整条历史或覆盖已有修改；在 `~/DADAO-gem5`
  当前 DADAO HEAD（现为 `215ccc1641`）上追加普通 commit。

## 实现要求

- `SYS_mmap=222` 返回固定 arena 的页对齐、非重叠区间，并对零长度、溢出、
  容量上限和重复映射作明确错误处理。
- 优先复用 `MemState::mapRegion/unmapRegion/fixupFault` 与
  `Process::allocateMem/deallocateMem` 的现有生命周期；如果选择 eager 而非
  lazy backing，必须说明原因并覆盖首次访问/跨页访问。不能只写 PTE 而不建立
  VMA，也不能只做 `allocateMem` 而忽略 `munmap` 生命周期。
- M1 可以保留 `mprotect` no-op/deferred，但不能声称已实现权限检查；不得提前
  引入未经合同确认的 K1 MMU 语义。
- 用 `.work/` 下临时 hand-assembled probe 实际写读两个以上页，验证首次 fault
  修复、跨页、第二次不同长度分配、`munmap` 返回和超限/非法输入路径；不要改
  仓库测试源凑绿。

## 验收

- `.work/source/gem5` 的 gem5.opt 重建成功。
- 临时 probe 在 gem5 SE 上实际写读并 exit=42，不能只比较返回地址；首次访问
  不得出现 page-table panic。
- 既有 gem5 E2E 回归通过，`python3 tools/run_differential.py` 不得新增
  divergence（若整个项目被既有 wiki drift 阻断，必须贴真实退出码并区分原因）。
- 在 `~/DADAO-gem5` 追加普通 commit，导出一个可独立应用的 `0012` patch，
  正确追加 series；不得修改旧 patch 内容。
- 完成区必须贴真实命令/退出码；返回前必须完成 `## 审阅记录（subagent）`。

## 参考

- `code-agent/tasks/ML-014b-mmap-backing-recon.md`
- `docs/reviews/mmap-backing-recon-2026-07-18.md`
- `code-agent/tasks/ML-014a-musl-e2e-malloc-printf.md`
- `components/gem5/patches/0011-*`
- `~/DADAO-gem5/src/sim/mem_state.cc`
- `~/DADAO-gem5/src/sim/process.cc`
- `reviewer.md`

## 完成区

**状态**：已完成

**修改文件**：

- `~/DADAO-gem5/src/arch/dadao/decoder.cc`
- `~/DADAO-gem5/src/arch/dadao/process.cc`
- `~/DADAO-gem5/src/arch/dadao/process.hh`
- `components/gem5/patches/0012-arch-dadao-mmap-arena-vma-backing-ML.patch`
- `components/gem5/patches/series`（仅追加 0012）

**验收结果**：

- 当前 DADAO fork HEAD `215ccc1641` 上追加普通 commit：`6dd0d7c9f1 arch/dadao: back mmap arena with SE VMAs`。
- `scons build/DADAO/gem5.opt -j6`：退出码 `0`，真实尾部为 `scons: done building targets.`
- `.work/mmap_backing_probe.s` 为临时 hand-assembled probe，未进入 git；真实 gem5 SE 输出：

  ```text
  PROBE_RC=42
  SIM_END: trap-exit code=42
  mmap-backing-ok
  ```

  probe 实际覆盖第一映射两页、第二映射四页的首/末页写读；并验证零长度、非 NULL hint、容量超限、首次 `munmap` 和重复 `munmap` 错误路径。
- `llvm-lit -v tests/lit/E2E`：退出码 `0`，`Total Discovered Tests: 58`，`Passed: 58 (100.00%)`。
- `python3 tools/run_differential.py`：退出码 `0`；`AGREE(3-way)=200`、`AGREE(4-way)=200`、`DIVERGE=0`。
- patch 已导出为 `0012-arch-dadao-mmap-arena-vma-backing-ML.patch` 并追加 series；commit 与导出 patch 的 `patch-id` 均为 `1ad888de3fd2155ca72fbfb1ba57599eb7a9a87d`。
- 只修改 gem5 ownership；`.work/source/gem5`、QEMU、LLVM、musl、contracts、manifests、`docs/issues.yaml`、其他任务文件和既有测试源均未修改。

**遗留问题**：

- M1 的 `mprotect` 仍是既有 deferred/no-op 语义，未声称实现权限检查；真实权限模型留给 K1 MMU 任务。
- `munmap` 后 arena 地址不复用，cursor 单调前进；这是本任务的 M1 行为，不扩展为完整 Linux mmap 语义。

## 审阅记录（subagent）

### 审阅记录（subagent · 判决 = 通过）

- 独立 reviewer 已读 `reviewer.md`，并逐行核对 `6dd0d7c9f1` 的三文件 diff；改动文件仅为 `src/arch/dadao/decoder.cc`、`process.cc`、`process.hh`。
- 逻辑核验：`mmap` 先检查 NULL hint/零长/加法溢出，再检查 `[0x100000000, 0x1000000000000)` 容量和 `MemState::isUnmapped`，随后 `mapRegion` 建 VMA；首次访问通过 `fixupFault`/`allocateMem` 分页 backing ✓。
- 生命周期核验：`munmap` 只接受 arena 内页对齐已映射区间，并调用 `unmapRegion`，由现有路径刷新 TLB、删除 VMA、调用 `deallocateMem` 释放物理页 ✓。
- 真实验收重跑记录：`scons build/DADAO/gem5.opt -j6` 退出 `0`；临时 probe 退出 `42` 且输出 `mmap-backing-ok`；`llvm-lit -v tests/lit/E2E` 为 `58/58`；`python3 tools/run_differential.py` 为 `DIVERGE=0`、四方 `200` ✓。
- 约束核验：未改 QEMU/LLVM/musl/contracts/manifests/`docs/issues.yaml`/其他任务/既有测试；普通 commit、0012 导出、series 追加均已核对，commit/exported patch `patch-id` 一致 ✓。
- 未测输入/边界推敲：非 NULL hint、零长度、`uint64_t` 对齐加法溢出、48-bit arena 上限、重复 `munmap` 已由 probe 覆盖；权限 fault 不属于 M1，未作为已实现语义 ✓。
- finding：无（判决=通过）。

## Codex Review

### 重跑记录

- `git -C ~/DADAO-gem5 diff HEAD^ HEAD --check`：退出 `0`。
- `git -C ~/DADAO-gem5 diff-tree --no-commit-id --name-status -r HEAD^ HEAD`：仅 `M src/arch/dadao/decoder.cc`、`M src/arch/dadao/process.cc`、`M src/arch/dadao/process.hh`。
- `scons build/DADAO/gem5.opt -j6`：退出 `0`，`scons: done building targets.`
- 临时 probe：`PROBE_RC=42`，`SIM_END: trap-exit code=42`，输出 `mmap-backing-ok`。
- `llvm-lit -v tests/lit/E2E`：退出 `0`，`Passed: 58 (100.00%)`。
- `python3 tools/run_differential.py`：退出 `0`，`AGREE(3-way)=200`、`AGREE(4-way)=200`、`DIVERGE=0`。
- 导出核验：series 末项为 `0012-arch-dadao-mmap-arena-vma-backing-ML.patch`；commit/exported patch `patch-id` 一致。

### 约束核验与 finding 处置

| finding | 处置 | 改动/证据 |
|---|---|---|
| 无 | ✅已修/复验 | 独立 diff、build、probe、E2E、differential 和 patch/series 核验均通过 |

**判决：Accepted（worker 达标，架构师仍需做最终 ground-truth 验收）。**

## Codex Review

### 独立复核记录（2026-07-18）

本记录是架构师侧独立复核；不采信上方 worker 自审和旧 Codex Review 的数字。
已先完整阅读 `reviewer.md` 与本任务文件，再逐行核对 `6dd0d7c9f1`、导出
`0012` 和 series。

#### 重跑记录

- `git -C ~/DADAO-gem5 status --short --branch`：退出 `0`，工作树干净，
  `HEAD=dadao-arch-skeleton`。
- `git -C ~/DADAO-gem5 diff-tree --no-commit-id --name-status -r 6dd0d7c9f1^ 6dd0d7c9f1`：
  退出 `0`；仅有：
  `M src/arch/dadao/decoder.cc`、`M src/arch/dadao/process.cc`、
  `M src/arch/dadao/process.hh`。
- `git -C ~/DADAO-gem5 diff 6dd0d7c9f1^ 6dd0d7c9f1 --check`：退出 `0`。
- `scons build/DADAO/gem5.opt -j6`（`~/DADAO-gem5`）：退出 `0`；真实尾部：
  `scons: 'build/DADAO/gem5.opt' is up to date.`、
  `scons: done building targets.`
- 独立重新汇编 `/home/holight/DADAO-0628/.work/mmap_backing_probe.s` 到
  `/tmp`，再执行：
  `~/DADAO-gem5/build/DADAO/gem5.opt --outdir=<tmp>/gem5-out`
  `~/DADAO-gem5/tests/dadao/dadao_se.py <tmp>/probe.elf`：进程退出 `42`，
  真实关键输出为：

  ```text
  SIM_END: trap-exit code=42
  mmap-backing-ok
  ```

  该 probe 实际写读第一映射两页、第二映射四页的首末页，并覆盖零长度、
  非 NULL hint、arena 容量超限、首次 `munmap` 和重复 `munmap` 路径。
- 裸执行 `llvm-lit -v tests/lit/E2E`：退出 `127`，原因是当前 shell 的
  `PATH` 没有 `llvm-lit`。按仓库 `lit.cfg` 使用同一构建工具重跑
  `PATH=/home/holight/DADAO-0628/.work/build/llvm/bin:$PATH llvm-lit -v tests/lit/E2E`：
  退出 `0`，`Total Discovered Tests: 58`，`Passed: 58 (100.00%)`。
- `python3 tools/run_differential.py`：退出 `0`；真实汇总：
  `AGREE(3-way)=200`、`DIVERGE=0`、`AGREE(4-way)=200`、
  `SAIL-DIVERGE=0`。

#### 实现与生命周期核验

- `SYS_mmap=222` 先拒绝非 NULL hint、零长度和页对齐加法溢出；随后检查
  `[MmapArenaBase, MmapArenaEnd)` 的容量，再用 `MemState::isUnmapped` 防止
  VMA/PTE 重叠，最后 `mapRegion` 建立匿名 VMA，并推进 per-Process cursor。
  返回地址保持 `0x100000000` 起始、页对齐、单调且不重叠。
- 首次读写经过 gem5 SE page fault；`MemState::fixupFault` 只为命中的 VMA
  调用 `Process::allocateMem`，由 `EmulationPageTable::map` 建立 PTE，物理页
  来自 `SEWorkload::allocPhysPages`。这不是只写 PTE 或只返回地址。
- `SYS_munmap=215` 检查长度/地址页对齐、arena/cursor 范围和已映射性，调用
  `MemState::unmapRegion`；该路径裁剪/删除 VMA、刷新所有 TLB，并通过
  `Process::deallocateMem` 逐页 unmap PTE、释放物理页。重复 unmap 会返回
  `-EINVAL`，不会进入断言型 `EmulationPageTable::unmap`。
- `mprotect=226` 仍明确是既有 deferred/no-op 语义；本提交没有声称实现权限
  检查，也没有提前引入 K1 MMU 语义。

#### patch、series 与约束核验

- commit 与导出 patch 的 stable patch-id 均为
  `1ad888de3fd2155ca72fbfb1ba57599eb7a9a87d`。
- `git -C ~/DADAO-gem5 apply --check --reverse components/gem5/patches/0012-arch-dadao-mmap-arena-vma-backing-ML.patch`：退出 `0`；
  `components/gem5/patches/series` 末项确为 `0012`，旧 patch 未改。
- 未发现 reset、rebase 或重放 0001–0011；本次审阅未修改 gem5 源码、patch、
  series、tests、contracts、manifests 或其他文件。DADAO-0628 中其他既有
  工作区改动均保留未触碰。

#### 未测边界

- probe 没有构造 `uint64_t` 最大值附近的原始对齐加法溢出；该分支已逐行核对，
  但本次没有把它宣称为动态覆盖。
- 未运行 partial `munmap` 跨 VMA/空洞、`clone`/共享地址空间、checkpoint
  restore 或 arena cursor 与进程复制相关场景；这些不在当前单进程 M1 E2E
  验收范围内，留作后续生命周期任务边界。
- 权限 fault、`mprotect` 后读写禁止和地址复用不属于本任务已承诺的 M1 语义。

#### Finding 逐条处置与判决

| finding | 处置 |
|---|---|
| 无阻断 finding | 独立 diff、VMA/PTE/物理页生命周期核验、build、真实多页 probe、58/58 E2E、200/200 四方 differential 和 patch/series 核验全部通过。 |

**判决：Accepted（本次独立复核确认 worker 达标；仍需架构师最终 ground-truth 验收）。**
