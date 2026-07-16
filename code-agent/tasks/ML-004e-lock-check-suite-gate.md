# ML-004e: 把 llvm-test-suite 目录锁进 `make check-suite` 回归门禁

**执行环境**: 本地 subagent（构建脚本/门禁基础设施）

**状态**: 通过（架构师复核，确认现状已覆盖，未新增冗余门禁）

**前置**：ML-004a-d 已完成，`tests/lit/E2E/llvm-test-suite/` 目录 23/23、全 E2E 54/54 全部真通过（零已知失败）。

## ⚠️ 硬性约束（必读）

**禁止对 `.work/llvm`（或任何 `.work/<component>`）做 `git rebase`/`git am` 重放整条历史/`git reset` 之类改写既有 git 历史的操作**。本任务大概率不需要碰 `.work/llvm` 源码（纯构建脚本/文档任务），若排查中发现需要改 CodeGen，如实报告，不擅自动手。

## 背景

`tests/lit/E2E/llvm-test-suite/` 现在已经是 `tests/lit/E2E/` 的子目录，`llvm-lit tests/lit/E2E/` 本身已经会跑到它（前面 ML-004a-d 的验收命令一直是这么跑的）。本任务不是要新建一个"额外"的 lit 目录扫描机制，而是确认/巩固这条路径在**日常回归**里稳定生效，并补充文档说明，防止未来有人误以为 `llvm-test-suite/` 子目录是"实验性、可以不管"的东西。

## 做什么

1. 确认 `Makefile`/CI 或任何现有的"跑 E2E"入口（无论是 `make check` 还是别的）是否已经覆盖 `tests/lit/E2E/llvm-test-suite/`（大概率已经覆盖，因为它就是 `tests/lit/E2E/` 的子目录，lit 默认递归）。如果发现某个门禁命令用了排除模式（比如某处 glob 只匹配平铺的 `.test` 不递归子目录），修正它。
2. 在 `docs/development-roadmap.md`/`docs/adr/0012-test-tiering-strategy.md` 或者更合适的位置（自行判断），把"`llvm-test-suite/` 子目录 = 常规 E2E 回归的一部分，不是实验性内容"这件事写清楚，附上当前 23/23 的状态和达成日期。
3. **不要**新建一个独立的 `check-suite` Makefile target 如果它只是重复已有的 `llvm-lit tests/lit/E2E/`——除非现有门禁真的漏了这个子目录，否则不需要额外machinery。如果调查后发现现状已经完全覆盖（最可能的结果），如实说明"已确认覆盖，无需新增"即可，不要为了"完成任务"硬造一个不必要的新脚本。

## 约束

- 这是一个轻量级、偏文档/确认性质的任务，不是要新写复杂脚本。
- 若发现现有门禁确实有缺口需要小的脚本改动，改动要精简（几行内解决），不要新建整套并行的测试基础设施。

## 验收（架构师亲跑）

```bash
cd ~/DADAO-0628
llvm-lit tests/lit/E2E/ 2>&1 | tail   # 确认仍然 54/54（或后续增加用例后的新总数）
make check 2>&1 | tail -5             # 确认 make check 本身不受影响（llvm-test-suite 目录不该进 make check，那是结构性检查，E2E 走独立的 llvm-lit 命令）
```

## 参考指针

- `docs/adr/0012-test-tiering-strategy.md`（测试分层策略，T2 全 E2E + 四方差分）
- ML-004a-d 完成区（`tests/lit/E2E/llvm-test-suite/` 目录的建立过程）
- `Makefile`（现有 `check`/其它 target 的定义，判断是否需要小改动）

—— 自审见 DS.md §自审流程同等标准（subagent 自己复核，逐条 finding + 判决）。**如实报告现状是否已覆盖，不要为了有产出而制造不必要的新脚本**。

---

## 架构师复核（2026-07-16，ground-truth）：通过

调查结论正确：`tests/lit/E2E/llvm-test-suite/` 是 `tests/lit/E2E/` 的普通子目录，lit 默认递归，唯一 E2E 入口 `llvm-lit tests/lit/E2E/` 已经覆盖（独立验证 54/54）；仓库内无其它用不递归 glob 单独跑 E2E 的 CI 脚本；`make check` 本身不含 E2E（结构性检查），不受影响。正确判断"无需新增机制"，只补充了 ADR-0012 D4 + development-roadmap.md 的说明性文字，没有制造冗余脚本——符合任务对"轻量确认性质"的要求。

**判定**：通过，提交。
