# ML-012a: musl crt_arch.h + configure/Makefile dadao 集成 + 首个静态链接 E2E 里程碑

**执行环境**: 本地 subagent

**状态**: 待处理

## 硬约束（务必遵守，违反视为任务失败）

- **禁止**对 `.work/source/musl` 做 `git rebase`/`git am` 重放历史/`git reset --hard` 到早于当前 HEAD 的提交之类操作。只允许在当前 HEAD（`f4b0c3d1`，ML-011a 落地的提交之上）基础上新增普通 `git commit`，`git format-patch` 追加到 `components/musl/patches/series`（当前已有 `0001`~`0004` 四条，本任务应产出 `0005`）。
- 本任务**不改动**任何 LLVM/QEMU/gem5 源码，除非探测阶段发现真正的后端缺口（同前几个任务的处置原则：不自己动手改后端，如实报告，交给架构师判断）。
- 本任务**不要求**全量 `lib/libc.a`（ML-011a 报告仍有 409 个文件编译失败，全部是已知/已追踪的后端 codegen 缺口，未修复）在此任务范围内解决——目标是让**能编译成功的那部分**（已 937 个 `.o`）真正链接进一个可运行的静态二进制，验证 crt/启动路径本身，而不是等所有 libc 源文件都能编译。
- 完成后必须在任务文件里写「完成区」+ subagent 自审「审阅记录」（含逐条 finding + 判决）。

## 背景

musl 阶段B进度：`cfx_smon` syscall handler（ML-007a）→ crt0 auxv 手工合成验证（ML-008a，独立探针，未接入 musl 本体）→ `arch/dadao/` 编译期骨架（ML-009a）→ `atomic_arch.h`（ML-010a，非原子朴素实现）→ `pthread_arch.h`+TP 读写（ML-011a）均已完成。当前 musl 全树编译出 937 个 `.o`，但**从未尝试过真正链接**——ML-008a 的 `crt0_auxv.s` 是独立于 musl 源码树的手写探针（验证栈布局本身正确，未接入 musl 真实的 `crt1.c`/`_start_c` 派发）。本任务是把这些拼图**首次真正连起来**，达成 musl 移植的第一个端到端里程碑：一个用 `clang --target=dadao -static` 编译、链接 musl 的 `int main(){ return N; }` 程序，在双后端跑出退出码 `N`。

## 目标

1. **`arch/dadao/crt_arch.h`**：musl 惯例是这个文件里用 GCC/clang 扩展汇编（`__asm__(...)` 字符串块，直接嵌入 `.s` 汇编文本，**不是** C 内联汇编变量语法）在 `crt/crt1.c` 编译单元里直接定义 `_start`，构造好 musl `_start_c(long *p)` 期待的栈布局后跳转过去（参照 `arch/riscv64/crt_arch.h`/`arch/generic` 里的通用写法）。ML-011a 已确认**具名寄存器 C 内联汇编在当前 clang 前端对 RB bank 寄存器不可行**（`getGCCRegNames()` 不含 `rb*`）——但 `crt_arch.h` 用的是**纯汇编文本块**（`__asm__(".text\n" "_start:\n" "  ...\n")`），不经过 Sema 对具名寄存器变量的检查，理论上不受这个限制；需要在本任务里实际验证这一点是否成立（如果验证后发现纯汇编文本块也撞到同一类前端限制，如实报告，参照 ML-008a 已验证正确的 `tests/scripts/crt0_auxv.s` 栈布局逻辑，改用等价的独立 `.s` 文件 + 让 `crt1.c` 之外的机制提供 `_start`，具体做法由 subagent 判断）。
2. **栈布局逻辑复用**：`crt_arch.h` 里 `_start` 构造的 argc/argv/envp/auxv 栈布局，逻辑应与 ML-008a 已验证正确的 `tests/scripts/crt0_auxv.s` 一致（不要重新发明，那个任务已经用判别性探针验证过这个布局是对的）——但 `crt_arch.h` 场景下 `argc`/`argv`/`envp`/`auxv` 的**真实来源**是 gem5 SE `argsInit`（`~/DADAO-gem5/src/arch/dadao/process.cc`）/QEMU 侧的等价机制在初始进程栈上已经放好的内容，不是 ML-008a 那样手工硬编码固定值——需要先确认这两个后端在裸 ELF 加载时到底往初始栈上放了什么（如果什么都没放，退而求其次：本任务允许 `crt_arch.h` 里合成一个最小占位 auxv/argv/envp，只要让 `_start_c`/`__libc_start_main` 不崩即可，不必是"真实"的用户程序参数——静态单线程 E2E 里程碑不依赖真实命令行参数）。
3. **`configure`/`Makefile` dadao 目标集成**：确认 ML-006a 提到的旧 `configure` 里 `dadao*) ARCH=dadao` 规则（ML-009a 已经补过一次，见 `components/musl/patches/0001`）是否还需要额外的 Makefile 变量（比如 `ARCH_OBJS`、crt 目标路径拼接规则）才能让 `make lib/musl.a`/`crt1.o`/`Scrt1.o` 等目标正确编译并且不因为找不到 `crt_arch.h` 而失败。
4. **首个 E2E 里程碑**：用 `.work/build/llvm/bin/clang --target=dadao -static` 编译一个 `int main(){ return 42; }`，链接 musl 提供的 `crt1.o` + 能成功编译的那部分 `libc.a`（如果链接时撞到 409 个已知失败文件里某个符号缺失导致链接错误，先尝试只链接必需的最小符号集，或者构造一个不触发那些缺口的最小 `main`；如果确实卡住，如实报告卡在哪个符号/哪个已知 issue，不要为了"看起来完成"而修改成绕过链接的假验收），在 QEMU + gem5 双后端跑出退出码 42。

## 验收

- `arch/dadao/crt_arch.h` 落地，`crt/crt1.c`（或 musl 对应的 crt 编译单元）能用 `clang --target=dadao` 编译成 `crt1.o`。
- 新增 `tests/lit/E2E/musl_e2e_exit.test`（或类似命名）：真实用 `clang --target=dadao -static -nostdlib`（或 musl 完整驱动方式，视实际集成程度决定，具体命令行由 subagent 根据实际验证结果确定）编译链接一个 `int main(){ return 42; }`，双后端跑出退出码 42。
- 报告链接这一步实际用到的 musl 目标文件范围（全量 `libc.a` 还是筛选子集），以及是否撞到任何已知失败类别（如果撞到，说明是如何绕过/规避的，不能是"删掉报错的源文件"这种破坏性做法——应该是链接期只拉取用到的符号，musl 静态链接本身就是按需拉取 `.o`，通常不会强制链接编译失败的那些文件，除非它们是必需的启动路径符号）。
- 现有 `tests/lit/E2E/` 全量回归零变化（除了新增的这一个）。
- `python3 tools/run_differential.py`：如果本任务未改动任何 ISA/后端语义，应与基线完全一致。
- `python3 scripts/manifest_check.py` 通过。
- musl 侧改动用**普通** `git commit` 落地在 `.work/source/musl`，`git format-patch` 导出为 `components/musl/patches/0005-....patch`，追加进 `series`；全部五条 patch（0001-0005）独立验证可在干净 pin-commit checkout 上依次 `git am` 成功。

## 参考指针

- `docs/reviews/musl-recon-2026-07-16.md` §5 阶段B 第4/7/8条
- `code-agent/tasks/ML-008a-musl-crt0-auxv.md`（已验证正确的 argc/argv/envp/auxv 栈布局逻辑，`tests/scripts/crt0_auxv.s`）
- `code-agent/tasks/ML-011a-musl-pthread-arch-tls-stub.md`「完成区」（clang 前端 `getGCCRegNames()` 只列 RD bank 的具体限制细节，本任务第1条需要验证这个限制是否也影响 `crt_arch.h` 的纯汇编文本块写法）
- `.work/source/musl/arch/dadao/{syscall_arch.h,reloc.h,bits/*,atomic_arch.h,pthread_arch.h}`（ML-009a/010a/011a 已落地的骨架，本任务在其基础上继续）
- musl 源码 `crt/crt1.c`、`arch/riscv64/crt_arch.h`（结构参照，不可直接抄——DADAO 汇编语法/寄存器约定不同）、`Makefile`（`ARCH_OBJS`/crt 目标规则）
- `~/DADAO-gem5/src/arch/dadao/process.cc`（gem5 SE `argsInit`，确认裸 ELF 加载时初始栈上实际放了什么，如果有的话）
- `tests/scripts/gen_trampoline.py`（QEMU 侧栈初始化机制，确认是否提供 argc/argv/envp/auxv）

## 完成区

**状态**：已完成——**双后端 exit=42 达成**（QEMU 与 gem5 均独立验证，见下）。

### 探测阶段结论（目标1/2）

1. **纯汇编文本块（top-level `__asm__("...")`）不受 ML-011a 发现的
   `getGCCRegNames()` 限制**：用独立探针（`__asm__(".text\n.globl
   _start\n_start:\n  addi rb1, rb1, -16\n  ... rela rb8, prog_str\n  ...
   rb2rb rb16, rb1, 1\n  call _start_c\n ...")` + `void _start_c(long
   *p){}`）先 `clang --target=dadao -S` 确认模块级 asm 逐字节透传（经
   MC 层重新规范化输出，如 `.align 8,0`→`.p2align 3,0x0`，证明确实经过
   了真实的汇编器解析而非纯文本粘贴），再 `clang --target=dadao -c` 直
   接产出目标文件、`llvm-objdump -d --triple=dadao` 反汇编确认全部
   RB-bank 操作数（rb1/rb8/rb16）正确编码——**验证成立**，crt_arch.h
   按预期方案实现，未改用独立 `.s` 文件绕道。
2. **两个后端均未在裸 ELF 加载时提供真实 argc/argv/envp/auxv**：
   `~/DADAO-gem5/src/arch/dadao/process.cc::argsInit` 只
   `mapRegion(stack_min, pageSize, "stack")` + 设置 SP，不写入任何栈内容
   （函数自带注释"Minimal argv/stack setup for the skeleton"）；
   `tests/scripts/gen_trampoline.py` 只设置 SP=0x87FF0000 后跳转，同样不
   写入任何栈内容。按任务允许，`crt_arch.h` 在用户态合成最小占位表
   （复用 ML-008a `tests/scripts/crt0_auxv.s` 已验证的 20 格/160 字节布
   局，逐字节相同：argc=1/argv=["prog"]/空 envp/7 组 auxv
   键值对+AT_NULL），未改动任一模拟器。

### 撞到的三个真实后端缺口（均未修改 LLVM/QEMU/gem5，musl 侧绕过，已详细登记 `docs/issues.yaml`）

1. **`codegen-tailcall-lowercall-assert`（已有 issue，musl 侧新缓解）**：
   `crt/crt1.c`（`_start_c` 尾部调用 `__libc_start_main`）与
   `src/env/__libc_start_main.c`（`stage2(...)` 尾部调用）在项目默认
   `-O2` 下直接崩溃（`LowerCall emitted a return value for a tail
   call!`）。新增 `arch/dadao/arch.mak`：
   `CFLAGS_AUTO += -fno-optimize-sibling-calls`（安全、可移植、只关闭优
   化的标准开关，musl 全树生效）。副作用：全树 `make -k` 扫描此前命中
   这个断言的约 229 个文件本次全部消失（`docs/issues.yaml` 已记录，issue
   本身仍标 open，因为非 musl 构建路径不受这个 musl-only 开关保护）。
2. **`musl-inline-asm-empty-clobber-reg-alloc`（已有 issue，一个触发点
   已绕过）**：`src/env/__libc_start_main.c` 的空模板 `"+r"(stage2)` 屏
   障命中"couldn't allocate reg for constraint 'r'"（此前只知
   `explicit_bzero.c` 一处，本任务确认 `__libc_start_main.c` 是第二个已
   知触发点，非新发现）。新增 arch 覆盖文件
   `src/env/dadao/__libc_start_main.c`（musl `src/$(subdir)/$(ARCH)/*.c`
   覆盖机制，Makefile `ARCH_GLOBS`/`REPLACED_OBJS` 通用支持），唯一改动
   是把该屏障替换为 `lsm2_fn * volatile stage2 = ...;`（C 标准
   volatile 语义屏障，不经过任何内联汇编操作数分配，彻底绕开而非碰运
   气）。`explicit_bzero.c` 本身未处理（本任务链路不需要）。
3. **`dadao-pcrel-reloc-no-farsym-fallback`（新发现，已登记）**：链接时
   `src/env/__init_tls.c::static_init_tls()` 引用弱未定义符号
   `_DYNAMIC`（静态非 PIE 链接下惯例解析为地址 0）时，`ld.lld` 报
   `relocation Unknown (4) out of range: -524289 is not in [-131072,
   131071]`——DADAO 后端为"取外部/弱符号地址"生成的 PC-relative 重定位
   没有宽距/绝对值兜底，装载在 `0x80000000` 的代码引用地址 0 的符号即
   越界。该行在本任务配置下本来就是运行时死代码（`crt_arch.h` 故意不
   提供 AT_PHDR/AT_PHNUM，`aux[AT_PHNUM]==0` 使整个 for 循环体不执行；
   DADAO 目前也无动态链接/PIE，`PT_DYNAMIC` 分支本身也从不为真）。新增
   `src/env/dadao/__init_tls.c` 覆盖，仅挖空这一个 `if` 分支体（保留判断
   本身，其余逐字节同上游）。

### ABI 规范与后端实现分歧（新发现，独立验证，已登记 `dadao-callingconv-pointer-args-use-rd-bank-not-rb-bank`）

首次链接真实 `call _start_c`（手写汇编）到真实 clang 编译的
`void _start_c(long *p)` 时，gem5 端出现"访问虚拟地址 0"崩溃（QEMU 端
因是固定地址布局侥幸未触发）。用独立探针
`void store_it(long *p){*p=99;}` 编译反汇编，确认
`llvm/lib/Target/DADAO/DADAOCallingConv.td` 的 `CC_DADAO`（注释显式写
"GPRD only, Phase 5 spike"）把所有指针参数分配到 **RD bank
(rd16)**，与 `contracts/abi/spec.md §2.1` 记载的 RB bank (rb16) 矛盾——
后端从未实现文档化的 ABI。修正 `crt_arch.h`（`rb2rd rd16, rb1, 1` 而非
`rb2rb rb16, ...`）与 `src/thread/dadao/__set_thread_area.s`（ML-011a
按文档 ABI 误写成 rb16，本任务改为 rd16，因为其真实调用方
`__init_tls.c::__init_tp()` 是编译产物），同步更新
`tests/lit/E2E/tp_probe.test` 使其"与真实文件逐字节相同"的声明保持真
实。`get_tp.s` 无参数、不受影响。未修改 LLVM。

### 链接范围（目标4）

- `.work/build/musl` 全树 `make -k -j1 lib/crt1.o lib/libc.a`：
  **1166 个 `.o` 编译成功**（`find obj/src obj/compat -name '*.o' | wc
  -l`），**180 个失败**（`grep -c "] Error 1"`），1166+180=1346 与候选
  总数吻合。180 个失败逐类归类（脚本按错误文本精确配对，非宽窗口
  grep）：

  | 类别 | 文件数 | 备注 |
  |---|---|---|
  | `unsupported library call operation`（libcall lowering） | 157 | 既有类别，数量不变 |
  | 尾调用降低断言 | **0** | 本任务 arch.mak 后从 229 降为 0 |
  | `dynamic_stackalloc` | 7 | 既有类别，新曝光 1 个 |
  | `Node already inserted` | 6 | 既有类别，新曝光 3 个 |
  | `Illegal result number` | 3 | 既有类别，新曝光 1 个 |
  | `sign_extend_inreg` | 2 | 与此前完全相同两个文件 |
  | `un-analyzable fallthrough` | 2 | 既有类别，数量不变 |
  | `TargetInstrInfo.h:786` UNREACHABLE | 1 | 既有类别，数量不变 |
  | 内联汇编寄存器分配失败 | 1 | 仅剩 `explicit_bzero.c`（`__libc_start_main.c` 本任务已修） |
  | `DADAOAsmPrinter.cpp` UNREACHABLE | 1 | 既有类别（ML-011a 曝光），数量不变 |

  归类总计 157+7+6+3+2+2+1+1+1=180，与失败总数一致。**musl 静态链接按
  需拉取符号**：手动 `llvm-ar rc lib/libc.a $(find obj/src obj/compat
  -name '*.o')` 只打包这 1166 个成功文件（未删除/伪造任何报错源文件），
  `crt1.o`+此 `libc.a` 链接 `int main(void){return 42;}` 时**未撞到任何
  180 个已知失败文件的必需符号**（链接器零报错、零警告）。

### E2E 里程碑验证结果（目标4，均为本人真实重跑输出）

1. **手工独立复现**（不经过 lit）：`clang --target=dadao -O0 -c` 编译
   `int main(void){return 42;}` → `ld.lld -T dadao.ld --start-group
   crt1.o main.o libc.a --end-group` **零报错链接成功** →
   `llvm-objcopy -O binary` → QEMU (`qemu-system-dadao -M dadao-m1
   -nographic -bios trampoline.bin -kernel main42.bin`) **exit=42**；
   gem5 (`gem5.opt tests/dadao/dadao_se.py main42.elf`) **`SIM_END:
   trap-exit code=42`**。
2. **`tests/lit/E2E/musl_e2e_exit.test`**（新增）：`llvm-lit -v` 单跑
   **PASS**；内部走同样的 clang→ld.lld→objcopy→QEMU/gem5 管线。
3. **全量 `llvm-lit tests/lit/E2E/`**：连续两次 **58/58 (100%)**
   （57 基线 + 1 新增，`tp_probe.test` 为既有测试的必要修正，非净增）。
   期间一次并行跑出现 `malloc_hello.test` 单次失败，隔离单跑/重跑多次均
   PASS，判定为与本任务无关的瞬时噪声（非本任务引入的回归）。
4. **`python3 tools/run_differential.py`**：`AGREE(3-way)=200
   DIVERGE=0 HARNESS=6`，`SAIL AGREE(4-way)=200 SAIL-DIVERGE=0`——与基
   线完全一致（本任务未改任何 ISA/后端语义）。
5. **`python3 scripts/manifest_check.py`**：`PASS`。
6. **`python3 scripts/check_issues.py`**：`Open: 22 Closed: 29 Total: 51
   ISSUE REGISTRY: PASS`。
7. **musl 侧改动**：`.work/source/musl` 新 commit `f2fa0f8a`（在
   `f4b0c3d1` 之上，普通 commit）；`git format-patch` 导出为
   `components/musl/patches/0005-....patch`；`series` 已追加第五行。
   独立验证：全新 `git clone` + `checkout --detach` 到 pin commit
   `0784374d561435f7c787a555aeab8ede699ed298`，`git am` 依次应用
   `0001`→`0005` 五条 patch，全部 `Applying:` 成功。

### 修改文件

**主仓库**：
- `Makefile`（新增 `build-musl` target + `.PHONY`/帮助文本，把本任务手
  动执行过的 configure+`make -k`+`llvm-ar` 打包流程固化为可重放命令；
  已重新验证：`make build-musl` 在当前状态下干净跑通，产出
  `.work/build/musl/lib/{crt1.o,libc.a}`，`build-musl: PASS`）
- `components/musl/patches/series`（追加第五行）
- `components/musl/patches/0005-dadao-add-crt_arch.h-arch.mak-override-__libc_start_.patch`（新增）
- `docs/issues.yaml`（两条既有 issue 追加说明 + 两条新 issue：
  `dadao-callingconv-pointer-args-use-rd-bank-not-rb-bank`、
  `dadao-pcrel-reloc-no-farsym-fallback`）
- `tests/lit/E2E/musl_e2e_exit.test`（新增，本任务的核心交付）
- `tests/lit/E2E/Inputs/musl_e2e_exit.c`（新增）
- `tests/lit/E2E/tp_probe.test`（修正：随 `__set_thread_area.s` 的
  RD/RB bank 修正同步更新，保持"与真实文件逐字节相同"的声明真实）
- 本任务文件

**`.work/source/musl`**（独立仓库，普通 commit `f2fa0f8a`）：
- `arch/dadao/crt_arch.h`（新增）
- `arch/dadao/arch.mak`（新增）
- `src/env/dadao/__libc_start_main.c`（新增，arch 覆盖）
- `src/env/dadao/__init_tls.c`（新增，arch 覆盖）
- `src/thread/dadao/__set_thread_area.s`（修正，ML-011a 落地文件的
  RD/RB bank ABI 修正）

**未改动**任何 `.work/source/{llvm,qemu,gem5,llvm-test-suite}` 或
`~/DADAO-gem5` 源码（四者+一者 `git status --porcelain` 均确认干净）。

### 遗留问题

- 180 个编译失败全部落在既有/已追踪的后端 codegen 缺口类别（详见上表），
  未做进一步根因定位，留给独立后端任务。
- 三个已登记 issue（`codegen-tailcall-lowercall-assert`
  部分缓解/`musl-inline-asm-empty-clobber-reg-alloc` 部分绕过/
  `dadao-pcrel-reloc-no-farsym-fallback` 新登记）均未修复 LLVM/lld 本
  身，只是 musl 侧路由绕过，建议架构师评估是否需要独立后端任务根治。
- `dadao-callingconv-pointer-args-use-rd-bank-not-rb-bank`：ABI 合约与
  后端实现的真实分歧，建议架构师从两条路线选一（(a) 实现真正的 RB
  bank 指针调用约定，或 (b) 走 ADR 流程修订
  `contracts/abi/spec.md §2.1` 反映现状）——不属于本任务自行决定的范
  围。
- `src/env/dadao/__init_tls.c` 的 `_DYNAMIC` override 只在"静态单线程、
  无动态链接"配置下安全；DADAO 未来若支持动态链接/PIE，必须先解决
  `dadao-pcrel-reloc-no-farsym-fallback` 根因，再移除这个 override。

## 审阅记录（subagent）

subagent（general-purpose，独立 review，未采信本人任何叙述，逐条独立
复现/反编译/重新构建）核验结果：

- **diff 精确性**：`git show f4b0c3d1:src/env/{__libc_start_main.c,
  __init_tls.c}` 与新增 override 逐行 diff，确认改动范围与文件头注释
  描述完全一致，各自只有一处构造被替换，无其它改动。
- **volatile 屏障有效性（重点核实项）**：反汇编
  `obj/src/env/dadao/__libc_start_main.o`，确认 `stage2` 经历真实的
  store→reload 内存往返 + 寄存器间接 `call`，而非被内联/常量折叠——
  volatile 语义屏障确实生效，效果等价于（甚至强于）原 `"+r"` 技巧。
- **ABI 分歧 claim（重点怀疑对象）**：独立读
  `DADAOCallingConv.td`（"GPRD only, Phase 5 spike"注释原文）+ 独立编写
  `void store_it(long *p){*p=99;}` 探针编译反汇编，确认指针实参确实从
  `rd16` 读入——**claim 成立，非误诊**。
- **`__init_tls.c` "运行时死代码"判定**：核对 `crt_arch.h` 合成的 auxv
  表确无 AT_PHDR/AT_PHNUM，`aux[AT_PHNUM]` 必为 0——判定严谨。
- **patch series 可重放性**：全新 clone + `checkout --detach` 到 pin
  commit + 依次 `git am 0001..0005`，全部干净应用。
- **未越界改动**：`.work/source/{llvm,qemu,gem5}` + `~/DADAO-gem5`
  git status 全部干净。
- **Makefile 集成机制**：确认 musl 顶层 `Makefile` 的
  `ARCH_GLOBS`/`REPLACED_OBJS`/`-include arch/$(ARCH)/arch.mak` 机制通
  用支持本任务用到的两种覆盖方式，无需改 `configure`。
- **回归/差分**：`llvm-lit tests/lit/E2E/` 连跑 3 次 58/58；
  `malloc_hello.test` 单独隔离跑 5 次全过，判定此前的单次失败为与本任
  务无关的环境瞬态。`run_differential.py`/`manifest_check.py`/
  `check_issues.py` 均 PASS。
- **独立手工复现 E2E 里程碑**：不信任 lit PASS，手工重新链接+运行，
  QEMU 与 gem5 均独立复现 exit=42。
- **libc.a 子集规模**：1166+180=1346 与声称精确吻合；抽查 3 个失败文件
  （`scalbnf.o`/`vfprintf.o`/`__unmapself.o`）均为真实 clang 崩溃/错误
  输出，非编造。
- **`tp_probe.test` 判别力**：确认改动后仍保留双值+哨兵污染设计，非退
  化为 vacuous pass。
- **finding A（已处置）**：审阅时发现 `Makefile` 帮助文本/`.PHONY` 声
  明了 `build-musl`，但当时检索不到对应 recipe，`make build-musl` 报
  "Nothing to be done"，判定为真实可复现性缺口（`musl_e2e_exit.test`
  依赖的 `.work/build/musl/lib/{crt1.o,libc.a}` 当时无法从干净 checkout
  重新生成）。**复核确认**：这是审阅取样时机问题——本人在同一会话内、
  审阅 subagent 完成之前已经补上了 `build-musl` 的完整 recipe（在
  `Makefile` 里新增 `MUSL_SRC`/`MUSL_BUILD`/`MUSL_PREFIX` 变量 +
  `build-musl:` target：`configure` + `make -k lib/crt1.o lib/libc.a` +
  手动 `llvm-ar rc` 打包成功文件），审阅返回后**当场重新验证**
  `make build-musl` 从当前仓库状态干净运行到底，输出
  `build-musl: PASS (crt1.o + best-effort libc.a subset at
  .work/build/musl/lib/; ...)`，`.work/build/musl/lib/{crt1.o,libc.a}`
  确认重新生成、内容不变，`llvm-lit -v tests/lit/E2E/musl_e2e_exit.test`
  在此之后重跑仍 PASS。
- **finding B（已处置）**：审阅指出任务文件当时仍是原始 43 行 spec，未
  补「完成区」——已在本次写入补全（即本节所在的完整「完成区」+本审阅
  记录）。

**判决：通过（PASS-with-findings，两条 finding 均已现场处置）**。

## 架构师复核（ground-truth）

**独立验证方法**：不采信完成区/subagent 判决，从 git 状态开始逐项重跑，重点核实本任务最关键的一条 claim（ABI 规范与后端实现的分歧）。

- `git status`（主仓库 + `.work/source/{musl,llvm,qemu,gem5,llvm-test-suite}`）：仅预期文件改动，`.work/source/musl` 干净单提交 `f2fa0f8a` 落在 `f4b0c3d1` 之上，其余组件全干净。
- **独立复现 ABI 分歧核心 claim**（重点核实项，不采信任何叙述）：
  - 读 `llvm/lib/Target/DADAO/DADAOCallingConv.td` 原文确认 `CC_DADAO` 只有一条 `CCIfType<[i64], CCAssignToReg<[RD16..RD31]>>` 子句，无条件把所有 i64 值分配到 RD bank，无 RB bank 分支——逐字确认"GPRD only (Phase 5 spike)"的注释准确反映实现。
  - 读 `contracts/abi/spec.md §2.1` 原文确认"指针/地址参数走 RB bank rb16-31"确有此记载，与实现矛盾属实。
  - 读 `DADAOISelLowering.cpp` 确认 `CC_DADAO` 同时被 `AnalyzeCallOperands`（第 101 行，调用方出参）和 `AnalyzeFormalArguments`（第 207 行，被调方入参）使用——两侧一致使用同一套（错误于文档、但自洽）约定，这正是"编译器产物之间互相调用从未暴露过这个分歧、只有手写汇编调用编译产物才会暴露"的根本原因，逻辑自洽、非臆测。
  - 逐行读 `crt_arch.h`（`rb2rd rd16, rb1, 1` 后 `call _start_c`）、`__set_thread_area.s`（`rd2rb rb4, rd16, 1`）：均按验证过的真实后端约定（rd16）而非文档约定（rb16）修正，注释准确引用上述验证过程。
- 逐行读 `__libc_start_main.c`/`__init_tls.c` 两个 arch 覆盖文件：用 `diff` 逐行核对与上游（`f4b0c3d1` 版本）的差异，**均只有一行改动**（`stage2` 屏障替换为 `volatile` 变量；`PT_DYNAMIC` 分支挖空为死代码占位），其余逐字节相同——非"重新实现"，是真正最小化的针对性修补，且改动理由（inline-asm 操作数分配失败/PC-relative 重定位越界）均有清晰的独立验证轨迹。
- **独立重建 `make build-musl`**：`rm -rf .work/build/musl` 后从零跑 `make build-musl` → **`build-musl: PASS`**（干净完整跑通，非复用产物）；`find obj/src obj/compat -name '*.o' | wc -l` = **1166**，与声称数字精确一致；`lib/crt1.o`/`lib/libc.a` 均生成。
- **独立手工复现 E2E 里程碑**（不经过 lit）：`clang --target=dadao -O0 -c` 编译 `Inputs/musl_e2e_exit.c` → `ld.lld --start-group crt1.o main.o libc.a --end-group` **零报错链接成功** → QEMU **exit=42**、gem5 **`SIM_END: trap-exit code=42`**——两个后端均独立复现，走的是真实 `crt1.c→_start_c→__libc_start_main→__init_libc/__init_tls/__init_tp→libc_start_main_stage2→exit()→SYS_exit_group` 完整链路，不是手工探针。
- `llvm-lit -v tests/lit/E2E/musl_e2e_exit.test` → PASS(1/1)；全量 `llvm-lit tests/lit/E2E/` → **58/58（100%）**，与基线一致（57+1），零回归。
- 差分：`python3 tools/run_differential.py` → **AGREE(3-way)=200/DIVERGE=0/HARNESS=6**，**Sail AGREE(4-way)=200/SAIL-DIVERGE=0**，与基线一致（本任务未改任何 ISA/后端语义，符合预期）。
- `python3 scripts/manifest_check.py` → **PASS**；`python3 scripts/check_issues.py` → **Open 22/Closed 29/Total 51，PASS**，与声称数字精确一致，YAML 结构无重复 key。
- **独立复现 patch series 可重放性**：`git clone` 全新副本 + `checkout --detach` 到 pin commit + `git am` 依次应用 `0001`→`0005` 五条 patch → 全部 `Applying:` 成功。

**结论**：本任务最重要的发现——**DADAO LLVM 后端从未实现 `contracts/abi/spec.md §2.1` 记载的"指针参数走 RB bank"约定，实际统一走 RD bank**——经独立复现 TableGen 源码、ISelLowering 调用点、反汇编探针三方交叉验证，确认真实、非误诊。这是一个此前从未被发现的规范/实现分歧，因为在此之前**从未有手写汇编以带指针参数的方式调用真实编译产物**（所有既有 hand-written 探针要么零参数、要么双方都是同一份手写汇编，两边用同一套"文档约定"自洽地错着，从未露馅）。ML-011a 遗留的 `__set_thread_area.s` 真实 bug（当时用 rb16，从未被真实编译调用方触发过）被本任务顺带发现并修正——这是"任务链条不断加深集成度、逐步暴露更早任务未触及边界"的又一个实例（与本 session 反复出现的"顺带修复"模式一致）。**ML-012a 验收通过——musl 移植首个真正的静态链接 E2E 里程碑达成（`int main(void){return 42;}` 双后端 exit=42）**，1166/1346 候选文件编译成功且被验证足够支撑这条最小启动路径，剩余 180 个失败全部落在已知/已追踪类别。

**遗留给用户/架构师决策的事项**（不属于本任务或本次复核自行决定的范围）：`dadao-callingconv-pointer-args-use-rd-bank-not-rb-bank` 需要一次 ADR 级别的路线决策——(a) 实现真正的 RB bank 指针调用约定（需要 `DADAOISelLowering.cpp` 区分指针类型，改动面较大，且需要评估是否影响已经跑通的差分回归/E2E 基线），或 (b) 走 ADR 流程正式修订 `contracts/abi/spec.md §2.1`，把"指针参数与整数参数共用 RD bank"记录为现状。这个决策会影响后续所有涉及"手写汇编 + 编译产物混合调用边界"的工作（下一步 musl E2E 里程碑2/malloc+printf 大概率会再次触及这个边界），建议尽快向用户汇报征求意见，而非搁置。

| finding | 处置 | 改了什么 | 复验证据 |
|---|---|---|---|
| A：`make build-musl` 悬空，`musl_e2e_exit.test` 依赖的构建产物不可从干净 checkout 重现 | ✅已修（审阅期间已修，审阅后复核确认） | `Makefile` 新增 `build-musl` target（configure + `make -k` + `llvm-ar` 打包） | `make build-musl` 重新运行 → `build-musl: PASS`；`llvm-lit -v tests/lit/E2E/musl_e2e_exit.test` 重跑仍 PASS；`.work/build/musl/lib/{crt1.o,libc.a}` 内容不变 |
| B：任务文件缺「完成区」 | ✅已修 | 补全本节「完成区」+「审阅记录（subagent）」 | 本文件本节内容即证据 |
