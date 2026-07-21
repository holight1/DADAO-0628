# ML-015j cross-gate fresh regression

日期：2026-07-21

| Gate | Command result | Fresh result |
|---|---|---|
| QEMU build | `ninja -C .work/source/qemu/build qemu-system-dadao` rc=0 | QEMU 10.0.0, source `ac58f31acddc7f583e5087002df100297f2f87f9` |
| QEMU ISA | runner rc=0 | active=202, deferred=11, pass=202, fail=0, skip=0, input_errors=0 |
| llvm-test-suite slice | llvm-lit rc=0 | 23 discovered, 23 passed, 0 failed, 0 skipped |
| full E2E | llvm-lit rc=0 | 59 discovered, 59 passed, 0 failed, 0 skipped |
| diff check | `git diff --check` rc=0 | clean |

本轮结果来自 ML-015i 之后的 fresh 执行；QEMU ISA、llvm-test-suite 子集和完整
E2E 仍保持独立统计。没有修改实现或 vector 语义，没有使用 `|| true`，也没有
修改 ML-014a、issues/wiki。
