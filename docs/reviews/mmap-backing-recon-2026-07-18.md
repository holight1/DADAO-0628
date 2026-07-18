# mmap arena 真实 backing 方案调研（ML-014b）

日期：2026-07-18
范围：当前 DADAO-0628 QEMU/gem5 patch、DADAO-gem5 SE 源码和现有测试脚本。
结论性质：调研和后续任务边界；没有在本任务中实现修复。

## 1. 当前事实与复现边界

当前 ML-007a patch 的 `SYS_mmap=222` 只维护地址游标：

- QEMU：`.work/source/qemu/target/dadao/cpu.c:173-191`，从
  `DADAO_MMAP_ARENA_BASE`（`.work/source/qemu/target/dadao/cpu.h:23`，
  `0x100000000`）返回页对齐地址；代码注释明确写着 “no real page mapping”。
- gem5：`/home/holight/DADAO-gem5/src/arch/dadao/decoder.cc:659-669`，
  `TrapInst::execute` 做同样的 bump；`/home/holight/DADAO-gem5` 当前
  HEAD 为 `215ccc1641`，对应 `components/gem5/patches/0011-*`。
- QEMU machine 的 MemoryRegion 只有：ROM `64 KiB @ 0x00100000`、exit
  MMIO `0x1000 @ 0x10000000`、`machine->ram` `128 MiB @ 0x80000000`，见
  `.work/source/qemu/hw/dadao/dadao-machine.c:14-19,57-76`。`ram_size` 还被
  `:69-75` 强制限定为精确的 128 MiB。因此 `0x100000000` 不在任何已注册
  region 中；QEMU 访问是 unassigned memory，写入不落地、读取返回 0。
- gem5 DADAO Process 在
  `/home/holight/DADAO-gem5/src/arch/dadao/process.cc:19-37` 建立
  `EmulationPageTable(PageBytes)` 和 `MemState`，但 mmap responder 没有调用
  `memState->mapRegion`、`allocateMem` 或等价路径。访问 `0x100000000` 时没有
  VMA/PTE，SE fault 无法修复。

现有 `tests/lit/E2E/mmap_probe.test` 仅检查三个返回地址的 delta、非零、页对齐
以及 `munmap`/`mprotect` 返回值（尤其见 `:53-109`），没有对返回地址做
`sto`/`ldo`。独立重跑：

```text
llvm-lit -v tests/lit/E2E/mmap_probe.test
PASS: E2E :: mmap_probe.test (1 of 1)
Total Discovered Tests: 1
  Passed: 1 (100.00%)
LLVM_LIT_RC=0
```

这个 PASS 只能证明两个 bump 游标实现一致，不能证明 backing 存在。
`tests/scripts/run_qemu_test.py:82-85` 的 QEMU 命令使用 `dadao-m1`、ROM
trampoline 和 flat binary；lit 的 gem5 配置在 `tests/lit/E2E/lit.cfg:19-24`
指向 `/home/holight/DADAO-gem5/build/DADAO/gem5.opt` 与
`tests/dadao/dadao_se.py`。后续 probe 应直接沿用这些真实路径。

## 2. QEMU 方案

### 2.1 方案 A：保持固定 `0x100000000`，新增独立 arena MemoryRegion（推荐）

在 `hw/dadao/dadao-machine.c` 注册一个与现有 RAM 分离的、从
`DADAO_MMAP_ARENA_BASE` 开始的 RAM region；`SYS_mmap` 继续返回同一固定
地址空间中的游标，但必须增加 arena 上限和溢出失败路径。最小实现可以是
一个预定容量的连续 region；如果选择按 mmap 调用建立子 region，则还要维护
region 对象列表和 `munmap` 的删除/生命周期。

优点：

- 保留现有 ABI/测试可见地址和 `QEMU/gem5` 的 `0x100000000` 共识；
  linker 的 `.text/.rodata/.data/.bss/.heap` 不用搬，trampoline stack、ROM、
  exit MMIO 也不变。
- QEMU 只需把 arena 地址加入 system address space；已有 flat binary 的
  `load_image_targphys(..., 0x80000000, ...)` 路径不受影响。
- 可以用一个明确的容量把“可用 mmap 范围”变成可测试的资源边界，而不是
  无界地增加 `mmap_cursor`。

代价和风险：

- 需要新增 host-backed RAM 的容量策略；固定大 region 会增加宿主内存/迁移
  状态，按调用子 region 则增加 QEMU MemoryRegion 管理和 snapshot 生命周期。
- 必须处理 `length==0`、页对齐加法溢出、超出 arena 上限；不能继续静默返回
  一个不可访问地址。
- QEMU 的 RAM region 是物理地址空间 backing，不等同于未来 MMU 的权限模型；
  `mprotect` 仍不能靠它完成真正的读写执行权限检查。

对现有布局影响：linker、stack、ROM、exit MMIO 和 flat/ELF load 地址均为
“不变”。只有 QEMU machine 的 MemoryRegion 列表及 mmap responder 的容量/失败
逻辑变化。

### 2.2 方案 B：把 arena 迁移到现有 128 MiB RAM 窗口内

把 `DADAO_MMAP_ARENA_BASE` 改为 `0x80000000..0x88000000` 中预留的范围，
使 QEMU 直接复用 `machine->ram`。这不是只改一个常量：当前 linker script
`tests/scripts/dadao.ld:49-54` 把 `.heap` 预留到 `0x87E00000`，trampoline
把 `rb1` 放在约 `0x87FF0000`，现有 RAM 的末端是 `0x88000000`。在这些约束
下，`0x87E00000` 到栈附近只有很小的空洞，无法作为可扩展 malloc arena；若
要放大空间，就必须搬 heap/stack、改变 trampoline 或扩大并重新定义 RAM。

优点：

- 不需要 QEMU 新增第二个 host-backed RAM region，内存迁移/设备枚举更简单。
- 返回地址落在现有 RAM，当前 QEMU TLB/flat-image 访问模型天然可达。

代价和风险：

- 会改变用户可见 mmap 地址，必须同步 QEMU、gem5、probe、相关 linker/运行
  时布局；旧的固定 `0x100000000` 假设和未来地址稳定性都会失效。
- 现有 heap 已经占用到 `0x87E00000`，stack 又在 RAM 尾部；若只取中间/尾部
  空间，容量很小且容易与栈增长或 brk 冲突。
- 若把 RAM 扩大到 `0x88000000` 以上，当前 machine 的精确 128 MiB 检查、
  linker 预留、trampoline 和 gem5 的对应地址策略都要一起改；这已经不是
  “复用已有 RAM” 的局部修复。

对现有布局影响：ROM 和 exit MMIO 地址可以保持，但 linker heap、stack、RAM
容量、mmap base、QEMU/gem5 地址一致性和地址型测试均可能变化。可复现性风险
显著高于方案 A。

### 2.3 QEMU 选择

推荐方案 A：保留 `0x100000000`，新增固定容量的独立 arena region，并在
responder 中用同一容量做边界检查。方案 B 只有在架构师明确接受改变用户态
地址空间布局后才值得考虑；不能默认把“放进 RAM”当作已批准决策。

## 3. gem5 SE 方案与生命周期

### 3.1 当前路径能否支持动态高虚拟地址

可以。`/home/holight/DADAO-gem5/src/sim/process.cc:318-345` 的
`Process::allocateMem(vaddr,size)` 只对 `vaddr` 做页对齐，然后从
`SEWorkload::allocPhysPages` 取得物理页，写入 `EmulationPageTable`；没有把
虚拟地址限制在 32 位或 system RAM 的低地址。`MemPool::allocate` 在
`src/sim/mem_pool.cc:95-101` 分配的是物理页，当前 `tests/dadao/dadao_se.py`
的 system memory range 是 512 MiB，因此高 VA 映射到低 PA 是可行的。

更完整的现成生命周期是 `MemState`：

- `mapRegion` 记录匿名 VMA；首次访问由 `fixupFault`（`mem_state.cc:385-416`）
  调 `Process::allocateMem` 懒分配物理页。
- `unmapRegion`（`mem_state.cc:190-275`）支持删除/裁剪/拆分 VMA，刷新
  TLB，并调用 `Process::deallocateMem` 释放已映射物理页。
- `extendMmap`（`mem_state.cc:451-477`）能寻找未占用范围，但 DADAO 当前
  `Process` 设置 `_mmapEnd=0x4000000000000000` 且默认 `mmapGrowsDown()`，
  与 ML-007a 选择的固定向上 `0x100000000` bump arena 不是同一策略。

因此，后续 gem5 patch 不应只调用 `allocateMem`：那会有 PTE 但没有 VMA，
`munmap`/fault 修复和生命周期不完整。推荐在 trap responder 中对已分配的、页
对齐的区间执行：

1. 检查固定 arena cursor、溢出和 `p->memState->isUnmapped`；
2. `p->memState->mapRegion(addr, aligned_len, "mmap")`；
3. 采用现有 `fixupFault` 懒分配，或在同一任务中明确采用
   `p->allocateMem(addr, aligned_len)` 的 eager 变体；两者都必须有验收依据。

对于当前单线程 M1，推荐匿名 VMA + 首次访问懒分配：它复用现有
`fixupFault`/`deallocateMem`，不会在 mmap 尚未触及时消耗全部物理页。`munmap`
应调用 `memState->unmapRegion`，以避免 VMA/PTE/物理页泄漏；当前 bump 地址不
复用也可以保留，不能把“释放后不复用”误写成完整 Linux mmap 语义。

### 3.2 权限边界

当前 `EmulationPageTable::Entry` 有 flags，但 `page_table.cc:48-72` 的 map
只存 flags，`translate` 只返回映射，不执行读/写/执行权限检查；DADAO 当前
Process 也没有 mprotect 的 VMA 权限接口。因此：

- M1 backing 任务必须实现：页对齐、非重叠地址、真实读写、匿名页首次访问
  backing、`munmap` 的 VMA/PTE/物理页生命周期，以及可观测的失败路径。
- M1 可以继续让 `mprotect` 返回 0 作为明确的 deferred/no-MMU 语义，但不能
  宣称已经实现保护；至少要避免它影响 backing probe 的真实读写结果。
- K1 MMU 任务再定义 PTE permission bits、读写执行 fault、TLB 刷新、partial
  unmap/protect 的边界和错误优先级。`contracts/mmu/README.md` 当前明确写着
  MMU deferred，未来 vectors 必须独立规定 VA/PTE/权限/故障优先级；本任务
  不应代替该合同做猜测性修改。

## 4. 判别性 backing probe 设计

建议新增独立的 hand-assembled `tests/lit/E2E/mmap_backing_probe.test`，不
依赖 musl/LLVM CodeGen，避免把后端或 libc 问题混入基础设施验收。输入和
判定如下：

1. `mmap(NULL, 0x1001, RW, ...)`，期望返回页对齐 `addr1`；实际写入并读回
   `addr1+0x0000`、`addr1+0x0fff`、`addr1+0x1000`、`addr1+0x1fff` 四个
   不同字节/字，覆盖两页和 page boundary。
2. `mmap(NULL, 0x3001, RW, ...)` 得到 `addr2`；期望
   `addr2-addr1 == 0x2000`，实际写入/读回 `addr2+0x0000` 和
   `addr2+0x3fff`，覆盖四页。marker 必须与第一段不同，防止两个返回地址
   别名或写入被丢弃。
3. 第三次 `mmap(NULL, 0x1, RW, ...)`，期望 `addr3-addr2 == 0x4000`；验证
   多次分配和页对齐游标，而不是只修一页/一段。
4. 对 `addr1` 调 `munmap`，检查返回 0；对 `addr2` 调 `mprotect`，检查
   返回 0。M1 不测试 `mprotect` 后禁止写入，因为当前 MMU contract deferred；
   K1 另加权限 fault probe。
5. 全部 marker 校验通过后 `SYS_write` 输出 `mmap-backing-ok\n`，再以
   `SYS_exit(42)` 结束；每个失败点使用不同非 42 退出码。若 QEMU 仍是
   unassigned memory，读回将是 0/错误；若 gem5 仍无 VMA/PTE，则首次 store
   在 `0x100000000` 处触发 page-table fault。这个测试能把“地址数值正确”
   与“真实 backing 正确”机械区分开。

建议的 lit 命令块：

```text
// RUN: %llvm-mc -triple=dadao -filetype=obj -o %t.o %s
// RUN: %ld.lld -T %S/../../scripts/dadao.ld %t.o -o %t.elf
// RUN: %llvm-objcopy -O binary %t.elf %t.bin
// RUN: bash -c '%qemu -M dadao-m1 -nographic -bios %trampoline -kernel %t.bin > %t.out 2>&1; test $? -eq 42'
// RUN: grep -c "mmap-backing-ok" %t.out | xargs test 1 -eq
// RUN: bash -c '%gem5 %gem5_se %t.elf > %t.gout 2>&1; test $? -eq 42'
// RUN: grep -c "mmap-backing-ok" %t.gout | xargs test 1 -eq
```

验收还应做一次负向 mutation：临时在本地验证分支中禁用 QEMU
MemoryRegion / gem5 VMA backing（不提交 mutation），确认 QEMU 读回校验失败、
gem5 首次访问不能以 42 结束。这样不会把“程序没有真正触碰 arena”误判为通过。

## 5. 后续任务拆分建议

任务号以下为待架构师确认的建议名，不表示已批准：

| 任务 | ownership | 依赖 | 主要交付与门禁 |
|---|---|---|---|
| `ML-014c-qemu-mmap-backing` | `.work/source/qemu/hw/dadao/dadao-machine.c`、`target/dadao/cpu.c/.h`；输出 `components/qemu/patches/0018-*.patch` 与 `series` | 本报告、固定 arena 方案决策 | 新 RAM region/容量和 cursor overflow；QEMU backing probe 42；既有 QEMU E2E 全绿；不得改 LLVM/musl/contracts |
| `ML-014d-gem5-mmap-backing` | `/home/holight/DADAO-gem5/src/arch/dadao/decoder.cc`，必要时 `src/arch/dadao/process.*`/`src/sim/*`；输出 `components/gem5/patches/0012-*.patch` 与 `series` | `ML-014c` 的地址/容量决策，或明确两边并行接口 | VMA + page-table/physical-page backing，munmap 生命周期，gem5 backing probe 42；`dadao_se.py` 与 existing E2E 回归；避免只加 PTE 不加 VMA |
| `ML-014e-mmap-backing-probe` | `tests/lit/E2E/mmap_backing_probe.test`（及必要的独立输入） | 两个 backend patch | 双后端实际写读、多页边界、多次分配、marker/exit/output 均通过；mutation 能失效；不依赖 musl |
| `ML-014f-musl-malloc-e2e-resume` | `tests/lit/E2E/Inputs/musl_malloc_printf.c`、`musl_malloc_printf.test`，必要时只更新任务记录 | `ML-014c`、`ML-014d`、`ML-014e` | 重新完成 ML-014a 的 mallocng 真实 mmap、两次不同尺寸内容校验、非变参输出；全 E2E 59/59 与既有 differential/manifest gates |

patch 要求：QEMU/gem5 每个任务在当前组件 HEAD 上追加普通 commit，再由架构师
导出并追加 patch series；本调研任务不做 `git am`、rebase、reset、源码修改或
patch 导出。每个实现任务都要单独记录 component HEAD、patch 应用顺序、双后端
probe 输出和回归门禁，最终再由架构师做 ground-truth 重跑。

## 6. 未决事项

- 固定 arena 的容量、超限返回值（建议明确为失败而不是回收/静默 alias）需要
  架构师确认；当前 ADR/contract 没有给出容量合同。
- gem5 采用 VMA lazy backing 还是 mmap 时 eager `allocateMem` 需要在实现任务
  中作出单一选择；本报告推荐 lazy，但验收必须覆盖首次访问和跨页访问。
- `munmap` 在 M1 是否允许地址不复用、以及错误输入的返回值仍属 syscall
  charter 的实现细节；本任务不修改 `contracts/` 或 ADR。
- `mprotect` 的真实权限、TLB/fault 规则留给 K1 MMU 任务；本任务不登记/关闭
  `docs/issues.yaml` 中已有 issue，也不把它写成已修复。

## 7. 本任务范围复核

本报告没有修改 QEMU、gem5、LLVM、musl 源码或 patch series，也没有修改
`contracts/`、`manifests/`、`docs/issues.yaml`。当前已有的 `docs/issues.yaml`
修改和其它未跟踪任务文件属于任务开始前工作区状态，未触碰。
