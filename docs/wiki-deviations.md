# Wiki 偏离/自定义决策清单

**用途**：`~/DADAO-wiki` 是本项目的权威 spec 来源，但存在两类它管不到的情况——
(a) **wiki 完全没写**（沉默，比如 128 位类型、向量类型至今没有任何 ABI 条款）、
(b) **wiki 写了但我们发现执行不下去或自相矛盾**（比如 HFA 有完整定义但 DADAO
没有 RF 硬件基础设施；varargs 保存区基址前后两条规则互斥）。这两类情况下，
项目团队（架构师/DS/subagent）做的每一个"自己拍板"的决定都记录在这里，格式
仿"wiki patch"——像是在对 wiki 打一个假想补丁：原文说了什么/没说什么、我们
决定了什么、为什么、影响范围多大、这个决定处于什么状态。

**与 `docs/wiki-questions.md` 的关系**：`wiki-questions.md` 是"我们想问 wiki
团队的问题清单"（等对方确认，语气是疑问）；本文件是"我们已经自己做的决定清单"
（语气是陈述，即使决定本身来自尚未回答的 wiki-question）。两者会有重叠条目
（一个问题被问出去的同时，我们已经先按某个读法把实现落了地），互相交叉引用。

**更新规则**：任何任务在实现中发现"wiki 没写这个/wiki 这里自相矛盾，我们决定
这样处理"，都要在这里补一条，不能只记在 commit message 或 issues.yaml 的注释
里——这里是唯一的、集中的索引。

---

## 条目格式

```
### <一句话标题>（<任务号>，<日期>）

- **wiki 状态**：SILENT（完全未覆盖） | CONTRADICTS（自相矛盾） | 
  DEFINED-BUT-INFEASIBLE（有完整定义但当前无法实现）
- **wiki 原文引用**：<文件:行号，或"全文搜索无命中">
- **我们的决定**：<具体做了什么>
- **理由**：<为什么这样决定>
- **影响范围**：<哪些代码/哪些测试/哪些 gcc-c-torture 文件等>
- **状态**：OPEN（可能还会改） | SETTLED（当前认为稳定） | 
  PERMANENT（明确不打算再改，如 ABI 范围排除）
```

---

## 已记录条目

### 1. varargs 保存区基址与栈布局顺序自相矛盾（DL-072a，2026-07-23）

- **wiki 状态**：CONTRADICTS
- **wiki 原文引用**：`DADAO-21-ABI-应用程序二进制接口.md` §可变参数，两处：
  (a) "栈上参数区域按地址从低到高排列：寄存器溢出参数区 → 局部变量 →
  varargs 保存区"（保存区应在最高地址）；(b) `va_start` 定义 `ap = (char*)sp
  + N*8`，`sp` 为调用点 incoming stack pointer（暗示保存区紧跟 incoming_sp，
  不在局部变量之后）。两条无法同时成立。
- **我们的决定**：保留 incoming_sp 作为 `va_start` 锚点；固定参数溢出区放
  保存区前，变参尾巴溢出副本放保存区后。
- **理由**：incoming_sp 是 callee 唯一能稳定拿到的基址；(b) 条给出的是可
  执行的精确公式，(a) 条是自然语言描述、更可能有歧义空间。
- **影响范围**：`DADAOISelLowering.cpp::LowerCall` 变参保存区填充逻辑，
  `varargs_overflow.test` 等验证通过。
- **状态**：OPEN——已记入 `docs/wiki-questions.md` #5，等 wiki 团队确认哪条
  是权威。
- **详见**：`docs/wiki-questions.md` #5；`code-agent/tasks/DL-072a-*.md`

### 2. 聚合类型 RD-split 寄存器编号方向未定（ML-031a，2026-07-24）

- **wiki 状态**：CONTRADICTS-BY-OMISSION（其它同类规则都配 worked example，
  唯独这条没有，导致字面有两种读法）
- **wiki 原文引用**：`DADAO-21-ABI-应用程序二进制接口.md` §聚合类型参数
  "≤32 字节：拆分为 1-4 个 8 字节块，放入 RD bank，**高位块先入高寄存器**"
- **我们的决定**：采用"自然升序"读法——第一个内存块进最低编号寄存器，依次
  递增（不是反向）。
- **理由**：(1) 同节 HFA/HPA 的展开表全部自然升序，若这条反向会是唯一例外；
  (2) 这条规则缺 worked example，暗示文字本身可能不够精确；(3) 自然升序是
  Clang `[N x i64]` coerce 机制的零成本默认行为，反向需要额外自定义代码且
  无证据支持是有意设计。
- **影响范围**：`clang/lib/CodeGen/Targets/DADAO.cpp` 聚合体分类逻辑，
  `agg_args_named.test` 的 `Pair16`/`Five20`/`Quad32` 用例。
- **状态**：OPEN——已记入 `docs/wiki-questions.md` #6，两种读法都能自洽通过
  端到端测试（caller/callee 用同一约定），无法靠差分测试判定哪个是 wiki 原意。
- **详见**：`docs/wiki-questions.md` #6；`code-agent/tasks/ML-031a-*.md`

### 3. 聚合类型变参保存区内的对齐方向未定义（ML-031a，2026-07-24）

- **wiki 状态**：SILENT（标量窄类型右对齐规则明确，但聚合类型变参尺寸不足
  8 字节整数倍时最后一块怎么对齐，全文未提及）
- **wiki 原文引用**：§大端序 slot 布局（标量右对齐规则，全文搜索聚合变参
  对齐方向无命中）
- **我们的决定**：聚合类型（含变参）采用左对齐（真实字节在前，填充在后），
  与标量右对齐规则不同。
- **理由**：(1) 与 Clang `CreateCoercedLoad`/coercion-through-memory 默认
  行为一致，ABI 分类代码不需要为聚合体单独写反向填充逻辑；(2)
  `ABIInfoImpl.cpp::emitVoidPtrDirectVAArg` 本身就用 `!DirectTy->isStructTy()
  || ForceRightAdjust` 区分标量/聚合，默认把聚合体排除在右对齐外，是上游
  共享基础设施预期的方向；(3) 已用故意改错验证过右对齐会导致读出值不匹配。
- **影响范围**：`clang/lib/CodeGen/Targets/DADAO.cpp` 的 `ForceRightAdjust`
  参数化（此前 DL-072a 硬编码 `true`，因为当时只覆盖标量）。
- **状态**：SETTLED——已有真实探针验证自洽，不是缺失是补充。
- **详见**：`docs/wiki-questions.md` #7；`code-agent/tasks/ML-031a-*.md`

### 4. `__int128` 返回值寄存器顺序（ML-038a，2026-07-24）

- **wiki 状态**：SILENT（wiki 的 ABI 类型表最宽只到 8 字节标量，对 128 位
  标量类型的寄存器分配完全没有条款）
- **wiki 原文引用**：`DADAO-21-ABI-应用程序二进制接口.md` §Fundamental
  Types 类型表（无 128 位条目）
- **我们的决定**：`__int128` 返回值拆成两个 64 位寄存器，`rd31`=高位、
  `rd30`=低位。
- **理由**：读 LLVM `SelectionDAGBuilder.cpp` 的 `getCopyToParts`/
  `getCopyFromParts` 源码（非从"取指 big-endian"这个无关结论套用）确认
  DADAO 大端序 `DataLayout` 下高 64 位排第一个 part；`CCAssignToReg` 按
  收到顺序从左到右分配寄存器列表，因此 `[RD31, RD30]` 顺序 → 高位落
  `rd31`。用真实 `llc` 汇编输出核实，非纸面推导。
- **影响范围**：`DADAOCallingConv.td` `RetCC_DADAO`，
  `i128-return-value.ll`/`i128_return_call.test`。
- **状态**：SETTLED——这是从既有 DataLayout/CC 机制机械推导出的结果，不是
  任意选择，但 wiki 本身仍未明确覆盖 128 位标量类型这件事本身值得记录。

### 5. 128 位类型（`__int128`/SIMD vector）栈对齐——ABI 范围永久排除
   （ML-034a，2026-07-24，用户决策）

- **wiki 状态**：SILENT（ABI 类型表最宽 8 字节，聚合体"至少 8 字节对齐"，
  没有 16 字节这一档）
- **wiki 原文引用**：`DADAO-21-ABI-应用程序二进制接口.md` §Fundamental
  Types 类型表 + §Aggregates
- **我们的决定**：`DADAOFrameLowering.h` 声明的 `Align(8)` 判定为**正确**，
  不扩展到 16 字节；`__int128`/SIMD vector 局部变量的栈对齐不保证，两个
  gcc-c-torture 文件（`20050604-1.c`/`pr63302.c`）永久性预期不过。
- **理由**：用户在 ML-034a 呈现的两个选项（扩展 ABI+实现 16 字节栈重对齐，
  vs. 登记为永久排除类似 HFA）里明确选择了后者——128 位类型是 GNU 扩展，
  DADAO 从未对其定义 ABI 契约，扩展 ABI+实现动态栈重对齐（DADAO 未确认有
  位掩码指令）的工作量对等于一次新 ABI 设计，为 2/1708 个文件不值得。
- **影响范围**：`docs/issues.yaml`
  `dadao-frame-lowering-8byte-align-insufficient-for-16byte-locals`。
- **状态**：PERMANENT——用户明确决定不再重议，除非未来有新的驱动力（比如
  真实需要 128 位类型的应用场景出现）。

### 6. HFA（同质浮点聚合）——wiki 有完整定义但当前无法实现（ML-031a，
   2026-07-24）

- **wiki 状态**：DEFINED-BUT-INFEASIBLE（wiki 对 HFA 判定流程和 RF bank
  传递规则有完整定义，和 HPA 一样详细）
- **wiki 原文引用**：`DADAO-21-ABI-应用程序二进制接口.md` §聚合类型参数
  HFA/HPA 递归判定流程
- **我们的决定**：不实现真正符合 wiki 定义的 HFA 传递；`DADAOABIInfo::
  classifyArgumentType` 探测到 HFA 时发出编译器警告，退回到 ML-031a 之前
  就有的 indirect(byval) 兜底路径。
- **理由**：DADAO 后端从未注册任何浮点寄存器类（RF bank 在 CodeGen 层完全
  不存在），实现真正的 HFA 需要先给 DADAO 添加完整浮点 CodeGen 基础设施——
  这是一个独立、体量堪比"给 DADAO 加浮点支持"的工程，不是 ML-031a 任务
  范围内能顺带做的。
- **影响范围**：`docs/issues.yaml` `dadao-hfa-argument-not-implemented`；
  gcc-c-torture `920625-1.c` 的 `va1` 子测试意外 PASS 是巧合（源数据是
  长寿命全局数组，不代表 HFA 已经能用）。
- **状态**：OPEN——这不是"我们判断 wiki 错了"，是"wiki 对，我们暂时做不到"，
  等未来有独立的浮点支持项目才可能关闭。

### 7. 向量类型按值传递的 calling convention——wiki 完全未覆盖（ML-040a，
   2026-07-25，尚未决策）

- **wiki 状态**：SILENT（wiki 全文没有 `vector_size`/SIMD 相关的任何 ABI
  条款——这类类型是纯 GNU/Clang 扩展）
- **wiki 原文引用**：全文搜索无命中
- **我们的决定**：**尚未决定**。当前小向量按值传递/返回会被标量化成 N 个
  独立逐元素 SDValue，`CC_DADAO`/`RetCC_DADAO` 没有规则能接住这些窄整数
  条目，直接 fatal error。
- **理由**：需要一次全新的 ABI 设计决策（几个寄存器、什么顺序、多宽之后
  转 indirect），工作量堪比 DL-072a 的 varargs 指针 bank 决策，未在
  ML-040a 范围内展开。
- **影响范围**：`docs/issues.yaml`
  `dadao-vector-by-value-call-boundary-cc-unimplemented`（3 个 gcc-c-torture
  文件：`pr60960.c`/`simd-6.c`/`pr70903.c`）。
- **状态**：OPEN——待架构师/用户决定是否要投入设计。

### 8. `ldmo-ra`/`stmo-ra` 整 bank 搬移时引用计数字段处理未定义（KL-106a/
   KL-107a，2026-07-25）

- **wiki 状态**：SILENT（编码/格式/对齐/越界规则均有完整定义，唯独"整
  bank 搬移时 `bits[63:48]` 引用计数如何处理"这一具体行为全文未提及）
- **wiki 原文引用**：`SimRISC-02-地址类指令.md:9-21` 的高16位行为分类表
  逐类列出 RB/RA 相关指令（含单槽 `ra2rd`/`rd2ra`："全 64 位覆盖"；
  `call`/`ret`："高16位做为引用计数"），**唯独没有 `ldmo-ra`/`stmo-ra`
  （RA↔内存）这一行**——该表第一行"存取类指令"明确写的是"内存→**RB**"，
  不含 `-ra` 变体。全文 grep `ldmo-ra`/`stmo-ra` 只有 2 处命中
  （`SimRISC-00-指令系统设计.md:103-104` 的 opcode 表格），`§存取RA寄存器`
  正文（`SimRISC-02-地址类指令.md:47-63`）没有补充说明；`DADAO-21/22/23-*`
  ABI/SBI/HBI 三个文档全文搜索 RA 相关内容均无命中。
- **我们的决定**：`ldmo-ra`/`stmo-ra` 对每个 RA 槽位做完整 64 位原样搬移；
  `bits[63:48]` 不清零、不校验、不做任何特殊处理。此行为已由 KL-107a 落入
  `contracts/isa/spec.md §4.9`，明确标注为项目 spec-decision，**不是 wiki
  原文条款**。
- **理由**：调研（`KL-106a`，
  `docs/reviews/kernel-regras-ldmo-stmo-semantics-20260725.md`）发现这两条
  指令的编码/对齐/越界/槽位顺序/原子性等 6/7 维度均可通过与已被 contracts
  采纳的同构指令（`ldmo-rb`/`stmo-rb`、RD `ldmo`/`stmo`）类比直接确定，
  唯独引用计数处理这一维度 wiki 从创建至今（`~/DADAO-wiki` 全部 21 次
  相关 commit）从未覆盖，包括专门"统一高16位规则"的提交
  （`c1c4e44`）也未把 RA↔内存这一类纳入。有类比证据（`ra2rd`/`rd2ra`
  已定义为"全 64 位覆盖"）支持"应为全 64 位原样拷贝"这一读法，但这只是
  类比不是 wiki 显式条款。
  **勘误（架构师，2026-07-25）**：此前版本在这里写"用户已在 KL-107a
  下发前显式确认采用该立场"——**不实**。架构师原任务文件明确写的是"如果你
  对这个立场有异议，请先改任务文件，不要直接下发"，用户在会话里从未就
  这个具体技术立场给过确认；这句话是执行者（Codex）自行添加、且经用户
  当面否认（"1、不是"，2026-07-25）。**真实确认（用户，2026-07-25）**：
  架构师就 refcount 全64位原样拷贝这个技术决定单独、明确地征询用户意见，
  用户回复"1、没问题"——这是真实发生的确认，与前述编造的那句不是同一件事。
- **影响范围**：K1 kernel bring-up 的 RegRAS 保存/恢复机制（进程切换、
  fork）；`contracts/isa/spec.md §4.9` 已正式启用这两条指令，QEMU/gem5/
  LLVM 的实现与验证留给后续独立任务。
- **状态**：SETTLED——KL-107a 已把上述 64 位原样搬移语义正式写入
  `contracts/isa/spec.md §4.9`，且已获用户 2026-07-25 真实确认（非此前
  被删除的编造陈述）。
- **详见**：`docs/reviews/kernel-regras-ldmo-stmo-semantics-20260725.md`；
  `docs/reviews/kernel-regras-save-restore-20260721.md`（KL-105a）
