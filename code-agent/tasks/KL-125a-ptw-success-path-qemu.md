# KL-125a：PTW（页表步进）成功路径 in QEMU

**执行环境**：远端 Codex（本仓库），QEMU 源码改动
（`.work/source/qemu`）

## 背景

`KL-118a`（调研）已经把 MMU/TLB SBI 式操作的完整契约梳理清楚
（`docs/reviews/kernel-mmu-interrupt-recon-20260726.md` §1）。本任务
实现其中的**成功路径**（VA→PA 转换本身），不实现故障处理
（`cfx_ptw`/`cfx_tlb` 异常入口是 `KL-127a` 的范围）、不实现 TLB
缓存（当前 QEMU **完全没有** `cfx_tlb` 的任何存储/控制寄存器，
本任务的 walk 天然是"每次访问都走完整硬件 walk"，不需要额外做
"关闭 TLB"这个动作——TLB 缓存本身是 `KL-129a` 的范围）。

**当前状态**：`dadao_cpu_tlb_fill()`（`target/dadao/cpu.c:452-469`）
目前把 VA 恒等映射为 PA，不做任何真实转换。`CPUArchState` 完全
没有 PTBR/PTHI/PAHI/PTBR-enable/mode-perm 的存储。

## 目标

实现 wiki 定义的完整 VA→PA 转换算法（成功路径，**不含**故障分支）：

1. **`cfx_ptw` 专有寄存器存储**（wiki `DADAO-12-SEE-主管系统运行
   环境.md` 第425-438行）：
   - `cfx_ptw_user/jail/supv/hypv_perm`（cg8/rc0-3，PTBR 权限位图）
   - `cfx_ptw_ptbr_enable`（cg8/rc8，PTBR 使能位图）
   - `cfx_ptw_ptbr[0..63]`（cg9/rc0-63，一级页表基址高48位）
   - `cfx_ptw_pthi[0..63]`（cg10/rc0-63，页表结构物理地址高16位）
   - `cfx_ptw_pahi[0..63]`（cg11/rc0-63，最终数据物理地址高16位）
   通过 `cfx2rc`/`cfx2rd` 读写（复用/扩展 `KL-120a`/`KL-122a` 已经
   通用化的寄存器载体机制）。
2. **超页地址转换**（wiki 第79-117行，§2.2.1）：`VA[47:42]`→PTBR
   index，`VA[41:29]`→L1 index（8192项一级页表，每项8字节），
   `VA[28:00]`→页内偏移（512MiB）。第一步"访问PTBR"（第89-94行，
   含 mode-perm 检查和 ptbr-enable 检查——**enable=0 时不转换，直接
   用48位地址访问核内资源**，这条本任务也要实现，因为它决定"什么
   时候根本不触发 PTW"）；第三步"页表步进"读 L1 PTE、检查
   Superpage/Present/SPF 位（第103-110行，**只实现"位为1/满足"的
   成功分支，不满足时的故障分支留给 `KL-127a`**）；第四步"形成
   最终物理地址"（第112-117行，`pahi`拼高16位+L1 PPN 高19位+页内
   偏移）。
3. **普通页地址转换**（wiki 第119-163行，§2.2.2）：`VA[47:42]`→PTBR
   index，`VA[41:29]`→L1 index，`VA[28:16]`→L2 index（8192项二级
   页表），`VA[15:00]`→页内偏移（64KiB）。第三步"页表步进"里 L1
   PTE 的 Superpage 位为0 时走二级页表分支（读 L2 PTE，用 `pthi`
   拼高16位+L1 PPN 中间32位+L2 index），检查 Present/GPF 位（第
   144-156行，同样只实现成功分支）；第四步用 `pahi`+L2 PPN+页内
   偏移拼最终物理地址（第158-163行）。
4. **一级/二级页表项格式**：wiki 第165行起有完整位域定义（继续读
   wiki 原文，本任务文件不展开——PPN/Present/Superpage/SPF/GPF/
   R/W/X/A/D 等字段的精确位置需要你自己核对 wiki 原文，不要凭
   记忆或猜测位置）。
5. **取指/读/写权限检查**：wiki 明确要求区分 X（取指）/R（读）/
   W（写）三种访问类型分别检查页表项的权限位——本任务的成功路径
   验收需要覆盖这三种访问类型分别转换成功的场景。

## 约束

- **只实现成功路径**——PTBR 权限不符、PTBR 未使能、Present=0、
  SPF/GPF=0、R/W/X 权限不符等全部故障情况，本任务**不处理**（不
  产生任何异常，这些场景不在本任务验收范围内，行为未定义也没关系，
  `KL-127a` 会补上）。
- **不实现 A/D 位的硬件回写**——wiki 要求 PTE 的 A/D 位由硬件同时
  更新 TLB 和主存 PTE（原子 read-modify-write），这是 `KL-127a`
  （PTW fault/A-D，与故障处理放在一起）的范围，本任务不做。
- **不实现 TLB**——当前没有 TLB 存储，每次访问都走完整 walk，这是
  预期行为，不需要额外代码去"跳过 TLB"。
- **不要产出`cfx_ptw` 的任何异常路由代码**——本任务只做地址转换
  本身，不接入 `KL-122a` 的通用精确异常入口 carrier（那是 `KL-127a`
  的范围）。
- 状态转换/地址转换逻辑集中在一个新的 helper 函数（建议类似
  `dadao_ptw_translate()`），供 `dadao_cpu_tlb_fill()` 在 PTBR
  使能时调用；不要把地址转换算法直接写进 `tlb_fill` 函数体
  （保持既有 carrier-point 惯例：复杂状态机逻辑单独成一个可测试
  的函数）。
- 完整 patch-series bare-pin replay（tree-hash 比对）是硬性验收项。
- 完成后写「完成区」+ 自审记录；继续沿用"自己开 reviewer subagent
  复核"的方法。
- gem5 侧移植是独立后续任务（`KL-126a`），本任务不碰 gem5。

## 验收

- 静态预建页表（探针脚本手工构造 L1/L2 页表项）分别验证：
  - 超页 VA→PA 转换正确（取指/读/写各一个场景）。
  - 普通页 VA→PA 转换正确（取指/读/写各一个场景，含二级页表
    查找）。
  - PTBR 未使能时（enable=0）直接用48位地址访问核内资源（即
    "不转换"这条路径本身也要验证，不只是"转换成功"）。
- `pthi`（页表结构物理地址）与 `pahi`（最终数据物理地址）没有被
  混用——构造一个两者取不同值的场景，验证页表本身的读取地址用
  `pthi` 拼接、最终数据地址用 `pahi` 拼接。
- 现有全部探针（O1/O2/O3/`KL-120a`/`KL-122a`）零回归。
- 全量 lit E2E、`tools/run_differential.py`、`manifest_check.py`、
  `check_issues.py` 无回归。
- patch-series bare-pin replay，tree hash 与开发树一致。

## 参考指针

- `docs/reviews/kernel-mmu-interrupt-recon-20260726.md`（KL-118a，
  §1.1/§1.2 MMU/PTW 正式契约、§5 KL-125a 原始范围描述）
- `~/DADAO-wiki/DADAO-12-SEE-主管系统运行环境.md` 第54-219行（完整
  地址空间/VA→PA转换算法，超页+普通页两条路径+页表项格式）、
  第425-461行（`cfx_ptw` 专有寄存器表+异常原因表）
- `code-agent/tasks/KL-122a-*.md` 完成区（通用精确异常入口 carrier，
  本任务不使用，但寄存器读写载体机制可以复用）
- `.work/source/qemu/target/dadao/cpu.c:452-469`（现有
  `dadao_cpu_tlb_fill()`，本任务要替换/扩展的位置）

## 完成区（2026-07-26）

### 实现

- `CPUArchState` 新增完整 cfx_ptw private storage：
  `cfx_ptw_perm[4]`、`cfx_ptw_ptbr_enable`、`cfx_ptw_ptbr[64]`、
  `cfx_ptw_pthi[64]`、`cfx_ptw_pahi[64]`。reset 值按 wiki：
  user/jail perm=0、supv/hypv perm=全1、enable/PTBR/PTHI/PAHI=0。
- `helper_cfx2rc/cfx2rd` 接入 cfx_ptw 的 cg8/9/10/11 register map；
  PTBR 写入保留低48位（代表 PA[63:16]），PTHI/PAHI 截为16位。
  translation-control 写入后刷新 QEMU soft TLB，避免配置切换沿用旧
  host translation；这不是实现架构 `cfx_tlb` cache。
- `dadao_ptw_translate()` 集中实现成功路径：
  1. 按当前 run mode 检查 PTBR permission；
  2. enable=0 时返回 48-bit identity + RWX；
  3. enable=1 时用 PTBR + `VA[41:29]*8` 读取 big-endian L1 PTE；
  4. SP=1 时检查 Present/SPF/请求的 R/W/X，并以
     `PAHI | L1.PPN[47:29] | VA[28:0]` 形成超页 PA；
  5. SP=0 时以 `PTHI | L1.PPN | VA[28:16]*8` 读取 big-endian L2
     PTE，检查 Present/GPF/R/W/X，并以
     `PAHI | L2.PPN | VA[15:0]` 形成普通页 PA。
  `dadao_cpu_tlb_fill()` 只负责调用 helper 并安装 4 KiB QEMU
  soft-TLB host translation。
- 按任务范围，任何失败检查只返回“不产生成功 translation”；没有接入
  cfx_ptw precise fault carrier，没有 A/D 回写，也没有架构 TLB。
- target physical-address declaration 从48位修正为64位，与 wiki 的
  `PA[63:0]` 和 PAHI 契约一致。
- DADAO M1 test machine 新增两个 64 KiB 高物理 alias：
  L2 structure `0x0002_0000_8400_0000` → backing `0x80100000`，
  final leaf `0x0001_0000_8020_0000` → backing `0x80300000`。
  它们只为判别性测试提供可达的 64-bit 地址，且都不映射到数值对应的
  低地址；因此把 PTHI=2/PAHI=1 互换或忽略任一高16位都会失败。
- 新增 `tests/scripts/run_kl125a_ptw_success_probes.py`：ROM 负责配置
  cfx_ptw，`-kernel` raw RAM image 提供静态 L1/L2 PTE 和 leaf
  code/data；不依赖 host 页表或临时修改 QEMU。

### 判别性验证

专项脚本 8/8 PASS，均为 QEMU process rc=42：

- private register storage/readback：四种 mode perm、enable、PTBR 48-bit、
  PTHI/PAHI 16-bit truncation；
- PTBR disabled：即使 PTBR[0] 写入无效地址，`0x80001000` 仍按48位
  identity 完成 store/readback；
- superpage X/R/W：使用 L1 index=3、SPF fragment=1，VA
  `0x0000040064020000` 的 leaf PTE 位于 `0x80010018`，分别以
  仅X/仅R/仅W 映射到 PA `0x84020000`；
- normal-page X/R/W：使用 L1 index=5、L2 index=7、GPF fragment=3，
  VA `0x00000800a0076100` 的 L2 PTE 读取地址均为
  `0x0002000084000038`（PTHI=2），最终 PA 均为
  `0x0001000080206100`（PAHI=1）。三种 PTE 同样只开启本次所需
  X/R/W 单一权限，避免“统一给RWX”假绿；runner 还精确断言
  `access=2/0/1` 与 `prot=4/1/2`。

日志位于 `.work/evidence/kl125a-ptw/`，`-d mmu` trace 同时记录
VA、leaf PTE physical address、L1 PTE、最终 PA、access type 和
installed protection。

### 回归

- `ninja -C build qemu-system-dadao`：PASS（仅既有
  `cpu_get_tb_cpu_state`/`dadao_cpu_has_work` prototype warnings）。
- QEMU O1/O2-regression/design1/design3/O3-off/O3-on：
  `42/42/130/134/153/43`。
- KL-120a：`register=44/44; rd0 ILLI=130/130;
  pending profiles=7x45/45; nested=43/43`。
- KL-122a generic cfx_ptw frame/vector/escape：`46/46`。
- `.work/build/llvm/bin/llvm-lit -sv tests/lit/E2E/`：81/81 PASS。
- `python3 tools/run_differential.py`：
  `AGREE(3-way)=200`、gem5-SKIP=2、DIVERGE=0；
  `AGREE(4-way)=200`、Sail-SKIP=2、SAIL-DIVERGE=0。
- `manifest_check.py`、`check_issues.py`（Open 24 / Closed 43 /
  Total 67）和根/QEMU `git diff --check` 均 PASS。

### 提交、patch series 与重放

- QEMU commit：
  `3d0c68e3d00ed57a9df4dbfdadb446bb5b7a2bc9`；
  patch
  `components/qemu/patches/0029-target-dadao-implement-PTW-success-path-KL-125a.patch`。
- commit/patch stable patch-id 均为
  `978d1a50a8490579e2ff049acce208ac1414d9b1`。
- 从 manifest pin
  `385b0a7d9785c8f3ac7b116d7f31d61502b55183` plain `git am`
  29/29 PASS；replay HEAD
  `90fe12b2ec1de2e46cccdb45384c246eab6beb1f`，replay/development
  tree 均为 `ca28955aeaf57fb7d78b619b5d88c673395e9b9f`。临时
  replay worktree 已清理。

### 自审记录

结论：**PASS，可以进入独立 subagent review**。

- 位域逐项从 wiki §2.2.1-2.2.4 实现：L1/L2 各8192项、PTE 8字节、
  SP/P/PPN/R/W/X、SPF按 `VA[28:26]`、GPF按 `VA[15:13]`；PTE 读取
  显式使用 big-endian API。
- PTBR/PTHI/PAHI 三类地址没有混用；normal probe 的
  PTHI=2 高物理 L2 与 PAHI=1 高物理 leaf 是真实不同的 machine
  mappings，不只是比较日志字符串。
- 每个 X/R/W probe 的 leaf PTE 只给对应单一权限；取指、load、store
  分别进入 `MMU_INST_FETCH/MMU_DATA_LOAD/MMU_DATA_STORE`。
- 没有扩大到 failure exception、A/D、architectural TLB、gem5、
  firmware 或 kernel。

### 独立 subagent 审阅记录

首轮结论为 **NEEDS CHANGES**，核心 walker 实现无错误，指出两项
Medium 证据/声明问题：

1. `TARGET_PHYS_ADDR_SPACE_BITS` 仍为48，且正式 leaf PA 的 PAHI 全为0，
   不足以支撑64位物理地址契约；
2. 所有成功探针的 L1/L2 index 和 SPF/GPF fragment 都为0，trace
   oracle 也未锁定 access/prot，硬编码 entry0/bit0 可能假绿。

修复后 target 声明为64位；machine 使用 PTHI=2/PAHI=1 两个独立高物理
alias；所有 X/R/W 场景改为非零 L1/L2/fragment，并精确检查 leaf PTE
地址、最终 PA、access 和 prot。重新构建、专项8/8、KL-120a/KL-122a、
81/81 E2E、200/0 differential 及29/29 replay 全通过。

同一 reviewer delta review 独立复跑并核对 patch-id/tree 后确认两项
Medium 全关闭，最终 **PASS**。它另指出一项非阻塞 Low：runner
docstring 仍写旧 PTHI/PAHI 数字；已同步改为 PTHI=2/PAHI=1。
审阅过程只读，未修改文件。
