# ML-038a：修复 `__int128` 返回值/调用结果的 CallingConv 分配崩溃

**执行环境**: 本地 subagent

## 硬约束（务必遵守，违反视为任务失败）

- **禁止**对 `.work/llvm` 做 `git rebase`/`git am` 重放整条历史/`git reset
  --hard`。只允许在当前 HEAD 基础上新增普通 `git commit`。
- **先诊断根因，再修复**——不要凭 `ML-035a` 报告里的错误信息猜测直接改代码，
  自己用 `-print-after-all`/IR dump 独立确认崩溃的确切触发点。
- **本任务范围只覆盖 `__int128`，不覆盖向量类型**（`ML-035a` 报告指出向量
  和 `__int128` 共享同一个 CC 分配崩溃点，但向量类型还有一个额外的、独立的
  `SetCC` 断言崩溃前置问题，本任务不处理——如果诊断中发现修复 `__int128`
  这条路径顺带也让某个向量文件真的编译通过，如实记录，但不要因此扩大任务
  范围去处理向量类型专属的问题）。
- **完成后立即导出 patch**（不要延后），追加进对应 `series`。
- 完成后必须在任务文件里写「完成区」+ subagent 自审「审阅记录」（含逐条 finding
  + 判决）。

## 背景

`ML-035a`（`docs/reviews/ML-035a-gcc-torture-gap-rescan-2026-07-24.md` §1.2
(b)(c)）确认：`__int128` 触发的 6 个 gcc-c-torture 文件（`pr54471.c`,
`pr85582-2.c`, `pr85582-3.c`, `pr49218.c`, `pr84748.c`, `pr84169.c`）全部
在编译期崩溃于同一类"128 位宽返回值 CallingConv 分配失败"问题，具体是两个
不同的崩溃点：

```
# (b) 7 个文件里的 3 个 __int128 文件：
<fatal error>: unable to allocate function return #1
```

```
# (c) 4 个文件里的 3 个 __int128 文件：
llvm/lib/CodeGen/CallingConvLower.cpp:174: UNREACHABLE executed
（llvm::CCState::AnalyzeCallResult 内）
```

这是 `ML-026a`（PASS=1328 基线）时就已经存在、`ML-027a`~`ML-034a` 均未触碰的
FAIL_COMPILE 真实候选缺陷，`ML-035a` 重新确认逐文件完全一致（零进展也零新
发现，代表这条路径需要专门任务才能推进）。

DADAO 是 64 位宽寄存器架构（RD bank），`__int128` 需要跨两个 64 位寄存器
（高/低半区）传递返回值——目前后端的 `CC_DADAO`/`RetCC_DADAO`（或等价的
CallingConv 分配逻辑）显然没有为 128 位宽标量值实现"拆成两个寄存器"这条路径，
遇到时直接崩溃而非静默错误（这点和聚合体的情况不同——`ML-031a` 已经实现了
聚合体的多寄存器拆分，但 `__int128` 是标量类型，走的是不同的分类代码路径，
可能完全没有复用 `ML-031a` 那套逻辑）。

## 目标

1. **根因诊断**：确认这 6 个文件具体在哪个 `TargetLowering`/`CallingConv`
   相关函数崩溃（`LowerReturn`/`LowerCallResult`/`RetCC_DADAO`/`CC_DADAO`
   或 `TargetLowering::LowerCallTo` 的返回值处理路径），弄清楚当前代码对
   128 位宽标量返回值到底是完全没处理，还是有处理但逻辑有 bug。
2. **修复**：让 `__int128` 函数返回值（以及如果诊断发现调用点传参也有同类
   缺口，视情况一并处理，但**不要主动扩大范围**去处理向量类型）能正确拆分
   到两个 64 位寄存器（RD bank，参照 wiki/`contracts/abi/spec.md` 里
   "标量参数拆分"相关规则，如果 `__int128` 没有被 wiki 明确覆盖，按现有
   `long`/`long long` 的既定寄存器分配惯例做最合理的扩展，并在完成区里说明
   依据）。
3. **判别性验证**：不能只靠这 6 个 torture 文件通过，需要独立构造 CodeGen
   lit 测试覆盖：`__int128` 作为返回值（含边界值：全 0、全 1、只有高位/
   低位非零、符号扩展相关的负数）、`__int128` 作为函数调用的返回值被
   调用方消费（对应 `AnalyzeCallResult` 那条崩溃路径）。

## 验收

- 独立、判别性的 CodeGen lit 测试（`llvm/test/CodeGen/DADAO/`），FileCheck
  断言生成的寄存器分配/返回序列正确（高低 64 位分别对应正确的输入值）。
- 独立、判别性的项目 E2E 测试（`tests/lit/E2E/`），用 `volatile` 输入 +
  正负控制，覆盖至少一个真实的 `__int128` 返回值+调用点消费的端到端场景，
  QEMU+gem5 双后端跑通。
- 6 个目标 torture 文件用 `python3 tests/scripts/gcc_torture_sweep.py
  --filter "pr54471|pr85582-2|pr85582-3|pr49218|pr84748|pr84169"` 重跑，
  如实报告有几个变绿（不强行要求全部 6 个——如果诊断中发现某个文件还牵涉
  本任务未覆盖的其它问题，如实报告）。
- 全量 `gcc-c-torture` 重扫（当前基线 `1465/104/124/15`），逐文件 diff
  确认零回归。
- 全量 `llvm-lit tests/lit/E2E/`（当前基线 78/78）：零回归。
- `python3 tools/run_differential.py`：AGREE 数与当前基线一致、DIVERGE=0。
- `python3 scripts/manifest_check.py`/`check_issues.py` 通过。
- LLVM 侧改动用**普通** `git commit` 落地，`git format-patch` 导出对应
  patch，追加进 `series`；独立验证可在干净 pin-commit checkout 上 `git am`
  成功，且 replay tree 与开发树 tree hash 一致。
- 如果诊断后发现这个修复的合理工作量远超预期（比如发现需要先做一个更大的
  "任意宽标量类型跨寄存器传递"通用框架），如实停下报告，不要为了"看起来
  完整"而勉强拼一个只覆盖这 6 个文件的特例补丁。

## 参考指针

- `docs/reviews/ML-035a-gcc-torture-gap-rescan-2026-07-24.md` §1.2(b)(c)
  （本任务对应的发现原文，含精确的崩溃点和文件分组）
- `.work/source/llvm-test-suite/SingleSource/Regression/C/gcc-c-torture/execute/
  {pr54471,pr85582-2,pr85582-3,pr49218,pr84748,pr84169}.c`（原始复现源码）
- `.work/llvm/llvm/lib/Target/DADAO/DADAOISelLowering.cpp`（`LowerReturn`/
  `LowerCallResult`/`CC_DADAO`/`RetCC_DADAO` 相关逻辑）
- `.work/llvm/llvm/lib/CodeGen/CallingConvLower.cpp:174`（`AnalyzeCallResult`
  UNREACHABLE 崩溃点，读这里的上下文理解触发条件）
- `code-agent/tasks/ML-031a-aggregate-struct-abi-parameter-passing.md`
  完成区（聚合体的多寄存器拆分实现，`__int128` 如果需要类似的"跨寄存器"
  处理可以参考其设计，但 `__int128` 是标量不是聚合体，具体机制大概率不同，
  需要自己诊断确认，不要想当然直接照抄）
- `contracts/abi/spec.md`（标量参数寄存器分配规则，如果 wiki/spec 对
  128 位标量类型没有明确覆盖，如实记录这个空白并按现有规则做最合理扩展）

## 完成区

### 根因诊断（独立复现，非凭错误信息猜测）

用真实 `-c` 编译 + 完整 backtrace 独立复现了两个崩溃点（未采信 `ML-035a`
报告文字，自己重新确认）：

- `pr54471.c`（`return irslt;`）→ `DADAOTargetLowering::LowerReturn` →
  `CCState::AnalyzeReturn` → `report_fatal_error("unable to allocate
  function return #1")`，`CallingConvLower.cpp:120`。Index `#1` 即第二个
  `Outs` 条目分配失败。
- `pr49218.c`（`main` 调用返回 `__int128` 的路径）→
  `DADAOTargetLowering::LowerCall` → `CCState::AnalyzeCallResult` →
  `llvm_unreachable`，`CallingConvLower.cpp:174`。

根因：`__int128` 比 DADAO 唯一的合法整数类型 `i64` 宽，target-independent
type legalization（`TargetLoweringBase::computeRegisterProperties`，不需要
DADAO 侧任何 opt-in）自动把它拆成两个 `i64` SelectionDAG 值——用
`clang -S -emit-llvm` 确认 IR 层是单一 `i128`，说明拆分发生在 SelectionDAG
构建阶段而非 clang CodeGen。`RetCC_DADAO` 的 `i64` 规则只有一个寄存器
（`rd31`），第二个值无处可去。

### 修复

**`DADAOCallingConv.td`**：`RetCC_DADAO` 的 `i64` 规则从
`CCAssignToReg<[RD31]>` 改为 `CCAssignToReg<[RD31, RD30]>`（`rd31` 在前）。

第一次尝试 `CCAssignToReg<[RD30, RD31]>`（`rd30` 在前）是**错的**，构成一次
真实回归：`CCAssignToReg` 底层 `CCState::AllocateReg` 从列表头开始顺序尝试，
不知道"是否还有第二个值要来"，导致每一个普通单值 `i64` 返回都会静默从
`rd31` 改配到 `rd30`——这不是靠代码审查发现的，是重新构建二进制、重跑全量
`CodeGen/DADAO` lit 后，2 个既有测试（`dynamic-stackalloc.ll`、
`varargs-save-area.ll`）真的挂了才抓到的。改成 `rd31` 在前后：单值返回仍然
拿到 `rd31`（ABI 不变，`contracts/abi/spec.md` §3.1），`__int128` 拆成的两个
值第一个（高 64 位，见下）落在 `rd31`，第二个（低 64 位）落在 `rd30`。

高低位顺序独立确认（读 `SelectionDAGBuilder.cpp` 源码，不是从"DADAO 取指
big-endian"这个无关的既有结论去推断）：`getCopyToParts`/`getCopyFromParts`
在 `DataLayout::isBigEndian()`（DADAO 是，`clang/lib/Basic/Targets/DADAO.h`
`resetDataLayout("E-...")`）为真时，把高 64 位排在第一个 part、低 64 位排
第二个。`CCAssignToReg` 按收到 `Outs`/`Ins` 的顺序从左到右分配寄存器列表，
因此 `rd31` 在前 → 高位落 `rd31`。用真实 `llc -mtriple=dadao` 汇编输出核实
（见下方 CodeGen lit 测试），非纸面推导。

**`DADAOISelLowering.cpp`**：`LowerCall` 里 `AnalyzeCallResult` 循环存在
第二个独立 bug——每次 `DAG.getCopyFromReg` 都复用同一个 `Glue` SDValue，没有
`Glue = Copy.getValue(2)` 串联到下一次调用。`Glue` 类型的 SDValue 只能有一个
消费者，`RVLocs.size() > 1` 时两个 `CopyFromReg` 节点共享同一个 glue 生产者
就会让调度器把同一个 SDNode 插入两次，崩在
`ScheduleDAGSDNodes::BuildSchedUnits`（`"Node already inserted!"`）。这个 bug
在本任务之前从未被触发过（返回值 CC 规则历来只产生 1 个 `RVLoc`），是修完
`RetCC_DADAO` 重新编译后才现出来的真实回归，按 `LanaiISelLowering.cpp`
`LowerCallResult` 的参照写法补上链式 `Glue` 更新修复。

**范围纪律**：没有碰向量类型。全量重扫发现 `20050316-1.c`/`20050316-3.c`
（向量返回值文件）作为副作用顺带编译通过——共享同一个
`RetCC_DADAO` 寄存器耗尽崩溃点，但走的是不同的 `Outs` 拆分路径——如实记录，
未借此扩大范围去处理向量类型专属问题（`SetCC` 断言等）。

### 判别性测试

- **CodeGen lit**：新增 `llvm/test/CodeGen/DADAO/i128-return-value.ll`，覆盖
  全 0、全 1、只有高位非零（`2^64`）、只有低位非零（`0x12345678`）、负数
  （`-0x12345678`，验证高位物化为全 1 而非截断/留零）、参数→返回值原样传递
  的往返（验证参数拆分 `rd16`=高/`rd17`=低 与返回拆分 `rd31`=高/`rd30`=低
  相互一致）、从 `i32` 符号扩展到 `i128`（验证高位来自低位符号位而非调用方
  不存在的高 32 位）、`AnalyzeCallResult` 路径（`consume_call_result` 消费
  另一函数的 `__int128` 返回值）。`CodeGen/DADAO` 全量 lit：**11/11**；
  `MC/DADAO`：**2/2**；两者均零回归。
- **项目 E2E lit**：新增 `tests/lit/E2E/i128_return_call.test` +
  `Inputs/i128_return_call.c`——`volatile` 全局输入（防 `-O2` 常量折叠掉整个
  计算），一个 `__int128` 返回值函数 + 调用点消费（覆盖 `LowerReturn` 和
  `AnalyzeCallResult` 两条路径）+ 一个真实负数的符号扩展验证，`-O0`/`-O2`
  两档 + `-DNEGATIVE_CONTROL` 负控制（故意错配期望值，验证正向断言不是
  空洞为真），QEMU + gem5 双后端均跑通。`tests/lit/E2E` 全量：**79/79**
  （原 78 + 新增 1），零回归。

### 验收结果

- 目标 6 文件（`--filter "pr54471|pr85582-2|pr85582-3|pr49218|pr84748|
  pr84169"`）：**4/6 PASS**（`pr54471.c`/`pr85582-2.c`/`pr85582-3.c`/
  `pr84169.c`）。**2/6 FAIL_LINK**（`pr49218.c` 缺 `__fixsfti`——`float`→
  `__int128` 转换 libcall；`pr84748.c` 缺 `__udivti3`——无符号 128 位除法
  libcall）：编译期崩溃已消失，暴露出的是一类不同、本任务范围外的问题
  （128 位算术/浮点转换运行时符号缺失，与调用约定无关，类似 ML-022a/
  ML-028a 的软浮点符号缺口模式），如实报告未处理。
- 全量 `gcc-c-torture`（1708 文件）**逐文件 diff**（不只看聚合数字）：用
  `git stash` 暂存改动、重新构建出修复前的二进制、跑一次全量扫描存档为
  真实修复前基线（`PASS=1465/FAIL_COMPILE=104/FAIL_LINK=124/FAIL_RUN=15`，
  与任务下发时给出的基线数字精确一致），`git stash pop` 恢复改动、重新
  构建、再跑一次全量扫描（`PASS=1471/FAIL_COMPILE=96/FAIL_LINK=126/
  FAIL_RUN=15`），逐文件比较状态：**8 个文件变化，0 个回归**（无
  `PASS`→非`PASS`）——4 个目标文件转 `PASS`、2 个目标文件转
  `FAIL_COMPILE`→`FAIL_LINK`（如上）、2 个向量文件（`20050316-1.c`/
  `20050316-3.c`）作为副作用转 `PASS`。
- `python3 tools/run_differential.py`：`AGREE(3-way)=200 DIVERGE=0`、
  `AGREE(4-way,Sail)=200 SAIL-DIVERGE=0`——与基线一致（本任务不改指令语义，
  预期不变）。
- `python3 scripts/manifest_check.py`：PASS。
- `python3 scripts/check_issues.py`：PASS（Open 21 / Closed 42 / Total 63，
  未新增/未关闭任何 issue）。
- `python3 scripts/check_codegen_abi.py`：**主动运行**（按项目 memory
  feedback「ABI 文档 vs 后端实现分歧盲区」的教训，凡碰 CallingConv 的任务
  应主动跑这个工具，不能只验证"手写代码自洽"）——第一次跑出
  `MISMATCH`：`tools/abi.yaml` 里 `returns.integer.register: rd31` 还是
  单寄存器契约，我的改动让后端多了 `rd30`，机器可读契约没跟上。见下方
  「ABI 文档更新」。

### ABI 文档更新（根仓库改动，未 commit）

- `contracts/abi/spec.md` §3.1：新增"128-bit scalar return"小节，
  `[M1 architecture decision, ML-038a]` 标注（沿用 §3.1 既有的
  `[M1 architecture decision: ...]` 括注写法），明确记录：wiki 对 128 位
  标量类型完全没有 ABI 契约（不只是这次涉及的寄存器分配，`docs/issues.yaml`
  `dadao-frame-lowering-8byte-align-insufficient-for-16byte-locals` 记录的
  是另一个不相关的、已永久排除的"局部变量 spill slot 对齐"缺口）；明确
  声明这**不是**在实现 §3.2"多返回值"（那条 wiki 规则覆盖的是真正独立的多
  个返回值，有一个未解决的声明顺序歧义，被排除出 M1——本任务拆分的是
  单个 128 位值，走一条无歧义的机械规则，两者互不依赖）；记录高低位→
  寄存器映射的推导依据（big-endian part 顺序 + `CCAssignToReg` 分配顺序），
  并指出这与参数传递侧"高位在低编号寄存器"刚好相反（谁先被尝试分配而已，
  不是对"哪半是高位"有分歧）。
- `tools/abi.yaml`：`returns.integer.register: rd31`（标量字符串）→
  `returns.integer.registers: [rd31, rd30]`（列表，与
  `arguments.integer.registers` 已有的列表 schema 对齐），并加注释指向
  `contracts/abi/spec.md` §3.1。
- `scripts/check_codegen_abi.py`：整数返回值比对分支从硬编码
  `[abi["returns"]["integer"]["register"].lower()]` 改为复用既有的
  `expand_range()`（本来就同时支持 list 和 `"rdX-rdY"` 字符串两种 schema），
  同步更新文件头部注释里的字段名（`returns.integer.register` →
  `returns.integer.registers`）。
- 修完后重跑：`MATCH=23 OPEN-COMMIT=3 INFO=2 MISMATCH=0`，`RESULT: PASS`
  （之前是 `MISMATCH=1`）。`OPEN-COMMIT`/`INFO` 均为改动前已存在项，与本任务
  无关（如 datalayout 字符串里 `i128:128` token 的 INFO，`clang/lib/Basic/
  Targets/DADAO.h` 里本来就有，本任务未碰这个文件）。
- 以上 3 个文件 + `components/llvm/patches/series`（新增第 62 条）均为
  **根仓库层面改动，未 `git commit`**，留给架构师复核；`gcc-torture-
  results.json` 是脚本运行产生的既有 untracked 产物，未特殊处理。

### LLVM 侧提交与 patch

- `.work/llvm`（独立 git 仓库）：确认 `git status` 干净后开始改动；全程
  只用 `git stash`/`git stash pop`（纯工作区操作，不改写任何历史，用来临时
  切回"改动前"二进制以获得真实的修复前 torture 基线做逐文件 diff）+ 一次
  普通 `git commit`（`be30d543202b`，`HEAD` 之上新增，无 rebase/am 重放/
  reset --hard）。
- 已 `git format-patch` 导出并落地
  `components/llvm/patches/0062-DADAO-split-__int128-return-values-across-rd31-rd30.patch`，
  追加进 `components/llvm/patches/series`（第 62 行）。
- **裸 pin 重放验证**：`git worktree add --detach` 到 manifest 锁定的 pin
  commit（`ca7933e47d3a3451d81e72ac174dcb5aa28b59d1`），对全部 62 个 patch
  按 series 顺序 `git am`，**全部应用成功，零冲突**；重放后的 tree hash
  （`3a51302b49870abae520baf8cfbd2519329f1e83`）与当前开发树 `HEAD^{tree}`
  **完全一致**。已 `git worktree remove` 清理临时 worktree。

## 审阅记录（自审，非嵌套 subagent）

| # | Finding | 判决 |
|---|---------|------|
| 1 | 首次尝试 `[RD30, RD31]` 会静默劫持所有既有单值 `i64` 返回的 `rd31`→`rd30`，属于会破坏现有 ABI 的严重回归 | **真实问题，已在最终版本修复**（改列表顺序为 `[RD31, RD30]`），并保留在完成区如实说明"第一次尝试是错的"这一过程，不隐藏走过的弯路 |
| 2 | `LowerCall` 的 `AnalyzeCallResult` 循环里 `Glue` 未串联更新，`RVLocs.size()>1` 时会让调度器崩溃 | **真实的独立既有 bug**（本任务之前从未被触发），已修复并在 patch/commit message 中明确记为"第二个独立发现的 bug"，不算在"__int128 CC 分配"这一条根因里蒙混过关 |
| 3 | 高低位→寄存器映射（`rd31`=高/`rd30`=低）是否有真实依据，还是拍脑袋 | 依据可验证：读了 `SelectionDAGBuilder.cpp` 的 `getCopyToParts`/`getCopyFromParts` 源码（非从"取指 big-endian"这个无关结论套用），并用真实 `llc` 输出核实了 `identity(i128)`/`ret_sext_from_i32` 等测试用例的寄存器排布，非纸面推导 |
| 4 | 是否误把这次改动等同于实现 wiki §3.2"多返回值"（该条款因声明顺序歧义被排除出 M1） | 已在 `DADAOCallingConv.td` 注释与 `contracts/abi/spec.md` 两处明确划清界限：本任务拆分单个 128 位值，走机械无歧义规则；§3.2 覆盖真正独立的多个返回值，其歧义未解决、仍被排除，两者不互相依赖，本任务未解决也未依赖那条开放问题 |
| 5 | 6 个目标文件里 2 个仍不过（`pr49218.c`/`pr84748.c`），是否该顺手把 `__fixsfti`/`__udivti3` 也补上凑够"6/6" | **判定为任务边界外**，未处理：这是运行时算术 libcall 缺失（另一类问题），任务验收条款本身明确允许"不强行要求全部 6 个"，如实报告缺口原因（缺哪个符号、对应哪行源码），未为了好看的数字扩大范围 |
| 6 | 全量回归验证是否只看聚合数字（"PASS 数变多了就行"），可能掩盖同时发生的隐藏回归 | 未止步于聚合数字：用 `git stash`/重新构建拿到修复前的真实二进制，重跑全量 1708 文件存档，与修复后逐文件比对状态变化，确认零 `PASS`→非`PASS` 回归，而不是只信任"净增 6 个 PASS"这类会掩盖"部分回归+更多新增"的聚合读数 |
| 7 | 是否遗漏了 ABI 文档层面的一致性（wiki/spec 文字 vs 机器可读 `tools/abi.yaml` vs 后端实际实现三者是否一致） | 主动运行 `scripts/check_codegen_abi.py`（按项目 memory 里"ABI 文档 vs 后端实现分歧盲区"的既有教训），抓到真实 `MISMATCH`（机器可读契约文件滞后于本次改动），已同步更新 `contracts/abi/spec.md`/`tools/abi.yaml`/`check_codegen_abi.py` 三处，复跑确认 `MISMATCH=0` |
| 8 | 向量文件（`20050316-1.c`/`20050316-3.c`）意外转绿，是否应该顺手扩大范围验证/修复向量类型 | 未扩大范围：如实记录这是同一崩溃点的副作用，明确指出向量类型还有独立的 `SetCC` 合法化缺口（任务文件已预先排除），未做任何针对向量类型的改动或验证 |
| 9 | `.work/llvm` 是否违反"禁止 rebase/am 重放历史/reset --hard"的硬约束 | 未违反：全程只用 `git stash`/`git stash pop`（工作区操作，不触碰任何 commit/历史）+ 一次在当前 `HEAD` 之上的普通 `git commit`；裸 pin 重放验证用的是**一次性临时 worktree**（`git worktree add --detach` + `git am` 到全新签出的 pin commit，随后 `git worktree remove`），完全不触碰 `.work/llvm` 主目录的历史 |
| 10 | 根仓库层面的改动（`contracts/abi/spec.md`/`tools/abi.yaml`/`scripts/check_codegen_abi.py`/`components/llvm/patches/series`）是否误 commit 到根仓库 | 未 commit：`git status` 确认全部改动停留在工作区（`Modified`/`Untracked`），未对根仓库执行任何 `git commit`，留给架构师复核 |
