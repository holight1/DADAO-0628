# kernel bring-up 调研报告（KL-001a，K0 阶段）

**日期**：2026-07-18
**任务**：`code-agent/tasks/KL-001a-kernel-bringup-recon.md`
**方法论**：仿 ML-006a（`docs/reviews/musl-recon-2026-07-16.md`）
**范围**：纯调研，未修改任何仓库文件（本报告除外）

---

## 0. 方法论说明：如何核对当前 wiki pin 内容

`~/DADAO-wiki` 本地 clone 的分支指针（`master`/`HEAD`）仍停在 `13a414d`，**没有** fast-forward 到当前 pin `9f378f4426e131903d60a208766086ae74a53c89`。但 `9f378f4` 提交对象本身在本地仓库中完整存在（`git log --oneline --all` 可见，是 `13a414d` 之后的 8 个提交之一，与 `manifests/spec.lock.toml` 注释"WU-001a：升级 13a414d→9f378f4，8 commits"完全吻合）。

**核对方法**：不要 `git checkout`/依赖分支指针，直接用 `git -C ~/DADAO-wiki show <sha>:<path>` 按提交对象读取文件内容，例如：

```bash
git -C ~/DADAO-wiki show 9f378f4426e131903d60a208766086ae74a53c89:DADAO-12-SEE-主管系统运行环境.md
```

已验证：该版本的 SEE/SBI 文档头部版本号为 `0.7.1`，与 `manifests/spec.lock.toml` 的 `see_sbi_version = "0.7.1"` 一致 ——确认取到的正是 pin 对应内容，不是分支尖端的陈旧版本。本报告以下所有 wiki 引用均取自该 pin。

---

## 1. SEE §5 完整定义 vs DADAO-0628 现有实现缺口

### 1.1 wiki pin 定义了什么（`DADAO-12-SEE-主管系统运行环境.md`，取自 9f378f4）

SEE 文档在当前 pin 下内容非常完整，不是草案：

- **§1 运行模式**：4 种运行模式 user(00)/jail(01)/supv(10)/hypv(11)，64 个 `cfx`（核芯功能扩展）编号表（0=umon, 1=jmon, 2=smon, 3=hmon, 4=ptw, 5=tlb, 6=cache, 15=hart, 16=llc, 17=pmem, 18=timer, 62=uart, 63=power）。
- **§2 地址空间**：48 位核内地址（cfxcode 占 bits[47:42]）+ 48 位虚拟地址 + 64 位物理地址；§2.2 给出完整的超页/普通页两级地址转换流程（PTBR→TLB→PTW→物理地址拼接，4 步）、§2.2.3/2.2.4 一二级页表条目格式（位域级）、§2.2.6 异常检查优先级顺序表。
- **§3 共有寄存器规范**：cg0-cg7（user/jail/supv/hypv mode 寄存器、cfx 配置寄存器、异常现场寄存器 cg5、暂存寄存器 cg6、内部存储控制 cg7），每个 cfx 都遵循同一寄存器布局规范。
- **§4 专有寄存器 + 每个 cfx 的异常原因表**：cfx_umon/jmon/smon/hmon（ILLI/UNDI/RASOF/RASUF/MALIGN/IALIGN/FPEXCP/CFXTRAP/CFXMEM/CFXREG）、cfx_ptw（NUPERM/NJPERM/NSPERM/NHPERM/NXPERM/NWPERM/NRPERM/IGPTRAP/ISPTRAP/IGPFTRAP/ISPFTRAP/DGPTRAP/DSPTRAP/DGPFTRAP/DSPFTRAP）、cfx_tlb、cfx_cache、cfx_hart（IPI）、cfx_llc、cfx_pmem、cfx_timer（TIMER 中断）、cfx_uart（UART0-31 中断）、cfx_power（POWEROFF/HARD_RESET/SOFT_RESET）。
- **§5 异常进入与退出**：完整硬件伪代码（10 步进入流程 + escape 退出流程），明确精确异常语义、中断电平触发规则、异常嵌套由软件负责、跨 cfx escape 的现场丢弃规则。

**结论**：SEE §5（以及整章）在当前 pin **已是完整规范**，不是"待补"草案——kernel bring-up 缺的不是 spec，是**实现**。

### 1.2 DADAO-0628 现有实现覆盖到哪一步（逐项列出）

检查 `components/qemu/patches/series`（17 个 patch）与 `components/gem5/patches/series`（11 个 patch），以及 `contracts/isa/spec.md §7 M1 Excluded`（第 957 行：`trap, escape; cfx2rd, cfx2rc; cfxld, cfxst` 整组列为 **M1 excluded**）：

| SEE §5 机制 | 现有实现状态 | 依据 |
|---|---|---|
| `trap` 指令进入 CFXTRAP | **部分实现，但非 spec 语义** | `components/qemu/patches/0013-dadao-trap-syscall.patch` — 直接在 `dadao_cpu_do_interrupt()` 里 C 代码 switch `cfxcode==2` 分支，**host 侧直接模拟 syscall**（write/exit/brk 走 QEMU C 函数），不做任何模式切换、不保存 `excp_prev_run_mode`/`excp_cause_*`、不跳转到 `excp_vector`。ML-002a 提交信息自述为"cfx_smon responder"，本质是**语义捷径**，不是 SEE §5 步骤 1-10 的硬件行为 |
| `escape` 指令（异常退出） | **完全未实现** | `grep -rl "escape" components/qemu/patches/*.patch components/gem5/patches/*.patch` 零匹配 |
| `cfx2rd`/`cfx2rc`（cg 寄存器读写） | **完全未实现** | 同上 grep，零匹配；`cfx_umon_user_excp_vector` 等 cg 寄存器在 QEMU/gem5 里没有对应存储 |
| `cfxld`/`cfxst`（内部存储块批量传输） | **未实现** | 同上 |
| `inner_run_mode`/`inner_cfx_mask`/`inner_cfx_code` | **完全未建模** | `grep -rn "inner_run_mode" components/*/patches/*.patch` 零匹配；QEMU CPU reset（`0001-dadao-target-skeleton.patch` 的 `dadao_cpu_reset_hold`）没有运行模式字段 |
| cg5 异常现场寄存器（`excp_prev_*`/`excp_cause_*`） | **未实现** | 无对应 QEMU/gem5 状态 |
| cfx_ptw / cfx_tlb / cfx_cache / cfx_pmem / cfx_timer / cfx_hart / cfx_llc | **完全未实现** | 只有 cfx_uart（write→host stdout）和 cfx_power（exit→host exit code）走了 host 捷径；其余 cfx 无任何寄存器/行为 |
| ILLI/UNDI/MALIGN/IALIGN | **已实现（M1 核心范围内）** | `0009-dadao-ldo-align-malign.patch`、`0010-dadao-reserved-undi.patch`、`0015-precise-exception-pc.patch` ——这些是**指令级**局部异常（精确 PC、host 侧 exit code 映射），已通过 200-AGREE 四方差分验证，但同样**不走 SEE §5 的 cfx 路由/模式切换**，只是"exit with fault code"的测试机语义（ADR-0004） |
| RASOF/RASUF | **已实现** | RegRAS 栈+块拷贝，MEMORY.md 记录 DG-004d 已验证；同样是"exit with fault code"层级，非 cfx 路由 |
| 特权模式切换（`inner_run_mode` 从 user→S-mode 等） | **无** | 见 §3 |
| 中断（timer/IPI/UART 中断信号，非 syscall trap） | **无** | 无定时器/异步中断源建模 |

**结论**：现有实现是"用 `trap` 指令编码 + host 侧语义捷径模拟了 3 个 syscall（write/exit/brk）"，**没有实现 SEE §5 定义的任何一条硬件异常进入/退出机制**（cfx 路由、模式切换、cg 寄存器、escape 返回全部空白）。ADR-0014 D4 本身也承认这是"MVP 模拟器侧"捷径，"未来换成 guest 侧真 SEE monitor firmware"。K1 要做的正是这个"未来"——从捷径升级为 spec 定义的真实机制。

---

## 2. MMU/TLB 的 SBI 式操作

### 2.1 当前 wiki pin 已正式定义（不是草案）

`DADAO-22-SBI-主管系统二进制接口.md`（取自 9f378f4，版本 0.7.1）§4/§5：

- **cfx_ptw**（地址转换部件）提供 8 个 SBI 功能：`SBI_PTW_SET_PTBR`(0)、`GET_PTBR`(1)、`SET_PTBR_PERM`(2)、`ENABLE_PTBR`(3)、`SET_PTE`(4)、`HANDLE_FAULT`(5)、`SET_PTHI`(6)、`SET_PAHI`(7)。全部通过 **`trap cfx_ptw, immu18` 陷入调用**，不是直接寄存器读写指令。
- **cfx_tlb**（TLB 管理）提供 `SBI_TLB_INVALIDATE`(0)，同样走 `trap cfx_tlb, 0`。
- 调用约定与 SBI §1 一致：`rd16-31`/`rb16-31`/`rf16-31` 传参，`rd31` 返回值，`escape cfxcode, 1` 返回。

**任务文件问题"`SBI_TLB_INVALIDATE`（旧项目 V5 提到的草案）是否已经正式定义"——回答：是，已从草案变为正式定义**，且比旧项目草案更完整（旧项目只提草案名，当前 wiki 给出完整 immu18 编号、入参/出参、初始化代码示例、异常入口分发伪代码、内部实现伪代码、调用示例，见 SBI §5 全文 90+ 行）。

### 2.2 PTBR/PTHI/PAHI 机制对比：旧项目 vs 当前 wiki（关键差异）

旧项目（`~/toolchain/DADAO/code-agent/designs/dadao-mmu-enable-design.md`）用的是 **RISC-V 风格 CSR 直接读写指令**：

```c
cp0_write(CSR_SATP, __pa(swapper_pg_dir));   // 旧项目 V1-V4 风格
cp0_write(CSR_SSTATUS, cp0_read(CSR_SSTATUS) | 1);
```

当前 wiki 里 PTBR（cg9, rc0-63）/PTHI（cg10, rc0-63）/PAHI（cg11, rc0-63）**不是 CSR 寄存器，是 cfx_ptw 这个核芯功能扩展下的寄存器组**，只能通过 `cfx2rc`/`cfx2rd`（读写 cg 寄存器）或更高层的 `trap cfx_ptw, SBI_PTW_SET_PTBR` 访问，且规定"调用前须已写入 pthi[idx] 和 pahi[idx]"的顺序依赖（SBI §4 表格下方说明）。

**结论**：旧项目的 CSR 式 MMU 使能代码（`dadao-mmu-enable-design.md` 全文、`dadao-sys-mode-v5.md` 相关代码）在寄存器访问机制层面**完全不可复用**——不是"编码变了"，是"访问范式变了"（CSR read/write → cfx trap/escape 调用）。这与 ADR-0015 D3 和 DS.md"不复用旧仓库实现代码"的原则一致，此处调研进一步确认了不可复用的**具体机制原因**。

### 2.3 页表格式：已明确规定，非 `[OPEN]`

SEE §2.2.3/§2.2.4 明确规定：
- 超页 512 MiB（2 级：L1 直接映射），8 个 64 MiB 小页（SPF 位图）；
- 普通页 64 KiB（2 级：L1→L2），8 个 8 KiB 小页（GPF 位图）；
- 一级/二级页表项均为 64 位，位域级定义（PPN、R/W/X、Access/Dirty、Present/Superpage 位）；
- 无 Global 位（按 PTBR 索引划分 64 个独立 TLB 集合替代）。

`docs/open-spec-issues.md` 中与 MMU 相关的**真实未决问题**（非页表格式本身，是细节接口一致性问题）：
- **TLB fault return**："Successful repair currently appears to skip instead of retry the faulting instruction"——阻塞 System QEMU、Kernel。SBI §4 `cfx_tlb_ptw_delegate` 示例代码里写的是 `escape cfx_tlb, 0`（重试故障指令），但 open-issues 记录了这与某处观察到的"skip"行为不一致，**K1 落地 cfx_ptw/cfx_tlb 时需要先厘清这一条**，不能直接照抄 SBI 示例伪代码。
- **PTW SBI ABI**："PTE/PTHI/PAHI register-bank classification is inconsistent with scalar ABI"——阻塞 SBI、Kernel。
- **VA2PA result**："Signed error encoding conflicts with full 64-bit physical addresses"——阻塞 SBI、MMU tools。
- **Cross-cfx escape**："Previous cfx state and nested return policy are not fully specified"——阻塞 Exception nesting（K1 若要支持 cfx_tlb 委托 cfx_ptw 这种跨 cfx escape 调用链，需要先解决这条）。

这 4 条是 K1 立项前应该逐条向 wiki 团队/架构师确认或做 spec-decision 的具体阻塞点，不是泛泛的"MMU 还没做"。

---

## 3. 特权级/模式切换机制现状

### 3.1 spec 层面：4 种模式 + 完整切换流程已定义

SEE §1 定义 4 种运行模式（user/jail/supv/hypv），§5 异常进入步骤 8"模式切换"：`inner_run_mode <= cfx_<cfxname>_<mode>_switch_run_mode`。**HBI §3"启动与引导移交约定"额外给出了一个关键、容易被忽略的规则**：

> 硬件复位后运行模式初始化为 **hypv**（不是 supv），`inner_cfx_code` 初始化为 `cfx_power`，`inner_cfx_mask` 全 1（屏蔽所有 cfx），PC 跳转到 `cfx_power_hypv_excp_vector`（`0xffff_ffff_0000`）。

也就是说，按当前 spec，**硬件永远从 H-mode 启动**，S-mode 内核入口必须由 hypv 引导代码执行一段 `cfx2rc`（清除各 cfx 的 `hypv_cg_reg_deleg`，把寄存器访问权限下放给 supv）+ `escape cfx_power, 0` 序列才能进入。HBI §3 给出了这段引导代码的完整示例（约 15 条指令）。

### 3.2 与 ADR-0015 D2（"暂不引入固件层，继续裸加载"）的张力——需要澄清

ADR-0015 D2 的表述是"继续沿用现有模式，QEMU/gem5 直接 `-kernel`/ELF 裸加载，无引导固件层"。**根据 HBI §3，"裸加载直接进 S-mode"在当前 spec 下没有对应的硬件行为**——spec 规定复位后必然先到 hypv 模式的 `cfx_power_hypv_excp_vector`。

这不意味着 D2 不可行，但需要修正理解：**D2 应解释为"不引入 OpenSBI 式的复杂固件（设备树解析、多核唤醒协商等），但仍需要 HBI §3 规定的那段最小 hypv→supv 移交桩代码（约 15-20 条指令，纯 `cfx2rc` delegation + 一次 `escape`）"**，而不是"硬件复位后可以配置为直接从 supv 开始执行"。这段桩代码本身工作量很小（HBI §3 给出的示例代码可以近乎直接抄），建议在 K1 任务里明确拆出来作为独立的小任务（详见 §7 K1 任务清单第 1 项），并在任务描述里向架构师标注这一发现，避免后续因误解 D2 而漏做这一步导致 boot 卡在 hypv 态。

### 3.3 trap 与"模式切换"的关系：现有 `cfx_smon` 实现完全没有特权级概念

现有 `0013-dadao-trap-syscall.patch` 里 `trap` 触发后，QEMU 直接在 host C 代码里处理 syscall 语义，**不修改任何"当前运行模式"状态**（因为 QEMU CPU 状态里根本没有 `inner_run_mode` 字段，见 §1.2 表格）。这是纯粹的"陷入 host 侧 responder 函数"，与 spec 定义的"陷入 guest 侧、有真实特权级切换的 monitor"完全是两回事。K1 需要从零建模 `inner_run_mode`/`inner_cfx_mask`/`inner_cfx_code` 三个隐藏状态，并让 QEMU/gem5 的 helper 真正执行 SEE §5 的 10 步伪代码，而不是继续走 host 捷径。

---

## 4. 旧项目 ~20 条踩坑逐条核实（`sysmode-debug-lessons.md`，B01-B22 + L1-L3，实际 25 条）

判定规则：
- **✅ 通用教训，仍适用** = 与具体 ISA 编码无关的方法论/工程纪律，直接抄进"必读清单"。
- **⚠️ ISA 版本特有，细节不可直接照搬，但背后的风险类别仍适用** = 需要在新 spec 下重新验证同类风险，不能假设已解决。
- **❌ 不适用/已被当前架构消除** = 当前 spec/工具链已经结构性避免了这个坑。

| # | 一句话 | 判定 | 理由 + 对应当前章节/K阶段 |
|---|---|---|---|
| B01 | rd0 硬连线不可写，QEMU 每 TB 强制清零 | ✅ 仍适用 | `contracts/isa/spec.md` 已把 rd0 列为 hardwired zero（§1.1 RD），M1 已用测试向量覆盖（`docs/open-spec-issues.md` "C-25 operand legality rd0→ILLI"已 resolved）。**但这条教训本身**（"零寄存器语义必须实测，不能假设可写"）对 K1 新增的 cg 寄存器组（如 `cfx_*_scratch_regs`）依然适用——暂存寄存器等新寄存器组的读写边界需要重新建基准，不能默认"和 rd0 一样安全" |
| B02 | setow w1/w2/w3 QEMU 实现 bug | ❌ 不适用 | ISA 版本特有指令（当前 spec 是否还有 setow/setzw 需查 SimRISC，且 M1 阶段已用 `setzw w2` 等验证通过，DADAO-0628 未见此 bug 复现记录）。教训"立即数构造指令要测所有 wyde 位置"仍属于通用范畴，但已被 T1（旧文档自己总结的建议）覆盖，无需重列 |
| B03 | atomic64 LL/SC 静默损坏 | ⚠️ 需重新验证 | `contracts/isa/spec.md §7` M1 Excluded 表已排除 `fence; lro_nn/nr/an/ar; sco_nn/nr/an/ar`（Atomics 整组）。当前 kernel bring-up 若是单核 UP（K3/K4 目标暂无 SMP 迹象），可以复用旧项目"全部改 local_irq_save/restore"的绕过策略，但**需要在 K1/K3 边界重新确认 DADAO-0628 的 lro/sco 双后端实现状态**（本调研未验证，因为 Atomics 是 M1 excluded，大概率仍未实现）——列入必读但标注"仅在需要原子操作时触发，UP kernel 可全程绕过" |
| B04 | ra2rd/rd2ra hb/hc 字段与直觉相反 | ❌ 不适用（机制已变） | 当前 spec `contracts/isa/spec.md §7`："RA register move: rd2ra, ra2rd — Excluded（M1 scope decision, 2026-06-29）"，而且当前 RA 模型是 RegRAS 硬件栈（ra1-63 环形栈+引用计数），根本没有"individual ra register 可寻址"的概念了，`ra2rd`/`rd2ra` 这两条指令语义在新 ISA 下大概率不存在或含义已完全不同。**但更换后出现了一个新的、更大的同类坑**：见下方"新发现"条目 |
| B05 | QEMU `-append` 对 dadao-virt machine 无效 | ⚠️ 需在 K3 重新验证 | 属于"QEMU machine 具体实现是否对齐通用 kernel 假设"的工程坑，与 ISA 版本无关，但当前 DADAO-0628 QEMU machine 是全新实现（`hw/dadao/` 全新写的，非旧项目代码），**这条 bug 本身不会被继承**（新代码没有这个历史包袱），但"验证 `-append` 生效"这个检查动作应该在 K3 kernel boot 阶段的 checklist 里过一遍，不能假设"新写的就没事" |
| B06 | LLVM IAS 拒绝带操作数 `ret` | ⚠️ 需在 K1/K3 验证 | ISA 版本特有（当前 `ret` 语法见 `contracts/isa/spec.md` §5.6 `ret rd0, 0`），当前 DADAO-0628 LLVM 后端是否正确支持带操作数 `ret` 汇编解析未在本次调研核实。属于"编译器 IAS/InstPrinter 对称性"这一类通用风险，建议 K1 前对 kernel 汇编会用到的所有助记符过一遍 IAS round-trip（T3 建议） |
| B07 | LLVM IAS 不支持 ra2rd/rd2ra 助记符 | ❌ 机制已变 | 同 B04，新 RA 模型不存在这两条指令，直接消失 |
| B08 | inline asm 约束缺 `+Rb`/`+Rd` 大写前缀 | ⚠️ 需在 K1 验证 | 通用 LLVM 后端坑（大小写约束前缀是否都注册），与 ISA 版本无关但**依赖 DADAO-0628 LLVM 后端当前 inline asm 约束支持状态**，本次调研未核实（不在 7 个目标范围内，超出 K0 边界）。列入 K1 必查项 |
| B09 | lro/sco 未进 MC 层 | ⚠️ 需在需要原子操作时验证 | 同 B03，Atomics 是 M1 excluded，DADAO-0628 是否已补 MC 层支持需要单独确认，K3/K4 若 kernel 需要原子操作（几乎必然需要，spinlock 等）时必须先做这项 |
| B10 | OS triple 仅注册字符串，缺 driver routing | ✅ 仍适用（通用工程坑） | 与 ISA 版本无关，是"三步注册"（Triple 枚举 + driver routing + 动态链接器路径）这一类通用 clang driver 集成坑，K3 引入 `dadao-linux-musl`/`dadao-linux-gnu` triple 时必须重新走一遍 checklist（当前只有 M1 baseline triple，未见 kernel/linux triple 注册记录） |
| B11 | RA bank 完全未保存（初始实现） | ⚠️→**升级为必读重点**，机制变了但风险更大 | 见下方"新发现"——当前 RegRAS 硬件栈模型下，AEE 文档明文规定"进程切换时，操作系统须保存和恢复全部 ra0-ra63 寄存器"（§AEE 返回地址栈，见 §5 本报告新发现），但**当前 M1 完全没有实现"访问 RA bank 做整体保存"的指令**（`ldmo-ra`/`stmo-ra` 被 M1 排除，`contracts/isa/spec.md` 第 958 行）。这比旧项目的坑更根本：旧项目至少有 `ra2rd`/`rd2ra` 可用（虽然语义踩坑），当前 DADAO-0628 **连保存 RA bank 的指令通路都还没有** |
| B12 | RD32-63 callee-saved 未保存 | ✅ 仍适用，但风险已降低 | `contracts/abi/spec.md §1.1` 已明确 rd32-63/rb32-63 为 callee-saved（"**Yes**"），比旧项目"边调试边发现"的状态好——**但这只是文档层面明确了寄存器分类，不代表 K1/K3 写 `__switch_to` 时会自动记得保存全部**。核心教训"写 context switch 前先列全 callee-saved 清单"依然要执行，只是清单已经现成（见 ABI spec 表），比旧项目省了"从零发现"的过程 |
| B13 | 保存顺序错误（RD32-63 须在 ra2rd 之前） | ⚠️ 具体顺序依赖新指令而变，但"顺序依赖"这个风险类别仍适用 | 当前没有 `ra2rd`，替代机制未知（可能是 `ldmo-ra`/`stmo-ra` 一次性块传输，也可能全新指令），**一旦 K1 定下 RA bank 批量保存指令，必须先分析该指令是否会 clobber 其它寄存器组**，重演 B13 同类分析 |
| B14 | rb2 帧指针未保存 + thread_info mask 编译器缓存失效 | ✅ 仍适用（两个子问题都通用） | rb2 在当前 ABI 已列为 callee-saved（`contracts/abi/spec.md §1.2`："rb2 rbfp Frame pointer (optional) **Yes**"），子问题1（帧指针必须保存）已被文档覆盖；子问题2（"编译器可能把不变量缓存到 callee-saved 寄存器，context switch 恢复的值可能是错的初始值"）是**与 ISA 完全无关的通用编译器行为陷阱**，必须原样保留进必读清单，且是这份清单里最容易被忽视的一条（不是"漏保存"，是"保存了但值语义不对"） |
| B15 | paging_init() 调用时机过晚 | ⚠️ 需在 K3 重新验证 | Linux 5.4 通用代码路径的问题（非 DADAO 特有），当前 K3 从零写 `arch/dadao` 时会重新面对这个通用 early-boot 时序问题，保留 |
| B16 | percpu.o setup_per_cpu_areas 弱符号冲突 | ⚠️ 需在 K3 重新验证 | 同样是"新 arch 目录未实现某通用 hook 导致强符号冲突"的通用坑，K3 从零写 arch/dadao 必然会撞到某个类似的符号，保留但不特指这一个符号（新 arch 目录可能缺的 hook 不同） |
| B17 | 调试插桩过度裁剪 sched/core.c | ✅ 仍适用（工程纪律） | 与 ISA 无关的纯工程纪律条款，直接保留（"只加 DDBG 不删业务逻辑"） |
| B18 | musl `__set_thread_area` 未写 rb4 | ❌ 已被验证不适用（更好消息） | MEMORY.md 记录 ML-006a 调研已确认 rb4=rbtp 在当前 ABI+LLVM 后端已就绪，musl 本体零处使用编译器 `__thread`，TLS 路径已过 Phase A/B。K3/K4 真 kernel 阶段仍需要验证"kernel 是否正确设置新进程的 rb4"，但这是新任务范畴，不是旧坑复现 |
| B19 | first-switch detection 依赖 rd0 可写 | ❌ 不适用 | 这是旧项目自己的设计缺陷（用 rd0 当 sentinel），教训是"设计前验证 ISA 假设"，已被 B01 教训覆盖，不必重复列出 |
| B20 | cpu_context 数组容量不足反复扩容 | ✅ 仍适用（工程纪律） | "写 context switch 前一次性做完整寄存器清单，不要边跑边扩容"是通用教训，当前 ABI spec 虽然给出了 callee-saved 清单，但 RA bank 保存方式未定（见 B11），**cpu_context 布局设计仍需要等 K1 定下 RA bank 访问指令后再一次性设计完整**，不能分批扩容 |
| B21 | initramfs/initrd 加载链路缺失 | ⚠️ 需在 K3/K4 重新实现 | QEMU dadao-virt machine 是全新代码（`hw/dadao/`），旧项目"改 virt.c 加 initrd 加载"的具体改法可参考思路（"K3/K4 需要在 QEMU machine 里显式加载 initrd 到约定物理地址，kernel 侧用某种约定方式发现它"），但代码不可抄（M1 QEMU machine 结构已完全不同）。当前 DADAO-0628 无 FDT——HBI §3 用 `rb16` 传"设备树或硬件信息指针（0 表示无）"，K3/K4 大概率延续"无 FDT，用某个 handoff 寄存器约定 initrd 地址"的思路 |
| B22 | pgtable.h 大量 stub 导致 slab BUG | ⚠️ 必然重新面对，且是本报告最大的单体新工作量 | 当前完全没有 arch/dadao 的 pgtable.h（连骨架都没有），K3 从零写会直接面对"实现真实 PTE/PMD 操作 vs 先 stub 绕过"的同一个权衡。**当前页表格式（SEE §2.2.3/2.2.4）比旧项目更复杂**（超页/普通页两级、SPF/GPF fragment 位图），意味着 pgtable.h 实现工作量可能比旧项目更大，需要在 K1 结束、K3 开始前专门评估 |
| L1 | busybox ELF 加载 VA 猜错（应用 `readelf -l` 确认，不要假设） | ✅ 仍适用（工程纪律） | 通用方法论：先用工具核实真实 ELF 装载地址，不假设。K3/K4 用 musl 静态链接的第一个用户程序时必须重新核实 DADAO-0628 musl 的默认 VA（当前 musl 已有 crt0/dadao.ld，可以直接 `readelf -l` 核实，成本很低） |
| L2 | DADAO softmmu IO region 映射是"低VA→高PA"，非 identity | ❌ 不适用（机制已完全不同） | 旧项目的"VA\|(1<<31)" IO region 映射是旧 QEMU softmmu.c 的具体实现细节；当前 spec 的地址转换完全走 SEE §2.2 的 cfx_ptw 页表机制（PTBR/PPN/pahi 拼接），没有"bit31 特殊含义"这种硬编码规则。这条具体结论不可带入，但"MMU 开启后 IO 访问路径要显式验证，不能假设 identity/低地址直通"这一类风险仍需要在 K1/K3 对新机制重新走一遍 |
| L3 | earlycon 在 MMU 开启瞬间必然中断 | ⚠️ 需在 K3 重新设计 | 通用风险类别（"MMU 开启时机与 console 驱动 VA 联动"）仍然适用，具体解法（旧项目用 paging_init 预建 VA 0x90000000→PA 0x10000000）依赖旧 IO region 规则（见 L2），不可直接复用，但**这个风险点本身**（K3 阶段 MMU 一开，earlycon 若映射方式不对会立即失聪，调试会很痛苦）应该保留在必读清单里，提前设计 |

### 4.1 新发现：比旧项目坑更根本的一条（不在原 20 条列表里，本次调研发现）

**RegRAS 整栈保存/恢复缺少 ISA 层支持**：当前 ISA（`contracts/isa/spec.md §1.5`）的 RA bank 已从旧项目的"64 个可当作 GPR 用的 ra 寄存器"变为"RegRAS 硬件栈（ra1-63，环形+引用计数），配合 `call`/`ret` 自动出入栈"。AEE wiki 原文明确规定（`~/DADAO-wiki` 9f378f4 pin，`DADAO-11-AEE-应用程序运行环境.md` "返回地址栈"节）：

> "进程切换时，操作系统须保存和恢复全部 ra0-ra63 寄存器。"

但 `contracts/isa/spec.md §7 M1 Excluded` 明确排除了 `ldmo-ra`/`stmo-ra`（RA↔内存访问指令）和 `rd2ra`/`ra2rd`（RA↔RD 寄存器移动指令）——**当前 M1 阶段没有任何指令可以把 RA bank 的内容读出或写入**。这意味着：K1/K2 阶段必须先决定"context switch 如何保存/恢复 RegRAS"这件事本身用什么机制（重新引入 `ldmo-ra`/`stmo-ra`？还是别的新指令？），这是一个**先于**"如何写 `__switch_to`"的独立设计问题，比旧项目 B11-B13/B20（"知道要保存，只是没保存全"）更前置——旧项目至少有指令可用，当前 DADAO-0628 连指令都没有。**建议作为 K1 任务清单的第一优先级项**（见 §7）。

### 4.2 精简后的"新 kernel 任务必读清单"（供 K1-K4 任务书引用）

1. **RegRAS 整体保存/恢复的 ISA 层机制必须先立项，不能假设"自然有"**（新发现，§4.1，对应 K1）。
2. **callee-saved 寄存器清单已经在 `contracts/abi/spec.md §1.1/1.2` 现成给出（rd32-63/rb32-63/rb2/rb1），写 `__switch_to` 前先照抄这份清单，不要边跑边扩容**（B12/B13/B20，对应 K3）。
3. **编译器可能把不变量缓存到 callee-saved 寄存器；`copy_thread()`创建的新任务若该寄存器槽初始值不对，缓存会失效导致隐蔽错误**——涉及编译器生成代码的地方要用 `barrier()`/inline asm 强制重算，不能信任缓存（B14-part2，对应 K3）。
4. **写内核汇编前，先扫描会用到的助记符 vs 编译器 IAS/AsmParser/inline-asm 约束实际支持状态**，不要假设"文档里有就能编译"（B06/B08/B09，对应 K1/K3 前置 gap analysis）。
5. **ISA 行为要用 bare-metal 测试实测建立基准，不能只读文档**（B01 教训延伸；当前 K1 引入的每个新 cfx/cg 寄存器都要建最小行为测试，对应 K2）。
6. **调试插桩只加不删业务逻辑，裁剪需显式记录**（B17，全程适用）。
7. **ELF 装载地址、MMU 开启后 IO 访问路径等"设计假设"要用工具实测验证，不能假设**（L1/L2/L3 教训延伸，对应 K3）。
8. **新 QEMU machine 的通用假设（initrd 加载、-append 等）即使代码全新写，也要重新过一遍 checklist，不能假设"新写的就没有历史 bug"**（B05/B21，对应 K3/K4）。
9. **原子指令（lro/sco）当前 M1 excluded，若 K3 kernel 需要 spinlock 等原子语义，必须先确认双后端 MC 层支持状态，UP kernel 可考虑全程 `local_irq_save/restore` 绕过**（B03/B09，对应 K3）。
10. **pgtable.h 从零实现的工作量可能比旧项目更大**（当前页表格式含 fragment 位图，旧项目没有），需要在 K1 结束时专门评估工作量再排 K3 任务粒度（B22，对应 K3 立项前）。

（已从原 25 条精简/合并为 10 条可执行清单；B02/B04/B07/B18/B19/L2 判定为"不适用"未收录，理由见上表。）

---

## 5. Linux 5.4 树本身的可用性

`~/toolchain/DADAO/__source/linux-0504` 是一个 **git 仓库**，`git status` 显示 `On branch dadao-0504`，`ahead of 'v5.4' by 7 commits`，工作区 clean。逐条检查这 7 个提交（`git log --stat v5.4..HEAD`）：

| 提交 | 改动 | 侵入性 |
|---|---|---|
| `660035e` "add arch/dadao dir" | `arch/dadao` 是一个 **symlink**（`git ls-tree` 显示 `120000 blob`），指向仓库外部的 `~/toolchain/DADAO/ENV-linux/linux-0504-newfiles/arch/dadao` | **零侵入**——真正的 arch 移植代码根本不在这棵树里，是外部目录通过符号链接接入（印证 MEMORY.md 记录的"DADAO 文件管理规则"：kernel 改动放 `ENV-linux/newfiles/`，不改 `linux-0504` 树本身） |
| `d3d398fd3` uapi elf-em.h | 新增 1 行 `#define EM_DADAO 0x0DA0` | 通用 ELF 机器号枚举扩展，无害 |
| `fb4b9b929` uapi audit.h | 新增 1 行 `#define AUDIT_ARCH_DADAO (EM_DADAO\|__AUDIT_ARCH_64BIT\|__AUDIT_ARCH_LE)` | 通用 audit 架构号枚举扩展，无害 |
| `1a150c8f7` drivers/base/Makefile | 新增 2 行：`CFLAGS_cacheinfo.o := -O0` | 编译优化等级覆盖（可能是旧工具链的编译器 bug workaround，需要在新 LLVM 后端下重新评估是否还需要） |
| `405c78e4d` fs/ext4/Makefile | 新增 2 行：`CFLAGS_xattr.o := -O1` | 同上 |
| `f59e02d5e` kernel/time/Makefile | 新增 2 行：`CFLAGS_alarmtimer.o = -O0` | 同上 |
| `69b70e749` lib/Makefile | 新增 2 行：`CFLAGS_iov_iter.o := -O1` | 同上 |

**结论**：这棵树**基本是干净的 vanilla 5.4.0**（`Makefile` 的 `VERSION=5 PATCHLEVEL=4 SUBLEVEL=0`），7 个提交里 6 个是不足 3 行的微小、非侵入性改动（2 个 uapi 枚举 + 4 个编译优化等级覆盖），真正的 `arch/dadao` 移植代码通过符号链接完全隔离在树外。**可以直接作为 DADAO-0628 新 `arch/dadao` 移植的基线**，不需要重新从上游拉取——直接复用这棵树（去掉 symlink 换成 DADAO-0628 自己新建的 `arch/dadao`）风险很低。

**唯一需要决策的点**：4 个 `CFLAGS_*.o := -Ox` 覆盖是否还需要保留。这些大概率是旧工具链（`llvm-1600`，即旧 LLVM 后端）在特定文件上触发编译器 bug/超时的 workaround，与新 DADAO-0628 LLVM 后端（新 codegen 路径）不一定有相同问题，**建议先不带这 4 行编译一遍，出问题再按需加回**，不要默认继承。

---

## 6. 裸机内核态回归的可行范围（K2 阶段前置调研）

### 6.1 现有差分/E2E 框架结构

- `tools/run_differential.py`：四路差分驱动（interp / QEMU / gem5 / Sail），逐条读 `tests/vectors/isa/*.yaml`（当前 10 个文件：control-flow/misc/rb-ops/rd-arith/rd-compare/rd-cond-assign/rd-load-store/rd-logic/rd-shift-extend/rd-wyde-block），每条向量是**单指令级**的输入寄存器状态 + 预期输出寄存器状态，走 `validate_interp.py` + `run_qemu_test.py` + `run_gem5_test.py` + `run_sail_test.py` 四个后端各自判定后 AGREE/DIVERGE/HARNESS/QEMU-SKIP 归类。
- `tests/lit/E2E/`：lit 驱动的**端到端二进制**测试（`.c`/`.s` → clang/llc → ELF → QEMU/gem5 跑 → 断言退出码/输出），当前只有 `musl_e2e_exit.test` 一条用例，走 `run_e2e.py`/`gen_e2e_binary.py`。
- `tests/e2e/`：目前只有 3 个裸汇编 smoke（`smoke_add.s`/`smoke_arith.s`/`smoke_jump.s`），走 gem5 SE 模式对拍（MEMORY.md 记录的 G1/G2 三方 198 AGREE 用的是这套）。

### 6.2 判断：现有框架**部分可扩展**，但"上下文切换"/"trap 分派"/"MMU 开关"这三类测试各自需要新增结构

- **trap 分派**（K1 早期）：现有 `tests/vectors/isa/*.yaml` 是**单指令**级向量（一条指令的输入→输出寄存器状态），`run_differential.py` 的四路验证机制（interp/QEMU/gem5/Sail）本身可以直接复用——**但向量的"预期状态"字段需要扩展**，因为 trap 分派涉及"陷入前状态 + 陷入后 cg 寄存器状态（`excp_prev_*`/`excp_cause_*`）+ PC 跳到 excp_vector"，这比现有向量"单指令改几个寄存器"复杂一个量级，需要新增字段（如 `cfx_state_before`/`cfx_state_after`）。**判断：结构可复用，字段需扩展，是增量工作不是推倒重来**。
- **上下文切换**（K2/K3）：这个天然是**多指令序列**级测试（保存寄存器→触发切换→恢复→验证），现有单指令 yaml 向量框架**不适用**，需要落在 `tests/lit/E2E/` 这一层（跑一段手写汇编/C 序列，断言最终寄存器/内存状态），但当前 lit E2E 框架的断言方式是"退出码 + stdout 文本"（`gen_e2e_binary.py`/`run_e2e.py`），**没有"跑到某个断点读寄存器/内存 dump 并断言"的机制**——这一点上 gem5 SE 模式的 halt-regdump（`0003-dadao-halt-regdump.patch`，MEMORY.md 记录的 G1 用它做过 3 条 smoke 的三方差分）已经有雏形，可以作为上下文切换测试的断言基础设施起点，但需要扩展成"通用断点+dump"框架，而不是现在这种"跑到 halt 才 dump"的一次性机制。**判断：需要新建断言机制（中等工作量），但可以复用 gem5 halt-regdump 已有的 dump 通路作为起点，不是从零发明**。
- **MMU 开关**（K1/K2）：同样是多指令序列级（设置 PTBR→使能→触发地址转换→验证 TLB/页表行为），且需要"故意制造页缺失/权限错误"这类断言（验证特定异常触发），**现有单指令 yaml 向量框架的"异常触发"部分（ILLI/UNDI/MALIGN 已有先例，见 `docs/open-spec-issues.md` C-25 等）可以作为参照扩展到页表异常**（NUPERM/IGPTRAP 等），但"页表数据结构本身的构造"（在测试里手工摆好一份页表）目前没有任何工具支持，需要新写一个"测试页表生成器"辅助脚本。**判断：异常触发断言机制可复用先例扩展，页表构造需要新建小工具，工作量中等**。

**综合判断**：不需要整套推倒重来，但也不是"现成框架直接够用"——三类测试各自需要在现有差分/lit 框架基础上做**结构性扩展**（trap 分派：向量字段扩展；上下文切换：新建断点+dump 断言机制；MMU 开关：新建页表构造小工具 + 异常断言扩展）。建议 K1/K2 任务里为每类测试扩展单独排一个子任务，不要合并成一个大任务（避免像旧项目 context-switch 那样"边调试边发现遗漏"）。

---

## 7. 建议的 K1 任务拆分清单

风险/工作量分级参照 ML-006a §7 格式（低/中/高 = 相对本项目其它任务的量级判断，非绝对工时估算）。

| 任务（建议编号占位） | 内容 | 风险 | 工作量 | 依赖 | 备注 |
|---|---|---|---|---|---|
| **KL-101a** | HBI §3 hypv→supv 移交桩代码 + `inner_run_mode`/`inner_cfx_mask`/`inner_cfx_code` 三个隐藏状态在 QEMU/gem5 建模（CPU reset 直接进 hypv，需要跑完移交序列才能进 supv） | 中 | 小-中 | 无 | 对应 §3.2 发现——务必先做，否则后续所有"从 S-mode 视角设计"的任务都建立在错误假设上 |
| **KL-102a** | `cfx2rd`/`cfx2rc` 指令 + cg 寄存器组通用存储框架（cg0-cg7 共有寄存器规范，先只做 cfx_smon 一个 cfx 的 cg0-cg7 打通，验证框架） | 高 | 中 | KL-101a | 这是所有后续 cfx 的地基，建议先单点打通一个 cfx 而不是一次性做全部 64 个 |
| **KL-103a** | `escape` 指令 + 异常退出流程（§5 步骤 0-4）+ cg5 现场寄存器 | 高 | 中 | KL-102a | 与 KL-102a 可能需要合并成一个任务考虑，因为 cg5 现场保存/恢复是 escape 语义的前提 |
| **KL-104a** | 把现有 `trap cfx_smon`（ML-002a host 捷径）升级为真正走 SEE §5 10 步流程（保留 syscall 语义，改造实现路径） | 中 | 中 | KL-102a, KL-103a | 这是"捷径→真实现"的收口任务，双后端 + 现有 E2E 回归（`musl_e2e_exit.test` 等）必须保持通过 |
| **KL-105a** | RegRAS 整体保存/恢复的 ISA 层机制立项调研（先确认 wiki 是否已有 `ldmo-ra`/`stmo-ra` 之外的机制，或需要 spec-decision 新增指令） | 高（不确定性最大） | 未知（先调研） | 无 | 对应 §4.1 新发现，**建议本身先派一个小型调研任务**（不是直接实现），因为连"用什么机制"都还不确定 |
| **KL-106a** | cfx_ptw/cfx_tlb SBI 调用链最小子集（`SET_PTBR`/`ENABLE_PTBR`/`SET_PTE` 三个功能，先不做 `HANDLE_FAULT` 委托链） | 高 | 大 | KL-102a, KL-103a | 建议先解决 §2.3 提到的 4 个 open-spec-issues（TLB fault return / PTW SBI ABI / VA2PA / cross-cfx escape）里至少前两条，否则实现中途会卡在语义不确定上 |
| **KL-107a** | K2 差分/lit 框架扩展：trap 分派向量字段扩展（`tests/vectors/isa/` 新增 exception 类 yaml + `run_differential.py` 字段支持） | 低-中 | 小-中 | KL-104a | 对应 §6.2 第一类，工作量相对小，可以和 KL-104a 并行或紧随其后 |
| **KL-108a** | K2 差分/lit 框架扩展：上下文切换断点+dump 断言机制（基于 gem5 halt-regdump 扩展为通用断点 dump） | 中 | 中 | KL-107a | 对应 §6.2 第二类，是 K3 `__switch_to` 验收的前提，建议在 K3 真正写 context switch 代码前完成 |
| **KL-109a** | K2 差分/lit 框架扩展：测试页表构造小工具 + 页表异常断言扩展 | 中 | 中 | KL-106a | 对应 §6.2 第三类 |
| **KL-110a** | pgtable.h 工作量专项评估（不是实现，是评估）：对照 SEE §2.2.3/2.2.4 的 fragment 位图设计，估算 arch/dadao pgtable.h 需要实现的函数清单+复杂度 | 低 | 小 | 无（可与 KL-105a 并行） | 对应必读清单第 10 条，建议在 K1 收尾、K3 立项前拿到这份评估，用来定 K3 任务粒度 |

**建议执行顺序**：KL-101a（特权切换地基）→ KL-102a/103a（cg 寄存器+escape，可与 KL-105a 并行调研）→ KL-104a（syscall 捷径收口，作为第一个端到端验收里程碑）→ KL-106a（MMU/TLB，需先决 open-issues）→ KL-107a/108a/109a（K2 测试框架扩展，穿插在上面任务中做）→ KL-110a（K3 立项前的工作量校准）。

**不建议**：不建议把"整个 SEE §5 一次性全实现"作为单个任务下发——参照 `feedback_ds_gem5_semantic_unreliable.md`（DS 不适合 gem5/语义细腻活）的既有教训，cg 寄存器组+escape+cfx 路由这类语义细腻、双后端一致性要求高的工作，建议按 cfx 逐个拆分（先 smon 打通，再 ptw/tlb，再其它 per-hart cfx），每个任务收敛到"能独立跑通并双后端验证"的最小单元。

---

## 附：本报告引用的原始文件路径清单

- Wiki（pin `9f378f4426e131903d60a208766086ae74a53c89`）：`DADAO-12-SEE-主管系统运行环境.md`、`DADAO-22-SBI-主管系统二进制接口.md`、`DADAO-13-HEE-超管系统运行环境.md`、`DADAO-23-HBI-超管系统二进制接口.md`、`DADAO-11-AEE-应用程序运行环境.md`（均通过 `git -C ~/DADAO-wiki show 9f378f4...:<path>` 读取）
- DADAO-0628 契约：`contracts/isa/spec.md`（§1.5, §7）、`contracts/abi/spec.md`（§1.1, §1.2, §1.4）、`contracts/exception/README.md`、`contracts/mmu/README.md`、`docs/open-spec-issues.md`
- DADAO-0628 ADR：`docs/adr/0014-libc-syscall-charter.md`、`docs/adr/0015-kernel-bringup-charter.md`
- DADAO-0628 实现：`components/qemu/patches/series`（17 patch）、`components/qemu/patches/0013-dadao-trap-syscall.patch`、`components/gem5/patches/series`（11 patch）、`manifests/spec.lock.toml`、`manifests/components.lock.toml`
- DADAO-0628 测试框架：`tools/run_differential.py`、`tests/vectors/isa/*.yaml`、`tests/lit/E2E/`、`tests/e2e/`、`tests/scripts/run_qemu_test.py`
- 旧项目：`~/toolchain/DADAO/code-agent/designs/sysmode-debug-lessons.md`（B01-B22+L1-L3）、`dadao-mmu-enable-design.md`、`dadao-userspace-plan.md`、`__source/linux-0504`（git log/show 逐提交核实）
