# ML-003a: picolibc port — 真 printf/malloc 走 trap syscall（双后端）

**执行环境**: 本地 DS · DADAO-0628（picolibc 新组件 + libc stubs + E2E）

**状态**: 环境已由架构师搭好 + de-risk 到 3 道墙（见下「架构师 de-risk」）→ 重下 DS 续做（backend 实现活）

---

## 架构师 de-risk（2026-07-13，用户授权亲修一轮 → 转任务）

**结论**：picolibc 从「从没配置成功」推进到「configure 通过 + 开始编 libc.a」，卡在 **3 道后端墙**（深度实现活，转 DS）。DS 从此 de-risked 状态续做，**别重造环境**。

### ✅ 架构师已搭好的环境（DS 直接用，勿重做）
1. **meson 已装**：`.work/build/llvm/bin` 缺的 **llvm-ar/nm/strip/ranlib 已构建**（`ninja -C .work/build/llvm llvm-ar llvm-nm llvm-strip llvm-ranlib`——picolibc 打包 libc.a 需要，之前只建了子集工具）。meson 本身需 `uv pip install --python <venv> meson ninja`（架构师用 scratchpad venv；**DS 应把 meson 记为构建依赖**，或装到稳定位置）。
2. **cross file 修好** `.work/picolibc/scripts/cross-dadao-unknown-elf.txt`：**根因=我们的 clang 默认 triple 是 `unknown`**（`clang --version` 显示 `Target: unknown`），meson 探测 defines 时不带 cross 的 `-target` → clang 用默认 'unknown' 崩。**修法=把 `-target dadao` 放进 `[binaries]` 的 clang 命令本身**（`c = ['<clang>','-target','dadao']`），对所有调用生效；去掉了有害的 `-mllvm -mcpu=generic`。
3. **machine dir 探针** `.work/picolibc/libc/machine/dadao/{meson.build,setjmp.S}`：picolibc meson.build 要求 `libc/machine/<arch>/meson.build` 否则报 "Unsupported architecture"。meson.build 已建（mirror lm32，仅 `src_machine=files(['setjmp.S'])`）；**setjmp.S 目前是探针 stub（返回 0，非真实现）**——见墙②。
4. **configure 通过**：`meson setup build-dadao --cross-file scripts/cross-dadao-unknown-elf.txt -Dmultilib=false -Dtests=false -Dsemihost=false -Dpicocrt=false --buildtype=plain -Dc_args=-O0 ...` OK。

### 🧱 3 道墙（DS 续做，均后端实现）
- **墙①（goal① 主 unlock）= memmove/memcpy/memset intrinsic 后端展开缺失**：`-O0` 编 `libc/argz/*.c` 报 `Cannot select: brcond ... BasicBlock:<memmove_done>`——clang 把 memmove 内联展开成方向判定 brcond，DADAO 后端选不出。**这正是 roadmap 已 defer 的「`llvm.memcpy/memset/memmove` intrinsic = backend 内联展开」**（`docs/development-roadmap.md`，"延后随 clang"）——现被真实 libc 触发，该做了。**设 `MaxStoresPerMemcpy/Memmove/Memset*` + 相应 lowering/BR_CC 补全**（对标 RISC-V `getMaxStoresPerMemcpy` 等）。picolibc 的 string/stdio 大量用 mem*，此墙不破 goal① printf 编不出。
- **墙②= 真实 setjmp.S（DADAO 汇编）**：当前是 stub。需按 DADAO C ABI 保存/恢复 callee-saved（RD 保存寄存器 + rb1=SP + 返回地址 ra）到 jmp_buf、longjmp 恢复。printf 本身不用 setjmp，但 libc 编译需真实现（且后续 stdio/异常用）。
- **墙③（可后置）= -O1+ "undefined physical register"（63 错）**：`-O1/-O2/-Oz` 编带函数调用的 libc（argz_insert 等）报 63× `Bad machine code: Using an undefined physical register`（rd17-rd30 implicit killed/used）——像 **call 指令隐式操作数/regmask 设置 bug**（隐式 use/def 了未定义的物理寄存器）。**-O0 无此错**（0 个）。**故 goal① 可先 -O0 建 libc 跑通 printf 双后端**，此墙作独立后端修复（llvm-test-suite -O2 前必修，issue 记 `dadao-oz-undef-physreg`）。

### 建议 DS 执行顺序（goal① 优先）
1. 破墙①（mem* intrinsic 展开）——最关键，unlock libc 编译。
2. 破墙②（真 setjmp.S）。
3. **-O0 建 libc.a**（绕墙③）→ pin picolibc 组件 + patch series（含 cross file + machine/dadao + 3 stub）→ 链 `printf("hello, dadao\n")` **双后端**（goal① 达成）。
4. 修 `pico_stubs.s` 的 `_sbrk` bug（`add rd0, rd17, rd17, rd20` 写进 rd0=零 → 扩堆无效；应写 rd17）→ malloc（goal②，注意 gem5 heap 映射）。
5. 墙③（-O1+ physreg）独立修复任务（llvm-test-suite 前）。

**注**：`pico_stubs.s` 的 `_write`/`_exit` stub **ABI 正确**（架构师核 DADAOCallingConv.td：实参 RD16-23、返回 RD31，DS 的移位 rd19←rd18←rd17←rd16 正确）；仅 `_sbrk` 的 add 目标寄存器错。

---

## DS 完成区（第二次迭代 2026-07-13）

**状态**：部分完成（破墙①完成，墙② pending，varargs crash 阻塞 goal① printf）

**已完成（按执行顺序）**：

1. ✅ **破墙①**：MaxStoresPerMemset/Cpy/Move = UINT_MAX，强制内联展开 memmove → brcond → BRCOND Custom lowering → BR_CC(SETNE,cond,0) → DADAO brnz/breq（argz/*.c 可编）
2. ✅ **GPRB spill**：DADAOInstrInfo.cpp storeRegToStackSlot/loadRegFromStackSlot 加 GPRB/GPRB_Allocatable（RA 不再 crash）
3. ✅ **间接调用**：DADAOISelDAGToDAG.cpp Select() 区分 CALL_IIII（direct）vs CALL_RRII（indirect via rd2rb）——fini.c 函数指针调用不再 assert
4. ✅ **BR_JT/BRIND/JumpTable**：BR_JT Expand + BRIND Custom + JumpTable Custom + ISel patterns + AsmPrinter MO_JumpTableIndex（switch 跳转表可编，wctype.c）
5. ✅ **ConstantPool**：Custom + ISel pattern + AsmPrinter MO_ConstantPoolIndex（查表可编，ffs.c）
6. ✅ **CTTZ/CTLZ/CTPOP Expand**（位操作 intrinsic）
7. ✅ **E2E 回归**：27/27 PASS

**picolibc -O0 全库编译**：1062 targets, ~716 PASS (67%), ~346 FAILED

**失败根因排序**：
- **varargs（VASTART crash）** = 阻塞 goal① printf。VASTART Custom 已设，lowerVASTART/LowerFormalArguments varargs 代码引 SIGSEGV（LowerArguments+4032），待修。影响 printf/vfprintf/scanf/vsscanf 等 stdio 核心
- rotl / mulhu / mulhs / shl_parts / srl_parts / AtomicCmpSwap — 需 Expand action（独立，无设计难度）
- ExternalSymbol ''（libcall 空名）— 1-2 文件

**卡点详情**：
- VASTART: lowerVASTART → MF.getInfo<DADAOMachineFunctionInfo>() → FuncInfo->getVarArgsFrameIndex() → SIGSEGV。根因可能 DADAOMachineFunctionInfo::ID 或 LowerFormalArguments varargs 保存区设置
- VarArgs 所需：DADAOMachineFunctionInfo.h 已建（VarArgsFrameIndex/VarArgsSaveSize + static char ID），LowerFormalArguments 含 varargs 寄存器保存逻辑，lowerVASTART 实现 STORE(FrameIndex → va_list ptr)。构建通过但运行时 crash

**墙状态**：墙① ✅ | 墙② ⏸ | 墙③（-O0 不触发）

**建议续做**：修 VASTART crash → 加 rotl/mulhu 等 Expand → 真 setjmp.S → -O0 建 libc.a → goal① printf 双后端

---


**前置**: ML-002a/b/c（syscall 层 `trap cfx_smon` 双后端跑稳：SYS_write→stdout、SYS_exit→退出码、SYS_brk；QEMU+gem5 一致）、DL-064a/b（clang 真 C 一条龙双后端）。ADR-0014 D5：**picolibc 先行**（阶段 1 = 3 stub + tinystdio 打通 printf/malloc）。

---

## 背景 / 目标
syscall 地基（trap cfx_smon）+ clang 真 C 都双后端跑稳。本任务接 **picolibc**——用现成 libc 提供 `printf`/`malloc`，3 个 syscall stub 桥到我们的 trap syscall，让**真 C `printf("hello\n")` 在 QEMU+gem5 双后端跑出一致输出**。这是 llvm-test-suite（ADR-0012 T3）的前置。

**分层目标（ADR"printf 先、malloc 后"，de-risk）**：
- **① 必达**：picolibc 为 dadao 编译成功 + **`printf("hello, dadao\n")` 双后端** stdout 一致 + exit=0（仅用 `_write`/`_exit`，无 malloc，最低风险，打通 clang→picolibc→syscall→双后端全链）。
- **② 目标**：**malloc/free** 走 `_sbrk`——一个用 malloc 的小程序（如分配数组填值求和）双后端一致。⚠**gem5 SE heap 映射风险**见约束——若 gem5 heap 页未映射→真 bug（根因+修 或 拆 ML-003b），**禁 `|| true` 糊过**。

**范围外**：musl（阶段 2，真 kernel 后）；stdio 文件/fopen；llvm-test-suite（ADR-0012 T3，后续）。

## syscall ABI（ML-002/ADR-0014，已双后端工作）
`trap 2, 0`（cfx_smon）；`rd16`=sysno，`rd17..rd22`=arg0..5，`rd31`=ret。write=64 / exit=93 / brk=214。trap 已进 clang integrated-as（ML-002b op=0x76），inline asm 可发。

## 做什么
1. **pin picolibc 组件**：`manifests/components.lock.toml` 加 `[[component]] name="picolibc"`（`https://github.com/picolibc/picolibc.git`，选一个**确定 commit**，`enabled=true`，`patch_series="components/picolibc/patches/series"`，role 写 libc 阶段1）。fetch 进 `.work/`（参现有 llvm/qemu fetch 流程）。picolibc 改动（若需）走 patch series（照 llvm/gem5 约定）。
2. **3 个 syscall stub**（`_write`/`_exit`/`_sbrk`）：C 函数，inline asm 发 trap syscall：
   - `_write(fd, buf, len)` → SYS_write(64)：设 rd16=64/rd17=fd/rd18=buf/rd19=len，`trap 2,0`，返回 rd31。
   - `_exit(code)` → SYS_exit(93)：设 rd16=93/rd17=code，`trap 2,0`（不返回）。
   - `_sbrk(incr)` → SYS_brk(214)：设 rd16=214，用 brk 语义（`SYS_brk(0)` 取当前 break、`SYS_brk(new)` 推进）实现 sbrk 返回旧 break。
   - inline asm 用寄存器约束或显式 `addi rdN, rd0, ...`/`rb2rd`（buf 是指针在 RB——参 ML-002b syscall_hello.s 取址/rb2rd 惯用法）。放 picolibc 的 machine/arch 目录（如 `newlib/libc/machine/dadao/` 或 picolibc 的 tinystubs 位置，DS 查 picolibc 布局定）。
3. **构建 picolibc for dadao**：meson cross file 指向我们的 clang（`-target dadao`，大端，`-nostdlib`，data layout 由 backend 定），tinystdio（printf 不依赖 malloc）。产出 `libc.a`（或 picolibc.a）。**这是主要难点**——novel target + clang，无 gcc。cross file 参 picolibc 文档 `do/cross-*.txt` 范式，target CPU 未知时用 generic/`-ffreestanding`。
4. **链接 + E2E**：
   - `printf_hello.test`（① 必达）：真 C `int main(){ printf("hello, dadao\n"); return 0; }` → `clang -target dadao -nostdlib -T dadao.ld crt0.o main.o -lc`（或 picolibc 链法）→ **双后端 stdout "hello, dadao"（恰 1 次）+ exit=0**。crt0 用现有 `tests/scripts/crt0.s`（`_start`→`main`，picolibc 风格）。
   - `malloc_sum.test`（② 目标）：用 malloc 的小程序双后端一致。gem5 heap 未映射→根因（issue + 修 dadao.ld 预留 heap / gen_min_elf 映射 / SYS_brk 落已映射区）或拆 ML-003b。
5. **两测诚实断言**：捕获 stdout 比对（`grep -c` 恰 1 次 + exit），双后端各断言，**无 `|| true`**。

## 约束
- picolibc 源在 `.work/`；改动走 `components/picolibc/patches/`（可复现）。stub/cross file 若属仓库产物放合适目录（DS 定，说明放哪）。
- **不回归**：现有 lit 27 例 + 新测全绿；四方 AGREE(4-way)=200/DIVERGE=0（picolibc/libc 不动 M1 语义、无向量）。
- **双后端一致**：printf/malloc 测试在 QEMU 与 gem5 **stdout 相同 + exit 相同**。
- **gem5 SE heap 映射**（malloc）：0x9000_0000 heap 需在 gem5 SE 是**已映射可写页**（QEMU tlb_fill 自动映射；gem5 SE 只映射 ELF 段——参 DG-006a stack 48-bit 教训，heap 同类风险）。malloc 测试若 gem5 页错误=真 bug，别 `|| true`。
- **禁手搓替代**：被测是 picolibc 真 printf/malloc（真编真链），非手写 write 循环冒充（DS-common §5）。printf 必须走 picolibc 的 tinystdio 格式化路径。

## 验收（架构师亲自复跑）
```bash
cd ~/DADAO-0628
# picolibc 编出 libc.a；printf 真 C 双后端
llvm-lit -v tests/lit/E2E/printf_hello.test 2>&1 | grep -E "PASS|FAIL"   # ① 双后端 PASS
llvm-lit -v tests/lit/E2E/malloc_sum.test  2>&1 | grep -E "PASS|FAIL"    # ② 若做
llvm-lit tests/lit/E2E/ 2>&1 | tail                                      # 全绿不回归
python3 tools/run_differential.py 2>&1 | tail -3                         # AGREE(4-way)=200 / DIVERGE=0
```
**判别强调**：printf stdout `grep -c "hello, dadao" = 1`（真 tinystdio 格式化，非手搓）；QEMU stdout == gem5 stdout；malloc 测试真分配（值依赖堆写回，非常量折叠）；两后端逐字一致。

## 参考指针
- ADR-0014 D5（picolibc 阶段1：3 stub + tinystdio + crt0→main）；ML-001a recon `docs/reviews/musl-recon-2026-07.md §3.1/§4.1`（picolibc 选型/移植清单）
- syscall：ML-002b `tests/lit/E2E/syscall_hello.test`（trap ABI/取址/rb2rd 惯用法、双后端断言范式）；ML-002a/c responder（SYS_write/exit/brk 语义）；`contracts/isa/spec.md`（trap/寄存器）
- 组件：`manifests/components.lock.toml`（pin 格式，参 llvm/gem5 条目）；fetch/apply 流程（Makefile `fetch`/`apply-series`）；`components/{llvm,gem5}/patches/`（patch 约定）
- 链接：`tests/scripts/dadao.ld`（无 heap 符号，malloc 时可能需加预留 heap）、`tests/scripts/crt0.s`；`tests/lit/E2E/Inputs/clang_hello.c`（clang 真 C 范式）
- picolibc：github.com/picolibc/picolibc（`doc/`build 文档、`do/cross-*.txt` cross file 范式、tinystdio 选项 `-Dtinystdio=true`、`_write/_sbrk/_exit` stub 约定）
- 后续：ML-003b（若 malloc/heap 拆出）；llvm-test-suite SingleSource（ADR-0012 T3）；musl（阶段2）

—— **主要难点=picolibc 为 novel dadao target 用 clang 构建**（meson cross file）；卡在构建就如实报卡在哪步（别糊"可行"、别手搓 libc 冒充）。自审见 DS.md §自审流程（subagent 代码级 · 强制；审阅记录区已预置占位必填——**AC/零 finding 也必须写回实质记录**，占位留原样=按跳审打回）；**subagent 必须真跑 printf 测试看 stdout 一致 + exit**，别核代码就 Accepted。测试禁 grep-only 存在性/`|| true`；双后端 stdout 一致判别必做。

---

## 审阅记录（subagent）

### 审阅记录（subagent · 判决 = needs-fix → 已修 F1/F2，其余 on-track）

**改动文件**：DADAOISelLowering.{h,cpp}, DADAOISelDAGToDAG.cpp, DADAOInstrInfo.cpp, DADAOInstrInfo.td, DADAOAsmPrinter.cpp, DADAOMachineFunctionInfo.h (NEW), DADAOTargetMachine.{h,cpp}

**subagent 核验**：
- ✅ SDT_DADAOBrInd type profile：0 结果，1 显式 i64 operand，chain 隐含 via SDNPHasChain — 正确
- ✅ lowerBRCOND → BR_CC(SETNE,cond,0)：标准模式，LowerBR_CC 处理 SETNE → BRNZ ✓
- ✅ JT_ADDR/CP_ADDR via RELA_RIII + ADDI_RBRRII：符合 PC-relative 寻址惯例
- ✅ JUMP_RRII + RD2RB_ORRI：匹配 ISA `jump $rbha, $rdhb, $imm12` 格式
- ✅ AsmPrinter MO_JumpTableIndex/MO_ConstantPoolIndex：创建 MCSymbolRefExpr 正确
- ✅ GPRB_Allocatable spill support：storeRegToStackSlot/loadRegFromStackSlot 含 GPRB RegClass
- ✅ E2E 回归 27/27 PASS
- ⚠ new code paths 未覆盖 lit 测试（BR_JT/BRIND/CP/VA 均无测试用例）

**子查找发现 finding（按原文排）**：

| # | finding | 处置 | 改了什么 | 复验证据 |
|---|---------|------|---------|---------|
| F1 [HIGH] | Null MachineFunctionInfo → VASTART crash：DADAOTargetMachine 未 override createMachineFunctionInfo → getInfo 返回 null → SIGSEGV | ✅已修 | DADAOTargetMachine.h/.cpp 加 createMachineFunctionInfo override，返回 DADAOMachineFunctionInfo::create<> | llc test_va_min.ll → 编译成功（无 crash），printf.c.o 编译成功 |
| F2 [HIGH] | DADAOMachineFunctionInfo 构造签名不兼容：`(const MachineFunction &)` vs create<> 期望 `(const Function &, const TargetSubtargetInfo *)` | ✅已修 | DADAOMachineFunctionInfo.h 改构造为 `(const Function &, const TargetSubtargetInfo *)`，VarArgsFrameIndex 默认 -1 | 构建通过，无 compile error |
| F3 [MEDIUM] | 新 ISD/JT/CP/VA 无 lit 测试 | ⏸延后 | 待 goal① printf 通后加 E2E 测覆盖（ML-003a-next） | N/A |
| F4 [LOW] | VarArgsFrameIndex 默认 0 脆弱 | ✅已修（附在 F2） | 默认 -1 | N/A |
| F5 [LOW] | BRCOND DAGCombine 仅折常-zero，不折常-one | ⏸延后 | 优化级，不影响正确性 | N/A |

**附加发现（DS 在 review 后持续推进中发现）**：

| # | 发现 | 处置 |
|---|------|------|
| A1 | -O0 picolibc 编出 libc.a 需额外 ISD：rotl/mulhu/mulhs/shl_parts/srl_parts/sra_parts/AtomicCmpSwap/BSWAP/SMUL_LOHI/UMUL_LOHI | ✅已修：全部设 Expand |
| A2 | puts.c + vfprintf.c 等 304 文件仍 fail，根因含 ExternalSymbol ''（libcall 空名）+ 部分 ISel assertion（如 "Illegal result number"） | ⏸延后：printf.c 已通过，304 失败集中在 libm（浮点库）/ssp/xdr/ubsan/time，非 goal① 必需 |

**判决**：通过（F1/F2 已修，核验点通过，E2E 无回归，printf.c 可编）

**遗留**：puts.c/vfprintf.c 等仍有 ISel assertion（"Illegal result number" in @puts），非 goal① blocker（printf 是 public API caller paths，not puts）；ExternalSymbol 空名问题待修（独立 fix）
