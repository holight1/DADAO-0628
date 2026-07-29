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

worker 完成后填写。

## Review

worker 返回后由独立只读 reviewer 审查，再由主控二次复核。
