# KL-109a：在 gem5 里实现 `ldmo-ra`/`stmo-ra`（RA bank 整块读写）

**执行环境**：本地（Codex/subagent 均可），只改 gem5 相关 patch（`components/gem5/patches/`）

## 背景

`KL-108a`（已 commit，`b9f412c`）在 QEMU 里实现了 `ldmo-ra`/`stmo-ra`
（`contracts/isa/spec.md §4.9`：编码 `0x67`/`0x6F`，格式 `rrri`，8字节对齐
MALIGN、`immu6∈[1,63]`且`raha+immu6≤64`否则ILLI、按`i`递增逐对先读后写、
每槽位完整64位原样搬移不做refcount特殊处理）。本任务是同一功能在 gem5 上的
对应实现，让这两条指令在双后端都可用——K1 后续的裸机差分验证（`run_differential.py`
的 QEMU/gem5/interp/Sail 四方比对）需要 gem5 侧也支持这两条指令才能纳入。

gem5 已有 RB bank 的整块读写实现（`ldmo-rb`/`stmo-rb`，opcode `0x47`/`0x4F`）
可以直接类比：`components/gem5/patches/0005-dadao-memory.patch` 里的
`MultiLoadInst`/`MultiStoreInst` 两个 `StaticInst` 子类，`decoder.cc` 里
对应的 dispatch 分支 `return StaticInstPtr(new MultiLoadInst(ha(w), hb(w),
hc(w), hd(w), 8, false, ...))`。RA bank 版本需要同样的类结构，但寄存器堆
换成 RA（`env.ra[]`/gem5 对应的 RA 寄存器文件，具体类名参照现有 gem5 skeleton
里 RA 相关寄存器定义）。

## 目标

1. **gem5 侧实现**：
   - `decoder.cc`：新增 `0x67`/`0x6F` 的解码分支，构造对应的 `StaticInst`。
   - 新增 `RAMultiLoadInst`/`RAMultiStoreInst`（或复用/扩展现有
     `MultiLoadInst`/`MultiStoreInst` 让它们能参数化目标 bank 为 RA——
     具体选哪种方式自行判断哪个改动面更小，两者都可以接受）。
   - 语义：EA = `(rbhb[47:0] + rdhc[47:0] + i×8) mod 2^48`，`i∈[0,immu6-1]`；
     8字节对齐（不对齐 → MALIGN）；`immu6=0` 或 `raha+immu6>64` → ILLI；
     每个 RA 槽位完整64位原样搬移，不对 `bits[63:48]` 做任何特殊处理；
     按 `i` 递增逐对先读源后写目的。
2. **不要求同时改 LLVM**——LLVM MC 汇编器/反汇编器支持是后续独立任务。
3. **验证**：
   - QEMU 那边已经有 `check_legality_matrix.py` 自动生成的判别性向量
     （`multi_immu6_zero`/`multi_range_overflow`/`data_malign` 各一对）。
     gem5 没有等价的自动化工具，需要手工构造对应的向量（可以直接照抄
     QEMU 那边验证时用的 `.work/evidence/KL-108a-*` 系列产物的指令序列/
     期望结果，改成跑在 gem5 SE 上），确认 gem5 对这三类边界情况产生
     一致的 fault/正确结果（ILLI/MALIGN 的具体退出码约定参照
     `contracts/isa/spec.md`/`docs/reviews/`已有的 QEMU/gem5 一致性惯例）。
   - **正常路径 QEMU/gem5 双后端一致性**：构造一个不触发任何 fault 的
     真实往返测试（写一批已知 RA 槽位值→`stmo-ra`→清空/覆盖→`ldmo-ra`→
     读回校验，含验证 `bits[63:48]` 原样保留），同一份指令序列分别在
     QEMU 和 gem5 上跑，确认两边输出完全一致——直接复用/改造 `KL-108a`
     完成区里那份 round-trip 测试的指令序列（5条指令：ldmo-ra保存→
     stmo-ra→ldmo-ra清空→ldmo-ra恢复→stmo-ra写出）即可，不需要重新设计。
   - `python3 tools/run_differential.py`：确认这条改动没有让既有 200/202
     AGREE 的基线发生变化（这条指令此前双后端都不支持，不在现有差分向量
     集合里，所以预期这个数字本身不变；如果本任务顺便把新指令加进了差分
     向量集合，需要新增的 AGREE 数量如实报告，不要和现有基线混为一谈）。

## 约束

- gem5 组件的改动方式：本项目对 gem5 采用 patch series 管理
  （`components/gem5/patches/`），不是直接改 `~/DADAO-gem5` 工作树后
  commit——参照现有 `0005-dadao-memory.patch` 等文件的组织方式，新增
  patch 文件（不要改写已有 patch 文件的历史内容）。
- `~/DADAO-gem5` 如果需要在其工作树里实际构建验证，正常 `git commit`
  该工作树本身（不要 rebase/reset --hard），验证完成后把改动 diff 导出成
  新的 patch 文件放进 `components/gem5/patches/`，两者都要有。
- `KL-102a`（`docs/reviews/kernel-cfx-state-patch-surface-20260721.md`）
  提到 gem5 现有 patch 链本身有个已知问题（`ISA::copyRegsFrom()` 用了
  未声明的 `tc` 变量）——如果这个问题真的会阻挡本任务的构建，如实报告
  并说明是否需要先处理它，不要绕过去假装没这回事；如果它不在本任务实际
  触及的代码路径上，如实说明为什么不受影响。
- 完成后必须在任务文件里写「完成区」+ 自审「审阅记录」（含逐条 finding +
  判决）。

## 验收

- 手工构造的三类边界向量（`immu6=0`/越界/未对齐）在 gem5 上产生与
  `contracts/isa/spec.md §4.9` 一致的 fault（ILLI/MALIGN）。
- 正常路径往返测试在 QEMU 和 gem5 上产生完全一致的结果（含高16位保真）。
- `python3 tools/run_differential.py`：如实报告改动前后的 AGREE 数变化
  （预期不变，除非本任务顺带把新指令纳入差分向量集合）。
- `python3 scripts/manifest_check.py`/`check_issues.py`：PASS。
- gem5 侧改动：新 patch 文件 + `components/gem5/patches/series` 更新；
  如果在 `~/DADAO-gem5` 工作树做了验证性 commit，独立验证可在干净状态
  下重新应用 patch series 复现同样的构建结果。

## 参考指针

- `code-agent/tasks/KL-108a-implement-ldmo-ra-stmo-ra-qemu.md` 完成区
  （QEMU 实现+验证方法论，本任务的直接类比模板；round-trip 测试指令
  序列可以直接复用）
- `contracts/isa/spec.md §4.9`（权威语义定义）
- `components/gem5/patches/0005-dadao-memory.patch`（`MultiLoadInst`/
  `MultiStoreInst` 现有实现，RB bank 版本的直接模板）
- `docs/reviews/kernel-cfx-state-patch-surface-20260721.md`（KL-102a，
  gem5 现有 patch 链已知问题的记录，包括 `copyRegsFrom` 的 `tc` 未声明
  问题）
- `~/DADAO-gem5/src/arch/dadao/decoder.cc`（当前 gem5 工作树，已应用
  的 patch 链结果，dispatch 逻辑现状）
