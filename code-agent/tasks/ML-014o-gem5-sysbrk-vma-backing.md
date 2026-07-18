# ML-014o：修复 gem5 `SYS_brk` 的 VMA/PTE/backing 生命周期

**执行环境**：本地 subagent worker；承接 ML-014n

**状态**：Implemented；等待独立 reviewer（2026-07-18）

## 目标

在不改变 DADAO mmap arena ABI 的前提下，修复
`/home/holight/DADAO-gem5` 中 `SYS_brk=214` 的最小实现，使 brk 返回的
heap 区间通过现有 MemState/VMA/fault-in 路径获得页面 backing。当前已确认
mallocng 在 gem5 首次形成并访问 `0x90001000` 时 page-table fault，原因是
现有 trap responder 只推进静态 brk 记账，没有调用 `updateBrkRegion` 或等价的
VMA 映射路径。

本任务只处理 gem5 brk 基本内存链路；不处理 `-O X`、puts、free、varargs、
mallocng 算法或 ML-014a 整体验收。

## Ownership

- worker 负责：`/home/holight/DADAO-gem5` 中 DADAO `SYS_brk` responder 及其
  必要的最小 MemState/Process 接口调用；构建、运行回归、临时报告和本任务
  完成记录。
- 允许修改 gem5 源码和本任务 `.work/ML-014o-gem5-sysbrk-vma-backing/`
  下的验证产物；如需在 gem5 仓库形成 source commit，可以直接提交，但不要
  修改 DADAO-0628 根目录的 patch series 或宣称 root 集成完成。
- 不允许修改 LLVM/QEMU/musl 源码、`components/*/patches`、
  `docs/issues.yaml`、contracts、manifests 或用户原始
  `code-agent/tasks/ML-014a-musl-e2e-malloc-printf.md`。
- 不得把 `~/toolchain` 或 `~/knowledge-graph` 传给 subagent；架构师可自行
  参考，worker 不得依赖它们。
- 本任务不扩展 mmap/munmap/mprotect 的 ABI 或 arena 边界；已有 mmap 回归必须
  保持通过。

## 执行阶梯

1. 检查当前 `TrapInst::execute()` 的 `case 214`、`MemState::updateBrkRegion`
   和 `fixupFault` 语义，明确 brk 初始值、页对齐、增长/查询/收缩和冲突时的
   返回约定；选择最小且复用现有框架的实现。
2. 实现 `SYS_brk` backing：`brk(0)` 应查询当前 break；有效增长应建立
   页粒度 VMA，使首次访问通过 `fixupFault` 分配物理页；不能因一次 syscall
   仅改变静态变量而留下无 VMA 的地址。对已有 heap/ELF 边界和映射冲突保持
   安全处理，不能覆盖现有映射。
3. 构建 gem5 DADAO 目标，并运行至少以下回归：
   - `return42` 和现有 `mmap_real` 保持 42；
   - `mallocng_real`、`malloc_pointer_after`、`malloc_rw_after` 在 gem5
     侧不再因 `0x90001000` 的 brk page-table fault 提前退出；
   - QEMU 侧既有结果不被改动（如需重新运行只记录，不修改 QEMU）。
4. 若 allocator 继续暴露独立的后续错误，必须记录真实退出码、fault VA/PC
   或 probe 判定，不能把“越过 brk fault”写成 mallocng/ML-014f/ML-014a
   完成。
5. 完成任务记录并做自审：列出实际修改文件、source commit、构建和回归命令、
   剩余 blocker 及未触碰范围；等待独立 reviewer 复核。

## 验收

- `SYS_brk=214` 使用现有 MemState/VMA/fault-in 机制，且 brk 查询/增长语义
  有源码或运行证据；没有 mmap ABI 回归。
- gem5 构建通过；return42/mmap 与 mallocng 三个 probe 的结果可复现并明确
  区分 brk blocker 与后续 allocator blocker。
- 修改集中在 gem5 brk 基本链路，没有越权触碰 ML-014a、docs/issues、patch
  series、LLVM/QEMU/musl 或 `-O X`/puts/free/varargs。
- 有 subagent 自审，随后由未参与实现的独立 reviewer 对代码、证据和范围做
  复核。

## 完成区

**Finding：Confirmed（限定为 gem5 `SYS_brk` backing/VMA 修复；mallocng 后续 probe 仍未完成）**

### 实际修改与语义

- 只修改了 `/home/holight/DADAO-gem5`：
  - `src/arch/dadao/decoder.cc`
  - `src/arch/dadao/process.cc`
  - `src/arch/dadao/process.hh`
- 删除 DADAO `case 214` 中与进程无关的静态 `brk` 记账，改为读取当前进程
  `MemState::getBrkPoint()`；非零有效请求调用已有
  `MemState::updateBrkRegion(old, new)`，再返回 MemState 的实际 break。
- 将 DADAO 初始 break 固定为既有 ABI 的 `0x90000000`（`Process::BrkBase`），
  因而 `brk(0)` 查询仍返回 `0x90000000`；增长由已有 MemState 负责页对齐、
  VMA 建立、冲突拒绝和收缩 unmap。
- 拒绝低于 `BrkBase` 或达到 `MmapArenaBase=0x100000000` 的请求，并返回原
  break；没有改 `mmap/munmap/mprotect` responder。
- source commit：`e6a6b9cdc9 arch/dadao: back SYS_brk with MemState VMAs`。
  gem5 工作树提交后保持 clean。

### 构建与回归

- 构建命令：

  ```text
  cd /home/holight/DADAO-gem5
  scons build/DADAO/gem5.opt -j6
  ```

  结果：exit 0；增量重新链接通过。仅有既有 decoder warning 以及主机缺少
  `protoc`/`capstone` 的非阻塞配置 warning。

- 使用同一组 ML-014m 真实 ELF，在 gem5 DADAO SE 上逐个运行：

  | probe | gem5 exit | 结果 |
  |---|---:|---|
  | `return42` | 42 | PASS |
  | `mmap_real` | 42 | PASS，mmap ABI 未回归 |
  | `mallocng_real` | 42 | 已越过原 `0x90001000` brk page-table fault |
  | `malloc_pointer_after` | 13 | brk fault 消失；后续 pointer 判定仍失败 |
  | `malloc_rw_after` | 134 | brk fault 消失；后续在 `0xfffffffb` page-table fault |

  命令模板为：

  ```text
  /home/holight/DADAO-gem5/build/DADAO/gem5.opt \
    /home/holight/DADAO-gem5/tests/dadao/dadao_se.py \
    /home/holight/DADAO-0628/.work/ML-014m-dadao-rela-page-fix/out/<probe>.elf
  ```

- VMA/backing 证据位于
  `.work/ML-014o-gem5-sysbrk-vma-backing/runs/mallocng_real.debug.log`：

  ```text
  3979000: ... creating vma (dadao-mmap) [0x100000000 - 0x100020000]
  4437000: ... creating vma (heap) [0x90000000 - 0x90002000]
  4437000: ... Creating vma start 0x90000000 len 8192 end 0x90002000
  ```

  这证明 mallocng 的 brk 增长实际进入 MemState heap VMA，首次访问
  `0x90001000` 不再因无 VMA 而 abort。对应的 `malloc_rw_after` 诊断日志仍只
  报后续 `0xfffffffb` fault，未再出现 `0x90001000`。

- 既有 ML-014m QEMU 结果保持为 `return42=42`、`mmap_real=42`、
  `mallocng_real=42`、`malloc_pointer_after=13`、`malloc_rw_after=14`；本任务
  没有修改或重建 QEMU/musl/LLVM。

### 剩余 blocker 与范围自审

- `mallocng_real` 的 42 仅表示本 probe 返回成功；不把 mallocng allocator 或
  ML-014f/ML-014a 写成完成。
- `malloc_pointer_after=13` 是 brk blocker 之后的独立 pointer 语义问题；
  `malloc_rw_after=134` 的 fault VA 已变为 `0xfffffffb`，属于后续问题，本任务
  不处理。
- 未修改 LLVM、QEMU、musl、DADAO-0628 root patch series、docs/issues.yaml、
  contracts、manifests、ML-014a，也未处理 `-O X`、puts、free、varargs 或
  mallocng 算法；未引用 `~/toolchain` 或 `~/knowledge-graph`。

### Subagent 自审

- 逐项核对了 `brk(0)` 查询、有效增长、页对齐入口、低/高边界拒绝和 VMA
  冲突回退路径；实现复用既有 `updateBrkRegion`，没有复制第二套 backing。
- 构建、return42、mmap_real 以及三个 mallocng probe 均以真实退出码记录；
  对两个剩余失败保留真实 exit/fault，没有用“越过 brk fault”代替整体验收。
- 自审结论：**Confirmed（SYS_brk backing 修复）；等待独立 reviewer**。

### 有限时长复核（2026-07-18）

- 按 60 秒上限执行增量构建：

  ```text
  timeout 60s scons build/DADAO/gem5.opt -j6
  scons_exit=0
  ```

  实际约 5 秒完成；仅出现既有主机依赖 warning（`protoc`、`capstone`、
  `png.h`、HDF5 等），没有新的编译或链接错误。

- 按 30 秒/probe 上限重跑五个关键 gem5 probe，结果仍为：

  ```text
  return42             exit=42
  mmap_real            exit=42
  mallocng_real        exit=42
  malloc_pointer_after exit=13
  malloc_rw_after      exit=134  (Page table fault at 0xfffffffb)
  ```

  重跑日志位于 `.work/ML-014o-gem5-sysbrk-vma-backing/rerun-20260718/`。
  `mallocng_real`、`malloc_pointer_after` 和 `malloc_rw_after` 均未重新出现
  `0x90001000` fault。

- 本任务没有无限等待完整工程回归。以下项目**未在 ML-014o 本轮重跑**：
  clean-room gem5 全量重编、LLVM patch 从零 replay、完整 `llvm-lit` E2E、
  全量三方 differential、QEMU 重跑以及独立 reviewer 复核；这些均不属于本
  任务 gem5 ownership，ML-014m 的既有结果仍作为基线。上述未跑项目不影响本
  任务已完成的增量构建和五个关键 probe 记录。

## 审阅记录

（待独立 reviewer 复核；请重点检查初始 `BrkBase` 与 ELF heap 边界、冲突/收缩
语义，以及上述五个回归证据。）

### 独立 reviewer 复核（2026-07-18）

**Finding：Needs-fix（gem5 本地 `brk` backing 机制接受；当前 `BrkBase` 跨后端
ABI/ELF heap 边界不一致，故 ML-014o 整体暂不 Accepted）**

本轮只读检查了 ML-014n/ML-014o 记录、`e6a6b9cdc9` 及其父提交 diff、相关
`MemState`/`Process`/DADAO trap 语义和 `.work/ML-014o-gem5-sysbrk-vma-backing/`
日志；没有修改 `/home/holight/DADAO-gem5` 源码，也没有回滚任何改动。

#### 1. `SYS_brk=214` 的 VMA/fault-in 语义

- `e6a6b9cdc9` 的 `decoder.cc` 已删除进程无关的静态 `brk` 记账，读取当前
  `process->memState->getBrkPoint()`；查询 `arg0==0` 和相同 break 直接返回当前值，
  其余请求调用已有 `MemState::updateBrkRegion(current, arg0)`，再读取实际 break。
- 当前 `MemState::updateBrkRegion` 的源码语义与调用方相符：新旧 break 按页向上
  对齐；增长前用 `isUnmapped` 检查 VMA 与 page table 冲突，冲突时不建映射且保留
  原 break；无冲突时 `mapRegion(..., "heap")`，将来访问由
  `Process::fixupFault -> MemState::fixupFault` 在 VMA 内分配页面。收缩时按页边界
  `unmapRegion`，再保存未对齐的精确 break。`arg0 < BrkBase` 或
  `arg0 >= MmapArenaBase` 返回原 break，因此不会穿过 mmap arena。
- 这些语义在代码审查上成立，且运行日志确实显示增长建立了
  `[0x90000000, 0x90002000)` heap VMA；五个 gem5 probe 重跑结果为
  `return42=42`、`mmap_real=42`、`mallocng_real=42`、
  `malloc_pointer_after=13`、`malloc_rw_after=134`。后一个 fault 已变为
  `0xfffffffb`，不再是 `0x90001000`。
- 但本任务没有独立的直接 `brk(0)`/非页对齐增长/冲突/收缩 probe；现有证据是源码
  语义加 mallocng 间接回归，不能把这些边界分支写成已运行验收。

#### 2. `BrkBase=0x90000000` 的边界与跨后端 ABI

这里发现原完成区“既有 ABI”的表述不成立，需修正后才能整体接受：

- `tests/scripts/dadao.ld` 的 `.heap` 输出段从各 ELF 的 `__heap_start=0x80007000`
  延伸到 `__heap_end=0x87e00000`；三个 mallocng ELF 的 `readelf -lW` 也显示 RW
  `PT_LOAD` 从 `0x80006000`、`MemSiz=0x7dfa000`，结束地址为 `0x87e00000`。
- 当前 QEMU patch series 包含 `0016-target-dadao-align-brk_base-default-with-dadao.ld-he.patch`，
  当前 `.work/source/qemu/target/dadao/cpu.c` 的 `case 214` 初值为
  `brk_base = 0x87E00000`。ML-014n 的 trace 也记录 QEMU `brk(0)` 为
  `0x87e00000`，而 gem5 本次实现返回 `0x90000000`。
- `0x90000000` 与当前 ELF 映像末端不重叠，也与 mmap arena
  `0x100000000` 不重叠；因此没有发现直接覆盖或 arena 重叠。但它在 ELF heap
  末端 `0x87e00000` 与 gem5 brk 初值之间留下未映射空洞，并使同一个 `SYS_brk`
  查询在 QEMU/gem5 返回不同地址。这是可观察的跨后端 ABI/布局分歧，不能称为
  当前统一 heap 边界；它也可能改变 allocator 的地址判定，虽然本轮没有证据把
  `malloc_pointer_after=13` 唯一归因于此。
- 后续必须二选一并由实现任务验证：让 gem5 与当前 ELF/QEMU 统一使用
  `0x87e00000`（或由实际 image boundary 计算），或者同步修改两后端和明确的 ABI
  约定。独立 reviewer 不在本轮修改实现。

#### 3. 构建、回归证据与宣称边界

- `/home/holight/DADAO-gem5` 在 `e6a6b9cdc9` 后 clean；该提交父为
  `6dd0d7c9f1`，父提交 diff 仅包含 `src/arch/dadao/decoder.cc`、
  `src/arch/dadao/process.cc`、`src/arch/dadao/process.hh` 三个文件，
  `git show --check` 无格式错误。
- 增量 `scons build/DADAO/gem5.opt -j6` 退出 0；五个 bounded rerun 日志与任务
  记录的退出码一致。`mallocng_real.debug.log` 的 heap VMA 记录和
  `malloc_rw_after` 的 `0xfffffffb` panic 足以支持“原 `0x90001000` brk fault
  已越过、仍有独立后续 fault”，不足以支持 mallocng 完整正确。
- 本任务本轮**未跑**：QEMU 重跑、直接 brk 边界 probe、clean-room gem5 全量重编、
  LLVM patch 从零 replay、完整 `llvm-lit` E2E、三方/四方 differential、root
  patch series 集成与回放。因此这些项目继续标记为未跑，ML-014m 的既有结果只能
  作为基线，不能冒充 ML-014o 本轮验收。

#### 4. 范围与最终区分

- 修改范围符合任务 ownership：source commit 只触及 gem5 DADAO 的上述三个文件，
  任务日志只在本任务 `.work` 下；没有触碰 LLVM/QEMU/musl、root patch series、
  `docs/issues.yaml`、contracts、manifests 或用户原始 ML-014a。
- **接受项**：gem5 `SYS_brk` 通过 `MemState::updateBrkRegion` 建立 VMA，并让
  `fixupFault` 获得 backing 的本地修复机制，按当前证据可接受。
- **Needs-fix 项**：`Process::BrkBase=0x90000000` 与当前 ELF `.heap` 末端及
  QEMU brk ABI 不一致，需另行修正或形成明确的双后端 ABI 决策；因此本任务总体
  判决为 **Needs-fix**，不能把 source commit 或五个 probe 结果写成完整 ML-014
  验收。
- `mallocng` 仅有 `mallocng_real` 的 gem5 probe 返回 42；pointer probe 为 13，
  read/write probe 为 134。`ML-014f` 仍为 Blocked/Not Accepted，原始
  `ML-014a` 仍未完成且保持原记录不变。
