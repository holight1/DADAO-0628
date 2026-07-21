# ML-015d：QEMU vector harness fail-closed 修复

**日期**：2026-07-21

**状态**：Accepted（30-task run：21/30）

## 背景

ML-015b 审计发现 harness 存在三个门禁问题：目录参数会触发
`AttributeError`；`expected_state` 中不支持的 `pc`/`ra` 等键会被静默忽略；
fault 只按进程退出码判断，尚不能证明 fault 来源或 faulting PC/RA。

## 目标与 ownership

worker 负责 `tests/scripts/run_qemu_test.py`、`tests/scripts/build_test_binary.py`
和必要的 `tests/vectors/schema.md`/harness unit evidence：

1. 目录参数 `tests/vectors/isa/` 应明确递归/聚合执行所有 YAML，正确统计
   active/deferred，遇到 FAIL/timeout 返回非零；目录不存在或没有 YAML 时
   fail-closed，不 traceback 冒充测试结果。
2. `build_test_binary.py` 对当前不支持的 `expected_state` 键（尤其 `pc`、`ra`
   及未知 bank）必须显式报错，不能生成一个看似通过的 binary；schema 文档要
   明确当前可比较字段与未来 PC/RA dump 的边界。
3. 保留现有 `FAULT_CODES` 和 QEMU exit protocol；不把 exit code 宣称为
   fault-source/PC/RA 证明。若当前无法加入观测能力，报告中明确列为后续任务。

## 约束

- 不修改 QEMU、LLVM、gem5、contracts、vectors 的语义、`docs/issues.yaml` 或 wiki。
- 不访问或引用 `~/toolchain`、`~/knowledge-graph`。
- 不修改用户原有未跟踪的 `code-agent/tasks/ML-014a-musl-e2e-malloc-printf.md`。
- 不用 `|| true`；现有测试必须保持可运行，新增 unit/CLI checks 要记录原始 rc。

## 验收

- 目录入口不再触发 `AttributeError`，能汇总多个 YAML。
- `pc`/`ra`/未知 key 的负例明确失败；rd/rb/memory 既有路径不回归。
- 脚本静态检查、unit/CLI checks 和必要的单个 vector smoke 通过。
- 独立 reviewer 复核 fail-closed 行为，没有把未实现的 PC/RA 能力伪装成已实现。

## 完成区

已完成 QEMU vector harness 的 fail-closed 修复，并由不同 subagent 独立 review
接受（2026-07-21）。

- 修改文件：`tests/scripts/run_qemu_test.py`、
  `tests/scripts/build_test_binary.py`、`tests/vectors/schema.md`。
- 目录入口现在递归收集 `.yaml/.yml`，跳过 `status: deferred`，输出
  `active/deferred/pass/fail/skip/input_errors` 汇总；无 YAML、无 active case、
  全部 skip、输入错误和 FAIL/timeout 均 fail-closed 返回非零。
- `expected_state` 只接受当前 runtime 真正比较的 `rd`、`rb`、`memory`；
  `pc`、`ra`、未知顶层字段、非法寄存器名/范围和错误结构显式抛出
  `ValueError`，不会被静默忽略。schema 同步声明 PC/RA 尚不可观测，fault exit
  code 也不被当作 fault source 或 faulting PC/RA 的证明。
- 保留 `FAULT_CODES`、QEMU exit protocol 和既有 QEMU 查找路径；没有修改
  QEMU/LLVM/spec/vector 语义。

实现侧检查：

- `python3 -m py_compile tests/scripts/run_qemu_test.py tests/scripts/build_test_binary.py`
  → `rc=0`。
- `python3 tests/scripts/run_qemu_test.py tests/vectors/isa --qemu /nonexistent`
  → `rc=2`，汇总 `active=202 deferred=11 pass=0 fail=0 skip=202 input_errors=0`。
- 同一目录使用 `.work/source/qemu/build/qemu-system-dadao` → `rc=0`，
  `active=202 deferred=11 pass=202 fail=0 skip=0 input_errors=0`。
- `rd-compare.yaml` 单文件真实 QEMU → `rc=0`，`10/10`；
  `control-flow.yaml` → `rc=0`，`33/33`，两个 cold-ret 均为预期 `RASUF`。
- `pc`、`ra`、未知 key 负例均明确拒绝；既有 `rd/rb/memory` 正常路径通过。
- `git diff --check` → `rc=0`。

独立 review：

- `docs/reviews/ML-015d-independent-review-20260721.md`，结论
  **Accepted**，reviewer 为 Harvey the 2nd；确认 py_compile、真实目录
  QEMU `202/202` 和 expected-state 负例均通过。
- 未修改用户原有未跟踪的 `code-agent/tasks/ML-014a-musl-e2e-malloc-printf.md`。
