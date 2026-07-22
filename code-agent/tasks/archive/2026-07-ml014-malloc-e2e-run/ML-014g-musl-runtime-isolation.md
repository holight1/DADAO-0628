# ML-014g：隔离 ML-014f 的 musl malloc runtime 链路

**执行环境**：本地 subagent worker；仅做诊断，不进入主线测试

**状态**：已完成诊断（2026-07-18；独立 reviewer Accepted）

## 背景

ML-014e 已证明 QEMU/gem5 的 mmap arena backing、真实写读和 syscall probe 正常。
ML-014f 在沿用当前 musl `-O0/optnone` 候选构建后，仍出现 QEMU 130/挂起、gem5
exit=0 且 `rd31=-38`，无法判断断点在 malloc、内存访问、free、stdio 输出还是 exit
链。本任务先隔离运行链，暂不追究优化级别 workaround 的长期合理性。

## Ownership

- 允许修改：`.work/ML-014g-runtime-isolation/` 下的临时 C 输入、构建脚本、ELF、
  输出和诊断报告；本任务 MD 的完成区和审阅记录。
- 可以使用当前 `.work/source/musl` 的候选普通 commit `8ecf6f6e` 及其已生成构建产物；
  不得 reset/rebase，不得修改 LLVM/QEMU/gem5/contracts/manifests、主仓库 musl
  patch series、`docs/issues.yaml`、主测试目录或 ML-014a 原文。
- 不得使用 `|| true` 掩盖失败。诊断命令允许用 `timeout` 终止挂死，但必须记录
  timeout 退出码和 backend 原始输出。

## 诊断阶梯

为每个阶段生成独立静态 ELF，并分别运行 QEMU 与 gem5；阶段成功统一返回 42，失败
使用独立非 42 码：

1. `malloc(131052)`，只检查非 NULL，不写内存、不 free；
2. 单次 malloc 后写读首字节/末字节，不 free；
3. 单次 malloc 后执行 `free`，不调用 stdio；
4. 两次不同大小 malloc，写读并 free；
5. 在阶段 4 成功后使用非变参 `puts` 输出 marker，再 return 42。

每阶段必须避免 printf/varargs；阶段 5 才允许 `puts`。记录“最后一个成功阶段”，并
通过 ELF/objdump 或 syscall trace 证实 `__mmap` 使用 syscall 222、返回值走 rd31。
对 QEMU/gem5 使用硬 timeout，区分 hang、错误 exit 和正常 exit。

## 验收

- `.work/ML-014g-runtime-isolation/report.md` 给出每阶段、每 backend 的命令、退出码、
  timeout 状态和关键输出；不得只写“挂了”。
- 至少确定断链属于：malloc 返回、mmap syscall、真实 arena 读写、free、stdio/puts、
  或 exit 链中的一个（若仍无法唯一定位，给出最小剩余假设）。
- 不修改主线文件；`git status` 只保留用户原有 ML-014a 未跟踪记录。
- 完成区必须有 subagent 自审；随后由独立 reviewer 复查诊断结论和关键复跑。

## 完成区

**状态**：已完成（诊断收口；ML-014f 仍为阻塞，未完成）

**诊断产物**：

- `.work/ML-014g-runtime-isolation/stage{1..5}_*.c`：5 个独立 C 输入。
- `.work/ML-014g-runtime-isolation/stage{1..4}.{o,elf,bin}`：阶段 1–4 独立静态 ELF 及构建产物。
- `.work/ML-014g-runtime-isolation/run_diagnosis.sh`：构建、静态检查和双 backend 硬 timeout 运行脚本。
- `.work/ML-014g-runtime-isolation/report.md`：完整命令、原始输出、退出码和分类更正。

**阶段结果**：

所有阶段 1–4 的 compile/link/objcopy 命令均为 `rc=0`（表示 `COMMAND_PASS`，不是 backend 成功）；backend 使用 `timeout 15s`，本轮没有出现 `rc=124` timeout。

| 阶段 | QEMU | gem5 | 结论 |
|---|---:|---:|---|
| 1 `malloc(131052)` only | `rc=11` | `rc=42` | QEMU 在 malloc 返回检查处失败；gem5 完成 exit=42。 |
| 2 malloc 后首/尾字节写读 | `rc=12` | `rc=134` | QEMU 仍在 malloc 返回检查处失败；gem5 输出 page-table fault，访问 `0xffffffffffff`。 |
| 3 malloc + free | `rc=129` | `rc=129` | 两 backend 均为 MALIGN-class failure，未到 exit=42。 |
| 4 两次 malloc + 写读 + free | `rc=129` | `rc=129` | 两 backend 均为 MALIGN-class failure，未到 exit=42。 |
| 5 stage 4 + 非变参 puts + return 42 | 未运行 | 未运行 | 链接 `rc=1`：`undefined symbol: puts`；当前归档 `libc.a` 没有归档 `puts`，因此没有 stage-5 ELF。 |

静态检查在阶段 1–4 ELF 中确认：`llvm-nm` 可见 `__mmap`/`malloc`（阶段 3/4 另有 `free`）；反汇编可见 `addi rd16, rd0, 222`、`trap 2, 0`，并在 trap 后以 `sto rd31, ...` 保存 syscall 返回值。该证据确认本轮确实走 syscall 222、返回链使用 `rd31`，但不把它误判为运行时成功。

**阻塞结论**：

- 没有共同的双 backend 成功阶段；gem5 最后成功为 stage 1，QEMU 无成功阶段。
- 最小剩余假设是 QEMU 与 gem5 对 malloc/mmap 返回链存在差异；gem5 stage 2 还暴露了无效返回值随后被用于实际读写的路径，stage 3/4 则进入 free 相关的 MALIGN-class failure。
- stdio/puts 未被执行到，stage 5 的未归档符号是独立的构建/归档边界，不可据此推断 puts runtime 行为。
- 本任务不修改实现，不宣称 ML-014f 或 ML-014a 完成；下一步若继续，应另开实现修复任务处理 malloc/mmap backend 差异和临时 libc 归档覆盖。

## 审阅记录（subagent）

> 记录每个阶段的真实命令/退出码、finding 处置和判决；不得将诊断通过误写成 ML-014f 已完成。

### Subagent 自审（2026-07-18）

- 逐阶段核对 `.work/ML-014g-runtime-isolation/report.md`：阶段 1–4 的编译、链接、objcopy 均为真实 `rc=0`；backend 结果按 QEMU/gem5 分列，没有忽略失败码或用 timeout 伪造成功。
- 复核诊断脚本的分类语义：构建命令 `rc=0` 改记为 `COMMAND_PASS`；backend 只有真实 `rc=42` 才记为 `SUCCESS_EXIT_42`，`rc=124` 才记为 `TIMEOUT`，其余保持错误退出。
- 复核阶段 5：链接器明确报告 `undefined symbol: puts`，没有生成 ELF，因此没有运行 backend；未把该阶段写成通过，也未补改主仓库归档或实现。
- 复核静态证据：阶段 ELF 的 `__mmap` 反汇编包含 syscall 222 和 trap 后 `rd31` 保存路径；该证据只用于定位调用链，不替代双 backend 验收。
- **自审判决：ML-014g 诊断记录完整；ML-014f/ML-014a 保持未完成。**

### 独立 reviewer 复核（2026-07-18）

**复核范围与限制**：仅检查本任务的 `report.md`、`run_diagnosis.sh`、阶段
1–5 输入和阶段 1–4 ELF；未修改 `.work` 诊断实现、主测试、musl series、后端、
issues 或其他文件。未重复运行整套可能耗时的 backend 命令。

**证据核对**：

- 阶段 1：QEMU `rc=11`，gem5 `rc=42`；与 stage 1 的 `p ? 42 : 11` 一致。
- 阶段 2：QEMU `rc=12`，gem5 `rc=134`；gem5 原始输出包含访问
  `0xffffffffffff` 的 page-table fault，不能记为成功。
- 阶段 3：QEMU/gem5 均 `rc=129`，原始输出为 `SIM_END: MALIGN code=129`。
- 阶段 4：QEMU/gem5 均 `rc=129`，原始输出同为 MALIGN-class failure。
- 阶段 5：compile `rc=0`，link `rc=1`，错误为 `undefined symbol: puts`；未生成
  ELF，因此两个 backend 均正确标记为未运行。独立用 `llvm-nm` 检查当前归档
  `libc.a` 未发现 `puts` 符号。
- 脚本对 backend 使用 `timeout 15s`；`rc=124` 才分类为 `TIMEOUT`，`rc=42` 才是
  `SUCCESS_EXIT_42`，其余保持 `ERROR_EXIT`。本轮实际没有 `rc=124`，所以不存在把
  hang 伪报为错误退出或成功的问题。
- 对阶段 1–4 ELF 独立复核 `llvm-nm`/`llvm-objdump`：均可见 `__mmap`；其 mmap
  路径包含 `addi rd16, rd0, 222`、随后 `trap 2, 0`，trap 后通过 `rd31` 使用或
  保存返回值（阶段 3/4 还可见 `free`）。这证明诊断 ELF 走的是 syscall 222/`rd31`
  链路，但不把静态证据误作 runtime 成功。

**Findings**：

1. `report.md` 的逐条构建记录仍显示 `rc=0` 后为 `classification=ERROR_EXIT`，
   与当前 `run_diagnosis.sh` 已修正的 `rc=0 → COMMAND_PASS` 语义不一致。原始
   `rc=0`、backend 结果表和报告的分类更正段仍足以判断构建成功；这是记录一致性
   问题，不影响阶段 1–4 backend 结论，也未发现脚本用 `|| true` 掩盖失败。
2. 阶段 3/4 的 `MALIGN` 证明 malloc/free 组合路径仍失败，但不能仅凭现有阶梯
   唯一归因于 `free`；报告已保留这一最小剩余假设，没有过度宣称根因。
3. `puts` 只得到归档/链接边界的失败证据，尚未得到 puts runtime 行为证据；报告
   正确将其与 ML-014f 的 runtime 结论分开。

**独立 reviewer 判定**：Finding 1–3 均已在现有记录中被明确揭示或正确限定，
没有阻断诊断收口。**诊断 Accepted；ML-014f 仍 Blocked，ML-014a 仍未完成。**
