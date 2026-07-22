# ML-014k：隔离 mallocng 链接后 TLS 全局数据畸变

**执行环境**：本地 subagent worker；承接 ML-014j

**状态**：Blocked（2026-07-18；本轮 worker 未产生新增可接受证据）

## 背景

ML-014i 的 archive selection 候选 `4741d4d1` 让 mallocng `malloc.o` 被静态
链接；ML-014j 已独立复核：同一 archive 下 `return42`、真实 `mmap` 均双后端
42，但真实 mallocng ELF 在 `main` 前双后端 MALIGN=129。gem5 证据为
`__init_tls` 的 `0x80000bcc sto` 对 `0xa000c000e00d4` 未对齐地址写入；此前
SYS_mmap 收到畸变 length `0xa000c000e00e8` 并返回 `-EINVAL`。

本任务只回答“为什么链接 mallocng object 后 TLS/全局数据形成该畸变”，先不
实现修复。

## Ownership

- 允许修改：临时 `.work/ML-014k-musl-mallocng-tls-image-isolation/` 的 ELF
  map/section/relocation dump、probe、报告和本任务 MD。
- 不允许修改 LLVM、QEMU、gem5、musl 源码、任何 patch series、contracts、
  manifests、issues、ML-014a；不处理 `-O`/`puts`。
- 可以比较 `.work/ML-014h` lite ELF、`.work/ML-014i` mallocng ELF 和最小
  `return42`/`mmap` ELF；不得把 raw syscall 结果当作真实链路验收。

## 执行阶梯

1. 对比 lite-only、mallocng-linked 的 ELF：PT_LOAD、`.data/.bss`、符号地址、
   `rela` 指令立即数、`libc`/`main_tls`/`builtin_tls`/`__malloc_context` 相关
   map，确认畸变值的第一个形成点。
2. 用最小真实 musl 输入逐步增加“archive member 被提取”的差异，记录
   `__init_tls` 之前的全局字段值与 SYS_mmap 参数；区分 linker/loader、codegen
   或 musl 源级原因。
3. 输出唯一根因或明确的最小下一任务边界；若证据指向 backend/LLVM，暂不改
   代码，只登记具体 PC/relocation/符号证据。

## 验收

- 报告给出具体 ELF/符号/指令/寄存器证据，不能只写“布局有问题”；
- 至少证明 lite-only 与 mallocng-linked 的关键差异；
- 不虚报 mallocng malloc+写读+free 双后端通过；
- 完成区有 subagent 自审，随后独立 reviewer 复核。

## 完成区

**状态**：Blocked；未完成链接映像隔离

**根因证据**：

- 已有 ML-014j 证据可以确认症状边界：lite-only ELF 的 malloc-only 阶段能
  进入 `main`（但仍是 lite allocator 失败码），mallocng-linked ELF 的
  `return42`/direct mmap 仍分别为 42/42，只有真实 mallocng member 被提取后
  在 `__init_tls` 之前双后端 MALIGN=129。
- 已有 gem5 IntRegs 显示 `__init_tls` 的 SYS_mmap length 为
  `0xa000c000e00e8`、返回 `-EINVAL`，随后 `0x80000bcc sto` 对
  `0xa000c000e00d4` 触发 MALIGN；但本轮没有完成更早的全局字段形成点定位。
- 因此不能把问题继续简化为 archive member order、backend mmap bridge 或
  mallocng 元数据中的任一项。

**验收结果**：

- 本轮未修改 LLVM/QEMU/gem5/musl/series 或任何受限文件，未生成实现 patch。
- 未达到 mallocng malloc+首尾写读+free 双后端=42；ML-014f/ML-014a 仍未完成。
- **Blocked**：worker 未在本轮时间窗口内产生新的可接受隔离证据，保留已有
  ML-014j 诊断作为下一轮起点。

**遗留问题**：

- 需要重新下发一个更窄的 probe，直接比较 mallocng-linked ELF 在
  `__init_libc`/`__init_tls` 对 `libc.tls_size`、`main_tls` 及 ELF 全局映像的
  形成顺序；优先判断是链接器/relocation 数据布局还是 musl TLS 代码输入。

### 后续处理

上述遗留问题已由 ML-014l 完成更窄的 ELF/relocation 证据定位，并由 ML-014m
修复 `R_DADAO_RELA_PAGE`。ML-014k 本身仍保持“本轮 worker 未完成新增证据”的
Blocked 记录，不重复改写为实现任务；当前剩余阻塞已转移到 mallocng 进入
`main` 后的 `0x90001000` 映射/allocator 路径。

## 审阅记录（subagent）

> 这是链接映像隔离诊断，不在本任务直接修 LLVM/backend/musl。

### Subagent 自审（2026-07-18）

- 本轮 worker 未完成新的隔离实验；不把 ML-014j 的已有症状证据冒充为本任务
  的唯一根因。
- 未修改越权范围；ML-014k 保持 **Blocked**，等待更窄的下一轮诊断。
