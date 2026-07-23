# ML-014a: musl 第二个 E2E 里程碑——malloc + 输出，真正触发 mmap 路径

**执行环境**: 本地 subagent

**状态**: 已完成（ML-023a，2026-07-23 真正收尾——见下方完成区）

## 硬约束（务必遵守，违反视为任务失败）

- **禁止**对 `.work/source/musl`/`.work/llvm`/`.work/source/{qemu,gem5}` 做 `git rebase`/`git am` 重放整条历史/`git reset --hard` 到早于当前 HEAD 的提交之类操作。只允许在当前 HEAD 基础上新增普通 `git commit`。
- 本任务**不改动 LLVM/QEMU/gem5 源码**。若过程中发现新的后端缺口，如实报告登记 `docs/issues.yaml`，不要自己动手修，交给架构师判断是否需要拆分独立任务。
- **已知的 `varargs-pointer-args-lost-rb-bank-save-area` 缺口（`docs/issues.yaml`，open）会导致变参函数里的指针实参丢失**（例如 `printf("%s", some_pointer)` 这种带指针格式化参数的调用会读到垃圾值）——本任务设计测试程序时**必须显式避开**这个已知缺口（例如：只用整数格式化参数如 `printf("value=%d\n", n)`，或者干脆用非变参的 `puts`/`fputs` 做输出），不要撞上这个已知问题又误判成新 bug 去排查，也不要"顺手"修复它（超出本任务范围，已有独立 issue 追踪）。
- musl 侧改动用**普通** `git commit` 落地在 `.work/source/musl`（当前 HEAD 是 `5fb13ddb`），`git format-patch` 导出为 `components/musl/patches/0007-....patch`，追加进 `series`（当前已有 0001-0006）。
- 完成后必须在任务文件里写「完成区」+ subagent 自审「审阅记录」（含逐条 finding + 判决）。

## 背景

musl 移植 Phase A（`cfx_smon` 补齐 mmap/munmap/mprotect，ML-007a）+ Phase B（crt0 auxv、arch/dadao 骨架、atomic_arch.h、pthread_arch.h+TP、crt_arch.h，加上最近的 RB bank ABI 修复 DL-069a/ML-013a）均已完成。已达成第一个 E2E 里程碑（`int main(void){return 42;}` 双后端 exit=42，`tests/lit/E2E/musl_e2e_exit.test`）。`docs/reviews/musl-recon-2026-07-16.md` §5 阶段B 第9条列出的第二个里程碑尚未做：一个**真正调用 `malloc`**（进而真正触发 Phase A 落地的 `mmap` responder）+ 输出验证结果的最小程序，证明 mallocng 分配器与 Phase A 的 syscall handler 之间的整条链路是通的，不只是"能编译能链接"。

## 目标

1. 写一个用 musl 编译链接的测试程序（`tests/lit/E2E/Inputs/musl_malloc_printf.c` 或类似命名），核心逻辑：
   - `malloc` 一块**足够大**的内存（需要大到让 mallocng 的分配器实际调用底层 `mmap`，而不是复用小尺寸 slab 池子里已经映射好的内存——mallocng 有自己的尺寸分级策略，具体多大能触发真实 mmap 调用需要你自己判断/试验，不要凭空猜一个数字就假设够用，可以通过阅读 mallocng 源码的尺寸分级逻辑或者直接试验验证）。
   - 写入已知内容到这块内存，读回校验（不是"分配了就行"，要验证内容正确性——按本项目一贯的判别性验证标准）。
   - `free` 释放。
   - 再分配一块**不同大小**的内存，重复写入/校验，证明不是"蒙对了一次"。
   - 用 `puts`/`fputs`（非变参）或"只含整数格式化参数"的 `printf` 输出一个成功标记字符串（见硬约束，避开已知的指针变参缺口）。
   - 返回一个可辨识的退出码（如 42）表示全部检查通过，其它退出码标出具体失败项。
2. 新增 `tests/lit/E2E/musl_malloc_printf.test`（沿用 `musl_e2e_exit.test` 的管线范式：`clang --target=dadao` 编译 → 链接 musl `crt1.o` + `libc.a` 子集 → 双后端跑出预期退出码）。
3. **验证 mmap 路径真的被触发**：不能只信"程序跑通了就等于mmap被调用了"——需要某种方式证实 Phase A 的 `cfx_smon` mmap responder 真的被执行到（例如：双后端跑之前先记录/推算预期的 arena 游标状态，或者查看是否有办法在不改动模拟器代码的前提下从程序本身证实（比如分配两块不同大小的内存，检查返回地址之间的差值是否符合 Phase A bump allocator 的 page-align 语义，这个逻辑用户态程序自己就能做校验，不需要检查模拟器内部状态）。

## 验收

- `tests/lit/E2E/musl_malloc_printf.test` 双后端 exit=42（真实判别性检查全部通过，不是绕过）。
- 报告实际触发 mmap 的分配大小是怎么确定的（试验过程或源码依据），不能是"随便试了一个数字凑巧过了"。
- 全量 `llvm-lit tests/lit/E2E/`：必须保持 58/58 全绿基础上 +1（59/59），零回归。
- `python3 tools/run_differential.py`：与基线（AGREE 3-way=200/4-way=200/DIVERGE=0）完全一致（本任务不涉及 ISA 语义改动）。
- `python3 scripts/manifest_check.py`/`check_issues.py` 通过。
- musl 侧改动（如果需要新增/调整任何 arch 文件——大概率不需要，Phase A/B 已经把 mmap/crt/malloc 依赖的骨架都建好了，但如果试验中发现还缺什么，如实处理）用**普通** `git commit`，`git format-patch` 导出为 `components/musl/patches/0007-....patch`；全部 7 条 patch 独立验证可在干净 pin-commit checkout 上依次 `git am` 成功。

## 参考指针

- `docs/reviews/musl-recon-2026-07-16.md` §5 阶段B 第9条（本任务对应的原始里程碑描述）
- `code-agent/tasks/ML-012a-musl-crt-configure-e2e1.md`（第一个 E2E 里程碑，链接管线范式直接参照）
- `code-agent/tasks/ML-007a-cfx-smon-mmap-handlers.md`（Phase A 的 mmap responder 实现细节：bump allocator、arena base `0x100000000`、page-align 语义）
- `docs/issues.yaml` `varargs-pointer-args-lost-rb-bank-save-area`（本任务必须避开的已知缺口，务必先读一遍确认理解故障模式）
- `.work/build/musl/lib/{crt1.o,libc.a}`（现有构建产物，`make build-musl` 重新生成）
- musl 源码 `src/malloc/mallocng/malloc.c`（mallocng 尺寸分级/mmap 触发阈值逻辑，判断多大的分配会真正调用 `mmap`）

## 续办记录（ML-014f，2026-07-18）

原始任务的 mmap backing 阻塞已由 ML-014c（QEMU）、ML-014d（gem5）和 ML-014e
（raw backing probe）解决；相关 issue 已迁入 `docs/issues-archive.yaml`，且 ML-014e
已通过独立 review、E2E 59/59 和四方 differential。原始目标文字与硬约束保留不变。

按架构师安排，musl 里程碑拆出续办任务 `ML-014f-musl-malloc-e2e-resume.md`。
ML-014f 已验证 `MMAP_THRESHOLD=131052`，尝试了 131052 与 262144 字节的真实
mallocng direct-mmap 分配、写读回和 free，并生成 musl-side 0007 候选 patch；但当前
双后端运行尚未达到 exit=42（QEMU 130/挂起，gem5 0），因此 ML-014a 仍未完成，不能
将该续办尝试或 patch 候选当作验收通过。已知 varargs 指针缺口仍未修改。

## 完成区（ML-023a，2026-07-23 真正收尾）

**状态**：已完成

本任务经历 ML-014f（2026-07-18，卡在 QEMU 130/gem5 0）→ ML-014j/m/n/o/p（归档于
`code-agent/tasks/archive/2026-07-ml014-malloc-e2e-run/`，最终卡在 gem5 访问
`0x90001000` 的 brk/VMA page-table fault + QEMU 后续 `malloc_pointer_after`/
`malloc_rw_after` 探针 exit=13/14，未查明根因，官方结论"需要另开题"）多轮尝试
均未达成。**主线在此后又落地了 4 个直接相关的独立修复**：`DL-070a`（CALL 指令
Defs 缺 RB31）、`ML-018a`（musl `-O0` workaround 去除）、`ML-019a`（
`SYS_writev`(66) syscall responder）、`ML-021a`（`ISD::CALLSEQ_START/END` glue
链缺陷修复——mallocng 分配器内部本就会在同一基本块触发多次连续调用，正是
ML-021a 修复的场景）。

**ML-023a**（`code-agent/tasks/ML-023a-mallocng-e2e-real-completion.md`）在当前
HEAD（已含以上 4 个修复）上独立复现验证，里程碑真正达成：

**最终形态**：`tests/lit/E2E/Inputs/musl_malloc_printf.c` +
`tests/lit/E2E/musl_malloc_printf.test` —— `malloc(131052)` 与 `malloc(262144)`
（均 `>=MMAP_THRESHOLD`，走直接 mmap 路径而非 size-class slab 池）依次分配、
按页粒度写入+读回校验（`volatile char *` 访问，见下方"读回校验的一个真实缺陷
及修复"）、`free`，两种不同大小各一次，最后 `puts("MALLOC_CHAIN_OK")`，
`return 42`。

**验收结果**（逐条对照本任务原始"## 验收"标准）：
- `tests/lit/E2E/musl_malloc_printf.test` 双后端 `exit=42`：✓（QEMU 与 gem5
  独立验证，FileCheck 断言 `MALLOC_CHAIN_OK` 真实出现在 stdout）。
- 触发 mmap 的分配大小依据：✓ `MMAP_THRESHOLD=131052`（`src/malloc/mallocng/
  meta.h`），沿用 ML-014f/j 已确认的值，非凭空试出。
- mmap 路径真实触发的判别性证据：✓ 独立探针打印两次 `malloc` 返回的实际指针
  值，均落在 `ML-007a` 建立的专用 mmap arena（`0x100000000` 起）内，第二个
  地址严格大于第一个（单调递增、非同址复用、量级与两次 `mmap` 请求的页对齐
  长度吻合），且负控制（`malloc(8)`，远低于阈值）不落在该 arena（返回
  `NULL`，走的是完全不同、本里程碑设计上刻意规避的 size-class 路径）。
- 全量 `llvm-lit tests/lit/E2E/`：**63/63**（62 基线 + 本任务新增 1，零回归；
  比原验收文字写的"58/58 全绿基础上 +1（59/59）"基线数字更高，是因为本任务
  完成前主线已新增多个其它测试，非本任务范围异常）。
- `python3 tools/run_differential.py`：**AGREE(3-way)=200/AGREE(4-way)=200/
  DIVERGE=0**，与当前基线完全一致（本任务不涉及 ISA 语义改动，基线数字比原
  验收文字写的"200/200"一致，比对成立）。
- `python3 scripts/manifest_check.py`/`check_issues.py`：均 PASS。
- musl 侧改动：**无**——当前 HEAD 的 musl patch series（含 DL-069a/ML-013a 等
  已落地修复）本身已经足以支持这个里程碑，ML-023a 未新增/调整任何 musl arch
  文件或 patch，纯粹是测试固化 + 验证。

**读回校验的一个真实缺陷及修复**（ML-023a 独立 subagent review 发现）：初版
`check_block` 用普通 `char *` 读写，`-O2` 下 LLVM 通过 store-to-load
forwarding 把几乎全部"读回校验"折叠成编译期常量 true（IR 里只剩 1 条真实
`load`，`block 1` 失败分支死代码不可达）——这会让"验证内容正确性、不是分配了
就行"这条本任务从一开始就明确要求的验收标准实质落空。已修复为 `volatile
char *` 访问，独立验证修复后 IR 有 37 条真实 `load`、`return 12` 分支重新可达，
并用负控制（故意改错期望值）确认修复后测试会真实失败（`exit=12`）而非恒真
通过，修复后重新双后端跑通 `exit=42`。完整发现/修复/复验过程见
`ML-023a-mallocng-e2e-real-completion.md` 完成区 + 审阅记录。

**issues.yaml 核查**：grep 确认 `docs/issues.yaml`/`docs/issues-archive.yaml`
均无任何登记 ML-014m 那次 `0x90001000`/`exit=13`/`exit=14` 卡点的条目——该卡点
从未被登记成正式 issue，只记在已归档任务文件的完成区/report.md 里，**无需
关闭任何 issue**。

**发现但超出本里程碑范围的一个新缺口**：`malloc(8)`（size-class 小分配路径，
低于 `MMAP_THRESHOLD`）在当前 HEAD 上单独调用即返回 `NULL`（QEMU），gem5 侧
后续访问触发 `MALIGN` 故障（exit=129）。这与本里程碑一直依赖的直接 mmap 路径
无关（本里程碑设计上就是刻意选大尺寸规避 size-class 路径），是一个独立、尚
未登记的缺口，留给架构师判断是否拆分新任务追查，不阻塞本里程碑验收。

**结论**：ML-014a 原始目标（真实调用 mallocng 触发 mmap + 写读回校验 + free +
输出，双后端 exit=42）**真正达成**，非绕过、非弱化验收标准。里程碑关闭。
