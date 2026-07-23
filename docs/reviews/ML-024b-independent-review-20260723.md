# ML-024b：mallocng size-class 修复独立验收

日期：2026-07-23
角色：独立 reviewer
判决：**Accepted-with-findings**

## 1. 判决摘要

ML-024a 的核心修复可以接受：

- `addi rd8, rd0, 4096` 违反 ISA 的有符号 12 位立即数范围；
- `setzw rd8, 0, 4096` 能按 spec 精确构造 4096；
- musl 导出 patch 与 component commit 的 patch-id 一致；
- 从 musl 裸 pin `0784374d561435f7c787a555aeab8ede699ed298`
  完整重放 0001～0011 成功，最终 tree 与 `.work/source/musl` 完全一致；
- malloc+free 与 malloc-only 二进制确实解析到不同 allocator；
- 三条目标 lit、完整 E2E、四方 differential、manifest 和 issues 门禁均通过；
- 修复前 crt1 的独立负控制能够稳定复现失败，修复后 QEMU/gem5 均通过。

**Blocking finding：无。**

存在三个 non-blocking findings：

1. `musl_malloc_sizeclass_liteonly.c` 只检查返回指针是否为 NULL，没有通过该
   指针执行真实读写；修复前它在 gem5 上仍会返回 42 并打印成功 marker。
2. lite-only 测试的标题和注释仍称其为“mallocng size-class”变体，但符号证据
   表明它实际测试的是独立的 `lite_malloc` 路径。
3. 当前 assembler 对越界 `addi` 立即数仍静默截断；本修复避开了该问题，但
   没有消除这一系统性风险。

这些 finding 不否定 ML-024a 修复本身，也不阻塞目标 commit 保留和收口。

## 2. 审查边界与仓库快照

本审查直接检查 diff、spec、component commit、patch、链接产物和运行结果，
没有采信 ML-024a 完成区或已有自审结论。

审查开始时：

```text
main HEAD = 82c3f1c2be3c30bac17c1fc87480cdda70202be8
ML-024a 的 9 项改动位于 index
musl HEAD = b3240b4a76ed143952af45dc4550e749cf08312b
```

审查期间有另一条并发工作流提交了被审改动：

```text
03aa5bff0f43d3a6f10ee7a7510ddf0ebf4f3524
ML-024a: fix AT_PAGESZ auxv immediate overflow, unblocking mallocng size-class path
```

随后 main 又前进到 `b7d3de89201a8f226e4cda1264fbb7d400a8b644`，并出现与
本审查无关的 LLVM patch 和 mmap 测试在途改动。本报告的验收对象仍是开始时
读取的 9 项 ML-024a diff，即 commit `03aa5bff...` 的内容；不能据此宣称最终
main 工作树整体 clean。

审查结束前读取到的 component 状态：

```text
LLVM            4b812d2f99305a259a3d37a827d67c6c1ae14546  clean
QEMU            cf5c06bbcf7ac0e176b7f5e52fca48868c3d03a9  clean
musl            b3240b4a76ed143952af45dc4550e749cf08312b  clean
gem5            ca12f8261eb6c096d48b50ff206293f32a7d1daa  clean
llvm-test-suite 68d03c39d62c2ef9ec663530066bdb66ca5cc4f6  clean
```

本 reviewer 没有提交 git，也没有修改 task、issues、wiki、roadmap 或任何
component 源仓。

## 3. diff 与 ISA 语义

检查命令：

```sh
git diff --cached -- \
  components/musl/patches/0011-dadao-fix-AT_PAGESZ-auxv-immediate-overflow-in-crt_a.patch \
  components/musl/patches/series \
  tests/lit/E2E/Inputs/musl_malloc_sizeclass.c \
  tests/lit/E2E/Inputs/musl_malloc_sizeclass_liteonly.c \
  tests/lit/E2E/musl_crt0_auxv.test \
  tests/lit/E2E/musl_malloc_sizeclass.test \
  tests/lit/E2E/musl_malloc_sizeclass_liteonly.test \
  tests/scripts/crt0_auxv.s

sed -n '132,160p' contracts/isa/spec.md
sed -n '451,463p' contracts/isa/spec.md
sed -n '604,626p' contracts/isa/spec.md
```

权威 contract 给出：

- `imms12` 是有符号 12 位，范围 `-2048..2047`；
- RD `addi` 语义是加上 `sext_12(imms12)`；
- `setzw rdha, ww, immu16` 将目标 wyde 设为无符号 16 位立即数，其余
  wydes 清零；
- `ww=0` 对应 bits `[15:0]`。

因此：

```asm
setzw rd8, 0, 4096
```

精确产生 64 位值 `0x0000000000001000`，替换语义正确。

对 prefix-0010 源码独立构建旧 crt1 后，反汇编显示：

```text
0x34: addi rd8, rd0, 0
```

即源码中的 4096 已被静默截断为 0。当前 crt1 反汇编显示：

```text
0x34: setzw rd8, 0, 4096
```

这直接验证了根因和修复后的实际机器码，而不只依赖源码描述。

## 4. patch 导出与完整重放

### 4.1 commit 与导出 patch

命令：

```sh
git patch-id --stable \
  < components/musl/patches/0011-dadao-fix-AT_PAGESZ-auxv-immediate-overflow-in-crt_a.patch

git -C .work/source/musl show --pretty=email --no-ext-diff \
  b3240b4a76ed143952af45dc4550e749cf08312b |
  git patch-id --stable
```

两者结果均为：

```text
f89ef81a2178afac423c6a356fd7b6c50d32c0f4
```

commit parent 为：

```text
fe3f43b6a1682398128e0f89f4ac273b2da32294
```

因此 0011 的 payload 与 `b3240b4a...` 一致。

### 4.2 0001～0011 裸 pin 重放

在 `/tmp/ml-024b-review-20260723.bKuwZz/musl-replay` 的隔离 clone 中执行：

```sh
git checkout 0784374d561435f7c787a555aeab8ede699ed298
while IFS= read -r patch_name; do
  git am "/home/holight/DADAO-0628/components/musl/patches/$patch_name"
done < /home/holight/DADAO-0628/components/musl/patches/series
```

0001～0011 全部无冲突应用。关键结果：

```text
replay tree = 2f550acf5cff0c0e8fa18b672927315853632308
source tree = 2f550acf5cff0c0e8fa18b672927315853632308
replay status = clean
```

同时，重放 0001～0010 的 tree 为：

```text
9d3cf0b395a1029f9fb00a101b53ea1c33b75f33
```

它也与 `b3240b4a^` 的 tree 完全一致。`git am` 产生的 commit hash 因
committer metadata 不同而不同，但两阶段 tree identity 均闭合。

## 5. allocator 符号解析

使用与 lit 相同的 clang、linker script、crt1 和 `libc.a` 独立编译两个输入，
链接时增加：

```sh
ld.lld ... -Map=<map> --trace-symbol=malloc --trace-symbol=free ...
llvm-nm -an <elf>
llvm-objdump --triple=dadao -d --disassemble-symbols=main <elf>
```

### 5.1 malloc+write+read+free

链接 trace：

```text
musl_malloc_sizeclass.o: reference to malloc
musl_malloc_sizeclass.o: reference to free
libc.a(lite_malloc.o): definition of malloc
libc.a(free.o): definition of free
libc.a(malloc.o): definition of malloc
```

最终 ELF：

```text
0000000080001f28 T free
00000000800049b0 T malloc
```

最终 `malloc` 为来自 mallocng `malloc.o` 的强符号，`free` 也已链接；
虽然 `lite_malloc.o` 因 libc 的其它入口仍存在于 ELF，调用解析并未落到其弱
`malloc`。反汇编还确认测试保留了实际 `stb` 写入和 `ldbu` 读回，未被 `-O2`
折叠。

### 5.2 malloc-only

链接 trace 和最终 ELF：

```text
musl_malloc_sizeclass_liteonly.o: reference to malloc
libc.a(lite_malloc.o): definition of malloc

0000000080001314 t __simple_malloc
000000008000174c t default_malloc
000000008000174c W malloc
```

最终 `malloc` 是 `lite_malloc.o` 的弱符号，ELF 中没有最终 `free`，也没有
mallocng 的强 `malloc`。两个测试确实覆盖不同 allocator 解析结果。

## 6. 正向运行与负控制

### 6.1 当前修复的手工双后端运行

```text
musl_malloc_sizeclass:
  QEMU rc=42, marker=SIZECLASS_OK
  gem5 rc=42, marker=SIZECLASS_OK

musl_malloc_sizeclass_liteonly:
  QEMU rc=42, marker=SIZECLASS_LITE_OK
  gem5 rc=42, marker=SIZECLASS_LITE_OK
```

### 6.2 prefix-0010 crt1 负控制

从完整重放的 0010 状态单独构建旧 `crt1.o`，其余对象和链接参数保持不变：

```text
                             QEMU                  gem5
malloc+write+read+free       rc=21, no marker      rc=129, MALIGN
malloc-only                  rc=11, no marker      rc=42, SIZECLASS_LITE_OK
```

这证明：

- mallocng 用例在两个后端都能区分修复前后，且 gem5 的 unbacked pointer 会被
  真实内存访问捕获；
- lite-only 用例作为“双后端整体门禁”能够由 QEMU 捕获旧 bug，但它单独在
  gem5 上缺少内存访问判别力。

### 6.3 auxv 补偿错误负控制

在隔离测试副本中保留当前 fixed checker，但将 producer
`tests/scripts/crt0_auxv.s` 换回 main `82c3f1c...` 的旧版本。结果：

```text
llvm-lit musl_crt0_auxv.test: rc=1, 0/1
QEMU direct rc=6
gem5 direct rc=6
```

因此 producer 为 0、checker 期望 4096 时会在两个后端失败；当前 producer 和
checker 同时修正后通过，不再是“双方都错误地得到 0”的补偿性假通过。

## 7. 运行门禁

为避免污染主仓和避免并发在途改动进入验收，lit 在隔离复制的测试树中运行，
工具、musl 构建物和 component 二进制仍取自被审快照。

### 7.1 三条目标 lit

```sh
llvm-lit -v \
  musl_malloc_sizeclass.test \
  musl_malloc_sizeclass_liteonly.test \
  musl_crt0_auxv.test
```

结果：

```text
Total Discovered Tests: 3
Passed: 3
rc=0
```

### 7.2 完整 E2E

```sh
llvm-lit -v tests/lit/E2E/
```

结果：

```text
Total Discovered Tests: 65
Passed: 65
rc=0
```

这是仓库 thin-lit E2E 入口的 65 项结果，不代表完整 upstream
`llvm-test-suite`。

### 7.3 differential

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tools/run_differential.py
```

结果：

```text
AGREE(3-way)=200
AGREE(interp+QEMU, gem5-SKIP)=2
DIVERGE=0
HARNESS=0
QEMU-SKIP=0
SAIL AGREE(4-way)=200
Sail-SKIP(out-of-slice)=2
SAIL-DIVERGE=0
rc=0
```

### 7.4 manifest 与 issues

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/manifest_check.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/check_issues.py
```

结果：

```text
manifest validation: PASS, rc=0
Open=23, Closed=34, Total=57
ISSUE REGISTRY: PASS, rc=0
```

## 8. Findings

### Blocking findings

无。

### Non-blocking finding 1：lite-only 缺少真实内存访问

`musl_malloc_sizeclass_liteonly.c` 只执行：

```c
void *p = malloc(8);
if (!p) return 11;
puts("SIZECLASS_LITE_OK");
```

它没有通过 `p` 写入和读回。负控制已经实证：旧 crt1 在 gem5 上仍返回 42 并
打印 marker。双后端组合门禁目前由 QEMU 捕获该旧 bug，因此不阻塞 ML-024a；
但 gem5 单腿并不能证明 lite_malloc 返回地址有真实 backing。

建议后续在不引用 `free`、不改变弱 `malloc` 解析的前提下，将 `p` 转为
`volatile unsigned char *`，至少写入并读回一个或多个字节，再复验最终符号仍为
lite_malloc 的弱 `malloc`。

### Non-blocking finding 2：lite-only 注释与实际覆盖名称不一致

`musl_malloc_sizeclass_liteonly.test` 和对应 C 文件仍使用“mallocng
size-class ... lite_malloc-linked variant”表述。符号核验表明这是独立的
lite_malloc bump allocator，不是 mallocng size-class 的一种链接变体。

建议改称“lite_malloc small-allocation / page-size regression”，并将
mallocng size-class 与 lite_malloc 两条覆盖边界分开描述。

### Non-blocking finding 3：assembler 仍接受越界立即数

旧源码中的 `addi ..., 4096` 被 assembler 静默编码为 0，而不是报范围错误。
ML-024a 用 `setzw` 正确规避了该实例，但未来代码仍可能重现同类错误。

建议由独立后续任务修复 MC/AsmParser 范围诊断，并增加 `2047/-2048` 成功、
`2048/-2049/4096` 失败的边界测试。该问题不阻塞当前 musl 修复。

### 流程记录

ML-024a commit `03aa5bff...` 在本独立审查完成前由并发工作流提交，因此本报告
是 post-commit acceptance，而不是 pre-commit gate。技术判决仍为可接受；
后续同类任务应在独立 review 判决后再执行收口提交。

## 9. 最终结论

**Accepted-with-findings。**

ML-024a 的根因、修复语义、allocator 符号分流、patch provenance、完整 musl
series 重放和运行门禁均已由 reviewer 独立闭合。没有 blocking finding；
commit `03aa5bff...` 可保留并视为 ML-024a 技术收口。

后续应优先补强 lite_malloc 测试的真实内存访问，再处理 assembler 立即数范围
诊断。由于审查期间 main 上已有其它并发在途改动，本判决不扩展为“当前 main
工作树整体可提交”。
