# DL-068b: 修复大端窄字节 load 偏移错误（重新下发，DL-068a 事故后）

**执行环境**: 本地 subagent（LLVM DAG combine 修复，大端字节序）

**状态**: 通过（架构师复核，含额外关闭一个同根因 issue）

**前置**：`code-agent/tasks/DL-068a-bigendian-narrowload-mask-fix.md`（原任务，含完整根因分析、反汇编证据、验收标准——**直接读那份文件的"现象"和"做什么"两节，本文件不重复**；该任务因 subagent 越界+触发账号限额中止，未完成实际修复，完成区记录了事故经过）。issue `codegen-global-byte-mask-load-wrong-endian-offset`（`docs/issues.yaml`）仍 open。

## ⚠️ 本次重新下发新增的硬性约束（最高优先级，必读）

上一轮（DL-068a）subagent 在排查过程中偏离任务范围，尝试用 `git am` 从零重放整条 patch series 重建 `.work/llvm` 的 git 历史，过程中删除/改写了此前已验证过的真实代码（clang DADAO 集成文件、`DADAOISelDAGToDAG.cpp`），随后触发账号周使用限额被中止，架构师发现一个后台 `ninja` 构建正准备用这份退化源码替换掉正常工作的 `clang`/`llc` 二进制，及时 kill 掉并用 `git reset --hard` 恢复到已验证好的 commit。

**本次任务严格禁止**：
- 禁止对 `.work/llvm`（或任何 `.work/<component>`）做 `git rebase`/`git am` 重放整条历史、`git reset`（对已有提交之外的操作）之类会改写既有 git 历史的操作。
- 禁止"从零重建 patch series 可复现性"之类的验证性大动作——这不是本任务的目标，如果怀疑 patch series 有问题，**如实报告给架构师，不要自己动手验证/修复**。
- 只允许：在当前 `.work/llvm` working tree 现有 HEAD 基础上直接改源码文件、编译、测试，改完后用 `git commit`（普通的、追加式的新提交，不 amend、不 rebase）记录改动，然后 `git format-patch` 生成新的 patch 文件加入 `components/llvm/patches/series`（这是本仓库一贯的、唯一正确的 patch 落地方式，参照 DL-065a/DL-067b/DL-066a 等已有提交的模式）。
- 若发现任何情况让你想要"重建"、"从零验证"、"清理历史"——**停下来，在完成区如实报告发现了什么、为什么想这么做，不要自己执行**，交给架构师决定。

## 做什么

见 `DL-068a-bigendian-narrowload-mask-fix.md` 的"做什么"一节（4 个步骤：debug 追踪定位具体 combine、修复字节偏移计算、判别性验证、回归 ML-004a 跳过的 5 个测试）。约束和验收标准同样沿用该文件对应章节，本文件只新增上面这条硬性约束。

## 参考指针

- `code-agent/tasks/DL-068a-bigendian-narrowload-mask-fix.md`（完整背景、根因分析、反汇编证据、做什么/约束/验收/参考指针——全部直接复用）
- `~/.claude/projects/-home-holight/memory/feedback_subagent_scope_drift_git_history.md`（若能读取——上一轮事故的完整记录，理解为什么这次加了这条约束）

—— 自审见 DS.md §自审流程同等标准（subagent 自己复核，逐条 finding + 判决）。**必须验证修复后的值真正正确**；**必须严格遵守上面的 git 历史操作禁令**。

---

## 架构师复核（2026-07-16，ground-truth）：通过

### 硬性约束遵守情况
- 独立核对 `.work/llvm` git log：`778e62ed55f0`（本次修复）→`840d71cc67f1`（DL-065a，恢复点）→... 链条完整，普通 additive 提交，无 rebase/reset/am 痕迹。**本次严格遵守了不碰 patch 历史的约束**。

### 根因更正（比任务原始假设更准确）
任务原本假设根因在 narrow-load DAG combine 的字节偏移计算。subagent 用 `-debug-only=dagcombine` + MIR dump 证明**该假设不成立**——combine 和 `isBigEndian()` 查询全部正确，MIR 里 `@acc+3` 地址计算完全正确；真正的 bug 在更下游的 `DADAOAsmPrinter::lowerToMCInst` 的 `MO_GlobalAddress` 分支——只用 `MO.getGlobal()` 建 `MCSymbolRefExpr`，完全丢弃 `MO.getOffset()`。诊断更精确、修复面更小（AsmPrinter 一处，非 DAG combine 通用代码），风险更低。

### 独立验证
- diff 审阅：`MO_GlobalAddress` case 改为 `MO.getOffset()!=0` 时用 `MCBinaryExpr::createAdd` 包一层，干净、局部。
- 全新 `ninja` 重建，独立复现最小用例（`return acc & 0xFF;`）在 QEMU 返回 5（正确）。
- **额外发现**：这与更早的独立 open issue `codegen-global-addr-const-offset-dropped`（DL-067b 探针设计时发现，`*(buf+3)` 读到 `buf[0]`）是**同一根因**——用该 issue 的原始复现代码独立验证，DL-068b 修复后返回正确值 4。已一并关闭该 issue（原任务只知道自己被指派修的那个 issue，不知道有这个更早的同根因记录）。
- E2E 33/34（同一已知无关的 `syscall_hello.test` 失败）、四方 AGREE(3-way)=200/Sail AGREE(4-way)=200，不回归。
- `issues.yaml` 校验通过（`check_issues.py` PASS，无重复 key）。

### ML-004a 遗留 5 个测试的复验结果（如实记录，未强求全过）
- 1/5（`2006-02-04-DivRem.c`）现在双后端真正跑通。
- 4/5（`crc8.le`/`crc16.be`/`popcount-clz-ctz`/`divtest`）仍失败，但换成了**另一种独立故障模式**（3 个撞 MALIGN 退出码 0x81 双后端一致、1 个双后端一致但值错）——与本次修的 bug 无关，留给 ML-004b 专门排查。

**判定**：通过，提交。

**下一步**：ML-004b——针对这 4 个仍失败的用例做根因排查（MALIGN 是否合法 spec 行为 vs 真 bug；"值错但双后端一致"是否是另一个独立 miscompile），扩大 llvm-test-suite 覆盖，产出第一轮 pass 报告。
