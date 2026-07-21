# ML-015i 独立 review

日期：2026-07-21

## 结论

**Accepted**

## Diff 范围

实现 diff 仅包含以下三个 fixture，各新增一条 Gem5 `RUN`，没有其它实现改动：

- `tests/lit/E2E/llvm-test-suite/arrayresolution.test`：期望码 `0`
- `tests/lit/E2E/llvm-test-suite/bitops.test`：期望码 `249`
- `tests/lit/E2E/llvm-test-suite/minint.test`：期望码 `1`

新增行分别与原有 QEMU `RUN` 的预期退出码一致；C 输入、QEMU 行及其它文件未纳入实现 diff。

## 验证

- 三项独立 `llvm-lit -a`：`3/3` PASS；verbose command output 逐条显示三条新增 Gem5 命令已执行，且分别通过 `test $? -eq 0/249/1`。
- `PATH=.work/build/llvm/bin:$PATH llvm-lit -v tests/lit/E2E/llvm-test-suite/`：rc `0`，`23/23` PASS，`0` FAIL，`0` SKIP。
- 完整 `PATH=.work/build/llvm/bin:$PATH llvm-lit -v tests/lit/E2E/`：采用工作树已有 fresh 输出记录，rc `0`，`59/59` PASS，`0` FAIL，`0` SKIP。
- `git diff --check`：rc `0`。

新增 Gem5 行不是仅由 diff 推断：三项 `llvm-lit -a` 输出包含实际展开并执行的 Gem5 命令，满足本 review 的执行性核验要求。
