# KL-120a：通用 CFX 寄存器载体 + 候选E嵌套返回修复（QEMU + gem5）

**执行环境**：远端 Codex（本仓库），QEMU（`.work/source/qemu`）+ gem5
（`~/DADAO-gem5`）双后端合并一个任务（按架构师/用户 2026-07-26 讨论
确定的"同阶段QEMU+gem5合并"原则）

## 背景

`KL-118a`（调研）把 K1 收尾项拆成 21 个增量任务；`KL-119a`（契约冻结）
已经把候选A-D 落进 `contracts/isa/spec.md §8.5.1-8.5.4`，候选E（嵌套
cfx 返回时 `inner_cfx_code` 恢复）已由用户确认采用 E1（`§8.5.5`，
`docs/wiki-deviations.md` #9）。本任务是 KL-118a 建议序列里的
KL-120a+121a 合并版——是后续 PTW/TLB/异步分派所有任务的共同前置。

**当前已知现状**（架构师已核实）：
- `cfx2rc`（写）已实现（`KL-110a`/`KL-112a`/`KL-113a`），`cfx2rd`
  （读）在 QEMU/gem5 都**完全没有指令实现**（`insn.decode` 里没有
  对应 pattern，`decoder.cc` 里也没有对应类）。
- QEMU `cfx_power_frame`（`cpu.h`）/`cfx_smon_frame` 只实现了 O1/O2/O3
  需要的窄字段（3-5个），没有通用的"任意 cfx 都能读写自己的 cg4/cg5"
  机制。gem5 `CfxPowerFrame`/`CfxSmonFrame`（`isa.hh`）同构。
- `contracts/isa/spec.md §8.5.1` 冻结的 common pending 寄存器
  `(cg,rc)=(4,7)` 目前完全没有存储。
- `contracts/isa/spec.md §8.5.5` 冻结的 `excp_prev_cfx_code`
  `(cg,rc)=(5,5)` 目前完全没有存储，`escape`/trap-entry 都不碰它。

## 目标

1. **实现 `cfx2rd`**（QEMU+gem5）：与已实现的 `cfx2rc` 完全对称的读
   指令（`crrr` 格式，读 `cfx_<cfxname>_cghb_rchc` 写入 `rdhd`）。
   覆盖范围与当前 `cfx2rc` 已支持的 `(cg,rc)` 组合一致（`cg_reg_deleg`/
   `cfx_power`/`cfx_smon` 的 cg5 帧/`escape_cfx_mask`/新的
   `excp_prev_cfx_code`/新的 common pending），reserved/未支持组合
   静默返回0（不是本任务范围的 CFXREG 通用化——只覆盖已有存储的
   组合，其余组合的 CFXREG 判定留给后续任务）。
2. **实现候选E（`excp_prev_cfx_code`，`contracts/isa/spec.md §8.5.5`）**：
   - `cfx_power_frame`/`cfx_smon_frame`（QEMU `cpu.h`；gem5 `isa.hh`
     的 `CfxPowerFrame`/`CfxSmonFrame`）各新增一个字段。
   - trap 真实进入流程（目前只有 `dadao_cfx_smon_trap_enter()`/gem5
     `TrapInst` 的对应逻辑）在步骤7"保存现场"时，除了
     `prev_run_mode`/`prev_cfx_mask`，一并保存进入前的 `inner_cfx_code`
     到这个新字段。
   - `helper_escape`/gem5 `EscapeInst`：自我 escape
     （`cfxcode==inner_cfx_code`）时，除了恢复 mode/mask/PC，也从这个
     字段恢复 `inner_cfx_code`。
   - `cfx2rc`/`cfx2rd` 新增 `(cg,rc)=(5,5)` 的读写支持。
3. **实现 common pending 寄存器（`contracts/isa/spec.md §8.5.1`）**：
   新增 `(cg,rc)=(4,7)` 的存储（每个 cfx 一份，64-bit，reset 0，
   RW/W0C）。本任务**只做存储和 `cfx2rc`/`cfx2rd` 读写支持**，不接
   任何真实中断源（timer/UART/PTW/TLB 都是后续任务的范围）——这个
   寄存器现在应该处于"能读写、但永远不会被硬件自动置位"的状态。
4. **硬性回归要求（不可省略）**：改动完成后必须**重新独立跑一遍**
   现有 O1（`KL-110a`）/O2（`KL-112a`）/O3（`KL-116a`/`KL-117a`）的
   全部探针（QEMU+gem5 各自的），确认零回归——`contracts/isa/spec.md
   §8.5.5` 已经把这条写成前置条件："KL-120a must re-verify O1/O2/O3's
   existing probes with zero regression before this section may say
   nested CFX return is closed"。这不是"顺便测一下"，是本任务能否
   声称候选E已经落地的必要条件。

## 约束

- **只做上面4项**，不要顺带实现候选A 的一般访问控制、O2 设计2
  （`cfx2rc_cfx_mask` 跨cfx检查，已知与 HBI §3 矛盾）、timer/TLB/PTW/
  外部中断的任何真实设备逻辑（那些是后续任务）。
- **不要实现"escape 一次跳过多个 cfx"的 shortcut**——`contracts/isa/
  spec.md §8.5.5` 明确这是候选E 范围之外的独立问题，K1 non-claim。
- 状态转换逻辑集中在 QEMU `helper_cfx2rc`/`helper_escape`/
  `dadao_cfx_smon_trap_enter()`（未来可能需要提升成通用函数，但本任务
  不强制要求泛化成"任意 cfx 的通用 trap-entry"——只要 `cfx_power`/
  `cfx_smon` 两个现有帧都正确处理 `excp_prev_cfx_code` 即可，其余
  cfx 目前没有真实 trap-entry 路径，不需要处理）；gem5 对应
  `CFX2RCInst`/`EscapeInst`/`TrapInst`。
- 完整 QEMU + gem5 patch-series bare-pin replay（tree-hash 比对）是
  硬性验收项。
- 完成后写「完成区」+ 自审记录；如果你自己内部开 reviewer subagent
  复核，继续沿用（`KL-118a`/`KL-119a` 都用了这个方法，效果不错）。

## 验收

- `cfx2rd`（QEMU+gem5）能正确读回 `cfx2rc` 已经支持的每一种
  `(cg,rc)` 组合（含新增的 `(5,5)`/`(4,7)`），round-trip 验证
  （写入→读回→比对）。
- 候选E 的往返验证：构造一个真实的 A→B 单层嵌套场景（复用/改造
  O3 的 `trap cfx_smon`→`escape cfx_smon` 探针，验证 `escape` 后
  `inner_cfx_code` 确实恢复到进入前的值，而不是停留在 `smon`——这是
  KL-119a 报告里指出的既有潜伏 bug，现在要能证明它被修复了）。
- **O1/O2/O3 全部既有探针**（`gen_kl110a_o1_probe.py`/
  `gen_kl112a_o2_probes.py`/`gen_kl116a_o3_probe.py` 及 gem5 对应
  runner）重新独立跑一遍，退出码/trace 与改动前逐一致。
- common pending `(cg,rc)=(4,7)` 读写正常，reset 为0，W0C 语义正确。
- 全量 lit E2E、`tools/run_differential.py`、`manifest_check.py`、
  `check_issues.py` 无回归。
- QEMU + gem5 patch-series bare-pin replay，tree hash 与各自开发树
  一致。

## 参考指针

- `docs/reviews/kernel-mmu-interrupt-recon-20260726.md`（KL-118a，
  §5 KL-120a/121a 原始范围描述）
- `docs/wiki-deviations.md` 第9条（候选E 完整方案比较+用户确认记录）
- `contracts/isa/spec.md §8.5.1`（common pending）、`§8.5.5`
  （候选E，含"必须重新验证O1/O2/O3零回归"这条硬性要求）
- `code-agent/tasks/KL-110a-*.md`/`KL-112a-*.md`/`KL-116a-*.md`/
  `KL-117a-*.md` 完成区（`cfx_power_frame`/`cfx_smon_frame` 现有实现、
  探针脚本位置、carrier-point 设计）
- `~/DADAO-wiki/DADAO-12-SEE-主管系统运行环境.md`（cg4/cg5 表、
  `cfx2rd`/`cfx2rc` 语义）、`SimRISC-04-系统类指令.md`（`cfx2rd`
  语法，与已实现的 `cfx2rc` 对称）

## 完成区（2026-07-26）

**状态**：PASS。目标1-4全部完成；QEMU/gem5 双后端实现、独立
O1/O2/O3 重跑、完整回归和两套 bare-pin patch-series replay 均通过。

### 实现

- **`cfx2rd`**：QEMU 新增 `0x72` decodetree/TCG helper，gem5 新增
  `CFX2RDInst`。两端读取同一 storage-backed 子集：`cg3/rc12`
  delegation、`cg0-3/rc7` escape mask、`cfx_smon cg2/rc10` vector、
  power/smon cg5 frame、common pending 和 E1 rc5。未支持/保留组合返回
  0；目标 `rd0` 精确触发 ILLI。`tools/opcodes.yaml` 同步登记 `0x72`
  及 `rd != rd0`。
- **common pending**：每个 cfxcode 一份 `cg4/rc7` 64-bit latch，reset
  0，读时按 K1 cause table 过滤，写为 W0C（0清除、1保留、不能由软件
  置位）。KL-120a 不连接 timer/UART/PTW/TLB 等真实来源。为避免
  reset-zero 产生假绿，两端只增加默认关闭的 test-only raw seed
  配置；guest 看不到新来源或新 ABI。
- **E1 nested return**：power/smon frame 新增 `prev_cfx_code`；
  `trap cfx_smon` 在覆盖 `inner_cfx_code` 前保存 caller；self-escape
  恢复 mode/mask/cfx-code/PC。power reset 默认 carrier 为 power，
  保持既有 O1 handoff；smon reset 为0。gem5 `copyRegsFrom()` 同步
  复制新增 frame/pending 状态；QEMU target 当前没有可登记的
  migration VMState，本任务不虚构 checkpoint 声明。
- **探针**：新增
  `tests/scripts/run_kl120a_cfx_carrier_probes.py`，同一 raw stream
  在 QEMU bare metal 与 gem5 SE 执行。覆盖所有已存储 family、
  smon HW-only rc2/rc4 读且写入无效、reserved read-zero、`rd0`
  ILLI、7组非零 raw pending valid-mask/W0C，以及
  power→smon→power 后第二次 power self-escape 的判别路径。
  QEMU pending 探针在 `halt` 前用零位移 taken branch 隔离 TB，避免
  QEMU 消费异步 shutdown 请求时重入当前 TB 而重复执行破坏性的 W0C；
  这只影响测试载体，不改变目标语义。

### 验证结果

- QEMU：`ninja -C build qemu-system-dadao` PASS。
- gem5：`scons build/DADAO/gem5.opt -j4` PASS。
- KL-120a 双后端探针：`register=44/44`、`rd0 ILLI=130/130`、
  `pending profiles=7x45/45`、`nested=43/43`。
- 独立 O1/O2/O3 重跑：
  - QEMU：O1/O2-regression/design1/design3/O3-off/O3-on =
    `42/42/130/134/153/43`。
  - gem5：KL-113a O1/design1/design3/O1-regression =
    `42/130/134/42`；KL-117a O3 off/on = `153/43`，process rc 与
    唯一 `SIM_END` guest code 一致。
- `.work/build/llvm/bin/llvm-lit -sv tests/lit/E2E/`：81/81 PASS。
- `python3 tools/run_differential.py`：
  `AGREE(3-way)=200`、gem5-SKIP=2、DIVERGE=0；
  `AGREE(4-way)=200`、Sail-SKIP=2、SAIL-DIVERGE=0。
- `check_wiki_refs.py --profile isa/abi`、`validate_encoding.py`
  （92 records）、`manifest_check.py`、`check_issues.py`
  （Open 24 / Closed 43 / Total 67）、`check_wiki_drift.py` 均 PASS。
  `check_qfc_coverage.py` 仍为既有 `0 only in yaml / 24 only in wiki`；
  `check_legality_matrix.py` 为 `QEMU-BUG=0 / opcodes漏=0`，新增
  `cfx2rd rd0` cell 正确通过，向量缺口仍是非阻塞清单。

### 提交、patch series 与重放

- QEMU commit：
  `dafb3d7c06d81d174ea540130cabdb8dfe4b4174`；
  patch `components/qemu/patches/0027-target-dadao-add-cfx-carrier-and-nested-return-KL-12.patch`；
  commit/patch stable patch-id 均为
  `63a53a51938998104d7a592c7260c9a92eb295ec`。
  从 manifest pin `385b0a7d9785c8f3ac7b116d7f31d61502b55183`
  plain `git am` 27/27 PASS；开发树与 replay tree 均为
  `0c8748af15965e3a0845fd1c78821ec43826a7bb`。
- gem5 commit：
  `5012ede5d2a932e02914c18773ea7e6f5bc3debd`；
  patch `components/gem5/patches/0020-arch-dadao-add-cfx-carrier-and-nested-return-KL-120a.patch`；
  commit/patch stable patch-id 均为
  `fc0b1523ab1e9d647f21410df1ea5f4f9c6b24c2`。
  从 manifest pin `c8222cc67a399bfc01e8658dd14b30d5bfd634f9`
  plain `git am` 20/20 PASS；开发树与 replay tree 均为
  `b8197a05923f221b3c00de028fe591c3a07bee9b`。
- 两个 KL-120a 临时 replay worktree 已清理。根仓库既有未跟踪
  `gcc-torture-results.json` 未纳入任务。

### 自审记录

结论：**PASS，可以进入同一 reviewer 的 delta review**。

- 逐项比对 QEMU/gem5：valid mask、W0C、frame truncation、HW-only
  rc2/rc4、`rd0` ILLI、trap-save 与 self-escape restore 对称。
- 动态 pending 不是 reset-zero 假绿：七种 profile 均以 raw all-ones
  注入，覆盖单 bit、多 bit、无 valid cause 三类；先保留后清零。
- nested probe 先验证真实 trap 写出的 rc2/rc4/rc5，再执行第二个
  power self-escape；旧的 stuck-at-smon 行为会在第二次 escape 触发
  ILLI，不能误报成功。
- 范围没有扩展到真实 interrupt source、dispatch、候选A、O2设计2、
  multi-frame shortcut、MMU/PTW/TLB 或 kernel。

### 独立审阅记录

首轮 reviewer 结论为 **NEEDS CHANGES**，核心实现语义本身无阻塞，
提出四项验收加固：

1. 当时 patch series/完成区尚未生成；
2. common pending 只测 reset-zero，存在假绿；
3. 应覆盖全部 `cg0-3` mask、smon HW-only 写保护，并严格校验 gem5
   唯一 `SIM_END` 与 process rc；
4. `copy` 声明应限定为 gem5 `ThreadContext`，不能暗示 QEMU migration。

现已逐项处理：完成 27/27 与 20/20 replay；增加七组动态 raw-seed
pending profile；mask 四组、HW-only rc2/rc4 与 gem5 双重退出码均纳入
探针；文档明确 gem5 copy/QEMU 无 VMState 的边界。最终 delta review
结论为 **PASS，无阻塞 findings**。Reviewer 独立重跑得到
`register=44/44; rd0 ILLI=130/130; pending profiles=7x45/45;
nested=43/43`，并复核 stable patch-id、27/27 与 20/20 series/tree、
encoding/manifest/issues/wiki refs/drift 及三棵树 `diff --check`；
仅见3条既有 wiki 引用解析 warning，非本任务引入且不阻塞。审阅过程
只读，未修改文件。
