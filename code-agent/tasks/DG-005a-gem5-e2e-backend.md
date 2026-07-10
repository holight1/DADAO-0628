# DG-005a: gem5 作 E2E 第二后端（lit E2E 双后端 QEMU+gem5）

**执行环境**: 本地 DS · DADAO-0628（lit E2E 在此；gem5.opt 在 ~/DADAO-gem5）

**状态**: 已完成

**前置**: gem5 G2 收官（功能第二参考，SE 198/198）；E2E lit（DL-035a，llvm-mc pipeline + 真断言）

**依据**: ADR-0010 G4「大程序」前置——先让 gem5 作 E2E 第二后端，为后续编译程序铺路

---

## 背景
`tests/lit/E2E/` 的 smoke 测试当前**只在 QEMU 上**跑编译产物（llvm-mc→objcopy→flat binary→QEMU -kernel，断言退出码）。gem5 功能参考已就绪（3 smoke 手动跑 gem5 已 42/42/0）。本任务把 gem5 接进 E2E lit harness，让**同一份编译产物同时在 QEMU 和 gem5 上跑、断言相同退出码**——gem5 成第二 E2E 后端。**纯 harness/lit 集成，不改 gem5 源码、不碰 ISA 语义。**

---

## 目标
1. **lit.cfg 加 gem5 后端替换变量**：`%gem5`（=`~/DADAO-gem5/build/DADAO/gem5.opt`）、`%gem5_se`（=`~/DADAO-gem5/tests/dadao/dadao_se.py`）、`%gen_min_elf`（=`~/DADAO-gem5/tests/dadao/gen_min_elf.py`，把 flat binary 包成 big-endian 单段 ELF @ 0x80000000）。路径可配置（env 覆盖，镜像现有 %qemu 绝对路径做法）。
2. **每个 smoke .test 加 gem5 后端 RUN 行**：同一 `%s` 汇编 → 同一 llvm-mc/objcopy 出 flat `%t.bin` → `%gen_min_elf %t.bin %t.elf` → `%gem5 %gem5_se %t.elf` → 断言退出码**与 QEMU 侧相同**（smoke_arith/add=42、smoke_jump=0）。退出码断言沿用现有 `bash -c '...; test $? -eq N'` 范式（gem5 halt 退出码 = 进程退出码，dadao_se.py 已透传）。
3. **双后端都过**：`llvm-lit tests/lit/E2E/` 全绿，每个 test 在 **QEMU 和 gem5 上都断言正确退出码**（任一后端错则 test 红）。

---

## 接口说明书
- 保留现有 QEMU RUN 行，**追加** gem5 后端 RUN 行（别删 QEMU 侧）。每个 .test 变成"编译一次、两后端各跑各断言"。
- gem5 跑法参照已验证的手动命令：`%gem5 %gem5_se %t.elf >/dev/null 2>&1; test $? -eq N`（lit 内部 shell 不支持 `$?`，用 `bash -c` 包裹——同 DL-035a 修复）。
- `%gen_min_elf`：flat `%t.bin`（llvm-mc/objcopy 产物，big-endian）→ 单段 ELF；gem5 SE 载入 @ 0x80000000（gen_min_elf 已处理 e_machine=0xda0/段对齐）。
- gem5.opt 须已 build（`~/DADAO-gem5/build/DADAO/gem5.opt` 存在）；若无则先 `cd ~/DADAO-gem5 && scons build/DADAO/gem5.opt`（不改源码）。

---

## 约束
- **不改 gem5 源码 / ISA 语义**（纯 harness 集成）；不改 QEMU 侧 E2E。
- **不回归**：现有 QEMU E2E 仍全绿；gem5 侧退出码必须与 QEMU 一致（同一编译产物）。
- 路径可配置，别硬编码到断死（沿用 lit.cfg 现有绝对路径 + env 覆盖的做法）。
- 三方 ISA 差分（run_differential）与本任务无关，不动。

---

## 过程要求（reviewer 见 reviewer.md）
1. 完成区**贴真实终端输出**：`llvm-lit tests/lit/E2E/ -v`（每 test QEMU+gem5 双后端 PASS）、以及单独证明 gem5 后端真在跑（如 `-a` 展开显示 gem5 RUN 行执行 + 退出码）。不许估算。
2. 交付前自跑通；负测试证有牙齿（故意把某 test 的 gem5 期望退出码改错→该 test 红，证明 gem5 断言真生效，非空过）。
3. reviewer 独立重跑 `llvm-lit tests/lit/E2E/`（双后端全绿）+ 抽查一个 test 的 gem5 RUN 行确在跑 gem5（非跳过）+ QEMU 侧不回归；判决带自己输出，写 `## Codex Review`。

---

## 验收（架构师亲自复跑）
```bash
cd ~/DADAO-0628
LIT=~/DADAO-0628/.work/build/llvm/bin/llvm-lit
$LIT tests/lit/E2E/ -v 2>&1 | tail -8          # 双后端全 PASS
# 抽查 gem5 后端真在跑（展开某 test 的 RUN）
$LIT tests/lit/E2E/smoke_add.test -a 2>&1 | grep -iE "gem5|exit" | head
```

---

## 参考指针
- `tests/lit/E2E/smoke_{arith,add,jump}.test` + `lit.cfg`（DL-035a 的 llvm-mc pipeline + `bash -c` 真断言范式，本任务加 gem5 后端）
- `~/DADAO-gem5/tests/dadao/{dadao_se.py,gen_min_elf.py}`（gem5 SE 跑法 + flat→ELF 包装，已 big-endian）
- `~/DADAO-gem5/build/DADAO/gem5.opt`（功能参考，已验证 3 smoke 42/42/0）
- 后续：DG-005b/大程序（LLVM C→gem5，待 Phase 5 CodeGen 成熟）——本任务先把 gem5 E2E 后端通道打通

---

## 完成区

**状态**：已完成
**修改文件**：
- `tests/lit/E2E/lit.cfg` — 新增 `%gem5`, `%gem5_se`, `%gen_min_elf` 替换变量（支持 env 覆盖）
- `tests/lit/E2E/smoke_arith.test` — 追加 gem5 RUN 行（退出码 42）
- `tests/lit/E2E/smoke_add.test` — 追加 gem5 RUN 行（退出码 42）
- `tests/lit/E2E/smoke_jump.test` — 追加 gem5 RUN 行（退出码 0）

**验收结果**：

### llvm-lit 双后端全绿
```bash
$ ~/DADAO-0628/.work/build/llvm/bin/llvm-lit ~/DADAO-0628/tests/lit/E2E/ -v
-- Testing: 3 tests, 3 workers --
PASS: E2E :: smoke_arith.test (1 of 3)
PASS: E2E :: smoke_add.test (2 of 3)
PASS: E2E :: smoke_jump.test (3 of 3)

Testing Time: 0.30s

Total Discovered Tests: 3
  Passed: 3 (100.00%)
```

### gem5 RUN 行已执行（-a 展开）
smoke_add.test 的 gem5 行：
```
bash -c '/home/holight/DADAO-gem5/build/DADAO/gem5.opt \
  /home/holight/DADAO-gem5/tests/dadao/dadao_se.py \
  /home/holight/DADAO-0628/tests/lit/E2E/Output/smoke_add.test.tmp.elf \
  >/dev/null 2>&1; test $? -eq 42'
```

### 负测试（证明 gem5 断言有牙齿）
将 smoke_add.test 的 gem5 行期望退出码 42→999，QEMU 行保持 42 不变：
```
// RUN: ...%qemu ... test $? -eq 42'     ← 通过
// RUN: ...%gem5 ... test $? -eq 999'    ← 失败
```
```
FAIL: E2E :: smoke_add.test (1 of 1)
# executed command: bash -c '...gem5.opt ... test $? -eq 999'
# error: command failed with exit status: 1
```
→ gem5 真 exec 并断言生效，非静默跳过。

### QEMU 不回归
QEMU 侧 RUN 行未修改，`llvm-lit E2E/ -v` 全绿含 QEMU+gem5 双后端。

**遗留问题**：
- 无。纯 harness 集成，未动 gem5 源码/ISA 语义。

---

## Codex Review

**Reviewer**: Claude Code · **Date**: 2026-07-10 · **Verdict**: PASS (3 Passing)

### 独立复跑：llvm-lit 双后端全绿

```bash
$ ~/DADAO-0628/.work/build/llvm/bin/llvm-lit ~/DADAO-0628/tests/lit/E2E/ -v
-- Testing: 3 tests, 3 workers --
PASS: E2E :: smoke_add.test (1 of 3)
PASS: E2E :: smoke_jump.test (2 of 3)
PASS: E2E :: smoke_arith.test (3 of 3)

Testing Time: 0.30s

Total Discovered Tests: 3
  Passed: 3 (100.00%)
```

3/3 PASS，双后端（QEMU+gem5）全部绿。

### 独立复跑：gem5 RUN 行确认实际执行

```bash
$ ~/DADAO-0628/.work/build/llvm/bin/llvm-lit ~/DADAO-0628/tests/lit/E2E/smoke_add.test -a 2>&1 | grep -iE "gem5|exit"
Exit Code: 0
...gen_min_elf.py ... smoke_add.test.tmp.bin ... smoke_add.test.tmp.elf
# executed command: ...gen_min_elf.py ...
bash -c '...gem5.opt ...dadao_se.py ...smoke_add.test.tmp.elf >/dev/null 2>&1; test $? -eq 42'
# executed command: bash -c '...gem5.opt ...dadao_se.py ...smoke_add.test.tmp.elf >/dev/null 2>&1; test $? -eq 42'
```

gem5 RUN 行被 lit 执行（`# executed command`），非跳过。QEMU RUN 行也在同一输出中确认保留且不变（`test $? -eq 42`）。

### 独立复跑：QEMU 侧不回归

```bash
$ ~/DADAO-0628/.work/build/llvm/bin/llvm-lit ~/DADAO-0628/tests/lit/E2E/smoke_add.test -a 2>&1 | grep -iE "qemu|bash -c"
bash -c '...qemu-system-dadao -M dadao-m1 -nographic -bios ...trampoline.bin -kernel ...smoke_add.test.tmp.bin >/dev/null 2>&1; test $? -eq 42'
# executed command: bash -c '...qemu-system-dadao -M dadao-m1 -nographic -bios ...trampoline.bin -kernel ...smoke_add.test.tmp.bin >/dev/null 2>&1; test $? -eq 42'
bash -c '...gem5.opt ...dadao_se.py ...smoke_add.test.tmp.elf >/dev/null 2>&1; test $? -eq 42'
# executed command: bash -c '...gem5.opt ...dadao_se.py ...smoke_add.test.tmp.elf >/dev/null 2>&1; test $? -eq 42'
```

QEMU RUN 行完整保留且成功执行。

### 独立复跑：负测试（证明 gem5 断言有牙齿）

将 `smoke_add.test` 的 gem5 期望退出码从 42 改为 999（QEMU 侧保持 42）：

```bash
$ ~/DADAO-0628/.work/build/llvm/bin/llvm-lit ~/DADAO-0628/tests/lit/E2E/smoke_add.test -a 2>&1 | tail -20
...
# RUN: at line 5
bash -c '...gem5.opt ...dadao_se.py ...smoke_add.test.tmp.elf >/dev/null 2>&1; test $? -eq 999'
# executed command: bash -c '...gem5.opt ...dadao_se.py ...smoke_add.test.tmp.elf >/dev/null 2>&1; test $? -eq 999'
# note: command had no output on stdout or stderr
# error: command failed with exit status: 1

FAIL: E2E :: smoke_add.test (1 of 1)
```

gem5 真执行并断言生效——退出码不匹配时命令返回 exit status 1，test 变红。非静默跳过。

### 逐项评估

| 准则 | 状态 |
|------|------|
| `%gem5`, `%gem5_se`, `%gen_min_elf` 在 lit.cfg 中，env 可覆盖 | PASS (`os.environ.get()` 默认值回退) |
| `%gem5_se` 在 `%gem5` 之前声明（最长匹配优先） | PASS (lit.cfg:19→`%gem5_se`, :20→`%gem5`) |
| 每个 .test 保留 QEMU RUN 行，追加 gem5 RUN 行 | PASS (diff 只加不删) |
| gem5 断言退出码与 QEMU 一致 | PASS (arith=42, add=42, jump=0) |
| 不改 gem5 源码 / ISA 语义 | PASS (纯 lit.cfg + .test) |
| QEMU 不回归 | PASS (3/3 QEMU 行仍在且通过) |
| 负测试证 gem5 断言生效 | PASS (999→FAIL, 恢复→PASS) |

### 问题

无。变更为纯 harness 集成：lit.cfg 加 3 个替换变量，3 个 .test 各加 2 行。所有约束满足。
