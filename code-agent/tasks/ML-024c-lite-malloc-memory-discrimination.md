# ML-024c：加固 lite_malloc 小分配内存判别测试

日期：2026-07-23

## 状态

已完成；独立 review 判决 **Accepted**。

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

## Worker 完成区（2026-07-23）

### 修改

- `musl_malloc_sizeclass_liteonly.c` 仍只调用 `malloc()` 与 `puts()`，不调用
  `free()`；把返回值转换为 `volatile unsigned char *`，分别写入并读回第 0、
  第 7 字节。NULL、首字节读回错误、尾字节读回错误的返回码依次为
  11、12、13。
- 输入文件和 `.test` 文件的标题/注释改为准确的 `lite_malloc`
  small-allocation memory-discrimination 描述。
- 未修改 `musl_malloc_sizeclass.test`：它现有注释已经明确区分 mallocng 与
  lite_malloc，运行逻辑也无需调整。

### 符号与代码生成

- 测试输入对象的未定义符号只有 `malloc` 与 `puts`，不含 `free`。
- 最终 ELF 中 `malloc` 为 `0000000080001788 W malloc`，没有最终
  `free` 符号；link map 显示实现来自 `libc.a(lite_malloc.o)`。
- `main` 反汇编保留两条 `stb`（偏移 0、7）和两条 `ldbu`（偏移 0、7），
  volatile 内存判别没有被 `-O2` 消除。

### 当前正向与 prefix-0010 负控制

- 当前 crt1：
  - QEMU：rc=42，`SIZECLASS_LITE_OK` 出现 1 次；
  - gem5：rc=42，`SIZECLASS_LITE_OK` 出现 1 次；
  - 目标 `llvm-lit`：1/1 PASS。
- prefix-0010 使用 musl commit
  `fe3f43b6a1682398128e0f89f4ac273b2da32294` 的 `crt_arch.h` 独立编译旧
  `crt1.o`，其反汇编在 AT_PAGESZ 值槽位显示
  `addi rd8, rd0, 0`：
  - QEMU：rc=11，无成功 marker；
  - gem5：对 `0xffffffffffff` 的首字节访问触发 page-table fault，
    进程中止 rc=134，无成功 marker。

因此旧 crt1 在两个后端都不能通过；此前 gem5 只检查非 NULL 的假阳性已被真实
内存访问消除。

### 完整门禁

```text
llvm-lit -sv tests/lit/E2E/
  66/66 PASS

PYTHONDONTWRITEBYTECODE=1 python3 tools/run_differential.py
  AGREE(3-way)=200
  AGREE(interp+QEMU, gem5-SKIP)=2
  DIVERGE=0
  AGREE(4-way)=200
  Sail-SKIP=2
  SAIL-DIVERGE=0

PYTHONDONTWRITEBYTECODE=1 python3 scripts/manifest_check.py
  PASS

PYTHONDONTWRITEBYTECODE=1 python3 scripts/check_issues.py
  Open=23 Closed=34 Total=57 PASS
```

完整 E2E 的 66 项包含并发 ML-025a 工作流已放入工作树的
`mmap_zero_length_consistency.test`；本 worker 未修改该文件。

详细命令和证据见
`docs/reviews/ML-024c-worker-report-20260723.md`。本 worker 未提交主仓，
等待独立 review。

## 独立 review

- 报告：`docs/reviews/ML-024c-independent-review-20260723.md`
- 判决：Accepted，无 blocking finding。
- 独立复核 `W malloc`、`-O2` 真实首尾写读、当前双后端正向、
  prefix-0010 双后端负控制以及全部门禁。
- reviewer 补充指出 prefix-0010 的 `_start_c` 在当前 LLVM 下重建需显式
  `-fno-optimize-sibling-calls`；这属于既有 tail-call issue，不影响本任务
  结论，负控制参数应在未来若固化为脚本时完整记录。
