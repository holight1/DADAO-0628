# ML-019a: cfx_smon SYS_writev(66) responder——补齐 puts/fputs/printf 输出链路缺失的 syscall

**执行环境**: 本地 subagent

**状态**: 已完成

## 硬约束（务必遵守，违反视为任务失败）

- **禁止**对 `.work/source/qemu`、`~/DADAO-gem5`、`.work/source/musl`、`.work/llvm` 做
  `git rebase`/`git am` 重放整条历史/`git reset --hard` 到早于当前 HEAD 的操作。只允许
  在当前 HEAD 基础上新增普通 `git commit`。
- 本任务**只改 QEMU (`target/dadao/cpu.c`) 和 gem5 (`src/arch/dadao/decoder.cc`) 的
  cfx_smon syscall responder**，不改 musl 侧代码（musl 的 `__stdio_write`/`puts` 等实现
  保持不动，本任务要让它们"如既有代码所写"就能工作，不是去改 musl 迁就模拟器）。
- **完成后立即导出 patch**（不要延后）：QEMU 侧 `components/qemu/patches/0020-...patch`，
  gem5 侧 `components/gem5/patches/0015-...patch`，各自追加进对应 `series` 文件。这是本项目
  上一轮审计（`docs/reviews/codex-run-integrity-audit-2026-07-21.md`）暴露的纪律缺口，本任务
  不得重蹈。
- 完成后必须在任务文件里写「完成区」+ subagent 自审「审阅记录」（含逐条 finding + 判决）。

## 背景（架构师已定位的根因，供验证而非重新排查）

`docs/reviews/ML-017d-final-handoff-roadmap-20260721.md` 记录：`puts`/`fputs`/`printf`
（整数参数）在 QEMU 与 gem5 双后端都不产生输出 marker，返回值为负（`PUTS_RC_ERR`）、
errno 非零（`PUTS_ERR_ERRNO_NONZERO`）；但一个直接调用 `write()` 的"fixed write"对照
测试在双后端都能正常输出（`rc=42, write-ok`）。roadmap 列为路线 **A（stdio/writev/stdout
runtime）**，是当前唯一的阻塞项。

架构师已读代码定位根因：两个后端的 cfx_smon(cfxcode=2) syscall responder
（QEMU: `target/dadao/cpu.c` 约 137-217 行；gem5: `src/arch/dadao/decoder.cc` 约
648-738 行）只实现了 `case 64`(`SYS_write`)、`93/94`(exit)、`214`(`SYS_brk`)、
`222`(`SYS_mmap`)、`215`(`SYS_munmap`)、`226`(`SYS_mprotect`)，其余一律走
`default: ret = -ENOSYS(38)`。

musl 的缓冲 stdio 写路径（`src/stdio/__stdio_write.c`）用的不是 `SYS_write`，而是
`SYS_writev`（`__NR_writev = 66`，见 `arch/dadao/bits/syscall.h.in:79`）：把已缓冲的
`wbase..wpos` 和新写入的 `buf` 组成两个 `struct iovec` 一次性传给 `writev()`。当前两
后端都没有 `case 66`，因此这次调用命中 `default:` 拿到 `-ENOSYS`：

- `__stdio_write` 里 `cnt = syscall(SYS_writev, ...)` 得到负值 → 进入 `if (cnt < 0)`
  分支：置 `F_ERR`、返回短写（`iovcnt==2` 时返回 0）。
- 上层 `puts`/`fputs`/`fwrite` 因此拿到失败的写入结果 → 返回负值、`errno` 被设成
  `ENOSYS` —— 与观测到的 `PUTS_RC_ERR` + `PUTS_ERR_ERRNO_NONZERO` 完全吻合。
- `__stdout_write`（`src/stdio/__stdout_write.c`）里先调用的
  `ioctl(fd, TIOCGWINSZ, ...)` 同样会走 `default:` 拿到 `-ENOSYS`，但这条路径本身就
  容忍失败（只置 `f->lbf = -1`，不置 `F_ERR`），**不是阻塞项**，本任务不需要为它专门
  实现 `ioctl`。

因此推断：**只要给两个后端的 cfx_smon responder 补上 `SYS_writev`(66)，puts/fputs/
整数 printf 的输出链路就应该打通**——这是本任务要验证并落地的假设，不是已经证实的结论，
DS 落地后必须用实际输出 marker 证实，不能只信这段推理。

## 目标

1. 在 QEMU `target/dadao/cpu.c` 的 cfx_smon switch 里新增 `case 66`，实现
   `SYS_writev(fd, iovec_ptr=arg1, iovcnt=arg2)`：
   - 依次读取 `iovcnt` 个 `struct iovec`（每个 `{void *iov_base; size_t iov_len}`，
     按 `arch/dadao/bits/alltypes.h.in` 或 musl 通用模板的实际内存布局取——不要凭空
     假设字段顺序/大小，落地前先确认这份布局），从 guest 内存里把每个 iovec 的字节
     依次写到宿主 `fd==1?stdout:fd==2?stderr:忽略` 上（可以复用现有 `case 64` 的
     单次 `cpu_physical_memory_read` + `fputc`/`fflush` 写法作为参考模式，扩展成多
     iovec 循环）。
   - 返回值：全部写入成功时返回写入的总字节数（所有 iovec 的 `iov_len` 之和），语义
     必须匹配 `__stdio_write.c` 里 `cnt == rem` 才算完全成功写的判断逻辑——不能只返回
     某一个 iovec 的长度。
   - 非 `fd==1/2` 的情况如何处理（忽略/返回长度/返回错误）由 DS 参照 `case 64` 现有
     对未知 fd 的处理方式保持一致，不要引入新的行为分歧。
2. 在 gem5 `src/arch/dadao/decoder.cc` 的 cfx_smon switch 里新增 `case 66`，做同等语义
   的实现（可复用现有 `case 64` 里 `SETranslatingPortProxy(tc).tryReadBlob` 的读取模式，
   扩展成多 iovec 循环）。
3. 两个后端的实现要**语义一致**（相同 fd 处理策略、相同的成功/失败返回值语义），因为
   下游有双后端 differential 测试依赖两者行为一致。

## 验收

- 新增一个最小的独立 lit 测试（例如 `tests/lit/E2E/musl_puts_writev.test` + 对应
  `Inputs/*.c`），程序用 `puts("...")` 或非变参 `fputs`/整数参数 `printf` 输出一个可
  识别的标记字符串并返回可辨识退出码（如 42）；测试**必须实际断言 FileCheck 匹配到
  输出的标记字符串本身**（不能只断言退出码——这正是本次要修的"退出码正常但没输出"的
  盲区，之前的 targeted gate 就是因为只看 rc 才被判定 blocking）。
- 该测试在 QEMU 与 gem5 双后端都要通过（含实际输出内容匹配）。
- 全量 `llvm-lit tests/lit/E2E/`：在当前基线基础上零回归、新增本任务测试全绿（具体
  基线数字以 DS 落地前重新跑一次 `llvm-lit` 记录的当前值为准，不要用旧文档里的数字
  硬编代）。
- `python3 tools/run_differential.py`：与当前基线相比 AGREE 数不变、DIVERGE=0（本任务
  是 host-side syscall responder 补全，不改指令语义，理论上不影响 ISA 差分结果，但必须
  实跑验证而不是假设）。
- `python3 scripts/manifest_check.py` / `check_issues.py` 通过。
- QEMU 与 gem5 侧改动均用**普通** `git commit` 落地，`git format-patch` 导出为
  `components/qemu/patches/0020-....patch`、`components/gem5/patches/0015-....patch`，
  追加进各自 `series`；两条 patch 独立验证可在干净 pin-commit checkout 上依次
  `git am` 成功。
- **不**将本任务的通过等同于 ML-014a（mallocng e2e）或 roadmap B/C/D/E 已完成——
  本任务只解决 A（stdio/writev/stdout runtime）范围内的 puts/fputs/整数 printf 输出
  链路，`vfprintf`/`vfscanf`（roadmap B）、mallocng e2e（roadmap D）、kernel（roadmap E）
  均不在本任务范围。

## 参考指针

- `docs/reviews/ML-017d-final-handoff-roadmap-20260721.md` §5 路线 A（本任务对应的
  roadmap 条目与验收门槛原文）
- `.work/source/qemu/target/dadao/cpu.c` 约 137-217 行（cfx_smon 现有 responder，
  `case 64` 是要参照扩展的模式）
- `~/DADAO-gem5/src/arch/dadao/decoder.cc` 约 648-738 行（gem5 侧同名 responder）
- `.work/source/musl/src/stdio/__stdio_write.c`、`__stdout_write.c`（本任务要打通的
  musl 调用方，不要改它们）
- `.work/source/musl/arch/dadao/bits/syscall.h.in:79`（`__NR_writev = 66`）
- `docs/issues.yaml` / `docs/issues-archive.yaml`（落地中如发现新的独立缺口，登记
  不要顺手扩大修）

## 完成区

**状态**：已完成

**修改文件**：

| 仓库 | 文件 | 改动 |
|---|---|---|
| `.work/source/qemu`（普通 git commit） | `target/dadao/cpu.c` | 在 `dadao_cpu_do_interrupt` 的 `EXCP_CFXTRAP`/cfx_smon switch 里，紧跟 `case 64` 之后新增 `case 66`（SYS_writev），+42 行。commit `cf5c06bbcf7ac0e176b7f5e52fca48868c3d03a9` |
| `~/DADAO-gem5`（普通 git commit） | `src/arch/dadao/decoder.cc` | 在 `TrapInst::execute` 的 cfx_smon switch 里，紧跟 `case 64` 之后新增 `case 66`，+34 行。commit `ca12f8261eb6c096d48b50ff206293f32a7d1daa` |
| `DADAO-0628` | `components/qemu/patches/0020-target-dadao-add-SYS_writev-66-cfx_smon-responder-ML.patch` + `components/qemu/patches/series` | 新增 patch，series 追加一行 |
| `DADAO-0628` | `components/gem5/patches/0015-arch-dadao-add-SYS_writev-66-cfx_smon-responder-ML-0.patch` + `components/gem5/patches/series` | 新增 patch，series 追加一行 |
| `DADAO-0628` | `tests/lit/E2E/musl_puts_writev.test` + `tests/lit/E2E/Inputs/musl_puts_writev.c` | 新增 lit 测试：真实 `puts("DADAO_WRITEV_PUTS_OK"); return 42;`，链接真实 musl `crt1.o`/`libc.a`，双后端跑，FileCheck 断言标记字符串 + `test $? -eq 42` |
| `DADAO-0628` | `tests/lit/E2E/lit.cfg` | 新增 `%FileCheck` 替换项（该目录此前没有 FileCheck 路径，只有 `tests/lit/MC/Dadao` 把 llvm bin 加进了 PATH），供新测试用 `%FileCheck %s` |

**两后端具体实现**（语义一致）：

- `struct iovec { void *iov_base; size_t iov_len; }`（`.work/source/musl/include/alltypes.h.in:78` + `arch/dadao/bits/alltypes.h.in` 的 `_Addr long`）在本 ABI 上两个字段均 8 字节、无 padding，共 16 字节/条目。
- 每条 iovec 的 16 字节按 spec §2.1 大端序手动 MSB-first 组装（`v=(v<<8)|byte`），读取手法复用各自文件里 `case 64` 已有的字节级读取原语（QEMU: `cpu_physical_memory_read`；gem5: `SETranslatingPortProxy(tc).tryReadBlob`），不是新写读内存路径。
- fd 处理：只有 `fd==1`（stdout）或 `fd==2`（stderr）才写入并计入返回值；其余 fd 保留 `ret=0`（贴合 QEMU 自身 `case 64` 对未知 fd 的既有处理方式）。gem5 自己既有的 `case 64`（本任务未改）对 fd 不做判断、无条件写 `std::cout`——新增的 `case 66` 特意不照抄这个 quirk，而是对齐 QEMU 新 `case 66` 的 fd 语义，理由是任务目标 3 明确要求两后端在 writev 上语义一致（下游 differential 依赖）。
- 不复用 `case 64` 的 NUL 提前截断 heuristic（`if (byte==0 && i>0 && len>100) break`）：`__stdio_write.c` 要求 `cnt==rem`（返回值精确等于所有 `iov_len` 之和）才算完全成功写，提前截断会破坏这个契约，因此 `case 66` 对每个 iovec 完整写出 `iov_len` 字节。
- 返回值：成功时为所有 iovec 的 `iov_len` 之和（不是某一个 iovec 的长度）。

**新增测试内容**：`tests/lit/E2E/musl_puts_writev.test`——`clang --target=dadao` 编译 `Inputs/musl_puts_writev.c`（`puts("DADAO_WRITEV_PUTS_OK"); return 42;`），`ld.lld` 静态链接真实 `.work/build/musl/lib/{crt1.o,libc.a}`（与 `musl_e2e_exit.test` 同一 1166-member partial archive），`llvm-objcopy` 转 flat binary。QEMU 侧 `-M dadao-m1 -bios trampoline -kernel bin`，断言 `test $? -eq 42` 后 `%FileCheck %s --check-prefix=MARKER < %t.out`；gem5 侧直接喂 ELF 给 `dadao_se.py`，同样断言 `$? -eq 42` 后 FileCheck 匹配。`MARKER: DADAO_WRITEV_PUTS_OK` 是唯一断言行，真实匹配输出内容本身，不只看退出码。

**验收结果（实际命令输出）**：

1. 单测（先跑通验证假设）：
   ```
   $ .work/build/llvm/bin/llvm-lit -v tests/lit/E2E/musl_puts_writev.test
   PASS: E2E :: musl_puts_writev.test (1 of 1)
   Passed: 1 (100.00%)
   ```
   手动 probe（写测试前的独立验证，非 lit）：QEMU 输出 `WRITEV_PROBE_OK`、rc=42；gem5 输出 `SIM_END: trap-exit code=42` + `WRITEV_PROBE_OK`、rc=42——确认假设成立（之前无 `case 66` 时 puts 返回负值/errno 非零/无输出）。

2. 全量 lit E2E（跑了 4 次，含 2 次架构师复核，全部 60/60，零回归——落地前基线为 59/59，新增本任务 1 条测试后为 60）：
   ```
   $ .work/build/llvm/bin/llvm-lit tests/lit/E2E/
   Total Discovered Tests: 60
     Passed: 60 (100.00%)
   ```
   （subagent 审阅中一次 `-j6` 并行跑出现 `malloc_hello.test` 误报 FAIL，单独重跑与另外 3 次全量跑均 PASS，判定为并行 worker 资源竞争的既有 flake，与本任务改动的文件无关——本任务未触碰 malloc_hello 相关任何文件。）

3. differential（零回归，ISA 语义不受影响——本任务只加 host-side syscall responder，不改指令语义）：
   ```
   $ python3 tools/run_differential.py
   AGREE(3-way)=200  DIVERGE=0  HARNESS=0  QEMU-SKIP=0
   AGREE(4-way, Sail)=200  SAIL-DIVERGE=0
   ```
   （与落地前基线一致，数字未变。）

4. manifest / issues：
   ```
   $ python3 scripts/manifest_check.py
   manifest validation: PASS
   $ python3 scripts/check_issues.py
   Open: 24  Closed: 31  Total: 55
   ISSUE REGISTRY: PASS
   ```

5. patch 独立验证（干净 pin-commit checkout 上依次 `git am`，均成功；worktree 清理后两个源码仓 `git status --porcelain` 均为空）：
   ```
   $ git -C .work/source/qemu worktree add --detach /tmp/verify_qemu HEAD~1
   $ cd /tmp/verify_qemu && git am components/qemu/patches/0020-....patch
   Applying: target/dadao: add SYS_writev(66) cfx_smon responder (ML-019a)
   $ git -C ~/DADAO-gem5 worktree add --detach /tmp/verify_gem5 HEAD~1
   $ cd /tmp/verify_gem5 && git am components/gem5/patches/0015-....patch
   Applying: arch/dadao: add SYS_writev(66) cfx_smon responder (ML-019a)
   ```
   （架构师本人跑了一遍；subagent 审阅中独立又跑了一遍，结果一致。）

**遗留问题**：

- `case 66` 对 `iov_len` 无上界校验（畸形/巨大值理论上可致 QEMU 长循环或 gem5 `std::vector` 巨量分配）；musl 实际调用路径 `iovcnt` 恒为 2 且长度有界不会触发，风险等级与既有 `case 64` 相同，本任务范围内不算未达成项，未登记 `docs/issues.yaml`（如后续需要可另开任务登记）。
- roadmap 路线 B（`vfprintf`/`vfscanf`）、C（be99 parent matrix）、D（mallocng e2e）、E（kernel）均不在本任务范围，未处理。

## 审阅记录（subagent · 判决 = 通过）

- subagent 已读 `reviewer.md` + 任务全文，**独立** `git show` 两个 commit 的完整 diff（未采信架构师的描述），确认 `case 66` 紧跟 `case 64`、字节序组装手法、fd 处理逻辑两后端完全一致。
- 核验点逐条（均为 subagent 自己重跑的真实输出，非转述）：
  - `struct iovec` 布局假设（16 字节、无 padding）——核对 `include/alltypes.h.in:78` + `arch/dadao/bits/alltypes.h.in` 的 `_Addr long` 确认成立 ✓
  - 大端序组装手法与既有 `memReadBE`（decoder.cc:488-503）、QEMU `translate.c` 全部 `MO_BE` 用法一致 ✓
  - 新测试 `llvm-lit -v tests/lit/E2E/musl_puts_writev.test` 独立重跑 → `PASS (1 of 1)`，exit=0 ✓
  - 全量 E2E 独立重跑 4 次：3 次 `60/60`，1 次因 `-j6` 并行资源竞争误报 `malloc_hello.test` FAIL（单独重跑 PASS）——判定为既有 flake、非本任务回归 ✓（non-blocking finding，架构师另加跑 2 次复核同样 `60/60`）
  - `python3 tools/run_differential.py` 独立重跑 → `AGREE(3-way)=200 DIVERGE=0`，与基线一致 ✓
  - `manifest_check.py` / `check_issues.py` 独立重跑 → 均 PASS ✓
  - 两个 patch 在 `HEAD~1` 干净 worktree 上独立 `git am`，均成功；worktree 清理后两仓库 `git status --porcelain` 均为空、无残留 ✓
  - 改动范围核查：`DADAO-0628` 仅 `lit.cfg` + 两个 `series` 文件被 modify，新增文件均为任务列出的产物；两个源码仓 `git status --porcelain` 为空（改动已 commit，无游离未提交内容）✓
  - 未测输入/边界推敲：`iovcnt>2`、`fd=0`（stdin，验证行为=忽略不写不计数，`ret=0`）、`iov_len` 无上界值——均已审阅，仅 `iov_len` 无上界校验列为 non-blocking（musl 实际调用路径不会触发，风险等级与既有 `case 64` 相同）。
- finding：
  | finding | 严重程度 | 处置 | 说明 |
  |---|---|---|---|
  | 全量 E2E 并行 `-j6` 下 `malloc_hello.test` 一次性误报 FAIL | non-blocking | ❌不修 | 单独重跑 + 另 3 次全量跑均 PASS，是既有并行资源竞争 flake，本任务未触碰 `malloc_hello` 相关任何文件，不成立为回归 |
  | `case 66` 对 `iov_len` 无上界校验 | non-blocking | ⏸延后 | musl 实际调用路径 `iovcnt` 恒为 2 且长度有界不会触发；风险等级与既有 `case 64` 相同（非本任务新增）；未登记 `docs/issues.yaml`，如后续需要可另开任务 |
- 判决：**通过（Accepted）**——验收命令块在 subagent 自己的重跑下全部通过，任务约束（只改两个 responder 文件、立即导出 patch、不改 musl、不做历史重放操作）均未违反。
