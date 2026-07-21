# ML-015k QEMU fault protocol cross-check

日期：2026-07-21

## Fresh inventory and run

inventory rc=`0`：`active=202`、`deferred=11`。active expected-fault counts：

| expected_fault | count |
|---|---:|
| `null` | 169 |
| `ILLI` | 30 |
| `MALIGN` | 1 |
| `RASUF` | 2 |
| `UNDI` | 0 |
| `RASOF` | 0 |

命令 `python3 tests/scripts/run_qemu_test.py tests/vectors/isa/ --qemu
.work/source/qemu/build/qemu-system-dadao` → `rc=0`，汇总
`active=202 deferred=11 pass=202 fail=0 skip=0 input_errors=0`。输出中
`ILLI=30`、`MALIGN=1`、`RASUF=2` expected fault 全部 PASS；本轮没有 UNDI/RASOF
vector 执行证据。

## Protocol mapping

`tests/scripts/run_qemu_test.py:23`：
`ILLI=0x82`、`MALIGN=0x81`、`UNDI=0x83`、`RASOF=0x84`、`RASUF=0x85`。

当前 QEMU source：

- `target/dadao/helper.c:64`：RegRAS push overflow raises `0x84`；
  `helper.c:80`：cold RegRAS pop raises `0x85`。
- `target/dadao/cpu.c:238-242`：exception `0x84/0x85` 分别以相同 code 请求
  guest panic shutdown。

因此当前 harness、QEMU helper 和 shutdown path 的 RASOF/RASUF code mapping
一致。该 exit code 只证明当前协议分类，不证明 fault source beyond the
selected path，也不证明 faulting PC/RA；这些观测能力仍未实现。

本任务只读检查，没有修改 QEMU、vectors、issues/wiki 或 ML-014a。
