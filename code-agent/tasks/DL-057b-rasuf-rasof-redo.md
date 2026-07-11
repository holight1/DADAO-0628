# DL-057b: QEMU 冷 ret RASUF 修复 + RASOF/RASUF 用 E2E 真测（DL-057a 重做）

**执行环境**: 本地 DS · DADAO-0628（QEMU target/dadao + E2E + 差分）

**状态**: 待执行

**前置**: DL-057a 打回（见其 `## 架构师复核（打回）`）。已保留：嵌套 E2E lit（`nested_call.test` 双后端 42）、Sail 源码 `F_RASOF/F_RASUF=0x84/0x85`、ADR-0004 §D5 pin `RASOF=0x84/RASUF=0x85`、3 runner FAULT_CODES、gem5 faults.hh。**已撤回**：两条单指令 RASOF/RASUF 向量（曾令 DIVERGE 0→2）。

---

## 为什么重做
DL-057a 想用**单指令向量**测 RASOF/RASUF，行不通且宣告了假完成：
- **RASOF** 需**满 RAS**，但四方 harness 都不能经 `input_state.ra` 预置 RAS（interp `build_state` 只读 rd/rb/memory）→ interp 得 None，向量 dead-on-arrival。
- **RASUF** 冷栈不需预置，interp 正确抛 RASUF，但 **QEMU 冷 bare-ret 实测 0x82(ILLI) 而非 0x85**——即 issues.yaml 早记的 `RASUF-cold-ret` bug 至今未修（DL-056c 只修了非冷嵌套 call/ret）。DL-057a 只 grep 看源码就填「QEMU 0x85 ✓」，且 patch 0012 谎称重生成（实仍 0x86/0x87）。

**结论**：RASOF/RASUF 的正确载体是 **E2E 程序**（真触发满栈/冷栈），不是单指令向量。

## 目标

1. **根因 + 修 QEMU 冷 ret → RASUF(0x85)**：定位为何 bare `ret`（冷 RAS）没落到 `helper_ras_pop` 的 `ref==0 → 0x85` 分支、反而塌成 ILLI(0x82)（查 `trans_ret` 是否真调 ras_pop、异常下游是否被 halt-rd0 覆盖）。修到**冷 ret 精确抛 RASUF、退出码 0x85**。
2. **重生成 patch 0012** 到含 `0x84/0x85` 的最终 helper.c（format-patch，覆盖 `components/qemu/patches/0012-qemu-ras-stack.patch`，series 不变，`git am` 复现 = 开发树）。**架构师会核 patch 内不得再有 0x86/0x87。**
3. **RASUF E2E 用例**（真 llc/汇编产物，禁手搓 CodeGen 产物）：一个 `crt0` 直接 `ret`（无配对 call，冷 RAS）→ 双后端 **exit=0x85(=133)**；入 lit E2E 套件（QEMU+gem5）。
4. **RASOF E2E 用例**：深嵌套调用溢出 RAS（RAS 深度 63，需足够层数触发 overflow）→ 双后端 **exit=0x84(=132)**；入 lit E2E。用真 llc 产物（如递归 C/IR）或最小汇编驱动，说明触发层数依据。
5. **诚实差分**：`tools/run_differential.py` 跑完 **DIVERGE 必须 = 0**；若 RASUF 仍想留单指令向量（冷栈 interp+QEMU 可 2-way），需真 AGREE 才留，**否则不许加会 DIVERGE 的向量**；gem5/sail 若结构性无法向量注入则如实 SKIP（注明理由），不得把 DIVERGE 粉饰成 abstain。

## 约束
- QEMU 只改 `target/dadao`，语义按 spec §5.6（RASUF/RASOF 精确、RA 不改）。
- **不回归**：AGREE(4-way)=198 / DIVERGE=0 / HARNESS=6、现有 lit E2E（含 `nested_call` 4/4）、DL-056c 嵌套 42 全绿。
- E2E 被测对象=真编译/汇编产物（DS.md §工作规则 禁手搓 CodeGen 产物）。RASUF/RASOF 触发不了就如实报卡在哪层，别改测例绕过（DS-common §5）。
- **本任务有代码改动 → DS 必须开 subagent 做代码级自审**（DS.md §自审流程），把 `## 审阅记录（subagent）` 写进本 md 再交回。DL-057a 因跳过自审 + 假声称被打回，勿重蹈。

## 验收（架构师亲自复跑）
```bash
cd ~/DADAO-0628
(cd .work/source/qemu/build && ninja qemu-system-dadao 2>&1 | tail -1)
grep -c "0x86\|0x87" components/qemu/patches/0012-qemu-ras-stack.patch   # 期望 0（patch 已重生成）
python3 tools/run_differential.py 2>&1 | tail -3                          # DIVERGE=0，AGREE(4-way)=198 不回归
llvm-lit -v tests/lit/E2E/ 2>&1 | tail -8                                 # nested_call + rasuf + rasof 全 PASS，双后端码正确
```

## 参考指针
- DL-057a `## 架构师复核（打回）`（全部证据）；issues.yaml `RASUF-cold-ret`（已标 ground-truth 确认仍坏）、`rasof-rasuf-exit-code-unpinned`
- QEMU：`.work/source/qemu/target/dadao/`：`translate.c` `trans_ret`（是否真调 ras_pop）、`helper.c` `helper_ras_pop`（`ref==0 → 0x85` 分支已在，冷 ret 为何到不了是根因点）、异常/halt 下游路径；patch 生成参 0009~0012 + `series`
- E2E：`tests/lit/E2E/nested_call.test`（现成范式：llc→.s→+crt0→bin→QEMU+gem5 断言退出码）、`tests/scripts/crt0.s`、`gen_e2e_binary.py`、`~/DADAO-gem5/tests/dadao/{gen_min_elf.py,dadao_se.py}`
- spec §5.4/§5.5/§5.6（call 压栈 / ret 弹栈 / RegRAS refcount + RASOF overflow + RASUF underflow，精确故障）；`tools/dadao_interp.py` `_ras_push/_ras_pop`（正确算法，别抄实现、对语义）
- ADR-0004 §D5（RASOF=0x84/RASUF=0x85 退出码定义）

—— 通用验收/自审纪律见 DS-common（§5 反偷换）与 DS.md §自审流程（subagent 代码级 · 本任务强制）。
