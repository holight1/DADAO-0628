# ADR-0012: 测试分层与运行时机策略（T0–T3 + QEMU/gem5 分工）

**状态**：Accepted（2026-07-12）
**日期**：2026-07-12
**关联**：ADR-0007（测试方法论·向量设计原则）、ADR-0009（验证链·四方差分）、ADR-0010（gem5 功能第二参考）、ADR-0011（Sail 第 4 参考）

---

## 背景

ADR-0007 定了**向量怎么设计**（独立预期值、五类向量、两条 LLVM 路径）。本 ADR 定**什么测试在什么时机、用什么后端跑**——运行策略，正交于 0007。

现状（2026-07-12）：22 个 E2E lit + 四方差分 200 向量（interp/QEMU/gem5/Sail）。**无 clang DADAO target**（只能 `.ll→llc`，不能 `C→clang`）、**无 in-tree `CodeGen/DADAO` lit 测试**、**无 libc**（freestanding）。用户问及 ①LLVM 全量测试（check-llvm）②llvm-test-suite ③QEMU vs gem5 分工 的时机。

**核心认知**：验证链靠**多独立实现的差分 + 双后端 E2E**。历史上"E2E 收口向量盲区"的真 bug（QEMU 无 RAS 栈、gem5 SE 数据栈 63-bit、gem5 divs 仅商拿余数）**全靠 QEMU↔gem5 双后端跑同一二进制、结果分歧**逮出——**分歧是金信号**（一对一错 → spec 定谁对）。单后端 + 向量会漏。

## 决策

### D1：四层测试金字塔（T0–T3）

| 层 | 内容 | 后端 | 时机 | 反馈 |
|----|------|------|------|------|
| **T0** | in-tree `CodeGen/DADAO/*.ll` FileCheck（钉 ISel/立即数）、`MC/DADAO` 编码 | 无模拟器（纯比对 .s） | 每次改动 | 秒级 |
| **T1** | 开发中特性的 E2E（功能 smoke） | **QEMU only**（快） | 内循环 | 秒级 |
| **T2** | 全 E2E + 四方差分（验收基线） | **QEMU + gem5 双后端** | 验收门槛 / CI | 分钟级 |
| **T3** | 全量 check-llvm（所有 target）→ llvm-test-suite | 视情况 | 定期 / 打包前 | 慢 |

**T0 与 E2E 互补**：E2E 验"行为对"（要跑模拟器），FileCheck 验"选对指令 / 填对立即数"（不用跑）。历史缺陷 `zext(setcc)` 三值、`exts` 立即数、`RELA_LO=R_ABS` 均属"选错指令/填错立即数"——FileCheck 一秒抓，比 E2E 快得多。**T0 是当前缺失的层，从现在起随每个 CodeGen 任务增量补**（每任务除 E2E 外附一个 FileCheck 钉关键指令）。

### D2：QEMU vs gem5 分工

**QEMU = 快的功能参考 + 内循环；gem5 = 独立一致性校验，在验收门槛和「新/风险」处付费买它。**

**必带 gem5 双后端一致性**（T2）：
- **新指令 / 新路径首次用**（嵌套 call、数据栈、div 仅商、窄 load/store、rela/全局、select…）——历史分歧全在此冒出
- **历史分歧域**：控制流/RAS、内存/栈寻址、除法、重定位/链接
- **验收里程碑**：宣布能力"完成"时，E2E 必须断言**双后端同退出码 + 正确**（禁 `|| true` 弱化；见 feedback 门槛游戏）

**QEMU 够了**（T1）：
- 四方差分向量已含 gem5，不必 E2E 重跑
- 纯功能 smoke、快速迭代内循环
- gem5 SE syscall 面窄；将来 libc/syscall-heavy 程序 **QEMU 主跑、gem5 抽检**

**动态**：现处 backend bring-up 期，codegen×模拟器 bug 密集 → 验收 E2E 保持双后端。待 backend + 双模拟器在大 E2E 语料证稳后，gem5 退成"新指令/微架构相关/定期"抽检，其余 QEMU 为主。

### D3：全量 check-llvm 时机

- **DADAO in-tree 子集**（`CodeGen/DADAO`、`MC/DADAO`）：即 T0，现在起增量建。
- **全量（X86/ARM/RISC-V…所有 target）**：唯一价值=确认 DADAO 加法式改动没弄坏 target-independent 代码（共享 TableGen/MC）。慢+噪声大，**不进每任务循环**；时机=大的 MC/lld 改动后 + 交 wiki/上游打包前各跑一次。

### D4：llvm-test-suite 时机（后期里程碑，非近期门槛）

前置全缺，按序解锁：
1. **clang DADAO target**（triple/TargetInfo/ABI/driver）——否则编不了 C
2. **libc（musl 移植）+ crt + syscall/半主机层**——test-suite 程序用 printf/malloc
3. run harness + I/O

**时序**：核心 CodeGen 补完（select→函数指针→memcpy→struct 返回）→ clang 集成 → 最小 musl+syscall → 先跑 **SingleSource 纯计算子集**（无 libc I/O，只算+返回值，能上 QEMU/gem5 退出码 harness，双后端一致性）→ 最后全量带 libc（QEMU 主、gem5 抽检）。**不用 llvm-test-suite 当近期门槛**。

**`llvm-test-suite/` 子目录 = 常规 T2 E2E 回归的一部分，不是实验性内容**（ML-004e，2026-07-16 确认）：`tests/lit/E2E/llvm-test-suite/` 就是 `tests/lit/E2E/` 下的普通子目录，`tests/lit/E2E/lit.cfg` 没有 `config.excludes` 或限定路径的 glob，lit 默认递归子目录——所以现有唯一 E2E 入口 `llvm-lit tests/lit/E2E/` 已经把它跟其余用例一起跑（当前 54/54，含 `llvm-test-suite/` 下 23/23）。本仓库没有另外的 CI workflow/脚本会用不递归的 glob 单独跑 E2E。确认后未新增 `make check-suite` 之类的并行 target（会是对同一条命令的重复封装）；`make check` 本身不含 E2E（结构性检查，E2E 走独立的 `llvm-lit` 命令），不受影响。

### D5：终极目标 = gcc-c-torture 全量通过，失败必有明确理由（2026-07-16 用户定，参照旧 toolchain 先例）

**用户目标**：C 的全量测试通过；不通过的必须有明确且合理的理由。

**已有先例（`~/toolchain/llvm-unicore`，已归档但结论可继承——只继承结论/分类方法，不 cherry-pick 代码）**：旧工具链用 CMake 集成方式（`TEST_SUITE_USER_MODE_EMULATION`直接跑 llvm-test-suite 自己的构建系统，非本仓库 D4 定的"薄 lit 封装"路线）+ 真 musl libc，跑 `SingleSource/Regression/C/gcc-c-torture`（GCC 官方 C 语言torture 测试集，llvm-test-suite 自带），达到 **1617/1708 通过（94.7%），且 DL-028a 深挖分析证实剩余 91 个失败中 DADAO ISel/backend bug = 0**：
- 51 个 FAIL_COMPILE：100% 是 clang 前端不支持的 GCC 扩展（嵌套函数 29、VLA-in-struct 8、未知 GCC builtin 8、asm 约束/十进制浮点 2、其它前端严格性 4）——**换任何 clang target 都会同样失败，与 DADAO 后端无关**。
- 32 个 FAIL_LINK：100% 是测试集自身无 `main()` 的 companion library 文件，不是真正的链接缺陷。
- 8 个 TIMEOUT：QEMU 模拟速度导致，非正确性问题。
- **零 compiler-rt 符号缺失、零 FAIL_LLC、零 FAIL_RUN**（凡是编译链接过的程序，运行结果全对）。

这证明"C 全量测试通过（不通过项有明确理由）"这个目标在 DADAO 这类目标架构上是**已经被验证过可行的**——DADAO-0628 的 greenfield 重建应该把 gcc-c-torture 的这份**失败分类方法论**（而非旧代码本身）当作最终验收基准：任何失败要么落进旧结果里已识别的"clang 前端不支持的 GCC 扩展/companion 文件/模拟器超时"这几类里，要么是需要記 issue 修的真 DADAO 缺陷。

**对当前路线的含义**：
1. gcc-c-torture 里大量用例依赖较完整的 hosted libc（`printf`/`malloc`/`string.h` 全套/`setjmp` 等）——当前 picolibc（ADR-0014 阶段1）大概率不足以覆盖，达到旧工具链同等通过率很可能需要先完成 **musl 移植（ADR-0014 阶段2）**。这不改变 D4"picolibc 先行"的阶段顺序，但明确了"全量通过"这个终极里程碑的真实前置是 musl，不是 picolibc。
2. llvm-test-suite 的封装方式（本仓库 D4 定的"薄 lit 封装"vs 旧工具链的"CMake 直接集成"）暂不改变——ML-004a/b 已验证薄封装路线可行且更符合本仓库 freestanding/QEMU-exit-code 的测试哲学；若未来薄封装规模上不去（用例数量大到手写 lit 封装不现实），再考虑评估 CMake 集成路线，需要专门 ADR 决策，不是现在的默认选项。
3. 当前 ML-004 系列（SingleSource 纯计算子集）是通往 gcc-c-torture 全量目标的第一步（不依赖 libc I/O），后续随 musl 完成再扩大到 gcc-c-torture 全集。
4. **变参指针保存区缺口必须先修（2026-07-18 架构师/用户决策）**：DL-069a/ML-013a 发现并确认 `varargs-pointer-args-lost-rb-bank-save-area`（LLVM 变参保存区只 spill RD bank，RB bank 的指针型可变实参被静默丢失，`contracts/abi/spec.md §6`/`docs/open-spec-issues.md` 已同步记录）。gcc-c-torture 里大量用例用 `printf`/`sprintf` 等变参函数做诊断输出，其中相当一部分带指针格式化参数（`%s` 等）——若不先修，正式大规模跑 gcc-c-torture/llvm-test-suite 时这个已知缺口会和真正的后端 bug 混在一起，排查成本高。**排期**：在 musl 第二个 E2E 里程碑（ML-014a，malloc+printf）之后、正式开始大规模 gcc-c-torture/llvm-test-suite 扫描或 kernel K1 任务之前，插入一个专门任务修复（预计沿用 §2.3 的"共享溢出区、按声明顺序排列"思路统一保存区设计，而不是简单地"RD 保存区旁边加一个 RB 保存区"）。

## 后果

**正面**：反馈分层（秒→分钟→慢），T0 补上"选错指令"的快回归网；gem5 成本用在刀刃（新/风险/验收）不浪费在每次重跑；llvm-test-suite 有清晰前置路线，不被当近期阻塞。

**负面 / 限制**：T0 需增量补写 FileCheck（当前为 0）；clang+libc 是 llvm-test-suite 的硬前置，工作量大，排在核心 CodeGen 之后。

**已知风险**：gem5 退成抽检后，若某新指令未进"必带 gem5"清单，分歧盲区可能重现——判据 D2 需随新指令域更新。

## 参考
- ADR-0007（向量设计原则）、feedback「E2E 收口向量盲区」（qemu-no-ras-stack / gem5-se-no-data-stack / gem5-divs-quotient-swap）
- knowledge-graph `ai-dev-workflow/06-simulator-tier-consistency`、`compiler-backend/07-isa-baremetal-test-harness`
