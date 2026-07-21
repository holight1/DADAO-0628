# ML-015h 独立 review

日期：2026-07-21  
结论：**Accepted-with-findings**

## 核对结果

| fixture | expected | QEMU rc | Gem5 rc | Gem5 marker |
|---|---:|---:|---:|---|
| `arrayresolution` | 0 | 0 | 0 | `SIM_END: halt code=0` |
| `bitops` | 249 | 249 | 249 | `SIM_END: halt code=249` |
| `minint` | 1 | 1 | 1 | `SIM_END: halt code=1` |

- 三个 `.test` 的 expected 值与报告中的 QEMU/Gem5 rc 一致；构建链三步均记录为 `rc=0`。
- Gem5 均在 `timeout 10s` 内结束；timeout 没有把失败吞掉，报告记录了实际 Gem5 rc 和 `SIM_END` marker。
- task/report 均明确没有使用 `|| true`。
- 三个 `.test` 仍只有原有 QEMU RUN 行；本任务未修改 `.test`，也未将 probe 说成双后端测试已经落地。

## Findings

证据支持“当前缺口看起来是遗漏 Gem5 RUN 行”，但这只是可行性 probe，不是完整 lit/E2E 回归，也没有在本任务中补测试断言。后续任务应单独增加三条 Gem5 RUN/断言并回归验证。

