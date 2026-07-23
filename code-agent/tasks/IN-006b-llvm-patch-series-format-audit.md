# IN-006b：LLVM 全 patch series 格式审计与完整重放修复

日期：2026-07-23

## 状态

已完成；独立 review 判决 **Accepted**。承接 IN-006a。

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

## Worker 完成记录（2026-07-23）

判决：**Worker PASS；尚未完成独立验收。**

一次性静态扫描 0006～0048 后，确认并修复了四个有证据的问题 patch：

- 0006：五个 hunk 的声明计数均与正文不符；CMake hunk 还缺失了由
  `08db6fd...` 到原声明 postimage `728f8ff...` 所需的行序调整。恢复后两个
  Disassembler 新文件 blob 与其在历史 `bb5415a...` 中首次落地的 blob 完全
  一致，CMake 命中 `728f8ff...`。
- 0007：0006 已先引入 decoder methods，原 0007 又从更早前像重复引入。仅适配
  `DADAOInstrInfo.td` 前像，输出仍命中历史 `e99cb0d...` 的
  `6ea5e385...` blob。
- 0013：历史提交 `bb5415a...` 曾把未独立提交的 Disassembler 一并带入；在
  series 已应用 0006 的前提下，原 patch 会重复创建文件并使用错误前像。按
  0012 后的实际 series tree 到 `bb5415a...` 的权威目标 tree 机械重建，
  应用后 tree 精确为 `6ea8b53...`。
- 0019：原 patch 可以解析和应用，但漏掉历史父提交 `e902b104...` 的 SEL node
  变更，应用后 tree 为错误的 `a3f74cef...`。按 0018 的正确 tree
  `129bb700...` 到历史 `b4f88e5...` tree `76479e5a...` 重建，补齐遗漏。

最终独立临时 checkout
`/tmp/in-006b-final-replay-20260723-6iEUNI/llvm` 从 manifest pin
`ca7933e47d3a3451d81e72ac174dcb5aa28b59d1` 顺序执行 plain `git am`：

```text
0001..0048: PASS (48/48)
final replay tree: f4adf7c77a6d5287442993d89d94cbb17eeb3136
expected HEAD tree: f4adf7c77a6d5287442993d89d94cbb17eeb3136
tree identity: PASS
```

其它门禁：

```text
0006..0048 static hunk count audit: PASS (43/43)
0006..0048 git apply parser audit: PASS (43/43)
python3 scripts/manifest_check.py: PASS
.work/llvm HEAD: 4b812d2f99305a259a3d37a827d67c6c1ae14546
.work/llvm status --short: empty
```

本 worker 只修改 0006、0007、0013、0019、本完成区，并新增
`docs/reviews/IN-006b-worker-report-20260723.md`。未修改 0001～0005、series、
manifest、`.work/llvm`、测试、issues、roadmap 或 wiki；主仓未提交。原 issue
在独立 reviewer 通过前保持开放。

## 独立 review

- 报告：`docs/reviews/IN-006b-independent-review-20260723.md`
- 判决：Accepted，无 blocking finding。
- 0006～0048 静态格式 43/43、裸 pin plain `git am` 48/48、最终 tree 与
  `.work/llvm` HEAD identity、manifest 和 source clean 均独立通过。
- reviewer 确认 0019 补回的 SEL node 属于原历史目标，不是夹带功能。
- 原 replay issue 技术上已具备关闭条件；本任务遵守既有保护约束，不直接修改
  `docs/issues.yaml`。
