# ML-014w：修复后真实 mallocng 双后端最小复验

**执行环境**：本地 subagent worker；承接 Accepted ML-014v

**状态**：Completed；等待独立 reviewer（2026-07-18）

## 目标

在不重建 musl/lld 的前提下，用 ML-014v 后端重新构建 clang，且只重编译真实
`malloc_pointer_after`/`malloc_rw_after` probe object；沿用锁定 crt1、libc.a、
linker script 和 lld 重链接，用同一新产物在 QEMU 与 ML-014p 后 gem5 复验。

## Ownership 与 locked inputs

- worker 负责本任务 `.work/ML-014w-*` 产物和本 task MD；可增量构建 LLVM
  `clang`，不得改任何源码。
- 必须先后核对 `ld.lld`、musl `crt1.o`、`libc.a`、`dadao.ld` 的 hash 未变化；
  不运行 musl build、不构建 lld/all target、不覆盖 ML-014m/s 历史产物。
- 只使用当前 QEMU 和 ML-014p 后 gem5；不修改后端、patch series、root tests、
  issues、contracts、manifests 或用户原始 ML-014a。
- 外部架构资料不在 worker scope；多人共享仓库，不回滚他人改动。

## 执行阶梯

1. 增量构建 `clang`，记录命令/退出码及 LLVM source HEAD。
2. 重编译两个 probe，核对 undefined symbols、object identity 差异和链接拉入的
   libc.a member 集合；pointer object 应为控制样本，rw object 应消除末端 `-21`。
3. 保留 rw object/ELF 反汇编，证明完整 `0x1ffeb` 地址物化和合法访存立即数。
4. 同一 ELF/bin 分别运行 QEMU/gem5，记录 timeout、guest exit、stdout/stderr、
   fault；区分 pointer probe 的显式 13 与 simulator fault。
5. 记录最窄结论、未验证项、自审并等待独立 review。

## 验收

- locked lld/crt1/libc/script 身份不变；两个新 probe 可复现构建。
- `malloc_rw_after` 不再含 `stb/ldbu ... -21`，QEMU/gem5 预期均 exit 42；若不符，
  按真实结果定位新 blocker，不得伪报。
- pointer probe 作为控制，不把 exit 13 当作 selector 修复失败，也不冒充 raw
  pointer 直接观测。
- 不宣称 free、输出、allocator 总体、ML-014f 或 ML-014a 完成。

## 完成区

### Finding：修复后的真实 mallocng rw probe 双后端通过；pointer 控制仍显式 exit 13

本轮严格复用锁定的 lld、musl `crt1.o`、`libc.a` 与 linker script，只在 LLVM
source commit `1697be42b5b13cf468043ec8bf9fc612fec17a33` 上增量构建 `clang`，并
只重编译既有 `malloc_pointer_after.c`、`malloc_rw_after.c`。全部新产物和日志在
`.work/ML-014w-mallocng-post-legalization-reverify/`；没有修改实现源码或历史产物。

#### 1. clang 增量构建与 locked identity

执行命令：

```text
cmake --build .work/build/llvm --target clang -j2
```

退出码为 `0`；`build-clang.stdout` 保存实际 7 步增量输出，最终只链接
`bin/clang-22` 并更新既有 `bin/clang` symlink。修复后 clang version string 指向
上述 ML-014v source commit；clang SHA-256 从构建前
`a136f455d7ba46b97f05f405020904fdd0655c73613d1652b86ae02d84b1c248`
变为
`08a8067cf96a5512dedff2a5b69da50a5d68fca9900ce3648e6b3f4c2a883ab4`。

`locked.before.sha256`、`locked.after-build.sha256`、
`locked.after-all.sha256` 三次逐项完全一致（两次 `cmp` 均为 `0`）：

| locked input | SHA-256 |
|---|---|
| `.work/build/llvm/bin/ld.lld` | `2c24e98f6252b3f2a490172d64b51a9362c87dfce072029a5ccb5420ff0885a8` |
| `.work/build/musl/lib/crt1.o` | `aaa322857309bab2618e5ee1a1ddb90bd4d4dcea673621090d54d5544ae4ced9` |
| `.work/build/musl/lib/libc.a` | `1b62bd670f481b0b46808639a65072021eca8f6d03d81adafa520e5c13ca07ee` |
| `tests/scripts/dadao.ld` | `bc3c1bf453ec0ddd6a4e0856c085930f1d12eeae3238a897f1c320f843d95b39` |

未运行 musl build、lld target 或 all target。QEMU 与 gem5 可执行文件在 clang
构建前后也保持各自 SHA-256
`6e0fb1fe6ea2fa67e94ee9162737b2e9ff8a7f4793f85a995984e8f0bb745529`、
`637ff701b5dd50b34304e18eb10f452ab9e06daf467c372310e8d302755174e7`。

#### 2. 两个新 probe object、undefined symbols 与 archive members

两份 source 均使用锁定参数
`--target=dadao -std=c99 -nostdinc -ffreestanding -O0`，compile/link/objcopy
退出码全部为 `0`。`llvm-nm --undefined-only` 对两个新 object 均只列出
`U malloc`。

| probe | ML-014m old object SHA-256 | ML-014w new object SHA-256 | `cmp` |
|---|---|---|---:|
| pointer | `61d5ce186703e07ee6930fbe52df27249148ac3e968d6b0617b653593f0e26d3` | `152b6c8a26df0e165d9ff8f6b1991bd1a2c85a33c153c307d0200aa019eff43a` | `1` |
| rw | `257eab02d1dd91477746e5f392029c41b1bda4b2e403aef667c09abed98672f5` | `2c1cb8c6274ce85381db244fbcb285fcdfc0d30b699b8a5de0664481b1990a9c` | `1` |

pointer 是语义控制样本：虽然完整 object identity 随新 clang 改变，old/new
`llvm-objdump -dr` 的 `.text` 指令和 relocation 完全相同（保存的 diff 除文件名
header 外无差异）。rw 则有预期的真实 codegen 差异：old object 的末端
`stb/ldbu ..., -21` 被完整大偏移物化和合法零偏移访存替代。

两个新 map 各提取完全相同的 19 个 `libc.a` members，且分别与 ML-014m 对应
map 的 member 集合 `cmp=0`；pointer 与 rw 之间也 `cmp=0`。成员为
`_Exit.o`、`__environ.o`、`__errno_location.o`、`__init_tls.o`、
`__libc_start_main.o`、`__lock.o`、`__set_thread_area.o`、`default_attr.o`、
`defsysinfo.o`、`exit.o`、`get_tp.o`、`libc.o`、`lite_malloc.o`、`malloc.o`、
`memcpy.o`、`mmap.o`、`mprotect.o`、`munmap.o`、`syscall_ret.o`。两份
`--why-extract` TSV 各有 19 条 extraction 记录（加 header 共 20 行），均显示
probe 先由 `lite_malloc.o` 解析 `malloc`，再由 `malloc.o` 解析强
`__libc_malloc_impl`；归档选择未变化。

#### 3. rw object/ELF 反汇编与新产物 identity

新 rw object 的 `main` 末端两条路径分别为：

```text
setzw rd18, 0, 65515
orw   rd18, 1, 1
add   rd0, rd18, rd16, rd18
...
stb   rd16, rb8, 0

setzw rd17, 0, 65515
orw   rd17, 1, 1
add   rd0, rd16, rd16, rd17
...
ldbu  rd16, rb8, 0
```

`65515=0xffeb`，随后 `orw ...,1,1` 形成完整 `0x1ffeb=131051`；地址经 `add`
形成后，store/load 均只使用合法立即数 `0`。新 rw ELF 的对应地址为
`0x80000158..0x8000016c` 和 `0x80000198..0x800001a8`，同样不存在该 probe
末端的 `stb/ldbu ..., -21`。完整 object/ELF 反汇编及 old/new diff 均已保留。

新产物 identity：

| probe | ELF SHA-256 | flat BIN SHA-256 |
|---|---|---|
| pointer | `9dc4252a4f07d43bbf3995f58786fddeaa3ab35eca02c51b4c514af14009ddef` | `538819ca47da929cd04a252028a18f6bf07825b6817a8798f90958b596708498` |
| rw | `63d69a0a4542ca60a95cfc1e49462ddf1aaeb08f03ef7cc2f7694ed349108b6c` | `c2e7788c2ff242e72e22306a1535ed332a2a1b80fcaf4c418a6abed6bc1de6c6` |

#### 4. 同一新产物的 QEMU/gem5 结果

QEMU 对上表 flat BIN 运行，gem5 对同一链接生成的对应 ELF 运行；均使用 15 秒
timeout。原始 stdout/stderr、host/guest exit sidecar 和 gem5 `m5out` 全部保留：

| probe | QEMU | gem5 | timeout / fault |
|---|---:|---:|---|
| `malloc_pointer_after` | `13` | `13`（`SIM_END: trap-exit code=13`） | 两者均未 timeout；无 simulator fault |
| `malloc_rw_after` | `42` | `42`（`SIM_END: trap-exit code=42`） | 两者均未 timeout；无 simulator fault |

pointer 的 13 是既有 source 对 payload pointer 与硬编码 arena base
`0x100000000` 不相等时的显式返回值，是控制样本，不是 selector 修复失败或
simulator fault，也不冒充 raw pointer 直接观测。QEMU stdout 只有 monitor
banner、guest 无输出，stderr 为空；gem5 stderr 只有既有 warning/info，未出现
page-table fault、panic、fatal 或 abort。rw 的 42 闭合了修复后真实 mallocng
末端首尾 byte store/load 路径在两个后端上的最小复验。

#### 5. 最窄结论、未验证项与范围自审

- **最窄结论**：在 locked lld/crt1/libc.a/linker script、当前 QEMU 与 ML-014p
  后 gem5 下，仅重编译两个既有 probe 后，ML-014v 修复使真实
  `malloc_rw_after` 的 `0x1ffeb` 末端访问合法化，QEMU/gem5 均 exit 42；pointer
  控制样本保持双后端显式 exit 13。
- 未验证 free、puts/printf/任何输出语义、allocator 总体、优化级别矩阵、全量
  E2E/differential、ML-014f 或用户原始 ML-014a；不宣称这些项目完成。
- 未修改 LLVM/QEMU/gem5/musl 源码、patch series、root tests、issues、
  contracts、manifests 或历史 `.work` 产物；只新增本任务 `.work` 证据并更新本
  task MD。用户原始未跟踪 `ML-014a-musl-e2e-malloc-printf.md` 保持不动。
- worker 自审：命令、hash、object/map/why-extract、完整反汇编、stdout/stderr、
  timeout 与退出码 sidecar 均已保留；验收在上述最窄边界内通过，等待不同
  reviewer 独立复核。
