# ML-014f：续办 ML-014a——musl malloc + 输出双后端 E2E

**执行环境**：本地 subagent worker

**状态**：阻塞（未完成）

## 背景

ML-014a 原始任务保留为未完成历史记录；其初始阻塞是 QEMU/gem5 的 mmap 返回地址
没有真实 backing，导致 mallocng 的真实 mmap 路径不能作为有效验收。ML-014c、ML-014d
已分别补齐两个后端，ML-014e 将把 backing 判别性 probe 固化。本任务只在这些前置
证据存在后，续办原始 musl 里程碑。

## 目标

在不修改 LLVM/QEMU/gem5 的前提下，新增一个 musl 静态链接 E2E：

- 两个不同大小、足够触发 mallocng 底层 mmap 的分配；
- 对每块内存进行判别性写入、读回和 free；
- 用 `puts`/`fputs` 或仅含整数参数的 printf 输出成功标记，避开已知的变参指针缺口；
- 双后端真实 exit=42，且测试能说明分配大小为何触发 mmap，而不是只凭“跑通”；
- 全量 E2E 从 59/59 保持全绿，四方差分保持 200/200、DIVERGE=0。

## Ownership

- 允许修改：`tests/lit/E2E/musl_malloc_printf.test`、对应 `tests/lit/E2E/Inputs/*`
  测试输入、musl 工作树中为该 E2E 必需的最小文件，以及本任务 MD 的完成/审阅区。
- musl 工作树若有新增提交，必须从当前 HEAD 普通 commit 导出为
  `components/musl/patches/0007-*.patch` 并追加 series；不得重放历史或 reset。
- 不允许修改 LLVM/QEMU/gem5、contracts、manifests、`docs/issues.yaml`、原 ML-014a
  的原始目标文字；不允许借本任务修复 varargs 指针缺口。
- 不得用 `|| true`、忽略 backend 退出码、只跑单一后端或只检查输出文本凑绿。

## 验收

- `llvm-lit -v tests/lit/E2E/musl_malloc_printf.test` 双后端通过，真实 exit=42；
- 任务记录 mallocng 触发 mmap 的尺寸依据和双后端命令/退出码；
- `PATH=.work/build/llvm/bin:$PATH llvm-lit -v tests/lit/E2E` = 59/59；
- `python3 -u tools/run_differential.py` = AGREE(4-way)=200、DIVERGE=0；
- `python3 scripts/manifest_check.py` 与 `python3 scripts/check_issues.py` 通过；
- musl patch series 可在干净 pin checkout 上顺序应用（若本任务无需 musl 改动也要明确记录）。

## 完成区

**状态**：阻塞（未完成；不得标记 Accepted）

- **尝试修改文件（未纳入主线）**：
  - 临时 `tests/lit/E2E/musl_malloc_printf.test` 与
    `tests/lit/E2E/Inputs/musl_malloc_printf.c` 已在阻塞确认后撤下，避免污染
    当前 59/59 基线。
  - musl 工作树已在当前 HEAD 上产生普通候选 commit `8ecf6f6e`，涉及
    `arch/dadao/arch.mak`、`src/malloc/mallocng/free.c`、`src/mman/mmap.c`；未回滚，
    以遵守“不 reset/rebase”约束。候选 patch 未追加到主仓库最终 `series`。

- **mmap 触发依据**：mallocng 的 `MMAP_THRESHOLD` 为 `131052`；测试分配
  `131052` 和 `262144` 字节，均进入 `mallocng/malloc.c` 的
  `n >= MMAP_THRESHOLD` 直接匿名 `mmap` 分支。测试先按 4096 字节步长写入，
  再写三个 sentinel，避免 `262144/2 == 131072` 被步长循环覆盖；随后读回并
  调用真实 `free`。

- **验收结果**：
  - musl 必需对象构建：
    `make -C .work/build/musl obj/src/malloc/mallocng/free.o obj/src/mman/mmap.o V=1`
    → **退出码 0**。
  - `clang` 编译测试输入 → **退出码 0**；重新打包 `libc.a` 并链接 ELF → **退出码 0**。
  - `PATH=.work/build/llvm/bin:$PATH llvm-lit -v tests/lit/E2E/musl_malloc_printf.test`
    → **退出码 1**：QEMU 步骤实际 **130**，因此 lit 未进入其后的 gem5 RUN 行；
    手工运行同一 ELF：QEMU **130**，gem5 **0**，均不是要求的 **42**，输出标记也未验收通过。
  - `python3 scripts/manifest_check.py` → **退出码 0**，`manifest validation: PASS`。
  - `python3 scripts/check_issues.py` → **退出码 0**，`ISSUE REGISTRY: PASS`。
  - 候选 0001—0007 patch series 在 musl `v1.2.5` 干净 pin checkout 顺序 `git am` →
    **退出码 0**；由于 ML-014f runtime 未通过，0007 未进入主仓库最终
    `components/musl/patches/series`。
  - 全量 E2E、differential 未运行：single test 尚未达到双后端 exit=42，继续运行只会
    掩盖当前阻塞，故不宣称 59/59 或 200/200。

- **-O0 / optnone workaround 依据与范围**：在原有 musl `-O2` 构建下，
  `mallocng/free.c` 和 `src/mman/mmap.c` 均触发 DADAO LLVM 后端寄存器分配器的
  “undefined physical register `$rb31`” verifier 崩溃，导致原 `libc.a` 缺少
  `__libc_free`/`__mmap`。0007 不改 syscall、mallocng 算法或任何后端实现：
  `free.c` 的 `free` 与 `mmap.c` 的 `__mmap` 仅加 `optnone` 标注，并在
  `arch/dadao/arch.mak` 追加最终的 `CFLAGS_AUTO += -O0`，使 DADAO musl 构建中
  所有 C 对象采用可复现的 `-O0`（范围是整个 musl DADAO 构建，不只两个对象）。
  这是当前后端缺口的 musl-side build workaround，需后续后端修复后收窄/删除；
  它本身没有解决本轮双后端运行结果不一致。
- **遗留问题**：QEMU exit 130、gem5 exit 0 的运行时差异尚未定位；ML-014f
  保持未完成，不能关闭 `ML-014a`。

## 审阅记录（subagent）

- Finding 1（已修正）：`check_block` 原先先写 sentinel、再做 page-stride 写入；
  第二块 `n/2` 恰为 stride 点。现改为 stride pass 后写 sentinel，并在源文件注释
  固化依据。
- Finding 2（真实阻塞）：`-O2` 构建 `free.c`/`mmap.c` 的命令以退出码 70/2
  失败并报告 undefined `$rb31`；0007 的 `-O0` 构建命令退出码 0，且 patch
  series 可应用，但不能据此宣称运行时通过。
- Finding 3（未解决）：single lit 退出码 1；QEMU 130、gem5 0，目标 42 未达成。
- **判决：Blocked / Not Accepted。** 本轮没有独立 reviewer 复跑；待运行时阻塞
  解决后，必须重新派独立 reviewer 复跑 single、全量 E2E 和 differential。

## 独立 Review（Codex，2026-07-18）

**判决：Blocked / Not Accepted。** 本轮只追加审阅记录，未修改测试输入、musl
patch/series、后端、issues 或其他用户文件；也没有把阻塞状态改成完成。

### 核对结果与 Finding

1. **Finding 0：mallocng mmap 分支依据成立。** 独立查看当前 musl 源码确认
   `src/malloc/mallocng/meta.h` 定义 `MMAP_THRESHOLD` 为 `131052`，
   `src/malloc/mallocng/malloc.c` 在 `n >= MMAP_THRESHOLD` 时直接调用匿名
   `mmap`。测试的 `131052UL` 与 `262144UL` 均满足条件，因此不是普通
   size-class 分配路径。

2. **Finding 0：sentinel 修正成立。** `check_block` 先按 4096 字节步长写入，
   再写 `p[0]`、`p[n/2]`、`p[n-1]` 并立即读回。对第二块而言
   `262144/2 == 131072` 确实是 stride 点，但 sentinel 写在 stride pass 之后，
   不会再被覆盖；两块随后都执行真实 `free`。测试使用 `fputs` 固定参数，未引入
   变参指针路径。

3. **Finding 0：0007 的范围与性质记录准确。** patch 只触及 musl 的
   `arch/dadao/arch.mak`、`mallocng/free.c` 和 `src/mman/mmap.c`：增加 DADAO
   构建的最终 `-O0`，并给 `free`/`__mmap` 加 `optnone`。未改 mmap syscall
   号、mallocng 算法、QEMU/gem5 或 LLVM；因此它是 musl-side 的临时编译兼容
   workaround，不能视为运行时问题已解决。

4. **Finding 1（未解决）：single lit 仍未达到双后端 exit=42。** 独立执行
   `PATH=.work/build/llvm/bin:$PATH llvm-lit -v tests/lit/E2E/musl_malloc_printf.test`
   得到 `1/1 FAIL`；编译、链接和 objcopy 步骤成功，但 QEMU RUN 的
   `test $? -eq 42` 失败，lit 因此没有继续执行其后的 gem5 RUN。对同一生成 ELF
   手工运行确认：

   - QEMU：**exit 130**，stdout/stderr 中没有 `musl-mmap-malloc-ok`；
   - gem5：**exit 0**，输出也没有该标记，halt dump 为
     `rd31=0xffffffffffffffda`（`-38`）且 `SIM_END: halt code=0`。

   这证明当前运行链尚未完成 malloc/free → 输出 → `return 42` 的验收链；现有
   输出可把阻塞定位在成功标记和 exit=42 之前，但不足以在不加诊断代码的情况下
   把根因唯一归到 malloc、free、输出或某一条 exit 链。没有为通过而修改实现。

5. **Finding 0：门禁与 patch series 检查通过，但不能解除运行时阻塞。** 独立
   运行 `scripts/manifest_check.py` 与 `scripts/check_issues.py` 均 exit 0。
   从 musl 当前 pin 的父提交 `b306b16a` 建临时 checkout，按本轮候选
   `components/musl/patches/series + 0007` 顺序应用 0001—0007，应用过程 exit 0，
   临时 checkout 干净；确认后已从主仓库最终 `series` 撤下未验收的 0007。

6. **Finding 2（流程范围）：全量 E2E 与 differential 未宣称通过。** 由于
   single test 的两个后端真实退出码仍不是 42，本轮没有把 `59/59` 或
   `AGREE(4-way)=200/DIVERGE=0` 写成验收结果；任务仍需在运行时阻塞解决后重新
   完整复跑。

**最终结论：Blocked / Not Accepted。**

### 后续状态（ML-014m，2026-07-18）

ML-014m 已修复并集成 linker 的 TLS startup 页差错误；修复后的
`return42`/真实 `mmap` 双后端均为 42，mallocng 已越过原先的 startup
`MALIGN=129`。但 mallocng 的后续路径仍未达到本任务要求的双后端 42：当前
probe 在访问 `0x90001000` 时出现 QEMU/gem5 后端差异（QEMU 13/14，gem5
134），因此 ML-014f 仍为 **Blocked / Not Accepted**，需要另开 allocator/
memory-mapping 诊断后再重开验收。
