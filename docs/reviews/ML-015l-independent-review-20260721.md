# ML-015l independent review

日期：2026-07-21

结论：**Accepted-with-findings**

## Static audit

基于 `tests/lit/E2E` 原始 `.test` 文件独立复核：

- `59` 个 test files、`384` 条 `RUN`。
- `|| true`：`0`。
- 后台运行：`0`。
- QEMU/Gem5 backend RUN：`120`。
- 同一 RUN 行显式断言 `test $? -eq N`：`118`。

剩余两条是 marker 检查 RUN，不是后端执行 RUN：

- `malloc_hello.test:37`：`grep -c "OK OK2" %t.gem5.out | xargs test 1 -eq`
- `printf_hello.test:31`：`grep -c "hello, dadao" %t.gem5.out | xargs test 1 -eq`

## Gem5 两步 RUN finding

两处 Gem5 均为“后端执行 + 输出 marker 检查”的两步结构：

- `malloc_hello.test:36` 先运行 Gem5，并在同一 `bash -c` 中断言
  `test $? -eq 0`；随后第 37 行检查 `OK OK2` marker。
- `printf_hello.test:30` 先运行 Gem5，并在同一 `bash -c` 中断言
  `test $? -eq 0`；随后第 31 行检查 `hello, dadao` marker。

因此，后续 marker RUN 不读取 Gem5 的 `$?` 是命令组织上的 finding，但不构成吞错：前一行的 Gem5 非零退出码会使该 RUN 失败，后一行的 `xargs test 1 -eq` 也会对 marker 缺失返回非零。两步均为独立的 lit 断言，不能把 Gem5 失败转成 PASS。

## Fresh E2E

核对 task/report 中记录的 fresh 命令：

`PATH=.work/build/llvm/bin:$PATH llvm-lit -v tests/lit/E2E/`

结果：`rc=0`，`59/59` pass，`0` fail，`0` skip。本次 review 按要求未重新运行测试。

## Boundary

本 review 只覆盖 E2E shell/lit 失败传播审计及 fresh 结果记录；未修改实现、任何 `.test`、ML-014a 或其他任务文件。
