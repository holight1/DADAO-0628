# IN-006a：修复 LLVM patch series 从裸 pin 无法完整重放

日期：2026-07-23

## 状态

部分完成（Accepted-partial）；0005 已修，完整重放被独立损坏的 0006 阻塞。

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

## Worker 完成区（2026-07-23）

### 状态

**阻塞，未完成验收。**

0005 的 corrupt/preimage 问题已在 ownership 内修复，并从裸 pin 使用 plain
`git am` 成功应用；但完整重放在 0006 自身的 mbox 格式错误处停止，因此只
完成 5/48。未比较 48 条重放最终树与 `.work/llvm` HEAD，也不得关闭 issue。

### 0005 根因与修复

- 原 line 447 所在 CMake hunk 声明 `-3,11 +3,13`，实际新侧只有 12 行；
  丢失的是其 postimage 所要求的
  `tablegen(LLVM DADAOGenMCCodeEmitter.inc -gen-emitter)`。解析器在读取下一
  个 hunk 头时仍等待第 13 行，因而报告 corrupt。
- 修复该处后又依次暴露两个同类序列化缺口：InstPrinter hunk 声明
  `14/14`、实际 `8/13`；新建 MCCodeEmitter 文件声明 77 行、实际 74 行。
- 依据 0005 原有 `index old..new` postimage、邮件统计及 `.work/llvm` 对应
  提交 `79e6b795...` 恢复缺失序列。当前 0001～0004 的实际 preimage 还比
  0005 声明 preimage 多一条 `DADAOInstrInfo.td` include、少文件末尾 `}`，
  因此在 0005 内做最小 preimage 适配，最终目标源码树不变。

语义目标验证方法：从 pin 重放 0001～0005 后执行
`git diff --exit-code HEAD 79e6b795...`，返回 0；两侧 tree id 均为
`9c62c5421eb1e9fc716b528e5304ce35d2166c9e`。原文件本身不可解析，故这里以
其原有 postimage hashes/对应历史 tree 作为“表达的源代码 tree”基准。

### 全量重放阻塞

在独立临时工作树中继续 plain `git am` 0006，结果为：

```text
Applying: DADAO Disassembler
error: corrupt patch at line 27
Patch failed at 0001 DADAO Disassembler
```

0006 首个新文件 hunk 声明 `+1,12`，在下一个 `diff --git` 前实际只有 10
条新增行；该文件不在 IN-006a ownership 内，worker 未修改或跳过。

### 验证摘要

- 0001～0005 plain `git am`：PASS（5/48）。
- 0005 目标 tree 与对应 `.work/llvm` 历史 tree：PASS。
- 0006：FAIL，独立 mbox corrupt；因此 48/48 与最终 `4b812d2f...` tree
  比较未达成。
- `python3 scripts/manifest_check.py`：PASS。
- `.work/llvm` 保持 clean，HEAD 仍为
  `4b812d2f99305a259a3d37a827d67c6c1ae14546`。
- 详细命令和证据见
  `docs/reviews/IN-006a-worker-report-20260723.md`。
