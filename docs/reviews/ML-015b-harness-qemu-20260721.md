# ML-015b 审计：harness → QEMU

日期：2026-07-21。范围：只读核对当前 QEMU fault/exit 实现与
`tests/scripts/run_qemu_test.py` 协议；未访问 `~/toolchain` 或
`~/knowledge-graph`，未修改源码、向量或 harness。

## 结论

QEMU 当前 fault code 的主要映射与 harness 一致，但这只能证明“退出码通路
一致”，不能证明 fault 来源、faulting PC 或 RA 精确状态一致。ML-015a 的两个
cold-ret 失败属于测试期望错误，不是 QEMU fault-code 错误。

| 检查项 | 当前证据 | 判定 |
|---|---|---|
| ILLI/UNDI/MALIGN | `cpu.h` 定义 `EXCP_ILLI/UNDI/MALIGN`；`cpu.c` 分别输出 `0x82/0x83/0x81`；harness `FAULT_CODES` 相同 | 一致（退出码层） |
| RASOF/RASUF | `helper_ras_push()` 对满栈抛 `0x84`，`helper_ras_pop()` 对 cold 栈抛 `0x85`；`cpu.c` 原样输出；harness 映射相同 | 一致（退出码层） |
| cold `ret` | spec §5.6 要求 RASUF；QEMU helper 产生 `0x85`；向量却声明 ILLI | 测试期望错误 |
| 精确异常 | `dadao_raise_exception()` 在非零 retaddr 时 `cpu_restore_state()`；RAS helper 当前以 `retaddr=0` 调用，且 harness 不检查 PC/RA | 证据不足，不能宣称完整 precise 验证 |
| 0019 scaffold | 只新增 `CPUArchState` 字段和 reset 初值；未改 RAS helper、异常分派或 exit path | 未改变现有 fault 语义 |
| fault 来源 | harness 仅按进程 rc 匹配 fault code，不验证 faulting instruction/PC | harness 覆盖不足 |

## 可复核证据

```bash
nl -ba .work/source/qemu/target/dadao/helper.c | sed -n '45,97p'
nl -ba .work/source/qemu/target/dadao/cpu.c | sed -n '115,130p;236,246p'
nl -ba tests/scripts/run_qemu_test.py | sed -n '24,59p'
nl -ba contracts/isa/spec.md | sed -n '883,914p;236,240p'
```

QEMU 侧当前结论是：没有证据要求为 ML-015a 的两个 cold-ret 失败修改 QEMU；
应先修正/审计向量分类，再决定是否增加能观察 PC/RA 的测试能力。
