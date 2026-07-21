# ML-016j 独立 review：RB31 pointer-return / CALL defs 最小复现

日期：2026-07-21  
Reviewer：独立抽查  
判定：**Accepted-with-findings**

## 范围与核验方法

本 review 只读核验了任务说明、worker review，以及
[`/tmp/ml-016j-rb31-pointer-return-repro-20260721/`](/tmp/ml-016j-rb31-pointer-return-repro-20260721/)
中的 summary、逐项 `.rc`/`.stderr`/`.argv`、两套矩阵、代表样本 raw machine dump 和扫描表。
没有修改 LLVM/TableGen、musl、build/archive、测试或规范，也没有进行 link/runtime 验收。

## 证据核验

### 禁用 sibling call 的主矩阵

[`results/summary.tsv`](/tmp/ml-016j-rb31-pointer-return-repro-20260721/results/summary.tsv)
逐项显示 15 个 probe、O0/O3、frontend/clang/llc 共 90 条记录，三阶段均为 30/30 `rc=0`。
抽查的 clang 与 llc `.argv` 均分别包含 `-fno-optimize-sibling-calls`；主矩阵的 stderr 为空，未见
`undefined physical register`、MachineVerifier error 或 tail-call assertion。

这支持的结论是：当前 direct/indirect/nested pointer-return、pointer result 跨 call、立即使用，
以及对应 integer-return 形状，在该 no-tail 配置下没有复现 verifier failure。它不支持“pointer
return 已被排除为所有 failure 的原因”，因为真实 representative 的控制流、调用数量和 RA pressure
不同。

### 默认 O3 sibling-tail-call 变体

[`variant-tail-call/results/summary.tsv`](/tmp/ml-016j-rb31-pointer-return-repro-20260721/variant-tail-call/results/summary.tsv)
显示 frontend 30/30 成功；clang 和 llc 在 O3 各 9/15 非零（clang `rc=1`，llc `rc=134`），失败集合
包括 direct/indirect/nested pointer-return，也包括 direct/indirect/nested integer-return。
抽查的默认 O3 `.argv` 没有 no-tail flag；对应 IR 将立即返回的 call 标成 `tail call`。

所有这些非零 backend stderr 的首个共同诊断都是：

```text
Assertion `(!CLI.IsTailCall || InVals.empty()) &&
"LowerCall emitted a return value for a tail call!"` failed.
```

这发生在 SelectionDAG call lowering，属于 tail-call assertion。integer-return 也触发它，故不能把
默认 O3 的失败归因于 pointer return，更不能把它当作 `$rb31` undefined physical register verifier
形状。`direct_ptr_use`、save-across-call 和 identity 对照不触发该 assertion，也与汇总一致。

### `posix_memalign` / `memmem` representative

[`results/representatives-summary.tsv`](/tmp/ml-016j-rb31-pointer-return-repro-20260721/results/representatives-summary.tsv)
显示两份真实 source 副本在 O0 的 frontend/clang/llc 均为 0；O3 frontend 为 0，clang 为 1，llc 为
134。O3 clang/llc 的 `.argv` 均包含 `-fno-optimize-sibling-calls -O3`，所以这两项不是默认
sibling-tail-call assertion 的结果。

原始 stderr 的机器码 dump 和
[`results/representatives-call-def-scan.tsv`](/tmp/ml-016j-rb31-pointer-return-repro-20260721/results/representatives-call-def-scan.tsv)
可独立复算为：

| representative | O3 CALL | `CALL ... implicit-def ... $rd31` | `$rb31` COPY | verifier errors |
|---|---:|---:|---:|---:|
| `posix_memalign` | 2 | 2 | 2 | 2 |
| `memmem` | 5 | 5 | 5 个 call-result COPY，另有 1 个最终 return COPY | 5 |

例如 `posix_memalign` 的 raw block 先有 `CALL_IIII @aligned_alloc ... implicit-def dead $rd31`，
随后是 `%9:gprd = COPY $rb31`；错误块明确报告该 `$rb31` 为 undefined。`memmem` 在 `memchr`、
短 needle helper 和 `twoway_memmem` 路径上重复同一 CALL-def/result-read 形状。两份 llc stderr 的
raw machine block 与 clang 对应，故不是 clang-only 文本现象。

这确认了 `$rd31`→`$rb31` 的 verifier 形状确实存在，并且与 representative failure 同时出现；但
它仍只是高价值候选机制：no-tail 最小 call-return probes 全通过，代表 source 的复杂 CFG、多个
CALL、结果 live range 和寄存器压力尚未被单独隔离。因此 worker review 正确地没有把 RB31 直接写成
已证实根因。

## Findings / 证据边界

1. **O3 representative register scan 不应被表述为完整的生成 asm 验证。**
   [`results/representatives-register-scan.tsv`](/tmp/ml-016j-rb31-pointer-return-repro-20260721/results/representatives-register-scan.tsv)
   只有 O0 行；O3 backend 失败，没有 `.s` 可供该扫描读取。并且脚本的 `undefined_rb31` 列实际把
   `rb31` 引用也计入，并非独立的 verifier 判定。当前代表性 O3 结论应明确归因于原始 stderr/raw
   machine dump 和 CALL-def scan，而不是 O3 `.s` register scan。该限制不推翻候选机制，但应保留在
   后续引用中。

2. **CALL-def 文本匹配不等于 calling-convention 因果证明。**
   `memmem` 的 6 个 `$rb31` COPY 中有 1 个是最终 ` $rb31 = COPY %30:gprd` 的 return setup，
   它不是五个 verifier error 之一；真正的错误是 call-result 路径读取 undefined `$rb31`。因此
   “CALL defs 为 `$rd31`、pointer result 读 `$rb31`”是机器码事实和候选形状，不是仅凭计数就能证明
   的根因。worker review 的保守措辞是正确的。

3. **简化 representative 不是复杂 representative 的等价复现。**
   `representative_posix_memalign.c` 是 integer-return + pointer output argument，
   `representative_memmem.c` 只是一个单一外部 pointer-return wrapper；二者 no-tail 主矩阵均通过。
   真实 musl source 在 O3 才出现 failure，说明当前证据不能把“任意一个 pointer-return call”称为
   充分触发条件。

## 独立结论

worker 交付完成了任务要求的诊断矩阵和 raw evidence，且正确区分了两类 failure：

- 默认 O3、保留 sibling tail call：`LowerCall emitted a return value for a tail call`，且 integer
  与 pointer 均可触发；
- no-tail O3 真实 representative：MachineVerifier 报告的 undefined `$rb31`，其 raw machine
  block 同时显示 CALL 的 `implicit-def dead $rd31`。

因此本交付接受，但带上述证据边界 findings。RB31/RD31 mismatch 可作为下一步 CodeGen
regression/debug 的候选入口，不能在本任务结论中升级为已证实根因；也不能把 frontend/asm/单个
llc 成功当作 libc/runtime 验收。
