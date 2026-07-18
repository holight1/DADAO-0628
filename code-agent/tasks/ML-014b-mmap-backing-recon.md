# ML-014b: mmap arena 真实 backing 方案调研

**执行环境**：本地 subagent（双后端基础设施调研，禁止实现修改）

**状态**：已完成

## 背景

`ML-014a` 在真实 mallocng mmap 路径中发现：`cfx_smon mmap(222)` 当前只推进地址游标，不建立真实内存 backing。QEMU 对 `0x100000000` arena 的访问静默丢写，gem5 SE 对同一地址访问直接 page-table fault panic。ML-014a 明确禁止修改 QEMU/gem5，因此本任务只负责把后续实现任务的边界和验收方案钉死。

## 目标

产出 `docs/reviews/mmap-backing-recon-2026-07-18.md`，分别审查 QEMU 与 gem5 的最小可行修复，并回答：

1. QEMU 当前 MemoryRegion/地址空间布局，arena backing 应放在固定 `0x100000000`，还是应迁移到已有 RAM 区；两种方案对 linker、stack、ROM、exit MMIO 和 ELF/flat binary 的影响。
2. gem5 SE 当前 DADAO Process/EmulationPageTable 的内存分配路径；`allocateMem` 或等价机制能否支持 mmap 动态范围，生命周期和权限语义如何处理。
3. `munmap`/`mprotect` 在当前无 MMU Phase A 与未来 K1 MMU 之间的边界，哪些语义必须现在实现，哪些应明确 deferred。
4. QEMU 与 gem5 如何用同一组判别性测试证明“地址返回 + 实际写读 + 多页/页对齐 + 多次分配”而不是只验证地址数值。
5. 需要拆成几个实现任务、每个任务的文件 ownership、依赖、回归门禁和 patch series 要求。

## 硬约束

- 不修改 QEMU、gem5、LLVM、musl 源码或 patch series。
- 不修改 `contracts/`、`manifests/`、`docs/issues.yaml`；新发现只写入报告和任务遗留区，交架构师决定是否登记。
- 不把“把 arena 放入 RAM”当成已批准方案，必须同时列出地址空间和可复现性风险。
- 必须独立阅读当前 QEMU/gem5 patch 与运行脚本，不能只引用 ML-014a 的描述。
- 完成后必须填写完成区，并在任务 md 追加 `## 审阅记录（subagent）`；reviewer 必须独立重跑关键命令/源码核验。

## 验收

- 报告包含 QEMU、gem5 各自的代码路径和证据。
- 给出至少两个方案的明确 trade-off，并推荐一个后续实现拆分。
- 给出最小真实 backing probe 的输入、期望结果和双后端执行命令。
- 本任务没有源码改动；`git diff -- components/qemu components/gem5 components/llvm components/musl contracts manifests` 为空。

## 参考

- `code-agent/tasks/ML-014a-musl-e2e-malloc-printf.md`
- `docs/issues.yaml` 中 `mmap-arena-unbacked-real-memory-qemu-gem5`
- `components/qemu/patches/0017-*`
- `components/gem5/patches/0011-*`
- `tests/scripts/run_qemu_test.py`
- `~/DADAO-gem5/src/arch/dadao/process.cc`

## 完成区

**状态**：已完成

**修改文件**：`docs/reviews/mmap-backing-recon-2026-07-18.md`、本任务文件完成区与审阅记录；未修改任何组件源码、patch series、contracts、manifests 或 `docs/issues.yaml`。

**验收结果**：
- 报告已给出 QEMU 真实 MemoryRegion 布局与 `SYS_mmap` 路径：`.work/source/qemu/hw/dadao/dadao-machine.c`、`.work/source/qemu/target/dadao/cpu.c/.h`。
- 报告已给出 gem5 DADAO Process/TrapInst、`MemState`、`Process::allocateMem/deallocateMem`、`EmulationPageTable` 与 `MemPool` 的真实路径和证据。
- 已比较固定 `0x100000000` 独立 arena 与迁移进现有 RAM 两个方案，明确推荐和地址空间/可复现性 trade-off。
- 已设计覆盖地址返回、非页长对齐、多页跨界、实际写读、多次分配、`munmap`/`mprotect` 返回值的双后端 backing probe，并给出 lit 命令块和负向 mutation 判别。
- reviewer 独立复跑 `llvm-lit -v tests/lit/E2E/mmap_probe.test`：`PASS`，`Total Discovered Tests: 1 / Passed: 1`，退出码 `0`。该结果只验证既有地址游标 probe，报告已明确它不能证明 backing。
- reviewer 独立核验报告必备证据：`REPORT_REQUIRED_EVIDENCE=PASS`；核验禁止组件范围：`FORBIDDEN_COMPONENT_DIFF=EMPTY`。

**遗留问题**：实现任务仍需架构师确认 arena 容量/超限错误、gem5 lazy/eager backing 选择和 M1 `munmap`/地址复用细节；这些属于后续实现任务，不是本调研报告的未完成验收项。现有 `docs/issues.yaml` 中 `mmap-arena-unbacked-real-memory-qemu-gem5` 保持 open，未在本任务中修改。

## 审阅记录（subagent）

### 审阅记录（subagent · 判决 = 通过）

- reviewer 已独立重读 `reviewer.md`，并逐段核对 `docs/reviews/mmap-backing-recon-2026-07-18.md`；本任务实际改动仅为报告和本任务文件记录。
- 证据核验：QEMU machine 的 ROM/exit/RAM 路径与地址范围 ✓；QEMU `case 222/215/226` 和 `0x100000000` 游标 ✓；gem5 `Process::allocateMem/deallocateMem`、`MemState::mapRegion/unmapRegion/fixupFault`、`EmulationPageTable` 和物理页池路径 ✓。
- 方案核验：报告包含固定独立 arena 与现有 RAM 内迁移两种方案，分别列出 linker、stack、ROM、exit MMIO、容量和可复现性影响，并明确推荐方案 ✓。
- probe 核验：报告要求真实 `sto/ldo`，覆盖非页长对齐后的多页边界、第二次不同大小分配和第三次游标推进，并给出 QEMU/gem5 lit 命令与失败判别 ✓。
- 真实命令重跑：`.work/build/llvm/bin/llvm-lit -v tests/lit/E2E/mmap_probe.test` → `PASS: E2E :: mmap_probe.test (1 of 1)`、`Passed: 1 (100.00%)`、`REVIEW_MMAP_PROBE_RC=0` ✓。
- 约束核验：`git diff -- components/qemu components/gem5 components/llvm components/musl contracts manifests` 为空；QEMU、gem5、musl 工作树无本任务引入的源码改动 ✓。
- 未测输入/边界推敲：审查了 zero-length/页对齐加法溢出、arena 容量上限、跨页访问、VMA 与 PTE 生命周期、mprotect 权限未实现和未来 K1 MMU 边界；报告均作为后续任务约束或 deferred 项记录，没有伪称已修复 ✓。
- finding：无（判决 = 通过）。

## 架构师复核（ground-truth，2026-07-18）

**判决：Accepted**

独立复核未采信 worker 完成区数字，重新检查了报告、任务 diff、当前组件源码和既有 probe：

- `.work/build/llvm/bin/llvm-lit -v tests/lit/E2E/mmap_probe.test` → `PASS: E2E :: mmap_probe.test (1 of 1)`，退出码 `0`。
- 独立核对 QEMU `DADAO_MMAP_ARENA_BASE=0x100000000`、`case 222`、`mmap_cursor` 和 `no real page mapping` 注释，证实当前实现确实只有地址记账。
- 独立核对 gem5 `Process::allocateMem/deallocateMem`、`MemState::mapRegion/unmapRegion/fixupFault` 与 DADAO trap 路径，证实报告给出的 lazy VMA/backing 路径有源码依据。
- 独立执行 `git diff` 检查，QEMU/gem5/LLVM/musl、contracts、manifests 均无本任务改动；`~/DADAO-gem5` 仍在预期分支且无本任务引入的变更。
- 报告明确区分了“现有 mmap 地址 probe 通过”和“真实 backing 尚未存在”，未把调研结果伪称为修复完成。

报告中的固定 arena 方案、gem5 lazy/eager 选择、容量/错误码和 M1 `mprotect` 边界仍保留为后续实现任务的决策点，符合本任务“只调研、不实现”的范围。无需返工。
