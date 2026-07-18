# Wiki 升级审计 — 13a414d → 9f378f4（首次执行 ADR-0013）

**任务**: WU-001a
**日期**: 2026-07-12
**流程**: ADR-0013 五阶段（Phase 0 探测 → Phase 1 分类 → Phase 2 三桶 triage → Phase 3 A桶再验证 → Phase 4 覆盖&回归 → Phase 5 重锁&记录）
**基线 pin**: `13a414d`（SimRISC 0.4.1）→ 目标 `9f378f4`（origin/master，8 commits ahead）

---

## 结论摘要

- **A 桶（M1 核心语义变更）= 空**。SimRISC-01（数据类/RD 标量）与 SimRISC-02（地址类/RB）在 `13a414d..9f378f4` 全程**零 diff**（命令输出证实见下）；SimRISC-03（浮点）未被触碰。
- **差分回归无回归**：`run_differential.py` = **AGREE(4-way)=200 / DIVERGE=0 / HARNESS=6**，与升级前基线完全一致。
- 8 commits 全部落在 **B 桶（deferred 域：SEE / SBI / HBI / FP）** 与 **C 桶（装饰：格式后缀 / 示例补全 / CSR 名去重 / 全局重命名）**。
- **推进 pin**：`manifests/spec.lock.toml` 的 wiki commit `13a414d` → `9f378f4`（**只改 pin，未改 spec.md 语义、未改任何 impl**）。simrisc_version 仍 0.4.1（未变）。

---

## Phase 0 — delta 探测

```
$ git -c core.quotepath=false diff --stat 13a414d..9f378f4
 DADAO-12-SEE-主管系统运行环境.md   | 121 ++++++-------  (SEE 域)
 DADAO-22-SBI-主管系统二进制接口.md | 114 ++++++-------  (SBI 域)
 DADAO-23-HBI-超管系统二进制接口.md |   2 +-           (HBI 域)
 SimRISC-00-指令系统设计.md         |  16 +---          (概览/编码表)
 SimRISC-04-系统类指令.md           |   2 +-           (系统类指令)
 5 files changed, 126 insertions(+), 129 deletions(-)
```

**关键**：net diff 只触及 5 个文件，**SimRISC-01 / SimRISC-02 / SimRISC-03 均不在其中**。M1 核心标量/地址指令语义文件全程未动。

---

## Phase 1 + 2 — 分类表（域 × M1相关性 × 三桶）

| # | commit | 日期 | 文件 | 摘要 | 域 | 桶 |
|---|--------|------|------|------|----|----|
| 1 | `bc39c7c` | 06-29 | SimRISC-00 | MISC-RF 子表全部浮点指令补格式后缀 `-orrr`/`-orri` | FP | **C**（FP 编码表装饰） |
| 2 | `b3d6c82` | 06-29 | DADAO-12 | cg4 重组：`excp_num` 拆为 `sync_num`+`async_num`，`escape_num` 移至 rc5 | SEE/异常 | **B** |
| 3 | `ea10f5e` | 06-29 | DADAO-12 | CFXMEM 触发条件增加"内部储存块非法访问"，全表描述更新 | SEE/异常 | **B** |
| 4 | `6079ecd` | 06-29 | DADAO-12 | 异常进入/退出伪代码统一、cfxld/cfxst 路由简化、check_nonmaskable 标签、not-sync 计数 | SEE/异常 | **B** |
| 5 | `defdd96` | 06-29 | DADAO-12 | §5 重构 + `FE`→`FPEXCP`、中断模型前移、指令行为/escape 说明整理 | SEE/异常 | **B** |
| 6 | `10929f7` | 06-29 | DADAO-22, SimRISC-04 | `cfx_power_power_ctrl`→`cfx_power_ctrl` CSR 名去重；PTBR/PTHI/PAHI 跳转表 rb→rd 中转（SBI 固件） | SBI + 系统 CSR | **C**（CSR 名去重） + **B**（SBI 固件示例） |
| 7 | `b1a5f7f` | 06-29 | SimRISC-00, DADAO-12, DADAO-22 | ftcls/focls `-orrr`→`-orri`（FP）；**add 补 rd0**（SBI 示例 4 操作数）；popcnt→TODO（SBI）；escape 指代说明（SEE）；ALLOC_PAGE 返回值 0→-1（SBI） | FP/SEE/SBI | **C**（add 示例补全 + FP 后缀） + **B**（popcnt/ALLOC_PAGE/escape） |
| 8 | `9f378f4` | 06-30 | DADAO-12/22/23 | `phymem`→`pmem` 全局重命名 | SEE/SBI/HBI | **C**（全局重命名） |

---

## A 桶结论：空 —— 证据

### 证据 1：SimRISC-01（RD 标量）+ SimRISC-02（RB 地址）全程零 diff

```
$ git diff 13a414d..9f378f4 -- 'SimRISC-01*' 'SimRISC-02*'
(无输出 — 空 diff)

$ git diff --stat 13a414d..9f378f4 -- 'SimRISC-01*' 'SimRISC-02*'
(无输出 — 无文件变更)
```

M1 已用 200 向量 + CodeGen 验证的全部标量整数（加减/移位/乘/除/取模/比较/条件/wyde/常量物化）与地址（load/store/RB 寻址/rd2rb 桥）指令语义**未被任何 commit 触碰**。

### 证据 2：SimRISC-03（浮点）未触碰

```
$ git diff --stat 13a414d..9f378f4 -- 'SimRISC-03*'
(无输出 — 未触碰)
```

### 证据 3：唯一被动的 M1 邻接文件 SimRISC-00 = 纯 FP 编码表

```
$ git diff 13a414d..9f378f4 -- 'SimRISC-00*'
@@ MISC-RF指令编码 @@
-| 000-xxx   | ftcls     | ft2fo     | ... | ftroot     | ftlog        |
+| 000-xxx   | ftcls-orri | ft2fo-orri | ... | ftroot-orri| ftlog-orri  |
-| 010-xxx   | ftadd     | ftsub     | ftmul     | ftdiv     | ...
+| 010-xxx   | ftadd-orrr | ftsub-orrr | ftmul-orrr | ftdiv-orrr | ...
（全部为 ft*/fo* 浮点指令补 -orrr/-orri 格式后缀；无一条整数/地址指令）
```

变更范围 = MISC-RF 浮点子表，全部条目为 `ft*`/`fo*`（浮点），无任何 M1 整数/地址 opcode 布局改动。

### 证据 4：唯一被动的系统指令文件 SimRISC-04 = 系统 CSR 名去重（非 M1 指令）

```
$ git diff 13a414d..9f378f4 -- 'SimRISC-04*'
-cfx2rc  cfx_power_power_ctrl, rd2      ; 写入 cfx_power 的 power_ctrl
+cfx2rc  cfx_power_ctrl, rd2             ; 写入 cfx_power 的 power_ctrl
```

仅一处 CSR 名去重（`cfx_power_power_ctrl`→`cfx_power_ctrl`），系统类 cfx2rc/cfx2rd 示例，非 M1 标量/地址指令语义。

### 证据 5："add 补 rd0" 是示例 4 操作数补全（C 桶装饰），非 add 语义变更

`b1a5f7f` 中所有 `add` 改动均在 **DADAO-22-SBI 固件示例汇编**内，形如：

```
-    add     rd3, rd3, rd16
+    add     rd0, rd3, rd3, rd16          ; cfx_ptw / cfx_pmem 跳转表基址计算
```

DADAO 的 `add` 本就是 **4 操作数**（`add rd_hi, rd_lo, rd_a, rd_b`，rd0 弃高位）。示例此前写成 3 操作数是笔误，补全为规范 4 操作数形式 `add rd0, ...`——**这正是我们 CodeGen 一直生成的形式**。add 指令语义未变（其定义在 SimRISC-01，证据 1 已证零 diff），仅示例书写修正 → **C 桶**。

### 证据 6：M1 助记符全网扫描 — 仅出现在 deferred 域固件示例

对 net diff 加行做 `subu/mulu/divs/ldo/sto/breq/brne/cmps/...` 扫描，命中仅 7 处 `brne`/`breq`，**全部在 `9f378f4` 的 DADAO-22-SBI `phymem`→`pmem` 重命名块内**（`cfx_pmem_*` 派发表的示例分支），是固件示例代码使用分支助记符，**非分支指令语义定义**（定义在 SimRISC-01/02，未动）。

**A 桶 = 空。M1 核心标量/地址指令语义、编码、legality 零变更。**

---

## Phase 4 — 差分回归（回归探测器）

```
$ cd ~/DADAO-0628 && python3 tools/run_differential.py 2>&1 | tail
=== AGREE(3-way)=200  AGREE(interp+QEMU, gem5-SKIP)=0  DIVERGE=0  HARNESS=6  QEMU-SKIP=0 ===
=== SAIL 4th column: AGREE(4-way)=200  Sail-SKIP=0  SAIL-DIVERGE=0 ===
```

**AGREE(4-way)=200 / DIVERGE=0 / HARNESS=6**——与升级前基线逐位一致。因 A 桶空（M1 impl 未改），回归探测器确认新 wiki 未让任何已测语义回归。

**覆盖洞（M1）**：无。本批 commit 未引入任何需新向量覆盖的 M1 语义角落。`b1a5f7f` 的 `popcnt→TODO` 是从 SBI 固件示例移除 `popcnt`（`popcnt` 不在我们的 M1 ISA 内，本就无向量），非 M1 覆盖洞。

---

## B 桶清单（deferred 域变更 — 记入各域未来基线，该域启动时吸收）

> 均不影响当前 M1。启动对应域时须回放这批 delta 做一次历史吸收（ADR-0013 Phase 2·B 桶策略）。

### 异常 / SEE 域（DADAO-12）— commits b3d6c82, ea10f5e, 6079ecd, defdd96, b1a5f7f(escape 指代), 9f378f4(pmem 重命名)
- `excp_num` 拆为 `sync_num` + `async_num`，`escape_num` 移至 rc5（异常号编码模型重构，`b3d6c82`）。
- CFXMEM 触发条件新增"内部储存块非法访问"（`ea10f5e`）。
- 异常进入/退出伪代码统一、cfxld/cfxst 路由简化、check_nonmaskable 标签、not-sync 计数（`6079ecd`）。
- §5 重构：异常码 `FE`→`FPEXCP`、中断模型前移、escape 硬件语义整理（`defdd96`）。
- escape 伪代码 `⟨cfxname⟩` 指代澄清（当前执行 escape 的 cfx = `inner_cfx_code`，`b1a5f7f`）。
- **关联当前 impl 的 open issue**：`RASUF-cold-ret` / 异常路由已在 M1 用双后端 E2E 收口（DL-057b，issue `rasof-rasuf-exit-code-unpinned` closed）；上游这批异常模型重构（sync/async 拆分、FPEXCP 命名）**属异常域未来基线**，M1 当前 RAS/异常收口不受影响。

### SBI 域（DADAO-22）— commits 10929f7, b1a5f7f, 9f378f4
- PTBR/PTHI/PAHI 设置走 rb→rd 中转（`setrd rdX, rbY`，因 cfx2rc 源须为 rd）+ 跳转表实现（`10929f7`）。
- `SBI_PHYMEM_ALLOC_PAGE` 返回值语义：成功返回 PPN（`>=0`），失败 `0`→**`-1`**（`b1a5f7f`）。
- `cfx_phymem_get_pm_count` 的 `popcnt` 实现改为 `; TODO: 遍历位图统计`（`popcnt` 不在 SimRISC ISA，`b1a5f7f`）。
- **SEE/musl 里程碑铺垫**：这批 SBI 接口/固件成型是未来 musl 系统调用落地（ML-001a recon）的上游依赖，见 issues.yaml note。

### HBI 域（DADAO-23）— commit 9f378f4
- `phymem`→`pmem` 重命名波及（1 行）。

### FP 域（SimRISC-00 MISC-RF 表）— commits bc39c7c, b1a5f7f
- 全部浮点指令补 `-orrr`/`-orri` 格式后缀；ftcls/focls 从 `-orrr` 修正为 `-orri`（`b1a5f7f`）。FP 未实现 → 记入 FP 域未来基线。

---

## C 桶清单（装饰 — 记录，无需验证）

- **`add` 示例补全 4 操作数**（`b1a5f7f`，DADAO-22 内 5 处）：`add rd3,rd3,rd16`→`add rd0,rd3,rd3,rd16`，印证 M1 CodeGen 生成形式，add 语义未变。
- **MISC-RF FP 格式后缀**（`bc39c7c`）：浮点子表补 `-orrr`/`-orri`，编码表装饰。
- **CSR 名去重**（`10929f7`，SimRISC-04）：`cfx_power_power_ctrl`→`cfx_power_ctrl`。
- **`phymem`→`pmem` 全局重命名**（`9f378f4`）：跨 DADAO-12/22/23 的标识符重命名，纯装饰。

---

## Phase 5 — 重锁

- `manifests/spec.lock.toml`：`commit` `13a414da...` → `9f378f4`（+ commit 短说明）。
- `simrisc_version` 保持 `0.4.1`（wiki 内版本号未变，M1 核心语义未变）。
- 其它版本字段（aee/see_sbi/hee）未在 wiki 元数据中改动，保持不变。

---

## 自审（强制）

- **每 commit 判定有 git 证据吗？** 有。8 commit 全部经 `git show --stat` / `git diff` 逐文件核对；分类表每行对应 Phase 0 diffstat + 逐 commit stat 输出。
- **A 桶结论有 SimRISC-01/02 diff 证实吗？** 有。证据 1 贴 `git diff 13a414d..9f378f4 -- 'SimRISC-01*' 'SimRISC-02*'` 空输出（含 `--stat` 双确认）；证据 2 证 SimRISC-03 未动；证据 3/4 逐 hunk 证 SimRISC-00（纯 FP）/SimRISC-04（系统 CSR）非 M1；证据 5 逐 hunk 证 "add 补 rd0" 为示例补全；证据 6 全网 M1 助记符扫描仅命中 deferred 域固件示例。
- **差分真跑了吗？** 跑了。Phase 4 贴 `run_differential.py` 尾部输出 = AGREE(4-way)=200/DIVERGE=0/HARNESS=6。
- **spec.md 语义 / impl 确实没动吗？** 确认。本次仅改 `manifests/spec.lock.toml`（pin）+ 新建本审计文档 + issues.yaml note 一行；未触 `contracts/isa/spec.md` 语义、未触 interp/QEMU/gem5/Sail 任何 impl（`git diff --stat` 复核）。
- **结论**：A 桶空 + 差分不回归 → 按 ADR-0013 Phase 5 门槛推进 pin 至 `9f378f4`。无需架构师定夺的 A 桶实现变更。

## IN-003a Reconciliation（2026-07-18）

本节记录已落地的状态对齐，不改变 WU-001a 的分类结论或 Wiki 内容：

- `/home/holight/DADAO-wiki` 切换前为干净工作树，目标对象
  `9f378f4426e131903d60a208766086ae74a53c89` 存在；随后以 detached checkout 切换到该完整 SHA。
- `contracts/isa/spec.md` 与 `contracts/abi/spec.md` 的 Source provenance 头均已更新为完整目标 SHA；正文语义未改。
- `manifests/spec.lock.toml` 未修改，仍固定目标 SHA；`docs/issues.yaml` 用户未提交改动保留。
- WU-001a 状态已更新为已完成，Phase 5 reconciliation 由 IN-003a 收口。
- 检查命令、退出码及四方 differential 结果见 IN-003a 任务完成区；若任一命令失败，按原始输出记录，不降级为 warning。
