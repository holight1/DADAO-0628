# DL-070a: CALL 系列指令 Defs 列表缺 RB31，导致指针返回值调用点 verifier 报 undefined physical register

**执行环境**: 本地 subagent

**状态**: 待处理

## 硬约束（务必遵守，违反视为任务失败）

- **禁止**对 `.work/<component>` 做 `git rebase`/`git am` 重放整条历史/`git reset --hard` 之类操作。只允许在当前 working tree 基础上新增普通 `git commit`，`git format-patch` 追加到 `components/llvm/patches/series`。
- 本任务**只改 LLVM**（`DADAOInstrInfo.td` 及必要的相关文件）。**不要**在本任务里改 musl 侧文件（包括 `arch/dadao/arch.mak` 里的 `-O0` workaround）——那是后续 ML-018a 的范围，本任务只需要在完成区报告"修完之后建议 ML-018a 去验证是否可以移除 -O0"。
- 完成后必须在任务文件里写「完成区」+ subagent 自审「审阅记录」（含逐条 finding + 判决）。
- **如果实现过程中发现根因判断有误、或者改动比预期复杂得多**（比如加了 `RB31` 到 `Defs` 之后引入了新的寄存器分配冲突或差分回归），如实报告，不要为了"看起来完成"而强行让测试通过。

## 背景

架构师在 2026-07-18 实现的 **DL-069a**（`llvm/lib/Target/DADAO/DADAOCallingConv.td` 新增 `RetCC_DADAO` 的 `CCIfPtr<CCAssignToReg<[RB31]>>` 规则，让指针返回值走 RB bank 的 `rb31`，而不是像整数返回值那样统一走 `rd31`）是一个正确的、经过独立 review 的修复，让后端实现追上了 `contracts/abi/spec.md §3.1` 的规定。

但后续 codex 的 `ML-016g/i/j` 三个任务发现：**`DADAOInstrInfo.td` 里 `CALL_IIII`/`CALL_RRII`/`CALL_PSEUDO_INDIRECT` 这几条 call 指令/伪指令的 `Defs` 列表从 DL-069a 之前就一直只写 `Defs = [RD31]`，DL-069a 加了 RB31 返回值这条新路径之后，这个列表没有跟着更新**——具体见 `.work/source/llvm/llvm/lib/Target/DADAO/DADAOInstrInfo.td`：

```tablegen
let isCall = 1,
    Defs = [RD31],
    isPseudo = 1,
    ...
def CALL_PSEUDO_INDIRECT : InstDADAO<(outs), (ins GPRD:$reg), "", []>;
...
let isCall = 1,
    Defs = [RD31] in
let op = 0x6C in def CALL_IIII : F_IIII<(outs), (ins imms24:$imm24), "call $imm24", []>;
let op = 0x6D in def CALL_RRII : F_RRII_JUMP<(outs), (ins GPRB:$rbha, GPRD:$rdhb, imms12:$imm12), "call $rbha, $rdhb, $imm12", []>;
```

`Defs` 列表是告诉 MachineVerifier/寄存器分配器"这条指令执行后，这些物理寄存器的值会被(重新)定义"——`CALL_IIII` 这样只声明 `RD31` 意味着"这条 call 指令执行完，只有 `rd31` 是新定义的返回值寄存器"。DL-069a 之后，任何调用一个**返回指针类型**的函数，`LowerReturn`/`LowerCallResult` 会把返回值放进 `rb31` 而不是 `rd31`——但 call 指令本身的 `Defs` 列表从未声明过 `rb31` 会被定义，于是 MachineVerifier 在 `-O1+`（打开 liveness tracking 之后）看到调用点之后紧跟着一条读取 `$rb31` 的 `COPY` 指令，认为这是"读了一个从未被定义过的物理寄存器"，报错 `Using an undefined physical register`。

**这正是 codex 遇到的、用"全项目 `-O0`" workaround 绕开的那 16 个 musl 编译失败（`docs/reviews/ML-016j-rb31-pointer-return-repro-20260721.md` 的诊断）的真正根因**——`posix_memalign.o`/`memmem.o` 等对象里的 `CALL_IIII` 指令后紧跟 `COPY $rb31`，MachineVerifier 报错，触发 fatal error。`-O0` 之所以能绕开，是因为 `-O0` 用 `RegAllocFast` 且从不打开 `tracksLiveness()`，这条检查根本不会跑（`DADAOInstrInfo.td` 里 `CALL_PSEUDO_INDIRECT` 定义上方已有一段 DL-065a 时代写的注释精确解释了这个"`-O0` 不检查、`-O1+` 才检查"的机制，可以直接参照）。

## 目标

1. **给 `CALL_IIII`/`CALL_RRII`/`CALL_PSEUDO_INDIRECT` 的 `Defs` 列表加上 `RB31`**（从 `Defs = [RD31]` 改成 `Defs = [RD31, RB31]`）。这是本任务的核心改动，预计是 3 处、每处一行的修改。
2. **判断是否还有其它需要同步更新的指令**：
   - `RET_RIII`（`ret $rdha, $imm18`）本身**不需要**改（它是纯 side-effect 指令，不"定义"返回值——返回值的定义发生在**调用方**看到 `CALL_IIII` 之后，不是被调用方执行 `ret` 的那一刻；`LowerReturn` 通过 `CopyToReg`+RET 节点的 glue 操作数机制让 InstrEmitter 正确标记 `RD31`/`RB31` 在函数出口处 live，这条链路本身不受本次改动影响）——但请你自己独立确认这个判断是否正确，不要直接照抄，如果你验证后发现 `RET_RIII` 也需要改，如实报告并处理。
   - 检查是否还有其它 call 相关的 pseudo/real 指令（比如 tail-call 相关的，如果存在的话）同样缺 `RB31`。
3. **验证修复本身**：
   - 独立写一个探针 C 函数（返回指针类型，通过 `call` 调用，返回值立即被使用/被跨调用保存两种情况都要覆盖），编译时打开 `-O1`/`-O2`（不加 `-fno-optimize-sibling-calls` 以外的特殊 workaround），确认 MachineVerifier 不再报错。
   - 用 `ML-016j` 提到的 musl `posix_memalign.c`/`memmem.c` 两个真实 representative（`-O2`，不加 `-O0`）重新编译，确认之前报错的 verifier 错误消失。
4. **回归验证不能有缺口**：
   - `python3 scripts/check_codegen_abi.py`：确认无新增 MISMATCH。
   - `python3 tools/run_differential.py`：与当前基线（`AGREE(3-way)=200 gem5-SKIP=2 DIVERGE=0`，`Sail AGREE(4-way)=200`）完全一致——本任务是纯 CodeGen 层面的 Defs 元数据修正，不改变任何单条指令的语义，理论上不应该影响这个基线。
   - 全量 `.work/build/llvm/bin/llvm-lit tests/lit/E2E/`：重新构建 LLVM 后完整跑一遍，报告所有变化（预期零变化，因为现有 E2E 测试集目前没有覆盖"O2 编译返回指针的函数"这个场景，否则这个 bug 应该早就被 E2E 抓到）。
   - `python3 scripts/manifest_check.py`/`check_issues.py` 通过。
5. **不要求本任务修改 musl**——但完成区需要明确写清楚："建议后续任务（ML-018a）在 musl 源码不变、只去掉 `arch/dadao/arch.mak` 里 `-O0` 覆盖的情况下重新编译，验证 `docs/reviews/ML-017a-*.md` 里记录的 16 个 'undefined physical register' 失败对象是否全部消失"——这句话本身要写进完成区，不需要你自己去验证 musl 编译结果。

## 验收

- `DADAOInstrInfo.td` 里所有 call 相关指令的 `Defs` 列表正确包含 `RB31`（且不引入无关改动）。
- 独立探针（`-O2`，指针返回值函数调用）编译通过、MachineVerifier 无报错。
- musl 两个 representative（`posix_memalign.c`/`memmem.c`，`-O2`，不用 `-O0`）编译通过、无 verifier 错误——**这是本任务最直接的验收标准**，报告具体的编译命令和退出码。
- `python3 scripts/check_codegen_abi.py`、`python3 tools/run_differential.py`（与当前基线一致）、全量 `llvm-lit tests/lit/E2E/`、`manifest_check.py`/`check_issues.py` 全部通过，逐一报告实际输出（不能笼统写"通过"）。
- LLVM 侧改动用**普通** `git commit` 落地，`git format-patch` 导出为新 patch（编号接续 `components/llvm/patches/series` 当前最后一条——如果 IN-005a 已经并行把 0042-0045 占用了，本任务的新 patch 应该编号为 0046 或更靠后，做本任务前先确认 `series` 当前状态，不要假设编号）。

## 参考指针

- `code-agent/tasks/DL-069a-rb-bank-pointer-calling-convention.md`（原始 RB bank 修复，含它自己独立复核时用的 §2.3 边界探针方法，可以参照同样的验证严谨度）
- `code-agent/tasks/ML-016j-rb31-pointer-return-repro.md` + `docs/reviews/ML-016j-rb31-pointer-return-repro-20260721.md`（本任务要解决的问题的完整诊断，包含具体的 machine-code dump 证据）
- `code-agent/tasks/ML-016g-backend-failure-cluster.md`、`ML-016i-dynamic-stackalloc-minimal-repro.md`（相关的失败簇分类，帮助判断本任务修复能覆盖 16 个失败对象里的多少个）
- `docs/reviews/ML-017a-post-frame-musl-object-matrix-20260721.md`（当前 16 个"undefined physical register"失败对象清单，本任务修完后可以对照）
- `.work/source/llvm/llvm/lib/Target/DADAO/DADAOInstrInfo.td`（`CALL_PSEUDO_INDIRECT` 定义上方已有 DL-065a 时代关于"-O0 不检查 liveness"的详细注释，直接参照理解机制）
- `docs/reviews/codex-run-integrity-audit-2026-07-21.md` §4（musl `-O0` workaround 的完整披露和依赖分析）

## 完成区

**状态**：已完成

**修改文件**：

- `.work/source/llvm/llvm/lib/Target/DADAO/DADAOInstrInfo.td`（`.work/llvm` 内 git commit `b72d02c8a864`，落在 `d3bd9c15434f` 之上）——
  1. `CALL_PSEUDO_INDIRECT`：`Defs = [RD31]` → `Defs = [RD31, RB31]`，附新增注释解释 DL-070a 根因。
  2. 覆盖 `CALL_IIII`/`CALL_RRII` 的共享 `let isCall = 1, Defs = [RD31] in` 块：→ `Defs = [RD31, RB31]`，同样附注释。
  3. `RET_RIII`：**未改**（独立验证后确认架构师初判正确，见下「RET_RIII 独立验证」），附新增注释记录判断依据，供后来者不必重新推导。
  - `git diff --stat`：`1 file changed, 20 insertions(+), 2 deletions(-)`（3 处实质性 `Defs` 改动 + 2 段解释性注释块，无无关改动）。
- `components/llvm/patches/0046-dadao-call-defs-rb31-missing.patch`（新增，`git format-patch -1 HEAD --start-number=46` 从上述 commit 导出）+ `components/llvm/patches/series`（追加第 46 行）。导出前核实 `series` 当前最后一条是 `0045-DADAO-round-frame-size-to-ABI-alignment.patch`（IN-005a 已并行占用 0042-0045，与任务文件写作时的预判一致），新 patch 编号为 0046，非假设。

**RET_RIII 独立验证**（任务要求不直接照抄架构师初判）：

- 读 `DADAOInstrInfo.cpp` 的 `expandPostRAPseudo`，`RET_PSEUDO` case：`BuildMI(MBB, MI, DL, get(DADAO::RET_RIII)).addReg(DADAO::RD0).addImm(0)`——`RET_RIII` 的 `$rdha` outs 操作数被硬编码为 `RD0`，从未承载真实返回值，注释「rdha = rd0 (value already in $rd31)」印证这一点。
- 读 `DADAOISelLowering.cpp` 的 `LowerReturn`：对每个 `RVLocs`（由 `RetCC_DADAO` 决定落在 `rd31` 或 `rb31`）都执行 `DAG.getCopyToReg(Chain, DL, VA.getLocReg(), OutVals[i], Glue)`，并把 `DAG.getRegister(VA.getLocReg(), ...)` 压进 `RetOps`、随 `DADAOISD::RET_GLUE` 节点一起 glue——这是 LLVM 标准机制：InstrEmitter 把这些 glued 寄存器操作数转成返回指令上的 implicit-use 操作数，verifier 需要的"reaching definition"来自**更早的 CopyToReg 指令**（一条普通指令），不是 `RET_RIII` 本身。
- 边界情形核查：`grep -rn "tailcall|TCRETURN|shouldGuaranteeTCO|isEligibleForTailCallOptimization"` 全仓库 0 命中——本后端完全没有 tail-call/sibling-call 支持，不存在"直接跳到 callee、绕过 CopyToReg 链"的替代返回路径会让这个推理失效。
- **结论：独立验证确认架构师初判正确，RET_RIII 不需要改。**

**验收结果**（均为本人真实重跑，非估算）：

1. **独立探针**（`/tmp/.../dl070a_probe.c`：direct/use/save-across-call/nested/indirect 五种指针返回调用形状）：
   - `clang --target=dadao -O2 -fno-optimize-sibling-calls -S/-c` → **exit 0**（`-fno-optimize-sibling-calls` 是任务文件明确允许的唯一 workaround，用于绕开一个独立已知、无关的 tail-call assertion——`return helper1(...)` 在纯 `-O2` 下会被识别为 sibling call 触发 `LowerCall emitted a return value for a tail call!`，这是 ML-016j/ML-016k 已记录的另一个独立后端缺口，不在本任务范围）。
   - 反汇编确认每个 `call helper1` 后紧跟 `rb2rd rdX, rb31, 1`——正是此前触发 verifier 报错的确切模式，现在编译干净通过。

2. **musl 两个 representative（真实 make 目标，非独立拷贝）**：
   ```
   cd .work/build/musl
   rm -f obj/src/malloc/posix_memalign.o obj/src/string/memmem.o
   make obj/src/malloc/posix_memalign.o   → exit 0
   make obj/src/string/memmem.o           → exit 0
   ```
   **重要澄清**：`make -n` 显示实际编译命令行尾部是 `... -fno-optimize-sibling-calls -O0 -O3 -c ...`——`-O0` 来自 `arch/dadao/arch.mak`（未改动），但 musl 上游 `Makefile` 第 119 行的 `OPTIMIZE_SRCS`/`OPTIMIZE_GLOBS` 规则（覆盖 `malloc/*.c`、`string/*.c`）在其后追加了 `-O3`，clang 以最后一个 `-O` 为准，**这两个文件实际编译级别是 `-O3`，比任务要求的 `-O2` 更严格**，而不是文件名字面暗示的 `-O0`。也解释了为什么 `arch.mak` 的 `-O0` "workaround" 对这两个文件从未真正生效——`docs/reviews/ML-017a-post-frame-musl-object-matrix-20260721.md` 的 `object-results.tsv` 证实这两个 `.o` 正是当前 16 个 "machine verifier: undefined physical register" 失败对象之一，编译级别与本任务的诊断完全吻合。
   - 反汇编 `posix_memalign.o` 确认 `call 0` 后紧跟 `rb2rd rd16, rb31, 1`（读 `aligned_alloc` 的指针返回值），修复前必现的 verifier 报错现在不再出现。
   - 额外用 `make -k -j6 lib/libc.a`（5 分钟内跑到自然结束，非 timeout 强杀）对全 musl 源码树做更广覆盖：`grep -c "undefined physical register"` = **0**（此前 16 个），`unsupported library call operation` = 155、`dynamic_stackalloc/Cannot select` = 7（均为已知、与本任务无关的既有后端缺口，数量与 ML-017a 基线 157/7 基本一致，无回归）。**此项为本任务验收标准之外的额外证据，非强制项，但进一步确认 RB31 verifier 报错这一簇已在真实 musl 全树范围内清零。**

3. `python3 scripts/check_codegen_abi.py`：
   ```
   MATCH=23  OPEN-COMMIT=3  INFO=2  MISMATCH=0
   RESULT: PASS (no MISMATCH; OPEN-COMMIT/INFO are advisory)
   ```
   与改动前基线逐位一致（本任务是纯 Defs 元数据修正，不改变 CC 分析结果，符合预期）。

4. `python3 tools/run_differential.py`：
   ```
   === AGREE(3-way)=200  AGREE(interp+QEMU, gem5-SKIP)=2  DIVERGE=0  HARNESS=0  QEMU-SKIP=0 ===
   === SAIL 4th column: AGREE(4-way)=200  Sail-SKIP(out-of-slice)=2  SAIL-DIVERGE=0 ===
   ```
   与任务文件写作时记录的基线（`AGREE(3-way)=200 gem5-SKIP=2 DIVERGE=0`、`Sail AGREE(4-way)=200`）**完全一致**，零回归。

5. 全量 `.work/build/llvm/bin/llvm-lit tests/lit/E2E/`：
   ```
   Total Discovered Tests: 59
     Passed: 59 (100.00%)
   ```
   **重要澄清（避免误报邀功）**：本任务开始时 E2E 套件已是 59/59 全 PASS（含 `malloc_hello.test`/`printf_hello.test`）——这两个测试此前在 DL-069a 完成时是 56/58 PASS（2 个失败），但 ML-013a（已独立完成，落在本任务开始之前）已把 `tests/scripts/pico_stubs.s` 改为按 RB bank 约定读取指针参数，使这两个测试恢复 PASS；且这两个测试的 C 代码部分（`stdout_min.c`/`malloc_hello.c`）都用 `-O0` 编译（RUN 行明确写 `-O0`），从不触发 -O1+ 才激活的 MachineVerifier liveness 检查，所以它们的 PASS 与本任务的 Defs 修复无因果关系。全仓库 grep 确认没有任何 E2E lit 测试在 `-O1` 及以上编译一个"返回指针类型的函数"（`clang_hello.test` 虽用 `-O1` 但只到 `-emit-llvm`，不过 codegen 后端；`tp_probe.test` 提到 `-O2` 只是注释、实际测试是纯手写汇编）——**这正是任务文件本身的预期**："现有 E2E 测试集目前没有覆盖'O2 编译返回指针的函数'这个场景，否则这个 bug 应该早就被 E2E 抓到"。因此本任务对 E2E 套件的真实增量贡献是**零变化**（59→59，不是回归也不是新增修复），验证方式是 (1) musl 真实 representative 直接 make 重编译 + (2) 独立探针，而非 E2E 套件。

6. `python3 scripts/manifest_check.py`：`manifest validation: PASS`。
7. `python3 scripts/check_issues.py`：`ISSUE REGISTRY: PASS`（Open 24 / Closed 31）。本任务未涉及任何 issue 开闭（不是 issues.yaml 登记的条目，未新开/未关闭 issue）。

**LLVM patch 可重放性验证**：独立 `git clone` + `checkout --detach d3bd9c15434f` + `git am 0046-dadao-call-defs-rb31-missing.patch` → 干净应用成功（`AM_EXIT=0`）。

**遗留问题**：

- **建议后续任务（ML-018a）**：在 musl 源码不变、只去掉 `arch/dadao/arch.mak` 里 `CFLAGS_AUTO += -O0` 那一行覆盖的情况下重新编译，验证 `docs/reviews/ML-017a-post-frame-musl-object-matrix-20260721.md` 记录的 16 个 "undefined physical register" 失败对象是否全部消失（本任务已经证实其中 2 个代表性对象——`posix_memalign.o`/`memmem.o`——单独编译时确实消失，且全树 `make -k` 复测显示该错误簇计数归零，但完整 archive/link/runtime 验收留给 ML-018a）。
- 非阻断观察：任务文件里预估验收用 `-O2`，实测这两个 musl representative 因 `OPTIMIZE_GLOBS` 规则实际editor编译级别是 `-O3`（细节见上方"验收结果 2"），比要求更严格，不构成缺口。

## 审阅记录（subagent）

**判决 = 通过（Accept）**

subagent 独立读取任务文件 + `.work/source/llvm` 内 `git show HEAD` diff + `DADAOInstrInfo.cpp`/`DADAOISelLowering.cpp`/`DADAORegisterInfo.cpp` 相关代码，未采信任何转述数字，逐项重新执行命令核验：

1. **diff 最小性/正确性**：直接读 `DADAOInstrInfo.td` 95-374 行，确认恰好 3 处 `Defs = [RD31]` → `Defs = [RD31, RB31]` 语义改动 + 2 段新增解释性注释，无无关改动；`git show HEAD` 确认 `+20 -2` 单文件改动。**判定：符合描述。**
2. **RET_RIII 独立验证**（任务要求的关键判断点）：读 `DADAOInstrInfo.cpp` L168-174 确认 `$rdha` 硬编码为 `RD0`；读 `DADAOISelLowering.cpp` `LowerReturn` L302-326 确认返回值通过 `CopyToReg`+glue 机制在 `RET_RIII` 执行前完成定义，InstrEmitter 据此生成 implicit-use 操作数；全仓库 grep `tailcall|TCRETURN|shouldGuaranteeTCO|isEligibleForTailCallOptimization` 零命中，确认本后端无 tail-call 替代返回路径会使该推理失效。**独立结论：同意架构师初判，RET_RIII 无需改动。**
3. **完备性检查**：全文件 grep `isCall` 仅 2 处命中，均已修复（`CALL_PSEUDO_INDIRECT` + `CALL_IIII`/`CALL_RRII` 共享块）；无 tail-call pseudo 遗漏。**判定：无遗漏。**
4. **越界/副作用检查**：读 `DADAORegisterInfo.cpp` 确认 `getCalleeSavedRegs`（仅 RD8-15）与 `getReservedRegs`（仅 RD0-7/RB0-7）均不含 RB31，RB31 是普通 caller-saved 可分配寄存器，`Defs` 新增 RB31 与 `getCallPreservedMask` 逻辑一致，不产生"call 后本该存活的寄存器被误标记为 clobbered"矛盾。**判定：无越界风险。**
5. **独立复跑构建/测试**（subagent 亲自执行，非转述）：`check_codegen_abi.py` → `MATCH=23/MISMATCH=0`；`run_differential.py` → `AGREE(3-way)=200/AGREE(4-way)=200/DIVERGE=0`；musl 真实 representative 重编译 → exit 0 无 verifier 错误（并独立发现 `-O0`/`-O3` 双 `-O` 标志、`-O3` 实际生效这一细节，与本报告"验收结果 2"一致）；`llvm-lit tests/lit/E2E` → 59/59 PASS。
6. **导出 patch 核验**：`components/llvm/patches/0046-dadao-call-defs-rb31-missing.patch` 存在且是 `series` 最后一行；独立 `git format-patch -1 HEAD --stdout` 重新生成并与仓库内文件逐字节 diff——**完全一致**。
7. **硬约束核验**：`.work/source/llvm` `git log --oneline` 确认单条新提交线性叠加、无 rebase/reset；`git status`（`.work/source/llvm`、`.work/source/musl`）干净；主仓库 `git status` 只有 `components/llvm/patches/series` 符合预期改动（另有 IN-005a/其它并行任务的无关改动，与本任务无关）；确认未改动任何 musl 源文件（`arch/dadao/arch.mak` 等）。

| finding | 处置 | 改了什么 | 复验证据 |
|---|---|---|---|
| 无（零 finding） | — | 无 | 见上 7 项逐条核验，均独立复现通过 |

**AC 结论**：无任何 finding 需要处置，完成区状态"已完成"与本判决一致。

## 架构师复核（ground-truth）

**独立验证方法**：不采信完成区/subagent 判决，从 git 状态开始逐项重跑，本任务是这一批收尾任务里技术含量最高的一项（真正修复而非文档化绕过），复核力度按 DL-069a 同等标准执行。

- `git status`（`.work/source/{llvm,musl}`）：均干净；`.work/source/llvm` 干净单提交 `b72d02c8a864` 落在 `d3bd9c15434f`（IN-005a 导出的 0045 源 commit）之上。
- 逐行读 `DADAOInstrInfo.td` diff：3 处 `Defs = [RD31]` → `Defs = [RD31, RB31]` 精确对应 `CALL_PSEUDO_INDIRECT`/`CALL_IIII`/`CALL_RRII`，无无关改动。
- **独立复现 `RET_RIII` 不需要改的判断**：读 `DADAOInstrInfo.cpp` 的 `expandPostRAPseudo` 确认 `RET_PSEUDO` 硬编码 `$rdha=RD0`；读 `LowerReturn` 确认返回值定义发生在更早的 `CopyToReg`+glue 链路，`RET_RIII` 执行前已完成；全仓库 `grep -rn "tailcall\|TCRETURN\|shouldGuaranteeTCO\|isEligibleForTailCallOptimization"` 零命中，确认无 tail-call 替代路径会使这条推理失效——**独立同意**架构师初判和 subagent 复核的结论。
- **独立重建 LLVM**（`ninja -C .work/build/llvm clang llc lld llvm-objcopy`），二进制时间戳晚于 `b72d02c8a864`，排除陈旧构建陷阱。
- **独立复现 musl 两个 representative 的 `-O0`/`-O3` 双 `-O` 细节**：`make -n obj/src/malloc/posix_memalign.o` 确认命令行确实是 `... -fno-optimize-sibling-calls -O0 -O3 ...`（clang 以最后一个 `-O` 为准，实际生效 `-O3`）；`rm -f` 该 `.o` 后重新 `make` 两个 representative，均 exit 0。
- **独立跑全树 `make -k -j6 lib/libc.a` 复测**（不复用 subagent 的运行结果）：`grep -c "undefined physical register"` → **0**（此前 16），`unsupported library call operation` → 154，`dynamic_stackalloc` → 7——与完成区声称的簇计数基本一致（libcall 154 vs 完成区记录的 155，个位数出入判断为并行构建日志交错的既有已知现象，不影响"该簇归零"这个核心结论）。
- 全量 `llvm-lit tests/lit/E2E/` → **59/59**；`python3 tools/run_differential.py` → `AGREE(3-way)=200/gem5-SKIP=2/DIVERGE=0`，`Sail AGREE(4-way)=200`——与基线一致，零回归。`manifest_check.py`/`check_issues.py` 均 PASS。
- **独立验证 patch 可重放性**：`git clone` 全新副本 + `checkout --detach d3bd9c15434f` + `git am 0046-*.patch` → 干净应用。

**结论**：**DL-070a 验收通过**——这是本轮收尾任务里最有价值的一项：把 codex 阶段用全项目 `-O0` workaround 绕开的真实后端 bug（`CALL` 系列指令 `Defs` 缺 `RB31`）从根源修复，独立复现确认 musl 全树"undefined physical register"失败簇从 16 归零。`RET_RIII` 不需要改这条非显然的判断，架构师、subagent、本次复核三方独立得出同一结论，值得信任。**下一步（ML-018a）**：去掉 `arch/dadao/arch.mak` 的 `-O0` 覆盖，用真实 `-O2`/`-O3` 重新构建+验收完整 musl archive/link/runtime，确认这个 workaround 可以被安全移除。
