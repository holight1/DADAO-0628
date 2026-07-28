# K2 裸机内核态回归契约与结构化 oracle（KL-140a 冻结）

**状态**：Frozen（2026-07-28，KL-140a）
**依赖**：KL-139a（K1 双后端单镜像集成门，已完成）
**后续依赖者**：KL-141a～KL-145a（不得修改本文件已冻结的布局、枚举与口径；
确需变更时另立任务并同步 bump schema version）
**参考**：`docs/adr/0015-kernel-bringup-charter.md`、
`docs/reviews/kernel-bringup-recon-2026-07-18.md` §4/§6、
`docs/reviews/kernel-mmu-interrupt-recon-20260726.md`、
`code-agent/tasks/KL-139a-k1-k2-integration-probe.md`、
`contracts/abi/spec.md` §1、`contracts/isa/spec.md` §4.9/§5.6/§8

---

## §0 定位

K2 在接触真实 Linux 之前，用裸机内核态程序钉死四类机制：

1. cooperative context switch；
2. trap dispatcher 与 preemptive full context；
3. PTBR 地址空间切换与显式 TLB invalidate；
4. timer 驱动的 context/MMU 综合切换。

本文件冻结这些机制验证所需的**状态所有权分类、一次性完整 frame
layout、结构化 guest report 格式、差分与 oracle 口径**。本任务不实现
context switch、调度器或 page-fault policy，也不修改 QEMU/gem5 架构语义。

K0 调研（`kernel-bringup-recon-2026-07-18.md` §6.2）曾建议扩展单指令
privileged YAML、通用 breakpoint+dump 与测试页表生成器。自那以后工程已具备
FullSystem carrier、页表/image 生成、guest 自校验和双后端单镜像运行
（KL-124a～KL-139a），因此 K2 **不再优先建设**单指令 privileged YAML 或
通用断点调试设施；多指令内核流程的正式断言载体是本文件冻结的结构化
report + 独立 oracle，宿主侧可复用实现为
`tests/scripts/k2_report.py`（见 §5）。

---

## §1 上下文类别契约

三类状态所有权严格区分，后续任务不得混用。

### 1.1 cooperative task context

cooperative switch 是任务**主动让出**控制流（自愿调用切换原语），保存
范围是"恢复该任务继续执行所必需的全部状态"，一次性冻结如下：

| 状态 | 契约 |
|---|---|
| resume PC / control state | 保存于 frame w0（恢复后第一条执行指令的 48 位 PC） |
| `rb1` SP、`rb2` FP | 保存/恢复（`contracts/abi/spec.md` §1.2 callee-saved） |
| `rb3` GP、`rb4` TP | **K2 完整任务上下文必须保存/恢复**。这只是因为它们属于"恢复任务执行环境"的一部分；**不得**据此把 rb3/rb4 外推为普通函数调用 ABI 的 callee-saved 寄存器（ABI §1.2 对二者的 callee-saved 定性保持 OPEN，本契约不改变它） |
| `rd32`～`rd63`、`rb32`～`rb63` | 保存/恢复（ABI §1.1/§1.2 callee-saved） |
| 完整 `ra0`～`ra63` | 保存/恢复，通过现行 `ldmo-ra`/`stmo-ra` contract（`contracts/isa/spec.md` §4.9：按 `i` 递增顺序逐槽 opaque 64-bit 传输，bits[63:48] 引用计数字段原样搬运，8-byte 对齐，MALIGN/ILLI 合法性不变）。AEE"进程切换时须保存和恢复全部 ra0-ra63"的要求（`kernel-bringup-recon-2026-07-18.md` §4.1）由此闭合 |
| RF | **不包含**。M1 明确排除（`contracts/isa/spec.md` §7），K2 guest 代码不触碰 RF，trap/cooperative 路径均不保存，保持 non-claim |

cooperative switch 不保存 caller-saved 的 rd8～rd31/rb8～rb31：切换原语
本身是一次普通调用，调用者（让出方）按 ABI 已假设这些寄存器被 clobber。
rd0（hardwired zero，immutable）与 rb0（read-only PC）不属于软件可写
状态，不出现在任何 frame 中。

### 1.2 preemptive trap context

trap（同步异常或异步中断）可在任意指令边界打断任务，**必须对所有软件
可写、可能 live 的 RD/RB 状态透明**，不能只保存 cooperative 的
callee-saved 子集。冻结如下：

**软件 trap frame 实际保存范围（每层一次完整保存）**：

| 范围 | 说明 |
|---|---|
| `rd1`～`rd63`（63 项） | 全部软件可写 RD。含 rd1（rderrno，kernel-use）与 rd2～rd7（ABI-reserved）：reserved 的含义是"编译器不分配"，不是"硬件不可写"或"永不 live"；为保证对任意未来使用透明，一并保存/恢复 |
| `rb1`～`rb63`（63 项） | 全部软件可写 RB，含 rb1～rb4 与 reserved 的 rb5～rb7，理由同上 |
| 完整 `ra0`～`ra63`（64 项） | RegRAS 整栈（`contracts/isa/spec.md` §5.6）。trap handler 自身可执行 call/ret，必须对被中断方的 RAS 透明；经 `ldmo-ra`/`stmo-ra` 同 §1.1 contract |

**不保存项及其处理**：

| 项 | 处理 |
|---|---|
| `rd0` | immutable（hardwired zero），不保存；恢复路径不写 rd0，由硬件保证其恒为 0 |
| `rb0` | read-only PC，软件不可写，不保存；断点/恢复 PC 由 CFX 硬件 frame 的 `excp_cause_ip` 承载（见下） |
| RF | M1 排除，同 §1.1，non-claim |

**CFX 自动保存 vs 软件 trap frame 的职责分界**：

- 硬件 entry（SEE §5 步骤 7-10，KL-122a 通用精确载体）自动写入目标
  cfx 的 cg5 frame：`excp_prev_run_mode`(rc0)、`excp_prev_cfx_mask`(rc1)、
  `excp_cause_id`(rc2)、`excp_cause_ip`(rc3)、`excp_cause_info`(rc4)，
  以及项目本地 E1 扩展 `excp_prev_cfx_code`(rc5)
  （`contracts/isa/spec.md` §8.2/§8.5.5）。mode/mask/cfx/PC 的恢复由
  `escape` 硬件语义完成，**软件不重复保存/恢复这组控制状态**。
- 软件 trap frame 负责：通用寄存器组（rd1-63/rb1-63/ra0-63）+ 硬件 cg5
  frame 六字段的**诊断拷贝** + 本层所有权/嵌套元信息（见 §2.2 布局）。
- `escape cfx_<name>,N` 的恢复语义（含 E1 的 `prev_cfx_code` 恢复）
  完全由硬件完成；软件只负责在此之前把通用寄存器组从本层 frame 恢复
  回来。软件不得用写 cg5 的方式"伪造"返回现场（K2 guest 不在恢复路径
  上写 rc0/rc1/rc3/rc5）。

**trap frame 落点与 prologue 保存序列（一次性冻结）**：

trap frame 不占用静态内存槽（那需要先物化地址、必须先 clobber 一个
live 寄存器），而是落在**进入时刻当前栈的向下保存窗口**
`[old_sp-0x630, old_sp)`。prologue 严格按以下顺序执行，全程不需要任何
尚未保存的 scratch：

0. 对 timer 这类 private level/pending 会在 common pending 清除前重新
   latch 的异步源，entry 的第一条指令允许用**预先装入且本来就属于 live
   context 的 RD 值**执行一次 `cfx2rc`，只把本 cfx 的
   `excp_cause_mask` 设为全屏蔽。该指令不得写 RD/RB/RA、不得访存、不得
   进入 handler body；被读取的 RD 仍由下一步原值保存。这是防止同 cfx
   在第一条 `sto` 前覆盖唯一 cg5 frame 的 entry exclusion，不是可任意
   插入 scratch 操作的豁免。非 level/re-latch 源不得借此扩大 prologue。
1. 以 `rb1` 为基址、signed-12 **字节**偏移 `sto`（`contracts/isa/spec.md`
   §3.2/§4.1，EA=`rb1+sext_12(imm)`，覆盖 ±2048 字节，0x630=1584 在
   范围内）把 rd1～rd63 存入窗口；`rb1` 全程不变。
2. 同法存入 rb1～rb63（`sto rb1, rb1, imm` 合法：基址不变，旧值入窗）。
3. 此刻全部 RD/RB 已入窗，用一个**已保存的** rd 作 scratch 装入负偏移
   常量，两条 `stmo-ra`（immu6≤63）保存 ra0～ra62 与 ra63。
4. `cfx2rd` 读硬件 cg5 六字段到 scratch rd 并写入 frame 头，再写
   `owner_cfx` 与 `nest_level`（嵌套深度由 handler 软件维护）。
5. 更新 `rb1`（下压 0x630 或切换到 handler 专用栈）；此后才允许
   handler 主体、call/ret 与按需解除异步 mask。

**栈窗协议与不可重入条件**：

- 任何 trap 可到达的时刻（异步未屏蔽的每个指令边界、任何同步 fault
  点），当前 `rb1` 的 `[rb1-0x630, rb1)` 必须 writable、resident
  （访问不触发 PTW/TLB fault）、8 字节对齐。K2 的每个任务栈和每个
  handler 栈都必须保持该不变量。
- 保存窗口**不可重入**：第 5 步完成之前，handler 不得解除任何异步
  mask、不得执行窗口外可能 fault 的访存（窗口内地址已由协议保证
  resident）。嵌套 entry 只能发生在 SP 已更新之后，此时自然在新 SP
  的自有窗口中压入新一层 frame。
- 恢复为严格逆序：scratch rd + 两条 `ldmo-ra` 恢复 ra0～ra63 → `ldo`
  恢复 rd1～rd63 → rb2～rb63 → **`rb1` 必须最后恢复**（此后窗口失效）
  → 立即 `escape`。

**嵌套（E1）时每层 frame 的所有权与恢复顺序**：

- 每一次 cfx entry 在当前栈上压入**一个独立的 trap frame**，所有权
  属于该次 entry；嵌套链天然形成栈式 LIFO。
- 恢复严格 LIFO：内层 handler 完成其 `escape`（硬件从内层 cfx 的 cg5
  恢复 mode/mask/PC/prev_cfx_code）之后，外层 handler 才恢复自己的通用
  寄存器组并执行自己的 `escape`。
- **同 cfx 递归重入为 non-claim**：硬件每 cfx 只有一份 cg5 frame，同
  cfx 再进入会覆盖之。K2 嵌套链仅覆盖跨 cfx 嵌套且每个 cfx 在链中至多
  出现一次——这正是 KL-119a/KL-120a 已冻结并实现的 E1"普通逐帧嵌套
  返回"范围（`contracts/isa/spec.md` §8.5.5），与 KL-139a 验证过的
  `cfx_tlb→cfx_ptw→cfx_tlb` 链同型。单次 escape 跨多层的 shortcut 同样
  保持 non-claim（§8.5.5 末段）。

### 1.3 address-space context

| 条款 | 契约 |
|---|---|
| PTBR/root 与 task 的绑定 | 每个任务绑定 `(asid, ptbr_root)`：asid ∈ 0..63 即 `VA[47:42]` 选择的 PTBR 序号；ptbr_root 为该 PTBR 寄存器的原始存储值（L1 基址 bits[63:16]）。绑定落点是 cooperative frame 的 w1/w2 字段（§2.1），随任务描述符一起生命周期管理 |
| 切换顺序 | 恢复目标任务前必须：写 `cfx_ptw` PTBR[asid]（若与当前不同）→ **执行显式 TLB invalidate** → 才能恢复目标任务的通用状态并 resume。K2 冻结的 invalidate 粒度：目标任务 asid 对应的整个 set（`start` = 该 set 内全范围、`size` 覆盖 4 TiB set；`contracts/isa/spec.md` §8.5.3 测试 profile 下等价于逐 set 全清），允许后续场景按需收窄为 range invalidate，但不得以"更省"为由省略 |
| TLB protocol generation | guest 软件维护一个单调递增计数器，每次显式 invalidate 后 +1，写入 report 对应 checkpoint（§3）；oracle 据此核对 invalidate 发生的确切次序 |
| disable→enable | `cfx_tlb_enable` 关闭再打开后旧 entry 是否保留保持 **non-claim**（KL-129b 已冻结的边界），K2 任何正确性论证不得以其为前提 |

### 1.4 范围边界（non-claim 汇总）

本轮 K2 只覆盖**单 hart、supervisor kernel task**。以下全部保持
non-claim，后续任务的 pass 清单不得包含、证据不得外推：

- user↔supervisor task switch；
- RF、Atomics/SMP、多 hart；
- 真实 UART/PLIC/device 协议（K2 可继续使用 K1 timer 与 `K1_EXT0`
  合成测试源验证内核软件策略，但不得外推为真实设备驱动证据）；
- Linux clocksource/clockevent/irqchip API；
- TLB 性能/时序与 gem5 Minor/O3 异步行为（功能 profile 见
  `contracts/isa/spec.md` §8.5.2/§8.5.3）；
- Linux paging allocator 与真实 Linux page-fault policy。

---

## §2 一次性完整 frame layout

以下布局**一次冻结**：字段、宽度、对齐、顺序、总大小在 KL-141a～145a
期间不得按发现的问题逐步扩容；确需变更必须 bump report schema version
并经独立任务评审。所有字段 8 字节宽、big-endian、起始地址 8 字节对齐
（`stmo-ra` 元素对齐要求）；除注明外保留字段写入 0。

### 2.1 cooperative task frame（总 135 word = 1080 字节）

| offset | 字段 | 说明 |
|---:|---|---|
| 0x000 | w0 `resume_pc` | 恢复执行的第一条指令 PC，bits[63:48]=0 |
| 0x008 | w1 `asid` | 地址空间 id（0..63），bits[63:6] 写 0 |
| 0x010 | w2 `ptbr_root` | 该任务 PTBR 原始存储值（L1 基址 bits[63:16]） |
| 0x018 | w3 `rb1_sp` | 栈指针 |
| 0x020 | w4 `rb2_fp` | 帧指针 |
| 0x028 | w5 `rb3_gp` | 全局指针 |
| 0x030 | w6 `rb4_tp` | 线程指针 |
| 0x038 | w7..w38 `rd32..rd63` | 32 项，按下标递增 |
| 0x138 | w39..w70 `rb32..rb63` | 32 项，按下标递增 |
| 0x238 | w71..w134 `ra0..ra63` | 64 项 RegRAS 整栈，按 `stmo-ra` 槽序（raha+i 递增），每槽 opaque 64-bit |
| 0x438 | 结束 | 总大小 0x438 = 1080 字节 |

### 2.2 preemptive trap frame（总 198 word = 1584 字节，每层一份，落于当前栈）

frame 位于进入时刻当前栈的 `[old_sp-0x630, old_sp)` 保存窗口
（§1.2 prologue 与栈窗协议）；下表 offset 相对 frame base =
`old_sp-0x630`。布局本身与层次无关，嵌套时每层各占一份。

| offset | 字段 | 说明 |
|---:|---|---|
| 0x000 | w0 `owner_cfx` | 本层 entry 的 `inner_cfx_code`（所有权标识） |
| 0x008 | w1 `saved_cause_id` | 硬件 cg5/rc2 的诊断拷贝 |
| 0x010 | w2 `saved_cause_ip` | 硬件 cg5/rc3 的诊断拷贝（断点 PC；恢复由 escape 硬件完成，软件不据此跳转） |
| 0x018 | w3 `saved_cause_info` | 硬件 cg5/rc4 的诊断拷贝 |
| 0x020 | w4 `saved_prev_mode` | 硬件 cg5/rc0 的诊断拷贝 |
| 0x028 | w5 `saved_prev_cfx_mask` | 硬件 cg5/rc1 的诊断拷贝 |
| 0x030 | w6 `saved_prev_cfx_code` | 硬件 cg5/rc5（E1）的诊断拷贝 |
| 0x038 | w7 `nest_level` | 嵌套深度，根层=0，每深一层 +1 |
| 0x040 | w8..w70 `rd1..rd63` | 63 项，按下标递增 |
| 0x238 | w71..w133 `rb1..rb63` | 63 项，按下标递增 |
| 0x430 | w134..w197 `ra0..ra63` | 64 项 RegRAS 整栈，同 §2.1 |
| 0x630 | 结束 | 总大小 0x630 = 1584 字节 |

两个 frame 均不含 RF、rd0、rb0（§1.1/§1.2 的理由）。digest 输入为
frame 全部 word 按 offset 顺序组成的 u64 序列（§3.4）。

---

## §3 结构化 guest report 契约

report 是 guest 在内存中写出的**版本化、定长上界**数据结构，host 在
guest 终止后读取。它只承担诊断与独立核对职能（§4），不代替 guest 内
fail-closed 判定。

### 3.1 传输与边界

- **endian/宽度/对齐**：全部字段 u64 big-endian；header 与每条
  checkpoint record 均 8 字节对齐；report 区起始物理地址由场景镜像
  生成器选定并告知 host runner（本契约不冻结单一地址），8 字节对齐。
- **容量上限**：`MAX_CHECKPOINTS = 64`；report 最大长度 = 72 + 64×88
  = **5704 字节**。host 读取规则：先读 72 字节 header，校验
  magic/version/capacity 后按 `checkpoint_count` 续读
  `count×88` 字节；不多读、不边跑边读（只在 guest 终止后读）。
- **越界处理**：guest 尝试发出超过容量的 checkpoint 时，丢弃多余条目、
  置 header `flags.bit0`（checkpoint_overflow），并继续完成后续判定与
  终止流程；`checkpoint_count` 始终 ≤ 64。host 端长度/容量越界一律
  HARNESS-ERROR（§3.5）。

### 3.2 header（9 word = 72 字节）

| word | 字段 | 冻结值/说明 |
|---:|---|---|
| w0 | `magic` | `0x4444414F4B325250`（ASCII "DDAOK2RP"） |
| w1 | `schema_version` | `1`；任何布局/语义变更必须 bump |
| w2 | `scenario_id` | 场景标识：任务编号**去连字符**的 6 字节 ASCII 左对齐零填充（如 KL-141a → "KL141a" → `0x4B4C313431610000`；编码 helper：`k2_report.scenario_id_for()`）；同一场景双后端一致 |
| w3 | `image_identity` | **规范化 image** 的 SHA-256 前 8 字节（big-endian u64）。规范化规则：ROM 中 8 字节 identity slot（场景声明 offset）与 RAM 中 report 区（场景声明 offset，长度 ≤ 5704）全部置零后按 ROM‖RAM 拼接。镜像生成器先对规范化 image 计算 identity，再把 identity 写入 slot 得到最终 ROM（`k2_report.embed_image_identity()`）；host 验证时对最终 image 重新规范化并重算。slot 必须位于 ROM（guest 只读）；report 区在 RAM，guest 运行时改写不影响 identity。规范化显式消除自引用：嵌入动作只改变被置零的 slot 区域 |
| w4 | `final_status` | 0=NONE（未终止）、1=PASS、2=FAIL、3=SKIP（§3.5 语义） |
| w5 | `mismatch_count` | guest 内 fail-closed 判定的失配累计（KL-139a 的 rd29 同型） |
| w6 | `checkpoint_count` | 实际记录的 checkpoint 条数，0..64 |
| w7 | `flags` | bit0=checkpoint_overflow；bits[63:1] MBZ |
| w8 | `checkpoint_capacity` | 必须等于 64（host 据此确认 guest 与本契约同版） |

### 3.3 checkpoint record（11 word = 88 字节/条）

| word | 字段 | 说明 |
|---:|---|---|
| w0 | `seq` | 单调序号：从 0 开始连续 +1；host 校验 0..count-1 无洞无重排 |
| w1 | `event_kind` | 1=INIT、2=COOP_SAVE、3=COOP_RESTORE、4=TRAP_ENTER、5=TRAP_RETURN、6=AS_SWITCH、7=TIMER、8=FINAL |
| w2 | `task_id` | 事件主体任务，按 event_kind 绑定：COOP_SAVE=outgoing（让出方）；COOP_RESTORE=incoming（恢复运行方）；trap 类=被中断/被恢复的任务；INIT/FINAL=当前任务 |
| w3 | `mode_cfx` | bits[7:0]=观测时 `inner_run_mode`，bits[15:8]=`inner_cfx_code`，bits[63:16] MBZ |
| w4 | `cause` | 该事件观测到的 cause id（one-hot；无则为 0） |
| w5 | `saved_pc` | 事件保存的 PC：COOP_SAVE=写入 outgoing frame 的 resume_pc 值；trap=硬件 frame cause_ip；INIT/FINAL/COOP_RESTORE 可为 0 |
| w6 | `resume_pc` | 事件完成后实际恢复执行的第一条指令 PC（COOP_RESTORE 必填）；无则为 0 |
| w7 | `context_digest` | §3.4 digest，输入为本事件绑定的 frame：COOP_SAVE=outgoing frame（保存完成后）；COOP_RESTORE=incoming frame（恢复前核对）；trap=本层 trap frame |
| w8 | `memory_digest` | §3.4 digest，输入为场景声明的关键内存区（逐场景固定字集合） |
| w9 | `ptbr_asid` | bits[63:48]=asid，bits[47:0]=当前 PTBR 原始存储值 |
| w10 | `tlb_gen` | 本事件观测到的 TLB protocol generation（§1.3） |

**cooperative switch 必须发 COOP_SAVE + COOP_RESTORE 两条
checkpoint**：单条记录无法同时证明 outgoing frame 已正确保存且
incoming frame 已正确恢复。SAVE 绑定 outgoing 任务及其保存后的
frame/digest 与写入的 resume_pc；RESTORE 绑定 incoming 任务及其恢复前
核对的 frame/digest 与实际恢复 PC。二者在 seq 上相邻（允许之间插入
AS_SWITCH——先切地址空间再恢复目标任务的情形），oracle 必须成对钉住。

### 3.4 digest 算法（guest/host 必须逐位一致）

word 级 FNV-1a-64：初值 `h = 0xCBF29CE484222325`；对输入 u64 序列按序
逐 word 执行 `h = (h XOR w) × 0x100000001B3 (mod 2^64)`；输出 h。
空序列输出初值。该算法只要求 xor 与 64-bit 乘常数，guest 汇编可直接
实现；host 在 `tests/scripts/k2_report.py` 中给出同一实现。

### 3.5 判定词汇（PASS/FAIL/SKIP/HARNESS-ERROR）

- **PASS**：report 结构可信（magic/version/长度/容量/image identity 全部
  通过），`final_status=PASS` 且 `mismatch_count=0`（**硬条件，oracle
  不提供任何豁免配置**），checkpoint 序列与独立 oracle 完全一致；双后端
  场景还要求两端各自对 oracle PASS 且规范化 report 互相一致（§4）。
- **FAIL**：report 结构可信但内容与期望矛盾——`final_status` 非 PASS 或
  `mismatch_count` 非 0（无豁免），scenario_id、flags 不符，seq 不连续，
  checkpoint 数目或任一受检字段不符，保留/MBZ 字段非零，未知
  event/status 枚举，非预期 overflow，双后端规范化 report 不一致。
- **SKIP**：只允许由**运行调度层**在运行之前逐后端声明；被声明 skip 的
  后端**不运行、不产生 report**（host API 中以 None 表示该端无 report）。
  任何已产生的 report 一律按上述规则完整 fail-closed 校验；事后观察到
  的失败不得重标为 SKIP，一端的 skip 也不能掩盖另一端的结果。K2 是
  双后端 gate：任一端 skip 时场景结论保持 SKIP；只有两端都运行、
  各自通过 oracle 且规范化互比一致时才可 PASS。
- **HARNESS-ERROR**：无法获得可信 report——缺 report、magic/version/
  capacity 不符、长度非法（截断、拖尾、count 与长度不一致、超容量）、
  image identity 与实跑镜像不符、后端异常退出/超时。HARNESS-ERROR 表示
  证据链本身断裂，结论无效，必须修复后才能宣称任何 PASS。

**所有非 PASS 输入均 fail-closed**：FAIL、SKIP、HARNESS-ERROR 互不升格；
正常后端退出码、双后端结果相同、日志/trace 相同，各自单独均不构成
PASS（§4）。

---

## §4 差分与 oracle 口径（K2 privileged 流程的正式口径）

1. QEMU/gem5 使用**字节完全一致**的 ROM/RAM image；host 记录**规范化
   SHA-256**（§3.2 w3 规则）并据此核对 report 的 `image_identity`。
2. guest **独立**计算 `mismatch_count` 与 `final_status`（fail-closed：
   任一内部检查失败即 FAIL，不依赖任何外部一致性）。
3. host 侧**独立场景 oracle**（不读后端日志、不复用 guest 判定）校验
   checkpoint 顺序与关键字段：event/task/mode/cfx/cause、saved/resume PC、
   ptbr/asid、tlb_gen 的逐步期望由场景定义静态给出。
4. QEMU、gem5 的 report **各自先与 oracle 比较**，再互相比较规范化
   report（§3.3 全部字段逐字段相等；当前 schema 没有合法后端差异项）。
   两端一致但不符合 oracle 时判 FAIL；oracle 通过但两端不一致同样判
   FAIL。任一端可在运行前被调度层声明 skip（该端不运行、无 report）；
   已运行端仍须完整校验，但因为缺少双后端互比，场景结论保持 SKIP，
   不得把单端 PASS 外推为 K2 PASS。
5. 每类后续场景（KL-141a～145a 各自）至少包含一个**故意破坏 guest
   状态或 oracle 期望的负向测试**，证明判定链具有敏感性（能从 PASS 变
   FAIL）。负向测试的宿主侧断言必须是 comparator 返回 FAIL 或
   HARNESS-ERROR；**不得**通过修改 oracle 期望使失败 report 返回
   PASS——`final_status=PASS` 且 `mismatch_count=0` 是 §3.5 的硬条件，
   host 模块不提供豁免配置。

**report 只增强诊断，不代替 guest 内 fail-closed 判定**：即使 report
全绿，guest `final_status` 非 PASS 时结论仍为 FAIL；反之 guest 报 PASS
而 oracle 不符时同样 FAIL。两边独立，谁也不压倒谁。

**既有三/四方差分的定位**：当前 interpreter/Sail 不建模 privileged
CFX/MMU 状态，`tools/run_differential.py` 的三/四方差分仅作为普通 ISA
**零回归门**继续存在；它不构成、也不得被表述为 K2 privileged 四方
oracle。K2 privileged 场景的双后端证据以本条口径为准。

---

## §5 host 侧复用设施（`tests/scripts/k2_report.py`）

KL-140a 交付的宿主模块，KL-141a～145a 直接复用，不得另起平行实现：

- schema 常量：magic/version/布局偏移/`MAX_CHECKPOINTS`/status/event
  枚举/flags/digest 常数，与本文件 §3 逐字对应；
- `fnv1a64(words)`：§3.4 digest；
- `image_identity(rom, ram, *, rom_identity_slot, ram_report_area)` 与
  `embed_image_identity(rom, slot_offset, identity)`：§3.2 w3 规范化
  hash 与嵌入；`scenario_id_for(tag)`：§3.2 w2 编码；
- `encode_report` / `decode_report`：编码/解码；decode 对结构问题抛
  `ReportStructureError`（映射 HARNESS-ERROR）；
- `validate_sequence` / `validate_content`：seq 连续性与内容合法性
  （映射 FAIL）；
- `compare_with_oracle`：report vs 独立 expected-checkpoint 列表
  （字段级 wildcard 支持），输出 Verdict+理由；`final_status=PASS` 且
  `mismatch_count=0` 为硬条件，无豁免配置，永不返回 SKIP；
- `compare_backend_reports` / `compare_dual_backend`：规范化双后端
  比较与"先各自对 oracle、再互相比"的完整口径；`*_bytes=None` 表示
  该端被调度层预声明 skip（未运行、无 report）；
- `Verdict`：PASS/FAIL/SKIP/HARNESS-ERROR 四值，语义同 §3.5。

模块与本文件构成单一事实源：schema 常量的权威定义在
`k2_report.py`，语义解释的权威文本在本节；二者冲突时以本文件为准并
视为缺陷处理。

---

## §6 后续任务挂钩

| 任务 | 本契约的复用点 |
|---|---|
| KL-141a cooperative switch | §1.1/§2.1 frame、COOP_SAVE/COOP_RESTORE 成对事件、INIT/FINAL、双后端口径 §4 |
| KL-142a trap dispatcher + preemptive full context | §1.2 栈窗协议/prologue、§2.2 frame、TRAP_ENTER/TRAP_RETURN 事件、嵌套 E1 恢复顺序 |
| KL-143a PTBR 切换 + 显式 TLB invalidate | §1.3 绑定/顺序/generation、AS_SWITCH 事件、ptbr_asid/tlb_gen 字段 |
| KL-144a timer 驱动综合切换 | §1 全部三类、TIMER 事件、§4.5 负向测试 |
| KL-145a 组合/收口 | 同上；汇总 pass/skip/fail/non-claim 清单 |

每个后续任务都必须：用同一 ROM/RAM image 跑双后端、给出 guest 独立
判定 + host oracle 判定 + 双后端规范化比较的三层证据、至少一个负向
mutation 场景，并显式列出 §1.4 的 non-claim 未被触碰。
