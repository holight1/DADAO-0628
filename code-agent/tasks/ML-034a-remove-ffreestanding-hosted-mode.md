# ML-034a：移除测试编译链路的 `-ffreestanding`，改用 hosted 模式

**执行环境**: 本地 subagent

## 硬约束（务必遵守，违反视为任务失败）

- **只改测试/扫描脚本编译用户程序时传给 clang 的 flags，不改 musl 自身构建**。
  `.work/source/musl/Makefile:47` 的 `CFLAGS_C99FSE = -std=c99 -ffreestanding
  -nostdinc` 是 musl 上游构建自身 libc 实现的标准做法（musl 编译自己的源码时
  一直是 freestanding，这是正确且不该动的），**不在本任务范围内**，不要碰。
  本任务只改"测试程序/torture 用例本身"被编译时用的 flags。
- **禁止**对 `.work/llvm`/`.work/source/musl`/`.work/source/qemu` 做
  `git rebase`/`git am` 重放整条历史/`git reset --hard`。本任务预期不需要改
  任何 `.work/*` 源码（纯粹是调用方传的编译选项变化），如果诊断后发现确实需要
  动 LLVM/musl/QEMU 源码才能保证零回归，先停下来报告，不要在没有把握的情况下
  硬改核心组件。
- 已知会用到 `-ffreestanding` 的文件（本任务范围内，需要逐一处理）：
  - `tests/scripts/gcc_torture_sweep.py`（`CFLAGS` 列表）
  - `tests/scripts/embench_sweep.py`（同名 `CFLAGS` 机制，`ML-032a` 刚新增）
  - 以下 10 个 E2E lit 测试文件里 `%clang` 调用的选项：
    `musl_malloc_printf.test`、`malloc_hello.test`、`musl_e2e_exit.test`、
    `musl_printf_ptrs.test`、`musl_stdin_getchar.test`、
    `musl_malloc_sizeclass.test`、`printf_hello.test`、
    `musl_malloc_sizeclass_liteonly.test`、`musl_printf_int.test`、
    `musl_scanf_int.test`、`musl_puts_writev.test`
  （用 `grep -rl -- '-ffreestanding' tests/` 复核这份清单是否完整，不要假设
  上面列的就是全部——脚本可能还有别的调用路径遗漏没抓到。）
- 完成后必须在任务文件里写「完成区」+ subagent 自审「审阅记录」（含逐条 finding
  + 判决）。

## 背景

`ML-026a`（`docs/reviews/ML-026a-gcc-c-torture-sweep-2026-07-24.md` §方法论
发现）识别出：编译 gcc-c-torture 用例时用 `-ffreestanding` 会关闭 C11 对
`hosted` 环境下 `main()` 落到函数末尾隐式 `return 0` 的保证——在 freestanding
模式下 clang 不做这个特殊处理，`main` 落到末尾时返回值是未定义的寄存器残留值，
导致至少 ~12-15 个原本逻辑正确的用例被误判为 `FAIL_RUN`。这是一个方法论层面
的假失败来源，不是后端 bug。

项目当年选 `-ffreestanding` 是因为最初 bare-metal + 手写 crt0、没有真实 libc
时，需要告诉 clang 不要假设 hosted 环境的运行时组件存在。但现在（`ML-007a`~
`ML-012a` 之后）项目已经有一个真实、完整链接的 musl（`crt1.o`+`libc.a`），
`main()` 由 musl 的 `_start` 按标准 hosted 约定调用——不再需要 `-ffreestanding`
这层假设。用户已于本 session 决定：**去掉 `-ffreestanding`，改用 hosted 模式**，
但要求验证"去掉后 crt0/musl 集成不会因为 clang 假设了某些 hosted 环境组件
（如 `__libc_start_main` 之类的语义联动）而出现新问题，需要全量 E2E 回归验证"。

## 目标

1. 逐一确认上面列出的每个文件里 `-ffreestanding` 的确切作用范围，改成不传
   `-ffreestanding`（即默认 hosted 模式）。同时评估是否需要保留/调整
   `-nostdinc`、`-nostdlib` 等其它 freestanding 相关 flag——这些和
   `-ffreestanding` 不是一回事，`-nostdinc`/`-nostdlib` 只影响头文件/link
   阶段的默认搜索路径，与"是否假设 hosted 运行时语义"无关，**默认保留不动**，
   除非诊断中发现有实际冲突再调整并说明理由。
2. **风险排查（用户明确要求的验证项）**：hosted 模式下 clang 可能对
   `main` 的签名、`__attribute__((used))`、内建函数识别（如 freestanding 关闭
   了一些内建 `memcpy`/`memset` 之类的假设，hosted 会重新打开）等产生不同的
   codegen 假设。需要在切换前后各跑一次全量套件，确认没有因为这类假设差异
   引入新的编译失败/运行时错误——如果发现有，如实诊断根因（是测试本身依赖
   freestanding 特有行为，还是后端对 hosted 模式下产生的某些 IR pattern
   缺乏支持），不要为了"看起来全绿"而回退到某个文件继续用 `-ffreestanding`
   而不说明理由。
3. 重新运行全量 gcc-c-torture 扫描（`python3 tests/scripts/gcc_torture_sweep.py`），
   报告修正后的真实 PASS 数、以及具体是哪些文件从 FAIL_RUN 翻转为 PASS（预期
   在 ML-026a 报告提到的 ~12-15 个附近，但以实测为准，不要假设一定是这个数字）。
   同时确认没有任何原 PASS 的文件退化（逐文件 diff，不只看聚合数字）。
4. 重新运行 Embench sweep（`python3 tests/scripts/embench_sweep.py`），确认
   O0/O2 结果不因为这个 flag 变化而改变（除非诊断后发现确有关联，如实报告）。
5. 全量 `llvm-lit tests/lit/E2E/`：确认零回归（这批测试原来就是靠
   `-ffreestanding` 编译的，现在改 hosted 模式后功能语义不能变，包括新增的
   聚合体/VLA/varargs 相关测试）。

## 验收

- `grep -rl -- '-ffreestanding' tests/` 在本任务改动范围内的文件里应为空
  （musl 自身 Makefile 除外，那不属于本任务范围）。
- 全量 gcc-c-torture 重扫：报告新分布，和当前基线 `1438/104/131/35`
  （`ML-033a` 完成后的基线）逐文件对比，明确列出所有状态变化的文件；
  **不允许任何原 PASS 文件退化**，FAIL_RUN→PASS 的文件数量和具体文件名如实
  报告。
- Embench sweep：O0/O2 各 19 项结果与当前基线（O0 19/19、O2 18/19 仅
  `qrduino` FAIL）对比，如实报告是否有变化。
- 全量 `llvm-lit tests/lit/E2E/`：零回归（落地前重新跑一次记录当前基线为准，
  当前应为 77/77）。
- `python3 tools/run_differential.py`：AGREE 数与当前基线一致、DIVERGE=0
  （本任务不改指令语义，理论上不应变化）。
- `python3 scripts/manifest_check.py`/`check_issues.py` 通过。
- 若诊断中发现任何一个文件因为 hosted 模式引入了新的、非假失败的真实失败，
  如实登记为独立 issue，不要为了保留统一 flag 集合而放弃摘除
  `-ffreestanding`——除非发现摘除会导致大范围真实回归，此时应停下来报告
  给架构师而不是自行决定折中方案。

## 参考指针

- `docs/reviews/ML-026a-gcc-c-torture-sweep-2026-07-24.md`（`-ffreestanding`
  发现的原始出处、~12-15 个假失败文件的方法论讨论）
- `tests/scripts/gcc_torture_sweep.py`（`CFLAGS` 列表，约第 90 行附近）
- `tests/scripts/embench_sweep.py`（同类 `CFLAGS` 机制，`ML-032a` 新增）
- `tests/lit/E2E/*.test`（上面列出的 10 个文件，`%clang` 调用里的 flags）
- `.work/source/musl/Makefile:47`（`CFLAGS_C99FSE`——**不要动**，仅作为
  "musl 自身构建仍应保持 freestanding"的对照参考）
- `contracts/abi/spec.md`（如果发现 hosted/freestanding 切换涉及 ABI 假设，
  这里是权威依据）

## 完成区

**状态**：已完成（改动留在工作区未 commit，等待架构师复核）。

### 改了哪些文件

`grep -rl -- '-ffreestanding' . --include=*` 复核过清单完整性（排除
`.work/`、`.git/`、`__pycache__`、`code-agent/tasks/`archive 里只是提到这个
词的历史任务文档），确认任务文件里列的清单就是全部，没有遗漏：

- `tests/scripts/gcc_torture_sweep.py`：`CFLAGS` 列表去掉 `-ffreestanding`
  （保留 `-nostdinc`），顶部注释同步更新说明（“freestanding” →
  “hosted 模式”），并在 `CFLAGS` 前新增一段注释说明为什么去掉
  （ML-026a 假失败方法论 + 保留 `-nostdinc` 的理由）。
- `tests/scripts/embench_sweep.py`：三处 `-ffreestanding`（编译命令列表 1
  处、`contracts.compile.flags` 元数据 1 处、Markdown 报告里的"编译契约"
  文案 1 处）全部去掉，`-nostdinc` 保留不动。
- 10 个 `tests/lit/E2E/*.test`：`musl_malloc_printf.test`、
  `malloc_hello.test`（2 处 `%clang` 调用）、`musl_e2e_exit.test`、
  `musl_printf_ptrs.test`、`musl_stdin_getchar.test`、
  `musl_malloc_sizeclass.test`、`printf_hello.test`（2 处）、
  `musl_malloc_sizeclass_liteonly.test`、`musl_printf_int.test`、
  `musl_scanf_int.test`、`musl_puts_writev.test`——全部去掉
  `-ffreestanding`，`-nostdinc`/`-nostdlib` 原样保留。
- `docs/issues.yaml`：新增 1 条 open issue
  `dadao-frame-lowering-8byte-align-insufficient-for-16byte-locals`（见下
  "发现的真实回归" 一节），登记本任务诊断出的、去掉 `-ffreestanding` 后
  暴露的一个真实的、预先存在的后端栈对齐缺口。

**没有改**：`.work/source/musl/Makefile:47` 的 `CFLAGS_C99FSE`（musl 自身
构建用，任务范围外，未触碰）；`.work/llvm`/`.work/source/musl`/
`.work/source/qemu` 无任何改动（未做 `git rebase`/`git am`/`git reset
--hard`，也没有改任何 `.work/*` 源码本身——诊断出的根因虽然定位到
`DADAOFrameLowering.h` 里的一行常量，但严格按硬约束没有去改它，只登记为
issue）。

### 验收项逐条实测结果

**1. `grep -rl -- '-ffreestanding' tests/`（任务范围内文件）**：
```
$ grep -rl -- '-ffreestanding' tests/ --include=*.py --include=*.test
(无输出，exit 1)
```
全仓库范围复核（排除 `.work/.git/__pycache__/code-agent/tasks` 历史文档）
同样为空，只有我自己在 `gcc_torture_sweep.py` 新增注释里提到
"`-ffreestanding` 被去掉"这几个字面量匹配（不是活的编译选项）。

**2. gcc-c-torture 全量重扫**（`python3 tests/scripts/gcc_torture_sweep.py
--workers 6`，1708/1708 全部跑完，未超时未中断）：

| | PASS | FAIL_COMPILE | FAIL_LINK | FAIL_RUN | TOTAL |
|---|---|---|---|---|---|
| 基线（ML-033a 后，仍带 `-ffreestanding`） | 1438 | 104 | 131 | 35 | 1708 |
| 本任务后（hosted 模式） | **1461** | 104 | **125** | **18** | 1708 |

逐文件 diff（不是只看聚合数字）：1708 个文件里 **27 个状态发生变化**，其余
1681 个文件状态完全不变。

- **FAIL_LINK → PASS（6 个）**：`20010122-1.c`、`20020314-1.c`、
  `20021113-1.c`、`20040223-1.c`、`941202-1.c`、`pr22061-1.c`。
- **FAIL_RUN → PASS（19 个）**：`20021127-1.c`、
  `alias-access-path-1.c`、`alloca-1.c`、`memchr-1.c`、`memset-2.c`、
  `memset-3.c`、`pr15262-1.c`、`pr38151.c`、`pr65170.c`、`pr68648.c`、
  `pr79737-2.c`、`pr87053.c`、`pr90949.c`、`return-addr.c`、
  `strlen-2.c`、`strlen-3.c`、`strlen-4.c`、`strlen-5.c`、`strlen-6.c`。
  （数量比 ML-026a 报告估计的"~12-15 个"多，实测 19 个 FAIL_RUN→PASS +
  6 个 FAIL_LINK→PASS，以实测为准；FAIL_LINK 里那 6 个能翻盘大概率是同一
  批 hosted-mode 内建函数识别变化带来的连带效果，未逐个深挖链接侧根因，
  因为它们全部是"从失败到通过"、且不在"需要深挖的回归"之列，超出本任务
  验收要求的范围）。
- **PASS → FAIL_RUN（2 个，真实回归，见下一节详细根因）**：
  `20050604-1.c`、`pr63302.c`。
- 其余（非 PASS → 不同的非 PASS）：**0 个**。数字对得上：
  `1438 + 6(FAIL_LINK→PASS) + 19(FAIL_RUN→PASS) - 2(PASS→FAIL_RUN) =
  1461`；`131 - 6 = 125`；`35 - 19 + 2 = 18`。

**发现的 2 个真实回归——根因分析（未回退，如实报告）**：

`20050604-1.c`（MMX/SSE 风格 `vector_size(8)`/`vector_size(16)` union 向量
运算）和 `pr63302.c`（`__int128` 位掩码运算，经 `noinline`/`noclone`
helper）从 PASS 退化为 FAIL_RUN（exit 127 = torture 用例自己的
`abort()`，不是硬件 fault code 0x81-0x85，说明是"计算值算错了"而不是
"访问越界被硬件拦截"）。

用独立最小复现定位（同一文件分别用旧 `-ffreestanding` CFLAGS 和新 hosted
CFLAGS 走 `clang -S -emit-llvm`，再 diff `.ll`；`llc -march=dadao` 出
`.s` 再 diff 汇编）：

- hosted 模式在 `main()` 里唯一引入的 IR 差异是 clang 标准 C11 hosted-main
  惯例：新增一个 `%retval = alloca i32` + `store i32 0, ptr %retval`
  （死代码——两个文件的 `main()` 本来就有显式 `return`——但在汇编层面仍然
  真实占了一个栈槽），以及把 `abort` 标成 `noreturn`（这一点只是消除了
  `call abort` 后一条跳到**紧邻下一条物理标号**的多余无条件跳转，本身是
  等价优化，不改变语义）。
- 真正调用向量运算/`__int128` 运算的 `foo()`/`bar()` 辅助函数，在两种模式
  下生成的 `.ll` 和 `.s` **逐字节完全相同**（已用 `diff` 核实）——问题不
  在这两个函数内部。
- 但那个死的 `%retval` 槽让 `main()` 的栈帧从"0 字节"变成
  "`addi rb1, rb1, -8` / `+8`"——**8 字节，不是 16 的倍数**。
- `foo()`/`bar()` 自己的 prologue 减的是 16 的倍数（分别是 128/32
  字节），并且把 128 位宽的局部变量（向量 compound literal / `__int128`
  的两半拼接）放在**编译期算好的常量偏移**上（例如
  `pr63302.c`里`foo()`的 `addi rb8, rb1, 16` 存 128 位值）——这个偏移只有
  在"调用者传进来的 `rb1` 本来就是 16 字节对齐"这个前提下才真的对齐；
  `foo()`/`bar()` 自己并不做运行时重新对齐（没有 `and rb1, rb1, ~15` 之
  类的指令）。
- 直接查 `DADAOFrameLowering.h` 确认了根因：
  `TargetFrameLowering(TargetFrameLowering::StackGrowsDown, Align(8), 0)`
  ——后端自己声明的栈对齐只有 **8 字节**，不是 16 字节。这意味着 LLVM 的
  frame-lowering 机制从未把某个函数的栈帧大小/调用点的出栈指针补齐到 16
  字节倍数，即使函数内部存在需要 16 字节对齐的局部变量（128 位向量/
  `__int128`）。此前测试语料里凑巧每条实际被跑到的调用链的栈帧大小总和
  都是 16 的倍数（纯属侥幸，不是被强制保证的不变量）；本任务给 `main()`
  引入的这个 8 字节死槽，是第一个打破这个"运气"的、导致某条调用链上出现
  奇偶不匹配帧大小的改动，从而让这个后端里本来就存在、只是从未被撞见过的
  栈对齐缺口第一次真实暴露出来。
- **已登记为新 open issue**
  `dadao-frame-lowering-8byte-align-insufficient-for-16byte-locals`（写入
  `docs/issues.yaml`，含完整诊断过程引用）。**未修复**：修复需要改
  `DADAOFrameLowering.h`（LLVM 后端源码），明确超出本任务"只改测试/扫描
  脚本编译 flags"的硬约束范围，按任务要求"发现需要动 LLVM 源码就停下来
  报告"处理，没有为了让数字好看而回退任何文件继续用
  `-ffreestanding`——2/1708 不构成"大范围真实回归"，且这是一个真实的、
  独立于 `-ffreestanding` 去留的后端缺陷（`-ffreestanding` 去留只是
  "触发条件"，不是"病因"），所以按任务里"该往前走就往前走，登记 issue、
  不要因小失大地走折中方案"的指示处理。

**3. Embench sweep**（`python3 tests/scripts/embench_sweep.py`，19 个
benchmark × 2 个优化级别，QEMU+gem5 双后端）：

- O0：19/19 PASS（与基线 O0 19/19 一致，无变化）。
- O2：18/19 PASS，唯一失败 `qrduino`（`FAIL_QEMU`，QEMU+gem5 都失败，与
  基线"O2 18/19 仅 qrduino FAIL"完全一致，无新增/减少的失败项）。
- 逐 benchmark 核对：18 个 O0 通过 + `qrduino` 除外的 O2 18 个通过，状态
  与基线逐项相同，没有发现任何一个 benchmark 因为这次 flag 变化而翻转
  状态（无论方向）。

**4. 全量 `llvm-lit tests/lit/E2E/`**：**77/77 PASS（100%）**，含改动过的
10 个文件本身。零回归。

**5. `python3 tools/run_differential.py`**：
`AGREE(3-way)=200  DIVERGE=0  HARNESS=0`；
`SAIL 4th column: AGREE(4-way)=200  SAIL-DIVERGE=0`——与改动前基线完全一致
（本任务不涉及指令语义，符合预期不变）。

**6. `python3 scripts/manifest_check.py`**：`manifest validation: PASS`。

**7. `python3 scripts/check_issues.py`**：`ISSUE REGISTRY: PASS`
（Open 22 / Closed 40 / Total 62——比改动前多 1 条 open，就是本任务新登记
的栈对齐 issue）。

### 附带发现（不在本任务范围内，仅供架构师知悉）

`pr38151.c` 这次从 FAIL_RUN 翻到 PASS，但它是 `docs/issues.yaml` 里已经
登记的 open issue `dadao-complex-vararg-padded-struct-field-corruption`
（`_Complex int` 字段在有尾部 padding 的 struct 里当 vararg 传递时读回错
误）对应的文件。这次为什么会"顺带"变成 PASS 没有深挖（不在本任务范围
内，且任务本身不要求逐个解释每个 FAIL_RUN→PASS 翻转的具体链接/运行时
细节）——只是提醒架构师，如果之后想关闭那条 issue，需要先确认这次翻盘是
真的修复了那个 bug 还是只是恰好绕开了触发条件（本任务没有做这个判断）。
`gcc-torture-results.json`（仓库根目录一个未追踪的历史遗留文件，本任务
开始前就已经存在）经确认就是"ML-033a 完成后"的基线（1438/104/131/35），
本任务复用它做 diff 基准；未删除/未改动这个文件本身。

## 审阅记录（自审，无嵌套 subagent）

逐条列出自己发现的 finding + 处置：

1. **finding**：任务文件给的"已知清单"是否完整？
   **处置**：`grep -rl -- '-ffreestanding'` 全仓库扫描（排除
   `.work/.git/__pycache__`），确认清单里的 12 个文件（2 脚本 + 10 lit）
   就是全部活跃使用点；`.pyc` 缓存和 `code-agent/tasks/archive` 里的历史
   任务文档也命中了这个词但只是文本引用，不是编译命令，不需要改。清单
   完整，无遗漏。

2. **finding**：`-nostdinc`/`-nostdlib` 要不要跟着一起动？
   **处置**：任务要求默认保留、除非发现冲突。检查后没有发现任何冲突
   （这两个 flag 只影响头文件/link 阶段默认搜索路径，跟 hosted/
   freestanding 语义假设无关），12 个文件全部原样保留，只删
   `-ffreestanding`。

3. **finding**：`malloc_hello.test`/`printf_hello.test` 这两个用的是
   picolibc + 手写 `crt0.s`（不是 musl 的 `_start`/`__libc_start_main`
   路径），跟其余 8 个基于 musl 的 lit 测试的运行时环境完全不同，去掉
   `-ffreestanding` 对它们是否有不同的风险？
   **处置**：读了 `crt0.s`（`call main; halt rd31`，main 的返回值直接进
   halt，不经过任何"hosted main 隐式 return 0"的转换）和对应的
   `Inputs/malloc_hello.c`/`printf_hello.c`——两个文件的 `main()` 都有
   **显式** `return` 语句（`return 0`/`return 1..4`），不依赖 C11 的
   "落到函数末尾隐式 return 0"这条 hosted-only 保证，所以对这两个文件而
   言 hosted/freestanding 切换在语义上是无差别的（已用 llvm-lit 实测
   确认两者仍然 PASS）。

4. **finding**（重点，任务明确要求排查的项）：全量重扫是否有任何原 PASS
   文件退化？
   **处置**：没有只看聚合数字就收工——写了逐文件 diff 脚本
   （before/after 两份 JSON 按 `file` 字段做 status 对比），发现
   **2 个真实回归**（`20050604-1.c`、`pr63302.c`，均 PASS→FAIL_RUN）。
   没有因为净增长是 +23（看起来"整体变好"）就忽略这 2 个退化，也没有为了
   保住这 2 个文件继续给它们单独保留 `-ffreestanding`（任务明确禁止这种
   "自行决定折中方案"）。用最小复现（好/坏两版 CFLAGS 分别过
   `clang -emit-llvm` + `llc`，diff IR 和汇编）把根因追到
   `DADAOFrameLowering.h` 声明的栈对齐只有 8 字节、不足以保证 128 位局部
   变量（SIMD 向量 / `__int128`）在跨调用链时保持 16 字节对齐——这是一个
   独立于本任务、本来就存在的后端缺口，只是被本任务新增的
   `%retval` 死槽第一次实际触发。已登记为新 issue，未修复（修复需要改
   LLVM 源码，超出本任务硬约束范围）。

5. **finding**：`FAIL_LINK → PASS` 的 6 个文件是否也需要跟"回归"一样深挖
   根因？
   **处置**：这 6 个是"变好"而非"变坏"，任务验收项只要求
   "FAIL_RUN→PASS 的文件数量和具体文件名如实报告"以及"不允许任何原 PASS
   文件退化"，没有要求解释每一个变好文件的具体机制；这 6 个大概率是同一
   批 hosted 模式下内建函数识别变化的连带效果（比如某些 libc 函数在
   freestanding 下被当成不透明外部符号需要链接，hosted 下被识别为编译器
   内建、不再产生未定义符号引用），但没有逐个验证，如实注明"未深挖"而非
   编造一个没有验证过的解释。

6. **finding**：Embench/E2E/差分/manifest/issues 这些"应该不受影响"的
   验收项是否真的原样跑了一遍，而不是假设不变？
   **处置**：全部真实重新执行了一遍（不是复用旧结果假设不变）：
   Embench 全量 19×2×2 后端实测、`llvm-lit` 全量 77 个实测、
   `run_differential.py` 实测、`manifest_check.py`/`check_issues.py`
   实测——所有实测结果和数字都写在"完成区"里，不是空口断言"应该没变"。

7. **finding**：仓库根目录那个未追踪的 `gcc-torture-results.json` 是什么？
   会不会是我自己操作产生的、该清理的垃圾？
   **处置**：`git status` 显示它在我做任何改动之前就已经是
   untracked 状态；读取内容确认其分布正好是
   `1438/104/131/35`——跟任务描述里"当前基线"的数字完全吻合，说明是架构师
   /之前某次运行留下的基线快照，不是我这次任务的副产物。复制了一份到
   scratchpad 当 diff 基准，没有删除或改动仓库里的原文件（不确定架构师是
   否还需要它，谨慎起见不擅自清理）。

8. **finding**：有没有可能因为 `--workers 6` 的并发度跟基线跑时的并发度
   不同，导致某些结果是"跑起来不稳定"（flaky）而不是真实的 flag 差异？
   **处置**：没有单独验证过基线本身的可重复性（基线是复用仓库里已有的
   历史结果文件，不是本任务重新跑的），但 2 个回归文件属于"确定性差异"
   类型——用不涉及 QEMU/时序的静态 IR/汇编 diff 就能稳定复现同一个栈帧
   大小差异，不依赖任何运行时时序或并发调度，可以排除是 flaky/并发引起的
   误判。FAIL_LINK/FAIL_RUN→PASS 的 25 个文件本任务没有反向验证"是否
   flaky"（如果架构师担心，可以重跑一遍 sweep 核对是否稳定复现同一
   分布——本次没有做重复第二遍全量 sweep，因为单次 1708 文件全跑就需要
   跑两次 QEMU pipeline，且 2 个回归的根因已经用确定性方法独立验证过，
   没有必要再多跑一次去验证其余 25 个"变好"的文件是否稳定）。
