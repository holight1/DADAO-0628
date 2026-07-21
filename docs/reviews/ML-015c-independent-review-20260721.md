# ML-015c independent review

结论：**Needs-fix**

## 核心阻塞项：合法 `rb0` jump/call 仍被执行，而且实际失败

`tests/vectors/isa/control-flow.yaml:434-468` 的四条记录（两个
`jump 0x65000000`、两个 `call 0x6D000000`）被改成了 active、`class:
encoding`、`expected_fault: null`。但这并不会使它们成为只校验编码的记录：

- `tests/scripts/build_test_binary.py:277-291` 对没有 `branch_behavior` 的 case
  仍发出被测指令；`expected_state: null` 随后走 `emit_exit(0)`。
- 对这四条 case 生成的布局是被测指令后紧跟 `emit_exit(0)`，没有 poison；但
  builder 没有初始化可供该 `rb0` 特例使用的运行时 PC/base。`BINARY_BASE` 只是
  二进制布局常量，不是对 `rb0` 的设置。
- 用仓内 `.work/source/qemu/build/qemu-system-dadao` 和
  `tests/scripts/trampoline.bin` 只读运行这四条 case，结果四条均为：
  `FAIL: unexpected exit=0x82`。`run_qemu_test.py:40-59` 将 `0x82` 识别为
  `ILLI`；这与跳到地址 0/下游 trampoline 后触发 `halt rd0` 的旧失败路径一致。

因此，`expected_fault` 从 `ILLI` 清为 `null` 后，测试并没有证明合法的
`rbha=rb0` 指令正常完成，反而把一个实际的 `ILLI` 变成了错误的 no-fault 预期。
规范本身并不支持原来的“把下游 fault 当作指令 fault”，但当前 harness 也不能
安全执行这两个 encoding-only control-flow 输入。

### 最小修复建议

1. 立即将上述四条 active 记录改为 `status: deferred`，保留
   `expected_fault: null`，并填写明确的 `deferred_reason`，例如
   `control-flow encoding-only case requires PC/rb0-safe harness layout`。
   这样不会把 harness/trampoline 的 `ILLI` 伪装成 ISA 断言，也不会继续产生
   已知失败的 active 测试。
2. 后续若要恢复 active，必须为 `rbha=rb0` 专门提供 PC-safe 的 builder/layout
   （或重写为带已知目标、可验证通过路径的执行 case），并用实际运行结果证明
   `jump/call` 自身无 fault；不能只清除 `expected_fault`。两组重复条目也应分别
   说明其目的，不能以改成 `encoding` 来替代原本的 legality/执行意图。

## cold `ret` 的 RASUF 修正

这部分方向正确。`contracts/isa/spec.md §5.6` 明确 `ra63[63:48] == 0`
时 `ret` 唯一 fault 是精确的 `RASUF`，且 RA 不变、PC 停在 faulting `ret`；
`§2.6.1` 也明确 `ret rdha=rd0` 合法。因此 `0x6E040000` 和 `0x6E000000`
的 boundary 断言改为 `expected_fault: RASUF` 是正确的，不能再用后续
`halt rd0` 的 `ILLI` 代替。

不过，两个 boundary 使用 `expected_state: {}`。按现有
`build_test_binary.py`，空 mapping 为 false，不会生成状态比较；所以该记录
实际只断言 fault code，notes 中的“PC/RA unchanged”没有被 harness 断言。若要
保留这项保证，应后续增加可表达/比较 PC 与 RA 的 harness/schema 支持；本次最小
修复不应把 notes 当成已验证的状态断言。

## schema、计数与断言

结构检查没有发现错误：`validate_vectors.py` 报告 `213` cases、`87/87`
opcodes covered，`validate_encoding.py` 报告 `87` records OK；当前计数为
`207 active / 6 deferred`，`encoding 89 / legality 13 / boundary 7`，fault
为 `ILLI 30 / RASUF 2 / MALIGN 1`。

但这些检查只验证 YAML 形状、编码匹配和部分字段一致性，不执行 active
encoding case；因此无法发现上述四条在 QEMU 中实际返回 `ILLI`。此外，schema
允许 active boundary 用 `{}` 满足“非 null”条件，不能保证有任何状态字段被比较。
计数本身没有被削弱到失效，但把两个 jump/call legality stub 改成 encoding
duplicate 确实移除了原有的 legality 断言，且没有等价的可执行替代。

