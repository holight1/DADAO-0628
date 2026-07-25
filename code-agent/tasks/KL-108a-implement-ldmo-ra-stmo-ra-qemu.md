# KL-108a：在 QEMU 里实现 `ldmo-ra`/`stmo-ra`（RA bank 整块读写）

**执行环境**：本地（Codex/subagent 均可），只改 `.work/source/qemu`

## 背景

`KL-107a`（已 commit）把 `ldmo-ra`/`stmo-ra` 正式纳入
`contracts/isa/spec.md §4.9`：编码 `0x67`/`0x6F`，格式 `rrri`，8 字节对齐
（MALIGN）、`immu6 ∈ [1,63]` 且 `raha+immu6 ≤ 64`（否则 ILLI）、按 `i` 递增
逐对先读后写、每个 RA 槽位**完整 64 位原样搬移**（`bits[63:48]` 引用计数不
清零/不校验/不特殊处理——这是项目 spec-decision，已获用户 2026-07-25 明确
确认，见 `docs/wiki-deviations.md` 第8条）。

`python3 scripts/check_legality_matrix.py`（ADR-0009 M3 生成式合法性矩阵，
不进 `make check`，只报告不阻塞，但脚本本身 fail-closed）目前对这两条指令
报 6 处 `QEMU-BUG`——因为 QEMU 还没实现这两条指令的译码/派发，遇到它们的
opcode 会走 reserved/UNDI（`0x83`）路径，而不是 spec 现在要求的 ILLI
（`0x82`）/MALIGN（`0x81`）。**这份报告本身就是本任务的验收测试向量清单**
（`multi_immu6_zero`/`multi_range_overflow`/`data_malign` 三类，`ldmo-ra`/
`stmo-ra` 各一组，共 6 个）。

## 目标

1. **QEMU 侧实现**（参照 `ldmo-rb`/`stmo-rb`——即 `.work/source/qemu/target/dadao`
   里现有的 RB bank 整块读写实现，opcode `0x47`/`0x4F`——的译码/翻译/执行
   结构，本任务是它在 RA bank 上的直接类比，不需要发明新机制）：
   - `insn.decode`：新增 `ldmo-ra`（`0x67`）/`stmo-ra`（`0x6F`）的 pattern。
   - `translate.c`：新增对应的 `trans_*` 翻译函数，提取 `raha`/`rbhb`/
     `rdhc`/`immu6` 四个字段。
   - 执行逻辑（`helper.c`/`translate.c`，具体放哪层参照 `ldmo-rb`/`stmo-rb`
     现有实现的分工）：
     - 计算 `immu6` 个元素的有效地址序列：
       `(rbhb[47:0] + rdhc[47:0] + i × 8) mod 2^48`，`i ∈ [0, immu6-1]`。
     - 8 字节对齐检查，不对齐 → **MALIGN**（`0x81`）。
     - `immu6 = 0` 或 `raha + immu6 > 64` → **ILLI**（`0x82`）。
     - 每个槽位整 64 位原样搬移（`ldmo-ra`：内存→`ra[raha+i]`；`stmo-ra`：
       `ra[raha+i]`→内存），按 `i` 递增逐对先读后写。
2. **不要求本任务同时改 gem5/LLVM**——本任务只覆盖 QEMU，gem5 和 LLVM 汇编器/
   反汇编器支持是后续独立任务（不需要本任务预先创建，等这个落地后再拆）。
3. **验证**：
   - `python3 scripts/check_legality_matrix.py`：目标是原先报的 6 个
     `QEMU-BUG` 全部消失（`QEMU-BUG (check-1): 0`）。这个脚本会自己生成
     测试向量并跑 QEMU，不需要额外手写这部分。
   - 正常路径（非 fault）的端到端正确性：脚本本身的合法性矩阵主要覆盖
     "触发 fault 的边界情况"，不直接覆盖"合法调用下数据真的搬对了"这条——
     需要额外用 QEMU（`.work/source/qemu/build/qemu-system-dadao`）手工/
     脚本化验证至少一个正常路径的往返（写一批已知 RA 槽位值→`stmo-ra`→
     清空/覆盖→`ldmo-ra`→读回校验，含验证 `bits[63:48]` 确实原样保留、
     不是被清零或截断），参照本项目已有的类似指令验证方法论
     （`feedback_dadao_test_vector_constraints`：RB expected 值须 48-bit
     截断等既有踩坑记录里的方法，但 RA 这里是全 64 位不做截断，注意区分）。
   - 现有全量差分/回归不应该受影响（这条指令此前是 M1 excluded，从未被
     任何既有测试触达，不应该有任何既有测试因为这个改动而产生新行为）：
     `python3 tools/run_differential.py` AGREE 数与当前基线一致、DIVERGE=0。

## 约束

- **禁止**对 `.work/source/qemu` 做 `git rebase`/`git am` 重放整条历史/
  `git reset --hard`。只允许在当前 HEAD 基础上新增普通 `git commit`。
- 完成后立即导出 patch，追加进 `components/qemu/patches/series`。
- 完成后必须在任务文件里写「完成区」+ 自审「审阅记录」（含逐条 finding +
  判决）。
- 根仓库（DADAO-0628）层面的改动（`gcc-torture-results.json` 之类的产出、
  本任务文件本身）不要求 commit，留给架构师复核，但 `.work/source/qemu`
  内部按硬约束要求是普通 commit。

## 验收

- `python3 scripts/check_legality_matrix.py`：`QEMU-BUG (check-1): 0`
  （针对 `ldmo-ra`/`stmo-ra` 的 6 个单元全部转为 `QEMU[OK]`）。
- 正常路径往返验证（写→读回，含高16位原样保留）有真实、可复现的测试记录
  （不要求是永久性的项目 lit 测试，但要在完成区展示具体命令和输出）。
- `python3 tools/run_differential.py`：AGREE 数与当前基线一致、DIVERGE=0。
- `python3 scripts/manifest_check.py`/`check_issues.py`：PASS。
- QEMU 侧改动用**普通** `git commit` 落地，`git format-patch` 导出对应
  patch，追加进 `series`；独立验证可在干净 pin-commit checkout 上 `git am`
  成功，且 replay tree 与开发树 tree hash 一致。

## 参考指针

- `contracts/isa/spec.md §4.9`（本任务要实现的完整语义定义，权威依据）
- `docs/reviews/kernel-regras-ldmo-stmo-semantics-20260725.md`（KL-106a，
  含 wiki 原文逐条引用）
- `docs/wiki-deviations.md` 第8条（refcount spec-decision 的决策记录+
  用户确认）
- `.work/source/qemu/target/dadao/`（`insn.decode`/`translate.c`/`helper.c`/
  `cpu.c` 里现有 `ldmo-rb`/`stmo-rb`（opcode `0x47`/`0x4F`）实现，本任务
  的直接类比模板）
- `python3 scripts/check_legality_matrix.py`（本任务的主要验收工具，直接
  生成测试向量+跑 QEMU，`docs/reviews`/Makefile 注释里有工具本身的设计
  说明）
- `feedback_dadao_test_vector_constraints`（历史踩坑：RB expected 值需
  48-bit 截断——但本任务 RA 是全64位不截断，两者不同，注意区分不要套错）

---

## 完成区（2026-07-25）

**状态**：已完成；实现、执行者自审与独立 subagent review 均通过。

**QEMU 落地**：

- 普通 commit：
  `b9f412ceaadcb8c07c2289cc7a53589b0ef0fa31`
  （`target/dadao: implement RA multi load and store`）。
- 改动严格限于：
  - `target/dadao/insn.decode`
  - `target/dadao/translate.c`
- 统计：2 files changed，74 insertions。
- patch：
  `components/qemu/patches/0023-target-dadao-implement-RA-multi-load-and-store.patch`
  （116 行），已追加 `components/qemu/patches/series`。
- commit 与 patch 的 stable patch-id 均为
  `290a623b471ef96137719d6586ce581b8040d599`；QEMU worktree clean。

**实现内容**：

- decodetree 新增 `0x67 ldmo_ra`、`0x6F stmo_ra` 两个 `rrri` pattern。
- 翻译器对 `immu6=0` 或 `raha+immu6>64` 生成 ILLI；`ra0` 没有被错误地
  套用 RB 目的寄存器的禁用规则。
- EA 使用 `rbhb[47:0]+rdhc[47:0]+i*8` 并在每步截到 48 位；访存使用
  big-endian 64-bit、8-byte alignment 的 TCG MemOp，因此未对齐走现有
  MALIGN 精确异常路径。
- `ldmo-ra` 直接把完整 64 位内存值写入 `env.ra[]`，`stmo-ra` 直接把
  `env.ra[]` 的完整 64 位写入内存；没有对 `bits[63:48]` 做 mask、清零、
  校验或重算。循环按 `i` 递增，每个元素先读源再写目的。

**验证结果**：

1. 增量构建：
   `ninja -C .work/source/qemu/build qemu-system-dadao` → PASS。
2. 修改前合法性矩阵精确复现 6 个目标缺陷：
   - `immu6=0`：`ldmo-ra`/`stmo-ra` 各 1；
   - `raha+immu6>64`：各 1；
   - data MALIGN：各 1；
   - 均为 expected ILLI/MALIGN、actual UNDI。
3. 修改后 `python3 scripts/check_legality_matrix.py`：
   - 上述 6 项全部 `QEMU[OK]`；
   - `QEMU-BUG (check-1): 0`；
   - `opcodes-漏 (check-2): 0`。
   - 工具仍报告这 6 项 `向量-缺`，按工具合同为非阻塞 backlog，不是
     QEMU 语义失败。
4. 正常路径高 16 位 round-trip：
   - 输入槽值：
     `0xA5C3123456789ABC`、`0xFFFFFEDCBA987654`；
   - 指令序列：
     `ldmo-ra ra10..ra11` → `stmo-ra` 保存 → 从全零区 `ldmo-ra` 覆盖清空
     → 从保存区 `ldmo-ra` 恢复 → `stmo-ra` 写到输出区；
   - 客体随后用普通 `ldo` 比较保存区和输出区的两个完整 64 位值；
   - `.work/evidence/KL-108a-roundtrip.bin` SHA-256
     `a9eb52e7ef27f2aa5a3b1439ac8f168e3b4e4e889907054f3973dc6cffdd3b7c`；
   - QEMU exit = **0**。两个值的高 16 位分别为 `0xA5C3`、`0xFFFF`，
     证明未被截断或清零。
5. `python3 tools/run_differential.py`：
   - `AGREE(3-way)=200`，gem5-SKIP=2，`DIVERGE=0`；
   - `AGREE(4-way)=200`，Sail-SKIP=2，`SAIL-DIVERGE=0`。
6. patch series 独立 replay：
   - manifest QEMU pin `385b0a7d9785c8f3ac7b116d7f31d61502b55183`
     （peel 后 commit `7c949c53e936...`）；
   - plain `git am` 依次应用 23/23 patch，全部成功；
   - replay tree 与开发树 tree 均为
     `04f99adc5c46feeaf379930fc706105742cab049`；
   - 临时 worktree 已清理。
7. `manifest_check.py`、`check_issues.py`、`git diff --check`：PASS。

## 执行者自审：审阅记录

**判决**：自审通过，未发现阻塞 finding。

- 编码与字段：`0x67/0x6F` 及 `ha/hb/hc/hd` 与
  `contracts/isa/spec.md §4.9` 一致。
- 合法性：RA bank 允许 `ra0`，只检查 count 非零和 bank 上界；未复制
  `ldmo-rb/stmo-rb` 的 `rb0` 禁止条件。
- 地址与端序：RB/RD 地址操作数先各自截成 48 位，求和及逐元素偏移后仍按
  48 位回绕；访存使用 `MO_BE|MO_[UQ/64]|MO_ALIGN_8`。
- 数据保真：RA 读写路径没有任何 48 位 mask，正常路径用两个非零 refcount
  高位值实际验证。
- 范围：未修改 gem5、LLVM、helper/cpu 状态模型、根仓库测试框架或 issues；
  未做 rebase/reset/am 开发树历史。`git am` 仅发生在独立临时 worktree。

## 独立 subagent review（2026-07-25）

**Verdict：Accepted。**

### Findings

- High：无。
- Medium：无。
- Low：无。

### 独立静态核对

- `contracts/isa/spec.md §4.9` 与 QEMU decode/translate 一致：
  `ldmo-ra=0x67`、`stmo-ra=0x6F`；`@rrri` 将 `ha/hb/hc/hd`
  分别解为 `raha/rbhb/rdhc/immu6`。
- 合法性判断仅拒绝 `immu6=0` 和 `raha+immu6>64`，未错误拒绝
  `raha=0`，因此 `ra0` 合法。
- EA 先分别截取 `rbhb[47:0]`、`rdhc[47:0]`，基址求和及每个
  `i*8` 偏移后均再次截为 48 位。
- load/store 分别使用 `MO_BE|MO_UQ|MO_ALIGN_8` 和
  `MO_BE|MO_64|MO_ALIGN_8`，满足大端、完整 64 位和 8-byte MALIGN；
  RA 路径没有 48 位数据 mask，`bits[63:48]` 原样保留。
- 两个循环均按 `i=0..immu6-1` 展开；每次先从该元素的源读取，再写入
  目的，符合逐对先读后写语义。

### 独立执行记录

1. `python3 scripts/check_legality_matrix.py`
   - exit 0；
   - `ldmo-ra`/`stmo-ra` 的 `immu6=0`、range overflow、data MALIGN
     六项均为 `QEMU[OK]`；
   - 汇总 `matrix cells=143`、`QEMU-BUG=0`、`opcodes-漏=0`、
     `向量-缺=110`。后者含本任务六项，按脚本合同为非阻塞 backlog，
     与完成区声明一致。
2. 独立生成 316-byte 判别 probe：
   - 指令字 `ldmo-ra=0x670020C2`、`stmo-ra=0x6F004142`；
   - 从 `ra0` 开始搬运两个值
     `0xA5C3123456789ABC`、`0xFFFFFEDCBA987654`；
   - load EA 使用
     `(0x0000FFFFFFFFFFF8 + 0x0000000080002008) mod 2^48
     = 0x80002000`，同时覆盖 `ra0` 合法、48-bit wrap、高 16 位保真和
     `i` 顺序；
   - probe SHA-256
     `b413361a5a1255285b34fefcd2c6eb7abd03e481a5dddff5fd63bc24ae0e8138`，
     QEMU exit 0。
3. 复跑已有 roundtrip：
   - `.work/evidence/KL-108a-roundtrip.bin` SHA-256
     `a9eb52e7ef27f2aa5a3b1439ac8f168e3b4e4e889907054f3973dc6cffdd3b7c`；
   - QEMU exit 0。
4. `python3 tools/run_differential.py`
   - `AGREE(3-way)=200`、gem5-SKIP=2、`DIVERGE=0`；
   - `AGREE(4-way)=200`、Sail-SKIP=2、`SAIL-DIVERGE=0`。
5. `ninja -C .work/source/qemu/build qemu-system-dadao`：PASS（4/4）。
6. 组件与 patch 身份：
   - QEMU HEAD 为
     `b9f412ceaadcb8c07c2289cc7a53589b0ef0fa31`，worktree clean；
   - commit 统计确为 2 files、74 insertions；
   - patch 116 行，series 中恰好一条；
   - commit/patch stable patch-id 均为
     `290a623b471ef96137719d6586ce581b8040d599`。
7. 从 manifest pin
   `385b0a7d9785c8f3ac7b116d7f31d61502b55183`
   （peel `7c949c53e936aa3a658d84ab53bae5cadaa5d59c`）在临时 clone 中执行
   plain `git am`：23/23 PASS；replay tree 与开发树均为
   `04f99adc5c46feeaf379930fc706105742cab049`。
8. `python3 scripts/manifest_check.py`、`python3 scripts/check_issues.py`、
   `git diff --check`：PASS。

审阅未修改 QEMU 源码、patch、series、issues 或其他文档；未启动 nested
subagent，未 commit。
