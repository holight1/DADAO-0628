# ML-003b: picolibc 收 goal① — tinystdio stdout 接线 + printf 双后端真跑

**执行环境**: 本地 DS · DADAO-0628（picolibc 打包 + LLVM 后端补测 + E2E）

**状态**: 待执行（第三次下发——地基已全部铺平，本轮聚焦收尾）

**前置**（**全部已提交，间接调用/MC重定位/QEMU死锁三大障碍均已清除**）：
- ML-003a/c/d：mem* intrinsic 展开、VASTART、跳转表/常量池、GPRB spill、**函数指针间接调用**（commit 316b04a / patch 0024）
- ML-003e：**MC 重定位缺口修复**——跨 section 同对象 call（G1）+ 数据段函数指针 `R_DADAO_ABS64`（G2）（`.work/llvm` commit `b3bbe0418bee` / patch 0025）。架构师 ground-truth 真链接验证：`call -2` 正确解析、`.data` 真存函数地址。
- ML-003f：**QEMU TCG 层死锁根治**——`dadao_tr_tb_stop` 的 `DISAS_TOO_MANY` 分支未推进 `env->pc`（只有分支族指令写 PC，`cpu_io_recompile` 给非分支指令构造的单指令 TB 因此死循环）。`.work/source/qemu` commit `63b6843` / patch 0014。架构师验证：之前 60 秒超时都跑不完的 printf 链接程序，现在几秒内正常结束。

E2E 27/27、四方 200/0 全程无回归。本任务接着把 goal① printf 从「不再挂起」推到「**双后端真正输出正确结果**」并收口成一个完整里程碑。

---

## 背景（2026-07-13 架构师最新状态，本轮下发前必读）

**⚠ 别重新排查已解决的问题**：MC 重定位（undefined stdout/vfprintf 链接失败）已随 ML-003e 修好；QEMU 无限挂起已随 ML-003f 修好。**stdout 接线方案已验证可行**——`FDEV_SETUP_STREAM(putc_fn,...)` 风格的最小 stdout（DS 之前手写的 `/tmp/stdout_min.c` 思路，非仓库文件，本任务需正式把它变成仓库内文件）能正确链接。

**当前真实卡点（架构师刚发现，ML-003f 复核时顺带测出）**：用干净重打包的 libc.a + 上述 stdout 接线方式，完整链接后跑 QEMU：**不再挂起，几秒内结束，但 exit=130（0x82 = ILLI 非法指令异常）**，无 "hello, dadao" 输出。`-d exec` trace 显示同一 PC 合法重复约 120 万次后终止于非法指令跳转（**不伴随 `cpu_io_recompile`**，与 ML-003f 那个死锁性质完全不同——真正到了执行阶段但跳到了非法地址，可能是间接调用目标寄存器算错/野指针，或 stdout 结构体字段布局与 tinystdio 期望不完全匹配）。

**本任务做什么（聚焦于此，不是重新排查已解决的）**：
1. 用 `-d exec`/gdbstub 定位 ILLI 具体触发点（哪条指令、PC、寄存器态）。
2. 核对 `stdout_min.c` 风格的 `FDEV_SETUP_STREAM` 结构体字段（`put`/`get`/`flags`/`unget` 等）与 tinystdio `libc/tinystdio/stdio_private.h` 里 `struct __file` 定义是否逐字段对齐——**优先检查这个**，字段错位是最常见的手写接线 bug。
3. 若结构体对齐没问题，再往深查是不是间接调用某个边界情形（本任务的 vfprintf callback 分发正是间接调用的实际使用场景，ML-003c/d 的复现矩阵未必覆盖了 tinystdio 真实调用形状）。

## 目标
- **① 必达**：`printf("hello, dadao\n")` 真 C → clang → picolibc(tinystdio) → 链接 → **QEMU+gem5 双后端 stdout 一致（"hello, dadao"恰 1 次）+ exit=0**。收口成里程碑**提交**（含 ML-003a 未提交后端改动 + picolibc 组件 + 测试）。
- **② 目标**：malloc/free 走 `_sbrk` 双后端一致（gem5 heap 映射风险）。

## 做什么
1. **修 ILLI（本任务的核心/首要工作）**：`-d exec`/gdbstub 定位非法指令跳转的具体触发点，按背景段给的方向排查（结构体字段对齐优先，间接调用边界情形其次）。修好后确认 QEMU 真输出 "hello, dadao\n" + exit=0。
2. **`stdout_min.c` 正式入库**：架构师验证工作的 `FDEV_SETUP_STREAM` 风格最小 stdout 接线（目前是 `/tmp/stdout_min.c`，DS 自己重写的临时文件，非仓库文件）——整理成正式仓库文件（如 `tests/scripts/stdout_min.c` 或 picolibc patch 里的 machine 目录），**方案已选定为 (a) 最小 stdout，不必再评估 (b) posix-console 选项**。
3. **打包干净 libc.a**（-O0，绕墙③ -O1+ physreg）→ 链 `printf_hello`（crt0 + stdout 接线 + `pico_stubs.s` 的 `_write`/`_exit` + libc.a + dadao.ld）→ **双后端真跑**（先 QEMU 确认输出正确，再补 gem5）。
4. **pin picolibc 组件 + patch series**：`manifests/components.lock.toml` 加 `[[component]] name="picolibc"`（确定 commit、enabled、`patch_series="components/picolibc/patches/series"`）；picolibc 侧改动（cross-file `scripts/cross-dadao-unknown-elf.txt`、`libc/machine/dadao/{meson.build,setjmp.S}`、stdout 接线）走 patch series。meson 记为构建依赖（文档/doctor）。
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
- **ML-003e**（MC 重定位 G1/G2 修复，`.work/llvm` commit `b3bbe0418bee`，patch 0025）；**ML-003f**（QEMU TCG 死锁根治，`.work/source/qemu` commit `63b6843`，patch 0014，**修法思路见知识图谱 `compiler-backend/05-qemu-tcg-target-porting.md` 新模式段**）——这两个都已解决，若又撞到类似症状先查这两个任务的完成区，别当新问题重排查
- picolibc：`.work/picolibc`（tinystdio `FDEV_SETUP_STREAM` 宏、`libc/tinystdio/stdio_private.h` 的 `struct __file` 定义——**修 ILLI 时核对字段对齐的关键参考**）；cross-file/machine dir 已由架构师建好
- syscall/链接：`tests/scripts/{crt0.s,dadao.ld,pico_stubs.s}`；ML-002b `syscall_hello.test`（双后端断言范式）
- 后端改动已提交（commit 316b04a，patch `components/llvm/patches/0024-picolibc-backend-enablement.patch`）：间接调用在 DADAOISelDAGToDAG.cpp（CALL_PSEUDO_INDIRECT）；VASTART 在 DADAOMachineFunctionInfo.h + TargetMachine；ML-003c/d 完成区有复现矩阵/调试方法可复用
- 测试分层 ADR-0012（T0 FileCheck / T2 双后端）
- 后续：`dadao-oz-undef-physreg`（墙③ -O2 修复）；llvm-test-suite SingleSource（T3）；musl（ADR-0014 阶段 2，kernel 后）

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

---

## 审阅记录（subagent · 本轮 2026-07-13 第三次下发）

> **[架构师预置占位 · DS 必填]** 上面两段是历史记录（G1/G2 已随 ML-003e 解决，QEMU 死锁已随 ML-003f 解决，**别重新排查**）。本轮任务聚焦**新发现的 ILLI（exit=130）**——DS 返回前必须开 subagent 代码级 review，逐条 finding + 处置表 + 判决写入本段（不要写进上面的历史段）。**占位未替换成实质记录 = 未自审 = 直接打回（AC/零 finding 也写：判决行 + 逐条核验点附证据 + finding:无）。**
> 特别核：printf **真跑**双后端输出 "hello, dadao" + exit=0（不是"不再挂起"就算完，ILLI 也要真修好）？`stdout_min.c` 已正式入库（非 `/tmp` 临时文件）？新后端能力有测试覆盖？无 `|| true`？
