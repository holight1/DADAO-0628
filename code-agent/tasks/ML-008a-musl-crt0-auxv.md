# ML-008a: musl crt0 auxv 合成（阶段B任务3）

**执行环境**: 本地 subagent

**状态**: 已完成（待架构师 ground-truth 复核）

## 硬约束（务必遵守，违反视为任务失败）

- **禁止**对 `.work/<component>`（llvm/qemu/gem5/llvm-test-suite）做任何 `git rebase`/`git am` 重放整条历史/`git reset --hard` 到早于当前 HEAD 的提交之类的操作。只允许在当前 working tree 基础上新增普通 `git commit`，需要导出改动时用 `git format-patch` 追加到 `components/<name>/patches/series`。
- gem5 侧改动只在 `~/DADAO-gem5`（独立仓库）进行，不在 `.work/source/gem5`。
- 本任务**不需要**改动 gem5 SE `argsInit` 或 QEMU 现有 trampoline（`tests/scripts/gen_trampoline.py`）——auxv/argv/envp 完全在用户态 `_start` 里合成，不依赖模拟器提供。
- **不需要真实 musl 源码**：本任务验证的是 crt0 合成的栈布局本身是否符合 musl `_start_c(long *p)` 期待的协议，不要求链接 musl 本体（musl `arch/dadao/` 骨架是后续任务，见任务清单 #4 起）。用一个手写/自造的桩函数模拟 `_start_c` 签名验证布局即可。
- 完成后必须在任务文件里写「完成区」+ subagent 自审「审阅记录」（含逐条 finding + 判决），供架构师复核；不要自行判定"已完成"而跳过自审。

## 背景

ADR-0014 D5.2（`docs/adr/0014-libc-syscall-charter.md`）+ `docs/reviews/musl-recon-2026-07-16.md` §5 阶段B：musl 静态单线程移植路径已确认 TLS/syscall 面均不构成阻塞（ML-006a 调研，Phase A 的 mmap/munmap/mprotect 已在 ML-007a 落地）。阶段B剩余工作里，**crt0 auxv 合成是唯一真正的新工作**（旧工具链 `~/toolchain/musl` 靠真实 QEMU linux-user/gem5 loader 生成 auxv，DADAO-0628 现在的 system-mode 极简 harness 没有这条路径，需要在用户态 `_start` 自己合成）。

musl `crt1`/`crt_arch.h` 的标准约定：`_start`（汇编）在跳转到 C 函数 `_start_c(long *p)` 之前，把 SP 指向一段满足以下布局的栈内存（`p` 即指向这段内存的起始地址，musl 源码 `src/env/__libc_start_main.c`/`crt/crt1.c` 按此布局解析）：

```
p[0]            = argc
p[1..argc]      = argv[0..argc-1]（指针）
p[argc+1]       = NULL                     （argv 结束）
p[argc+2..]     = envp[0], envp[1], ...    （指针，可以是空表，只有一个 NULL）
...             = NULL                     （envp 结束）
...             = auxv 对（每对 2 个 long：type, value），以 AT_NULL(0),0 结束
```

## 目标

写一个新的 crt0 变体（新文件，不要改动现有 `tests/scripts/crt0.s`——那是 picolibc 阶段专用，两者并存），在 `_start` 里于栈上手工构造上述最小布局，然后跳转/调用一个桩函数验证：

- `argc = 1`
- `argv = ["prog", NULL]`（"prog" 可以是任意占位字符串，指针必须真实指向该字符串数据）
- `envp = [NULL]`（空环境表）
- `auxv` 至少包含以下键值对（顺序不限，以 `AT_NULL(0), 0` 收尾）：
  - `AT_PAGESZ = 4096`
  - `AT_UID = 0` / `AT_EUID = 0` / `AT_GID = 0` / `AT_EGID = 0`
  - `AT_SECURE = 0`
  - `AT_RANDOM = <指向一段 16 字节缓冲区的指针>`（缓冲区内容可以全零，musl 只要求指针有效可读 16 字节，不校验随机性）

桩函数（模拟 `_start_c(long *p)`）用真实的判别性检查（寄存器比较，不是"不崩溃"）验证：读出 `argc`、`argv[0]` 内容匹配预期字符串、`argv[1]==NULL`、`envp[0]==NULL`、遍历 auxv 直到 `AT_NULL` 找到每个上述键并核对值，`AT_RANDOM` 指针可解引用读出 16 字节。全部通过则退出码 42，任一项不符退出码标出具体失败项编号（同 `mmap_probe.test` 的编号约定）。

## 验收

- 新增 `tests/lit/E2E/musl_crt0_auxv.test`（沿用现有 lit RUN 行范式，参考 `tests/lit/E2E/mmap_probe.test` 的写法：`%llvm-mc` 汇编 → `%ld.lld` 链接 → 双后端 QEMU/gem5 均跑出 exit=42）。
- 双后端 exit=42。
- 全量 `llvm-lit tests/lit/E2E/` 零回归。
- `python3 tools/run_differential.py` 差分不变（AGREE(3-way)=200/Sail(4-way)=200，本任务不涉及 ISA 语义改动，理论上不应有任何变化——如有变化说明改错了地方，需要排查）。
- `python3 scripts/manifest_check.py` 通过。

## 参考指针

- `docs/reviews/musl-recon-2026-07-16.md` §5 阶段B 第4条（auxv 字段清单出处）、§2.2（musl 启动路径 syscall 触发条件）
- musl 1.2.6 源码（`~/toolchain/musl` 仅供查阅协议细节，不抄代码）：`crt/crt1.c`、`src/env/__libc_start_main.c`、`arch/generic/crt_arch.h`（通用参考写法，DADAO 没有对应文件，需要新写）
- `tests/scripts/crt0.s`（现有 picolibc 阶段 crt0，作为汇编写法参考，本任务不改它）
- `tests/lit/E2E/mmap_probe.test`（判别性探针 + lit RUN 行范式参考）
- `contracts/abi/spec.md`（寄存器约定，本任务只用到普通 RD/RB 寄存器和栈操作，不涉及 rb4/rbtp）
- `docs/adr/0014-libc-syscall-charter.md` D5.2（本任务在整体路线图中的位置）

## 完成区

**状态**：已完成

**修改文件**（均为新增，无任何既有文件被改动）：
- `tests/scripts/crt0_auxv.s`（新）—— musl 风格 crt0 变体：`_start` 在栈上（`rb1 -= 160`）手工构造 20 格（160 字节）argc/argv/envp/auxv 表，然后 `rb2rb rb16, rb1, 1` + `call _start_c`。表布局（8 字节格，低到高）：
  - `[0]` argc=1
  - `[1]` argv[0]=&prog_str，`[2]` argv 终止符 NULL
  - `[3]` envp 终止符 NULL（空环境表）
  - `[4..17]` 7 组 auxv 键值对：AT_PAGESZ(6)=4096、AT_UID(11)=0、AT_EUID(12)=0、AT_GID(13)=0、AT_EGID(14)=0、AT_SECURE(23)=0、AT_RANDOM(25)=&rand_buf
  - `[18..19]` AT_NULL(0),0 终止符
  - `prog_str`/`rand_buf` 数据各用 `.align 8, 0` 对齐（`rand_buf` 需要 8 字节对齐以支持探针里的 `ldo` 读取）
- `tests/lit/E2E/musl_crt0_auxv.test`（新）—— lit E2E 测试，内联汇编即 `_start_c(long *p)` 的判别性探针实现：`argc==1` 检查、`argv[0]` 逐字节核对 "prog\0" 的 ASCII 字面量（不是回读同一块内存跟自己比）、`argv[1]==NULL`、`envp[0]==NULL`、真实遍历 auxv（游标从 `p+32` 开始，逐对读 type 用 `breq` 链分派，匹配则核对 value 并计数器 `rd11` +1，遇 `AT_NULL` 停止）、`AT_RANDOM` 额外核实指针非空且可解引用读出 16 字节（两次 8 字节 `ldo`，不核值，按任务要求）。终止时要求计数器精确等于 7（既能抓漏键也能抓错值——错值走各自专属 fail code 6~12，不会被计数器掩盖）。通过=exit 42；否则 exit 1~13 标出具体失败项。
- `code-agent/tasks/ML-008a-musl-crt0-auxv.md`（本文件）—— 补完成区/审阅记录。

**验收结果**（均为本人真实重跑输出）：

1. 单测直接跑（QEMU + gem5 SE 手动流水线，未走 lit）：
   ```
   llvm-mc(crt0_auxv.s) + llvm-mc(musl_crt0_auxv.test) → ld.lld -T dadao.ld → llvm-objcopy -O binary
   QEMU: qemu-system-dadao -M dadao-m1 -nographic -bios trampoline.bin -kernel *.bin  → exit=42
   gem5: gem5.opt tests/dadao/dadao_se.py *.elf → exit=42, SIM_END: halt code=42
     （gem5 SE 下 rb1 初始值是真实宿主栈地址 0x7fffffffdf60，与 QEMU trampoline 固定的
     0x87FF0000 不同——crt0 未硬编码任何绝对栈地址，只做相对 -160 调整，两个后端都正确验证了这一点）
   ```
2. 全量 `llvm-lit tests/lit/E2E/`：
   ```
   Total Discovered Tests: 56
     Passed: 56 (100.00%)
   ```
   （55 个既有 + 1 个新增 `musl_crt0_auxv.test`，零回归。新增前项目为 55/55。）
3. `python3 tools/run_differential.py`：`AGREE(3-way)=200  ...  DIVERGE=0  HARNESS=6`；`SAIL 4th column: AGREE(4-way)=200  SAIL-DIVERGE=0`——与任务前基线完全一致（本任务不涉及 ISA 语义改动，符合预期）。
4. `python3 scripts/manifest_check.py`：`manifest validation: PASS`。

**遗留问题**：无。

## 审阅记录（subagent）

subagent（general-purpose，独立 review，未采信本人任何叙述，全部亲自重跑）核验结果：

- **布局逐格核对**（crt0 写入 vs 探针读取）：追踪全部 20 格/160 字节偏移，argc@0、argv[0]@8、argv终止符@16、envp终止符@24，7 组键值对@32/40…128/136，AT_NULL@144/152；探针游标从 `p+32` 每次 +16，第 7 次迭代后恰好落在 144（AT_NULL）——**无偏移错误**。
- **寄存器合法性**（rd0/rb0 目的寄存器规则 + store 源寄存器不得为零寄存器规则，对照 spec §2.6.1/§2.6.2/§3.1-3.2/§4.1/§4.4/§4.7 逐条核对每个 `sto`/`ldo`/`addi`/`rb2rb`/`rb2rd`/`rd2rb`）：所有零值均先用 `addi rdX, rd0, 0` 物化到暂存寄存器再作为 store 源，从未直接以 `rd0`/`rb0` 作为 store 源或写目的——**无违规**。
- **大端/位宽**：所有标量字段（argc、指针、auxv 键值）全走整字 8 字节 `sto`/`ldo`；唯一的字节级访问（`ldbu`）只用于逐字符比对 ASCII 字面量，从未手工拼接多字节值——**无大端假设错误**。
- **寄存器生存期/覆盖**：追踪 `rb8`/`rb9`（各算一次、各用一次，中间无覆盖）、`rd8`（每次 store 前重新赋值，两次复用 0 值是有意为之且正确）、探针里的 `rb16–rb21`/`rd11–rd15`/`rd30`/`rd31`（各自生存期不重叠）——**无覆盖 bug**。
- **auxv 分派链**：未识别 type 正确落到 `aux_advance`（当前固定向量下这条路径是死代码但连线正确）；表内恒含 `AT_NULL`，循环保证终止；计数器==7 的收尾检查是漏键的真实兜底，错值由各自专属 fail code（6~12）直接拦截、不会被计数器掩盖——用变异测试验证（见下）。非阻断备注：当前只有一条固定测试向量，未来若引入重复键场景需重新评估计数器法是否仍够用，本任务范围内可接受。
- **对齐**：重新汇编后 `llvm-objdump -t` 确认 `prog_str@0x800000b8`(184，8 对齐)、`rand_buf@0x800000c0`(192，8 对齐)——`aux_random` 里的 8 字节 `ldo` 不会 MALIGN，**非侥幸，已用 objdump 实证**。
- **变异测试 1**（AT_UID 值从 0 改成 5，重建，QEMU 跑）：exit=7，恰好命中 `aux_uid` 的专属 fail code——证明错值检测真实生效。
- **变异测试 2**（AT_SECURE 键从 23 改成 999，重建，QEMU 跑）：exit=13（"未凑满 7 个键"），证明漏键检测（计数器兜底）真实生效。
- **流水线亲自重跑**：assemble→link→objcopy→QEMU 得 exit=42；assemble→link→gem5 SE 得 exit=42（`DADAO_REGDUMP` 显示 `rd11=...07`、`rd31=0x2a`）；`llvm-lit` 单跑该测试 PASS；全量 E2E 56/56 PASS；变异测试后已确认 `crt0_auxv.s` 已恢复原状（本人复核 `grep` 输出与原文件一致，无变异残留）。

**判决：通过**（无 blocking finding）。

| finding | 处置 |
|---|---|
| 无 blocking finding | — |
| 非阻断：单一固定测试向量未覆盖"重复键"场景 | ⏸延后（超出本任务范围；后续若扩展 auxv 键集合可一并补充重复键回归） |

## 架构师复核（ground-truth）

**独立验证方法**：不采信完成区/subagent 判决，从 git 状态开始逐项重跑。

- `git status --porcelain`：仅 3 个新增文件（`crt0_auxv.s`/`musl_crt0_auxv.test`/本任务文件），无既有文件改动，无 `.work/<component>` 触碰——符合硬约束。
- 逐行读 `crt0_auxv.s`：160 字节栈表布局（20 格×8 字节）逐格核对偏移与注释一致；`rela`+`addi` PC 相对寻址模式与既有 `mmap_probe.test` 一致；所有 store 源寄存器均先用 `addi rdX, rd0, 0` 物化零值再写，未见任何 `rd0`/`rb0` 直接作为 store 源的违规。
- 逐行读 `musl_crt0_auxv.test`（即 `_start_c` 探针）：argc/argv[0]（逐字节 ASCII 字面量比对，非自我回读）/argv[1]/envp[0] 四项检查逻辑正确；auxv 扫描是真实游标遍历+`breq`分派，非硬编码固定偏移读取；`AT_RANDOM` 检查非空指针后真实解引用两次 8 字节 `ldo`；收尾要求匹配计数器恰好=7，能同时拦下"漏键"和"错值"两类回归。
- `llvm-lit -v tests/lit/E2E/musl_crt0_auxv.test` → **PASS (1/1)**。
- 全量 `llvm-lit tests/lit/E2E/` → **56/56（100%）**，较基线 55 净增 1，零回归。
- 差分：`python3 tools/run_differential.py` → **AGREE(3-way)=200/DIVERGE=0/HARNESS=6**，**Sail AGREE(4-way)=200/SAIL-DIVERGE=0**，与基线逐位一致（本任务不涉及 ISA 语义改动，符合预期）。
- `python3 scripts/manifest_check.py` → **PASS**。
- **独立变异测试**（不依赖 subagent 报告，架构师自己动手验证判别力）：把 `crt0_auxv.s` 里 `AT_PAGESZ` 的值从 4096 改成 4097，手动走 llvm-mc→ld.lld→objcopy→QEMU 流水线 → **exit=6**，精确命中 `aux_pagesz` fail 分支（`addi rd30, rd0, 6`）——证明判别性探针真实生效，非"总是通过"的假测试。测试后已用备份恢复 `crt0_auxv.s` 到原始内容，`git status` 确认无残留改动。

**结论**：subagent 判决（通过）与架构师独立复核完全吻合。**ML-008a 验收通过**，musl Phase B 唯一真正新工作（crt0 auxv 合成）完成，为后续 `arch/dadao/` 骨架任务（syscall_arch.h/reloc.h/bits、pthread_arch.h+TLS stub、atomic_arch.h、configure 集成、两个 E2E 里程碑）打好地基。
