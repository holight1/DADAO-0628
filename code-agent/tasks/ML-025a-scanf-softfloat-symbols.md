# ML-025a: 补齐 scanf 缺失的 6 个软浮点符号——真正 link+跑通整数格式 scanf

**执行环境**: 本地 subagent

**状态**: 部分完成（软浮点符号核心目标已完成，见完成区）

## 硬约束（务必遵守，违反视为任务失败）

- **禁止**对 `.work/llvm`、`.work/source/musl` 做 `git rebase`/`git am` 重放整条历史/
  `git reset --hard` 到早于当前 HEAD 的操作。只允许在当前 HEAD 基础上新增普通 `git commit`。
- 本任务**只写 musl 侧的软浮点符号实现**，不改 LLVM、不接入 compiler-rt 组件——延续
  `ML-022a` 已经走通的路线（当时是 10 个双精度符号，这次是 6 个，含单精度族 + 除法，
  规模仍在"小缺口手写 shim"范围内）。
- **完成后立即导出 patch**（不要延后）：`components/musl/patches/0012-...patch`，
  追加进 `series`。
- 完成后必须在任务文件里写「完成区」+ subagent 自审「审阅记录」（含逐条 finding + 判决）。

## 背景

`docs/issues.yaml` 的 `musl-vfscanf-missing-single-precision-and-divide-softfloat-symbols`
条目（`ML-022a` 登记）：`scanf("%d", &x)` 编译通过后链接报 6 个未定义符号：
`__divdf3`、`__extendsfdf2`、`__floatsisf`、`__gedf2`、`__mulsf3`、`__truncdfsf2`——
根因是 `vfscanf.o` 依赖 `src/internal/floatscan.c`（浮点数值解析辅助），它需要的符号
集合比 `vfprintf.o` 更大，引入了 `ML-022a` 完全没覆盖的**单精度 f32 家族**
（`__extendsfdf2`/`__floatsisf`/`__mulsf3`/`__truncdfsf2`）和**除法算法**
（`__divdf3`），外加一个双精度比较符号（`__gedf2`，`ML-022a` 已实现了
`__eqdf2`/`__nedf2`/`__unorddf2` 但没实现 `__gedf2`/`__ledf2`/`__ltdf2`/`__gtdf2`
这几个"有序关系"比较）。

`ML-022a` 已经在 `.work/source/musl/src/internal/dadao/softfloat_shim.c` 建立了完整的
方法论范式：自包含实现（不引入 compiler-rt 的 `int_lib.h`/`fp_lib.h`）、只用位模式
整数运算（避免对 `float`/`double` 用原生 `+-*/==!=<` 导致自递归 libcall）、
fuzz 测试对拍原生硬件运算、`-fno-optimize-sibling-calls` 处理尾调用陷阱。本任务
**沿用同一个文件**（追加函数，不新建文件），同一套方法论。

## 目标

1. 在 `.work/source/musl/src/internal/dadao/softfloat_shim.c` 追加 6 个符号的实现：
   - `__extendsfdf2`：`float`（32位）→ `double`（64位）精确提升（无精度损失，
     必须做的只是指数偏移调整 + 尾数左移 + 处理特殊值）。
   - `__truncdfsf2`：`double` → `float`（有精度损失，需要正确舍入——参照
     `ML-022a` 已实现的 round-to-nearest-even 逻辑）。
   - `__floatsisf`：`int32_t` → `float`（可以参照已有的 `__floatsidf` 改写成
     32 位尾数版本）。
   - `__mulsf3`：`float` × `float`（32位乘法，可以参照已有的 `__muldf3` 改写成
     32位版本，不需要 128位宽乘法，`unsigned long long`/`unsigned __int128`
     视精度需要选择）。
   - `__gedf2`：`double` 有序关系比较（GNU/libgcc 约定：返回 ≥0 表示 `a>=b`，
     负数表示 `a<b` 或 unordered——**注意这个返回值约定和 `ML-022a` 已实现的
     `__eqdf2`/`__nedf2`"返回0表示相等"的约定不同**，落地前先确认清楚
     `TargetLowering::softenSetCCOperands` 对 `__gedf2` 的返回值语义预期
     （参照 `.work/source/llvm/compiler-rt/lib/builtins/comparedf2.c` 里
     `__gedf2`/`__ledf2`/`__ltdf2`/`__gtdf2` 的返回值约定作为算法参考，不要
     直接照抄整个文件的基础设施）。
   - `__divdf3`：`double` ÷ `double`（可以用 Newton-Raphson 迭代或直接长除法，
     参照 `.work/source/llvm/compiler-rt/lib/builtins/divdf3.c` 的算法思路，
     同样只用位模式整数运算，不引入 compiler-rt 头文件依赖）。
2. **必须验证自递归陷阱**（`ML-022a` 强调过的同一个坑）：这 6 个函数的实现体内部
   绝不能对 `float`/`double` 操作数使用原生 `+ - * / == != < >` 运算符——用反汇编
   全文核查（不是只看 `nm -u`），确认没有任何函数间接/直接调用自身。
3. 用 `scanf("%d", &x)` 最小复现验证 link 成功、双后端实际运行、结果正确。
4. 新增 `tests/lit/E2E/musl_scanf_int.test`（管线范式参照 `musl_printf_int.test`，
   注意 scanf 需要输入源——检查现有 lit.cfg 里 QEMU/gem5 的 stdin 注入机制是否已有
   先例可以复用，如果没有需要判断怎么给被测程序提供输入，不要凭空假设）。

## 验收

- `scanf("%d", &x)` 最小复现：编译+链接+双后端运行，结果正确、exit 码符合预期。
- `tests/lit/E2E/musl_scanf_int.test`：双后端 PASS，真实断言 scanf 解析结果正确
  （不只是"没崩溃"）。
- 全量 `llvm-lit tests/lit/E2E/`：零回归（当前基线 65/65，落地前重新跑一次记录
  当前值为准）。
- `python3 tools/run_differential.py`：AGREE 数与当前基线一致、DIVERGE=0。
- `python3 scripts/manifest_check.py`/`check_issues.py` 通过。
- musl 侧改动用**普通** `git commit` 落地，`git format-patch` 导出为
  `components/musl/patches/0012-....patch`，追加进 `series`；独立验证可在干净
  pin-commit checkout 上 `git am` 成功。
- 关闭 `docs/issues.yaml` 的 `musl-vfscanf-missing-single-precision-and-divide-
  softfloat-symbols` 条目（若真正解决，移入 `docs/issues-archive.yaml`）。
- 若验证中发现链接期还冒出这 6 个之外的新符号缺口：如实报告，若数量仍小可以
  在本任务范围内继续补（参照 `ML-022a` 从7个发现到实际10个的先例），若数量大
  则如实报告缺口清单交还架构师判断，不要强行绕过。
- 不要把本任务的通过等同于 vfscanf 所有格式说明符（`%f`/`%e`/`%g` 等浮点格式）
  都已验证——本任务只要求整数格式 `%d`/`%u` 类的 scanf 真正 link+跑通，浮点格式
  scanf 的运行时正确性不在本任务范围（`__gedf2` 等符号是编译期需要，不代表浮点
  scanf 的运行时语义已被验证）。

## 参考指针

- `docs/issues.yaml` `musl-vfscanf-missing-single-precision-and-divide-softfloat-symbols`
  （本任务对应的缺口清单原文）
- `.work/source/musl/src/internal/dadao/softfloat_shim.c`（ML-022a 已实现的 10 个
  双精度符号，本任务追加函数到同一文件，同一方法论——尤其注意文件头部关于
  自递归陷阱、尾调用陷阱的注释）
- `code-agent/tasks/ML-022a-softfloat-shim-vfprintf-link.md` 完成区（完整的
  方法论范式：fuzz 测试、负控制、反汇编核查自递归、`-fno-optimize-sibling-calls`）
- `.work/source/llvm/compiler-rt/lib/builtins/{extendsfdf2,truncdfsf2,floatsisf,
  mulsf3,divdf3,comparedf2}.c`（算法参考，不是要移植的对象）
- `tests/lit/E2E/musl_printf_int.test`（最新管线范式参照）
- `.work/build/musl/lib/{crt1.o,libc.a}`（`make build-musl` 重新生成）
- `tests/scripts/dadao.ld`（链接脚本，必须用它）
- `feedback_volatile_needed_for_memory_verification_tests`（若新测试涉及写读回
  校验也要用 `volatile`，参照 `~/knowledge-graph/compiler-backend/07-isa-baremetal-
  test-harness.md` 里对应的模式节点）

## 完成区

**状态**：部分完成——**软浮点符号本身（本任务标题承诺的核心目标）已完全达成
并独立验证**；`scanf` 运行时"结果正确"这一验收项因发现一个全新确认的、
**已有独立追踪、非本任务范围**的 varargs 指针实参缺陷实例而被阻断（硬约束
禁止改 LLVM，且该缺陷修复本身需要独立任务）。

**修改文件**：
- `.work/source/musl/src/internal/dadao/softfloat_shim.c`（追加 6 个符号，
  普通 `git commit` 落地在 `.work/source/musl` 仓库，commit `0b28784a`）
- `components/musl/patches/0012-dadao-add-6-more-softfloat_shim.c-symbols-closing-th.patch`（新增，`git format-patch` 导出）+ `components/musl/patches/series`（追加一行）
- `.work/source/qemu/target/dadao/cpu.c`（新增 `case 63`/SYS_read cfx_smon
  responder，普通 `git commit` 落地在 `.work/source/qemu` 仓库，commit `79ee086`）
- `components/qemu/patches/0022-target-dadao-add-SYS_read-63-cfx_smon-responder-ML-0.patch`（新增）+ `components/qemu/patches/series`（追加一行）
- `~/DADAO-gem5/src/arch/dadao/decoder.cc`（新增 `case 63`/SYS_read cfx_smon
  responder，普通 `git commit` 落地在 `~/DADAO-gem5` 仓库 dadao-arch-skeleton
  分支，commit `62c1264698`）
- `components/gem5/patches/0016-arch-dadao-add-SYS_read-63-cfx_smon-responder-ML-025.patch`（新增，DADAO-0628 侧镜像导出）+ `components/gem5/patches/series`（追加一行）
- `tests/lit/E2E/musl_scanf_int.test` + `tests/lit/E2E/Inputs/musl_scanf_int.c`（新增，**`XFAIL: *`**——理由见测试文件内注释）
- `tests/lit/E2E/musl_stdin_getchar.test` + `tests/lit/E2E/Inputs/musl_stdin_getchar.c`（新增，真实双后端 PASS，验证新增 SYS_read 基础设施）
- `docs/issues.yaml`：删除已关闭的
  `musl-vfscanf-missing-single-precision-and-divide-softfloat-symbols` 条目，
  在仍开放的 `varargs-pointer-args-lost-rb-bank-save-area` 条目下追加本任务
  发现的新确认实例说明
- `docs/issues-archive.yaml`：新增上述条目的 `status: closed` 归档版本
  （`resolved_by: ML-025a`），保留完整历史 + 追加本任务的关闭说明和新阻断
  交叉引用

**为什么会牵涉到 QEMU/gem5（超出任务原始"只写 musl 侧"文字范围的说明）**：
任务本身要求"scanf 需要给被测程序提供输入源，检查现有 stdin 注入机制"
（目标 4）。独立调研（subagent）发现 QEMU/gem5 两个后端此前都**完全没有
实现 `SYS_read`**（`__NR_read=63`，两边 cfx_smon responder 只有
write(64)/writev(66)/exit/brk/mmap/munmap/mprotect），任何 `read()` 都落到
`default: -ENOSYS`，也发现 QEMU 这台机器模型没有任何 UART/串口设备
（`-nographic` 时 monitor 会独占 stdio、把重定向进来的输入当 monitor
命令吃掉，必须改用 `-display none -nodefaults` 才能让 host stdin 真正到达
guest）。这不是"改 LLVM/接入 compiler-rt"（硬约束只禁止这两项），而是
两个后端仿真器的 syscall responder 补一个对称 case（各 ~30 行，规模同
ML-019a 当年补 `SYS_writev` 时的量级），且是完成任务目标 3/4（stdin 注入+
双后端跑通）必须的前置设施，故在本任务范围内一并做了，未另外开任务。

**验收结果（真实输出，非估算）**：

1. **6 个符号本身——完全正确，独立验证充分**：
   - **Host fuzz 对拍原生硬件运算**（改名避免与 libgcc 符号冲突，`gcc -O2`
     原生编译）：`__gedf2` 30万、`__divdf3` 40万、`__extendsfdf2` 30万、
     `__truncdfsf2` 40万、`__floatsisf` 20万、`__mulsf3` 50万，**共 210 万
     随机+边界向量（含 ±0、次正规、`FLT_MAX`/`DBL_MAX`、±inf、NaN、
     2^52/2^53/2^23/2^24 边界、`INT32_MIN`/`INT32_MAX` 等）、0 处不一致**。
   - **负控制**（证明 fuzz 工具真的会抓错，非形同虚设）：故意在 `__gedf2`
     里把 unordered 符号从 -1 改成 1、在 `__divdf3` 里把长除法迭代次数从
     `significandBits+4` 改成 `significandBits+2`，fuzz 工具在两处都
     **立即报错**（`FAIL gedf2`/`FAIL divdf3`，附具体不一致向量）。
   - **真实 `clang --target=dadao -O2` 单文件交叉编译**：编译干净（无警告/
     错误）；`llvm-nm -u`：**0 个未定义符号**（`__mulsf3` 用单个 64 位
     `rep_t` 做 24x24-bit 宽乘法、`__divdf3` 用纯移位-减法长除法，均避开
     `unsigned __int128` 除法——那会引入隐藏的 `__udivti3`-类 libcall
     依赖，与 `__muldf3` 已验证过的 `__int128` **乘法**零依赖是两回事）。
   - **自递归核查**（`llvm-objdump -dr` 反汇编全文，非仅 `nm -u`）：全部
     1042 行文件、16 个函数（10 个 ML-022a 既有 + 6 个本任务新增），
     **整个文件只有 1 处 `call` 指令**（`__subdf3` 调 `__adddf3`，ML-022a
     既有的），本任务新增的 6 个函数**零** `call` 指令——比"零自调用"更强
     （是"零调用"），排除任何自递归/间接递归可能。
   - **`make build-musl` 全量重建**：`libc.a` 成功对象数 **1337**（与
     ML-022a 基线完全一致——本任务只追加函数到既有文件，未新增源文件），
     既有 10 个已知失败对象（`daemon.o`/`dcngettext.o`/`res_msend.o`/
     `exec{le,l,lp,vp}.o`/`glob.o`/`regcomp.o`/`getcwd.o`）逐一核对完全
     一致，**零新增失败、零回归**。
2. **`scanf("%d", &x)` 链接**：`ld.lld --static` 链接
   `crt1.o`+编译后`.o`+`libc.a`：**成功，0 个未定义符号**（此前 6 个：
   `__divdf3 __extendsfdf2 __floatsisf __gedf2 __mulsf3 __truncdfsf2`）——
   本任务标题承诺的链接缺口**已彻底关闭**。
3. **QEMU/gem5 `SYS_read` 新增**：`getchar()`（无指针可变实参，绕开下述
   varargs 缺陷）双后端探针：读取真实 host stdin `"42"`，QEMU/gem5 均
   输出 `c1=52 c2=50`（正确 ASCII 值）、`exit=42`——新 syscall
   responder 真正工作（非桩）。
4. **`scanf` 运行时崩溃 + 根因隔离（新发现，非本任务引入）**：
   - `scanf("%d", &x)` 从真实 stdin 读取后，QEMU/gem5 均在解析/写回阶段
     出现"看似合理但错误"的行为（具体外在表现随代码形状变化：一种写法
     两后端一致 `MALIGN exit=129`；另一种写法两后端一致 `exit=1`——不
     是随机的，同一份二进制每次重跑结果确定性一致，只是"哪种写法触发哪
     种外在症状"依赖编译产物的具体寄存器/栈布局，这正是"读到未初始化/
     残留寄存器内容"这类 ABI bug 的典型指纹）。
   - **隔离测试排除本任务符号的责任**：`sscanf("42", "%d", &x)`（纯计算，
     零 I/O/SYS_read 参与）复现同一崩溃（QEMU/gem5 均 `MALIGN exit=129`，
     两次独立重跑结果一致）；`sscanf("hello", "hello")`（**零个**输出型
     指针可变实参，无 `%` 转换符）作负对照，**两后端均干净 `exit=42`**——
     证明 vfscanf/intscan 解析机制本身在此目标上完全健全，崩溃 100%
     由 `&x` 这个输出型指针可变实参触发，与本任务新增符号的算术正确性
     无关。
   - **根因定位**：与已有 open issue `varargs-pointer-args-lost-rb-bank-
     save-area`（ML-013a 登记，picolibc `printf("%s %s",p,q)` 场景）
     完全同源——LLVM 变参函数序言的保存区只 spill RD bank，从未 spill
     RB bank 的指针可变实参；`scanf` 的 `&x` 是输出型指针，走 RB bank，
     va_arg 读到的是保存区里的 RD-bank 残留值而非真实地址。**`scanf` 的
     语义决定它的转换说明符总是至少需要一个指针可变实参**（这是 `scanf`
     存在的意义），不同于 `printf` 的 `%d`（按值传递 `int`，可以绕开）,
     所以这条缺陷对**任意** `scanf`/`vscanf` 转换调用都是无法绕过的阻断，
     不是"换个格式说明符"能避开的情形。已在 `docs/issues.yaml` 的
     `varargs-pointer-args-lost-rb-bank-save-area` 条目下追加本次确认
     实例的完整记录（非新开条目，同一根因）。
5. **全量 `llvm-lit tests/lit/E2E/`**：**68 个测试，67 PASS + 1 XFAIL
   （`musl_scanf_int.test`，符合预期）、0 FAIL、0 UNRESOLVED**。落地前
   基线 66（本任务新增 2 个：`musl_scanf_int.test`(XFAIL) +
   `musl_stdin_getchar.test`(PASS)），**零回归**（66 个既有测试全部仍
   PASS）。
6. **`python3 tools/run_differential.py`**：`AGREE(3-way)=200
   gem5-SKIP=2 DIVERGE=0` / `AGREE(4-way)=200 Sail-SKIP=2
   SAIL-DIVERGE=0`——与基线完全一致（本任务不改任何指令语义，QEMU/gem5
   改动只涉及 cfx_smon syscall responder，非指令译码/执行逻辑）。
7. **`python3 scripts/manifest_check.py`**：`manifest validation: PASS`。
   **`python3 scripts/check_issues.py`**：`Open: 21 / Closed: 36 /
   Total: 57 / ISSUE REGISTRY: PASS`（Open 从 22 变 21，Closed 从 35 变
   36——正是本任务关闭的那条 softfloat 符号缺口条目）。
8. **patch 导出 + 独立验证**（三份 patch，均 `git am` 干净应用 + 结果
   文件与工作树逐字节一致，独立验证均在全新 detached worktree 里完成
   后已清理）：
   - musl `0012-...patch`：pin `b3240b4a`（ML-024a）之上 `am exit=0`，
     `diff -r` 逐字节一致。
   - qemu `0022-...patch`：pin `cf5c06b`（ML-019a）之上 `am exit=0`，
     `diff -r` 逐字节一致。
   - gem5 `0016-...patch`：pin `ca12f8261e`（ML-019a）之上 `am exit=0`，
     `diff -r` 逐字节一致。

**遗留问题**：
- `varargs-pointer-args-lost-rb-bank-save-area`（既有 open issue，本任务
  追加了新确认实例，未修复——修复超出本任务硬约束"不改 LLVM"授权范围，
  且本身是独立量级的 CodeGen 任务）：`scanf`/`vscanf` 家族任何真实转换
  调用在此修复前都无法验证运行时正确性。`tests/lit/E2E/musl_scanf_int.test`
  按任务原文管线落地但标记 `XFAIL: *`，会在该缺陷修复后自动翻转成
  "unexpected pass" 提醒需要摘掉 XFAIL 标记。
- 本任务未验证浮点格式（`%f`/`%e`/`%g`）scanf 的运行时正确性——不在任务
  范围内（任务原文本身已声明），且即使范围内也会先撞上同一个 varargs
  阻断，无法验证。

## 审阅记录（subagent）

### 判决：Accepted（零阻断发现，2 个 nitpick 级别观察）

subagent（general-purpose agent）已读 `reviewer.md` + `DS.md`，独立执行以下核验
（非仅采信完成区转述，逐条真实命令重跑，未信任完成区任何数字）：

1. **自递归陷阱**：源码级 grep 排查所有裸标识符出现处（排除 `toRep`/`toRepF32`
   包装调用后，仅剩 `__floatsisf(int a)` 里 `int` 类型的 `a==0`/`a<0`，非
   float/double 操作数，安全）+ 独立反汇编核查：`llvm-nm -u` 0 未定义符号；
   `llvm-objdump --triple=dadao -dr` 全文件仅 1 处 `call`（既有 ML-022a 的
   `__subdf3`→`__adddf3`，地址 0x5e8），ML-025a 新增 6 个函数地址范围内
   **零** `call` 指令 ✓。
2. **`__divdf3` 除法算法**：grep 确认新增区域无任何 `/`/`%` 作用于代码（仅
   注释提及"为什么不用"）；确认纯移位-减法 restoring long division，循环
   `significandBits+4`=56 次迭代产出 56 位 guard/round/sticky 形状，`quotient
   |= (rem!=0)` 正确折叠粘滞位；`scale` 对 a/b 符号相反（除法与乘法方向相反）
   经核实是正确要求，非笔误 ✓。
3. **`__mulsf3` 位位置**：手动重新推导 bit 位置（product 范围
   `[2^46,2^48)`，`shift=21` 提取窗口），与代码 `(shifted>>3)&F32_SIG_MASK`
   完全吻合，未发现 off-by-one ✓。
4. **独立 fuzz 复现**（未信任"210万次"数字，自己重写了一份 harness）：
   `gcc -O2` 原生编译改名版（`my_*`），300万随机+256组特殊边界交叉，覆盖全部
   6 个符号，**0 处不一致**；独立注入的负控制（`__gedf2` unordered 返回值
   -1→1、`__divdf3` 循环次数+4→+2）**立刻被抓到**（分别 3059 处/2284662 处
   不一致），证明 fuzz 工具非形同虚设 ✓。
5. **QEMU/gem5 SYS_read**：fd 校验（QEMU `fd==0`/gem5 `arg0==0`，非0落空）
   与 case64/66 惯例一致；EOF 语义正确（返回已读字节数,仅真实流错误才
   -EIO）；缓冲区边界安全（QEMU 逐字节写不越界；gem5 `tryWriteBlob` 只写
   `nread` 字节而非整个 `len`，比"偷懒写整个buffer"更严谨）；`__NR_read=63`
   与 musl `syscall.h.in` 核对一致 ✓。
6. **lit 测试亲自重跑**（非只读文件）：`musl_scanf_int.test`→XFAIL、
   `musl_stdin_getchar.test`→PASS，各重跑3次结果一致（无flaky）；全量
   68个测试 67 PASS+1 XFAIL+0 FAIL+0 UNRESOLVED，与完成区一致；`XFAIL: *`
   语法核实独占一行，lit正确识别（非UNRESOLVED/解析错误）；`MARKER: got=42`
   断言的是"修复后应有"的正确行为非已知错误行为，未来缺陷修复后会翻转成
   unexpected pass ✓。
7. **其余验收命令亲自重跑**：`run_differential.py`(AGREE 3-way=200/4-way=200
   DIVERGE=0)、`manifest_check.py`(PASS)、`check_issues.py`(21/36/57 PASS)、
   `check_lit_bytes.py`(69 patterns OK)、`check_codegen_abi.py`(23/0 PASS)
   均与完成区数字完全一致 ✓。
8. **patch/commit 完整性**：**3 份 patch 全部**独立核对（非只抽查1份）——
   `diff <(git format-patch --stdout) 对应patch文件` 三份均无差异；额外对
   musl patch 做独立 `git am`（干净 detached worktree，pin `b3240b4a`）
   `am rc=0` + 结果文件与工作树逐字节一致，验证后已清理、主仓库状态确认
   干净未受影响 ✓。
9. **issues.yaml/issues-archive.yaml**：`- id:` 层面确认关闭条目只存在于
   archive（非重复），`issues.yaml` 同名字符串只是普通注释引用；新增说明
   确认追加在既有 `varargs-pointer-args-lost-rb-bank-save-area` 条目下（非
   新开条目），三处交叉（issues.yaml 追记/issues-archive.yaml 关闭记录/
   测试文件注释）内容一致、无自相矛盾 ✓。

**finding**（2 个，均 nitpick 级别，非阻断）：

| finding | 处置 | 理由 |
|---|---|---|
| gem5 `case 63` 的 `std::vector<uint8_t> d(len)` 分配大小由 guest 控制的 `arg2` 决定，理论上巨大 `len` 会造成宿主机大内存分配 | ❌不修 | 与 pre-existing 的 `case 64`/`66` 用的同一模式，非本任务引入的新问题，不在本任务范围内修 |
| gem5 用字面量 `5 /* EIO */` 而非 `errno.h` 符号常量 `EIO`（QEMU 侧用的是符号）——纯风格不一致 | ❌不修 | 功能上等价（Linux/macOS errno 编号一致），不影响正确性；跟随既有 gem5 `decoder.cc` 该处代码整体偏字面量的既有风格（如 `-ENOSYS` 也是字面量），非本任务引入的新不一致 |

两项均判定为可不修（非阻断、非新引入、有明确理由）。**完成区状态对账**：
subagent 对本任务实际产出的代码本身判决 = Accepted（零阻断 finding，2 个
nitpick 均已 ❌不修+给出理由），不存在"未修的阻断 finding"意义上需要打回
的情形；完成区仍标「部分完成」不是因为 subagent 发现了未处置的代码问题，
而是因为**任务本身「## 验收」列出的验收项之一**（`scanf` 双后端运行时
"结果正确"）在一个范围外、已独立追踪、硬约束禁止修复的既有缺陷
（`varargs-pointer-args-lost-rb-bank-save-area`）面前无法达成——这是任务
验收标准层面的"部分"，不是代码质量/review层面的"部分"，两者是不同的轴，
如实分别记录，不互相掩盖。
