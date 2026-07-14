# DG-007c/DL-066b: picolibc goal①/② 双后端真正复验（gem5 补断言）

**执行环境**: 本地 subagent（lit 测试 + 双后端验证）

**状态**: 待执行

**前置**：本轮全部已完成并合入的修复——DG-007b（gem5 堆区 PT_LOAD 覆盖）、DL-066a（间接调用不再误用 rb0）、ML-005a（libc.a 解锁重建，DL-066a 修复已烘进）、DL-067b（string 函数 BR_CC 崩溃修复，picolibc 干净重建可用）。四个修复叠加后，`printf_hello.test`/`malloc_hello.test` 理论上首次具备在 gem5 SE 上真正跑通的全部前提条件。

## 背景

`tests/lit/E2E/printf_hello.test`（goal①）和 `tests/lit/E2E/malloc_hello.test`（goal②）目前都只有 QEMU 断言，gem5 因本轮修复的两个独立 bug（`gem5-se-heap-not-covered-by-elf-segment`、`codegen-indirect-call-rb0-misuse`）而被跳过。这两个 issue 均已 closed。

## 做什么

1. **重建 libc.a**：确认 `.work/picolibc/build-dadao/libc.a` 是用当前（含 DL-066a + DL-067b 修复）的编译器构建的最新产物（若不确定，`rm -rf .work/picolibc/build-dadao && make build-picolibc` 干净重建一次）。
2. **`printf_hello.test` 补 gem5 断言**：仿照 `align_strfn.test`/既有双后端测试的写法，加一行 `%gem5 %gem5_se %t.elf`（直接用 `ld.lld` 产出的真实 ELF，不经 `gen_min_elf`——参考 `align_strfn.test` 已验证过这条路径对纯栈程序可行；`printf_hello.c` 不涉及堆，理论上不会撞上 `gem5-se-heap-not-covered-by-elf-segment`）+ 输出断言（gem5 侧同样 `grep -c "hello, dadao"`）。
3. **`malloc_hello.test` 补 gem5 断言**：同样加 gem5 RUN 行 + `grep -c "OK OK2"` 断言（`malloc_hello.c` 涉及堆，这条路径现在应该被 DG-007b 覆盖）。
4. **真跑双后端**，如实报告结果——若仍然因为某个未知原因跑不通，**不要用绕过手段（`|| true`/弱化断言/删掉 gem5 行装作没加过）**，如实记录卡在哪、报告架构师，交给后续任务。若两个测试都真正双后端通过，这是 picolibc goal①/② 首次真正完整收官的时刻，值得在完成区明确写出来。

## 约束

- 禁止 `|| true`、grep-only 弱断言、或任何形式的"让测试看起来过"的手段（这是本仓库反复强调过的红线，见 memory `feedback_ds_task_workflow`）。
- 若某个测试暂时还是跑不通，如实标注为"gem5 skipped — <具体原因/issue>"，不要删掉尝试的痕迹或假装没做这件事。
- 不回归：E2E 全绿（除已知的 `syscall_hello.test` 无关失败）、四方 AGREE(3-way)=200/DIVERGE=0、Sail AGREE(4-way)=200。

## 验收（架构师亲跑）

```bash
cd ~/DADAO-0628
rm -rf .work/picolibc/build-dadao && make build-picolibc
llvm-lit -v tests/lit/E2E/printf_hello.test tests/lit/E2E/malloc_hello.test 2>&1 | grep -E "PASS|FAIL"
llvm-lit tests/lit/E2E/ 2>&1 | tail
python3 tools/run_differential.py 2>&1 | tail -3
```

**判别强调**：若声称"双后端通过"，必须是真实两条 RUN 行都跑到、都断言正确输出，不是"加了 gem5 行但用宽松断言蒙混过关"。

## 参考指针

- `tests/lit/E2E/align_strfn.test`（已验证的、真实 ELF 直接喂 gem5 SE 的写法范式，可参考）
- DG-007a/b、DL-066a、ML-005a、DL-067b 完成区（本任务依赖的全部前置修复）
- `docs/issues.yaml` 的 `gem5-se-heap-not-covered-by-elf-segment`（closed）、`codegen-indirect-call-rb0-misuse`（closed）条目

—— 自审见 DS.md §自审流程同等标准（subagent 自己复核，逐条 finding + 判决）。**如实报告，不确定能不能双后端通过就老实去试，试出来是什么结果就报告什么结果**。
