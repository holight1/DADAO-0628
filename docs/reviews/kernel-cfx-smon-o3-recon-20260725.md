# KL-115a：O3（真实 `trap cfx_smon`→guest handler→`escape` 往返）最小切片调研

**日期**：2026-07-25
**范围**：本地只读调研；未修改 QEMU、gem5、LLVM、kernel、contracts 或 wiki，未运行测试、未编译。
**证据标签**：`[正式契约]`=wiki SEE/HEE/HBI 原文；`[已有实现]`=当前
`.work/source/qemu`/`components/gem5/patches` 源码事实；`[推断]`=据此
给出的设计判断或尚待架构确认的结论。

## 结论先行

O3（"移交后真实受控操作"）**不是"guest handler 例子"这个描述能覆盖的
规模**。核对 wiki 原文后确认：`CFXTRAP` 对 `cfx_smon` 是不可屏蔽异常
`[正式契约]`，这意味着步骤2-5（`excp_cause_nonmaskable`/
`inner_cfx_mask`/`global_cfx_mask`/`excp_cause_mask` 四项判断）对本场景
可以合法整体跳过——不是"简化掉"，是 wiki 步骤2 本身规定不可屏蔽异常直接
跳到步骤6。步骤6（陷入计数）不影响验收，可排除。**但步骤7-10（保存现场→
模式切换→保存异常信息→跳异常向量）在 QEMU/gem5 双后端目前是 100% 空白**
——不只是"cfx_smon 专属部分缺失"，是**整个 `trap` 指令的异常进入流程从未
被实现过，对任何 cfxcode 都没有**（现有的 `cfx_power` prev/cause 三字段
只是 O1 的 HBI §3 stub 用 `cfx2rc` **软件写入**模拟出来的，从未被一次
真正的硬件 trap 进入路径写过）。

更关键的是一个 O1/O2 都没遇到过的新问题：**`trap` 指令的 `cfxcode==2`
（`cfx_smon`）这个具体分支，当前在 QEMU/gem5 里被现有 host/SE syscall
捷径**无条件占用****（`.work/source/qemu/target/dadao/cpu.c:157`
`if (cfxcode == 2)`；gem5 `components/gem5/patches/0010:24`
`if (cfxcode == 2)`）。O1/O2 新增的 `cfx2rc`/`escape` 是全新 opcode，
和捷径没有交集；O3 要做的"真实 `trap cfx_smon` 进入流程"和现有捷径**争夺
同一个 `cfxcode==2` 分支**，这是本次调研发现的、任务背景未曾预判的额外
复杂度来源，必须先有一个明确的区分机制（架构师决策点，见 §4.4）才能
开始实现。

**范围估计**：O3 需要新增的状态容器（`cfx_smon` 专属异常现场帧，含
`cause_id`/`cause_info`——这两个字段连 `cfx_power` 都没有过）、新的
`cfx2rc` 可写寄存器（`cfx_smon_supv_excp_vector` 必须新支持）、新的
trap 进入状态机、以及"真实入口 vs 现有捷径"的区分机制，体量上**不小于
O1+O2 两个任务的合计**（不是"guest handler 示例"量级）。建议拆成
**QEMU 一个任务 + gem5 一个任务**，且在下发实现任务前，"区分机制"这个
设计分叉点建议由架构师先拍板（详见 §4.4 三个选项），不适合让实现 DS/
subagent 自行现场决定。

---

## §1 目标1：wiki 10步伪代码逐步核对

### 1.1 步骤2（不可屏蔽判断）：`CFXTRAP` 对 `cfx_smon` 是否不可屏蔽

`[正式契约]` `cfx_smon` 的异常原因表原文是"异常原因编码与 `cfx_umon`
一致"（`DADAO-12-SEE-主管系统运行环境.md:417-419`）。`cfx_umon` 的异常
原因表（`:396-411`）里 `CFXTRAP` 行原文：

```
| `1 << 0`   | CFXTRAP | 功能调用      | 否 | 指令编码 |
```

"是否可屏蔽"列 = **否**（`:402`）。同一张表里 `CFXMEM`（`:403`）、
`CFXREG`（`:404`）、`ILLI`/`UNDI`/`RASOF`/`RASUF`/`MALIGN`/`IALIGN`
（`:405-410`）全部为"否"，只有 `FPEXCP`（`:411`）是"可"。

`cg5` 的 `excp_cause_nonmaskable` 寄存器原文（`:362`）："硬件根据异常
原因表**静态设置**"——即这个寄存器不是软件配置项，是硬件按上面这张表
固化的只读值。entry-flow 步骤2 原文（`:693`）："检查
`cfx_⟨cfxname⟩_excp_cause_nonmaskable` 对应位，若置1则该异常不可屏蔽，
**跳过步骤3-5直接进入步骤6**"；伪代码（`:763-765`）：

```
check_nonmaskable:
if (cfx_⟨cfxname⟩_excp_cause_nonmaskable & cause) == 0:
    [步骤3-5]
// cause 的 nonmaskable 位为1时，直接落到步骤6（if 条件为假，不进入分支体）
```

**结论**：`trap cfx_smon,func` 触发的 `cause=CFXTRAP` 对 `cfx_smon`
硬件固化为不可屏蔽。任务背景问的"`CFXTRAP` 是不是包含在'其余同步异常
均为不可屏蔽'里"——原文（`:697`）这句话本身就是对 `cfx_umon`/`cfx_smon`
共用异常表的准确复述（表里 6 个同步异常只有 `FPEXCP` 可屏蔽，`FPEXCP`
在 `cfx_umon`/`cfx_smon` 表里并不存在——这张表压根没有 `FPEXCP` 行，
`FPEXCP` 只在其他有浮点单元语义的 cfx 才会出现），读法成立。

**对 O3 的直接影响**：步骤2-5 对本场景可以合法整体跳过——**不需要**
实现 `inner_cfx_mask`/`global_cfx_mask`/`excp_cause_mask` 的判断逻辑，
硬编码"CFXTRAP 直达步骤6"即可，这不是简化，是 wiki 步骤2 本身要求的
分支结果。

### 1.2 步骤3/4（inner_cfx_mask/global_cfx_mask）：任务背景关于 O1 遗留
mask 值的担忧是否成立

任务背景问："O1 的 `inner_cfx_mask` 复位是全1……这会不会导致从 hypv
发起的、以及 supv 侧任何目标 cfx 的异常在到达 `cfx_smon` 之前就先被
`inner_cfx_mask`/`global_cfx_mask` 挡住？"

`[已有实现]` 核实 `.work/source/qemu/target/dadao/cpu.c:66`：
`env->inner_cfx_mask = DADAO_CFX_MASK_ALL`（reset 值，全1，O1 保持不动，
`escape` 的 O1 唯一用例把它设回全1，见 `helper.c` 的
`cfx_power_frame.prev_cfx_mask` 复位同为全1）。这个值在 O1 handoff 完成
后确实是全1（"屏蔽一切跨 cfx"的语义，`0=可触发，1=屏蔽`，见
`DADAO-12-SEE §3` cg0-2 表说明）。

但 §1.1 已确认：**这个担忧对 `trap cfx_smon` 场景不成立**——因为
`CFXTRAP` 不可屏蔽，步骤2 的检查在到达步骤3（`inner_cfx_mask`）之前就
已经短路跳过。`inner_cfx_mask` 全1 只会影响**可屏蔽**的异常原因（本
cfx_smon/cfx_umon 表里没有任何一个可屏蔽的同步异常，只有异步中断——
本场景不涉及）。**结论：不需要在 O3 探针里清除 `inner_cfx_mask`/
`global_cfx_mask`，它们的值对 `trap cfx_smon` 是否可达无影响**。

### 1.3 步骤5（`excp_cause_mask`）

同 §1.2，被步骤2 短路，且 `cfx_smon` 异常表里没有可屏蔽项，`excp_cause_
mask` 的值同样不影响本场景。**不需要实现存储或检查**。

### 1.4 步骤6（陷入计数）

`[正式契约]` `cfx_⟨cfxname⟩_trap_num`（cg4/rc2，`:345`）"HW"写，
"trap指令陷入该核芯功能扩展的次数"。`[已有实现]` 当前 QEMU/gem5 对
**任何** cfx 的 cg4 计数寄存器组（`trap_num`/`excp_sync_num`/
`excp_async_num`/`escape_num`，`:345-348`）都没有分配存储——O1/O2 的
`escape_num` 同样未实现（`helper_escape` 函数级注释明确："Step 3
(escape_num++...) is not modeled: no cg4 counter infrastructure exists
yet for any cfx"）。O3 验收目标是"确认走了真实路径，不是走了 host
捷径"，判定依据是 mode/`inner_cfx_code`/PC/marker/`rd31` 这些可观测
架构状态，`trap_num` 是否递增不参与这个判定。**结论：明确排除在 O3
范围外，类比 `escape_num` 在 O1/O2 里的处理**。

### 1.5 步骤7-10（核心）：`cfx_power` 的现有实现能否直接复用

`[已有实现]` 逐项核对 `cfx_power` 当前拥有什么：

| 字段 | wiki 定义（cg/rc） | `cfx_power` 现状 | `cfx_smon` 现状 |
|---|---|---|---|
| `excp_prev_run_mode`（步骤7） | cg5/rc0，`:357` | `DADAOCfxPowerFrame.prev_run_mode`，**软件写**（`helper_cfx2rc` `cpu.c` L155-165），从未被真实硬件入口写过 | **完全没有存储** |
| `excp_prev_cfx_mask`（步骤7） | cg5/rc1，`:358` | 同上，`.prev_cfx_mask` | **完全没有存储** |
| `switch_run_mode`（步骤8） | cg2/rc8，`:326`，默认 `2(supv)` | **没有存储**（`helper_cfx2rc` 对 `cfx_power` 只识别 cg5，见 `helper.c:155`） | **没有存储** |
| `switch_cfx_mask`（步骤8） | cg2/rc9，`:327`，默认全1 | **没有存储** | **没有存储** |
| `inner_cfx_code<=temp_cfx_code`（步骤8） | 硬件内部 | O1/O2 从未写过（`inner_cfx_code` 恒为 `power`，reset 后再未变化——见 §2） | 同左 |
| `excp_cause_ip`（步骤9） | cg5/rc3，`:360` | `.cause_ip`，**软件写**（`helper.c:169-170`） | **完全没有存储** |
| `excp_cause_id`（步骤9） | cg5/rc2，`:359`，HW写 | **完全没有存储**（`helper_cfx2rc` 的 cg5 switch 只有 case 0/1/3，`default: return;`，`helper.c:172-173`） | **完全没有存储** |
| `excp_cause_info`（步骤9） | cg5/rc4，`:361`，HW写 | **完全没有存储** | **完全没有存储** |
| `excp_vector`（步骤10） | cg2/rc10，`:328`，默认0 | **没有存储** | **没有存储** |
| 真正的"进入"状态机（步骤6-10 的执行体） | `helper_trap`/`TrapInst::execute()` | **不存在**——`helper_trap`（`helper.c:100-110`）只把 `cfxcode`/`func` 放进 scratch 变量、设 `EXCP_CFXTRAP`、`cpu_loop_exit`；真正的分派在 `dadao_cpu_do_interrupt` 的 `EXCP_CFXTRAP` 分支（`cpu.c:151-336`），那里只有 `cfxcode==2` 的 host syscall responder 和"其它 cfxcode→0x82 panic"两条路径，**没有第三条"真实 SEE 进入流程"路径** | 同左 |

`helper_escape` 的退出侧只对 `cfxcode==DADAO_CFX_CODE_POWER` 从
`cfx_power_frame` 恢复（`helper.c:261-264`）；其它 cfxcode（含 `smon`）
落入 `else` 分支得到**全零伪造帧**（`prev_run_mode=USER,
prev_cfx_mask=0, cause_ip=0`，`helper.c:265-269`，代码注释自己说明
"has no frame to restore from and falls back to a zeroed frame instead
of fabricating per-cfx state that was never written"）。

**结论**：任务背景把现有实现描述为"步骤7-10 里 `cfx_power` 专属的
`escape` 退出侧镜像"——这个描述准确，但需要补充两点独立核实到的细节：
(a) 这个"镜像"只覆盖 `prev_run_mode`/`prev_cfx_mask`/`cause_ip` 三个
字段，**`cause_id`/`cause_info` 连 `cfx_power` 都从未有过存储**；
(b) 这三个字段是 O1 的 HBI §3 stub 用**软件 `cfx2rc` 写入**模拟出来的
"伪造现场"，**从来没有一次真正的硬件 trap 进入执行过步骤7/9**——O1 的
`escape cfx_power,0` 严格说是"回放一段手工准备好的假现场"，不是"进入
过再退出"。`cfx_smon` 要做 O3，**这两点都要从零实现**，不是"仿照
`cfx_power` 抄一份存储"这么简单——`cfx_smon` 还需要一次**真正**由
硬件（trap 指令执行路径）写入 `prev_*`/`cause_*` 的入口，`cfx_power`
至今没有这样的入口可供参照复制粘贴（只有软件写入的先例）。

---

## §2 目标2：`cfx_smon` 从 supv 可达的前置条件

`[已有实现]` 核对 `inner_cfx_code` 的生命周期：reset 时设为
`DADAO_CFX_CODE_POWER`（`cpu.c:65`），此后**唯一**可能改变它的地方是
entry-flow 步骤8（`inner_cfx_code<=temp_cfx_code`）——但如 §1.5 所述，
这一步骤在当前实现里根本不存在。`escape` 的 wiki-deviations #9（已有
决定）明确 `escape` 不恢复/不修改 `inner_cfx_code`。**结论：O1 handoff
完成后，`inner_cfx_code` 仍然是 `power`(63)，不是 `smon`——这本身就是
"`cfx_smon` 尚未被真正进入过"的直接证据，与 O3 要证明的目标一致（O3
就是要第一次让 `inner_cfx_code` 变成 `smon`）**。

任务背景问的"是否需要额外的 `cfx2rc` 写入才能让这条路径不被 O2 已实现
的检查挡住"：

- **`trap_cfx_mask`（cg2/rc6，`DADAO-12-SEE §3 :324`）**：wiki entry-flow
  步骤1 的通用 `<instr>_cfx_mask` 检查（`:721`）字面上适用于 `TRAP`
  这一类指令，语义是"`cfx_⟨inner_cfx_code⟩_⟨inner_run_mode⟩_trap_cfx_mask`
  第 `cfxcode`（目标）位"——即检查的是**当前正在执行 trap 的 cfx**
  （O1 之后是 `power`）的 `trap_cfx_mask`，不是 `cfx_smon` 自己的。
  `[已有实现]` 核实 `helper_cfx2rc` 完全不识别 `cg<=2 && rc==6` 这个
  组合（`helper.c:143-219` 逐条 if 链没有这一支，落入默认静默 no-op），
  QEMU/gem5 两端都**没有为这个检查分配任何存储或判断代码**——不是"默认
  全1挡住"，是"这个检查机制本身尚不存在，永远不会被触发"。**结论：不
  需要任何额外 `cfx2rc` 写入，因为当前实现根本不会执行这项检查**（这
  和 O2 设计2的 `cfx2rc_cfx_mask` 是两个不同的寄存器，`trap_cfx_mask`
  从未被 KL-111a/KL-112a 评估或实现过，既不在"已挡住"名单里，也不在
  "已放行"名单里——是完全未触及的第三态）。
- **reserved cfxcode 检查（步骤1第一支）**：`cfx_smon`=2，不在
  `{7-14,19-61}` 保留区间内，即使这项检查真的实现了也不会拦截它，
  与 O3 无关。
- **`escape_cfx_mask`（KL-112a 设计1，已实现）**：只在 `escape` 目标
  `cfxcode != inner_cfx_code` 时检查（`helper.c:249-255`）。如 §1.5
  末尾所述，只要 O3 正确实现步骤8 令 `inner_cfx_code` 在进入 `cfx_smon`
  处理程序期间确实等于 `smon`，那么 `escape cfx_smon,N`（自我 escape）
  时 `cfxcode==inner_cfx_code`，设计1检查天然不生效（与 O1 的
  `escape cfx_power,0` 同构，是 self-escape，不是跨 cfx escape）。
  **不需要额外 `cfx2rc` 写入去关闭这项检查**。
- **CFXREG 设计3（已实现）**：只窄范围命中 `cfxcode==power && cg==8
  && rc>1`（`helper.c:189-210`），与 `cfx_smon` 无关，不会拦截。

**结论**：O2 已实现的两项检查（设计1/设计3）**都不会拦截 O3 探针**，
原因不是"O3 需要额外写入去满足它们"，而是它们的触发条件本身与 O3 场景
不相交。真正的可达性问题不是"被某个已实现的权限检查挡住"，而是
§1.5/§4.4 描述的"entry-flow 步骤7-10 这条路径本身不存在，`trap
cfx_smon` 目前 100% 落进 host syscall 捷径，不会以任何方式抵达一个
'guest-side smon handler'"。

---

## §3 目标3：guest handler 的 ABI 约定

`[已有实现]` 现有 host/SE 捷径的寄存器约定：`rd16`=sysno、
`rd17-19`=arg0-2（`cpu.c:159-162`）、返回值写 `rd31`（`cpu.c:328`）。
这组寄存器是**普通整数寄存器**（`rd` bank），读写不经过任何 cfx 状态
机检查——`cfx2rd`/`cfx2rc`/`cfxld`/`cfxst` 才是访问 cfx 专有/暂存寄存器
的指令，`rd16-19`/`rd31` 从来不属于这个范畴。

**结论**：O3 的 guest handler 直接复用这组寄存器约定（读 `rd16`/
`rd17-19`，写 `rd31=0`）没有任何冲突——这只是"程序员之间约定好用哪几个
通用寄存器传参"，和是否走真实 trap 路径无关，也不需要独立约定。**唯一
需要注意的是**：guest handler 代码本身运行在真实 `cfx_smon` 异常向量
处（`excp_vector`），是**普通指令流**（`setrd`/`cfx2rc` 写 `rd31`/
`escape`），不调用任何 host API——这与"复用寄存器约定"是两件独立的事，
不冲突。

---

## §4 目标4：O3 探针设计

### 4.1 探针指令序列（供 KL-116a 直接使用）

```
; ==== 阶段0：HBI §3 stub（复用 KL-110a 已验证的 gen_kl110a_o1_probe.py 逻辑，不变）====
; 12× cfx2rc cfx_<name>_hypv_cg_reg_deleg, rd2   ; 已实现（cg3/rc12）
; cfx2rc cfx_power, 5, 0, rd_prev_mode(=2 supv)   ; 已实现
; cfx2rc cfx_power, 5, 1, rd_prev_mask(=-1)       ; 已实现
; cfx2rc cfx_power, 5, 3, rd_cause_ip(=supv_entry); 已实现
; escape cfx_power, 0                             ; 已实现，落地 supv_entry，mode=supv

; ==== supv_entry：阶段1：O3 新增的 supv 侧准备 ====
; cfx2rc cfx_smon, 2, 10, rd_excp_vector(=smon_handler)  ; ★需新实现（cg2/rc10 存储）
; （switch_run_mode/switch_cfx_mask 使用 wiki 默认值 2(supv)/全1，
;   §1.5 已确认默认值即可满足 O3 最小场景，不需要额外写入）
; setrd rd16, <sysno 常量>       ; 复用现捷径 ABI，仅作可观测参数
; setrd rd17, <arg0 常量>
; trap cfx_smon, 0               ; ★需新实现的真实进入流程（步骤6-10 子集）

; ==== smon_handler（excp_vector 落地处）：阶段2：guest-side handler ====
; ; 读 rd16 确认参数被真实传递（可选：写回某内存位置做可观测校验）
; setrd rd31, 0                  ; 普通整数寄存器写，无冲突（§3）
; escape cfx_smon, 1             ; ★需新实现（self-escape，恢复 cfx_smon 专属现场）
;   → 返回 cause_ip+4，即 trap 指令的下一条

; ==== 阶段3：marker（复用 KL-110a 惯例）====
; 写 marker 到 RAM，读回比对，编码进退出码
```

### 4.2 已实现可直接复用的部分

- HBI §3 stub 全部12条 delegation + `cfx_power` 三字段 + `escape
  cfx_power,0`（KL-110a，QEMU commit `72cba5f`/`6eb9d01`；gem5 commit
  `635a70bd9d`）。
- `escape` 指令译码/riii 操作数提取、`cfx2rc` 指令译码/crrr 操作数提取
  （两端都已有，`insn.decode:172-175`；gem5 `decoder.cc` `case 0x73`/
  `0x77`）——**指令编码本身不用重新做**，缺的是 `helper_cfx2rc`/
  `TrapInst`/`EscapeInst` 内部对新 `(cg,rc)` 组合和新 cfxcode 分支的
  处理逻辑。
- marker 读回比对惯例（`gen_kl110a_o1_probe.py`）、trace 观测惯例
  （`CPU_LOG_INT`/gem5 `stderr` 行）。
- guest handler 的寄存器 ABI 约定（`rd16-19`/`rd31`，§3）。

### 4.3 本任务发现必须新实现的部分（QEMU + gem5 对称）

1. **新的 `cfx_smon` 异常现场帧**（结构体扩展或新增，含
   `prev_run_mode`/`prev_cfx_mask`/`cause_ip`/`cause_id`/`cause_info`
   五字段——比 `cfx_power` 现有的三字段多两个，因为 `cfx_power` 从未
   补过 HW-only 字段）。
2. **`cfx_smon_supv_excp_vector`（cg2/rc10）的 `cfx2rc` 写入支持**——
   `helper_cfx2rc` 当前对这个 `(cg,rc)` 组合是静默 no-op，必须新增分支
   （不需要 `switch_run_mode`/`switch_cfx_mask`，§1.5/§4.1 已确认默认值
   够用）。
3. **`trap` 指令真实进入流程的状态机**（步骤6跳过、步骤7保存现场、
   步骤8切换 mode/mask/`inner_cfx_code`、步骤9保存 `cause_*`、步骤10
   跳 `excp_vector`）——`helper_trap`/`TrapInst::execute()` 当前完全
   没有这条路径。
4. **`helper_escape`/`EscapeInst` 的恢复分支扩展**：新增
   `else if (cfxcode == DADAO_CFX_CODE_SMON)` 从新 `cfx_smon` 帧恢复，
   否则会像现在这样落入"全零伪造帧"（`helper.c:265-269`）。
5. **区分"真实进入"与现有 host/SE 捷径的机制**——见 §4.4，这是本次
   调研发现的、任务背景未预判的额外设计问题，**建议先由架构师拍板**再
   下发实现任务。
6. `contracts/isa/spec.md` §8 需要新增 §8.x 覆盖 `trap` 的 O3 子集
   语义（目前 `trap` 仍整体列在 §7 M1 Excluded，`:992`）。

### 4.4 核心设计分叉：`cfxcode==2` 的捷径与真实入口冲突（需要架构师决策）

`[已有实现]` 无论 QEMU（`cpu.c:151-336`）还是 gem5
（`0010-dadao-trap-syscall.patch:24`），`trap` 指令对 `cfxcode==2` 这
一个具体值的处理**完全被 host/SE syscall 捷径占用**——这不是"捷径和
真实路径在不同触发条件下并存"，是"当前只要 `cfxcode==2` 就唯一走捷径"。
O1/O2 新增的 `cfx2rc`/`escape` 是全新 opcode，天然不与捷径冲突；O3
第一次要求"真实进入流程"和"现有捷径"共享同一个 `(opcode=trap,
cfxcode=2)` 组合，两者语义互斥（真实进入流程要跳 `excp_vector` 并切换
mode，捷径要留在当前 mode 直接返回 syscall 结果）。三个可选方向，均未
在本次调研中实现或验证，供架构师选择：

- **选项A（推荐）**：新增一个可开关的 CPU/machine 属性（如 QEMU
  `-cpu dadao,cfx-smon-real=on` 或等价机制；gem5 对应 SimObject
  param），默认关闭（保持现有 E2E/lit 全部继续走捷径，零回归风险），
  O3 探针显式打开后 `helper_trap`/`TrapInst::execute()` 对 `cfxcode==2`
  改走真实入口流程。这与 `KL-102a` 报告 §5.2 当初设想但从未实现的
  "profile 互斥"设计一致（`docs/reviews/
  kernel-cfx-state-patch-surface-20260721.md:96-118`）。代价：需要新增
  一层配置/属性基础设施，QEMU/gem5 各自实现方式不同，是本次范围估计
  偏大的主要原因之一。
- **选项B**：把 O3 的目标 cfxcode 从 `cfx_smon`（2）改成一个当前未被
  捷径占用的 cfxcode（如 `cfx_umon`=0、`cfx_jmon`=1、`cfx_hmon`=3、
  `cfx_ptw`=4 等——这些在 QEMU 侧当前统一落入"unknown cfxcode→0x82
  panic"分支，`cpu.c:329-332`；gem5 侧当前是静默 no-op），可以不新增
  任何开关，直接把"真实进入流程"接到这个未占用分支上。代价：偏离
  `KL-101a` 当初对 O3 的字面定义（"`cfx_smon` 可达"），需要架构师明确
  同意重新定义 Oracle O3 的目标 cfx。
- **选项C**：保持 `trap` 指令语义不变，但在**探针内部**用一个 sysno
  之外的判定信号（比如约定 `func`/`imm18` 的某个取值范围表示"这是 O3
  探针，不是真实 syscall"）让 `helper_trap`/`TrapInst` 内部分岔。这个
  选项**语义上不诚实**——真实硬件的 trap 进入流程不会检查 `func` 的
  取值来决定是否"进入"，这样实现出来的东西证明的是"软件路由技巧"而不是
  "SEE §5 真实进入流程"，与 O3 的验收目的（KL-101a §3.4"不是走了 host
  捷径"）直接矛盾，**不建议采用**，本报告只是为了完整列出选项而记录。

**本报告不替架构师做这个决定**——它决定了 O3 实现任务的具体形状（选项A
需要新的配置基础设施；选项B 只需要选一个未占用的 cfxcode 接线，实现
成本明显更低但改变了 Oracle O3 的字面定义）。

### 4.5 工作量估计与任务拆分建议

`[推断]` 参照量级对比：O1（KL-110a）新增了 1 个状态容器
（`cfx_power_frame`+delegation数组）+ 2 条新 opcode 的最小语义；O2
（KL-112a）新增了 2 个检查分支（escape mask + CFXREG）；gem5
（KL-113a）把 O1+O2 合并成一个任务完成。O3 需要：1 个新状态容器（比
`cfx_power_frame` 多2字段）+ 1 个新可写 `cfx2rc` 寄存器 + **一整条此前
从未实现过的 trap 进入状态机**（步骤6-10）+ **一个此前不存在的
"真实/捷径"区分机制**（§4.4，量级不确定，取决于选项A/B/C）——**保守
估计不小于 O1+O2 的合计工作量**，"区分机制"这一项如果选选项A，可能
单独就接近一个 O1 量级的任务。

**建议**：
1. **不要**把 O3 当作"KL-116a 一个任务，QEMU/gem5 各自在其中顺带做"来
   下发——按 O1/O2 的先例拆成独立的 **QEMU 实现任务 + gem5 实现任务**
   两个任务（gem5 可以像 KL-113a 一样一次性对齐两条 Oracle，但 O3
   目前只有一条 Oracle，不需要拆负例/正例两个任务）。
2. **§4.4 的选项A/B/C 建议架构师先决定**，再把决定写进任务文件的
   "约束"区（而不是留给实现 DS/subagent 现场判断）——这是一个会
   影响任务范围和验收标准形状的架构决策，不是实现细节。
3. 如果架构师倾向"先把范围压到最小、优先验证 SEE 进入流程本身是否可行"，
   选项B（换一个未占用的 cfxcode）是成本明显更低的起点，可以先用非
   `cfx_smon` 的 cfx 验证一遍步骤6-10 状态机本身的正确性，再单独讨论
   是否/如何把 `cfx_smon` 的捷径共存问题（选项A）作为后续任务补上。这
   个先后顺序建议供参考，不是本报告的结论。

---

## §5 wiki-deviations 候选：无新增条目

本次调研没有发现新的 wiki"沉默"（未定义）或"矛盾"（两处正式文本字面
互斥）需要登记。逐项确认排除的理由：

- `excp_vector`（cg2/rc10）的地址解释规则本身是清楚的（"若对应 PTBR
  未开启则为核内地址"，`:706`）；`cfx_smon` 的核内地址区间（cfxcode=2
  对应 `addr[47:42]=2`）没有被 `DADAO-12-SEE §2.1` 分配实际映射
  （该表只列了 `cfx_power` 一项，`:64-73`），但这不是矛盾或沉默——
  `ADR-0004` 已经明确测试机整体偏离 SEE 的核内地址空间语义、改用扁平
  物理地址（O1 的 `cause_ip`/`supv_entry` 就是这么处理的），O3 的
  `excp_vector` 延续同一个已有先例即可，是复用既有设计决策，不是新
  wiki gap。
- `excp_cause_info` 对 `CFXTRAP` 的取值（"指令编码"，`:402`）文字上没有
  歧义（触发 trap 的那条指令的完整编码），只是"具体存哪个粒度（func
  字段还是完整32位指令字）"是实现细节，不影响 O3 验收（§1.4/§1.5 已
  确认 `cause_info` 本身不参与 O3 的判定路径），不构成需要登记的沉默。
- §4.4 的"真实入口 vs host 捷径如何共存"完全是 QEMU/gem5 模拟器实现
  层面的问题，wiki 描述的是真实硬件语义，从未也不需要对"模拟器如何
  保留一个非 ISA 定义的兼容捷径"表态——这不是 wiki 该回答的问题，不
  登记。

---

## 完成区（2026-07-25）

**状态**：调研完成，未修改任何文件（QEMU/gem5/LLVM/kernel/contracts/
wiki 均未触碰）。

**核心结论**：
1. Wiki 步骤2-5 对 `trap cfx_smon` 场景可合法整体跳过——`CFXTRAP` 对
   `cfx_smon`/`cfx_umon` 共用异常表硬件固化为不可屏蔽
   （`DADAO-12-SEE-主管系统运行环境.md:402/419/693/763-765`），任务
   背景关于 O1 遗留 `inner_cfx_mask`=全1 的担忧经核实**不成立**（这个
   值只影响可屏蔽异常，`CFXTRAP` 不是）。步骤6（陷入计数）可排除，
   类比 `escape_num` 处理先例。
2. 步骤7-10 是真正的核心缺口——**不是"`cfx_smon` 部分缺失"，是整个
   `trap` 指令的异常进入流程从未被实现过**（`cfx_power` 现有的
   prev/cause 三字段是 O1 用软件 `cfx2rc` 写入模拟出来的假现场，从未
   经历过一次真正的硬件 trap 进入；`cause_id`/`cause_info` 连
   `cfx_power` 都没有存储）。
3. O2 已实现的两项检查（escape mask 设计1、CFXREG 设计3）**都不会
   拦截 O3 探针**，`trap_cfx_mask` 这项 wiki 提到但从未被任何任务
   实现/评估过的检查同样不会拦截（机制本身不存在）——真正的可达性
   障碍不是权限检查，是 §4.4 的架构冲突。
4. **新发现（任务背景未预判）**：`trap` 指令的 `cfxcode==2` 分支当前
   被 host/SE syscall 捷径无条件独占（QEMU `cpu.c:157`；gem5
   `0010-dadao-trap-syscall.patch:24`），O3 要做"真实进入流程"必须先
   解决这个共存问题，三个选项（新增开关/换未占用 cfxcode/func 取值
   分岔）已在 §4.4 列出，**建议架构师先拍板再下发实现任务**。
5. guest handler ABI 约定（`rd16-19`/`rd31`）可直接复用，无冲突。
6. 本次调研未发现需要登记 `docs/wiki-deviations.md` 的新沉默/矛盾。
7. 工作量估计：不小于 O1+O2 合计，建议拆 QEMU/gem5 两个独立实现任务，
   §4.4 的设计分叉点需要架构师决策后才适合下发。

**产出文件**：本报告（`docs/reviews/kernel-cfx-smon-o3-recon-20260725.md`）。
未修改：`contracts/isa/spec.md`、`docs/wiki-deviations.md`、任何
QEMU/gem5 源码或 wiki 文件。

---

## 自审：审阅记录（subagent 自审）

**判决**：自审通过，无阻断 finding。

- **wiki 引用逐项复核**：本报告引用的每一处 wiki 行号（`DADAO-12-SEE
  §5` 第678-811/813-845行、cg0-2表第273-331行、cg4表第337-349行、
  cg5表第351-364行、cfx_umon/cfx_smon异常原因表第396-419行、
  cfxcode表第20-36行）均用 Read 工具亲自打开原文核对，不是转述任务
  文件或历史 review 报告的转述——任务文件给出的 678-811 行范围与独立
  读取结果一致；cg0-2/cg4/cg5 的具体行号（317-329/339-349/351-364）
  是本次调研为了精确定位 `switch_run_mode`/`excp_vector`/`cause_id`/
  `cause_info` 的 `(cg,rc)` 编号而补充读取的，任务文件本身没有展开到
  这个精度。
- **源码引用逐项复核**：`helper.c`/`cpu.c`/`cpu.h` 的每一行号引用
  （如 `helper.c:100-110`/`136-219`/`228-269`，`cpu.c:64-81`/
  `151-336`）均用 Read/grep 工具直接核对当前 `.work/source/qemu` 源码
  取得，不是照抄 KL-110a/112a 完成区报告里的行号（这两份报告成文于
  改动完成时，行号可能随后续 commit 漂移；本次独立重新核对过一遍，
  确认与当前 `.work/source/qemu` 状态一致）。
- **gem5 侧核实方式说明**：`.work/source/gem5` 当前 checkout 不含
  `src/arch/dadao`（与 KL-102a 报告 §2.2 描述的情况一致），本报告
  gem5 相关引用最初计划只依据 `components/gem5/patches/0010-dadao-
  trap-syscall.patch` 的 patch 文本；自审阶段发现本机实际存在
  `~/DADAO-gem5`（KL-113a 的开发仓库，非 DADAO-0628 内部路径，但同样
  只读可访问，不违反"不修改 QEMU/gem5/LLVM/kernel/contracts/wiki"的
  约束），补充直接读取了当前 checkout 独立核实：
  `~/DADAO-gem5/src/arch/dadao/decoder.cc:708` 确认
  `TrapInst::execute()` 的 `if (cfxcode == 2)` 与 patch 文本逐字一致
  （无 else 分支，其它 cfxcode 直接 `return NoFault`，即静默 no-op）；
  `decoder.cc:904/922/955/964-967` 与 `isa.hh:36/83/85` 确认
  `CFX2RCInst`/`EscapeInst` 的 `cfxcode_ == CfxCodePower` 专属分支、
  `innerCfxCode` 复位为 `CfxCodePower`、`escape` 对非 `power` cfxcode
  同样落入零帧恢复的结构，与 QEMU 侧逐条对应。**结论：gem5 侧的关键
  论断（"`cfxcode==2` 捷径独占""无 trap 进入流程""`escape` 只对
  `cfx_power` 有真实帧"）现已由当前 `~/DADAO-gem5` source tree 一手
  核实，证据强度与 QEMU 侧一致**，不再是仅依赖 patch 文本/KL-113a
  转述的二手证据。
- **"未发现新 wiki-deviations 候选"的自查**：逐条检查了 §1-§4 涉及的
  每一个可能的沉默点（`excp_vector` 核内地址映射缺口、`cause_info`
  粒度、真实/捷径共存问题），确认它们要么有明确先例（ADR-0004 扁平
  地址）、要么不影响 O3 验收（`cause_info` 粒度）、要么根本不是 wiki
  该回答的问题（模拟器实现层面），没有为了"凑一个看起来完整的方案"
  而回避应该登记的沉默——如果后续 KL-116a 实现时发现 §4.4 之外还有
  真正的 wiki 沉默/矛盾，应该在那个任务里补登记，不是本报告遗漏。
- **未过度简化的自查**：本报告没有把"guest handler 最小往返"简化成
  "只要能让 PC 跳到某处再跳回来就算过"——§1.5 明确列出了 `cause_id`/
  `cause_info` 这两个连 `cfx_power` 都没有的字段缺口，§4.4 明确指出
  了任务背景完全没有预判的"捷径独占 `cfxcode==2`"这个架构冲突，并且
  没有替架构师做选项A/B/C 的决定——如实反映了范围比"guest handler
  例子"这个描述大得多，符合任务目标4"如实说明，不要为了凑一个'看起来
  可行'的方案而简化掉必要步骤"的要求。
