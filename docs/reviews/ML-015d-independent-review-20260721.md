# ML-015d Independent Review

日期：2026-07-21

结论：**Accepted**

## 检查范围

仅阅读并检查：

- `tests/scripts/run_qemu_test.py`
- `tests/scripts/build_test_binary.py`
- `tests/vectors/schema.md`

未修改实现文件；本次仅写入本 review 文档。

## 验证命令与返回码

1. `python3 -m py_compile tests/scripts/run_qemu_test.py tests/scripts/build_test_binary.py`
   - rc：`0`

2. `python3 tests/scripts/run_qemu_test.py tests/vectors/isa --qemu .work/source/qemu/build/qemu-system-dadao`
   - rc：`0`
   - 结果：`active=202 deferred=11 pass=202 fail=0 skip=0 input_errors=0`

3. 临时 Python 片段调用 `validate_expected_state`，分别验证 `pc`、`ra`、`unknown` key 被拒绝。
   - rc：`0`
   - 结果：三种 key 均抛出 `ValueError` 并被明确拒绝。

## Review 结论

`expected_state` 当前仅比较 `rd`、`rb`、`memory`；`pc`、`ra` 及未知 key 均 fail-closed 拒绝，且 schema 文档与实现边界一致。真实 QEMU ISA 目录测试全量 active case 通过，因此本次独立短检查接受。
