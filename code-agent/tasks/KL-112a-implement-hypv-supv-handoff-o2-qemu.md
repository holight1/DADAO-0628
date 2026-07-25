# KL-112a：实现 hypv→supv 移交 O2（越权/被 mask 负例）in QEMU

**执行环境**：本地 subagent，QEMU 源码改动（`.work/source/qemu`），产出
patch 落 `components/qemu/patches/`

## 背景

`KL-110a`（已 commit）实现了 O1（`escape cfx_power,0` 成功移交 hypv→supv），
明确排除了 O2（越权/被 mask 负例）。`KL-111a`（已 commit，
`docs/reviews/kernel-hypv-supv-o2-permission-recon-20260725.md`）调研了
O2 的精确机制，给出三个已用 wiki 原文+行号钉死、且已被架构师独立复核
（对照 wiki 原文和当前 QEMU 源码逐条核实）的负例设计。本任务是把这三个
设计变成真实的 QEMU 实现+验收。

**当前实现现状**（KL-111a 已核实，本任务直接复用其证据，不用重新调研）：

- `helper_escape()`（`target/dadao/helper.c:169-214`）完全没有 SEE §5
  异常退出流程步骤0（escape cfx mask 检查）——目标 cfxcode 非 `power`
  时，当前代码会静默用全零 frame 完成"恢复"并跳到 `pc=0`，这是一个真实
  bug（不会报错，但行为是错的），需要本任务堵上。
- `helper_cfx2rc()`（`target/dadao/helper.c:118-164`）只识别两种
  `(cg,rc)`：`(3,12)`（delegation 数组）和 `(63,5,{0,1,3})`（power
  frame），其它任何组合（包括 reserved 组合）一律静默 no-op，不产生
  CFXREG 异常。
- `cpu.h` 的 `EXCP_*` 枚举目前没有 `EXCP_CFXREG`；已用退出码惯例是
  `0x81`(MALIGN)/`0x82`(ILLI)/`0x83`(UNDI)/`0x84`(RASOF)/`0x85`(RASUF)。

## 目标

实现并验收 KL-111a 报告 §4 的**设计1**（必做）+**设计3**（必做）+
**设计2**（可选，成本低，建议一并做）：

1. **设计1（候选B）：跨 cfx `escape` 权限检查**——`helper_escape()` 补上
   SEE §5 异常退出流程步骤0：若目标 `cfxcode != inner_cfx_code`，检查
   `cfx_⟨cfxname⟩_<mode>_escape_cfx_mask`（`⟨cfxname⟩=inner_cfx_code`，
   `<mode>=inner_run_mode`，检查发生在步骤1-2 恢复 mode/mask **之前**）
   第 cfxcode 位；若为1，触发 ILLI，且**不执行**步骤1-4（不恢复
   mask/mode，不跳转到 cause_ip，PC 停在触发异常的 `escape` 指令本身，
   `inner_run_mode` 保持不变）。
   - 需要新增 `cfx_power_hypv_escape_cfx_mask`（HEE §1 cg3/rc7）以及
     其余 mode（user/jail/supv 各自的 `escape_cfx_mask`，SEE §3 cg0-2
     rc7）的存储——至少要能通过 `cfx2rc`/reset 读到"全1"默认值以支撑本任务
     的验收场景（reset 后未经任何委托清除，检查应恒为"禁止"）。是否为
     每个 cfx（不只 power）都建立完整存储，由你根据"不为验收之外的场景
     过度设计"原则判断最小实现范围，但至少要让 KL-111a 设计1描述的
     `escape cfx_smon,0` @ reset 场景产生正确的 ILLI。
2. **设计3（候选C）：`cfx2rc` reserved `(cg,rc)` → CFXREG**——
   `helper_cfx2rc()` 补上默认分支的 CFXREG 触发（当前是静默 no-op）。
   需要新增 `EXCP_CFXREG` 异常类型 + 对应退出码（建议延续
   `0x81`-`0x85` 的编号规律，具体数值你决定，只要在 patch 和 spec.md
   里保持一致）。验收场景：`cfx2rc cfx_power,8,63,rdX`（`cfx_power` 的
   cg=8 只定义 rc=0,1，rc=63 未定义）→ 产生 CFXREG，不修改任何架构状态。
3. **设计2（候选B2，可选）**：`cfx2rc` 的跨 cfx 权限检查
   （`cfx2rc_cfx_mask`，与设计1同构机制），如果实现成本低可以一并做；
   如果发现和设计1有实质性的额外复杂度（比如需要区分四条指令各自的
   `<instr>_cfx_mask`），可以只做 escape 一条，在完成区如实说明为什么
   跳过，不强求。

## 约束

- **只实现 KL-111a 报告 §4 明确给出、且已被架构师独立复核过的三个设计**，
  不要顺带"顺便也实现"报告里判定为"不可行"的候选A（一般形式的
  delegation 访问控制）——那需要先解决 `docs/wiki-deviations.md` 第10条
  的 OPEN 状态，不是本任务范围。
- 不要修改 `EXCP_CFXTRAP`（trap→host syscall 捷径）路径的任何行为。
- Carrier-point 设计延续 `KL-110a`/`KL-102a` 已确立的约定：所有状态
  转换/异常触发逻辑集中在 `helper.c` 的 `helper_escape`/`helper_cfx2rc`
  里，不要在 `translate.c` 里加检查逻辑。
- `contracts/isa/spec.md §8` 需要更新：把这三个负例的语义补充进
  §8.1（cfx2rc）/§8.2（escape）已有小节（不新增顶层小节，是扩展已有
  小节的异常行为描述），每条断言都要有 wiki 引用（同行标注，参照
  `check_wiki_refs.py --profile isa` 的既有要求）。
- 新增的探针脚本（参照 `tests/scripts/gen_kl110a_o1_probe.py` 的模式）
  要能同时验证"正例继续工作"（O1 的 `escape cfx_power,0` 依然成功）和
  "负例被正确拦截"（设计1/2/3 各自的场景产生正确的 fault class，且**不
  产生**任何成功 marker）——负例的验收关键是"确认异常真的被触发了，
  且没有意外副作用"，不能只验证"程序退出码不是0"这么弱的断言。
- 完整 patch-series bare-pin replay（tree-hash 比对）是硬性验收项，
  照 `KL-110a`/`KL-109a` 的标准执行。
- 完成后写「完成区」+ 「审阅记录（subagent 自审）」；不需要嵌套
  subagent、不需要独立 reviewer（架构师会亲自复核，含独立重跑探针）。

## 验收

- `helper_escape()`/`helper_cfx2rc()` 的改动通过手写探针验证：
  - O1 正例（`escape cfx_power,0`）继续产生原有的 marker+退出码42
    （回归验证，复用或改造 `gen_kl110a_o1_probe.py`）。
  - 设计1负例：`escape cfx_smon,0` @ reset → ILLI，`inner_run_mode`
    保持 `hypv`，不跳转到 `cause_ip`。
  - 设计3负例：`cfx2rc cfx_power,8,63,rdX` → CFXREG，架构状态不变
    （`cfx_power_pending`/`cfx_power_ctrl` 均不受影响）。
  - （若做了设计2）跨 cfx `cfx2rc` 负例 → ILLI。
- `contracts/isa/spec.md`：`scripts/check_wiki_refs.py --profile isa`、
  `scripts/validate_encoding.py tools/opcodes.yaml`、
  `scripts/manifest_check.py`、`scripts/check_issues.py`、
  `scripts/check_wiki_drift.py` 全部 PASS。
- `components/qemu/patches/`：新增 patch 落地，`series` 更新，从
  `manifests/components.lock.toml` 锁定 commit 起裸 pin + 完整 series
  replay，tree hash 与开发树一致。
- 现有 lit E2E（`tests/lit/E2E/`）与差分验证（`tools/run_differential.py`）
  保持全绿，无回归。

## 参考指针

- `docs/reviews/kernel-hypv-supv-o2-permission-recon-20260725.md`
  （KL-111a，本任务三个设计的精确规格来源，§4）
- `code-agent/tasks/KL-110a-implement-hypv-supv-handoff-o1-qemu.md`
  完成区（O1 实现细节、carrier-point 设计先例）
- `docs/wiki-deviations.md` 第9条（`inner_cfx_code` 未被 escape 恢复，
  本任务的负例设计不依赖这条被恢复，无需处理）、第10条（候选A 被排除
  在本任务范围外的依据）
- `tests/scripts/gen_kl110a_o1_probe.py`（探针脚本模式参考）
- `~/DADAO-wiki/DADAO-12-SEE-主管系统运行环境.md`（第813-845行 escape
  硬件语义；第711-738行 entry-flow `<instr>_cfx_mask` 检查）
- `~/DADAO-wiki/DADAO-13-HEE-超管系统运行环境.md`（第7-26行 cg3 寄存器
  表，含 `escape_cfx_mask`/`cfx2rc_cfx_mask` 定义）
- `~/DADAO-wiki/SimRISC-04-系统类指令.md` 第87行（CFXREG 触发条件原文）

---

## 完成区（2026-07-25）

**状态**：设计1（必做）+ 设计3（必做）已完成并验收通过。设计2（可选）
评估后**判定不实现**——不是"实现成本高"，是发现了一个真实的 wiki
矛盾（详见下文），已记为 `docs/wiki-deviations.md` 第11条。

### wiki 原文复核（动手前，亲自读，非转述任务文件）

逐条核对了任务文件引用的全部原文，行号与内容一致，另有两点任务文件
行号之外的补充核实：

- `DADAO-12-SEE-主管系统运行环境.md` 第813-845行 escape 硬件语义：
  步骤0（`:824-827`）"若 cfxcode != inner_cfx_code 且
  `cfx_⟨cfxname⟩_<mode>_escape_cfx_mask` 第 cfxcode 位=1 → cause<=ILLI，
  重定向到当前模式 monitor"；`⟨cfxname⟩`=`inner_cfx_code`（`:815`）。
- 第711-738行 entry-flow：确认 `<instr>_cfx_mask` 通用检查（`:721`）对
  `CFX2RC`/`ESCAPE` 等六条特权指令统一适用，`⟨cfxname⟩`=`inner_cfx_code`、
  `<mode>`=检查时刻的 `inner_run_mode`（当前正在执行该指令的 cfx/mode，
  非目标）。
- `DADAO-13-HEE-超管系统运行环境.md` 第7-26行 cg3 寄存器表：`rc=7`
  "hypv escape cfx mask"、`rc=3`"hypv cfx2rc cfx mask"，均复位"全1"。
  `DADAO-12-SEE §3` 第273-331行 cg0-2 表核对一致（`rc=7`/`rc=3` 同名
  含义，user/jail/supv 三份）。
- `SimRISC-04-系统类指令.md` 第87行：CFXREG 触发条件原文三分句核对，
  设计3只用第一句"读写不存在的 `cfx_<cfxname>_cghb_rchc` 组合"。
- `DADAO-12-SEE-主管系统运行环境.md` 第628-650行 `cfx_power` cg=8
  专有寄存器表：只定义 `rc=0`(power_pending)/`rc=1`(power_ctrl)——补充
  核实，任务文件未展开但设计3验收场景（`cg=8,rc=63`）依赖这张表。
- `DADAO-23-HBI-超管系统二进制接口.md` 第29-64行完整引导序列——补充
  核实（任务文件未直接引用，但为判断设计2是否可行必须核对），发现
  第34-45行 12 条 `cfx2rc cfx_<name>_hypv_cg_reg_deleg,rd2` 中 11 条
  目标 cfxcode ≠ `inner_cfx_code`（恒为 power），且全程未写
  `cfx_power_hypv_cfx2rc_cfx_mask`——见下文"设计2 撤回"。

### QEMU 实现（`.work/source/qemu`，commit `4d8d9fa`）

严格延续 KL-110a/KL-102a 的 carrier-point 约定：状态转换与异常触发全部
在 `helper.c` 的 `helper_escape`/`helper_cfx2rc` 里，`translate.c` 零改动
（`git diff translate.c` 确认空）。

- **`cpu.h`**：新增 `EXCP_CFXREG`(=6)；新增
  `cfx_escape_cfx_mask[64][4]` 状态数组（索引 `[cfxcode][mode]`，`mode`
  直接复用 `DADAORunMode` 数值 USER=0/JAIL=1/SUPV=2/HYPV=3，与 wiki
  cg0-3 分组编号天然对齐）；新增 `DADAO_CFX_MASK_REG_ESCAPE`(=7) 常量。
  **没有** `cfx_cfx2rc_cfx_mask` 存储（设计2撤回）。
- **`cpu.c`**：reset 时把 `cfx_escape_cfx_mask` 全部初始化为全1（HEE §1/
  SEE §3 复位值）；`dadao_cpu_do_interrupt` 新增 `EXCP_CFXREG` 分支，
  退出码 `0x86`（延续 `0x81`-`0x85` 编号规律，项目自定义，非 wiki 定义
  数值——wiki 只定义 CFXREG 的 cause id=`1<<2`）。
- **`helper.c`**：
  - `helper_escape()`：函数开头（`cfxcode &= 0x3F` 之后、恢复
    mask/mode 之前）新增设计1检查——`cfxcode != env->inner_cfx_code`
    时读 `cfx_escape_cfx_mask[inner_cfx_code][inner_run_mode]`，位为1则
    `dadao_raise_exception(env, EXCP_ILLI, GETPC())`（noreturn，函数
    其余部分不执行，PC 由 `cpu_restore_state` 走 TCG 标准回溯机制精确
    落在触发异常的 escape 指令本身，与 `gen_exception_illegal` 的
    既有机制同构，未发明新的 PC 定位方式）。
  - `helper_cfx2rc()`：默认分支新增设计3——
    `cfxcode==DADAO_CFX_CODE_POWER && cg==8 && rc>1` 时触发
    `EXCP_CFXREG`。**刻意窄范围**：只覆盖 wiki 明确证实"真正不存在"的
    这一个组合，不把整个默认分支（其余 cg0-2/cg3 剩余寄存器等，wiki
    有定义只是 QEMU 未实现存储）改判成 CFXREG，避免"未实现"和"不存在"
    被混淆成同一件事（详见代码注释）。同时新增
    `cg<=3 && rc==DADAO_CFX_MASK_REG_ESCAPE` 分支，写入
    `cfx_escape_cfx_mask[cfxcode][cg]`（设计1的寄存器写入路径，O1 stub
    从不触碰，无冲突）。
- **未触碰** `EXCP_CFXTRAP` 路径任何一行；未改 `translate.c`；未实现
  候选A（cg_reg_deleg 访问控制，任务范围外，`docs/wiki-deviations.md`
  第10条）。

### 设计2（候选B2）撤回过程（真实发现，非纸面推理）

先按字面实现了候选B2（`cfx2rc_cfx_mask` 跨 cfx 检查，与设计1同构，加了
`cfx_cfx2rc_cfx_mask[64][4]` 存储 + 检查代码），**用 O1 回归探针实测
重放**（不是理论推演）时发现：O1 exit code 从 42 变成 0x82——HBI §3
引导桩第一条 `cfx2rc cfx_umon_hypv_cg_reg_deleg,rd2`（cfxcode=umon=0
≠ inner_cfx_code=power=63）撞上了 `cfx_power_hypv_cfx2rc_cfx_mask`
默认全1（从未被 HBI §3 清除）触发 ILLI。这是一个**真实的 wiki 内部
矛盾**：SEE §5 entry-flow 的 `<instr>_cfx_mask` 通用检查字面无条件
适用于 `cfx2rc`（不区分运行模式），而 HBI §3 的唯一文档化引导序列本身
就是跨 cfx `cfx2rc` 的密集使用者且从不清这个 mask——两者不可能同时
按字面成立。`KL-111a` 报告设计2的原始提案是一个独立场景
（`cfx2rc cfx_smon_user_global_cfx_mask,rd2`），报告本身没有针对 O1
重放验证，未能发现这个矛盾。

**处理**：撤回候选B2的检查代码和存储（`git diff` 里已看不到
`cfx_cfx2rc_cfx_mask`），只保留设计1+设计3；把矛盾原样记入
`docs/wiki-deviations.md` 第11条（标注 CONTRADICTION 而非 SILENT，
因为两处 wiki 文本都明确存在、字面同时成立时互斥，不是"沉默未定义"）；
`contracts/isa/spec.md` §8 开头方括号范围说明和 §8.1 对应 bullet 都
如实标注"设计2刻意不实现"及原因。这个撤回不影响设计1——O1 唯一的
`escape` 使用（`escape cfx_power,0`）是 self-escape
（`cfxcode==inner_cfx_code`），设计1的跨 cfx 检查按定义对 self-escape
不生效，两者不对称，没有同样的冲突。

### `contracts/isa/spec.md` 改动

- §8 开头范围说明：从"QEMU 只实现 O1 子集"改为"O1 + 设计1/设计3"，
  并显式记录设计2被排除的原因（引用 wiki-deviations #11），避免读者
  以为是"还没做"而非"评估后主动不做"。
- §8.1：`cfx2rc` "Full semantics" bullet list 拆成三条——reserved
  cfxcode（未实现）、跨 cfx `cfx2rc_cfx_mask`（**刻意**未实现，引用
  #11）、CFXREG（**已实现**，但只精确到 `cfx_power` cg=8 这一个具体
  组合，非泛化）。
- §8.2：`escape` 步骤0改为"QEMU 已实现"，补充精确异常约定（PC 不动、
  mode/mask 不变，对齐 §2.7 precise-fault 惯例）；步骤3
  (`escape_num++`) 标注未实现（无 cg4 计数器存储）。
- 每条新增/改动断言都在同一行带 `[wiki §...]` 或
  `[spec-decision: KL-112a, 2026-07-25]`，`check_wiki_refs.py
  --profile isa` 复跑 PASS（过程中修过一次自己引入的 Check 2 违规，
  见「审阅记录」finding 1）。

### `docs/wiki-deviations.md` 新增第11条

记录设计2撤回的完整矛盾链（SEE §5 entry-flow 字面条款 + HEE §1 mask
复位值 + HBI §3 引导序列三者互斥），分类为 CONTRADICTION（区别于第9/
10条的 SILENT）。状态 OPEN，列了三个未评估可行性的候选解法方向（模式
豁免/引导序列补全/范围收窄读法），不预判。

### 探针脚本与验证证据

新增 `tests/scripts/gen_kl112a_o2_probes.py`（仿
`gen_kl110a_o1_probe.py` 模式，未 commit，留工作区）。三个探针 +
一次 A/B 负控制，全部写入 `.work/evidence/kl112a-probes/`
（gitignored，不影响提交）：

1. **`kl112a-o1-regression.bin`**（复用 `gen_kl110a_o1_probe` 的完整
   HBI §3 stub 逻辑）：exit=42（0x2a），trace 显示
   `escape cfx=63 mode 3->2 ... pc=0x100200`——与 KL-110a 原始证据
   （`.work/evidence/KL-110a-o1-handoff.trace.log`）完全一致，确认设计1
   对 O1 零回归。
2. **`kl112a-design1-negative.bin`**（reset 后单条
   `escape cfx_smon,0`）：exit=0x82（ILLI），trace **没有**
   "escape cfx=..." 行（对照 O1 正例的 trace 一定有这行，说明步骤1-4
   确实没有执行到 `qemu_log_mask` 调用点之前就被 noreturn 异常截断）。
   **另做了一次 A/B 经验负控制**（`kl112a-design1-negative.
   AB-disabled.trace.log`）：临时把设计1检查代码禁用（`if (0 && ...)`）
   重编译重跑同一个探针二进制，观测到 trace **确实出现**
   `escape cfx=2 mode 3->0 mask=0x0 pc=0x0000000000000000`——即"检查
   缺失"时 escape 会真的把 `inner_run_mode` 从 hypv(3) 改成 user(0)、
   PC 跳到 0x0，是真实的架构状态改变；巧合的是两种情况最终 exit code
   都是 0x82（禁用检查后 PC=0 处解码出 `halt ha=0`，二次触发 ILLI），
   这正是任务文件警告的"不能只验证退出码"陷阱的真实案例——若只看 exit
   code 会误判"反正一样"，实际上只有 trace log 能看出架构状态是否真的
   被污染。验证完成后已恢复检查代码、重新编译，确认 `diff` 与恢复前
   逐字节一致。
3. **`kl112a-design3-negative.bin`**（`cfx2rc cfx_power,8,63,rd2` +
   poison `halt rd9=0x77`）：exit=0x86（CFXREG），**没有**到达 poison
   halt（否则会是 exit=0x77）——证明 CFXREG 在到达 poison 之前就
   中断了执行，`cfx_power_pending`/`cfx_power_ctrl`（`(cg,rc)=(8,0)`/
   `(8,1)`）本身在 QEMU 里没有任何存储字段，"不受影响"是平凡成立，
   重点是"读写 (8,63) 这个不存在的组合没有被静默吞掉"这件事本身。
4. （设计2已撤回，`gen_design2_negative()` 函数保留在脚本里作为
   "如果做了会用什么探针"的记录，未纳入 `gen_all()` 的必需集合，探针
   文档字符串已注明。）

**已知限制（如实标注，非隐瞒）**：设计1的寄存器写入路径
（`cfx2rc cfx_<name>_<mode>_escape_cfx_mask, rdX`）没有独立的"写入后
生效"正例探针——验收场景本身（reset 后默认全1即拒绝）不需要写入这个
寄存器；构造一个"清除 mask 位后跨 cfx escape 成功"的正例需要控制
non-power cfxcode 的 escape 目标地址（该分支硬编码 `prev_run_mode=
USER,cause_ip=0`），而 `imms18` 的 18 位有符号范围（±131071×4≈
±512KB）够不到 ROM 基址 `0x00100000`，会落到未映射地址，引入与本任务
设计1/2/3 无关的额外不确定性，故未构造。写入路径本身经过代码走查确认
（一行 `env->cfx_escape_cfx_mask[cfxcode][cg]=value` 无分支，逻辑简单
到走查即足够，不是"没测的复杂代码"）。

### 验证结果

- 探针（O1正例/设计1负例/设计3负例）：**PASS**（见上，含 A/B 负控制）。
- `python3 scripts/check_wiki_refs.py --profile isa`：`OVERALL: PASS`
  （Check 2 修过一次自己引入的违规，见审阅记录 finding 1）。
- `python3 scripts/validate_encoding.py tools/opcodes.yaml`：
  `91 records OK`（未新增/改动任何编码记录，数字与改动前一致）。
- `python3 scripts/manifest_check.py`：PASS。
- `python3 scripts/check_issues.py`：PASS（Open 24/Closed 43/Total 67，
  无变化——本任务未新增/关闭 issue）。
- `python3 scripts/check_wiki_drift.py`：PASS。
- `python3 scripts/check_qfc_coverage.py` / `check_legality_matrix.py`
  （非任务强制项，沿用 KL-110a 惯例额外跑了一遍）：`QEMU-BUG(check-1)
  =0`、`opcodes-漏(check-2)=0`，QFC 覆盖缺口数字与改动前一致（未碰
  opcode 编码，符合预期）。
- `python3 tools/run_differential.py`：`AGREE(4-way)=200，DIVERGE=0`——
  与改动前基线完全一致（cfx2rc/escape 的 O2 分支尚未进差分向量集合，
  预期数字不变）。
- `lit tests/lit/E2E`：**81/81 PASS**（与 KL-110a 基线一致，无回归）。
- QEMU 侧改动：普通 `git commit`（`4d8d9fa`，detached HEAD），
  `git format-patch` 导出
  `components/qemu/patches/0025-target-dadao-implement-hypv-supv-handoff-O2-negative.patch`
  并追加进 `series`；commit 与导出 patch 的 stable patch-id 均为
  `3c94c83d1355c84b45e7dbdb5fbf686fe5cbc6ff`；独立在 manifest pin
  （`385b0a7d9785c8f3ac7b116d7f31d61502b55183`）干净 worktree 上依次
  `git am` 全部 25 个 patch 成功，replay tree 与开发树 tree 均为
  `b129cd66849d9d35192373fc3d697183aafccdff`，临时 worktree 已清理
  （`git worktree remove --force`）。

### 附带的小改动

- `tests/scripts/run_qemu_test.py`：`FAULT_CODES` 字典新增
  `'CFXREG': 0x86` 一行——本任务引入的新故障类，供后续 YAML 测试向量
  编写者使用，低风险纯增量改动。

### 范围边界确认

- 设计2（候选B2）评估后判定不实现，原因和证据链见上；已记入
  `docs/wiki-deviations.md` 第11条，状态 OPEN。
- 候选A（cg_reg_deleg 访问控制）未涉及，任务范围外
  （`docs/wiki-deviations.md` 第10条）。
- `cfxld`/`cfxst`/`cfx2rd`/`trap` 未涉及，M1 排除范围不变
  （`contracts/isa/spec.md §7`）。
- 未碰 gem5、未碰 Sail——`run_differential.py` 的四方数字不变（O2
  分支未进差分向量集合）符合预期。
- 未触碰 `EXCP_CFXTRAP`/host syscall 捷径任何一行；未改
  `translate.c`；未 rebase/重放 patch series 历史（只有一次新增
  commit + 一次 `git format-patch` 导出，验证用的临时 worktree 已清理）。
- 未 commit 到 DADAO-0628 根仓库——`contracts/isa/spec.md`、
  `docs/wiki-deviations.md`、`tools/opcodes.yaml`（未改动，无需
  commit）、`tests/scripts/gen_kl112a_o2_probes.py`、
  `tests/scripts/run_qemu_test.py`、`.work/evidence/kl112a-probes/`、
  本任务文件均留在工作区等架构师复核。

---

## 自审：审阅记录（subagent 自审）

**判决**：自审通过，一处过程性 finding（已在完成过程中自行修复，非
遗留问题）。

- **Finding 1（自查发现并修复）**：`contracts/isa/spec.md` §8 开头范围
  说明改写后，`check_wiki_refs.py --profile isa` Check 2 报了一处硬
  错误（`spec.md:1009`，"reserved-cfxcode routing to **ILLI**"这句因为
  含 `ILLI` 触发词但同一物理行没有 `[wiki §...]`/`[spec-decision:]`
  标记）——原文这条信息已经在 §8.1 bullet list 里带着完整 wiki 引用，
  是范围说明段落里的重复提及触发了误报，不是缺引用。已改写为"见 §8.1
  bullet list"的指代，避免重复陈述同一断言两次（一次带引用一次不带），
  复跑 `Check 2 missing ref: 0`，`OVERALL: PASS`。
- **wiki 引用逐项复核**：本次新增/改动的每一处 `[wiki §... Lxx–Lyy]`
  行号区间，动手前用 Read 工具打开对应 wiki 文件核对过原文内容（见
  完成区"wiki 原文复核"小节），不是照抄任务文件或 KL-111a 报告字面
  行号——任务文件/KL-111a 给出的行号与独立核对结果一致；HBI §3 引导
  序列的独立核实（任务文件未直接引用这段，为判断设计2可行性主动补读）
  是这次实现最关键的一步，直接导致了设计2撤回的决定。
- **设计3窄范围决定的自查**：没有把 `helper_cfx2rc` 默认分支整体
  改判成 CFXREG（那样成本更低、代码更短），是因为验证过 cg0-2/cg3 的
  剩余寄存器（`global_cfx_mask`/`cfx2rd_cfx_mask`/`cfxld_cfx_mask`/
  `cfxst_cfx_mask`/`trap_cfx_mask`/`switch_run_mode`/`switch_cfx_mask`/
  `excp_vector`/`excp_cause_mask` 等）在 wiki 里都有正式定义（SEE §3/
  HEE §1 表格逐条列出），只是当前 QEMU 没有为它们分配存储——把"未实现"
  和"不存在"混为一谈会让 spec.md §8.1 自己的"O1 subset"框架自相矛盾，
  代价是设计3的实现范围比"字面上默认分支全改" 窄，但避免了引入新的
  错误断言。
- **设计1 GETPC()/noreturn 机制核对**：确认 `helper_escape`/
  `helper_cfx2rc` 在 `helper.h` 里声明为非 `noreturn`（`DEF_HELPER_5(
  cfx2rc, void, ...)`/`DEF_HELPER_3(escape, void, ...)`），与
  `helper_raise_exception`（已验证工作正常的既有机制）同样的
  TCG 直接调用模式——`GETPC()` 在这两个函数体内直接调用（不是转调
  `helper_raise_exception` 再让它内部调用 `GETPC()`，那样会拿到错误的
  返回地址），与既有 `gen_exception_illegal` 机制完全同构，未发明新的
  PC 定位方式。
- **O1 回归的完整链路核对**：不是只看"exit code=42"这一个数字，而是
  对照 trace log 的完整两行（reset 行 + escape mode 3->2 行）与
  KL-110a 原始证据文件逐字节比对（`.work/evidence/
  KL-110a-o1-handoff.trace.log`），确认这不是"恰好数字对上"而是同一条
  执行路径。
- **A/B 负控制的独立性核对**：design1-negative 的 A/B 对比不是凭空
  断言"应该不同"，而是真实临时改代码（`if (0 && ...)`）、重新
  `ninja` 编译、独立跑出 `mode 3->0 pc=0x0` 的 trace，再恢复代码、
  重新编译、`diff` 确认恢复后文件与备份逐字节相同——这个过程本身也是
  对"我的检查代码真的是导致行为差异的原因"这一因果关系的直接验证，
  不是只在纸面上推理"应该是这样"。
- **patch-series replay 独立性核对**：replay worktree 用 `git worktree
  add --detach <pin-commit>` 从 manifest 锁定的裸 commit
  （`385b0a7d9785c8f3ac7b116d7f31d61502b55183`）开始，不是从当前开发树
  分支出去的；25 个 patch 全部用 `git am` 逐条应用（无冲突、无
  `--3way`/`-C` 之类的宽松选项），tree hash 用 `git rev-parse
  HEAD^{tree}` 独立计算两侧后逐字符比对，worktree 完成后
  `git worktree remove --force` 清理，未残留。
- **未做事项确认**（对照约束逐条自查）：未对 `.work/source/qemu` 做
  `rebase`/重放历史/`reset --hard`（只有一次新 `git commit` + 一次
  `git format-patch`，A/B 负控制的临时改动用 `cp` 保存/恢复原文件，
  不涉及任何 git 历史操作）；未实现候选A；未碰 gem5/Sail；未碰 host
  `cfx_smon` handler；未碰 `EXCP_CFXTRAP`；未改 `translate.c`；未
  commit 到 DADAO-0628 根仓库；`docs/issues.yaml`
  的 `Cross-cfx-escape` 条目（关于"未清 delegation"，对应
  wiki-deviations 第9条 `inner_cfx_code`）与本任务无关，未触碰。
