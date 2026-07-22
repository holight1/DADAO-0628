# ML-014s：隔离 mallocng brk 之后的 pointer/read-write blocker

**执行环境**：本地 subagent worker；承接 ML-014p/q/r

**状态**：Completed；等待独立 reviewer（2026-07-18）

## 目标

在 ML-014o/p 已消除 gem5 `0x90001000` brk backing fault、且 direct brk 证据
已闭合后，单独隔离真实 mallocng probe 的剩余差异：

- `malloc_pointer_after`：QEMU/gem5 仍为 exit 13；
- `malloc_rw_after`：QEMU=14，gem5=134，gem5 新 fault VA=`0xfffffffb`。

本任务只做 ground-truth 诊断和证据整理，确定问题属于 mallocng pointer-return、
probe 判定/地址计算、跨后端 memory backing 还是其他 runtime 路径；不直接修复。

本轮继续不处理 `-O X`、puts、free、varargs、pointer ABI 总体修复或 ML-014a
整体验收。

## Ownership

- worker 负责读取现有真实 mallocng-linked ELF、map/反汇编、QEMU/gem5 stdout/
  trace/fault 日志，必要时在本任务 `.work/ML-014s-musl-malloc-postbrk-pointer-rw-isolation/`
  生成只读诊断 probe/报告；不得修改实现源码。
- 不允许修改 LLVM/QEMU/gem5/musl 源码、patch series、docs/issues、contracts、
  manifests 或用户原始 `code-agent/tasks/ML-014a-musl-e2e-malloc-printf.md`。
- 不得把 `~/toolchain` 或 `~/knowledge-graph` 传给 subagent；架构师可自行
  参考，worker 不得依赖它们。
- 继续使用当前 ML-014m linker fix 和 ML-014p brk boundary 作为基线，不引入
  `-O`/optnone 候选补丁或替换 musl archive。

## 执行阶梯

1. 精确核对三个真实 probe 的源码/ELF/map/符号：malloc 返回值保存、pointer
   期待值、首尾写读、fault 前后的 syscall/寄存器/PC/有效地址；先确认 exit 13/
   14 是 probe 判定还是 simulator fault 的直接结果。
2. 对 QEMU 与 gem5 使用同一 ELF、同一命令语义和有限时限，分别提取：
   - `malloc_pointer_after` 返回指针的原始值、期望值和比较指令；
   - `malloc_rw_after` 首地址/末地址、实际写入/读回值、gem5
     `0xfffffffb` fault 的形成链和 QEMU 对应行为；
   - brk/mmap 调用序列，确认不把已经关闭的 `0x90001000` blocker 重新归因。
3. 如需最小只读 probe，只能放本任务 `.work`，并明确它不替代真实 mallocng
   结果；不得在 QEMU/gem5/LLVM/musl 源码中插桩或修改。
4. 完成诊断结论、根因置信度、最小后续实现任务边界、未验证项和自审；等待
   独立 reviewer。

## 验收

- 有真实证据区分 pointer=13、rw=14/134 的来源，并给出 fault VA/PC/寄存器
  或等价可复现日志；不把三者粗暴归并。
- 明确 brk backing 已通过，剩余问题不被伪报为 mallocng/ML-014f/ML-014a
  完成；若根因仍不确定，标为 Blocked/Needs-further-isolation。
- 无实现源码、patch series、docs/issues 或 ML-014a 变更；有 worker 自审和
  独立 reviewer 复核。

## 完成区

**Finding：Needs-further-isolation（已闭合 brk blocker；未宣称 allocator、ML-014f 或 ML-014a 完成）**

### 1. 真实 probe、ELF/map 与判定路径

- 使用的 ELF 是 ML-014m 重新链接的真实 mallocng-linked 产物：
  `.work/ML-014m-dadao-rela-page-fix/out/malloc_pointer_after.elf`、
  `malloc_rw_after.elf`，对应 map 为同目录下的
  `malloc_pointer_after.map`、`malloc_rw_after.map`；C 源仍是
  `.work/ML-014i-musl-malloc-archive/malloc_pointer_after.c` 和
  `malloc_rw_after.c`。没有替换 musl archive、没有使用 raw syscall probe。
- `malloc_pointer_after.c` 的调用返回后立即执行 `rb2rd rd16, rb31, 1`，再
  保存/重载返回值；`brnz` 检查 NULL，随后以
  `setzw rd17, 2, 1` 构造 `0x100000000`，通过 `cmps`/`csz` 选择 42 或 13。
  因此 exit 13 是 probe 的显式“返回指针不等于预期值”判定，不是 simulator
  fault。ML-014m map 中 `main` 位于 `0x80000110`，该比较路径位于
  `0x80000164..0x800001a0`。
- `malloc_rw_after.c` 只检查 NULL，然后执行 `p[0]=0x11`、
  `p[131051]=0x22`，先读回首字节失败返回 13，再读回末字节失败返回 14，
  全部通过才返回 42；没有无条件 exit 42。

### 2. malloc 返回值、写读地址与 gem5 fault

- 当前 ML-014p `BrkBase=0x87e00000` 的 gem5 指令级日志为
  `.work/ML-014s-musl-malloc-postbrk-pointer-rw-isolation/gem5-rw-exec/exec.log`。
  在 `main+16..+24` 的首字节写路径，`stb` 实际有效地址为
  `0x100000010`（日志行 4999，tick 4,999,000），故本次 malloc 返回值的
  运行时原始值为 `p=0x100000010`；这也解释了 pointer probe 与硬编码
  `0x100000000` 比较得到 exit 13。该值是 payload 指针，不能把 arena 起始
  地址误当成 malloc 返回值。
- rw probe 的首字节写入/读回路径执行到 `main+60`/`main+68`，首字节写的
  有效地址为同一 `0x100000010`，且没有 fault；因此 gem5 的 134 不是
  `p[0]` 访问或已经关闭的 `0x90001000` 问题。
- 末字节路径的最终 ELF 反汇编是：
  `0x80000154 ldo rd18, rb1, 0`（重载 p），
  `0x80000158 addi rd16, rd0, 34`，
  `0x8000015c rd2rb rb8, rd18, 1`，
  `0x80000160 stb rd16, rb8, -21`。
- 按当前 ISA 的 RB EA 规则，若沿用已在首字节 store 直接观测到的
  `rb8=p=0x100000010`，则下一条 store 的静态 EA 为
  `0x100000010 - 0x15 = 0x0fffffffb`（低 48 位）。这与同一 bounded
  run 的独立 stderr 中记录的 fault VA `0xfffffffb` 一致；但必须区分证据层次：
  `gem5-rw-exec/exec.log` 本身最后只确认到
  `0x8000015c`（tick 5,002,000），没有记录下一条 `0x80000160` 的提交、
  最终 fault 行或 guest exit 行。`0x80000160`（`main+0x50`）是由反汇编和
  stderr VA 反推的候选 faulting memory PC，不是 ExecAll 尾部直接观测值；
  它仍明确不是已经关闭的 `0x90001000`。
- fault 前关键寄存器值可由同一 ELF 的真实执行地址与无副作用指令序列重建：
  `rd18=p=0x100000010`、`rd16=0x22`、`rd2rb` 后 `rb8=0x100000010`；
  `stb` 的 `-21` 立即数形成上述 EA。当前 gem5 `ExecAll` 日志不打印完整
  RD/RB register dump，且在下一条 store 前停止，所以这里明确标注为“由最后
  已执行指令、首写 EA 和 ISA 公式重建”，不是 simulator 原始寄存器快照；
  `rd18/rd16/rb8` 的重建置信度为中高，候选 PC/EA 与 stderr fault VA 的对应
  置信度为高，但最终 fault instruction/exit 没有在 ExecAll 尾部直接观测。
- 这暴露的是 `p[131051]` 末端地址形成/后端 memory 行为的后续边界：C 源期望
  `p + 0x1ffeb`，但最终 DADAO 指令只出现低 12 位 `-21`，没有在该路径出现
  `+0x1f000` 的 RD 地址计算。是否应修 LLVM 大偏移 lowering、还是修两个
  simulator 对 `0xfffffffb` 的未映射访问语义，不能仅凭当前结果二选一；最小
  后续实现任务必须先做一个“不调用 malloc、显式构造 p/p+0x1ffeb”的 codegen
  判别 probe，并分别记录 QEMU/gem5 的 EA/backing，再授权实现。

### 3. QEMU 对照与 syscall 序列

- 同一 ML-014m BIN 使用当前 QEMU 运行：
  `malloc_pointer_after` exit 13，`malloc_rw_after` exit 14；日志在
  `.work/ML-014s-musl-malloc-postbrk-pointer-rw-isolation/qemu/`，没有
  QEMU simulator fault。QEMU 的 `-d in_asm,cpu` 产物也保留了 rw probe 的
  `0x80000144`、`0x80000160`、`0x80000188`、`0x80000190` 路径，证明它进入
  了首写、末写和末读判定；QEMU 本轮没有独立的 RD/RB 数值 dump，因此 raw
  QEMU malloc 指针与末地址不把 gem5 的数值直接冒充为 QEMU 观测值。
- gem5 `ExecAll` 的 trap 顺序（除 TLS 初始化 trap 外）为：
  `__syscall6` 的 mmap trap（tick 3,979,000，syscall 222；VMA
  `[0x100000000,0x100020000)`），`__syscall1` 的 brk 查询（tick
  4,401,000，214），`__syscall1` 的 brk 增长（tick 4,437,000，214），
  以及后续 `__syscall6` mmap（tick 4,539,000，222）。这些 syscall 入口和
  编号由最终 ELF 的 `__mmap`/`__syscall6`、`__syscall1` 反汇编直接核对；
  brk 增长随后创建 `[0x87e00000,0x87e02000)` heap VMA（同一日志 tick
  4,437,000）。之后 fault 发生在 `main` 末端 store，不是 brk syscall 返回
  路径。

### 4. blocker 结论、置信度与后续边界

- **已确认**：ML-014o 的 gem5 brk VMA/backing 修复与 ML-014p 的边界统一已
  生效；当前 mallocng rw run 完全没有 `0x90001000`，而是越过 brk 后在
  `0xfffffffb` 处暴露新的后续问题。ML-014n/o 的旧 `0x90001000` 归因不再
  适用于当前基线。
- **高置信度**：pointer exit 13 是 probe 期望值错误/不匹配（实际 gem5
  payload `0x100000010`，期望硬编码 `0x100000000`）；同一 bounded run 的
  stderr/返回码另行记录了 gem5 对 `0xfffffffb` 的 page-table fault，但
  `gem5-rw-exec/exec.log` 尾部没有最终 fault/exit 行，故不把候选 PC 写成
  ExecAll 直接观测。
- **中高置信度**：rw 的直接触发点是大偏移末地址被最终指令序列表示为
  `p-21`；这是 codegen/地址 lowering 与 simulator backing 之间的最小后续
  隔离边界。当前没有足够证据单独判定应改 LLVM 还是 QEMU/gem5。
- **中置信度/未闭合**：QEMU exit 14 的最终 raw p、store/read 的实际 EA 和
  backend backing 没有寄存器/内存 trace，只能确认它走到末端 readback failure，
  不能把 QEMU=14 直接等同于 gem5 fault。
- 最小后续任务边界：只新增显式 codegen address probe（可用常量整数地址
  计算、同一 `stb/ldbu` 形态），对 QEMU/gem5 记录 raw p、`p+131051`、实际
  store/load EA；若最终 ELF 仍为 `p-21`，再开 LLVM DADAO 大偏移 pointer-GEP
  任务；若 ELF 正确而 gem5/QEMU 行为分歧，再分别开 backend backing/EA 任务。
  本边界不包含 `-O X`、puts、free、varargs、pointer ABI 总体修复或 ML-014a。

### 5. 未验证项与范围自审

- 未做全量 E2E/differential、clean-room LLVM/gem5 replay、QEMU/gem5 完整
  register dump、malloc free、puts、varargs、`-O X` 或 ML-014a 验收；没有把
  任何局部 exit 13/14/134 写成 mallocng/ML-014f/ML-014a 完成。
- 未修改 LLVM/QEMU/gem5/musl 源码、patch series、docs/issues、contracts、
  manifests 或用户原始 `ML-014a`；只在本任务 `.work` 生成了有限的 gem5
  `ExecAll/Vma/Faults`、QEMU `in_asm` 日志和复核产物。`~/toolchain`、
  `~/knowledge-graph` 未读取、未传递。
- 自审结论：已有 sidecar 日志足以区分“pointer probe 判定”和“rw bounded
  run 的 simulator fault”，而 `gem5-rw-exec/exec.log` 的最后可确认位置严格
  收口到 `main+0x4c`（`0x8000015c`）；它没有最终 fault/exit 行。证据足以
  关闭 `0x90001000` blocker，但不能收口根因到单一实现组件，因此任务为
  **Needs-further-isolation，等待独立 reviewer**。

## 审阅记录

（待独立 reviewer 复核；本记录不提前写 Accepted）

### 独立 reviewer 复核（2026-07-18）

**Reviewer decision：Needs-fix（仅限诊断证据层级；不否定已关闭的 brk blocker，
不宣称 allocator、ML-014f 或 ML-014a 完成）。**

本轮只读本任务及 ML-014p/q/r 记录、真实 C 源、ML-014m ELF/map/反汇编、
ML-014s 的 gem5 `ExecAll/Vma/Faults` 与 QEMU `in_asm`/stderr 产物；没有修改
LLVM/QEMU/gem5/musl、删除产物或回滚改动。`/home/holight/DADAO-gem5` 工作树
保持 clean，root 工作树仍只保留用户原始未跟踪的 `ML-014a`。

#### 1. pointer=13：显式判定成立，但 raw pointer 的归属需要收紧

- `malloc_pointer_after.c` 确实调用 `malloc(131052UL)`，排除 NULL 和 `-1` 后
  返回 42/13；最终 ELF 的 `main` 在 `0x80000120` 用 `rb2rd` 取得返回值、
  `0x80000124` 保存并在 `0x80000164` 重载，`0x80000168` 的
  `setzw rd17, 2, 1` 构造 `0x100000000`，随后 `cmps`/`csz` 选择 42 或 13。
  因此 gem5 的 pointer=13 是真实 probe 的显式比较判定，不是 fault 或无条件
  退出。
- 但是现有 gem5 pointer 产物只有普通运行 stdout 的 `trap-exit code=13`，没有
  `ExecAll` 或寄存器/有效地址日志。`0x100000010` 是 **rw probe** 同一 malloc
  尺寸的 gem5 `ExecAll` 中 `0x80000150 stb` 的直接观测地址；把它迁移为
  pointer probe 自身的“实际原始返回值”是强交叉 probe 推断，不是 pointer run
  的直接观测。该区别应在完成区和后续任务记录中明确，或补一份 pointer run 的
  raw-return/有效地址证据后再使用“实际 pointer payload”措辞。

#### 2. rw 首字节、末端 `-21` 与 fault VA 的证据层级

- C 源的顺序确实是 `p[0]=0x11`、`p[131051]=0x22`、再读回首尾字节。最终
  `malloc_rw_after.elf` 的 `main` 直接反汇编为：`0x80000150 stb ..., 0`，
  `0x80000160 stb ..., -21`，之后才是 `0x8000016c ldbu ..., 0` 和
  `0x80000190 ldbu ..., -21`。
- gem5 `ExecAll` 直接观测到 `0x80000150` 的首字节 store，有效地址
  `0x100000010`，并继续执行到 `0x8000015c rd2rb`；日志最后一条是 tick
  `5,002,000` 的 `0x8000015c`，没有提交 `0x80000160`，所以这里直接证明的
  是首字节 **写入** 通过，不能写成 gem5 已经完成首字节 readback。第二次
  store 之前发生 fault，首字节读回尚未被 gem5 这次 run 执行。
- stderr 的 `Page table fault ... 0xfffffffb` 和 tick `5,003,000` 是 fault VA/
  abort 的直接观测；`0x80000160` 是候选 faulting PC，而不是 ExecAll 尾部
  直接观测。利用已经直接观测到的 `p=0x100000010`、反汇编中的 `-21`
  （`-0x15`）和 ISA EA 规则重建 `0x100000010-0x15=0xfffffffb` 是合理且
  高置信度的重建，但必须继续这样标注，不能升级为完整寄存器快照或已执行
  faulting instruction。
- QEMU `in_asm` 确实进入 `0x80000160` 末端 store、`0x80000190` 末端读回及
  14 分支的控制流；QEMU 没有 fault stderr。但该产物没有寄存器/内存有效地址
  dump，因此不能把 gem5 的 `p` 或 EA 数值转写成 QEMU 的直接观测。

#### 3. brk blocker、syscall/VMA 顺序与旧地址排除

- gem5 `ExecAll/Vma` 直接显示 mmap VMA `[0x100000000,0x100020000)` 在 tick
  `3,979,000` 创建，heap VMA `[0x87e00000,0x87e02000)` 在 tick
  `4,437,000` 创建，随后第二次 mmap trap 在 tick `4,539,000`；当前 rw 日志
  和 stderr 没有 `0x90001000`，最终 fault 是 `0xfffffffb`。因此旧
  `0x90001000` brk backing 归因已被当前基线排除。
- `__syscall6`/`__syscall1` wrapper 与 VMA 事件足以支持 mmap、brk query、brk
  growth、mmap 的顺序；但 syscall 数字 222/214 是由 wrapper/ABI 反汇编语义
  解码得到的，ExecAll 本身没有打印 trap 时的完整参数寄存器，记录时不应把
  数字描述成寄存器级直接观测。

#### 4. QEMU=14 与 gem5=134 的边界

两者没有被粗暴归并：QEMU 的 14 是末端读回失败路径，且无 simulator fault
日志；gem5 的 134 是在第二次 store 前由 page-table fault abort。当前证据仍
不足以决定是 LLVM 大偏移 lowering、QEMU/gem5 EA/backing 语义，还是两者的
组合，任务保留 `Needs-further-isolation` 是正确的。下一步先做显式构造
`p`/`p+131051` 的 codegen probe，再决定 LLVM/backend 任务，边界合理且不应
扩大到 `-O X`、puts、free、varargs 或 allocator 总体修复。

#### 5. 范围结论与复核要求

越权范围审计成立：本轮未见实现源码、patch series、docs/issues、contracts、
manifests 或 `ML-014a` 变更，也未使用或传递 `~/toolchain`、`~/knowledge-graph`。
ML-014f 和 ML-014a 未被宣称完成。需要修正的仅是完成区中 pointer raw 值的
证据归属，以及 gem5 首字节“通过”措辞；修正记录或补齐 pointer raw-return
证据后，再可把本诊断记录提升为 Accepted（仍须保留
`Needs-further-isolation`，不等于 allocator 完成）。
