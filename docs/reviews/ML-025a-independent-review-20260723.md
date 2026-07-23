# ML-025a 独立审查：零长度 mmap 双后端一致性

日期：2026-07-23

## 判决

**Accepted-with-findings**

ML-025a 的一致性目标成立，未发现 blocking finding：

- 当前实际运行的 QEMU 与 gem5 都在 `length == 0` 时返回 raw `-EINVAL`
  (`-22`)；
- 两侧早退都发生在 arena cursor 推进以及任何按调用建立的映射/VMA 副作用前；
- 新增 raw syscall 探针能分别判别返回值、首个正常映射地址、真实 backing、
  第二次零长度调用以及后续 cursor；
- 双后端探针、完整 E2E、四方 differential、manifest 和 issues 门禁均通过；
- gem5 series 可从裸 pin 完整重放并得到 live tree。

任务背景所述“当前 gem5 会接受零长度 mmap”已经过时。现有正确实现来自既有
提交，而非 ML-025a 新增修复；因此不应为了满足任务中依赖旧前提的文字要求而
制造空的 QEMU/gem5 commit。

QEMU patch series 确有一个既存的可复现性缺口，但它不由本任务改动引入，也不
改变本任务对当前双后端 mmap 语义的验收。该问题列为 non-blocking finding，
应由独立 reproducibility 任务修复。

## 审查边界

本审查先独立读取任务正文和当前未提交 diff；没有以 worker report 的判断作为
证据。审查只新增本文件，没有修改或提交任务文件、测试、component 源码、
patch series、issues、wiki 或并发中的 LLVM/musl 文件。

运行路径需要明确区分：

- QEMU live source/binary：
  `.work/source/qemu`，HEAD
  `cf5c06bbcf7ac0e176b7f5e52fca48868c3d03a9`。
- E2E 实际使用的 gem5 live source/binary：
  `/home/holight/DADAO-gem5`，HEAD
  `ca12f8261eb6c096d48b50ff206293f32a7d1daa`。
- `.work/source/gem5` 当前是 manifest 裸 pin
  `c8222cc67a399bfc01e8658dd14b30d5bfd634f9`，并不是 E2E 配置使用的
  applied live tree。

两份 live component source 均为干净工作树。

## 源码顺序与副作用

### QEMU

`target/dadao/cpu.c` 的 syscall 222 分支按以下顺序执行：

1. 定义静态 `mmap_cursor` 并读取 `arg1` 到局部 `length`；
2. 在计算 `aligned` 前检查 `length == 0`；
3. 命中后写 raw `-(int64_t)EINVAL` 并直接 `break`；
4. 只有成功路径才读取并推进 `mmap_cursor`。

因此零长度调用不会推进 cursor。QEMU machine 在启动时预先注册整个固定 mmap
RAM `MemoryRegion`；该 backing 并不是一次 syscall 创建的 VMA，所以零长度
调用也没有额外的按调用映射副作用。相关早退来自
`ac58f31acddc7f583e5087002df100297f2f87f9`。

### gem5

`src/arch/dadao/decoder.cc` 的 syscall 222 分支先取得 process/page size 和
`length`，随后检查：

```text
arg0 != 0 || length == 0 || rounding overflow
```

命中后写 raw `ERR_EINVAL` 并 `break`。`aligned` 计算、
`mmapArenaCursor()` 读取、`isUnmapped()`、`mapRegion()` 以及 cursor setter
全部位于该早退之后。因此零长度调用既不建立 VMA，也不推进 arena cursor。
`git blame` 将这一顺序精确归于
`6dd0d7c9f162fa4e414e8824f6129ff5c78a35ed`。

本地 ADR-0014 D2 使用 Linux asm-generic syscall 编号并要求 syscall 层双后端
一致；未发现允许零长度 mmap 成功的相反项目契约。

## 探针判别力

`tests/lit/E2E/mmap_zero_length_consistency.test` 绕过 libc/malloc，直接设置
`rd16=222` 并执行 `trap 2, 0`。逐项检查如下：

1. 首次 `length=0` 后将 `rd31` 与精确的 `-22` 比较；
2. 随后 `length=1` 必须返回 `0x100000000`；
3. 将该地址转入 RB，执行 64-bit store/load 回读；
4. 在首个正常映射后再次调用 `length=0`，仍要求 `rd31 == -22`；
5. 随后 `length=4096` 必须返回 `0x100001000`。

`setzw rd9, 2, 1` 按 ISA wyde 语义精确构造 `0x100000000`；
`add rd0, rd11, rd9, rd2` 将低 64-bit 和写入 `rd11`，精确构造第二个期望
地址。各失败点保留不同退出码 1 至 5；成功路径同时要求 marker
`mmap-zero-ok` 恰好出现一次且退出码为 42。

因此该探针不只是比较最终退出码。两个精确地址能够捕获任一次失败请求错误推进
cursor；首个映射读写能够排除只返回 plausible address 而没有 backing 的实现。
源码顺序审查进一步直接排除了 gem5 的零长度 VMA 副作用。

## 独立运行结果

| 检查 | 结果 |
|---|---|
| `ninja -C .work/source/qemu/build qemu-system-dadao` | rc=0 |
| `scons build/DADAO/gem5.opt -j6`（在 live gem5 tree） | rc=0，target up to date |
| 新增探针（含 QEMU 和 gem5 RUN 行） | 1/1 PASS |
| 完整 `tests/lit/E2E/` | 66/66 PASS |
| differential 三方 | `AGREE=200`，gem5-SKIP=2，`DIVERGE=0` |
| differential 四方 | `AGREE=200`，Sail-SKIP=2，`SAIL-DIVERGE=0` |
| `scripts/manifest_check.py` | PASS |
| `scripts/check_issues.py` | PASS，Open=23 / Closed=34 / Total=57 |

使用 `llvm-lit -a` 复核了展开命令：同一个 ELF/flat binary 分别由配置中的
QEMU 和 `/home/holight/DADAO-gem5/build/DADAO/gem5.opt` 实际执行，两个
backend 的退出码和 marker 检查均被执行，并非只发现测试但跳过其中一侧。

## Patch series 独立重放

### gem5

从 manifest pin
`c8222cc67a399bfc01e8658dd14b30d5bfd634f9` 建立临时裸 checkout，按当前
series 顺序执行全部 15 个 `git am`：

- 15/15 应用成功；
- replay tree：
  `77c92ec86c7f27140d61a9a07e857368ec5baec7`；
- live HEAD tree：
  `77c92ec86c7f27140d61a9a07e857368ec5baec7`。

两者完全一致。

### QEMU

从 manifest pin
`385b0a7d9785c8f3ac7b116d7f31d61502b55183` 原样重放当前 series：

- 0001 至 0007 成功；
- 0008 `0008-dadao-fix-helper-exit.patch` 在
  `target/dadao/helper.c:20` 无法应用，因为目标树尚不存在
  `helper_exit()`。

live pin..HEAD 是无 merge 的 21 个提交，而 series 只有 20 个 patch。唯一缺少
的 live 历史提交是：

```text
e7639ea9a84ecfd42b28d387fb5ca5383999605e
target/dadao: DL-026a divs/divu TCG label fix + machine/CPU hardening
```

该提交不仅创建 `helper_exit()`，还包含对应 machine/CPU/translate 改动。按真实
历史位置在现有 0006 后、0007 前注入由该提交直接生成的 patch，再应用现有
0007 至 0020，全部成功。最终结果：

- 当前 series 20/20 成功，外加注入的 1 个真实缺失提交；
- replay tree：
  `fb88a907774b33fa656e05e6f8ce3308f954d876`；
- live HEAD tree：
  `fb88a907774b33fa656e05e6f8ce3308f954d876`。

因此“缺失 `e7639ea`”的判断精确；在当前线性 pin..HEAD 范围内，没有第二个
被 0008 首错掩盖的源码树缺失。

## Findings

### Blocking

无。

### Non-blocking

1. **QEMU series 缺少 `e7639ea`。** 这不阻塞 ML-025a 对当前 live 双后端
   mmap 一致性的验收，但会阻塞从 manifest 裸 pin 重建完整 QEMU live tree。
   应单独补入正确位置、原样重放并更新可复现性记录。
2. **gem5 的标准 `.work/source/gem5` 与实际 E2E live tree 路径不同。**
   当前 lit 配置明确使用 `/home/holight/DADAO-gem5`，本审查已按该路径验证，
   且 gem5 series 能重建同一 tree；后续报告仍应显式写清 source/binary 路径，
   避免把裸 pin 工作副本写成运行产物来源。

## 后续建议

关闭 ML-025a 时保留“无需 component 语义修复”的事实，并将 QEMU 缺失提交拆为
独立 patch-series reproducibility 任务。修复任务至少应要求：在 0006 与 0007
之间加入由 `e7639ea` 导出的 patch、裸 pin 全链重放、最终 tree 比对，以及
manifest/issues 门禁。
