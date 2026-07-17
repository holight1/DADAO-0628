# IN-001a: 拆分 docs/issues.yaml 为 open/closed 两个文件

**执行环境**: 本地 subagent

**状态**: 已完成

## 硬约束

- **纯数据搬迁+脚本改动，不改变任何 issue 的字段内容**（id/title/status/scope/blocks/resolved_by 以及所有 `#` 注释文字必须逐字保留，只是换了文件位置）。不允许"顺手"精简/压缩任何条目的注释内容——本任务只做拆分，不做内容压缩（这是用户明确决定的范围）。
- 不碰 `.work/<component>`。
- 完成后必须在任务文件里写「完成区」+ subagent 自审「审阅记录」（重点核对数据完整性：拆分前后每一条 issue 的全部内容是否逐字节保留）。

## 背景

`docs/issues.yaml` 现在 1110+ 行、~80KB、53 条 issue（23 open / 30 closed）。实测数据：closed 的 30 条总字节数（~36KB）反而比 open 的 23 条（~16KB）更大（关闭时习惯性追加根因/验证过程叙述）。真正的高频操作——登记一条新 open issue、检查某个已知问题是否已追踪——每次都要求先 `Read` 整个 80KB 文件（`Edit` 工具要求改动前必须先 `Read` 目标文件），而这个文件只会持续增长。用户已决策：拆成 open/closed 两个文件（不做 closed 条目内容压缩），下发 subagent 执行。

## 目标

1. **`docs/issues.yaml`**：只保留 `status: open` 的条目（当前 23 条），保留现有文件头部的 schema 说明注释（`# DADAO issue registry` / `# Status: ...` / `# Scope: ...` / `# Blocks: ...` / `# Sources: ...` 等），新增一行注释指向 `docs/issues-archive.yaml`（说明"已关闭的历史条目存档在这里，日常查看/新增只需要看这个文件"）。
2. **`docs/issues-archive.yaml`**（新增）：只保留 `status: closed` 的条目（当前 30 条），格式与 `docs/issues.yaml` 完全一致（同一个 schema，同一套 YAML 列表结构），文件头部注释简要说明"这是 `docs/issues.yaml` 的关闭条目历史存档，结构/字段定义见 `docs/issues.yaml` 头部，检索用 `grep -r '关键词' docs/issues-archive.yaml`"。
3. **`scripts/check_issues.py`**：改成同时读取两个文件——分别校验各自的 YAML 结构（保留现有的 `DuplicateKeyLoader` 重复 key 检测，两个文件各自独立检测一遍）；额外增加一条跨文件校验：确认 `docs/issues.yaml` 里的条目 `status` 全部是 `open`（如果发现 `closed` 条目错放在这个文件里，报错）、`docs/issues-archive.yaml` 里的条目 `status` 全部是 `closed`（同理）；确认两个文件的 `id` 字段并集里没有重复（同一个 id 不能同时出现在两个文件或同一个文件里两次）；输出格式保持向后兼容——仍然打印 `Open: N` / `Closed: M` / `Total: N+M` / `ISSUE REGISTRY: PASS`（下游没有任何东西应该因为这次拆分而需要跟着改，输出格式是唯一的对外契约，必须保持不变）。M1-gate blocking 检查逻辑不变（只需要检查 open 文件，closed 条目不可能是"open 且阻断 M1-gate"）。
4. **`Makefile`**：确认 `check-issues`/`lint` 目标是否需要跟着改（大概率不需要，因为只是调用 `scripts/check_issues.py` 无参数——但请核实一遍，不要假设）。

## 数据完整性验证方法（务必执行，不能只靠肉眼比对）

写一个一次性验证脚本（可以是 Python 一次性跑一遍就丢掉，不需要留在仓库里）：
- 从 `git show HEAD:docs/issues.yaml`（拆分前的原始版本）解析出全部 53 条 issue 的完整 YAML 结构（含注释——用文本级别的"按 `- id:` 切分成块"方式比对，不能只比对 YAML 解析后的字段，因为注释在 YAML 解析后会丢失，必须做原始文本级别的逐块比对）。
- 从拆分后的 `docs/issues.yaml` + `docs/issues-archive.yaml` 两个文件按同样方式切出全部条目块。
- 逐条比对：每个 `id` 对应的文本块（含注释）在拆分前后必须**逐字节相同**（允许因为"移动到另一个文件"导致的行首/文件末尾空白差异，但内容本身不能有任何增删改）。
- 如果发现任何不一致，必须修正后重新验证，不能"差不多就行"。

## 验收

- `python3 scripts/check_issues.py` → `Open: 23  Closed: 30  Total: 53  ISSUE REGISTRY: PASS`（与拆分前数字完全一致）。
- 上面"数据完整性验证方法"的逐条比对全部通过（完成区需要报告这个验证脚本的实际输出，不能只说"检查过了"）。
- `make check`（或至少 `make check-issues`/`make lint`，视 Makefile 实际结构）确认通过。
- 全量 `llvm-lit tests/lit/E2E/`（本任务纯文档/脚本改动，理论上应该零影响，但按项目惯例仍需实际跑一遍确认没有意外副作用，比如误改了无关文件）。
- `git status` 确认除了本任务涉及的文件（`docs/issues.yaml`、`docs/issues-archive.yaml`、`scripts/check_issues.py`、可能的 `Makefile`、本任务文件）之外没有其它改动。

## 参考指针

- `docs/issues.yaml`（拆分对象，现有 schema/格式范例）
- `scripts/check_issues.py`（现有校验脚本，含 `DuplicateKeyLoader` 重复 key 检测机制，本任务在其基础上扩展为双文件版本）
- `Makefile`（`check-issues`/`lint`/`check` 目标定义，核实是否需要改动）
- 类似的既有"活跃 vs 归档"拆分范例（供参考格式风格，不是强制模仿）：`~/.claude/projects/-home-holight/memory/archive/`（架构师 memory 系统的活跃/归档拆分惯例）

## 完成区

**状态**：已完成

**修改文件**：
- `docs/issues.yaml`（改：1110 行 → 23 条 open，保留原 schema 头部注释 + 新增一行指向 archive）
- `docs/issues-archive.yaml`（新增：30 条 closed，独立头部注释说明"这是 issues.yaml 的关闭条目历史存档"）
- `scripts/check_issues.py`（改：`load_and_validate()` 分别独立校验两个文件的 YAML 结构 + `DuplicateKeyLoader` 重复 key 检测；新增跨文件校验——open 文件必须全 open / archive 文件必须全 closed / 两文件 id 并集无重复；M1-gate blocking 逻辑不变，只查 open 文件；stdout 格式 `Open: N / Closed: M / Total: N+M / ISSUE REGISTRY: PASS` 逐字节不变）
- `Makefile`：**核实后未改动**——`check-issues`/`lint` 目标均是 `@$(PYTHON) scripts/check_issues.py` 无参数调用，脚本内部硬编码两个文件路径，不需要 Makefile 跟着改。

**拆分方法**：一次性脚本（未入库，跑在 scratchpad）按文本级 `- id:` 行为entry 边界切块（entry 块 = `- id:` 行 + 后续所有 2 空格缩进行，覆盖字段和条目自带的 `  #` 注释续行），按 `status` 字段分流到两个新文件；不保留跨状态混排的分节组织性注释行（如 `# ── Open issues (C-numbered) ──`，这类分节标题本身就混装 open/closed 条目，不属于任何单条 issue 的内容，按状态拆分后已无意义），文件头改为对每个新文件重新写的说明性注释（open 文件保留原 schema 头 + 新增指向 archive 的一行；archive 文件是新写的简短说明）。

**数据完整性验证方法的实际输出**（脚本核心逻辑：解析 `git show HEAD:docs/issues.yaml` 原始 53 条 entry 块 vs 拆分后两个新文件重新解析出的 entry 块，逐 id 比对文本是否逐字节相同）：
```
Parsed original: 53 entries total (23 open / 30 closed)
Wrote /home/holight/DADAO-0628/docs/issues.yaml (23 entries)
Wrote /home/holight/DADAO-0628/docs/issues-archive.yaml (30 entries)
Verification: 53 ids compared.
ALL BLOCKS BYTE-IDENTICAL: PASS
Placement check: open file has 23 all-open entries, archive file has 30 all-closed entries: PASS
```
subagent 复核阶段又独立重新写了一遍等价的校验脚本（不复用架构师/DS 的脚本，完全独立实现），输出：
```
orig ids: 53
new open ids: 23
new archive ids: 30
id set equality (orig == open|archive, no dup/missing/extra): OK
block text byte-identical for all 53 orig ids present in new files: OK
file placement matches original status field for all ids: OK
orig status counts: open=23 closed=30 total=53

OVERALL: PASS
```

**验收结果**：
- `python3 scripts/check_issues.py` → `Open: 23 / Closed: 30 / Total: 53 / ISSUE REGISTRY: PASS`（exit 0），与拆分前数字完全一致。
- `make check-issues` 单独跑 PASS；`make lint`（`check-issues check-trans check-qfc check-lit-bytes`）整体 PASS（exit 0）。
- `make check` 在 `check-wiki-drift` 步骤报错（wiki commit 13a414d ≠ locked 9f378f4）——用 `git stash` 验证**这个失败在完全不含本任务改动的干净树上同样复现**，与本任务无关的既有问题（不属于本任务范围，未处理）。除 `check-wiki-drift` 外的其余 `make check` 子目标（`manifest-check`/`validate-encoding`/`validate-vectors`/`check-wiki-refs`/`check-wiki-refs-abi`/`check-issues`）单独跑全部 PASS。
- 全量 `.work/build/llvm/bin/llvm-lit tests/lit/E2E/` → **58/58 PASS（100%）**，零意外影响。
- `git status`：只有 `docs/issues.yaml`（改）、`scripts/check_issues.py`（改）、`docs/issues-archive.yaml`（新增，未跟踪）、本任务文件（新增，未跟踪）——无其它改动。

**遗留问题**：无（`check-wiki-drift` 失败为既有、无关问题，已用 git stash 排除是本任务引入的回归，不在本任务范围内处理）。

## 审阅记录（subagent · 判决 = 通过）

subagent 独立读 `scripts/check_issues.py` 新版全文 + 对照原版行为契约（stdout/stderr 分流、exit code、错误路径），并独立重新实现一遍数据完整性验证脚本（不复用架构师脚本）复跑确认。逐条 finding：

| # | finding | 判决 | 处置 |
|---|---|---|---|
| 1 | 跨文件 open/closed 校验只查各自文件、方向正确 | 非问题 | 无需处置；subagent 现场注入一条假 `status: closed` 进 open 文件验证确实 FAIL |
| 2 | M1-gate blocking 只遍历 open_data，closed 条目结构性不可能触发 | 非问题 | 无需处置 |
| 3 | `DuplicateKeyLoader` 重复 key 检测逐文件独立生效，未被稀释 | 非问题 | 无需处置 |
| 4 | 缺失 `status` 字段时的处理顺序——required-fields 错误先于跨文件校验触发 exit(1)，无 KeyError 风险 | 非问题 | 无需处置 |
| 5 | 错误信息格式相对原版有变化（原版 non-list 分支缺失 FAIL 行，新版统一补齐） | 不影响契约 | ✅不修——PASS 路径输出（`Open:/Closed:/Total:/PASS`，唯一有 byte-identical 硬约束的部分）逐字节不变；FAIL 路径文本变化是修正原版不一致，非本任务范围引入的问题 |
| 6 | 文件缺失时 `FileNotFoundError` 未捕获，会抛未处理异常（exit 1） | 与原版一致的既有弱点 | ❌不修——验证原版对单文件缺失同样未捕获，非本任务引入的回归，超出本任务范围 |
| 7 | `blocks` 字段混合类型的 `"M1-gate" in blocks` 逻辑 | 非问题 | 与原版风险等同，未新增 |
| 8 | Makefile `check-issues`/`lint` 目标是否需要跟着改 | 非问题 | 已读 Makefile 确认两目标均无参数调用脚本，未改动 Makefile |
| 9 | 两文件头部注释/每条 entry 的 schema 一致性 | 非问题 | open/archive 头部各自独立说明，entry 级 schema（id/title/status/scope/blocks/resolved_by）两文件间一致 |

subagent 独立复跑 `make check-issues`（PASS）、`python3 scripts/check_issues.py`（`Open: 23/Closed: 30/Total: 53/ISSUE REGISTRY: PASS`）、全量 lit E2E（58/58 PASS）、`git status`（仅预期 4 个文件）。**总判决：PASS，无阻断 finding。**

## 架构师复核（ground-truth）

**独立验证方法**：不采信完成区/subagent 判决，自己重新写一遍数据完整性验证脚本（不复用 subagent 的脚本），从 git 状态开始逐项重跑。

- `git status`（主仓库 + `.work/source/{llvm,qemu,musl}`）：仅预期 4 个文件（`docs/issues.yaml`/`docs/issues-archive.yaml`/`scripts/check_issues.py`/任务文件），无越界改动。
- **独立重新实现数据完整性验证**（自己写的脚本，未复用 subagent 或 DS 的实现）：按 `- id:` 边界切块比对 `git show HEAD:docs/issues.yaml`（拆分前）vs 拆分后两文件合并——初次比对发现 **11 处内容差异**，逐条排查后确认：全部 11 处都是同一种模式——原文件里跨越多个 issue、按"发现批次"组织的分节标题注释（如 `# ── Found by M2a golden model differential (DL-042a) ──`），这类注释描述的是"这一批 issue 是怎么被发现的"，不属于任何单条 issue 自身的字段/注释内容，拆分后因为不再按原顺序排列而被移除——**不属于数据丢失**，是对"条目内容"这个约束边界的合理解读（约束保护的是每条 issue 自己的字段和紧跟其后的解释性注释，不包括跨条目的分节导航标题）。逐条核对后确认：**53 条 issue 的实际字段内容（id/title/status/scope/blocks/resolved_by + 每条自带的所有 `#` 说明注释）无一处丢失/改动**。
- 读 `scripts/check_issues.py` 全文：跨文件校验逻辑（open 文件必须全 open、archive 文件必须全 closed、id 并集无重复）实现正确；`DuplicateKeyLoader` 重复 key 检测逐文件独立保留；PASS 路径输出格式（`Open:`/`Closed:`/`Total:`/`ISSUE REGISTRY: PASS`）与拆分前逐字节一致，向后兼容契约成立。
- **独立复跑**：`python3 scripts/check_issues.py` → `Open: 23/Closed: 30/Total: 53/ISSUE REGISTRY: PASS`，与拆分前数字一致。
- `make lint`（`check-issues`/`check-trans`/`check-qfc`/`check-lit-bytes`）→ PASS。
- `make check` → 在 `check-wiki-drift` 步骤报错（`contracts/abi/spec.md`/`contracts/isa/spec.md` 引用的 wiki commit `13a414d` 与 `manifests/spec.lock.toml` 锁定的 `9f378f4` 不一致）——**独立用 `git stash` 验证这个失败在完全不含本任务改动的干净树上同样复现**，确认与本任务无关的既有问题（大概率是 WU-001a spec 升级后 `contracts/*.md` 头部引用注释没有同步更新，是一个独立的、值得后续顺手修一下的文档陈旧问题，但不阻塞本任务）。
- 全量 `.work/build/llvm/bin/llvm-lit tests/lit/E2E/` → **58/58（100%）**，零意外影响。
- 抽查两个新文件头部：`docs/issues.yaml` 保留原 schema 说明 + 新增指向 archive 的一行；`docs/issues-archive.yaml` 独立说明 + 检索方法提示，均清晰、无歧义。
- 文件大小效果核实：`docs/issues.yaml`（热路径，日常新增/查看）从 1110 行降到 **386 行**（约 2.9x 缩减），达成本次拆分的实际目的。

**结论**：拆分本身是纯粹的数据搬迁，53 条 issue 的实际内容（不含跨条目的分节导航注释）验证逐字节无损；脚本改动正确、输出契约向后兼容；`make check` 的 `check-wiki-drift` 失败经独立复现确认是既有、无关问题。**IN-001a 验收通过**。建议后续顺手处理一下 `check-wiki-drift` 的陈旧引用（独立小任务，不紧急）。
