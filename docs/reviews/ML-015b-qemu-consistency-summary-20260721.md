# ML-015b：QEMU 一致性审计汇总

**日期**：2026-07-21　　**结论**：发现测试/门禁一致性缺口，暂停实现推进

## 总结结论

当前不能把 QEMU 的 `204/206` fresh 结果当作 QEMU 正确性回归结论。三层审计
结果如下：

| 层次 | 结论 | 处理意见 |
|---|---|---|
| spec → vector | 有明确不一致：cold `ret` 应为 RASUF，却写成 ILLI；合法 `rb0` control-flow 用法被标成 legality/ILLI；encoding 分类混入执行 fault；当前无 RASOF/RASUF 专门覆盖 | 不得直接改成“QEMU fail”；先开向量/分类修复任务，逐条引用 spec |
| vector → harness | 五类主要 fault code 映射一致；目录参数会 traceback；部分 SKIP 可被文件模式跳过；harness 不验证 fault 来源、PC、RA，未知 RA/PC expected_state 可能被忽略 | 先修 harness 输入处理和 fail-closed 状态 schema，再扩大向量 |
| harness → QEMU | QEMU 的 ILLI/UNDI/MALIGN/RASOF/RASUF 退出码与 harness 一致；0019 未改变异常路径；RAS precise 的 PC/RA 仍缺少可观测证据 | 不因 ML-015a 两项 cold-ret 失败修改 QEMU；增加 PC/RA 观察能力后再判断实现问题 |

## 当前数字的正确解释

- QEMU 当前 fresh build：`rc=0`。
- 逐 YAML fresh harness：206 active 中 204 通过、2 项触发 RASUF；但这两项
  向量期望错误，不能计为 QEMU 失败，也不能计为正式 PASS。
- `python3 tests/scripts/run_qemu_test.py tests/vectors/isa/` 的目录入口会因
  参数处理触发 `AttributeError`，应视为 harness 缺陷，不是 QEMU 失败。
- 本轮 LLVM E2E 被中断，没有 fresh 数值；历史 59/59 和 203 PASS 继续保留为
  历史证据，不冒充本轮结果。

## 不应擅自做的事

1. 不把两个 `expected_fault: ILLI` 改成 `RASUF` 后直接宣布测试全绿；需要先
   审计这些条目的 class、notes、wiki_cite，以及同类 control-flow 条目。
2. 不把 downstream `halt rd0` 的 ILLI 当成 jump/call/ret 指令本身的 fault。
3. 不用退出码一致替代 precise PC/RA 证据。
4. 不在当前一致性问题未收敛前继续 KL-102c/O1 handoff 或 kernel 实现。

## 建议的下一顺序

1. 单独修复/审计 vectors 的 spec 引用与 class/expected_fault 分类；
2. 修复 harness 目录参数、未知状态键和 fault-source/PC/RA 的 fail-closed 行为；
3. fresh 重跑 QEMU 裸金属与 LLVM/E2E；
4. 只有基线可信后，才继续 LLVM/用户态扩展，再重新评估 kernel 入口门槛。

详细证据：

- `docs/reviews/ML-015b-spec-vector-harness-20260721.md`
- `docs/reviews/ML-015b-harness-qemu-20260721.md`
- `docs/reviews/ML-015a-independent-review-20260721.md`
