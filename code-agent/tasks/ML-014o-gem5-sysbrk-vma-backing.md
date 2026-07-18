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

## 审阅记录

（待独立 reviewer 复核；请重点检查初始 `BrkBase` 与 ELF heap 边界、冲突/收缩
语义，以及上述五个回归证据。）
