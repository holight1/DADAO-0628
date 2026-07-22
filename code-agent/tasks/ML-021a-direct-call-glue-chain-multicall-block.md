# ML-021a: 修复"同一基本块内 ≥2 个直接 CALL"的 glue 链拓扑缺陷（roadmap B 阻断项，高风险深挖任务）

**执行环境**: 本地 subagent

**状态**: 待处理

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
