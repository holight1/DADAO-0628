# ML-006a: musl 移植调研（迈向 gcc-c-torture 全量通过的前置）

**执行环境**: 本地 subagent（调研，非实现——产出报告，不写代码）

**状态**: 待执行

**前置**：ADR-0014（libc/syscall charter，D5：picolibc 阶段1→musl 阶段2）；ADR-0012 D5（终极目标=gcc-c-torture 全量通过，用户 2026-07-16 定；结论：达到旧工具链 `~/toolchain/llvm-unicore` 同等覆盖率大概率需要 musl，不是 picolibc）；`tests/lit/E2E/llvm-test-suite/` 目前 23/23 全通过（无 libc I/O 的纯计算子集）。

## 背景

用户终极目标是 C 全量测试（以 gcc-c-torture 为基准）通过，不通过的要有明确合理理由。ADR-0012 D5 已经判断达到这个目标需要 musl（picolibc 阶段1的 scope 本来就不打算覆盖 gcc-c-torture 需要的完整 hosted libc 表面）。`~/toolchain/DADAO`（已归档）曾经跑过真实 musl 移植（`~/toolchain/musl`、`~/toolchain/DADAO/DADAO-testset/testset-llvm-testsuite.mk` 等），达到 gcc-c-torture 1617/1708 通过。

**本任务是调研/规划，不是实现**——产出一份"musl 移植路线图"报告，供架构师规划后续实现任务，本任务本身不写 musl 移植代码，也不改 DADAO-0628 任何源码（除了产出报告文档）。

## 做什么

1. **调研旧 musl 移植**（`~/toolchain/musl`、`~/toolchain/DADAO` 里跟 musl 相关的部分）：搞清楚旧工具链的 musl 移植做了什么层面的适配——`arch/dadao/` 目录结构、syscall 表映射方式、crt 启动代码、有没有踩过特别的坑（对照 memory/ADR-0014 已经提到的"musl 现在上是早的：syscall 面不够（malloc 要 mmap、__init_libc 要 TLS/线程指针）"）。**只看结论/坑，不建议直接照抄代码**（DADAO-0628 是 greenfield 重建，ABI/syscall 约定可能和旧工具链不同——ADR-0014 D2 定的 syscall ABI 是`本 ADR 定，wiki 未定义`，需要核对是否和旧工具链一致）。
2. **核对 DADAO-0628 当前 syscall 面**（`tests/scripts/pico_stubs.s`、QEMU/gem5 的 `cfx_smon` responder 实现，`docs/adr/0014-libc-syscall-charter.md`）能覆盖 musl `arch/<target>/` 移植通常需要的最小 syscall 集合（`brk`/`write`/`exit`/`mmap`/`munmap`/`clone`/`set_tid_address`/`futex`/... musl 的 `__init_libc`/TLS 初始化具体需要哪些，需要查 musl 源码或 musl 移植文档确认）——列出当前**缺口**（哪些 syscall 还没有 cfx_smon handler）。
3. **调研 DADAO-0628 的 ABI/ELF 现状是否满足 musl 构建要求**：TLS 模型（musl 需要某种 TLS，DADAO M1 spec 有没有线程指针寄存器约定？）、动态链接需求（musl 静态构建应该不需要，但要确认 DADAO-0628 目标是静态链接 musl，参照 ADR-0014 的"crt 用现有 crt0.s"）。
4. **产出报告**（放 `docs/reviews/musl-recon-2026-07-16.md` 或类似路径，参照 `docs/reviews/musl-recon-2026-07.md`——ML-001a 已有的调研报告，本次是它的后续/更新，不是重复）：
   - 当前 syscall 面缺口清单（对照 musl `arch/generic`/`arch/<最相近现有移植>` 需要的最小集合）
   - TLS/线程指针需求 vs DADAO M1 spec 现状
   - 建议的移植阶段划分（比如：静态单线程程序先行→ TLS/多线程后置，如果这样分阶段可行）
   - 对 syscall ABI（ADR-0014 D2 定的）是否需要扩展/调整的判断
   - 粗略的工作量/风险评估（不需要精确，给架构师一个"这是几个任务还是几十个任务"级别的量级判断）

## 约束

- **纯调研，不写 DADAO-0628 的实现代码**（不碰 `.work/llvm`、`.work/qemu`、`.work/gem5`、`tests/scripts/` 等任何源码）。
- 引用旧工具链时只取"结论/坑"，不要建议直接复制代码（greenfield 原则）。
- 报告要给出**可执行的下一步任务清单建议**（哪怕只是"任务1：实现 mmap syscall handler"这种级别），不要只是泛泛而谈。

## 验收（架构师亲跑）

- 报告文件存在、结构清晰，覆盖上面 4 点。
- 报告里的"syscall 缺口清单"要有具体依据（引用 musl 源码里对应 arch 移植文件需要哪些 syscall，不能凭空列）。
- 不涉及任何代码改动（`git status` 应该只有新增的报告文件，没有源码变更）。

## 参考指针

- `docs/adr/0014-libc-syscall-charter.md`（现有 syscall ABI charter）
- `docs/reviews/musl-recon-2026-07.md`（ML-001a 的早期调研，本次是后续/深化）
- `~/toolchain/musl`、`~/toolchain/DADAO/DADAO-testset/testset-llvm-testsuite.mk`（旧工具链的 musl 移植，只取结论）
- `tests/scripts/pico_stubs.s`（当前 syscall 面现状）
- `docs/adr/0012-test-tiering-strategy.md` D5（本次调研的动机）

—— 自审见 DS.md §自审流程同等标准（subagent 自己复核，逐条 finding + 判决）。**这是调研任务，判决标准是报告的完整性/依据充分性，不是代码正确性**。
