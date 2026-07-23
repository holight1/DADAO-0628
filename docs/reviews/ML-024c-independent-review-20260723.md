# ML-024c 独立审查：lite_malloc 内存判别加固

日期：2026-07-23

判决：**Accepted**

## 审查范围

独立读取并核对：

- `code-agent/tasks/ML-024c-lite-malloc-memory-discrimination.md`
- `tests/lit/E2E/Inputs/musl_malloc_sizeclass_liteonly.c` 的当前 diff
- `tests/lit/E2E/musl_malloc_sizeclass_liteonly.test` 的当前 diff
- `docs/reviews/ML-024c-worker-report-20260723.md`

未采信 worker 的结论或既有运行产物。Reviewer 在独立临时目录
`/tmp/ml-024c-reviewer.hkmF0j` 中重新编译、链接、反汇编并运行正向和
prefix-0010 负控制，然后重新执行完整门禁。

## 独立核对结果

### 1. lite_malloc 符号边界

按测试中的 `-O2` 参数重新编译输入对象，`llvm-nm -u` 只有：

```text
U malloc
U puts
```

输入对象不引用 `free`，也不定义或带入强 `malloc` 实现。重新链接后的最终
ELF 中：

```text
0000000080001788 W malloc
```

最终 ELF 不含 `free` 符号。link map 将 `__simple_malloc`、
`__libc_malloc` 和 `default_malloc` 定位到
`libc.a(lite_malloc.o)`，确认没有被 mallocng 强入口替换。

结论：**PASS**。

### 2. `-O2` 下真实内存写读

重新生成的 `main` 机器码包含：

```text
stb  ..., rb8, 0
stb  ..., rb8, 7
ldbu ..., rb8, 0
ldbu ..., rb8, 7
```

反汇编同时显示写入常量 `0x5a`、`0xa5`，读回后分别通过 `brne` 比较，
失败路径预置返回码 12、13。NULL 路径预置返回码 11。

因此 volatile 首尾字节写入、读回和判别分支均在 `-O2` 机器码中真实保留，
不是仅凭源码推断。

结论：**PASS**。

### 3. 当前 crt1 双后端正向

Reviewer 使用当前 `crt1.o`、重新编译的输入对象及当前 `libc.a` 独立链接：

```text
QEMU: rc=42, SIZECLASS_LITE_OK count=1
gem5: rc=42, SIZECLASS_LITE_OK count=1
```

目标 lit 用例也独立执行通过。

结论：**PASS**。

### 4. prefix-0010 负控制

Reviewer 核实负控制源码 checkout：

```text
commit fe3f43b6a1682398128e0f89f4ac273b2da32294
tree   9d3cf0b395a1029f9fb00a101b53ea1c33b75f33
```

从该源码重新编译旧 `crt1.o`。旧对象在 AT_PAGESZ 值槽位 `0x34` 的实际机器码
为：

```text
addi rd8, rd0, 0
```

Reviewer 重建的旧对象 SHA-256 为
`30cddc965bb53d2a2d1c597d06bb7878d7e63f7fcc8d952ee8c48e947bae167d`，
并与 worker 产物逐字节一致。其余输入对象、`libc.a`、linker script 和运行器
保持当前版本，运行结果：

```text
QEMU: rc=11, SIZECLASS_LITE_OK count=0
gem5: rc=134, SIZECLASS_LITE_OK count=0
```

gem5 日志明确报告：

```text
Page table fault when accessing virtual address 0xffffffffffff
```

这证明旧 crt1 在 QEMU 的 NULL 判别和 gem5 的首次真实内存访问上均不能通过，
尤其 gem5 先前只验证非 NULL 所产生的假阳性已经消失。

结论：**PASS**。

### 5. 完整门禁

Reviewer 独立执行：

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

结论：**PASS**。

## Findings

### Blocking

无。

### Non-blocking

1. prefix-0010 的 `_start_c` 在当前 assertions-enabled LLVM 上以普通 `-O2`
   编译会触发已有的 tail-call assertion；独立重建需要显式加入
   `-fno-optimize-sibling-calls`。加入后对象与 worker 产物逐字节一致，且不改变
   本任务需要判别的旧 AT_PAGESZ 机器码。worker report 没有记录这一关键编译
   参数，后续若固化负控制，应把完整命令写入可重复脚本或测试。
2. 完整 E2E 的 66 项包含并发 ML-025a 加入的
   `mmap_zero_length_consistency.test`。这不影响 ML-024c 目标用例及其独立
   正负对照，但 66/66 应理解为当前工作树的联合回归结果，而不是 ML-024c
   独占增量。

## 最终结论

ML-024c 已满足任务验收条件：lite_malloc-only 链接边界保持，`-O2` 产物包含
真实首尾字节写读，当前 QEMU/gem5 正向均成功，prefix-0010 在两个后端均无成功
marker，且 gem5 旧假阳性被真实内存 fault 消除；全量 E2E、differential、
manifest 和 issues 门禁均通过。不存在阻塞 finding，判决为 **Accepted**。
