# ML-016z：final-head varargs provenance blocking findings 修复

日期：2026-07-21

## 目标

在 nested LLVM 最终 clean HEAD
`d3bd9c15434fd7a48c0b7bab87354778cd932a72` 上重新生成 ML-016y varargs 的
compile/link/runtime 证据，闭合独立 review 的 B1/B2。不得回退并行改动；不得修改
`.work/source/llvm`、musl、QEMU/Gem5、spec、launcher、LLVM regression 或 tracker。

## 验收

- 记录 nested HEAD、status、production/test source SHA-256，并新增不覆盖历史证据的
  `final-head-source-manifest-20260721.txt`。
- 用 final clang/llc 重新生成 varargs IR、MIR、assembly、object；link crt0、objcopy、
  disasm；每条命令保留 argv/stdout/stderr/rc 和 hash。
- 用同一 ML-016v trampoline 在 QEMU/Gem5 运行 final-head ELF。正常 varargs 期望
  两端 rc=0；odd/padding=4 仅做静态边界 probe，不能将不安全形状伪造为 runtime 通过。
- 对 `direct_syscall1`、`wrapper_noreturn`、`exit_shape` 做 final-tool 静态 provenance
  绑定，不重跑已通过的完整矩阵。
- 只新增本 task 与对应 report；不提交 nested LLVM commit。

## 结果

完成结果和全部原始证据见：
`docs/reviews/ML-016z-final-head-varargs-provenance-20260721.md`，证据目录为
`/tmp/ml-016z-final-head-varargs-provenance-20260721/`。

状态：**Audit-accepted-with-findings**。独立 review 已确认 B1/B2 闭合、无阻塞 finding；
非阻塞项是缺少链路结束后的 nested status 日志，以及应明确 QEMU 使用 launcher、Gem5
直接加载 ELF。后者已修正文案；完整 LLVM suite/odd runtime 仍未宣称通过。
