# ML-016x：`_Exit`/syscall 栈对齐最小复现与归因

日期：2026-07-21

## 目标

围绕 ML-016w 的 MALIGN `rc=129` 结论，建立可审计、可独立复跑的最小证据，确认：

1. musl `src/exit/_Exit.c`、`arch/dadao/syscall_arch.h` 与启动/退出调用链的实际形状；
2. 直接 `__syscall1`、`_Exit`、有/无返回值包装、显式 `trap` fixture 分别在哪一级
   prologue/stack adjustment 破坏 8-byte ABI 对齐；
3. 修复应归属 musl syscall wrapper、DADAO frame lowering 还是测试 launcher。

## 范围

- 只读检查 `.work/source/musl`、`.work/source/llvm`、ABI 契约、ML-016w/ML-016v/ML-016u
  既有证据。
- include-free C、LLVM IR、DADAO 汇编探针；使用仓库 LLVM、`ld.lld`、标准 linker script、
  QEMU 和 Gem5 入口。
- 所有 probe、日志、对象、ELF/BIN、MIR 和 hash 仅写入：
  `/tmp/ml-016x-exit-syscall-frame-repro-20260721/`。
- 仓库内只允许本任务文件和对应 review 报告发生写入。

明确不做：不修改 `.work/source/llvm`、`.work/source/musl`、musl archive、QEMU/Gem5、
测试、ABI/spec、launcher 或生产修复；不查阅或引用 `~/toolchain`、`~/knowledge-graph`。

## 验收标准

- [x] 记录 musl `_Exit`、syscall、startup/exit 路径及 source hash。
- [x] include-free C/IR/汇编 probe 保存源、argv、stdout/stderr、rc、产物和 SHA-256。
- [x] 至少有一个直接 syscall/trap 成功对照和一个 `-4` 对齐失败对照，并在 QEMU/Gem5
  双后端复跑。
- [x] exact ML-016u `_Exit.o` 的 hash、MIR `stackSize` 和对齐 caller 的双后端结果可复核。
- [x] 报告事实/推断分栏，明确与 ML-016w 的关系、修复归属和未决风险。
- [x] 不实现生产修复。

## 状态

**Audit-accepted-with-findings / diagnosis only / no production fix**（2026-07-21）。

独立 review：[`ML-016x-independent-review-20260721.md`](../../docs/reviews/ML-016x-independent-review-20260721.md)。
无阻塞 finding；已修正 QEMU faulting-store wording，并补入复跑 launcher hash。

关键结论与完整证据索引见：
[`docs/reviews/ML-016x-exit-syscall-frame-repro-20260721.md`](../../docs/reviews/ML-016x-exit-syscall-frame-repro-20260721.md)。
