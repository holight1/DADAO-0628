# KL-101a 独立 review（2026-07-21）

## 结论

**Needs-fix**。报告的主结论（现有 QEMU/gem5 是 host/SE syscall shortcut，不能证明真实 reset→hypv→supv handoff）方向正确；但报告引用、O2/O3 验收措辞仍有 3 处需要修正后才能接受。

## 发现（3 条证据）

1. **O2/O3 的证据标签不完整。** O1 明确标为“`[推断的可执行测试]`”，但 O2（报告 §3.3）和 O3（§3.4）没有同等的“推断/验收草案”标记；其中“应产生相同 fault class”“均出现真实 trap/状态切换”等是尚待实现的验收草案，不是当前观测结果。建议给 O2/O3 标注 `[推断/验收草案]`，并保留“当前不能通过”的实现状态。

2. **QEMU patch series 的引用存在可复核错误，且 CFXTRAP 措辞过强。** `components/qemu/patches/series` 实际有 18 个 patch，不是报告附录所写的 17 个；其中第 14–18 行还包括 TB PC advance、precise exception PC、brk 默认值和 mmap arena，不是“只显示 trap-syscall 与 cfx_smon syscall patch”。同时，报告 §2 写“无真实 CFXTRAP 进入”容易被理解为没有 CFXTRAP 路径；源码实际在 `helper.c:99-108` 设置 `EXCP_CFXTRAP`，并由 `cpu.c:124-230` 进入 host-side responder。准确表述应为“有 host-side EXCP_CFXTRAP dispatch，但无 SEE 级 cfx 路由、现场保存、模式切换、guest vector 和 escape”。

3. **O2 的“未建立 prev/cause 后 escape”负例没有被现有 SEE 文字证明为非法。** SEE 的 escape 流程（`DADAO-12-SEE-主管系统运行环境.md:813-844`）只规定检查 escape mask、恢复 `excp_prev_cfx_mask`/`excp_prev_run_mode`、递增计数并跳到 `excp_cause_ip + offset`；没有“prev/cause 未先写就必须产生 ILLI”的前置校验。cg5 初值在 SEE `:351-362` 记为 0，因此该负例应改成“未授权/被 mask 的 cfx2rc 或 trap”这一有直接依据的非法路径；或明确把 early-escape 预期标为“语义待冻结”，不能断言为 O2 的 ILLI 负例。

## 可复核命令（只读）

```bash
cd /home/holight/DADAO-0628
rg -n '^\s*0[0-9]{4}-|^\s*001[0-9]-' components/qemu/patches/series
nl -ba .work/source/qemu/target/dadao/helper.c | sed -n '99,108p'
nl -ba .work/source/qemu/target/dadao/cpu.c | sed -n '124,230p'
nl -ba docs/reviews/kernel-hypv-supv-handoff-20260721.md | sed -n '94,114p;246,252p'
nl -ba /home/holight/DADAO-wiki/DADAO-12-SEE-主管系统运行环境.md | sed -n '351,362p;813,844p'
```

审阅范围未访问 `~/toolchain` 或 `~/knowledge-graph`，未修改原报告。
