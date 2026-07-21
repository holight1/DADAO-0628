# ML-015c：ISA vector 与 spec 期望对齐

**日期**：2026-07-21

**状态**：Accepted-with-findings（30-task run：20/30）

## 背景

ML-015b 审计确认当前 QEMU fault code 主路径基本一致，但 vectors 存在多类
规范错配：cold `ret` 的 RASUF 被写成 ILLI，合法 control-flow 被写成
legality/ILLI，部分 `class: encoding` 实际依赖执行 fault，wiki 引用也不总是
落到定义该异常的章节。若不先修正，后续 QEMU 回归会把错误测试期望固化。

## 目标与 ownership

worker 只负责 `tests/vectors/isa/*.yaml`、本 task MD 完成区和 task-owned audit
evidence，不改 QEMU、LLVM、harness、contracts、`docs/issues.yaml` 或 wiki。

必须逐条对照 `contracts/isa/spec.md`，修正所有能被当前 spec 直接证明的错配：

- cold `ret` → `RASUF`，并引用 §5.6，说明 precise/PC/RA 语义；
- 合法 `rb0` control-flow 用法不得标为非法 operand；
- `class: encoding` 必须符合 schema 的“只验编码”含义；若条目实际验证
  operand legality 或执行 fault，应改为合适 class，或拆分/重写为不依赖下游
  poison 的测试；
- `wiki_cite`、notes、expected_fault 必须与实际被测指令一致，不能把
  downstream `halt rd0` 的 ILLI 当成目标指令 fault；
- 不为了追求全绿而删测试、降低断言或把未知语义标成 PASS；对 spec 不足以
  决定的条目保留为 deferred/记录 finding，不擅自推断。

## 约束

- 不访问或引用 `~/toolchain`、`~/knowledge-graph`。
- 不修改 `tests/scripts/run_qemu_test.py`，harness 修复另立任务。
- 不修改用户原有未跟踪的 `code-agent/tasks/ML-014a-musl-e2e-malloc-printf.md`。
- 先做完整 inventory，再做最小 YAML 修改；保留修改前后计数、diff check 和
  schema/validator 输出。

## 验收

- 每个修改项有 spec 章节和理由。
- vectors schema 检查通过；active/deferred 总数变化有解释。
- 不运行 QEMU 作为“规范正确”的替代证明；QEMU fresh 回归留到后续任务。
- 由不同 subagent 独立 review，重点检查没有引入错误测试或削弱断言。

## 完成区

已完成独立 review 后的最小 control-flow vector 修订（2026-07-21）。

- 修改文件：`tests/vectors/isa/control-flow.yaml`。
- 记录文件：`docs/reviews/ML-015c-vector-spec-alignment-20260721.md`。
- 本次修订前后计数：`213 / 207 / 6` → `213 / 202 / 11`（total / active /
  deferred）。class 计数保持 `encoding 89`、`legality 13`、`boundary 7`；
  fault 计数保持 `ILLI 30`、`RASUF 2`、`MALIGN 1`。
- 两条 cold `ret` boundary 记录继续使用 `expected_fault: RASUF` 和
  `spec.md §5.6`；`expected_state: {}` 仅满足现有 boundary schema 条件，
  不声称验证 PC/RA。
- 四条合法 `rb0` jump/call 记录保留为 `class: encoding`、
  `expected_fault: null`，但均标为 `deferred`，理由统一为“当前 harness 没有
  encoding-only non-executing mode；待独立 harness 任务提供安全目标/静态路径”。
  encoding-only cold `ret` 也保留一条 deferred 记录；对应的另一条记录继续是
  active boundary `RASUF`，避免把执行 fault 与编码记录混淆。
- 独立 review finding：当前 builder 会实际发出 encoding-class 指令，四条
  `rb0` jump/call 在下游得到 `ILLI`；因此不能以 active/no-fault 记录表示
  encoding-only 验证。未删除条目、未伪造通过，也未运行 QEMU。
- Schema/validator/diff-check：
  `python3 scripts/validate_vectors.py` → `213 cases, 87/87 opcodes covered OK`；
  `python3 scripts/validate_encoding.py tools/opcodes.yaml` → `87 records OK`；
  `python3 -c 'import pathlib,yaml; cs=[c for p in pathlib.Path("tests/vectors/isa").glob("*.yaml") for c in yaml.safe_load(p.read_text())]; assert all({"mnemonic","format","class","encoding","input_state","wiki_cite"} <= set(c) and c["class"] in {"encoding","legality","semantic","boundary","overlap"} and c.get("expected_fault") in {None,"ILLI","UNDI","MALIGN","IALIGN","RASOF","RASUF"} for c in cs); print("schema_check: PASS")'` → `schema_check: PASS`；
  `git diff --check` → `PASS`。
- 未运行 QEMU。未处理疑点：active boundary 的空 `expected_state` 不验证
  PC/RA；encoding-only non-executing mode、安全目标/静态路径仍需独立 harness
  任务；其他文件中的 encoding-class 执行 fault、MALIGN class 及 schema 缺少
  execution-fault class 的问题仍保留，未擅自猜测或修改。
- 保留他人改动；未修改 `code-agent/tasks/ML-014a-musl-e2e-malloc-printf.md`，
  也未访问 `~/toolchain`、`~/knowledge-graph`。

### 独立 review

- 首轮 review：`docs/reviews/ML-015c-independent-review-20260721.md`，
  `Needs-fix`；确认 active legal jump/call 改为 no-fault 会在现有 builder 下
  产生错误测试。
- 修订后 review：`docs/reviews/ML-015c-independent-review-r2-20260721.md`，
  `Accepted`；确认相关 encoding-only 条目均 deferred，两个 active cold-ret
  boundary 均为 `RASUF`，没有削弱断言。
