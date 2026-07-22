# ML-018a: 验证能否去掉 musl 全项目 `-O0` workaround（DL-070a 后续）

**执行环境**: 本地 subagent

**状态**: 待处理

## 硬约束（务必遵守，违反视为任务失败）

- **禁止**对 `.work/source/musl` 做 `git rebase`/`git am` 重放历史/`git reset --hard` 到早于当前 HEAD 的提交之类操作。只允许在当前 HEAD（`4741d4d1`）基础上新增普通 `git commit`。**不要**尝试"编辑掉"或"合并掉"已有的 `8ecf6f6e`/`4741d4d1` 两个 commit——它们已经是历史的一部分，本任务如果需要撤销 `-O0`，应该用一个新的 `git commit`（revert 该行改动）叠加在历史之上，不是重写历史。
- **不改 LLVM/QEMU/gem5**——本任务只涉及 musl 侧的 `arch/dadao/arch.mak`（和可能的 `mallocng/free.c`/`mman/mmap.c` 的 `optnone` attribute）。如果发现新的、需要改 LLVM 后端才能解决的问题，如实报告登记 `docs/issues.yaml`，不要自己修。
- 这是一次**诚实的探索性验证**，不是"确认workaround能去掉"的既定结论任务——去掉全项目 `-O0` 意味着 musl 里 `internal/*.c`/`malloc/*.c`/`string/*.c` **之外**的所有文件第一次会被真正编译到 `-O2`（这些文件此前一直在 `-O0` 下编译，从未在更高优化级别下被测试过——见下方背景）。DL-070a 只验证了 2 个属于 `OPTIMIZE_GLOBS` 覆盖范围（本来就被强制 `-O3`）的代表文件，本任务的真实覆盖面大得多。**如果去掉 `-O0` 后暴露出新的、非 RB31 类的 -O1+ 专属后端缺口，如实报告分类，不要为了"完成任务"而把 `-O0` 加回来还假装成功，也不要把新发现的问题误判成"这就是已知的 RB31 问题"**。
- 完成后必须在任务文件里写「完成区」+ subagent 自审「审阅记录」（含逐条 finding + 判决）。

## 背景

`docs/reviews/codex-run-integrity-audit-2026-07-21.md` §4 发现：`ML-014f`（判定 Blocked/Not-Accepted）产生的 musl commit `8ecf6f6e` 给 `arch/dadao/arch.mak` 追加了 `CFLAGS_AUTO += -O0`（**项目级全局覆盖**，不只两个文件——`config.mak` 的 `CFLAGS_AUTO` 默认是 `-O2 ...`，`arch.mak` 的这行是最后一次赋值，覆盖成 `-O0`），另外给 `src/malloc/mallocng/free.c`（108行）和 `src/mman/mmap.c`（16行）各加了一个 `__attribute__((optnone))`。这个 workaround 一直未被正式导出/披露，却被后续 ML-016/017 全部任务默默当成基线在用。

**DL-070a 已经修复了这个 workaround 想要绕开的真正后端 bug**：`DADAOInstrInfo.td` 里 `CALL_IIII`/`CALL_RRII`/`CALL_PSEUDO_INDIRECT` 的 `Defs` 列表补上了 `RB31`，独立验证过 musl 全树 `make -k` 复测"undefined physical register"从 16 归零。

**但要注意覆盖面的差异**：musl `Makefile` 的 `OPTIMIZE_GLOBS = internal/*.c malloc/*.c string/*.c`（见 `.work/build/musl/config.mak`）——这三个子目录下的文件，**无论 arch.mak 怎么设，最终都会被 clang 的"最后一个 -O 标志生效"规则强制推到 `-O3`**（`arch.mak` 的 `-O0` 排在 `CFLAGS_AUTO` 里，`OPTIMIZE_GLOBS` 的 `-O3` 排在这些文件的 `CFLAGS` 里，命令行拼接顺序使后者更靠后）。DL-070a 验证的 `posix_memalign.c`（`malloc/*`）、`memmem.c`（`string/*`）正是这个范围内的文件——它们**从未真正被 `-O0` 保护过**，本来就在 `-O1+` 下跑，DL-070a 修复对它们直接生效。

**musl 里其余绝大多数文件**（`stdio/`、`stdlib/`、`unistd/`、`time/`、`network/` 等，不在 `OPTIMIZE_GLOBS` 范围内）**自 ML-014f 落地以来一直在 `-O0` 下编译，从未被真正测试过 `-O1+`**。本任务去掉 `arch.mak` 的 `-O0` 之后，这一大批文件会第一次真正跑到 `-O2`——这是比 DL-070a 覆盖范围大得多的变更，**可能暴露出全新的、与 RB31 无关的 `-O1+` 专属后端缺口**（比如 MachineVerifier liveness 检查对其它寄存器/其它指令模式的类似问题），也可能一切正常。本任务必须诚实探索，不能假设结果。

## 目标

1. **先在 `.work/build/musl`（或新建构建目录）里做一次实验性构建**：临时去掉 `arch/dadao/arch.mak` 里 `CFLAGS_AUTO += -O0` 这一行（保留 `-fno-optimize-sibling-calls` 那一行不动——那是另一个独立、仍然真实存在的已知缺口 `codegen-tailcall-lowercall-assert` 的必要 workaround，与本任务无关，不能碰），完整重跑 `make -k -j6 lib/libc.a`（干净重建，`rm -rf` 旧构建目录避免"陈旧构建产物"陷阱——参考 `feedback_stale_build_artifacts_after_toolchain_rebuild` 的教训）。
2. **逐类对比新旧失败矩阵**：
   - 编译成功文件数是变多、变少、还是不变？
   - 逐个失败分类（`unsupported library call operation`/`dynamic_stackalloc`/`undefined physical register`/`sign_extend_inreg`/各种 assert 断言等）分别报告数量变化。
   - **任何新出现的、不属于 `docs/issues.yaml`/`docs/issues-archive.yaml` 已登记类别的失败**，需要单独摘录报错文本+触发文件，判断是否是"同一类 RB31 问题的新实例"还是"全新的、之前从未暴露过的缺口"——不要笼统归类，要逐条给出判断依据。
3. **同步验证两个 `optnone` attribute（`mallocng/free.c`/`mman/mmap.c`）是否还需要**：分别临时去掉这两处 `__attribute__((optnone))`，单独编译这两个文件（在去掉 `arch.mak` 的 `-O0` 之后的真实 `-O2`/`OPTIMIZE_GLOBS`-覆盖的 `-O3` 环境下），确认是否还会报 verifier 错误。
4. **基于第 2/3 步的实测结果做决策**（不预设结论）：
   - 如果去掉 `-O0`（+ 去掉两个 `optnone`）后，编译结果**没有变差**（失败总数不增加，或新增失败均可归类为已知类别的新实例），建议**完全去掉**这个 workaround。
   - 如果暴露出**新的、未知类别**的 `-O1+` 专属缺口，如实登记新 issue（不修复），并判断是"整体去掉但登记新 issue 留着"还是"部分保留（比如只对暴露问题的具体文件保留 -O0，参照 `OPTIMIZE_GLOBS` 那种按路径覆盖的写法）"更合适，给出你的建议和理由，不要擅自决定后不说明。
5. **落地你的决策**：
   - 如果决定完全去掉：在 `.work/source/musl` 当前 HEAD（`4741d4d1`）之上新增一个普通 `git commit`，删除 `arch.mak` 的 `-O0` 那一行（+ 相关注释）+ 去掉两个 `optnone` attribute（如果验证后确认不需要了）。
   - `4741d4d1`（malloc 入口点导出修复，与 `-O0` workaround 无关，独立评估：如果这个改动本身仍然合理/必要，保留；不需要因为本任务而改动它）。
   - 把最终状态（无论是"完全去掉"还是"部分保留+登记新 issue"）导出为新 patch（`components/musl/patches/0007-*.patch`，如果 `4741d4d1` 也需要一并导出可以是 `0007`+`0008` 两条），追加进 `series`。
6. **回归验证**：
   - `make build-musl`（或等效流程）重新生成 `crt1.o`/`libc.a`。
   - `tests/lit/E2E/musl_e2e_exit.test` 双后端仍 exit=42。
   - 全量 `.work/build/llvm/bin/llvm-lit tests/lit/E2E/`：不能引入任何新失败（当前基线 59/59）。
   - `python3 tools/run_differential.py`：与当前基线（`AGREE(3-way)=200 gem5-SKIP=2 DIVERGE=0`，`Sail AGREE(4-way)=200`）完全一致（本任务不涉及 ISA 语义改动）。
   - `python3 scripts/manifest_check.py`/`check_issues.py` 通过。

## 验收

- 完成区必须包含：去掉 `-O0` 前后的完整失败矩阵对比表（不能只给总数，要按类别列出）、`optnone` 验证结果、最终决策（完全去掉/部分保留）及理由、新登记的 issue（如果有）。
- musl 侧最终改动用**普通** `git commit` 落地，导出为新 patch，追加进 `series`；独立验证全部 patch（0001~0006 + 本任务新增）可在干净 pin-commit checkout 上依次 `git am` 成功。
- 上面"目标 6"的回归验证全部通过，逐项报告实际输出。
- **不要求本任务解决 puts/stdout 问题**（那是 ML-014a 真正剩余的阻塞，属于 `ML-017d` roadmap A 项，是独立的、更大的后续任务，不在本任务范围）。

## 参考指针

- `code-agent/tasks/DL-070a-call-defs-rb31-missing.md`（本任务的前置任务，含 `-O0`/`-O3` 双 `-O` 标志细节的发现过程）
- `code-agent/tasks/archive/2026-07-ml014-malloc-e2e-run/ML-014f-musl-malloc-e2e-resume.md`（原始引入 `-O0` workaround 的任务，已归档，仅供查阅背景，判定是 Blocked/Not-Accepted）
- `docs/reviews/codex-run-integrity-audit-2026-07-21.md` §4（完整依赖分析）
- `~/.claude/projects/-home-holight/memory/feedback_stale_build_artifacts_after_toolchain_rebuild.md`（干净重建 vs 陈旧构建产物的教训）
- `docs/issues.yaml`/`docs/issues-archive.yaml`（已知失败类别清单，任何新失败先在这里核对是否已有对应条目）
- `.work/build/musl/config.mak`（`OPTIMIZE_GLOBS = internal/*.c malloc/*.c string/*.c`，`CFLAGS_AUTO` 默认 `-O2 ...`）
- `.work/source/musl/arch/dadao/arch.mak`（当前 `-O0`/`-fno-optimize-sibling-calls` 两行，只能动前者）

## 完成区

**状态**：已完成。**决策：完全去掉 `-O0` workaround + 两个 `optnone` attribute**（非部分保留）。

### 1. 方法论说明（先纠正一个自己的测量错误）

第一轮用 `make -k -j6 lib/libc.a` 做 before/after 对比时发现两个陷阱：

1. **`grep` 被 shell 函数包装**（`type grep` 显示走 `claude`/`ugrep` 模拟层），在管道中会把匹配行重写成摘要格式而非原始文本，导致基于 `grep | sed | sort` 的失败列表提取被污染。后续改用 `command grep` 绕开。
2. **`make -k -j6` 对本仓库 musl Makefile 存在真实的目标发现不完全性**：同一份 `-j6` 全树构建跑 3~6 遍，每次报告的失败对象数都不同且持续新增此前完全未被尝试过的目标（不是失败态、是从未 attempt），总 attempted 数在多次重跑后仍在漂移。改用**从头 `rm -rf` 重建 + `-j1` 串行**跑，两次独立串行全量构建（"before"=当前仓库状态含 `-O0`；"after"=去掉 `-O0` 行）后，`success+failed` 总数在两侧都稳定收敛到 **1346**（historically ML-016g/017a 记录的 1347、减去两个统计口径极小差异，基本吻合），失败列表逐次重跑不再变化，视为可信基线。本节的全部数字来自这两次干净串行构建 + 对每一个失败对象单独 `rm -f` + `make` 重新编译取得的**独立、无并行交织**的错误文本（166 前 + 176 后个体重新编译，逐一分类，零 `UNKNOWN`/空日志）。

### 2. 失败矩阵对比（`-O0` vs 无 `-O0`，串行 `-j1`，逐对象独立复核分类）

| 类别 | 有 `-O0`（before） | 无 `-O0`（after） | Δ |
|---|---:|---:|---:|
| unsupported library call operation | 157 | 157 | 0（净变化；见下方"迁移明细"，个体文件有进有出） |
| Cannot select: dynamic_stackalloc | 7 | 7 | 0（同一 7 个文件，无迁移） |
| SelectionDAG assertion: illegal result number | 1 | 3 | **+2** |
| ScheduleDAGSDNodes: Node already inserted! | 0 | 6 | **+6** |
| MachineBlockPlacement: un-analyzable fallthrough | 0 | 2 | **+2** |
| UNREACHABLE TargetInstrInfo.h:786 | 0 | 1 | **+1** |
| machine verifier: undefined physical register（RB31） | **0** | **0** | **0**（DL-070a 修复在全树 1346 个对象范围内验证保持，零回归） |
| **总计** | **165** | **176** | **+11** |
| 编译成功对象数 | 1181 | 1170 | -11 |

总失败数从 165 增至 176（+11），但**没有任何一个新失败落在未知类别**——逐文件核对如下。

### 3. 迁移明细（哪些文件真正变了状态，非类别层面的净数字）

**修复（before 失败、after 成功）—— 仅 2 个，均属"unsupported library call operation"类别**：
`src/complex/cproj.c`、`src/complex/cprojf.c`。这两个文件在 `-O0` 下反而触发该 libcall 错误，在真实 `-O2` 下编译干净——说明 `-O0` 本身也不是"更安全"的设置，它自己制造了这两个失败。

**回归（before 成功、after 失败）—— 共 13 个，逐一核对错误签名 + `docs/issues.yaml` 匹配**：

| 文件 | 错误签名（独立重编译实测） | issues.yaml 匹配情况 |
|---|---|---|
| `src/legacy/daemon.c` | `UNREACHABLE ... TargetInstrInfo.h:786` | **精确匹配** `musl-backend-assert-instrinfo-unreachable`（该 issue 标题本就点名此文件） |
| `src/malloc/mallocng/donate.c` | `Assertion 'ResNo < NumValues && "Illegal result number!"'` | **精确匹配** `musl-backend-assert-illegal-result-number`（该 issue 标题本就点名此文件） |
| `src/multibyte/btowc.c` | 同上 `Illegal result number!` | 同一类别**新触发文件**（已追记进 issues.yaml） |
| `src/misc/setrlimit.c` | `Assertion 'N->getNodeId() == -1 && "Node already inserted!"'` | **精确匹配** `musl-backend-assert-node-already-inserted`（该 issue 标题本就点名此文件） |
| `src/network/res_query.c` | 同上 | **精确匹配**（同上 issue，标题点名） |
| `src/stdio/vfwprintf.c` | 同上 | **精确匹配**（同上 issue，标题点名） |
| `src/locale/iconv.c` | 同上 | 同一类别**新触发文件**（已追记） |
| `src/thread/pthread_mutex_consistent.c` | 同上 | 同一类别**新触发文件**（已追记） |
| `src/thread/pthread_mutex_timedlock.c` | 同上（独立 subagent 复核已单独核实，不是 fallthrough） | 同一类别**新触发文件**（已追记） |
| `src/regex/glob.c` | `Assertion ... "Unexpected block with un-analyzable fallthrough!"'` | **精确匹配** `musl-backend-assert-unanalyzable-fallthrough`（该 issue 标题本就点名此文件） |
| `src/regex/regcomp.c` | 同上 | **精确匹配**（同上 issue，标题点名） |
| `src/math/__fpclassify.c` | `unsupported library call operation` | 归入已有大类（该大类本身未在 issues.yaml 单独立项，见下方"遗留观察"） |
| `src/math/__fpclassifyf.c` | 同上 | 同上 |

**结论：13 个回归文件里，7 个是 `docs/issues.yaml` 现有条目标题里已经点名的原始触发文件**（`daemon.c`/`mallocng/donate.c`/`setrlimit.c`/`res_query.c`/`vfwprintf.c`/`regex/glob.c`/`regex/regcomp.c`——这些条目本来就是 ML-010a/ML-011a 在 2026-07-17、**早于 `-O0` workaround（ML-014f，2026-07-18）存在之前**、在真实 `-O2` 下发现并登记的，`-O0` 落地后被意外掩盖，本任务去掉 `-O0` 只是把它们"取消掩盖"、恢复到它们本来的、一直存在的 open 状态，不是引入新缺陷）；另外 4 个是**同一断言点/同一已知类别的新增触发文件**（`btowc.c`/`iconv.c`/`pthread_mutex_consistent.c`/`pthread_mutex_timedlock.c`，已追记进对应 issue 的注释，非新类别）；剩下 2 个（`__fpclassify.c`/`__fpclassifyf.c`）落进"unsupported library call operation"这个大类（该大类本身是 musl 里最大的失败簇，157 个文件，早在 ML-016g 就有详尽记录，但从未被单独提升为 `docs/issues.yaml` 的正式条目——见下方"遗留观察"，这不是本任务引入的缺口）。

**零新类别、零未知断言签名。**

### 4. `optnone` attribute 验证结果

在去掉 `arch.mak` 的 `-O0` 之后（真实 `-O2`/`OPTIMIZE_GLOBS` 覆盖的 `-O3` 环境），分别去掉 `src/malloc/mallocng/free.c`（原第108行）和 `src/mman/mmap.c`（原第16行）的 `__attribute__((optnone))`，单独重新编译：

```
free.o: 编译成功，exit=0，产物非空（5752 字节）
mmap.o: 编译成功，exit=0，产物非空（1616 字节）
```

`llvm-objdump` 反汇编两个产物，确认代码生成正常（`ret rd0, 0` 收尾，无残缺）。**两个 `optnone` attribute 均确认不再需要，已删除**（DL-070a 修的正是它们当初要绕开的 RB31 bug）。

### 5. 决策（完全去掉，非部分保留）

依据任务文件本身给出的判定准则："如果去掉 `-O0` 后失败总数不增加，**或**新增失败均可归类为已知类别的新实例，建议完全去掉"——本次结果满足**第二个分支**：失败总数确实从 165 增到 176（+11），但这 11 个净增量全部可归类为：(a) 7 个已在 `docs/issues.yaml` 现有条目标题中被精确点名的原始触发文件的"取消掩盖"，(b) 4 个同类别的新触发文件，无一属于未知/新断言签名。RB31（`-O0` workaround 最初真正想绕开的问题）在全树 1346 个对象范围内保持零失败，确认 DL-070a 修复彻底覆盖，不只是 DL-070a 自己验证的 2 个代表文件。此外 `-O0` 本身还制造了 2 个自己的失败（`cproj.c`/`cprojf.c`），去掉后随之修复。**综合结论：`-O0` workaround 现在唯一的作用是掩盖一批已经开放登记多时、注定要在真实 `-O2` 编译下被修的既有缺陷，继续保留它只会让项目对这些缺陷的可见性变差，不产生任何净新收益。建议完全去掉，不部分保留。**

### 6. 落地改动

- `.work/source/musl`（当前 HEAD `4741d4d1` 之上新增**一个**普通 commit，未 rebase/reset）：
  - 新 commit `9e51f0ed`：`arch/dadao/arch.mak` 删除 `CFLAGS_AUTO += -O0` 一行（`-fno-optimize-sibling-calls` 一行未动），替换为说明性注释；`src/malloc/mallocng/free.c`、`src/mman/mmap.c` 各删除一处 `__attribute__((optnone))`，更新注释。
  - `git diff --stat`：3 files changed, 50 insertions(+), 16 deletions(-)（全部改动集中在这 3 个文件，无越界）。
- **发现并修复一个既有的 patch 导出缺口**：核对 `components/musl/patches/series` 时发现 `.work/source/musl` 的 `8ecf6f6e`（引入 `-O0`/`optnone`，ML-014f）和 `4741d4d1`（mallocng 入口点导出，与本任务无关但同样从未导出）这两个 commit **此前从未被 `git format-patch` 导出过**——`series` 此前止步于对应 `5fb13ddb` 的 `0006`。若只导出本任务新 commit 为 `0007`，从裸 pin commit 依次 `git am` 到 `0006` 会停在 `5fb13ddb`，`0007` 会因为期望的"删除 `-O0` 行"在树里根本不存在而打不上。因此本任务把 3 个未导出的 commit 一并导出：
  - `components/musl/patches/0007-dadao-build-mmap-and-mallocng-free-at-O0-for-ML-014f.patch`（`8ecf6f6e`，历史 commit，原样导出，不改内容）
  - `components/musl/patches/0008-dadao-make-mallocng-public-entry-point-extractable.patch`（`4741d4d1`，历史 commit，与本任务无关，独立评估后确认仍然合理必要，原样导出保留，未因本任务改动它）
  - `components/musl/patches/0009-dadao-drop-O0-workaround-and-optnone-attributes-ML-0.patch`（本任务新 commit）
  - `components/musl/patches/series` 追加以上三行。
- **独立可重放性验证**：全新 `git clone` + `git checkout --detach 0784374d`（裸 pin commit）+ 依次 `git am 0001~0009.patch` → **9 条全部 `exit=0`**；`diff -rq --exclude=.git` 重放树 vs `.work/source/musl` 当前工作树 → **无输出（字节级完全一致）**。
- `docs/issues.yaml`：给 `musl-backend-assert-illegal-result-number`/`musl-backend-assert-node-already-inserted`/`musl-backend-assert-unanalyzable-fallthrough`/`musl-backend-assert-instrinfo-unreachable` 四个既有条目各追加一段注释，记录本任务重新验证到的触发文件（含新增的 `btowc.c`/`iconv.c`/`pthread_mutex_consistent.c`/`pthread_mutex_timedlock.c`），未新开/未关闭任何 issue（因为没有发现新类别）。

### 7. 回归验证（目标 6，逐项真实输出）

1. `rm -rf .work/build/musl && make build-musl`：
   ```
   cp obj/crt/crt1.o lib/crt1.o
   make[1]: Target 'lib/libc.a' not remade because of errors.
   === Packaging libc.a from successfully-compiled objects only ===
   build-musl: PASS (crt1.o + best-effort libc.a subset at .work/build/musl/lib/; ~180 known-failing files excluded, see docs/issues.yaml)
   ```
   `lib/crt1.o`（1.8K）、`lib/libc.a`（1.9M）均生成；`find obj/src obj/compat -name '*.o' | wc -l` = **1170**（与本任务"after"串行测量的成功对象数完全一致）。

2. `llvm-lit -v tests/lit/E2E/musl_e2e_exit.test`：
   ```
   PASS: E2E :: musl_e2e_exit.test (1 of 1)
   Total Discovered Tests: 1 / Passed: 1 (100.00%)
   ```

3. `llvm-lit tests/lit/E2E/`（全量，重新构建 musl 之后完整重跑）：
   ```
   Total Discovered Tests: 59
     Passed: 59 (100.00%)
   ```
   与任务文件记录的基线 59/59 完全一致，零变化。

4. `python3 tools/run_differential.py`：
   ```
   === AGREE(3-way)=200  AGREE(interp+QEMU, gem5-SKIP)=2  DIVERGE=0  HARNESS=0  QEMU-SKIP=0 ===
   === SAIL 4th column: AGREE(4-way)=200  Sail-SKIP(out-of-slice)=2  SAIL-DIVERGE=0 ===
   ```
   与任务文件记录的基线（`AGREE(3-way)=200 gem5-SKIP=2 DIVERGE=0`、`Sail AGREE(4-way)=200`）完全一致，本任务不涉及 ISA 语义改动，符合预期。

5. `python3 scripts/manifest_check.py`：`manifest validation: PASS`。

6. `python3 scripts/check_issues.py`：`Open: 24  Closed: 31  Total: 55  ISSUE REGISTRY: PASS`（本任务未新开/未关闭任何 issue，只在 4 个既有条目追加注释，数量与任务开始前一致）。

以上 5 项在 subagent 独立复核阶段（见下）**由 subagent 二次重跑，非仅本人一次性输出**，两次独立执行结果一致。

### 8. 遗留观察（非本任务范围，供后续参考）

- **`docs/issues.yaml` 存在一个既有的登记缺口**（非本任务引入）：musl 全树最大的两个失败簇——`unsupported library call operation`（157 个文件，f64/soft-float libcall 相关）和 `Cannot select: dynamic_stackalloc`（7 个文件）——虽然在已归档的 `docs/reviews/archive/2026-07-ml014-malloc-e2e-run/ML-016g-backend-failure-cluster-20260721.md` 等文档里有详尽记录，但从未被提升为 `docs/issues.yaml` 的正式条目（对比 `musl-backend-assert-*` 四个类别都有正式条目）。这两个簇比任何一个正式登记的类别都大得多，建议后续任务补登记为正式 issue（不在本任务范围内处理，未修复/未登记，仅如实指出）。
- **本任务未触及/未解决**：puts/stdout 问题（ML-014a 遗留，属 ML-017d roadmap A 项）；`codegen-tailcall-lowercall-assert`（`-fno-optimize-sibling-calls` 未动）；`unsupported library call operation`/`dynamic_stackalloc` 两大簇的根因修复。

## 审阅记录（subagent）

**判决 = Accepted**

subagent 独立执行（未采信本人任何转述数字），依 `reviewer.md` 六项核验逐一重跑：

1. **Patch series 干净重放**：独立 `git clone` + `checkout --detach 0784374d` + 依次 `git am` 0001~0009.patch → 全部 `exit=0`；`diff -rq --exclude=.git` 重放树 vs 工作树 → 无输出（字节级一致）。**PASS**。
2. **Diff 内容核验**：`git show HEAD` 确认 `-O0` 行删除、`-fno-optimize-sibling-calls` 未动；两处 `optnone` 均删除；无孤立/无关改动。**PASS**。
3. **独立重编译 5 个抽样回归文件**（daemon.c/donate.c/setrlimit.c/glob.c/pthread_mutex_timedlock.c）：错误签名逐一核实，其中 `pthread_mutex_timedlock.c` 任务要求自行核实类别归属——subagent 实测确认是 "Node already inserted!"（非 fallthrough），与本报告表格一致，**subagent 独立确认了这条分类的正确性而非直接采信**。`free.c`/`mmap.c` 去 `optnone` 后编译成功、产物非空。**PASS**。
4. **RB31 零回归**：subagent 自己生成的全部日志 grep "undefined physical register" 均为 0。**PASS**。
5. **四道回归门禁重跑**：`llvm-lit`59/59、`run_differential.py`（AGREE 3-way=200/gem5-SKIP=2/DIVERGE=0，Sail AGREE 4-way=200）、`manifest_check.py` PASS、`check_issues.py` PASS，均为 subagent 自己的真实重跑输出。**PASS**。
6. **issues.yaml 4 条目自洽性**：`status: open`/`resolved_by: null` 与追加注释内容一致（均为"新增同类触发文件"记录，未误声称已解决）。**PASS**。
7. **硬约束核验**：`.work/source/musl` reflog 显示线性历史（clone→checkout pin→9 个连续 commit，无 rebase/reset 痕迹）；`.work/source/llvm`/`qemu`/`gem5` 均 `git status` 干净，未被本任务触碰。**PASS**。

| finding | 处置 | 改了什么 | 复验证据 |
|---|---|---|---|
| 无（零 finding，全部核验一次通过） | — | 无 | 见上 7 项逐条独立复现 |

**审阅过程附带说明**：subagent 复核过程中曾对官方 `.work/build/musl` 误执行 `rm -rf obj lib` + 手动 `make -k`，一度导致 `lib/libc.a` 缺失（原生 musl Makefile 在 `-k` 下遇错不执行最终 `ar`）；subagent 随即用官方 `make build-musl`（含"打包实际编译成功对象"收尾逻辑）重新生成恢复，`crt1.o`(1808B)/`libc.a`(1974998B) 确认存在，随后重新执行第 5 步四道门禁全部通过。此为 subagent 复核过程中的操作性插曲，非交付物本身缺陷；本人在 subagent 报告后又独立重跑了一遍全部 4 道门禁（`llvm-lit`/`run_differential.py`/`manifest_check.py`/`check_issues.py`），结果与 subagent 一致，确认最终状态干净。

**AC 结论**：无任何 finding 需要处置，完成区状态"已完成"与 subagent 判决一致。

## 架构师复核（ground-truth）

**独立验证方法**：不采信完成区/subagent 判决，从 git 状态开始逐项重跑。这是本轮收尾任务里方法论最讲究的一项（诚实的探索性验证，而非既定结论），复核重点放在"分类判断是否真的站得住"而非只重跑数字。

- `git status`（`.work/source/{llvm,qemu,musl}` + `~/DADAO-gem5`）：均干净；`.work/source/musl` 单线性提交 `9e51f0ed` 落在 `4741d4d1` 之上，无 rebase/reset 痕迹。
- 逐行读 `arch/dadao/arch.mak` diff：`-O0` 行确认删除，`-fno-optimize-sibling-calls` 行原样保留未动；`grep "optnone"` 确认 `mallocng/free.c`/`mman/mmap.c` 里只剩解释性注释，无实际 attribute 残留。
- **独立复现 patch 可重放性**：全新 `git clone` + `checkout --detach` 到裸 pin commit `0784374d` + 依次 `git am` 全部 9 条 patch（`0001`~`0009`）→ 全部干净应用；`diff -rq --exclude=.git` 重放树 vs 当前 `.work/source/musl` 工作树 → **零输出**（字节级一致；重放后的 commit hash 与实际 HEAD 不同属预期——`git am` 的 committer 时间戳不同必然导致 hash 不同，树内容一致才是真正要验证的东西）。
- **独立完整重跑全树构建**：`rm -rf .work/build/musl && make build-musl` → `build-musl: PASS`，`find ... -name '*.o' | wc -l` = **1170**，与完成区数字精确一致；额外用 `make -k -j1 lib/libc.a` 独立复测：**总失败 176、"undefined physical register" = 0**——与完成区表格逐位吻合，确认 DL-070a 的修复在去掉 `-O0` 后的全树范围内依然保持零回归。
- **抽查一条分类判断是否站得住**（不只信任务文件转述）：`musl-backend-assert-instrinfo-unreachable` 这条既有 issue 的**标题原文就点名 `legacy/daemon.c`**——独立读 `docs/issues.yaml` 确认，这条 issue 是 ML-010a（2026-07-17，`-O0` workaround 存在之前）发现并登记的，直接证实"去掉 `-O0` 后 `daemon.c` 重新失败 = 恢复到它本来的、一直存在的 open 状态，不是新缺陷"这个论断成立，不是事后编造的辩解。
- 全量 `llvm-lit tests/lit/E2E/` → **59/59**；`musl_e2e_exit.test` → PASS；`python3 tools/run_differential.py` → `AGREE(3-way)=200/gem5-SKIP=2/DIVERGE=0`，`Sail AGREE(4-way)=200`——与基线一致；`manifest_check.py`/`check_issues.py`（Open 24/Closed 31/Total 55）均 PASS。

**结论**：**ML-018a 验收通过**——这是一次真正诚实的探索性验证：没有预设"workaround 一定能去掉"的结论，用干净串行构建（先纠正了自己遇到的 `grep` shell 包装 + `make -j6` 目标发现不完全两个测量陷阱）拿到可信数字，对每一个净增失败逐文件核对错误签名+`docs/issues.yaml` 比对，找到"7 个是已知 issue 标题原文点名的原始触发文件（`-O0` 存在之前就登记）、4 个是同类别新触发文件、0 个是未知类别"这个结论后才做出"完全去掉"的决策，而不是反过来。顺带发现并修复了 `8ecf6f6e`/`4741d4d1` 两个此前从未导出的历史 commit（IN-004a 审计当时点名过这两个，本任务一并收尾）。musl `-O0` workaround 到此彻底清除，DL-070a 的修复得到全树规模的验证。
