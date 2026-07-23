# ML-025a worker report：零长度 mmap 双后端一致性

日期：2026-07-23  
角色：worker（非独立 reviewer）

## 1. Worker 判决

**当前实现一致；任务背景已过时；测试补强完成；等待独立 review。**

当前 QEMU/gem5 对 raw syscall 222、`length=0` 都返回 raw `-EINVAL`
（64-bit two's complement `-22`），并在任何 cursor/VMA 修改之前退出。
本轮新增判别性 E2E 并完成双后端和全门禁验证，但没有合理的 simulator 源码
修复可做，因此没有创建空 component commit 或伪造 patch。

另发现一个与 mmap 无关、但阻塞任务“QEMU 完整 series 重放”验收的既有问题：
QEMU component series 漏掉 live 历史提交 `e7639ea...` 的 patch。

## 2. 初始状态与源码事实

```text
main HEAD: b7d3de8 task: dispatch post-ML-024 consistency and replay cleanup
QEMU HEAD: cf5c06bbcf7ac0e176b7f5e52fca48868c3d03a9
gem5 HEAD: ca12f8261eb6c096d48b50ff206293f32a7d1daa
QEMU status: clean
gem5 status: clean
```

QEMU `target/dadao/cpu.c`：

```c
if (length == 0 || length > UINT64_MAX -
    (DADAO_MMAP_PAGE_SIZE - 1)) {
    ret = (uint64_t)(-(int64_t)EINVAL);
    break;
}
```

gem5 `src/arch/dadao/decoder.cc`：

```c++
if (arg0 != 0 || length == 0 ||
    length > std::numeric_limits<uint64_t>::max() - page_mask) {
  ret = static_cast<uint64_t>(ERR_EINVAL);
  break;
}
```

gem5 `git blame -L 719,752 -- src/arch/dadao/decoder.cc` 将检查、
`mapRegion()` 和 cursor 更新全部归于 `6dd0d7c9f1`；错误早退位于后两者之前。

## 3. 契约核对

项目 ADR-0014 D2 将 syscall 软件 ABI 定为：

```text
rd16=sysno, rd17..rd22=args, rd31=return,
Linux asm-generic syscall numbering
```

并要求 QEMU/gem5 syscall 层一致。未发现零长度 mmap 的相反项目契约。

本机对应 Linux UAPI 头的证据：

```text
/usr/include/asm-generic/unistd.h:570:#define __NR3264_mmap 222
/usr/include/asm-generic/unistd.h:870:#define __NR_mmap __NR3264_mmap
```

Linux 主线 `mm/mmap.c` `do_mmap()` 的顺序是：

```c
if (!len)
    return -EINVAL;
...
len = PAGE_ALIGN(len);
```

即在地址选择和 VMA 建立前拒绝零长度请求。Linux man-pages `mmap(2)` 也明确
记录 Linux 2.6.12 起 `length==0` 返回 `EINVAL`。

## 4. Raw probe

新增：

```text
tests/lit/E2E/mmap_zero_length_consistency.test
```

探针内部验证两个 raw `-22`、arena base、下一页精确地址及 backing 回读。

手工命令使用：

```bash
.work/build/llvm/bin/llvm-mc -triple=dadao -filetype=obj \
  -o "$probe/probe.o" tests/lit/E2E/mmap_zero_length_consistency.test
.work/build/llvm/bin/ld.lld -T tests/scripts/dadao.ld \
  "$probe/probe.o" -o "$probe/probe.elf"
.work/build/llvm/bin/llvm-objcopy -O binary \
  "$probe/probe.elf" "$probe/probe.bin"
.work/source/qemu/build/qemu-system-dadao \
  -M dadao-m1 -nographic -bios tests/scripts/trampoline.bin \
  -kernel "$probe/probe.bin"
/home/holight/DADAO-gem5/build/DADAO/gem5.opt \
  /home/holight/DADAO-gem5/tests/dadao/dadao_se.py "$probe/probe.elf"
```

真实结果：

```text
QEMU: mmap-zero-ok
QEMU_RC=42
gem5: SIM_END: trap-exit code=42
gem5: mmap-zero-ok
GEM5_RC=42
```

手工产物目录：`/tmp/ml-025a-probe-BfUAfX`。

## 5. 构建与回归命令

```text
ninja -C .work/source/qemu/build qemu-system-dadao
  exit 0

(cd /home/holight/DADAO-gem5 &&
 scons build/DADAO/gem5.opt -j6)
  exit 0; target is up to date

.work/build/llvm/bin/llvm-lit -sv \
  tests/lit/E2E/mmap_zero_length_consistency.test
  1/1 PASS

.work/build/llvm/bin/llvm-lit -sv tests/lit/E2E/
  66/66 PASS

python3 tools/run_differential.py
  AGREE(3-way)=200
  AGREE(interp+QEMU, gem5-SKIP)=2
  DIVERGE=0
  AGREE(4-way)=200
  Sail-SKIP=2
  SAIL-DIVERGE=0

python3 scripts/manifest_check.py
  PASS

python3 scripts/check_issues.py
  Open=23 Closed=34 Total=57 PASS
```

## 6. Series replay

### gem5

临时目录：`/tmp/ml-025a-gem5-replay-kAfMHu`。

从 pin `c8222cc67a399bfc01e8658dd14b30d5bfd634f9` 按
`components/gem5/patches/series` 依次 `git am`，15/15 成功。
重放 HEAD 为 `a1002e8c...`（commit hash 因 committer metadata 不同而不同），
与 live `ca12f826...` 执行 `git diff --exit-code` 为 0，tree 一致。

### QEMU

首次临时目录：`/tmp/ml-025a-replay-7XrKHe`。

从 pin `385b0a7d9785c8f3ac7b116d7f31d61502b55183` 重放：

```text
0001..0007(series 前七项): applied
0008-dadao-fix-helper-exit.patch:
  error: patch failed: target/dadao/helper.c:20
```

live 历史显示 series 遗漏：

```text
e7639ea9a84ecfd42b28d387fb5ca5383999605e
target/dadao: DL-026a divs/divu TCG label fix + machine/CPU hardening
```

该提交创建 `helper_exit()`，后续 0008 才能修改它。诊断临时目录
`/tmp/ml-025a-qemu-replay-diag-ITqvHF` 中，在现有 0006 后注入该真实 commit
的 `git format-patch` 输出，再继续 series，所有后续 patch 成功，最终 tree
与 live `cf5c06bb...` 一致。

这是一条精确、可独立修复的 series 漏项；本 worker 未越权修改 patch 链。

## 7. 改动与边界

本任务改动：

- 新增 `tests/lit/E2E/mmap_zero_length_consistency.test`
- 更新 ML-025a 完成区
- 新增本 worker report

未修改：

- QEMU/gem5 源码、commit 或 component patch/series
- LLVM、musl、spec/contract、kernel、wiki、issues

主仓未 commit。验证期间并发出现的 LLVM 0005 patch 修改属于 IN-006a worker，
本任务未读取后继续修改，也未纳入 ML-025a 结论。

## 8. 交给独立 reviewer 的重点

1. 不采信本报告，独立重跑新增探针并核对 exact-address checks。
2. 独立检查两个 responder 的早退顺序，确认 gem5 在
   `mapRegion()`/cursor update 前退出。
3. 判断在任务前提已过时的情况下，“不新增 simulator commit/patch”是否应按
   Accepted-with-findings 接受。
4. 独立复现 gem5 15/15 replay 和 QEMU missing-`e7639ea` finding。
