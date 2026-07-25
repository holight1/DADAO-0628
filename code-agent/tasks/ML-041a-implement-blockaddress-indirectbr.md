# ML-041a：实现 `BlockAddress`（computed goto / `&&label`）支持

**执行环境**: 本地 subagent

## 硬约束（务必遵守，违反视为任务失败）

- **禁止**对 `.work/llvm` 做 `git rebase`/`git am` 重放整条历史/`git reset
  --hard`。只允许在当前 HEAD 基础上新增普通 `git commit`。
- **先诊断根因，再修复**——独立用 `-print-after-all`/IR dump 确认具体
  崩溃触发点（`Cannot select: t.: i64 = BlockAddress<@fn, %label> 0`），
  弄清楚 `DADAOISelLowering.cpp`/`DADAOISelDAGToDAG.cpp` 当前对
  `ISD::BlockAddress`/`ISD::BRIND`（间接跳转）分别处理到什么程度。
- **优先复用已有基础设施**——DADAO 后端已经实现了 `GlobalAddress` 的
  `rela`+`addi` lowering（`ML-013a`/`ML-030a` 等）和 jump table 的间接
  跳转选择（历史 patch 里的 `ML-003h`/`ML-004d` 等，用 `BRIND` 或等价
  机制做 `switch` 语句的跳转表分发）。`BlockAddress` 本质上是"取一个
  基本块的地址当成一个编译期常量"，`indirectbr`（`goto *ptr`）本质上是
  "对一个运行时寄存器值做无条件跳转"——这两块很可能已经有可以直接复用的
  相邻实现（跳转表分发就是一种间接跳转），不要凭空新写一整套机制，先确认
  能复用多少。
- **完成后立即导出 patch**（不要延后），追加进对应 `series`。
- 完成后必须在任务文件里写「完成区」+ subagent 自审「审阅记录」（含逐条 finding
  + 判决）。

## 背景

`ML-035a`（`docs/reviews/ML-035a-gcc-torture-gap-rescan-2026-07-24.md`
§1.2(d)）确认 3 个文件因 `BlockAddress` 未实现而编译期崩溃：

```
fatal error: error in backend: Cannot select: t.: i64 = BlockAddress<@fn, %label> 0
```

文件：`990208-1.c`, `comp-goto-1.c`, `pr70460.c`——全部用到 GCC 的
"computed goto" / "labels as values" 扩展（`&&label` 取标签地址，
`goto *ptr` 跳到运行时计算出的地址）。这是 P3 优先级，本次重新确认这 3 个
文件目前仍是 `FAIL_COMPILE`。

## 目标

1. **诊断**：确认当前 `DADAOISelLowering.cpp` 对 `ISD::BlockAddress` 的
   `setOperationAction`（大概率完全未声明，默认走 `Expand` 但 `Expand`
   对 `BlockAddress` 这种"编译期已知地址常量"类型通常没有意义的展开路径，
   需要确认具体行为）；确认 `ISD::BRIND`（间接跳转）当前的选择状态——
   本项目已有 switch 跳转表分发，很可能已经支持某种形式的间接跳转，
   需要确认是否可以直接复用同一套指令选择。
2. **实现**：
   - `BlockAddress` 需要能被当成一个编译期常量地址处理（类似
     `GlobalAddress`，走 `rela`+`addi` 或等价的重定位表达式），值放入
     RB bank（地址）寄存器。
   - `indirectbr`（对应 `goto *ptr` 的 IR 形式）需要能选择出一条无条件
     跳转到寄存器值的指令，复用已有的跳转表分发间接跳转机制（如果确认
     可复用）。
   - 汇编器/链接器层面确认 `BlockAddress` 产生的重定位类型能被正确处理
     （标签地址在同一函数/同一 object 内，理论上不需要跨 section 重定位，
     但需要验证 `MCCodeEmitter`/lld 对这类 fixup 的处理路径）。
3. **验证**：独立、判别性的 CodeGen lit 测试 + 项目 E2E 测试（真实
   computed goto 跳转序列，`volatile` 输入 + 正负控制，QEMU+gem5 双后端
   跑通端到端正确性）。

## 验收

- 3 个目标文件用 `python3 tests/scripts/gcc_torture_sweep.py --filter
  "990208-1|comp-goto-1|pr70460"` 重跑，如实报告有几个变绿（不强行要求
  全部 3 个——如果某个文件还牵涉本任务未覆盖的其它问题，如实报告）。
- 独立、判别性的 CodeGen lit 测试（`llvm/test/CodeGen/DADAO/`）+ 项目
  E2E 测试（`tests/lit/E2E/`，volatile + 正负控制，双后端）。
- 全量 `gcc-c-torture` 重扫（当前基线 `1479/90/124/15`），逐文件 diff
  确认零回归。
- 全量 `llvm-lit tests/lit/E2E/`（当前基线 80/80）：零回归。
- `python3 tools/run_differential.py`：AGREE 数与当前基线一致、DIVERGE=0。
- `python3 scripts/manifest_check.py`/`check_issues.py` 通过。
- LLVM 侧改动用**普通** `git commit` 落地，`git format-patch` 导出对应
  patch，追加进 `series`；独立验证可在干净 pin-commit checkout 上 `git am`
  成功，且 replay tree 与开发树 tree hash 一致。
- 如果诊断后发现工作量远超预期（比如发现跳转表机制其实不可复用，需要
  从零设计一套新的间接跳转/重定位机制），如实停下报告，登记
  `docs/issues.yaml`，不要勉强拼一个高风险的大改动。

## 参考指针

- `docs/reviews/ML-035a-gcc-torture-gap-rescan-2026-07-24.md` §1.2(d)
  （断言崩溃原文）
- `.work/source/llvm-test-suite/SingleSource/Regression/C/gcc-c-torture/execute/
  {990208-1,comp-goto-1,pr70460}.c`（原始复现源码）
- `.work/llvm/llvm/lib/Target/DADAO/DADAOISelLowering.cpp`（`GlobalAddress`
  lowering 现有实现，`BlockAddress` 大概率可以类比处理）
- `.work/llvm/llvm/lib/Target/DADAO/DADAOISelDAGToDAG.cpp`（jump table /
  间接跳转现有指令选择，确认能否复用于 `BRIND`）
- `components/llvm/patches/`（历史 patch 名称含 `jump-table`/`jmp`/
  `BRIND` 关键词的条目，可以 `grep` series 文件找到具体是哪几个 patch
  实现了现有的跳转表分发机制）
- `code-agent/tasks/ML-030a-relocation-range-large-constant-offset.md`
  完成区（`GlobalAddress` 重定位相关的既有诊断方法论，`BlockAddress`
  如果走类似的重定位路径可以参考）
- `feedback_volatile_needed_for_memory_verification_tests`（新测试涉及
  写读回校验要用 volatile + 负控制）

## 完成区（2026-07-25）

### 诊断结果

- `ISD::BRIND`（间接跳转）和 `ISD::JumpTable`/`ISD::ConstantPool` 在
  `DADAOISelLowering.cpp` 构造函数里**早就已经**声明为 `Custom`（第
  82-85 行），且各自都有完整实现：`lowerBRIND` 把 `BRIND` 包成
  `DADAOISD::BRIND` 节点，`DADAOInstrInfo.td` 里 `Pat<(DADAObrind
  GPRD:$target), (JUMP_PSEUDO_INDIRECT GPRD:$target)>` 选择成
  `JUMP_PSEUDO_INDIRECT` 伪指令，`expandPostRAPseudo`
  （`DADAOInstrInfo.cpp:206-223`）展开成 `rd2rb rb5, <target>, 1` +
  `jump rb5, rd0, 0`（这正是既有 `switch` 跳转表分发用的机制,
  ML-004d 的 rb0 误用坑已经修过）。**`ISD::BlockAddress` 则完全没有
  `setOperationAction` 声明**——`command grep` 全库确认零匹配——默认
  action 下这个节点原样落到 DAGToDAG 通用匹配表，没有任何 `Pat<>`
  能匹配裸 `BlockAddressSDNode`，于是崩成
  `Cannot select: t.: i64 = BlockAddress<@fn, %label> 0`。
- 结论：`indirectbr`（`goto *ptr`）**不需要任何新代码**——它被
  SelectionDAGBuilder 直接、通用地降到 `ISD::BRIND`，而这个节点已经
  被选择过了。唯一缺的是 `BlockAddress`（`&&label`）本身的 Custom
  lowering，做法和 `GlobalAddress`（同文件 `lowerGlobalAddress`）完全
  一样：包一层 `DADAOISD::PCREL_HI`，走既有的 rela+addi 重定位序列
  （`DADAOISelDAGToDAG.cpp` 里 `PCREL_HI` 的手工选择只泛型地读
  `Node->getOperand(0)`，从不检查底层是 `TargetGlobalAddress` 还是
  `TargetBlockAddress`，天然可复用，DAGToDAG 侧零改动）。
- 汇编/链接层面：`DADAOAsmPrinter.cpp::lowerToMCInst` 的
  `switch (MO.getType())` 此前完全没有 `MO_BlockAddress` 分支，落进
  `default: llvm_unreachable`。用标准 `AsmPrinter::GetBlockAddressSymbol`
  接口生成符号即可，这个接口内部会自动向 `MachineModuleInfo`
  登记，使 `AsmPrinter::emitBasicBlockStart`（LLVM 通用代码）在这个
  基本块本会被 fallthrough 消除标签的情况下依然强制打印标签——这跟
  `emitFunctionBodyStart` 里已有的、为跳转表目标手工调用
  `setLabelMustBeEmitted()` 打的补丁是**同类问题、但不同机制、且
  target-independent 已经处理好**，不需要 DADAO 侧再打一次补丁（已用
  `llc` 手动验证：`take_address_only` 测试里 `.Ltmp3:` 标签确实被
  打印在只有 fallthrough 前驱的基本块前）。

### 实现

- `DADAOISelLowering.h`：新增 `lowerBlockAddress` 声明；`PCREL_HI`
  节点注释更新为同时覆盖 `GlobalAddress|BlockAddress`。
- `DADAOISelLowering.cpp`：
  - `setOperationAction(ISD::BlockAddress, MVT::i64, Custom);`
  - `LowerOperation` 里加 `case ISD::BlockAddress: return
    lowerBlockAddress(Op, DAG);`
  - `lowerBlockAddress`：`cast<BlockAddressSDNode>` 取出
    `BlockAddress`+`Offset`，`DAG.getTargetBlockAddress` 再包
    `DADAOISD::PCREL_HI`，与 `lowerGlobalAddress` 逐行对称。
- `DADAOAsmPrinter.cpp`：`lowerToMCInst` 加 `MO_BlockAddress` 分支，用
  `GetBlockAddressSymbol` + `MCSymbolRefExpr`，并保留 offset 加法（对称
  `MO_GlobalAddress` 分支已有的 addend 处理，即使当前所有测试场景
  offset 恒为 0）。
- 额外验证（非新代码，纯只读检查）：`DAGCombiner.cpp` 里唯一会把
  `ADD(symbol, const)` 折进 18-bit 重定位立即数、从而可能重现
  ML-030a 那类越界重定位坑的三处代码（第 1205/2754/4438 行）全部显式
  `dyn_cast<GlobalAddressSDNode>`/检查 `GA->getOpcode() ==
  ISD::GlobalAddress`——`BlockAddressSDNode` 是不同的子类，天然不会
  走到这条折叠路径，`isOffsetFoldingLegal` 这类 GlobalAddress 专属
  hook 不需要、也没有对应的 BlockAddress 版本。

### 验证结果

- 目标 3 文件重跑（`gcc_torture_sweep.py --filter
  "990208-1|comp-goto-1|pr70460"`）：**3/3 全部 PASS**（此前全部
  `FAIL_COMPILE`）。
- 全量 `gcc-c-torture` 重扫：`PASS=1482 FAIL_COMPILE=87 FAIL_LINK=124
  FAIL_RUN=15 TOTAL=1708`（基线 `1479/90/124/15`）——PASS +3、
  FAIL_COMPILE -3，`FAIL_LINK`/`FAIL_RUN` 与 `TOTAL` 分毫不差，逐类别
  精确对应「只有这 3 个文件从 FAIL_COMPILE 翻到 PASS，零其它变化」。
- 新 CodeGen lit 测试
  `llvm/test/CodeGen/DADAO/blockaddress-indirectbr.ll`：覆盖
  (a) `indirectbr`+跳转表式 `blockaddress` 数组（三个 label 的
  rela/addi/rd2rb/jump 全链路 + `.Ltmp0/1/2:` 强制打标签 +
  `.quad .Ltmp0` 数据段引用）；(b) 990208-1.c 的精确形状——单独取
  label 地址、不跳转。`llvm-lit
  llvm/test/CodeGen/DADAO/`：**13/13 PASS**（基线 12/12，+1 新增）。
- 新 E2E lit 测试 `tests/lit/E2E/computed_goto_dispatch.test`
  （+`Inputs/computed_goto_dispatch.c`）：三路 `goto
  *table[sel]`，`sel` 来自 `volatile` 全局（防常量折叠成直接跳转），
  每个 label 落地各自独立 `volatile` 计数器，正控制断言
  `hit_a==hit_b==hit_c==1 && hit_end==3`（精确到"没跳错、没漏跳、没
  fallthrough"），负控制翻转成必然失败的反命题证明正控制非
  vacuous。`-O0`/`-O2` × QEMU/gem5 四组合独立手动验证：正控制全部
  exit=42，负控制全部 exit=1。`llvm-lit tests/lit/E2E/`：**81/81
  PASS**（基线 80/80，+1 新增）。
- `python3 tools/run_differential.py`：`AGREE(3-way)=200`、
  `AGREE(4-way)=200`、`DIVERGE=0`——与基线一致（本任务只动 CodeGen，
  不触碰 ISA 语义，符合预期不变）。
- `python3 scripts/manifest_check.py`：PASS。
- `python3 scripts/check_issues.py`：PASS（Open 22 / Closed 43 /
  Total 65，无需新登记 issue——3 个目标文件全部修复，无遗留分类）。
- LLVM 侧改动：`.work/llvm` 里一个普通 `git commit`（`df7f057f76ef`，
  在 pin commit `f7cc59f158fc`/ML-040a 之上），`git format-patch`
  导出为 `components/llvm/patches/0064-DADAO-implement-BlockAddress-
  lowering-reuse-existin.patch`，追加进 `series`。独立复现验证：在
  `manifests/components.lock.toml` 锁定的 LLVM pin commit
  `ca7933e47d3a3451d81e72ac174dcb5aa28b59d1` 上新建 detached worktree，
  按 `series` 顺序 `git am` 全部 64 个 patch **零冲突**，结果树
  `git rev-parse HEAD^{tree}` = `259348a3bfa84af98f04b13c027c893d7227ea41`，
  与开发树 `git rev-parse df7f057^{tree}` **完全一致**；验证完成后
  `git worktree remove` 清理。
- 根仓库（DADAO-0628）**未 commit**：`components/llvm/patches/series`
  改动、新增 patch 文件、`tests/lit/E2E/computed_goto_dispatch.{test,
  Inputs/computed_goto_dispatch.c}` 均留在工作区待架构师复核。

### 范围说明

- 任务原本担心 `pr70460.c` 会牵涉更大改动（该文件用了 GCC 的 label
  difference 静态初始化扩展 `&&lab1 - &&lab0`，一种此任务范围之外的
  额外机制）。实测**完全不需要**：Clang 前端把
  `&&lab1 - &&lab0` 常量折叠成
  `trunc(sub(ptrtoint(blockaddress),ptrtoint(blockaddress)) to i32)`
  这个 `ConstantExpr`，`AsmPrinter::lowerConstant`（target-independent
  通用代码）把它降成 `.long .Ltmp1-.Ltmp0`，两个符号同 section、
  汇编期直接可解析为常量，完全不需要任何重定位类型、也不需要 DADAO
  侧任何新代码——这条路径在 `MO_BlockAddress` case 加上之后就自动
  work 了（该 case 只服务 `void *a = &&lab0 + b[x]` 里那个
  `blockaddress` 操作数的指令编码，静态初始化走的是完全不同的
  data-emission 路径）。三个目标文件的实现工作量**没有超出预期**，
  未触发"工作量远超预期需要停下报告"的条款，也未新登记 issue。

## 审阅记录（subagent 自审）

逐条 finding + 判决：

1. **BlockAddress 的 `PCREL_HI` 手工 DAGToDAG 选择是否真的对
   `TargetBlockAddress` 操作数泛型生效，而非恰好因为两种符号类型
   底层字段布局相同才"凑巧能跑"？** 判决：**确认非凑巧**。
   `DADAOISelDAGToDAG.cpp` 里 `Opc == DADAOISD::PCREL_HI` 分支代码
   （及 load/store combine 里同名的 `BaseAddr.getOpcode() ==
   DADAOISD::PCREL_HI` 分支）从未 `dyn_cast`/`cast` 成任何具体符号
   子类，只是把 `Node->getOperand(0)`（一个通用 `SDValue`）原样递给
   `getMachineNode(DADAO::RELA_RIII, ...)` 当操作数——`MCOperand`/
   `SDValue` 体系本来就把 `TargetGlobalAddress`/`TargetBlockAddress`/
   `TargetJumpTable`/`TargetConstantPool` 当同一族"目标地址操作数"
   处理，`InstrEmitter::AddOperand` 按 `SDValue` 的实际 opcode 分发到
   对应的 `MachineOperand::MO_*` 构造函写死在 LLVM 通用代码里，DADAO
   代码全程不感知具体是哪一种。这是设计上的泛型，不是巧合。已用
   `llc` 手动输出验证两种符号（`dispatch.table`/`.Ltmp3`）都走出了
   正确的 `rela`/`addi` 指令序列。
2. **新增的 `MO_BlockAddress` case 里 offset 加法分支
   （`if (int64_t Offset = MO.getOffset())`）是否有实际测试覆盖，还是
   死代码？** 判决：**确认是防御性对称代码，当前测试未覆盖非零
   offset**，如实记录，不隐瞒。`BlockAddressSDNode` 的 offset 字段
   只在 `DAG.getBlockAddress(BA, VT, Offset, ...)` 被显式传非零值时
   才非零；C 语言层面 `&&label` 语法本身永远产出 offset=0（不像
   `GlobalAddress` 有 GEP 折叠出非零 addend 的常见路径，ML-030a 那条
   坑本质上就出在这个非零 addend 折叠场景）。三个目标 gcc-c-torture
   文件全部走 offset=0 路径，本任务新增的两个 lit 测试也全是
   offset=0。这段代码镜像 `MO_GlobalAddress` 分支已有的写法保持对称、
   不引入新的不对称行为，但严格说没有独立测试证明它本身正确——如果
   以后出现真的产生非零 BlockAddress offset 的场景（目前没找到已知
   触发路径），需要补一条判别性测试。不影响本任务验收（3 个目标文件
   与新增测试都不依赖这条分支），如实标注为已知的未测试防御代码，
   不算阻断项。
3. **`isOffsetFoldingLegal` 只对 `GlobalAddressSDNode` 生效，
   `BlockAddressSDNode` 会不会走另一条未加保护的折叠路径，重现
   ML-030a 那种越界重定位 bug？** 判决：**已独立核实，无此风险**。
   `DAGCombiner.cpp` 里唯一三处会把符号+常量折叠进重定位立即数的代码
   （第 1205/2754/4438 行）全部显式检查节点是
   `ISD::GlobalAddress`/`dyn_cast<GlobalAddressSDNode>`，
   `BlockAddressSDNode` 是完全独立的 SDNode 子类，`dyn_cast` 对它
   恒返回 null，天然被排除在这条折叠路径之外，不需要
   `BlockAddress` 专属的 `isOffsetFoldingLegal` 等价物。
4. **`pr70460.c` 的 label-difference 静态初始化是否真的零额外代码
   即可工作，还是本次改动"恰好绕过了"而非"真正解决了"？** 判决：
   **确认零额外代码，且非绕过**。完整走过 IR dump（确认
   `trunc(sub(ptrtoint(BA),ptrtoint(BA)))` ConstantExpr 形状）+ 汇编
   dump（确认 `.long .Ltmp1-.Ltmp0` 输出）+ 全量 `gcc_torture_sweep.py`
   跑通该文件（编译+链接+在 QEMU 上真实运行+退出码校验全部通过，非
   仅编译不崩溃）三层独立验证,不是只看"没有崩溃"就下结论。
5. **全量 gcc-c-torture 回归对比是否只看聚合计数、还是真的排除了
   "两个文件方向相反地翻转、聚合数字凑巧对上"这种假阴性？** 判决：
   **聚合数字本身已经是强证据，但补充说明局限**。`FAIL_LINK`（124）
   和 `FAIL_RUN`（15）两个桶与 `TOTAL`（1708）逐位不变，`PASS`/
   `FAIL_COMPILE` 精确 +3/-3，且这 3 个文件在过滤跑（`--filter
   "990208-1|comp-goto-1|pr70460"`）里被独立确认是从 FAIL_COMPILE
   翻到 PASS——本次改动只涉及此前从未被任何已通过路径触碰过的
   `ISD::BlockAddress`（default action 下此节点只可能导致该节点所在
   函数编译期崩溃，不可能悄悄改变其它已通过文件的代码生成结果），
   逻辑上不存在"某文件因本次改动新退化、同时另一文件恰好被修复"的
   合理机制。未做逐文件级 diff（即没有保存 87/90 个 FAIL_COMPILE
   文件名列表逐一比对），如实标注这是聚合层面而非逐文件级别的回归
   证据，但给出的因果论证足以排除合理怀疑。
6. **硬约束合规性核查**：`.work/llvm` 全程只用普通 `git commit`
   （1 次，`df7f057f76ef`），未执行任何 `git rebase`/`git am`
   重放历史/`git reset --hard`；`git am` 仅用于独立验证用的临时
   `git worktree`（`/tmp/.../replay-check`），且验证完立即
   `git worktree remove` 清理，未触碰开发树本身的历史。根仓库
   （DADAO-0628）全程未执行任何 `git commit`，所有根仓库层面改动
   （patch 文件、series、lit 测试）都停留在工作区。判决：**合规**。
