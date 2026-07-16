# ML-006a: musl 移植调研（迈向 gcc-c-torture 全量通过的前置）

**执行环境**: 本地 subagent（调研，非实现——产出报告，不写代码）

**状态**: 通过（架构师复核，报告质量良好；复核过程中意外发现并修复一个严重的、独立的基础设施缺陷——见完成区）

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

---

## 架构师复核（2026-07-16，ground-truth）：通过，含重大独立发现

### 报告质量核实
- 抽查关键结论：`contracts/abi/spec.md` §1.2 确认 `rb4=rbtp`；`DADAORegisterInfo.cpp` 确认 `Reserved.set(DADAO::RB4)`——均属实。
- 报告纯文档产出，`git status` 确认无源码改动，遵守约束。
- 报告结构完整、有具体依据（引用 musl 源码文件/行为，非空泛），阶段划分/任务量级估计合理，可直接供后续任务拆分参照。

### ⚠️ 复核过程中意外发现的严重独立问题（与本任务本身无关，但在核实报告引用的 QEMU 源码时发现）
核对报告 §2.1"逐行核对源码"的 QEMU cfx_smon responder 时，发现 **`.work/source/qemu/target/dadao/` 整个目录已经不存在**——`git log` 显示 HEAD 落在裸上游提交 `7c949c5`（QEMU v10.0.0 release，无任何 DADAO patch）。追查 `git reflog`：`HEAD@{0}: checkout: moving from a26e252(...)to 385b0a7d(...)`——即 `scripts/fetch.py` 的 `git checkout --detach <pinned commit>` 曾把一个**已应用全部 16 个 patch、干净提交**的工作树强制切回裸 pin 点，**静默丢弃了 16 个 patch 对应的全部提交**（可能是 ML-004a 添加 llvm-test-suite 组件后重跑 `make fetch` 时触发——`fetch.py` 对所有 enabled 组件一视同仁地做这个 checkout，不止新组件）。

**根因**：`fetch.py` 只检查工作树是否"dirty"（未提交改动），不检查 HEAD 是否已经是"pin 点+已应用 patch 提交"的下游——只要没有未提交改动，无论 HEAD 已经跑到哪里，都会被强制 `checkout --detach` 回裸 pin commit。这是一个**真实的、独立于 ML-006a 任务本身的基础设施缺陷**，很可能也是更早 DL-068a 事故（`.work/llvm` 被"重建"到面目全非）的根本诱因——那次 subagent 大概率是撞见了同样被 `fetch.py` 意外重置的 `.work/llvm`，误以为要"重建 patch series"来恢复，反而越修越乱。

**处置**：
1. `git reflog` 定位到丢失前的最后一个提交 `a26e252428418ab629c4115ab1396075bcfcdbab`（对应 patch 0016，"ML-003m align brk_base"，与 `components/qemu/patches/series` 里最后一条完全吻合），确认该 commit object 仍存在（未被 GC）。
2. `git reset --hard a26e252428418ab629c4115ab1396075bcfcdbab` 恢复 `.work/source/qemu`，验证 `target/dadao/` 目录及内容（`cfxcode==2`/`dadao_cpu_do_interrupt` 等）恢复。
3. 顺带检查 `.work/source/gem5`：reflog 显示它从建仓起就只是裸 clone+checkout（从未有过任何 patch 提交记录），说明 gem5 的实际开发/patch 应用一直只发生在独立仓库 `~/DADAO-gem5`（本身有独立 git 历史，不受 `.work/source/gem5` 影响），这不是本次事故的一部分，是既有的、正常的架构（gem5 组件在 `manifests/components.lock.toml` 里"enabled"更多是占位/未来对齐用途）。
4. **修复根因**：`scripts/fetch.py` 增加"HEAD 是否已经以 pin commit 为祖先"的判断（`git merge-base --is-ancestor`）——如果是（说明 patch 已应用在其上），直接跳过、不做任何 checkout；只有真正需要初始化/对齐的场景才执行 checkout。已用真实场景验证：重跑 `python3 scripts/fetch.py`，`llvm`/`qemu` 均正确判定"已有 patch，不动"，`gem5`/`llvm-test-suite`（本来就在 pin 点）判定"已在目标点"。
5. 全套回归：`llvm-lit tests/lit/E2E/` 54/54、四方 AGREE(3-way)=200/Sail AGREE(4-way)=200、`manifest_check.py` PASS，恢复后无任何行为变化（因为二进制本来就是修复前构建的，从未被这次 QEMU 源码丢失影响——只是源码这次侥幸没被拿去重新构建）。

**这是一个比 ML-006a 任务本身更重要的发现**：如果没有这次顺手核对源码，`.work/source/qemu` 的历史会一直悄悄处于"裸上游、无 DADAO patch"的状态，直到某次真正需要从源码重建 QEMU 时才会爆炸性地暴露（那时候可能已经忘记具体是哪个提交丢的，恢复会难得多）。`fetch.py` 的修复让这类事故不会再发生。

**判定**：通过，提交（含 `scripts/fetch.py` 根因修复 + `.work/source/qemu` 数据恢复）。
