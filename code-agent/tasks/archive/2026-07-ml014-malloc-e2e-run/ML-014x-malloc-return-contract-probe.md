# ML-014x：建立真实 malloc 返回指针合同 probe

**执行环境**：本地 subagent worker；承接 Accepted ML-014w

**状态**：Accepted（2026-07-18，独立 review）

## 目标

替代历史 `malloc_pointer_after` 将返回值错误硬编码为 mmap arena base 的判定。
创建最小真实 mallocng-linked probe，直接把 malloc 返回指针编码为固定 16 位十六
进制并通过固定参数 `write` 输出，同时检查非 NULL、自然对齐、位于当前 mmap arena
范围内，以及首字节可写读。用同一 ELF/bin 在 QEMU/gem5 建立一致返回合同。

## Ownership

- worker 只写本任务 `.work/ML-014x-*` probe/runner/产物与本 task MD。
- 沿用 ML-014w 已锁定 clang/lld/crt1/libc.a/linker script 和当前双后端；不得
  修改实现源码、root tests、patch series、issues、contracts、manifests 或原始
  ML-014a。
- 不使用 printf/varargs/puts；只允许手工 hex 转换和固定参数 write。
- 外部架构资料不在 worker scope；多人共享仓库，不回滚他人改动。

## 执行阶梯

1. `malloc(131052)`，保存返回值；输出 `p=0x<16hex>\n`，输出失败单独编码。
2. 检查 p 非 NULL、至少 16-byte 对齐、处于 `[0x100000000,0x100020000)`，并对
   `p[0]` 做写读；每个失败使用不同 guest exit，成功 42。
3. 编译/链接/反汇编，确认没有历史大偏移访问或 printf 依赖；记录 undefined /
   archive member 和锁定输入 hash。
4. 同一产物跑 QEMU/gem5，保留 stdout/stderr/exit/fault；输出值必须两端一致。
5. 记录结论、未验证项、自审并等待独立 review。

## 验收

- 双后端 exit 42，固定 hex 输出一致并提供 probe 自身的 raw pointer 证据；否则
  按真实结果收口 blocker。
- 不把 arena base 当 payload pointer，不把单次返回合同冒充 allocator 总体验收。
- 不触及 free、复用、多尺寸、输出库高层接口、ML-014f 或 ML-014a。

## 完成区

### Finding：真实 malloc 返回合同在 QEMU/gem5 上一致通过

本轮只新增 `.work/ML-014x-malloc-return-contract-probe/` 内的 probe、runner、
构建产物和原始证据，并更新本 task MD。直接使用当前已构建 clang 和 ML-014w
锁定链接输入；未重建 musl、lld 或 clang，未修改任何实现、root tests、历史
`.work` 产物或用户原始 ML-014a。

#### 1. Probe 合同与失败分流

`malloc_return_contract.c` 调用真实 `malloc(131052)`，把返回值按高 nibble 到低
nibble 手工转换为 16 个小写 hex digit。输出缓冲区固定为 21 字节
`p=0x<16hex>\n`，且只调用固定参数 `write(1, out, 21)`；没有使用
printf/varargs/puts 或其他高层输出接口。

检查和 guest exit 一一分流：write 长度不等于 21 → 10，NULL → 11，非
16-byte 对齐 → 12，低于 `0x100000000` → 13，不低于 `0x100020000` → 14，
首字节 volatile 写入 `0xa5` 后读回不符 → 15，全部通过 → 42。故成功 42 同时
证明非空、至少 16-byte 对齐、arena 范围和首字节写读四项合同成立；arena base
没有被当作 payload pointer。

完整可复现命令保存在 `commands.txt`，runner 为 `run_probe.sh`。compile/link/
objcopy sidecar 均为 `0`。object undefined symbols 只有 `malloc` 和 `write`；map
提取出 21 个 `libc.a` members，其中 allocator 路径仍含 `lite_malloc.o`、
`malloc.o`、`mmap.o`、`mprotect.o`、`munmap.o`，输出路径只新增所需的
`write.o`/`__syscall_cp.o`。`forbidden-output-dependencies.txt` 为空。

#### 2. 锁定输入与产物 identity

运行前后的 locked hash 逐项一致，`locked-hash-cmp.rc=0`；QEMU、gem5 与
trampoline 的前后 hash 也一致，`runtime-tools-hash-cmp.rc=0`：

| input | SHA-256 |
|---|---|
| clang | `08a8067cf96a5512dedff2a5b69da50a5d68fca9900ce3648e6b3f4c2a883ab4` |
| ld.lld | `2c24e98f6252b3f2a490172d64b51a9362c87dfce072029a5ccb5420ff0885a8` |
| crt1.o | `aaa322857309bab2618e5ee1a1ddb90bd4d4dcea673621090d54d5544ae4ced9` |
| libc.a | `1b62bd670f481b0b46808639a65072021eca8f6d03d81adafa520e5c13ca07ee` |
| dadao.ld | `bc3c1bf453ec0ddd6a4e0856c085930f1d12eeae3238a897f1c320f843d95b39` |
| QEMU | `6e0fb1fe6ea2fa67e94ee9162737b2e9ff8a7f4793f85a995984e8f0bb745529` |
| gem5 | `637ff701b5dd50b34304e18eb10f452ab9e06daf467c372310e8d302755174e7` |

同一次 compile/link 生成的运行产物为：

| artifact | SHA-256 |
|---|---|
| `malloc_return_contract.o` | `016605d42f10cb63141dbb050ca28a3f304fe281c104be1d4a09f9bad8875372` |
| `malloc_return_contract.elf` | `0c0668a0fd905f47cb58b835102a826b9c6558888621a60413f55dac299ca1f7` |
| `malloc_return_contract.bin` | `aa5af1b1c0664d9e5eb789fa00a7b58351e48816ce3286d1ddc114a72d1ecf37` |

QEMU 使用该 ELF 对应的 flat BIN，gem5 使用同一链接产出的 ELF。
`main.disassembly.txt` 证明首字节检查为 `stb ..., rb8, 0` 与
`ldbu ..., rb8, 0`；main 中没有历史 payload `p+0x1ffeb` 访问，也没有
`stb/ldbu ..., -21`。反汇编开头形成的 `0x1ffec` 仅是传给 malloc 的请求
大小 131052，不是 payload 地址偏移。

#### 3. 双后端 raw pointer 与退出结果

每个后端均在 15 秒 timeout 内运行同一产物，原始 stdout/stderr、stdout hex
dump、退出码、timeout、fault focus 和 gem5 `m5out/` 已完整保留：

| backend | raw probe output | guest/host exit | timeout | fault |
|---|---|---:|---|---|
| QEMU | `p=0x0000000100000010` | 42 | no-timeout | 空 |
| gem5 | `p=0x0000000100000010` | 42；`SIM_END: trap-exit code=42` | no-timeout | 无 simulator fault |

两份 `pointer.txt` 逐字节 `cmp=0`，且各自恰有一条固定格式输出；runner 总体验证
`validation.rc=0`。真实 payload pointer 是 `0x100000010`，不是 arena base
`0x100000000`；它非空、低 4 bit 为零，并位于
`[0x100000000,0x100020000)`。双端 exit 42 进一步证明首字节 `0xa5` 写读成功。

#### 4. 最窄结论、未验证项与范围自审

- 最窄结论：对单次 `malloc(131052)`，当前真实 mallocng-linked 产物在当前
  QEMU/gem5 上给出相同 payload pointer `0x100000010`，并共同满足本任务规定的
  非空、16-byte 对齐、arena 范围和首字节写读合同。
- 本结果不是 allocator 总体验收；未验证 free、复用、多尺寸、末字节、优化级别
  矩阵、高层输出接口、ML-014f 或 ML-014a。
- 完整证据只位于指定 `.work/ML-014x-malloc-return-contract-probe/`。未修改
  LLVM/QEMU/gem5/musl、patch series、issues、contracts、manifests、root tests
  或原始 ML-014a；等待不同 reviewer 独立复核。

## 审阅记录

### 独立 reviewer 复核（2026-07-18）

**Reviewer decision：Accepted（Finding=0；仅限单次 `malloc(131052)` 返回指针
合同，不等价于 allocator、ML-014f 或 ML-014a 完成）。**

- 独立核对 C、object/ELF symbols 与反汇编：object undefined 仅 `malloc`、
  `write`，最终 ELF 无 undefined；两个 call 分别落到 `malloc@0x80002cac` 和
  `write@0x80001484`。输出由手工 16-nibble 小写 hex 转换构造，固定调用
  `write(1, out, 21)`；无 printf/varargs/puts 依赖。
- `main` 反汇编逐项闭合返回分流：write 短写→10、NULL→11、非 16-byte
  对齐→12、低于 `0x100000000`→13、不低于 `0x100020000`→14、首字节
  `0xa5` 写读不符→15，全部通过后才生成 42。首字节访问是
  `stb/ldbu ..., rb8, 0`；未见历史 `p+0x1ffeb` 或 `-21` payload 访问，
  `0x1ffec` 只用于形成 malloc 请求大小 131052。
- 独立重算 `artifacts.sha256`、`locked.before.sha256` 与
  `runtime-inputs.sha256` 全部通过；locked before/after、runtime-tools
  before/after 均 `cmp=0`。现有 ELF/BIN hash 分别保持
  `0c0668a0...f7`、`aa5af1b1...f37`。
- 未重编译，使用同一现有 BIN/ELF 独立复跑：QEMU 与 gem5 均各输出恰一条
  21-byte `p=0x0000000100000010\n`，两端 host/guest exit 均为 42；gem5 同时
  报告 `SIM_END: trap-exit code=42`，两端均无 fault，复跑前后 ELF/BIN hash
  不变。

结论保持最窄边界：本任务规定的真实 malloc 返回指针、固定 write 输出、判定
分流、locked identity 与 QEMU/gem5 同值/exit 42 均闭合，故 **Accepted**。
未验证 free、复用、多尺寸、末字节、优化矩阵、高层输出、allocator 总体、
ML-014f 或 ML-014a，不得由本结论外推。
