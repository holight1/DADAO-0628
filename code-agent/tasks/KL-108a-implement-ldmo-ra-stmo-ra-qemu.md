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
