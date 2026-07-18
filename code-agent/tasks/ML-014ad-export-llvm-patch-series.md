# ML-014ad：导出并集成 LLVM 修复到 root patch series

**执行环境**：本地 subagent worker；承接 ML-014v 与 ML-014ac 的已验证 source commits

**状态**：Ready（30-task run：10/30）

## 目标

把已经通过运行验证的两个 LLVM source commit 以追加式 patch 纳入 root
`components/llvm/patches/series`：先导出 ML-014v 的大偏移地址合法化，再导出
ML-014ac 的 `RELA_PAGE` signed-low 页舍入修复，保持现有 0039 之后的顺序和可重放性。
本任务只做 patch integration 与静态 replay 门禁，不修改实现内容，不改
`docs/issues.yaml`、wiki pin 或原始 ML-014a。

## Ownership

- worker 负责 root `components/llvm/patches/0040-*`、`0041-*` 及 `series`，以及
  本 task MD；外部 source tree 仅作导出来源，不回滚历史。
- 只允许普通追加式 `git format-patch`/复制结果；不 reset、rebase、重写已有 patch。
- 不访问或引用 `~/toolchain`、`~/knowledge-graph`；不修改 QEMU/gem5/musl。
- 若发现 source parent 与 root patch base 不一致，记录为阻塞并停止，不强行拼 patch。

## 执行阶梯

1. 核对 external LLVM source 当前链：`1697be42b5b1`（ML-014v）→
   `f5a06de81358`（ML-014ac），以及 root 0039 的 parent/series 顺序。
2. 导出两个 patch，命名为连续的 0040/0041，追加到 `components/llvm/patches/series`；
   核对 patch 只包含各自 source commit 的预期文件。
3. 在临时 clean checkout/worktree 上按 root series replay 至 0041，使用
   `git apply --check`/`git am` 等非破坏方式，验证不会损坏已有 patch；若全量 replay
   受既有历史 blocker 影响，精确记录边界。
4. 运行 `scripts/manifest_check.py` 与相关 patch/series 静态检查；不擅改 manifest。

## 验收

- 两个 patch 与 source commit 可一一对应，series 顺序正确，root worktree 可审计。
- replay/静态门禁结果原样记录；不声称 root 全量从零 replay 已通过，除非确实完成。
- 必须由不同 subagent 独立 review patch 内容、顺序和未越权范围。

## 完成区

（由 worker 填写；完成后由不同 subagent 独立 review）
