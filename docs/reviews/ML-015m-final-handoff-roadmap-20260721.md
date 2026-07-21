# ML-015m 最终 handoff 与后续 roadmap

**日期**：2026-07-21  
**范围**：ML-015a～ML-015l 的 task、review 与 30-task tracker 汇总  
**结论**：LLVM + QEMU 一致性与当前仓库门禁已形成可交接基线；LLVM+QEMU/ABI 仍应先于 kernel 扩展。

## 已解决（当前覆盖范围内）

| 门禁/证据 | fresh 结果 | 交接解释 |
|---|---:|---|
| spec/vector/harness consistency | vector `213 total / 202 active / 11 deferred`；fail-closed harness 的 active `202/202` | cold `ret` 已按 spec 使用 `RASUF`；合法但当前不能安全执行的 encoding-only 条目保留为 deferred；目录聚合、输入错误、未知 `pc/ra` 状态键不会静默通过。 |
| QEMU | build `rc=0`；ISA harness `active=202, deferred=11, pass=202, fail=0, skip=0, input_errors=0` | 当前 QEMU/harness fault exit-code 协议一致；active fault counts 为 `null=169 / ILLI=30 / MALIGN=1 / RASUF=2`。 |
| LLVM | 完整仓库 `tests/lit/E2E/`：`59/59`，`rc=0` | 这是当前仓库 E2E 门禁结果。 |
| 仓库内 llvm-test-suite 切片 | `23/23`，`rc=0` | 这是 `tests/lit/E2E/llvm-test-suite/` 的仓库切片，不是 upstream 全量 suite。 |
| Gem5 fresh fixture 覆盖 | 三项隔离 `3/3`；退出码 `arrayresolution=0 / bitops=249 / minint=1` | 三个原 QEMU-only fixture 已补齐并实际执行 Gem5 断言；完整 E2E 仍为仓库门禁的 `59/59`。 |
| E2E fail-closed 审计 | `59` files / `384` RUN；`120` 条 backend RUN 中 `118` 条同行检查 rc；无 `|| true`、后台运行或 shell 吞错 | `malloc_hello`、`printf_hello` 的 Gem5 marker 为两步断言，但前一步已检查 Gem5 rc，后一步缺 marker 也会失败。 |

## 未完成与边界

- `ML-014a` 的 mallocng 真实双后端里程碑仍未解决；`59/59` 不等于 mallocng 已解决。
- upstream 全量 `llvm-test-suite` 与 `gcc-c-torture` 尚未完成；仓库切片 `23/23` 不得写成 upstream 全量通过。
- 当前没有 active `UNDI` 或 `RASOF` vectors（两者均为 `0`），因此尚未完成这两类异常的 active 覆盖。
- fault exit code 一致不等于 precise faulting `PC/RA` 已被观测或断言；PC/RA 仍未完成。
- tail-call lowering 与 varargs 的 RB pointer save-area/ABI 边界仍是扩大测试前的未完成项。
- kernel 路线仍未完成；CFX、RegRAS save/restore 和真实 handoff 不能由本轮 LLVM/QEMU 数字替代。
- 当前仍有 `11` 条 deferred vector；不得将 deferred 计入 active 通过率。

## Roadmap

1. **优先 LLVM + QEMU/ABI**：先推进 `ML-014a` mallocng 的真实双后端证据，并定位/关闭明确的 codegen、tail-call、varargs 与 RB-bank ABI blocker。
2. 在 ABI/libc 证据稳定后，扩大 upstream `llvm-test-suite` 与 `gcc-c-torture` 的构建和运行范围；保留仓库切片与 upstream 全量的独立统计。
3. 补充 active `UNDI/RASOF` vectors，并建立 fault source、precise PC/RA 的可观测/可断言证据。
4. **之后再考虑 kernel**：以 LLVM+QEMU/ABI 基线为前置，再进入 kernel 的 CFX、RegRAS 与真实 handoff 验证；不以当前用户态门禁结果宣称 kernel 已就绪。

## 口径与来源

本 handoff 依据 [ML-014 30-task tracker](../../code-agent/tasks/ML-014-30-task-run-20260718.md)、[ML-015m task](../../code-agent/tasks/ML-015m-final-handoff-roadmap.md) 以及 ML-015a～ML-015l 的 task/review 完成区和独立 review。报告只做汇总，不修改实现、vectors、issues、wiki、roadmap 或 ML-014a；未访问或引用 `~/toolchain`、`~/knowledge-graph`。
