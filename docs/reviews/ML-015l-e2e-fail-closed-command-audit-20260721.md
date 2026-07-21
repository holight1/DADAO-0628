# ML-015l E2E fail-closed command audit

日期：2026-07-21

## Static audit

- 扫描对象：`tests/lit/E2E/**/*.test`，共 `59` 个文件、`384` 条 `// RUN:`。
- `|| true`：`0`。
- 后台运行：`0`。
- QEMU/Gem5 相关 RUN：`120`；其中 `118` 条同一行显式包含
  `test $? -eq N`。
- `malloc_hello.test` 和 `printf_hello.test` 的两条 Gem5 marker grep 行本身
  不重复读取 Gem5 `$?`，但每条之前的 Gem5 RUN 已显式检查 `test $? -eq 0`；
  marker grep 使用 `xargs test 1 -eq`，失败仍返回非零。因此这是两步 RUN 的
  组织 finding，不是后端退出码被 `|| true` 或未检查而吞掉。

静态审计命令 rc=`0`。

## Fresh smoke

`PATH=.work/build/llvm/bin:$PATH llvm-lit -v tests/lit/E2E/` → `rc=0`；
`59 discovered / 59 passed / 0 failed / 0 skipped`。

## Boundary

本审计只证明当前仓库 E2E 门禁的 shell/lit 失败传播规则，不扩展为 upstream
llvm-test-suite/gcc-c-torture 结论；没有修改测试、实现、issues/wiki 或 ML-014a。
