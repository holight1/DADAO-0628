# ML-015l：E2E fail-closed 命令审计

**日期**：2026-07-21

**状态**：Accepted-with-findings（30-task run：29/30）

## 背景

此前项目曾出现 lit `|| true` 遮蔽退出码的问题。ML-015d 已修复 ISA harness
的 fail-closed 行为，ML-015i 又增加了三条 Gem5 RUN；现在审计整个
`tests/lit/E2E/` 的测试命令，确保完整 E2E 59/59 的绿色结果不是由 shell
容错或漏检退出码造成。

## 目标与 ownership

worker 只做只读审计和必要 fresh smoke，写 task 完成区及
`docs/reviews/ML-015l-e2e-fail-closed-command-audit-20260721.md`：

1. 扫描所有 `.test` 的 `RUN` 行，找出 `|| true`、忽略 `$?`、后台运行或
   可能把 QEMU/Gem5 失败转成 PASS 的命令。
2. 对发现的每一类给出文件/行和判定；没有发现也要记录原始命令与 rc。
3. fresh 运行完整 `PATH=.work/build/llvm/bin:$PATH llvm-lit -v tests/lit/E2E/`
   并记录结果，不修改测试语义。

## 约束

- 不修改任何实现、`.test`、LLVM/QEMU/Gem5、vectors、kernel、spec、issues/wiki。
- 不访问或引用 `~/toolchain`、`~/knowledge-graph`，不修改 ML-014a。
- 不使用 `|| true`；不把 lint PASS 等同于 upstream 全量通过。

## 完成区

已完成整个 `tests/lit/E2E/` 的 fail-closed 命令审计（2026-07-21）。

- 扫描 `59` 个 `.test`、`384` 条 `RUN` 行，静态审计命令 rc=`0`。
- 未发现 `|| true`、后台运行命令或以 shell 容错吞掉失败的路径。
- 共 `120` 条包含 QEMU/Gem5 的 RUN 行，其中 `118` 条在该行显式使用
  `test $? -eq N`；`malloc_hello.test` 与 `printf_hello.test` 的 Gem5 输出
  grep 是下一条独立 RUN，但前一条 Gem5 RUN 已检查 `test $? -eq 0`，grep
  自身也通过 `xargs test 1 -eq` 检查 marker。两步均失败会使 lit 失败，记录为
  命令组织上的 finding，不判为退出码被吞掉。
- fresh `PATH=.work/build/llvm/bin:$PATH llvm-lit -v tests/lit/E2E/` → `rc=0`，
  `59/59` pass，`0` fail，`0` skip。

报告：`docs/reviews/ML-015l-e2e-fail-closed-command-audit-20260721.md`。
本任务只读审计，没有修改测试或实现。

### 独立 review

`docs/reviews/ML-015l-independent-review-20260721.md`，结论
**Accepted-with-findings**；reviewer 复核了静态计数和两条 Gem5 两步断言，确认
marker 检查行不读取前一行 `$?` 但不能把前一行 Gem5 失败转成 PASS；该命令组织
finding 保留供未来统一化，不阻塞当前门禁。
