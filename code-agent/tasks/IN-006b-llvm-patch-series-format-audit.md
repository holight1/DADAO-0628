# IN-006b：LLVM 全 patch series 格式审计与完整重放修复

日期：2026-07-23

## 状态

待处理；承接 IN-006a。

## 背景

IN-006a 修复 0005 后，plain `git am` 在 0006 又报告独立的 hunk 行数损坏。
这证明历史 patch 可能存在多处序列化缺失，逐文件下任务会造成低效追洞。本任务
一次性扫描 0006～0048，并恢复整个 series 的从零可复现性。

## Ownership 与约束

- 允许修改 `components/llvm/patches/0006-*.patch` 至 `0048-*.patch` 中经证据
  证明损坏的 patch、本任务完成区及 worker report。
- 不修改已复核的 0001～0005、series 顺序、manifest pin、`.work/llvm` 源码、
  测试、issues、roadmap、wiki 或其它 component。
- 不得跳过 patch、使用 `--reject`/`--3way` 掩盖错误、放宽 apply 条件、改 pin、
  squash/rebase/amend 历史。
- 对每个修复 patch，必须以其 `index` postimage、对应 `.work/llvm` 历史提交和
  前后 tree 为依据；不能只修改 hunk count 让 parser 接受却生成错误源码。

## 目标

1. 先做全量静态格式扫描，列出所有 hunk 声明计数与实际正文不一致、邮件截断或
   preimage/postimage 不完整的 patch。
2. 按 series 顺序从裸 pin plain `git am`，每修一处继续向后，直至 48/48。
3. 对每个被修改 patch，记录：
   - 原错误位置与根因；
   - 恢复内容的权威来源；
   - 应用后 tree 与对应历史提交 tree 的比较。
4. 最终重放 tree 必须与 `.work/llvm` HEAD
   `4b812d2f99305a259a3d37a827d67c6c1ae14546` 完全一致。
5. 运行 manifest；保持 `.work/llvm` clean。

## 验收

- 裸 pin 48/48 plain `git am` 成功。
- 最终 tree identity 闭合。
- 所有修改仅修复 patch 序列化/前像适配，不改变当前 LLVM 源码语义。
- 必须由独立 reviewer 复核；通过前不得关闭
  `llvm-patch-series-full-replay-corrupt-at-0005`。
