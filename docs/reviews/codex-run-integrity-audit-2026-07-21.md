# codex 30+ 任务运行完整性审计（IN-004a）

日期：2026-07-22（复核对象：2026-07-18～2026-07-21 的 ML-014aa~ag / ML-016a~z /
ML-017a~d，60+ 任务文件与最终交接 `ML-017d-final-handoff-roadmap-20260721.md`）

审计性质：**纯只读**。全程只用 `git log`/`git show`/`git diff`/`git status`/
`git apply --check`/文件读取/`python3 tools/run_differential.py`（该脚本本身
是只读评测，不写回任何仓库文件）。未修改 patch、series、`.work/<component>`、
`~/DADAO-gem5`、`docs/issues.yaml`、`docs/issues-archive.yaml`、任何任务文件。

---

## 1. 可复现性缺口

### 1.1 LLVM：4 个未导出 commit（坐实，且是完整枚举）

```
$ git -C .work/source/llvm log --oneline f5a06de81358..HEAD
d3bd9c15434f DADAO: round frame size to ABI alignment
be99e5505abe [DADAO] Expand i1 sign extension
40bc313742b0 [DADAO] Map generic inline asm registers
10690fc4d40d [DADAO] Handle external symbols in AsmPrinter
```

`f5a06de81358` 正是 `components/llvm/patches/0041-*.patch` 的源 commit（已用
`ML-014ad` 正常导出），`.work/source/llvm` 当前 `git status --porcelain` 为空
（工作区干净）。这四个 commit **确实存在于活历史里，且是 `series` 最后一条之后
到 HEAD 之间的全部新增**，没有遗漏，也没有额外的第 5 个。

内容判断（读 diff + 对应任务文件 ML-016p/q/t/y 的完成区与独立 review）：四项
均为真实、通过独立 review 的 CodeGen 修复，不是实验性/失败尝试：

| commit | 对应任务 | 独立 review 结论 |
|---|---|---|
| `10690fc4d40d` | ML-016p | Accepted（`docs/reviews/ML-016p-independent-review-20260721.md`）|
| `40bc313742b0` | ML-016q | Audit-accepted-with-findings |
| `be99e5505abe` | ML-016t | Audit-accepted-with-findings |
| `d3bd9c15434f` | ML-016y→ML-016z（provenance 修复）| Audit-accepted-with-findings |

**结论**：这四个 commit 需要执行（架构师决定时机，本审计不执行）：

```
cd .work/source/llvm
git format-patch f5a06de81358..d3bd9c15434f -o /tmp/out --start-number 42
# 生成 0042/0043/0044/0045，追加进 components/llvm/patches/series
```

因为 HEAD 已经指向 `d3bd9c15434f` 且工作区干净，这四个 commit **在 git 对象
层面是安全的**（可达、不会被 gc 回收）——风险是"缺失可复现性"，不是"数据丢失"。

### 1.2 gem5：2 个未导出 commit（坐实）

```
$ git -C ~/DADAO-gem5 log --oneline -20
c7e92c7f80 arch/dadao: unify SYS_brk base with ELF heap
e6a6b9cdc9 arch/dadao: back SYS_brk with MemState VMAs
6dd0d7c9f1 arch/dadao: back mmap arena with SE VMAs   ← components/gem5/patches/0012 的源 commit
```

`components/gem5/patches/0012-arch-dadao-mmap-arena-vma-backing-ML.patch` 的
`From` 行 hash 为 `6dd0d7c9f162fa4e414e8824f6129ff5c78a35ed`，与该 commit 完全
匹配（`git show 6dd0d7c9f1 --stat` 核对文件列表一致）。`git -C ~/DADAO-gem5
status --porcelain` 为空。`e6a6b9cdc9`/`c7e92c7f80` 是 series 之后到 HEAD 之间
**全部**新增 commit，没有遗漏。这两个 commit 属于 ML-014o/p 系列（gem5
SYS_brk/VMA backing），是真实修复，同样安全可达，只是未导出 `0013-*`/`0014-*`
patch。

### 1.3 QEMU：dirty 工作区 + 伪造 commit-hash 的 patch（坐实，且是本轮最高优先级问题）

```
$ git -C .work/source/qemu status --porcelain
 M target/dadao/cpu.c
 M target/dadao/cpu.h
$ git -C .work/source/qemu log --oneline -1
ac58f31 target/dadao: add mmap arena host backing (ML-014c)   ← 与 0018 patch 的 From hash 完全一致
```

`components/qemu/patches/0019-dadao-cfx-state-scaffold.patch` 的 `From` 行是
`0000000000000000000000000000000000000000`——不是真实 `git commit` 产生的
hash。已用只读方式验证该 patch 与当前 dirty 工作区**内容完全一致**：

```
$ cd .work/source/qemu && git apply --check --reverse \
    /home/holight/DADAO-0628/components/qemu/patches/0019-dadao-cfx-state-scaffold.patch
（exit 0，无输出——反向应用干净，说明 patch 内容与当前未提交 diff 逐字节一致）
```

这个改动来自 `KL-102b`（不属于 codex 的 ML-014/016/017 分支，是并行的 K1 kernel
bring-up 前置任务），任务文件明确记录"新增
`components/qemu/patches/0019-dadao-cfx-state-scaffold.patch` 及
`components/qemu/patches/series`"，`docs/reviews/KL-102b-independent-review-20260721.md`
也判定 Accepted，并且独立 review 在可复核命令里已经写了这条 `git apply
--reverse --check` 命令——说明 worker/reviewer 都**知道**这不是走 `git
commit`+`git format-patch` 的正规流程，而是直接从 diff 手写 patch header 并
伪造了全零 hash，但没有在 KL-102b 的完成区/review 里用醒目文字标注"这段代码从未
`git commit` 进 `.work/source/qemu`，工作区是唯一权威副本"这一事实——这正是
ADR-0002 明确列为 Rejected Legacy Behavior 的
「Treating a dirty generated source tree as the authoritative implementation」。

**恢复验证**：若这段改动被 `git checkout .`/`git clean -f` 之类命令误删，可以用
`git apply components/qemu/patches/0019-dadao-cfx-state-scaffold.patch`（在
`.work/source/qemu` 下，从 `ac58f31` 干净状态开始）完整恢复——已用 `--check
--reverse` 验证过字节级一致，是安全的。**但在恢复之前，这段代码始终只存在于
一份未提交的工作区 diff 里，只要有人在这份工作区上跑一次 `git commit -a`
之外的历史操作（`git checkout`、`git reset --hard`、`git clean`、甚至某个
任务脚本里的 `git stash` 忘记 pop），就会真实丢失，且丢失后除非有人记得
"哦对应 0019 patch"，否则不会意识到丢了什么。**

需要执行（架构师决定时机）：

```
cd .work/source/qemu
git add target/dadao/cpu.c target/dadao/cpu.h
git commit -m "target/dadao: add CFX state scaffold (KL-102b)"
git format-patch -1 -o /tmp/out    # 生成带真实 hash 的 0019，替换现有伪造版本
```

### 1.4 musl：见第 4 节（与 ML-014f 候选 patch 强相关，单独讨论更完整）

---

## 2. 四方差分基线偏移

### 2.1 复现架构师的观察

```
$ python3 tools/run_differential.py
=== AGREE(3-way)=200  AGREE(interp+QEMU, gem5-SKIP)=2  DIVERGE=0  HARNESS=0  QEMU-SKIP=0 ===
=== SAIL 4th column: AGREE(4-way)=200  Sail-SKIP(out-of-slice)=2  SAIL-DIVERGE=0 ===
```

与本 session 早前稳定的 `AGREE(3-way)=200 DIVERGE=0 HARNESS=6`（总覆盖 206）相比，
现在总覆盖是 202（200+2），HARNESS 从 6 归零，多出的 2 个变成
`AGREE(interp+QEMU, gem5-SKIP)`。

### 2.2 定位引入这个变化的具体 commit

```
$ git log --oneline --all -- tests/vectors/isa/control-flow.yaml | head -1
b5b8c57 test: align control flow vectors with spec
```

`git log --oneline --all -- tools/run_differential.py` / `-- tools/validate_interp.py`
**没有**在这之后出现任何新提交——四方脚本本身没被改过，纯粹是向量数据变了。

`b5b8c57` 对应任务 **ML-015c（vector/spec alignment）**，改动只有
`tests/vectors/isa/control-flow.yaml`（42 insertions/25 deletions）：把之前
`status: active, expected_fault: ILLI` 的 4 条 `jump`/`call`/`ret`
encoding-only 记录改成 `status: deferred`，把 2 条 `ret`（RegRAS 冷栈）记录的
`expected_fault` 从 `ILLI` 订正为 `RASUF`（`spec.md §5.6`）并保留 `active`。
`tests/vectors/isa/*.yaml` 总条数不变（213→213），只是 `active`
207→202、`deferred` 6→11。

### 2.3 这是不是"新增了 2 条向量"

**不是**。总条数没变化，是**重新分类**：4 条从 active 移到 deferred（不再被
`run_differential.py` 计入任何桶——脚本对 `status=='deferred'` 直接
`continue`），2 条从"因为下游 halt 才产生的 ILLI trampoline 假象"订正为"能被
interp 精确建模的 RASUF"，因此从旧的 HARNESS 桶（`SKIP-harness`）变成新的
AGREE 桶。ML-015c 是**任务本身就是为了修正向量与 spec 的错配**，走了完整的
"Needs-fix→修订→Accepted" 两轮独立 review（`docs/reviews/ML-015c-independent-review-20260721.md`
与 `-r2-`），不是顺手在无关任务里悄悄改的。

### 2.4 gem5-SKIP=2 的根因：一处过时但仍生效的适配器规则，不是 gem5 语义回归

用最小脚本单独跑这 2 条 RASUF 向量（只读，未改任何文件）：

```
control-flow.yaml[34] ret status=active class=boundary
  interp=PASS/fault RASUF
  qemu=PASS/RASUF (expected)
  gem5=SKIP-unsupported/ret: not in gem5 G1 coverage
```

根因在 `tests/scripts/run_gem5_test.py:104-106`：

```python
if case.get('mnemonic') in ('jump', 'call', 'ret') \
        and case.get('expected_fault') is not None:
    return None
```

这条规则和其上方注释（"The 6 HARNESS control-flow abstains ... are SKIPped
here"）是 **DG-004d 时代**写的，当时全部 6 条 jump/call/ret+fault 向量都确实
是"下游 halt 产生的 trampoline 假象"，gem5 SKIP 是对的。ML-015c 把其中 2 条
订正为真实的 RASUF 语义向量后，这条按 mnemonic+expected_fault blanket 判断的
规则**没有同步更新**，导致这 2 条本该能测的向量继续被结构性 SKIP——而
`docs/issues-archive.yaml` 的 `rasof-rasuf-exit-code-unpinned` 条目明确记录
gem5 **已经**正确实现 RASUF（`DL-057b`：「架构师独立复跑：QEMU+gem5 各
RASUF=133/RASOF=132」），所以这不是 gem5 真的不支持 RASUF，是**这个单指令
差分 harness 的通用 builder 函数太粗粒度**，把"gem5 不支持"和"gem5 支持但
这个 builder 没跟上向量订正"混为一谈。

### 2.5 是否被记录

- QEMU-only 的 202/11 计数**有**被记录（`ML-015d`/`ML-015e` 任务文件都写了
  `active=202 deferred=11`，并各自有独立 review Accepted）。
- 但 `tools/run_differential.py`（四方差分脚本，本项目"基线不能无声变化"这条
  验收标准真正盯的指标）**从未在 ML-015b 之后的任何任务或 review 文件里被
  实际运行过一次**（`grep -rl "run_differential" code-agent/tasks/ML-01[5-7]*.md
  docs/reviews/ML-01[5-7]*.md` 零命中）。也就是说 ML-015c 改完向量之后，直到
  这次架构师独立抽查为止，没有人真正确认过这次改动对四方差分总数/gem5
  覆盖率的连锁影响，`gem5-SKIP=2` 这个新状态没有出现在任何任务文件或
  `docs/issues.yaml`/`docs/issues-archive.yaml` 里。

### 2.6 结论

向量本身的修改（ML-015c）是合规的、经过独立 review 的语义修正，**不违反**
"基线不能在非语义相关任务里发生变化"——它就是语义相关任务本身。但它的一个
真实副作用（gem5-SKIP 从 0 变 2，且根因是适配器代码的粗粒度判断而非真实
gem5 缺陷）**没有被任何后续任务验证或记录**，属于监督缺口，不属于向量修改
本身违规。

---

## 3. puts/stdout 阻塞现状复核

独立重新读取 `/tmp/ml-017c-targeted-partial-archive-qemu-20260721/runtime/`
下的原始产物（该目录仍然存在，见第 5 节），不采信文档转述：

```
$ cat runtime/puts_probe/qemu.stdout
QEMU 10.0.0 monitor - type 'help' for more information
(qemu)                       ← 无 puts 输出
$ cat runtime/puts_probe/qemu.rc
rc=42

$ cat runtime/puts_probe/gem5.stdout
...
SIM_START
SIM_END: trap-exit code=42   ← 无 puts 输出

$ cat runtime/puts_errno_bypass/qemu.stdout
QEMU 10.0.0 monitor - type 'help' for more information
(qemu) PUTS_ERR_ERRNO_NONZERO
$ cat runtime/puts_errno_bypass/gem5.stdout
...
SIM_END: trap-exit code=42
PUTS_ERR_ERRNO_NONZERO
```

对应源码（`inputs/puts_errno_bypass.c`）确认这是真实探针：调用
`puts("ML-017c puts errno")` 后读 `errno`，若 `rc<0` 且 `errno!=0` 才输出
`PUTS_ERR_ERRNO_NONZERO`。两个后端都输出了这个 marker，与文档转述完全一致。
文件 mtime 为 `2026-07-21 22:xx`，与任务日期吻合，非陈旧遗留数据。

**结论：ML-017d 关于 puts 在两后端均无 marker、errno 非零的结论目前依然成立，
是可独立复核的真实结果，不是过时转述。**

---

## 4. musl 侧候选 patch（ML-014f）现状

```
$ git -C .work/source/musl log --oneline -3
4741d4d1 dadao: make mallocng public entry point extractable
8ecf6f6e dadao: build mmap and mallocng free at O0 for ML-014f
5fb13ddb dadao: restore RB-bank pointer calling convention (ML-013a, DL-069a follow-up)  ← 0006 patch 源 commit
$ git -C .work/source/musl status --porcelain   （空，工作区干净）
```

两个 commit 的实际内容：

- **`8ecf6f6e`**（2026-07-18 13:45，ML-014f 阶段产生）：
  - `arch/dadao/arch.mak` 追加 **`CFLAGS_AUTO += -O0`**（作为最终赋值，覆盖
    全部 DADAO musl 对象的优化级别，不只两个文件）；
  - `free.c`/`mmap.c` 给 `free`/`__mmap` 加 `optnone`。
  - 这就是 ML-014f 任务文件中提到的"候选 0007 patch"的核心内容（任务文件
    `ML-014f-musl-malloc-e2e-resume.md` 完成区第 77-85 行原文描述与此完全对应）。
- **`4741d4d1`**（2026-07-18 15:01，同一天但在 ML-014f 判定 Blocked 之后）：
  给 `mallocng/malloc.c` 加一个不走 `glue.h` 命名空间的强符号 `malloc()`
  入口，让静态链接能提取 mallocng 而不是停在 weak `lite_malloc`。**这不是
  ML-014f 原始候选 patch 的一部分**，是同一天稍晚追加的第三个改动，同样从未
  导出成 `0007-*` patch。

**这两个 commit 是否已经不只是"候选"，而是被后续所有 ML-016/017 任务默默当成
基础状态在用**：

```
$ grep -rn "4741d4d1" code-agent/tasks/ML-016s*.md code-agent/tasks/ML-017a*.md \
    docs/reviews/ML-016s*.md
ML-016s: 新 source commit 为 4741d4d1105849adf551a7998503866ed4f8b961
ML-017a: isolated musl | commit 4741d4d1105849adf551a7998503866ed4f8b961
docs/reviews/ML-016f-isolated-musl-clean-rebuild-20260721.md:
  隔离 source 是当前 musl checkout 的提交 4741d4d1105849adf551a7998503866ed4f8b961
```

provenance（commit hash）**是透明披露的**，不是隐瞒；但没有任何一份 ML-016/017
文档明确指出"这个 commit 包含一个来自已判定 Blocked/Not-Accepted 的 ML-014f
任务的、覆盖全项目的 `-O0` 编译选项变更"这一事实，也没有讨论过是否应该保留。

**这件事的分量**：ML-017a 最终矩阵（`docs/reviews/ML-017a-post-frame-musl-object-matrix-20260721.md`
第 78/90 行）显示 **"machine verifier: undefined physical register" 簇仍有
16 个失败对象，整个 ML-016/017 全程没有变化（16→0→16，即全程未修复）**。而
`ML-014f-musl-malloc-e2e-resume.md` 原文明确记录：这正是 `-O2` 下寄存器分配器
针对 `$rb31` 的 verifier 崩溃，`-O0` 是绕开它的唯一已知手段。`ML-016j`（RB31
pointer-return repro）进一步确认这个崩溃与 sibling-call/tail-call 优化相关
（对比 O0 与 O3 的行为差异）。也就是说：

**当前"最终 1166/181 object matrix"这个贯穿 ML-016s~ML-017c 全部报告的核心
数字，事实上依赖于一个从未被正式采纳（ML-014f 判定 Blocked/Not Accepted）、
从未导出进 `components/musl/patches/series` 的、覆盖全项目的 `-O0` 编译选项
覆盖。如果有人从官方 `components/musl/patches/series`（0001-0006，止于
`5fb13ddb`，仍是 `-O2`）干净重放，很可能无法复现 1166/181，"undefined
physical register"簇的失败数会明显更多（该 bug 本身仍未修复，只是被 -O0
全局绕开）。** 已确认 `docs/reviews/ML-017d-final-handoff-roadmap-20260721.md`、
`code-agent/tasks/ML-017d-final-handoff-roadmap.md`、
`docs/reviews/ML-017d-independent-review-20260721.md` 三份文件都**没有**提到
`-O0`/`CFLAGS`/`arch.mak`/`optnone` 中的任何一个词——这是一个应该在最终交接
里显式声明的前提条件，但没有声明。

**建议（只分析不执行）**：

1. 不建议直接撤销回 `5fb13ddb`——`8ecf6f6e`/`4741d4d1` 是后续 60+ 任务实际
   测量所基于的真实状态，撤销会让 ML-016/017 全部数字失去可复现的起点。
2. 应该做的是**在最终交接文档里补一条明确声明**："当前 `1166/181` 矩阵基于
   musl `4741d4d1`，其中包含未导出的、来自已判定 Blocked 的 ML-014f 的全项目
   `-O0` workaround；官方 patch series 重放（`-O2`）预期会有更多
   `undefined physical register` 失败，且该 bug 本身仍未修复。"
3. 长期应该走 ML-014ad 那样的"导出+scope-limited 独立 review"流程，把
   `8ecf6f6e`（-O0 workaround，作为已知的临时性后端 bug 绕过手段，标注清楚
   何时可移除）和 `4741d4d1`（malloc 入口点，看起来是一个独立、良性、值得
   长期保留的构建修复）分别导出为 `0007-*`/`0008-*`，而不是继续放在未导出的
   git 历史里被动依赖。

---

## 5. 任务文件卫生问题

### 5.1 重复/别名任务文件

```
$ ls code-agent/tasks/ML-01[4-7]*.md | sed -E 's/^.*(ML-0(14|15|16|17)[a-z]+)-.*/\1/' \
    | sort | uniq -c | sort -rn | head -3
      2 ML-016w
      1 ML-017d
      1 ML-016z
      ...
```

`ML-016w` 是**唯一**一处编号重复。`ML-016w-malign-runtime-consistency-audit-20260721.md`
（278 字节）内容为：

```
# ML-016w 索引别名
Canonical task file: ML-016w-malign-runtime-consistency-audit.md
The dated path is an index alias; completion and review records are
maintained in the canonical adjacent task file and docs/reviews/.
```

这是一个明确标注自己是"索引别名"的 stub，指向真正的 7.1K 内容文件，**没有
内容冲突**——不是"两份内容矛盾的任务文件"，是命名习惯从"无日期后缀"过渡到
"带日期后缀"时留下的一个转发桩。**无功能影响，纯风格/卫生问题**，建议后续
清理时直接删除这个 stub（0 字节损失，因为规范内容都在别处）。

### 5.2 "字母叠字母"命名（ML-014aa~ag）的排序歧义

不是无中生有——用实际 `sort` 复现：

```
$ echo -e "ML-014a-musl-e2e-malloc-printf.md\nML-014aa-...\nML-014ag-...\nML-014b-..." | sort
ML-014aa-dual-large-main-entry-isolation.md
ML-014ag-knowledge-graph-update.md
ML-014a-musl-e2e-malloc-printf.md      ← 原始里程碑任务被排到 aa/ag 之后
ML-014b-mmap-backing-recon.md

$ locale
LANG=en_US.UTF-8
```

本机默认 `en_US.UTF-8` locale 下，`ls`/`sort` 会把 `ML-014a-musl...`（原始、
必须"保持不动"的里程碑任务）排在 `ML-014aa`~`ML-014ag`（七个衍生子任务）
**之后**；只有强制 `LC_ALL=C` 才会按预期把 `ML-014a-` 排在 `ML-014aa` 之前。
这是一个真实、可复现的浏览/排序陷阱：有人用默认 `ls code-agent/tasks/ML-014*`
粗看一眼，容易把 aa~ag 误认为是 ML-014a 之前的准备工作，而不是它的后续
衍生任务。**这是排序/可发现性问题，不是内容冲突或编号真实碰撞**——没有发现
`ML-014aa` 与其它已有任务编号有语义/内容层面的冲突。建议：以后新增子任务
用 `ML-014-14`/`ML-014_2a` 之类不含纯字母尾缀延伸的编号，避免同类 locale
排序问题；当前已存在的 aa~ag 不需要重命名（重命名成本 > 收益，且无实质歧义）。

### 5.3 `/tmp/ml-0xxx-.../` 证据持久性

**架构师的假设（"这些临时目录大概率已经不存在"）经核实是错误的**：

```
$ find /tmp -maxdepth 1 -iname "ml-01*" -type d | wc -l
29
```

从 `ml-016a` 到 `ml-017c` 几乎每一个任务的证据目录**目前仍然存在**，且抽查
`ml-017c` 目录下的 `puts_probe`/`puts_errno_bypass` 原始 stdout/rc/argv 内容
与任务文档转述完全一致（见第 3 节），文件 mtime 与任务日期吻合，不是巧合
残留的旧数据。

**但这不代表证据链是安全的**：这些目录能存活到现在，纯粹是因为这台机器/
容器从 2026-07-18 到审计当天没有重启、没有被清理任务扫过 `/tmp`。这是
run-to-run 偶然性，不是设计保证——`/tmp` 在多数环境里会在容器重启或系统级
清理时被清空，而这 60+ 个任务的"完成区"里引用的所有原始命令输出、hash、
disassembly 全部只存在于 `/tmp`，仓库里的 task md/review 只有转述和摘要。
**如果现在做一次容器重启，这条证据链就会永久断裂，且断裂后不会有任何机制
提醒——正确的表述是"当前证据链完整且已独立验证，但持久性依赖于环境侥幸，
是一个应尽快消除的风险，不是已经发生的问题"。**

---

## 6. 开放式扫描

系统性过了 ML-014aa~ag（7 个）、ML-016a~z（26 个）、ML-017a~d（4 个）共 37
个任务文件的完成区/审阅记录，加上两份 30-task 台账（`ML-014-30-task-run-20260718.md`、
`ML-016-30-task-run-20260721.md`）。发现：

1. **独立 review 存放位置不统一，但内容确实存在（此前的"缺失"疑虑是假阳性）**。
   ML-014aa~ag 系列把 review 直接嵌在任务 md 自己的 `### Independent review`
   小节里（不落单独 `docs/reviews/*.md` 文件）；ML-016/017 系列落单独文件，但
   文件名不完全统一——多数是 `<id>-independent-review-20260721.md`，但
   `ML-016b`/`ML-016d` 等是 `<id>-<slug>-20260721.md`（标题内是"独立 review"，
   文件名不含"review"字样），还有 `<id>-worker-report-20260721.md` 与
   `<id>-independent-review-20260721.md` 成对出现的模式。抽查内容（如
   `ML-016b-musl-output-api-linkability-20260721.md`）确认标题、正文都明确
   自称独立 review，**不是缺失，是命名规范不统一**，建议以后统一成
   `<id>-independent-review-<date>.md`。

2. **worker/reviewer 用不同人名署名，抽查内容显示确有实质性差异**（不是
   纯粹换个署名的自我复核）：抽查 `ML-016p`（AsmPrinter 修复，Accepted）
   的 worker 报告与独立 review 文件行数分别为 91/63 行，内容结构不同；
   `ML-015c` 的独立 review 走了两轮（首轮 Needs-fix→修订→Accepted），说明
   至少这次 reviewer 真的发现了问题并要求返工，不是走过场。**受限于审计
   方式（无法从外部核实两次 Task 调用是否为真正独立的 subagent 进程），
   本审计只能在内容层面确认"读起来像独立审查、且至少一次真的打回过"，
   不能给出"绝对是不同进程"的证明**——如实说明这是本审计方法论的边界，
   不是可以证伪或证实的点。

3. **验收标准放宽的唯一实例，且已被记录**：ML-015c 把 4 条向量从
   `active`（会被 harness 判 PASS/FAIL）改成 `deferred`（不计入任何桶）。
   这确实是"验收范围收窄"，但原因写得很清楚（"当前 harness 没有
   encoding-only non-executing mode"），且经过两轮独立 review 确认没有
   借此把一个错误测试悄悄改成通过——不属于"未被记录的放宽"。

4. **patch/series/git commit 步骤被跳过的其它实例**：除第 1 节列出的
   llvm(4)/gem5(2)/qemu(dirty 1) 之外，musl 的 `8ecf6f6e`/`4741d4d1`
   （第 4 节）是第四类实例，且是唯一一类"已知晓依赖关系但从未在最终文档
   中声明"的情形（llvm/gem5/qemu 三类至少在各自任务文件里对"未导出"这件
   事本身有清楚记录，只是没做导出动作；musl 这个是连"这个依赖关系值得
   记一笔"都没有意识到）。

5. **没有发现**：`|| true`、忽略 exit code、单后端顶替双后端断言、手搓汇编
   替代 CodeGen 产物、编辑或关闭原始 `ML-014a-musl-e2e-malloc-printf.md`
   （该文件截至审计时仍是 git 未跟踪状态，内容与此前读取一致）、`docs/issues.yaml`
   /`docs/issues-archive.yaml` 被本轮任何 commit 触碰
   （`git log b5b8c57~60..HEAD -- docs/issues.yaml docs/issues-archive.yaml`
   零命中，最后一次改动是本轮开始前的 `e359bf4`）。

---

## 分级处置建议清单

### 必须立即处理

1. **`.work/source/qemu` 的未提交 CFX scaffold 改动**：执行
   `git commit` 落地 + 用真实 hash 重新 `git format-patch` 替换现有
   `0019-dadao-cfx-state-scaffold.patch`（该文件当前 `From` 是全零伪造
   hash）。这是唯一有真实、非理论性数据丢失风险的项——任何一次
   `git checkout`/`git clean`/`git reset --hard`/忘记 `pop` 的 `git stash`
   都会真实抹掉这段代码，且抹掉后除非有人记得对应 0019 patch，不会意识到
   丢了什么。（已验证可用 `git apply` 该 patch 完整恢复，但恢复不能替代
   "先提交"这个根本修复。）

### 应该处理但不紧急（工程债务，无数据丢失风险）

2. 导出 LLVM 4 个未导出 commit（`10690fc4d40d`/`40bc313742b0`/`be99e5505abe`/
   `d3bd9c15434f`）为 `components/llvm/patches/0042~0045`，追加 series——
   commit 本身安全（已在 HEAD 可达历史里），纯粹是复现性缺口。
3. 导出 gem5 2 个未导出 commit（`e6a6b9cdc9`/`c7e92c7f80`）为
   `components/gem5/patches/0013~0014`，追加 series——同上，commit 安全。
4. 在最终交接文档（或后续任务）里补一条明确声明：当前 `1166/181` musl
   object matrix 依赖 musl `4741d4d1`，其中含未导出、来自 Blocked 状态
   ML-014f 的全项目 `-O0` CFLAGS 覆盖，官方 patch series（`-O2`）重放预期
   会有更多 `undefined physical register` 失败，该簇本身全程未修复
   （16→0→16）。之后视情况把 `8ecf6f6e`（workaround，标注临时性）与
   `4741d4d1`（良性构建修复）分别导出为 `0007-*`/`0008-*`。
5. 把 `gem5-SKIP=2` 的根因（`tests/scripts/run_gem5_test.py:104-106` 的
   blanket 判断规则对 ML-015c 订正后的 2 条 RASUF 向量失效）记录进
   `docs/issues.yaml` 或专门任务，说明这不是 gem5 语义回归（gem5 已经
   在 DL-057b 里证明支持 RASUF），只是差分 harness 适配器代码没跟上向量
   订正；同时把这一发现同步进 `run_differential.py` 头部注释或
   `docs/adr/0009`/`0010` 相关文档,避免以后有人误以为 gem5 出现了真的
   语义回归。
6. 统一 `docs/reviews/` 独立 review 文件命名（部分为
   `<id>-independent-review-<date>.md`，部分为 `<id>-<slug>-<date>.md`），
   降低未来审计时的检索成本。
7. 把仍在 `/tmp/ml-01[4-7]*` 的证据目录搬进仓库内某个明确的
   非-git-tracked-但受控的位置（或至少打包归档），消除当前"证据链完整性
   纯靠环境侥幸未重启"的风险——目前证据是完整的，但没有任何机制保证它
   明天还在。

### 无需处理（虚惊一场/风格问题，不影响功能）

8. `ML-016w` 的重复文件：确认是唯一一例，且是明确标注的索引别名 stub，
   无内容冲突，无功能影响；可在下次任务文件清理时顺手删除，不必单独立项。
9. `ML-014aa~ag` 字母叠字母命名：确认在 `en_US.UTF-8` locale 下与
   `ML-014a` 存在真实的 `ls`/`sort` 顺序颠倒，但**没有**发现内容冲突或与
   其它已用编号的真实碰撞，纯粹是浏览时的排序陷阱；不建议重命名现有文件
   （成本大于收益），仅建议未来新编号避免这种后缀模式。
10. ML-014aa~ag 独立 review 嵌在任务 md 内、不落单独 `docs/reviews/` 文件：
    只是与 ML-016/017 系列不同的归档习惯，内容真实存在且可核实，不是缺失。
11. 验收标准放宽（ML-015c 向量 active→deferred）：有明确 spec 依据、两轮
    独立 review、任务文件如实记录计数变化，符合项目"不擅自削弱断言"的
    要求，不算违规放宽。
