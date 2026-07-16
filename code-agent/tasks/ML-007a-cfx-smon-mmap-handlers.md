# ML-007a: cfx_smon mmap/munmap/mprotect handler（musl 移植阶段A）

**执行环境**: 本地 subagent（QEMU + gem5 双后端，syscall responder 扩展）

**状态**: 待执行

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
