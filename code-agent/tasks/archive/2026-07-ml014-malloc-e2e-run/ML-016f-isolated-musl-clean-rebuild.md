# ML-016f：隔离 musl clean rebuild 与 archive regeneration

**日期**：2026-07-21

**状态**：Audit-accepted-with-findings（ML-016 新 30-task run：6/30）

## 背景

ML-016e 将 `fflush.o`、`fileno.o`、`__fdopen.o` 等 28 个 stdio object 的首次缺失
定位在主构建的 object/编译输出层，并发现主 archive 还漏掉 3 个已有 object。需要
在隔离副本中做一次完整 clean rebuild，区分“构建可重复生成完整 archive”与“当前
编译链本身仍会失败”。本任务不替换主 archive，也不进入 runtime 修复。

## 目标与 ownership

worker 负责只在 `/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/` 工作：

1. 从当前 source/config/构建参数中恢复实际 musl 构建方式，在 `/tmp` 做 clean
   build；如果完整构建不可行，分层执行 object 编译与 archive 打包，并说明边界。
2. 保存实际命令、环境/配置摘要、逐对象原始退出码与 stderr、成功 object 清单、
   `llvm-ar`/`llvm-ranlib` 原始退出码、archive member 清单、哈希和时间戳。
3. 将主 `.work/build/musl/lib/libc.a` 与隔离产物按 basename 和关键符号对照；
   单独做 `/tmp` 的 link-only probe，确认 `fflush/fileno/fdopen` 是否可解析，
   但不把 link 成功当作 stdio runtime 或 ML-014a 已修复。

## 约束

- 只写本 task 完成区和
  `docs/reviews/ML-016f-isolated-musl-clean-rebuild-20260721.md`；其他产物放
  `/tmp`。
- 不修改主 `.work/build/musl`、musl source、LLVM/QEMU/gem5、contracts、
  vectors、issues、wiki 或 ML-014a。
- 不访问或引用 `~/toolchain`、`~/knowledge-graph`。
- 不使用 `|| true` 隐藏失败；每个阶段保留原始退出码。若完整构建耗时较长，允许
  充分等待，不要用缩减测试替代 clean rebuild。

## 完成区

worker 已完成隔离 clean rebuild，所有构建和中间产物位于
`/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/`；主 archive 未替换。

- configure：`rc=0`；全量 `make -k -j6 lib/crt1.o lib/libc.a`：原始 `rc=2`。
- 逐对象：1163 成功、184 个 LLVM DADAO backend 编译失败；失败原始 stderr、argv、rc 和时间戳均已保存。
- best-effort archive：`llvm-ar rc rc=0`、`llvm-ranlib rc=0`，包含 `__fdopen.o`、`fflush.o`、`fileno.o`；四个 link-only probes（`fflush`、`fileno`、`fdopen`、`__fdopen`）均可解析。
- “全部预期 musl object 的完整 archive”仍不可生成，边界是编译器后端失败，不是 archive 工具失败。

详细原始证据、主 archive 对照、hash/timestamp、probe 和失败边界见
`docs/reviews/ML-016f-isolated-musl-clean-rebuild-20260721.md`。

独立 reviewer Aristotle the 2nd 的结论为 **Accepted-with-findings**，见
`docs/reviews/ML-016f-independent-review-20260721.md`。review 补充两个低严重度边界：
初始 build tree 清场 provenance 不完整，且 archive command log 的 glob 文本不完全
可重放；两者不改变本任务的 rc、对象统计和 link-only 结论。
