# ML-015c independent review r2

日期：2026-07-21  
结论：**Accepted**

## 复核范围

只读核查 `tests/vectors/isa/control-flow.yaml` 的四个合法 `rb0`
`jump/call` 条目、encoding-only cold `ret` 条目及两个 active boundary
条目；运行 schema/validator/diff-check，未运行 QEMU。

## 证据

- 四个合法 `rb0` 条目均为 `class: encoding`、`expected_fault: null`、
  `status: deferred`：两个 `jump 0x65000000` 位于
  `control-flow.yaml:434-445`、`499-510`，两个 `call 0x6D000000` 位于
  `control-flow.yaml:459-470`、`512-523`。
- 四个条目的 `deferred_reason` 均明确为：
  “当前 harness 没有 encoding-only non-executing mode；待独立 harness 任务
  提供安全目标/静态路径”。条目未删除，也没有把已知下游 `ILLI` 伪造为通过。
- encoding-only cold `ret 0x6E040000` 保留为 `class: encoding`、
  `expected_fault: null`、`status: deferred`（`control-flow.yaml:472-483`）。
  它没有被当作 active execution case，也没有与 boundary fault 混淆。
- 两个 active boundary cold-ret 均为 `expected_fault: RASUF`、
  `wiki_cite: spec.md §5.6`：`0x6E040000`（`control-flow.yaml:485-495`）
  与 `0x6E000000`（`control-flow.yaml:525-535`）。这两项保留了目标 fault
  断言；下游 `halt rd0` 的 `ILLI` 未替代 `RASUF`。
- 两个 boundary 的 `expected_state: {}` 只满足现有 schema 的非 null 形状，
  不验证 PC/RA；当前 notes 不应被解读为 harness 已比较 PC/RA。PC/RA
  状态比较仍是未处理疑点。

## 断言完整性判断

本次修订没有削弱 active boundary 的 fault 断言：全量向量统计为
`213 total / 202 active / 11 deferred`，fault 统计为 `RASUF 2`、
`ILLI 30`、`MALIGN 1`。四个无法安全执行的 encoding-only `rb0` 条目和一条
encoding-only cold-ret 被明确 deferred，因而不再以 active/no-fault 预期掩盖
builder 实际执行后的下游 `ILLI`；这属于移除误导性 active 断言，而不是伪造
通过或删除测试覆盖。

## 检查结果

```text
python3 scripts/validate_vectors.py
→ validate_vectors: 10 files, 213 cases, 87/87 opcodes covered OK

python3 scripts/validate_encoding.py tools/opcodes.yaml
→ validate_encoding: 87 records OK

schema_check
→ PASS

git diff --check
→ PASS
```

## 未处理疑点

- 当前 harness 没有 encoding-only non-executing mode；恢复这些 deferred 条目
  需要独立 harness 任务提供安全目标或静态路径，并重新证明 `jump/call` 自身
  无 fault。
- `expected_state: {}` 不提供 PC/RA 比较；该语义仍需可表达并可执行的
  harness/schema 支持。
- 本 review 未运行 QEMU，因此不把 validator/schema 通过当作运行时证明。
