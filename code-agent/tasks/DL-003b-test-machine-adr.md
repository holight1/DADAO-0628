# DL-003b: Test Machine ADR（裸机测试环境架构决策记录）

**执行环境**：本地 DS · DADAO-0628

---

## 目标

产出 `docs/adr/0004-test-machine.md`（ADR-0004），冻结 Phase 3 QEMU 裸机测试环境
的所有可观测行为。本 ADR 使得测试断言可以完全依赖 guest-visible 状态，
不依赖 host 日志、QEMU 输出、或超时。

---

## 背景

Phase 3 QEMU 实现必须在裸机（bare-metal）环境下运行语义/合法性/边界向量测试。
测试需要可编程方式报告 pass/fail（exit port），以及对 MALIGN、ILLI、UNDI 等异常
的 guest-visible 状态断言。

Wiki（`~/DADAO-wiki`，commit `13a414d`）提供了部分异常语义，但没有定义测试机器的
内存映射、exit 协议或硬件复位值全集。本 ADR 作为原始决策文件填补这些空白。

遗留 `ENV-qemu-v2/hw/dadao/virt.c`（`~/toolchain/DADAO/`，只读参考）已有一套
内存布局：ROM 0x00100000 / UART 0x10000000 / RAM 0x80000000，但无 exit port 设计。
本 ADR 须独立决策，可参考遗留布局但须说明是采用、修改还是另行设计。

---

## 交付物

**文件**：`docs/adr/0004-test-machine.md`

### 必须覆盖的决策点

#### D1. 内存映射

给出 M1 测试机器的完整地址空间分配：

| 区域 | 必须决策内容 |
|------|-------------|
| ROM / boot ROM | 起始地址、大小（须能容纳最小 trampoline 代码） |
| RAM | 起始地址、大小（须能容纳测试程序 + 栈 + 数据） |
| Exit port | MMIO 地址（须与 ROM/RAM 不重叠）；设计为 8-byte 对齐 MMIO 写地址 |
| 保留区 | 其他区域的处理（非 mapped 区域访问的行为：是 MALIGN 等价还是其他？） |

所有地址须为 48-bit 有效地址（`contracts/isa/spec.md` §2.6.2 C-19：有效地址为低 48 位）。

#### D2. 复位向量与入口点

| 事项 | 决策要求 |
|------|---------|
| 硬件复位后 PC 初值 (`rb0`) | 必须冻结（Wiki C-18a：rb0 复位值 = cfx_power_hypv_excp_vector；M1 bare-metal 下的等价值是？） |
| 测试程序加载地址 | ELF 入口点？固定 RAM 基址？两者如何协调 |
| 加载方法 | flat binary 还是 ELF 加载（对应 QEMU `-bios`/`-kernel` 的哪种） |
| RD 寄存器硬件复位值（rd0–rd63） | Wiki 仅明确 rd0=0；其余决策（0 还是 UNPREDICTABLE？） |
| RB 寄存器硬件复位值（rb1–rb63） | Wiki 明确 rb0=reset_vector, rb0[63:48]=0；rb1–rb63 决策 |
| RA 寄存器硬件复位值（ra0–ra63） | Wiki 明确 process-entry 全零，但硬件复位与 process-entry 不同；须冻结 |

#### D3. Exit Port 协议

须给出完整的 pass/fail 签名编码，使得：
1. 测试代码通过一次 MMIO 写触发退出
2. QEMU 将写入值映射为退出码（exit code）
3. 测试框架可通过 QEMU 退出码无歧义地判断 pass/fail

决策内容：
- Exit port 的字节宽度（建议 8 字节，与 `sto` 对齐要求一致）
- 写入值语义：0 = pass，非零 = fail（还是其他编码？）
- 是否支持多字段编码（测试编号 + 结果 + 错误码）？M1 最小化即可
- 写入 exit port 后 QEMU 的行为（立即退出？flush 数据？）

#### D4. MALIGN 可观测行为

`contracts/isa/spec.md` §6.2 和 Wiki SimRISC-01/02 说明 MALIGN 是精确异常。
本 ADR 须冻结 M1 bare-metal 下的 MALIGN 可观测状态：

| 问题 | 须决策内容 |
|------|-----------|
| 异常类型 | guest 看到什么（MALIGN exception code in 哪个寄存器/内存位置？） |
| faulting PC | guest 能读到触发异常的指令地址（`rb0`？还是别的寄存器）？ |
| 寄存器/内存提交 | 精确异常：目标寄存器/内存 **不写**；须明确"所有 M1 对齐异常（byte/wyde/tetra/octa 各宽度）遵循同一规则" |
| 测试断言方式 | 测试程序如何 assert MALIGN 发生（检查 PC 不前进？异常状态字？exit port code？） |

若 M1 bare-metal 没有 SEE 异常向量（无 OS），须说明 MALIGN 如何 surface 到 guest（QEMU 直接 abort？写 exit port？进入一个固定的异常 handler？）。

#### D5. ILLI/UNDI 可观测行为

与 D4 平行，冻结非法指令异常的可观测行为：

| 异常类型 | 决策要求 |
|---------|---------|
| ILLI（`contracts/isa/spec.md` §2.6.1） | guest 可观测状态，faulting PC，寄存器不提交 |
| UNDI（保留编码，Wiki C-02 → UNDI） | 同上 |
| SBZ 字段非零 | 决策 ILLI 还是 UNDI（关闭 `docs/open-spec-issues.md` "SBZ behavior" 条目）；给出理由 |

须说明：
- 在 M1 bare-metal 无 SEE 的情况下，test harness 通过何种机制区分 ILLI 和正常 exit。
- 非法指令是否会导致 QEMU 崩溃（不可接受），还是产生可断言的 guest 状态。

#### D6. 测试签名规范

将 D3/D4/D5 整合为一个测试程序可使用的 API 规范：

```
对于语义测试：
  ... 执行被测指令 ...
  检查预期结果
  sto rd_pass_code, rb_exit_port, 0   ; 写 exit port = pass (0)

对于异常测试：
  安装异常 handler（或设计无 handler 的断言方法）
  执行触发异常的指令
  验证 PC/寄存器状态
  sto rd_result_code, rb_exit_port, 0  ; 写 exit port
```

须说明：在无操作系统的 bare-metal 环境下，如何安装"最小异常 handler"，
或者是否设计 "QEMU 直接映射 guest fault → exit code" 使得不需要 handler。

---

## 约束

1. **零 host 依赖**：所有可观测结果必须来自 QEMU exit code 或 guest 寄存器状态，
   不得依赖 host log、QEMU stderr、或超时判定 pass/fail。
2. **可实现性**：决策须在标准 QEMU `hw/dadao/` 机器实现中可实现，
   不需要 out-of-tree QEMU patch。
3. **精确异常承诺**：MALIGN/ILLI/UNDI 均为精确异常（ISA contract 保证），
   ADR 须明确"精确异常"在 M1 bare-metal 下的实际含义（无 commit = 哪些状态不变）。
4. **对齐约束**：exit port 写须使用 `sto`（8 字节对齐）；exit port 地址须为 8B 对齐。
5. **Wiki 缺失即决策**：硬件复位值、exit port、内存映射均无 Wiki 依据，
   须标注"无 Wiki 依据，架构自定义"并给出理由。
6. **格式**：遵循 `docs/adr/0001-greenfield-rebuild.md` 格式。

---

## 参考指针

| 资源 | 用途 |
|------|------|
| `contracts/isa/spec.md` §6 | MALIGN / ILLI / UNDI 异常语义 |
| `contracts/isa/spec.md` §2.6.1–§2.6.4 | 合法性规则，各触发条件 |
| `contracts/isa/spec.md` §3.2 | load/store 对齐要求 |
| `~/DADAO-wiki/DADAO-11-AEE-应用程序运行环境.md` §异常 | AEE 异常状态寄存器 layout |
| `~/DADAO-wiki/SimRISC-01-数据类指令.md` | MALIGN 对各宽度的对齐要求 |
| `~/DADAO-wiki/SimRISC-02-地址类指令.md` | RB addi 高 16 位规则；对齐要求 |
| `docs/wiki-questions.md` §C-18 | 硬件复位值 wiki 已知/未知状态 |
| `docs/open-spec-issues.md` | "Hardware reset" 和 "SBZ behavior" 条目（本 ADR 关闭后者） |
| `docs/adr/0001-greenfield-rebuild.md` | ADR 文件格式 |
| `code-agent/designs/0002-detailed-roadmap.md` §Phase 0.5B | exit gates |
| `~/toolchain/DADAO/ENV-qemu-v2/hw/dadao/virt.c` | 遗留内存映射（只读参考：ROM 0x00100000 / RAM 0x80000000） |

---

## 验收门

- [ ] `docs/adr/0004-test-machine.md` 存在且 Status = Candidate
- [ ] D1–D6 全部覆盖，无"待定"
- [ ] exit port 协议完整（地址 + 宽度 + 编码 + QEMU 行为）
- [ ] MALIGN 可观测行为给出完整的 guest-visible 状态清单
- [ ] ILLI/UNDI/SBZ 行为给出完整决策；SBZ 选择 ILLI 还是 UNDI 须有理由
- [ ] 所有硬件复位值（RD/RB/RA）给出完整冻结值
- [ ] `docs/open-spec-issues.md` "SBZ behavior" 条目标注"已关闭（ADR-0004）"
- [ ] Architecture Review 通过后标注 Status: Accepted
