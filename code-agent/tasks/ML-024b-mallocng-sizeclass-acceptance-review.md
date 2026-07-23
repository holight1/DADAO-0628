# ML-024b：ML-024a mallocng size-class 修复独立验收

日期：2026-07-23

## 状态

已完成，独立判决 **Accepted-with-findings**，无 blocking finding。

## 背景

ML-024a 已形成一组尚未提交的修复：将 musl crt0 中构造
`AT_PAGESZ=4096` 的越界 `addi` 改为 `setzw`，同步修正 auxv 探针，并新增
mallocng 与 lite_malloc 两条小分配双后端 E2E。worker 已在 ML-024a 完成区
记录诊断与自审，本任务负责不采信该转述的独立验收。

## Ownership 与约束

- reviewer 只允许新增
  `docs/reviews/ML-024b-independent-review-20260723.md`；不得修改生产代码、
  测试、patch、series、task、issues、roadmap、wiki 或 component 源仓。
- 不执行 rebase、reset、checkout 覆盖工作树或其它历史重写。
- 必须直接检查当前未提交 diff、musl commit `b3240b4a` 和导出 patch，不以
  ML-024a 完成区文字作为证据。
- review 必须明确区分 blocking finding、non-blocking finding 和建议后续任务。

## 验收范围

1. 核对 ISA 立即数范围及 `setzw` 替换的语义正确性。
2. 核对 malloc-only 与 malloc+free 是否确实链接到不同 allocator 符号。
3. 独立运行两条新增测试、`musl_crt0_auxv.test` 和全量 E2E。
4. 独立运行 differential、manifest、issues 门禁。
5. 从 musl 裸 pin `0784374d...` 完整重放 0001～0011，确认最终 tree 与
   `.work/source/musl` 一致。
6. 检查测试是否具有负控制和真实内存访问判别力，检查注释与实际覆盖一致。
7. 核对主仓和 component 仓状态，判断 ML-024a 是否可提交收口。

## 交付

独立 review 报告必须给出 Accepted、Accepted-with-findings 或 Needs-fix 判决，
列出实际命令、关键输出、finding 和建议处置。

## 完成区

- 独立报告：
  `docs/reviews/ML-024b-independent-review-20260723.md`
- 判决：Accepted-with-findings；ML-024a 核心修复可接受。
- 已独立确认 musl 0001～0011 裸 pin 重放、allocator 符号分流、目标测试、
  E2E 65/65、四方 differential、manifest 和 issues 门禁。
- 三项 non-blocking finding：
  1. lite_malloc 测试未读写返回内存，在旧 bug 下会在 gem5 假阳性；
  2. lite-only 测试命名/注释不准确；
  3. assembler 仍静默接受越界立即数。
- finding 1/2 下发为 ML-024c；finding 3 已下发为 DL-071a。
