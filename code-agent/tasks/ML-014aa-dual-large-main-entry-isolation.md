# ML-014aa：双大块 ELF 的 startup→main-entry 分阶段隔离

**执行环境**：本地 subagent worker；承接 ML-014z Needs-isolation

**状态**：Completed/Needs-further-isolation（2026-07-19）

## 目标

只定位 ML-014z ELF 在 startup 间接调用 main 时为何偏离到栈地址。先证明或否定
同一代码布局、同一 archive member 集合下能进入 main；在 main-entry 双端成立前
不运行 allocator 阶段，不修改任何实现。

## Ownership

- worker 只写 `.work/ML-014aa-*` 派生 probe/runner/trace 与本 task MD。
- 保留 ML-014z 完整后续 body 和链接成员，通过 volatile stage 在 main 第一段
  立即返回专用码；不得让编译器消去后续 malloc/free 引用。
- 沿用锁定 clang/lld/crt1/libc.a/script 和双后端；不修改源码实现、root tests、
  patches、issues、contracts、manifests 或 ML-014a。
- 外部架构资料不在 worker scope；多人共享仓库，不回滚他人改动。

## 执行阶梯

1. 构造 stage=0 的 main-entry 变体：入口第一项可观测 marker/专用 guest exit，
   后续保留 ML-014z 完整 body；核对 object/ELF/map/成员与 main 入口地址。
2. 同一 ELF/bin 跑 QEMU/gem5，并保留 QEMU in_asm 与 gem5 Exec trace，证明实际
   call target、main 是否命中、返回/退出路径。
3. 与 Accepted ML-014y 和失败 ML-014z 的 startup/main callsite、寄存器搬运、
   relocation、代码/页布局逐项比较，指出首个静态或动态差异。
4. 若 main-entry 双端均命中，才提出后续 allocator stage 任务；若未命中，下一
   任务必须收口到 startup/call/relocation/code-layout，不进入 malloc。
5. 记录结论、置信度、自审并等待独立 review。

## 验收

- 同一 stage ELF 的两后端有可审计 main-entry 命中或未命中证据，不能只看 host rc。
- 给出首个可证明差异和最窄后续实现/诊断边界。
- 不宣称双块 allocator、ML-014f 或 ML-014a 完成。

## 完成区

### Finding：双后端均未越过 startup→main，任务完成但不能接受

本记录只收口既有 `.work/ML-014aa-dual-large-main-entry-isolation/` 产物；未运行
新实验、未重编译、未改写 `.work`，也未修改实现。结论为
**Completed/Needs-further-isolation**：本任务的 startup→main-entry 隔离证据已完成，
但 `main-entry` 双端门未闭合，因此不能进入 allocator 阶段。

#### 1. 构建、链接与 object/ELF 结果

| 阶段 | 既有结果 | 证据与判定 |
|---|---:|---|
| compile/object | `compile_rc=0` | `.o`、object readobj/disassembly 均生成；object undefined 仅为 `malloc`、`free` |
| link | `link_rc=0` | ELF、map、`--why-extract` 均生成；`main=0x80000110` |
| objcopy | `objcopy_rc=0` | flat BIN 生成 |
| 总体验证 | `validation_rc=1` | 双后端没有达到专用 main-entry 成功码，故验收失败 |

以上均来自 `result.txt` 与对应 sidecar；没有把 host 退出码当作 guest 阶段码。

#### 2. 双后端动态边界

- QEMU：`qemu_rc=130`、`qemu_timeout=no-timeout`。`qemu.in_asm.trace` 在
  startup 间接调用之后反复执行错误目标 `0x7ffffcb8`；没有命中
  `main@0x80000110`，也没有 main-entry marker/成功码。
- gem5：`gem5_rc=0`、`gem5_timeout=no-timeout`，但
  `gem5.exec.trace` 在 `__libc_start_main+100` 的间接 `call` 后执行
  `0x7ffffcb8 @__fini_array_end+3256` 的 `halt`；`gem5.result-focus.txt`
  明确记录 `SIM_END: halt code=0`。这只是错误 halt 的模拟器 host rc，不是
  probe 成功。
- 因而两个 backend 都实际执行错误 target `0x7ffffcb8`，都未到达
  `main@0x80000110`；现有证据没有进入 malloc/free 或任何 allocator 语义。

#### 3. archive、锁定输入与 runtime 比较

aa 的 archive member set 与 ML-014z 完全一致，`members_vs_z_rc=0`：

`_Exit.o`, `__environ.o`, `__errno_location.o`, `__init_tls.o`,
`__libc_start_main.o`, `__lock.o`, `__set_thread_area.o`, `default_attr.o`,
`defsysinfo.o`, `exit.o`, `free.o`, `get_tp.o`, `libc.o`, `lite_malloc.o`,
`madvise.o`, `malloc.o`, `memcpy.o`, `mmap.o`, `mprotect.o`, `munmap.o`,
`syscall_ret.o`。

`locked-hash-cmp.rc=0` 与 ML-014z 的锁定输入比较一致；
`runtime-tools-hash-cmp.rc=0` 与 ML-014z 的 runtime-tools 比较一致。现有
比较只证明记录中的锁定/runtime identity 未漂移，不证明运行时控制流正确。

#### 4. 最窄静态结论与下一边界

`relocation-comparison.txt` 显示三份 ELF 的 locked `crt1` relocation 输入相同，
最终 ELF 的 relocation section 均为空；但 aa 的 startup 布局把
`__libc_start_main` 放在 `0x80000c44`，其间接调用前的地址物化序列位于
`0x80000c84`--`0x80000ca8`，包含 `rela`、global-page 访问与随后
`call rb5`。动态 trace 正好在这次 startup 间接调用后落到 `0x7ffffcb8`。

因此下一边界应是 **startup address materialization**。现有静态形态使
**RELA/global-page boundary** 成为谨慎的优先检查方向，但这不是根因结论：本任务
没有证明 RELA 解码、global-page 值或任一具体 materialization 指令存在 bug，也没有
证明它们之外的因素已排除。

下一任务必须是 **minimal ELF/code-layout threshold plus relocation decode**：用最小
ELF/代码布局阈值复现地址物化转折，并解码/对照对应 relocation；在该边界闭合前，
不做 allocator、malloc、free、mmap 或 munmap 工作。

### Independent review

本收口依据既有 aa 与 ML-014z 产物完成；没有新增实验或实现修改。判定保持
**Completed/Needs-further-isolation**，后续范围限定为上述 ELF/code-layout 与
relocation decode 边界。

### Independent review（2026-07-19；独立复核）

**Verdict：Accepted-as-isolation。** 该 verdict 仅接受本任务作为
startup→main-entry 的隔离收口，不接受 main-entry 命中，也不接受任何 allocator
阶段结论。复核未运行新实验、未重编译、未修改实现或 `.work` 产物。

- `.work/ML-014aa-dual-large-main-entry-isolation/result.txt` 与对应 sidecar
  明确记录 `qemu_rc=130`、`qemu_timeout=no-timeout`、`gem5_rc=0`、
  `gem5_timeout=no-timeout`、`validation_rc=1`。
  `.work/ML-014aa-dual-large-main-entry-isolation/qemu.in_asm.trace`
  在 startup 间接调用后的 trace block 反复执行 `0x7ffffcb8`；
  `.work/ML-014aa-dual-large-main-entry-isolation/m5out/gem5.exec.trace` 在 `0x80000ca8
  @__libc_start_main+100` 的间接 `call` 后执行
  `0x7ffffcb8 @__fini_array_end+3256` 的 `halt`，而
  `.work/ML-014aa-dual-large-main-entry-isolation/gem5.result-focus.txt` 对应记录
  `SIM_END: halt code=0`。
  因此两个 backend 的错误目标均为 `0x7ffffcb8`；这两个 host rc 都不是
  `EXIT_MAIN_ENTRY=73`，也不是双大块成功码 `42`。
- `.work/ML-014aa-dual-large-main-entry-isolation/elf.nm.txt`、
  `.work/ML-014aa-dual-large-main-entry-isolation/main.disassembly.txt` 与
  `.work/ML-014aa-dual-large-main-entry-isolation/runtime-main-entry-focus.txt`
  将 `main` 固定为 `0x80000110`；对 QEMU
  in_asm 和 gem5 Exec trace 检索 `0x80000110`/`@main` 均无命中，且没有
  main-entry marker 或 allocator (`malloc`/`free`/`munmap`) runtime 命中。
  这支持“未证明进入 main”的窄结论，不把 gem5 halt 或 QEMU 130 误报为阶段成功。
- `.work/ML-014aa-dual-large-main-entry-isolation/libc-members-vs-z.rc=0` 且
  `.work/ML-014aa-dual-large-main-entry-isolation/libc-members.txt` 与
  `.work/ML-014z-dual-large-allocation-free-probe/libc-members.txt` 完全相同，
  均为 21 个 members；`.work/ML-014aa-dual-large-main-entry-isolation/locked-hash-cmp.rc=0`、
  `runtime-tools-hash-cmp.rc=0`，并且 aa 与 ML-014z 的 locked/runtime
  before/after sidecar 逐项相同。该证据证明输入与 runtime identity 未漂移，
  不证明控制流正确。ML-014y 的 Accepted 记录只支持单次
  `malloc(131052)`/真实 `free` 的既有边界；ML-014z 的 Needs-isolation 记录
  明确把 startup→main 作为 allocator 前的阻断边界，故本 verdict 不扩大两者结论。
- `.work/ML-014aa-dual-large-main-entry-isolation/startup-layout-comparison.txt`
  与 `.work/ML-014aa-dual-large-main-entry-isolation/relocation-comparison.txt`
  支持把下一边界收口到 startup address materialization，尤其是
  `RELA`/global-page 形态与 `0x80000c84`--`0x80000ca8` 的间接 target 物化。
  这是优先检查方向而非已证根因；下一任务应保持为 minimal ELF/code-layout
  threshold plus relocation decode，在闭合前不进入 malloc/free/mmap/munmap。

**Correction：无。** 本次独立复核未发现需修正的事实或范围声明；上述“未命中
main”和下一边界均按现有 trace/static evidence 的上限表述。
