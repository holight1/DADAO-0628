# ML-014j：定位 mallocng 选择后启动链 MALIGN

**执行环境**：本地 subagent worker；承接 ML-014i 的实现后回归

**状态**：诊断完成，Blocked（2026-07-18）

## 背景

ML-014i 的最小归档选择修复在链接层生效：mallocng `malloc.o` 新增强 public
`malloc` 后，`malloc_pointer` 的 link map 同时包含 mallocng 的
`__libc_malloc_impl` 与 `malloc`，不再只选 `lite_malloc.o`。但同一真实 musl
ELF 在两个后端均于 `main` 前退出 MALIGN=129，尚未证明是 malloc 本身、TLS
启动、SYS_mmap 返回链或具体 backend 对齐实现。

## Ownership

- 允许修改：临时 `.work/ML-014j-musl-mallocng-startup-malign/` 探针、反汇编、
  运行日志和报告；本任务 MD 的完成/审阅区。
- 可以在 `.work/source/musl` 保留当前普通候选 commit `4741d4d1`，但本任务
  不得修改 LLVM/QEMU/gem5、patch series、contracts、manifests、issues、
  ML-014a，不能处理 `-O` 或 `puts`。
- 需要临时 backend 日志时必须可逆且不得作为实现提交；不得把 raw syscall
  probe 当成 musl 链路通过，最终必须回到真实 musl C 链路。

## 执行阶梯

1. 对比 ML-014h 的 lite allocator ELF 与 ML-014i mallocng ELF，定位第一个
   不同的执行基本块；核对 startup TLS、SYS_mmap 返回、RB pointer 和存取对齐。
2. 用最小真实 musl 输入逐层裁剪：`int main return 42`、真实 `mmap`、真实
   mallocng 入口；记录 QEMU/gem5 的第一条故障指令/地址或最小共同失败点。
3. 若证据是现有 backend 对齐/MMU 实现缺陷，只提交明确的最小 backend 修复
   建议，不在本任务直接修改 backend；若是 musl/ABI 侧，记录最小修复方向，
   不越权实现。

## 验收

- 报告包含具体 PC、指令、有效地址/寄存器 bank 或共同失败路径；
- 明确区分“归档选择已生效”和“mallocng 基本链路尚未通过”；
- 不虚报 QEMU/gem5=42，不把 ML-014f/ML-014a 标为完成；
- 完成区含 subagent 自审，随后独立 reviewer 复核。

## 完成区

**状态**：Blocked；已定位共同第一失败点，尚未实现修复

**根因证据**：

- 分层真实 musl 结果：`return42` QEMU/gem5=42；真实 C `mmap` QEMU/gem5=42；
  链接 mallocng public entry 后的真实 mallocng probe QEMU/gem5=129，均在
  `main` 前失败。
- gem5 `ExecAll,IntRegs,Faults`：`__init_tls` PC `0x80000bc8` 为
  `rd2rb rb8, rd9, 1`，下一条 `0x80000bcc sto rd17, rb8, 0` 触发
  `MALIGN=129`；故障前 `rd9=0xa000c000e00d4`，有效地址未按 8 字节对齐。
- 同一 trace 显示之前 `SYS_mmap` trap PC `0x80000af0` 收到 malformed length
  `rd18=0xa000c000e00e8`，返回 `rd31=0xfffffffffffffff4`（`-EINVAL`）；
  该错误指针/大小随后进入 TLS copy 路径。QEMU trace 也到达同一 startup
  block，最终 QEMU=129。
- 这不是 mallocng 元数据访问：`main` 尚未执行；同一 archive 下 return42 和
  direct mmap 均通过。结论是“mallocng member 被链接后暴露了 startup TLS
  malformed size/pointer”，还不能把根因简化为 backend mmap bridge。

**验收结果**：

- 诊断 probe 均真实 C musl 链接，无 raw syscall 绕过验收。
- QEMU/gem5：return42=42/42、mmap=42/42、mallocng=129/129。
- 未修改 LLVM/QEMU/gem5、patch series、contracts、manifests、issues 或
  ML-014a；未生成实现 patch。
- **Blocked**：未达到 mallocng malloc+写读+free 双后端=42。

**遗留问题**：

- 另开后续任务定位 `__init_tls` 在 mallocng object 被链接时为何计算出
  `0xa000c000e00e8` 级别的 TLS size/地址，并确认是否为链接/代码生成数据布局
  问题；在此之前不导出 ML-014i 的 `4741d4d1` 为主 patch series。

## 审阅记录（subagent）

> 本任务仅定位 startup MALIGN，不擅自扩大为 backend 或 `-O` 修复。

### Subagent 自审（2026-07-18）

- 复核 layered probes、QEMU/gem5 真实退出码，以及 gem5 IntRegs 的 PC、寄存器
  和有效地址；没有把 archive selection 生效写成 mallocng runtime 通过。
- 复核没有改动 backend、LLVM、series 或用户任务文件；所有未通过结果保留原始
  exit=129。
- **自审判决：诊断完成但 Blocked；需要单独定位 malformed TLS startup。**

### 独立复核（2026-07-18）

**Finding 数：4**

1. 分层结果核对一致：`return42=42/42`、`mmap=42/42`、`mallocng=129/129`
   （顺序为 QEMU/gem5）。mallocng 失败发生在 `main` 前。
2. 第一共同故障位置核对一致：`__init_tls` 的 PC `0x80000bc8` 后续至
   `0x80000bcc` 触发 `MALIGN=129`；故障前 `rd9=0xa000c000e00d4`，有效地址未
   按 8 字节对齐。
3. 先行 syscall 证据核对一致：`SYS_mmap` 的 length 为
   `0xa000c000e00e8`，返回 `rd31=-EINVAL`
   （`0xfffffffffffffff4`），错误值随后进入 TLS 启动路径。
4. 范围核对一致：本任务未修改 backend、LLVM、series 或 ML-014a；归档选择已
   生效，但 mallocng 实现链路尚未完成。

**独立复核判定：Accepted（诊断任务）。** 诊断验收证据充分；实现状态仍为
**Blocked（实现未完成）**，不应将该 Accepted 解读为 mallocng 运行时已通过。
