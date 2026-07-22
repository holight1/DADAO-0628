# 归档：codex 接手 ML-014a（musl malloc+printf 里程碑）2026-07-18~21

**这批 65 个任务文件是一个内部代号"codex"的独立 agent 在 session 上下文重置期间自主推进的工作**，接手对象是 `code-agent/tasks/ML-014a-musl-e2e-malloc-printf.md`（原始里程碑任务，未被这批工作编辑/关闭，仍在 `code-agent/tasks/` 主目录，保持 open）。

**先读这两份，不要从这批文件里逐个啃**：
1. `docs/reviews/ML-017d-final-handoff-roadmap-20260721.md`（codex 自己写的最终交接：完成计数、事实、推断、边界、后续 roadmap A/B/C/D/E）+ 对应任务文件 `code-agent/tasks/ML-017d-final-handoff-roadmap.md`。
2. `docs/reviews/codex-run-integrity-audit-2026-07-21.md`（架构师事后独立完整性审计：确认哪些是真实产出、发现了哪些工程纪律问题、分级处置建议）。

**结论速览**（详见上面两份文档）：
- 真实、已验证的产出：QEMU mmap arena backing、gem5 mmap/SYS_brk VMA backing、lld RELA_PAGE 跨页修复、4 个 LLVM CodeGen 修复（AsmPrinter/inline-asm/i1/frame）、wiki pin drift 修复。
- 里程碑本身（malloc+printf E2E）**未完成**——`puts`/stdout 在两后端均无输出 marker。
- 审计发现的纪律问题（7 处未导出 patch、1 处伪造 hash 假 patch、musl 侧未披露依赖已拒绝任务的 `-O0` workaround、差分基线偏移未经验证）已由后续 `IN-005a`+`DL-070a`（不在本归档内，仍在 `code-agent/tasks/` 主目录）收尾修复。

**目录内容**：`ML-014b`~`ML-014ag`（32 个，mmap backing → gem5 brk VMA → mallocng 诊断链）、`ML-016a`~`ML-016z`（26 个，musl 编译失败簇诊断+4 个 LLVM 修复）、`ML-017a`~`ML-017c`（3 个，最终 object matrix + scope 订正 + targeted gate）、两份 30-task 阶段性台账、一份 `ML-014-current-status-20260718.md` 阶段性状态快照。对应的独立 review/worker-report 文件在 `docs/reviews/archive/2026-07-ml014-malloc-e2e-run/`。
