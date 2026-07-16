# ML-004b: llvm-test-suite 失败用例排查 + 扩大覆盖 + 第一轮通过报告

**执行环境**: 本地 subagent（CodeGen 排查 + lit 测试扩充）

**状态**: 通过（架构师复核，含补登记 3 个遗漏 issue）

**前置**：ML-004a（首批 8 个 SingleSource 用例布线，3/8 通过）、DL-068b（修复全局地址偏移丢失的 miscompile，让 1/5 此前失败的用例转为通过，另 4 个转为新的独立故障模式）。用户明确要求"第一轮的 llvm-test-suite 测试通过报告"。

## ⚠️ 硬性约束（与 DL-068b 相同，必读）

**禁止对 `.work/llvm`（或任何 `.work/<component>`）做 `git rebase`/`git am` 重放整条历史/`git reset` 之类改写既有 git 历史的操作**。只允许在当前 HEAD 基础上做普通的、追加式的新提交 + `git format-patch` 生成新 patch 加入 series（参照 DL-065a/DL-066a/DL-067b/DL-068b 的模式）。若排查中怀疑 patch series 有问题，如实报告，不要自己动手"验证"或"重建"。

## 背景

当前 `tests/lit/E2E/llvm-test-suite/` 下有 3 个通过的用例（`bitops`/`minint`/`arrayresolution`）+ DL-068b 新验证通过的 `divrem`（原 ML-004a 挑选的 8 个里的一个，此前因 DL-068b 修的 bug 失败，现在应该已经能过，但尚未正式写成 lit `.test` 提交）。还有 4 个用例（`crc8.le`/`crc16.be`/`popcount-clz-ctz`/`divtest`）撞上了 DL-068b 完成区记录的**新的、独立**故障模式：3 个撞 MALIGN（退出码 0x81，双后端一致）、1 个双后端一致但返回值错误。

## 做什么

1. **补上 `divrem` 的 lit 测试**：DL-068b 已验证 `2006-02-04-DivRem.c` 双后端通过，正式写成 `tests/lit/E2E/llvm-test-suite/divrem.test`（仿照现有 3 个的范式）。
2. **排查 4 个失败用例**：
   - **MALIGN 的 3 个（crc8.le/crc16.be/popcount-clz-ctz）**：先确认是不是**合法的 spec 行为**——DADAO spec §3.1 要求 8 字节对齐访问，若这些测试里有非对齐的 load/store（比如对 `char[]`/`uint8_t` 数组做非 8 字节对齐的多字节读写，或者结构体打包访问），MALIGN 可能是**正确、预期**的行为，不是 bug，只是这些 llvm-test-suite 用例假设了 x86/宿主那种任意对齐访问的自由度，不适配 DADAO 的对齐约束。若确认是"用例本身对 DADAO 不适用"（不是 bug），如实记录为"该测试在 DADAO 上不适用"，不必勉强让它过。
   - **值错的 1 个（divtest）**：这个更像真 bug（双后端一致但算错，不是异常/故障）——用类似 DL-068b 的方法（缩小复现范围、debug trace）定位根因，如果能确认根因并且是小范围修复，可以修；如果发现是更大范围的问题，如实报告、记 issue，不强行在本任务内解决。
3. **扩大覆盖**：从 `.work/source/llvm-test-suite` 的 `SingleSource/UnitTests/`（或 `Benchmarks/`）再挑 **10-15 个**新的纯计算测试（不同类型：递归、数组、字符串处理不含 libc I/O、简单数学），布线运行，如实报告结果。
4. **产出"第一轮通过报告"**：汇总当前 `tests/lit/E2E/llvm-test-suite/` 目录下所有测试用例的通过/失败情况，做成一份清晰的表格（测试名/通过或失败/若失败注明原因分类：真 CodeGen bug / 合法 spec 行为不适用 / 其它），写入完成区。

## 约束

- 不为了让某个用例过而修改 CodeGen（除非确认是小范围、有把握的修复——若修了，要有反汇编/运行时判别性验证，不是"看起来编过了"就算）。
- MALIGN 若确认是合法行为，不要绕过（不要给测试加特殊对齐指令让它凑合过——如实标注"不适用于 DADAO 对齐模型"）。
- 不回归：E2E 全绿（含 `syscall_hello.test` 已知无关失败）、四方 AGREE(3-way)=200/DIVERGE=0、Sail AGREE(4-way)=200。

## 验收（架构师亲跑）

```bash
cd ~/DADAO-0628
llvm-lit -v tests/lit/E2E/llvm-test-suite/ 2>&1 | tail -30
llvm-lit tests/lit/E2E/ 2>&1 | tail
python3 tools/run_differential.py 2>&1 | tail -3
```

**判别强调**：完成区必须有一份清晰的"当前 llvm-test-suite 通过情况"表格（测试名/结果/失败原因分类），这是用户明确要的交付物；MALIGN 类的"不适用"判断需要有 spec 依据（引用 §号），不能凭感觉断定。

## 参考指针

- ML-004a 完成区（首批 8 个用例的选择理由 + 3/8 通过详情）
- DL-068b 完成区（全局地址偏移丢失修复 + 4 个剩余失败用例的故障模式初步分类）
- `contracts/isa/spec.md` §3.1（对齐访问要求，MALIGN 语义）
- `tests/lit/E2E/llvm-test-suite/*.test`（现有 3 个测试的封装范式）
- `.work/source/llvm-test-suite/SingleSource/`（测试源码所在）

—— 自审见 DS.md §自审流程同等标准（subagent 自己复核，逐条 finding + 判决）。**必须产出清晰的通过情况表格**；**严格遵守不碰 patch/git 历史的约束**。

---

## 架构师复核（2026-07-16，ground-truth）：通过

### 硬性约束遵守情况
- `.work/llvm` git log 确认仍停在 `778e62ed55f0`（DL-068b），无任何新提交/历史改动——严格遵守。

### 独立验证
- `llvm-lit -v tests/lit/E2E/llvm-test-suite/`：12/12 全部真 PASS（含 subagent 报告的所有新增用例）。
- 全 E2E 42/43（同一已知无关的 `syscall_hello.test` 失败）、四方 AGREE(3-way)=200/Sail AGREE(4-way)=200，不回归。
- **独立复现 `codegen-call-clobbers-gprb-not-declared` 的核心发现**：用 issue 里给出的 `rbreuse.c` 最小复现，host=36，DADAO(QEMU)=21——完全吻合报告。这是一个真实、系统性的寄存器分配正确性 bug（CALL 类指令未声明 RegMask/GPRB caller-saved 信息），影响面是"调用前算好一个地址值、调用后继续用"这一常见模式，值得后续专门任务修复。
- subagent 自己的 review 阶段纠正了初稿的一处不精确描述（`CALL_IIII`/`CALL_RRII` 都声明 `Defs=[RD31]`的说法有误，用 `llvm-tblgen -gen-instr-info` 生成物核实后订正为 `CALL_RRII` 根本不在寄存器分配阶段出现、真正的第二个受影响指令是 `CALL_PSEUDO_INDIRECT`）——这个自我纠错的严谨度值得肯定。

### 遗漏补登记
完成区报告里提到的扩充覆盖新发现的 3 个失败用例（`switch_stmt`/`misha_sum`/`sign_conversions`）在报告文字里说明了"不同于已知根因、未展开排查"，但没有写进 `issues.yaml`——已由架构师补登记为三个独立 open issue（`codegen-switch-dispatch-malign-in-callee`/`codegen-misha-sum-wrong-value-no-call`/`gem5-sign-conversions-backend-divergence`），确保这些发现不会只停留在对话记录里、后续任务能查到。

### 第一轮 llvm-test-suite 通过报告（用户要的交付物，汇总）

| 测试 | 结果 |
|------|------|
| bitops / minint / arrayresolution | PASS（ML-004a，QEMU-only） |
| divrem / bitwise_not / cast_bool / bad_load / sdiv_two / compare64_const / shorts_mask / load_shorts / fold_bug | PASS（双后端，ML-004b 新增） |
| crc8.le / crc16.be / popcount-clz-ctz / divtest / long_shifts / loopbug / loopbug2 / int_overflow | FAIL——同一根因 `codegen-call-clobbers-gprb-not-declared`（CALL 指令未声明 GPRB caller-saved RegMask，调用后复用陈旧地址值） |
| switch_stmt | FAIL——独立问题，疑似跳转表相关，`codegen-switch-dispatch-malign-in-callee` |
| misha_sum | FAIL——独立问题，无调用参与，`codegen-misha-sum-wrong-value-no-call` |
| sign_conversions | FAIL（gem5 独有）——双后端分歧，`gem5-sign-conversions-backend-divergence` |

**当前：12 通过 / 10 失败（收敛到 4 个独立 issue，其中 1 个已定位精确根因待修，3 个待排查）**。

**判定**：通过，提交。
