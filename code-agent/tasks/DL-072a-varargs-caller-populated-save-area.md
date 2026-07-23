# DL-072a：修复变参指针实参丢失——严格按 wiki 实现"调用者填充统一保存区"

**执行环境**: 本地 subagent

**状态**: 已完成（独立 review Accepted）

## 硬约束（务必遵守，违反视为任务失败）

- **禁止**对 `.work/llvm` 做 `git rebase`/`git am` 重放整条历史/`git reset --hard` 到早于
  当前 HEAD 的操作。只允许在当前 HEAD 基础上新增普通 `git commit`。
- **本任务的 ABI 设计不是开放讨论题——严格按 wiki 原文实现**，不要采用"两个独立 bank
  计数器"（x86-64 风格 `va_list` 结构体）或"变参尾巴强制走单一 bank"（RISC-V 风格）这
  两个替代方案——**架构师最初考虑过这两个方向，用户明确要求"严格按照 wiki"，架构师
  随后在 `~/DADAO-wiki/DADAO-21-ABI-应用程序二进制接口.md` 找到了权威原文，机制与这
  两个替代方案都不同**（见下方「wiki 原文」）。发现实现中 wiki 原文有任何歧义/看似
  不可行之处，如实报告给架构师，不要自行切换到其它设计。
- **完成后立即导出 patch**（不要延后）：`components/llvm/patches/0050-...patch`，
  追加进 `series`。
- 完成后必须在任务文件里写「完成区」+ subagent 自审「审阅记录」（含逐条 finding + 判决）。

## wiki 原文（权威依据，逐字引用自 `~/DADAO-wiki/DADAO-21-ABI-应用程序二进制接口.md`
第 247-334 行，不是架构师转述）

> ### 可变参数：Variable Arguments
>
> DADAO 采用 `va_list` 即为 `void*` 指针的极简实现，调用者在 call 指令前将所有参数
> 按调用顺序依次写入栈上的连续保存区。
>
> **保存区布局**
>
> 调用者按参数在调用点出现的顺序，将每个参数以 8 字节为单位依次写入保存区。保存区
> 大小 = 总参数个数 × 8 字节。
>
> 三组参数寄存器（rd16-rd31 / rb16-rb31 / rf16-rf31）独立计数导致 callee 无法仅从
> 寄存器重建声明顺序，保存区必须由调用者在调用点写入，不分区存放。
>
> **栈布局顺序**
>
> 栈上参数区域按地址从低到高排列：**寄存器溢出参数区 → 局部变量 → varargs 保存区**。
> 溢出区紧接寄存器参数槽位之后，保存区在最高地址，二者均为 8 字节对齐、连续紧凑存放。
>
> **大端序 slot 布局**
>
> DADAO 为大端序。8 字节 slot 内，N 字节类型的有效值**右对齐**（byte `8-N` 至 `7`），
> 低地址字节（byte 0 至 `8-N-1`）为符号/零扩展位。
>
> **实参提升**（caller 端，C 标准）：
>
> | 实参类型 | 提升为 | 写入 slot 方式 |
> |---------|--------|--------------|
> | `char`/`short`（有/无符号） | `int`（32位符号扩展后放rd） | `*(uint64_t*)slot = rd_value` |
> | `int`/`long`/`long long` | 64位（符号/零扩展放rd） | `*(uint64_t*)slot = rd_value` |
> | 指针 | 64位（放rb） | `*(uint64_t*)slot = rb_value` |
>
> （原文还含 `float`/`double` 走 rf bank 的行——**本任务不实现，M1 CodeGen 从未注册
> 浮点寄存器类，浮点变参不在本任务范围**，实现时只处理 RD/RB 两个 bank 的实参类型）
>
> **示例**（原文用 6 个混合参数，本任务节选 RD/RB 部分对应的机制）：命名参数**同时**
> 装入对应参数寄存器（供 callee 直接从寄存器访问）**并且**被写入保存区（供 `va_arg`
> 按声明顺序读取）——即命名参数是"双写"的，不是只写寄存器或只写保存区。
>
> **va_list 定义**：`typedef void* va_list;`
>
> **va_start(ap, last_named_arg)**：`last_named_arg` 是第 N 个参数（从1计），
> `ap = (char*)sp + N * 8`（`sp` 为调用点 sp，即 callee 的 incoming stack pointer）。
>
> **va_arg(ap, type)**：`(*(type*)((char*)((ap += 8) - 8) + (8 - sizeof(type))))`——
> 统一 8 字节步进，大端序下 narrow 类型右对齐读取 slot 尾部。

**关键理解（这是本任务修复方向和此前 `docs/issues.yaml`/`contracts/abi/spec.md` 里
"declaration order 保存区"这个说法的一个重要澄清，之前的文字没写清楚"谁来填充"这个
save area，这次要按 wiki 原文明确：是 caller 在调用点填充，不是 callee 在序言里
spill 自己的传入寄存器）：

- **当前（bug）实现**：`LowerFormalArguments`（callee 侧，`DADAOISelLowering.cpp`
  约 259-297 行）在变参函数序言里，把自己"没分配完的"RD bank 寄存器（rd16..rd31 里
  超出固定参数用量的部分）spill 到一个只属于 RD bank 的保存区——这是 callee 侧的
  "spill 剩余寄存器"模式（类似 RISC-V/x86-64 传统实现），**完全不是 wiki 规定的机制**，
  且从未处理 RB bank，这正是本 bug 的直接原因。
- **wiki 要求的（正确）机制**：由 **caller**（`LowerCall`，`DADAOISelLowering.cpp`
  约 103-214 行）在每次调用变参函数时，除了正常把前 16 个 RD 参数和前 16 个 RB 参数
  分别装入 rd16..31/rb16..31 寄存器之外，**额外**按调用点出现的原始参数顺序（不分
  bank），把**全部**实参（命名 + 变参，包括寄存器传递的那些）以 8 字节为单位依次
  `store` 进调用点栈上的一块连续保存区；callee 侧不需要做任何 spill，`va_start`
  只需要计算一个偏移量（跳过命名参数占的 slot 数）指向 caller 已经写好的这块内存。

## Ownership 与目标

1. **LowerCall（caller 侧）改动**：当 `CLI.IsVarArg` 为真（调用点的被调用函数类型
   带 `...`）时，在现有正常传参逻辑（前16个RD走寄存器、前16个RB走寄存器、溢出走
   §2.3 共享溢出区）之外，**额外**在栈上新分配（或复用/紧邻现有溢出区，参照 wiki
   "寄存器溢出参数区→局部变量→varargs保存区"这个布局顺序自行判断具体怎样和现有帧
   布局协调）一块 varargs 保存区，大小 = 全部实参个数 × 8 字节，按调用点参数出现
   顺序（不分 bank）依次 store 每个实参的值：
   - `int`/`long`/`long long` 类实参：64位值（符号/零扩展）整个存进 8 字节 slot
     （wiki 例子对这类整数是"全 64 位"存法，不是"右对齐 narrow 值"——注意区分
     "实参提升"表格里 char/short 会先提升到 int 但示例图里 int 本身是存 64 位扩展
     值，不是 4 字节右对齐；**这个细节务必对照 wiki 示例图（第 297-306 行的
     `foo` 例子）逐字节核实，不要只看提升表格就下结论，两处如有出入以示例图prose
     周围更详细的字节图为准，如实报告任何看起来矛盾的地方**）。
   - 指针类实参：64位值整个存进 slot。
   - 命名参数在寄存器传递的同时，**也**要写入这个保存区（双写，见"关键理解"）。
2. **LowerFormalArguments/lowerVASTART（callee 侧）改动**：删除当前"spill 剩余
   RD 寄存器"的逻辑（bug 本体，且现在有了 caller 侧的写入不再需要），`va_start`
   改为按 wiki 公式计算：保存区基址（调用点 sp）+ 命名参数个数 × 8。`va_arg` 的语义
   由 Clang 对 `CharPtrBuiltinVaList` 目标的通用展开机制处理（`DADAOTargetInfo`
   已经声明 `CharPtrBuiltinVaList`，`.work/llvm/clang/lib/Basic/Targets/DADAO.h:56`）
   ——**需要验证** Clang 这条通用路径本身是否已经正确处理大端序 narrow 类型的
   slot 内偏移（`8 - sizeof(type)`），不要假设它自动是对的，用真实探针验证（例如
   `va_arg(ap, int)` 读一个已知非 0 高 32 位模式的 slot，看读出来的值是否符合右
   对齐语义）。
3. `contracts/abi/spec.md` 的 Varargs 行（第 318 行附近）目前的措辞含糊（"declaration
   order 保存区"没写清楚是 caller 填充还是 callee spill）——**更新这一行，明确
   引用 wiki §可变参数 原文机制**（caller 在调用点填充统一保存区，不是 callee
   spill），避免未来再有人误读成"callee-side 双 bank spill"这个已被证伪的理解。
   `docs/open-spec-issues.md` 对应 Varargs 行同步更新。

## 验收

- 用一个真实的、mix RD/RB 类型的变参调用探针验证（参照 wiki 示例但只用 int/指针，
  例如：`void probe(int a, int b, void *c, int d, ...)` 被调用为
  `probe(1, 2, &x, 4, 5, &y, 6)`，`probe` 内部用 `va_arg` 依次读出 `5`、`&y`、`6`
  ——**必须验证指针值和整数值都读取正确**，不能只测全 int 或只测全指针，这正是
  bug 场景本身：混合类型才会暴露"哪个 bank"的问题）。
- 用一个更贴近实际的复现：把 `docs/issues.yaml` `varargs-pointer-args-lost-rb-bank-
  save-area` 条目里描述的原始故障场景（`printf("%s %s\n", p, q)`，两个指针变参）
  真实跑一遍，确认两个字符串顺序和内容都正确（不是"看起来合理但错误"的换位）。
- 用 `ML-025a` 已经验证过 6 个软浮点符号正确、但被这个 varargs bug 挡住的
  `scanf("%d", &x)` 场景真实跑一遍双后端，确认现在能正确解析（`tests/lit/E2E/
  musl_scanf_int.test` 目前是 `XFAIL: *`——如果本任务修复成功，这个测试会从
  XFAIL 变成 unexpected pass，**按 lit 惯例这会被报告为需要关注的异常**，本任务
  应该把这个 `XFAIL: *` 标记摘掉、让它变回正常 `PASS` 断言，不要留着 XFAIL 让它
  一直报 unexpected pass 噪音）。
- 全量 `llvm-lit tests/lit/E2E/`：零回归（当前基线 68/68，落地前重新跑一次记录
  当前值为准；`musl_scanf_int.test` 摘掉 XFAIL 后应计入正常 PASS 数）。
- `python3 tools/run_differential.py`：AGREE 数与当前基线一致、DIVERGE=0（本任务
  不改指令语义）。
- `python3 scripts/manifest_check.py`/`check_issues.py` 通过。
- LLVM 侧改动用**普通** `git commit` 落地，`git format-patch` 导出为
  `components/llvm/patches/0050-....patch`，追加进 `series`；独立验证可在干净
  pin-commit checkout 上 `git am` 成功。
- 关闭 `docs/issues.yaml` 的 `varargs-pointer-args-lost-rb-bank-save-area` 条目
  （若真正解决，移入 `docs/issues-archive.yaml`），同步更新 `docs/open-spec-issues.md`
  对应行、`contracts/abi/spec.md` 第 318 行的 Varargs 说明。
- 如果实现过程中发现 wiki 原文有内部矛盾/看不懂的地方（例如上面「目标1」提到的
  "实参提升表格 vs 示例字节图"的潜在出入），**如实报告具体矛盾点和你的判断依据**，
  不要自己选一个理解就往下做而不说明——这类澄清可能需要转达给 wiki 团队。

## 参考指针

- `~/DADAO-wiki/DADAO-21-ABI-应用程序二进制接口.md` 第 240-337 行（本任务的权威依据，
  务必自己完整重读原文，不要只信本任务文件的引用摘录）
- `docs/issues.yaml` `varargs-pointer-args-lost-rb-bank-save-area`（bug 完整历史、
  ML-013a/ML-025a 两次独立确认的具体故障实例）
- `code-agent/tasks/archive/.../ML-025a-scanf-softfloat-symbols.md`（`tests/lit/
  E2E/musl_scanf_int.test` 的 XFAIL 现状，本任务如修复成功要摘掉这个标记）
- `.work/llvm/llvm/lib/Target/DADAO/DADAOISelLowering.cpp`：`LowerCall`（约103-214行，
  caller 侧要新增保存区填充逻辑的位置）、`LowerFormalArguments`（约216-300行，
  callee 侧要删除的 RD-only spill 逻辑）、`lowerVASTART`（约559行附近）
- `.work/llvm/clang/lib/Basic/Targets/DADAO.h:56`（`CharPtrBuiltinVaList` 声明，
  确认 va_arg 走 Clang 通用展开路径而非自定义 lowering）
- `contracts/abi/spec.md` §2.3（Register Overflow，共享溢出区/声明顺序规则，与
  varargs 保存区是姊妹机制但不完全相同——溢出区是"寄存器用完后的额外参数"，varargs
  保存区是"变参函数专属、涵盖全部实参"，本任务实现时注意区分不要混淆）、第318行
  Varargs 现有措辞（本任务要更新的位置）
- `docs/open-spec-issues.md` 第11行 Varargs 条目（同步更新）

## 完成区（实现 subagent，2026-07-23）

### 根因与实现

根因由三层组成：

1. `LowerFormalArguments` 在 callee 侧只 spill 尚未分配的 RD16–RD31，RB
   指针实参从未进入 `va_list`，也无法在 callee 侧恢复原声明顺序。
2. DADAO 原先沿用通用 `SelectionDAG::expandVAArg`，`int` 按 4 字节递增并
   从 slot 基址读取，违反 wiki 的统一 8 字节步进和大端 `slot+4` 读取。
3. 新增 caller save area 后暴露既有 frame 缺口：无操作数的
   `ADJCALLSTACKDOWN/UP` 在 PEI 前被 dead-MI elimination 删除，
   `maxCallFrameSize` 变成 0，outgoing save slots 会覆盖 caller locals。

LLVM 普通提交 `3aa546d1d0cd516e04edc599e8c32a964acd96b2`
（`DADAO: implement caller-populated varargs save area`）完成：

- `LowerCall` 对 `CLI.IsVarArg` 的全部 RD/RB 标量实参按原顺序双写到统一
  8-byte-slot save area；固定/未命名 overflow 另有不重叠布局。
- 删除 callee RD-only spill；`va_start` 用 incoming fixed-stack size 加
  named-slot 偏移直接定位 caller area。
- 新增 DADAO Clang ABI `EmitVAArg`：slot size 8、每次 `+8`、大端窄值右对齐。
- 删除 `VarArgsSaveSize` 及 DADAOFrameLowering 旧特判；call-frame pseudos
  标记 side-effecting，使 PEI 真正预留最大 outgoing frame。
- 新增 LLVM/Clang 回归和 4 个 E2E：mixed RD/RB、big-endian narrow、
  fixed/unnamed overflow、real musl `printf("%s %s")`；scanf 原 XFAIL 删除。

已立即导出
`components/llvm/patches/0050-DADAO-implement-caller-populated-varargs-save-area.patch`
并追加 `series`。具体 pointer-loss issue 已从 `docs/issues.yaml` 移入
`docs/issues-archive.yaml`；ABI/open-spec 文档已明确 caller-populated 机制。

### 验收证据

- 改动前 E2E：68 discovered，67 PASS + 1 XFAIL（scanf）。
- Clang narrow IR：两次 `va_arg(int)` 均为 `argp.next = argp + 8`，读取地址
  均为 `argp.cur + 4`。
- LLVM 定向 lit：`varargs-slot.c` + `varargs-save-area.ll` = 2/2 PASS。
- 核心运行探针：mixed RD/RB（O0/O2）、narrow、overflow、
  `printf("%s %s")`、`scanf("%d",&x)` = 5/5 PASS；每个运行探针均覆盖
  QEMU + gem5。printf 输出严格为 `left right`；scanf 输出 `got=42` 且
  双后端退出 42。
- frame 证据：修复前 `maxCallFrameSize=0, stackSize=16, local=sp+12`
  与 save slot `sp+8` 重叠；修复后
  `maxCallFrameSize=16, stackSize=32, local=sp+28`，不再重叠。
- 干净 musl object/libc archive 重建：`make -C .work/build/musl clean`
  后 `make build-musl` PASS（best-effort archive，既有已登记失败仍按项目
  recipe 处理）。
- 全量 E2E：72/72 PASS（新增 4，scanf 由 XFAIL 转正常 PASS）。
- differential：
  `AGREE(3-way)=200, gem5-SKIP=2, DIVERGE=0, HARNESS=0`；
  `AGREE(4-way)=200, Sail-SKIP=2, SAIL-DIVERGE=0`。
- `manifest_check.py` PASS。
- `check_issues.py` PASS：Open 20 / Closed 37 / Total 57。
- 干净 manifest pin `ca7933e47d3a...` worktree 依次 `git am`：
  50/50 PASS；最终 tree
  `c9f9803b7fb5f35c8199174bfb1ff4a29ff420fe` 与 LLVM 提交 tree 完全一致。

### wiki 歧义与范围

wiki 的标量提升表与字节图不冲突：caller 存完整扩展后的 64 位值；callee
读取 `int` 时在大端 slot 内从 `+4` 取低 32 位。

但 wiki 另有一处真实文字冲突：`save-area base = incoming SP` 与“地址从低到高
为 overflow → locals → save area”在存在普通 overflow 副本时无法同时成立，
因为 callee 不知道调用点的未命名 overflow 总量，也没有第二个 base 参数。
本实现保留 incoming SP 这一唯一 callee 可得锚点：无 fixed overflow 时
save area 以 incoming SP 为基址；有 fixed overflow 时，`va_start` 使用
`incoming SP + fixed_stack_size + named_count*8`，同时将 fixed overflow
放在 save area 前、未命名 overflow 的普通副本移到 save area 后。
fixed/unnamed overflow E2E 均通过。该措辞冲突已保留在
`docs/open-spec-issues.md`，未静默宣称完整 RF/aggregate ABI 已闭合。
DL-072a 仍严格限定于 RD/RB 标量；RF 与完整 aggregate coverage 未实现。

## 审阅记录（实现者自审）

| Finding | 处置 |
|---|---|
| 通用 `expandVAArg` 会 `int +4` 且从 slot 基址读 | 新增 DADAO Clang ABI，IR 回归锁定 `+8/+4` |
| caller slots 首版覆盖 caller local，scanf 输出正确后 MALIGN | 追到 call-frame pseudo 过早删除；保留 pseudo 至 PEI，MIR/双后端复验 |
| 只测寄存器内参数会遗漏 overflow 偏移风险 | 新增 17 fixed + 17 unnamed overflow 真实双后端探针 |
| 增量 musl build 会复用旧编译器产物 | 执行 clean 后完整重建，再运行真实 printf/scanf |
| wiki overflow 排列文字与 incoming-SP 公式冲突 | 明确记录 open-spec；未改 wiki、未隐瞒 |

**实现者自审判决：PASS，提交独立 subagent review。**

## 独立 subagent review（2026-07-23）

- 审查记录：`docs/reviews/DL-072a-independent-review-20260723.md`
- 判决：**Accepted**，无 blocking finding。
- 独立复跑：LLVM/Clang 定向 2/2 PASS；核心 E2E 5/5 PASS；全量 E2E
  72/72 PASS；四方差分 200 AGREE、0 DIVERGE；manifest/issues PASS。
- 独立复核：0050 与 LLVM 普通提交逐字节对应；manifest pin 上 50/50
  full replay clean，最终 tree 与 `3aa546d1d0cd...` 一致。
- 非阻断边界：wiki 的 overflow/locals/save 地址顺序与 incoming-SP 公式
  仍存在文字冲突；broader `Varargs` issue 保持 open，RF 与完整 aggregate
  未纳入本任务完成声明。
