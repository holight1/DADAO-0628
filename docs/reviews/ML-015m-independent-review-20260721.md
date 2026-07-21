# ML-015m 独立 review

日期：2026-07-21

结论：**Accepted**

## Handoff 口径核对

- QEMU ISA 明确区分 `202 active / 11 deferred`，并记录 active `202/202`
  通过；deferred 未被计入 active 通过率。
- 完整仓库 E2E 明确为 `59/59`，与仓库内 `llvm-test-suite` 切片的
  `23/23` 分开统计；报告明确指出 `23/23` 不是 upstream 全量。
- 三项 Gem5 fixture 明确为隔离 `3/3`，并给出退出码 `0/249/1`，没有把
  Gem5 fixture 数字扩大成 upstream 全量结论。
- 未完成项完整保留：`ML-014a` mallocng 真实双后端、upstream 全量
  `llvm-test-suite`/`gcc-c-torture`、active `UNDI/RASOF` vectors、precise
  `PC/RA` 观测或断言、tail-call lowering、varargs RB pointer save-area/ABI
  边界，以及 kernel 的真实 handoff/CFX/RegRAS 路线。
- roadmap 没有越界：先推进 LLVM+QEMU/ABI 与 ML-014a 或明确的 codegen/ABI
  blocker，再扩大 upstream 测试并补 UNDI/RASOF 与 PC/RA 证据，最后才考虑
  kernel；同时明确当前用户态门禁不代表 kernel 已就绪。

## 依据

- [ML-015m task](../../code-agent/tasks/ML-015m-final-handoff-roadmap.md) 的
  必须明确项与完成区一致。
- [ML-015m handoff report](ML-015m-final-handoff-roadmap-20260721.md) 的已解决、
  未完成与 roadmap 段落均保持上述边界。
- [ML-014 30-task tracker](../../code-agent/tasks/ML-014-30-task-run-20260718.md)
  中 ML-015e、ML-015f、ML-015i、ML-015j、ML-015k、ML-015l 的记录分别支持
  ISA/E2E、仓库切片、三项 Gem5、交叉回归、异常覆盖边界和 fail-closed 口径。

本 review 仅检查 handoff 口径；未修改实现、roadmap、ML-014a 或其它文件，
也未访问或引用 `~/toolchain`、`~/knowledge-graph`。
