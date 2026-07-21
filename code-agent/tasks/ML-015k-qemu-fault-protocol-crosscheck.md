# ML-015k：QEMU fault-code 协议交叉核对

**日期**：2026-07-21

**状态**：Accepted-with-findings（30-task run：28/30）

## 背景

ML-015b 审计确认 fault code 主路径基本一致，ML-015d 又把 harness 改成
fail-closed。现在对当前 QEMU ISA active vectors 做一次只读 fault protocol
交叉核对，避免把 exit code、vector expected_fault 和 QEMU helper case 的
语义混为一谈。

## 目标与 ownership

worker 只负责 inventory、fresh QEMU 输出、task 完成区和
`docs/reviews/ML-015k-qemu-fault-protocol-crosscheck-20260721.md`：

1. 统计 active vectors 按 `expected_fault` 的数量，明确 deferred 不计入。
2. 运行全量 QEMU ISA harness，记录每个 fault 类的通过/失败和原始 rc。
3. 只读核对 `tests/scripts/run_qemu_test.py` 的 `FAULT_CODES` 与当前 QEMU
   `helper.c`/`cpu.c` 的 RASOF/RASUF exception/exit 分支；说明 exit code 只
   证明当前协议分类，不证明 faulting PC/RA。

## 约束

- 不修改 QEMU、LLVM、vectors、kernel、spec、`docs/issues.yaml` 或 wiki。
- 不访问或引用 `~/toolchain`、`~/knowledge-graph`，不修改 ML-014a。
- 不用 `|| true`，不以历史输出替代 fresh run。

## 完成区

已完成 fresh QEMU fault protocol 交叉核对，等待独立 review。

- inventory rc=`0`：`active=202`、`deferred=11`；active fault 计数为
  `ILLI=30`、`MALIGN=1`、`RASUF=2`、`expected_fault=null=169`；当前没有
  active `UNDI`/`RASOF` vector，不能从本轮执行声称覆盖这两类 fault。
- `python3 tests/scripts/run_qemu_test.py tests/vectors/isa/ --qemu
  .work/source/qemu/build/qemu-system-dadao` → `rc=0`，
  `active=202 deferred=11 pass=202 fail=0 skip=0 input_errors=0`。
  输出中 `ILLI` 30、`MALIGN` 1、`RASUF` 2 个 expected fault 均 PASS。
- harness `FAULT_CODES` 为 `ILLI=0x82`、`MALIGN=0x81`、`UNDI=0x83`、
  `RASOF=0x84`、`RASUF=0x85`；QEMU `helper.c` 中 RASOF/RASUF 分别抛出
  `0x84/0x85`，`cpu.c` 对应分支分别以 `0x84/0x85` shutdown。
- 结论仅证明当前 exit-code 分类协议和 active vector 执行结果一致；它不证明
  faulting PC/RA，且 RASOF/UNDI 的实际 vector 覆盖仍是后续工作。

报告：`docs/reviews/ML-015k-qemu-fault-protocol-crosscheck-20260721.md`。

### 独立 review

`docs/reviews/ML-015k-independent-review-20260721.md`，结论
**Accepted-with-findings**；reviewer 确认 counts、fresh SUMMARY 和 RASOF/RASUF
mapping 一致，并保留两个边界：当前没有 active UNDI/RASOF vector，exit code 不
证明 PC/RA。
