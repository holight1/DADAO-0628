# KL-122a：通用精确异常入口 carrier（QEMU + gem5）

**执行环境**：远端 Codex（本仓库），QEMU（`.work/source/qemu`）+ gem5
（`~/DADAO-gem5`）双后端合并一个任务

## 背景

`KL-120a`（已完成）把 `excp_prev_cfx_code`（E1）之类的寄存器载体通用化
了，但**没有碰"真实 trap 进入流程"本身**——QEMU 的
`dadao_cfx_smon_trap_enter()`/gem5 `TrapInst` 里对应逻辑目前**硬编码
只服务 `cfx_smon` 一个 cfx**（O3，`KL-116a`/`KL-117a`）。

`KL-118a`（调研）§1.3 已确认：`cfx_ptw` 的全部18类异常原因**同样全部
不可屏蔽**（"是否可屏蔽"列全部"否"，与 `CFXTRAP` 对 `cfx_smon` 的情况
相同）——这意味着 wiki 异常进入流程步骤2-6（不可屏蔽判断/两级mask/
陷入计数）对 PTW fault 同样可以合法整体跳过，跳过之后剩下的步骤7-10
（保存现场→模式切换→保存异常信息→跳向量）和 O3 已经实现的这套状态机
在结构上完全一样，只是"目标 cfx"不同。`KL-118a` §2.1 明确建议："后续
应先把 O3 的专用函数提升为共享 entry/exit carrier，再挂 PTW、TLB、
timer、UART；若各设备各复制一份入口逻辑，mask 优先级、精确 PC、
counter 和 nested frame 很容易漂移"。

本任务就是做这次提升——是 `KL-125a`（QEMU PTW 成功路径）、`KL-124a`
（gem5 FullSystem carrier）以及后续 timer/TLB/异步分派任务的共同前置。
**只处理"不可屏蔽同步异常"这一类**（步骤7-10 carrier），**不实现**
可屏蔽异常/异步中断的 mask/pending/优先级选择逻辑（步骤2-6 的真正
实现）——那是 `KL-131a`/`132a`（可屏蔽异步分派核心）的范围，本任务
只是给它们也预留了可复用的落脚点。

## 目标

1. **把异常现场存储从"两个具名 struct"泛化成"按 cfxcode 索引的
   数组"**：QEMU `cpu.h` 的 `DADAOCfxPowerFrame`/`DADAOCfxSmonFrame`
   两个专用类型 + `cfx_power_frame`/`cfx_smon_frame` 两个字段，改成
   一个统一的 `DADAOCfxFrame` 类型（含 `prev_run_mode`/
   `prev_cfx_mask`/`cause_id`/`cause_ip`/`cause_info`/`prev_cfx_code`
   六字段，`cfx_power`/`cfx_smon` 现有字段范围的并集）+
   `cfx_frame[64]`（每个 cfxcode 一份）。gem5 `isa.hh` 同构改造
   （`CfxPowerFrame`/`CfxSmonFrame`→统一 `CfxFrame`/`cfxFrame[64]`）。
   **这是对已验收代码的重构，不是纯增量**——迁移后 `cfx_power`
   （index 63）/`cfx_smon`（index 2）的现有字段值和行为必须逐位不变。
2. **把 `cfx_smon_supv_excp_vector` 泛化成按 cfxcode 索引的
   数组**：`cfx_supv_excp_vector[64]`（cg2/rc10，wiki `DADAO-12-SEE §3`
   cg2 表——这是每个 cfx 自己的 supv 异常向量，不是 `cfx_smon` 专有的，
   之前只实现了 `cfx_smon` 这一份是因为当时只有 O3 一个用例）。
3. **把 `dadao_cfx_smon_trap_enter()` 泛化成通用函数**（建议签名类似
   `dadao_cfx_precise_trap_enter(cpu, target_cfxcode, cause_id,
   raw_insn)`）：
   - 保留 O3 已验证的步骤7-10 逻辑（保存 `prev_run_mode`/
     `prev_cfx_mask`/`prev_cfx_code`→模式切换→保存
     `cause_id`/`cause_ip`/`cause_info`→跳 `cfx_supv_excp_vector
     [target_cfxcode]`），改成对任意 `target_cfxcode` 都成立。
   - 模式切换目标继续硬编码 wiki 默认值（`switch_run_mode`=supv，
     `switch_cfx_mask`=全1）——`KL-119a` §1.5 已确认这对 K1 范围
     足够，**不需要**新增 `cfx2rc`/`cfx2rd` 对
     `switch_run_mode`/`switch_cfx_mask` 本身的读写支持（那两个
     寄存器仍然不可配置，是本任务明确的非目标，不要顺带做）。
   - `cfx_smon` 的调用点（`trap cfxcode==2` 且 `cfx_smon_real` 打开）
     改成调用这个通用函数，验证行为逐字节不变。
4. **`helper_escape`/gem5 `EscapeInst` 的 frame 选择逻辑泛化**：
   把"`if cfxcode==power`...`else if cfxcode==smon`...`else 零帧`"
   这个特判链，改成"从 `cfx_frame[cfxcode]` 读取"（对所有 cfxcode
   统一）。由于 `cfx_frame[64]` 初始化时每个 slot 的 reset 值已经
   按 `cfx_power`（index 63，`prev_cfx_code` 默认=power）/`cfx_smon`
   （index 2，默认=0）/其余 62 个 slot（默认=0，同现有"零帧"行为）
   分别设置好，这个改动本身不需要新增任何检查分支，只是把两个具名
   访问点统一成一次数组索引。
5. **`cfx2rc`/`cfx2rd` 对 cg5 帧字段和 `(cg,rc)=(2,10)` 向量寄存器的
   读写路径**同步从"`if cfxcode==power||smon`"泛化成"对
   `cfx_frame[cfxcode]`/`cfx_supv_excp_vector[cfxcode]` 通用生效"——
   这意味着理论上任何 cfxcode 现在都能通过 `cfx2rc` 写自己的
   `excp_prev_run_mode`/`prev_cfx_mask`/`cause_ip`/`prev_cfx_code`/
   `excp_vector`，即使目前还没有真实硬件 trap 会进入它们（这是
   合理的、无害的泛化——寄存器本来就该是通用可读写的存储，只是
   目前只有 `cfx_power`/`cfx_smon` 会被真实硬件路径触碰）。
6. **硬性回归要求（不可省略，比 `KL-120a` 更重要，因为这次是重构
   已有存储结构）**：完成后必须重新独立跑一遍
   **`KL-110a`/`KL-112a`/`KL-116a`/`KL-117a`/`KL-120a` 全部既有探针**
   （QEMU+gem5 各自的），确认退出码/trace 逐位不变。

## 约束

- **不要实现 mask/pending/优先级选择逻辑**（wiki 步骤2-6 对可屏蔽
  异常的真正判定）——本任务的 carrier 只服务"不可屏蔽同步异常"这
  一类，`cfx_ptw`（18类原因全部不可屏蔽，`KL-118a` §1.3 已确认）
  和 `cfx_smon/CFXTRAP` 都属于这一类，可屏蔽/异步的通用分派是
  `KL-131a`/`132a` 的范围，不要提前做。
- **不要接任何真实的 PTW/TLB/timer/UART 触发源**——本任务只是把
  "已经被 `trap cfxcode==2` 触发过一次的入口逻辑"泛化成"任何
  cfxcode 都能复用同一段代码"，触发条件（什么时候真的产生一次
  `cfx_ptw` 异常）是 `KL-125a` 及后续任务的范围。
- **不要新增 `switch_run_mode`/`switch_cfx_mask` 的 `cfx2rc` 写入
  支持**——继续硬编码 wiki 默认值，这是明确的非目标（见目标3）。
- Carrier-point 逻辑集中在 QEMU `helper_cfx2rc`/`helper_cfx2rd`/
  `helper_escape`/`dadao_cfx_precise_trap_enter()`；gem5
  `CFX2RCInst`/`CFX2RDInst`/`EscapeInst`/`TrapInst`（及未来任何调用
  这个通用入口的新指令）。不要在 `translate.c`/gem5 decode 分派处
  加检查逻辑。
- 完整 QEMU + gem5 patch-series bare-pin replay（tree-hash 比对）是
  硬性验收项。
- 完成后写「完成区」+ 自审记录；继续沿用"自己开 reviewer subagent
  复核"的方法（`KL-118a`/`119a`/`120a` 都用了，效果很好）。

## 验收

- `KL-110a`/`112a`/`116a`/`117a`/`120a` **全部既有探针**（QEMU+gem5）
  重新独立跑一遍，退出码/trace 与改动前逐位一致——这是本任务能否
  声称"重构未破坏既有行为"的唯一证据，不能只跑新增的验证场景。
- 新增一个"泛化验证"探针：对一个**当前没有真实硬件 trap 路径**的
  cfxcode（比如 `cfx_ptw`=4，只是作为泛化正确性的验证对象，不是
  真的实现 PTW），用 `cfx2rc` 写它的 `excp_prev_run_mode`/
  `prev_cfx_code`/`excp_vector` 等字段，`cfx2rd` 读回验证；如果能
  构造一个"手工模拟 trap 进入"的场景（比如直接调用通用入口函数
  的测试接口，或者用某种方式触发它——如果做不到干净的触发方式，
  用寄存器读写往返验证即可，不强求）。
- 全量 lit E2E、`tools/run_differential.py`、`manifest_check.py`、
  `check_issues.py` 无回归。
- QEMU + gem5 patch-series bare-pin replay，tree hash 与各自开发树
  一致。

## 参考指针

- `docs/reviews/kernel-mmu-interrupt-recon-20260726.md`（KL-118a，
  §1.3 PTW 18类原因全部不可屏蔽的确认、§2.1"应提升为共享carrier"
  的建议、§5 KL-122a/123a 原始范围描述）
- `code-agent/tasks/KL-116a-*.md`/`KL-117a-*.md`/`KL-120a-*.md`
  完成区（O3 现有实现、E1 现有实现，本任务泛化的起点）
- `~/DADAO-wiki/DADAO-12-SEE-主管系统运行环境.md`（cg2/cg5 表、
  完整异常进入流程10步伪代码、`cfx_ptw` 异常原因表——第440-461行）

## 完成区（2026-07-26）

**状态**：实现与验收 PASS，独立 review 待回填。原路线图 KL-123a
（gem5 port）已按本任务契约合并执行，没有另造缺失任务文件。

### 实现

- QEMU：`DADAOCfxPowerFrame`/`DADAOCfxSmonFrame` 合并为
  `DADAOCfxFrame cfx_frame[64]`，向量改为
  `cfx_supv_excp_vector[64]`。reset 全 slot 清零，仅 index63 保留既有
  power 默认；`cfx2rc/cfx2rd` 的 cg5 与 cg2/rc10、`helper_escape`
  全部按 cfxcode 索引。O3 调用新的
  `dadao_cfx_precise_trap_enter(target,cause,raw)`，既有 smon trace
  格式保持不变。
- gem5：同构为 `CfxFrame cfxFrame[64]`/
  `cfxSupvExcpVector[64]`，reset 和 `copyRegsFrom()` 覆盖完整数组；
  `cfxPreciseTrapEnter()` 集中步骤7-10，TrapInst 只负责现有 smon
  source 路由并保持 NPC staging。
- 新增 `tests/scripts/run_kl122a_generic_carrier_probes.py`：以此前
  没有 frame/vector 存储的 cfx_ptw=4 验证 rc0/1/3/5、vector、
  HW-only rc2/4 写保护，并放开 power/hypv→ptw 后通过 generic
  `escape` 落到 PTW frame 的 cause_ip。QEMU/gem5 均退出46。
- 未实现 mask/pending/priority、step2-6、trap/escape counter、新
  PTW/TLB/timer/UART source 或 switch_run_mode/switch_cfx_mask 写口。

### 验证

- QEMU build PASS；gem5 `scons build/DADAO/gem5.opt -j4` PASS。
- KL-122a：`generic cfx_ptw frame/vector/escape=46/46`。
- KL-120a：`register=44/44; rd0 ILLI=130/130;
  pending profiles=7x45/45; nested=43/43`。
- QEMU O1/O2-regression/design1/design3/O3-off/O3-on：
  `42/42/130/134/153/43`。
- gem5 KL-113a：`42/130/134/42`；KL-117a：`153/43`。
- E2E 81/81；差分 `AGREE(3-way)=200`、gem5-SKIP=2、
  DIVERGE=0；`AGREE(4-way)=200`、Sail-SKIP=2、
  SAIL-DIVERGE=0。
- manifest/issues/wiki refs/wiki drift 与三仓 `diff --check` PASS。

### 提交与 replay

- QEMU `ae8afe05900c7c92300d08722c9b054703b6a1e3`；
  patch `0028-target-dadao-generalize-precise-CFX-carrier-KL-122a.patch`；
  stable patch-id `5a1d277151d7fa941b4a01c17290014aa74f548d`。
  manifest pin 起 28/28 replay，开发/replay tree 均为
  `d06de0af504efc0daee2386b5e2002b864d27484`。
- gem5 `d85d2bd8b9a475d42e87498a3b02d9fc850a946b`；
  patch `0021-arch-dadao-generalize-precise-CFX-carrier-KL-122a.patch`；
  stable patch-id `7988a2f58c993ef9f282c55ee78f65b724bde7ae`。
  manifest pin 起 21/21 replay，开发/replay tree 均为
  `326443813e90aeefb3ac3e5f5e2b40ae81abd1a2`。

### 自审

结论：**PASS，可进入独立 review**。逐项比对两端 frame 字段、reset、
copy、地址截断、HW-only 字段、escape 和 precise-entry；generic
cfx_ptw 探针会使旧的 smon/power 特判实现失败，不是仅重跑 O3 的假绿。
范围保持在不可屏蔽同步 carrier，未提前实现 KL-125a 或异步分派。

### 独立 review

Reviewer 结论：**PASS，无阻塞项**。其独立复核确认 power/smon
逐位等价、双端 cg5/vector/escape/entry/NPC staging 对称、泛化探针
能击穿旧实现、28/28 与21/21 replay tree 正确且无范围扩张。

唯一 Low finding 是 QEMU 通用入口的日志仍硬编码 `cfx_smon`，并有
三处注释引用已删除的旧函数名。已直接修复：当前 smon/CFXTRAP 分支
保留 KL-116a trace 字节不变，其它未来 target 使用带数字 cfxcode 的
通用 trace；旧注释全部改指向 `dadao_cfx_precise_trap_enter()`。修复后
QEMU 重建、KL-122a `46/46`、gem5 O3 `153/43` 和 28/28 replay 均
再次通过。Reviewer 全程只读，未修改文件。
