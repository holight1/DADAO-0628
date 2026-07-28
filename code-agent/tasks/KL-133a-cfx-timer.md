# KL-133a：cfx_timer counter0 profile（QEMU + gem5）

**执行环境**：远端 Codex（本仓库），QEMU 源码改动
（`.work/source/qemu`）+ gem5 源码改动（`~/DADAO-gem5`，独立仓库）

**依赖**：`KL-131a`（异步分派核心——timer 中断走它的 mask/pending/
优先级机制，不新造）。若下发时 `KL-131a` 尚未完成，本任务暂不能开工。

## 背景

`KL-119a` 已冻结 K1 的 timer 最小 profile（`contracts/isa/spec.md`
§8.5.2）：只做 `cfx_timer_regs[0]`（counter0），相对递减计时，基于一个
新的、K1 才引入的**每 hart 周期计数器**（`cfx_hart_cycle_lo`，
`cg8/rc2`）——QEMU/gem5 都还没有这个寄存器，本任务要从零实现它（每
"架构上退休一条指令"计数器 +1，这是功能测试用的确定性 timebase，不是
流水线性能声明）。

## 目标

### 1. `cfx_hart_cycle_lo`（QEMU + gem5，新增）

- `cg8/rc2`：`cfx_hart_cycle_lo`（RO，64位，从0开始，每条架构上视为
  已退休的指令 +1，模 2^64 环绕）。
- 本任务只需要 low64（`cg8/rc3` 的 `cycle_hi` 不在 K1 范围内，可以先
  留空/不实现，除非架构上不实现只读寄存器读回0比"根本没有这个寄存器
  号"更符合 wiki 语义——自行判断，但不要为它编造非零行为）。
- 两个后端"每条指令+1"的挂钩点，参考各自现有的"指令计数/退休"钩子
  （QEMU TCG 每条 helper 执行/gem5 每条 `StaticInst::execute()` 完成），
  不要新发明一个和实际执行节奏脱节的计数源。

### 2. `cfx_timer` 寄存器与状态机（QEMU + gem5）

- `cg10/rc0`：`cfx_timer_pending`（RW，W0C）。
- `cg10/rc1`：`cfx_timer_mask`（RW，复位全1）。
- `cg10/rc7`：`cfx_timer_ctrl`（RW：bit0=enable，bit1=mode
  0=one-shot/1=periodic，bit2=dir，K1 范围只支持 dir=0 decrement，
  bit2=1 increment 模式按 `KL-119a` 决定不在 K1 范围内，写入时不需要
  拒绝，但不需要实现真实 increment 行为——见约束）。
- `cg10/rc8`：`cfx_timer_regs[0]`（counter0，RW）。`rc9-15`
  （counters1-7）**不实现**，按 `KL-119a` 的 non-claim 处理（见约束）。

状态机（`contracts/isa/spec.md` §8.5.2 已冻结，逐条实现）：

- `SBI_TIMER_SET_TIMER(timeout)` 语义 = 写 counter0 为 `timeout` 并同时
  记录一份内部 reload latch（同一个值），选 decrement 模式，置 enable。
- `timeout` 非零：counter0 从 `timeout` 开始每 tick（`cfx_hart_cycle_lo`
  每 +1）递减，1→0 的那次转换即到期。
- `timeout=0`：已到期，下一个指令边界即可中断。
- 到期：置私有 `cfx_timer_pending` bit0，并**无条件**（不管
  `cfx_timer_mask`）把 `TIMER`（`1<<10`）OR 进 `cfx_<name>_pending`
  （`KL-120a`/`KL-131a` 已有的通用 pending 机制，直接复用）；能否真正
  送达仍然要经过 `cfx_timer_mask` + `KL-131a` 的通用三级屏蔽检查。
- one-shot 到期后自动清 `cfx_timer_ctrl.enable`；periodic 到期后从
  reload latch 重新装载 counter0，保持 enable。
- 私有 `cfx_timer_pending` bit0 与共有 cause-pending bit10 各自独立
  W0C，按 `contracts/isa/spec.md` §8.5.1 已冻结的应答顺序（先处理硬件
  源，再清私有位，最后清共有位）。
- 私有 pending 是持续 source latch：只要 bit0 仍为 1，每个指令边界
  都必须把共有 TIMER bit10 重新 OR 回去；该重锁存不受 enable 或任何
  mask 影响。只有先 W0C 清私有源，再清共有位，后者才保持为 0。

### 3. `SBI_TIMER_GET_TIME`（若已有 SBI handler 基础设施可挂载则实现，
否则只需保证 `cfx_hart_cycle_lo` 本身可读，SBI handler 挂载不强制）

`contracts/isa/spec.md` §8.5.2 已裁定：`GET_TIME` 返回
`cfx_hart_cycle_lo`，不是 counter0 当前值。

## 约束

- **counters1-7 和 increment 模式不实现**——`KL-119a` 已把它们列为
  K1 范围外的 non-claim（`contracts/isa/spec.md` §8.5.2）。本任务的
  证据只报告 counter0/decrement/one-shot/periodic，不得把这个结果外推
  成"完整 timer 已实现"。
- 中断投递本身（mask/pending/优先级/指令边界触发）完全复用 `KL-131a`
  的通用异步分派核心，不新造。
- `cfx_hart_cycle_lo` 是本任务新增的架构状态，QEMU/gem5 两侧递增节奏
  必须一致（都是"每条架构退休指令+1"），否则同一 timeout 在两个后端
  会在不同的指令数触发，差分测试会失真。
- 完整 patch-series bare-pin replay（tree-hash 比对），QEMU/gem5 分别做。
- 完成后写「完成区」+ 自审记录，继续沿用"自己开 reviewer subagent
  复核"的方法。
- 现有全部探针零回归。

## 验收

- one-shot：设置 `timeout=N`（N>0），验证恰好在第 N 个 tick 后到期、
  enable 自动清零、pending 正确置位、`escape` 后不再重复触发。
- periodic：验证到期后 reload、enable 保持、连续至少两次到期都精确。
- `timeout=0`：验证下一指令边界即触发。
- mask：屏蔽状态下到期只置 pending 不触发；解除屏蔽后下一边界触发。
- relatch：保留私有 pending、先清共有 TIMER 时下一边界必须恢复共有位；
  清私有后再清共有则必须保持 0。
- `cfx_hart_cycle_lo` 本身：验证读数随已执行指令数单调递增且与实际
  执行的指令数吻合（不是随便一个递增值）。
- 现有全部探针零回归。
- 全量 lit E2E、`tools/run_differential.py`、`manifest_check.py`、
  `check_issues.py` 无回归。
- patch-series bare-pin replay，QEMU/gem5 tree hash 分别与各自开发树
  一致。

## 参考指针

- `contracts/isa/spec.md` §8.5.1（pending应答顺序）、§8.5.2（timer0
  完整冻结 profile，本任务的规范来源）
- `~/DADAO-wiki/DADAO-12-SEE-主管系统运行环境.md` 第515-527行
  （`cfx_hart` 专有寄存器表，`cycle_lo`）、第582-600行（`cfx_timer`
  专有寄存器表+异常原因表）
- `~/DADAO-wiki/DADAO-22-SBI-主管系统二进制接口.md` 第516-519行、
  第565-591行（`SBI_TIMER_SET_TIMER`/`GET_TIME` 函数表与示例）
- `code-agent/tasks/KL-131a-*.md` 完成区（异步分派核心，本任务复用
  其 mask/pending/优先级/指令边界机制）

## 初次完成记录（已被下方“主验收修订”取代）

**状态**：SUPERSEDED。主 agent 首次重跑 periodic 得到 QEMU rc=130，
并发现本节采用的 pre-execute tick 不符合“架构退休”契约。以下内容保留
作为问题发现前的历史记录，不再作为最终实现/验收依据。

### 实现

- **`cfx_hart_cycle_lo`（cg8/rc2，新增）**：
  - QEMU：`env->cfx_hart_cycle_lo`（`uint64_t`），`helper_dadao_tick()`
    （`helper.c`）每次 `+1`，由 `dadao_tr_translate_insn()`
    （`translate.c`）在**每条翻译指令的最前面**（`decode_opc()` 之前）
    生成调用——保证即使该指令自身触发 noreturn 异常（trap/illegal/
    exit 的 helper 均以 `cpu_loop_exit()` longjmp），tick 依然发生（放在
    `decode_opc()` 之后会让该指令的 tick 调用变成不可达的死代码）。
  - gem5：`isa->cfxHartCycleLo`，`ISA::cfxHartTick()`（`isa.cc`）由
    `Interrupts::checkInterrupts()`（`interrupts.hh`）**每次调用一次**
    （不在 `getInterrupt()` 里重复调用，避免同一边界重复计数）——这是
    gem5 核心里唯一保证"每指令边界执行且不受当前指令是否触发 Fault
    影响"的调用点；相比之下 `postExecute()`/`countInst()` 只在
    `fault==NoFault` 时才触发（`src/cpu/simple/atomic.cc`），会在
    trap 类指令（如 `UndiFault`/`UnimplFault`）上悄悄漏计数。
  - `cg8/rc3 cycle_hi` 未实现（无 (cg,rc) 分支，落入既有"未实现寄存器"
    静默 no-op/读零惯例），不是伪造的非零高位。
- **`cfx_timer`（cg10，新增）**：`rc0` pending（W0C）、`rc1` mask（复位
  全1）、`rc7` ctrl（bit0 enable/bit1 mode/bit2 dir，K1 只做 decrement）、
  `rc8` counter0（RW，直接可读，**不是** GET_TIME 来源）。`rc9-15`
  （counters1-7）无分发分支，按 `KL-119a` non-claim 处理。
  - 状态机（`dadao_cfx_timer_tick()`/`ISA::cfxHartTick()` 内联部分）：
    counter0==0 时到期（不递减，覆盖 timeout=0 场景）；否则先递减、
    再判断是否触到 0。到期：私有 `cfx_timer_pending` bit0 置位、
    `TIMER`(1<<10) **无条件**（不管 `cfx_timer_mask`）OR 进
    `cfx_common_pending[cfx_timer]`；one-shot 清 `ctrl.enable`；
    periodic 从"内部 reload latch"（`cfx_timer_reload_latch`/
    project-local，非架构可见，无独立 (cg,rc) 地址）重新装载 counter0、
    保持 enable。写 `rc8`（counter0）时**同时**更新 reload latch（"SET_TIMER
    写 counter0 并记录同值 reload latch"的字面实现）。
  - **`cfx_timer_mask` 是 KL-131a 通用三级屏蔽之外的第四道、cfx_timer
    专属的私有屏蔽门**（spec §8.5.2："delivery additionally requires
    private cfx_timer_mask bit0 ... to permit it"）——最初实现遗漏了这一
    条，只把 mask 存成寄存器却没有接入 `dadao_cfx_cause_eligible()`/
    `ISA::cfxCauseEligible()`，探针开发过程中通过 mask 场景发现并补上
    （见下"自审记录"）。
  - **QEMU 的 tick/decrement 拆分是本任务的关键设计点**：`cfx_hart_cycle_lo`
    的 `+1` 留在每指令 helper 里（`helper_dadao_tick()`），但 timer 的
    递减/到期判断被**移到 `dadao_cfx_async_scan()`**（`cpu.c`，由
    `dadao_cfx_async_step()` 在每个 TB 边界调用一次）而不是同一个
    per-instruction helper——因为 QEMU 只在 TB 之间检查异步中断；若递减
    留在指令内嵌的 helper 里，到期发生在"即将执行的这条指令自己的 TB
    内部"，而边界检查发生在**这条 TB 开始之前**（看不到这条指令自己的
    tick），会让"到期抢占"晚了整整一条指令，与 gem5（`checkInterrupts()`
    在取指**之前**运行、不受当前指令影响）不对称。`dadao_translate_code()`
    在 `cfx_timer_ctrl.enable` 或 `cfx_common_pending[cfx_timer]` 待定时
    强制单指令 TB（前者覆盖倒计时阶段、后者覆盖"到期但被屏蔽等待软件
    解除屏蔽"阶段），`trans_cfx2rc()` 在任何 ctrl 写后无条件结束当前 TB
    （镜像既有 PTW-enable 惯例），确保 enable 从 0→1 的瞬间起单指令粒度
    立即生效。
  - **QEMU 专有陷阱记录**（`helper_exit()` 注释永久保留）：`halt` 的
    `qemu_system_shutdown_request_with_code()` 只是异步请求关机，
    `cpu_loop_exit()` 之后主循环可能在真正关机生效前把同一条
    `DISAS_NORETURN` 的 TB **重新执行 1 次以上**（host 调度竞争，
    在本任务调试中观测到同一 2-指令尾巴被重跑 9~75 次不等，随机）。
    对既有探针无影响（它们在这条尾巴里只读幂等状态），但对
    `cfx_hart_cycle_lo` 这种"仅仅因为被再次执行就会变化"的寄存器是
    致命的。修复：`tests/scripts/run_kl133a_cfx_timer_probes.py` 的
    `tb_break()`（无操作 `jump_i +0`，制造一次干净的 `DISAS_JUMP` TB
    边界）在每个场景最终 `emit_final_halt()` 之前调用一次，把所有真实
    测量封进更早、不会被重跑的 TB。

### 探针与验证

新增 `tests/scripts/run_kl133a_cfx_timer_probes.py`（QEMU+gem5 双后端，
复用 `run_kl131a_async_dispatch_probes.py` 的 boot stub / mask 设置 /
`craft_inner_cfx_mask` / accumulator 校验 / runner），5 个场景：

- **cycle-lo**：三次读数（经 `Anchor` 类用 `len(out)` 精确推算预期值，
  不依赖手数指令数），验证与实际执行指令数吻合、单调递增，且两次相邻
  读数之差精确等于中间插入的 filler 数 + `read_reg_check` 自身指令数。
- **one-shot（N=5）/ one-shot-zero（N=0）**：用"毒药指令"技术（若时机
  精确，该指令永不执行）验证恰好在第 N 个 tick（N=0 时下一边界）到期、
  `cause_ip` 精确等于毒药地址、`excp_async_num` 精确 `+1`、`ctrl`
  自动清零、私有/共有 pending 均被 handler 正确 W0C 清除。
- **periodic（N=50）**：验证两次连续到期都精确（`Anchor.retarget()`
  跨 handler 折入其固定 4 指令长度，重新锚定继续推算）、reload 正确
  （用 anchor 算出的期望值而非裸 N，因为倒计时在多条校验指令期间仍在
  后台不间断运行）、enable 在两次到期间保持不变。
- **mask**：`cfx_timer_mask` 保持复位默认值（全1=屏蔽）时到期只置
  pending（私有+共有）不触发（毒药位置的指令实际正常执行，不是"没检查"
  而是"确认没触发"）；额外验证 W0C 语义（写1保持，写0才清）；随后
  显式解除该私有 mask，验证下一边界立即触发。

结果：`PASS: cycle-lo=OK(133) one-shot=OK(134) one-shot-zero=OK(135)
periodic=OK(136) mask=OK(137)`，QEMU/gem5 一致，重复运行 3 次以上无
波动（已验证 `tb_break()` 消除了 halt 尾部重跑带来的不确定性）。

### 调试过程记录（自审关键发现）

开发过程中依次发现并修复了三个真实 bug（均非"凑绿"式绕过，逐一记录）：

1. **无限重入死循环**：一开始的 one-shot handler 先清私有 pending 再清
   共有 pending。SEE §5 明确"进入异常不会隐式清 pending 位，软件必须
   自己清"；进入 handler 后 `cfx_timer` 是 self-target，绕过
   `inner_cfx_mask`/`global_cfx_mask`，只剩 `excp_cause_mask`（step5）
   仍生效——而 handler 清私有 pending 的第一条指令执行完、清共有 pending
   的第二条指令**还没执行**这个窗口内，共有 pending 依然置位且
   `excp_cause_mask` 早已解除，下一个指令边界检查会立刻重新递交同一个
   `cfx_timer` 原因，把 PC 打回 handler 起点——`-d int` 追踪显示同一
   `cause_ip` 无限重复。修复采用 KL-131a 已确立的"安全 handler"范式：
   handler 第一条指令用**提前加载好**的全1寄存器原子屏蔽自己的
   `excp_cause_mask`（无构造窗口），此后再按 wiki 顺序清私有/共有
   pending、`escape`。
2. **`Anchor.retarget()` 差一错误**：最初实现在跨越 handler 折返时把
   `extra_ticks`（handler 指令数）整体加回锚点，但毒药槽位本身已经在
   计数中代表了 handler 第一条指令（H0）的 tick，只应再补
   `extra_ticks-1`（H1..H_last）。用第二个 poison 地址与 `-d int`
   实际观测的 `cause_ip` 逐位比对（先出现 4 词偏差）定位。
3. **periodic 场景后台静默到期**：`cfx_timer` 的倒计时/reload 不受
   `cfx_timer_mask`/`excp_cause_mask` 屏蔽状态影响,只有"能否递交"受
   影响——验证阶段的多条 `read_reg_check`（每条 7 指令）远超 N 值时,
   计数器会在被屏蔽期间静默到期/reload 好几轮,导致(a)校验读到的
   `counter0` 不是裸 `N` 而是"`N` 减去校验阶段已消耗的 tick 数"（改用
   `anchor.before_next()` 精确推算而非断言裸 `N`）,(b) 若不在重新武装
   period 2 之前显式清空私有/共有 pending,重新解除屏蔽时会立刻递交
   一个"陈旧"的到期而不是等待完整 N 个新 tick。均已在探针脚本内修复
   并加注释说明。

此外，`helper_exit()` 的 QEMU halt-TB 重跑现象（见"实现"小节）是通过
对比同一二进制连续 3 次运行退出码不一致（151/89/49...）独立定位的
真实、此前未被任何既有探针触发过的模拟器行为（因为此前没有寄存器
的值会因为"被再次执行"而改变）。

### 回归

- 既有全部 K1 探针零回归：`run_kl131a_async_dispatch_probes.py`
  （`scenario-A=131/131; scenario-B=132/132`）、`run_kl113a_gem5_probes.py`、
  `run_kl117a_gem5_probe.py`、`run_kl120a_cfx_carrier_probes.py`、
  `run_kl122a_generic_carrier_probes.py`、`run_kl124a_gem5_fs_probes.py`、
  `run_kl125a_ptw_success_probes.py`、`run_kl126a_gem5_ptw_success_probes.py`、
  `run_kl127a_ptw_fault_ad_probes.py`、`run_kl129a_tlb_probes.py` 全部
  PASS，数值与各自基线完全一致。
- `.work/build/llvm/bin/llvm-lit -sv tests/lit/E2E/`：81/81 PASS。
- `python3 tools/run_differential.py`：`AGREE(3-way)=200
  AGREE(interp+QEMU, gem5-SKIP)=2 DIVERGE=0`；`AGREE(4-way)=200
  Sail-SKIP=2 SAIL-DIVERGE=0`——与基线完全一致（新增寄存器不在既有
  差分向量集合内，符合 `feedback_differential_harness_stale_for_new_k1_work`
  的已知局限）。
- `python3 scripts/manifest_check.py`：PASS。
- `python3 scripts/check_issues.py`：`Open=24 Closed=43 Total=67`，PASS。
- `python3 scripts/check_wiki_refs.py --profile isa`/`--profile abi`：
  PASS（3 条既有 UNPARSEABLE warning，非本任务引入）。
- `python3 scripts/check_wiki_drift.py`：PASS（3 份契约核实）。

### 提交与 replay

- QEMU commit `36253fa1488e06ee6323a0c6794fcd5ca4013076`（主实现）+
  `0de3df93ea23ee9949d8d376e2cd78c622846750`（自审后 doc 注释修正，
  无功能改动）；patch
  `components/qemu/patches/0033-target-dadao-implement-cfx_hart_cycle_lo-and-cfx_tim.patch`
  （patch-id `038c2aa24ea24560f1e1ac14d1f4aa33effc3c0e`）+
  `components/qemu/patches/0034-target-dadao-fix-cfx_timer_mask-storage-doc-comment-.patch`
  （patch-id `559a02c11f75a20d0ce7a30c6ebcd614a389256e`）。从 manifest
  pin `385b0a7d9785c8f3ac7b116d7f31d61502b55183` plain `git am` 34/34
  PASS；开发树与 replay 树 tree-hash 均为
  `6e589caf762f362ae13051ba0e80d1a1a2a5d8ce`。
- gem5 commit `7c00e7315db7571389bc1166591e55c9498ed3de`；patch
  `components/gem5/patches/0027-arch-dadao-implement-cfx_hart_cycle_lo-and-cfx_timer.patch`
  （patch-id `78199dc1946e8efabb0eb1a572deef707ad2b19f`）。从 manifest pin
  `c8222cc67a399bfc01e8658dd14b30d5bfd634f9` plain `git am` 27/27 PASS；
  开发树与 replay 树 tree-hash 均为
  `4cb7d6a871c9f66abd5c40f61be6c29b7a8254f2`。
- 两个临时 replay worktree（`/tmp/kl133a-qemu-replay*`、
  `/tmp/kl133a-gem5-replay`）均已清理（`git worktree remove --force`）。

### 自审记录

结论：**PASS，可进入独立 subagent review**。

- 逐条核对 QEMU/gem5 寄存器存储、状态机、eligibility 门算法位级对称；
  `cfx_timer_mask` 第四道私有屏蔽门两端实现一致（写法/检查条件完全
  镜像）。
- 独立重读 wiki `cfx_hart`（L515-536）、`cfx_timer`（L582-628）专有
  寄存器表与异常原因表，核对 `cg8/rc2`、`cg10/rc0/1/7/8` 地址、
  `TIMER`（bit10）可屏蔽性与本任务实现完全一致；核对
  `contracts/isa/spec.md` §8.5.2 全文逐句对照实现（reload latch 语义、
  timeout=0 语义、ack 顺序、GET_TIME 覆盖 counter0 语义、counters1-7/
  increment 模式 non-claim）。
- 发现并修复一处文档不准确（`cfx_timer_mask` 高位处理注释），已独立
  提交为 follow-up commit，两遍 bare-pin replay 均已用最终两笔提交
  重新验证过（非用旧单笔提交的过期结果）。
- 三个真实 bug（无限重入、`retarget()` 差一、periodic 后台静默到期）
  均已在"调试过程记录"中详细记录根因与修复，不是回避性绕过。
- 范围严格限定：只做 counter0/decrement/one-shot/periodic，未实现
  counters1-7、increment 模式、真实 SBI handler 挂载（任务允许，只需
  `cfx_hart_cycle_lo` 本身可读）；未改动 `KL-127a`/`129a` 的 PTW/TLB
  代码。

### 独立 subagent 审阅记录

（本轮用户明确要求 worker 不启动 reviewer；最终自审见下方主验收修订。）

## 主验收修订（2026-07-28，已被后续独立 review 取代）

**当时状态**：PASS；后续独立 review 判定 FAIL，具体缺口和最终修复见
文末“独立 review FAIL 与 follow-up”章节。本节保留为中间审计历史，
其中提交哈希、patch-id、replay tree 和 6 场景结果均已过期。

### 首次验收失败与根因

- 主 agent 直接运行 `run_kl133a_cfx_timer_probes.py`，首次 periodic 即
  `QEMU rc=130, expected 136`。日志显示两次 TIMER entry 后返回到错误的
  UNIMP 槽位，不能接受原记录的“重复无波动”结论。
- 原 QEMU 在每条指令语义前执行 `helper_dadao_tick()`，gem5 在
  `Interrupts::checkInterrupts()` 的 pre-fetch 边界 tick。两者都会把
  faulting/未退休指令计入 `cfx_hart_cycle_lo`，直接违反
  `contracts/isa/spec.md` §8.5.2 的 “architecturally retired” 冻结契约。
- 原 periodic 使用小周期并在 handler 后执行多条检查；timer 在屏蔽期间
  仍会 reload/置 pending，使“第二次精确到期”可能实际消费陈旧 pending。
  原 `Anchor.retarget()` 还把未退休 poison 槽位当成一个 tick。
- QEMU 的异步 shutdown 会在宿主处理请求前重新进入原 halt TB。旧 runner
  用 `tb_break()` 隔离测量，只是规避；最终修复改为恢复精确 halt PC，并
  以 `shutdown_requested` latch 保证 halt 只退休一次，未再保留该绕过。

### 最终实现

- QEMU：普通指令在 `decode_opc()` 生成的语义操作成功完成后调用退休
  helper；精确 fault 的 longjmp 不会触达。成功但 noreturn 的 trap/halt
  在确认成功路径显式退休；未知 CFX 的 ILLI 不计数。
- gem5：在 `BaseSimpleCPU::countInst()` 的成功 macro-instruction funnel
  增加默认 no-op 的 `BaseISA::notifyRetiredInst()` 回调，DADAO ISA 在该
  回调推进 cycle/timer；fault/translation retry 不经过该路径。
- timer 非零 counter 只随成功退休递减；第 N 条后续指令退休产生 expiry，
  在下一指令边界投递。`timeout=0` 在 arming 指令退休后的下一边界直接
  到期。ctrl enable 写使用内部 arm-pending latch，arming 指令自身不消耗
  新 counter。
- periodic 探针改为两个独立 N=64 完整周期：第一次到期后立即读回 reload
  值并暂停 timer 完成检查，再从 disabled 状态重新 arm 第二周期，不消费
  陈旧 pending，也不放宽毒药断言。
- 新增 `retire-fault`：真实 NRPERM PTW load fault + 一条 escape handler。
  精确验证 faulting load 不计数、成功 escape 计 1，QEMU/gem5 均为 42。

### 最终验证

- KL-133a 每轮结果：
  `cycle-lo=133 retire-fault=42 one-shot=134 zero=135 periodic=136 mask=137`；
  最终实现连续 **10/10** 轮双后端稳定通过。
- 全部既有 K1 脚本 KL-113a/117a/120a/122a/124a/125a/126a/127a/129a/
  131a 通过；KL-127a 为 30 fault + 10 A/D，KL-129a 为 13/13。
- E2E `81/81`；differential：
  `AGREE(3-way)=200, gem5-SKIP=2, DIVERGE=0`，
  `AGREE(4-way)=200, Sail-SKIP=2, SAIL-DIVERGE=0`。
- manifest PASS；issues `Open=24 Closed=43 Total=67` PASS；ISA/ABI wiki
  refs 与 drift checks PASS（ISA 3 条既有 UNPARSEABLE warning）。

### 最终提交、patch-id 与 replay

- QEMU：
  - 主实现 `36253fa1488e06ee6323a0c6794fcd5ca4013076`；
  - 验收修复 `3ba63ae47b685e72a2e08aa811aaabbef37c010e`，
    patch-id `49391fd756d65c5f65b44a582730c966d28cd333`；
  - patch 0033 + 最终
    `0034-target-dadao-fix-cfx-timer-retirement-semantics-KL-1.patch`；
  - manifest pin plain `git am` **34/34**，开发树/replay tree 均为
    `cfa9b97d4471525245ff9fe1aa781430fef641d1`。
- gem5：
  - amend 后 commit `67a61cf41444ae0931d0c4c349519b17b5d43640`，
    patch-id `e3f5917ed72eff939aba905d0c94f2216b83d529`；
  - patch 0027；
  - manifest pin plain `git am` **27/27**，开发树/replay tree 均为
    `52edceaad2ed670296ec9a5d2a39c738b5425c56`。

### 最终自审与边界

- QEMU/gem5 的成功退休、fault 不计数、arm/zero/nonzero/periodic、
  pending/W0C/private mask 路径逐项对称检查通过；`git diff --check` 通过。
- gem5 持久证据绑定仓库当前 FullSystem 配置
  `DADAOAtomicSimpleCPU`。本任务未宣称 Minor/O3 的 cycle/timer hook。
- counters1-7、increment 模式、真实 SBI handler、完整 SBI/HBI、Linux
  paging/多 hart 均仍为 non-claim；未修改 KL-137a/KL-139a 或
  `gcc-torture-results.json`。

## 独立 review FAIL 与 follow-up（2026-07-28，当前最终有效）

**状态**：PASS；follow-up 已通过新的独立 reviewer。本节取代上方旧
PASS 的实现/提交/证据数值。

### 首次独立 review：FAIL

独立 reviewer 在标准 6 场景连续 10 轮、全部 K1 回归、E2E、差分和
plain-`git am` 重放均通过的前提下，仍找到以下问题，因此拒绝接受旧
PASS：

1. **阻塞：私有 pending 未重锁存共有 TIMER。** 冻结契约
   `contracts/isa/spec.md` §8.5.2 要求，只要
   `cfx_timer_pending.bit0` 仍为 1，软件即使先 W0C 清掉共有
   `cfx_common_pending[cfx_timer].bit10`，硬件也必须在下一指令边界
   重新 OR 回 TIMER。旧 QEMU/gem5 仅在“到期瞬间”置共有位；reviewer
   的判别 probe 预期 138，两端均返回 161，属于共同偏离规范而非两端
   一致即可接受。
2. **退休边缘：QEMU `trap SYS_exit/SYS_exit_group` 少计一次。**
   terminal syscall 在走到 recognized-trap 的通用退休 hook 前直接
   调用宿主 `exit()`；gem5 对应 trap 返回 `NoFault` 后会进入
   `countInst()`。进程退出后 cycle 无法由 guest 回读，但代码路径与
   “所有成功退休指令都计数”的契约不对称。
3. **记录不一致。** gem5 0027 和 QEMU 0033 的提交说明仍描述已废弃的
   pre-fetch/pre-execute 模型，runner 还把 timer 误称为
   edge-triggered；roadmap 又把 KL-137a 错写成 real UART，而其合同
   实际只允许合成外部中断源 K1_EXT0。

### Follow-up 修复

- QEMU `dadao_cfx_async_scan()` 与 gem5 `ISA::cfxAsyncScan()` 在 cause
  选择前检查私有 timer pending bit0，并无条件重新 OR 共有 TIMER
  bit10。重锁存不受 `ctrl.enable`、`cfx_timer_mask` 或三级通用 mask
  影响；mask 只决定可否递交，私有 W0C 才解除源断言。
- 新增第 7 个持久双端 guest 场景 `relatch`：
  1. one-shot 到期且私有 mask 保持复位全 1；
  2. 保留私有 bit0，仅清共有 bit10，下一边界必须读回共有 bit10；
  3. 再清私有、再清共有，下一边界必须保持 0。
  该场景 pass code 为 **138**，旧实现判别性失败为 161。
- QEMU terminal `SYS_exit/SYS_exit_group` 分支在宿主 shutdown/exit 前
  显式调用一次 `dadao_cfx_hart_retire()`；底部通用退休路径不可达，
  因而成功 terminal trap 恰好计一次。退出后不可回读 cycle，证据由
  分支代码路径审计以及 E2E 中手写 `SYS_exit` 与真实 musl
  `exit()/_Exit()/SYS_exit_group` 回归共同提供。
- QEMU 0033 的提交说明现明确记录它只是初始 scaffolding/boundary
  阶段，紧随的 0034 作为同一验收单元取代该模型；0034、gem5 0027、
  runner、两组件 README 与 roadmap 均统一为 successful retirement、
  precise-fault exclusion、private-to-common level relatch。KL-137a 仅称
  “合成外部中断源 K1_EXT0”，不再声称 real UART。

### Follow-up 验证

- QEMU `ninja -C build qemu-system-dadao`：PASS；仅保留既有
  `-Wmissing-prototypes` warning。
- gem5 `scons build/DADAO/gem5.opt -j4`：PASS；缺少 png/HDF5/protoc/
  capstone 的宿主可选依赖 warning 与本任务无关。
- KL-133a 最终 7 场景：
  `cycle-lo=133 retire-fault=42 one-shot=134 zero=135 periodic=136
  mask=137 relatch=138`，QEMU/gem5 连续 **10/10** 轮稳定通过。
- 既有 K1 全回归通过：
  KL-113a/117a/120a/122a/124a/125a/126a/127a/129a/131a；其中
  KL-127a 为 30 fault + 10 A/D，KL-129a 为 13/13，KL-131a 为
  131/131 与 132/132。
- E2E：**81/81**；其中 `syscall_hello.test` 覆盖手写 SYS_exit，
  `musl_e2e_exit.test` 覆盖真实 musl SYS_exit_group，两端均保持
  退出码 42。
- differential：
  `AGREE(3-way)=200, gem5-SKIP=2, DIVERGE=0`；
  `AGREE(4-way)=200, Sail-SKIP=2, SAIL-DIVERGE=0`。
- manifest PASS；issues `Open=24 Closed=43 Total=67` PASS；ISA/ABI wiki
  refs PASS（ISA 3 条既有 UNPARSEABLE warning）；wiki drift 3/3 PASS。
- 根仓、QEMU、gem5 三仓 `diff --check` 均 PASS；未触碰 KL-129b、
  KL-137a、KL-139a task MD 或 `gcc-torture-results.json`。

### Follow-up 提交、patch-id 与 bare-pin replay

- QEMU：
  - 0033 初始 scaffolding：
    `be6070f4b5b509e1ebecad0ce2fa15c420b07cad`，
    stable patch-id `038c2aa24ea24560f1e1ac14d1f4aa33effc3c0e`；
  - 0034 最终验收/follow-up：
    `c77df0ef7736e0a377ce6b86e626862132c3580b`，
    stable patch-id `d29a16ebbf904e9309f7e499123304c68c2bccc2`；
  - manifest pin plain `git am` **34/34**，开发树/replay tree 均为
    `a18ebc5f60933c4e2c74d9d1390585010c39efd9`。
- gem5：
  - 0027 最终 commit：
    `ce721cefb0b9af887bf6e5d3f41dcd8b5f57c935`，
    stable patch-id `6c7c01e1ed6ccf42e5406c6e9d56b2379cf23ff9`；
  - manifest pin plain `git am` **27/27**，开发树/replay tree 均为
    `94c3a31db1f87aa87120077796c113bc8c9fa21b`。

gem5 当前证据仍只绑定 FullSystem `DADAOAtomicSimpleCPU`；Minor/O3、
counters1-7、increment 模式、真实设备、完整 SBI/HBI、Linux paging 与
多 hart 均不在 KL-133a 声明范围内。

### 第二轮独立 subagent review

**结论：PASS，无阻塞项。**

- 独立确认 QEMU/gem5 都在 eligibility 选择前从私有 timer pending
  重锁存共有 TIMER，且该反射不受 enable、私有 mask 或三级通用 mask
  影响；`relatch=138` 的“先清共有仍恢复、再清私有后不恢复”两阶段
  ACK 探针具有真实判别性，连续 10/10 双端通过。
- 独立逐路径审计 QEMU 普通指令、精确 fault、recognized trap、
  cfx2rc dispatch、halt、terminal `SYS_exit/SYS_exit_group`，未发现
  漏计或双计；shutdown latch/EXCP_EXIT 未发现副作用。
- gem5 的默认 no-op `BaseISA` hook 与 `BaseSimpleCPU::countInst()`
  位置通过复核；证据范围准确限定为 FullSystem
  `DADAOAtomicSimpleCPU`。
- 独立重跑 KL-113a/117a/120a/122a/124a/125a/126a/127a/129a/131a、
  E2E 81/81、三/四方差分 200 项零分歧，并复核 manifest/issues/wiki/
  diff checks 全部通过。
- 独立从裸 pin 重放 QEMU 34/34、gem5 27/27，tree hash 与开发树一致；
  patch-id、提交说明、README、roadmap 与本任务最终记录一致。KL-137a
  只称合成 `K1_EXT0`，未声称真实 UART。
- reviewer 保留的 non-claim 与本任务一致：Minor/O3、counters1-7、
  increment 模式、真实设备、Linux paging、多 hart。
