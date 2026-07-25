# KL-116a：实现 O3（`trap cfx_smon` 真实进入流程）in QEMU

**执行环境**：本地 subagent，QEMU 源码改动（`.work/source/qemu`），产出
patch 落 `components/qemu/patches/`

## 背景

`KL-115a`（纯调研，已 commit，`docs/reviews/
kernel-cfx-smon-o3-recon-20260725.md`）把 O3（移交后真实受控操作：
`trap cfx_smon`→guest handler→`escape` 往返）的精确范围钉死了。**关键
结论**（架构师已独立核对全部 wiki 引用和源码引用属实）：

1. wiki 异常进入流程步骤2-5（不可屏蔽判断/`inner_cfx_mask`/
   `global_cfx_mask`/`excp_cause_mask`）对 `trap cfx_smon` 场景可以
   合法整体跳过——`CFXTRAP` 对 `cfx_smon` 硬件固化为不可屏蔽（wiki
   `DADAO-12-SEE-主管系统运行环境.md:402/419`，`cfx_smon` 复用
   `cfx_umon` 的异常原因表），步骤2的 `check_nonmaskable` 直接跳到
   步骤6（`:763-765`）。步骤6（陷入计数）本任务同样不实现，类比
   `escape_num` 在 O1/O2 里的处理先例（无存储基础设施，不影响验收）。
2. **真正的核心是步骤7-10**：保存现场（`excp_prev_run_mode`/
   `excp_prev_cfx_mask`）→模式切换（`switch_run_mode`/
   `switch_cfx_mask`/`inner_cfx_code<=temp_cfx_code`）→保存异常信息
   （`excp_cause_ip`/`excp_cause_id`/`excp_cause_info`）→跳转异常向量
   （`excp_vector`）——这条状态机对**任何** cfxcode 都从未被真正实现过
   （`cfx_power` 现有的 `prev_run_mode`/`prev_cfx_mask`/`cause_ip` 三
   字段是 O1 用**软件** `cfx2rc` 写入模拟出来的假现场，从未经历过真正
   的硬件 trap 进入；`cause_id`/`cause_info` 连 `cfx_power` 都没有
   存储）。
3. **架构冲突（已由用户拍板，见下）**：`trap` 指令当前对
   `cfxcode==2`（`cfx_smon`）无条件独占执行 host/SE syscall 捷径
   （`.work/source/qemu/target/dadao/cpu.c:157` `if (cfxcode == 2)`），
   和"真实进入流程"语义互斥，不能共存在同一触发条件上。

**用户决策（2026-07-25）**：采用 KL-115a 报告 §4.4 的**选项A**——新增
一个默认关闭的可开关 profile（QEMU CPU 属性，比如
`-cpu dadao,cfx-smon-real=on`，具体命名由你决定，保持项目现有 QEMU
CPU 属性命名惯例），默认关闭时行为与现在完全一致（现有全部依赖 host
syscall 捷径的 E2E/lit 测试零回归）；只有显式打开这个属性时，
`trap cfx_smon` 才走本任务新实现的真实 SEE §5 进入流程。

O2 已实现的检查（`escape_cfx_mask` 设计1、`cfx2rc` CFXREG 设计3）均不
会拦截 O3 探针，`trap_cfx_mask` 这项检查机制当前完全不存在（不是"默认
挡住"，是"从不触发"）——详见 KL-115a 报告 §2，不需要为此额外做任何事。

## 目标

1. **新增 profile 开关**：QEMU CPU 属性（默认 off），控制 `trap
   cfxcode==2` 是走现有 host/SE syscall 捷径还是走本任务新实现的真实
   进入流程。默认关闭时 `cpu.c:151-336` 现有逻辑一字不改、一字节不受
   影响。
2. **新增 `cfx_smon` 专属异常现场帧**（结构体，比 `cfx_power` 现有的
   `cfx_power_frame` 多两个字段）：`prev_run_mode`/`prev_cfx_mask`/
   `cause_id`/`cause_ip`/`cause_info` 五个字段（SEE §3 cg5 表，
   `DADAO-12-SEE-主管系统运行环境.md:357-361`）。
3. **新增 `cfx_smon_supv_excp_vector` 的 `cfx2rc` 写入支持**（cg2/
   rc10，`DADAO-12-SEE §3` supv 表，KL-115a 报告已核对具体行号）——
   `switch_run_mode`/`switch_cfx_mask` 用 wiki 默认值即可（KL-115a §1.5
   已确认默认值满足本任务最小场景，不需要额外 `cfx2rc` 写入支持）。
4. **实现真实 `trap` 进入流程状态机**（profile 打开、`cfxcode==2` 时）：
   - 跳过步骤2-6（按 §1 结论，`CFXTRAP` 对 `cfx_smon` 不可屏蔽，直接
     视为通过）。
   - 步骤7：`cfx_smon` 帧的 `prev_run_mode<=inner_run_mode`、
     `prev_cfx_mask<=inner_cfx_mask`（异常发生前的值）。
   - 步骤8：`inner_run_mode<=switch_run_mode`（wiki 默认值 2/supv，
     `DADAO-12-SEE §3`）、`inner_cfx_mask<=switch_cfx_mask`（默认值
     全1）、`inner_cfx_code<=2`（smon）——这是本任务**第一次**真正让
     `inner_cfx_code` 变成非 `power` 的值。
   - 步骤9：`cause_id<=CFXTRAP`（`1<<0`）、
     `cause_ip<=`触发异常的 `trap` 指令自身地址（同步异常约定，
     `DADAO-12-SEE §5 L703`）、`cause_info<=`指令编码（原始 32 位
     `trap` 指令字，`DADAO-12-SEE §5` CFXTRAP 行"指令编码"）。
   - 步骤10：跳转到 `cfx_smon_supv_excp_vector`（本任务新增的可写
     寄存器，本项目延续 ADR-0004 扁平物理地址惯例，非 wiki 字面的核内
     地址映射——参照 O1 的 `cause_ip`/`supv_entry` 处理先例，不是新
     wiki gap）。
5. **`helper_escape`/`escape` 恢复分支扩展**：新增 `cfxcode ==
   DADAO_CFX_CODE_SMON` 分支，从新的 `cfx_smon` 帧恢复
   `prev_run_mode`/`prev_cfx_mask`/`cause_ip`（`cause_id`/`cause_info`
   是 HW-only 字段，不参与 escape 恢复，同 `cfx_power` 现有惯例）——
   否则会像现在这样落入"全零伪造帧"（`helper.c:265-269`）。
6. **`contracts/isa/spec.md`** 新增覆盖本任务实现的 `trap`（O3 子集）
   语义（当前 `trap` 整体列在 §7 M1 Excluded，`:992`，需要参照
   KL-110a/112a 把已实现部分从排除表移出、写进 §8 新小节，未实现部分
   继续留在排除表）。

## 约束

- **只实现 KL-115a 报告 §4.3 列出的部分**，不要顺带实现候选A（一般
  `cg_reg_deleg` 访问控制）、O2 设计2（已知与 HBI §3 矛盾）、
  `trap_cfx_mask` 通用检查机制（KL-115a 已确认这项检查从不触发，不影响
  O3，不在本任务范围）、`cfxld`/`cfxst`/`cfx2rd`、MMU/TLB、多层嵌套
  trap。
- 默认关闭时现有全部 E2E/lit/差分测试必须**零回归**——这是硬性验收项，
  不是"尽量不影响"。
- 状态转换逻辑集中在 `helper_trap`/`dadao_cpu_do_interrupt` 的
  `EXCP_CFXTRAP` 分支（profile 打开时的新代码路径）里，延续本项目
  carrier-point 惯例；不要在 `translate.c` 加检查逻辑。
- 不要修改 `cfxcode==2` 捷径本身的任何现有行为（profile 关闭时的行为
  逐行不变）。
- 完整 patch-series bare-pin replay（tree-hash 比对）是硬性验收项。
- 完成后写「完成区」+「审阅记录（subagent 自审）」；不需要嵌套
  subagent、不需要独立 reviewer（架构师会亲自复核，含独立重建 QEMU、
  独立构造/重跑探针、独立验证 profile 默认关闭时零回归）。
- gem5 侧移植是**独立后续任务**（比照 KL-110a/112a→KL-113a 的先例），
  本任务不碰 gem5。

## 验收

- **profile 默认关闭**：现有全量 lit E2E（`tests/lit/E2E/`）、
  `tools/run_differential.py`、`syscall_hello.test` 等依赖 host syscall
  捷径的测试全部零回归。
- **profile 打开时的 O3 探针**（沿用 KL-115a 报告 §4.1 给出的指令
  序列，可直接复用/改造 `gen_kl110a_o1_probe.py` 的 HBI §3 stub 部分）：
  - HBI §3 stub 执行完成后（O1 落地 supv），supv 侧写 `cfx_smon`
    的 `excp_vector`，然后执行 `trap cfx_smon,0`。
  - 观测到：`inner_run_mode`（应仍是 supv，因为 `switch_run_mode`
    默认值就是 supv）、`inner_cfx_code`（应变成 `smon`=2，第一次
    非 `power` 的值）、PC 落在 `cfx_smon` 的 `excp_vector`。
  - guest handler（在 `excp_vector` 处）读 `rd16`/`rd17` 确认参数
    真实传递、写 `rd31=0`、`escape cfx_smon,1`——观测到正确返回到
    `trap` 指令的下一条（`cause_ip+4`），`inner_run_mode`/
    `inner_cfx_code` 恢复到 trap 前的值。
  - 全程**不调用**任何 host syscall API（这是 O3 的核心断言，KL-101a
    "禁止直接调用 QEMU host syscall API"）。
- `contracts/isa/spec.md` 相关检查（`check_wiki_refs.py --profile isa`
  等）全部 PASS。
- 完整 patch-series bare-pin replay，tree hash 与开发树一致。

## 参考指针

- `docs/reviews/kernel-cfx-smon-o3-recon-20260725.md`（KL-115a，本任务
  精确范围、探针设计、架构冲突分析的来源，§4.1/§4.3/§4.4 尤其重要）
- `code-agent/tasks/KL-110a-*.md`/`KL-112a-*.md` 完成区（`cfx_power`
  帧的确切实现方式、carrier-point 设计、wiki 引用行号先例）
- `docs/reviews/kernel-cfx-state-patch-surface-20260721.md` §5.2
  （KL-102a 当年设想的"profile 互斥"设计，本任务是它的实际落地）
- `~/DADAO-wiki/DADAO-12-SEE-主管系统运行环境.md` 第678-811行（完整
  异常进入流程 10 步伪代码）、第351-364行（cg5 异常现场寄存器表）、
  第313-330行（cg2/supv 表，`switch_run_mode`/`switch_cfx_mask`/
  `excp_vector`）、第396-419行（`cfx_umon`/`cfx_smon` 异常原因表）
- `.work/source/qemu/target/dadao/cpu.c:130-336`（现有 host/SE syscall
  捷径实现，profile 关闭时必须逐行不变）
- ADR-0004（QEMU CPU 属性命名惯例、扁平物理地址先例）

---

## 完成区（2026-07-25）

**状态**：目标1-6 全部完成并验收通过。O3 探针 A/B 双跑（同一个二进制，
仅切换 CLI 属性开关）分别产生 exit=43（profile 打开，真实进入流程完整
往返成功）与 exit=0x99（profile 关闭，走现有 host/SE 捷径，`smon_handler`
从未被执行）——这组对照本身就是"profile 默认关闭时行为完全不变 + 打开
后走的是真实流程而非巧合"的直接证据。

### wiki 原文复核（动手前，亲自读，非转述任务文件/KL-115a 报告）

用 Read 工具亲自打开 `~/DADAO-wiki/DADAO-12-SEE-主管系统运行环境.md`
核对了任务文件和 KL-115a 报告引用的每一处行号，与转述一致，无发现偏差：

- 第273-331行 cg0-2 表：`switch_run_mode`(cg2/rc8，默认2/supv)、
  `switch_cfx_mask`(cg2/rc9，默认全1)、`excp_vector`(cg2/rc10，默认0)
  行号与含义核对无误。
- 第337-364行 cg4/cg5 表：`trap_num`(cg4/rc2)、`excp_prev_run_mode`
  (cg5/rc0)、`excp_prev_cfx_mask`(cg5/rc1)、`excp_cause_id`(cg5/rc2)、
  `excp_cause_ip`(cg5/rc3)、`excp_cause_info`(cg5/rc4)、
  `excp_cause_nonmaskable`(cg5/rc63) 逐条核对，`cause_id`/`cause_info`
  访问权限为 HW（硬件写），`prev_run_mode`/`prev_cfx_mask`/`cause_ip`
  为 RW（软件可写）——与 KL-115a 报告表格一致。
- 第396-419行异常原因表：`cfx_umon`/`cfx_smon`/`cfx_jmon`/`cfx_hmon`
  共用同一张表（"异常原因编码与 cfx_umon 一致"），`CFXTRAP`
  （`1<<0`）"是否可屏蔽"列="否"，`excp cause info`列="指令编码"，
  与任务文件/KL-115a 报告转述完全一致。
- 第678-811行完整 10 步异常进入流程伪代码：步骤2
  （`check_nonmaskable`，`:763-765`）确认"cause 的 nonmaskable 位为1时
  直接跳过步骤3-5"这一控制流本身就是 wiki 字面写法，不是简化；步骤7
  （`:700, 796-797`）、步骤8（`:701, 799-802`）、步骤9
  （`:703-705, 804-807`）、步骤10（`:706, 809-810`）逐行核对与本任务
  实现的状态机一一对应。
- 第813-845行异常退出流程（`escape`）：步骤1-2（`:838-840`）恢复
  `inner_cfx_mask`/`inner_run_mode`，步骤4（`:844`）
  `inner_inst_pointer <= cause_ip + (imms18<<2)` —— 探针里
  `escape cfx_smon,1` 的 `imms18=1` 故意选择让偏移量恰好是 4
  字节（一条指令），验证时用 trace 里的 `pc=` 字段逐字节核对
  （`cause_ip=0x100234` → `escape` 落地 `pc=0x100238`，差值正好4），
  不是只看"退出码非0"这种弱断言。

### QEMU 实现（`.work/source/qemu`，commit `8dc9d5a`）

延续 KL-110a/KL-112a 的 carrier-point 惯例：状态转换全部在
`helper_trap`/`dadao_cpu_do_interrupt` 的 `EXCP_CFXTRAP` 分支和新增的
静态函数 `dadao_cfx_smon_trap_enter()`（cpu.c）里，`translate.c` 只新增
了一处**纯数据操作数提取**（`trans_trap` 把 `ctx->opcode`——一个
翻译期常量——多传一个参数给 `gen_helper_trap`，供 `excp_cause_info`
使用），没有新增任何分支/检查逻辑（`git diff translate.c` 只有这一处
改动，可核对）。

- **`cpu.h`**：新增 `DADAOCfxSmonFrame`（5 字段：`prev_run_mode`/
  `prev_cfx_mask`/`cause_id`/`cause_ip`/`cause_info`，比 `cfx_power_frame`
  多 `cause_id`/`cause_info` 两个字段）；`CPUArchState` 新增
  `cfx_smon_frame`/`cfx_smon_supv_excp_vector`/`trap_insn`（后者是
  `trap_cfxcode`/`trap_func` 同类的 helper→do_interrupt 传值 scratch，
  存放触发异常的 `trap` 指令原始32位编码）；`ArchCPU` 新增
  `bool cfx_smon_real`（本任务第一个 QEMU CPU 属性字段）。
- **`cpu.c`**：
  - reset：`cfx_smon_frame` 全字段 + `cfx_smon_supv_excp_vector` 显式
    清零（wiki 字面复位值，无 O1 式的自定义复位先例可循，因为这是
    第一次有真实硬件入口写这个 frame）。
  - 新增 `static const Property dadao_cpu_properties[]`（照
    `target/riscv/cpu.c` 的 `DEFINE_PROP_BOOL` 用法）+
    `device_class_set_props(dc, dadao_cpu_properties)`，注册
    `cfx-smon-real`（默认 `false`）。
  - 新增 `dadao_cfx_smon_trap_enter()`：步骤7（保存现场，用
    `env->pc-4` 求 `trap` 指令自身地址而非用 `env->pc`
    本身——因为 `trans_trap` 无条件把 `pc_next+4` 存进 `env->pc`，这个
    约定不受 profile 影响，profile 打开/关闭都能复用同一个减法）→
    步骤8（模式切换，硬编码 wiki 默认值 `switch_run_mode=2/supv`、
    `switch_cfx_mask=全1`，第一次让 `inner_cfx_code` 变成非
    `power` 的值）→步骤9（`cause_id=CFXTRAP`、`cause_ip`、
    `cause_info=`原始指令字）→步骤10（跳 `cfx_smon_supv_excp_vector`）。
  - `EXCP_CFXTRAP` 分支：把原来的 `if (cfxcode == 2)` 改成
    `if (cfxcode == 2 && !cpu->cfx_smon_real)`（profile 关闭时与原条件
    逐字节等价，因为 `cfx_smon_real` 默认 `false`），host/SE 捷径的
    switch-case 分支体一字未改；新增
    `else if (cfxcode == 2 && cpu->cfx_smon_real)` 调用
    `dadao_cfx_smon_trap_enter()`；原来的 `else`（未知 cfxcode →
    0x82）不变。
- **`helper.h`/`helper.c`**：
  - `helper_trap` 新增第4个参数 `raw_insn`（存入 `env->trap_insn`，
    与 `trap_cfxcode`/`trap_func` 同一 scratch 传值机制，仅
    `cfx_smon_real` 分支消费）。
  - `helper_cfx2rc` 新增
    `if (cfxcode == DADAO_CFX_CODE_SMON && cg == 2 && rc == 10)` 分支，
    写 `cfx_smon_supv_excp_vector`（`(cg,rc)=(2,10)`），与其余分支的
    判定条件互斥（不同 `cfxcode`/`cg`/`rc` 组合），不影响任何既有分支。
  - `helper_escape` 的 frame 选择 `if/else` 链新增
    `else if (cfxcode == DADAO_CFX_CODE_SMON)` 分支，从
    `cfx_smon_frame` 恢复 `prev_run_mode`/`prev_cfx_mask`/`cause_ip`
    （`cause_id`/`cause_info` 不参与恢复，同 `cfx_power` 既有惯例）。
    **零回归论证**：profile 关闭时 `cfx_smon_frame` 永远不会被任何代码
    写入（`dadao_cfx_smon_trap_enter()` 只在 profile 打开时被调用），
    reset 把它清成
    `prev_run_mode=USER(0)/prev_cfx_mask=0/cause_ip=0`——这组值与改动前
    "无 frame 时退回的全零伪造帧"（`helper.c` 原 `else` 分支的
    `DADAO_RUN_MODE_USER/0/0`）逐值相同，因此
    `escape cfx_smon,N`（如果有测试真的这样调用）在 profile 关闭时的
    观测结果与改动前逐字节一致，不是"大概率不受影响"而是构造上必然
    相同。

### CPU 属性机制的一个发现（已如实记录，未修，超出本任务范围）

`-cpu dadao-cpu,cfx-smon-real=on` 实测失败（`unable to find CPU model
'dadao-cpu'`）。根因核实：`dadao_cpu_class_by_name()`
（`target/dadao/cpu.c`）在本任务之前从未被真正验证过——此前没有任何
任务用 `-cpu <name>,<prop>=<val>` 语法调用过 QEMU（DADAO 只有一个 CPU
类型，从未需要 `-cpu` 参数）。`parse_cpu_option()` 会把逗号前的
model-name 部分单独传给 `class_by_name`（不含逗号），但
`dadao_cpu_class_by_name` 内部再次用 `DADAO_CPU_TYPE_NAME()` 宏拼接后
缀（`"-dadao-cpu"`），导致查找的 typename 变成
`"dadao-cpu-dadao-cpu"`——不存在的类型名，这是一个预先存在、与本任务
无关的 bug（本任务约束里没有列出这个函数，任务范围外不修复）。
`-global dadao-cpu.cfx-smon-real=on`（QEMU 通用 QOM 全局属性机制，不
经过 `parse_cpu_option`/`class_by_name`）不受影响，本任务全部验证
用的都是这条路径。已在 `contracts/isa/spec.md` §8.4 和探针证据摘要里
如实记录，留给后续任务（或架构师决定是否算作"单行明确错误"直接修）。

### `contracts/isa/spec.md` 更新

- §7 M1 Excluded 表：`trap` 从整体排除改为"partial——见§8.4"，
  `cfx2rd`/`cfxld`/`cfxst` 仍整体排除不变。
- §8 顶部 scope note：补充说明 O3 覆盖的三项（`cfx_smon_supv_excp_vector`
  写入支持、`cfx_smon` self-escape、`trap` 的 SEE §5 步骤7-10 子集），
  明确排除范围（除 `cfx_smon` 外一律 ILLI、步骤2-6 不实现的原因、
  candidate B2/A 仍不实现的既有理由不变）。
- §8.2 code block/Encoding 行更新 `trap` 的排除范围描述。
- 新增 §8.4「`trap` Entry Flow — O3 Subset」：profile 机制说明 + 步骤
  1/2-5/6/7/8/9/10 逐条 wiki 引用（全部用 `[wiki §DADAO-12-SEE...]`
  格式，与项目既有引用惯例一致）+ escape 恢复范围说明 + CPU 属性
  机制发现的记录。
- `python3 scripts/check_wiki_refs.py --profile isa`：`OVERALL: PASS`
  （Check 2 曾因引用换行导致关键词与引用不在同一行触发4处误报，逐条
  改成同行引用后清零，过程见下「审阅记录」finding 1）。
- `python3 scripts/check_wiki_refs.py --profile abi`：PASS（未改动
  `contracts/abi/spec.md`，用于确认没有意外触碰）。

### 探针脚本与验证证据

新增 `tests/scripts/gen_kl116a_o3_probe.py`（仿 `gen_kl110a_o1_probe.py`
模式，复用其 `CFX_DELEG_TARGETS` 和 HBI §3 stub 逻辑）。证据存
`.work/evidence/kl116a-probes/`（gitignored）：

- `kl116a-o3-probe.bin`：单一探针二进制，同时用作 A/B 对照（见下）。
- **A（profile 关闭，默认）**：`exit=153(0x99)`，trace **没有**
  "trap cfx_smon real-entry" 行——确认走的是原捷径，`smon_handler`
  从未执行，`HANDLER_MARKER_ADDR` 保持 reset 值0，回读的
  `rd19`/`rd20` 与预期常量不符触发 mismatch 退出码。
- **B（profile 打开，`-global dadao-cpu.cfx-smon-real=on`）**：
  `exit=43`（success），trace：
  ```
  dadao: trap cfx_smon real-entry mode 2->supv cause_id=0x1 cause_ip=0x100234 vector=0x100400
  dadao: escape cfx=2 mode 2->2 mask=0xffffffffffffffff pc=0x100238
  ```
  逐项核对：`cause_ip=0x100234` = `trap` 指令自身地址（手工核算
  `supv_entry(0x100200)+0x34`字节的 setup 代码，与地址吻合）；
  `escape` 落地 `pc=0x100238=cause_ip+4`（`escape cfx_smon,1` 的
  `imms18=1`），精确验证了返回地址计算；`inner_run_mode` 全程保持
  `supv(2)`（`switch_run_mode` 默认值即 supv，与 trap 前一致）；
  `inner_cfx_code` 变成 `smon`（2）——KL-115a 报告强调的"第一次非
  power 的值"，`cause_id=0x1=CFXTRAP` 正确；`exit=43` 本身要求
  `smon_handler` 真的执行过（把 `rd16`/`rd17` 写进 RAM，之后
  `after_trap` 读回比对），不是"程序退出码非0"这种弱断言。
  **全程未调用任何 host syscall API**——`dadao_cfx_smon_trap_enter()`
  函数体里没有任何 stdio/文件 I/O 调用，代码走查即可确认
  （KL-101a §3.4 核心断言）。
- **O1/O2 回归复核**（同一个 `qemu-system-dadao`）：
  `kl110a-o1-handoff`（regen）、`kl112a-o1-regression`（regen）、
  `kl112a-design1-negative`（regen）、`kl112a-design3-negative`（regen）
  在 profile 关闭/打开两种情况下退出码均与改动前逐一致
  （42/42/0x82/0x86），因为这四个探针都不执行 `trap`，profile 对它们
  是无操作分支。
- 完整命令、trace 摘录、地址核算见
  `.work/evidence/kl116a-probes/kl116a-o3-summary.txt`。

### 验证结果

- 探针（A/B + O1/O2 回归复核）：**PASS**（见上）。
- `lit tests/lit/E2E`：**81/81 PASS**（profile 关闭，默认，无 lit 测试
  传 `-cpu`/`-global` 属性）。
- `python3 tools/run_differential.py`：
  `AGREE(3-way)=200 DIVERGE=0 HARNESS=0 QEMU-SKIP=0`；
  `SAIL AGREE(4-way)=200 SAIL-DIVERGE=0`——与 KL-112a 完成区记录的
  基线数字逐一致，零回归。
- `python3 scripts/check_wiki_refs.py --profile isa`：`OVERALL: PASS`。
- `python3 scripts/check_wiki_refs.py --profile abi`：`OVERALL: PASS`。
- `python3 scripts/validate_encoding.py tools/opcodes.yaml`：
  `91 records OK`（未新增/改动任何编码记录，数字与改动前一致——本任务
  不新增 opcode，`trap`/`cfx2rc`/`escape` 编码本身在 KL-110a 就已存在）。
- `python3 scripts/manifest_check.py`：PASS。
- `python3 scripts/check_issues.py`：PASS（Open 24/Closed 43/Total 67，
  无变化）。
- `python3 scripts/check_wiki_drift.py`：PASS（3 contracts verified）。
- `python3 scripts/check_qfc_coverage.py` / `check_legality_matrix.py`
  （非任务强制项，沿用 KL-110a/112a 惯例额外跑了一遍）：输出与本任务
  改动前的既有缺口性质一致（`op=0x76(trap)` 仍未登记进
  `tools/opcodes.yaml`——本任务未被要求也未新增/改动 opcode 编码记录，
  `validate_encoding.py` 的 91 条不变已确认这点）。

### `components/qemu/patches/`

- 新增 `0026-target-dadao-implement-O3-trap-cfx_smon-real-entry-f.patch`
  并追加进 `series`。QEMU commit：`8dc9d5a3c39856b70f718ec0075e0110c9078852`
  （detached HEAD，延续 KL-110a/112a 同样不建分支的提交方式）。
- **patch-series bare-pin replay**：`git worktree add --detach` 从
  manifest 锁定的 `385b0a7d9785c8f3ac7b116d7f31d61502b55183`（实为一个
  指向 `7c949c5` 的 tag，与 KL-112a 记录的同一枚举结果一致）开始，
  26 个 patch（`0001`-`0026`）全部用 `git am` 逐条应用成功（无冲突、
  无 `--3way`/`-C`）。
  - 开发树：`git rev-parse HEAD^{tree}` = `8be49dd403e2e317c2fc2e9347a589aa93230c72`
  - replay 树：同上，`8be49dd403e2e317c2fc2e9347a589aa93230c72`
  - **完全一致**。replay worktree 完成后 `git worktree remove --force`
    清理，`git worktree list` 确认未残留。

### 未做事项确认（对照约束逐条自查）

- 未实现候选A（`cg_reg_deleg` 访问控制）、O2设计2（`cfx2rc_cfx_mask`）、
  `trap_cfx_mask` 通用检查机制、`cfxld`/`cfxst`/`cfx2rd`、MMU/TLB、
  多层嵌套 trap——均未触碰，`git diff` 可核对没有引入这些机制的任何
  存储或检查代码。
- 未碰 gem5（`~/DADAO-gem5`/`components/gem5/patches/` 均未读写）。
- 状态转换逻辑集中在 `helper_trap`/`dadao_cpu_do_interrupt`
  （`dadao_cfx_smon_trap_enter()` 是 `cpu.c` 内的 static 函数，属于
  `dadao_cpu_do_interrupt` 同一个 carrier-point 单元），`translate.c`
  只有一行纯数据提取（`ctx->opcode` 传参），没有新增检查/分支逻辑。
- 未新增 `docs/wiki-deviations.md` 条目——本任务的每一个"没有额外
  cfx2rc 写入支持"的决定（`switch_run_mode`/`switch_cfx_mask`）都是
  直接使用 wiki 给定的默认值，不是发明例外规则或遇到矛盾，KL-115a
  报告 §5 的结论（"本次调研没有发现新的 wiki 沉默/矛盾"）在实现阶段
  没有被推翻。

---

## 审阅记录（subagent 自审）

**判决**：自审通过，一处发现已记录（CPU 属性命名机制的预先存在 bug，
见上文"发现"小节），不阻断本任务验收。

- **wiki 引用逐项复核**：本任务 §8.4 新增的每一处 `[wiki
  §DADAO-12-SEE-主管系统运行环境.md L###]` 引用，均用 Read 工具在
  `~/DADAO-wiki` 原文里逐条核对过（详见上文"wiki 原文复核"小节），
  不是照抄 KL-115a 报告或任务文件的转述——虽然内容与两者一致，但这是
  本次实现独立重新打开原文确认的，不是信任转述。
- **`check_wiki_refs.py` Check-2 报错的排查过程**：第一版 §8.4 文字里
  把关键词（`ILLI`/`excp_cause_mask` 等）和它们的 wiki 引用分写在
  相邻但不同的物理行上（Markdown 里视觉上是一段话，但脚本按物理行扫描），
  导致4处误报"缺引用"。核对脚本源码（`check_normative_assertions`，
  逐行扫描、要求引用/`[spec-decision:...]`与关键词同一物理行）后，把
  受影响的几处改写成关键词与引用同行（必要时牺牲一点排版换行成一整行），
  不是简单地在段落末尾多贴一个引用了事——如果只在段尾加引用而不管
  行内关键词是否在同一行，脚本仍会误报，这一点在第一轮修复后复测出来，
  确认第二轮改法（关键词与引用同行）才是真正解决问题而非绕过检查。
- **零回归论证不是"跑了测试所以大概率没问题"，是构造性证明**：
  `helper_escape` 新增的 `cfx_smon` 分支在 profile 关闭时读到的
  `cfx_smon_frame` 值，与改动前"无 frame 回退到的全零伪造帧"逐字段
  相同（`USER(0)/0/0`），这是靠代码走查（reset 赋值 + 没有任何
  profile-关闭路径会写这个 frame）得到的构造性保证，不只是依赖
  lit/differential 测试跑绿的经验性证据——测试通过是这个论证的
  交叉验证，不是论证本身。
- **A/B 探针复用同一二进制而非分别写两个探针**：这是本次实现的一个
  设计选择（相比 KL-112a 的"A/B 负控制"用了临时禁用代码重编译两次），
  优点是不需要重新编译 QEMU 就能拿到对照组，代价是需要在探针设计阶段
  想清楚"两条路径会落到同一个返回地址"这个事实（`trans_trap`
  无条件存 `pc_next+4`，与 profile 无关）——这一点在写探针脚本前就
  已经通过读 `translate.c` 确认，不是巧合发现。
- **未过度简化的自查**：`cause_id`/`cause_info` 是 KL-115a 报告强调的
  "连 `cfx_power` 都没有过"的两个字段，本次没有以"§1.5 说
  `cause_info` 不参与判定"为由跳过实现——任务目标2/步骤9明确要求
  实现，本次按"原始32位指令字"字面实现（新增 `helper_trap` 第4参数
  + `trap_insn` scratch 字段），没有用更省事的"只存 func 字段"之类
  的简化替代。
- **发现但未修复的 CPU 属性 bug 的处理方式自查**：确认这个 bug 与
  本任务的验收标准无关（`-global` 路径完全等价地验证了 profile
  机制本身），不属于"约束里列出的范围"，也不是"一行明确错误"（涉及
  `g_strsplit`/宏拼接逻辑的重新设计，不是改一个字面量），按任务规则
  如实记录、不擅自扩大范围去修，留给架构师决定后续处理方式。
