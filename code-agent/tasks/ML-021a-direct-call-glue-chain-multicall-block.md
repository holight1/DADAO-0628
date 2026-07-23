# ML-021a: 修复"同一基本块内 ≥2 个直接 CALL"的 glue 链拓扑缺陷（roadmap B 阻断项，高风险深挖任务）

**执行环境**: 本地 subagent

**状态**: 已完成

## 硬约束（务必遵守，违反视为任务失败）

- **禁止**对 `.work/llvm` 做 `git rebase`/`git am` 重放整条历史/`git reset --hard` 到早于
  当前 HEAD 的操作。只允许在当前 HEAD 基础上新增普通 `git commit`。
- **这是第三次尝试同一类 SelectionDAG glue 链问题**（见下方「前情提要」）。前两次
  （DL-063b/c，间接调用场景）磨了 3 轮，最终 deferred，WIP 被 stash 且从未真正解决
  （后来这个具体的间接调用问题被**另一次不同的改动**用 `Pat<>` 方式解决，细节见下）。
  **如果本任务诊断到一定程度判断需要的改动量/风险超出单任务合理范围，允许停下来如实
  报告诊断结果+根因假设，不要为了"完成任务"硬着头皮上一个低把握度的修复。** 这比强行
  提交一个可能引入新回归的补丁更有价值。
- **在写任何修复代码之前，先用 SelectionDAG 调试输出（`llc -debug` 或
  `-print-after-all`/`-view-sched-dags`-类机制，具体用哪个以 LLVM 当前版本实际支持的
  为准）把两个 CALL 节点的 glue 链拓扑真正打印出来看清楚，而不是凭代码走读猜测**——
  ML-020a 的诊断已经用 gdb 定位到断言点，但没有做完整的 DAG 转储分析，本任务要把这
  一步补上再动手改。
- **完成后立即导出 patch**（不要延后）：`components/llvm/patches/0048-...patch`，
  追加进 `series`。这是本项目上一轮审计暴露的纪律缺口，本任务不得重蹈。
- 完成后必须在任务文件里写「完成区」+ subagent 自审「审阅记录」（含逐条 finding + 判决）。

## 前情提要（必读，避免重复踩坑）

### 第一次尝试：DL-063b/c（2026-07-12，间接调用场景，deferred 未解）

`code-agent/tasks/DL-063c-debug-indirect-call-scheduler.md` 记录：**间接调用**
（函数指针 `%fp()`）在调度阶段撞
`SelectionDAGNodes.h:1116 Assertion 'ResNo < NumValues && "Illegal result number!"'`
——与本任务要修的断言**完全相同**。DS 磨了 3 轮（尝试去掉 isPseudo、嵌入 Pattern、
显式 SDT profile 均未解），Codex review 判定 Needs Revision，最终决策 C：deferred，
WIP `git stash`，转做 clang 里程碑优先。

**重要：这个具体的间接调用问题现在已经不存在了**——架构师已确认当前
`.work/llvm/llvm/lib/Target/DADAO/DADAOInstrInfo.td` 里 `CALL_PSEUDO_INDIRECT`
（注意不是 DL-063c 描述的 `CALL_INDIRECT_PSEUDO`，命名不同，是后来某次改动重新实现的）
**已经是 `Pat<>`-based**：
```
def CALL_PSEUDO_INDIRECT : InstDADAO<(outs), (ins GPRD:$reg), "", []>;
def : Pat<(DADAOcall GPRD:$reg), (CALL_PSEUDO_INDIRECT GPRD:$reg)>;
```
即 DL-063c 报告里"推荐路线：换 pattern-based 选择"这个方向**后来确实被采纳并且成功
落地了**——只是不知道是哪个任务做的（不在 DL-063 系列任何一个任务文件里，可能是
DL-065a/ML-004c 之类后续任务顺手做的，本任务不需要考古是谁做的，只需要知道这个具体
问题已解决）。E2E 现有间接调用相关测试（如有）应该已经覆盖这条路径且通过，本任务
**不要在间接调用路径上花时间**。

### 第二次尝试：ML-020a（2026-07-22，直接调用/libcall 场景，本任务的直接前置）

`code-agent/tasks/ML-020a-f64-softfloat-libcall-vfprintf.md` 完成区记录：给 DADAO
注册 f64 软浮点 RTLIB libcall 名字后（`components/llvm/patches/0047-...patch`），
musl 里大量浮点相关文件第一次真正走到指令选择/调度阶段，**撞上同一个
`Illegal result number`/`Node already inserted` 断言**——但触发场景不是间接调用，
是**同一个基本块内出现 ≥2 个独立的、由 `TargetLowering::makeLibCall` 发起的直接
（外部符号）CALL**。架构师已独立构造并复现最小案例（不依赖 musl）：

```c
double cmp(double a, double b) { return (a >= b) + (a == 0); }
```

`clang --target=dadao -O1`（`-O0` 不复现，`-O1`/`-O2`/`-O3` 均复现）编译崩溃，
gdb 定位：某个读取第二个 `makeLibCall`（本例 `__gedf2`）返回值的 `CopyFromReg` 节点，
其 Glue 操作数错误地指向了一个只有 1 个结果值（`i64` only）的 `ADDI_RRII`
（materialize-constant）节点的 `ResNo=1`。也就是说：**当一个基本块里有第二个（或
更多）独立的直接 CALL 时，某个跟 CALL 无关的普通指令节点的编号/glue 被错误关联进了
调用序列**。

`docs/issues.yaml` 的 `musl-backend-assert-illegal-result-number`（当前 15 个触发
对象）和 `musl-backend-assert-node-already-inserted`（当前 88 个触发对象）两条 issue
已记录本次深挖的完整触发文件清单与初步根因分析，可以直接读，不用重新收集样本。

### 关键线索（架构师本次新增的诊断，供你继续深挖）

对比当前 `DADAOISelDAGToDAG.cpp` 里 `Opc == DADAOISD::CALL` 分支：**直接调用
（`CALL_IIII`，callee 是 `TargetGlobalAddress`/`TargetExternalSymbol`）走的是纯手工
`CurDAG->getMachineNode(DADAO::CALL_IIII, DLC, MVT::Other, MVT::Glue, DirectOps)`**
（`DADAOInstrInfo.td` 里 `CALL_IIII` 的 `Pattern` 是空 `[]`，完全不靠 tablegen 匹配）
——**跟已经工作正常的 `CALL_PSEUDO_INDIRECT` 形成鲜明对比**：后者是 `Pat<>`-based，
前者不是。DL-063c 报告里"手动建节点的 glue/result 结构最易在调度器出错，应该换
pattern-based 选择"这个诊断，很可能同样适用于直接调用路径——只是当时只对间接调用
做了转换，直接调用路径的手工建节点方式一直留着，只是"单个基本块最多 1 个直接 CALL"
的场景下从未暴露过问题（这也是为什么 ML-020a 之前从未被察觉——之前 DADAO 编译的代码
几乎不产生连续两次直接 libcall）。

## 目标

1. 用架构师给出的两行 C 最小复现（或更简的、你自己构造的、不依赖 musl 的 `.ll` IR
   直接喂给 `llc`，绕开 clang 前端）先复现问题，用 SelectionDAG 调试转储确认到底是
   哪个节点、在哪个 pass（DAGToDAG selection 还是之后的 scheduler `BuildSchedUnits`）
   把 glue/result 编号关联错了——不要只看 gdb 栈，要看真正的 DAG/MIR 转储。
2. 判断根因是否与"直接调用路径仍是手工 `getMachineNode` 而非 `Pat<>`-based"这个假设
   相符。如果相符，参照 `CALL_PSEUDO_INDIRECT` 已经工作的模式，把直接调用路径也转成
   `Pat<>`-based（注意直接调用比间接调用复杂：`LowerCall` 会给直接调用节点动态附加
   变长的实参寄存器 `RegisterSDNode` 列表 + `RegisterMaskSDNode`，`CALL_PSEUDO_INDIRECT`
   的 `Pat<(DADAOcall GPRD:$reg), (CALL_PSEUDO_INDIRECT GPRD:$reg)>` 看起来只匹配了
   固定的 1 个操作数——搞清楚这些变长附加操作数在间接调用路径里是怎么"透传"到最终
   机器指令上的（`SDNPVariadic`？`variable_ops`？），直接调用路径要用同样的机制而不是
   凭空设计一套新的）。
3. 如果诊断后发现根因**不是**"手工建节点 vs pattern-based"这个假设（比如实际是
   `LowerCall` 里 Chain/Glue 线程化本身的 bug，架构师读过 `LowerCall` 代码本身看起来
   是标准写法，跟 RISC-V 参考实现结构一致，没有明显问题，但不排除某个细节问题），
   如实调整诊断方向，不要削足适履地往"改成 pattern-based"这一个方向硬套。
4. 落地修复后，用**架构师给出的两行复现**+ **至少一个不含浮点、纯粹"同一基本块 2 个
   连续直接函数调用"的普通 C 测试**（比如 `int f(void){ return g() + h(); }`，
   `g`/`h` 是两个不同的外部函数，不涉及 libcall）分别验证，确认这是通用的"直接调用
   路径"修复，不是只对 libcall 场景的特殊打补丁。

## 验收

- 架构师给出的两行浮点比较最小复现：`clang --target=dadao -O1 -c` 编译通过，不再
  crash。
- 新增的"同一基本块 2 个连续直接调用"最小复现（非浮点）：编译通过且反汇编/双后端
  运行结果正确（两个调用的返回值都被正确使用，不是巧合正确）。
- `vfprintf.o` 用 musl 真实构建标志（`cd .work/build/musl && make -j1
  obj/src/stdio/vfprintf.o`）重新编译：报告实际结果（编译通过是最理想情况；如果
  还有其它独立问题挡着也要如实说明，不要跳过验证直接假设"修好了"）。
- musl 全量 fresh 编译：重新统计失败矩阵（不要用旧数字），报告
  `musl-backend-assert-illegal-result-number`/`musl-backend-assert-node-already-
  inserted` 两个簇缩小了多少、具体哪些对象转为成功。
- 全量 `llvm-lit tests/lit/E2E/`：零回归（当前基线 60/60，落地前重新跑一次记录当前
  值为准），**尤其要确认间接调用相关的既有测试没有被本次改动带崩**（本任务不改
  `CALL_PSEUDO_INDIRECT`，但如果诊断发现两条路径共享某些底层机制，要额外小心）。
- `python3 tools/run_differential.py`：AGREE 数与当前基线一致、DIVERGE=0。
- `python3 scripts/manifest_check.py`/`check_issues.py` 通过。
- LLVM 侧改动用**普通** `git commit` 落地，`git format-patch` 导出为
  `components/llvm/patches/0048-....patch`，追加进 `series`；独立验证可在干净
  pin-commit checkout 上 `git am` 成功。
- 更新 `docs/issues.yaml` 对应两条 issue 的状态（如彻底解决，按项目惯例把条目搬去
  `docs/issues-archive.yaml`；如部分解决，如实更新触发对象清单）。
- **如果诊断后判断这个改动量/风险超出单任务合理范围**：允许在这一步停下，把诊断
  结果（DAG 转储证据、根因假设、你认为需要多大改动）写清楚交给架构师判断，不算
  任务失败，是诚实的范围边界判断——参照 ML-020a 选项 B 的先例。

## 参考指针

- `code-agent/tasks/DL-063b-codegen-indirect-call.md`、
  `code-agent/tasks/DL-063c-debug-indirect-call-scheduler.md`（第一次尝试的完整
  历史、已排除的假设、Codex review 的详细 finding——不要重复已经排除过的假设）
- `code-agent/tasks/ML-020a-f64-softfloat-libcall-vfprintf.md` 完成区（本任务的
  直接前置，包含 gdb 定位细节）
- `.work/llvm/llvm/lib/Target/DADAO/DADAOISelDAGToDAG.cpp`（`Opc == DADAOISD::CALL`
  分支，直接调用手工 `getMachineNode` 的位置）
- `.work/llvm/llvm/lib/Target/DADAO/DADAOISelLowering.cpp`（`LowerCall`，Chain/Glue
  线程化逻辑，架构师读过认为结构上跟标准写法一致，但不排除细节问题）
- `.work/llvm/llvm/lib/Target/DADAO/DADAOInstrInfo.td`（`CALL_IIII`/`CALL_RRII`
  `Pattern=[]` 对比 `CALL_PSEUDO_INDIRECT` 的 `Pat<>`；`DADAOcall` SDNode 定义
  的 `SDNPVariadic`/`SDNPOutGlue` 等 flag）
- `.work/llvm/llvm/lib/Target/RISCV/RISCVInstrInfo.td`（`PseudoCALL` 一类
  pattern-based call 选择的标准参照，DL-063c 已指出的对标对象）
- `docs/issues.yaml`：`musl-backend-assert-illegal-result-number`、
  `musl-backend-assert-node-already-inserted`（完整触发对象清单+两次独立根因分析）
- `.work/build/musl/`（`make -j1 obj/src/stdio/vfprintf.o` 复现命令）

## 完成区

**状态**：已完成

**根因（与任务假设不同，已用 DAG 转储验证，非猜测）**：

任务假设 H1（"CALL_IIII 手工 `getMachineNode` vs `Pat<>`"）**被证伪**——
`DADAOInstrInfo.td` 里 `CALL_PSEUDO_INDIRECT` 的注释（本任务过程中读到）显示
这条路线**此前已被独立试过**：给 `DADAOcall`/`CALL_IIII` 写 `Pat<>` 同样撞
**同一个** `BuildSchedUnits` 断言，并非因为"没试过 pattern-based"。

真根因在别处：`DADAOISelDAGToDAG.cpp::Select()` 对 `ISD::CALLSEQ_START`/
`ISD::CALLSEQ_END` 做手写特判：
```cpp
if (Opc == ISD::CALLSEQ_START || Opc == ISD::CALLSEQ_END) {
  ReplaceUses(SDValue(Node, 0), Node->getOperand(0));
  CurDAG->RemoveDeadNode(Node);
  return;
}
```
这只重定向了 **ResNo=0（chain）**，从未处理 `callseq_end` 的
**ResNo=1（glue）**——而这个 glue 结果正是后续读取调用返回值的
`CopyFromReg` 节点的 glue 操作数来源。单个调用的基本块里这个缺陷不可见
（没有别的东西会去抢占那块被 `RemoveDeadNode` 释放的内存）；一旦同一基本
块出现第二个独立调用（直接/间接/libcall 均可触发），前一个 `callseq_end`
被删除后遗留的悬空 glue 引用会与后续新分配节点的内存产生错误关联，被
`ScheduleDAGSDNodes::BuildSchedUnits` 的"已插入"检测抓到，报
`Node already inserted!` / `Illegal result number!`。

**DAG 转储证据**（`llc -debug-only=isel`，最小复现
`double cmp(double a,double b){return (a>=b)+(a==0);}` `-O1`）：

修复前，"Selected selection DAG" 里 **同一个 `t93`（`CALL_IIII` for
`__eqdf2`）节点被完整打印两次**，且另一处 `CopyFromReg` 的 glue 操作数显示
为 `<<Deleted Node!>>`；一个本该读自己 callseq_end 的 `CopyFromReg`（`t66`）
其 glue 操作数被错误地指到了**另一个无关调用**（`t93`）的 ResNo=1。

修复后重跑同一 DAG 转储：43→49 节点无重复打印，每个 `CopyFromReg` 都正确
从**自己的** `ADJCALLSTACKUP` 取 glue（`t39` 从 `t38:1`，`t66` 从
`t65:1`），零 `<<Deleted Node!>>`。

**修复方案**：仿照 `RISCVInstrInfo.td` 的标准做法，把 `callseq_start`/
`callseq_end` 转成 tablegen `Pat<>`-based 选择，而不是手写特判：

1. `DADAOInstrInfo.td`：新增目标专属 `SDT_DADAOCallSeqStart`/
   `SDT_DADAOCallSeqEnd`（i64 类型，对应 DADAO 实际用 i64 承载调用帧调整
   立即数）+ `callseq_start`/`callseq_end` SDNode 重声明 + 两个新
   `DADAOPseudo`：`ADJCALLSTACKDOWN`/`ADJCALLSTACKUP`（`Size=0`，因为
   `DADAOFrameLowering::eliminateCallFramePseudoInstr` 无条件
   `MBB.erase(MI)`——DADAO 恒定预留调用帧，这两个伪指令从不真正落地）。
2. `DADAOISelDAGToDAG.cpp`：删除对 `ISD::CALLSEQ_START/END` 的手写特判，
   让 `SelectCode()` 走新 `Pat<>` 匹配——`MorphNodeTo`（tablegen 匹配的
   底层机制）是**原地**变形节点，不换节点身份，所有 ResNo 的 use-edge
   自动全部保持有效，不需要任何手动 glue 记账。
3. `DADAOInstrInfo.cpp`：`DADAOGenInstrInfo` 构造函数此前把 `CFSetup`/
   `CFDestroy` 传成字面量 `0`（导致 `PrologEpilogInserter` 从未识别出
   任何"call frame setup/destroy"伪指令，`eliminateCallFramePseudoInstr`
   从未被调用）——现在改传真实的
   `DADAO::ADJCALLSTACKDOWN`/`DADAO::ADJCALLSTACKUP`。这个遗漏是新
   pseudo 指令能生效的必要条件（缺了这步会导致 `ADJCALLSTACKDOWN/UP`
   泄漏到最终汇编，报 "Unsupported instruction"，本任务过程中先踩了这个
   坑再补上，详见下面"验收结果"里第一轮 lit 回归的记录）。

**修改文件**（均在 `.work/llvm`，已 `git commit` 4b812d2f9930，父提交
9bb9dffdaeb7 = ML-020a）：
- `llvm/lib/Target/DADAO/DADAOInstrInfo.td`（+35/-0）
- `llvm/lib/Target/DADAO/DADAOISelDAGToDAG.cpp`（+8/-5，移除手写特判）
- `llvm/lib/Target/DADAO/DADAOInstrInfo.cpp`（+2/-1，CFSetup/CFDestroy 接线）
- 合计 3 文件 +45/-6

Patch 已导出：`components/llvm/patches/0048-DADAO-fix-ISD-CALLSEQ_START-END-glue-linkage-bug-ML-.patch`，
已追加进 `series`。独立验证：在 pin 提交 `9bb9dffdaeb7` 建临时 worktree，
`git am 0048-...patch` **exit=0** 干净应用（已清理临时 worktree）。

新增回归测试（非浮点，隔离出"同一基本块 2 个独立直接调用"这个纯粹场景，
不依赖 libcall）：
- `tests/lit/E2E/Inputs/direct_call_multicall_block.ll`：`g()`返回10,
  `h()`返回32, `main`返回`g()+h()`（期望 42）。
- `tests/lit/E2E/direct_call_multicall_block.test`：同时跑 QEMU 和 gem5
  两个后端，各自断言 `exit=42`。

**验收结果**（均为本次真实重跑输出，非估算/转述）：

1. **架构师给出的浮点最小复现**：
   `clang --target=dadao -O1 -c cmp.c` → **exit=0**（修复前 exit=134/
   SIGABRT）。DAG 转储核验见上方"根因"部分。

2. **新增非浮点两连续直接调用测试**：`llvm-lit
   tests/lit/E2E/direct_call_multicall_block.test` → **PASS**（QEMU 和
   gem5 两条 `RUN:` 均 `exit 42`，两个调用的返回值都被真实使用相加，不是
   巧合正确——`g()`和`h()`返回不同值，任一个的返回值被吃掉或用错都不会
   凑出 42）。

3. **`vfprintf.o` 真实 musl 构建标志**：
   ```
   cd .work/build/musl && rm -f obj/src/stdio/vfprintf.o && make -j1 obj/src/stdio/vfprintf.o
   ```
   → **exit=0**，`obj/src/stdio/vfprintf.o`（27152 字节）生成成功。

4. **全量 `llvm-lit tests/lit/E2E/`**：
   - 首次重跑（补 `ADJCALLSTACKDOWN/UP` 后、接线 CFSetup/CFDestroy
     前）：**35/60 PASS，25 FAIL**（`indirect_call.test` 报
     `Unsupported instruction : <MCInst 324 ...>`——诊断出
     `eliminateCallFramePseudoInstr` 从未被触发，伪指令泄漏到汇编）。
   - 补上 `DADAOInstrInfo.cpp` 的 CFSetup/CFDestroy 接线后重跑：
     **60/60 PASS**（零回归）。
   - 加入新测试后最终重跑：**61/61 PASS**（100.00%）。

5. **`python3 tools/run_differential.py`**：
   `AGREE(3-way)=200  AGREE(interp+QEMU, gem5-SKIP)=2  DIVERGE=0`；
   `AGREE(4-way)=200  Sail-SKIP(out-of-slice)=2  SAIL-DIVERGE=0`——与修复前
   基线一致，零回归。

6. **`python3 scripts/manifest_check.py`**：`manifest validation: PASS`。
   **`python3 scripts/check_issues.py`**：`Open: 22 / Closed: 34 / Total:
   56 / ISSUE REGISTRY: PASS`。

7. **musl 全量 fresh 编译**（`rm -rf .work/build/musl/obj lib/libc.a
   lib/crt1.o` 后 `make build-musl` 从零重建，非增量）：
   - 成功编译对象：**1336**（`find obj/src -name '*.o' | wc -l`）。
   - 失败对象：**10**（从修复前 Makefile 注释记录的 ~180 降到 10）。逐个
     单独 `-j1` 重跑确认真实崩溃原因（避免 `-j6` 并行导致的日志交织误判）：
     - `legacy/daemon.o`：`UNREACHABLE at TargetInstrInfo.h:786`——**既有、
       不相关问题**（`musl-backend-assert-instrinfo-unreachable`，未动）。
     - `regex/glob.o`、`regex/regcomp.o`：`MachineBlockPlacement`
       "unanalyzable fallthrough" 断言——**既有、不相关问题**
       （`musl-backend-assert-unanalyzable-fallthrough`，未动）。
     - `locale/dcngettext.o`、`network/res_msend.o`、
       `process/execle.o`/`execl.o`/`execlp.o`/`execvp.o`、
       `unistd/getcwd.o`（共 7 个）：`fatal error: error in backend:
       Cannot select: tNN: i64,ch = dynamic_stackalloc ...`——**新发现、
       与本任务改动无关的独立缺口**（DADAO 后端从未实现
       `ISD::DYNAMIC_STACKALLOC` 的合法化/选择，这几个文件用到运行时决定
       大小的 `alloca`）。这些文件此前大概率先撞本任务修的
       `BuildSchedUnits` 断言（先崩在更早的阶段），本次修复解锁后才第一次
       真正走到指令选择这一步曝光这个不同的、真正的阻断点——**不是本次
       改动引入的回归**（已用独立重跑核实：`rm -f getcwd.o && make -j1
       getcwd.o` 崩溃信息是干净的 `Cannot select`，不是断言，与
       CALLSEQ/glue 完全无关）。已登记为新 open issue
       `musl-backend-dynamic-stackalloc-unimplemented`。
   - `docs/issues.yaml` 更新：`musl-backend-assert-illegal-result-number`
     （15 个触发对象）、`musl-backend-assert-node-already-inserted`（88
     个触发对象）、`musl-backend-assert-asmprinter-unmapself`（1 个，
     `__unmapself.o` 单独 `rm+rebuild` 核实确实已能干净编译，大概率同根
     因的副带收益）**三条全部移至 `docs/issues-archive.yaml`
     （`status: closed`，`resolved_by: ML-021a`）**；新增 1 条 open issue
     `musl-backend-dynamic-stackalloc-unimplemented`（7 个触发对象，详见
     issue 正文）。
   - `Makefile` 的 `build-musl` 目标提示文案 `~180 known-failing files`
     更新为 `~10 known-failing files as of ML-021a`（纯文档性更正）。

**遗留问题**：
- `musl-backend-dynamic-stackalloc-unimplemented`（7 个触发对象）——真实
  存在的独立后端缺口（`ISD::DYNAMIC_STACKALLOC` 从未实现），不在本任务
  范围内，已登记为新 issue，留给独立任务处理。
- `musl-backend-assert-unanalyzable-fallthrough`（glob.c/regcomp.c）、
  `musl-backend-assert-instrinfo-unreachable`（daemon.c）两个既有问题未动
  （本任务范围外，验证过与本次改动无关）。
- 一处**文档准确性订正**（非代码问题）：本任务过程记录 + LLVM commit
  message 曾写"CFSetup/CFDestroy 字面量 0 碰巧等于 HALT_RIII 的
  opcode"——subagent review 核实后发现这是**事实错误**：生成的枚举里
  opcode 0 实际是 `PHI`（target-independent 伪指令，`Target.td:1200`），
  不是 `HALT_RIII`。这**不影响修复本身的正确性**（`PHIElimination` 在
  PEI 之前已消除所有 PHI 节点，所以"PEI 从未识别出任何 call-frame 伪指令"
  这个结论依然成立，只是原因是"此时函数体里已不存在 opcode 0 的 MI"而非
  "opcode 0 恰好被占用"）。已在 `docs/issues-archive.yaml` 里订正这段
  文字；**LLVM commit message 本身按 git 规范未做 amend**（未 push、未被
  其它提交依赖，若架构师认为有必要可自行决定是否 squash 订正，本任务不
  擅自改写已提交的 git 历史）。

## 审阅记录（subagent）

### 审阅记录（subagent · 判决 = 通过 Accepted）

subagent 已读 `reviewer.md`，独立重跑（非采信完成区转述）：

- **Diff 逐行核对**：`git show HEAD`（`.work/llvm`）与完成区描述一致，
  3 文件 +45/-6，无出入。
- **类型正确性**：核对 `DADAOISelLowering.cpp` 的 `DAG.getCALLSEQ_START`/
  `getCALLSEQ_END` 实际经 `getIntPtrConstant`（DADAO 指针类型 i64）——
  `SDT_DADAOCallSeqStart/End` 的 i64 约束正确 ✓。
- **`Size=0` 核验**：`DADAOFrameLowering::eliminateCallFramePseudoInstr`
  无条件 `MBB.erase(MI)`，`hasFPImpl` 恒 `false` ⇒
  `hasReservedCallFrame()` 恒真 ⇒ PEI 恒清除这两个伪指令——`Size=0` 正确；
  实测最终 `.s` 里 `grep -ni ADJCALLSTACK` 零匹配 ✓。
- **CFSetup/CFDestroy 操作数顺序**：核对构造函数参数顺序
  `CFSetup→ADJCALLSTACKDOWN`、`CFDestroy→ADJCALLSTACKUP` 未颠倒 ✓。
- **重新独立 build**：`ninja llc clang` 干净通过。
- **独立重跑 lit E2E**：61/61 PASS（含新测试）✓。
- **独立重跑差分**：`AGREE(4-way)=200 DIVERGE=0` ✓。
- **独立复现崩溃已修**：两行浮点最小复现 `exit=0` ✓。
- **新测试真实性核验**：读 `.test`+`.ll`，手动跑两条 `RUN:` 行确认 QEMU
  和 gem5 都真实 `exit=42`，非假动作/未跳过任一后端 ✓。
- **issues.yaml 记账核验**：`check_issues.py` PASS；3 条归档 + 1 条新增
  逐一 grep 核对状态字段 ✓。
- **dynamic_stackalloc "非本次引入"核验**：独立 `rm -f getcwd.o && make
  -j1 getcwd.o` 重跑，确认崩溃是干净的 `Cannot select: ... dynamic_
  stackalloc ...`（DAGToDAG"无法选择"，非断言），与 CALLSEQ/glue 无关 ✓。
- **finding（1 条，事实性文档错误，非代码 bug）**：commit message /
  完成区草稿称"CFSetup/CFDestroy=0 碰巧等于 HALT_RIII 的 opcode"——
  subagent 直接读生成的 `DADAOGenInstrInfo.inc` 枚举，opcode 0 实际是
  `PHI`（`Target.td:1200`），不是 `HALT_RIII`（`HALT_RIII=373`）。不影响
  修复正确性结论（`PHIElimination` 先于 PEI 跑，opcode 0 的 MI 到 PEI 时
  已不存在，无论其真实身份是什么，结论不变）。
  | finding | 处置 | 改了什么 | 复验证据 |
  |---|---|---|---|
  | CFSetup/CFDestroy=0 "碰巧等于 HALT_RIII opcode" 的说法与生成枚举不符（实为 PHI=0） | ✅已修 | `docs/issues-archive.yaml` 对应条目文字订正；`git show HEAD`（.work/llvm commit）message 本身未 amend（未 push/无下游依赖，按 git 规范不擅自改写已提交历史，已在完成区"遗留问题"里显式记录这个已知的文档不一致） | `rtk proxy grep -n "PHI\s*=\s*0" DADAOGenInstrInfo.inc` → `PHI = 0, // Target.td:1200`，`check_issues.py` 订正后仍 PASS |
- **未测输入/边界推敲**：subagent 额外检查了"是否存在
  `callseq_start`/`callseq_end` 的其它 glue/no-glue 组合本 `Pat<>` 匹配不到"
  这一潜在风险——DADAO `LowerCall` 只产出单一形状（`amt2` 恒为字面量
  `0`，从不需要真实寄存器调整），61 个 lit 测试 + 一次全量 musl fresh 重建
  均未出现 callseq 节点的"cannot select"，判定当前无实际风险，但未刻意
  构造合成反例穷举，如实记录为未完全穷举项。
- **未独立复跑整个 musl 全量重建**（耗时较长，判断为合理的审查范围收敛，
  仅抽查核实了 `getcwd.o` 一个对象的失败类型，其余 9 个采信完成区的单独
  `-j1` 重跑记录）。

**判决：Accepted**（1 条 finding 为文档准确性问题，已处置，不影响代码
正确性判断）。
