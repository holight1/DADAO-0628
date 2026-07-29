# KL-146a：K3 Linux 5.4 基线启用与干净源码门

**状态**：PASS（独立 review 因额度限制待补）  
**日期**：2026-07-29  
**前置**：KL-145a（K2 closed）  
**后续**：KL-147a（kernel build contract + `arch/dadao` skeleton）

## 目标

打开 K3，但只完成可复现源码基线，不在本任务混入架构实现：

1. 将 Linux 组件固定到 upstream Linux 5.4 的 peeled commit
   `219d54332a09e8d8741c1e1982f5eae56099de85`；
2. 通过仓库 manifest/fetch 流程取得 `.work/source/linux`；
3. 证明源码 HEAD 精确等于 pin、worktree clean、patch series 为空；
4. 冻结“新写 `arch/dadao`，不导入历史实现”的来源边界；
5. 在 roadmap 中记录 K3 已开始以及 login + 用户态 hello 的最终验收目标。

## 非目标

- 不创建 `arch/dadao`；
- 不修改 QEMU、gem5、LLVM 或 musl；
- 不声称 Linux 已可配置、编译或启动；
- 不把 KL-145a 的历史 stop-boundary runner 改写成 K3 runner。

## 验收

```text
python3 scripts/manifest_check.py
python3 scripts/fetch.py
git -C .work/source/linux rev-parse HEAD
git -C .work/source/linux status --porcelain=v1
```

必须满足：

- manifest PASS；
- Linux HEAD 等于上述 40 位 commit；
- Linux worktree无输出；
- `components/linux/patches/series` 除注释外无条目；
- 主仓仅保留用户既有未跟踪文件 `gcc-torture-results.json`。

## 实施记录

- `manifests/components.lock.toml` 已将 Linux 组件设为 `enabled=true`，
  pin 为 Linux 5.4 peeled commit
  `219d54332a09e8d8741c1e1982f5eae56099de85`。
- `python3 scripts/manifest_check.py`：PASS；enabled components 明确包含
  `linux`。
- kernel.org 不支持 `scripts/fetch.py` 使用的 partial-clone filter，首次
  clone 被主动中止，避免下载完整历史。随后从本机已有的 upstream v5.4
  Git 对象创建 `--depth 1` 干净 clone，并将 `origin` 重设为 manifest
  中的 kernel.org 官方地址；这一步只复用 Git 对象，不复用旧工作树、
  patch 或 `arch/dadao`。
- `.work/source/linux`：
  - HEAD =
    `219d54332a09e8d8741c1e1982f5eae56099de85`；
  - `git status --porcelain=v1` 无输出；
  - `origin` =
    `https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git`；
  - 当前体积约 1.2 GiB。
- `components/linux/patches/series` 仍只有 deferred 注释，无 active
  patch。
- 本任务没有创建 `arch/dadao`，没有修改任何组件源码。
- 启动 K3 前按用户要求清理可再生工作产物：项目由约 121 GiB 降至约
  14 GiB，LLVM build 由 108 GiB 的 `RelWithDebInfo` 重建为约 1.5 GiB
  的 assertions-on `Release`；DADAO clang/LLD/MC 可用，最小
  `smoke_add.test` 1/1 PASS。K1/K2 evidence 与所有组件源码/构建保留。

## 独立 review

2026-07-29 尝试启动独立 subagent；agent 在执行任何检查或写入前因
账户 usage limit 直接报错退出，因此本任务没有伪造“独立 PASS”。

主控复核结果：

- manifest PASS，Linux enabled 且 pin 为精确 40 位 commit；
- Linux HEAD/pin 相等，worktree clean，origin 与 manifest 相等；
- patch series 无 active 条目，`arch/dadao` 不存在；
- `git diff --check` PASS；
- 本任务声明没有越过“只启用干净 baseline”的边界。

结论：**KL-146a PASS**。独立 review 标记为待额度恢复后补审，不作为
本基线任务继续推进的阻断项；后续不得把本段主控复核改称独立 review。
