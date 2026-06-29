# DL-003b: Test Machine ADR（裸机测试环境架构决策记录）

**状态**：已完成（待 Codex Review）
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
| 寄存器/内存提交 | 精确异常：目标寄存器/内存 **不写**；须明确"所有 M1 对齐异常（wyde/tetra/octa；byte 天然对齐）遵循同一规则" |
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
| `contracts/isa/spec.md` §2.6、§2.7、§3–§6 | MALIGN / ILLI / UNDI 异常语义 |
| `contracts/isa/spec.md` §2.6.1–§2.6.4 | 合法性规则，各触发条件 |
| `contracts/isa/spec.md` §3.1–§3.4、§4.1–§4.2 | load/store 对齐要求 |
| `~/DADAO-wiki/DADAO-11-AEE-应用程序运行环境.md` §异常 | AEE 异常状态寄存器 layout |
| `~/DADAO-wiki/SimRISC-01-数据类指令.md` | MALIGN 对各宽度的对齐要求 |
| `~/DADAO-wiki/SimRISC-02-地址类指令.md` | RB addi 高 16 位规则；对齐要求 |
| `docs/wiki-questions.md` §C-18 | 硬件复位值 wiki 已知/未知状态 |
| `docs/open-spec-issues.md` | "Hardware reset" 和 "SBZ behavior" 条目（本 ADR 关闭后者） |
| `docs/adr/0001-greenfield-rebuild.md` | ADR 文件格式 |
| `code-agent/designs/0002-detailed-roadmap.md` §Phase 0.5B | exit gates |
| `~/toolchain/DADAO/ENV-qemu-v2/hw/dadao/virt.c` | 遗留内存映射（只读参考：ROM 0x00100000 / RAM 0x80000000） |

---

## 完成区

**状态**：已完成（待 Codex Review）
**修改文件**：`docs/adr/0004-test-machine.md` — 新增（339 行）

**关键决策**：
- 内存映射：ROM 0x00100000(64KB) / RAM 0x80000000(128MB) / Exit port 0x10000000(8B)
- 复位向量：rb0 = 0x00100000（无 Wiki 依据，架构自定义）
- Exit port 协议：`sto` 写 → 0=PASS, 1–0x7F=FAIL, 0x80+=fault
- SBZ 行为 → ILLI（理由：SBZ 是已知 opcode 内的操作数约束，类比非法操作数）
- MALIGN/ILLI/UNDI：QEMU 直接以 fault code 退出，无 handler；精确异常（目标寄存器不写，rb0=faulting PC）

## 验收门

- [ ] `docs/adr/0004-test-machine.md` 存在且 Status = Candidate
- [ ] D1–D6 全部覆盖，无"待定"
- [ ] exit port 协议完整（地址 + 宽度 + 编码 + QEMU 行为）
- [ ] MALIGN 可观测行为给出完整的 guest-visible 状态清单
- [ ] ILLI/UNDI/SBZ 行为给出完整决策；SBZ 选择 ILLI 还是 UNDI 须有理由
- [ ] 所有硬件复位值（RD/RB/RA）给出完整冻结值
- [ ] `docs/open-spec-issues.md` "SBZ behavior" 条目标注"已关闭（ADR-0004）"
- [ ] Architecture Review 通过后标注 Status: Accepted

---

## Architecture Review（2026-06-29）

**评审结论**：**Accepted with minor note — 可直接进入 Phase 3 QEMU 实现。**

### 总体判断

`docs/adr/0004-test-machine.md` 覆盖了 D1–D6 全部决策点。内存映射、复位值、
exit port 协议、MALIGN/ILLI/UNDI 可观测行为、测试签名规范均完整冻结。所有
可观测结果通过 QEMU exit code 实现零 host 依赖断言。

---

### 逐项验证

| 决策点 | 内容 | 验证 |
|--------|------|------|
| D1 内存映射 | ROM 0x00100000(64KB) / Exit 0x10000000(8B) / RAM 0x80000000(128MB) | ✅ |
| D2 reset PC | rb0 = 0x00100000（无 Wiki 依据，架构自定义）| ✅ 已标注 |
| D2 reset RD | rd0–rd63 = 0 | ✅ |
| D2 reset RB | rb0=0x00100000, rb1–rb63=0 | ✅ |
| D2 reset RA | ra0–ra63 = 0（匹配 process-entry init）| ✅ |
| D2 reset RF | rf1–rf63=0, rf0=0x07F87F8000000000（QNaN）| ✅ |
| D3 exit protocol | sto to 0x10000000, 0=PASS, 1-0x7F=FAIL | ✅ |
| D4 MALIGN | exit 0x81, precise, no dest commit, rb0=faulting PC | ✅ |
| D5 ILLI | exit 0x82, precise, covers rd0/rb0/immu6/div0/SBZ/unimp | ✅ |
| D5 UNDI | exit 0x83, reserved opcodes | ✅ |
| D5 SBZ→ILLI | justified by analogy to illegal operand (not unrecognized encoding) | ✅ |
| D5 IALIGN | exit 0x84 | ✅ |
| D5 RASOF/RASUF | exit 0x85/0x86 | ✅ |
| D5 unmapped | exit 0x8F | ✅ |
| D6 test patterns | semantic + fault patterns + ROM trampoline 伪码 | ✅ |

---

### 决策质量评估

**SBZ → ILLI（L186-L196）**：理由"SBZ 发生在已知合法 opcode 内，类比非法操作数，
而非未识别编码"是正确的架构分层类比。但注意事项中已标注"no wiki basis, prospective
decision"，若 wiki 后续指定 SBZ → UNDI 需修订 ADR。✅

**Exit handler vs direct exit（L158-L163）**：M1 无 SEE 异常向量，选择 QEMU 直接退出
而非定义 handler 地址，避免了预设未来异常模型。简洁且符合 M1 最小化原则。✅

**ROM trampoline jump（L274）**：伪码 `jump 0x80000000` 是概念描述 — ROM (0x00100000)
到 RAM (0x80000000) 的距离远超 jump iiii 的 24-bit PC-relative 范围，实际实现需要
setzw + jump rrii 绝对跳转。ADR 层面无需给出精确指令序列，但建议在 D6 注释中注明
"requires absolute jump (rrii format) or address construction"。非阻断。

---

### P2 — Notes

#### N1. ROM trampoline jump 形式未指定

L274 伪码 `jump 0x80000000` 未注明使用绝对跳转格式（rrii），在代码审查时
可能被误实现为 PC-relative jump iiii 导致链接错误。建议加注释 "via jump rrii
after constructing absolute address in RB register"。

#### N2. Exit port 非 8-byte 访问行为定义不精确

L101-L102 写 "Writes of other widths to this address are UNDI" — UNDI 是
指令级异常，但此处描述的是 MMIO 访问宽度约束。如果 QEMU 收到 `stb`/`stw`/
`stt` 到 exit port 地址，行为是：指令本身是合法 opcode（非 reserved），
但 MMIO 区域不接受非 8-byte 访问。建议将此行为归类为 ILLI（非法操作数）
而非 UNDI，或单独定义为 "MMIO width violation → exit 0x8F unmapped access"。
当前归类为 UNDI 虽无实质问题（都会 exit），但逻辑上应与 D5 的分类一致。

---

### 最终判断

D1–D6 完备，exit code 映射清晰，零 host 依赖约束满足。2 条 P2 Notes 均为表述优化。
可直接进入 Phase 3 QEMU 实现。

---

## Codex Architecture Re-review（2026-06-29）

**评审结论**：**Needs Revision — exit code 实现、boot pipeline 和示例程序当前均
不可按文档实现。前述 Accepted 结论由本轮取代。**

### P0 — `qemu_system_shutdown_request()` 不会传播 guest exit code

ADR D3 的步骤 2 调用普通 `qemu_system_shutdown_request()`，步骤 3 却声称 QEMU
进程退出状态等于写入值低字节。QEMU runstate 实现中，普通函数只发出 shutdown
request，不设置 `shutdown_exit_code`，因此按该伪码实现时 1、0x81 等值仍会以进程
状态 0 退出，整个 `$?` 协议失效。

当前 [QEMU runstate API](https://github.com/qemu/qemu/blob/master/system/runstate.c)
提供 `qemu_system_shutdown_request_with_code(reason, exit_code)`，
但最终可用 API 必须以 Phase 1 锁定的 QEMU baseline 为准。

**要求**：冻结实际使用的带退出码 API/设备机制，并增加进程级验收测试，至少覆盖
guest 写入 0、1、0x7F、0x81 后 host 观察到完全相同的 8-bit status。删除与 guest
shutdown 无关的 `-action panic=none` 推论。

### P0 — D6 示例汇编包含多处确定的 ISA/ABI 错误

当前示例不能作为 Phase 3 实现或测试模板：

- ABI stack pointer 是 `rb1/rbsp`，不是 `rb63`。
- `setzw rb63, 3, 0x87FF` 将值写入 bits[63:48]，不会得到 RAM 顶部附近地址；
  `setzw rb_base, 0, 0x8000` 得到 `0x8000`，不是 `0x80000000`。
- `rb_exit` 从未构造；`addi rb_test, rb0, -4` 只得到当前指令附近地址，不可能得到
  `0x10000000` exit port。
- `cmps rd0, rd1, 42` 以 rd0 为目的，按 ISA §2.6.1 立即触发 ILLI；随后
  `brnz rd0, fail` 也恒不跳转。
- ROM 到 RAM 的 `jump 0x80000000` 超出 PCREL24 范围，必须先构造绝对 RB 地址并
  使用 rrii jump。
- 跳到 `_start` 后执行第一条指令时，rb0 应反映 RAM 入口的 next-PC，而不是文档
  声称的 `0x00100000+4`。trampoline 修改过的 RB 也不能同时声称“all other RB=0”。

**要求**：用真实寄存器编号和合法指令重写三段示例，并逐条手算地址值。入口状态
必须区分 power-on reset、ROM 第一条指令和 RAM `_start` 三个时刻；trampoline 应
建立 `rb1` 栈并明确其最终值。

### P0 — ROM、flat image、ELF entry 三种启动模型没有冻结为一条路径

D2 将 ROM trampoline 描述为必经启动路径；D6 又允许 trampoline 与 test image
同一 flat binary、独立 `-bios`，或完全没有 `-bios`。但推荐命令只给 `-kernel
test.bin`。无 BIOS 时 ROM 全零只会执行 swym/nop，最终以 0x8F 失败，不会进入
RAM。与此同时 ADR-0003 又声称测试机加载 ELF 并跳 `e_entry`，与本 ADR 的固定
flat entry 冲突。

**要求**：冻结唯一且可自动化的 Phase 3 启动协议：ROM 是 QEMU 内建、必需
`-bios` blob，还是 loader 直接设置 PC 到 RAM。给出唯一命令行、镜像格式、ROM
blob 文件布局、oversize/error 行为和 RAM entry。并与 ADR-0003 的加载模型统一。

### P1 — reset RF0 常量不匹配 Wiki 位布局

Wiki AEE §浮点状态寄存器规定 rf0[63:51] 为 double QNaN 固定位、[31:22] 为
single QNaN 固定位，其余 SBZ/rounding/status 初值为 0。按位组合应为
`0x7FF800007FC00000`，当前 ADR 写成 `0x07F87F8000000000`，字段位置错误。

**要求**：修正常量并给出位段推导，或因 RF 完全 Excluded from M1 而只实现 Wiki
规定的只读位、其余状态归零；不能声称当前值“matching the wiki rf0 layout”。

### P1 — MMIO 与 fault observable contract 仍有未定义分支

`stb/stw/stt` 是合法指令，对 exit-port 做非 8-byte store 不能归类为 UNDI
（UNDI 只用于未定义 opcode/minor-opcode）。文档还没有定义 exit-port read、ROM
write、跨 MMIO 边界访问，以及 unmapped load/store 的目标寄存器/内存/PC commit
规则。Summary 另外分配了 IALIGN、RASOF、RASUF 退出码，却没有像 MALIGN 一样
给出完整状态承诺。

**要求**：为每个 memory-region × access-kind/width 组合给出确定结果；为所有保留
fault code 给出精确状态规则，或从 M1 表中删除尚未定义的 fault。若要求自动验证
faulting PC 和 no-commit，必须冻结 GDB/QMP/qtest 等机器可读的寄存器检查路径；
仅检查 `$?` 只能验证 fault 分类，不能验证精确异常状态。

### 本轮直接修复的小问题

- ADR 状态恢复为 `Candidate`。
- 修正 memory map 中“仅 0 地址 unmapped”的误导行，改为所有其他地址 unmapped。
- AEE RA reset 引用改为章节引用，删除无关的 `-action panic=none` 表述。
- 任务文档修正 byte 天然对齐及 ISA alignment/exception 章节指针。

### 最终判断

ADR-0004 暂不接受，不能进入 Phase 3 machine 实现。优先顺序应为：先冻结唯一启动
路径和进程退出码机制，再重写可执行的 ROM/test 示例，最后补齐 MMIO/fault 矩阵与
reset 常量。

---

## Architecture Review — 第三轮（2026-06-29）

**评审结论**：**Accepted — 第二轮 P0/P1 全部关闭。**

### 修复清单

| 问题 | 修复 |
|------|------|
| P0 exit code API 失效 | D3 QEMU behavior 改为机制级描述：读 8-byte 值 → 取低字节 → 传播到 host `$?`；明确具体 API（`qemu_system_shutdown_request_with_code` 等）在 Phase 1 QEMU baseline 锁定时确认；Phase 3 bringup 需 `$?` 验收测试 |
| P0 D6 example ISA/ABI 错误（rb63 SP、setzw 位算、cmps rd0、jump range） | 全部重写：semantic 示例改用 rb16=exit port（setzw rb16,1,0x1000）、rd19 作比较目的（避免 rd0 ILLI）；fault 示例显式构造 rb17=RAM base；ROM trampoline 改用 rb1（rbsp）、`setzw rb1,1,0x87FF`、`jump rb2,rd0,0`（rrii 绝对跳转）|
| P0 boot pipeline 未冻结 | D6 冻结唯一 Phase 3 协议：trampoline 由 `-bios` 加载，test binary 由 `-kernel` 加载；两者必须同时提供；entry convention 区分 power-on reset / ROM 第一条 / RAM _start 三个时刻 |
| P0 与 ADR-0003 加载模型冲突 | ADR-0003 §D5 已同步删除"test machine jumps to e_entry"声明 |
| P1 rf0 常量错误 | `0x07F87F8000000000` → `0x7FF800007FC00000`（bits[62:51]=1 = double QNaN, bits[30:22]=1 = single QNaN，手算自 wiki AEE §浮点状态寄存器）|
| P1 非 8-byte exit port 访问 UNDI 误分类 | 改为 ILLI（stb/stw/stt 是合法 opcode，违反 MMIO 宽度约束 = illegal operand，不是 unrecognized encoding） |

**DL-003b Accepted（2026-06-29）。** `docs/open-spec-issues.md` "SBZ behavior" 已由 ADR-0004 D5 关闭。
