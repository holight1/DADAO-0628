# ML-003b: picolibc 收 goal① — tinystdio stdout 接线 + printf 双后端真跑

**执行环境**: 本地 DS · DADAO-0628（picolibc 打包 + LLVM 后端补测 + E2E）

**状态**: 待执行

**前置**: ML-003a（架构师 de-risk + DS 第二轮：破墙① mem* intrinsic 展开、VASTART/F1、~10 Expand、跳转表、常量池、GPRB spill、间接调用部分——**均在 `.work/llvm` 未提交**，架构师复核 E2E 27/27 + 四方 200 **无回归**）。本任务接着把 goal① printf 从「编译成功」推到「**双后端真跑通**」并收口成一个完整里程碑一起提交。

---

## 背景（ML-003a 复核已确认的状态）
- ✅ 后端墙①/VASTART 已破，`printf.c` 能编（0 错误）；libc.a 可从 737 .o 手动打出（含 printf.c.o）。
- ❌ goal① 未达，卡在两处（架构师实测）：
  1. **链接 `undefined stdout + vfprintf`**——**picolibc 控制台配置缺口**（`stdout` 在 `libc/stdio/posixiob_stdout.c`，受 `posix-console` 门控；tinystdio 是唯一 stdio 引擎，**非 libc 选型问题**，见 ADR-0014 D5.1）。
  2. **8 文件编不出**：6 个 POSIX/locale（`setgrent/getlogin/fnmatch/nl_langinfo/setpwent/mb_cur_max`，**printf 不需要**）；2 个 `init.c/fini.c` 报 `Illegal result number` assertion（= defer 的间接调用老 bug，DS 间接调用实现对 init/fini 仍不全）。

## 目标
- **① 必达**：`printf("hello, dadao\n")` 真 C → clang → picolibc(tinystdio) → 链接 → **QEMU+gem5 双后端 stdout 一致（"hello, dadao"恰 1 次）+ exit=0**。收口成里程碑**提交**（含 ML-003a 未提交后端改动 + picolibc 组件 + 测试）。
- **② 目标**：malloc/free 走 `_sbrk` 双后端一致（gem5 heap 映射风险）。

## 做什么
1. **tinystdio stdout 最小接线**（unlock 链接）：让 `stdout` 绑到我们的 `_write`，**不依赖完整 POSIX-console/reent**。两条路选其一（DS 判定哪条干净）：
   - (a) 给 tinystdio 一个最小 stdout：`FDEV_SETUP_STREAM(putc_fn, ...)` 风格的 `static FILE __stdout`，putc 调 `_write(1,&c,1)`；或
   - (b) 按需开 picolibc 选项（`-Dposix-console=true` 或相应 io 选项）把 `posixiob_stdout.c`/`vfprintf` 正确编进。
   目标：`printf` 链接**无 undefined**（stdout/vfprintf 解析）。
2. **处理 8 个失败文件**（让 libc.a 干净产出）：
   - 6 个 POSIX/locale：**printf 不需要**——从构建排除 或 确认不进 printf 链接闭包即可（别为它们卡住）。
   - 2 个 `init.c/fini.c`（`Illegal result number` 间接调用）：**crt0.s 直接 `_start`→`main`（picolibc 风格），不跑 init/fini 数组**——确认链接闭包不需 init/fini（则可排除）；若 tinystdio 强依赖，则**根因间接调用 codegen 的 `Illegal result number`**（对标 RISC-V PseudoCALLIndirect 纯 pattern，见 roadmap 间接调用 defer 记录）或立 issue `dadao-indirect-call-illegal-resno` 记为独立后端修复。
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
- 后端：ML-003a 改的 8 文件在 `.work/llvm/.../DADAO/`（间接调用在 DADAOISelDAGToDAG.cpp；VASTART 在 DADAOMachineFunctionInfo.h + TargetMachine）；roadmap 间接调用 defer/RISC-V PseudoCALLIndirect 范式
- 测试分层 ADR-0012（T0 FileCheck / T2 双后端）
- 后续：ML-003c（若 malloc/setjmp 拆出）；`dadao-oz-undef-physreg`（墙③ -O2 修复）；llvm-test-suite SingleSource（T3）；musl（ADR-0014 阶段 2，kernel 后）

—— 自审见 DS.md §自审流程（subagent 代码级 · 强制；审阅记录占位必填——**AC/零 finding 也写实质记录**；**完成区状态必须与 subagent 判决对账**——ML-003a 教训：完成区写"VASTART 待修"但 subagent F1 已标"已修"=状态打架，返回前对齐）。**subagent 必须真跑 printf 双后端看 stdout 一致+exit**（别停在"编译成功"）。测试禁 grep-only/`|| true`。

---

## 审阅记录（subagent）

> **[架构师预置占位 · DS 必填]** 

### 审阅记录（subagent — 本次 DS 做的是 backend 实现，未达 goal①，判决=blocked-by-indirect-call）

**改动文件**：DADAOISelDAGToDAG.cpp（indirect call 尝试 3 模式）

**核验点**：
- stdout 接线：识别出 `posix-console=true` 可编译 `posixiob_stdout.c`（定义 `stdout`），通过编译 ✅
- 间接调用 crash 根因定位：在 `BuildSchedUnits` 中 `getValueType(OpResNo)` assertion，Crash 发生于将 LoadSDNode 作为 CALL_RRII/JUMP_RRII 的寄存器 operand 时 ❌
- CALL_IIII（全调用路径）可编译通过（test_indirect.ll + puts.c 均不 crash 但 codegen 错）✅
- llc from IR works, clang `-c` crashes — 差异在 clang CodeGen pipeline vs llc standalone，待进一步定位
- E2E 回归 27/27 PASS ✅

**尝试过的间接调用方案（均 crash）**：
1. `getMachineNode(RD2RB_ORRI + CALL_RRII)` — scheduler crash
2. `getMachineNode(RB0 + Callee + 0 + Chain + Glue)` — scheduler crash  
3. `getCopyToReg` first, then CALL_RRII — scheduler crash
4. TableGen pattern `(DADAOcall GPRD:$func)` → removed (tablegen issue)
5. TableGen pattern `(DADAObrind GPRD:$target)` → removed (scheduler crash)

**结论**：间接调用 blocker = `getMachineNode` for CALL_RRII/JUMP_RRII with non-machine SDNode operands → `BuildSchedUnits` assertion。需更深层 fix（可能需 PseudoCALLIndirect + expandPostRAPseudo，或修 getMachineNode operand handling）。建议拆为独立 issue `dadao-indirect-call-scheduler`。

**Finding**：

| # | finding | 处置 | 说明 |
|---|---------|------|------|
| F1 [HIGH] | 间接调用 scheduler crash 阻塞 goal① printf（vfprintf/puts 无法编） | ⏸ issue `dadao-indirect-call-scheduler` | 根因 clear（BuildSchedUnits OpResNo mismatch），需架构师指派独立修复任务 |
| F2 [INFO] | stdout 接线可走 `posix-console=true` + 提供 `write()` wrapper | ✅ 已确认 | `posixiob_stdout.c` 编译通过，stdout 定义可用 |

**判决**：blocked-by-indirect-call（不可推进 goal①，需先修间接调用）
