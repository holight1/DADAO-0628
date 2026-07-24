# ML-033a：实现 DADAO 动态栈分配与恢复，关闭 VLA/alloca CodeGen 崩溃簇

**执行环境**：本地 subagent

**状态**：已完成

## 背景

ML-031a 后的 fresh gcc-c-torture 全量基线为
`PASS=1429 / FAIL_COMPILE=113 / FAIL_LINK=131 / FAIL_RUN=35`。其中 9 个
`FAIL_COMPILE` 不是 Clang 前端不支持，而是 DADAO 后端缺失动态栈节点：

- `DYNAMIC_STACKALLOC`：
  `20040811-1.c`、`20070824-1.c`、`920929-1.c`、`frame-address.c`、
  `pr36321.c`、`pr86528.c`
- `STACKRESTORE`/动态区生命周期：
  `920721-2.c`、`pr43220.c`、`vla-dealloc-1.c`

同一缺口还阻塞 musl 的 7 个对象：
`process/execl.c`、`process/execle.c`、`process/execlp.c`、`process/execvp.c`、
`unistd/getcwd.c`、`network/res_msend.c`、`locale/dcngettext.c`，已由
`docs/issues.yaml` 的 `musl-backend-dynamic-stackalloc-unimplemented` 记录。

## 目标

在当前 LLVM HEAD 上实现符合 DADAO ABI 的动态栈分配、`stacksave` 和
`stackrestore` lowering：

- SP 使用保留寄存器 `rb1`，栈向低地址增长；
- 动态大小按 ABI 至少 8 字节对齐；
- `stacksave` 返回调整前的真实 SP 指针；
- `stackrestore` 恢复保存值，不把动态调整错误折进固定 frame size；
- 固定 frame、callee-saved、动态区、调用序列和 epilogue 组合时仍正确；
- 大动态 size 不得依赖 imms12，使用合法的 RD/RB 物化与桥接路径；
- 不把真实 SP 调整误当成 `ADJCALLSTACKDOWN/UP` 的可消除 pseudo。

## 硬约束

- 先读 `contracts/abi/spec.md` §4、现有 `DADAOFrameLowering`/
  `DADAORegisterInfo`/`DADAOISelLowering` 和
  `musl-backend-dynamic-stackalloc-unimplemented` issue，不凭其它 target
  直接猜 DADAO 寄存器语义。
- 禁止用 `-O0`、固定 VLA 大小、改 testcase、禁用优化或为 9 个文件加特殊 flags
  绕过。
- 不顺带给外部 `alloca()` C 函数提供 libc stub；当前 6 个
  `missing_symbol:alloca` 是独立链接/API 问题，不作为本任务通过数。
- 正常普通 commit 落到 `.work/llvm`，立即导出一个或多个 patch，追加
  `components/llvm/patches/series`；禁止 rebase/reset/am 历史。
- 不启动 nested subagent，不提交根仓库。

## 判别性测试

新增 target in-tree CodeGen 测试和项目 E2E，至少覆盖：

1. 运行时 size（含非 8 字节倍数）分配、写入、读回；
2. 两次嵌套/顺序动态分配互不覆盖；
3. `stacksave` → 动态分配 → `stackrestore` → 再分配，确认地址和旧数据边界；
4. 固定局部变量与 VLA 同函数；
5. VLA 函数内部再调用普通函数，返回后数据正确；
6. size 足以触发非 imms12 调整；
7. O0/O2，QEMU 与 gem5 同一 ELF/语义双后端通过；
8. negative control 确认测试确实读回目标内存而非被优化折叠。

## 验收

- 上述 9 个 torture 文件由 `FAIL_COMPILE` 推进到可编译；逐项报告最终
  `PASS/FAIL_LINK/FAIL_RUN`，不强行要求无关缺陷也全消失。
- fresh musl 重建后，上述 7 个对象不再因
  `DYNAMIC_STACKALLOC/STACKRESTORE` 失败；报告对象级状态及 musl 总体变化。
- 全量 gcc-c-torture 1708 项重扫，和 `1429/113/131/35` 逐文件对账；
  允许目标项正向变化，禁止任何既有 PASS 回归。
- 全量 `llvm-lit -v tests/lit/E2E/`、DADAO CodeGen lit、
  `tools/run_differential.py`、manifest/issues checks 通过。
- 清理/归档对应 issue 时保留历史和精确 resolved commit/patch；若仅部分关闭，
  更新原 issue 的现状，不得直接删除。
- 填写任务完成区，并接受独立 subagent review，review 特别检查 SP 恢复、
  对齐、固定 frame 交互、大 size 和测试判别力。

## 非目标

- 不实现 Clang 不支持的 VLA-in-struct GCC 扩展。
- 不处理向量 legalize、BlockAddress、`__int128` 返回分配或外部
  `alloca()` libc symbol。
- 不修改 QEMU/gem5 来配合错误 lowering。

## 完成区

**状态**：已完成

**LLVM 落地**：

- 普通 commit：
  `dd80ef109bbb0a8f1bcc83c4377e46fec832b37f`
  （`DADAO: implement dynamic stack allocation and restore`）。
- patch：
  `components/llvm/patches/0060-DADAO-implement-dynamic-stack-allocation-and-restore.patch`
  （816 行），已立即追加 `components/llvm/patches/series`。
- commit 与 patch 的 stable patch-id 均为
  `0fc8ec3758064b86133aa6c8d0a396fdbaec576b`。
- LLVM diff：7 files changed，503 insertions(+)，44 deletions(-)；LLVM
  worktree 最终 clean。根仓库按硬约束未 commit。

**实现**：

- `DADAOISelLowering`：
  - `DYNAMIC_STACKALLOC` 自定义 lowering：运行时 size 向上对齐到 ABI
    至少 8 字节（请求更高对齐时按请求值），从真实 `rb1` 向低地址调整；
    调整量走 GPRD，使用 RD/RB bridge 写回 `rb1`，不依赖 imms12。
  - `STACKSAVE`/`STACKRESTORE` 分别读写真实 `rb1`；用 chain 串行化实际
    SP 改动，没有复用会被消除的 call-frame pseudo。
  - 新增 `DADAOISD::ADJDYNALLOC`/`ADJDYNALLOC` pseudo，在 PEI 已知最终
    outgoing call-frame 大小时修正动态区返回地址，保证 VLA 函数内部调用
    普通函数时地址不落入调用参数区。
  - LowerCall 的普通栈参数和 vararg save-area 共用
    `getOutgoingStackAddress`；大于 imms12 的偏移通过新增
    `DADAOISD::ADDRB` 显式选择 `GPRB base + GPRD offset → GPRB`，不再
    把物理 `rb1` 送入普通 RD `ADD`。
  - `frame-address.c` 暴露 generic `FRAMEADDR` 会返回零，因而补充
    `FRAMEADDR` lowering：一级返回 ABI frame pointer `rb2`，更深层沿
    saved-rb2 链读取。
- `DADAOFrameLowering`/`DADAORegisterInfo`：
  - 含动态对象或取 frame address 的函数启用 `rb2` frame pointer。
  - prologue/epilogue 严格采用 `contracts/abi/spec.md` §4 的布局：
    incoming-SP-8 保存旧 `rb2`，新 `rb2` 指向该槽；epilogue 从
    `rb2+8` 恢复 incoming SP，再从 `rb2+0` 恢复旧 FP。因此即使函数退出
    时仍有动态分配存活，也不会用错误的当前 SP 恢复固定 frame。
  - 固定 frame/FI 引用改用最终 frame register；有 FP 时局部对象相对
    `rb2` 稳定，incoming fixed object 偏移补偿 8 字节 saved-FP 槽。
  - `ADJDYNALLOC` 在最终 max call-frame 已知后展开；大 call-frame 同样走
    现有 64-bit RD 物化路径。

**新增测试**：

- LLVM in-tree：
  `llvm/test/CodeGen/DADAO/dynamic-stackalloc.ll`（266 行），覆盖 O0/O2、
  fixed+dynamic frame、8/16 字节对齐、stacksave/restore、17 个整数参数
  的函数调用、300 参数/2272-byte outgoing area、300 参数 vararg 的
  2400-byte save-area + 2272-byte overflow area、frameaddress 和大 size
  生成路径；显式禁止 `rb1` 被当成 `rd1` 的 RD ADD。
- 项目 E2E：
  `tests/lit/E2E/Inputs/dynamic_stackalloc.c`（121 行）和
  `tests/lit/E2E/dynamic_stackalloc.test`（26 行）。同一组语义在 O0/O2、
  QEMU/gem5 上运行；覆盖 13 字节运行时 size、5003 字节大 size、固定局部、
  嵌套/恢复/再次分配、17 参数调用、VLA 存活时的 300 参数/2272-byte
  outgoing area、16 字节对齐和内存首/中/尾读回。独立
  `NEGATIVE_CONTROL` 故意误判最后两个栈参数参与计算的返回值，在两个
  优化级别、两个后端均返回预期失败码 1，正例返回 42。

**before 证据**：

- `.work/evidence/ML-033a-before/torture-9.json`：目标 9 项均
  `FAIL_COMPILE`，错误分别落在 `dynamic_stackalloc` 或 `stackrestore`
  无法选择。
- fresh 前逐对象 `make -B -j1`：目标 7 个 musl 对象全部 rc=2，均因
  `dynamic_stackalloc` 无法选择。

**验收结果**：

1. 完整 LLVM build：首次 `-j6` 在链接 `clang-import-test` 时被系统以
   signal 9 杀死（内存压力）；降为 `-j2` 后失败目标成功，剩余 137/137
   完整构建通过。
2. 9 个目标 torture：
   `20040811-1.c`、`20070824-1.c`、`920721-2.c`、`920929-1.c`、
   `frame-address.c`、`pr36321.c`、`pr43220.c`、`pr86528.c`、
   `vla-dealloc-1.c` 最终全部 **PASS（9/9）**。
3. fresh musl：目标 7 个对象逐项 `make -B -j1` 均成功（7/7）。
   best-effort `libc.a` 收录 1344 个对象；总体失败从约 10 个降为 3 个
   已有、无关对象：`legacy/daemon.o`、`regex/glob.o`、
   `regex/regcomp.o`。
4. gcc-c-torture 1708 全量：
   `PASS=1438 / FAIL_COMPILE=104 / FAIL_LINK=131 / FAIL_RUN=35`。
   对比 ML-031a 基线 `1429/113/131/35`，目标 9 项恰好全部
   `FAIL_COMPILE → PASS`，其余分类计数不变，既有 PASS 零回归。结果：
   `.work/evidence/ML-033a-after-torture-1708.json`。
5. 全量 E2E：**77/77 PASS**；完整 DADAO CodeGen lit：**9/9 PASS**。
6. differential：
   `AGREE(3-way)=200`、`gem5-SKIP=2`、`DIVERGE=0`；
   `AGREE(4-way)=200`、`Sail-SKIP=2`、`SAIL-DIVERGE=0`。
7. `python3 scripts/manifest_check.py`、`python3 scripts/check_issues.py`
   及最终 `git diff --check` 均通过（见本任务最终收尾复跑记录）。

**issue 状态**：

- `musl-backend-dynamic-stackalloc-unimplemented` 已从
  `docs/issues.yaml` 完整迁移至 `docs/issues-archive.yaml`，保留原历史，
  标记 `status: closed`，并写入精确 LLVM commit、patch、stable patch-id
  与 fresh musl/全量验证结果。

## 审阅记录

用户明确禁止 nested subagent，因此没有执行任务模板原先要求的独立 subagent
review；由同一执行者完成逐文件自审和判别性验证。重点复核结果：

- SP 恢复不依赖动态调整后的当前 `rb1`，而从 `rb2+8` 恢复 incoming SP；
- 动态 size 和返回地址对齐路径均有 O0/O2 CodeGen/E2E 覆盖；
- 固定 frame、saved FP、动态区、17 参数调用的 outgoing area 互不重叠；
- 5003 字节 size 与大 call-frame 路径不依赖 imms12；
- positive/negative control 均在 QEMU、gem5 独立执行；
- 未发现需要停下定夺的 ABI 歧义；实现直接采用已冻结 ABI §4 的 FP/SP
  关系，没有引入新 ABI 规则。

## 独立审阅（2026-07-24）

**Verdict：Changes requested。**

执行 worker 遵守了“不启动 nested subagent”的任务约束；上面的“没有执行独立
subagent review”只描述 worker 自身没有嵌套委派，并不表示项目跳过独立审阅。
parent 按用户要求在 worker 返回后执行了本节独立 review。

### Findings

1. **High — `>imms12` outgoing call frame 与动态 alloca 组合仍会生成错误地址，
   而正式测试只覆盖 8 字节 call frame。**

   `dynamic-stackalloc.ll` 的 `dynamic_call_frame` 只有 17 个整数参数，
   `MaxCallFrameSize=8`，只能覆盖 `ADJDYNALLOC` 的小 immediate 分支。独立
   probe 使用 300 个整数参数，使 outgoing area 为 2272 字节，同时保留
   5003 字节运行时 VLA；O0 结果为 QEMU rc=1、gem5 abort(rc=134)，gem5
   报 `Page table fault ... 0x8d8`。反汇编确认新提交的
   `ADJDYNALLOC` 展开本身正确生成了
   `setzw rd2, 2272; add rb8, rb8, rd2`，但随后
   `DADAOTargetLowering::LowerCall` 为偏移 2264 的栈参数生成
   `add rd0, rd20, rd1, rd19; rd2rb rb8, rd20, 1; sto ..., rb8, 0`：
   它把物理 `rb1` 当作普通 `i64` DAG operand 送入 RD `ADD`，最终实际读了
   `rd1`，地址退化到低地址 `0x8d8`。这是已有的大 outgoing-stack-offset
   缺口，但 ML-033a 新增并声称支持大 `MaxCallFrameSize` 的
   `ADJDYNALLOC` 路径后，该组合属于本任务必须闭合的交互面；当前 issue
   归档中“大 call-frame 同样走现有 64-bit RD 物化路径”的口径也因此过宽。

   **最小修复建议**：在 `LowerCall` 的栈参数/vararg save-area 地址构造中，
   对超出 imms12 的常量偏移使用合法的 RB 基址加 RD 物化偏移路径，禁止把
   `DAG.getRegister(RB1, i64)` 交给普通 RD `ADD`；新增一个
   `MaxCallFrameSize > 2047` 的 VLA+调用 E2E，O0/O2 下同一 ELF 分别由
   QEMU/gem5 返回 42，并在 CodeGen test 中检查大 `ADJDYNALLOC` 展开与
   栈参数地址均没有 RB/RD bank 混用。修复前不应把对应 issue 视为完整关闭，
   至少应收窄归档口径并另开显式阻塞 issue。

2. **Informational — gem5 执行路径沿用项目既有的外部 live tree。**

   `tests/lit/E2E/lit.cfg` 实际使用
   `/home/holight/DADAO-gem5/build/DADAO/gem5.opt`（source HEAD
   `62c1264698c5`），不是 manifest checkout
   `.work/source/gem5`（HEAD `1da944e05a5f`）。两处
   `dadao_se.py` SHA-256 相同，且本任务正/负例确实在同一 ELF、同一
   expected-exit 语义下分别执行；因此这不构成功能一致性失败，但报告应把它
   称为当前 E2E 默认 gem5，而不是 manifest pin 产物。

### 独立复跑与核对

- `git patch-id --stable` 分别计算 commit 导出和 patch 0060：
  二者均为 `3322ef1ae303bed6f4723c468bf6f69df532563a`；LLVM HEAD
  `790bfb4cd40f`、worktree clean，`clang --version` 也标识该 HEAD。
- `.work/build/llvm/bin/llvm-lit -v
  .work/source/llvm/llvm/test/CodeGen/DADAO`：9/9 PASS。
- `.work/build/llvm/bin/llvm-lit -v tests/lit/E2E`：77/77 PASS；其中
  `dynamic_stackalloc.test` 单跑 1/1 PASS，正例/negative control 的
  O0/O2 QEMU/gem5 RUN 均实际执行。
- `python3 tests/scripts/gcc_torture_sweep.py --workers 4 --filter
  '(^|/)(20040811-1|20070824-1|920721-2|920929-1|frame-address|pr36321|
  pr43220|pr86528|vla-dealloc-1)\.c$'`：9/9 PASS。
- `python3 tests/scripts/gcc_torture_sweep.py --workers 8`：
  `PASS=1438 / FAIL_COMPILE=104 / FAIL_LINK=131 / FAIL_RUN=35`；
  与 worker 的 1708 项 JSON 逐文件比较，status mismatch=0。
- 在 `.work/build/musl` 对 7 个目标对象执行
  `make -B -j1 obj/src/{process/execl,process/execle,process/execlp,
  process/execvp,unistd/getcwd,network/res_msend,locale/dcngettext}.o`：
  7/7 成功；`llvm-ar t lib/libc.a | wc -l` 为 1344，`daemon.o`、
  `glob.o`、`regcomp.o` 均缺席，口径与完成区一致。
- 独立 FRAMEADDR 链 probe：caller 用运行时 VLA 强制建立 rb2 frame，
  callee 比较 `__builtin_frame_address(1)` 与 caller 的
  `__builtin_frame_address(0)`；O0/O2 下 QEMU=42、gem5=42。
- 大 outgoing-frame probe：300 个整数参数 + 5003 字节运行时 VLA；
  O0 为 QEMU=1、gem5=134，并由反汇编和 gem5 `0x8d8` fault 定位到 finding
  1。最初一次 reviewer 命令误把 crt0 ELF 受 `-x c` 影响当成 C 输入，该次
  为无效命令；调整输入顺序后的上述失败才是有效结果。
- `python3 scripts/manifest_check.py`：PASS；
  `python3 scripts/check_issues.py`：PASS（Open 21 / Closed 40 /
  Total 61）；`git diff --check`：PASS。

## 修复轮次（独立审阅 Changes requested 后）

**状态**：High finding 已修复；独立 finding 原文保留在上节。上节出现的
`790bfb4cd40f` 与 `3322ef1a...` 仅是被审初版的历史快照，不是最终落地值。

**根因与修复**：

- finding 中的 `ADJDYNALLOC` 大 call-frame 展开本身正确；真正错误位于
  `DADAOTargetLowering::LowerCall` 的两个同源地址构造点。普通栈参数和
  vararg save-area 都用 generic `ISD::ADD(rb1, constant)`；偏移无法折进
  imms12 时，i64 ADD 被分配到 GPRD，物理 `rb1` 因 bank 信息丢失而编码为
  同编号 `rd1`。
- 新增共享 `getOutgoingStackAddress`：imms12 内继续使用已有折叠路径；
  大偏移生成 `DADAOISD::ADDRB`，TableGen 严格选择
  `ADDRB_ORRR(GPRB base, GPRD offset) -> GPRB address`。普通 stack arg
  与 vararg save-area 均调用该 helper，不按测试名或参数个数特殊处理。

**新增/加强回归**：

- CodeGen 的 300 参数 fixed call：16 个寄存器参数 + 284 个栈参数，
  outgoing area 为 2272 字节；检查 `ADJDYNALLOC +2272` 和末参数
  `rb1 + rd(2264)`，并用 `NO-RD-RB-NOT` 禁止 `add rd*, rd1, ...`。
- CodeGen 的 300 参数 vararg call：2400-byte source-order save-area +
  2272-byte overflow area，总 call frame 4672；分别检查 2392 和 4664
  两个大地址均使用 RB base + RD offset。
- E2E 在 5003-byte、16-byte-aligned runtime VLA 存活期间调用 300 参数
  callee，读取寄存器/栈边界和最后两个栈 slot；O0/O2 的同一 ELF 分别在
  QEMU/gem5 返回 42。负控故意期待错误的 callee 结果，四种组合均返回 1。
  原 review probe 的 QEMU=1/gem5=134、fault `0x8d8` 不再复现。

**最终 LLVM 落地**：

- 按用户允许的 amend 路径，将原 commit 修订为
  `dd80ef109bbb0a8f1bcc83c4377e46fec832b37f`。
- 最终 LLVM 统计：7 files changed，503 insertions(+)，44 deletions(-)。
- 重新导出同一序号 patch
  `0060-DADAO-implement-dynamic-stack-allocation-and-restore.patch`
  （816 行）；`series` 仍仅包含一条 0060。
- commit 导出和 patch 文件的 stable patch-id 均为
  `0fc8ec3758064b86133aa6c8d0a396fdbaec576b`；LLVM worktree clean。

**修复后验证**：

- 增量 LLVM build：PASS（`cmake --build .work/build/llvm -j2`）。
- 定向 CodeGen：1/1 PASS；完整 DADAO CodeGen：9/9 PASS。
- 定向 E2E：1/1 PASS；完整 E2E：77/77 PASS。
- 目标 gcc-c-torture：9/9 PASS。
- 目标 musl 对象强制重编：7/7 PASS；`libc.a` 仍为 1344 members。
- differential：3-way AGREE=200、gem5-SKIP=2、DIVERGE=0；
  4-way AGREE=200、Sail-SKIP=2、SAIL-DIVERGE=0。
- 因修复是通用 LowerCall 地址路径，未仅凭影响分析跳过全量验证：
  1708 项重新扫描仍为
  `PASS=1438 / FAIL_COMPILE=104 / FAIL_LINK=131 / FAIL_RUN=35`；
  与修复前 `.work/evidence/ML-033a-after-torture-1708.json` 逐文件比较
  `STATUS_MISMATCH=0`。
- 最终 metadata 与 whitespace checks：`manifest_check.py` PASS、
  `check_issues.py` PASS、`git diff --check` PASS。

仍按用户约束未启动 nested subagent，未提交根仓库。

## 独立复审（2026-07-24）

**Verdict：Accepted with one non-blocking Low finding。**

前一节独立审阅的 **High finding 已关闭**。最终 LLVM commit
`dd80ef109bbb0a8f1bcc83c4377e46fec832b37f` 中，共享
`getOutgoingStackAddress` 同时接管普通 stack argument 和 vararg
save-area 地址；小偏移保留原生 imms12 折叠，大偏移通过
`DADAOISD::ADDRB` 严格选择 `ADDRB_ORRR(GPRB, GPRD) -> GPRB`。独立重跑
原失败 probe 后，旧的 QEMU=1、gem5=134/`0x8d8` fault 不再复现。

### Findings

1. **Low（不阻塞接受）— CodeGen 的显式 negative pattern 没有匹配历史坏指令
   的真实四操作数形态。**

   两处
   `NO-RD-RB-NOT: add {{rd[0-9]+}}, rd1,`
   只会匹配 `rd1` 作为第二个汇编 operand；历史坏指令实际为
   `add rd0, rd20, rd1, rd19`，`rd1` 是第三个 operand，因此这条
   `NOT` 本身抓不到原 finding。

   该问题不削弱本轮功能结论：同一 CodeGen 测试还正向要求
   `setzw 2264/2392/4664` 后出现 `add rb*, rb1, rd*` 并以该 RB 地址执行
   store，旧 lowering 无法满足；正式 E2E 和两组独立 runtime probe 也会在
   旧实现上分别返回错误或 fault。最小后续修正是把 pattern 写成能够匹配
   四操作数形态的
   `add {{rd[0-9]+}}, {{rd[0-9]+}}, rd1, ...`，或在目标函数范围内采用
   等价的精确 bank-aware negative check。本次依约未修改测试。

前一审阅的 gem5 provenance informational finding 保持原状：本轮 E2E 使用
项目既有默认 `/home/holight/DADAO-gem5` live binary；这不影响同一 ELF、
同一 expected-exit 的双后端功能结论，但不扩张为 manifest checkout binary
的可复现性声称。

### 独立复跑与核对

- **原 300 参数 + 5003-byte VLA probe**：重新生成与前一 review 同构的
  300 个普通整数参数程序，读取 `a0`、首个 stack arg `a16`、最后一个
  stack arg `a299`，并验证 16-byte-aligned VLA 的首/中/尾：
  - O0：QEMU=42，gem5=42；
  - O2：QEMU=42，gem5=42。
  O0 反汇编包含 `setzw ..., 2272`、`setzw ..., 2264` 和
  `add rb8, rb1, rd...`；搜索历史坏形态
  `add rd*, rd*, rd1, rd*` 为 0。
- **独立大 vararg probe**：17 个 fixed 参数加 283 个 varargs，在
  5003-byte、16-byte-aligned VLA 存活期间调用；callee 读取首个/最后一个
  vararg，并同时验证第 17 个 fixed stack arg：
  - O0：QEMU=42，gem5=42；
  - O2：QEMU=42，gem5=42。
  O0 反汇编实际出现 `4672` 总 call frame、`4664` ordinary overflow
  offset、`2392` save-area offset，三者均使用 `add rb*, rb1, rd*`；
  历史坏形态计数为 0。
- `.work/build/llvm/bin/clang --version` 标识最终 revision
  `dd80ef109bbb0a8f1bcc83c4377e46fec832b37f`；LLVM source HEAD 与之相同，
  worktree clean。
- commit 导出和
  `components/llvm/patches/0060-DADAO-implement-dynamic-stack-allocation-and-restore.patch`
  的 stable patch-id 均为
  `0fc8ec3758064b86133aa6c8d0a396fdbaec576b`；patch 首行 From 为最终
  commit，816 行，`series` 中 0060 恰好一条。
- `.work/build/llvm/bin/llvm-lit -v
  .work/source/llvm/llvm/test/CodeGen/DADAO`：9/9 PASS；正式
  `dynamic-stackalloc.ll` 为 266 行，覆盖 fixed 2272-byte 与 vararg
  4672-byte 大调用区。
- `.work/build/llvm/bin/llvm-lit -v tests/lit/E2E`：77/77 PASS；正式
  `dynamic_stackalloc.test` 的 O0/O2 正例和 negative control 均在
  QEMU/gem5 实际执行。C probe 读取寄存器/栈边界及最后两个 stack slots，
  并在调用前后验证 VLA。
- `python3 tests/scripts/gcc_torture_sweep.py --workers 8`：
  `PASS=1438 / FAIL_COMPILE=104 / FAIL_LINK=131 / FAIL_RUN=35`；
  与 `.work/evidence/ML-033a-after-torture-1708.json` 的 1708 项逐文件
  `status_mismatch=0`，目标 9 项均 PASS。
- 在 `.work/build/musl` 强制重编 7 个目标对象：7/7 成功；
  `llvm-ar t lib/libc.a | wc -l` 仍为 1344。第一次从根目录调用同一
  `make` target 因工作目录错误报 `No rule to make target`，改到真实 musl
  build 目录后的上述结果才是有效复审结果。
- `python3 scripts/manifest_check.py`：PASS；
  `python3 scripts/check_issues.py`：PASS（Open 21 / Closed 40 /
  Total 61）；`git diff --check`：PASS。
- task 完成区、issue archive `resolved_by`、patch From、LLVM HEAD 和
  `clang --version` 的最终 commit 均为 `dd80ef109bbb...`；最终 stable
  patch-id 均为 `0fc8ec375806...`。任务/issue 中保留的
  `790bfb4...`/`3322ef1...` 均有“初版/历史快照”上下文，没有被当作最终值。
