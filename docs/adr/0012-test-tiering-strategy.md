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

## 后果

**正面**：反馈分层（秒→分钟→慢），T0 补上"选错指令"的快回归网；gem5 成本用在刀刃（新/风险/验收）不浪费在每次重跑；llvm-test-suite 有清晰前置路线，不被当近期阻塞。

**负面 / 限制**：T0 需增量补写 FileCheck（当前为 0）；clang+libc 是 llvm-test-suite 的硬前置，工作量大，排在核心 CodeGen 之后。

**已知风险**：gem5 退成抽检后，若某新指令未进"必带 gem5"清单，分歧盲区可能重现——判据 D2 需随新指令域更新。

## 参考
- ADR-0007（向量设计原则）、feedback「E2E 收口向量盲区」（qemu-no-ras-stack / gem5-se-no-data-stack / gem5-divs-quotient-swap）
- knowledge-graph `ai-dev-workflow/06-simulator-tier-consistency`、`compiler-backend/07-isa-baremetal-test-harness`
