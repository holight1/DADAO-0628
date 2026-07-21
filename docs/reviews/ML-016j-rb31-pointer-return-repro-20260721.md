# ML-016j RB31 pointer-return / CALL defs 最小复现 review

日期：2026-07-21  
状态：worker complete；仅诊断，待独立 review。

## 结论

RB31 目前仍是高价值候选，不是已证实根因。

真实 musl representative 在 O3、禁用 sibling tail call 后稳定进入 MachineVerifier/Greedy RA failure：CALL 指令的 machine-code dump 只显示 `implicit-def dead $rd31`，而 call result 路径随后读取 `$rb31`。这与“pointer return 使用 RB31、CALL defs 使用 RD31”的候选机制一致；但本任务的 direct/indirect/nested 最小 pointer-return probe 在同样的 O0/O3 条件下全部成功，不能把 representative 现象升级为最小机制已证实。

默认 O3 还存在一个独立的 tail-call assertion：立即返回 call result 的 pointer-return 和 integer-return 都触发 `LowerCallTo` 的 `LowerCall emitted a return value for a tail call`。因此 pointer 类型不是该 assertion 的必要条件，不能用默认 O3 的失败直接证明 RB31。

## 运行配置与证据保存

使用仓库内现成的 DADAO LLVM 22.1.8 assertions build：

```text
clang = /home/holight/DADAO-0628/.work/build/llvm/bin/clang
llc   = /home/holight/DADAO-0628/.work/build/llvm/bin/llc
target = dadao
```

主脚本为 [`run-matrix.sh`](/tmp/ml-016j-rb31-pointer-return-repro-20260721/run-matrix.sh)，真实 representative 脚本为 [`run-representatives.sh`](/tmp/ml-016j-rb31-pointer-return-repro-20260721/run-representatives.sh)。每个命令都有单独的 `.argv`、`.rc`、`.stdout`、`.stderr`；成功后端输出保存在 asm 目录，失败后端的原始 machine-code block 既保留在完整 stderr，也抽取到 `raw-machine/` 便于只读扫描。

主矩阵的逐项汇总是 [`results/summary.tsv`](/tmp/ml-016j-rb31-pointer-return-repro-20260721/results/summary.tsv)，寄存器引用扫描是 [`results/asm-register-scan.tsv`](/tmp/ml-016j-rb31-pointer-return-repro-20260721/results/asm-register-scan.tsv)。默认 sibling-tail-call 的原始变体完整保存在 [`variant-tail-call/`](/tmp/ml-016j-rb31-pointer-return-repro-20260721/variant-tail-call/)，其汇总是 [`variant-tail-call/results/summary.tsv`](/tmp/ml-016j-rb31-pointer-return-repro-20260721/variant-tail-call/results/summary.tsv)。

## 最小 C/IR 矩阵

probe source 在 [`probes/c/`](/tmp/ml-016j-rb31-pointer-return-repro-20260721/probes/c)，frontend IR 在 [`probes/ir/`](/tmp/ml-016j-rb31-pointer-return-repro-20260721/probes/ir)，clang/llc asm 分别在 [`probes/asm/clang/`](/tmp/ml-016j-rb31-pointer-return-repro-20260721/probes/asm/clang) 和 [`probes/asm/llc/`](/tmp/ml-016j-rb31-pointer-return-repro-20260721/probes/asm/llc)。主矩阵为 O0/O3 加 `-fno-optimize-sibling-calls`，以便让 call-return 形状到达后端而不被 tail-call assertion 抢先终止。

| 阶段 | 命令数 | rc=0 | 非零 rc |
|---|---:|---:|---:|
| frontend IR，15 probes × O0/O3 | 30 | 30 | 0 |
| clang 直接 asm，15 probes × O0/O3 | 30 | 30 | 0 |
| llc asm，15 probes × O0/O3 | 30 | 30 | 0 |

覆盖的形状包括：

- `direct_ptr_return`、`direct_ptr_arg_return`、`indirect_ptr_return`、`nested_ptr_return`；
- `direct_ptr_use`（返回值立即 load）；`direct_ptr_save_across_call` 和 `indirect_ptr_save_across_call`（返回值保存并跨越后续 call）；
- `direct_int_return`、`direct_int_save_across_call`、`indirect_int_return`、`nested_int_return`；
- `ptr_identity`、`int_identity` 成功对照；
- 简化的 `representative_posix_memalign`（integer return + pointer output argument）和 `representative_memmem`（pointer return）。

主矩阵没有观察到 verifier error，也没有 pointer-only 与 integer-only 的 rc 分叉。代表性 O3 asm 例如：

- [`direct_ptr_return.O3.s`](/tmp/ml-016j-rb31-pointer-return-repro-20260721/probes/asm/clang/direct_ptr_return.O3.s) 为 call 后直接 return；
- [`nested_ptr_return.O3.s`](/tmp/ml-016j-rb31-pointer-return-repro-20260721/probes/asm/clang/nested_ptr_return.O3.s) 显示第一次 pointer call 结果经 `rb31` 读出并作为下一次 pointer call 参数；
- [`direct_ptr_save_across_call.O3.s`](/tmp/ml-016j-rb31-pointer-return-repro-20260721/probes/asm/clang/direct_ptr_save_across_call.O3.s) 显示 pointer result 保存后跨越 `consume_ptr` 再返回。

## 默认 O3 tail-call 变体

第一轮保留了不加 `-fno-optimize-sibling-calls` 的完整原始输出，见 [`variant-tail-call/`](/tmp/ml-016j-rb31-pointer-return-repro-20260721/variant-tail-call/)。统计为 frontend 30/30 成功；clang 21/30 成功、9/30 `rc=1`；llc 21/30 成功、9/30 `rc=134`。

O3 失败集合为 `direct_ptr_return`、`direct_ptr_arg_return`、`indirect_ptr_return`、`nested_ptr_return`、`direct_int_return`、`indirect_int_return`、`nested_int_return` 及两个简化 representative。所有失败 stderr 的首个共同诊断是：

```text
Assertion `(!CLI.IsTailCall || InVals.empty()) &&
"LowerCall emitted a return value for a tail call!"` failed.
```

`direct_ptr_use`、两个 save-across-call probe、`ptr_identity`、`int_identity` 等不触发该 assertion。这个对照证明默认 O3 tail-call lowering 是独立边界；它不等于 `$rb31` undefined verifier，也不能被归因到 pointer return。

## 真实 musl representative 对照

真实只读 source 副本位于 [`probes/representatives/c/`](/tmp/ml-016j-rb31-pointer-return-repro-20260721/probes/representatives/c)，来自既有隔离 source snapshot；未修改该 snapshot。完整逐项结果在 [`results/representatives-summary.tsv`](/tmp/ml-016j-rb31-pointer-return-repro-20260721/results/representatives-summary.tsv)。

| representative | 阶段 | O0 | O3 |
|---|---|---:|---:|
| `posix_memalign.c` | frontend IR | 0 | 0 |
|  | clang backend | 0 | 1 |
|  | llc backend | 0 | 134 |
| `memmem.c` | frontend IR | 0 | 0 |
|  | clang backend | 0 | 1 |
|  | llc backend | 0 | 134 |

O3 的原始 backend stderr：

- [`clang.posix_memalign.O3.stderr`](/tmp/ml-016j-rb31-pointer-return-repro-20260721/logs/representatives/clang.posix_memalign.O3.stderr) 与 [`llc.posix_memalign.O3.stderr`](/tmp/ml-016j-rb31-pointer-return-repro-20260721/logs/representatives/llc.posix_memalign.O3.stderr)；
- [`clang.memmem.O3.stderr`](/tmp/ml-016j-rb31-pointer-return-repro-20260721/logs/representatives/clang.memmem.O3.stderr) 与 [`llc.memmem.O3.stderr`](/tmp/ml-016j-rb31-pointer-return-repro-20260721/logs/representatives/llc.memmem.O3.stderr)。

machine-code dump 的只读抽取和 CALL-def 扫描在 [`probes/representatives/asm/raw-machine/`](/tmp/ml-016j-rb31-pointer-return-repro-20260721/probes/representatives/asm/raw-machine) 与 [`results/representatives-call-def-scan.tsv`](/tmp/ml-016j-rb31-pointer-return-repro-20260721/results/representatives-call-def-scan.tsv)：

| representative | O3 CALL 行 | `implicit-def ... $rd31` | `$rb31` COPY | verifier errors |
|---|---:|---:|---:|---:|
| `posix_memalign` | 2 | 2 | 2 | 2 |
| `memmem` | 5 | 5 | 6 | 5 |

`posix_memalign` 的关键原始片段是：

```text
CALL_IIII @aligned_alloc, ..., implicit-def dead $rd31, ...
%9:gprd = COPY $rb31
...
CALL_IIII @___errno_location, ..., implicit-def dead $rd31
%11:gprd = COPY killed $rb31
```

`memmem` 同样在 `memchr`、短 needle helper 和 `twoway_memmem` 的结果路径出现 `COPY $rb31`，而对应 CALL 行的 defs 是 `$rd31`。这确认真实 representative 与原始 16-object verifier 记录是同一类 machine-code 形状；它仍然没有证明所有 16 个对象只有这一个原因。

对照也很重要：简化 `representative_posix_memalign.c` 和 `representative_memmem.c` 在主 no-tail 矩阵中全通过，而真实 musl source 在 O3 失败。复杂控制流、多次调用、结果活跃区间和 RA pressure 是当前仍未隔离的必要条件，不能把“一个 pointer-return call”单独称为充分触发器。

## 判定与后续边界

当前判定：

1. RB31/RD31 mismatch 是真实 verifier dump 支持的候选机制；证据强于单纯错误字符串，但最小 direct/indirect/nested pointer-return 还没有复现 verifier，因此仍是候选。
2. 默认 O3 tail-call assertion 是另一个已复现、且同时覆盖 integer-return 的后端边界，不能并入 RB31 结论。
3. O0 successful asm 不能升级为 ABI/runtime 验收；它只说明本次 O0 路径没有在当前阶段报告 verifier failure。

下一步最小 CodeGen regression 应至少固定：

- 一个 no-tail 单 direct pointer-return 成功对照、一个 nested pointer call 成功对照，以及一个含分支和两次 pointer-return CALL 的 `posix_memalign` 形状；
- 一个 integer-return 同构 probe，确保 tail-call 或 CALL-def 修复不会被误判为 pointer-only；
- MachineVerifier 前的 raw machine code，分别断言 CALL 的 implicit defs、return convention、call-result copy 的 bank 和 live range；
- O0/O3 与 sibling-tail-call enabled/disabled 四象限，避免把 tail-call assertion 和 RB31 verifier 合并。

本任务不修改 calling convention、TableGen、CALL defs、regmask 或 liveness 实现，也不提交测试变更。
