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

---

## 完成区（2026-07-25）

**状态**：已完成；实现、执行者自审、首次 findings 修复与独立复审均通过。

### 实现与提交

- live gem5 普通 commit：
  `8c4c73125b357f1c5f7dcbe7fce55a565cba2883`
  （`arch/dadao: implement RA multi load and store`）。
- live 源码只修改 `~/DADAO-gem5/src/arch/dadao/decoder.cc`：
  1 file changed，57 insertions；worktree clean。
- 新增 `RAMultiLoadInst`/`RAMultiStoreInst`：
  - 使用 `RA_BASE + raha + i` 访问 RegRAS bank；
  - 只拒绝 `immu6=0` 和 `raha+immu6>64`，`ra0` 保持合法；
  - 地址操作数分别截成 48 位，逐元素 EA 再按 48 位回绕；
  - 每元素固定 big-endian 64-bit、8-byte alignment；
  - RA 槽位完整 64 位搬移，不 mask/清零/重算高 16 位；
  - 非法 count/range 不登记 RA data operand，避免 O3 rename 在 execute
    返回 ILLI 前消费 bank 外 RegId；
  - 循环按 `i` 递增，每次先完成该元素的源读，再写目的。
- decoder 新增 `0x67`/`0x6F` 分支，字段按 `ha/hb/hc/hd` 解释为
  `raha/rbhb/rdhc/immu6`。
- 新 patch：
  `components/gem5/patches/0017-arch-dadao-implement-RA-multi-load-and-store.patch`
  （87 行），已追加 `components/gem5/patches/series`。
- commit 与 patch 的 stable patch-id 均为
  `45c8e278adbabdc3395e9a81bbaaa66012003540`。

### 验证

1. `scons build/DADAO/gem5.opt -j4`：PASS。最终 live binary SHA-256：
   `f97462386becf6125e723713c7f8a76b03227bd175eddfa8e36cdfe16bbd7c19`。
2. 六个边界向量 before/after：
   - before 使用未修改的 `.work/source/gem5/build/DADAO/gem5.opt`：
     0/6，`immu6=0`、range overflow、data misalign 的
     `ldmo-ra`/`stmo-ra` 全部误走 UNDI `0x83`；
   - after 使用最终 live binary：6/6，四个非法操作数向量精确产生
     ILLI `0x82`，两个未对齐向量精确产生 MALIGN `0x81`。
3. KL-108a 同一份 656-byte raw 指令流
   `.work/evidence/KL-108a-roundtrip.bin`，SHA-256
   `a9eb52e7ef27f2aa5a3b1439ac8f168e3b4e4e889907054f3973dc6cffdd3b7c`：
   - QEMU exit 0；
   - gem5 SE 将相同 raw text 包成 ELF，同时映射 self-modifying guard
     所需的 `0x80001000` 页和 RW 测试数据窗口
     `[0x87FEF000,0x87FF2000)`，exit 0；
   - 测试实际搬移 `0xA5C3123456789ABC` 和
     `0xFFFFFEDCBA987654`，覆盖保存、清空、恢复、写回及高 16 位保真。
4. 额外 RA0 + 48-bit wrap 判别 probe：
   - `ldmo-ra ra0,rb1,rd2,2` 使用
     `(0xFFFFFFFFFFF8 + 0x87FF0008) mod 2^48 = 0x87FF0000`；
   - 随后从 `ra0/ra1` 写回并比较上述两个完整 64 位值；
   - raw SHA-256
     `371f708b3ce3164fe87709ad61af42b3587be4f83f3c60e401976d76b7da617c`；
   - QEMU exit 0，gem5 exit 0。
5. `python3 tools/run_differential.py`：
   - before 与 after 均为 `AGREE(3-way)=200`、
     `AGREE(interp+QEMU, gem5-SKIP)=2`、`DIVERGE=0`；
   - 均为 `AGREE(4-way)=200`、Sail-SKIP=2、`SAIL-DIVERGE=0`；
   - 本任务未擅自修改现有差分向量，基线数字按预期不变。
6. 从 manifest pin
   `c8222cc67a399bfc01e8658dd14b30d5bfd634f9` 在临时 worktree plain
   `git am`：17/17 patch PASS；replay tree 与 live tree 均为
   `91aa0da7345b847935788ec60b1b04d6f515bb8e`。
7. `python3 scripts/manifest_check.py`、`python3 scripts/check_issues.py`、
   源码及根仓库受控文本的 `git diff --check`：PASS。

### KL-102a 已知 `copyRegsFrom` 说明

该项没有阻挡本任务构建。当前 gem5 25.1 的
`src/arch/generic/isa.hh::BaseISA` 已声明 protected 成员
`ThreadContext *tc`，DADAO `ISA::copyRegsFrom()` 使用的是该继承成员，并非当前
源码中的未声明标识符；本轮两次实际增量编译和链接均成功。因此未为此扩大范围
或修改 `isa.cc`。

## 执行者自审：审阅记录

**判决**：首次独立 review 的 High/Low finding 均已接受并修复，等待复审。

- High：初版在非法 range 上仍登记 bank 外 RA operand；已改为
  `if (!illegal)` 后才登记 RA data operands。最终 AtomicSimpleCPU 六项
  fault 仍为 6/6；O3 两个 range probe 均不再宿主 `SIGSEGV`。O3 当前对
  `unimp`、`immu6=0`、MALIGN 等既有 fault 也统一落到 halt 而不交付 fault，
  属于超出本任务的既有 O3 fault-delivery 限制，不再由非法 RegId 触发崩溃。
- Medium：无。
- Low：初版 round-trip 记录遗漏 RW 数据窗口；已补记完整映射
  `[0x87FEF000,0x87FF2000)`。
- 编码、字段、合法性、RA0、48-bit EA、big-endian 64-bit、MALIGN 和逐元素
  顺序均逐项对照 `contracts/isa/spec.md §4.9`。
- 正常 round-trip 与独立 RA0/wrap probe 都在 QEMU 和 gem5 双后端执行，
  不是只凭静态阅读或单后端退出码作结论。
- 未修改 LLVM、QEMU、spec、issues、差分向量或测试框架；根仓库既有未跟踪
  `gcc-torture-results.json` 保持原样。

## 独立 subagent review（2026-07-25）

**Verdict：Changes Required。** AtomicSimpleCPU 下的目标语义和现有验收用例
通过，但 StaticInst 在非法 range 上登记越界 RA operand，可在仓库已提供的
`DADAOO3CPU` 上稳定触发宿主 `SIGSEGV`，因此不能接受当前实现。

### Findings

#### High

1. **`raha+immu6>64` 时仍登记越出 RegRAS bank 的 StaticInst operand，
   在 `DADAOO3CPU` 上导致宿主崩溃，而不是产生 ILLI。**

   - `RAMultiLoadInst` 和 `RAMultiStoreInst` 虽将该编码标记为 `illegal`，
     构造函数仍按 `i < count && i < 63` 填充 operand。以验收向量
     `raha=63, immu6=2` 为例，第二个 operand 是
     `RA_BASE + 63 + 1 = 192`；而 `NumIntRegs=192`，有效 flat index 仅为
     `0..191`。
   - AtomicSimpleCPU 直到 `execute()` 才读取/写入这些 operand，所以当前
     `dadao_se.py` 恰好先走 `if (illegal) RET_ILLI`，掩盖了越界登记。
     O3 rename 在 execute 前消费 StaticInst operand，越界 RegId 因此进入
     rename map。
   - 独立复现使用同一 live binary 和临时 SE 配置，仅将
     `DADAOAtomicSimpleCPU/atomic` 换为仓库已定义的
     `DADAOO3CPU/timing`：
     - `0x67FC1042`（`ldmo-ra ra63,...,2`）：
       process return `-11`，`SIM_END` 缺失，日志为
       `gem5 has encountered a segmentation fault!`；
     - `0x6FFC1042`（`stmo-ra ra63,...,2`）：同样 return `-11` /
       `SIGSEGV`。
   - 这不是 `srcRegs[65]`/`dstRegs[63]` 容量不足：两个数组对合法最大
     count 的容量足够；问题是非法 range 仍创建了 bank 外 RegId。修复时应
     保证 illegal 指令不登记任何越界 RA data operand，再由 execute 返回
     ILLI；本 review 按约束未修改实现。

#### Medium

- 无。

#### Low

1. **正常路径 ELF 映射说明不完整，现有文字不能独立复现。**

   - 完成区称“仅补齐 self-modifying guard 所需的 `0x80001000` 映射”。
     独立按该说明将 raw text 加该映射后，两份测试均在
     `0x87FF0000` 发生 `Page table fault` 并以 `SIGABRT` 退出。
   - 同时映射测试数据窗口
     `[0x87FEF000, 0x87FF2000)` 和 guard 页后，
     `KL-108a-roundtrip.bin`、`KL-109a-ra0-wrap.bin` 才均为
     QEMU exit 0 / gem5 `SIM_END: halt code=0`。实现的正常路径结果成立，
     但任务记录应补全实际 ELF data segment 条件。

### 其余静态核对

- decoder 的 `0x67/0x6F` 与 `ha/hb/hc/hd` 字段对应
  `raha/rbhb/rdhc/immu6`，与 `contracts/isa/spec.md §4.9` 一致。
- 合法性条件没有错误拒绝 `raha=0`；合法路径中的 RA operand index、
  load destination index 和 store `dataStart+i` source index 对应正确。
- RB、RD 各自先 `& MASK48`，每个 EA 再 `& MASK48`；每元素检查
  8-byte alignment。
- `memReadBE`/`memWriteBE` 使用完整 8-byte 值，RA 数据没有 48-bit mask，
  高 16 位保持原样；循环按递增 `i` 每次先读该元素源再写目的。

### 独立执行证据

1. AtomicSimpleCPU 六个 fault 向量：`PASS=6 SKIP=0 FAIL=0`；四个非法操作数
   为 ILLI `0x82`，两个未对齐访问为 MALIGN `0x81`。
2. round-trip 与 RA0/wrap：
   - 两个既有 raw SHA-256 分别为
     `a9eb52e7ef27f2aa5a3b1439ac8f168e3b4e4e889907054f3973dc6cffdd3b7c`
     和
     `371f708b3ce3164fe87709ad61af42b3587be4f83f3c60e401976d76b7da617c`；
   - 补齐上述两个 ELF data segment 后，两份均 QEMU exit 0、gem5 exit 0；
   - RA0 probe 的指令字实为 `0x67001082`/`0x6F003002`，覆盖
     `ra0..ra1`、48-bit wrap 和完整 64-bit 往返。
3. `python3 tools/run_differential.py`：
   `AGREE(3-way)=200`、gem5-SKIP=2、`DIVERGE=0`；
   `AGREE(4-way)=200`、Sail-SKIP=2、`SAIL-DIVERGE=0`。
4. `scons build/DADAO/gem5.opt -j4`：PASS/up to date；binary SHA-256
   `464150af12539556258f5c1b07f4c7faa69842c343aa4cad142599d464c631b0`。
5. commit 与 patch stable patch-id 均为
   `0e016f112d9a9a8e92b3c2ce9c0705d0bfd8f026`；series 中 0017 恰好一条。
6. 从 manifest pin `c8222cc67a399bfc01e8658dd14b30d5bfd634f9`
   plain `git am`：17/17 PASS；replay/live tree 均为
   `9028c1d81e346f6c07dd4cf0027cf4b22dad292b`。
7. `manifest_check.py`、`check_issues.py` 和受控 diff whitespace 检查：
   PASS。
8. KL-102a 更正说明准确：当前 `BaseISA` 确有 protected
   `ThreadContext *tc`，并由 `setThreadContext()` 设置；因此
   `copyRegsFrom()` 中的 `tc` 不是未声明标识符，本轮 build 也未受其阻挡。

本 review 未修改 gem5 源码、patch、series、issues 或其他文档，未 commit。

## 独立 subagent 复审（2026-07-25）

**Verdict：Accepted。** 首次 review 的 High/Low findings 均已关闭；本轮未发现
新的 High、Medium 或 Low finding。

### Findings

- High：无。首次 High 已修复并独立验证关闭。
- Medium：无。
- Low：无。首次 Low 已修复并独立验证关闭。

### 首次 findings 关闭证据

1. **High：非法 range 的 StaticInst operand 越界——Closed。**
   - `RAMultiLoadInst`/`RAMultiStoreInst` 现在仅在 `!illegal` 时登记 RA data
     operands；`immu6=0` 或 `raha+immu6>64` 时只保留始终合法的 RB base
     和可选 RD index operand，不再构造 `RA_BASE+64` 或更大的 RegId。
   - 合法最大边界仍正确：`immu6≤63`，load 最多登记 63 个 destination；
     store 最多为 2 个地址 source 加 63 个 RA source，分别落在
     `dstRegs[63]` 和 `srcRegs[65]` 容量内。
   - 独立以 `DADAOO3CPU/timing` 复跑：
     - `0x67FC1042`（ldmo-ra range overflow）：process 0，
       `crash=False`，`SIM_END: halt code=0`；
     - `0x6FFC1042`（stmo-ra range overflow）：同上。
     两项均不再出现首次 review 的 return `-11`/宿主 `SIGSEGV`。
2. **O3 范围说明——合理且非本任务阻塞项。**
   - O3 下本任务的 count-zero、range-overflow、MALIGN 六个编码均不崩溃，
     但都直接到 `halt code=0`，没有交付架构 fault。
   - 独立控制组中，既有 `addi rd0` 的 ILLI 和 reserved encoding 的 UNDI
     也同样直接 `halt code=0`。因此这是当前 DADAO O3 通用 fault-delivery
     限制，不是 KL-109a RA operand 修复后的特有回归。
   - 本任务正式 SE runner 使用 `DADAOAtomicSimpleCPU/atomic`；复审只据此接受
     本任务的 fault 语义，不将结果扩大为 O3 fault delivery 已实现。
3. **Low：正常路径 ELF 映射记录不完整——Closed。**
   - 完成区已明确同时映射 self-modifying guard 页 `0x80001000` 和 RW
     数据窗口 `[0x87FEF000,0x87FF2000)`，与独立复跑实际条件一致。

### 独立回归证据

1. AtomicSimpleCPU 六个目标 fault：
   `PASS=6 SKIP=0 FAIL=0`；四个 ILLI 均为 `0x82`，两个 MALIGN 均为
   `0x81`。
2. 使用上述完整 ELF 映射复跑：
   - `KL-108a-roundtrip.bin`：QEMU exit 0，gem5 exit 0，
     `SIM_END: halt code=0`；
   - `KL-109a-ra0-wrap.bin`：QEMU exit 0，gem5 exit 0，
     `SIM_END: halt code=0`；
   - 两个 raw SHA-256 与完成区记录一致。
3. `python3 tools/run_differential.py`：
   `AGREE(3-way)=200`、gem5-SKIP=2、`DIVERGE=0`；
   `AGREE(4-way)=200`、Sail-SKIP=2、`SAIL-DIVERGE=0`。
4. `scons build/DADAO/gem5.opt -j4`：PASS/up to date；binary SHA-256
   `f97462386becf6125e723713c7f8a76b03227bd175eddfa8e36cdfe16bbd7c19`。
5. live HEAD 为 `8c4c73125b357f1c5f7dcbe7fce55a565cba2883`，worktree clean；
   commit/patch stable patch-id 均为
   `45c8e278adbabdc3395e9a81bbaaa66012003540`；patch 87 行，series 中
   0017 恰好一条。
6. 从 manifest pin `c8222cc67a399bfc01e8658dd14b30d5bfd634f9`
   plain `git am`：17/17 PASS；replay/live tree 均为
   `91aa0da7345b847935788ec60b1b04d6f515bb8e`。
7. `manifest_check.py`、`check_issues.py`、根仓库受控 diff 和 live gem5
   `git diff --check`：PASS。

本复审未修改 gem5 源码、patch、series、issues 或其他文档，未 commit。
