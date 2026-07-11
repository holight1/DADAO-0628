# DL-061b: CodeGen — 全局变量（rela PC 相对 + .data 管道 + 双后端）

**执行环境**: 本地 DS · DADAO-0628（LLVM backend + QEMU target + E2E）

**状态**: 部分完成（ISel 全部就绪，.data 管道需链接器——见遗留）

**前置**: DL-061a（wyde 常量物化）。全局变量地址物化路线定为 **rela（PC 相对）**，非绝对地址。

---

## 完成区

**状态**：部分完成
**已完成**：
1. ✅ QEMU-rb0 已修（commit 3e0e57c，trans_rela 用 ctx PC+4，无需再改）
2. ✅ rb-ops.yaml case[4] 已 sync（expected 0x80001000）
3. ✅ LLVM GlobalAddress ISel：Custom lowering → DADAOISD::PCREL_HI → RELA_RIII
4. ✅ PCREL_HI→load/store：rela + ldo/sto 组合 emit
5. ✅ MC fixups：fixup_dadao_rela_page（imm18 页差）+ fixup_dadao_rela_lo（页内偏移）

**ISel 验证**：
```asm
@ g = global i64 42
load @g:
    rela rb8, g       ← PCREL_HI fixup
    ldo rd31, rb8, 0  ← page offset = 0 (needs lo fixup for non-aligned)
```

**E2E 回归**：15/15 PASS, AGREE(4-way)=200, DIVERGE=0

**遗留**：
- **.data 管道需链接器**：llvm-mc 产 .data 在独立 ELF 段，objcopy 只取 .text；跨段 PCREL fixup 须链接器解析。无 lld/dadao 链接器
- **ldo 页偏移**：lo fixup 已定义但 ldo imm12 非 expr 路径（需 MC 层 operand 改造）
- 路线备选：DG-006b 后可引入 lld-linker 或 inline-data（.text embedded）绕过

## 路线（重要，先读）
当前 E2E 管道**无链接器**（`.s → llvm-mc → objcopy --only-section=.text → flat binary`，加载于 0x80000000）。因此：
- **绝对地址不可行**：绝对 VA 需链接器分配，没有 ld/lld。
- **PC 相对（rela）可行**：`call`/`branch` 证明**同一汇编单元内的 PC 相对 fixup 汇编器（llvm-mc）能在汇编期解析**（符号在同一 .text/.data blob，偏移可算），无需链接器。
- 故全局地址走 **rela（PC 相对，类 RISC-V `auipc`+`addi`/`ld`）**：`rela` 取 PC 页基址（§4.8：base=rb0[47:0]&~0xFFF），再加低位偏移形成地址。

## 缺口（现状复现）
```
llc: @g=global i64 42; load @g → LLVM ERROR: Cannot select: GlobalAddress<ptr @g>
```
GlobalAddress 完全没 lower。且 **QEMU-rb0 bug**（issue `QEMU-rb0-not-maintained`）令 QEMU 里 rela 读 rb0=0 → 地址错，必须先修。

## 目标
让 llc 能编译**全局变量的读写**，双后端跑对。

1. **修 QEMU-rb0**（前置，issue 已诊断）：QEMU `target/dadao` 从不维护 `env->rb[0]=PC+4`（spec §1.3/§4.8）。按 issue 修 `trans_rela` 用 ctx PC+4（参 RISC-V auipc 用 `ctx->base.pc_next`）；**同步修** `tests/vectors/isa/rb-ops.yaml` case[4] expected `0x1000→0x80001000`（issue 明列，须同时落地，否则差分 DIVERGE）。QEMU 改动入 `components/qemu/patches/` 新 patch。**先确认 gem5 是否维护 rb0**（跑 rela 向量看 gem5 是否已对；若 gem5 也不维护，一并修 gem5，参 DG-006a/b 方式）。
2. **GlobalAddress lower（rela PC 相对 hi/lo）**：`GlobalAddress` → `rela`（PC 相对高位，取符号页基址）+ `ldo`/`addi`（低位页内偏移），两个 fixup（如 `fixup_dadao_rela_hi` / `_lo`，参 DL-056b/058a 的 call/branch fixup 范式 + RISC-V `%pcrel_hi`/`%pcrel_lo`）。同 blob 全局由 llvm-mc 汇编期解析。load/store 全局 = 物化地址 + ldo/sto。
3. **.data 管道**：全局的初值数据入 `.data`，产出的 flat 镜像含 `.text`+`.data`（改 objcopy 纳入 .data，或 .text/.data 连续布局）；**双后端加载**——QEMU flat（trampoline 加载整镜像于 0x80000000）、gem5 用 `gen_min_elf` 的 `data_segs`（已支持 RW PT_LOAD 段）把 .data 放对 VA。

## 约束
- 编译器改动在 `.work/source/llvm/`；QEMU 改动在 `.work/source/qemu/target/dadao` + patch；语义按 spec §4.8（rela）、§1.3（rb0）。
- **不回归**：lit E2E 现 15 例全绿 + 四方差分（修 rb0 + 同步向量后）AGREE(4-way)=200/DIVERGE=0 + DL-050a~061a 产物。
- 新增 E2E 入 `tests/lit/E2E/`（双后端 QEMU+gem5 断言退出码）。
- **禁**：手搓 .s、grep-only 测试、`|| true`、全常量折叠（判别值须运行时真跑）。

## 验收（架构师亲自复跑；被测=真 llc 产物）
```bash
cd ~/DADAO-0628
(cd .work/source/qemu/build && ninja qemu-system-dadao 2>&1 | tail -1); ninja -C .work/build/llvm llc llvm-mc
# 全局读写程序：@g 初值 → load → 改 → store → 再 load，双后端退出码 = 预期
# 例：@g=global i64 40; main{ %a=load @g; %b=add %a,2; store %b,@g; %c=load @g; ret %c } → 42
llvm-lit -v tests/lit/E2E/ 2>&1 | tail            # 全 PASS（含新增 global 用例，双后端）
python3 tools/run_differential.py 2>&1 | tail -3  # AGREE(4-way)=200 / DIVERGE=0（rb0 修后不回归）
```

**验收强调（架构师会加做判别探针）**：
- 全局程序**读初值 + 写回 + 再读**，双后端退出码一致且=预期（防"只 load 没 store"或地址错却碰巧对）。
- **多个全局**（不同偏移）+ 全局数组（`@arr=global [N x i64]` 变址访问），验证 rela 地址物化对不同符号/偏移都对。
- QEMU-rb0 修后：`rela` 向量（rb-ops）四方 AGREE，且 rb0 为源的其它路径（call 返回地址等）不回归。

## 参考指针
- issue `QEMU-rb0-not-maintained`（诊断 + 修法：trans_rela 用 ctx PC+4 + rb-ops case[4] 同步）；`QEMU-rela-rbha-hi16-not-preserved`（rela 写目的保留高 16，同域，一并留意）
- spec `contracts/isa/spec.md §4.8`（rela：base=rb0[47:0]&~0xFFF + 偏移）、`§1.3`（rb0=PC+4 硬件维护）、`§3.1/§3.2`（ldo/sto）；`tools/opcodes.yaml`（rela 编码）
- LLVM 侧：`DADAOISelLowering.cpp`（GlobalAddress→Custom）、`MCTargetDesc/`（新 fixup_dadao_rela_hi/lo + R_DADAO_RELA_* + AsmBackend applyFixup + ELFObjectWriter，**参 DL-056b call fixup / DL-058a branch fixup 范式**）、`DADAOInstrInfo.td`（rela pattern）
- LLVM 22 范式：RISC-V `%pcrel_hi`/`%pcrel_lo`（auipc+addi/ld 物化 PC 相对地址）+ `RISCVMCExpr`/relocation
- 管道：`tests/lit/E2E/*.test`（objcopy 纳入 .data）、`~/DADAO-gem5/tests/dadao/gen_min_elf.py`（`data_segs` RW 段，`build_elf(binary, data_segs=[(vaddr,bytes)])`）、`tests/scripts/gen_trampoline.py`
- DL-061a（wyde 物化，若 rela 低位需大立即数）；DL-056b/058a（fixup 基建、R_DADAO_* 现有类型）

—— 通用验收/自审纪律见 DS-common（§5 反偷换：被测=真 llc 产物）与 DS.md §自审流程（subagent 代码级 · 本任务强制，**据 review 修完再交、别标已完成就返回、别跳自审**）。CodeGen 产物禁手搓；测试禁 grep-only / `|| true` / 全常量折叠（判别值运行时真跑，双后端都要真跑断言）。**这是多部件任务（QEMU+LLVM+管道），卡哪层如实报，别糊。**

---

## 架构师复核（部分完成·诚实，但功能未通）

**复核日期**: 2026-07-11 · ground-truth（重建 QEMU+llc + 端到端跑全局 + 查 .o 重定位）

### 已完成且真实
- **QEMU-rb0 无需改**：DS 正确发现 rela 的 rb0 早由 **DL-042d(5a32df7)** 修过（"commit 3e0e57c"是 DS 幻觉 hash，但结论对）。差分 AGREE(4-way)=200/DIVERGE=0，rb-ops case[4] 已 spec-correct 0x80001000。
- **GlobalAddress ISel 编译成功**：`load @g → rela rb8, g; ldo rd31, rb8, 0`（不再崩）。lit 15/15。
- DS **诚实报部分完成**，没造假、没门槛游戏、没跳过阻塞——好行为。

### 功能未通（真块）
- **端到端全局 load 返回 0 不是 42**：rela 指令字节 `4820 0000`（imm18=0）。
- **根因比"需链接器"更欠**：`readelf -r` 显示 **.o 无任何重定位条目**——DS 的 rela fixup **没为跨段符号 @g 发 ELF 重定位**，imm18 被静默填 0。故 mini-linker 也无从解析（没有"要解析什么"的记录）。
- `gen_flat_binary.py` 只字节拼接 .text+.data，不解析重定位（也没得解析）。
- 完成区"MC fixups 完成"过乐观：跨段不发重定位。

### 两条完成路线（架构师定夺）
- **路线 A（globals 放 .text，同段 rela，推荐）**：全局数据 emit 进 .text（同 code 段），llvm-mc **汇编期解析同段 rela**（如 call/branch，无需重定位/链接器）；整镜像加载为 RW（QEMU -kernel 已 RW；gem5 gen_min_elf 段标 RW）。**最省**，绕开重定位+链接器全部机器。风险：写全局需镜像可写（确认 gem5 段 p_flags）。
- **路线 B（.data + 重定位 + mini-linker）**：修 MC 层为跨段符号发 R_DADAO_RELA_* 重定位 + Python mini-linker 按 .data 布局解析 patch + .data 独立 RW 段双后端。更通用但机器多得多。

### 判决
**部分完成**（ISel 就绪、rb0 已现成、诚实报块）。功能未通不提交。→ **DL-061c 走路线 A**（globals-in-.text 同段解析 + RW 镜像 + 真全局读写 E2E），最快让全局跑通。
