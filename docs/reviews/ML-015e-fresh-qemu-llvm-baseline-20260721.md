# ML-015e fresh QEMU + LLVM baseline report

日期：2026-07-21

## QEMU

- `ninja -C .work/source/qemu/build qemu-system-dadao` → `rc=0`。
- QEMU：`10.0.0 (v10.0.0-19-gac58f31-dirty)`。
- source HEAD：`ac58f31acddc7f583e5087002df100297f2f87f9`。
- `python3 tests/scripts/run_qemu_test.py tests/vectors/isa/ --qemu
  .work/source/qemu/build/qemu-system-dadao` → `rc=0`。
- 结果：`active=202 deferred=11 pass=202 fail=0 skip=0 input_errors=0`。

## LLVM E2E

- `PATH=.work/build/llvm/bin:$PATH llvm-lit -v tests/lit/E2E/` → `rc=0`。
- 结果：`59 discovered / 59 passed (100.00%)`，用时约 `5.89s`。
- 该数字来自本轮实际执行，不复用历史报告；QEMU ISA vector 通过不被当作
  LLVM E2E 结果。

## Scope

本轮只做 fresh build/test evidence，没有修改实现、spec、vectors、kernel、
`docs/issues.yaml` 或 wiki，也没有修改 ML-014a；未访问或引用
`~/toolchain`、`~/knowledge-graph`。
