# ML-007a: cfx_smon mmap/munmap/mprotect handler（musl 移植阶段A）

**执行环境**: 本地 subagent（QEMU + gem5 双后端，syscall responder 扩展）

**状态**: 已完成

**前置**：`docs/reviews/musl-recon-2026-07-16.md`（musl 移植调研，阶段A定义）、`docs/adr/0014-libc-syscall-charter.md` D5.2（musl 阶段2 时机更正）。现有 `cfx_smon` responder（QEMU `target/dadao/cpu.c`、gem5 `src/arch/dadao/decoder.cc`）只实现 `write`(64)/`exit`(93)/`exit_group`(94)/`brk`(214)，其余一律 `-ENOSYS`。

## ⚠️ 硬性约束（必读，本 session 反复踩过的坑）

1. **禁止对 `.work/llvm`/`.work/qemu`/任何 `.work/<component>` 做 `git rebase`/`git am` 重放整条历史/`git reset` 之类改写既有 git 历史的操作**。只允许在当前 HEAD 基础上做普通的、追加式的新提交 + `git format-patch` 生成新 patch 加入对应 `components/<name>/patches/series`。
2. **禁止运行 `make fetch` / `python3 scripts/fetch.py`**（本任务不需要拉取新组件；即使 `fetch.py` 现在已修复"跳过已应用 patch 的组件"这个 bug，也没有理由在本任务里触发全组件的 fetch 检查）。
3. gem5 侧改动在 `.work/source/gem5` 或直接在 `~/DADAO-gem5`？**本仓库 gem5 的实际开发一直在独立仓库 `~/DADAO-gem5`（有自己的 git 历史），不是 `.work/source/gem5`（只是占位/未来对齐用途，从未真正应用过 patch）**——gem5 侧改动请在 `~/DADAO-gem5` 里做，验证后用 `git format-patch` 导出到 `components/gem5/patches/`，参照现有 `0009`/`0010` 等 gem5 patch 的模式。

## 做什么

给 QEMU 和 gem5 的 `cfx_smon` responder 各补三个 syscall（asm-generic 编号）：

- **`mmap`（222）**：musl mallocng 唯一真正依赖的分配方式（`mmap(NULL, n*pagesize, PROT_READ|PROT_WRITE, MAP_PRIVATE|MAP_ANON, -1, 0)`，无 fd）。当前 M1 无 MMU/无分页（SEE 特权层已排除），**记账式实现**：维护一个独立的"mmap 区间"游标（简单 bump allocator，从某个固定起始地址往上分配，按 `length` 参数前进，页对齐），返回分配到的地址；不做真实页保护（`PROT_NONE`/`PROT_READ`/`PROT_WRITE` 一律接受，语义上都当作"这段地址现在可读写"处理，因为没有 MMU 就没有真正的保护机制可言，双后端在这一点上要行为一致）。
- **`munmap`（215）**：记账式返回成功（0），不需要真正回收/复用地址空间（阶段A/B 的静态单线程测试规模不需要这个）。
- **`mprotect`（226）**：记账式返回成功（0），不做真实保护语义变更。

**关键设计决策——mmap 区间起始地址选哪**：需要选一个和现有内存布局（`.text`@0x80000000、`.rodata`/`.data`/`.bss`/`.heap` 到 `0x87E00000`、QEMU trampoline 栈约 `0x87FF0000`、gem5 SE 栈 `0x00007FFFFFFFF000`——见 DG-006a）**不冲突**的地址区间，且 QEMU 和 gem5 要用**同一个**起始地址（双后端一致，不能各自拍脑袋定不同的值）。建议：选一个明显在 heap 区之上、trampoline 栈之下的地址（比如 `0x88000000`起，如果间隙够用），或者选一个更高、明显不会跟任何现有布局冲突的固定值（比如 `0x100000000`，即 4GB 处——DADAO RB 地址空间是 48-bit，完全放得下，且离所有现有布局都很远）。**由 subagent 自行核实现有布局+ 选定一个安全值，两个后端必须用相同的起始地址常量**。

## 约束

- **不做真实页保护**（没有 MMU，`mprotect`/mmap 的 `PROT_NONE` guard page 都当"成功但无实际约束"处理）——这是 ADR-0014 D3 已经确立的"记账式"路线，不是本任务自创，参照现有 `brk` handler 的实现风格。
- QEMU 和 gem5 的实现要**语义一致**（同样的地址分配策略、同样的起始地址常量），不能各写各的。
- 手写 `trap cfx_smon` 汇编向量验证（不依赖 musl 本身——musl 骨架是后续任务），类似现有 `tests/scripts/pico_stubs.s`/`syscall_hello.test` 的验证范式。
- 不回归：全 E2E（当前 54/54，零已知失败）、四方 AGREE(3-way)=200/DIVERGE=0、Sail AGREE(4-way)=200。

## 验收（架构师亲跑）

1. 写一个手写汇编测试（`trap cfx_smon` 直接调用 mmap，检查返回地址在预期区间内、非零、页对齐；调用 munmap/mprotect 确认返回 0），QEMU + gem5 双后端跑通、结果一致。
2. 判别性探针：连续两次 mmap 不同 `length`，确认两次返回的地址不重叠（真正在往前推进，不是每次都返回同一个地址——参照本 session 一直强调的"真实运行时判别性验证"标准，不能只验证"不崩溃"）。
3. 全 E2E + 四方差分不回归。

```bash
cd ~/DADAO-0628
llvm-lit tests/lit/E2E/ 2>&1 | tail
python3 tools/run_differential.py 2>&1 | tail -3
```

## 参考指针

- `docs/reviews/musl-recon-2026-07-16.md` §2.3（缺口清单+优先级）、§5（阶段A定义）
- `components/qemu/patches/`（现有 `0013-dadao-trap-syscall.patch` 是 write/exit/brk 的原始实现，本任务在其基础上扩展；`.work/source/qemu/target/dadao/cpu.c` 的 `dadao_cpu_do_interrupt` `cfxcode==2` 分支）
- `~/DADAO-gem5/src/arch/dadao/decoder.cc`（`TrapInst::execute`，gem5 侧对应实现；`components/gem5/patches/0010-dadao-trap-syscall.patch` 是原始版本）
- `tests/scripts/pico_stubs.s`、`tests/lit/E2E/syscall_hello.test`（现有手写 syscall 测试范式）
- `docs/adr/0014-libc-syscall-charter.md` D2（syscall ABI：rd16=号/rd17-22=参数/rd31=返回值）

—— 自审见 DS.md §自审流程同等标准（subagent 自己复核，逐条 finding + 判决）。**必须真跑判别性探针（连续 mmap 地址不重叠），不能只验证"不崩溃"**；**严格遵守不碰 patch/git 历史的约束**。

## 完成区

**状态**：已完成

**arena 起始地址选择**：`0x100000000`（4GiB），QEMU（`DADAO_MMAP_ARENA_BASE`，`target/dadao/cpu.h`）与 gem5（`MMAP_ARENA_BASE`，`src/arch/dadao/decoder.cc`）字面量完全一致。核实过的现有布局：`dadao.ld` `.heap` 段止于 `0x87E00000`；`tests/scripts/gen_trampoline.py` 确认 QEMU trampoline 栈 SP=`0x87FF0000`；`~/DADAO-gem5/src/arch/dadao/process.cc:31` 确认 gem5 SE 栈 `stack_base=0x00007FFFFFFFF000`（DG-006a）。`0x100000000` 距三者都有巨大余量（上距 heap/trampoline 区约 1.9GB，下距 gem5 栈约 8×10^7 倍），且远低于 gem5 自身通用 SE `mmap_end`（`process.cc:35`，`0x4000000000000000`，我们的自定义 `trap` responder 并不使用这条路径，仅供交叉核实无冲突）。

**修改文件**：
- `.work/source/qemu/target/dadao/cpu.c`（`EXCP_CFXTRAP`/`switch(sysno)` 新增 `case 222/215/226`）
- `.work/source/qemu/target/dadao/cpu.h`（新增 `DADAO_MMAP_ARENA_BASE` 宏）
- `~/DADAO-gem5/src/arch/dadao/decoder.cc`（`TrapInst::execute` 新增 `case 222/215/226` + `MMAP_ARENA_BASE` 常量）
- `tests/lit/E2E/mmap_probe.test`（新增，手写 `trap cfx_smon` 判别性探针）
- `components/qemu/patches/0017-target-dadao-cfx_smon-mmap-munmap-mprotect-handlers-.patch` + `series`
- `components/gem5/patches/0011-arch-dadao-cfx_smon-mmap-munmap-mprotect-handlers-ML.patch` + `series`

**核心实现（两后端逐字一致）**：
```c
// mmap(222): bump allocator，page-align 请求长度后前进
static uint64_t mmap_cursor = ARENA_BASE;   // 首次 = ARENA_BASE
uint64_t aligned = (length + 0xFFF) & ~0xFFFULL;
if (aligned == 0) aligned = 0x1000;
ret = mmap_cursor;
mmap_cursor += aligned;
// munmap(215): ret = 0;（不做真实回收）
// mprotect(226): ret = 0;（不做真实保护变更）
```

**验收结果**（架构师亲跑 ground-truth，非估算）：
- `mmap_probe.test`（3 次 mmap，长度 8192/12288/4096；用寄存器减法+`breq`比较，非立即数比较，因差值超 12-bit 立即数范围）：QEMU exit=42、gem5 exit=42，输出均含 `mmap-ok`（`grep -c` 各=1）——两次地址差分别精确等于 8192、12288，证明游标真实前进而非返回同一地址；`addr1` 非零且 4095-mask 页对齐；munmap/mprotect 均返回 0。
- 全 E2E：`llvm-lit tests/lit/E2E/` → **55/55 通过**（54 基线 + 新增 `mmap_probe.test`，零回归）。
- 差分：`python3 tools/run_differential.py` → **AGREE(3-way)=200/DIVERGE=0/HARNESS=6/QEMU-SKIP=0**，**Sail AGREE(4-way)=200/SAIL-DIVERGE=0**，与基线一致。
- QEMU 侧独立重 build（`ninja qemu-system-dadao`）、gem5 侧独立重 build（`scons build/DADAO/gem5.opt -j6`）均通过（仅预置无关警告，无 error）。
- `git commit`（普通追加提交，非 amend/rebase）+ `git format-patch` 导出，`.work/source/qemu`、`~/DADAO-gem5` 均未触碰既有历史；`python3 scripts/manifest_check.py` 通过。

**遗留问题**：无阻塞项。subagent review 记的 2 条均为不影响正确性的风格提示（见下），已如实记录、判定无需处置。

## 审阅记录（subagent · 判决 = 通过）

- subagent 已读 reviewer.md 惯例并逐行审 diff（改动文件：QEMU cpu.c/cpu.h、gem5 decoder.cc、mmap_probe.test），核对参照 syscall_hello.test 范式与 spec.md §3.5/§5.2。
- 核验点：
  - 页对齐取整逻辑两后端逐字一致（`(length+0xFFF)&~0xFFFULL`，`length=0`兜底`0x1000`）✓，手算/脚本核验 length∈{0,1,4095,4096,4097} 两后端结果一致 ✓。
  - arena 常量两后端字面量完全相同（`0x100000000ULL`）✓；munmap/mprotect 均无条件 `ret=0` ✓。
  - 寄存器/状态卫生：仅读 rd16-19、写 rd31，`static` 游标与既有 `brk_base` 模式一致，进程级生命周期正确、无跨测试污染风险 ✓。
  - 判别性：手推"回退到 -ENOSYS"或"总返回同一固定地址"两种回归场景下 rd31 取值，确认 check1/check2 的 `breq`+`jump fail` 路径会真正拦下 ✓；`add`/`sub` 四操作数用法（`rdha=rd0` 弃高位、`rdhb` 取结果）符合 spec §3.5 legality ✓。
- 未测输入/边界推敲：mmap_probe.test 本身只探测已页对齐的 3 个长度（8192/12288/4096），非对齐长度（如 1、4097）的取整分支未被运行时探针覆盖——**但逻辑本身经手算证实两后端一致正确**，判定为覆盖面提示、非缺陷。
- finding：
  1. 取整逻辑正确性——手算 5 组值两后端一致 → 非缺陷。
  2. 双后端一致性（常量+取整+munmap/mprotect）——逐字核对一致 → 非缺陷。
  3. 寄存器/状态卫生——仅涉及文档化寄存器、static 变量作用域正确 → 非缺陷。
  4. 探针判别力——回归场景手推确认会被拦下 → 非缺陷。
  5. **风格提示（不阻塞）**：`length+0xFFF` 对接近 `UINT64_MAX` 的长度无溢出防护（会绕回小值而非放大）。处置：❌不修——记账式 bump allocator（ADR-0014 D3）无真实调用方会传此类长度，非真实风险面。
  6. **风格提示（不阻塞）**：check3（`addr1 != 0`）在当前固定非零 arena 常量下是非判别性的死代码，只有未来改 arena 常量为 0 才有意义。处置：❌不修——保留作为未来改常量时的防御性检查，无害。
- 判决：**通过**（Accepted，无真实缺陷；2 条非阻塞风格提示均判定不修，理由已附）。

## 架构师复核（ground-truth）

**独立验证方法**：不采信完成区/subagent 判决，从 git 状态开始逐项重跑。

- `.work/source/qemu` `git log`：干净单提交 `3587e17`（"target/dadao: cfx_smon mmap/munmap/mprotect handlers (ML-007a)"），落在已知恢复基线 `a26e252` 之上；`git status` 干净，无未提交改动、无历史重写迹象。
- `~/DADAO-gem5` `git log`：干净单提交 `215ccc1641`，落在 `61fe302bf2` 之上；`git status` 干净。
- 逐行读 `cpu.c`/`cpu.h` diff：改动量小（27+11 行），`case 222/215/226` 语义正确；核对 ABI（ADR-0014 D2：rd17=arg0/rd18=arg1/...）确认 `arg1` 即 mmap 的 `length` 参数无误。
- `ninja -C .work/source/qemu/build qemu-system-dadao`：**干净重 build 通过**（4 步、零 error）——subagent 报告的"本地 -Werror 环境问题"在架构师重 build 中未复现，判定为该 subagent 会话的局部环境问题，非代码缺陷，无需处理。
- `scons build/DADAO/gem5.opt -j6`（`~/DADAO-gem5`）：已是最新（up to date），零改动重 build 确认。
- `llvm-lit -v tests/lit/E2E/mmap_probe.test` → **PASS (1/1)**。
- 读 `mmap_probe.test` 源码逐行核对判别性：三次 mmap（8192/12288/4096）用寄存器减法 + `breq`（非立即数比较，因差值超 12-bit 立即数范围）精确断言游标前进量；`brz`/`and`+`brnz` 断言非空+页对齐；munmap/mprotect 断言返回值为 0；确认非"仅不崩溃"式弱测试，是真判别性探针——与 subagent 自评一致。
- 全 E2E：`llvm-lit tests/lit/E2E/` → **55/55（100%）**，较基线 54 净增 1，零回归。
- 差分：`python3 tools/run_differential.py` → **AGREE(3-way)=200/DIVERGE=0/HARNESS=6**，**Sail AGREE(4-way)=200/SAIL-DIVERGE=0**，与基线逐位一致。
- `python3 scripts/manifest_check.py` → **PASS**（spec 锁 `9f378f4`，enabled 组件 llvm/qemu/gem5/llvm-test-suite 均一致）。

**结论**：subagent 判决（通过）与架构师独立复核完全吻合，2 条风格提示（整数溢出无防护、check3 当前非判别性）判定不修的理由合理，予以采纳。**ML-007a 验收通过，Phase A（syscall handler 补齐）三项 P0/P1 syscall（mmap/munmap/mprotect）全部落地，一任务完成，无需拆分。**
