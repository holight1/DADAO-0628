# DL-068b: 修复大端窄字节 load 偏移错误（重新下发，DL-068a 事故后）

**执行环境**: 本地 subagent（LLVM DAG combine 修复，大端字节序）

**状态**: 待执行

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
