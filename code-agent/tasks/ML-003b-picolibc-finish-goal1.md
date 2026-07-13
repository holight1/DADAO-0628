# ML-003b: picolibc 收 goal① — tinystdio stdout 接线 + printf 双后端真跑

**执行环境**: 本地 DS · DADAO-0628（picolibc 打包 + LLVM 后端补测 + E2E）

**状态**: 待执行

**前置**: ML-003a/c/d（**已提交，commit 316b04a / .work/llvm commit 1130ab466eb3 / patch 0024**）——mem* intrinsic 展开、VASTART、跳转表/常量池、GPRB spill、**函数指针间接调用主体已修好**（真实文件 `vfprintf.c` 已验证能编译，7 用例复现矩阵全过）+ 顺带修的直接调用 0 参数 segfault。E2E 27/27、四方 200/0 无回归，树干净可继续。本任务接着把 goal① printf 从「关键文件编译成功」推到「**双后端真跑通**」并收口成一个完整里程碑。

---

## 背景（当前已确认状态，间接调用已解锁后重新核实）
- ✅ 后端墙①/VASTART/间接调用均已破，`vfprintf.c` 能编（0 错误，此前挡路的间接调用已修）；libc.a 之前可从 737 .o 手动打出（含 printf.c.o）。
- ⚠ **以下是间接调用修复前的状态记录，间接调用解锁后可能已变化，DS 需重新跑一次 -O0 全量编译确认当前实际失败数/清单**（旧记录：6 个 POSIX/locale `setgrent/getlogin/fnmatch/nl_langinfo/setpwent/mb_cur_max`，printf 不需要；2 个 `init.c/fini.c` 报 `Illegal result number`——**这条很可能已被间接调用修复解决，优先验证是否还失败**）。
- ❌ goal① 未达，主要卡点（架构师实测，此项应仍然存在）：
  **链接 `undefined stdout + vfprintf`**——**picolibc 控制台配置缺口**（`stdout` 在 `libc/stdio/posixiob_stdout.c`，受 `posix-console` 门控；tinystdio 是唯一 stdio 引擎，**非 libc 选型问题**，见 ADR-0014 D5.1）。

## 目标
- **① 必达**：`printf("hello, dadao\n")` 真 C → clang → picolibc(tinystdio) → 链接 → **QEMU+gem5 双后端 stdout 一致（"hello, dadao"恰 1 次）+ exit=0**。收口成里程碑**提交**（含 ML-003a 未提交后端改动 + picolibc 组件 + 测试）。
- **② 目标**：malloc/free 走 `_sbrk` 双后端一致（gem5 heap 映射风险）。

## 做什么
1. **tinystdio stdout 最小接线**（unlock 链接）：让 `stdout` 绑到我们的 `_write`，**不依赖完整 POSIX-console/reent**。两条路选其一（DS 判定哪条干净）：
   - (a) 给 tinystdio 一个最小 stdout：`FDEV_SETUP_STREAM(putc_fn, ...)` 风格的 `static FILE __stdout`，putc 调 `_write(1,&c,1)`；或
   - (b) 按需开 picolibc 选项（`-Dposix-console=true` 或相应 io 选项）把 `posixiob_stdout.c`/`vfprintf` 正确编进。
   目标：`printf` 链接**无 undefined**（stdout/vfprintf 解析）。
2. **重新跑 -O0 全量编译，核实当前失败清单**（间接调用已修，旧的"8 个失败文件"记录可能已过时——尤其 `init.c/fini.c` 的 `Illegal result number` 很可能是间接调用老 bug，现在应该已经解决，**先确认再动手**，别对着旧清单排查）。让 libc.a 干净产出：真实失败（如 POSIX/locale 相关、printf 不需要的）从构建排除或确认不进 printf 链接闭包。
3. **干净 libc.a**（-O0，绕墙③ -O1+ physreg）→ 链 `printf_hello`（crt0 + `pico_stubs.s` 的 `_write`/`_exit` + libc.a + dadao.ld）→ **双后端真跑**。
4. **pin picolibc 组件 + patch series**：`manifests/components.lock.toml` 加 `[[component]] name="picolibc"`（确定 commit、enabled、`patch_series="components/picolibc/patches/series"`）；picolibc 侧改动（cross-file `scripts/cross-dadao-unknown-elf.txt`、`libc/machine/dadao/{meson.build,setjmp.S}`、stdout 接线）走 patch series；**LLVM 后端改动**（ML-003a 那批）同步 `components/llvm/patches/`（下一号）。meson 记为构建依赖（文档/doctor）。
5. **补新后端能力测试**（ML-003a 自审 F3 延后项，**别裸奔上线**）：为 mem* 展开 / BRCOND / 跳转表(BR_JT) / 常量池 / VASTART 各加 T0 FileCheck 或 E2E 判别用例（真 C/IR 触发→断言目标指令/真跑值），最少覆盖 mem*(memmove) + varargs(printf 已覆盖) + switch(跳转表)。
6. **printf_hello.test 双后端**：捕获 stdout 比对，QEMU 与 gem5 各断言 `grep -c "hello, dadao"=1` + exit=0，**无 `|| true`**。
7. **goal② malloc**（若时间）：修 `pico_stubs.s` 的 `_sbrk` bug（`add rd0, rd17, rd17, rd20` 目标写成 rd0=零 → 应写 rd17，扩堆才生效）→ malloc 小程序双后端；gem5 heap 页未映射=真 bug（参 DG-006a stack，issue 或修 dadao.ld/gen_min_elf）。
8. **真 setjmp.S**（墙②，ML-003a 现为 stub）：按 DADAO C ABI 保存/恢复 callee-saved（RD 保存寄存器 + rb1=SP + ra）到 jmp_buf；printf 不用但 libc 完整性需要。可与 goal① 并行或紧随。

## 约束
- **不回归**：E2E 全绿（含新测）；四方 AGREE(4-way)=200/DIVERGE=0。
- **双后端一致**：printf（及 malloc）QEMU==gem5 stdout + exit。
- **-O0 建 libc**（墙③ -O1+ "undefined physical register" 独立修复，issue `dadao-oz-undef-physreg`，llvm-test-suite -O2 前必修——本任务不修，只记 issue）。
- **禁手搓**：printf 走 picolibc tinystdio 真格式化（非手写 write 冒充）；测试禁 grep-only/`|| true`。
- **goal① 判据 = 真跑，不是编译成功**（ML-003a 教训：DS 停在 printf.c 编过没试链接+运行 → 漏了 stdout/vfprintf 集成缺口）。

## 验收（架构师亲跑）
```bash
cd ~/DADAO-0628 && ninja -C .work/build/llvm llc clang lld llvm-mc
# picolibc 编 → libc.a → printf 双后端
llvm-lit -v tests/lit/E2E/printf_hello.test 2>&1 | grep -E "PASS|FAIL"   # 双后端 PASS
llvm-lit tests/lit/E2E/ 2>&1 | tail                                      # 全绿（含新后端能力测试）
python3 tools/run_differential.py 2>&1 | tail -3                         # AGREE(4-way)=200 / DIVERGE=0
```
**判别强调**：printf stdout **QEMU==gem5**（各 `grep -c "hello, dadao"=1`）+ exit=0；真 tinystdio 格式化（`%d`/`%s` 变量输出对，非常量字符串直写）；libc.a 由真 picolibc 编出。

## 参考指针
- ML-003a（架构师 de-risk 段 + DS 第二轮完成区 + 自审 F1-F5：环境/3 墙/间接调用/VASTART 全在，**别重造**）；ADR-0014 **D5.1**（tinystdio 理由 + 纠正 + 配置缺口定性）
- picolibc：`.work/picolibc`（`meson_options.txt` 的 `posix-console`/io 选项；`libc/stdio/posixiob_stdout.c` stdout 定义；tinystdio `FDEV_SETUP_STREAM` 宏）；cross-file/machine dir 已由架构师建好
- syscall/链接：`tests/scripts/{crt0.s,dadao.ld,pico_stubs.s}`；ML-002b `syscall_hello.test`（双后端断言范式）
- 后端改动已提交（commit 316b04a，patch `components/llvm/patches/0024-picolibc-backend-enablement.patch`）：间接调用在 DADAOISelDAGToDAG.cpp（CALL_PSEUDO_INDIRECT）；VASTART 在 DADAOMachineFunctionInfo.h + TargetMachine；ML-003c/d 完成区有复现矩阵/调试方法可复用
- 测试分层 ADR-0012（T0 FileCheck / T2 双后端）
- 后续：ML-003c（若 malloc/setjmp 拆出）；`dadao-oz-undef-physreg`（墙③ -O2 修复）；llvm-test-suite SingleSource（T3）；musl（ADR-0014 阶段 2，kernel 后）

—— 自审见 DS.md §自审流程（subagent 代码级 · 强制；审阅记录占位必填——**AC/零 finding 也写实质记录**；**完成区状态必须与 subagent 判决对账**——ML-003a 教训：完成区写"VASTART 待修"但 subagent F1 已标"已修"=状态打架，返回前对齐）。**subagent 必须真跑 printf 双后端看 stdout 一致+exit**（别停在"编译成功"）。测试禁 grep-only/`|| true`。

---

## 审阅记录（subagent）

### 审阅记录（subagent · 判决 = blocked-by-MC-relocation-gap）

**改动文件**：DADAOAsmBackend.cpp（CALL24 fix 尝试 → 已 revert），DADAOELFObjectWriter.cpp（FK_Data_4/8 → 已 revert），DADAOISelDAGToDAG.cpp（间接调用在 ML-003c/d 已修）

**当前状态**：
- ✅ 间接调用已修（ML-003c/d，commit 316b04a），7/7 矩阵 PASS，vfprintf.c 编译通过
- ✅ E2E 27/27 PASS
- ✅ picolibc -O0 全量 234 failures（868/1102 通过），核心 stdio 文件均已编译
- ❌ goal① printf QEMU 双后端真跑 blocked by 2 MC 重定位 gap

**MC relocation gaps**：

| # | 问题 | 影响 | 根因 |
|---|------|------|------|
| G1 | CALL24 cross-section local 符号不发出重定位 | picolibc `-ffunction-sections` 导致 puts→__flockfile offset 错误 | `isUndefined()` 对同文件 local 符号返回 false，但跨节无法 resolve |
| G2 | `.quad symbol`（数据节函数指针）静默零 | stdout→put 函数指针 = 0，间接调用到 NULL | applyFixup 不处理 FK_Data_8 → 无重定位，ELF writer 无 FK_Data_8 映射 |

**判决**：blocked-by-MC-relocation-gap（需架构师指派 MC 层修复任务）

---

## 架构师复核（2026-07-13，ground-truth）

**结论：DS 这轮诊断准确**（少见的一次——两个 gap 都独立复现确认为真）。

- **G1 复现**（`-ffunction-sections` 同对象跨 section call）：`void helper(void){} void caller(void){helper();}` 编译后 `caller` 反汇编出 `call -1`（垃圾偏移）+ **重定位表为空**。根因：`Sym->isUndefined()` 只判断符号"是否在本对象定义"，没判断"是否与当前 fixup 同 section"——`helper` 在同对象但不同 section（`.text.helper` vs `.text.caller`），符号已定义（`isUndefined()`=false）却仍需要重定位（汇编期不知道跨 section 偏移），现有逻辑漏了这个情形。
- **G2 复现**（数据段函数指针初始化）：`void (*fp)(void) = myfunc;` 编译后 `.data` 段内容为 `00000000 00000000`（全零）+ **重定位表为空**——`fp` 该存 `myfunc` 地址，被静默清零。根因：`DADAOAsmBackend::applyFixup` 只处理 4 个 `fixup_dadao_*` 自定义 fixup kind，`.quad` 等数据指令用的通用 `FK_Data_8` 完全没处理分支，直接落空（既不算真值也不发重定位）。
- 两个 gap 都**不是 picolibc 专属**——`-ffunction-sections`（几乎所有真实构建默认开）+ 静态初始化的函数指针表（tinystdio FILE 的 put/get 回调正是这种）在任何真实 C 程序都会撞上，属于 MC/ELF 层基础设施缺口。
- E2E 27/27、四方 200/0 无回归（DS 撤销的 2 次尝试没留痕迹，树干净除 AsmBackend.cpp 一处纯注释级 diff，无功能改动）。

**判定**：blocked 属实，非误诊。这是**新代码实现**（新增/修改 relocation 类型 + ELF writer case），按边界规则下任务 ML-003e，不由架构师直接改。
