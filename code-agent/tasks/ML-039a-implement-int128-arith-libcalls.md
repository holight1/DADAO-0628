# ML-039a：补齐 `__int128` 算术 libcall 缺口（`__fixsfti`/`__udivti3` 起步）

**执行环境**: 本地 subagent

## 硬约束（务必遵守，违反视为任务失败）

- **禁止**对 `.work/source/musl` 做 `git rebase`/`git am` 重放整条历史/
  `git reset --hard`。只允许在当前 HEAD 基础上新增普通 `git commit`。
- **先摸清真实范围，再动手**——`docs/issues.yaml`
  `musl-softfloat-shim-missing-int128-arith-libcalls` 里明确写了"未审计
  compiler-rt 定义的 128 位算术 libcall 全集 vs. gcc-c-torture 语料库
  实际用到几个"，本任务第一步是**在全量 gcc-c-torture 重扫的 FAIL_LINK
  分类里 grep 所有含 `ti`/`ti2`/`ti3`/`ti4` 后缀（compiler-rt 128 位宽
  libcall 命名惯例）的 undefined symbol**，摸清真实需要实现的符号集合，
  不要只做 `__fixsfti`/`__udivti3` 这两个已确认的就收工，也不要没摸清楚
  范围就开始实现。
- **方法论沿用 `softfloat_shim.c` 已有约定**（`ML-022a`/`ML-025a`/`ML-028a`/
  `ML-037a`）：纯位模式运算实现（`__udivti3` 是无符号 128 位整数除法，
  不涉及浮点，但同样不能调用原生 128 位 `/` 运算符——需要确认 DADAO
  后端本身是否已经支持 `i128` 的原生 `udiv`/`urem` legalization，如果
  后端自己就能生成正确代码只是缺运行时符号，这个符号的实现可以直接用
  C 语言的移位减法长除法算法，不需要位模式技巧；如果后端对 `i128` 除法
  的 legalization 本身有问题，如实诊断报告，不要在错误的假设上硬写代码）、
  反汇编确认无自递归、fuzz + 显式边界值 + 负控制。
- **完成后立即导出 patch**（不要延后），追加进对应 `series`。
- 完成后必须在任务文件里写「完成区」+ subagent 自审「审阅记录」（含逐条 finding
  + 判决）。

## 背景

`ML-038a` 修复 `__int128` 返回值 CallingConv 崩溃后，`pr49218.c`/`pr84748.c`
两个文件从编译期崩溃变成链接期缺符号：`__fixsfti`（`float`→`__int128`
转换）、`__udivti3`（无符号 128 位除法）。这暴露出 `softfloat_shim.c`
从未实现任何 `__int128` 相关的 compiler-rt libcall——此前这类符号缺口一直
被更前置的编译期崩溃掩盖，从未真正被链接阶段触达过。

架构师已独立复现两个具体链接错误：

```
ld.lld: error: undefined symbol: __fixsfti
>>> referenced by pr49218.c:(main)
ld.lld: error: undefined symbol: __udivti3
>>> referenced by pr84748.c:(foo)
```

## 目标

1. **摸清范围**：全量 `gcc-c-torture` 重扫（当前基线 `1471/96/126/15`），
   在 126 个 `FAIL_LINK` 文件里逐一识别 undefined symbol，筛出所有
   `ti`/`ti2`/`ti3`/`ti4` 后缀的 128 位宽 libcall（`compiler-rt` 命名
   惯例参考 `.work/source/llvm/compiler-rt/lib/builtins/` 目录下
   `*ti3.c`/`*ti2.c` 等文件名），统计每个符号被几个文件引用。
2. **逐个实现**：按 `compiler-rt` 对应源文件的算法逻辑重写成
   `softfloat_shim.c` 风格（纯位模式/整数运算，不引入自递归，参照上面
   硬约束的方法论）。不要求本任务必须覆盖 `compiler-rt` 定义的全部
   128 位 libcall——只需要覆盖本次 gcc-c-torture 重扫实际暴露出的需求，
   多余的可以不做，但要在完成区写清楚"实现了哪些、还有哪些
   compiler-rt 有但本语料库未触达、未实现"。
3. **验证**：反汇编确认无自递归；fuzz + 显式边界值（0、全 1、符号相关的
   边界如 `INT128_MIN`、除以 1、除以自身等）+ 负控制，对拍原生 128 位
   算术（宿主机 GCC/Clang 通常原生支持 `__int128`，可以直接用宿主机
   编译对拍，不需要额外软件模拟）。

## 验收

- `docs/issues.yaml` `musl-softfloat-shim-missing-int128-arith-libcalls`
  提到的 `pr49218.c`/`pr84748.c` 用 `python3 tests/scripts/
  gcc_torture_sweep.py --filter "pr49218|pr84748"` 重跑，确认转 PASS
  （如果范围摸查后发现还有其它文件依赖同类符号，一并覆盖并如实报告）。
- 反汇编确认新增函数无自递归 `call`。
- fuzz + 显式边界值测试，对拍宿主机原生 128 位算术结果，含负控制。
- 全量 `gcc-c-torture` 重扫（当前基线 `1471/96/126/15`），逐文件 diff
  确认零回归。
- 全量 `llvm-lit tests/lit/E2E/`（当前基线 79/79）：零回归。
- `python3 tools/run_differential.py`：AGREE 数与当前基线一致、DIVERGE=0。
- `python3 scripts/manifest_check.py`/`check_issues.py` 通过；
  `musl-softfloat-shim-missing-int128-arith-libcalls` 状态更新为 closed
  并迁移到 `docs/issues-archive.yaml`（如果摸查后确认还有 compiler-rt
  定义但本语料库未触达的符号未实现，可以在关闭说明里如实注明"仅覆盖本次
  暴露的需求"，不必因此阻塞关闭）。
- musl 侧改动用**普通** `git commit` 落地，`git format-patch` 导出对应
  patch，追加进 `series`；独立验证可在干净 pin-commit checkout 上 `git am`
  成功，且 replay tree 与开发树 tree hash 一致。

## 参考指针

- `docs/issues.yaml` `musl-softfloat-shim-missing-int128-arith-libcalls`
  （完整背景，架构师已独立复现的两个具体链接错误）
- `.work/source/llvm/compiler-rt/lib/builtins/`（`fixsfti.c`/`udivti3.c`
  等权威参考实现，命名惯例可以据此枚举其它可能需要的符号）
- `src/internal/dadao/softfloat_shim.c`（现有符号写法风格，`ML-022a`/
  `ML-025a`/`ML-028a`/`ML-037a` 建立的方法论）
- `.work/source/llvm-test-suite/SingleSource/Regression/C/gcc-c-torture/execute/
  {pr49218,pr84748}.c`（原始复现源码）
- `code-agent/tasks/ML-037a-implement-divsc3-softfloat-shim.md` 完成区
  （最近一次同类符号缺口任务的方法论范本，包括 fuzz oracle 选择的踩坑
  记录——原生宿主机运算符可能启用 FMA 等编译器优化导致假阳性不一致，
  `__int128` 整数运算没有这个问题但如果后续任务涉及 128 位浮点转换要
  留意类似陷阱）
- `feedback_volatile_needed_for_memory_verification_tests`（如果验证测试
  涉及写读回校验，记得用 volatile + 负控制）

## 完成区（2026-07-25）

### 1. 摸清范围

对 `gcc-torture-results.json`（全量 1708 文件，1471/96/126/15 基线）的
126 个 `FAIL_LINK` 条目逐一解析 `stderr` 里的 `undefined symbol: X`，筛出
后缀匹配 `ti`/`ti2`/`ti3`/`ti4` 的 compiler-rt 128 位 libcall 命名。结果：

| 符号 | 引用文件数 | 文件 |
|---|---|---|
| `__fixsfti` | 1 | `pr49218.c` |
| `__udivti3` | 1 | `pr84748.c` |

**全部 126 个 FAIL_LINK 文件里，除了这 2 个已知符号，不存在任何其它
`*ti*` 后缀的 undefined symbol**——用两种方式交叉核实：(a) 对每个文件的
`undefined symbol: X` 逐条正则提取后按后缀过滤；(b) 对全部 stderr 文本
做一次不区分文件的宽口径 grep（`\w*ti[234]?\b` 紧跟在
`undefined symbol:` 之后）。两种方式结果一致，`docs/issues.yaml` 原条目
里列出的"未审计的 compiler-rt 128 位 libcall 全集"
（`__divti3`/`__modti3`/`__umodti3`/`__fixdfti`/`__fixunssfti`/
`__fixunsdfti`/`__floattisf`/`__floattidf`/`__floatuntisf`/
`__floatuntidf`/`__muloti4` 等）**在本语料库当前 126 个 FAIL_LINK 里一个
都未被引用**，不实现，留给未来若有文件真正需要时再补。

其余 124 个非 `*ti*` undefined symbol（`main`/`inside_main` 等大量条目
是"分离编译辅助文件缺少 main"或跟本任务无关的既有已知缺口，如
`setjmp`/`longjmp`/`__builtin_apply`/`__memcpy_chk` 系列等）不属于本任务
范围，未触碰。

### 2. 实现

`.work/source/musl/src/internal/dadao/softfloat_shim.c` 追加两个函数
（commit `0b1e006c`，`git format-patch` 导出为
`components/musl/patches/0015-dadao-add-__fixsfti-__udivti3-__int128-arithmetic-li.patch`，已追加进
`series`）：

- **`__udivti3`**（无符号 128 位除法）：128 次迭代的移位-减法恢复除法
  （不实现 compiler-rt `udivmodti4.c` 的 Knuth Algorithm D 64 位除数快速
  路径——该路径的 `__builtin_clzll(divisor.s.high)` 在
  `divisor.s.high == 0` 时是未定义行为，正是它要特判的那个 case，本语料
  库唯一一处除法（`pr84748.c`，除数恒为 0 或 1）不需要这个优化）。全程
  只用原生 `unsigned __int128` 的加/减/比较/移位，**从不对 128 位操作数
  用 `/` 或 `%`**（自递归陷阱：独立探针确认 `a / b`（`unsigned __int128`）
  在 DADAO target 上确实会生成 `undefined symbol: __udivti3`，即在函数
  体内写 `/` 会递归调用自己）。

- **`__fixsfti`**（`float`→`__int128`）：现有 `__fixsfti`（正确，是
  `__fixsfdi`，float→`long long`)的直接位宽扩展，同一套 compiler-rt
  `fp_fixint_impl.inc` 算法/饱和边界，复用已有 `F32_*` 位模式宏。

- **探针确认**（`clang --target=dadao -c` + `llvm-nm -u`）：原生
  `unsigned __int128`/`__int128` 的加/减/比较/位移（含变量位移量）在
  DADAO 后端上全部内联展开、**不引入任何新 undefined symbol**（不像
  `/` 那样会打洞到 `__udivti3`）——所以两个函数的实现自由使用原生
  128 位算术（除 `/`/`%` 外），比强行手搓 64 位半字拼接更贴近 compiler-rt
  原始参考实现、更易审查，同时不牺牲安全性。

### 3. 验证

- **反汇编**：`llvm-objdump -d --triple=dadao` 对
  `.work/build/musl/obj/src/internal/dadao/softfloat_shim.o` 里
  `__udivti3`/`__fixsfti` 两段反汇编逐行核对，**零 `call` 指令**（该 ISA
  的调用助记符是 `call`，在文件其它函数如 `__divsc3` 里能看到，但不出现
  在这两个新函数体内）；`llvm-nm -u` 对整个 `.o` 文件输出为空，确认零
  undefined symbol（无自递归，也未引入任何新的隐藏依赖）。

- **fuzz + 边界值 + 负控制**（宿主机 `gcc -O2` 和
  `gcc -O0 -fsanitize=undefined,address` 各跑一遍，两者结果一致）：
  - `__udivti3`：显式边界（`0/1`、`1/1`、全 1 操作数、`MSB/1`、
    `MSB/MSB`、自除、跨字/宽除数等 16 组）+ 40 万次随机 128 位对拍
    （`a/b` 用宿主机原生 `unsigned __int128 /`）+ 额外 20 万次窄除数
    (`b` 限制在 64 位内，压测优化路径边界）——**0 处不一致**。
  - `__fixsfti`：显式边界（±0、±1、±0.5、0.999、±1.5、2、
    `16777215`(0xFFFFFF)、`8388608`(2^23)）+ 4 个"接近 1e30/1e18"的显式
    大值 + 20 万次随机浮点位模式 fuzz（限制在有明确定义结果的区间内，
    即 `|f| < 2^126`，避开 compiler-rt 自身在 `[2^127,2^128)` 这个边界
    区间就不完全饱和的已知怪癖——见下方"已知的 compiler-rt 边界行为"）
    + subnormal 遍历——**0 处不一致**，对拍宿主机原生 `(__int128)float`
    强制转换。
  - **负控制**：两个"故意写错"的对照版本（`buggy_udivti3` 循环边界写成
    64 而不是 128；`buggy_fixsfti` 指数偏置故意错一）都被同一套 fuzz
    harness 抓到差异，证明比对方法论本身是有效的，不是形式主义空跑。
  - harness 源码：
    `/tmp/claude-1000/-home-holight/9d0a7e60-2718-445f-9a83-ccf36348e840/scratchpad/ml039a/host_verify.c`
    （宿主机独立小程序，不属于本任务交付物，仅作验证记录）。

  **已知的 compiler-rt 边界行为（如实报告，非本任务引入）**：`__fixsfti`
  忠实照抄 compiler-rt `fp_fixint_impl.inc` 的饱和判断
  (`exponent >= 128` 才饱和)，在 `exponent == 127`（数值接近
  `FLT_MAX`，量级 ~3.4e38，远超 `INT128_MAX` ~1.7e38）这个窄区间内不会
  干净地饱和到 `INT128_MAX`/`INT128_MIN`——这是 upstream compiler-rt 本
  身的既有行为（`softfloat_shim.c` 里原有的 `__fixsfdi` 在 64 位宽度上
  也有对应的同构边界），而且这个区间内"浮点转整数溢出"本身在 ISO C
  （6.3.1.4p1）里就是未定义行为，宿主机原生转换同样没有"标准定义的正确
  答案"可比对。`pr49218.c` 只会转换 `0.0f`，不会触达这个区间。未修改
  这个边界判断，保持与 compiler-rt/现有 `__fixsfdi` 一致，仅在代码注释
  和本节里如实记录。

- **`pr49218.c`/`pr84748.c` 目标验收**：
  `python3 tests/scripts/gcc_torture_sweep.py --filter "pr49218|pr84748"`
  → 两个都 `PASS`（真实走完 `clang -> ld.lld -> objcopy -> QEMU` 全链路，
  之前是 `FAIL_LINK`）。

- **全量 gcc-c-torture 重扫**：`1473/96/124/15`（基线 `1471/96/126/15`）。
  逐文件 diff（1708 个文件的 status 一一比对）：**只有 `pr49218.c`/
  `pr84748.c` 两个文件从 `FAIL_LINK` 变成 `PASS`，其余 1706 个文件状态
  完全不变，零回归**。结果已写回 `gcc-torture-results.json`（根目录，
  未 git add，留给架构师复核）。

- **`llvm-lit tests/lit/E2E/`**：`79/79` PASS，与基线一致，零回归。

- **`python3 tools/run_differential.py`**：`AGREE(3-way)=200`、
  `AGREE(4-way)=200`、`DIVERGE=0`/`SAIL-DIVERGE=0`——与基线完全一致（本
  任务只改 musl 运行时符号，不触碰 ISA 语义，符合预期不受影响）。

- **`python3 scripts/manifest_check.py`**：PASS。
  **`python3 scripts/check_issues.py`**：PASS（`Open: 21`，
  `Closed: 43`，`musl-softfloat-shim-missing-int128-arith-libcalls` 已
  从 `docs/issues.yaml` 移除、以 `status: closed` +
  `resolved_by: "ML-039a; musl patch 0015-..."` 追加进
  `docs/issues-archive.yaml`）。

- **patch 独立验证**：在 `0784374d561435f7c787a555aeab8ede699ed298`
  （musl pin commit）上新建 `git worktree`，`git am` 全部 15 个 series
  patch（含新的 `0015-...patch`）**全部无冲突应用成功**；replay 出的
  tree（`cc30c01ea656b071595dac266406ebe12e311ad3`）与开发树（`.work/
  source/musl` HEAD `0b1e006c` 的 tree）**哈希完全一致**。worktree 用后
  已 `git worktree remove` 清理。

### 4. 根仓库层面改动（未 commit，留给架构师复核）

按指示，musl 侧改动已在 `.work/source/musl` 用普通 `git commit` 落地，
但根仓库（`DADAO-0628`）层面的以下文件改动**只做了编辑，未 git add /
commit**，留在工作区：

- `docs/issues.yaml`：移除 `musl-softfloat-shim-missing-int128-arith-libcalls` 条目
- `docs/issues-archive.yaml`：追加该条目的 closed 版本（含完整解决记录）
- `components/musl/patches/0015-dadao-add-__fixsfti-__udivti3-__int128-arithmetic-li.patch`（新文件，未 add）
- `components/musl/patches/series`：追加 `0015-...patch` 一行
- `gcc-torture-results.json`（根目录，未跟踪文件）：刷新为本次全量重扫的最新结果（`1473/96/124/15`）

## 审阅记录（subagent 自审）

逐条自查如下，均判定为"通过"，未发现需要打回重做的问题：

1. **范围摸查是否真的做了，而不是走过场？** —— 通过。用两种独立方式
   （逐文件正则提取 + 全文本宽口径 grep）交叉核实 126 个 FAIL_LINK 里
   `*ti*` 后缀符号只有 `__fixsfti`/`__udivti3` 各 1 处引用，结果一致；
   没有跳过这一步直接开始写代码。

2. **是否真的避开了自递归陷阱，而不是想当然？** —— 通过。没有假设
   "division 会自递归"就直接绕过，而是先用独立探针实证：(a) 确认
   `a / b`（`unsigned __int128`）确实会生成
   `undefined symbol: __udivti3`（证实陷阱真实存在，不是继承自其它
   target 的传言）；(b) 确认加/减/比较/移位不会（`llvm-nm -u` 空输出），
   这一步让实现可以放心使用原生 128 位算术而不是被迫手搓 64 位拼接，
   同时有真实探针证据支撑，不是猜测。

3. **反汇编核实是否只看了"有没有报错"，还是真的读了每条指令？** ——
   通过。逐行读取了 `__udivti3`（0x0-0x104）和 `__fixsfti`
   （0x0 起）两段完整反汇编，确认助记符里没有出现 `call`（该 ISA 的调用
   指令），且用 `grep -n "call"` 对整个反汇编文件做了行号级核对，确认
   两个函数的行号区间内零命中，而 `call` 助记符确实在文件其它地方
   （`__divsc3` 调用 `__addsf3` 等）出现过，证明这不是"这个 ISA 反汇编器
   压根不认识 call 指令"这种假阳性。

4. **fuzz 对拍是否选对了 oracle？** —— 通过，并且吸取了 ML-037a 任务
   文件提到的"FMA 假阳性"教训主动避坑：`__udivti3` 是纯整数运算，宿主机
   `unsigned __int128 /` 没有 FMA 这类浮点重排问题，可以直接全域对拍
   （已做 40 万+20 万次）；`__fixsfti` 涉及浮点转整数，主动把 fuzz 范围
   限制在"两边都有明确定义结果"的区间（`|f| < 2^126`），避开
   `[2^127,2^128)` 这个 compiler-rt 自身也不担保饱和、ISO C 也判 UB 的
   窄边界，而不是硬要在 UB 区间"对拍出一个结论"（那样对比出的"不一致"
   毫无意义，对比出"一致"也不能说明什么）。

5. **负控制是否真的验证了"测试方法论有效"，而不是摆设？** —— 通过。
   两个函数各写了一个独立的"故意错"变体（循环边界写错 / 指数偏置写错），
   跑同一套比对逻辑，确认真的会报不一致（"CAUGHT"），而不是"写了负控制
   但从没跑过/跑了但没看输出"。

6. **是否只做了 2 个已知符号就收工，还是真的按硬约束摸清了范围？** ——
   通过，见上面第 1 条 + 完成区"1. 摸清范围"一节，摸查结果确认范围就是
   这 2 个，如实记录进 `docs/issues-archive.yaml` 的关闭说明（未夸大也
   未缩小范围）。

7. **是否违反了"不对 `.work/source/musl` 做 `git rebase`/`git am` 重放
   整条历史/`git reset --hard`"这条硬约束？** —— 通过。全程只在当前
   HEAD（`69cadae0`）上新增了一个普通 `git commit`（`0b1e006c`），没有
   动过历史；`git am` 只在**新建的、独立的临时 worktree**（检出 pin
   commit 后重放 series 做独立验证）里执行，验证完立即
   `git worktree remove` 清理，**没有在 `.work/source/musl` 主工作区
   本身执行过 `git am`**，不违反硬约束的字面和精神。

8. **是否直接 commit 到了 DADAO-0628 根仓库？** —— 通过，未 commit。
   `docs/issues.yaml`/`docs/issues-archive.yaml`/`components/musl/
   patches/series`/新 patch 文件/`gcc-torture-results.json` 都只做了
   工作区编辑，`git status` 确认根仓库没有任何 staged/committed 改动，
   留给架构师复核。

9. **验收清单（任务文件"验收"一节）是否逐条跑过，而不是挑着跑？** ——
   通过，9 条验收标准（filter 重跑转 PASS / 反汇编无自递归 / fuzz+边界
   +负控制 / 全量重扫零回归 / lit 79/79 / differential 一致 /
   manifest_check+check_issues 通过+issue 迁移 / patch 导出+series /
   pin-commit 独立 `git am`+tree hash 一致）逐条执行并在"完成区"记录了
   对应的实测结果，没有跳过任何一条。

**结论**：任务目标（摸清范围 + 实现 + 验证）均达成，未发现需要打回或
转交架构师处理的阻断性问题。
