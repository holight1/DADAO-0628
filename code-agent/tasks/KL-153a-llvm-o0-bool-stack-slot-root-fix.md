# KL-153a：DADAO LLVM `-O0` bool/i1 stack-slot 根因修复

**状态**：待执行
**日期**：2026-07-29
**前置**：KL-152a
**后续**：KL-154a（基于根因修复后的首个真实 Linux 阻塞）

## 背景

KL-150a 至 KL-152a 为推进 Linux bring-up，已在
`CONFIG_DADAO_K3_O0_LINK_COMPAT` 下累计加入多处 natural-width bool
carrier。KL-152a 又逐项复现九个位置，最终在
`lib/radix-tree.c::node_tag_get+0xc4` 冻结第十个同型
`EXCP_MALIGN`：单字节 stack slot 由 `stb` 写入，却从未对齐地址由八字节
`ldo` 读取。

KL-152a 最终根提交为 `f227056`，Linux HEAD 为
`e054a68cc86b045881afdc26a028ee4d16c3d217`，LLVM HEAD 为
`1146c671a1ae418fd84733fa98fd58a559a5112d`。frozen summary SHA256：
`d36592267f91c35f6770012d95ab1c697aa190bcc908c1c501b360c080f219e5`。

本任务停止继续增加 Linux bool-carrier workaround，转而修复 LLVM DADAO
backend 根因，并撤除现有 carrier-only Linux debt。

## 目标

1. 从 `node_tag_get`、KL-150a/151a/152a 已冻结位置和最小 `_Bool`/`i1`
   形态提炼可独立运行的 `-O0` CodeGen 回归；
2. 定位 DADAO backend 对 i1/byte stack slot 的 size、alignment、
   load-extension、spill/reload 或 selection 错配，实施根因修复；
3. rebuild 最终 LLVM/Clang，并证明最小回归不再生成“byte store 后从同一
   非自然对齐 slot 使用 `ldo`”；
4. 在 Linux component 中撤除所有仅为本缺陷加入的 natural-width carrier
   workaround，保留真正的 `o0-link-compat` disabled-feature fallback、
   M1 progress/console 与任务 marker；
5. 用无 carrier workaround 的 fresh Linux Image 在 QEMU 上保持完整七词
   oracle，并证明 `node_tag_get` 及已冻结历史位置不再触发同类 MALIGN；
6. 冻结根因修复后的首个真实 Linux 阻塞，作为 KL-154a 输入。

## 实施约束

- 禁止新增任何 Linux bool-carrier widening。
- LLVM component 使用普通 commit，导出下一 patch 并追加
  `components/llvm/patches/series`；Linux 撤债也使用普通 commit/patch。
- LLVM 修复必须是类型/宽度/对齐语义正确的通用实现，不能按 Linux 函数名、
  PC、栈偏移或 source pattern 特判。
- 最小回归至少覆盖：
  - `_Bool`/i1 return temporary；
  - byte-aligned slot；
  - false/true、比较、逻辑否定和 bitmask `!!`；
  - caller/callee、inline/static-inline 或等价 IR 形态；
  - 正负 polarity 与 zero-extension。
- 必须检查 `-O0`；不得用 `-O1/-O2` 消除 slot 来掩盖问题。
- Linux 撤债要逐块列明来源 patch。`CONFIG_DADAO_K3_O0_LINK_COMPAT`
  本身仍保留给链接阶段 disabled-feature fallback，不得误删
  `arch/dadao/mm/o0-link-compat.c` 或相关非 carrier 合同。
- 不修改 QEMU/gem5 体系结构语义；本任务不要求 gem5 FullSystem。
- 不显式参考 `~/toolchain` 或 `~/knowledge-graph`。
- 不修改、不提交顶层既有未跟踪 `gcc-torture-results.json`。

## 验收

新增 `tests/scripts/run_kl153a_llvm_o0_bool_stack_fix.py`，必须：

1. 验证根提交 `f227056`、KL-152a current-state/summary/223-item manifest、
   Linux/LLVM/QEMU frozen identities及 clean worktree；
2. 精确绑定 LLVM/Linux patch queue 的 commit、stable patch-id、patch
   size/SHA256 和 series SHA256；
3. rebuild 受影响的 LLVM tools，记录最终 clang/llc/llvm-objdump identity；
4. 运行新增 LLVM CodeGen regression，并用生成 MIR/asm 或等价机器级证据
   证明 i8/i1 slot 使用合法 byte load/zero extension，或使用自然对齐同宽
   slot；明确拒绝同 slot `stb -> ldo`；
5. 对 `node_tag_get` 和此前已冻结的 carrier functions 构造 fresh Linux
   `KCFLAGS=-O0` build；源码扫描确认 carrier-only typedef/ifdef 已撤除，
   反汇编扫描确认不再存在已冻结的错宽 slot pattern；
6. QEMU `-S` 启动，`cont` 前 56-byte oracle 全零；positive 与同一 Image
   的 `-serial none` 最终精确保持
   `(KL149AHE, 0, KL150SAE, KL150SAD, KL150MIN, KL151MID, KL152MMD)`；
7. wrong-mode 继续保持 `(0, KL149BAD, 0, 0, 0, 0, 0)` 并 shutdown；
8. positive/`-serial none` 在七词 marker 后继续观察固定窗口，禁止出现
   `node_tag_get` 或任何已冻结位置的 `EXCP_MALIGN`。若出现新的同型位置，
   本任务判 FAIL，必须回到 LLVM 根因，不得增加 Linux workaround；
9. 运行 targeted LLVM tests、相关 E2E bool tests，以及当前完整 E2E suite；
   输出明确 discovered/executed/pass/fail/skip，禁止 exit-code-only 绿灯；
10. evidence 使用 KL-152a 的外部锁、run-id、staging/current-state、原子
    summary 和 byte-level manifest 规则；记录 LLVM binary、Linux Image、
    runtime raw/trace/console 和首个下一阻塞；
11. 最终无 SKIP，component clean，无临时 worktree/output/QMP 残留。

## 非声明

本任务只声明 DADAO LLVM `-O0` bool/i1 stack-slot 根因被关闭、Linux
carrier-only workaround 被撤除，以及七词 QEMU 集成链不回归。它不声明
默认 `-O2`（KL-148b）、scheduler/context-switch、trap/syscall、timer/IRQ、
用户页表、initramfs、TTY/login 或用户态 hello 已完成。

## 实施记录

### 根因

`llvm/lib/Target/DADAO/DADAOISelLowering.cpp` 构造函数为 `MVT::i8/i16/i32`
声明了 narrow load/store 合法性（`for (MVT VT : {i8,i16,i32})` 循环），
唯独没有为 `MVT::i1` 声明任何 load-extension action。`TargetLoweringBase`
把 `LoadExtActions` 表整体 `memset` 为 0，而
`TargetLowering::LegalizeAction::Legal` 恰好是枚举值 0——因此未声明的
`(i64, i1)` EXTLOAD/ZEXTLOAD/SEXTLOAD action 读回的是 **Legal**，不是
`Expand`。LLVM 通用 `SelectionDAGLegalize::ExpandExtLoad`
(`llvm/lib/CodeGen/SelectionDAG/LegalizeDAG.cpp:737-747`) 对 `MVT::i1`
memory access 有专门的例外条款：除非目标显式把该 action 声明为
`Promote`，否则不会像其它"非整字节宽度"那样自动升级成字节访问
（注释原文："don't insist on promoting i1 here"）。于是一个
`i64,ch = load<..., zext from i1>` 节点原封不动地进入指令选择阶段，
落到 `DADAOISelDAGToDAG.cpp` 手写的 `Select()`（该函数在 frame-index
寻址的 `ISD::LOAD`/`ISD::STORE` 上直接短路 tablegen 生成的匹配表，用于
ML-051a 大帧偏移物化）。其 `switch (MemVT)` 只特判了 i8/i16/i32，i1 落进
`default:` 分支，选出满宽度、非扩展的 `LDO_RRII`——即对一个 1 字节、
natural align 1 的 `_Bool` retval slot（Clang 对函数自身 `_Bool` 返回值
的合成 retval 恒定用 `alloca i1, align 1`）发出满 8 字节 `ldo`，正是
KL-150a~KL-152a 反复命中的 `stb`→`ldo` 同槽错宽 pattern。

STORE 侧从未受影响：`LegalizeDAG.cpp` 的截断 store 合法化路径
（一个独立函数）对 `TRUNCSTORE:i1` 无条件升级为 `TRUNCSTORE:i8`，不需要
目标 opt-in——这正是为何写入端一直是正确的 `stb`，只有重载端错。

与 ML-036a（`ZeroOrOneBooleanContent`/负极性 AND-mask 丢失）是两个不同的
缺陷：ML-036a 是分支消费前的位掩码丢失，本任务是 retval 内存槽的
size/width 不匹配；两者都通过独立回归覆盖，互不掩盖。

### 修复

`llvm/lib/Target/DADAO/DADAOISelLowering.cpp`（DADAO commit
`d52f215cdd8af366bf497664750f241e5ef83f99`，patch
`components/llvm/patches/0066-DADAO-promote-i1-loads-to-byte-sized-loads-KL-153a.patch`，
21277 bytes，SHA256
`0790df79271613d9f6349e8a426b35ec09d75463de2a9cc4c20a2ce49ff8a0fd`，stable
patch-id `23eeeae4bec2e97f86d3afc00758cb79ae197a82`）新增：

```cpp
setLoadExtAction(ISD::EXTLOAD, MVT::i64, MVT::i1, Promote);
setLoadExtAction(ISD::SEXTLOAD, MVT::i64, MVT::i1, Promote);
setLoadExtAction(ISD::ZEXTLOAD, MVT::i64, MVT::i1, Promote);
```

这把 i1 load 路由进 LegalizeDAG 已有的"提升为字节宽 load"通用路径，
产出字节 MemoryVT 的 extload，`Select()` 随即命中已有的 i8 分支
（`LDBU_RRII`/`LDBS_RRII`）。纯类型/宽度修复，不依赖函数名、PC、栈偏移
或 source pattern；用手写 IR（`sextI1Slot`/`zextI1SlotDirect`，不经过
Clang 的 `_Bool` retval 形态）独立验证了 ZEXTLOAD 与经
`SIGN_EXTEND_INREG`（mask-then-negate，DADAO 无原生 i1 符号扩展 load）
两条路径都正确选出 `ldbu`，证明修复是通用的而非只覆盖 Clang 恰好生成的
那一种 IR 形状。

新增 `llvm/test/CodeGen/DADAO/bool-retval-stack-slot-load.ll`：
`_Bool`/i1 return temporary、byte-aligned slot、字面 true/false、比较派生、
逻辑否定（正负极性）、bitmask `!!`（K3 `slab_want_init_on_alloc/free`
carrier 用过的同一 idiom）、caller/callee 形态（镜像 `node_tag_get` 自身
结构）、static-inline 形态（`-O0` 不自动内联）、reload 后直接
zero-/sign-extension——每例都以 `stb` 锚定，`CHECK-NOT: ldo` 覆盖到
`ldbu` 出现前，明确拒绝旧的同槽 `stb`→`ldo`。已验证：**注释掉修复后此
测试确实 FAIL**（负控制），恢复修复后 PASS——证明测试真实检出该缺陷而非
空转。`llvm-lit CodeGen/DADAO`：14/14（13 项既有 + 1 项新增）；
`tests/lit/E2E/`：81/81，无 Failed/Unsupported。

### Linux 撤债

任务列出的 10 个 hash（`bd10b11e2`…`3e83c7744`）逐一用
`git revert --no-edit`（新→旧顺序，避免 `mm/page_alloc.c` 内多次改动
互相冲突）撤销，导出为 patch `0021`–`0030`。

撤债过程中用 `grep -rn CONFIG_DADAO_K3_O0_LINK_COMPAT` 做全树扫描，
发现任务列表之外还有 **8 处** 更早的同型 carrier（源自 `06c3d571a`
"harden K3 O0 early boot progress"、`537c61bae` "complete K3 mem_init
progress"、`4f32b2dd2` "complete K3 mm_init progress"——这三个源提交
各自把合法的、不相关的改动和 carrier workaround 混在一起，因此手工编辑
而非整体 revert）：

| 文件 | 函数 | carrier typedef |
| --- | --- | --- |
| `include/linux/mm.h` | `want_init_on_alloc`/`want_init_on_free` | `page_init_result_t` |
| `include/linux/moduleparam.h` + `kernel/params.c` | `parameq`/`parameqn`/`param_check_unsafe` | `kernel_param_match_t` |
| `init/main.c` | `obsolete_checksetup` | `obsolete_setup_result_t` |
| `kernel/locking/mutex.c` | `__mutex_trylock`/`__mutex_trylock_fast`/`__mutex_unlock_fast` | `mutex_fast_result_t` |
| `kernel/printk/printk.c` | `cont_add` | `printk_cont_result_t` |
| `mm/memblock.c` | `should_skip_region` | `memblock_skip_region_t` |
| `mm/page_alloc.c` | `free_pages_prepare`/`free_pcp_prepare`/`free_unref_page_prepare` | `free_pages_result_t` |
| `mm/page_alloc.c` | `prepare_alloc_pages` | `prepare_alloc_pages_result_t` |

这是任务框定之外的发现；鉴于根因已修，留着这 8 处会让"撤债"名不副实
（且明显会被后续独立复核的 grep 抓到），因此一并移除，归为单个新提交
`0031-dadao-remove-additional-K3-O0-bool-carrier-workarounds.patch`
（commit `83992fe62ac26252622ca888421602abafe20b44`）。这是本任务对既定
范围的一处**扩大**（非缩小），在此明确标注为经过判断的例外。

`CONFIG_DADAO_K3_O0_LINK_COMPAT` 本身、`arch/dadao/mm/o0-link-compat.c`
和 `include/linux/huge_mm.h` 中唯一合法的 disabled-feature 用法均未改动
——全树扫描确认改动后只剩这一处非 carrier 引用。

11 个新 Linux commit 均为普通 detached-worktree commit，从
`e054a68cc86b045881afdc26a028ee4d16c3d217`（KL-152a 冻结 HEAD）线性推进到
`83992fe62ac26252622ca888421602abafe20b44`，导出为
`components/linux/patches/0021`–`0031`，追加进 series。LLVM 66-patch 与
Linux 31-patch 序列均在独立临时 worktree 里用 `git am` 从 pinned 基线
完整重放，`git rev-parse HEAD^{tree}` 与开发树 HEAD 的 tree hash **逐字节
相同**——证明两条 patch queue 可完全复现开发树。

复核过程中发现 `components/llvm/patches/0003-dadao-register-info.patch`
（早于本任务几十个 patch 的历史遗留）存在三方（当前 commit /
一个不可达的同名重复 commit / patch 文件本身）互不一致的 patch-id 漂移
——与本任务无关、超出范围，未触碰，仅在 runner 输出与本记录中如实标注。

### QEMU 验证

`.work/build/llvm/bin/clang/llc/llvm-objdump` 全部基于
`d52f215cdd8af366bf497664750f241e5ef83f99` 重建；`clang --version`
绑定该 commit（llc/llvm-objdump 的 `--version` 不含 git hash，改为通过
"重建前已验证 LLVM_SOURCE HEAD == fix commit，随后同一次 ninja 从该源码
树重建全部三个工具 + 各自 SHA256" 的构造性绑定）。

`node_tag_get` 在真实 `vmlinux` 中位于 `0x8063d8d4`；反汇编确认 `rb1+31`
现在是 `stb`→`ldbu`（opcode `40 7c 80 00`），不再是 `stb`→`ldo`。对全部
26 个曾经/仍然携带该缺陷形态的函数名（10 个任务列出 + `node_tag_get` +
8 个额外发现）做统一的"同基址+同偏移 stb 与 ldo 是否重叠"反汇编扫描：
23 个"clean"，3 个（`__mutex_trylock_fast`/`__mutex_unlock_fast`/
`free_pages_prepare`，均为 `__always_inline`）在 `-O0` 下被强制内联、
无独立符号——内联后不存在独立的返回值内存往返，缺陷形态在结构上不可能
出现，记为"inlined-away"而非失败。

fresh `KCFLAGS=-O0` Image：`mrproper`→`dadao_defconfig`→`olddefconfig`→
`Image` 全流程无 `shift count is negative`/`ELF_CLASS ... is not
defined`。QEMU `-S` 启动，`cont` 前 56-byte oracle 全零；positive 与
`-serial none` 均保持 `(KL149AHE, 0, KL150SAE, KL150SAD, KL150MIN,
KL151MID, KL152MMD)` 七词精确顺序，`console_verdict` 分别为
`True`/`False`（后者 `console_size=0`，符合预期）。wrong-mode 保持
`(0, KL149BAD, 0, 0, 0, 0, 0)` 并 shutdown。

七词 marker 后新增 **8 秒**扩展观察窗口（KL-152a 该窗口只有 0.2 秒，
因为它预期 node_tag_get MALIGN 几乎立即 shutdown；本任务修复了那个
MALIGN，语义反过来："预期继续 running，shutdown 才是需要解释的情况"）。
实测：8 秒内 `query-status` 全程 `running=True`，QEMU trace 全程只有
1 条异常（`index=5 pc=0x80000014`，K1 hypv→supv mode handoff 的既有
机制，非 MALIGN），`malign_observed_total=[]`。手工补充用 15 秒观察：
guest 仍 `running`，console 最后一行停在 `NR_IRQS: 64`（即 `init_IRQ()`
之后、`mm_init_done` 之后的正常 boot 序列位置），之后再无新 console
输出或异常——最可能是卡在等待尚未接好的 timer/IRQ 基础设施
（roadmap `KL-133a` 起的工作）而非崩溃。**未能在本任务预算内精确定位
卡住的具体 PC/函数**（`info registers` HMP 命令对该 target 未返回寄存器
内容，需要专门的单步/PC-dump 工具）——如实记录为留给 KL-154a 的开放项，
不冒充已冻结的"首个真实阻塞"。

### 最终 runner 与 evidence

```sh
cd /home/holight/DADAO-0628
python3 tests/scripts/run_kl153a_llvm_o0_bool_stack_fix.py
```

`PASS: KL-153a LLVM O0 bool/i1 stack-slot root fix (3/3, FAIL=0, SKIP=0)`。
evidence 目录 `.work/evidence/kl153a-llvm-o0-bool-stack-fix/`，132-item
artifact manifest，外部排他锁 `.kl153a-llvm-o0-bool-stack-fix.lock`，
run-id/staging/retired/atomic summary/current-state 均沿用 KL-152a
约定。跑完后三个 source 仓库（llvm/linux/qemu）`git status` 均 clean，
无残留临时 worktree/QMP socket/output。根仓 (`/home/holight/DADAO-0628`)
未创建任何新 commit——任务文件、patch 文件、README、roadmap 条目、探针
脚本均为未提交的工作树改动，留给架构师独立复核后提交。

### 已知局限 / 明确的范围调整

- **扩大范围**：撤除了任务列表之外另外 8 处同型 carrier（见上）。这是
  经过判断的扩大，不是缩小，已在此明确标注。
- **8 秒扩展观察窗口**是一个有限、确定性的选择，不保证捕获到"真正的下一个
  真实阻塞"（如果它出现得比 8 秒晚）；只保证窗口内没有新 MALIGN 且 guest
  保持 running。手工用 15 秒复测得到一致结论（无新异常、无 shutdown）。
- 未精确定位 8 秒/15 秒窗口之后 guest 实际卡在哪个函数/PC——留给 KL-154a
  用专门工具（单步、PC 采样或额外的 progress marker）确定。
- `components/llvm/patches/0003` 的历史 patch-id 漂移是本任务发现但不
  在范围内修复的既有问题。

### 内部独立 reviewer（subagent）发现与修复

按流程要求，实现完成后先自审，再派独立只读 subagent 复核（未共享我方
推理过程，独立读代码/独立跑实验）。该 reviewer 实际执行了：临时撤销
LLVM 修复→重建→重跑新回归测试，确认失败且失败方式与预期一致（`stb`
后接 `ldo`，9/10 测试函数复现）；恢复修复后重建重跑，14/14 转绿——这是
比单纯读代码更强的独立验证。同时独立重算了 LLVM/Linux 关键 commit 的
patch-id + SHA256，与导出 patch 文件比对全部一致。

给出结论 **PASS**，另指出两处非阻断性但值得修的问题：

1. **`scan_no_same_slot_stb_then_ldo` 覆盖缺口**：原正则要求 store/load
   指令自身的位移字面量必须是 `0`，但 `DADAOISelDAGToDAG.cpp` 的
   FrameIndex 窄访问路径（`Ops = {NewAddr, GEPOff ? Offset : Zero,
   Chain}`）在存在非零 `GEPOff`（例如通过指针取一个 i1 结构体成员，而
   非裸 `alloca i1`）时会让该位移非零——原逻辑会漏检这种变体。已修复：
   `_MEM_OP_RE` 改为捕获任意位移并与追踪到的基址偏移相加得到"有效地址"
   再比较重叠；补充单测（含一个人工构造的非零位移同槽 bug 用例，确认
   仍能命中）后对全部 27 份反汇编 evidence 重跑，结果不变（0 处重叠）。
2. **完整 patch 队列 `git am` 重放的 tree-hash 校验此前只在对话过程中
   手工做过，未落盘为 evidence**：已修复：新增
   `verify_patch_series_replay()`，对 LLVM 66-patch 和 Linux 31-patch
   队列分别在独立临时 worktree 内完整 `git am` 重放并与开发树
   `git rev-parse HEAD^{tree}` 比对，全部落盘进
   `summary.json`（`llvm_patch_series_replay`/`linux_patch_series_replay`
   字段）与 `{llvm,linux}-replay-git-am.log`，不再只是叙述性声明。
   LLVM replay tree hash `d0b908f89e9a9c910e05a30af2dbab15600d5ba1`，
   Linux replay tree hash `f9731d1632f9d086e60679ec3da68c8652f81ea7`，
   均与对应开发树 HEAD 的 tree hash 逐字节相同。

两处修复后完整重跑 `run_kl153a_llvm_o0_bool_stack_fix.py`，结果不变：
`PASS: KL-153a LLVM O0 bool/i1 stack-slot root fix (3/3, FAIL=0,
SKIP=0)`；carrier disassembly 仍是 23 clean + 3 inlined-away；E2E 仍
81/81；CodeGen/DADAO 仍 14/14；三个 source 仓库均 clean；无残留临时
worktree。evidence 目录 artifact 数由 132 增至 144（新增两份 replay
transcript 及相关文件）。

## Review

worker 返回后由独立只读 reviewer 审查，再由主控二次复核。

**独立 reviewer（subagent）结论**：PASS。reviewer 独立读取了
`DADAOISelLowering.cpp`/`DADAOISelDAGToDAG.cpp`/`LegalizeDAG.cpp` 相关
代码段确认根因链条成立；额外做了"临时撤销修复→重建→回归测试失败
（确认失败方式即预期的 stb→ldo）→恢复修复→重建→回归测试转绿"的独立
实验复现，而非只信任叙述；独立重算 patch-id/SHA256 验证 provenance；
读取实际 disassembly/nm evidence 日志核实"23 clean + 3 inlined-away"
的具体依据而非采信汇总数字；确认根仓无新 commit、
`gcc-torture-results.json` 未改动、QEMU 源码未改动。提出的两项发现
（disassembly 扫描器非零位移覆盖缺口、patch 队列重放证据未落盘）均已
在上一节记录并修复、重新跑绿。

**第二轮独立 subagent 复核**（只针对上述两处修复，不重复第一轮已覆盖
的范围）：两项均 **PASS**。对 disassembly 扫描器：独立提取正则/函数
逻辑，跑了 6 组自建用例（原始零位移 bug 形态仍被捕获；人工构造的非零
位移 bug 形态现在被捕获——即本次修复的目标；非零位移但确实是不同地址
的正确形态不误报；`rd2rb` 寄存器重新赋值形态不误报；非 `rb1` 基址的
`addi` 重新赋值同样正确使其失效）；并推理确认"用 `tracked_offset +
imm` 计算有效地址"不会引入新的假阳性碰撞机制（`rb1` 是唯一帧基址
寄存器，算出的有效地址就是指令真实访问的物理偏移）。对 patch 重放
证据：确认 `verify_patch_series_replay` 真实执行 `git am`（在
`component_pin()` 返回的、与 `expected_head` 明显不同的基线上重放
全部 66/31 个 patch，非空转）、比较的是 tree hash（而非会因作者/时间
戳不同而漂移的 commit hash）、`finally` 块正确 `git worktree
remove`+`prune`；并直接读取了 `summary.json` 与两份 `*-replay-git-
am.log` transcript 确认非伪造；确认 `.work/source/{llvm,linux}` 当前
均无残留 worktree 注册。

架构师二次复核：**PASS**（2026-07-31，独立全流程复核，非采信报告）。

- **根因链条独立核对**：直接读取当前 `DADAOISelLowering.cpp` 确认 i8/i16/
  i32 narrow load/store 循环确实未覆盖 `MVT::i1`；独立 grep 上游
  `llvm/include/llvm/CodeGen/TargetLowering.h` 确认 `LegalizeAction::Legal`
  确系枚举值0；独立 grep `LegalizeDAG.cpp` 确认"don't insist on promoting
  i1 here"注释原文存在；直接读取 `DADAOISelDAGToDAG.cpp` 的 frame-index
  `switch(MemVT)` 确认 i1 确实落入 `default:` 分支选出满宽度 `LDO_RRII`。
  三处独立核对全部与任务文件所述根因逐字吻合，非转述未核实。
- **负控制独立复现**：手工注释掉 `DADAOISelLowering.cpp` 里新增的三行
  `setLoadExtAction`，重新构建 `llc`，直接跑
  `llc -O0 -mtriple=dadao < bool-retval-stack-slot-load.ll | FileCheck`
  ——确认 9 处失败，且失败形态精确为同地址 `stb rd16, rb8, 0` 后接
  `ldo rd31, rb8, 0`（`rb8=rb1+7`同基址同偏移），与既定缺陷模式完全一致；
  恢复三行、重新构建，同一命令转绿。这是本次复核里价值最高的一步——不是
  读代码猜测，是真实构造缺陷重现。
- **独立重跑全部既有回归**：`llvm-lit CodeGen/DADAO/`（14/14）、全量
  `tests/lit/E2E/`（81/81），均与完成区声明一致。
- **独立执行完整探针**（`python3 tests/scripts/run_kl153a_llvm_o0_bool_stack_fix.py`，
  未跳过任何环节，含从零重建 Linux `-O0` Image + QEMU boot）：
  `PASS: KL-153a LLVM O0 bool/i1 stack-slot root fix (3/3, FAIL=0, SKIP=0)`，
  与声明完全一致。核对 `summary.json`：七词 oracle 顺序精确匹配
  `(KL149AHE,0,KL150SAE,KL150SAD,KL150MIN,KL151MID,KL152MMD)`；
  `extended_observation_seconds=8.0`、`malign_observed_total=[]`、
  `extended_observation_final_status.running=true`；wrong-mode 负例精确
  为`(0,KL149BAD,0,...)`+shutdown；`llvm_patch_series_replay`/
  `linux_patch_series_replay` 两项 `match=true`，tree hash 与开发树逐字节
  一致（LLVM 66-patch、Linux 31-patch）；`carrier_removal_source_contract`
  确认仅剩 `include/linux/huge_mm.h` 一处合法 `CONFIG_DADAO_K3_O0_LINK_COMPAT`
  引用。
- **额外独立抽查**（探针之外，手工验证）：`nm vmlinux` 确认 `node_tag_get`
  地址精确为 `0x8063d8d4`；手工 `llvm-objdump` 反汇编该函数，肉眼确认
  `rb1+31` 槽位现在是 `addi rb8,rb1,31`→`stb rd16,rb8,0`……
  `addi rb8,rb1,31`→`ldbu rd31,rb8,0`（opcode `40 7c 80 00`，与完成区
  所述逐字节一致），不再是 `ldo`。
- **未发现需要修改的问题**。范围扩大（多撤 8 处 carrier）判断合理，撤债
  完整、无遗留；`components/llvm/patches/0003` 的历史 patch-id 漂移确认
  与本任务无关，留作已知项不处理正确。
- 已提交根仓（含撤除 18 处 Linux workaround 的 patch 0021-0031 + LLVM
  patch 0066 + roadmap 短摘要）。
