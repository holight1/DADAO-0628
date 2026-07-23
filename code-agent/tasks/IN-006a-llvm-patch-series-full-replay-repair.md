# IN-006a：修复 LLVM patch series 从裸 pin 无法完整重放

日期：2026-07-23

## 状态

待处理。

## 背景

`docs/issues.yaml` 的 `llvm-patch-series-full-replay-corrupt-at-0005` 记录：
LLVM patch series 从 manifest pin
`ca7933e47d3a3451d81e72ac174dcb5aa28b59d1` 开始，0001～0004 可应用，
0005 `dadao-asmparser.patch` 在 line 447 被 `git am` 判定为 corrupt。
2026-07-23 架构师已在独立临时 clone 中再次复现。

## Ownership 与约束

- worker 只修改：
  - `components/llvm/patches/0005-dadao-asmparser.patch`
  - 本任务文件的完成区
  - 必要时新增一份 worker report 到 `docs/reviews/`
- 不修改 `.work/llvm` 当前源码、其它 LLVM patch、series、生产代码、测试、
  issues、roadmap、wiki 或其它 component。
- 先诊断 mbox/patch 格式根因；不得通过跳过 0005、放宽 apply 参数、改 pin、
  squash/rebase 历史或手工伪造“成功”绕过。
- 修复必须尽量小，只修补丁序列化/格式问题，不改变 0005 表达的源代码 tree。

## 目标

1. 精确定位 line 447 corrupt 的原因。
2. 修复 0005，使 `git am` 能从裸 pin 继续。
3. 从裸 pin 依次重放当前 series 的全部 48 条 patch。
4. 比较重放后的 tree 与 `.work/llvm` HEAD `4b812d2f...`，必须字节级一致
   （排除 `.git`）。
5. 运行 `scripts/manifest_check.py`；不得改变当前 component commit 或 series
   顺序。

## 验收

- 全量 48/48 `git am` 成功。
- 重放 tree 与当前 `.work/llvm` tree 一致。
- 0005 的语义 diff 在修复前后不变；完成区需说明验证方法。
- 由另一名独立 reviewer 复核后方可关闭相关 issue。
