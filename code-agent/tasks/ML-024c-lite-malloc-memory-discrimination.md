# ML-024c：加固 lite_malloc 小分配内存判别测试

日期：2026-07-23

## 状态

待处理。

## 背景

ML-024b 独立 review 接受 ML-024a，但发现
`musl_malloc_sizeclass_liteonly.c` 只检查 `malloc(8)` 非空，不通过返回指针
读写。旧 `AT_PAGESZ=0` 状态下 gem5 会返回非空但未映射地址，因此该测试在 gem5
单独出现假阳性。同时测试命名/注释把 lite_malloc 称为 mallocng size-class，
与实际符号解析不一致。

## Ownership 与约束

- 只修改：
  - `tests/lit/E2E/Inputs/musl_malloc_sizeclass_liteonly.c`
  - `tests/lit/E2E/musl_malloc_sizeclass_liteonly.test`
  - 如确有必要，修订 `musl_malloc_sizeclass.test` 的注释，不改其运行逻辑
  - 本任务完成区及 worker report
- 不修改 LLVM/QEMU/gem5/musl component、patch、series、issues、roadmap、wiki。
- 继续保证链接单元不引用 `free` 或其它会拉入 mallocng 强 `malloc` 的符号。

## 目标与验收

1. 对 lite_malloc 返回的 8 字节执行 volatile 写入和读回，失败码可区分 NULL、
   首尾写读错误。
2. 用 `llvm-nm` 证明最终仍解析为 `W malloc`，不含 mallocng 强符号。
3. 用 prefix-0010 旧 crt1 做负控制：QEMU 与 gem5 都必须失败，gem5 不得继续
   打印成功 marker。
4. 修订标题/注释，使其准确称为 lite_malloc 路径。
5. 当前修复下双后端通过，全量 E2E、differential、manifest/issues 不回归。
6. 由独立 reviewer 复核后方可完成。
