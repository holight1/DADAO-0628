# ML-004d: 排查剩余 3 个 llvm-test-suite 独立 issue

**执行环境**: 本地 subagent（CodeGen/gem5 排查）

**状态**: 通过（架构师复核，★★ 全 E2E 54/54 = 100% 通过，含补关闭一个更早的老 issue）

**前置**：ML-004a/b/c 已完成，`tests/lit/E2E/llvm-test-suite/` 目录 20/20 全通过。ML-004b 扩充覆盖时另外发现的 3 个独立、尚未排查的失败用例仍是 open：`codegen-switch-dispatch-malign-in-callee`、`codegen-misha-sum-wrong-value-no-call`、`gem5-sign-conversions-backend-divergence`（均在 `docs/issues.yaml`）。

## ⚠️ 硬性约束（与 DL-068b/ML-004b/ML-004c 相同，必读）

**禁止对 `.work/llvm`（或任何 `.work/<component>`）做 `git rebase`/`git am` 重放整条历史/`git reset` 之类改写既有 git 历史的操作**。只允许在当前 HEAD 基础上做普通的、追加式的新提交 + `git format-patch` 生成新 patch 加入 series（参照 DL-065a/DL-066a/DL-067b/DL-068b/ML-004c 的模式）。若排查中怀疑 patch series 有问题，如实报告，不要自己动手"验证"或"重建"。

## 做什么

逐个排查 `docs/issues.yaml` 里这 3 个 issue（每条都有源码位置/复现指引，`.work/source/llvm-test-suite/SingleSource/` 下能找到原始测试源码）：

1. **`codegen-switch-dispatch-malign-in-callee`**：故障（MALIGN 0x81，双后端一致）发生在 switch-dispatch 的被调用函数内部，疑似跳转表相关。用 gem5 `--debug-flags=Exec` 或 `-print-after-all` MIR dump 定位具体故障指令/地址计算，确认是不是又是 GPRB 相关问题的另一种表现（ML-004c 修复后应该重跑确认这个还在不在——**先重跑一次看看是否已被 ML-004c 顺带修好**，若已经好了直接关闭 issue 并说明）。
2. **`codegen-misha-sum-wrong-value-no-call`**：host=1/dadao=2，热循环内无函数调用。同样先用 ML-004c 修复后的工具链重跑确认现状，再定位。
3. **`gem5-sign-conversions-backend-divergence`**：QEMU PASS/gem5 SIGABRT。先重跑确认现状，再用 gem5 `--debug-flags=Exec`/gdbstub 定位故障 PC。

对每一个：如果 ML-004c 已经顺带修好，如实关闭 issue 说明原因（不用重新排查）；如果依然失败，做真正的根因定位，能小范围安全修复就修（要有反汇编/运行时判别性验证），修复面大或不确定就如实记录、不强行修。

## 约束

- 不为了让某个用例过而打局部补丁或使用绕过手段。
- 每个 issue 的排查/修复相互独立，一个卡住不要阻塞其它两个的进度。
- 不回归：全 E2E（含 `syscall_hello.test` 已知无关失败）、四方 AGREE(3-way)=200/DIVERGE=0、Sail AGREE(4-way)=200。

## 验收（架构师亲跑）

```bash
cd ~/DADAO-0628 && ninja -C .work/build/llvm llc clang
llvm-lit tests/lit/E2E/ 2>&1 | tail
python3 tools/run_differential.py 2>&1 | tail -3
llvm-lit -v tests/lit/E2E/llvm-test-suite/ 2>&1 | tail -30
```

**判别强调**：对每个 issue 明确给出结论（已被 ML-004c 修好 / 定位到新根因已修 / 定位到根因但范围外未修 / 未能定位），不要笼统汇报"排查了但没结果"。

## 参考指针

- `docs/issues.yaml` 的三个条目（各自的复现描述）
- ML-004b/ML-004c 完成区（前两轮排查方法论、`--debug-flags=Exec` 定位手法）
- `.work/source/llvm-test-suite/SingleSource/`（原始测试源码）

—— 自审见 DS.md §自审流程同等标准（subagent 自己复核，逐条 finding + 判决）。**严格遵守不碰 patch/git 历史的约束**。

---

## 架构师复核（2026-07-16，ground-truth）：通过 —— ★★ 全 E2E 100% 通过

### 硬性约束遵守情况
- `.work/llvm` git log 确认干净 additive 提交（`d324a5db0956`，在 `ab11cbd8e94e` ML-004c 之上），无 rebase/am/reset。

### 独立验证
- 全新 `ninja` 重建；`llvm-lit tests/lit/E2E/`：**54/54 全部真 PASS**（含 `syscall_hello.test`——这是本 session 从很早期就开放的一个"无关既有缺陷"，从未被本轮任何任务当作目标，这次是真正的意外之喜）。
- `tests/lit/E2E/llvm-test-suite/`：23/23（20 既有 + 3 新增）。
- 四方 AGREE(3-way)=200/Sail AGREE(4-way)=200，不回归。`manifest_check.py`/`check_issues.py` 均 PASS。
- 代码审阅：`DADAOAsmBackend.cpp` 的修复方向是**删除一个此前（ML-003j/patch 0030）添加的、事后证明不健全的"同 section 快路径"优化**，改为始终走真实 ELF relocation（与早已验证过的跨 section/全局变量路径完全一致）——这是简化而非增加复杂度，对正确性是好事。`JUMP_PSEUDO_INDIRECT` 的修复严格镜像 `CALL_PSEUDO_INDIRECT`（DL-066a）的 rd2rb桥接scratch RB5 手法，一致性好。

### 遗漏补齐
subagent 报告里提到"顺带修复了 syscall_hello.test"，但只在对话报告里说明，未更新 `docs/issues.yaml` 里对应的老 issue `syscall-hello-write-output-missing`（这是本 session 很早期发现、非本任务分配范围内的 issue）——架构师已补充关闭，注明根因关联。

**判定**：通过，提交。★★ **全部 E2E 测试 100% 通过（54/54），无任何已知失败**——这是 DADAO-0628 项目自创立以来首次达成"零已知失败"的状态。
