# ML-015k 独立 Review

日期：2026-07-21

结论：**Accepted-with-findings**

## 核对结果

- task/report 的 active/deferred inventory 一致：`active=202`、`deferred=11`。
- active `expected_fault` counts：`null=169`、`ILLI=30`、`MALIGN=1`、`RASUF=2`、`UNDI=0`、`RASOF=0`。deferred 不计入 active fault counts。
- fresh QEMU harness：`SUMMARY active=202 deferred=11 pass=202 fail=0 skip=0 input_errors=0`，即 202 active 全部通过，11 条 deferred 未执行。
- `tests/scripts/run_qemu_test.py` 的 `FAULT_CODES` 为：`MALIGN=0x81`、`ILLI=0x82`、`UNDI=0x83`、`RASOF=0x84`、`RASUF=0x85`。
- `.work/source/qemu/target/dadao/helper.c` 对 RAS push overflow 抛 `0x84`、cold RAS pop 抛 `0x85`；`.work/source/qemu/target/dadao/cpu.c` 对 exception `0x84/0x85` 分别以相同 code 请求 shutdown。harness 与 QEMU 的 RASOF/RASUF mapping 一致。

## Findings / 限制

1. `UNDI=0`、`RASOF=0` 反映当前没有 active vector；报告没有声称这两类 fault 已被执行或覆盖。
2. 本轮结果只证明 harness/QEMU 的 exit-code 分类协议及 active vectors 的通过结果；没有证明 faulting PC/RA，也没有 PC/RA assertion 或观测证据。报告未声称 PC/RA 已覆盖。

因此，现有交付可接受，但应保留上述覆盖与观测边界，后续补充 UNDI/RASOF active vectors 及 PC/RA 验证时再扩大结论。
