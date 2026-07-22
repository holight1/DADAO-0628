# IN-004a: codex 30+ 任务运行(ML-014aa~af/ML-016a~z/ML-017a~d)的完整性审计

**执行环境**: 本地 subagent（纯审计/调研，禁止修改除本报告外的任何仓库文件）

**状态**: 已完成（纯审计，见 `docs/reviews/codex-run-integrity-audit-2026-07-21.md`）

## 硬约束（务必遵守，违反视为任务失败）

- **纯审计任务，只允许新增一份报告文件**（`docs/reviews/codex-run-integrity-audit-2026-07-21.md` 或类似命名）+ 在本任务文件里写「完成区」。**不允许修改任何其它文件**（不改 patch 文件、不改 series、不 commit 到任何 `.work/<component>`、不碰 `~/DADAO-gem5`、不改 `docs/issues.yaml`/`docs/issues-archive.yaml`、不动任何任务文件）。
- 允许**只读**地探查 `.work/source/{llvm,qemu,musl}`（注意：仓库里实际路径是 `.work/llvm`、`.work/source/qemu`、`.work/source/musl` ——先用 `ls .work/ .work/source/` 确认准确路径，不要假设）、`~/DADAO-gem5`（gem5 实际工作副本，不是 `.work/source/gem5`——那是一个未被任何脚本引用的孤立目录，本任务可以顺带确认一下这一点但不用深究）。
- 完成后必须在任务文件里写「完成区」+ subagent 自审「审阅记录」（审计类任务自审重点是"每条结论有没有具体命令输出佐证"，不是代码 review）。

## 背景

架构师（你的上级）在 2026-07-18 到 2026-07-21 期间，一个独立运行的 agent（内部代号"codex"）接手了 musl 第二个 E2E 里程碑（原 ML-014a：malloc+printf）的后续工作，并自行衍生出 ML-014aa~af、ML-014r~z、ML-016a~z、ML-017a~c 加最终 handoff ML-017d，累计 60+ 个任务文件。架构师读了 git log 和最终交接文档 `docs/reviews/ML-017d-final-handoff-roadmap-20260721.md` 后，做了一轮抽查式独立核实，发现了若干需要系统性审计的疑点。你的任务是把这些疑点逐一坐实（或推翻），并系统性扫描是否还有同类问题被遗漏。

**架构师已经独立核实、你需要在此基础上做完整/系统性核对（不是重新发现，是扩大覆盖面+交叉验证）的具体疑点**：

1. **可复现性缺口（最高优先级）**：以下 commit 存在于对应组件的活 git 历史里，但架构师抽查未在 `components/<name>/patches/` 里找到对应的、通过 `git format-patch` 正常导出的 patch 文件，`series` 里也没有对应条目：
   - `.work/llvm`：`10690fc4d40d`（AsmPrinter external symbol）、`40bc313742b0`（inline asm 寄存器约束）、`be99e5505abe`（i1 sign extension expand）、`d3bd9c15434f`（frame 对齐/round frame size to ABI alignment）。
   - `~/DADAO-gem5`：`e6a6b9cdc9`（back SYS_brk with MemState VMAs）、`c7e92c7f80`（unify SYS_brk base with ELF heap）。
   - `.work/source/qemu`：当前工作区**处于 dirty 状态**（`git -C .work/source/qemu status --porcelain` 会显示 `target/dadao/cpu.c`/`cpu.h` 有未提交改动），对应的 `components/qemu/patches/0019-dadao-cfx-state-scaffold.patch` 文件本身用的是占位 commit hash（`From 0000000000000000000000000000000000000000`），不是从真实 `git commit` 用 `git format-patch` 导出的——意味着这段改动从未被真正提交进 `.work/source/qemu` 的 git 历史。

   **你需要做的**：
   a. 逐个组件（llvm/qemu/gem5/musl）完整枚举"最后一个已导出 patch 对应的 commit"之后、到当前 HEAD（含 dirty 工作区改动）之间的**全部**新增 commit/改动，不要只核对架构师列出的这几个，可能还有遗漏的。
   b. 对每一个未导出的改动，判断：这个改动本身是否是真实、有效的修复（读 diff 内容+相关任务文件+相关 review 文档判断），还是应该被丢弃的实验性/失败尝试。
   c. 如果是真实有效的修复，明确写出"需要执行 `git commit`+`git format-patch`+更新 series 才能让这个改动可复现"这个结论，并列出具体需要执行的命令（不要自己执行，这是审计任务不是修复任务）。
   d. 特别检查 `.work/source/qemu` 的 dirty 工作区：这段 cfx state scaffold 改动如果丢失（比如被误 `git checkout` 或 `git clean`）是否可以从 `0019-dadao-cfx-state-scaffold.patch` 完整恢复（用 `git apply --check` 或类似方式验证，不要真的执行会改变工作区状态的命令，除非你确认操作可逆且会在验证后还原）。

2. **四方差分基线偏移**：本 session 全程稳定的基线是 `AGREE(3-way)=200 DIVERGE=0 HARNESS=6`（interp/QEMU/gem5 三方，Sail 第四方 `AGREE(4-way)=200`）。架构师刚才独立跑了一次 `python3 tools/run_differential.py`，结果变成了 `AGREE(3-way)=200 gem5-SKIP=2 HARNESS=0`（总覆盖 202，而非 200）。
   - 找出这个变化是哪个任务引入的（搜索 git log 里改动 `tests/vectors/isa/*.yaml`、`tools/run_differential.py`、`tools/validate_interp.py` 或相关 harness 脚本的提交）。
   - 确认这是"新增了 2 条向量、gem5 暂不覆盖是预期内的、有没有被记录进某个 issue 或任务文件里说明"，还是一次未被恰当评审/记录的、可能掩盖了真实分歧的改动。
   - 明确回答：这个偏移是否符合本项目一贯的"四方差分基线不能在非语义相关任务里发生变化"的验收标准？如果不符合，是哪个任务违反的。

3. **puts/stdout 阻塞现状复核**：`ML-017d` 声称 high-level `puts` 在两个后端都没有输出 marker，`errno` 诊断显示非零。请你独立重新验证这个结论目前是否依然成立（用 handoff 文档里提到的 targeted probe，或者你认为更直接的验证方式），不要只采信文档转述。如果你重新验证后发现结论已经过时（比如某个后续任务其实已经解决了但没更新 handoff），如实报告。

4. **musl 侧候选 patch（ML-014f）现状**：`.work/source/musl` 当前 HEAD 是 `4741d4d1`（"make mallocng public entry point extractable"），领先于 `components/musl/patches/series` 最后一条已导出 patch（`0006`，对应 commit `5fb13ddb`）两个 commit（`8ecf6f6e` + `4741d4d1`）。`ML-014a` 任务文件的"续办记录"部分提到 ML-014f 生成过一个"候选 0007 patch"但因为验收未通过（QEMU/gem5 双后端都没有达到 exit=42）而"不能当作验收通过"。请确认：这两个未导出的 musl commit 具体是什么内容（是否就是那个"候选 patch"对应的改动，还是又有新的改动）、当前是否应该保留在 `.work/source/musl` 的工作树里（如果最终不采用，是否应该考虑撤销回到 `5fb13ddb`，还是保留以便未来任务复用其中的诊断产出）——只分析给出建议，不要自己执行任何撤销操作。

5. **任务文件卫生问题**：
   - `code-agent/tasks/ML-016w-malign-runtime-consistency-audit-20260721.md`（278 字节，是指向 `ML-016w-malign-runtime-consistency-audit.md` 的别名 stub）与 `ML-016w-malign-runtime-consistency-audit.md`（7.1K，真正内容）并存——确认这是否是唯一一处这类"重复/别名"任务文件，扫描全部 `code-agent/tasks/ML-01[4-7]*` 文件是否还有类似情况（同一个任务编号对应两个不同文件名、内容却不一致或互相矛盾的情况）。
   - 确认 ML-014 系列里 `ML-014aa`/`ML-014ab`/.../`ML-014af` 这类"字母叠字母"命名是否有跟"合理的任务编号规则"冲突的具体问题（比如排序歧义、和其它已有任务编号疑似冲突），如果只是风格不规范但无实质歧义/冲突，如实说明"只是风格问题，无功能性影响"，不要夸大。
   - 检查若干任务文件里提到的"证据存放在 `/tmp/ml-0xxx-.../`"这类路径——这些临时目录大概率已经不存在（容器/session 重启后 `/tmp` 内容通常不持久），确认是否属实，如果属实，这意味着这些任务的"证据"事实上已经无法复核，只能依赖任务文件里转述的文字描述——如实指出这是一个证据链持久性风险（不是说任务本身的结论就一定是假的，是说"如果以后想重新核实，会发现原始证据已经不在了"）。

6. **开放式扫描**：除了以上 5 点，请你自己再系统性过一遍 ML-014aa~af/ML-016a~z/ML-017a~d 全部任务文件（至少读每个文件的"完成区"和"审阅记录"部分，不需要逐字读全文），看看有没有其它同类性质的问题（比如：声称"独立 review"但 reviewer 和 worker 明显是同一个 agent 自我复核、验收标准被中途放宽却没有明确记录原因、`patch`/`series`/`git commit` 步骤被跳过的其它实例）。如实报告发现，不要为了"审计报告看起来完整"而牵强附会小题大做。

## 产出要求

一份结构清晰的报告，按照上面 1-6 的顺序组织，每一条结论都要有具体命令输出/文件路径/行号作为证据（不能是"我觉得/大概"）。报告末尾给出一个**分级处置建议清单**：
- **必须立即处理**（会导致真实数据丢失风险或已经违反项目核心承诺的）
- **应该处理但不紧急**（工程债务，不会立即导致数据丢失）
- **无需处理**（虚惊一场/风格问题不影响功能）

## 参考指针

- `docs/reviews/ML-017d-final-handoff-roadmap-20260721.md`（最终交接文档，本次审计的起点）
- `docs/reviews/ML-017d-independent-review-20260721.md`（对应的独立 review，如果存在的话读一下，看看它有没有已经覆盖上面某些疑点）
- `docs/adr/0002-build-orchestration.md`（component-lock + patch-series 机制的原始设计文档，理解"为什么这套机制存在"有助于判断偏离有多严重）
- `~/.claude/projects/-home-holight/memory/feedback_subagent_scope_drift_git_history.md`（本 session 更早发生过的一次类似事故——patch 历史与 `.work/<component>` 实际状态脱节——可以类比参照，但注意这次的性质不完全相同：那次是历史被破坏性重写，这次是新改动没有被导出，两者都破坏可复现性但机制不同）
- `code-agent/tasks/ML-014a-musl-e2e-malloc-printf.md`（原始任务+续办记录）
- `components/{llvm,qemu,gem5,musl}/patches/series`（各组件当前已导出的 patch 清单，逐一对照 git log）

## 完成区

**状态**：已完成。产出报告：`docs/reviews/codex-run-integrity-audit-2026-07-21.md`。

- 全程只读，未修改 patch/series/`.work/<component>`/`~/DADAO-gem5`/
  `docs/issues.yaml`/`docs/issues-archive.yaml`/任何其它任务文件。
- 6 个调研点逐条坐实/推翻，均附具体命令输出（`git log`/`git show --stat`/
  `git apply --check --reverse`/`python3 tools/run_differential.py` 实测/
  独立小脚本重跑 gem5 单条 vector/直接读 `/tmp` 原始产物）。
- 关键发现：
  1. LLVM 4 个（`10690fc4d40d`/`40bc313742b0`/`be99e5505abe`/`d3bd9c15434f`）、
     gem5 2 个（`e6a6b9cdc9`/`c7e92c7f80`）未导出 commit——均安全可达（HEAD
     可达，非 dangling），是复现性缺口非数据丢失风险。
  2. QEMU `.work/source/qemu` 当前确有 dirty 工作区，对应
     `0019-dadao-cfx-state-scaffold.patch` 用全零伪造 commit hash；已用
     `git apply --check --reverse` 验证 patch 与 dirty diff 字节级一致（可
     恢复），但恢复前工作区是唯一权威副本，真实存在丢失风险——**列为唯一
     "必须立即处理"项**。
  3. 四方差分基线偏移（200/HARNESS=6 → 200/gem5-SKIP=2）根因定位到
     commit `b5b8c57`（任务 ML-015c，向量 spec 对齐，两轮独立 review
     Accepted）；`gem5-SKIP=2` 的具体原因是 `tests/scripts/run_gem5_test.py`
     一条 DG-004d 时代的粗粒度 SKIP 规则未随向量订正同步更新，不是 gem5
     真实语义回归（`docs/issues-archive.yaml` 的 `rasof-rasuf-...` 条目已
     证明 gem5 支持 RASUF）；但此连锁效应从未被后续任何任务用
     `tools/run_differential.py` 验证或记录。
  4. puts/stdout 阻塞结论：独立重读 `/tmp/ml-017c-.../runtime/` 原始 stdout/
     rc，与 ML-017d 转述完全一致，**结论仍然成立，非过时**。
  5. musl `ML-014f` 候选：确认 `.work/source/musl` HEAD 上两个未导出 commit
     （`8ecf6f6e` 全项目 `-O0` workaround + `4741d4d1` malloc 入口点）已被
     后续全部 ML-016/017 矩阵结果默默依赖，且该依赖从未在最终交接文档中
     声明；`ML-017a` 最终矩阵的 "undefined physical register=16" 簇全程
     未修复，正是 `-O0` 掩盖的那个 bug。
  6. 任务文件卫生：`ML-016w` 重复文件确认是唯一实例、是良性别名 stub；
     `ML-014aa~ag` 命名在 `en_US.UTF-8` locale 下与 `ML-014a` 确有真实
     `sort` 顺序颠倒（已用实测复现），但无内容冲突；**`/tmp` 证据目录的
     "已不存在"假设被推翻**——29 个 `ml-01*` 目录当前仍在，且抽查内容
     与文档转述一致，但这只是环境侥幸未重启，不是设计保证。
- 开放式扫描（全部 37 个 ML-014aa~ag/016/017 任务文件完成区+审阅记录）
  未发现 `|| true`/忽略退出码/单后端顶替/手搓汇编顶替 CodeGen 等禁止模式；
  未发现 `docs/issues.yaml`/原始 `ML-014a` 任务文件被本轮触碰。

## 审阅记录（subagent · 自审）

**判决：通过（自审）。** 本任务为纯审计任务，自审重点核对"每条结论是否有
具体命令输出佐证"，非代码 review。

- 逐条核验：
  - 第 1 节 4+2+1 个未导出 commit：均有 `git log --oneline <last-exported>..HEAD`
    的直接输出作为证据，且用 `git show --stat` 交叉核对 gem5 `0012` patch
    header hash 与 commit hash 一致 ✓；QEMU 伪造 hash 用 `head -3` 直接展示
    `From 0000...` ✓，字节级一致性用 `git apply --check --reverse` 实测
    exit 0 佐证 ✓。
  - 第 2 节基线偏移：用真实 `python3 tools/run_differential.py` 跑出当前
    数字（非引用架构师转述）✓；用 `git log --oneline --all -- <文件>` 定位
    到具体 commit 并 `git show --stat`/完整 diff 展示改动内容 ✓；gem5-SKIP
    根因用独立小脚本（写在 scratchpad，非仓库内）单独跑 2 条向量并读
    `run_gem5_test.py` 源码定位到具体行号 104-106 ✓。
  - 第 3 节 puts 复核：直接 `cat` `/tmp/ml-017c-.../runtime/puts_probe/*`
    与 `puts_errno_bypass/*` 原始 stdout/rc ✓，并读对应 `inputs/*.c` 源码
    确认探针逻辑成立 ✓，用 `stat` 核对 mtime 排除陈旧数据嫌疑 ✓。
  - 第 4 节 musl 候选：`git show <commit>` 展示两个 commit 完整 diff ✓；
    `grep` 交叉确认 `4741d4d1` 被 `ML-016s`/`ML-017a`/`ML-016f` 显式引用为
    base commit ✓；"undefined physical register=16 全程未修复"用
    `grep` 直接摘 `ML-017a`/review 文件里的簇计数表格佐证 ✓。
  - 第 5 节任务文件卫生：重复文件用 `sort | uniq -c` 实测 ✓；locale 排序
    陷阱用现场 `sort` vs `LC_ALL=C sort` 对照实测 ✓（非猜测）；`/tmp` 目录
    存在性用 `find /tmp -maxdepth 1 -iname "ml-01*" -type d` 实测列出 29 个
    ✓，并抽查其一内容验证非空壳。
  - 第 6 节开放式扫描：抽查独立 review 文件命名不统一用 `ls docs/reviews/`
    实测列出 ✓；`docs/issues.yaml` 未被触碰用
    `git log b5b8c57~60..HEAD -- docs/issues.yaml docs/issues-archive.yaml`
    零命中佐证 ✓。
- 未测/未覆盖的边界：未对 60+ 任务文件逐字通读（任务允许只读完成区+审阅
  记录）；无法从外部核实 worker/reviewer 是否为真正独立的 subagent 进程，
  只能做内容层面判断，已在报告第 6.2 条如实声明这一方法论局限；未对
  `ML-014b~z`（ML-014f 之外，非本次 codex 独立衍生序号）逐一复核，因任务
  范围明确限定在 ML-014aa~af/ML-016a~z/ML-017a~d + 与之直接相关的 ML-014f/
  KL-102b。
- finding：无遗漏发现自身报告的逻辑漏洞；所有结论均可用报告中列出的命令
  复现。
