# ML-014t：显式判别大偏移 pointer-GEP 的 codegen/EA

**执行环境**：本地 subagent worker；承接 ML-014s independent review

**状态**：Accepted（仅限显式大偏移 codegen/EA probe，2026-07-18）

## 目标

创建一个不调用 malloc、显式构造已映射地址和大偏移访问的最小 probe，判别
`p[131051]` 对应的问题是在 LLVM DADAO codegen 中丢失高位/错误形成 `p-21`，
还是在 QEMU/gem5 backend 的 EA/backing 处理。该 probe 只提供决策证据，不直接
修改 LLVM/QEMU/gem5/musl 实现。

需要在同一 probe 中保留可观测的 `p`、`p+131051` 期望关系，并尽可能让 QEMU
与 gem5 对同一 store/load 形态给出明确结果；不得把单后端结果写成最终根因。

本任务不处理 `-O X`、puts、free、varargs、pointer ABI 总体修复或 ML-014a。

## Ownership

- worker 只负责本任务 `.work/ML-014t-musl-large-offset-codegen-probe/` 的
  C/assembly probe、ELF/map/反汇编、QEMU/gem5 stdout/stderr/trace 和报告；
  不修改实现源码。
- 可使用当前 ML-014m linker、ML-014p brk/mmap 基线和既有 raw mmap probe；
  不允许修改 LLVM/QEMU/gem5/musl、patch series、docs/issues、contracts、
  manifests 或用户原始 `ML-014a`。
- 不得把 `~/toolchain` 或 `~/knowledge-graph` 传给 subagent；架构师可自行
  参考，worker 不得依赖它们。

## 执行阶梯

1. 设计最小 probe：不依赖 mallocng，先通过既有 `mmap(222)` 获得固定 arena
   base 或使用等价已映射地址，再显式构造 `p=base+16` 和
   `q=p+131051`；验证 q 的数学期望为 `0x10001fffb`（若 base 为
   `0x100000000`），并将 q 用于实际 byte store/load。
2. 生成并检查 ELF/map/反汇编：确认是否有完整大偏移加法，还是出现类似
   `stb ... -21` 的低 12 位伪替代；记录 source-level expectation 与实际
   EA 的差异，不用注释代替反汇编证据。
3. 用同一 ELF 在 QEMU/gem5 运行，保留有限时限的 raw stdout、stderr、必要
   trace 和返回码；若需要打印 raw 地址，使用固定长度/无 varargs 的已有
   syscall 方式，不能引入 puts/printf 依赖。
4. 给出决策矩阵：
   - ELF/codegen 已错误：后续开 LLVM 大偏移 lowering 任务；
   - ELF/codegen 正确但 gem5/QEMU EA/backing 分歧：后续开对应 backend 任务；
   - probe 仍无法判别：明确缺口和下一条最小可观测路径。
5. 完成任务记录与 worker 自审，等待独立 reviewer；不宣称 allocator 或
   ML-014a 完成。

## 验收

- 有 source/C、ELF/map/反汇编和两后端运行证据，能判定或明确不能判定大偏移
  的 codegen/EA 问题；不把 `0xfffffffb` 直接归因于未经验证的组件。
- 无实现源码、patch series、docs/issues 或 ML-014a 变更；有独立 reviewer。
- ML-014s 的 Needs-further-isolation 结论只在新增证据支持的范围内更新。

## 完成区

### Finding：当前显式大偏移 codegen/EA probe 通过；不能据此宣称 mallocng 或 ML-014a 完成

#### 1. 最小 source/ELF/map 产物

- source：[large_offset_probe.c](/home/holight/DADAO-0628/.work/ML-014t-musl-large-offset-codegen-probe/large_offset_probe.c)
- runner：[run_probe.sh](/home/holight/DADAO-0628/.work/ML-014t-musl-large-offset-codegen-probe/run_probe.sh)
- ELF：[large_offset_probe.elf](/home/holight/DADAO-0628/.work/ML-014t-musl-large-offset-codegen-probe/large_offset_probe.elf)
- flat binary：[large_offset_probe.bin](/home/holight/DADAO-0628/.work/ML-014t-musl-large-offset-codegen-probe/large_offset_probe.bin)
- map、ELF headers/sections、完整反汇编和后端日志均保存在同一 `.work/ML-014t-musl-large-offset-codegen-probe/` 目录。

probe 通过当前 musl `mmap` 声明申请 `0x20000` bytes，不调用 malloc；随后构造：

```text
p = base + 16
q = p + 131051 = base + 0x1fffb
base = 0x100000000 => q = 0x10001fffb
```

`ml014t_p_marker`、`ml014t_q_marker`、`ml014t_loaded_marker` 是 volatile 全局
marker，分别记录 p、q 和 q 的 byte load，符号位于 ELF `.bss` 的
`0x80003008/0x80003010/0x80003018`。没有 puts、printf、varargs、free 或
`-O X`。

#### 2. 编译、ELF/map 和反汇编证据

实际使用当前工作区 clang/lld：

```text
.work/build/llvm/bin/clang --target=dadao -std=c99 -nostdinc -ffreestanding -O0 -c ...
.work/build/llvm/bin/ld.lld -T tests/scripts/dadao.ld -Map=... --start-group crt1.o probe.o libc.a --end-group ...
.work/build/llvm/bin/llvm-objcopy -O binary ...
```

三步返回码均为 `0`。ELF 为 `elf64-unknown`、DADAO machine `0xDA0`、entry
`0x80000000`，`.text` 从 `0x80000000` 开始，marker 符号和 `.bss` 布局见
`nm.txt`、`readelf.txt`、`large_offset_probe.map`。

`large_offset_probe.disassembly.txt` 的 `main` 关键序列为：

```text
0x80000178  ldo  rd16, rb1, 16       # base
0x8000017c  addi rd17, rd0, 16
0x80000180  add  rd0, rd16, rd16, rd17 # p = base + 16
0x80000188  ldo  rd16, rb1, 8        # p
0x8000018c  setzw rd17, 0, 65515     # low 16 = 0xffeb
0x80000190  orw  rd17, 1, 1          # rd17 = 0x1ffeb = 131051
0x80000194  add  rd0, rd16, rd16, rd17 # q = p + 0x1ffeb
0x800001c8  stb  rd17, rb8, 0
0x800001d4  ldbu rd16, rb8, 0
```

q 的期望值也在 `0x80000200..0x80000210` 以完整 `0x10001fffb` 构造并比较，
成功路径才返回 42。因此当前 ELF 没有出现 malloc rw probe 中的
`stb ..., -21` 伪替代；大偏移先由完整 RD 加法形成，再通过 `rd2rb` 作为
byte store/load 的 EA。

首次 runner 尝试发现当前 LLVM 工具目录没有 `llvm-readelf`，不是构造或运行
阻塞；已改用同目录存在的 `llvm-readobj`，并完成同一 ELF 的有限时限重跑。

#### 3. 同一 ELF 双后端运行

runner 使用同一个 `large_offset_probe.elf`（gem5）和其对应的
`large_offset_probe.bin`（QEMU），每个 `timeout 15s`：

```text
compile=0 link=0 objcopy=0 qemu=42 gem5=42
```

- QEMU stdout/stderr、`-d in_asm,cpu` trace：`qemu.stdout`、`qemu.stderr`、`qemu.trace`。
- gem5 stdout/stderr、`m5out/`：`gem5.stdout`、`gem5.stderr`、`m5out/`。
- QEMU 只有正常 monitor 文本，无 fault；gem5 为
  `SIM_END: trap-exit code=42`，stderr 只有已有 simulator warning 和栈扩展
  info，没有 page-table fault。

exit 42 同时覆盖 q 的 expected-value compare、q byte store 和 q byte load；
所以该显式 `mmap` arena 的大偏移访问在两个后端均通过。marker 的运行时数值
没有通过 printf/格式化输出打印，而是由成功判定、ELF symbol/map、反汇编和
后端 trace 共同审计，避免引入额外 ABI 依赖。

#### 4. codegen/EA 决策矩阵

| 观察 | 结论 | 后续动作 |
|---|---|---|
| ELF 中大偏移已错误，出现低 12 位/`-21` | 本 probe：否 | 不开启通用 LLVM 大偏移 lowering 修复 |
| ELF 正确但某一后端 store/load 失败 | 本 probe：否，QEMU/gem5 均 42 | 不开启本 probe 导出的 backend EA/backing 修复 |
| ELF 正确且两个后端均通过 | **本 probe：是** | 保留 mallocng 专属路径为未闭合问题，做最小路径对比 |
| 本 probe 与 mallocng rw 的 `stb -21` 不一致 | **已确认存在** | 后续只比较 malloc 返回值保存、pointer-GEP lowering 和实际 RB EA；不扩大到 allocator 总体修复 |

当前证据支持：通用的 C `p + 131051` 在现行 clang/lld 下形成完整
`0x1ffeb` 加法，且这个结果在 QEMU/gem5 的已映射 arena 上可写可读。它不能
单独解释或修复 ML-014s 中真实 mallocng 路径的 `stb -21`，也不能把问题归因
给 QEMU 或 gem5 的一般 EA/backing。

#### 5. 未验证项与最小后续边界

- 未验证真实 malloc 返回指针的同一源码/同一 IR 是否经过与本 probe 相同的
  lowering；本 probe 的 base 来自 mmap，不来自 mallocng。
- 未取得 QEMU/gem5 的完整寄存器快照来直接打印运行时 p/q；QEMU trace 主要
  提供执行块，gem5 普通 stdout 只提供最终 exit。
- 未做 `-O X`、puts、free、varargs、全量 E2E/differential、clean-room
  replay，也未修改/验收 ML-014f 或 ML-014a。
- 最小后续任务应复用当前已通过的显式 p/q 形态，与真实
  `malloc_rw_after` 的 malloc 返回值保存和末端访问逐条对齐；只在能证明
  两者 IR/寄存器形态不同后再决定 LLVM 专项任务，或在 ELF 形态一致而后端
  行为分歧时再开 backend 任务。

#### 6. 范围自审

- 仅新增本任务 `.work/ML-014t-musl-large-offset-codegen-probe/` 下的 probe、
  runner 和产物，以及本 task MD；没有修改 LLVM/QEMU/gem5/musl 源码、patch
  series、docs/issues、contracts、manifests 或用户原始 `ML-014a`。
- 没有读取、引用或传递 `~/toolchain`、`~/knowledge-graph`。
- 没有把 QEMU/gem5 的局部 `42` 写成 allocator、ML-014f 或 ML-014a 完成；
  当前 Finding 仅限显式大偏移 codegen/EA probe。

## 审阅记录

（待独立 reviewer 复核；本记录不提前写 Accepted）

### 独立 reviewer 复核（2026-07-18）

**Reviewer decision：Accepted（仅限本显式大偏移 codegen/EA probe 证据；不等价于
mallocng、ML-014f 或 ML-014a 完成）。**

本轮按要求只读了本任务、ML-014s review、probe C/runner、ELF/map、反汇编、QEMU
trace/stdout/stderr 和 gem5 stdout/stderr/m5out 产物；没有修改实现源码、删除产物、
回滚改动或使用/传递 `~/toolchain`、`~/knowledge-graph`。

#### 1. source expectation 与 ELF 闭合

- C 源实际是 `mmap(..., 0x20000UL, ...)`，然后 `p = base + 16UL`、
  `q = p + 131051UL`。`131051 = 0x1ffeb`，故
  `q = base + 0x1fffb`；当 `base = 0x100000000` 时，期望值为
  `0x10001fffb`。
- 最终反汇编的 `main` 在 `0x80000178..0x80000180` 形成 `p = base + 16`，
  在 `0x80000188..0x80000194` 以 `setzw 0xffeb`、`orw` 和完整 `add` 形成
  `q = p + 0x1ffeb`。这里没有出现 mallocng 证据中的 `stb ..., -21` 伪替代。
- `q` 的期望常量在 `0x80000204..0x8000020c` 以低 16 位、高位字逐步构造，
  `0x80000210` 执行比较；map/nm 同时闭合了三个 volatile marker：
  `p=0x80003008`、`q=0x80003010`、loaded=`0x80003018`。

#### 2. 两后端的实际成功路径

- C/ELF 的访问顺序是：`q` 写入 `0x5a`（`0x800001c8 stb`），从 `q` 读回
  （`0x800001d4 ldbu`），写入并重读 loaded marker（`0x800001e0`、
  `0x800001e4`），先在 `0x800001e8` 比较 marker，再在 `0x80000210`
  比较期望地址；只有两项均通过才落到 `0x8000022c` 的返回值 42。
- QEMU trace 实际出现 `IN 0x80000178`（包含上述 q 计算和 q store/load）、
  `IN 0x80000200`（期望地址比较）和 `IN 0x80000228`（构造 42），随后
  `IN 0x80000238` 返回；runner 记录 `qemu_rc=42`，qemu stderr 为空，没有
  fault。因而 42 不是无条件退出路径。
- gem5 stdout 记录 `SIM_END: trap-exit code=42`；gem5 stderr 只有既有 simulator
  warning/info，没有 page-table fault。该结果与同一 ELF 的条件控制流闭合，支持
  gem5 通过此 probe，但不提供 gem5 raw p/q 或有效地址的直接寄存器级观测。

#### 3. 结论边界

本证据支持“当前通用 C `p + 131051` 的 codegen/已映射 arena EA 基线在 QEMU 和
gem5 均通过”，也支持不因该结果开启通用 LLVM 大偏移 lowering 或一般 backend
EA/backing 修复。它**不**证明真实 malloc 返回指针走相同 IR/lowering，不解释
ML-014s 中 mallocng 的 `stb ..., -21`，也不关闭 ML-014s、ML-014f 或 ML-014a。

必须保留的未验证项：本任务 work 目录没有独立 gem5 指令级 trace（m5out 只有配置和
统计文件），所以没有 gem5 raw p/q、寄存器或 EA 的直接 trace；也未做 mallocng
路径对齐、`-O X`、puts、free、varargs、全量 E2E/differential 或 clean-room
replay。任务完成区已经准确保留这些限制，未把局部 `42` 写成 allocator 或项目完成。

#### 4. 范围审计

root 工作树未见实现源码变更；本轮只需记录本 reviewer 结论，用户原始未跟踪的
`ML-014a-musl-e2e-malloc-printf.md` 保持不动。结论 **Accepted** 仅适用于本任务的
显式大偏移 codegen/EA probe 证据。
