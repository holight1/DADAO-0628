# ML-015f review：llvm-test-suite 子集独立门禁

日期：2026-07-21

## 证据

在 `/home/holight/DADAO-0628` 执行：

```text
bash -lc 'files=(tests/lit/E2E/llvm-test-suite/*.test); printf "test_count=%s\n" "${#files[@]}"'
```

rc：`0`；统计：`23` 个 `tests/lit/E2E/llvm-test-suite/*.test`。

```text
PATH=.work/build/llvm/bin:$PATH llvm-lit -v tests/lit/E2E/llvm-test-suite/
```

rc：`0`。完整输出报告 `23 tests`：`23` PASS、`0` FAIL、`0` SKIP，测试耗时 `2.84s`。

## 范围边界

本证据只覆盖仓库中该目录的 23 个测试，即隔离结果 `23/23`。它与完整 E2E 的 `59/59` 是不同统计口径；本结果不代表 upstream 全量 `llvm-test-suite` 或 `gcc-c-torture` 已通过。
