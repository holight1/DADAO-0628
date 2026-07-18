# ML-014n：隔离 mallocng 进入 main 后的 0x90001000 访问阻塞

**执行环境**：本地 subagent worker；承接 ML-014m/ML-014f

**状态**：Blocked（2026-07-18；根因已隔离，不直接修复）

## 背景

ML-014m 已修复并集成 `R_DADAO_RELA_PAGE`，消除了 mallocng 在
`__init_tls` 的 startup `MALIGN=129`。当前真实 mallocng probes 已进入
`main`，但后续仍不一致：

- `mallocng_real`（只调用 `malloc(131052)` 后返回）：QEMU=42，gem5=134；
- `malloc_pointer_after`：QEMU=13，gem5=134；
- `malloc_rw_after`：QEMU=14，gem5=134；
- gem5 日志显示访问虚拟地址 `0x90001000` 时 page-table fault。

本任务只回答“0x90001000 是谁形成的、两后端在哪一层分歧、是否为 mmap
返回/arena backing/ELF loader/allocator 访问链路”，不直接修改实现。

## Ownership

- 允许修改：本任务 MD、`.work/ML-014n-musl-malloc-postmain-90001000/`
  下的 trace、map、ELF dump、临时 probe 和报告。
- 可以阅读 `.work/source/musl`、`.work/source/qemu`、`~/DADAO-gem5`、
  `.work/source/llvm` 和现有任务记录；不得把 `~/toolchain` 或
  `~/knowledge-graph` 传给 subagent。
- 不允许修改 LLVM/QEMU/gem5/musl 源码、patch series、docs/issues.yaml、
  contracts、manifests、ML-014a；不处理 `-O`、puts、free 或 varargs。
- 不得把 QEMU=42 单独写成 mallocng allocator 已完成；必须保留 gem5 134
  和 pointer/read-write 的真实失败。

## 执行阶梯

1. 复核三个现有 mallocng ELF 的 map、符号、mmap syscall 参数/返回值和第一条
   访问 `0x90001000` 的 PC/寄存器；区分“malloc 返回了什么”与“首次访问了
   什么地址”。
2. 对比 QEMU/gem5：确认 QEMU=13/14 是正常失败码、错误路径或静默内存丢失，
   不把它与 gem5 page-table fault 粗暴归一。
3. 使用最小真实 musl 分层 probe（malloc-only、malloc+pointer、首尾读写，
   必要时只增加诊断输出）隔离：
   - mmap responder 的返回地址/游标是否符合 ABI；
   - QEMU arena backing 与 gem5 VMA/PTE backing 是否覆盖实际地址；
   - mallocng 的 chunk/meta 计算是否在 `0x90001000` 形成错误地址；
   - 是否有 stale ELF/build artifact 或错误的 malloc archive member。
4. 输出唯一根因，或明确最小修复任务边界；本任务不实现修复。

## 验收

- 报告包含第一条 fault/access 的 PC、地址、寄存器或 syscall 证据；
- 至少有一个 QEMU/gem5 对照实验，说明分歧发生在哪一层；
- 不虚报 mallocng malloc+写读+free=42，不修改越权文件；
- 有 subagent 自审，随后由独立 reviewer 复核。

## 完成区

**Finding：Confirmed（限定为 gem5 `brk` backing/VMA blocker；mallocng 基本链路仍未完成）**

### 第一条 fault/access 证据

- 使用既有 `.work/ML-014m-dadao-rela-page-fix/out/mallocng_real.elf`，只在
  `.work/ML-014n-musl-malloc-postmain-90001000/gem5-real/exec.log` 生成
  `ExecAll,IntRegs,Faults` 诊断 trace；未修改任何组件源码。
- gem5 最先尝试访问 `0x90001000` 的指令为：

  ```text
  PC=0x80001798  __malloc_alloc_meta+1092  blockcopy
  preceding: PC=0x80001794 ld A=0x80006268
  ```

- fault 前的关键寄存器为：

  ```text
  rd17 = 0x90001000       ; 从 ctx.avail_meta_areas 读出
  rd73 = 0x90001000       ; blockcopy 使用的地址寄存器
  rd16 = 0                 ; fault 前仍为零值
  rb1  = 0x7fffffffde60   ; 当前 malloc 栈帧
  ```

  随后 gem5 报 `Page table fault when accessing virtual address
  0x90001000`，退出 134。

- `0x90001000` 的**首次形成**早于该 fault：

  ```text
  tick=4590000
  PC=0x80001554  __malloc_alloc_meta+512  sub rd16, rd16, rd17
  input: rd16=0x90002000, rd17=0x1000
  result: rd16=0x90001000
  ```

  最终 fault 的精确位置为：

  ```text
  tick=4652000
  PC=0x80001798  __malloc_alloc_meta+1092  blockcopy
  address=0x90001000
  ```

- trace 更早记录了 `brk(0)` 返回 `rd31=0x90000000`，随后 mallocng 计算并
  保存 `0x90002000`、`0x90001000`；这与 `alloc_meta()` 中
  `new = ctx.brk + pagesize`、`avail_meta_areas = new - pagesize` 的形成链
  一致。故该地址不是 `SYS_mmap=222` 的 `0x100000000` arena 返回值。
- 同一 exec.log 的第一次 `SYS_mmap=222` trap 记录 `rd31=0x100000000`，随后
  guest 读回的 mmap 返回也是 `0x100000000`。因此 mmap 返回值**不是**
  `0x90001000`；后者来自 brk metadata 地址计算。
- 三个现有 mallocng ELF 的 `.gem5.out` 均在同一运行阶段报告访问
  `0x90001000` 的 page-table fault；其 map 显示共用同一 `malloc.o` 的
  `__malloc_alloc_meta`（pointer/rw 版本因前置 main 大小不同，函数 PC 只发生
  常量偏移）。pointer/rw 的旧 stdout 没保留逐指令寄存器 trace，因此不把上述
  `mallocng_real` 的精确 PC 伪称为三者各自独立观测值。

### QEMU / gem5 语义分歧

| probe | QEMU | gem5 | 语义解释 |
|---|---:|---:|---|
| `mallocng_real` | 42 | 134 | QEMU 只验证非空；gem5 在 `alloc_meta()` 首次触碰 brk 元数据时 fault |
| `malloc_pointer_after` | 13 | 134 | QEMU 返回非空且非 `-1`，但 payload 指针不是测试预期的 `0x100000000` |
| `malloc_rw_after` | 14 | 134 | QEMU 已完成首字节检查，但末端读回不符；gem5 仍先在 brk 元数据访问处 fault |

因此 QEMU=42 不是 mallocng backing 完成证明，13/14 也不能与 gem5=134
粗暴归一为同一错误码。QEMU 的 arena responder 返回 `0x100000000`，并有独立
host-backed MemoryRegion；其 `brk_base=0x87e00000` 落在现有 guest RAM/heap
布局内。gem5 当前 `TrapInst::execute()` 的 `case 214` 从 `0x90000000`
开始返回/推进 brk，但只改变记账值，没有调用 `mapRegion`；该地址也不在
ELF `.heap`（`0x80007000` 至 `0x87e00000`）或已建立的 VMA/PTE 中。

### 根因与最小后续任务边界

**唯一已确认根因**：gem5 的 `SYS_brk=214` responder 与 mallocng 的真实
metadata 使用不匹配。它把 `0x90000000` 当作可用 brk 返回，却没有为
`0x90001000` 等后续 brk 区间建立 VMA/PTE；因此 generic page fault 的
`fixupFault()` 找不到覆盖该地址的 VMA，最终 abort。当前证据不支持把根因归到
`mmap` 返回 bridge、mallocng archive member、RELA_PAGE 或 stale ELF。

最小后续任务应单独处理 **gem5 brk backing**：在不改变 mmap arena ABI 的前提下，
定义 brk 与静态 `.heap` 的统一边界，令 `SYS_brk` 的增长通过 MemState/VMA
路径建立可 fault-in 的页面，并用 mallocng `alloc_meta` 与 pointer/read-write
probe 双后端验证。该任务不应顺带修改 mallocng 算法、puts、free、varargs 或
`-O`；修复前不得重开 ML-014f/关闭 ML-014a。

### 越权与 stale-build 检查

- 只读检查了三个 ELF、map、gem5/QEMU 结果、当前 musl archive 和两端
  `brk/mmap` responder；ELF 均链接当前 `malloc.o`，map 中符号为
  `__malloc_context=0x80006228`，未发现旧 archive member 证据。
- 未修改 LLVM/QEMU/gem5/musl 源码、patch series、docs/issues.yaml、contracts、
  manifests 或 ML-014a；诊断产物仅位于本任务 `.work` 目录。

### Subagent 自审

- 逐项复核了本任务验收条件：fault VA、PC、寄存器、brk 返回链、QEMU/gem5
  退出码语义和 VMA/PTE 缺口均有对应日志或源码证据。
- 明确区分了“mallocng_real 的 QEMU 非空返回”和“真实写读/backing 已通过”，
  没有把 42/13/14 写成 mallocng 完成，也没有把 pointer/rw 缺失的逐指令日志
  填成虚构观测。
- 自审判定：**Confirmed（gem5 brk backing blocker）；ML-014f/ML-014a
  仍 Blocked**。

## 审阅记录

（待独立 reviewer 复核；本轮未修改实现。）
