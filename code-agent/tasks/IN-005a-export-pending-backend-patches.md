# IN-005a: 补齐 codex 阶段遗留的未导出 patch（LLVM×4 + gem5×2 + QEMU×1 dirty commit）

**执行环境**: 本地 subagent

**状态**: 已完成

## 硬约束（务必遵守，违反视为任务失败）

- 本任务**只做导出/提交动作，不改任何实现语义**——所有涉及的改动都已经是真实存在、已通过某种形式 review 的既有代码（LLVM 4 个 commit、gem5 2 个 commit 已经是干净提交；QEMU 1 处是未提交的 dirty 工作区改动）。你的工作是让它们变得**可复现**（正规 `git commit` + `git format-patch` + 更新 `series`），不是重新设计或修改这些改动的内容。
- **QEMU 那一处务必先处理，优先级最高**：`.work/source/qemu` 当前是 dirty 状态（`target/dadao/cpu.c`/`cpu.h` 未提交），对应的 `components/qemu/patches/0019-dadao-cfx-state-scaffold.patch` 是用占位全零 commit hash 手工拼出来的假 patch，不是正规流程产物。在你做任何操作之前，**先用 `git apply --check --reverse components/qemu/patches/0019-dadao-cfx-state-scaffold.patch`（在 `.work/source/qemu` 目录下）确认现有 dirty diff 与该 patch 文件内容完全一致**，确认无误后才能继续（如果对不上，立刻停止报告，不要假设、不要自己去"修正"内容差异）。
- **禁止**对任何 `.work/<component>` 或 `~/DADAO-gem5` 做 `git rebase`/`git am` 重放整条历史/`git reset --hard`/`git checkout .`/`git clean` 之类破坏性操作。只允许普通 `git add` + `git commit`（针对现有 dirty 改动，不产生任何新内容）+ `git format-patch`。
- 完成后必须在任务文件里写「完成区」+ subagent 自审「审阅记录」（含逐条 finding + 判决）。

## 背景

架构师对 2026-07-18~21 期间一个独立运行的 agent（"codex"）接手的 musl malloc+printf 里程碑（ML-014a）后续工作做了一轮独立完整性审计（`docs/reviews/codex-run-integrity-audit-2026-07-21.md`），发现该轮工作虽然产出了几项真实、已通过独立 review 的后端修复，但有 7 处改动从未被正规导出成 `components/<name>/patches/` 里的 patch 文件：

1. **LLVM**（`.work/source/llvm`，series 最后一条对应 commit `f5a06de81358`）：
   - `10690fc4d40d`「[DADAO] Handle external symbols in AsmPrinter」（对应任务 ML-016p，独立 review Accepted）
   - `40bc313742b0`「[DADAO] Map generic inline asm registers」（ML-016q，Audit-accepted-with-findings）
   - `be99e5505abe`「[DADAO] Expand i1 sign extension」（ML-016t，Audit-accepted-with-findings）
   - `d3bd9c15434f`「DADAO: round frame size to ABI alignment」（ML-016y/z，Audit-accepted-with-findings）
   - 这 4 个 commit 依次线性排列在 `f5a06de81358..HEAD`，`.work/source/llvm` 当前工作区干净（`git status --porcelain` 为空）。
2. **gem5**（`~/DADAO-gem5`，series 最后一条对应 commit `6dd0d7c9f1`）：
   - `e6a6b9cdc9`「arch/dadao: back SYS_brk with MemState VMAs」
   - `c7e92c7f80`「arch/dadao: unify SYS_brk base with ELF heap」
   - 这两个 commit 依次排列在 `6dd0d7c9f1..HEAD`，`~/DADAO-gem5` 当前工作区干净。
3. **QEMU**（`.work/source/qemu`，series 最后一条对应 commit `ac58f31`）：
   - 当前 dirty 工作区改动（`target/dadao/cpu.c`+`cpu.h`，CFX state scaffold：`inner_run_mode`/`inner_cfx_code`/`inner_cfx_mask`/`DADAOCfxPowerFrame` 结构体，来自 K1 kernel bring-up 前置任务 KL-102b）从未被 `git commit`，对应的 `components/qemu/patches/0019-dadao-cfx-state-scaffold.patch` 是伪造 hash 的假 patch。**这是唯一有真实数据丢失风险的项**（工作区是唯一权威副本，任何历史操作误触都会永久丢失）。

## 目标

### 第一步：QEMU（最高优先级，先做）

1. 按上面"硬约束"要求先验证 dirty diff 与现有 `0019` patch 一致。
2. `cd .work/source/qemu && git add target/dadao/cpu.c target/dadao/cpu.h && git commit -m "target/dadao: add CFX state scaffold (KL-102b)"`（commit message 可参照 KL-102b 任务文件里的描述调整措辞，不要求逐字照抄）。
3. `git format-patch -1 -o <临时目录>`，生成带真实 commit hash 的新 `0019` patch，**替换**（不是新增）现有的 `components/qemu/patches/0019-dadao-cfx-state-scaffold.patch` 文件内容（文件名保持不变，`series` 里已有这一行不需要改）。
4. 验证：`git -C .work/source/qemu status --porcelain` 现在应该为空（干净）；`diff` 新旧两版 `0019` patch 文件，确认除了 `From <hash>` 行和 commit 元数据之外，实际 diff hunk 内容完全一致（这是"补提交"，不是"改内容"）。

### 第二步：LLVM

1. `cd .work/source/llvm && git format-patch f5a06de81358..HEAD -o <临时目录> --start-number 42`，应该生成 4 个新 patch 文件（`0042`~`0045`）。
2. 把这 4 个文件复制进 `components/llvm/patches/`，在 `components/llvm/patches/series` 末尾按顺序追加这 4 行。
3. 文件命名可以直接用 `git format-patch` 生成的默认名（通常是 commit subject 的 slug 化版本），如果和现有命名风格（`00xx-description.patch`）差异较大，可以手动重命名成风格一致的名字（但必须保留正确的 patch 内容，只改文件名）。

### 第三步：gem5

1. `cd ~/DADAO-gem5 && git format-patch 6dd0d7c9f1..HEAD -o <临时目录> --start-number 13`，应该生成 2 个新 patch 文件（`0013`~`0014`）。
2. 同上，复制进 `components/gem5/patches/`，追加进 `series`。

### 第四步：回归验证（全部三个组件的导出动作完成后统一做一次）

- 全量 `.work/build/llvm/bin/llvm-lit tests/lit/E2E/`：应该保持当前的通过数（本任务不改变任何实现语义，只是把已经在用的代码正式记录下来，理论上零变化）。
- `python3 tools/run_differential.py`：应该与当前实测基线（`AGREE(3-way)=200 gem5-SKIP=2 DIVERGE=0`，`Sail AGREE(4-way)=200`）完全一致——**这就是当前的真实基线，不要求恢复到更早的 `HARNESS=6`**（那是 ML-015c 之前的旧基线，`gem5-SKIP=2` 是已经确认过的、合规的向量订正的副作用，见 `docs/reviews/codex-run-integrity-audit-2026-07-21.md` §2）。
- `python3 scripts/manifest_check.py`/`check_issues.py` 通过。
- **独立验证全部导出 patch 的可重放性**：分别对 llvm/gem5/qemu 做一次"从各自最后一个已知良好 commit 开始，`git am` 依次应用新导出的 patch"的干净重放测试（用临时 clone/worktree，不要在原地操作），确认新 patch 能干净应用且重放后内容与当前 HEAD 完全一致。

## 验收

- `.work/source/qemu`/`.work/source/llvm`/`~/DADAO-gem5` 三者 `git status --porcelain` 均为空（无 dirty）。
- `components/{llvm,qemu,gem5}/patches/series` 分别新增对应行，patch 文件全部来自真实 `git format-patch`（无占位/伪造 hash）。
- 上面"第四步"的全部验证通过。
- `git diff`（主仓库）确认只改了 `components/{llvm,qemu,gem5}/patches/` 相关文件和本任务文件，没有触碰其它任何文件（尤其不碰 `docs/issues.yaml`、其它任务文件、`contracts/`）。

## 参考指针

- `docs/reviews/codex-run-integrity-audit-2026-07-21.md` §1（本任务要解决的问题的完整背景+证据）
- `code-agent/tasks/KL-102b*.md`（QEMU cfx state scaffold 的原始任务，如果存在的话；如果找不到明确文件名，用 `grep -rl "cfx state scaffold\|inner_run_mode" code-agent/tasks/` 定位）
- `docs/reviews/KL-102b-independent-review-20260721.md`（如果存在，读一下确认这段改动的设计意图，避免 commit message 描述有误）
- `components/{llvm,qemu,gem5}/patches/series`（当前状态，追加新行的位置）

---

## 完成区

**状态**：已完成

### 第一步：QEMU（最高优先级）

1. 验证：`cd .work/source/qemu && git apply --check --reverse components/qemu/patches/0019-dadao-cfx-state-scaffold.patch` → exit 0，无输出，反向应用干净。补充做了字节级核对：`git diff --stat` 显示 dirty diff 为 `cpu.c +6 / cpu.h +26`，与旧假 patch 的 hunk 内容逐字节一致（只有 `From <hash>`/`Date` 元数据不同）——**确认一致，未发现任何内容差异**，按任务要求继续执行。
2. `git add target/dadao/cpu.c target/dadao/cpu.h && git commit -m "target/dadao: add CFX state scaffold (KL-102b)\n\n<正文，参照 KL-102b 任务描述>"` → 新真实 commit `f638e620f794b281ebe440b4775044e63bb93543`（父提交 `ac58f31`，即 series 现有 0018 的源 commit）。
3. `git format-patch -1` 生成新 `0019`，**替换**（同文件名）`components/qemu/patches/0019-dadao-cfx-state-scaffold.patch`。新旧两版 diff hunk 逐字节比对：完全一致（唯一差异是 `From <hash>`/`Date` 行 + 末尾一个 cosmetic 空行，这是 `git format-patch` 标准产物特征）。
4. `.work/source/qemu` `git status --porcelain` 现在为空。

### 第二步：LLVM

`git format-patch f5a06de81358..HEAD -o <tmp> --start-number 42` 生成 4 个新 patch（`0042`~`0045`，对应 `10690fc4d40d`/`40bc313742b0`/`be99e5505abe`/`d3bd9c15434f`，oldest-first），复制进 `components/llvm/patches/`，用 `git format-patch` 默认文件名（`0042-DADAO-Handle-external-symbols-in-AsmPrinter.patch` 等，风格与现有命名一致，未改名），追加进 `series`。

### 第三步：gem5

`git -C ~/DADAO-gem5 format-patch 6dd0d7c9f1..HEAD -o <tmp> --start-number 13` 生成 2 个新 patch（`0013`=`e6a6b9cdc9`、`0014`=`c7e92c7f80`），复制进 `components/gem5/patches/`，追加进 `series`。

### 第四步：回归验证（全部完成，逐项实测输出）

- `.work/build/llvm/bin/llvm-lit tests/lit/E2E/`：`Total Discovered Tests: 59 / Passed: 59 (100.00%)`（跑了两次，结果一致，第二次在全部三个组件导出动作+一次并发的 DL-070a 落地之后重跑确认无变化）。
- `python3 tools/run_differential.py`：`AGREE(3-way)=200  AGREE(interp+QEMU, gem5-SKIP)=2  DIVERGE=0  HARNESS=0  QEMU-SKIP=0`；`SAIL 4th column: AGREE(4-way)=200  Sail-SKIP(out-of-slice)=2  SAIL-DIVERGE=0` —— 与任务文件给定基线完全一致，零漂移。
- `python3 scripts/manifest_check.py`：`manifest validation: PASS`。
- `python3 scripts/check_issues.py`：`ISSUE REGISTRY: PASS`（Open: 24 / Closed: 31 / Total: 55）。
- **独立重放验证**（三者均用 `git worktree add <临时目录> <起点 commit>` + `git am` + `git diff <重放后HEAD> <原HEAD>` 校验树内容完全一致，验证后 `git worktree remove --force` 清理，未触碰原目录任何内容）：
  - QEMU：从 `ac58f31` 重放 `0019` → 新 commit 树与 `f638e62`（即 `.work/source/qemu` 当前 HEAD）`git diff` 结果为空。
  - LLVM：从 `f5a06de81358` 依次重放 `0042`~`0045` → 新 HEAD 树与 `d3bd9c15434f` `git diff` 结果为空。
  - gem5：从 `6dd0d7c9f1` 依次重放 `0013`~`0014` → 新 HEAD 树与 `c7e92c7f80` `git diff` 结果为空。
  - 三次重放全部 `git am` 干净应用（无 reject、无 3-way fallback 提示）。

### 修改文件清单（主仓库层面，`git diff --stat` 实测）

```
components/gem5/patches/series                              | 2 ++
components/llvm/patches/series                              | 5 +++++
components/qemu/patches/0019-dadao-cfx-state-scaffold.patch | 5 +++--
```

新增未跟踪文件：
```
components/gem5/patches/0013-arch-dadao-back-SYS_brk-with-MemState-VMAs.patch
components/gem5/patches/0014-arch-dadao-unify-SYS_brk-base-with-ELF-heap.patch
components/llvm/patches/0042-DADAO-Handle-external-symbols-in-AsmPrinter.patch
components/llvm/patches/0043-DADAO-Map-generic-inline-asm-registers.patch
components/llvm/patches/0044-DADAO-Expand-i1-sign-extension.patch
components/llvm/patches/0045-DADAO-round-frame-size-to-ABI-alignment.patch
```

`components/llvm/patches/series` 的 `+5` 行（非 `+4`）和目录下多出的 `0046-dadao-call-defs-rb31-missing.patch` 是**另一个并发 session**（DL-070a 任务，独立于本任务）在本任务执行期间落地的成果，不是本任务产生——详见下方「过程中发现的异常」。

### 验收对照

- `.work/source/qemu`/`.work/source/llvm`/`~/DADAO-gem5` 三者 `git status --porcelain` 均为空 ✓（最终态；过程中 llvm 侧一度短暂因并发 session 而 dirty，见下）。
- `components/{llvm,qemu,gem5}/patches/series` 均新增对应行，patch 文件全部来自真实 `git format-patch`（`From` 行均为真实 40 位 hex hash，无 `0000...` 占位）✓。
- 第四步全部验证通过 ✓（见上）。
- 主仓库 `git diff` 只改了 `components/{llvm,qemu,gem5}/patches/` 相关文件和本任务文件 ✓ —— 另有若干**非本任务产生**的既存未跟踪文件（见下方过程记录），未被本任务触碰或修改。

### 过程中发现的异常（如实记录，非任务失败）

在完成 LLVM 侧重放验证后例行复查时，发现 `.work/source/llvm` 短暂出现一个意料之外的 dirty 文件：`llvm/lib/Target/DADAO/DADAOInstrInfo.td`（修改，非本任务touch）。排查确认：
- 本任务对 LLVM 仅执行了只读的 `git format-patch`/`git log`/`git diff`（比较 commit 对象）+ 隔离的 `git worktree add/am/remove`（在独立临时目录内操作），没有任何命令写入主 `.work/source/llvm` 工作区文件。
- `ps -ef` 确认当时有另一个活跃的 `claude --continue` 进程；`code-agent/tasks/DL-070a-call-defs-rb31-missing.md`（状态：待处理）内容与该 dirty diff 的改动（`CALL_IIII`/`CALL_RRII`/`CALL_PSEUDO_INDIRECT` 的 `Defs` 补 `RB31`）完全对应——判断是**另一个并发 session 正在处理 DL-070a 任务**，与本任务在同一共享 `.work/source/llvm` 目录下并发写入，属于外部并发编辑，不是本任务操作引入。
- 本任务**未触碰**该 dirty 文件（未 add/commit/checkout/clean）。独立 review subagent（见下）复核确认：该并发 session 已自行把这段改动提交为 `b72d02c8a864`（"DL-070a"）并导出为 `components/llvm/patches/0046-dadao-call-defs-rb31-missing.patch`（已追加进 series），使 `.work/source/llvm` 恢复干净——这是**该并发任务自己的正规导出动作**，不是本任务的交付物，本任务对 0046 的内容/正确性不做背书。
- 本任务的 `0042`~`0045` 四个 patch 基于 commit 范围 `f5a06de81358..d3bd9c15434f`（在 `b72d02c8a864` 之前），`format-patch`/重放验证均在该 dirty 文件出现之前或与其操作互不相交的路径上完成，**未受影响、内容仍然正确**（已用重放 + `git diff` 逐树比对确认，见上）。

**建议架构师注意**：`.work/` 目录是跨 session 共享的可变工作区，多个并发 agent 同时操作同一组件目录存在真实的交叉写入风险（本次是良性巧合——两个任务恰好互不冲突的文件范围/commit 范围），但下次可能没这么幸运。是否需要给 `.work/<component>` 引入某种任务级排他锁或调度约束，值得单独讨论（本任务不展开处置，仅如实上报）。

---

## 审阅记录（subagent · 判决 = 通过）

按 DS.md 自审惯例，在完成主体交付后开了一个独立 general-purpose subagent 做代码级复核，subagent 不预设信任上面的完成区叙述，独立重新跑 `git log`/`git show`/`git diff` 等命令核验。

**逐条 finding + 判决**：

| # | 核验点 | subagent 独立结论 | 判决 |
|---|---|---|---|
| A | QEMU `0019` 新 `From` hash 是否真实、hunk 是否与旧假 patch 一致 | 真实 hash `f638e620f794b281ebe440b4775044e63bb93543`；`git diff` 新旧 patch 只有 `From`/`Date` 行不同，hunk（cpu.c+6/cpu.h+26）逐字节一致；`.work/source/qemu` 干净 | ✅ PASS |
| B | LLVM `series` 0042-0045 顺序/hash 是否与 `f5a06de81358..d3bd9c15434f` 提交历史一致；未在 `.work/source/llvm` 执行任何 commit/am/reset/checkout/clean | 顺序、hash 均核对一致（0042=10690fc4d40d…0045=d3bd9c15434f）；subagent 全程只读操作 | ✅ PASS |
| B' | （警示项）`DADAOInstrInfo.td` dirty 文件现状 | 复核时已不再 dirty——已被并发 session 提交为 `b72d02c8a864` 并导出为 `0046`；确认 0042-0045 基于其之前的 commit 范围，不受影响 | ✅ PASS（非本任务范围，如实记录） |
| C | gem5 `series` 0013-0014 顺序/hash 与 `6dd0d7c9f1..HEAD` 一致；`~/DADAO-gem5` 干净 | 顺序、hash 核对一致（0013=e6a6b9cdc9，0014=c7e92c7f80）；工作区干净 | ✅ PASS |
| D | 主仓库 `git diff --stat` 是否只涉及预期文件 | 确认只有 3 个预期文件被修改 + 6 个本任务新增的 patch 文件为 untracked；另有若干**非本任务产生**的既存 untracked 文件（`DL-070a`/`IN-004a`/`ML-014a` 任务文件、audit 报告、`0046` patch），均非本任务触碰，`docs/issues.yaml`/`contracts/` 未被涉及 | ✅ PASS（non-blocking 备注已如实记录） |
| E | 抽查新导出 patch 是否为真实 `git format-patch` 产物（非手工拼接） | 抽查 LLVM `0045`、gem5 `0014`：均有正确 `From <40位hex>`/`Author`/`Date`/`Subject: [PATCH n/N]` 头 + 正常 diff hunk + `-- \n2.43.0` trailer，无手工编辑/截断痕迹 | ✅ PASS |

**未测/边界推敲**：subagent 额外检查了是否有除预期外的破坏性操作痕迹（`git reflog`/`git worktree list` 核对无残留 linked worktree、无非预期新 commit），未发现异常。

**finding 处置**：本轮 subagent 未发现任何 blocking finding；唯一非 blocking 观察（并发 DL-070a 落地产生的 `0046`/series 额外一行）已在完成区「过程中发现的异常」如实记录，不需要本任务处置（不属于本任务 scope，且未对本任务交付物产生负面影响）。

**总判决**：通过。三个组件的 7 处遗留改动已全部正规导出为可 `git am` 复现的真实 patch，QEMU 唯一有数据丢失风险的 dirty 工作区已落地为正规 commit，series 文件已更新，回归验证（E2E/差分/manifest/issues）与既定基线零漂移，独立重放验证三者皆干净通过。

## 架构师复核（ground-truth）

**独立验证方法**：不采信完成区/subagent 判决，从 git 状态开始逐项重跑。

- `git status`（主仓库 + `.work/source/{llvm,qemu}` + `~/DADAO-gem5`）：三个组件工作区均干净；主仓库只有预期的 patch/series 文件改动。
- **独立重建 LLVM 工具链**（`ninja -C .work/build/llvm clang llc lld llvm-objcopy`）：干净构建成功，二进制时间戳晚于 HEAD（`b72d02c8a864`，含 DL-070a 的并发提交），排除"构建产物陈旧"陷阱。
- 全量 `llvm-lit tests/lit/E2E/` → **59/59（100%）**；`python3 tools/run_differential.py` → `AGREE(3-way)=200/gem5-SKIP=2/DIVERGE=0`，`Sail AGREE(4-way)=200/SAIL-DIVERGE=0`——与任务基线完全一致；`manifest_check.py`/`check_issues.py`（Open 24/Closed 31/Total 55）均 PASS。
- **独立验证三个 patch 的真实性**：`grep -m1 "^From " components/{llvm,gem5}/patches/00{42..46,13,14}-*.patch` 确认全部为真实 40 位 hex commit hash（无 `0000...` 占位）。
- **独立复现 QEMU patch 的可重放性**（未复用 subagent 的验证产物，全新 `git clone` + `checkout --detach ac58f31` + `git am 0019-*.patch`）：`am` 干净应用（exit 0），重放后树哈希 `git rev-parse HEAD^{tree}` 与 `.work/source/qemu` 当前 HEAD 树哈希**逐字符相同**（`c8b02787e68dd66cfa0fbace523b19d44697b717`）——这是本任务里唯一有真实数据丢失风险的一项，独立确认修复彻底、patch 内容与实际提交完全对应。
- 关于并发 `DL-070a` 会话在 `.work/source/llvm` 上短暂产生 dirty 文件这件事：确认完成区如实记录、subagent 复核判定非本任务范围产生的问题，且最终未对本任务的 0042-0045 交付物造成任何损坏——**认可"是否需要给 `.work/<component>` 引入任务级排他锁"这个建议值得后续讨论**，但本次是良性巧合，不阻塞本任务验收。

**结论**：**IN-005a 验收通过**——7 处遗留的未导出/伪造 patch 全部转正为可复现的正规 `git format-patch` 产物，最高优先级的 QEMU 数据丢失风险已消除。
