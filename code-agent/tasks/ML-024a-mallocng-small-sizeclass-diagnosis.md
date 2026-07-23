# ML-024a: mallocng size-class（小分配）路径诊断与修复——`malloc(8)` 崩溃/返回 NULL

**执行环境**: 本地 subagent

**状态**: 已完成

## 硬约束（务必遵守，违反视为任务失败）

- **禁止**对 `.work/llvm`、`.work/source/{qemu,gem5,musl}`、`~/DADAO-gem5` 做
  `git rebase`/`git am` 重放整条历史/`git reset --hard` 到早于当前 HEAD 的操作。
  只允许在当前 HEAD 基础上新增普通 `git commit`。
- 本任务是**诊断优先**任务：先把根因摸清楚、用可复现的最小样例证实，再判断是否
  在本任务范围内修。如果诊断后发现修复需要深入 mallocng 分配器算法或后端
  较大改动，**允许停下来如实报告诊断结果+根因假设**，不要为了"完成任务"勉强上
  一个没把握的修复——参照 `ML-020a`/`ML-021a` 的先例（那两个任务都是先诚实报告
  范围边界，而不是强行绕过验收标准）。
- 完成后必须在任务文件里写「完成区」+ subagent 自审「审阅记录」（含逐条 finding
  + 判决）。若走"仅诊断不修复"的路线，同样需要完成区+审阅记录，只是完成区写
  诊断结论而非修复方案。

## 背景

`ML-023a`（`code-agent/tasks/ML-023a-mallocng-e2e-real-completion.md`，2026-07-23）
关闭了 mallocng **直接 mmap 路径**（分配 ≥`MMAP_THRESHOLD`=131052 字节）的 E2E
里程碑，但过程中发现一个**不在该里程碑范围内、独立的新缺口**：mallocng 的
**size-class（小对象/slab 池）分配路径**（低于 `MMAP_THRESHOLD` 的分配，走
`.work/source/musl/src/malloc/mallocng/meta.h` 里 `size_classes[]` 数组和
`donate.c`/`malloc.c` 的正常池化逻辑，不是直接 mmap）在当前 HEAD 上有问题。

架构师用两个几乎相同的最小样例复现，**发现结果对测试程序的具体写法敏感**
（这一点本身就值得诊断，不要假设"malloc(8) 就是单纯地总是失败"）：

**样例 1**（只调用 `malloc`，不声明/调用 `free`，不写入返回的内存）：
```c
typedef unsigned long size_t;
void *malloc(size_t);
int main(void) {
    void *p = malloc(8);
    return p ? 42 : 11;
}
```
结果：**QEMU exit=42，gem5 exit=42**（`malloc(8)` 看起来成功，两后端一致）。

**样例 2**（额外声明 `free`，写入+读回校验返回的内存，成功路径调用 `free`）：
```c
typedef unsigned long size_t;
void *malloc(size_t);
void free(void*);
int main(void) {
    char *p = malloc(8);
    if (!p) return 11;
    volatile char *vp = (volatile char *)p;
    vp[0] = 5;
    vp[7] = 6;
    if (vp[0] != 5 || vp[7] != 6) return 12;
    free(p);
    return 42;
}
```
结果：**QEMU exit=11**（`malloc(8)` 这次返回了 NULL），**gem5 exit=129**
（`SIM_END: MALIGN code=129`，硬件对齐故障，不是干净返回）。

两个样例除了"是否声明/调用 free、是否写入返回内存"之外没有其它区别，但结果
从"两后端一致成功"变成"两后端不一致地失败（QEMU 干净返回 NULL vs gem5 直接
故障）"。这个对测试写法的敏感性本身可能就是诊断的重要线索（例如：链接进 `free`
相关代码后二进制布局/relocation 发生变化、或者 mallocng 内部有依赖调用顺序的
全局状态、或者是一个真实的、与访问模式相关的 allocator bug），**不要跳过这个
现象直接去猜一个原因**。

## 目标

1. 独立复现架构师给出的两个样例（自己重新编译/链接/跑，不采信转述），确认现象
   是否可稳定复现。
2. 诊断 size-class 分配路径失败的根因。可能的方向（供参考，不要预设结论，自己
   验证）：
   - mallocng 的 size-class 元数据结构初始化/`donate.c` 的正常池化逻辑是否有
     依赖某个之前只在直接-mmap 路径上验证过、但 size-class 路径上从未验证过
     的机制（比如某种特定寻址模式、某个尚未被最近几个修复覆盖到的 CodeGen
     场景）。
   - QEMU 的"返回 NULL"（相对干净）与 gem5 的"MALIGN 硬故障"（不干净）是同一个
     根因的两种不同表现，还是两个独立的、恰好都在小分配路径触发的不同 bug——
     需要分别追踪，不要假设是同一个原因。
   - 可以用 gdb/`llc`/gem5 debug 输出等手段实际定位到具体是哪条指令/哪次访问
     出的问题，参照 `ML-020a`/`ML-021a` 那种"先用调试转储找到真根因，不要凭代码
     走读猜测"的方法论。
3. 如果根因是**后端/CodeGen 缺陷**且改动范围可控（参照 ML-020a/021a 的"个位数
   文件、几十行以内"量级）：修复并验证。
4. 如果根因在于 **mallocng 分配器算法本身**（比如某个 DADAO 特定的对齐/地址
   空间假设与 mallocng 上游假设冲突）：如实说明，判断是否需要 musl 侧改动，
   同样只在改动范围可控时修，否则停下报告。
5. 修复后（如果修了）：新增一个正式的、覆盖 size-class 路径的 lit 测试
   （建议同时覆盖"只 malloc"、"malloc+读写+free"两种场景，因为架构师的复现表明
   这两种写法的行为可能不同，需要都验证），双后端 exit=42。

## 验收

- 独立复现架构师给出的两个样例，报告实际结果（可能与架构师的结果一致，也可能
  由于并行/环境差异略有不同——如实报告，不要假设一定复现一致）。
- 诊断结论：具体是哪一层（mallocng 算法/musl 集成/LLVM CodeGen/QEMU 或 gem5
  模拟器）出的问题，给出可复现的最小样例和证据（调试转储/反汇编/gdb 输出等）。
- 若修复：新增 lit 测试覆盖 size-class 路径，双后端 exit=42；全量
  `llvm-lit tests/lit/E2E/` 零回归（当前基线 63/63，落地前重新跑一次记录当前值
  为准）；`python3 tools/run_differential.py` AGREE 数与当前基线一致、
  DIVERGE=0；`python3 scripts/manifest_check.py`/`check_issues.py` 通过；改动
  按项目惯例普通 `git commit` + patch 导出 + 追加 series。
- 若仅诊断未修复：在 `docs/issues.yaml` 登记一条新 issue，包含诊断结论、两个
  复现样例、根因假设、建议的后续方向；不算任务失败。
- 不要把本任务的结果误报为"malloc 完全解决"——即使本任务修好了 size-class
  路径，也只是覆盖了 mallocng 的另一半分配路径，不代表 mallocng 所有场景
  （比如更极端的分配模式、多线程——本项目当前是单线程，不用管这个）都已覆盖。

## 参考指针

- `code-agent/tasks/ML-023a-mallocng-e2e-real-completion.md` 完成区（本任务
  发现的缺口出处，direct-mmap 路径的对照参考）
- `.work/source/musl/src/malloc/mallocng/meta.h`、`malloc.c`、`donate.c`
  （size-class 分配逻辑，`size_classes[]` 数组、`MMAP_THRESHOLD=131052`）
- `code-agent/tasks/ML-020a-f64-softfloat-libcall-vfprintf.md`、
  `code-agent/tasks/ML-021a-direct-call-glue-chain-multicall-block.md`
  （"先用调试转储找到真根因，不要凭代码走读猜测"方法论的参照先例）
- `docs/issues.yaml`（若登记新 issue，检查现有 `musl-backend-*` 系列条目的
  命名/格式约定）
- `tests/lit/E2E/musl_malloc_printf.test`（direct-mmap 路径的现有测试范式，
  含 `volatile` 校验的踩坑记录，见 [[feedback-volatile-needed-for-memory-verification-tests]]
  同类教训——本任务新测试如果涉及写读回校验也要用 `volatile`）
- `.work/build/musl/lib/{crt1.o,libc.a}`（`make build-musl` 重新生成）
- `tests/scripts/dadao.ld`（链接脚本，必须用它才能跑得起来）

## 完成区

**状态**：已完成（诊断 + 修复，均在可控范围内）

**独立复现**（自己重新编译/链接/跑，未采信架构师转述）：

- 样例1（malloc-only）：QEMU exit=11（NULL），gem5 exit=42（"成功"但返回未
  验证地址）——与架构师转述的"两后端一致=42"**不一致**：本次独立复现在当前
  HEAD 上 QEMU 侧对样例1 也失败。如实报告这一差异，未强行凑同一个结论。
- 样例2（malloc+write+free）：QEMU exit=11（NULL），gem5 exit=129
  （`SIM_END: MALIGN code=129`）——与架构师转述一致。
- 用 `llvm-nm` 确认样例1/样例2 静态链接了**两个不同的 malloc 实现**：样例1
  （全程只引用 `malloc`，从未引用 `free`）解析到 `W malloc`（弱符号，musl
  `src/malloc/lite_malloc.c` 的 `default_malloc`→`__simple_malloc` 简单 bump
  allocator）；样例2（额外引用 `free`）解析到 `T malloc`（强符号，真正的
  mallocng `src/malloc/mallocng/malloc.c`）。这解释了架构师观察到的"对测试
  写法敏感"现象的**部分**机制层面：是否引用 `free` 决定链接器拉取哪个
  `malloc` 实现，而不是同一实现对不同调用模式产生不同结果。

**根因（用调试转储定位，非代码走读猜测）**：

1. 在 `mallocng/malloc.c`（`alloc_meta`/`alloc_group`）与 `lite_malloc.c`
   （`__simple_malloc`）中临时加入基于 raw `write(2,...)` syscall 的调试打印
   （不依赖 malloc 自身，重建 musl 后独立跑 QEMU/gem5，跑完立即还原源码，
   `diff` 确认已完全复原——见下方"改动文件"，最终提交的 patch 不含任何调试
   代码）。
2. 追出：样例2（mallocng 路径）在 `alloc_group()` 内 `size*cnt+UNIT >
   pagesize/2` 恒为真（`pagesize=PGSZ=libc.page_size` 读到 **0**），导致
   `needed` 经 `needed += -needed & (pagesize-1)` 折算为 **0**，最终
   `mmap(0, 0, ...)` 零长度请求。
3. 样例1（lite_malloc 路径）在 `__simple_malloc()` 内同样因 `PAGE_SIZE`
   （= `libc.page_size`）为 0，`req = n-(end-cur)+PAGE_SIZE-1 & -PAGE_SIZE`
   的位运算退化为 0（`PAGE_SIZE-1` 下溢为 `SIZE_MAX`，`-PAGE_SIZE` 为 0），
   同样落到 `mmap(0, 0, ...)`。
4. `libc.page_size` 为何是 0：`arch/dadao/crt_arch.h`（crt0 手写汇编）用
   `addi rd8, rd0, 4096` 合成 auxv 的 `AT_PAGESZ=4096` 条目。`addi` 的立即数
   是**有符号 12 位**（`imms12`，-2048..2047，`contracts/isa/spec.md` §3.6/
   附录编码表第 1011 行），4096 超出该范围，汇编器**未报错、静默环绕成
   0**（`llvm-objdump` 反汇编修复前的 `crt1.o` 直接证实：该槽位立即数字段
   解码为 `0x0000` 而非 `0x1000`）。`__init_libc()` 正确解析 auxv 表结构
   本身（argc/argv/envp 偏移、`AT_PAGESZ` 键值对位置全部正确），只是键对应
   的**值**本身在源头就被汇编器截断成 0。
5. QEMU 的 `mmap` syscall responder（`target/dadao/cpu.c` case 222）对
   `length==0` 正确拒绝返回 `-EINVAL`——`malloc()` 因而干净返回 NULL；gem5
   的 mmap 仿真对零长度请求未做同样拒绝，返回一个非 NULL 但完全未真实映射
   的地址——样例1（从不解引用返回指针）因此"看起来成功"（`p!=NULL` 即真），
   样例2（写入返回指针）则在实际访问时触发 `MALIGN` 硬件故障。这就是两个
   样例、两个后端呈现四种不同现象的**单一根因**的完整解释链：不是两个独立
   bug，是同一个 `libc.page_size==0` 缺陷经由两条不同分配器代码路径 + 两个
   后端不同的 mmap(0,0) 处理策略，产生的四种表面症状。

**修复**（范围可控——3 个文件、每处单行汇编替换 + 注释）：

- `.work/source/musl/arch/dadao/crt_arch.h`：`AT_PAGESZ` 槽位由
  `addi rd8, rd0, 4096` 改为 `setzw rd8, 0, 4096`（`setzw` 为无符号 16 位
  立即数指令，spec §607/§617，可精确表示 4096；该写法在
  `tests/lit/E2E/tp_probe.test`/`mmap_backing_probe.test` 中已有先例）。
- `tests/scripts/crt0_auxv.s`：同一处独立手写探针脚本，同样的 bug、同样的
  修复。
- `tests/lit/E2E/musl_crt0_auxv.test`：该测试自身构造"期望值"时**也**独立
  写了 `addi rd9, rd0, 4096`（同样溢出成 0）——即被测值和期望值两边独立犯了
  同一个错误、都变成 0，`0==0` 让 `AT_PAGESZ` 这一项检查此前**一直恰好通过
  却未真正验证过任何东西**（补偿性错误/"两边都错但凑巧相等"）。已同样改为
  `setzw`，现在是真实比较 4096==4096。

**负控制**（证明新增测试确实具有判别力，非恒真）：临时把 `crt_arch.h` 改回
`addi rd8, rd0, 4096`（bug 复现），重建 musl 后单独跑
`musl_malloc_sizeclass.test`：**FAIL**（非误报 PASS）。随后还原修复、重建，
确认恢复 PASS。

**新增 lit 测试**（拆成两个独立编译单元，理由见下方"审阅记录"finding A）：

- `tests/lit/E2E/musl_malloc_sizeclass.test` + `Inputs/musl_malloc_sizeclass.c`
  ：`malloc`+`volatile` 写读回校验+`free`，三种 size-class 尺寸（8/500/4095
  字节）。`llvm-nm` 确认链接到 mallocng（`T malloc`，强符号）。
- `tests/lit/E2E/musl_malloc_sizeclass_liteonly.test` +
  `Inputs/musl_malloc_sizeclass_liteonly.c`：只调用 `malloc`，整个链接单元
  从不引用 `free`。`llvm-nm` 确认链接到 `lite_malloc`（`W malloc`，弱符号）
  ——这是独立 review 发现的真实缺陷（finding A）修复后的产物：早期版本把
  两种场景放进同一个编译单元，导致 `free` 的引用把 mallocng 强符号拉进来
  覆盖了整个链接单元，"malloc-only" 场景实际上也在测 mallocng 而非
  lite_malloc，注释声称的覆盖范围与实际不符。

**回归验证**（修复落地后）：
- `llvm-lit tests/lit/E2E/` → **65/65**（基线 63 + 本任务新增 2，零回归）。
- `python3 tools/run_differential.py` → **AGREE(3-way)=200/AGREE(4-way)=200/
  DIVERGE=0**，与基线一致（本任务不涉及 ISA 语义改动）。
- `python3 scripts/manifest_check.py` → PASS。
- `python3 scripts/check_issues.py` → PASS（Open=23/Closed=34）。

**修改文件**：
- `.work/source/musl/arch/dadao/crt_arch.h`（真正的修复，`.work/source/musl`
  自身 git 仓库内单独 commit `b3240b4a`）
- `components/musl/patches/0011-dadao-fix-AT_PAGESZ-auxv-immediate-overflow-in-crt_a.patch`
  （导出上述 commit）+ `components/musl/patches/series`（追加一行）
- `tests/scripts/crt0_auxv.s`（同一 bug 的探针脚本副本）
- `tests/lit/E2E/musl_crt0_auxv.test`（修复其自身期望值构造中的同一 bug/
  补偿性错误）
- 新增 `tests/lit/E2E/musl_malloc_sizeclass.test` +
  `Inputs/musl_malloc_sizeclass.c`
- 新增 `tests/lit/E2E/musl_malloc_sizeclass_liteonly.test` +
  `Inputs/musl_malloc_sizeclass_liteonly.c`
- 本任务文件（状态改为已完成，本节 + 审阅记录）
- 诊断过程中临时改过 `.work/source/musl/src/malloc/mallocng/malloc.c` 和
  `src/malloc/lite_malloc.c`（加调试打印用于定位），**跑完已用备份文件完整
  还原，未进入任何 commit/patch**。

**遗留问题**：
- 本任务只覆盖 mallocng "malloc-only"（lite_malloc 路径）与"malloc+write+
  free"（mallocng 路径）两种场景在 size-class 范围内的行为；更极端的分配
  模式（如大量交替 malloc/free 造成 slab 复用、跨多个 size class 边界的
  压力测试）未覆盖，不代表 mallocng 所有场景都已验证——按任务要求明确写在
  此处，不误报为"malloc 完全解决"。
- 独立 review（见下）建议登记一个新 issue："DADAO 汇编器/MC 层对超范围立即
  数（如 `imms12`）静默截断而非报错"，本任务未创建该 issue（不在本任务
  授权范围内新增 issue 分类判断），留给架构师决定是否登记及归入哪个既有
  `musl-backend-*`/新分类。

## 审阅记录（subagent）

**执行方式**：本任务由架构师直接调度的 subagent 执行（非 DS 走 DS.md 常规
流程）。按项目"任何代码改动前必须走独立 subagent review"的硬性要求，另开
一个独立 subagent 做了不采信本 subagent 转述的复核（该 subagent 自己重新
读 spec、重新 build musl、重新跑 lit/差分/manifest/issues，未读本 subagent
的调试过程记录）。

**判决：PASS，附 2 项 finding（均已处置）**

独立 subagent 报告的核验点摘要：
1. 独立读 `contracts/isa/spec.md` 确认 `addi` 确为有符号 12 位 `imms12`
   （-2048..2047）、`setzw` 确为无符号 16 位、且本任务引用的章节号/行号
   （§3.6/1011、§607/617）准确无误 ✓。
2. 独立读修复后的 `crt_arch.h`/`crt0_auxv.s`/`musl_crt0_auxv.test`/新增
   测试文件全文，确认风格一致、无遗漏边界 ✓。
3. 独立 `make build-musl` + `llvm-objdump` 反汇编 `crt1.o`，确认 `AT_PAGESZ`
   槽位现为 `16 20 10 00`（`setzw` 操作码 `0x16`，立即数 `4096`）✓。
4. 独立跑 `llvm-lit tests/lit/E2E/` → 64/64（该轮次为 finding A 修复前的
   中间版本，含 1 个合并测试；finding A 处置后复验为 65/65，见上）✓。
5. 独立跑差分/manifest/issues，数字与本任务完成区一致 ✓。
6. 全仓库扫描 `addi ..., N`（`N` 超出 -2048..2047）未发现其它遗漏实例
   （仅测试注释文本中提及历史 bug 数值的文字，非真实指令）✓。
7. 核查 `docs/issues.yaml`/`issues-archive.yaml` 确认"汇编器静默截断超范围
   立即数"当前未被登记为独立 issue 类别 ✓。

| finding | 处置 | 改了什么 | 复验证据 |
|---|---|---|---|
| **A（中等，真实缺陷）**：新增测试早期版本把 `malloc_only()` 与
`malloc_write_free()` 放进**同一个**翻译单元/链接，独立 subagent 用
`llvm-nm` 证实：由于该链接单元里其它函数引用了 `free`，mallocng 的强
`malloc` 符号覆盖了**整个二进制**，导致"malloc-only"场景实际上也链接/
执行 mallocng，而非注释声称的 lite_malloc——测试覆盖范围声明与实际不符 | ✅已修 | 拆成两个独立编译单元：`musl_malloc_sizeclass.c`（只保留
`malloc_write_free`，链接 mallocng）+ 新增
`musl_malloc_sizeclass_liteonly.c`（只调用 `malloc`，整个链接单元不引用
`free`，链接 lite_malloc）；两份 `.test` 文件头注释相应更新，不再有覆盖
范围与实际不符的声称 | 独立 `llvm-nm` 复验：`musl_malloc_sizeclass.test`
→ `T malloc`（mallocng）；`musl_malloc_sizeclass_liteonly.test` →
`W malloc`（lite_malloc）；两测试独立 `llvm-lit` 均 PASS；全量回归重新
跑通 65/65 |
| **B（轻微，流程合规）**：独立 review 时任务文件仍是"状态：待处理"、无
完成区/审阅记录，与实际已完成的代码/patch/测试工作不符 | ✅已修（本次
即为处置：填写状态/完成区/本审阅记录区） | 本任务文件本身 | 本节即为
证据 |

**未处置/延后项**：无（两项 finding 均已处置且已复验，无 ❌不修/⏸延后
条目）。
