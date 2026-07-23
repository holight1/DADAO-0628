# ML-024c worker report：lite_malloc 内存判别加固

日期：2026-07-23

状态：Worker 完成，待独立 review。

## 范围

本 worker 只修改：

- `tests/lit/E2E/Inputs/musl_malloc_sizeclass_liteonly.c`
- `tests/lit/E2E/musl_malloc_sizeclass_liteonly.test`
- `code-agent/tasks/ML-024c-lite-malloc-memory-discrimination.md`
- 本报告

未修改 component、patch、series、issues、wiki、roadmap，也未提交主仓。
工作树开始时已有 ML-025a、IN-006a 和 LLVM patch 的并发改动，本 worker
未触碰。

## 测试改动

`malloc(8)` 返回值保持为 lite_malloc-only 链接边界，并通过
`volatile unsigned char *` 执行：

```c
p[0] = 0x5a;
p[7] = 0xa5;
if (p[0] != 0x5a) return 12;
if (p[7] != 0xa5) return 13;
```

NULL 返回码仍为 11。成功路径仍打印 `SIZECLASS_LITE_OK` 并返回 42。
输入和测试注释均改称 lite_malloc small-allocation
memory-discrimination，不再把该路径称作 mallocng size-class 变体。

## 链接边界与机器码

按 lit 相同参数独立编译、链接后：

```text
input object undefined:
  U malloc
  U puts

final ELF:
  0000000080001788 W malloc
  no final free symbol

link map:
  libc.a(lite_malloc.o): .text.__simple_malloc
  libc.a(lite_malloc.o): .text.default_malloc
```

输入对象不引用 `free`，最终 `malloc` 仍是 lite_malloc 的弱符号。`main`
反汇编中有：

```text
stb  ..., rb8, 0
stb  ..., rb8, 7
ldbu ..., rb8, 0
ldbu ..., rb8, 7
```

因此首尾写读没有被 `-O2` 优化掉。

## 正向运行

目标 lit：

```text
.work/build/llvm/bin/llvm-lit -sv \
  tests/lit/E2E/musl_malloc_sizeclass_liteonly.test

1/1 PASS
```

对独立生成的当前 ELF/BIN 手工执行：

```text
QEMU: rc=42, SIZECLASS_LITE_OK count=1
gem5: rc=42, SIZECLASS_LITE_OK count=1
```

## prefix-0010 负控制

从 musl prefix-0010 commit
`fe3f43b6a1682398128e0f89f4ac273b2da32294` 的隔离 shared clone 编译旧
`crt1.o`，其余测试对象、`libc.a`、linker script 和运行器保持当前版本。
旧 crt1 反汇编在 AT_PAGESZ 值槽位 `0x34` 显示：

```text
addi rd8, rd0, 0
```

运行结果：

```text
QEMU:
  rc=11
  SIZECLASS_LITE_OK absent

gem5:
  rc=134
  SIZECLASS_LITE_OK absent
  Page table fault when accessing virtual address 0xffffffffffff
```

QEMU 在 NULL 检查处失败；gem5 的非 NULL、无 backing 指针在第一条
volatile store 处触发 page-table fault。两个后端都不再接受旧 crt1，尤其消除
了 gem5 先前只看非 NULL 而产生的假阳性。

负控制与手工正向证据位于临时目录：

```text
/tmp/ml-024c-worker-20260723.SofyPp
```

## 完整门禁

```text
.work/build/llvm/bin/llvm-lit -sv tests/lit/E2E/
  66/66 PASS

PYTHONDONTWRITEBYTECODE=1 python3 tools/run_differential.py
  AGREE(3-way)=200
  AGREE(interp+QEMU, gem5-SKIP)=2
  DIVERGE=0
  HARNESS=0
  QEMU-SKIP=0
  AGREE(4-way)=200
  Sail-SKIP(out-of-slice)=2
  SAIL-DIVERGE=0

PYTHONDONTWRITEBYTECODE=1 python3 scripts/manifest_check.py
  manifest validation: PASS

PYTHONDONTWRITEBYTECODE=1 python3 scripts/check_issues.py
  Open=23 Closed=34 Total=57
  ISSUE REGISTRY: PASS
```

完整 E2E 的 66 项包含并发 ML-025a 工作流新增但未提交的
`mmap_zero_length_consistency.test`。本 worker 没有修改该测试。

## Worker 结论

ML-024c 的 worker 验收项已满足：lite_malloc-only 符号边界未变，真实首尾
内存写读已加入，prefix-0010 在 QEMU 与 gem5 上均失败且无 marker，当前双后端
正向与完整门禁通过。任务保持“待独立 review”，本 worker 不提交主仓。
