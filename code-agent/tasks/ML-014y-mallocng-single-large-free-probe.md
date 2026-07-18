# ML-014y：真实 mallocng 单次大块 free probe

**执行环境**：本地 subagent worker；承接 Accepted ML-014w/x

**状态**：Completed（2026-07-18，等待独立 review）

## 目标

隔离验证真实 mallocng 的单次大块分配、首尾写读和 `free` 返回路径。probe 不做
高层输出、不做第二次分配；用分阶段 guest exit 区分 NULL、首写读、末写读以及
free 之前/之后的控制流，成功返回 42。

## Ownership

- worker 只写 `.work/ML-014y-*` probe/runner/产物与本 task MD。
- 沿用当前 ML-014v clang、锁定 lld/crt1/libc.a/script 与当前 QEMU/gem5；不得
  修改源码、root tests、patch series、issues、contracts、manifests 或 ML-014a。
- 分配大小固定 `131052`，必须调用真实 `free`；不得以 stub/no-op 替代。
- 无 printf/puts/varargs；外部架构资料不在 worker scope。

## 执行阶梯

1. 构造 `malloc(131052)`，检查非 NULL；首尾 byte 写读，各失败码独立。
2. 调用真实 `free(p)`，随后只设置/检查栈上或全局 marker，禁止 use-after-free；
   成功返回 42。
3. 核对 ELF/map/undefined/archive member，证明拉入 mallocng `free`/munmap 路径，
   且末端访问使用完整地址、无 `-21`。
4. 同一产物跑 QEMU/gem5，记录退出码、fault、syscall/munmap 可得证据。
5. 更新记录、自审并等待独立 review。

## 验收

- 双后端真实 exit 42，且反汇编与 archive 证据证明调用真实 free；否则记录 blocker。
- 无 use-after-free、无输出依赖，不把单次 free 冒充复用、多尺寸或 allocator 总体。
- 不宣称 ML-014f/ML-014a 完成。

## 完成区

### Finding：真实 mallocng 单次大块首尾写读与 free 在双后端 exit 42

本轮只新增 `.work/ML-014y-mallocng-single-large-free-probe/` 内的 probe、runner、
构建产物和原始证据，并更新本 task MD。直接复用 ML-014x/ML-014w 锁定的 clang、
lld、crt1、libc.a、linker script 及当前 QEMU/gem5；没有重建或修改任何实现源码、
root tests、历史 `.work`、patch series、issues、contracts、manifests 或 ML-014a。

#### 1. Probe 合同与 free 后边界

`malloc_single_large_free.c` 只声明并调用 `malloc`/`free`，固定执行
`malloc(131052)`。退出码分流为：NULL → 10，首字节 `0xa5` 写读失败 → 11，
末字节 `p[131051]` 的 `0x5a` 写读失败 → 12，free 前全局 volatile marker 失败
→ 13，`free(p)` 返回后原 marker 未保持 → 14，随后 post-free marker 设置/检查
失败 → 15，全部通过 → 42。

源码在 `free(p)` 后不再解引用、计算或读取 `p`，只读取旧 marker、设置并检查
post-free marker 后返回；故没有 UAF，也没有第二次分配。object undefined 恰为
`malloc`、`free` 两项；`forbidden-output-dependencies.txt` 为空，没有
printf/puts/write/varargs 或 guest 输出依赖。完整命令在 `commands.txt`，runner 为
`run_probe.sh`，compile/link/objcopy sidecar 均为 0，最终 `validation.rc=0`。

#### 2. 完整末端地址与真实 free/munmap 链

`main.disassembly.txt` 在 `0x80000184..0x8000018c` 以
`setzw 0xffeb`、`orw ...,1,1` 形成完整 `0x1ffeb=131051`，再与 payload pointer
相加；末端 `stb`/`ldbu` 位于 `0x800001a0`/`0x800001ac`，访存立即数均为 0，
没有历史 `-21`。首字节同样以零偏移 `stb`/`ldbu` 完成。

map 提取到 21 个唯一 `libc.a` members。`--why-extract` 的关键链为：probe object
因 `malloc` 拉入 `lite_malloc.o`，因 `free` 拉入 wrapper `free.o`；该 wrapper 因
`__libc_free` 拉入 mallocng implementation `free.o`，implementation 再因
`munmap` 拉入 `munmap.o`。最终 ELF 同时定义 `free@0x80001404`、
`__libc_free@0x8000140c` 与 `munmap/__munmap@0x80002b64`。

反汇编逐跳闭合真实调用：`main` 在 `0x80000200` 的 PC-relative call 落到
`free`；wrapper 在 `0x80001404` 落到 `__libc_free`；mallocng implementation
在 `0x800017b0` 落到 `munmap`。`munmap` 在 `0x80002b78` 装入 syscall 215，
并于 `0x80002b88` 执行 `trap 2,0`。这不是 stub 或 no-op free。

#### 3. 锁定 identity 与同一产物双后端结果

运行前后 locked inputs 逐项一致，`locked-hash-cmp.rc=0`；QEMU、gem5、
trampoline 的前后 hash 也一致，`runtime-tools-hash-cmp.rc=0`。关键 identity：

| item | SHA-256 |
|---|---|
| clang | `08a8067cf96a5512dedff2a5b69da50a5d68fca9900ce3648e6b3f4c2a883ab4` |
| ld.lld | `2c24e98f6252b3f2a490172d64b51a9362c87dfce072029a5ccb5420ff0885a8` |
| crt1.o | `aaa322857309bab2618e5ee1a1ddb90bd4d4dcea673621090d54d5544ae4ced9` |
| libc.a | `1b62bd670f481b0b46808639a65072021eca8f6d03d81adafa520e5c13ca07ee` |
| dadao.ld | `bc3c1bf453ec0ddd6a4e0856c085930f1d12eeae3238a897f1c320f843d95b39` |
| probe ELF | `606bd7b0cff88d205e91ed50ff2091b2340b84b70ee5ca3bc67619e7b0376a61` |
| probe flat BIN | `f5eb8c44cf788805214a2062cb7ac33375ceccb0f3c68b8ef9713d1c42a9d8de` |

QEMU 使用该 ELF 对应的 flat BIN，gem5 使用同一次链接生成的 ELF；两者均在
15 秒 timeout 内结束：

| backend | host/guest exit | timeout | fault / runtime evidence |
|---|---:|---|---|
| QEMU | 42 | no-timeout | 无 fault；stdout 只有 QEMU monitor banner，无 guest 输出 |
| gem5 | 42；`SIM_END: trap-exit code=42` | no-timeout | 无 simulator fault；Exec trace 实际经过 `free`、`__libc_free+932`、`munmap` 与 `munmap+36` trap |

gem5 trace 的连续关键 PC 为 `0x80001404`（free）、`0x8000140c`
（__libc_free）、`0x800017b0`（通向 munmap 的 call）、`0x80002b64`
（munmap）和 `0x80002b88`（trap）。因此双端 42 不仅证明 free 返回后 marker
路径完成，也有运行时执行到真实 munmap syscall wrapper 的直接证据。

#### 4. 最窄结论与范围自审

- 最窄结论：单次真实 `malloc(131052)` 的非 NULL、首尾 byte 写读、真实
  `free(p)` 返回及 post-free marker，在锁定产物和当前 QEMU/gem5 上均 exit 42。
- 本任务没有 UAF、输出依赖或第二次分配；没有验证复用、多尺寸、优化矩阵、
  allocator 总体、ML-014f 或 ML-014a，也不由本结果外推这些项目完成。
- 全部证据只位于指定 `.work/ML-014y-mallocng-single-large-free-probe/`，等待不同
  reviewer 独立复核。
