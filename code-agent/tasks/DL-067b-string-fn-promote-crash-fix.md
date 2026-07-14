# DL-067b: 修复 DADAO backend string 函数 CodeGen 崩溃（BR_CC 过早 combine）

**执行环境**: 本地 subagent（LLVM SelectionDAG lowering 修复）

**状态**: 通过（架构师复核）

**前置**：DL-067a 根因定位（`code-agent/tasks/DL-067a-string-fn-promote-crash-rootcause.md` 完成区）、issue `codegen-string-fn-promote-crash`（`docs/issues.yaml`）。

## 背景（DL-067a 已确认，直接复用）

`DADAOISelLowering.cpp` 里有两处对 `ISD::BR_CC` 的处理，功能重复：

1. `LowerOperation`（约 277-281 行）：`case ISD::BR_CC: return LowerBR_CC(Op, DAG);`——经 `setOperationAction(ISD::BR_CC, MVT::Other, Custom)` 注册，在**正确的合法化后阶段**触发。
2. `PerformDAGCombine`（约 538-539 行）：`case ISD::BR_CC: return LowerBR_CC(SDValue(N,0), DAG);`——在 **Combine1（pre-legalize DAG combine）阶段**提前触发，早于 `SelectionDAG::LegalizeTypes()`。

当某次 combine（如 `ReduceLoadWidth`，把大端对齐检查场景下的 i64 load 窄化成 i8）产出一个非法类型（i8）的 `br_cc` 操作数时，(2) 这条过早的 combine 分支会抢先把 `ISD::BR_CC` 转成自定义 `DADAOISD::BRZ` 节点——**在类型合法化跑完之前**。等到类型合法化阶段再遇到这个已经是自定义节点的 `BRZ`，因为全部 18 个 `DADAOISD::` 节点都没有 `PromoteIntegerOperand`/`ReplaceNodeResults` 覆写，无法识别、`fatal error`。

**最小复现**（DL-067a 已产出，路径见该任务完成区）：
```c
unsigned long test_align(char *str) {
    while ((unsigned long)str & 7) {
        if (!*str) return 0;
        str++;
    }
    return 1;
}
```
`llc -march=dadao -O0 -filetype=obj` 直接崩溃，复现 "Op #1: ... Unknown Target Node #524 ... Do not know how to promote this operator's operand"。

## 做什么

1. **主修复**：去掉 `PerformDAGCombine` 里 `case ISD::BR_CC: return LowerBR_CC(SDValue(N,0), DAG);` 这条冗余分支（或用 `DCI.isBeforeLegalize()` 之类的守卫确保它绝不在类型合法化完成前触发）——让 `LowerOperation` 的标准 `Custom` 路径在正确阶段（类型已合法化）独立完成这个转换，不再有非法类型操作数流入 `DADAOISD::*` 自定义节点。
2. **验证**：
   - DL-067a 的最小复现用例（6 行 C）用 `llc -march=dadao -O0` 编译不再崩溃，产出正确的分支指令序列（`brz`/`brnz` 等）。
   - 反汇编确认生成的分支逻辑语义正确（不是"编过了但跳转条件错"）——构造一个真跑判别性测试（真实调用 `test_align`-类似函数，传入对齐/不对齐指针 + NUL 提前结束的字符串，双后端验证返回值正确）。
   - `strlen.c`/`memset.c`/`memchr.c`/`strcat.c`/`strchr.c`/`strstr.c`（issue 里列出的失败函数）现在能正常编译。
3. **防御性加固（可选，视时间）**：DL-067a 提到的次选方向——给 `DADAOISD::` 自定义节点补 `PromoteIntegerOperand`/`ReplaceNodeResults` 覆写作为防御——若主修复已经彻底解决问题，这一步不是必须的，可以只记录为后续加固建议而不实现（避免范围膨胀）。

## 约束

- **不要**只是让这一个特定文件/函数绕过崩溃（比如给 `strlen.c` 加特殊编译选项跳过某个 combine pass）——要修 `PerformDAGCombine` 本身这个结构性问题。
- 修复后需要确认**没有引入行为变化**——`LowerBR_CC` 的转换逻辑本身不变，只是触发时机从"combine 阶段"移到"legalize 阶段"，理论上对已经是合法类型的 br_cc（现有 E2E 测试用的场景）应该是完全等价的结果，需要验证这一点（现有 E2E 全绿即是最好的证据）。
- 不回归：E2E 29/30（`syscall_hello.test` 已知无关失败）、四方 AGREE(3-way)=200/DIVERGE=0、Sail AGREE(4-way)=200。

## 验收（架构师亲跑）

```bash
cd ~/DADAO-0628 && ninja -C .work/build/llvm llc clang
# 用 DL-067a 的最小复现用例验证不再崩溃
.work/build/llvm/bin/clang --target=dadao -nostdlib -nostdinc -ffreestanding -O0 -c \
  <DL-067a 最小复现 .c 路径> -o /tmp/mini_align.o
# 重建 picolibc，确认 strlen.c 等此前失败的文件现在能编译
rm -rf .work/picolibc/build-dadao && make build-picolibc
llvm-lit tests/lit/E2E/ 2>&1 | tail
python3 tools/run_differential.py 2>&1 | tail -3
```

**判别强调**：反汇编确认 BR_CC 相关分支指令生成正确（不只是"不崩溃"，语义要对——用真实运行时探针，如对齐/非对齐指针 + 提前 NUL 的字符串双后端跑出正确返回值）；`ninja libc.a`（非 `-k 0` 容错模式）里 string 函数不再崩溃；E2E/四方不回归。

## 参考指针

- DL-067a 完成区（`code-agent/tasks/DL-067a-string-fn-promote-crash-rootcause.md`）：完整根因证据链（`-debug-only=dagcombine` trace）+ 最小复现用例路径
- `docs/issues.yaml` 的 `codegen-string-fn-promote-crash` 条目
- `.work/llvm/llvm/lib/Target/DADAO/DADAOISelLowering.cpp`（`LowerOperation` 约 277-281 行、`PerformDAGCombine` 约 538-539 行、`LowerBR_CC` 约 304-363 行）
- `.work/picolibc/libc/string/`（strlen.c 等一批此前失败的文件，重建 libc.a 后应能编译）

—— 自审见 DS.md §自审流程同等标准（subagent 自己复核，逐条 finding + 判决）。**必须用真实运行时判别性探针验证分支语义正确，不能只验证"编译不崩溃"**。

---

## 完成区（2026-07-14，架构师直执行）：通过

**状态**：通过

**主修复**：`DADAOISelLowering.cpp` 去掉 `PerformDAGCombine` 里冗余的 `case ISD::BR_CC: return LowerBR_CC(SDValue(N,0), DAG);` + 对应的 `setTargetDAGCombine(ISD::BR_CC)` 注册。

**追加修复（执行中发现，任务范围内的必要连带修正）**：单纯去掉冗余 combine 后，全部使用比较的现有 E2E 测试（loop_sum/cond_abs/usum_loop/arr_sum/bubble_sort/malloc_hello/printf_hello 共 7 个）反而以 `Cannot select: br_cc` 崩溃退步——ground-truth 排查发现 `setOperationAction(ISD::BR_CC, MVT::Other, Custom)` 这条注册从建立以来就从未被 `LegalizeDAG` 真正查询过：其 BR_CC 分支按被比较操作数类型（`Node->getOperand(2)`，即 LHS，i64）查 action，不是 BR_CC 自身的链类型（`Other`）。冗余的 pre-legalize combine 一直在悄悄代劳真正的转换工作，掩盖了这条注册本身是错的。已同步修正为 `setOperationAction(ISD::BR_CC, MVT::i64, Custom)`，`LowerOperation` 的 Custom 路径由此在正确阶段（类型合法化后）真正生效。

**验证**：
1. DL-067a 最小复现（对齐检查 + 提前 NUL 循环）`llc`/`clang -O0` 编译不再崩溃，反汇编确认生成 `brz`/`brnz` 分支序列。
2. 真实运行时判别性探针（`tests/lit/E2E/Inputs/align_strfn.c`，4 个案例：8 字节对齐指针跳过循环体/未对齐指针走满整个检查范围/未对齐指针分别在 0 次与 2 次迭代后遇 NUL）——QEMU=gem5=0（全部正确），已固化为回归测试 `tests/lit/E2E/align_strfn.test`。
3. picolibc 干净重建（`rm -rf build-dadao && make build-picolibc`）：`strlen.c`/`memset.c`/`memchr.c`/`strcat.c`/`strchr.c`/`strstr.c` 对应 `.o` 全部产出，不再崩溃；剩余约 205 个失败编译单元核对全部是 libm/complex 浮点（M1 排除范围内，与本 issue 无关，strtod/strtof 属浮点解析非本任务范围）。
4. `llvm-lit tests/lit/E2E/`：30/31（新增 `align_strfn.test`，同一个既有 `syscall_hello.test` 无关失败，基线 29/30 不回归）。
5. `python3 tools/run_differential.py`：AGREE(3-way)=200/DIVERGE=0/HARNESS=6，Sail AGREE(4-way)=200，与基线完全一致。

**patch series**：`components/llvm/patches/0033-br-cc-premature-combine-fix.patch`，已加入 `components/llvm/patches/series`；在临时 worktree 用 `git am` 从父提交重放，产出树与开发树（`.work/llvm` == `.work/source/llvm` 的符号链接）逐字节一致。

**附带发现、已记新 issue（未修复，超出本任务范围）**：`codegen-global-addr-const-offset-dropped`——构造运行时探针过程中发现，`@global + 编译期常量`（如 `buf+3`）物化为独立地址值时，`RELA_LO` addi 的低 12 位丢弃了这个常量偏移（`*(buf+3)` 实际读到 `buf[0]`）。与 BR_CC 无关，探针已改用纯栈上变量 + 运行时指针算术绕开，不受影响。

**issues.yaml**：`codegen-string-fn-promote-crash` → `status: closed`，`resolved_by: DL-067b`；新增 `codegen-global-addr-const-offset-dropped`（open）。

---

## 架构师复核（2026-07-14，ground-truth）：通过

- `DADAOISelLowering.cpp` diff 审阅：去掉 `PerformDAGCombine` 冗余 `BR_CC` case + `setTargetDAGCombine(ISD::BR_CC)`；`setOperationAction(ISD::BR_CC, MVT::Other, Custom)` 更正为 `MVT::i64`——**发现并修复了一个从后端建立起就存在、被冗余 combine 掩盖的注册错误**，这是本任务中意外但真实且必要的连带修复，非范围膨胀。
- 独立确认无副作用：`PerformDAGCombine` 顶部被删的 `DAG`/`DL` 局部变量在剩余的 `BRCOND` case 里未被引用，清理正确。
- 独立重跑：全新 `ninja llc/clang/lld/...` → `align_strfn.test` 单独 PASS（双后端 4 组判别性用例：对齐跳过/满程遍历/两种 trip count 的提前 NUL，均非"只是不崩溃"）→ 全 E2E 30/31（新增用例，同一个既有 `syscall_hello.test` 无关失败）→ 四方差分 AGREE(3-way)=200/DIVERGE=0、Sail AGREE(4-way)=200，不回归。
- 独立手动编译确认 `strlen.c` 不再崩溃（此前必现的 `PromoteIntegerOperand`/`Unknown Target Node` 错误消失，产出正常 `.o`）。
- 新登记 `codegen-global-addr-const-offset-dropped`（探针设计时意外发现，与本任务无关，正确未修复、如实记录）——条目完整、有具体复现证据，格式合规（`python3 scripts/check_issues.py` PASS）。

**判定**：通过，提交。
