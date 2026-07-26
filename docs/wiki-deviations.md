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

### 9. `escape` 退出流程从未赋值 `inner_cfx_code`（KL-101a/KL-110a，
   2026-07-25）

- **wiki 状态**：CONTRADICTS-BY-OMISSION。`escape` 的步骤0-4没有任何一步
  提到 `inner_cfx_code`；同时指令行为说明声称 cross-cfx operand 可直接
  跳过多层、恢复目标 cfx 的 prev frame，但退出伪码只读取当前 cfx frame，
  没有目标 frame 选择/遍历步骤。
- **wiki 原文引用**：`DADAO-12-SEE-主管系统运行环境.md` 第813-845行
  "异常退出流程"完整伪代码——步骤0（escape cfx mask 检查）、步骤1
  （`inner_cfx_mask <= cfx_⟨cfxname⟩_excp_prev_cfx_mask`）、步骤2
  （`inner_run_mode <= cfx_⟨cfxname⟩_excp_prev_run_mode`）、步骤3
  （`cfx_⟨cfxname⟩_escape_num <= ... + 1`）、步骤4（跳转），**没有任何
  一步写 `inner_cfx_code`**。对照"异常进入流程"（同文件第678-811行）
  第8步会显式写 `inner_cfx_code <= temp_cfx_code`；`inner_run_mode`/
  `inner_cfx_mask` 都各自有专门的 `excp_prev_run_mode`/
  `excp_prev_cfx_mask` 寄存器（SEE §3 cg5, rc0/rc1，第357-358行）用于
  异常退出时恢复，但**没有对应的 `excp_prev_cfx_code` 寄存器**——这不是
  遗漏一行赋值这么简单，而是从存储结构上就没有为"恢复 `inner_cfx_code`"
  预留位置。此项已被 `KL-101a`（`docs/reviews/
  kernel-hypv-supv-handoff-20260721.md` 第30-36行）核实为真实 wiki 空白，
  原话："这段伪代码里 `escape` 从未写 `inner_cfx_code`——这是架构师已核实
  的真实 wiki 空白"；`KL-102a`（`docs/reviews/
  kernel-cfx-state-patch-surface-20260721.md`）在给出 O1 最小语义清单
  （§3.1）时同样只列出"恢复 mask/mode、`escape_num++`、跳转"，未包含
  `inner_cfx_code` 的任何处理步骤，隐含的处置方向与 wiki 的沉默一致。
  同文件第664-676行又明确描述 cross-cfx shortcut：B 中
  `escape cfx_A` 应直接恢复 A 的 prev 现场并丢弃中间 frame；这与
  第815行“`⟨cfxname⟩` 是当前 `inner_cfx_code`”及第837-844行只读取当前
  frame 的伪码无法同时执行。
- **我们的决定**：`escape` 不修改 `inner_cfx_code`——执行前是什么值，
  执行后保持不变。已落入 `contracts/isa/spec.md §8.2`（"QEMU's O1
  implementation therefore leaves `inner_cfx_code` unmodified by
  `escape`, matching the wiki's silence rather than inventing a restore
  rule"），QEMU 实现（`target/dadao/helper.c::helper_escape()`）中
  `env->inner_cfx_code` 未被触碰，仅作为代码注释里的显式说明存在。
- **理由**：wiki 沒有定义就不该凭空发明恢复规则；且没有配套的
  `excp_prev_cfx_code` 存储寄存器可供恢复，"保持不变"是唯一不需要额外
  发明存储结构的读法。这个决定对 KL-110a 的 O1 验收范围没有实际影响——
  HBI §3 的 hypv 引导桩在执行 handoff 序列全程都没有经历过任何异常进入
  （`inner_cfx_code` 自 reset 起一直是 `cfx_power`，未被任何 trap
  改写过），所以 `escape` 执行前后 `inner_cfx_code` 是否被"恢复"在这个
  具体场景下不可观察。
- **影响范围**：K1 kernel bring-up 后续任务中，若出现真实的
  `trap → cfx_A → trap → cfx_B → escape cfx_A` 这类多层调用链，
  `inner_cfx_code` 在 `escape` 后到底应该是什么值，会成为一个需要独立
  验证的开放问题（当前"保持不变"的读法在这类多层场景下是否正确未经
  测试）；`contracts/isa/spec.md §8.2` 已经把这个决定和它的依据写清楚，
  后续任务如果要挑战这个读法，应该先在这里更新。
- **KL-119a 候选E方案比较（2026-07-26，尚未拍板）**：
  1. **E1：新增 `excp_prev_cfx_code`（建议 `(cg,rc)=(5,5)`）**。每次
     trap 在目标 cfx 的 frame 中保存进入前的 `inner_cfx_code`，escape
     先锁定当前 frame owner，再与 mode/mask/PC 一起恢复 caller cfx。
     它沿用 cg5 既有 per-cfx frame 模型；A→B→C 这类各层 cfx 不同的链
     无需硬件栈，每个 cfx 各保存一份 caller。A→B→A 这类同 cfx 重入仍
     按 SEE 第660行由软件先把 cg5 保存到 cg6，和现有嵌套规则一致。
     代价是一份每-cfx 6-bit（按寄存器实现可为64-bit）状态、`cfx2rd/
     cfx2rc` 映射、双后端 migration/copy state，以及修改 §8.2 的既有
     “保持不变”决定。优点是 SBI 的 TLB→PTW→TLB 示例无需改写，且没有
     隐藏栈深/溢出语义。它只闭合逐层普通返回；`escape` 一次跳过多个 cfx
     的 shortcut 与 SEE 伪码存在独立矛盾，K1 明确 non-claim。未来若保留
     shortcut，E1 还需增加 operand 选择目标 frame、验证目标确实在调用链、
     丢弃中间 frame 的规则，成本不再只是一个 rc5。
  2. **E2：硬件异常上下文栈**。trap push
     `{cfxcode,mode,mask,cause frame}`，escape pop，cg5 显示栈顶。
     它可原生支持同 cfx 多层重入，但必须新定义栈深、溢出异常、跨-cfx
     shortcut 如何按 operand 查找并 pop 到目标层、软件写 cg5 修改哪一层，以及 QEMU migration/
     gem5 ThreadContext copy。功能完整但新增状态和验证面最大。
  3. **E3：K1 单层软件 trampoline/SBI 改写**。PTW 返回 tlb continuation
     并由软件恢复 tlb frame。当前 ISA 没有可写 `inner_cfx_code`，因此
     trampoline 仍运行在 ptw 身份；若再 trap tlb 会覆盖原 tlb frame，
     仍需软件保存/恢复且最终 caller code 依旧无法恢复。除非同时新增
     “escape operand 设置 return cfx”或可写 inner-code 机制并改写 SBI
     示例，否则它不是闭合方案，只能作为测试捷径，**不建议**。
- **KL-119a 建议**：选择 E1。它是唯一同时保持现有 per-cfx frame 模型、
  不改写 SBI handler 控制流且不引入隐藏深度/溢出规则的方案；但这是
  架构变更建议，不是已冻结决定，须等待架构师/用户确认后才能修改本条
  “escape 不修改 inner_cfx_code”的现行决定。若还要求一次跨越多层的
  shortcut，需与 E1 分开再冻结，不应阻塞 K1 的逐层 SBI return。
- **状态**：OPEN——技术决定本身有 wiki 文本结构（缺配套存储寄存器）支持，
  但只在 O1（单层、无嵌套 trap）场景下被验证过，多层调用链场景仍是
  未决语义；KL-119a 已给出 E1/E2/E3 比较并建议 E1，尚待确认。
- **详见**：`docs/reviews/kernel-hypv-supv-handoff-20260721.md`
  （KL-101a，第30-36行发现原文）；`docs/reviews/
  kernel-cfx-state-patch-surface-20260721.md`（KL-102a，O1/O2 范围划分）；
  `contracts/isa/spec.md §8.2`（决定落地位置）

### 10. `cg_reg_deleg` 委托状态被拒绝时的异常类别与检查时机未定义（KL-111a，
    2026-07-25）

- **wiki 状态**：SILENT（寄存器语义"bit=0 时允许 supv 访问"有明确定义，
  且有一个"委托后允许访问"的正面用例，唯独"未委托/仍被拒绝时应该产生什么
  异常、检查发生在指令执行的哪个阶段"全文未提及）
- **wiki 原文引用**：`DADAO-13-HEE-超管系统运行环境.md:24`（寄存器定义）；
  `DADAO-22-SBI-主管系统二进制接口.md:701`（唯一正面用例，"因此 supv
  可直接通过 cfx2rc/cfx2rd 操作该寄存器"，只说委托后能访问，不说委托前
  访问会怎样）；`DADAO-23-HBI-超管系统二进制接口.md:32`（HBI 引导代码
  注释，同样只描述"清除委托"这个动作，不描述不清除的后果）。全文 grep
  `cg_reg_deleg`/`cg reg delegation` 只有这 3 处命中，`DADAO-12-SEE-
  主管系统运行环境.md` 的两处正式伪代码（§5 异常进入流程
  `:678-811`、SimRISC-04 §寄存器传输指令 `:72-103`）均未提及这个寄存器，
  与同一文档里 `escape_cfx_mask`/`<instr>_cfx_mask` 这组"跨 cfx 执行权限"
  机制形成对比——后者被写入了正式检查伪代码（`:721`），前者完全没有。
- **我们的决定**：尚未决定。
- **理由**：`KL-111a`（`docs/reviews/
  kernel-hypv-supv-o2-permission-recon-20260725.md`）在设计 O2 负例时
  发现，"未清 delegation 就从 supv 访问被 delegation 的 cg"这个候选无法
  构造出一个 wiki 有依据的精确负例——SimRISC-04:87 的"读写权限不匹配→
  CFXREG"是唯一可能相关的条款，但它与 `cg_reg_deleg` 的关系是推断，不是
  wiki 显式陈述，且这条条款本身更可能指向寄存器"访问"列（RO/RW/HW/WO）
  的读写方向不匹配，而不是委托状态。
- **影响范围**：K1 O2 实现任务的候选范围——"cg0-2/cg4/cg6/cg7 的 supv
  委托访问控制"这个候选暂不实现，O2 优先实现"跨 cfx escape/cfx2rc 权限
  检查"和"cfx2rc 目标 (cg,rc) reserved → CFXREG"这两个已有明确 wiki
  依据的候选（详见 KL-111a 报告 §4）。
- **状态**：OPEN——待架构师/用户决定是否需要 wiki 团队澄清，或项目自行
  拍板（如"deleg 拒绝统一按 CFXREG 处理，等同 SimRISC-04:87 第三分句"）。
- **详见**：`docs/reviews/kernel-hypv-supv-o2-permission-recon-20260725.md`
  §2.1、§3

### 11. `cfx2rc_cfx_mask` 跨 cfx 执行权限检查与 HBI §3 引导桩相互矛盾（KL-112a，2026-07-25）

- **wiki 状态**：CONTRADICTION（不是沉默——两处正式文本都明确存在，字面
  同时成立时互相冲突）。
  1. `DADAO-12-SEE-主管系统运行环境.md` 第711-728行"异常进入流程"
     伪代码：`elif cfxcode != inner_cfx_code and
     cfx_⟨cfxname⟩_<mode>_<instr>_cfx_mask & (1 << cfxcode): cause <=
     ILLI`（`<instr>=CFX2RC` 时即 `cfx2rc_cfx_mask`），对 `cfx2rc` 无条件
     适用，不区分运行模式（`<mode>` 只是决定用哪一份寄存器，hypv 模式
     没有被文字排除在检查之外）。
  2. `DADAO-13-HEE-超管系统运行环境.md` 第15行：`cfx_⟨cfxname⟩_hypv_
     cfx2rc_cfx_mask` 复位值="全1"（即默认禁止所有跨 cfx `cfx2rc`）。
  3. `DADAO-23-HBI-超管系统二进制接口.md` 第31-64行 hypv→supv 移交
     唯一文档化序列：前 12 条 `cfx2rc cfx_<name>_hypv_cg_reg_deleg, rd2`
     （第34-45行，umon/jmon/smon/ptw/tlb/cache/hart/llc/pmem/timer/uart/
     power）里，除最后一条（`cfx_power`）外，其余 11 条的目标 cfxcode
     全部 ≠ `inner_cfx_code`（复位起恒为 `cfx_power`=63）——是**跨 cfx**
     `cfx2rc`。这段引导代码全程**没有任何一条**写
     `cfx_power_hypv_cfx2rc_cfx_mask`（该 (cg,rc)=(3,3) 从未出现在 HBI
     §3 原文里）。
  三者字面同时生效时得到矛盾：若 1+2 按字面严格执行，第一条
  `cfx2rc cfx_umon_hypv_cg_reg_deleg, rd2`（cfxcode=umon=0）就会因
  `cfx_power_hypv_cfx2rc_cfx_mask` 位0=1（从未清除）触发 ILLI——HBI §3
  这段唯一文档化的引导序列会在第一条指令就永久失败。
- **发现过程**：`KL-111a` 报告 §4 设计2（候选B2）提出"跨 cfx `cfx2rc`
  权限检查"作为与设计1同构、"成本几乎为零"的可选附加负例，给出的验证
  指令是一个独立场景（`cfx2rc cfx_smon_user_global_cfx_mask, rd2`），
  报告本身没有针对 O1 回归重放验证。`KL-112a` 实现时先按候选B2字面实现，
  **对 O1 回归探针重放时**（`tests/scripts/gen_kl110a_o1_probe.py` 生成
  的原始 HBI §3 桩）实测发现第一条 `cfx2rc cfx_umon_hypv_cg_reg_deleg,
  rd2` 就触发 ILLI，O1 回归从 exit=42 变成 exit=0x82——用真实回放而非
  纸面推理确认了这个矛盾，是 KL-111a 调研阶段（未接触真实 QEMU 回归
  套件）未能发现的。
- **我们的决定**：候选B2（"设计2"）不在 KL-112a 实现——`cfx2rc` 只实现
  设计3（reserved (cg,rc) → CFXREG），不实现跨 cfx `cfx2rc_cfx_mask`
  检查。`target/dadao/helper.c::helper_cfx2rc()` 完全不读写
  `cfx2rc_cfx_mask`，也没有为它分配任何 `CPUArchState` 存储（早期实现
  版本加过 `cfx_cfx2rc_cfx_mask[64][4]` 数组和检查代码，因触发本条矛盾
  已撤回，未落入最终 commit）。
- **理由**：把 SEE §5 entry-flow 的通用检查按字面无条件套用到
  `cfx2rc`，会让 wiki 自己给出的唯一 `cfx2rc` 真实使用范例（HBI §3
  引导桩）永久非法——这不是"实现复杂度高"，是两处正式文本字面互斥，
  在没有第三处 wiki 文字给出"hypv 模式豁免"或"引导阶段豁免"这类例外
  规则之前，实现方只能二选一（要么破坏 HBI §3，要么不做这个检查），
  凭空发明豁免规则违反项目"不发明未在 wiki 出现的规则"惯例（对照
  第9条"不发明未定义的恢复规则"的同一原则）。设计1（`escape` 的
  `escape_cfx_mask` 检查）没有这个问题——O1 的唯一 `escape` 使用
  （`escape cfx_power,0`）是 self-escape（`cfxcode==inner_cfx_code`），
  设计1的跨 cfx 检查按定义对 self-escape 不生效，两者不对称。
- **影响范围**：K1 kernel bring-up 后续如果需要真正的跨 cfx `cfx2rc`
  权限隔离（比如 supv 内核限制某些 cfx 只能被特定 cfx 访问），需要先
  解决这条矛盾——可能的方向包括（未评估可行性，仅列出候选）："hypv 模式
  下 cfx2rc_cfx_mask 检查不适用"这类模式豁免、"HBI §3 应该先写
  cfx2rc_cfx_mask 但 wiki 漏写了"这类引导序列补全、或"这条检查实际只
  适用于 supv/user/jail 模式，cg3/hypv 那份 cfx2rc_cfx_mask 寄存器的
  存在只是为了寻址对称性，从不被读"这类范围收窄读法——均需 wiki 团队
  澄清或项目自行拍板，本条只记录矛盾本身，不预判解法。
- **状态**：OPEN。
- **详见**：`docs/reviews/kernel-hypv-supv-o2-permission-recon-20260725.md`
  §2.4（候选B2 原始提案）；`code-agent/tasks/
  KL-112a-implement-hypv-supv-handoff-o2-qemu.md`（完成区，撤回过程与
  A/B 回归重放证据）；`target/dadao/helper.c::helper_cfx2rc()`
  函数级注释（撤回决定落地位置）。

### 12. 通用 pending 寄存器与同 cfx cause 优先级（KL-119a，2026-07-26）

- **wiki 状态**：SILENT/CONTRADICTS-BY-OMISSION——异常流程反复使用
  `cfx_⟨cfxname⟩_pending`，共有寄存器表却没有它；timer/UART/power 有
  专有 pending，带可屏蔽 IPI 的 hart 和带可屏蔽 FPEXCP 的 monitor 没有。
  同一 cfx 多 pending cause 的选择顺序也未定义。
- **wiki 原文引用**：`DADAO-12-SEE-主管系统运行环境.md:337-364`
  （cg4/cg5 common table）、`:588,608,636`（三个专有 pending）、
  `:411,536,600,624-628,648`（全部可屏蔽 cause）、`:650-660,693-699,
  763-785`（pending/优先级与 entry flow）。
- **我们的决定**：所有非 reserved cfx 新增 common pending
  `(cg,rc)=(4,7)`，64-bit、reset 0、RW/W0C；只有该 cfx cause 表中的
  maskable 位有效。现有 timer/UART/power pending 是独立的 device-source
  latch，不是 common cause latch 的 alias；source assert/expire 不受任何
  mask 影响，先置专有 source bit，再 OR 映射后的 cause 到 common pending。
  只要同一 cause 映射的任一 private pending 仍为1，common cause 就必须
  保持/重新置位。选择顺序为先最低
  cfxcode，再选该 cfx 最低 set cause bit；进入不自动清 pending。电平源
  ack 顺序固定为 source deassert/service → drain 该 cause 的全部 private pending →
  清 common cause pending，顺序颠倒且 level 未撤销时会重新置位。
- **理由**：cg4/rc7 是 common table 后首个空槽，一处定义即可补齐 hart/
  monitor 缺口；source/cause 两级区分保留 8 个 timer counter 等多个设备
  source 汇聚到一个 cause 的能力。最低位优先与已有最低 cfxcode 方向一致
  且可确定双后端 oracle。
- **影响范围**：`cfx2rd/cfx2rc`、所有 cfx state、FPEXCP/IPI/timer/UART/
  power、QEMU migration、gem5 ThreadContext copy、异步优先级测试。
- **状态**：SETTLED（项目 K1 profile）；已落入
  `contracts/isa/spec.md §8.5.1`。

### 13. K1 timer0 语义与 `GET_TIME`（KL-119a，2026-07-26）

- **wiki 状态**：CONTRADICTS-BY-OMISSION——函数表称 timeout 是“周期
  计数值”，示例称“timeout 周期后”，伪码写 counter0 后递减；没有定义
  到期、one-shot stop、periodic reload、pending ack。`GET_TIME` 表述为
  当前周期数，伪码却读取会递减的 counter0。
- **wiki 原文引用**：`DADAO-12-SEE-主管系统运行环境.md:582-600`
  （timer registers/causes）、`DADAO-22-SBI-主管系统二进制接口.md:
  516-519,565-596`（SBI 表、伪码和示例）、`DADAO-12-SEE-
  主管系统运行环境.md:523-527`（per-hart cycle counter）。
- **我们的决定**：K1 只承诺 counter0 decrement profile。
  `SET_TIMER(timeout)` 是相对延迟，写 current counter 与内部 reload latch；
  非零值在恰好 timeout 个 tick 后的 1→0 到期，0 在下一指令边界可触发。
  counter0 到期无视 timer mask 先置 private timer pending bit0 和 common
  pending bit10；private timer mask bit0 只控制交付。one-shot 到期清
  enable，periodic 从最后写值 reload；两级 pending 按第12条顺序 W0C。
  `GET_TIME` 返回 `cfx_hart_cycle_lo`，不返回倒计时。counters1-7 与 increment
  mode 明确是 K1 non-claim，后续条件任务收口。K1 functional timebase
  固定为1 timer tick = 1次 per-hart cycle counter increment；QEMU/gem5
  均按每条架构指令退休推进一次 virtual cycle，`cycle_lo` 按 `2^64` 回绕。
- **理由**：相对递减与 SBI 的实际 set-timer 示例一致；monotonic hart cycle
  才能满足 `GET_TIME` 名称和 kernel clocksource 需求；共享 virtual-cycle
  timebase 防止 QEMU/gem5 对“tick”采用不同单位；reload latch 是在不新增
  可见寄存器时让 periodic 可确定的最小状态。该 timebase 只作功能 oracle，
  不代表流水线性能。
- **影响范围**：QEMU timer/event、gem5 timer/event、SBI handler、
  kernel clockevent/clocksource、K1 timer regressions。
- **状态**：SETTLED（K1 最小 profile）；已落入
  `contracts/isa/spec.md §8.5.2`。完整八 counter/increment 仍为 OPEN
  non-claim。

### 14. 双后端架构 TLB 固定测试 profile（KL-119a，2026-07-26）

- **wiki 状态**：SILENT（非架构阻断）——wiki 用 `tlb_exist` 暴露逻辑集合，
  但未规定每集合容量、相联度或替换策略。
- **wiki 原文引用**：`DADAO-12-SEE-主管系统运行环境.md:463-495`
  （exist/enable/control、64 个逻辑集合与 fault）。
- **我们的决定**：K1 QEMU/gem5 测试 profile 固定为 64 个集合全部存在、
  每集合 16-entry、统一 fully-associative、deterministic true-LRU；
  `tlb_exist=UINT64_MAX`，enable 按 wiki 复位为全1。
- **理由**：固定容量/替换才能构造稳定 hit/miss/eviction 差分 oracle；这些
  数值只服务功能一致性，不是 ISA 性能或硬件微架构承诺。
- **影响范围**：QEMU/gem5 architected TLB model、失效/替换探针和测试报告
  的 non-claim 边界。
- **状态**：SETTLED（测试 profile，不是架构性能契约）；已落入
  `contracts/isa/spec.md §8.5.3`。

### 15. K1 外部中断采用合成 level source，不冻结 UART/PLIC（KL-119a，
2026-07-26）

- **wiki 状态**：SILENT——wiki 只给出“外设按 source 路由”和 UART cause
  bits；UART0 的 64 个寄存器写“参照硬件协议”，没有 IRQ 拉高/撤销、
  source clear 或 device/pending ack 顺序，全文也无 PLIC。
- **wiki 原文引用**：`DADAO-12-SEE-主管系统运行环境.md:40-42,
  602-628,650-656`；`DADAO-22-SBI-主管系统二进制接口.md:625-680`。
- **我们的决定**：K1 使用 test-machine-only `K1_EXT0` level source，
  路由为 cfx_uart source0，但不实现/宣称 UART 或 PLIC。assert 设置 private
  `cfx_uart_pending` bit0 并映射到 common UART0 cause bit32；deassert
  只撤销 level，随后清 private bit0，再清 common bit32。若先 clear 再
  deassert，active level 在下一边界前重新置位。刺激机制属于 backend test
  infrastructure，不形成 guest ABI。
- **理由**：这能验证真实异步 source、mask/pending/unmask/re-entry 和双后端
  路由，又不从“参照硬件协议”四个字发明 UART device model。
- **影响范围**：KL-137a/138a 外部 IRQ probe、QEMU/gem5 test machine、
  K1/K2 集成证据；UART/PLIC 和 kernel serial/irqchip 仍需独立契约。
- **状态**：SETTLED（K1 test profile）；已落入
  `contracts/isa/spec.md §8.5.4`。
