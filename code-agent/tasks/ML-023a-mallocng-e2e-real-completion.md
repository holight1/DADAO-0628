# ML-023a: ML-014a（mallocng e2e 里程碑）真正收尾——架构师已复现双后端跑通

**执行环境**: 本地 subagent

**状态**: 待处理

## 硬约束（务必遵守，违反视为任务失败）

- **禁止**对 `.work/llvm`、`.work/source/{qemu,gem5,musl}`、`~/DADAO-gem5` 做
  `git rebase`/`git am` 重放整条历史/`git reset --hard` 到早于当前 HEAD 的操作。
  只允许在当前 HEAD 基础上新增普通 `git commit`。
- **不要假设架构师下面给出的复现结果一定正确**——独立重新跑一遍，用你自己的命令
  验证，再往下走。这是本项目一贯要求（subagent 自审不采信转述）。
- 本任务是**当前 HEAD（已含 DL-070a/ML-018a/ML-019a/ML-020a/ML-021a/ML-022a 全部
  修复）之上的验证+测试固化任务**，预期**不需要改 LLVM/QEMU/gem5 任何源码**——
  如果验证中发现还需要动源码才能通过，如实报告，不要为了"完成任务"勉强绕过或
  弱化验收标准。
- **完成后必须真正更新原始 `code-agent/tasks/ML-014a-musl-e2e-malloc-printf.md`
  任务文件本身**（把它的「状态」从未跟踪/待处理改为已完成，写完成区）——这是本
  任务和之前所有 ML-014* 续办任务的关键区别：之前的续办任务明确禁止修改/关闭
  ML-014a 原始任务文件（因为都没有真正完成），**如果本任务验证通过、里程碑真正
  达成，这次要真正关闭它**，不是绕开它。
- 完成后必须在本任务文件里写「完成区」+ subagent 自审「审阅记录」（含逐条 finding
  + 判决）。

## 背景

`ML-014a`（原始任务见 `code-agent/tasks/ML-014a-musl-e2e-malloc-printf.md`）是
musl 移植的第二个 E2E 里程碑：真实调用 mallocng 分配器（触发底层 mmap）+
写入/读回校验 + free，两种不同大小重复一次，输出成功标记，双后端 exit=42。这个
里程碑经过多轮尝试（ML-014f/ML-014j/ML-014m 等，归档在
`code-agent/tasks/archive/2026-07-ml014-malloc-e2e-run/`）一直未达成：

- ML-014f（2026-07-18）：QEMU exit=130、gem5 exit=0（`rd31=-38`/ENOSYS，当时
  writev 还没实现，测试用 `fputs` 输出撞上这个缺口）。
- ML-014m（2026-07-18）：修了一个不相关的 linker `RELA_PAGE` 页差 bug 之后，
  单次 `malloc(131052)` 本身在 QEMU 上能到 42，但 gem5 在访问 `0x90001000` 时
  page-table fault（exit 134）；后续 `malloc_pointer_after`/`malloc_rw_after`
  探针在 QEMU 上也失败（exit 13/14）。这个 allocator/backend 地址映射问题从
  未被诊断出根因，官方结论是"需要另开题"。

**自那以后，主线又落地了 4 个直接相关的修复**：`DL-070a`（CALL 指令 Defs 缺
RB31）、`ML-018a`（musl `-O0` workaround 去除）、`ML-019a`（`SYS_writev`(66)
syscall responder）、`ML-021a`（`ISD::CALLSEQ_START/END` glue 链缺陷——**这个
尤其值得怀疑就是 ML-014m 那个 `0x90001000` 野指针式 page fault 的真正根因**，
因为 mallocng 内部分配路径本来就会在同一基本块触发多次连续调用，正是
ML-021a 修复的那类场景）。

**架构师已经用当前 HEAD 独立验证**（供你复现，不要直接采信，要自己重新跑一遍）：

```c
typedef unsigned long size_t;
void *malloc(size_t);
void free(void*);
int puts(const char*);

static int check_block(char *p, size_t n, int seed) {
    for (size_t i = 0; i < n; i += 4096) p[i] = (char)((i + seed) & 0x7f);
    p[1] = (char)(0x10 + seed);
    p[n-1] = (char)(0x20 + seed);
    for (size_t i = 0; i < n; i += 4096) if (p[i] != (char)((i + seed) & 0x7f)) return 0;
    if (p[1] != (char)(0x10 + seed)) return 0;
    if (p[n-1] != (char)(0x20 + seed)) return 0;
    return 1;
}

int main(void) {
    char *p = malloc(131052UL);
    if (!p) return 11;
    if (!check_block(p, 131052UL, 1)) return 12;
    free(p);

    char *q = malloc(262144UL);
    if (!q) return 21;
    if (!check_block(q, 262144UL, 2)) return 22;
    free(q);

    puts("MALLOC_CHAIN_OK");
    return 42;
}
```

编译（`clang --target=dadao -O2 -nostdinc -nostdlib` + musl include 路径）、
链接（`ld.lld -T tests/scripts/dadao.ld --start-group crt1.o <obj> libc.a
--end-group`，注意**必须用这个 linker script**，不加会得到一个跑不起来的
镜像）、`objcopy -O binary` 后：

- QEMU（`-M dadao-m1 -nographic -bios tests/scripts/trampoline.bin -kernel
  <bin>`）：**exit=42**，stdout 含 `MALLOC_CHAIN_OK`。
- gem5（`dadao_se.py <elf>`）：**exit=42**（`SIM_END: trap-exit code=42`），
  stdout 含 `MALLOC_CHAIN_OK`。

即：ML-014m 卡住的链式 malloc/free/输出场景，在当前 HEAD 上双后端都已经真实
跑通。

## 目标

1. **独立复现架构师给出的样例**（自己重新编译/链接/跑，不要只信上面贴的结果）。
2. **验证 mmap 真的被触发**（这是原始 ML-014a 任务明确要求的判别性证据，不能
   只凭"程序跑通了"）：131052 字节是 mallocng 的 `MMAP_THRESHOLD`（已由
   ML-014f/j 确认），走的是直接匿名 mmap 分支而非 size-class 池；可以用两块
   不同大小分配返回地址的差值是否符合 Phase A bump allocator 的 page-align
   语义（`cfx_smon` SYS_mmap responder 的 bump-cursor 逻辑，见
   `code-agent/tasks/ML-007a-cfx-smon-mmap-handlers.md`）来做用户态自证，不需要
   检查模拟器内部状态。
3. 把架构师给出的样例整理成正式的 `tests/lit/E2E/musl_malloc_printf.test` +
   `tests/lit/E2E/Inputs/musl_malloc_printf.c`（沿用 `musl_printf_int.test`/
   `musl_e2e_exit.test` 的管线范式：clang 编译 → `ld.lld -T
   tests/scripts/dadao.ld` 链接 → objcopy → 双后端跑 → FileCheck 断言输出
   marker + 退出码 42）。
4. 全量回归：`llvm-lit tests/lit/E2E/`、`tools/run_differential.py`、
   `scripts/manifest_check.py`/`check_issues.py`。
5. **如果验证全部通过**：
   - 更新 `code-agent/tasks/ML-014a-musl-e2e-malloc-printf.md`：状态改为已完成，
     写完成区说明里程碑达成的最终形态、验收结果，以及"是被哪些后续修复
     （DL-070a/ML-018a/ML-019a/ML-021a）共同解锁的"这段因果说明，不要重写
     原始目标/背景文字（保留历史，只新增完成区）。
   - 如果 `docs/issues.yaml`/`docs/issues-archive.yaml` 里有专门登记
     ML-014m 那个 `0x90001000` page fault 或 QEMU exit 13/14 的 open issue，
     核实是否要关闭归档（如实核查，不要凭空假设存在这样的条目——architect
     记忆里这些是记在任务文件的完成区/report.md 里，不一定登记成了正式
     issue，需要你自己 grep 确认）。
6. **如果验证发现某个环节其实还没真正打通**（比如更大的分配、更多次
   malloc/free循环、或者某个特定访问模式仍有问题）：如实报告具体卡在哪，
   不要因为架构师给的最小样例过了就假设"全部通过"——按原始 ML-014a 任务的
   验收标准逐条核对，不能满足的逐条说明，ML-014a 任务文件本次不要标记为
   已完成，保持如实的部分完成/待续状态。

## 验收

- 架构师给出的最小复现：独立重新编译/链接/跑，双后端 exit=42 + 输出
  `MALLOC_CHAIN_OK`。
- `tests/lit/E2E/musl_malloc_printf.test`：双后端 PASS，FileCheck 真实断言
  输出内容。
- mmap 真实触发的判别性证据：报告具体怎么验证的（地址差值计算/page-align
  核对），不能只说"应该是触发了"。
- 全量 `llvm-lit tests/lit/E2E/`：零回归（当前基线 62/62，落地前重新跑一次
  记录当前值为准）。
- `python3 tools/run_differential.py`：AGREE 数与当前基线一致、DIVERGE=0。
- `python3 scripts/manifest_check.py`/`check_issues.py` 通过。
- 若验证全部通过：`code-agent/tasks/ML-014a-musl-e2e-malloc-printf.md` 真正
  更新为已完成状态（这是本任务和历史上所有 ML-014 续办任务最大的不同）。
- 若本任务本身产生新代码文件改动（大概率不需要，纯测试固化），按项目惯例
  普通 `git commit` + patch 导出。

## 参考指针

- `code-agent/tasks/ML-014a-musl-e2e-malloc-printf.md`（原始任务，本任务如果
  验证通过要真正关闭的文件）
- `code-agent/tasks/archive/2026-07-ml014-malloc-e2e-run/ML-014f-musl-malloc-e2e-resume.md`、
  `ML-014m-dadao-rela-page-fix.md`（历史尝试与卡点的完整记录，含
  `0x90001000` page fault 的具体细节）
- `code-agent/tasks/ML-007a-cfx-smon-mmap-handlers.md`（Phase A bump
  allocator/page-align 语义，mmap 触发证据的判别方法参考）
- `tests/lit/E2E/musl_printf_int.test`（最新的管线范式参照：linker script、
  FileCheck 断言输出内容而非只判 exit code）
- `.work/build/musl/lib/{crt1.o,libc.a}`（`make build-musl` 重新生成）
- `tests/scripts/dadao.ld`（链接脚本，架构师踩过"不加这个链接失败"的坑，
  必须用它）
